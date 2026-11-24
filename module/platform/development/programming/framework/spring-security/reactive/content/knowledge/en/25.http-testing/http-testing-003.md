# @WebFluxTest, @SpringBootTest, and Loading the Right Security Configuration

## 1. Goals and Common Failure Scenarios

In reactive/WebFlux Spring Security, an HTTP test can return 200, 401, or 403 **without ever loading the production `SecurityWebFilterChain`**. A classic case is using `@WebFluxTest`, which loads only controllers and web infrastructure while omitting the custom `@Configuration` that defines the `SecurityWebFilterChain` bean. In that situation, Spring Boot may apply a default security policy that differs from the real application; negative tests still pass, misleading us into thinking authorization was verified.

Example business requirements:

- `GET /health` is public.
- `GET /api/reports/{id}` requires `ROLE_READER`.
- `POST /api/reports/{id}/preview` requires `ROLE_EDITOR` **and** a valid CSRF token.
- Undeclared routes are denied.
- The controller calls a reactive `ReportService`. Slice tests use a mocked service; full tests use the real implementation.
- When the system uses JWT, the decoder must also verify signature, issuer, audience, and expiration; `mockJwt()` does not replace that test.

**Core questions:** Which security beans is the test suite loading? Do client requests actually pass through the WebFlux Security filters? Is Authentication the result of verifying real credentials, or just a fake principal created by the test?

After this lesson, you will be able to:
1. Choose the right `@WebFluxTest`, `@SpringBootTest(MOCK)`, or `@SpringBootTest(RANDOM_PORT)`.
2. Know when you must `@Import(SecurityConfig.class)` to test a custom `SecurityWebFilterChain`.
3. Distinguish a `@MockBean` service from mocking the security policy.
4. Use `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`.
5. Test real HTTP Basic authentication, mockUser/mockJwt, role-based authorization, and CSRF.
6. Write a full runnable-oriented Java 17+ Gradle project with all three test levels.
7. Recognize the limits of controller slices regarding `@PreAuthorize`, tenant/owner ACLs, JWT decoders, and live HTTP transport.
8. Interpret 200/401/403/404 results rigorously and avoid false positives.

## 2. Map of HTTP Test Levels in WebFlux

~~~text
A. Unit Test:
   new ReportController(fakeService).read("r-1")
   → no Spring context, no security filters, no HTTP.

B. WebTestClient.bindToController(...)
   → mock controller handler; DOES NOT automatically include app security chain.

C. @WebFluxTest(ReportController.class)
   + @Import(SecurityConfig.class)
   + @MockBean ReportService
   + WebTestClient + springSecurity()
   → Controller, WebFlux WebFilters, custom SecurityWebFilterChain
   → DOES NOT open a TCP port.

D. @SpringBootTest(MOCK)
   + @AutoConfigureWebTestClient
   → Full Spring application context, real services/security
   → Mock HTTP runtime, DOES NOT open a TCP port.

E. @SpringBootTest(RANDOM_PORT)
   → Full context + real Netty HTTP server on a random port
   → WebTestClient sends real HTTP; DO NOT use mockUser over a socket.
~~~

| Criterion | `@WebFluxTest` | `@SpringBootTest(MOCK)` | `@SpringBootTest(RANDOM_PORT)` |
| --- | --- | --- | --- |
| Component scan | Web slice only | Full application | Full application |
| Regular `@Service` | Usually excluded from slice | Present | Present |
| Custom security config | **Must be imported intentionally** | Via component scan | Via component scan |
| Mockito mock services | Common | Used when isolating outbound dependencies | Used when isolating outbound dependencies |
| `WebTestClient` | Auto-configured | Typically add `@AutoConfigureWebTestClient` | Boot provides a live-bound client |
| Runs real HTTP listener | No | No | **Yes** |
| Tests security filters | Yes if the right chain is loaded | Yes | Yes |
| Tests real password/JWT | Yes if real auth manager/decoder is present | Yes | Yes |
| Speed/cost | Usually lightweight | Medium | Heavier |
| Risk of faulty tests | Missing chain/service bean | Wrong properties/external dependencies | Port/transport/state and mock-mutator misuse |

**Note:** `@SpringBootTest` without `webEnvironment` defaults to `MOCK`. A mock **web environment** does not mean every service is a Mockito mock. With `RANDOM_PORT`, the application starts a real web server.

### 2.1. Distinguishing MVC and WebFlux

- `@WebMvcTest`/`MockMvc`/`HttpSecurity`/`SecurityFilterChain` are for **Servlet MVC**.
- `@WebFluxTest`/`WebTestClient`/`ServerHttpSecurity`/`SecurityWebFilterChain` are for **reactive WebFlux**.
- Spring Boot usually prioritizes MVC when both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath. For a WebFlux-only project, do not accidentally add the Servlet starter.
- If you must force reactive mode while both are present, consider `spring.main.web-application-type=reactive`, though fixing the dependency graph is best.

## 3. Why must `@WebFluxTest` import `SecurityConfig` explicitly?

Spring Boot 3.3 documentation explicitly notes that `@WebFluxTest` **does not auto-detect custom security configurations that register a `SecurityWebFilterChain` bean**. The slice primarily loads web components such as controllers, controller advice, JSON/converters, `WebFluxConfigurer`, and some infrastructure. It does not automatically load every `@Configuration`, `@Service`, and `@Repository`.

Standard structure:

~~~java
@WebFluxTest(controllers = ReportController.class)
@Import(SecurityConfig.class)
class ReportSliceTest {
    @MockBean
    ReportService reports;
}
~~~

- `@WebFluxTest` loads the controller and test infrastructure.
- `@Import(SecurityConfig.class)` loads the **real security policy**.
- `@MockBean ReportService` supplies a mock service to avoid pulling DB/business graphs into the slice.
- `@Import` alone is not proof that the filter chain is executing; you must use `WebTestClient` wired with security filters and test behavior.
- If the security config depends on `ReactiveJwtDecoder` or a policy service, supply the appropriate bean for the test scope; do not disable the entire chain just to make the context start.

**Why aren't 401/403 tests alone enough?** A default `denyAll` or auto-generated "anyRequest authenticated" rule can also return 401/403. You need **positive tests**: anonymous `GET /health` → 200, reader → 200, editor+CSRF → 200, alongside negative tests. When the custom config is imported, the `securityChain` bean name can also be asserted in the context.

### 3.1. Do not `@Import` the entire Application class just to get security

`@Import(TestingApplication.class)` can trigger deep component scanning and pull in R2DBC, Kafka, Redis, or unnecessary beans. Better:
- Isolate `SecurityConfig` into a small class configuring only security/authentication.
- `@Import(SecurityConfig.class)` and mock the exact service dependencies.
- Use full `@SpringBootTest` when you genuinely need to verify coordination across security, services, and repositories.

### 3.2. Functional endpoints are an exception

`@WebFluxTest` does not automatically scan all WebFlux.fn `RouterFunction` beans. If the app uses `RouterFunctions.route(...)`, you must import the router config/bean or use `@SpringBootTest`. `bindToController` also does not automatically wire functional routers.

## 4. `@SpringBootTest`: the four `webEnvironment` modes

| Value | Meaning |
| --- | --- |
| `MOCK` (default) | Full context, mock web infrastructure, no HTTP socket |
| `RANDOM_PORT` | Full context, real web server listening on a random port |
| `DEFINED_PORT` | Full context, server on a fixed port (prone to collisions in automated tests) |
| `NONE` | Application context without web runtime |

For a full WebFlux mock HTTP test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class FullContextMockHttpTest {
    @Autowired WebTestClient client;
}
~~~

For a live HTTP test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LivePortHttpTest {
    @Autowired WebTestClient client;
    @LocalServerPort int port;
}
~~~

`@AutoConfigureWebTestClient` creates the client for a mock full context; it **does not** open a server socket. With an autowired live-port client, relative requests like `/api/reports/r-1` are sent to the Boot-managed random port.

If a test uses `@Transactional` with `RANDOM_PORT`, transactions on the HTTP server side can be separate from the test thread's transaction; do not assume test rollback automatically reverts server-side commits. Design fixtures/cleanup accordingly.

## 5. `WebTestClient` and Spring Security test support

In a mock web environment:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

`bindToApplicationContext(...)` uses the context's WebFlux controllers/filters; `apply(springSecurity())` installs Spring Security Test support such as `mockUser()`/`csrf()`. Do not use `bindToController(...)` alone and assume it automatically adds the production security chain.

### 5.1. Three kinds of credentials in tests

| Approach | Verifies password/signature? | Used for |
| --- | --- | --- |
| `client.mutateWith(mockUser("alice").roles("READER"))` | **No** | Testing route/authorization with a fake principal |
| `@WithMockUser` | **No** | Testing method/HTTP authorization in a mock context |
| `client.mutateWith(mockJwt())` | **No** | Testing mocked JWT principal/authorities, not the decoder |
| `headers(h -> h.setBasicAuth("reader","reader-pass"))` | **Yes** when real chain/manager is loaded | Testing HTTP Basic authentication |
| `headers(h -> h.setBearerAuth(signedJwt))` | **Yes** when real JWT decoder is loaded | Testing signature/claims/route authorization |
| Live HTTP + Basic/Bearer headers | **Yes** | Testing network transport and authentication |

`mockUser()` and `mockJwt()` are not flawed in themselves: they intentionally skip the hard part so you can test authorization logic. The mistake is describing their results as proof that signing keys, passwords, issuers, or audiences are valid.

### 5.2. CSRF in WebFlux tests

For unsafe methods such as POST/PUT/DELETE with CSRF enabled, a valid token is required:

~~~java
client.mutateWith(csrf())
    .post().uri("/api/reports/r-1/preview")
    .headers(h -> h.setBasicAuth("editor","editor-pass"))
    .bodyValue(new PreviewRequest("Draft"))
    .exchange()
    .expectStatus().isOk();
~~~

This is `SecurityMockServerConfigurers.csrf()` for WebTestClient, **not** `MockMvcRequestPostProcessors.csrf()` for Servlet. In this example using HTTP Basic, CSRF is kept enabled because browsers can automatically send Basic credentials as ambient auth. For pure Bearer-header APIs, the CSRF decision must follow a threat model; never disable it unconditionally just to make tests pass.

## 6. Java 17+ project comparing the three test styles

Project goals:
- Spring Boot **3.3.13**, Gradle 8.x, Java 17+.
- WebFlux + reactive Spring Security.
- Two **lab-only** users: reader has `ROLE_READER`, editor has `ROLE_READER` and `ROLE_EDITOR`.
- `/health` is public, GET report requires reader, POST preview requires editor + CSRF.
- Stateless service so results are deterministic.
- 3 test classes: slice, full MOCK, live-port.

**Safety:** Uses `{noop}` passwords solely to demonstrate HTTP Basic; **never use in production**. Production requires password hashing/IdP, HTTPS, owner/tenant authorization, and auditing.

~~~text
webflux-security-testing/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/testing/
    │   ├── TestingApplication.java
    │   ├── SecurityConfig.java
    │   ├── ReportService.java
    │   ├── DefaultReportService.java
    │   └── ReportController.java
    └── test/java/demo/testing/
        ├── ReportSliceTest.java
        ├── FullContextMockHttpTest.java
        └── LivePortHttpTest.java
~~~

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'webflux-security-testing'
~~~

### 6.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In Boot 3.3, use `org.springframework.boot.test.mock.mockito.MockBean`; in newer versions, Spring Framework's `@MockitoBean` has progressively replaced the older annotation. Do not mix imports from newer Boot guides into a 3.3 project without checking the API.

### 6.3. `TestingApplication.java`

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

### 6.4. `SecurityConfig.java`

~~~java
package demo.testing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasRole("READER")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasRole("EDITOR")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // CSRF remains enabled by default; do not call csrf.disable().
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader-pass")
            .roles("READER")
            .build();
        UserDetails editor = User.withUsername("editor")
            .password("{noop}editor-pass")
            .roles("READER", "EDITOR")
            .build();
        return new MapReactiveUserDetailsService(
            reader, editor);
    }
}
~~~

**Reading the config:**
- `@EnableWebFluxSecurity` and `SecurityWebFilterChain` use `ServerHttpSecurity`, not Servlet `HttpSecurity`.
- `GET /health` acts as a 200 sentinel when the real policy is loaded.
- `hasRole("READER")` and `hasRole("EDITOR")` check authorities `ROLE_READER`/`ROLE_EDITOR` respectively; do not confuse them with `SCOPE_` from OAuth2 JWTs.
- `anyExchange().denyAll()` protects other routes/methods.
- `httpBasic` requires valid username/password against the reactive user details service.
- `formLogin` is disabled to avoid HTML login in the API demo; CSRF remains enabled.
- Roles/users are declared in source only for the lab; real applications never hardcode passwords.

### 6.5. `ReportService.java`

~~~java
package demo.testing;

import reactor.core.publisher.Mono;

interface ReportService {
    Mono<ReportView> read(String id);
    Mono<ReportView> preview(String id, String title);
}

record ReportView(String id, String title) {}

record PreviewRequest(String title) {}
~~~

These Java records hold JSON data for HTTP. `preview` does not write to a database; its purpose is testing authz/CSRF with POST.

### 6.6. `DefaultReportService.java`

~~~java
package demo.testing;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
class DefaultReportService implements ReportService {

    @Override
    public Mono<ReportView> read(String id) {
        return Mono.defer(() -> {
            if (!"r-1".equals(id)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
            }
            return Mono.just(new ReportView(
                id, "Report " + id));
        });
    }

    @Override
    public Mono<ReportView> preview(String id, String title) {
        return Mono.defer(() -> {
            if (!"r-1".equals(id)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
            }
            return Mono.just(new ReportView(id, title));
        });
    }
}
~~~

In the full context, this service implementation is the real `@Service`. In `@WebFluxTest`, it is not component-scanned; the test provides `@MockBean ReportService`. That exact difference illustrates the boundary between slice and full integration.

### 6.7. `ReportController.java`

~~~java
package demo.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class ReportController {

    private final ReportService reports;

    ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/reports/{id}")
    Mono<ReportView> read(@PathVariable String id) {
        return reports.read(id);
    }

    @PostMapping("/api/reports/{id}/preview")
    Mono<ReportView> preview(
            @PathVariable String id,
            @RequestBody Mono<PreviewRequest> body) {
        return body.flatMap(request ->
            reports.preview(id, request.title()));
    }
}
~~~

The controller does not read user IDs/roles from raw request headers. In production, services/repositories must also enforce tenant, ownership, and report ACL checks rather than treating `ROLE_READER` as permission to read all documents.

## 7. Testing `@WebFluxTest` with the real security config

`src/test/java/demo/testing/ReportSliceTest.java`:

~~~java
package demo.testing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(controllers = ReportController.class)
@Import(SecurityConfig.class)
class ReportSliceTest {

    @Autowired
    ApplicationContext context;

    @MockBean
    ReportService reports;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void loadsCustomChain() {
        assertThat(context.containsBean("securityChain"))
            .isTrue();
    }

    @Test
    void publicHealthReturns200() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void anonymousGetReturns401() {
        client.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
        verifyNoInteractions(reports);
    }

    @Test
    void incorrectBasicPasswordReturns401() {
        client.get().uri("/api/reports/r-1")
            .headers(h -> h.setBasicAuth("reader","invalid"))
            .exchange()
            .expectStatus().isUnauthorized();
        verifyNoInteractions(reports);
    }

    @Test
    void correctReaderGetsMockServiceResult() {
        given(reports.read("r-1")).willReturn(
            Mono.just(new ReportView("r-1","From mock")));

        client.get().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("r-1")
            .jsonPath("$.title").isEqualTo("From mock");

        verify(reports).read("r-1");
    }

    @Test
    void mockUserOnlyTestsAuthorizationRule() {
        given(reports.read("r-1")).willReturn(
            Mono.just(new ReportView("r-1","From mock")));

        client.mutateWith(
                mockUser("fake-reader").roles("READER"))
            .get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isOk();
        // Does not prove the password of user "fake-reader".
    }

    @Test
    void readerWithCsrfStillCannotPost() {
        client.mutateWith(csrf())
            .post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isForbidden();
        verifyNoInteractions(reports);
    }

    @Test
    void editorWithoutCsrfCannotPost() {
        client.post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isForbidden();
        verifyNoInteractions(reports);
    }

    @Test
    void editorWithCsrfGets200() {
        given(reports.preview("r-1","Draft")).willReturn(
            Mono.just(new ReportView("r-1","Draft")));

        client.mutateWith(csrf())
            .post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Draft");

        verify(reports).preview("r-1","Draft");
    }

    @Test
    void deleteMethodIsNotAllowedByPolicy() {
        client.delete().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .exchange()
            .expectStatus().isForbidden();
        verifyNoInteractions(reports);
    }
}
~~~

### 7.1. Which boundaries do the ten test methods verify?

| Group | Assertions | Layer tested |
| --- | --- | --- |
| Bean presence | `securityChain` exists | `@Import` wiring |
| Public route | health 200 | Custom `permitAll` |
| Anonymous/invalid password | GET 401 | HTTP Basic authentication/filter |
| Valid reader | GET 200, mock called properly | Authn/authz + controller |
| MockUser | GET 200 | **Only** authorization with fake Authentication |
| Missing role | Reader POST with CSRF → 403 | `hasRole("EDITOR")` |
| Missing CSRF | Editor POST → 403 | CSRF filter |
| Valid role+CSRF | Editor POST → 200 | Positive HTTP/security path |
| Disallowed method | DELETE → 403 | `denyAll` |

A `@WebFluxTest` that loads the wrong security setup may return 401/403 on many negative cases; **positive 200 tests** and bean assertions help catch miswiring.

### 7.2. Why not mock `SecurityWebFilterChain`?

If the goal is to test real authorization, mocking the chain or configuring `permitAll` in tests makes the test meaningless. Mock the collaborator `ReportService`, while keeping the chain as the bean implementing the production policy.

### 7.3. Slices do not prove data-layer permissions

`@MockBean ReportService` replaces the business implementation. Thus a 200 test only proves HTTP/serialization/controller/role rules, **not**:
- That `@PreAuthorize` on the real service executed.
- That Tenant A is blocked from reading Tenant B's data.
- That R2DBC queries include owner/tenant predicates.
- That database row-level security/transactions are correct.
- That a newly locked user is still rejected.

Those require service/repository tests or full integration tests with real beans and a test DB.

## 8. Testing `@SpringBootTest(MOCK)` + `@AutoConfigureWebTestClient`

`src/test/java/demo/testing/FullContextMockHttpTest.java`:

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class FullContextMockHttpTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    WebTestClient bootClient;

    @Autowired
    ReportService reports;

    @Test
    void usesRealServiceAndCorrectSecurityConfig() {
        assertThat(reports)
            .isInstanceOf(DefaultReportService.class);
        assertThat(context.containsBean("securityChain"))
            .isTrue();
    }

    @Test
    void anonymousIs401InFullContext() {
        bootClient.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void actualServiceReturnsExpectedContent() {
        bootClient.get().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("r-1")
            .jsonPath("$.title").isEqualTo("Report r-1");
    }

    @Test
    void unknownReportIs404AfterAuthentication() {
        bootClient.get().uri("/api/reports/other")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void fullContextStillRequiresCsrfForPost() {
        WebTestClient secureClient = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();

        secureClient.post()
            .uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isForbidden();

        secureClient.mutateWith(csrf())
            .post().uri("/api/reports/r-1/preview")
            .headers(h ->
                h.setBasicAuth("editor","editor-pass"))
            .bodyValue(new PreviewRequest("Draft"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Draft");
    }
}
~~~

**Five methods** demonstrate the full application context with the **real service** but a mock web runtime. `bootClient` is created by Boot via `@AutoConfigureWebTestClient`; `secureClient` is explicitly bound to ApplicationContext with `springSecurity()` applied to use the CSRF mutator.

**Note:** A real application's full context may load R2DBC/Kafka/Redis/OAuth2 clients. Use `@ActiveProfiles("test")`, test-specific configurations, Testcontainers, or mock **only outbound dependencies**—never disable the security chain just to make startup succeed.

## 9. Testing `@SpringBootTest(RANDOM_PORT)` — real HTTP

`src/test/java/demo/testing/LivePortHttpTest.java`:

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LivePortHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void webServerHasRealRandomPort() {
        assertThat(port).isPositive();
    }

    @Test
    void noAuthenticationReturns401OverHttp() {
        client.get().uri("/api/reports/r-1")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicReaderGets200OverHttp() {
        client.get().uri("/api/reports/r-1")
            .headers(h ->
                h.setBasicAuth("reader","reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Report r-1");
    }
}
~~~

**Three methods** traverse a real Netty/HTTP socket. `@LocalServerPort` verifies the port; Boot auto-configures `WebTestClient` to target the live server. Do not use `mockUser()` or `mockJwt()` mutators as credentials against a real server; mutators affect the mock server context and do **not** travel over the TCP wire.

### 9.1. Overall results

The three test classes contain **18 test methods**: 10 slice + 5 full MOCK + 3 RANDOM_PORT. They are designed to pass on Java 17/Spring Boot 3.3.13 with compatible dependencies, though **no actual compile/run log is included in this article**. You must run Gradle before claiming `BUILD SUCCESSFUL`.

~~~bash
gradle test
~~~

If using the Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Start the app:

~~~bash
gradle bootRun
~~~

Test with curl:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/reports/r-1
curl -i -u reader:reader-pass http://localhost:8080/api/reports/r-1
~~~

Expected:
- GET `/health` → HTTP 200, body `ok`.
- GET report without credentials → HTTP 401.
- GET report with valid reader → HTTP 200, JSON `{"id":"r-1","title":"Report r-1"}`.
- POST preview as editor without CSRF token → 403. The mock web client test uses `csrf()` to illustrate a successful POST; the demo does not expose a CSRF token issuance endpoint for curl/browser.

**Use demo passwords only on localhost.** HTTP Basic over the Internet requires HTTPS and an appropriate authentication design.

## 10. When using an OAuth2 Resource Server JWT instead of HTTP Basic

Tests must still ensure the right `SecurityWebFilterChain` is loaded.

### 10.1. Illustrative JWT chain (not part of the runnable Basic project)

~~~java
@Configuration
@EnableWebFluxSecurity
class JwtSecurityConfig {
    @Bean
    SecurityWebFilterChain jwtChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Requires `spring-boot-starter-oauth2-resource-server` and a `ReactiveJwtDecoder` configured with the right issuer/JWKS/audience. With JWT, default scopes usually map to `SCOPE_*`; do not confuse them with `ROLE_*` in the Basic example.

### 10.2. JWT slice test and decoder dependency

~~~java
@WebFluxTest(ProtectedReportController.class)
@Import(JwtSecurityConfig.class)
class JwtSliceTest {

    @MockBean
    ReactiveJwtDecoder decoder;

    // Mock context client + apply(springSecurity())
    // client.mutateWith(mockJwt().authorities(
    //    new SimpleGrantedAuthority("SCOPE_reports.read")))
    //    .get().uri("/api/reports/r-1") ...
}
~~~

This is a **non-standalone snippet**; `ProtectedReportController` is an example controller name in a separate JWT app, not a file in the runnable Basic project. `@MockBean ReactiveJwtDecoder` satisfies the chain's dependency in the slice, while `mockJwt()` creates a fake Authentication to test authorization. **This result DOES NOT verify the real signature, issuer, audience, or `JwtAuthenticationConverter`.**

### 10.3. How to test cryptographic validation?

Use full-context mock/live tests with a real `Authorization: Bearer <signed-JWT>`:
- Sign the JWT with a test-only RSA private key.
- `NimbusReactiveJwtDecoder` trusts only the test public key.
- `JwtValidators.createDefaultWithIssuer(issuer)` + audience validator.
- Valid signature/issuer/audience/expiry + authority → 200.
- Valid JWT missing `SCOPE_reports.read` → 403.
- Tampered JWT or wrong signature/issuer/audience/exp → 401.
- `@TestConfiguration` decoder is injected only in tests; **never** bundle private signing keys into production.
- Separately test JWKS metadata discovery, caching/rotation, and TLS if within system scope.
- With `RANDOM_PORT`, pass a **real Bearer header**, never `mockJwt()`.

A `mockJwt().authorities(ROLE_ADMIN)` test returning 200 does not prove an attacker cannot forge signatures. It only proves the rule checks the authority.

## 11. Method security and data permissions are absent in controller mocks

Suppose the real service has:

~~~java
@Service
class ReportWriteService {
    @PreAuthorize("hasAuthority('SCOPE_reports.write')")
    Mono<Void> update(String reportId) {
        return Mono.empty();
    }
}
~~~

If the slice uses `@MockBean ReportWriteService`, the real method **never runs**, so `@PreAuthorize` on that method is not tested as you might assume. You must have `@EnableReactiveMethodSecurity` in the appropriate config, invoke through the Spring proxy, and test the real service or full context.

Verify separately:
1. Unauthorized users are denied before side effects.
2. Users with the scope but wrong tenant are still denied.
3. Repository queries/updates include tenant/owner predicates, preventing IDOR/BOLA.
4. Permissions changed/revoked while a token is still unexpired are handled per policy.
5. Reactor `SecurityContext` propagates across `Mono`/`Flux`, rather than relying on Servlet ThreadLocal.
6. Self-invocation or `new ReportWriteService()` can bypass the method security proxy.

**Do not** use a passing controller slice to claim repository/object authorization has been tested.

## 12. Multiple `SecurityWebFilterChain`s and selecting the right chain

When multiple chains exist:
- `securityMatcher` selects which **chain** applies per request.
- `authorizeExchange` defines **permissions** inside the selected chain.
- `@Order` controls priority order.
- A test missing the JWT chain import can cause requests to fall through to a fallback Basic/default chain and return misleading responses.

Example design:

~~~text
@Order(1) /api/**  → JWT chain, SCOPE_api.read
@Order(2) fallback → Basic/login chain, ROLE_USER
~~~

Tests should include:
- `/api/reports` without token 401, valid JWT with scope 200, missing scope 403.
- `/web/**` following the second chain's login policy.
- Unmatched routes → deny.
- POST differs from GET; CSRF policies may differ per chain.
- Positive and negative assertions for **every** boundary, not just `getBean(SecurityWebFilterChain.class)`.

If a slice targets only one chain, state that explicitly and import the right config; full-context integration tests must confirm ordering and interaction across all chains.

## 13. Troubleshooting faulty WebFlux security tests

| Symptom | Possible cause | Action |
| --- | --- | --- |
| `@WebFluxTest` health returns 401 instead of 200 | Custom `SecurityWebFilterChain` not loaded | `@Import(SecurityConfig.class)` |
| Controller slice missing ReportService bean | `@Service` excluded from slice | `@MockBean ReportService` |
| Context missing ReactiveJwtDecoder | JWT chain imported without decoder | Mock decoder/test config or full test |
| `bindToController` test 200 but production 401 | No security filters | Bind ApplicationContext + apply(springSecurity()) |
| `mockUser` passes despite wrong password | Mock bypasses password manager | Test real HTTP Basic |
| Mock JWT passes but signed JWT returns 401 | Mock bypasses signature/issuer/audience | Test signed Bearer JWT and decoder |
| POST by valid editor returns 403 | Missing CSRF or wrong role | Separate role and CSRF tests |
| DELETE returns 403 | `denyAll` or CSRF | Verify path/method matcher; don't open carelessly |
| `@SpringBootTest(MOCK)` does not autowire WebTestClient | Missing auto-config | `@AutoConfigureWebTestClient` |
| Random-port test has no server | Wrong web environment or startup error | Check webflux starter, logs, config |
| Security config bean exists but wrong route behavior | Wrong multiple-chain order or matcher | Positive/negative tests per chain |
| `@PreAuthorize` does not block in slice | Service is mocked/missing method security | Full tests with proxied real service |
| Slice loads DB unexpectedly | Explicit `@ComponentScan` widens scope | Split configs/keep imports narrow |
| Context cannot find app class | Test is in wrong package | Place test in package tree or specify classes |
| 403 for user with role | `SCOPE_` vs `ROLE_` / CSRF / tenant ACL | Check authorities, policy, and data |
| All negative tests pass | A deny-all chain would also pass | Add health/authorized 200 tests |
| `@MockBean` API error on newer Boot | Framework version changed | Use `@MockitoBean` matching Boot version |
| Live DB test side effects do not roll back | HTTP server transaction differs from test thread | Dedicated data setup/cleanup |
| Browser gets CORS error while WebTestClient passes | Test does not send Origin/preflight | Test CORS explicitly; don't treat CORS as auth |

### 13.1. Wrong "fixes"

- **Wrong:** disabling CSRF when a POST test returns 403 without understanding why.
- **Wrong:** changing the entire SecurityConfig to `permitAll` in tests claimed to "verify security".
- **Wrong:** `@Import(TestingApplication.class)` to pull the whole app into a web slice.
- **Wrong:** using `mockJwt()` and concluding JWT cryptography is trustworthy.
- **Wrong:** checking only 401/403 statuses without any 200 tests.
- **Wrong:** placing `@WithMockUser` on a live TCP test and assuming real requests carry that principal.
- **Right:** define the test scope, load the real security config, mock only out-of-scope boundaries, and verify full behavior.

## 14. Self-check exercises

**Q1.** Does `@WebFluxTest` automatically load a custom `SecurityWebFilterChain`?

**Answer:** Not guaranteed; Boot 3.3 explicitly documents it is not auto-detected. Use `@Import(SecurityConfig.class)` or full context.

**Q2.** Does `@SpringBootTest` open a real port by default?

**Answer:** No. `MOCK` is the default; use `RANDOM_PORT` for a real HTTP server.

**Q3.** Does `@AutoConfigureWebTestClient` automatically open a Netty socket?

**Answer:** No. It is client auto-configuration within the context.

**Q4.** Why is health 200 a good sentinel, yet insufficient?

**Answer:** A missing import can cause the default chain to reject health. However, an app-wide `permitAll` chain also returns 200; you need protected positives/negatives.

**Q5.** Does `mockUser("reader")` verify the `reader-pass` password?

**Answer:** No. Use real HTTP Basic requests to test the password path.

**Q6.** Does `mockJwt()` verify the signature and JWKS?

**Answer:** No. Use a signed Bearer JWT through `ReactiveJwtDecoder`.

**Q7.** An editor has permission, but what does a POST without CSRF receive in the demo?

**Answer:** 403.

**Q8.** A reader has CSRF, but lacks `ROLE_EDITOR`?

**Answer:** 403.

**Q9.** An editor has CSRF and the service returns the report?

**Answer:** 200.

**Q10.** Does mocking a service with `@MockBean` test `@PreAuthorize` on the real service?

**Answer:** No. Method security must be tested with the real proxied service.

**Q11.** `@WebFluxTest` does not auto-load functional `RouterFunction`s—what should you do?

**Answer:** `@Import` the router configuration or use `@SpringBootTest`.

**Q12.** Under `RANDOM_PORT`, should you use `mockUser()` instead of Basic credentials over TCP?

**Answer:** No; `mockUser` is not an HTTP credential on the wire.

**Q13.** A JWT has `SCOPE_reports.read` while the service checks `hasRole("READER")`—does it match?

**Answer:** Not by default; `SCOPE_` and `ROLE_` are distinct.

**Q14.** Why doesn't test `@Transactional` automatically roll back server commits under `RANDOM_PORT`?

**Answer:** The real HTTP client/server run in different execution/transaction contexts; explicit test data cleanup is needed.

**Q15.** A controller slice passes 200—is that enough to prove Tenant B is denied?

**Answer:** Not when the service/repository is mocked. You need object/tenant data-layer integration tests.

## 15. Checklist before merging security tests

- [ ] The project is truly WebFlux; no MVC annotations mixed in by mistake.
- [ ] Use `@WebFluxTest` for controller slices, importing the right `SecurityConfig`.
- [ ] Mock out-of-scope services/dependencies, never the `SecurityWebFilterChain` under test.
- [ ] Include a 200 public sentinel route and 200 protected positive tests.
- [ ] Include anonymous 401, wrong credential 401, and missing role 403 tests.
- [ ] Include CSRF allowed/denied tests for unsafe methods.
- [ ] Mock-context `WebTestClient` applies `springSecurity()` when using mutators.
- [ ] `@SpringBootTest(MOCK)` has `@AutoConfigureWebTestClient` or explicit context binding.
- [ ] `RANDOM_PORT` tests use real Basic/Bearer credentials, not mocked principals over TCP.
- [ ] Multiple chains are verified for exact path/order/method matching.
- [ ] Method security is tested on the real service/proxy when in scope.
- [ ] JWT resource server tests include real-signed tokens to verify signature/issuer/audience/expiry.
- [ ] Tenant/owner/resource policies are tested at the data boundary.
- [ ] Tests do not use production passwords, tokens, databases, or IdPs.
- [ ] Build against the exact framework version and update imports when upgrading Boot.
- [ ] Separate 401/403/404 cases and root causes according to the response contract.
- [ ] Never disable CSRF or add `permitAll` to make test results look green.
- [ ] Test fixtures are deterministic, with cleanup for live-port writes.
- [ ] Never claim production security is verified based solely on a controller slice.

## 16. Official references

- Spring Boot 3.3 — Testing Spring Boot Applications, `@WebFluxTest`, `@SpringBootTest`, `RANDOM_PORT`, auto-config WebTestClient: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — WebFluxTest API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Security — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Reactive Authentication Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — Reactive CSRF Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — Testing OAuth2 and mockJwt: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot — How-to Testing: https://docs.spring.io/spring-boot/how-to/testing.html

**Remember:** `@WebFluxTest` requires `@Import(SecurityConfig.class)` to test a custom `SecurityWebFilterChain`; `@SpringBootTest(MOCK)` loads the full context without opening an HTTP server, whereas `RANDOM_PORT` starts a real server. `WebTestClient` must traverse the proper filter chain rather than binding only to a controller. Use `mockUser`/`mockJwt` for authorization tests, real Basic/JWT credentials for authentication tests, and verify **both allowed and denied cases** to avoid false confidence from a misconfigured security policy.
