# Migrating from MockMvc to WebTestClient When Testing Spring Security WebFlux

> **Topic:** Spring Security - reactive → Migration and debugging → Migrating from MockMvc to WebTestClient. This lesson guides migrating HTTP and security tests from the Spring MVC/Servlet model to Spring WebFlux/Reactor while preserving the semantics of 401, 403, principal, role/scope, and response payload assertions.

## 1. When to Migrate and What to Change

**MockMvc** is the HTTP testing tool for the **Spring MVC/Servlet** stack: requests go through **DispatcherServlet**, Servlet Filters, and the corresponding security chain. **WebTestClient** is a test client usable in two ways: bound directly to an in-memory **WebFlux** application or issuing real HTTP calls to a running server. When migrating a module genuinely from Spring MVC to WebFlux, the test suite must execute through **WebFilter/Reactive SecurityWebFilterChain**, exercise **Publishers (Mono/Flux)**, and propagate security context via Reactor.

**Migrating test syntax does not mean the runtime has migrated**:

- An application still using **spring-boot-starter-web**, **DispatcherServlet**, and **HttpSecurity/SecurityFilterChain** can be called by WebTestClient over HTTP, but that does not turn the application into WebFlux.
- **MockMvcWebTestClient** is an adapter that lets you write WebTestClient-style assertions on top of MockMvc. It is a test-API transition step while still on Servlet, and does not prove reactive security filters are working.
- For a real WebFlux application, use **spring-boot-starter-webflux**, **ServerHttpSecurity/SecurityWebFilterChain**, controllers returning **Mono/Flux**, and security context living in **Reactor Context**.
- If both **spring-boot-starter-web** and **spring-boot-starter-webflux** are present, Spring Boot normally selects **Servlet/MVC** via its web application type auto-detection rules. Verify dependencies and runtime before rewriting all tests.

### Objectives Upon Completion

1. Distinguish Servlet testing from WebFlux testing.
2. Convert request builders, execution calls, and assertions from MockMvc to WebTestClient.
3. Migrate security tests from **SecurityMockMvcRequestPostProcessors** to **SecurityMockServerConfigurers**.
4. Write 200/401/403 tests and verify JWT claims/authorities inside the reactive pipeline.
5. Choose the right test scope: **@WebFluxTest**, **@SpringBootTest + bindToApplicationContext**, or real HTTP against a server.
6. Debug scenarios where tests pass "green" yet filters did not run, JWTs were not verified, Reactor context was lost, or streaming requests hung.

## 2. MockMvc → WebTestClient Comparison Table

| Scenario | MockMvc (Spring MVC) | WebTestClient (WebFlux) |
| --- | --- | --- |
| Controller slice test | **@WebMvcTest**, inject **MockMvc** | **@WebFluxTest**, inject or build **WebTestClient** |
| Full app without opening an HTTP port | **@SpringBootTest + @AutoConfigureMockMvc** | **@SpringBootTest**, **WebTestClient.bindToApplicationContext(context)**, **apply(springSecurity())** |
| Calling a real HTTP server | **MockMvc** is not a real HTTP client | **WebTestClient.bindToServer()** or auto-configured client at RANDOM_PORT |
| Building a GET | **mockMvc.perform(get("/api/me"))** | **client.get().uri("/api/me").exchange()** |
| Building a JSON POST | **post(...).contentType(...).content(...)** | **post().uri(...).contentType(...).bodyValue(...)** |
| Checking HTTP status | **andExpect(status().isOk())** | **expectStatus().isOk()** |
| Checking JSONPath | **andExpect(jsonPath("$.subject").value("alice"))** | **expectBody().jsonPath("$.subject").isEqualTo("alice")** |
| Checking headers | **andExpect(header().string(...))** | **expectHeader().valueEquals(...)** |
| Mock principal | **.with(user("alice"))** | **client.mutateWith(mockUser("alice"))** |
| Mock JWT | **.with(jwt())** | **client.mutateWith(mockJwt())** |
| Mock CSRF | **.with(csrf())** | **client.mutateWith(csrf())** |
| Security test support | **SecurityMockMvcRequestPostProcessors** | **SecurityMockServerConfigurers** |
| Async results | **asyncDispatch(...)** in certain MVC scenarios | **exchange()**, **returnResult(...)**, **StepVerifier** for Flux/Mono |
| Reactive method security | Not part of pure Servlet MockMvc | Executes on Reactor Context with **@EnableReactiveMethodSecurity** when enabled |

The easiest pair to confuse is **.with(jwt())** and **.mutateWith(mockJwt())**. Both come from **spring-security-test**, yet belong to different configuration branches and are not interchangeable drop-in APIs.

## 3. Before Editing Tests: Verify Runtime and Behavior Contracts

Build a checklist for each existing endpoint:

- **Routes and HTTP methods:** preserve paths, query params, status codes, media types, and response structures if the migration does not alter the API contract.
- **Permissions:** distinguish anonymous, authenticated without required authority, JWT with required scope, and different principals or tenants.
- **Errors:** confirm expected statuses/bodies for 401 (unauthenticated), 403 (forbidden), 400 (invalid payload), and 404 (not found/not visible).
- **CSRF/session:** stateless Bearer token APIs differ from cookie-based login apps; never disable CSRF just to make a test turn green.
- **Async behavior:** controllers returning **Mono/Flux** must be subscribed to by the WebFlux test runtime; never call **block()** inside handlers to mimic Servlet.
- **Controller dependencies:** slice tests may mock services; integration tests use real beans to prove WebFilter → controller/service wiring works.
- **JWT source:** mock JWT only supplies an **Authentication** to verify internal behavior; it does not replace signature/issuer/audience/expiry verification over real HTTP.

Once these contracts are clear, migrate in two passes: verify HTTP/security behavior inside the WebFlux application context, then verify real-token scenarios against a server and trustworthy IdP/decoder.

## 4. Complete Example: Spring Boot 3.3.x, Java 17+, Spring Security WebFlux

The example below runs an **in-memory WebFlux application context**, protects two endpoints with `SecurityWebFilterChain`, and tests security with **mockJwt()**. Class names and paths are consistent; create the files following this layout:

~~~text
settings.gradle
build.gradle
src/main/java/example/migration/WebfluxMigrationApplication.java
src/test/java/example/migration/WebfluxMigrationSecurityTest.java
~~~

Versions are pinned for this Java 17 example; real projects should align versions with their build and dependency management.

**settings.gradle**

~~~groovy
rootProject.name = 'webflux-security-migration'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This demo uses only **starter-webflux**, never adding **starter-web**. The test suite uses Spring Test, JUnit Jupiter, and Spring Security Test. **@MockBean** in the test snippet matches the pinned Spring Boot 3.3.x version here; on newer versions, check the replacement API for your project version.

**src/main/java/example/migration/WebfluxMigrationApplication.java**

~~~java
package example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebfluxMigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxMigrationApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class WebSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Suitable only for a cookie-free Bearer JWT API demo.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/me")
                        .hasAuthority("SCOPE_profile.read")
                        .pathMatchers(HttpMethod.POST, "/api/notes")
                        .hasAuthority("SCOPE_notes.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}

record PublicView(String message) {}
record ProfileView(String subject, String tenant) {}
record NoteRequest(String text) {}
record NoteReceipt(String createdBy, String tenant, String text) {}

@RestController
@RequestMapping("/api")
class DemoApiController {
    @GetMapping("/public")
    Mono<PublicView> publicEndpoint() {
        return Mono.just(new PublicView("public-ok"));
    }

    @GetMapping("/me")
    Mono<ProfileView> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(new ProfileView(
                jwt.getSubject(),
                jwt.getClaimAsString("tenant_id")));
    }

    @PostMapping("/notes")
    Mono<NoteReceipt> addNote(
            @RequestBody Mono<NoteRequest> body,
            @AuthenticationPrincipal Jwt jwt) {
        return body.map(request ->
                new NoteReceipt(
                        jwt.getSubject(),
                        jwt.getClaimAsString("tenant_id"),
                        request.text()));
    }
}
~~~

The application demonstrates using **@AuthenticationPrincipal Jwt** in a reactive controller. **/api/public** allows anonymous access; **/api/me** requires **SCOPE_profile.read**; **POST /api/notes** requires **SCOPE_notes.write**. The POST endpoint returns simulated data and **does not persist to a DB**; the example focuses on proving HTTP security test migration, not transaction/persistence testing.

**Security note:** in a real multi-tenant system, you must validate **tenant_id** from an authenticated JWT and enforce it in queries/services; reading the claim here only demonstrates testing the principal. If browser cookies/sessions are used, re-evaluate CSRF, logout, and session management; do not copy **csrf(...disable)** unconditionally.

### 4.1 Migrated Test: WebTestClient + mockJwt()

**src/test/java/example/migration/WebfluxMigrationSecurityTest.java**

~~~java
package example.migration;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class WebfluxMigrationSecurityTest {

    @Autowired
    ApplicationContext context;

    // Only to bootstrap the OAuth2 Resource Server filter chain in tests.
    // mockJwt() supplies an in-memory SecurityContext per request.
    @MockBean
    ReactiveJwtDecoder jwtDecoder;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    private WebTestClient asJwt(
            String subject, String tenant, String scope) {
        return client.mutateWith(mockJwt()
                .jwt(jwt -> jwt
                        .subject(subject)
                        .claim("tenant_id", tenant))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_" + scope)));
    }

    @Test
    void publicEndpointWorksWithoutToken() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("public-ok");
    }

    @Test
    void anonymousRequestGets401() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedWithoutScopeGets403() {
        asJwt("alice", "tenant-a", "other.read")
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void correctJwtScopeReachesController() {
        asJwt("alice", "tenant-a", "profile.read")
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice")
                .jsonPath("$.tenant").isEqualTo("tenant-a");
    }

    @Test
    void writeRequiresWriteScope() {
        asJwt("alice", "tenant-a", "profile.read")
                .post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteRequest("first note"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void allowedWriteUsesAuthenticatedPrincipal() {
        asJwt("alice", "tenant-a", "notes.write")
                .post()
                .uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteRequest("first note"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.createdBy").isEqualTo("alice")
                .jsonPath("$.tenant").isEqualTo("tenant-a")
                .jsonPath("$.text").isEqualTo("first note");
    }

    @Test
    void ClientTenantHeaderCannotOverrideJwtClaim() {
        asJwt("alice", "tenant-a", "profile.read")
                .get()
                .uri("/api/me")
                .header("X-Tenant-Id", "tenant-b")
                .header("X-User-Id", "bob")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice")
                .jsonPath("$.tenant").isEqualTo("tenant-a");
    }
}
~~~

**Run:**

~~~bash
gradle test
~~~

If the project already has a Gradle Wrapper compatible with the Boot version:

~~~bash
./gradlew test
~~~

On Windows PowerShell you can use **gradlew.bat test**. **7 test cases** are expected to pass when the fixture is set up properly and the environment has compatible dependencies and JDK. To inspect test failures, check the Gradle report at **build/reports/tests/test/index.html**. This is a **fixture expectation**, not a claim that tests have already been run on the learner's machine.

### 4.2 Why This Test Setup Works

- **@SpringBootTest** loads the actual filter chain, controller, and context of the demo; **WebEnvironment.MOCK** opens no external HTTP port.
- **bindToApplicationContext(context)** binds WebTestClient to the in-memory handler chain; requests are dispatched by Spring WebFlux.
- **apply(springSecurity())** attaches Spring Security test support for WebFlux request binding so **mockJwt()** mutations are properly applied by the filter.
- **@MockBean ReactiveJwtDecoder** satisfies the OAuth2 Resource Server bean dependency at bootstrap; the test does not perform JWT signature verification.
- **mockJwt().jwt(...)** builds a principal with subject and tenant claims; **authorities(...)** grants the actual authorities checked by **hasAuthority**.
- **exchange()** executes the request/subscription pipeline; **expectStatus/expectBody** assert both security outcomes and controller responses.
- Each test creates a tailored **mutateWith(...)** client variant per request instead of writing a global Authorization state that could leak one test's principal into another.

MockJwt **does not prove** that the decoder accepts valid tokens or rejects invalid signatures, wrong issuers, wrong audiences, expired tokens, or unknown `kid`s. To verify those, you must run decoder tests and real signed-Bearer-token requests in an integration environment.

## 5. Comparing the Same Case Before and After

Suppose the legacy test used Servlet Spring Security Test:

~~~java
// Spring MVC + MockMvc syntax example (do not add to the WebFlux demo project).
mockMvc.perform(get("/api/me")
        .with(jwt()
                .jwt(jwt -> jwt.subject("alice")
                        .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_profile.read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject").value("alice"));
~~~

After migrating to WebFlux, the same test intent:

~~~java
// Place in a test configured with WebTestClient and springSecurity().
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice")
                .claim("tenant_id", "tenant-a"))
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_profile.read")))
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.subject").isEqualTo("alice");
~~~

**Observation:** both verify scope/claim logic with a simulated `Authentication`. The WebFlux version exercises **SecurityWebFilterChain** and reactive handlers when backed by a true WebFlux app. Swapping those syntax lines without migrating and re-testing the **runtime SecurityFilterChain → SecurityWebFilterChain** can leave you testing the wrong stack.

## 6. Choosing Test Scope: Slice, Full Context, and Real HTTP

### 6.1 @WebFluxTest: Fast, Controller-Focused

Use **@WebFluxTest(controllers = DemoApiController.class)** to load a WebFlux slice. When testing controller security, import **WebSecurityConfig** if the slice does not auto-load custom configuration; provide a mock **ReactiveJwtDecoder** and **@MockBean** collaborators for the controller. Purpose-built skeleton example reusing classes from Section 4:

~~~java
@WebFluxTest(controllers = DemoApiController.class)
@Import(WebSecurityConfig.class)
class ApiControllerSliceTest {
    @Autowired ApplicationContext context;
    @MockBean ReactiveJwtDecoder jwtDecoder;

    @Test
    void authorizedProfile() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient().build();

        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice")
                        .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                        "SCOPE_profile.read")))
                .get().uri("/api/me").exchange()
                .expectStatus().isOk();
    }
}
~~~

This is an **additional skeleton**, requiring JUnit/Spring imports and the demo classes provided earlier; do not treat it as a standalone Java file. Not every **@Configuration** or bean in an application is loaded into a slice. When a controller calls real services, mock them with **@MockBean** or import beans intentionally, and decide clearly whether the test targets HTTP protection or business logic.

### 6.2 @SpringBootTest + bindToApplicationContext: In-Memory WebFlux Testing

Use this when you need real wiring across beans, filters, controllers, and services inside one context, while optionally mocking external dependencies such as databases or IdPs. This is the full path shown in Section 4, well suited for testing **SecurityWebFilterChain**, reactive principals, and endpoint contracts without network dependencies.

**In-memory context execution differs from real network execution:** tests may bypass the decoder with `mockJwt` to focus on authorization. Do not treat those results as proof of production issuer/audience or TLS settings.

### 6.3 @SpringBootTest(RANDOM_PORT): Real HTTP Testing

Use **@SpringBootTest(webEnvironment = RANDOM_PORT)** with **@AutoConfigureWebTestClient**, or create **WebTestClient.bindToServer().baseUrl(...)**, to send real HTTP requests to a live server. In this mode, WebFlux security test's `mockJwt` is a local mutation on an application-context-bound client; it **does not send Authentication over the wire** and cannot substitute for a Bearer token. You must send **Authorization: Bearer ...** with a real JWT signed by a test IdP/key or a valid opaque token for your test IdP so the Resource Server decoder/introspector actually executes.

Here is the core difference:

~~~text
A. Context-bound:
   WebTestClient → test WebFilter(mockJwt) → SecurityWebFilterChain → Controller
   Authentication is attached in the test; no real JWT is verified.

B. Real HTTP:
   WebTestClient → TCP/HTTP → Reactor Netty server
                 → SecurityWebFilterChain → JwtDecoder/Introspector
                 → Controller
   The Authorization header must carry a real fixture credential.
~~~

Never take an HTTP 200 from a context-bound client as proof that production JWT signatures are verified. Nor should you inject fake principals via **X-User-Id** or **X-Tenant-Id** headers without a trusted gateway-to-backend contract.

## 7. Migrating Common Authorization Test Patterns

### 7.1 User/Role vs. JWT/Scope Differences

WebFlux supports both:

~~~java
// When the endpoint only requires authenticated or ROLE_USER.
client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/api/user").exchange()
        .expectStatus().isOk();
~~~

~~~java
// When the endpoint checks SCOPE_profile.read from a JWT.
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice"))
        .authorities(new SimpleGrantedAuthority("SCOPE_profile.read")))
        .get().uri("/api/me").exchange()
        .expectStatus().isOk();
~~~

These are **illustrative snippets** requiring matching endpoints and configuration; **/api/user** does not exist in the Section 4 demo. **mockUser()** creates a username/password-style `Authentication` with a matching principal, so a controller expecting **@AuthenticationPrincipal Jwt** should not be tested with `mockUser()`. Conversely, **mockJwt()** fits Resource Server endpoints expecting a `Jwt` principal. If using **@WithMockUser** in reactive tests, ensure Spring Security Test populates Reactor Context properly for that setup; explicit **mutateWith(mockUser())** is readable and supports per-request variations.

**ROLE_** and **SCOPE_** follow different conventions. **roles("ADMIN")** typically yields **ROLE_ADMIN**; **hasAuthority("SCOPE_notes.write")** must be granted that exact authority and is not inferred from `roles("ADMIN")`.

### 7.2 CSRF: Apply Only to Appropriate Session/Cookie Mechanisms

For form login or cookie-based sessions, test both POST failures without CSRF and POST successes with valid CSRF; in WebTestClient use **SecurityMockServerConfigurers.csrf()**, for example:

~~~java
// Specific example for apps with CSRF enabled and cookie/session auth.
// Do not assert status 200 if the real endpoint/service/policy dictates otherwise.
client.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/api/form")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"value\":\"demo\"}")
        .exchange()
        .expectStatus().isOk();
~~~

This snippet does not apply to the stateless JWT demo where CSRF is disabled and is not a standalone runnable test. When an app migrates from sessions to Bearer tokens, the decision to enable or disable CSRF must rest on whether browsers send credentials automatically, not on the framework alone.

### 7.3 Method Security Using Reactor Context

When migrating **@PreAuthorize**, **@PostAuthorize**, or custom method-security mechanisms:

- On WebFlux, enable **@EnableReactiveMethodSecurity** when the project uses reactive method security.
- Invoke through **real Spring proxies/beans**; never instantiate the service with **new** in integration tests, which bypasses the proxy.
- Place **Authentication** into **Reactor Context** so services work across thread/scheduler hops; do not rely on ThreadLocal **SecurityContextHolder** as the default source for reactive pipelines.
- For publisher unit tests you can use **StepVerifier** and **ReactiveSecurityContextHolder.withAuthentication(auth)**; for context-bound WebTestClient tests, **mockJwt()/mockUser()** attach `Authentication` through the `WebFilter`.
- Always include both allowed and denied cases; if a mocked service returns 403 unconditionally, tests can give false greens.

### 7.4 JSON, Headers, Query Params, and Body

MockMvc often passes request bodies as raw JSON strings; WebTestClient offers **bodyValue(Object)** using Jackson or **BodyInserters** when needed. Tests should assert status, `Content-Type`, and key payload fields, and verify error responses leak no secrets. For requests with query parameters, use **uri(uriBuilder -> uriBuilder.path(...).queryParam(...).build())** instead of manual string concatenation across multiple parameters.

When migrating API contracts, keep error-data edge cases: empty bodies, invalid JSON, missing fields, validation failures, malformed headers, Unicode, and insufficient permissions. Do not test only the 200 happy path.

## 8. Flux/SSE/Streaming: Do Not Copy Servlet asyncDispatch Patterns Directly

Spring MVC may return **DeferredResult/Callable** and require **asyncDispatch()** in certain MockMvc tests. In WebFlux, handlers emit **Mono** or **Flux**; WebTestClient subscribes to the pipeline. For finite responses use **expectBody()**, while long-lived or infinite streams should not call **expectBody()** to wait for the entire stream.

Illustrative example when an endpoint returns **Flux<String>** and streams using an appropriate media type:

~~~java
// Snippet for a test whose endpoint GET /api/events returns a streaming body.
Flux<String> events = client
        .get().uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class)
        .getResponseBody();

StepVerifier.create(events.take(3))
        .expectNextCount(3)
        .verifyComplete();
~~~

This is an auxiliary snippet requiring **Flux**, **StepVerifier**, **MediaType** imports and a real streaming endpoint; it does not exist in the Section 4 fixture. If the body is **ServerSentEvent<T>**, use an appropriate `ParameterizedTypeReference` and assert event/data formats. For non-terminating streams, explicitly define item counts, timeouts, cancellation/backpressure, and expected payloads. Never convert a **Flux** via **blockLast()** inside a Netty handler just to mimic Servlet tests.

Service-level publisher tests can use **StepVerifier** to assert **onNext/onError/onComplete**, especially when verifying authorization inside lambdas/operators at subscription time. HTTP tests verify **WebFilter and status codes**, while `StepVerifier` verifies pipeline **semantics**; the two complement each other.

## 9. Step-by-Step Migration Plan

1. **Confirm the runtime:** verify the module is truly WebFlux, remove unintended MVC dependencies or document intentional coexistence. Check startup logs and which **SecurityFilterChain** type is active.
2. **Categorize existing tests:** pure controller tests, security tests, service unit tests, DB/IdP integration tests, and streaming tests. Keep existing service tests if still valid; focus on replacing MockMvc/Servlet-dependent tests.
3. **Select new setups:** **@WebFluxTest** for slices, **@SpringBootTest + bindToApplicationContext** for in-memory HTTP security, **RANDOM_PORT + real Bearer tokens** for decoder/remote integration.
4. **Convert APIs:** **perform(...) → ...exchange()**, **andExpect → expectStatus/expectBody**, **.with(jwt()/user()/csrf()) → .mutateWith(mockJwt()/mockUser()/csrf())**.
5. **Preserve security contracts:** for every route, include at least anonymous 401, under-privileged authenticated 403, authorized 2xx, and response mapping assertions; add tenant/owner tests where endpoints enforce ownership.
6. **Verify Reactor Context:** method-layer authorization, scheduler hops, and lazy publishers; never move blocking logic onto the event loop just to fix a test.
7. **Test real endpoints:** verify issuer/audience/signature/expiry, HTTP 401 on bad tokens, HTTPS/JWK/introspection, and system config; `mockJwt` does not cover this.
8. **Run tests and review outcomes:** check test reports, mutations/authorization, races/timeouts, and ensure no false positives from unloaded routes or excluded security filters in slices.

Do not delete legacy tests just because the syntax differs: only retire MockMvc paths once the new tests prove identical behavior and the runtime has genuinely migrated. If an application remains Servlet, WebTestClient over HTTP can still be a valid test tool provided you accurately document what it measures.

## 10. Debugging Common Failures

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| Test named WebFlux, but runtime is MVC | Both starter-web and starter-webflux present; WebApplicationType is SERVLET | Inspect dependency graph/startup logs; align stack with actual target |
| Test gets 401 despite using mockJwt() | WebTestClient lacked Spring Security test support, or hit real HTTP | Use **bindToApplicationContext(...).apply(springSecurity())**; for real HTTP, send a valid JWT |
| JWT test gets 403 | Rule requires **SCOPE_...**, yet test granted **ROLE_...** or another scope | Verify exact authority matching **hasAuthority** |
| Context fails with missing ReactiveJwtDecoder | Resource Server JWT enabled without decoder/JWKS config and no test bean provided | `@MockBean ReactiveJwtDecoder` in test context, or configure real decoder in integration |
| Used mockUser(), yet @AuthenticationPrincipal Jwt is null | Principal is not a `Jwt` | Switch to **mockJwt()** when testing JWT endpoints; do not cast blindly |
| Test returns 200 even though filters did not run | `bindToController` used directly without WebFilter/Security chain; overly broad permitAll | Also assert 401/403, bind full context, or import security/filters into the slice |
| Cookie-based login test gets 403 on POST | CSRF enabled and request lacks token | Use **mutateWith(csrf())** in valid-CSRF tests and test missing-CSRF rejections |
| StepVerifier sees no security context | Service created via **new**, context not attached to Reactor, or manual subscribe elsewhere | Call the Spring proxy, pass Authentication via Reactor Context, avoid manual subscribe |
| Test hangs on infinite Flux response | **expectBody()** waits for body completion | Use **returnResult(...).getResponseBody()** + `StepVerifier`, `take`/cancel, and timeouts |
| MockMvc assertions fail imports | Still importing **MockMvcRequestBuilders**, **SecurityMockMvcRequestPostProcessors** | Replace with **WebTestClient** and **SecurityMockServerConfigurers** |
| JWT tests are green, yet production returns 401 | `mockJwt()` skips decoder/JWKS/issuer/audience validation | Add integration tests with real signed tokens and matching validators |
| Behavior changes across scheduler switches | Used ThreadLocal or misplaced `block`/`subscribe` | Keep the Reactor chain, use `StepVerifier`, and observe event-loop and propagation behavior |

**How to isolate 401/403:** first determine whether the request goes through context-bound WebFlux or real HTTP; next determine whether an `Authentication` was created; finally compare **authorities/claims** against specific rules and service policies. Never disable security altogether to make tests pass, as that bypasses the very path under test.

## 11. Acceptance Criteria

This lesson is complete when:

- WebFlux tests use **WebTestClient** and execute through the proper **SecurityWebFilterChain**.
- Tests verify **public, anonymous 401, insufficient scope 403, sufficient scope 2xx**, and assert expected principals/claims.
- Reactive controllers still return **Mono/Flux** per contract, without manual **block()/subscribe()** inserted to fit old tests.
- Body, headers, validation, CSRF (if applicable), method security, and streaming cases preserve exact semantics.
- Documentation/tests clearly distinguish **mockJwt()** inside the application context from **real Bearer JWTs** traveling over HTTP through the decoder.
- There is evidence of running tests with dependencies matching the proper stack, plus integration tests for JWT signature/issuer/audience/expiry when using a real Resource Server.

**Remember:** the goal of migrating from MockMvc to WebTestClient is to test the true reactive request pipeline and preserve security boundaries. Renaming test APIs is only part of the work; the `Authentication` source, `WebFilter` chain, Reactor Context, and test integration depth determine whether the results can be trusted.