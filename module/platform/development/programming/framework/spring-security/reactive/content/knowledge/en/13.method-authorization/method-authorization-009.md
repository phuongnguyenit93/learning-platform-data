# Spring AOP, Same-Object Self-Invocation, and Why Annotations Have No Effect

## 1. Context and objectives

In reactive Spring Security, you can attach `@PreAuthorize("hasRole('ADMIN')")` to a `Mono<String>` method, run the application, and observe authorization checks working when the controller invokes that method. However, as soon as **another method on the same object** calls it via `this.adminOnly()`, the authorization check may **not happen**. This is the **self-invocation** pitfall of **proxy-based Spring AOP**, which can create an authorization bypass even when the annotation and SpEL expression are completely accurate.

This lesson belongs to **Method Authorization in Spring Security reactive/WebFlux**. You will:

1. Understand Spring AOP proxies and their relationship with `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and `@PostAuthorize`.
2. Explain why calls **through the Spring proxy** trigger security advice, whereas **internal same-bean calls via `this`** do not traverse the proxy.
3. Distinguish self-invocation bugs from disabled method security, non-Spring-managed beans, `private`/`final` methods, wrong proxy types, or missing Reactor security context.
4. Run a Java 17+ Spring Boot WebFlux example featuring all three paths: **direct proxied call**, **bypassed internal call**, and **protected call through another bean**.
5. Test authorized and unauthorized users with `WebTestClient`, interpreting **200/401/403** outcomes accurately.
6. Prefer fixing via **bean extraction/call-flow redesign**, while knowing the limits of self-injection, `AopContext.currentProxy()`, and AspectJ weaving.
7. Design regression tests so future refactors never silently skip authorization policies.

**Example warning:** This lesson intentionally creates a bypassable endpoint **solely to reproduce the bug in a local learning environment**. Never ship this endpoint to a real system; after observing it, remove it or replace it with a call through a protected bean.

## 2. What does WebFlux method security rely on?

For **reactive** flows, Spring Security combines Spring AOP with **Reactor Context**, rather than relying solely on Servlet `ThreadLocal`.

Components:

| Component | Purpose |
| --- | --- |
| `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` | Enables reactive method-authorization advisors/interceptors using the `AuthorizationManager` model |
| `@PreAuthorize("...")` | Evaluates authorization rules **before** allowing the protected method to run |
| `@PostAuthorize("...")` | Evaluates rules when a result exists to decide whether that result may be returned |
| Spring AOP proxy | Wrapper around external calls enabling authorization advice to run |
| `ReactiveSecurityContextHolder` | Reads `SecurityContext` from Reactor Context inside the pipeline |
| `SecurityWebFilterChain` | Protects HTTP requests at the WebFilter layer, **distinct** from method authorization |
| `Mono<T>` / `Flux<T>` | Returned publishers allowing reactive method security to integrate with subscription/Context |

Enabling method security example:

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {
    // ... declare required @Bean definitions ...
}
```

This is an **excerpt**; the full class is in section 8. In Spring Security 6.x, `useAuthorizationManager = true` indicates the `AuthorizationManager` infrastructure is used; this is the recommended configuration for this lesson.

Example on a Spring bean:

```java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.just("restricted-report");
    }
}
```

If an object **obtained from the Spring container** calls `reportService.adminOnly()` through its proxy, a logged-in user holding only `ROLE_USER` will be denied by method security. A user holding `ROLE_ADMIN` can be granted access.

However, **placing an annotation in source code does not automatically inject checks into every Java call**. To see why, we must understand proxies.

## 3. Spring AOP proxies and where advice runs

Standard Spring AOP uses **runtime proxies**. The proxy sits between an **external caller** and the **target object**; only when a caller goes through the proxy do matching interceptors/advice get a chance to execute.

```text
Controller / Another Bean
       |
       v
Spring proxy of ReportService
       |
       +--> Method-security advisor (@PreAuthorize)
       |         |
       |     check permissions
       |      /       \
       |   deny      allow
       |    |          |
       |   403         v
       |           target.adminOnly()
       |                  |
       |                  v
       |              Mono<String>
       |
       +--> Caller receives reactive signal
```

This is a conceptual diagram: HTTP 403 is produced by WebFlux filters/error handlers translating the `AccessDeniedException` signal into an appropriate response; `@PreAuthorize` itself does not return an HTTP status directly.

### JDK dynamic proxies and class-based proxies

| Proxy type | How it is created | Design implications |
| --- | --- | --- |
| JDK dynamic proxy | Proxies interfaces implemented by the bean | Callers generally inject by interface; methods not on the interface may not be exposed through the proxy |
| Class-based (CGLIB) proxy | Generates a subclass of the target class | Cannot override `final` methods; `private` methods cannot be advised this way |

Spring Boot may configure class-based proxies by default or force proxy types in certain contexts; do not infer whether a proxy is JDK or CGLIB merely from whether a class implements an interface. **Both proxy types share the same rule: calls must pass through the proxy.**

Do not inspect `getClass()` on a bean to assume annotations are enforced. Proper tests must verify **denied/allowed behavior** of the method rather than just checking proxy class names.

### Does `@PreAuthorize` belong to the service or HTTP layer?

You can combine both layers:

```java
// HTTP rule: every API URL requires a logged-in user.
http.authorizeExchange(exchanges ->
        exchanges.anyExchange().authenticated());

// Business method rule: only ADMIN may fetch confidential reports.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOnly() { /* ... */ }
```

These are two **illustrative snippets** in different scopes, not complete Java methods. They guard two boundaries:

- HTTP `authenticated()`: the user must log in to call the endpoint.
- Method `hasRole('ADMIN')`: reading confidential reports is restricted to ADMIN.

A regular logged-in user can pass the URL layer yet be rejected at the method. If the method is bypassed via self-invocation, the URL layer **does not replace** the ADMIN rule. Good defense in depth requires both layers to be sound.

## 4. Core bug: `this` is not a proxy

Examine this class:

```java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.just("restricted-report");
    }

    public Mono<String> unsafeInternal() {
        return this.adminOnly();
    }
}
```

A controller calling `reportService.adminOnly()` goes through the Spring proxy; security advice sees `adminOnly` and checks ADMIN.

Another controller calls `reportService.unsafeInternal()` through the proxy. Once the proxy delegates into the target, `unsafeInternal()` calls `this.adminOnly()` directly on the **target**. That internal call **never goes back out through the proxy**, so `adminOnly`'s interceptor **never runs**.

```text
SAFE PATH
Controller -> [ReportService proxy] -> @PreAuthorize(adminOnly)
                                        |
                                 role ADMIN?
                                /          \
                              no           yes
                              |             |
                            deny       target.adminOnly

BYPASSED PATH (self invocation)
Controller -> [ReportService proxy] -> target.unsafeInternal()
                                          |
                                          v
                                   this.adminOnly()
                                          |
                              DOES NOT go back through proxy
                                          |
                                          v
                                 "restricted-report"
```

**Conclusion:** The annotation is still on the method, the bean may still be an AOP proxy, and the class may still be Spring-managed. The bug occurs because of **the Java call path**. Both `this.adminOnly()` and bare `adminOnly()` (omitting `this`) are self-invocation calls.

A variant with the exact same issue:

```java
public Mono<String> unsafeInternal() {
    return adminOnly(); // implicit this.adminOnly()
}
```

### Why is this a real security vulnerability?

Suppose `/api/report/unsafe` requires only `authenticated()` at the URL layer. User `reader` holds USER role, without ADMIN:

1. HTTP Basic authenticates `reader` successfully.
2. URL-level `authenticated()` lets the request through.
3. The controller calls `ReportService.unsafeInternal()`.
4. `unsafeInternal` calls `this.adminOnly()` directly.
5. The annotation on `adminOnly` **is not enforced** for that call.
6. A non-ADMIN user still receives the protected content.

If the route is publicly open, the impact is even worse. Thus **a method security bypass does not necessarily throw 403/500**; it can silently return `200 OK` with confidential data, making logs look like normal requests.

## 5. Reactor `Mono` does not fix self-invocation automatically

Because this lesson covers **reactive** Spring Security, add one more crucial distinction:

- `Mono`/`Flux` are publishers; they are not AOP proxies.
- Reactor Context carries the verified identity across a subscription; it does not replace method interceptors.
- `Mono.defer(...)` and `Mono.fromSupplier(...)` defer evaluation, yet **do not route `this.method()` through the proxy**.
- `subscribeOn(...)` switches schedulers; it cannot restore bypassed authorization advice.
- `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` supplies `SecurityContext` to the pipeline, yet if the method is not intercepted by method security, **having context present does not evaluate `@PreAuthorize`**.

Example:

```java
public Mono<String> unsafeInternal() {
    return Mono.defer(this::adminOnly);
}
```

This is an **illustrative snippet inside the same `ReportService` class**, and it still fails to fix the bug: when the subscription runs the supplier, it still invokes `this.adminOnly()` on the target.

Conversely, calling through **another Spring bean** injected via DI:

```java
@Service
public class SafeWorkflow {
    private final ReportService reportService;

    public SafeWorkflow(ReportService reportService) {
        this.reportService = reportService;
    }

    public Mono<String> run() {
        return reportService.adminOnly();
    }
}
```

`reportService` here is the Spring-provided bean (with its method-security proxy). `SafeWorkflow.run()` calls **another bean**, so `ReportService.adminOnly()` is advised.

**Note on side effects:** When writing reactive methods, keep I/O and real side effects inside publishers properly rather than eagerly evaluating sensitive data before policy enforcement. Yet lazy execution **does not replace** designing proper authorization boundaries.

## 6. Distinguishing causes when annotations "have no effect"

| Symptom / structure | Possible cause | Verification and fix |
| --- | --- | --- |
| `this.adminOnly()` is not blocked | Self-invocation bypasses AOP proxy | Extract call into another Spring bean |
| Calling `new ReportService()` | Object is not Spring-managed | Inject Spring bean instead of `new` |
| `@PreAuthorize` present yet method security not enabled | Reactive advisors not registered | Add `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` |
| Using Servlet `@EnableMethodSecurity` in WebFlux | Wrong security stack config | Use reactive method security and `ServerHttpSecurity` |
| Annotation placed on `private` method | Private methods cannot be proxy-advised | Move rule to a public proxied entrypoint or service |
| Annotation on `final` method with class-based proxy | Subclass proxy cannot override | Remove `final` or design via suitable interface |
| `final` class with expected CGLIB | Subclass proxy cannot be generated | Do not make class `final` for class-based proxies; check actual proxy mode |
| Code invokes target object instead of Spring bean | Bypasses proxy | Inject bean via constructor |
| Interface proxy while caller needs non-interface method | Method absent from proxy contract | Inject via interface declaring the method or use supported class-based proxy |
| Method does not return a suitable reactive publisher | Wrong type for reactive method authorization | Use `Mono`/`Flux` per API/version; do not assume sync methods are advised identically |
| Test invokes method inside class via `this` | Test accidentally bypasses despite annotation | Test calling bean obtained from `ApplicationContext` |
| `onErrorResume(ex -> Mono.just(secret))` swallows denial | Code replaces error with secret data | Never convert `AccessDeniedException` into success |
| `403` from missing role | Method security **did** run and deny | Check authorities/SpEL; do not treat as broken annotation |
| `401` from missing credentials | Rejected at authentication filter | Check HTTP Basic/session and SecurityContext |
| SpEL uses wrong parameter name | Expression cannot resolve argument | Check parameter metadata/annotations and error messages |
| Overly broad HTTP authorization rule | URL-level policy bug, not necessarily method security | Test both controller and service |
| `@PostAuthorize` with side effects already executed | Post-result check is too late for irreversible actions | Use `@PreAuthorize` for writes; design safe business flows |

**Verification tip:** An unexpected 200 has many possible causes. Check whether the annotated method is actually called **through a bean proxy** before tweaking SpEL or flooding logs with DEBUG.

### `private`, `final`, and proxyability

With class-based proxies, the proxy is a subclass, so it cannot intercept `final` or `private` methods; a `final` class cannot be subclassed. With JDK dynamic proxies, the proxy exposes interface methods, yet self-invocation **still bypasses**. Spring Security method annotations may support various placements depending on mode/version, yet to stay predictable, choose **public, non-final methods on Spring beans**, called via Spring-injected references.

In Kotlin, classes/methods are `final` by default and may require `kotlin-spring`/`all-open` plugins or interface-based design; never copy a Java example and assume proxies work in Kotlin without testing.

## 7. Fixes: order of preference

### Option A — Split responsibilities across two beans (recommended)

Replace:

```java
// A class calling its own sensitive method:
public Mono<String> execute() {
    return this.adminOnly();
}
```

With the design:

```text
Controller
   |
   v
SafeWorkflow (bean)
   |
   v
ReportService (bean proxy)
   |
   v
@PreAuthorize("hasRole('ADMIN')")
   |
   v
ReportService.adminOnly()
```

This establishes a clear security boundary, is easy to test, and avoids needing to care whether the proxy is JDK or CGLIB to invoke the method properly.

### Option B — Protect the externally called entry point directly

If logic belongs in the same bean with a clear public API, place `@PreAuthorize` on the **public method that callers actually invoke through the proxy**, rather than placing the annotation only on a helper called via `this`.

Example:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> exportReport() {
    return internalComputeReport();
}

private Mono<String> internalComputeReport() {
    return Mono.just("restricted-report");
}
```

This is a fragment in a Spring bean with method security enabled. When **every path** into `internalComputeReport()` passes through `exportReport()`, the policy is enforced at the public boundary. However, if the class has **multiple public entry points** or another method calls `this.exportReport()`, you must still audit self-invocation and boundaries. Do not assume annotating one public method covers every path to a helper.

### Option C — Self-injection (possible, yet requires caution)

You can inject a reference to the bean's own proxy and call through that reference instead of `this`. However, this introduces circular dependencies, complicates lifecycle management, and can mask poor architecture. If strictly necessary, use `ObjectProvider`/lazy injection appropriately, test against the real container, and avoid manually creating proxies or holding raw target references.

**Prefer extracting a separate bean**, as it is easier to review and less coupled to Spring AOP internals.

### Option D — `AopContext.currentProxy()` (discouraged)

Spring Framework offers `AopContext.currentProxy()` in some proxy configurations with `exposeProxy` enabled. However, it couples code to AOP infrastructure, execution timing, and whether the proxy is actually exposed. In reactive pipelines that can switch threads and subscription timing, it is even less suitable as a default fix.

Do not add `AopContext.currentProxy()` to business code as a quick patch when extracting a bean solves the problem cleanly.

### Option E — AspectJ weaving (distinct from default AOP proxies)

AspectJ compile-time or load-time weaving can advise self-invocation because it instruments bytecode differently. However, `@EnableReactiveMethodSecurity` relies on Spring AOP proxies in this lesson's configuration; merely "adding an AspectJ dependency" **does not automatically** switch all reactive method security to a weaver supporting every annotation. Weaving requires dedicated design, build/runtime tooling, and testing. For most WebFlux apps, this is **unnecessary** just to fix self-invocation.

## 8. Java 17+ / Spring Boot 3.3.5 project to reproduce and fix the bug

The example uses **Java 17+**, **Spring Boot 3.3.5**, Boot-managed Spring Security 6.x, and Gradle 8.5 or a compatible wrapper. All demo requests are GETs to keep the focus on method authorization without mixing in POST CSRF handling.

What to observe:

- `GET /api/report/direct`: calls `adminOnly` **directly through the bean proxy**.
- `GET /api/report/unsafe`: calls `unsafeInternal` which internally calls `this.adminOnly()`, **bypassing** the role check.
- `GET /api/report/safe`: calls `SafeWorkflow.run()`, which delegates to the **`ReportService` bean**, enforcing the role check.
- `GET /health`: public; all API routes first require login.

Project structure:

```text
reactive-method-aop-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/methodaop/
    │   ├── MethodAopApplication.java
    │   ├── SecurityConfig.java
    │   ├── ReportService.java
    │   ├── SafeWorkflow.java
    │   └── ReportController.java
    └── test/java/dev/example/methodaop/
        └── MethodAopSecurityTests.java
```

### 8.1. Gradle files

`settings.gradle`:

```groovy
rootProject.name = 'reactive-method-aop-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` provides WebFlux/Reactor. Do not add `spring-boot-starter-web` when you want pure WebFlux: having both starters usually causes Spring Boot to select Servlet/MVC instead of a reactive web application.

### 8.2. Main application

`src/main/java/dev/example/methodaop/MethodAopApplication.java`:

```java
package dev.example.methodaop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodAopApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodAopApplication.class, args);
    }
}
```

### 8.3. WebFlux and method security configuration

`src/main/java/dev/example/methodaop/SecurityConfig.java`:

```java
package dev.example.methodaop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/health").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Key points:

- `@EnableWebFluxSecurity` enables WebFlux HTTP security configuration; `@EnableReactiveMethodSecurity` enables **method-level authorization**. They are not a single annotation.
- `MapReactiveUserDetailsService` creates demo accounts `reader` with `ROLE_USER` and `admin` with both `ROLE_USER` and `ROLE_ADMIN`.
- `.anyExchange().authenticated()` requires login at the URL level; **it does not require ADMIN**. The ADMIN requirement lives only in `@PreAuthorize` on the sensitive method.
- `httpBasic` is enabled for testing with curl/`WebTestClient`; form login is disabled so status codes are clear.
- Passwords are BCrypt-hashed in memory. The two demo passwords in source code are **never for production**.
- Because all lesson requests are GET, default CSRF does not trigger 403 for missing CSRF tokens; do not assume POST APIs behave identically.

### 8.4. Bean with self-invocation (intentionally buggy for learning)

`src/main/java/dev/example/methodaop/ReportService.java`:

```java
package dev.example.methodaop;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.fromSupplier(() -> "restricted-report");
    }

    // Only to reproduce the self-invocation bug in local demo.
    public Mono<String> unsafeInternal() {
        return this.adminOnly();
    }
}
```

`ReportService` is public, non-final, `adminOnly` is public and non-final, and the bean is Spring-managed. All basic AOP conditions **are satisfied**. The only bug is calling `this.adminOnly()`. `Mono.fromSupplier` keeps evaluation lazy so learners don't confuse assembly-time side effects; it **does not fix** the proxy issue.

### 8.5. Workflow bean fixing via proxied call

`src/main/java/dev/example/methodaop/SafeWorkflow.java`:

```java
package dev.example.methodaop;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SafeWorkflow {

    private final ReportService reportService;

    public SafeWorkflow(ReportService reportService) {
        this.reportService = reportService;
    }

    public Mono<String> run() {
        return reportService.adminOnly();
    }
}
```

Because `ReportService` is Spring-injected into `SafeWorkflow`, the reference held is the AOP-proxied bean. When `SafeWorkflow.run()` calls `reportService.adminOnly()`, the interceptor checks the role before allowing results to flow downstream.

### 8.6. Controller exposing all three comparison paths

`src/main/java/dev/example/methodaop/ReportController.java`:

```java
package dev.example.methodaop;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    private final ReportService reportService;
    private final SafeWorkflow safeWorkflow;

    public ReportController(ReportService reportService,
                            SafeWorkflow safeWorkflow) {
        this.reportService = reportService;
        this.safeWorkflow = safeWorkflow;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/report/direct")
    public Mono<String> direct() {
        return reportService.adminOnly();
    }

    // FOR LOCAL DEMO ONLY, NEVER DEPLOY TO PRODUCTION.
    @GetMapping("/api/report/unsafe")
    public Mono<String> unsafe() {
        return reportService.unsafeInternal();
    }

    @GetMapping("/api/report/safe")
    public Mono<String> safe() {
        return safeWorkflow.run();
    }
}
```

**Analysis of expected results:**

| Endpoint | Actual call chain | User `reader` (`ROLE_USER`) | User `admin` (`ROLE_ADMIN`) |
| --- | --- | --- | --- |
| `GET /health` | Controller returns public | 200, `ok` | 200, `ok` |
| `GET /api/report/direct` | Controller → `ReportService` proxy → `adminOnly` | **403** | 200, `restricted-report` |
| `GET /api/report/unsafe` | Controller → `unsafeInternal` → **`this.adminOnly`** | **200, `restricted-report` (DEMO VULNERABILITY)** | 200, `restricted-report` |
| `GET /api/report/safe` | Controller → `SafeWorkflow` → `ReportService` proxy | **403** | 200, `restricted-report` |
| `GET /api/report/unsafe` without credentials | URL `authenticated()` blocks first | **401** | Not applicable |

**Explaining 401/403/200:** `reader` lacks ADMIN yet **was authenticated by HTTP Basic**; direct/safe are denied by method security so they return 403. Unsafe returns 200 because the method security advisor on `adminOnly` never ran. Unauthenticated users are blocked at 401 by the URL filter, even though the dangerous self-invocation path still exists underneath.

## 9. Running the demo and observing with curl

In `reactive-method-aop-demo`:

```bash
gradle bootRun
```

If a Gradle Wrapper exists: `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). The example uses `http://localhost:8080` locally; **HTTP Basic requires HTTPS in real environments**, never sending passwords over the internet over plain HTTP.

In another terminal:

```bash
curl -i http://localhost:8080/health

curl -i http://localhost:8080/api/report/direct

curl -i -u reader:reader-pass http://localhost:8080/api/report/direct
curl -i -u reader:reader-pass http://localhost:8080/api/report/unsafe
curl -i -u reader:reader-pass http://localhost:8080/api/report/safe

curl -i -u admin:admin-pass http://localhost:8080/api/report/direct
curl -i -u admin:admin-pass http://localhost:8080/api/report/safe
```

The passwords above are **dummy values strictly for local demos**; never put real passwords on the command line since shell history and process arguments can record them. For real services, use HTTPS and secure secret prompts (e.g., `curl` prompting for a password when only username is provided).

Key expected results:
- `/health` → 200, body `ok`.
- `/api/report/direct` without credentials → 401.
- Reader calling `/direct` → 403.
- Reader calling `/unsafe` → **200, body `restricted-report`**, purely to observe the self-invocation bypass.
- Reader calling `/safe` → 403.
- Admin calling `/direct` or `/safe` → 200, body `restricted-report`.

These are **expected results of the example**, not logs from running Gradle locally. Certain headers/error bodies may vary by version, yet the crucial authorization difference is **reader: direct=403, unsafe=200, safe=403**.

## 10. Integration testing with `WebTestClient`

Tests must catch an **unexpected 200 vulnerability** as well. If you only test that `admin` gets 200, you have no idea whether `reader` can slip through an internal call path.

File `src/test/java/dev/example/methodaop/MethodAopSecurityTests.java`:

```java
package dev.example.methodaop;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class MethodAopSecurityTests {

    @Autowired
    WebTestClient client;

    @Autowired
    ReportService reportService;

    @Test
    void reportServiceIsSpringAopProxy() {
        assertTrue(AopUtils.isAopProxy(reportService));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void anonymousCannotEnterApi() {
        client.get().uri("/api/report/unsafe")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerIsDeniedByDirectProxyInvocation() {
        client.get().uri("/api/report/direct")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerCanIncorrectlyAccessSelfInvocation() {
        // Test documenting the demo vulnerability, not desired production behavior.
        client.get().uri("/api/report/unsafe")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void readerIsDeniedWhenWorkflowCallsOtherBean() {
        client.get().uri("/api/report/safe")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallDirectMethod() {
        client.get().uri("/api/report/direct")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void adminCanCallSafeWorkflow() {
        client.get().uri("/api/report/safe")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void adminCanCallUnsafeDemoRoute() {
        client.get().uri("/api/report/unsafe")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("restricted-report");
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        client.get().uri("/api/report/direct")
                .headers(h -> h.setBasicAuth("reader", "incorrect"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

**Expected:** 10 tests pass with the demo configuration. This is expected from the code and contracts, **not a claim that Gradle ran on your machine**.

### Why is checking `AopUtils.isAopProxy` insufficient?

A bean can be a proxy because of another advisor (transaction, cache, logging...). `AopUtils.isAopProxy(bean) == true` only proves it is a Spring AOP proxy, **not** that a specific `@PreAuthorize` runs on every call path. The crucial tests are:

- Reader direct → 403.
- Reader unsafe → **200** (exposes bypass path).
- Reader safe → 403.

Once refactored, **delete the unsafe route** and replace the "reader can incorrectly access" test with a test asserting **reader is denied across all sensitive business entry points**. Never keep a test that accepts a vulnerability as production criteria.

### A method-level test without HTTP

If you don't want HTTP Basic, inject `ReportService` from the Spring `ApplicationContext` and attach authentication to Reactor Context using `StepVerifier`:

```java
Authentication reader = UsernamePasswordAuthenticationToken.authenticated(
        "reader", null,
        java.util.List.of(
                new SimpleGrantedAuthority("ROLE_USER")));

StepVerifier.create(
        reportService.adminOnly()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(reader)))
        .expectError(AccessDeniedException.class)
        .verify();
```

**This is an illustrative snippet inside a JUnit test**, not a standalone test file. Requires imports for `Authentication`, `UsernamePasswordAuthenticationToken`, `SimpleGrantedAuthority`, `ReactiveSecurityContextHolder`, `AccessDeniedException`, `StepVerifier`, and the `io.projectreactor:reactor-test` dependency. This verifies direct invocation through the proxy with Reactor Context; for `this.adminOnly()` inside the target, interception is still bypassed.

The advantage of HTTP tests is that they also verify security filters populate Reactor Context from real requests. The advantage of Reactor tests is isolating method-level logic. Both are valuable and do not completely replace each other.

## 11. How to fix the demo before moving to production?

A clean production version should **have no `unsafeInternal()` and no `/api/report/unsafe` route**. Keep:

```text
ReportController
    |
    v
SafeWorkflow.run()
    |
    v
ReportService proxy
    |
    v
@PreAuthorize("hasRole('ADMIN')")
    |
    v
ReportService.adminOnly()
```

Or have the controller call `ReportService.adminOnly()` directly on the injected bean if no extra orchestration is needed. Before going to production:

1. Remove endpoints exploiting self-invocation.
2. Audit every public method/entry point that can reach sensitive business logic.
3. Keep an enforceable authorization checkpoint, such as the service boundary via bean proxy.
4. Write **non-admin denied** tests for every entry point, not only admin allowed tests.
5. Keep appropriate URL-level rules rather than assuming every caller goes through a method proxy.
6. Add resource ownership/tenant authorization if sensitive data does not depend solely on ADMIN roles.
7. Ensure no pathway instantiates beans with `new` or invokes raw target objects from framework code.
8. Audit transactional/async/cache annotations too if they also rely on Spring AOP proxies.

For write operations, use `@PreAuthorize` to check permissions **before** executing the operation. `@PostAuthorize` checks after a result exists; never rely on it as the sole guard for irreversible side effects.

## 12. Deeper questions and edge cases

### 12.1. If the method is public and the bean is proxied, why is it still bypassed?

Because `this.adminOnly()` runs **on the target**, not through the proxy. Being `public` or non-`final` only makes external calls proxy-advisable; it does not turn internal calls into proxied calls.

### 12.2. What if we wrap it in `Mono.defer(() -> adminOnly())`?

Still bypassed if the lambda captures `this`/target. Reactor `defer` delays execution; it does not change the call receiver. Only when the lambda invokes a reference **to another Spring proxy** does the corresponding advice get a chance to run.

### 12.3. If a method is protected/private, is the annotation picked up?

Do not assume every visibility level is advised. Private methods cannot be overridden via class-based proxies; JDK proxies do not expose private methods either. For method security in a proxy environment, the safest guarantee is placing policies on **public bean entry points** called externally.

### 12.4. What if `@PreAuthorize` is placed on an interface?

Spring Security has mechanisms to discover annotations on interfaces/classes depending on configuration and proxy strategy. Consult docs for your exact version and avoid conflicting annotations; more importantly, **test behavior through the interface bean** and never assume an interface annotation makes `this` go through the proxy.

### 12.5. What if `ReactiveSecurityContextHolder` is missing?

In WebFlux integrated with Spring Security, `ReactorContextWebFilter` normally propagates the security context down the pipeline. If you call a service directly in a unit test without attaching authentication to Reactor Context, you may get a missing-context or deny error. That is **different from self-invocation**: in self-invocation, the annotated call never passes through the advisor in the first place.

### 12.6. Do `@Transactional` or `@Cacheable` suffer from internal self-invocation too?

Mechanisms using Spring AOP **proxy mode** have the exact same issue: calling from another method on the same target can skip transaction/cache advice. Each annotation has its own semantics, though; never assume a Spring Security workaround fixes every annotation if proxy topologies differ.

### 12.7. Does using AspectJ automatically fix everything?

AspectJ weaving (compile-time/load-time) differs from Spring AOP proxies and can advise self-invocation. However, reactive method security defaults to proxies; simply adding an AspectJ dependency will not automatically weave `@PreAuthorize` properly. Extracting a bean is usually simpler and safer.

### 12.8. What if a user lacks ADMIN yet the endpoint still returns 200?

Do not immediately blame SpEL `hasRole`. Check:
- Does the request actually pass through the target bean proxy?
- Is there a `this.method()` call in between?
- Was the bean created by Spring or manually via `new`?
- Is `@EnableReactiveMethodSecurity` enabled?
- Is `@PreAuthorize` on the exact right method/implementation?
- Is an `onErrorResume` swallowing `AccessDeniedException` and returning data?
- Is another route/service accessing the data without rules?
- Does the HTTP chain require only login rather than the needed privilege?
- Were negative tests with unauthorized users written for **every entry point**?

## 13. Code review checklist for method security

1. **Boundary:** Annotation sits on a public method of a Spring bean actually called via proxy.
2. **No self-invocation:** No `this.sensitiveMethod()` or implicit `sensitiveMethod()` inside the same class when relying on advice.
3. **Enable:** `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` is loaded, without confusing it with the Servlet stack.
4. **Bean lifecycle:** Services come from dependency injection, never instantiated with `new`.
5. **Proxyability:** Classes/methods are not accidentally `final`/`private` under class-based proxies; interfaces are injected properly under JDK proxies.
6. **Reactive return:** Protected methods return suitable `Mono`/`Flux`; never call `block()` inside WebFlux handlers.
7. **Context:** Authentication flows through Reactor Context; direct tests must populate context appropriately.
8. **Expression:** `hasRole("ADMIN")` maps to authority `ROLE_ADMIN` with default prefix; `hasAuthority` checks exact strings.
9. **Error handling:** Never swallow `AccessDeniedException` or turn denials into success via fallbacks.
10. **Defense in depth:** Both HTTP authorization and method authorization are reviewed.
11. **Tests:** Reader/non-admin gets 403 at all sensitive entry points; admin gets 200; anonymous gets 401 appropriately.
12. **Deployment:** No unsafe demo endpoints, no demo credentials, and no HTTP Basic without TLS outside localhost.

## 14. Before and after comparison table

| Criterion | Before: self-invocation | After: bean extraction |
| --- | --- | --- |
| Call path | `this.adminOnly()` on target | `safeWorkflow -> reportService proxy -> adminOnly()` |
| Goes through `adminOnly` proxy? | No | Yes |
| `@PreAuthorize` checked? | Bypassed | Enforced |
| Reader lacking ADMIN | Can receive secret 200 | Denied with 403 |
| Admin | Receives result | Receives result |
| Negative testing | Easy to miss if testing only ADMIN | Both direct and workflow tests prove denial |
| Coupling to AOP API | Unclear and broken at call path | No need to call `AopContext` |
| Operational posture | Privilege escalation risk | Clear proxy boundary design |

Even after extracting a bean, **every other entry point** to sensitive data must still be checked. One properly protected method does not automatically make databases, caches, or other endpoints safe.

## 15. Self-check questions and answers

**1. What role does a Spring AOP proxy play in method security?**  
It lets Spring intercept external method calls to run authorization advice before/after invoking the target.

**2. Why does `this.adminOnly()` bypass `@PreAuthorize`?**  
Because an internal call on the target does not go back through the Spring proxy, so that method's advice is never invoked.

**3. Does `Mono.defer(this::adminOnly)` fix it?**  
No. It only defers the self-invocation; the receiver is still the target, not the proxy.

**4. Why can self-invocation happen on a bean that is already a Spring proxy?**  
The proxy intercepts calls **entering through the proxy**. Inside the target, `this` still points to the raw target object.

**5. What is the preferred fix?**  
Extract the protected operation into a separate bean, inject it, and call its public method through the Spring proxy. Or guard the exact public entry point that all callers pass through.

**6. How do roles and authorities differ?**  
`roles("ADMIN")` typically creates authority `ROLE_ADMIN`; `hasRole("ADMIN")` checks the prefixed authority. `hasAuthority("reports:read")` checks the literal authority string.

**7. If you use `new ReportService()`, will annotations run?**  
Normally no: the object bypasses the Spring container and method-security proxy.

**8. Why are `private`/`final` methods unsuitable for class-based proxies?**  
Private methods cannot be overridden; final methods cannot be overridden. Subclass proxies cannot apply standard advice to those calls.

**9. Why is testing that `admin` gets 200 insufficient?**  
Because unauthorized users might still get 200 through a self-invocation path. Negative tests with `reader` are mandatory.

**10. What are the expected results for `reader` on the three demo endpoints?**  
`/direct` → 403; `/unsafe` → 200 (demo bug); `/safe` → 403.

**11. When does a method authorization failure become HTTP 403?**  
When the method call is blocked with an access-denied signal and WebFlux Security translates it into a Forbidden response for an authenticated user.

**12. Does `@EnableWebFluxSecurity` automatically enable method security?**  
Do not rely on that. You must enable `@EnableReactiveMethodSecurity` for annotation-based reactive method authorization.

**13. When using Kotlin `final` classes, what should you watch out for?**  
Class-based proxies cannot subclass final classes; you may need to open classes with an appropriate plugin or use interfaces/proxies, and test thoroughly.

**14. Why does `AopUtils.isAopProxy` not prove permissions are checked?**  
Because a bean being proxied does not guarantee every call path traverses the right advisor; testing denied behavior is the critical proof.

### Hands-on exercises

1. Run the demo and confirm with `curl` or `WebTestClient` that reader direct/safe return 403 while unsafe returns 200. Explain **precisely** where the proxy is bypassed.
2. Delete `unsafeInternal()`, replace `/api/report/unsafe` with `safeWorkflow.run()` or remove the endpoint. Update tests so **reader always gets 403** across all entry points.
3. Add a `@PreAuthorize("hasAuthority('report:export')")` method on another bean, create a user with that permission, and test with `WebTestClient`.
4. Write `public Mono<String> invokeIndirect() { return adminOnly(); }` in `ReportService` and test it. Explain why omitting `this` does not fix the bug.
5. Try placing `@PreAuthorize` on a private helper and explain why proxy-based interception must not be trusted there. Never deploy the broken pattern to production.
6. Write an `AopUtils.isAopProxy(reportService)` test alongside a reader-denied test; explain why the second test is more essential.
7. Temporarily add an `onErrorResume(AccessDeniedException.class, ... )` in the controller layer only in a learning environment, observe the danger of returning success when exceptions are swallowed, then remove it.
8. Redraw the two-bean workflow diagram and highlight that the controller must receive a **Spring-managed bean** via constructor injection, never `new`.

## 16. Official documentation

- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, Reactor Context, and method interceptor infrastructure.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxies, `this` self-invocation, `final`/`private` limitations, and alternatives.
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html): advice, proxies, and pointcuts.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): HTTP authentication/authorization and `SecurityWebFilterChain`.
- [Spring Security — Reactive Method Security tests](https://docs.spring.io/spring-security/reference/servlet/test/method.html): method security test examples; when applying to reactive, use Reactor Context properly.
- [Project Reactor — Adding a Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context and subscriptions.
- [Spring Boot Gradle Plugin 3.3.5](https://docs.spring.io/spring-boot/docs/3.3.5/gradle-plugin/reference/htmlsingle/): running applications and Gradle tasks.

**Key takeaway:** `@PreAuthorize` works when **calls pass through the Spring AOP proxy**. Calling `this.someMethod()` on the same target **bypasses the proxy**, so annotations on the target method can be skipped even in WebFlux on a `Mono`-returning method. The durable fix is **placing authorization on an externally called public boundary** or **extracting the protected operation into another Spring bean**, while testing unauthorized users across every entry point.