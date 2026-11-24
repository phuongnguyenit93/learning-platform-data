# Diagnosing Security Annotations Not Running and Self-Invocation Errors in Spring Security Reactive

This lesson belongs to the **Migration and debugging** group of the **Spring Security – reactive** module. Typical scenario: a method carries `@PreAuthorize("hasRole('ADMIN')")`, yet regular users still receive the data; calling it from another controller rejects them, while calling it from another method in the same class succeeds. Root causes usually lie in **enabling method security**, **Spring AOP proxy boundaries**, **reactive method signatures**, or **Reactor SecurityContext**—and occasionally the annotation runs, yet the authorization expression evaluates differently than expected.

The goal is pinpointing the exact failing layer, **reproducing self-invocation**, fixing it by routing calls through a Spring-managed bean/proxy, and writing regression tests. Examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, WebFlux, and Reactor**.

## 1. Distinguishing "Annotation Didn't Run" from "Wrong Decision"

| Symptom | What may have happened | What to inspect |
| --- | --- | --- |
| `USER` can invoke an `ADMIN`-only method | Advice did not run, self-invocation occurred, or expression/authorities are misconfigured | Is `@EnableReactiveMethodSecurity` enabled? Is the call via proxy? What are the real roles? |
| API returns 401 when unauthenticated | Web filter or method auth rejected and delegated to authentication entry point | Are HTTP Basic/Bearer configured? What is the current security context? |
| API returns 403 for an authenticated account | Either WebFlux URL authorization **or** method authorization rejected it | Isolate HTTP policy from service policy to identify the layer |
| `@PreAuthorize` method not invoked when test only checks newly created `Mono` | Reactive chain was never subscribed; signals were not observed | Use `StepVerifier` or `WebTestClient.exchange()` |
| Method works in normal requests, fails in background tasks | Missing `Authentication` in Reactor `Context`, or detached subscription | Inspect subscription site and security context |
| Proxy exists, yet `this.secured()` still skips checks | Spring AOP only intercepts calls passing **through the proxy** | Move the method to another bean, inject it, and call via that bean |

**Two separate defense layers:** `authorizeExchange(...)` inside `SecurityWebFilterChain` protects URLs, whereas `@PreAuthorize`/`@PostAuthorize` protects Spring bean method calls. `@EnableWebFluxSecurity` or the `spring-boot-starter-security` dependency **does not replace** `@EnableReactiveMethodSecurity` when enforcing method-level annotations. A `permitAll()` route can still be blocked by `@PreAuthorize` on a service; conversely, a route properly protected at the HTTP layer does not prove method annotations are enabled.

## 2. Proxy Mechanics and Self-Invocation

Spring Security reactive method authorization relies on **Spring AOP**. In default proxy mode, the interceptor can only run when callers invoke the method **on the bean's proxy**:

```text
Controller
   |
   | service.secured()      (Spring-injected service)
   v
Spring AOP proxy
   |
   | @PreAuthorize -> checks Authentication + permissions
   |-- DENY -> AccessDeniedException, never reaches target method
   '-- GRANT
          |
          v
      target.secured()
```

However, if a method inside the same object calls `this.secured()` or simply `secured()`:

```text
Controller -> proxy.outer() -> target.outer()
                                  |
                                  | this.secured()
                                  v
                              target.secured()
                    (bypasses proxy, skips @PreAuthorize)
```

Even though `target.secured()` has the annotation and Spring **created a proxy**, the internal call bypasses the advice. This remains true when the call sits inside `Mono.defer(() -> this.secured())`, `flatMap(x -> this.secured())`, or a lambda on the same instance: the receiver is still `this`, not the proxy. Switching to reactive operators **does not automatically fix** self-invocation.

**Not limited to security annotations:** `@Transactional`, `@Cacheable`, and other Spring AOP advice share similar self-invocation constraints, though exact behavior depends on configuration and proxy type.

## 3. Prerequisites for Reactive Method Security to Work

### 3.1. Enable the Right Annotation for Reactive

Use:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
```

Import:

```java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

Since Spring Security 6.0, `useAuthorizationManager` defaults to `true`; `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` is also valid in 6.3 though verbose. It activates interceptors such as `AuthorizationManagerBeforeReactiveMethodInterceptor` for `@PreAuthorize`.

Do not substitute standard `@EnableMethodSecurity` in a WebFlux app when reactive method interception is required. `@EnableWebFluxSecurity` configures web filters and does not turn on method annotations. For `@Secured` or `@RolesAllowed`, check their specific enablement flags; this lesson uses `@PreAuthorize` to isolate the bug.

### 3.2. Methods Must Belong to a Spring Bean Invoked Through Its Proxy

- The class must be Spring-managed: `@Service`, `@Component`, or an `@Bean` in the right application context. Direct instantiation via `new SensitiveService()` yields no Spring proxy.
- Spring uses JDK interface proxies when interfaces apply, or subclass proxies (CGLIB) where appropriate. With subclass proxies, `final` classes/methods cannot be advised by overriding, and `private` methods are not intercepted through subclass proxies.
- In Kotlin, classes and methods are `final` by default; configure `kotlin-spring`/`all-open` or use interface proxies rather than expecting subclass proxies on `final` methods.
- Place annotations on public service methods for readability and testability; when using interfaces, generics, bridge methods, inheritance, or implementation-level annotations, verify the proxy sees the intended annotation and target method.
- When interface-based proxies are used, inject by the interface and invoke interface methods; do not cast the proxy to a concrete class it does not implement.

### 3.3. Reactor Publishers, Subscription, and SecurityContext

In Java reactive method security, standard practice uses methods returning `Mono<T>`/`Flux<T>` (or `Publisher<T>`) so authorization integrates with Reactor `Context`. Do not copy a synchronous Servlet method returning `String` into a reactive codebase expecting identical behavior.

`ReactiveSecurityContextHolder` stores/reads authentication from **Reactor Context**. For WebFlux requests passing through Spring Security, context is populated by HTTP authentication. For unit tests or non-HTTP jobs, supply context explicitly via `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`. Never treat Servlet ThreadLocal `SecurityContextHolder.getContext()` as proof inside a reactive pipeline.

An unsubscribed Publisher will neither emit results nor signal authorization errors like a real request. Never "test" by writing `Mono<String> result = service.secured()` without subscribing and claiming it was allowed/denied. Avoid `.block()` on WebFlux event loops; use `StepVerifier` in unit tests or `WebTestClient` for HTTP tests.

## 4. Complete Example: Reproducing the Vulnerability, Then Fixing It Properly

This example intentionally exposes two endpoints **strictly for a local demo**:

- `GET /lab/self` calls a protected method via `this` inside the same bean: **bypasses** method authorization.
- `GET /lab/proxy` calls a protected method on another Spring-injected bean: **respects** the proxy boundary and requires `ROLE_ADMIN`.

The HTTP layer permits both paths (`permitAll()`) **to observe method security in isolation**. This configuration intentionally demonstrates a vulnerability—never deploy `/lab/self` to production. Demo accounts use fixed passwords and are registered only under the `demo` profile.

### 4.1. Create the Maven Project

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-method-proxy-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

### 4.2. Application Bootstrap

Create `src/main/java/com/example/methodlab/MethodLabApplication.java`:

```java
package com.example.methodlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodLabApplication.class, args);
    }
}
```

### 4.3. Web Security and Reactive Method Security

Create `src/main/java/com/example/methodlab/SecurityConfiguration.java`:

```java
package com.example.methodlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        // Solely to observe whether method security runs.
                        .pathMatchers(HttpMethod.GET, "/lab/self", "/lab/proxy")
                            .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // GET-only demo: do not disable CSRF globally.
                .build();
    }

    @Bean
    @Profile("demo")
    MapReactiveUserDetailsService demoUsers() {
        return new MapReactiveUserDetailsService(
                User.withUsername("viewer")
                        .password("{noop}viewer123")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin123")
                        .roles("ADMIN")
                        .build());
    }
}
```

`{noop}` simply denotes an explicit lab PasswordEncoder and **does not protect passwords**; never use demo accounts or plaintext storage in production. Real systems must use secure password hashes, an identity provider/authorization server, TLS, and proper secret management. Per authentication config, valid Basic credentials populate `Authentication` with `ROLE_USER` or `ROLE_ADMIN` in Reactor `SecurityContext`.

### 4.4. Self-Calling Bean: Annotation Is Bypassed

Create `src/main/java/com/example/methodlab/SelfCallingService.java`:

```java
package com.example.methodlab;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SelfCallingService {

    public Mono<String> readInternally() {
        // Wrong: target invokes a same-class method directly, bypassing the AOP proxy.
        return this.secret();
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> secret() {
        return Mono.fromSupplier(() -> "secret-report");
    }
}
```

Notice carefully: `SelfCallingService` is a Spring bean, `secret()` is public, and the annotation is valid. If another bean calls `selfCallingService.secret()` through the proxy, permissions are enforced. Yet `readInternally() -> this.secret()` executes **inside the target**, skipping `secret()`'s interceptor. `Mono.fromSupplier` only defers value creation until subscription; it **does not** alter proxy routing.

### 4.5. Fixing by Splitting the Protected Bean from the Coordinator Bean

Create `src/main/java/com/example/methodlab/ProtectedReportService.java`:

```java
package com.example.methodlab;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProtectedReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readReport() {
        return Mono.fromSupplier(() -> "secret-report");
    }
}
```

Create `src/main/java/com/example/methodlab/ReportFacade.java`:

```java
package com.example.methodlab;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportFacade {

    private final ProtectedReportService protectedReport;

    public ReportFacade(ProtectedReportService protectedReport) {
        this.protectedReport = protectedReport;
    }

    public Mono<String> readThroughProxy() {
        // Right: delegates to another Spring bean through the DI-injected proxy reference.
        return protectedReport.readReport();
    }
}
```

`ReportFacade` coordinates while `ProtectedReportService` owns the permission policy. When Spring injects `protectedReport`, the injected instance is the proxy, so `@PreAuthorize` executes. Splitting beans also makes authorization boundaries visible in code reviews and easy to test independently.

### 4.6. Controller Sharing the Same HTTP Policy for Comparison

Create `src/main/java/com/example/methodlab/LabController.java`:

```java
package com.example.methodlab;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@Profile("demo")
@RestController
class LabController {

    private final SelfCallingService self;
    private final ReportFacade facade;

    LabController(SelfCallingService self, ReportFacade facade) {
        this.self = self;
        this.facade = facade;
    }

    @GetMapping("/lab/self")
    Mono<String> unsafeSelfCall() {
        return self.readInternally();
    }

    @GetMapping("/lab/proxy")
    Mono<String> secureCrossBeanCall() {
        return facade.readThroughProxy();
    }
}
```

Here the controller is another bean, yet `self.readInternally()` **has no** `@PreAuthorize`; once inside that method, `this.secret()` bypasses security. `facade.readThroughProxy()` goes through `ProtectedReportService`'s proxy, so the ADMIN policy runs.

**Key diagram:**

```text
GET /lab/self
  Controller -> SelfCallingService proxy -> target.readInternally()
                                      -> this.secret() [BYPASS]
  USER/anonymous can see "secret-report" (demonstrated vulnerability)

GET /lab/proxy
  Controller -> ReportFacade -> ProtectedReportService proxy
                               -> @PreAuthorize ADMIN
  anonymous -> HTTP 401
  USER      -> HTTP 403
  ADMIN     -> HTTP 200, "secret-report"
```

Never keep `/lab/self` in a real system: it exists solely to **demonstrate** the bug. The proper business fix is moving sensitive logic to a protected bean/path and removing every discovered bypass—not sprinkling annotations until tests turn green by accident.

## 5. Running and Observing Signals

Run with JDK 17+ and Maven:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=demo
```

Once the server listens on `localhost:8080`, try:

```bash
curl -i http://localhost:8080/lab/self
curl -i -u viewer:viewer123 http://localhost:8080/lab/self

curl -i http://localhost:8080/lab/proxy
curl -i -u viewer:viewer123 http://localhost:8080/lab/proxy
curl -i -u admin:admin123 http://localhost:8080/lab/proxy
```

**Expected** outcomes (exact statuses depend on custom exception handlers/entry points; with the sample config they are 200/401/403):

| Caller | `GET /lab/self` (buggy) | `GET /lab/proxy` (fixed) |
| --- | --- | --- |
| Anonymous | **200**, returns `secret-report` without login | **401**, authentication required |
| `viewer` with `ROLE_USER` | **200**, violates protection goal | **403**, authenticated yet lacks ADMIN |
| `admin` with `ROLE_ADMIN` | 200 | 200, returns `secret-report` |

Seeing 403 at a controller alone **is not proof** that method annotations ran: if the HTTP policy already required ADMIN at the URL layer, the controller may have been blocked **before the service was ever called**. In this demo, both URLs intentionally use `permitAll` to isolate the two enforcement layers.

Sending a Basic header with a wrong password rejects the request immediately in the authentication filter (401) before reaching the controller. Do not use wrong-password requests to evaluate self-invocation. In real systems, avoid passing passwords on the command line; `curl -u` with sample passwords is for local labs only, and remote calls should use TLS.

## 6. Integration Test Proving the Proxy Boundary

Create `src/test/java/com/example/methodlab/MethodSecurityIntegrationTest.java`:

```java
package com.example.methodlab;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("demo")
class MethodSecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    SelfCallingService self;

    @Autowired
    ProtectedReportService report;

    @Test
    void springHasProxiesButSelfInvocationStillBypassesAdvice() {
        assertThat(AopUtils.isAopProxy(self)).isTrue();
        assertThat(AopUtils.isAopProxy(report)).isTrue();

        client.get().uri("/lab/self")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("secret-report");
    }

    @Test
    void anonymousRequestIsStoppedAtProtectedMethod() {
        client.get().uri("/lab/proxy")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ordinaryUserIsDeniedByMethodSecurity() {
        client.get().uri("/lab/proxy")
                .headers(h -> h.setBasicAuth("viewer", "viewer123"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallTheProtectedMethod() {
        client.get().uri("/lab/proxy")
                .headers(h -> h.setBasicAuth("admin", "admin123"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("secret-report");
    }
}
```

Run:

```bash
mvn test
```

The tests confirm two distinct facts: **a proxy exists** and **whether calls pass through the proxy**. `AopUtils.isAopProxy(self) == true` does not mean inner calls inside that bean are intercepted. That is why the anonymous request to `/lab/self` returning 200 demonstrates the bypass, while `/lab/proxy` enforces 401/403/200 by identity. Tests that merely assert a bean has an annotation or proxy will miss self-invocation bugs.

After fixing a real app, acceptance criteria should assert **no bypass paths remain**; never turn a vulnerability-reproduction test into a production pass criterion.

## 7. Testing Methods Directly with Reactor Context

You can decouple from HTTP to prove the bug resides at the method layer. When testing directly, supply `Authentication` in Reactor context yourself. Example simple test assuming `ProtectedReportService` and `SelfCallingService` beans are `@Autowired` in `@SpringBootTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

@SpringBootTest
class MethodAuthorizationUnitStyleTest {

    @Autowired
    ProtectedReportService report;

    @Autowired
    SelfCallingService self;

    @Test
    void userGetsDeniedThroughProxy() {
        Authentication viewer = new UsernamePasswordAuthenticationToken(
                "viewer", "n/a", AuthorityUtils.createAuthorityList("ROLE_USER"));

        StepVerifier.create(report.readReport()
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(viewer)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void sameUserBypassesProtectionWithSelfCall() {
        Authentication viewer = new UsernamePasswordAuthenticationToken(
                "viewer", "n/a", AuthorityUtils.createAuthorityList("ROLE_USER"));

        StepVerifier.create(self.readInternally()
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(viewer)))
                .expectNext("secret-report")
                .verifyComplete();
    }
}
```

This can be saved as `src/test/java/com/example/methodlab/MethodAuthorizationUnitStyleTest.java` after adding `package com.example.methodlab;` at the top; imports and class body are complete, with `package` omitted only to focus on Reactor context testing. If compiling as a standalone file, add the matching `package` declaration.

Tests must **subscribe** via `StepVerifier`; calling `report.readReport()` alone does not prove authorization ran. When using `Mono.deferContextual` or standard operators, Reactor Context flows along the subscription. Normal `publishOn`/`subscribeOn` calls **do not by default** lose Reactor Context; issues usually arise from manual `.subscribe()` detaching the chain, calling non-Reactor code, or failing to attach context to new publishers.

When testing method security without an HTTP request, do not blindly apply `@WithMockUser` everywhere and reason in ThreadLocal terms. `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` transparently shows which authentication the pipeline sees. In HTTP tests using `WebTestClient`/Spring Security test support, the context is populated by the filter chain.

## 8. Ordered Diagnostic Procedure

When an annotation appears not to execute, investigate in this order to avoid editing the wrong layer:

### Step 1 — Confirm Requests Actually Reach the Method

- Record controller route, HTTP status, matched authorization rule, and a safe entry log in the method (without secrets).
- If blocked before the controller, the issue lies in `authorizeExchange`, authentication filters, exception handlers, or CSRF—not service `@PreAuthorize`.
- If requests bypass the gateway or enter via another entry point, review all security chains and internal/batch paths.
- Isolate a service integration test calling the protected bean directly and compare with HTTP tests.

### Step 2 — Check Annotations and Activation Configuration

- Is `@EnableReactiveMethodSecurity` present in the right Spring application context?
- Is the annotated class genuinely a Spring bean created by component scan/`@Bean`, rather than instantiated with `new` somewhere?
- Does the method return `Mono`/`Flux` per Java reactive contracts? Is the annotated method public, non-final, and not excluded by proxy rules?
- Is the matching annotation type (`@PreAuthorize`, `@Secured`, `@RolesAllowed`) enabled with the proper options?
- When using a Spring test slice like `@WebFluxTest`, are the real configuration/service/advisor included in the test context? Overly narrow slices can diverge from production.

### Step 3 — Verify the Proxy at the Caller

Inside a test or internal diagnostic tool:

```java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean(ProtectedReportService.class);
boolean proxied = AopUtils.isAopProxy(bean);
Class<?> targetType = AopUtils.getTargetClass(bean);
```

This is an **illustrative snippet** inside a test or bean that already has `applicationContext`, not a standalone Java program. `proxied == false` is a strong clue when the class expects method security; `proxied == true` only proves the bean has a proxy, **not** that the specific advisor ran for your call site. Check whether the caller holds the Spring-injected bean or a newly constructed instance; if the caller is a same-class method, look for `this.secured(...)` or unqualified calls.

When multiple advice types coexist, inspect the advisor chain using AOP diagnostics. Still, never treat printing proxy names as a standalone "security check"—**role-based behavioral tests** confirm the policy.

### Step 4 — Observe Authentication in Reactor Context

- In WebFlux, know which mechanism (Basic, Bearer token, OAuth2 Login, session) supplies which principal and authorities.
- Is there a manual `.subscribe()` inside a service? An independent chain may execute outside the expected security context.
- Are publishers/`CompletableFuture`s left uncomposed with the request's Reactor subscription, or is Servlet ThreadLocal `SecurityContextHolder` being used?
- For non-HTTP invocations (messaging, scheduled jobs, CLI, tests), design a dedicated technical identity model rather than defaulting to "admin".
- A request switching schedulers does not necessarily lose context: verify the real pipeline via `ReactiveSecurityContextHolder.getContext()` instead of relying on ThreadLocal/MDC.

### Step 5 — Check Authorities, Expressions, and Error Handling

- `hasRole('ADMIN')` looks for `ROLE_ADMIN`. `hasAuthority('ADMIN')` looks for exact `ADMIN`. Holding only `SCOPE_admin` does not satisfy `ROLE_ADMIN`.
- When referencing parameter names in SpEL (e.g., `#ownerId`), verify parameter-name metadata (`-parameters`), `@P`, or the parameter name discoverer in use; invalid expressions may throw errors instead of authorizing cleanly.
- If `@PreAuthorize` appears on interfaces, classes, and overrides, verify which annotation Spring resolves and avoid conflicting annotations.
- An `AccessDeniedException` can be swallowed by another `onErrorResume` and turned into HTTP 200: that is **dangerous error handling**, not proof that advice failed to run.
- `@PostAuthorize` evaluates **after** the method executes and does not prevent side effects inside the method. For writes/deletes, use `@PreAuthorize` or check permissions prior to side effects by design.
- If migrating legacy reactive method security configs from older Spring Security, check migration to `AuthorizationManager` and annotation-enabling defaults.

### Step 6 — Add Temporary Logs While Protecting Secrets

Enable targeted logs in a controlled environment:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.authorization: TRACE
    org.springframework.aop: DEBUG
```

TRACE logs can be voluminous and contain authorization evaluation details; use only in authorized environments with short lifetimes and redact sensitive fields. Never log passwords, access tokens, `Authorization` headers, raw JWTs, or user data just to "prove" context. Focus on method names, sanitized principal types, required authority sets, evaluated rules, outcomes, and correlation IDs.

## 9. Which Fix Is Appropriate?

**Prefer splitting beans (such as `ReportFacade -> ProtectedReportService`):** Readable, testable, and independent of proxy-exposure flags. Protection becomes an explicit service boundary so other callers must pass through the protected bean too. Splitting code does not automatically secure every path: audit all other callers that might hit implementations or data repositories directly without passing through policy.

**Self-injection / injecting the bean's own proxy:** You can inject a Spring-managed reference (often lazily/via provider) and call the protected method through that proxy reference. However, this easily creates circular dependencies or confusing wiring and needs clear tests. Never replace it with `this.secured()`.

**`AopContext.currentProxy()`:** Supported by Spring Framework when expose-proxy is enabled, yet couples business code directly to AOP infrastructure and complicates testing. Avoid choosing it as the default fix for this bug.

**AspectJ weaving:** Unlike AOP proxies, compile-time/load-time weaving can intercept self-invocation because advice is woven into bytecode. This is an architectural/build/runtime change with distinct testing and compatibility requirements—not a single property flip where every reactive security advisor automatically works identically. For learning code and most WebFlux services, splitting beans is the safest, simplest solution.

**Never "fix" by:** deleting `@PreAuthorize`, wrapping `AccessDeniedException` with `onErrorResume(e -> Mono.just(secret))`, adding `permitAll` at the HTTP layer, assigning default `ROLE_ADMIN`, or fabricating a full-privilege `SecurityContext` for unauthenticated requests. Those remove security barriers and mask the root cause.

## 10. Common Mistakes When Migrating from Servlet to WebFlux

| Misconception | Reality and fix |
| --- | --- |
| Enabling `@EnableWebFluxSecurity` means `@PreAuthorize` will run | Enable `@EnableReactiveMethodSecurity` separately |
| Using `@EnableMethodSecurity` from an MVC example is equivalent | Use the reactive config supporting Reactor `SecurityContext` and reactive interceptors |
| Because the class has `@Service`, `this.secured()` still uses the proxy | Self-invocation calls the target directly, bypassing advice |
| Checking `AopUtils.isAopProxy(bean)` is enough | A proxy may exist while inner calls still skip it |
| Changing `Mono.just(...)` to `Mono.defer(...)` fixes self-invocation | Reactive laziness does not change the `this` receiver |
| An unsubscribed `Mono` throwing no exception means access was granted | Subscribe via `StepVerifier` or `WebTestClient` |
| `SecurityContextHolder.getContext()` always works in WebFlux | Reactive `SecurityContext` travels via Reactor `Context` |
| `publishOn` always loses security context | Reactor Context propagates along subscriptions; look for where the pipeline detached |
| `private`/`final` methods always receive AOP advice | Subclass proxies cannot intercept those methods; verify proxy type |
| `hasRole('ADMIN')` equals `hasAuthority('ADMIN')` | `hasRole` normally expects the `ROLE_ADMIN` authority |
| HTTP 403 proves method annotations ran | HTTP authorization may have blocked the request before reaching the service |
| `@PostAuthorize` prevents side effects inside a method | The action may already have run; use pre-authorization for sensitive actions |
| Circularly self-injecting a bean is the best fix | Moving the secured method to a separate bean is clearer and easier to test |

## 11. QA Checklist for a Method-Security Bug

A fix should be accepted only when:

1. The protected method genuinely belongs to a Spring-managed bean in the request-serving application context, with reactive method/interceptors matching your version and proxy type.
2. Every caller of the sensitive operation **must** enter through the authorized entry point; no `this.method()`, `new` instances, or shortcuts bypass policy.
3. Authorization tests cover **anonymous**, under-privileged, and authorized accounts, verifying results at the **service method** and at least one HTTP path.
4. Tests subscribe to `Mono`/`Flux`; outside HTTP, `ReactiveSecurityContextHolder` is supplied explicitly without assuming ThreadLocal holds identity.
5. 401/403 responses follow policy and are not swallowed into "success" by custom handlers; HTTP routing rules do not inadvertently mask method-security gaps.
6. `final`/`private` methods are not relied upon as the sole place for annotations when proxies cannot advise them, and missing matchers/registration do not silently leave the app unprotected.
7. During service refactoring, all sibling call paths, side effects, and check orderings are reviewed; broader default privileges are never added just to make tests pass.

## 12. Summary of Mechanics for Self-Debugging

In WebFlux, `@PreAuthorize` takes effect only when reactive method security is enabled, the method signature fits, and invocation passes through the Spring AOP proxy inside a Reactor subscription carrying a valid `SecurityContext`. **Self-invocation** is the most deceptive trap: the bean is proxied and the annotation is valid, yet `this.method()` inside the bean bypasses the interceptor. Fix by **extracting the protected method into another bean and injecting it**, testing anonymous/USER/ADMIN at both service and HTTP layers, and confirming every caller uses the protected path.

### Official Documentation

- Spring Security 6.3 – Reactive Method Security (`EnableReactiveMethodSecurity`, `AuthorizationManager`, Reactor Context): https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security – Reactive Method Security (latest docs; cross-check your version when applying): https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – Reactive Testing Authentication: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Framework – AOP Proxying Mechanisms and Self-Invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Reactor – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Spring Security – Reactive Web Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html