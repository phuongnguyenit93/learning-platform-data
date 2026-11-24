# Implementing the Same Policy in WebFlux and Verifying Reactor Context

> **Topic:** Spring Security — authorization, **Integration Practice** group. The goal is using **a single authorization policy** for both the Spring WebFlux HTTP layer and the service layer protected by reactive method security, while verifying that `Authentication` flows through **each subscriber's Reactor Context**, even when execution switches schedulers. This practice uses Java 17, Spring Boot 3.x, Spring Security 6.x, Project Reactor, WebTestClient, and StepVerifier.

## 1. Expected Outcomes

After this lesson, you will be able to:

1. Distinguish authentication in `SecurityWebFilterChain`, URL authorization, and `@PreAuthorize` on methods returning `Mono`/`Flux`.
2. Implement a **single source of truth for rules**: a user needs authority `report:read` **and** must own the report, unless granted `report:read:any`.
3. Reuse `ReportPolicy.canRead(authentication, id)` in both HTTP authorization and method authorization, preventing two rules from drifting apart.
4. Read `ReactiveSecurityContextHolder.getContext()` inside a reactive chain instead of reading a Servlet app's ThreadLocal `SecurityContextHolder` to find the principal.
5. Test both HTTP requests with `WebTestClient` and direct service calls with `StepVerifier`, covering anonymous users, missing permissions, wrong owners, scheduler switches, and two concurrent subscribers.
6. Diagnose Reactor Context loss caused by manual `subscribe()`, `block()`/ThreadLocal, non-Reactor callbacks, self-invocation, or tests going only through controllers.

**Test contract:** report 101 belongs to user `an`; report 102 belongs to user `binh`. `an` holding only `report:read` can view 101 but not 102. `reviewer` holding `report:read` and `report:read:any` can view 102. A user holding only `report:write` is denied both.

## 2. Big Picture of Authorization in WebFlux

In a Spring WebFlux application, the request chain flows through reactive security filters. After authentication, Spring Security stores the request's `SecurityContext` in the **Reactor Context** so downstream operators, including reactive method security, see the current subscriber's authentication.

~~~text
HTTP request GET /api/reports/101
  |
  v
SecurityWebFilterChain
  |-- Authentication (user an)
  |-- ReactiveAuthorizationManager for URL + reportId
  |          \-- ReportPolicy.canRead(an, 101)
  |
  v
ReportController.view(101) -> Mono<ReportView>
  |
  v
ReportService.read(101)
  |-- @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
  |          \-- SAME ReportPolicy.canRead(an, 101)
  |-- repository lookup
  |-- publishOn(...)
  |-- ReactiveSecurityContextHolder.getContext()
  |
  v
HTTP 200 + data; or 401/403 if not permitted
~~~

Key points to remember:

- **Authentication**: “who is sending the request?”, e.g., `Authentication.getName() == "an"`.
- **Function authorization**: “does the caller have `report:read`?”.
- **Object authorization**: “is the caller allowed to read this specific `reportId`?”.
- **Reactor Context**: **per-subscription** data, not a global variable or a ThreadLocal pinned to one thread.
- **Reactive method security**: `@EnableReactiveMethodSecurity` activates `@PreAuthorize` for Spring-managed beans with appropriate reactive return types; checks normally run in the subscribe flow.
- **Defense in depth**: check at HTTP to reject early and at the service to prevent new endpoints or internal callers from bypassing business rules.

The policy must obtain the principal from Spring Security (already authenticated) and resource data on the server. Never accept an `isAdmin` or `owner` field sent by the client as proof of permission.

## 3. How Does Reactor Context Differ from ThreadLocal?

A reactive pipeline can execute across multiple threads, especially with `publishOn`, `subscribeOn`, asynchronous I/O, or merging multiple `Mono`s. Servlet-style ThreadLocal `SecurityContextHolder.getContext()` does not guarantee retrieving the current subscriber's authentication in WebFlux.

~~~java
// DO NOT use this as the standard way to get the principal in a WebFlux chain:
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Proper usage:

~~~java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

When not going through HTTP filters (e.g., service tests), attach context **on the subscribed publisher**:

~~~java
Mono<String> withUser = currentUsername.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));
~~~

`contextWrite(...)` applies to a subscription; it is **not** a command mutating a global ThreadLocal. Each subscription can carry a different `Authentication`. Building a `Mono` first and adding `contextWrite` at subscribe time still works if all operators propagate Context properly.

A subtle bug is creating a `Mono`, calling `subscribe()` inside the method, and returning another `Mono`: you created a detached subscription, losing error management, transactions, or security context, so “single-flow” assumptions break. In server code, **return the publisher** and let the WebFlux subscriber drive execution.

## 4. Setting Up a Spring Boot + WebFlux Project

The example uses **Spring Boot 3.x / Spring Security 6.x** and Java 17. Do not also add `spring-boot-starter-web` to this application: that starter can cause Spring Boot to pick MVC instead of WebFlux. When upgrading to Boot 4/Security 7, use the proper version BOM and migration notes, then re-run the entire test suite.

### 4.1. Dependencies

In a Maven project already using the Spring Boot parent/BOM, add:

~~~xml
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
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Sample code layout:

~~~text
src/main/java/com/example/reactiveauth/
    ReactiveAuthApplication.java
    Report.java
    ReportView.java
    ReportRepository.java
    ReportPolicy.java
    ReportService.java
    ReportController.java
    WebFluxSecurityConfig.java
src/test/java/com/example/reactiveauth/
    ReportHttpSecurityTest.java
    ReportReactorContextTest.java
~~~

Every Java file in the example shares `package com.example.reactiveauth`. Choose a Spring Boot 3.x version supporting Java 17 and Spring Security 6.x via its BOM; do not randomly mix different Spring Framework/Security versions.

### 4.2. Main Application

File `src/main/java/com/example/reactiveauth/ReactiveAuthApplication.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
~~~

Run command from the project using Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

In Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Startup output depends on version, port, and environment; by default a Boot WebFlux app typically listens on port 8080 unless `server.port` is changed. Do not predict fixed framework stdout.

## 5. Single Data Source and Single Authorization Policy

### 5.1. Domain Model

File `src/main/java/com/example/reactiveauth/Report.java`:

~~~java
package com.example.reactiveauth;

public record Report(long id, String owner, String title) {
}
~~~

File `src/main/java/com/example/reactiveauth/ReportView.java`:

~~~java
package com.example.reactiveauth;

public record ReportView(
        long id,
        String owner,
        String title,
        String seenBy) {
}
~~~

`seenBy` is a field included **only in this demo** to prove the principal actually traveled through Reactor Context after `publishOn`; it is unnecessary to expose subscriber details in production JSON.

### 5.2. Repository Holding Illustrative Data

File `src/main/java/com/example/reactiveauth/ReportRepository.java`:

~~~java
package com.example.reactiveauth;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class ReportRepository {

    private final Map<Long, Report> reports = Map.of(
            101L, new Report(101L, "an", "Bao cao cua An"),
            102L, new Report(102L, "binh", "Bao cao cua Binh")
    );

    public Optional<Report> findById(long id) {
        return Optional.ofNullable(reports.get(id));
    }
}
~~~

The in-memory repository returns `Optional` synchronously without I/O, suitable for illustrating a **non-blocking** policy. In real applications, **never put JDBC or blocking I/O** inside `@PreAuthorize` expressions on the WebFlux event loop. With R2DBC/remote PDPs, design asynchronous policies using a reactive authorization manager/service pipeline instead; never call `block()` to force a result.

### 5.3. Shared Permission Definition

File `src/main/java/com/example/reactiveauth/ReportPolicy.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {

    private final ReportRepository repository;

    public ReportPolicy(ReportRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long reportId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        boolean hasReadPermission = authentication.getAuthorities().stream()
                .anyMatch(a -> "report:read".equals(a.getAuthority()));

        if (!hasReadPermission) {
            return false;
        }

        return repository.findById(reportId)
                .map(report -> {
                    boolean owner = report.owner().equals(
                            authentication.getName());

                    boolean allowedAcrossOwners =
                            authentication.getAuthorities().stream()
                                    .anyMatch(a ->
                                            "report:read:any".equals(
                                                    a.getAuthority()));

                    return owner || allowedAcrossOwners;
                })
                .orElse(false);
    }
}
~~~

The policy returns `false` if unauthenticated, missing `report:read`, or the report does not exist. Holding `report:read:any` **does not replace** the base `report:read` permission. Only with both can `reviewer` read cross-owner. Never derive authorities from a frontend role variable.

This policy does not depend on Reactor APIs: it is a plain Java function taking a verified `Authentication` and an ID. The advantage is that **both the HTTP reactive authorization manager and the reactive method annotation reuse the exact same decision**. Since the repository is in memory, `canRead` is non-blocking. With a multi-tenant database, filter/check by real tenant/owner rather than only generic roles.

## 6. WebFlux Configuration: HTTP Also Calls the Same ReportPolicy

File `src/main/java/com/example/reactiveauth/WebFluxSecurityConfig.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http, ReportPolicy reportPolicy) {

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(
                                HttpMethod.GET, "/api/reports/{id}")
                        .access((authentication, context) -> {
                            long id;
                            try {
                                Object rawId =
                                        context.getVariables().get("id");
                                id = Long.parseLong(String.valueOf(rawId));
                            } catch (NumberFormatException error) {
                                return Mono.just(
                                        new AuthorizationDecision(false));
                            }

                            long reportId = id;
                            return authentication
                                    .map(auth -> new AuthorizationDecision(
                                            reportPolicy.canRead(
                                                    auth, reportId)))
                                    .defaultIfEmpty(
                                            new AuthorizationDecision(false));
                        })
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // DEMO DATA: never use {noop} passwords in production.
        UserDetails an = User.withUsername("an")
                .password("{noop}demo-only")
                .authorities("report:read")
                .build();

        UserDetails binh = User.withUsername("binh")
                .password("{noop}demo-only")
                .authorities("report:read")
                .build();

        UserDetails reviewer = User.withUsername("reviewer")
                .password("{noop}demo-only")
                .authorities("report:read", "report:read:any")
                .build();

        return new MapReactiveUserDetailsService(
                an, binh, reviewer);
    }
}
~~~

Explanation:

- `@EnableWebFluxSecurity` activates WebFlux security filters; `@EnableReactiveMethodSecurity` activates reactive method security. Adding the starter alone does not automatically enable method annotations.
- `pathMatchers(HttpMethod.GET, "/api/reports/{id}")` matches the exact route; `AuthorizationContext.getVariables().get("id")` reads the matched path variable rather than trusting a client-sent `owner` body field.
- Unparseable ID: **DENY** instead of trying a permissive default. Clients may receive 403; in real systems routing/input validation may return 400 while still returning no data.
- `authentication` in the `access` callback is a `Mono<Authentication>`; `map` creates an `AuthorizationDecision` from the **same** `ReportPolicy`, and `defaultIfEmpty(false)` blocks when no identity is present. Never call `block()`.
- `anyExchange().denyAll()` denies all other APIs/methods by default.
- `httpBasic` is only for testing HTTP 401 status in the demo. When deploying an OAuth2 Resource Server/JWT or sessions, swap in the proper authentication mechanism **while keeping the same ReportPolicy rules**.
- CSRF stays at its default; the demo uses GET only. For POST/PUT/DELETE, configure explicit CSRF and authorization rules rather than disabling CSRF reflexively.

**On sharing the same policy:** both the HTTP gate and the service gate call `ReportPolicy.canRead`, avoiding two separate `owner.equals(...)` copies that easily drift. In production, avoid querying the DB twice; you can enforce functional permissions at HTTP and object permissions at the service, or use an appropriate evaluator/cache so the same policy logic runs without redundant I/O.

## 7. Service: Method Security and Reading Principal After publishOn

File `src/main/java/com/example/reactiveauth/ReportService.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
    public Mono<ReportView> read(long reportId) {
        return Mono.defer(() -> Mono.justOrEmpty(
                        repository.findById(reportId)))
                // Switch scheduler to prove subscriber context
                // follows the reactive chain rather than depending on the thread.
                .publishOn(Schedulers.parallel())
                .flatMap(report ->
                        ReactiveSecurityContextHolder.getContext()
                                .map(SecurityContext::getAuthentication)
                                .map(authentication ->
                                        new ReportView(
                                                report.id(),
                                                report.owner(),
                                                report.title(),
                                                authentication.getName())))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Report not found")));
    }
}
~~~

Because `ReportService` is a Spring bean and the method returns `Mono<ReportView>`, `@PreAuthorize` executes reactively upon subscription. `#p0` is the first parameter (`reportId`), independent of whether the compiler retains parameter names.

`ReactiveSecurityContextHolder.getContext()` is read **after switching schedulers**. When successful, `seenBy` still reflects the exact user. This is a useful check against ThreadLocal reliance. In normal WebFlux requests, the security filter populates context on the reactive subscription; when testing the service without HTTP, attach `contextWrite` yourself.

**Demo limitation:** `publishOn(Schedulers.parallel())` here merely illustrates Context propagation, not advice to switch schedulers for in-memory reads. Never use `Schedulers.parallel()` to run blocking JDBC. This pattern uses `Mono.defer` to avoid running repository lookup before subscription, and `switchIfEmpty` when a report does not exist.

## 8. WebFlux Controller Does Not Decide Permissions Directly

File `src/main/java/com/example/reactiveauth/ReportController.java`:

~~~java
package com.example.reactiveauth;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ReportView> view(@PathVariable long id) {
        return service.read(id);
    }
}
~~~

The controller only returns the publisher from the Spring service bean. It never calls `subscribe()` or `block()`. If another endpoint is added calling the same `service.read(id)`, method security still protects the business operation. **Direct service tests** in section 10 prove the rule does not live solely in the HTTP filter.

### 8.1. Quick Testing via HTTP Basic Demo

After starting the application:

~~~bash
curl -i http://localhost:8080/api/reports/101
curl -i -u an:demo-only http://localhost:8080/api/reports/101
curl -i -u an:demo-only http://localhost:8080/api/reports/102
curl -i -u reviewer:demo-only http://localhost:8080/api/reports/102
~~~

Expected statuses (HTTP headers/error body details depend on version):

| Request | HTTP | Why |
| --- | --- | --- |
| Unauthenticated, reading 101 | 401 | HTTP Basic challenges for identity |
| `an`, reading 101 | 200 | `report:read` and matching owner |
| `an`, reading 102 | 403 | Valid authority yet wrong owner |
| `reviewer`, reading 102 | 200 | Holds both `report:read` and `report:read:any` |
| `an`, calling `DELETE /api/reports/101` | Denied | `anyExchange().denyAll()` and possible CSRF enforcement |

Successful responses return `ReportView` JSON, for example for `an`:

~~~json
{
  "id": 101,
  "owner": "an",
  "title": "Bao cao cua An",
  "seenBy": "an"
}
~~~

`seenBy = "an"` is solely proof that Reactor Context propagated through the chain. In real systems, avoid returning this field unless there is a business need.

## 9. HTTP Integration Testing: WebTestClient + springSecurity()

To test real HTTP authorization (not clicking UI buttons), use Spring Test and the Security WebTestClient configurer. The client binds to the started Spring `ApplicationContext`, applies `springSecurity()`, and attaches test identities with `mockUser`.

File `src/test/java/com/example/reactiveauth/ReportHttpSecurityTest.java`:

~~~java
package com.example.reactiveauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReportHttpSecurityTest {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousGets401() {
        client.get().uri("/api/reports/101")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void missingReadAuthorityGets403() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:write")))
                .get().uri("/api/reports/101")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void ownerSeesOwnReportAndItsReactorPrincipal() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:read")))
                .get().uri("/api/reports/101")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("an")
                .jsonPath("$.seenBy").isEqualTo("an");
    }

    @Test
    void changingIdCannotReadOtherOwnersReport() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:read")))
                .get().uri("/api/reports/102")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void reviewerWithBothPermissionsCanReadCrossOwner() {
        client.mutateWith(mockUser("reviewer").authorities(
                        new SimpleGrantedAuthority("report:read"),
                        new SimpleGrantedAuthority("report:read:any")))
                .get().uri("/api/reports/102")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("binh")
                .jsonPath("$.seenBy").isEqualTo("reviewer");
    }

    @Test
    void elevatedObjectPermissionAloneDoesNotGrantRead() {
        client.mutateWith(mockUser("reviewer").authorities(
                        new SimpleGrantedAuthority("report:read:any")))
                .get().uri("/api/reports/102")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void invalidReportIdIsNotGrantedAccess() {
        client.mutateWith(mockUser("an").authorities(
                        new SimpleGrantedAuthority("report:read")))
                .get().uri("/api/reports/not-a-number")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Java syntax note:** in the example above, two static imports are split across two lines before the dot (`...server` then `.SecurityMockServerConfigurers...`). Java allows line breaks there, though when copying into an IDE you can write them cleanly on single lines:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
~~~

Do not paste both import styles into the same file; choose the single-line style for readability. `mockUser` only simulates an identity **for authorization testing**; it does not verify real passwords/JWTs.

**Expected result:** seven HTTP tests PASS when running matching Spring Boot 3.x + Security 6.x with the filter and method beans from the example. There is no fixed stdout from tests/framework; HTTP statuses and JSON paths are asserted. If the app does not enable Spring WebFlux properly, tests fail on context setup rather than silently passing the policy.

## 10. Testing Service Reactor Context with StepVerifier

This is the most important part: **calling the service directly** without HTTP filters. Attach `Authentication` to Reactor Context with `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))`; verify `@PreAuthorize` and `seenBy` after `publishOn`.

File `src/test/java/com/example/reactiveauth/ReportReactorContextTest.java`:

~~~java
package com.example.reactiveauth;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReportReactorContextTest {

    @Autowired
    ReportService service;

    private static Authentication user(
            String name, String... authorities) {
        var grants = java.util.Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .toList();
        return new UsernamePasswordAuthenticationToken(
                name, "n/a", grants);
    }

    @Test
    void anCanReadHisReportAfterPublishOn() {
        Authentication an = user("an", "report:read");

        Mono<ReportView> publisher = service.read(101L)
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(an));

        StepVerifier.create(publisher)
                .expectNextMatches(view ->
                        view.id() == 101L
                        && "an".equals(view.owner())
                        && "an".equals(view.seenBy()))
                .verifyComplete();
    }

    @Test
    void sameUserIsDeniedForAnotherOwner() {
        Authentication an = user("an", "report:read");

        StepVerifier.create(
                        service.read(102L)
                                .contextWrite(
                                        ReactiveSecurityContextHolder
                                                .withAuthentication(an)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void authorityWithoutFunctionPermissionIsDenied() {
        Authentication reviewer = user(
                "reviewer", "report:read:any");

        StepVerifier.create(
                        service.read(102L)
                                .contextWrite(
                                        ReactiveSecurityContextHolder
                                                .withAuthentication(
                                                        reviewer)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void approvedReviewerMayReadCrossOwner() {
        Authentication reviewer = user(
                "reviewer", "report:read", "report:read:any");

        StepVerifier.create(
                        service.read(102L)
                                .contextWrite(
                                        ReactiveSecurityContextHolder
                                                .withAuthentication(
                                                        reviewer)))
                .expectNextMatches(view ->
                        view.id() == 102L
                        && "binh".equals(view.owner())
                        && "reviewer".equals(view.seenBy()))
                .verifyComplete();
    }

    @Test
    void concurrentSubscribersRemainIsolated() {
        Authentication an = user("an", "report:read");
        Authentication binh = user("binh", "report:read");

        Mono<ReportView> first = service.read(101L)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(an));
        Mono<ReportView> second = service.read(102L)
                .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(binh));

        StepVerifier.create(Mono.zip(first, second))
                .expectNextMatches(pair ->
                        "an".equals(pair.getT1().seenBy())
                        && "binh".equals(pair.getT2().seenBy())
                        && pair.getT1().id() == 101L
                        && pair.getT2().id() == 102L)
                .verifyComplete();
    }

    @Test
    void publisherCanBeBuiltBeforeContextIsWritten() {
        Mono<ReportView> waitingForSubscriber = service.read(101L);
        Authentication an = user("an", "report:read");

        StepVerifier.create(waitingForSubscriber.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(an)))
                .expectNextMatches(view ->
                        "an".equals(view.seenBy()))
                .verifyComplete();
    }
}
~~~

Note: the `java.util.List` import in the test file is unused (only `Arrays` is used). The Java compiler allows unused imports; you can remove it to keep code tidy. Test names intentionally describe what they verify: `concurrentSubscribersRemainIsolated` creates two publishers with separate contexts and uses `Mono.zip` to subscribe to both, without relying on shared ThreadLocal state. In multi-request apps, also test that context does not leak across connection pools, caches, and non-Reactor callbacks.

Run with Maven Wrapper:

~~~bash
./mvnw -Dtest=ReportHttpSecurityTest,ReportReactorContextTest test
~~~

Windows:

~~~powershell
.\mvnw.cmd "-Dtest=ReportHttpSecurityTest,ReportReactorContextTest" test
~~~

**Expected:** 7 HTTP tests and 6 service tests PASS; `publisherCanBeBuiltBeforeContextIsWritten` proves the publisher is constructed first and context is supplied at subscription time. If a different `AccessDeniedException` occurs due to config/context mistakes, inspect the root cause rather than loosening assertions to accept any exception.

## 11. Matrix Verifying the Same Policy Across HTTP and Service

| Scenario | HTTP WebTestClient | Service StepVerifier | Decision |
| --- | --- | --- | --- |
| Unauthenticated | `401` | Must deny when no Reactor Authentication | DENY |
| Has `report:write`, lacks `report:read` | `403` | `AccessDeniedException` | DENY |
| `an` reads report 101 | `200` + `seenBy=an` | Mono emits matching `ReportView` | ALLOW |
| `an` reads report 102 | `403` | `AccessDeniedException` | DENY |
| Reviewer has only `report:read:any` | `403` | `AccessDeniedException` | DENY |
| Reviewer has both authorities, reads 102 | `200` + `seenBy=reviewer` | Mono emits matching data | ALLOW |
| Non-numeric path ID | `403` in demo HTTP matcher | `long` service not invoked | DENY |
| Two subscriptions with different identities | Add parallel HTTP test if needed | Isolated `Mono.zip` | No context leak |

Verifying the same policy means **same input principal + action + resource + context -> same permission**. HTTP can return 401 for anonymous via an authentication entry point; a method publisher emits a security error rather than an HTTP status. Do not compare exception text with HTTP status; compare ALLOW/DENY semantics and observed data.

With multiple tenants, policies must add `tenantId` from verified identity and server data. Checking only an authority and returning any `reportId` causes BOLA/IDOR even when Reactor Context propagated properly.

## 12. Stricter Ways to Test Reactor Context

### 12.1. Switching Schedulers Does Not Drop Context

Standard Reactor operators `publishOn` and `subscribeOn` propagate **Reactor Context with the subscription**. A common mistake is using APIs that spawn execution outside Reactor without preserving Context.

~~~java
// Correct: the publisher remains in the same reactive chain.
return source.publishOn(Schedulers.parallel())
        .flatMap(value ->
                ReactiveSecurityContextHolder.getContext()
                        .map(ctx -> value + ":" +
                                ctx.getAuthentication().getName()));
~~~

This is a **snippet**, assuming `source` is a `Mono<String>`; not a standalone file. Never use `new Thread(...)` and call `SecurityContextHolder.getContext()` expecting WebFlux's principal. For external callbacks or `CompletableFuture`, bridge context explicitly with an appropriate mechanism instead of writing a global static holder.

### 12.2. Do Not Call subscribe() Manually Inside Services

~~~java
// WRONG: internal subscription detaches from the HTTP flow,
// errors, cancellation, and caller context are no longer managed.
Mono<ReportView> result = service.read(101L);
result.subscribe(view -> saveAudit(view));
return Mono.empty();
~~~

The proper approach is **composing** a single chain and returning the publisher; if auditing is needed, use `doOnNext`/`flatMap` connected to a reactive audit publisher to await completion properly. Reserve `doOnNext` for short, non-blocking side effects.

~~~java
// Snippet: write audit asynchronously and return only when finished.
return service.read(101L)
        .flatMap(view -> auditRepository.saveEvent(view.id())
                .thenReturn(view));
~~~

`auditRepository.saveEvent` here is a hypothetical interface returning `Mono<?>` that must be implemented; it is not a built-in Spring Security method.

### 12.3. Do Not Block the Event Loop to Read SecurityContext

~~~java
// WRONG in WebFlux: block can cause deadlocks,
// event-loop errors, or loss of subscription-attached context.
Authentication auth = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .block();
~~~

Never call `block()` in a production reactive chain, especially on an event-loop thread. For blocking DB access, switch to a reactive driver or isolate a proper blocking adapter, rather than forcing `Authentication` out of context and storing it in a ThreadLocal manually.

### 12.4. Distinguish Subscriber Context from Global State

A single publisher can be subscribed to twice with two different `Authentication`s. If code stores `Authentication` in a static variable or singleton field and reuses it for the next request, it creates a **cross-request data leak**. Ensure every decision reads fresh context per subscription and never caches ALLOW results without principal/resource/tenant/policy version.

## 13. Compatibility Notes for Spring Security 6.x and 7.x

Spring Security reactive method authorization uses `@EnableReactiveMethodSecurity`. Documentation and annotation options evolve across versions. Many Spring Security 6.x guides show `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`; newer versions may use AuthorizationManager by default. Never copy flags or custom interceptors verbatim from older articles without checking your active dependencies.

In Spring Security 7.x, interfaces/return types of custom authorization managers may change compared to 6.x. **Do not mix a `ReactiveAuthorizationManager` implementation written against 7.x signatures into a 6.x app.** Section 6's example avoids defining a custom manager class; it uses the `access` lambda and `AuthorizationDecision` common in 6.x, and when upgrading versions you should consult the migration guide, recompile, and re-test.

Two points must not be overlooked:

1. Spring Security Servlet uses `SecurityFilterChain`, `HttpSecurity`, `@EnableMethodSecurity`. WebFlux uses **`SecurityWebFilterChain`, `ServerHttpSecurity`, `@EnableReactiveMethodSecurity`**. They are not directly interchangeable.
2. Reactive `@PreAuthorize` guards the publisher during subscription. If a method returns a synchronous value or you call `block()` yourself and return the computed object, authorization and context propagation may stop working properly. Return `Mono`/`Flux`/Publisher and test against real Spring beans.

Pin versions in CI, verify dependency compatibility, and audit every ALLOW/DENY change on upgrades. Never infer from a single `200` test that all permissions remain intact.

## 14. Common Mistakes and Fixes

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| `403` for valid owner | Missing `report:read`, wrong role mapping, faulty policy result | Inspect raw authorities and owner in server data |
| User with authority reads another owner's report | Checked only functional permission, missing object policy | Share `ReportPolicy.canRead` across HTTP + service |
| HTTP works yet direct service call bypasses policy | `@EnableReactiveMethodSecurity` disabled, not calling Spring proxy | `StepVerifier` test calling `@Autowired` bean |
| Service gives 404 instead of 403 on unknown ID | Different policy/model for nonexistent objects | Standardize 403/404 consistently without leaking data |
| Reactive method security test loses principal | Did not attach `contextWrite` on subscribed publisher | Attach `ReactiveSecurityContextHolder.withAuthentication(auth)` |
| Principal is null after `publishOn` | Accessed Servlet ThreadLocal or non-Reactor callback | Use `ReactiveSecurityContextHolder` and compose chains |
| Two requests leak identities | Stored auth in static field / singleton | Never share Authentication; test `zip`/concurrent subscriptions |
| `WebTestClient` mockUser has no effect | Forgot `apply(springSecurity())` or bound wrong context | Use the proper test configurer |
| Manual `subscribe()` called | Detached reactive chain from original subscriber | Return publisher and chain operators |
| Using JDBC inside `canRead` | Blocks event loop, increases latency | Use R2DBC, reactive authorization manager, avoid `block()` |
| Using `SecurityContextHolder` in WebFlux | ThreadLocal does not reflect subscriber context | Use `ReactiveSecurityContextHolder` |
| Testing only HTTP, not service | New endpoint can bypass policy | Test `service.read` directly |
| Testing only service, not HTTP | Wrong filter/matcher or status | Test `WebTestClient` for 401/403/200 |
| Using `@WithMockUser(roles="USER")` when policy needs `report:read` | `roles` creates `ROLE_USER`, not `report:read` | Use `authorities="report:read"` |
| Browser has CSRF token yet unauthorized action still runs | CSRF is not object authorization | Enforce dedicated permission rules per action |
| Parsing ID via arbitrary URL substring | Other routes/malformed paths can bypass | Use exact matcher variables and test edge cases |

## 15. Practice Completion Checklist

- [ ] Project uses only the WebFlux starter for reactive examples (not accidentally starting Spring MVC).
- [ ] Both `@EnableWebFluxSecurity` and `@EnableReactiveMethodSecurity` are enabled.
- [ ] `ReportPolicy` is the single logic source used at HTTP and method security.
- [ ] Policy checks both `report:read` and owner/cross-owner authority; deny by default.
- [ ] Never trust browser-sent owner/tenant/role.
- [ ] All protected services are Spring beans returning reactive publishers.
- [ ] No manual `block()`/`subscribe()` inside controllers/services.
- [ ] Context is read from `ReactiveSecurityContextHolder` inside the chain.
- [ ] `WebTestClient` tests anonymous, missing authority, right owner, wrong owner, reviewer, and invalid IDs.
- [ ] `StepVerifier` tests direct service calls, scheduler switches, and two subscriptions with distinct identities.
- [ ] Negative tests catch 403/AccessDeniedException, not only testing 200.
- [ ] When replacing the in-memory repository with a DB, remain non-blocking and scope tenant per object.
- [ ] Never treat CSRF/CORS/hidden buttons as replacing server authorization.
- [ ] When upgrading Spring Security, re-run the matrix on the real version.

## 16. Self-Practice Exercises

**Exercise 1 — Extend actions:** add `DELETE /api/reports/{id}` with authority `report:delete` and owner-only deletion. Write `canDelete(authentication, id)` shared across HTTP/service; test DELETE by guest, owner, another owner, reviewer, and user lacking authority. When using HTTP Basic/sessions in browsers, handle CSRF properly; never disable it just to make tests pass.

**Exercise 2 — Add tenant:** add `tenantId` to `Report`. `report:read:any` applies **only within the authenticated tenant**, not across all tenants. Write cross-tenant DENY tests even for `reviewer`. Never read `tenantId` from arbitrary request fields.

**Exercise 3 — Context isolation:** create 100 independent subscriptions with two users, combining `flatMap` and `publishOn`, verifying every `seenBy` matches its owner. Never store principal in a static variable; if increased concurrency mixes users, locate where subscriptions/callbacks detach from the chain.

**Exercise 4 — Reactive DB policy:** replace the in-memory `ReportRepository` with an R2DBC repository and a real reactive authorization manager. Explain why blocking DB calls should not run in `@PreAuthorize` and how to preserve “functional permission + right object” semantics with a single rule definition.

## 17. References

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — WebFlux Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Authentication Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Reactive Method Security Testing](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

**Conclusion:** “The same policy” does not mean duplicating two if-else blocks; it means a single policy invoked at multiple boundaries and verified with the same permission matrix. In WebFlux, the principal must travel via the **subscriber's Reactor Context**; to trust this mechanism, verify it with HTTP requests, StepVerifier, scheduler switches, and concurrent subscribers.