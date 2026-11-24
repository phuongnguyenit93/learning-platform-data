# Testing Reactive Security with WebTestClient and Reactor Context

## 1. Why does Reactive Security have its own testing mechanism?

In a **Spring Boot WebFlux** application, an HTTP request passes through a chain of security `WebFilter`s for user authentication and authorization, after which the controller typically returns a `Mono` or `Flux`. Reactor can switch execution across threads via `publishOn`, `subscribeOn`, or asynchronous publishers. Therefore, mechanisms relying purely on `ThreadLocal`, familiar from many Servlet applications, are not the right model for reasoning about identity at every step in a reactive chain.

Spring Security supports **`ReactiveSecurityContextHolder`**. It retrieves the `SecurityContext` from the **subscriber's Reactor Context**. Identity is not stored in a global variable shared across all requests; it propagates scoped to each subscription. An application can be tested at multiple levels:

- **Request security:** anonymous callers are denied, users with matching roles are allowed, and POSTs missing CSRF tokens are blocked.
- **Method security:** real `@PreAuthorize` methods are enforced by the Spring AOP proxy using the authentication in the Reactor Context.
- **Context propagation:** the principal remains intact when downstream operators run after `publishOn`.
- **Authentication path:** HTTP Basic credentials or JWTs are verified through the real mechanism, as opposed to supplying a mock `Authentication` via `mockUser`.

Use each tool in its proper role: **`WebTestClient` + `springSecurity()` + `mockUser()/csrf()`** for WebFlux security request tests; **`StepVerifier` + `ReactiveSecurityContextHolder.withAuthentication(...)` + `contextWrite(...)`** for pure publisher tests.

This lesson uses **Java 17, Spring Boot 3.3.0, Spring Security 6.x, Reactor, and JUnit Jupiter**; full code examples follow below. These versions form a consistent baseline for learning, not the latest production recommendation. **Do not claim tests were executed**: expected results are confirmed only when you run Gradle in an appropriate environment.

## 2. What will you learn?

1. Explain the difference between Servlet/`ThreadLocal` `SecurityContextHolder` and Reactor Context `ReactiveSecurityContextHolder`.
2. Configure `SecurityWebFilterChain` via `ServerHttpSecurity` and enable `@EnableWebFluxSecurity`.
3. Enable `@EnableReactiveMethodSecurity` and test `@PreAuthorize` on beans returning `Mono`.
4. Set up `WebTestClient.bindToApplicationContext(...).apply(springSecurity())`.
5. Use `mockUser(...).roles(...)` for identity/authorization tests without pretending passwords were checked.
6. Distinguish HTTP 401, 403, and 200 in security tests.
7. Use `csrf()` to build paired tests: right role missing token -> 403, with token -> 200.
8. Send real HTTP Basic credentials to test the authentication filter and user details service.
9. Write `StepVerifier` tests checking context across different scheduler threads.
10. Prove two subscriptions never leak principals into each other.
11. Understand differences among `@WebFluxTest`, `@SpringBootTest(MOCK)`, and `RANDOM_PORT`.
12. Avoid false positives from missing security filters, mocking away protected beans, or method self-invocation.
13. Understand how `mockJwt` differs from real JWT signature, issuer, audience, and expiration verification.
14. Recognize security bugs caused by `block()`, manual `subscribe()`, static mutable identities, and untrusted role headers.
15. Organize tests with both positive and negative paths rather than guessing from an ambiguous status code.

## 3. Request and context diagram

```text
Client (WebTestClient)
       |
       v
WebFlux handler chain
       |
       +-- Authentication WebFilter
       +-- SecurityContext / CSRF / Authorization WebFilters
       |
       v
@RestController returns Mono/Flux
       |
       +-- Calls Spring-managed @Service proxy
       |       |
       |       +-- @PreAuthorize evaluated for reactive publisher
       |
       v
Reactor subscription
       |
       +-- ReactiveSecurityContextHolder.getContext()
       +-- Reactor Context tied to Subscriber
       +-- operators: map, flatMap, publishOn...
       |
       v
HTTP status / body
```

**Important:** creating a `Mono` is assembly; only upon subscription do operators run and read context. `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`, not a guaranteed global `SecurityContext` object.

## 4. Authentication, authorization, CSRF, and Reactor Context

| Mechanism | Question | Meaningful assertion |
| --- | --- | --- |
| Authentication | Who is calling? Are credentials valid? | Protected anonymous GET 401; wrong Basic 401 |
| Authorization | Does the user have permission? | READER to admin method 403, ADMIN 200 |
| CSRF | Does a state-changing request carry a valid token? | EDITOR POST without token 403; with token 200 |
| Method Security | Are annotations enforced via proxy? | `@PreAuthorize` denied/allowed |
| Reactor Context | Does principal survive async scheduler? | GET returns `"async:alice"`; StepVerifier returns `"bob"` |
| Context isolation | Does authentication leak across subscriptions? | `alice`, `bob`, and anonymous stay isolated |
| JWT validation | Signature, issuer, audience, expiry? | Decoder with test-signed tokens |
| Deployment security | TLS, reverse proxy, IdP? | Appropriate real-environment tests |

In HTTP Basic-only Spring Security WebFlux like this demo, protected **unauthenticated GETs** typically return **401**, while authenticated callers lacking authorities get **403**. However, if you test **POST without CSRF**, the CSRF filter can return **403** before the authentication entry point runs. Never use a POST missing CSRF as your sole proof of 401.

### 4.1. `ROLE_` prefix

`hasRole("ADMIN")` normally requires authority `ROLE_ADMIN`. `mockUser("alice").roles("ADMIN")` adds that authority automatically. `hasAuthority("REPORT_READ")` compares the exact authority name. Never confuse roles with scopes, and never pass `roles("ROLE_ADMIN")` when the builder already adds the prefix.

### 4.2. Signs of false positives

A test checking only “anonymous gets 403/401” can pass when a broken `denyAll` blocks everyone. A test checking only “ADMIN gets 200” can pass when a method annotation was removed. Therefore, every rule needs **an allow/deny pair**.

## 5. Choosing the right WebTestClient mode

### 5.1. Bind-to-controller

```java
WebTestClient client =
        WebTestClient.bindToController(
                new ExampleController())
                .build();
```

This is an **illustrative snippet** as `ExampleController` is not in the hands-on project. This mode runs simulated WebFlux requests without ensuring the application's `SecurityWebFilterChain` is loaded. Use it only for controller-focused tests with a clearly understood scope.

### 5.2. Bind-to-ApplicationContext

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

The sample code below uses this setup. `springSecurity()` is a helper from `SecurityMockServerConfigurers` inside `spring-security-test`. It wires Spring Security test support so the mock WebFlux handler pipeline applies security filters and `mockUser`/`csrf` mutators. **No HTTP TCP port is opened.**

If you forget `.apply(springSecurity())` on a manually bound client, security filters/test mutators may fail to run as expected. Tests should assert anonymous 401 and reader 403 to detect a missing filter chain.

### 5.3. SpringBootTest RANDOM_PORT

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveTest {
    @Autowired WebTestClient client;
}
```

This is a configuration outline; a runnable class appears later. A real server starts on a random port and the client connects over HTTP. **`mockUser` in the JUnit JVM is not an authentication object transmitted over the network** to a remote server. Send real credentials/tokens via request headers/cookies when testing the live authentication path.

### 5.4. @WebFluxTest vs @SpringBootTest

- `@WebFluxTest` creates a web-focused slice and does not automatically scan all `@Service`/repository beans; `@Import` or mock collaborators intentionally.
- `@WebFluxTest` may not detect custom `SecurityWebFilterChain` configurations; import security config to test real rules.
- `@SpringBootTest` loads the full application context, ideal when testing controllers alongside real method-security service beans.
- In Spring Boot 3.3, `@MockBean` replaces Spring beans; mocking the secured service itself skips the method interceptor you meant to test.
- When both Spring MVC and WebFlux are on the classpath, Boot normally prefers MVC; this project uses **only** the WebFlux starter.

## 6. Reactor Context differs from ThreadLocal

In Servlet apps, `SecurityContextHolder` typically uses per-request-thread `ThreadLocal`. In WebFlux, Reactor Context follows the **subscriber**, so reactive operators retrieve the principal via:

```java
ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
```

This is an expression snippet, not a standalone class. `getContext()` can complete empty when a subscription has no security context.

### 6.1. `contextWrite` at subscription time

```java
Authentication auth = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_READER");

Mono<String> name =
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth));
```

`TestingAuthenticationToken` supplies a test authentication. `contextWrite` creates an immutable context variant for the upstream chain within that subscription, without storing `alice` in a global mutable field. `ReactiveContextUnitTest` below provides full imports and `StepVerifier`.

### 6.2. `publishOn` and `subscribeOn`

`publishOn(Schedulers.parallel())` moves downstream execution to a scheduler thread. `subscribeOn` governs how subscription/upstream execution is scheduled. In a properly composed Reactor chain, Reactor Context follows the subscriber, so `ReactiveSecurityContextHolder.getContext()` stays readable in downstream operators.

Do not assume **arbitrary `ThreadLocal`s of your own** propagate automatically. If an app uses `CompletableFuture.supplyAsync`, executors, or non-Reactor callbacks, configure an appropriate context-propagation bridge and test it explicitly.

### 6.3. FlatMap vs manual subscribe

```java
// Anti-pattern - detached subscription:
Mono.just("start").doOnNext(value -> {
    downstreamPublisher.subscribe();
});
```

`downstreamPublisher` is an illustrative variable. Manual `subscribe()` detaches the inner flow's errors, cancellation, backpressure, and context. To compose, use `flatMap(value -> downstreamPublisher)` so the inner publisher stays attached to the same reactive chain. Never call `block()` on a Netty event loop just to read a username.

## 7. Full runnable lab — Java 17, Spring Boot 3.3.0

Directory tree:

```text
reactive-security-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/reactivesecurity/
    │   ├── ReactiveSecurityLabApplication.java
    │   ├── SecurityConfig.java
    │   ├── IdentityService.java
    │   ├── AuditService.java
    │   ├── NoteInput.java
    │   ├── NoteResult.java
    │   └── SecureController.java
    └── test/java/example/reactivesecurity/
        ├── SecurityWebTestClientTest.java
        ├── ReactiveContextUnitTest.java
        └── LiveBasicAuthTest.java
```

### 7.1. settings.gradle

```groovy
rootProject.name = 'reactive-security-lab'
```

### 7.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

The Spring Boot BOM aligns Framework, Security, Reactor, and test dependencies compatible with Boot 3.3. Do not override to Spring Security 7.x due to differing APIs and version requirements.

**No Spring MVC starter** is present in the lab so the application runs reactive WebFlux auto-configuration.

## 8. Main application

**src/main/java/example/reactivesecurity/ReactiveSecurityLabApplication.java**

```java
package example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveSecurityLabApplication.class, args);
    }
}
```

## 9. SecurityConfig: SecurityWebFilterChain and method security

**src/main/java/example/reactivesecurity/SecurityConfig.java**

```java
package example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(
                                HttpMethod.POST, "/api/notes")
                            .hasRole("EDITOR")
                        .pathMatchers("/api/**")
                            .authenticated()
                        .anyExchange()
                            .denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
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
                .roles("EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin-pass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(
                reader, editor, admin);
    }
}
```

### 9.1. Why design URL rules this way?

- `GET /public` allows anonymous.
- `POST /api/notes` requires `ROLE_EDITOR` and CSRF in this sample config.
- Remaining `/api/**` requires only `authenticated`.
- `GET /api/admin/audit` is **intentionally** not restricted to ADMIN in URL rules, so `@PreAuthorize` on the service can be tested.
- `anyExchange().denyAll()` blocks undeclared paths.
- `httpBasic` enables request-credential authentication.
- `csrf` remains enabled to test missing/present tokens.

### 9.2. Security warning on demo credentials

`{noop}` and password literals are **fake accounts for this local lab**. Production requires a secure `PasswordEncoder` (BCrypt/Argon2 per policy), secrets management, TLS, user lifecycle, and a real IdP. Never copy a no-op password encoder config into public services.

### 9.3. `@EnableReactiveMethodSecurity`

This annotation activates reactive method-security AOP. Secured methods should return reactive publishers per contract. In the lab, `AuditService` is a Spring-managed bean, `readAudit()` returns `Mono<String>`, and the controller calls it through the Spring proxy.

Never call `new AuditService()` expecting annotations to run; also avoid self-invocation inside the same bean bypassing the proxy.

## 10. IdentityService.java

**src/main/java/example/reactivesecurity/IdentityService.java**

```java
package example.reactivesecurity;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> authentication.getName());
    }
}
```

This class does not store usernames in a singleton field. Each HTTP subscription reads the `Authentication` bound to its Reactor Context. Without a security context, the publisher completes empty; in the lab, `/api/**` requires `authenticated`, so valid WebFlux paths carry context.

Never use `SecurityContextHolder.getContext().getAuthentication()` inside a WebFlux scheduler callback assuming it always holds the request's user.

## 11. AuditService.java and @PreAuthorize

**src/main/java/example/reactivesecurity/AuditService.java**

```java
package example.reactivesecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuditService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readAudit() {
        return Mono.defer(() -> Mono.just("audit-ok"));
    }
}
```

The method-level rule checks `ROLE_ADMIN` from `Authentication` inside Reactor Context. When an authenticated `READER` calls the method through the proxy, Spring Security rejects it with `AccessDeniedException`, and WebFlux security error handling maps it to HTTP 403.

**Why require negative/positive pairs?** If the annotation is disabled, ADMIN still gets 200, yet READER can enter too; the READER 403 test catches that bug.

## 12. DTO classes

**src/main/java/example/reactivesecurity/NoteInput.java**

```java
package example.reactivesecurity;

public record NoteInput(String text) {}
```

**src/main/java/example/reactivesecurity/NoteResult.java**

```java
package example.reactivesecurity;

public record NoteResult(String text) {}
```

The demo simply echoes text. Its purpose is exercising CSRF/role/JSON binding, not providing persistence or sample business validation. Real systems must add validation and resource/data authorization where needed.

## 13. SecureController.java — Reactor Context after publishOn

**src/main/java/example/reactivesecurity/SecureController.java**

```java
package example.reactivesecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class SecureController {

    private final IdentityService identityService;
    private final AuditService auditService;

    public SecureController(
            IdentityService identityService,
            AuditService auditService) {
        this.identityService = identityService;
        this.auditService = auditService;
    }

    @GetMapping("/public")
    public Mono<String> publicMessage() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return identityService.currentUsername();
    }

    @GetMapping("/api/me/async")
    public Mono<String> asyncCurrentUser() {
        return Mono.just("go")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored ->
                        identityService.currentUsername())
                .map(name -> "async:" + name);
    }

    @GetMapping("/api/admin/audit")
    public Mono<String> audit() {
        return auditService.readAudit();
    }

    @PostMapping("/api/notes")
    public Mono<NoteResult> createNote(
            @RequestBody Mono<NoteInput> input) {
        return input.map(note ->
                new NoteResult(note.text()));
    }
}
```

In `asyncCurrentUser`, `publishOn` happens **before** `flatMap(ignored -> identityService.currentUsername())`, so context is read across a scheduling boundary. The test asserts only `async:alice`, not thread names like `parallel-N` or arbitrary timings.

Never call `subscribe()` manually inside a controller to trigger downstream work: WebFlux subscribes to the returned publisher and manages context/lifecycle per request.

## 14. SecurityWebTestClientTest.java — 12 request-level tests

**src/test/java/example/reactivesecurity/SecurityWebTestClientTest.java**

```java
package example.reactivesecurity;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class SecurityWebTestClientTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void buildClientWithSecurityFilters() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("public-ok");
    }

    @Test
    void protectedWithoutAuthenticationIs401() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockReaderNameFromReactorContext() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("alice");
    }

    @Test
    void mockUserCannotAccessAdminMethod() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/admin/audit")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void mockAdminCanAccessAdminMethod() {
        client.mutateWith(
                mockUser("sara").roles("ADMIN"))
                .get()
                .uri("/api/admin/audit")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("audit-ok");
    }

    @Test
    void identitySurvivesPublishOn() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/me/async")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("async:alice");
    }

    @Test
    void editorBasicWithoutCsrfGets403() {
        client.post()
                .uri("/api/notes")
                .headers(headers ->
                        headers.setBasicAuth(
                                "editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteInput("first"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorBasicWithCsrfGets200() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/notes")
                .headers(headers ->
                        headers.setBasicAuth(
                                "editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteInput("accepted"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.text")
                    .isEqualTo("accepted");
    }

    @Test
    void readerBasicWithCsrfLacksRole() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/notes")
                .headers(headers ->
                        headers.setBasicAuth(
                                "reader", "reader-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteInput("not allowed"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void invalidBasicCredentialsAre401() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth(
                                "reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserDoesNotLeakIntoNextRequest() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("alice");

        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void injectedRoleHeaderCannotElevate() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/admin/audit")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

### 14.1. Takeaways from the request test group

- **Anonymous GET 401**: protected route is verified.
- **READER GET 200 with body `alice`**: exact identity propagated, not just any user.
- **READER admin 403, ADMIN admin 200**: method security is active.
- **Async GET returns `async:alice`**: context survives `publishOn`.
- **Basic EDITOR POST without CSRF 403, with CSRF 200**: CSRF gate observed.
- **Basic READER with CSRF still 403**: CSRF does not substitute for roles.
- **Bad password GET 401**: part of the real authentication path ran without `mockUser`.
- **Request after `mockUser` stays anonymous**: identity is not stored globally.
- **`X-Role: ADMIN` cannot escalate privileges**: client-supplied role headers are ignored.

### 14.2. Where is real Spring method security tested?

The URL matcher requires only `authenticated` for `/api/admin/audit`, yet `AuditService.readAudit()` carries `@PreAuthorize("hasRole('ADMIN')")`. Because the controller injects the service bean, calls pass through the Spring proxy. If the annotation is disabled, the READER denial test turns red even though ADMIN still gets 200.

### 14.3. 401 vs 403 paired cases

If a POST lacks CSRF while sent as READER and asserts 403, you do not know whether CSRF or role caused it. The lab uses the **right EDITOR role** in both no-CSRF and with-CSRF tests to isolate CSRF. It then pairs **READER with a valid token** to prove the role rule.

### 14.4. `csrf()` is a test helper

`SecurityMockServerConfigurers.csrf()` generates a valid token for the mock `WebTestClient` security infrastructure. It does not prove browser cookie/session flows, `SameSite`, `Secure` attributes, or live CSRF token repositories. When products use session cookies, add corresponding live integration tests.

### 14.5. Do not treat `mockUser` as an authentication test

`mockUser` supplies a principal and roles trusted by the test. It never calls password encoders or JWT decoders. When testing real credentials, send Basic/Bearer in HTTP headers or test token fixtures per security config. `mockUser` fits **authorization and Reactor Context** tests.

## 15. ReactiveContextUnitTest.java — 4 tests without HTTP

**src/test/java/example/reactivesecurity/ReactiveContextUnitTest.java**

```java
package example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextUnitTest {

    private Authentication user(String name) {
        return new TestingAuthenticationToken(
                name, "unused", "ROLE_READER");
    }

    private Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
    }

    @Test
    void authenticationFromContextIsVisibleOnSubscribe() {
        Mono<String> publisher = currentName()
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("alice")));

        StepVerifier.create(publisher)
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void contextCrossesScheduler() {
        Mono<String> publisher = Mono.just("go")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> currentName())
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("bob")));

        StepVerifier.create(publisher)
                .expectNext("bob")
                .verifyComplete();
    }

    @Test
    void differentSubscriptionsRemainIsolated() {
        Mono<String> lookup = currentName();

        StepVerifier.create(
                lookup.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("alice"))))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(
                lookup.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("bob"))))
                .expectNext("bob")
                .verifyComplete();

        StepVerifier.create(lookup)
                .expectNext("anonymous")
                .verifyComplete();
    }

    @Test
    void absentContextDefaultsToAnonymous() {
        StepVerifier.create(currentName())
                .expectNext("anonymous")
                .verifyComplete();
    }
}
```

### 15.1. Why is StepVerifier the right measurement tool?

`StepVerifier.create(publisher)` initiates subscription and asserts `onNext`/`onComplete` or error signals. It does not inject an `Authentication` automatically. `contextWrite(withAuthentication(...))` is applied to the publisher under test so each subscription receives the intended identity.

### 15.2. Empty context

`ReactiveSecurityContextHolder.getContext()` can be empty outside an HTTP security chain. The `currentName()` helper uses `defaultIfEmpty("anonymous")` for observable output. In production, missing context at a secured boundary must fail closed rather than silently letting anonymous run privileged methods.

### 15.3. No leakage across subscriptions

`differentSubscriptionsRemainIsolated` reuses the exact same publisher across three subscriptions: `alice`, `bob`, and unauthenticated. It proves the principal comes from the subscription context rather than a static variable overwritten by a prior test.

### 15.4. Direct method security testing

To test `@PreAuthorize` on a service without HTTP, obtain the **Spring-managed bean proxy** and subscribe with Reactor authentication. Example (illustrative snippet requiring Spring test context/imports):

```java
Authentication reader = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_READER");

Mono<String> result = auditService.readAudit()
        .contextWrite(
                ReactiveSecurityContextHolder
                        .withAuthentication(reader));

StepVerifier.create(result)
        .expectError(AccessDeniedException.class)
        .verify();
```

If `auditService` is instantiated with `new`, Spring AOP method interceptors do not run. Never put this test in a plain unit class assuming `@PreAuthorize` runs by itself.

## 16. LiveBasicAuthTest.java — real HTTP server

**src/test/java/example/reactivesecurity/LiveBasicAuthTest.java**

```java
package example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class LiveBasicAuthTest {

    @Autowired
    WebTestClient client;

    @Test
    void liveServerAcceptsRealBasicCredentials() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth(
                                "reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("reader");
    }
}
```

This test starts an embedded HTTP server on a random port. The HTTP Basic header travels over a real network socket, Spring Security's authentication filter validates against the lab's user details, and `IdentityService` reads the principal from Reactor Context.

Do not assume this test verifies external TLS/PKI, reverse proxies, OAuth2 IdPs, mTLS, or production network security. Testing those requires an appropriate integration environment.

## 17. Run commands and expected results

The machine needs JDK 17, a compatible Gradle Wrapper (e.g., Gradle 8.7), and Maven Central access or cached dependencies. No Docker or database is required.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.reactivesecurity.SecurityWebTestClientTest
./gradlew test --tests example.reactivesecurity.ReactiveContextUnitTest
./gradlew test --tests example.reactivesecurity.LiveBasicAuthTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.reactivesecurity.SecurityWebTestClientTest
.\gradlew.bat test --tests example.reactivesecurity.ReactiveContextUnitTest
```

| Test class | Methods | Spring context | HTTP TCP |
| --- | ---: | --- | --- |
| `SecurityWebTestClientTest` | 12 | Yes | No |
| `ReactiveContextUnitTest` | 4 | No | No |
| `LiveBasicAuthTest` | 1 | Yes | Yes |
| **Total** | **17** | Depends on class | Depends on class |

**Expected result:** 17 test methods pass when code is placed in the right packages/files with matching dependencies and config. This is not a record of running Gradle; verify the real report before reporting PASS. There is no fixed business stdout; HTTP ports, scheduler thread names, logs, and test order may vary.

## 18. Common pitfalls when testing WebFlux Security

### 18.1. Mock setup missing `springSecurity()`

In a manual `bindToApplicationContext` client, omitting `.apply(springSecurity())` stops security test mutators/WebFilters from running properly. Testing only `/public` 200 does not prove the security chain was wired; include anonymous 401 and reader 403.

### 18.2. Method security bypassed

When a Spring bean carries `@PreAuthorize` yet tests instantiate it with `new` or mock the service itself, AOP method interceptors never execute. Inject the real Spring-managed bean. Watch for self-invocation within the same bean.

### 18.3. Asserting only 403

READER POST without a token returns 403 due to CSRF or role? Impossible to tell. Write paired tests with the right role plus/minus token, and wrong role with token.

### 18.4. Treating `@WithMockUser` as the Context for any Reactor chain

`@WithMockUser` belongs to Spring Security test support. In pure publisher unit tests outside HTTP/integration contexts, do not assume the annotation attaches principals across every scheduler; explicit `contextWrite` is clearer.

### 18.5. Measuring identity with `ThreadLocal`

`Thread.currentThread().getName()` does not verify context. A `ThreadLocal<String>` can vanish across `publishOn`. Assert the string read from `ReactiveSecurityContextHolder` inside a downstream operator.

### 18.6. `.subscribe()` detaching from parent chain

Manual subscriptions inside services break error, cancellation, backpressure, and context handling. Compose with `flatMap`/`map` and return the publisher for the WebFlux runtime to subscribe.

### 18.7. Blocking on the Netty event loop

Calling `block()`/`Thread.sleep()` in a reactive handler blocks the event loop, causing timeouts/hangs and defeating nonblocking execution. Never do that just to read `Authentication`, since reactive APIs already return `Mono`.

### 18.8. Static fields holding the current user

A singleton service holding `static String username` or a mutable “current principal” field risks cross-request data leakage. Reactor Context is strictly per subscription.

### 18.9. Disabling CSRF just to make tests run

Only disable CSRF when the real threat model and auth mechanism justify it, never to fix missing test tokens. With browser cookie/session authentication, CSRF is a critical risk. Stateless bearer APIs have a different threat model requiring explicit analysis.

### 18.10. Testing 401 via POST missing CSRF

CSRF can return 403 before authentication. To test the authentication entry point cleanly, hit a safe protected GET endpoint with anonymous/invalid credentials.

### 18.11. Trusting `X-Role: ADMIN`

Client-supplied HTTP headers grant no permissions. If roles come from headers, you need a trusted proxy/authenticated boundary with proper signatures/validation. The lab explicitly tests that spoofed headers never escalate privilege.

### 18.12. `@WebFluxTest` omitting security config

Web slices can omit custom `SecurityWebFilterChain` beans or services required for method security. Import configs/collaborators intentionally or use full `@SpringBootTest`.

## 19. Reactive method security, JWTs, and scopes

`@EnableReactiveMethodSecurity` reads Reactor Context to evaluate method authorization. With `@PreAuthorize("hasRole('ADMIN')")`, authority `ROLE_ADMIN` is required. Richer rules may inspect user ownership/tenant IDs, scopes, or trusted claims; role-level tests alone cannot protect multi-tenant data.

### 19.1. `mockJwt` does not prove JWT signatures

`mockJwt()` is a test mutator for apps with OAuth2 resource server config and matching dependencies. It injects simulated claims/authorities onto the test exchange, typically **without** calling a real JWT decoder or verifying signatures.

Illustrative snippet only (not part of the runnable project because it lacks the resource-server module/route):

```java
client.mutateWith(
        mockJwt()
            .jwt(jwt -> jwt.subject("alice"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_read")))
        .get()
        .uri("/api/secure")
        .exchange();
```

To test real JWT security, configure a `ReactiveJwtDecoder` with test keys and send actually signed bearer tokens, including invalid signature/issuer/audience/expiry cases. Never place production tokens in CI fixtures or logs.

### 19.2. `@WithMockUser` and `mockUser`

`mockUser` scopes to a single `WebTestClient` request; `@WithMockUser` is annotation-based setup in Spring Security tests. Both **simulate principals** without exercising password encoders, user databases, or external IdPs.

Pure `StepVerifier` tests need context inside the publisher. Outside an HTTP security chain, explicit `ReactiveSecurityContextHolder.withAuthentication(...)` is the clearest approach.

## 20. When must you test outside the HTTP mock boundary?

| Goal | Required test |
| --- | --- |
| Method security and HTTP statuses | Mock-bound `WebTestClient` + security config |
| Reactor context after scheduler | `StepVerifier` + `contextWrite` |
| HTTP Basic over socket | `SpringBootTest` `RANDOM_PORT` |
| Cookie-based CSRF repository/`SameSite` | Live HTTP/browser-like test with sessions |
| JWT issuer/audience/signature/expiry | Decoder + signed fixture/JWKS test |
| OAuth2 login redirects/sessions | Provider sandbox/auth server test |
| mTLS, reverse proxy, ingress, WAF | Deployment/security integration environment |
| Multi-tenant data isolation | Authorization tests across multiple tenants/resources |
| Replay/duplicate requests | Idempotency tests across business/storage layers |

Never call a mock-bound `WebTestClient` test end-to-end against an IdP or production network, even though it executes the real Controller, Service, and SecurityConfig.

## 21. Security context in scheduled jobs and messaging

Kafka consumers and scheduled jobs can run Reactor publishers **outside an HTTP request**, leaving `ReactiveSecurityContextHolder.getContext()` empty. When business methods require an authenticated identity:

1. Decide where the trusted service identity comes from.
2. Verify event signatures/tokens/sources before constructing an `Authentication`.
3. Attach the `Authentication` to that specific pipeline's Reactor Context.
4. Never read a client-supplied role header and pass it straight to `withAuthentication`.
5. Test missing identity, right role, and insufficient permission.
6. Never cache context in a global field or let Request A inherit Request B's principal.

**`withAuthentication` is merely the transport setting context**, not verification that the authentication object itself is trustworthy.

## 22. Quick troubleshooting

| Symptom | Cause | Check |
| --- | --- | --- |
| Anonymous GET 200 | Missing security filter or `permitAll` URL | Chain/configurer |
| `mockUser` GET 401 | Client not mutated properly or filter missing | `apply(springSecurity())` |
| READER admin 200 | Method security not enforced | `@EnableReactiveMethodSecurity`, AOP proxy |
| ADMIN admin 403 | Wrong role/authority name | `ROLE_ADMIN` vs `hasRole` |
| EDITOR POST 403 | Missing CSRF token or wrong role | Paired token tests |
| READER + CSRF 403 | Missing `ROLE_EDITOR` | Expected |
| Wrong Basic password 200 | Auth flow bypassed/mocked | Real Basic header & user details |
| `getContext` empty | No context in subscription | `WebFilter` or `contextWrite` |
| Wrong scheduler identity | Detached `subscribe`/ThreadLocal | Compose chain, read downstream |
| Live HTTP `mockUser` has no effect | Mock principal never crosses sockets | Real credentials/tokens |
| Test passes when annotation removed | Only positive cases tested | Add READER negative test |
| `@WebFluxTest` missing beans | Slice skips custom config | `@Import` or full context |
| 302 instead of 401 | Form login entry point | Match security config |
| Anonymous POST 403 instead of 401 | CSRF filter rejects before auth | GET auth test |
| WebFlux event loop blocked | `block`/`sleep`/legacy I/O | Nonblocking operators, `StepVerifier` |
| Two requests see same principal | Static mutable field/cache scope | Context isolation tests |

When test-only logs are needed:

```properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.web.reactive=DEBUG
```

Never enable broad debug/trace logging in production or public CI if logs could capture `Authorization` headers, tokens, credentials, principal names, session IDs, or PII.

## 23. Exercises

1. Temporarily omit `.apply(springSecurity())`; check whether negative tests still detect the missing filter.
2. Remove `@EnableReactiveMethodSecurity`; can READER reach `/api/admin/audit`? Restore it.
3. Change mock admin to READER; expect 403.
4. Temporarily omit `csrf()` on EDITOR POST; expect 403; add it back and expect 200.
5. Use READER with CSRF; expect 403 due to role.
6. Change a valid HTTP Basic password to an invalid one; expect 401.
7. Move context reading before `publishOn` and pass only a `String`; contrast testing true context propagation vs propagating a plain `String`.
8. Omit `contextWrite` from a `StepVerifier` test; expect `"anonymous"` from the helper.
9. Subscribe to the same publisher with separate `alice`/`bob` contexts; confirm no leakage.
10. Call `new AuditService()` and compare against the Spring proxy to understand the AOP boundary.
11. Try a WebFlux slice test; import security config/collaborators to preserve rules.
12. Add a JWT decoder integration test with test keys; reserve `mockJwt` for authorization unit tests.
13. Expand to multi-tenant ownership authorization; matching roles alone do not grant access to another tenant's resources.
14. Have READER send `X-Role: ADMIN` and confirm no privilege escalation.
15. Test background publishers without HTTP context and verify service authentication has a verified source.
16. Run the live `RANDOM_PORT` test and verify wrong Basic passwords fail over the socket.

## 24. Checklist before closing QA

- [ ] Spring WebFlux chosen consistently without mixing Servlet MVC.
- [ ] `SecurityWebFilterChain`/`ServerHttpSecurity` configuration loaded.
- [ ] Manually bound `WebTestClient` calls `.apply(springSecurity())`.
- [ ] Anonymous GET 401 and authenticated GET 200 verified.
- [ ] READER 403 and ADMIN 200 verified on secured method.
- [ ] `@EnableReactiveMethodSecurity` and real bean proxy used.
- [ ] POST with right role missing CSRF token returns 403; with token returns 200.
- [ ] POST with CSRF yet lacking role still returns 403.
- [ ] `mockUser` treated strictly as fake identity, never credential validation.
- [ ] When real authentication is needed, real Basic/Bearer headers are sent.
- [ ] `ReactiveSecurityContextHolder` used inside Publishers.
- [ ] `StepVerifier` injects context via `contextWrite(withAuthentication)`.
- [ ] Verified context reading after `publishOn`.
- [ ] No principal leakage across requests or subscriptions.
- [ ] Current user never stored in singleton/static mutable fields.
- [ ] No manual `subscribe()` or `block()` inside WebFlux handlers.
- [ ] No self-invocation bypassing `@PreAuthorize`.
- [ ] `@MockBean` never replaces the bean whose method security is under test.
- [ ] Unverified `X-Role`/headers/claims never trusted.
- [ ] `mockJwt` never mistaken for JWT signature verification.
- [ ] CSRF enabled/disabled by threat model, not test convenience.
- [ ] Live HTTP tests send real credentials rather than relying on mock principals across sockets.
- [ ] Tests never assert fixed thread names, ports, or timings.
- [ ] No real credentials/JWTs/PII in fixtures or logs.
- [ ] Real executed/passed/failed/skipped counts verified before reporting results.
- [ ] TLS, IdP, or production ingress never claimed proved solely by mock `WebTestClient`.

## 25. Decision summary

```text
Test objective?
    |
    +-- Pure business rule?
    |      -> JUnit/Mockito.
    |
    +-- WebFlux request auth/roles/CSRF?
    |      -> WebTestClient.bindToApplicationContext
    |         + springSecurity() + mockUser()/csrf().
    |
    +-- Reactor identity across schedulers?
    |      -> ReactiveSecurityContextHolder
    |         + contextWrite + StepVerifier.
    |
    +-- @PreAuthorize method enforcement?
    |      -> Spring proxy + allowed/denied tests.
    |
    +-- Real Basic/Bearer HTTP?
    |      -> RANDOM_PORT + actual headers.
    |
    +-- JWT signature/issuer/audience?
    |      -> Real token decoder and test keys.
    |
    +-- TLS/IdP/ingress/HA?
           -> Staging/deployment security tests.
```

**Remember:** Reactive security testing must account for both HTTP security filters and the **Reactor subscriber context**. `WebTestClient` verifies 401/403, `mockUser`, and `csrf` inside the request pipeline; `StepVerifier` and `ReactiveSecurityContextHolder` verify identity propagation per reactive subscription. Positive/negative pairs prevent false-green tests. Never equate mock principals with real authentication or mock HTTP tests with production security certification.

## 26. Official documentation

- Spring Boot 3.3 — Testing Spring Boot Applications, WebFlux/WebTestClient: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — WebTestClient mock and live setup: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — Reactive WebTestClient setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Testing Authentication, mockUser: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — Testing CSRF, csrf(): https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — Enable Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Reactive HTTP authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — SecurityMockServerConfigurers Javadoc: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
- JUnit Jupiter — User Guide: https://docs.junit.org/current/user-guide/
