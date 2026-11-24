# @PreAuthorize and Checking Permissions Before Business Execution

## Learning Objectives

This lesson belongs to **Method Authorization** in **Spring Security reactive (Spring WebFlux)**. After this lesson, you will be able to:

- Explain `@PreAuthorize` as an **authorization check before the business method is allowed to run**, distinct from authentication and from URL rules in `authorizeExchange(...)`.
- Enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` and understand how Spring AOP, `AuthorizationManagerBeforeReactiveMethodInterceptor`, `ReactiveSecurityContextHolder`, and Reactor `Context` work together.
- Write SpEL expressions such as `hasRole('ADMIN')`, `hasAuthority('SCOPE_reports.read')`, `isAuthenticated()`, compare parameter `#p0` with `authentication.name`, and invoke policy beans.
- Understand why protected reactive methods should return `Mono<T>` or `Flux<T>`, and why side effects must remain inside the pipeline so you can verify **no business logic runs when denied**.
- Distinguish internal `AccessDeniedException` from HTTP 401/403 status codes, and identify cases where `@PreAuthorize` does not run due to self-invocation or a missing Spring proxy.
- Run a **Java 17 + Spring WebFlux** example, test method security with Reactor `StepVerifier`, and test HTTP endpoints with valid/insufficient credentials.

> **Scope:** **reactive** Spring Security with `@EnableReactiveMethodSecurity`. Do not mix with Servlet's `@EnableMethodSecurity` or ThreadLocal-based `SecurityContextHolder`. This lesson focuses on **before-method authorization**; APIs such as `@PostAuthorize` are mentioned only for contrast.

## 1. Why check permissions at the method layer?

A WebFlux system often has multiple paths calling the same service:

~~~text
HTTP Controller ---------+
                         |
Message Consumer --------+--> ReportService.readConfidentialReport()
                         |
Scheduled Job -----------+
                         |
Another service ---------+
~~~

If you only authorize at HTTP URLs, you are protecting calls **going through the controller**. Other calls, or a new route that happens to invoke the service, may not be bound by the same rule. Method security adds a **protective boundary close to where business logic executes**.

Example requirement: *Only users with the ADMIN role may read internal reports*.

HTTP-level rule:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated());
~~~

This is a **`ServerHttpSecurity` configuration fragment**, not a standalone Java program. It protects `/api/admin/**` URLs, yet if a controller at `/api/reports/secret` or a job calls the service directly, the rule above does not directly cover that call.

Add protection at the service:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readConfidentialReport() {
        return Mono.just("internal-report");
    }
}
~~~

The snippet above is an illustrative class; imports are `@Service`, `@PreAuthorize`, and `Mono`. When reactive method security is enabled, a call through the Spring proxy evaluates authorization **before the method body is allowed to execute**. Unauthorized callers receive an error and never receive confidential data.

**Defense in depth:** You should have both HTTP authorization (who can call a route) and method authorization (who can execute a business operation). The two layers can use different rules. `permitAll()` at the URL layer **does not override** `@PreAuthorize` on the service.

## 2. Authentication and authorization are different

- **Authentication:** Which identity does the request sender hold? For example, `Authentication.getName() == "reader"`, with authorities containing `ROLE_USER`.
- **Authorization:** Is that identity permitted to perform a specific action on a specific resource?
- **HTTP authorization:** `ServerHttpSecurity.authorizeExchange(...)` evaluates requests/matchers in the WebFilter chain.
- **Method authorization:** `@PreAuthorize(...)` evaluates a **method invocation**, and can use the principal, roles, authorities, and method arguments.

| Scenario | Method-level decision | Meaning |
|---|---|---|
| Anonymous caller invokes a method requiring `hasRole('ADMIN')` | Denied | No Authentication satisfies the rule. |
| Logged-in user `reader` has only `ROLE_USER` | Denied | Authenticated, but lacks ADMIN role. |
| User `admin` has `ROLE_ADMIN` | Granted | Method body is allowed to be called. |
| Authenticated user calls a method allowing only their own record | Depends on identity + ownership | A generic role is insufficient; a per-resource policy is needed. |
| Public `permitAll()` URL calls a method requiring ADMIN | Can still be denied | HTTP-level permit and method-level permit are two independent decisions. |

Do not infer that an authenticated user is allowed to view all data. Likewise, never treat a client-sent `X-Role: ADMIN` header as a verified `GrantedAuthority`.

## 3. Enabling Reactive Method Security properly

With Spring Security 6.x, the recommended declaration in documentation is:

~~~java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class MethodSecurityConfig {
}
~~~

Requires importing `org.springframework.context.annotation.Configuration` and `org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity`. The annotation can be placed on another Spring configuration class; the hands-on example puts it directly alongside `@SpringBootApplication`.

Essential prerequisites:

1. Include the appropriate Spring Security dependency in the WebFlux application.
2. Enable **`@EnableReactiveMethodSecurity`** — enabling only `@EnableWebFluxSecurity` or `http.authorizeExchange(...)` does not automatically activate `@PreAuthorize` on services.
3. The method must reside on a **Spring-managed bean**, invoked **through the Spring AOP proxy** (not `new ReportService()` or `this.method()` self-invocation in the same class).
4. Protected methods return a reactive `Publisher` such as `Mono` or `Flux` so Spring can integrate with **Reactor Context**. Versions supporting Kotlin coroutines have their own mechanism.
5. An `Authentication` must be populated into the reactive subscription's context, such as by the WebFlux security filter chain from HTTP Basic/Bearer/form login.

### 3.1. What do AuthorizationManager and Spring AOP do?

With `useAuthorizationManager=true`, Spring Security creates method interceptors based on `AuthorizationManager`. For `@PreAuthorize`, the before-method mechanism uses `AuthorizationManagerBeforeReactiveMethodInterceptor` to evaluate the expression and make a decision.

~~~text
Caller (Controller / another service)
    |
    v
Spring AOP proxy of ReportService
    |
    v
@PreAuthorize expression
    |
    +-- read Authentication from Reactor Context
    +-- get method arguments (if expression needs them)
    +-- evaluate hasRole / hasAuthority / policy bean
    |
    +-- DENY --> AccessDeniedException (Mono/Flux error)
    |               Method body / business logic does not run
    |
    +-- GRANT --> invoke target method and continue Publisher
                    |
                    v
                 DB/API/business logic
~~~

The diagram explains the intended behavior. In a reactive environment, you must **subscribe to the publisher** for signals and authorization checks to take place. Do not call `block()` inside a WebFlux service or call `subscribe()` manually to escape the security lifecycle.

### 3.2. Reactor Context, not ThreadLocal

Reactive Spring Security accesses context through `ReactiveSecurityContextHolder` and Reactor `Context`. This matters when a pipeline switches schedulers/threads; a Servlet-style `ThreadLocal` is not guaranteed to carry Authentication across reactive operators.

Pure Reactor example — a **code snippet inside a Java method** with an already validly constructed Authentication:

~~~java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(securityContext -> securityContext.getAuthentication())
        .map(authentication -> authentication.getName());

Mono<String> withUser = currentUser.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication));
~~~

The `authentication` variable here is a server-verified `Authentication`; this snippet is not a way to turn unverified header data into a logged-in user. In WebFlux requests handled by the security filter chain, the framework usually sets the context automatically.

**If there is no security context**, an expression like `hasRole('ADMIN')` will not grant access. In certain direct method-call tests, `AccessDeniedException` surfaces as a reactive error rather than automatically turning into an HTTP status.

## 4. Writing @PreAuthorize expressions

`@PreAuthorize` accepts a SpEL expression whose result determines whether the method may be invoked.

| Expression | Meaning | Things to remember |
|---|---|---|
| `@PreAuthorize("hasRole('ADMIN')")` | Requires `ROLE_ADMIN` with default prefix. | `hasRole` adds `ROLE_`; do not write `hasRole('ROLE_ADMIN')` out of habit. |
| `@PreAuthorize("hasAnyRole('USER','ADMIN')")` | Has at least one specified role. | Roles are still mapped to prefixed authorities. |
| `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` | Requires exact authority `SCOPE_reports.read`. | Useful with OAuth2/JWT scopes when the converter grants that authority. |
| `@PreAuthorize("isAuthenticated()")` | Requires a valid Authentication per policy. | Does not imply permission to run every operation. |
| `@PreAuthorize("#p0 == authentication.name")` | First method argument must equal principal name. | Simple ownership example only; real owner must be verified from the database. |
| `@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")` | Resource owner or admin. | `#p0` avoids relying on parameter names retained in bytecode. |
| `@PreAuthorize("@documentAcl.canRead(#p0, authentication)")` | Calls policy bean `documentAcl`. | Used for complex decisions; can return `Mono<Boolean>` with AuthorizationManager config. |
| `@PreAuthorize("denyAll()")` | Always denies. | Useful when temporarily disabling a feature, though method security must actually be enabled. |

### 4.1. hasRole and hasAuthority

When using:

~~~java
User.withUsername("reader")
    .password("{noop}demo-pass")
    .roles("USER")
    .build();
~~~

`roles("USER")` creates `ROLE_USER`; the expression `hasRole('USER')` checks this exact authority. Meanwhile, `hasAuthority('USER')` looks for an authority **named exactly** `USER` and is not automatically equivalent to `ROLE_USER`. Thus, if an API grants scope `SCOPE_reports.read`, use `hasAuthority('SCOPE_reports.read')` or an appropriate converter/mapping.

Both roles and authorities are trustworthy only when coming from a verified Authentication source (such as a security manager or token validator); never construct roles from user-chosen query parameters or headers.

### 4.2. Reading method arguments in SpEL

Given the method:

~~~java
@PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
public Mono<String> readForOwner(String owner) {
    return Mono.just("owner=" + owner);
}
~~~

The expression compares the **first parameter** with `Authentication.getName()`, or lets ADMIN pass. Use `#p0` (or `#a0`) to avoid relying on parameter name metadata. If using `#owner`, ensure parameter names are preserved for Spring SpEL via compiler metadata (typically the `-parameters` flag or a supporting annotation).

**Pitfall to avoid:** If `owner` comes from a client-supplied URL path, comparing it to username only proves **the client typed their own name**; it does not prove the accessed record actually belongs to that user. Real business logic must check permissions based on the **trusted owner/ID in the database**, tenant relationships, scopes, and resource state.

### 4.3. Calling an authorization bean — can be asynchronous

A per-record policy often needs to query a database. According to Spring Security 6.x documentation with `AuthorizationManager`, expressions can call a bean returning `Boolean` **or** `Mono<Boolean>`:

~~~java
@PreAuthorize("@documentAcl.canRead(#p0, authentication)")
public Mono<Document> readDocument(Long documentId) {
    return repository.findById(documentId);
}
~~~

This snippet is an illustrative method; `Document` and `repository` belong to the application domain. A policy bean can have the signature:

~~~java
@Component("documentAcl")
public class DocumentAcl {

    private final DocumentRepository repository;

    public DocumentAcl(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(
        Long id, Authentication authentication) {

        return repository.findById(id)
            .map(doc ->
                authentication != null &&
                (doc.ownerUsername().equals(authentication.getName())
                 || authentication.getAuthorities().stream()
                       .anyMatch(a ->
                           a.getAuthority().equals("ROLE_ADMIN"))))
            .defaultIfEmpty(false);
    }
}
~~~

**This is an illustrative class that does not compile standalone** because `Document`, `DocumentRepository`, and ownership mapping belong to a real project. Also import `org.springframework.stereotype.Component`, `org.springframework.security.core.Authentication`, and `reactor.core.publisher.Mono`. `defaultIfEmpty(false)` ensures that missing records result in **deny** rather than leaving an empty publisher that could be interpreted as abstain. In practice, define whether "record not found" yields 404 or 403 so you do not leak resource existence.

Authorization beans must avoid blocking operations on the event loop; use reactive repositories or bounded offloading. Never call `block()` inside a SpEL expression to query permissions.

## 5. Before business execution: protecting side effects

This lesson emphasizes **checking permissions before executing business logic**, which is especially critical when a method transfers money, publishes reports, mutates order state, or sends notifications.

Example of **what not to do**:

~~~java
// Illustrative method body: work runs immediately when the method is called.
// Can make reactive lifecycle control and testing difficult.
public Mono<Void> publishReport(Long id) {
    auditClient.sendImmediately(id); // synchronous eager side effect!
    return reportRepository.publish(id);
}
~~~

Even if Spring AOP blocks the target method before invocation, **eager side effects** in unprotected publishers or calls bypassing the proxy make the system harder to control. Reactive side effects should live inside the publisher so they are governed by subscription, error, and cancellation semantics.

Reactive-friendly approach:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> publishReport(Long id) {
    return Mono.defer(() ->
        reportRepository.publish(id));
}
~~~

This is a **service method snippet**; `reportRepository` is a reactive application dependency. When a caller goes through the proxy and authorization is denied, the pipeline does not invoke the business body of the method. For authorized users, the work runs when the publisher is subscribed. `Mono.defer` prevents creating side effects before subscription and provides a clean execution per subscription.

**Do not confuse before-method execution with transactional guarantees.** After authorization grants access, data or permissions can still change (TOCTOU: time-of-check/time-of-use). For sensitive operations, enforce tenant/owner constraints directly in the update query or transaction, using appropriate optimistic locking/constraints. Method security is one layer; it does not replace consistency checks in the database.

### 5.1. Why calling subscribe() to "bypass errors" is wrong

~~~java
// WRONG in WebFlux controller/service:
protectedService.publishReport(id).subscribe();
return Mono.empty();
~~~

This is an anti-pattern snippet to recognize errors. Calling `subscribe()` creates a detached subscription, making errors, cancellation, and Reactor Context hard to coordinate; it can lose the authentication context or return HTTP success before the operation fails. The right way is usually:

~~~java
// Return the publisher and let the framework subscribe.
return protectedService.publishReport(id);
~~~

For `Mono`, never call `block()` on the Netty event loop. Only in unit tests do you use `StepVerifier` to actively subscribe and inspect signals.

## 6. HTTP authorization and method authorization: order and status

HTTP configuration typically sets clear URL rules:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public").permitAll()
    .anyExchange().authenticated());
~~~

If an unauthenticated request hits a protected endpoint, the HTTP layer typically responds with **401** when HTTP Basic is enabled. If an authenticated request lacks permissions required by `@PreAuthorize`, the service emits `AccessDeniedException`, which WebFlux security exception handling usually converts into **403 Forbidden**.

| Request | HTTP layer | Method layer | Typical HTTP status |
|---|---|---|---|
| No Basic auth to protected `/api/docs/secret` | `authenticated()` rejects | May not be invoked | **401** (Basic challenge) |
| Valid Basic `reader` to protected secret | Passes because authenticated | `hasRole('ADMIN')` rejects | **403** |
| Valid Basic `admin` to protected secret | Passes | Method grants | **200** |
| Valid Basic `reader` to `reader`'s owner record | Passes | Owner expression grants | **200** |
| Valid Basic `reader` to `alice`'s owner record | Passes | Owner expression rejects | **403** |
| Valid Basic `admin` to any owner record | Passes | Admin override grants | **200** |

The HTTP statuses in the table are expected with the demo configuration below. **`AccessDeniedException` is not inherently an HTTP response**: when calling a service directly in a test or background job, it is a reactive error signal and has no 401/403 status without an HTTP adapter. With custom exception handlers or different filter chains, status mapping can change.

Do not let a controller catch `AccessDeniedException` and return a default 200 or log confidential data. Let the security infrastructure translate errors according to policy, or customize denial handling explicitly and test it thoroughly.

## 7. Standalone runnable Java 17+ example: protecting ReportService with @PreAuthorize

The project uses **Java 17**, **Spring Boot 3.5.16**, and WebFlux/Spring Security 6.5 libraries managed by Boot. Spring Boot 3.5.16 has been released as the final OSS release of the 3.5 line; production projects should use a supported branch/appropriate patches. In this exercise, the version is pinned so learners can build a consistent example.

Features:

- User `reader:demo-pass` has `ROLE_USER`.
- User `admin:admin-pass` has `ROLE_ADMIN`.
- Endpoint `GET /api/docs/secret` requires HTTP login and service-level ADMIN role.
- Endpoint `GET /api/docs/owner/{owner}` requires HTTP login; the method allows only `owner == Authentication.name` or ADMIN.
- `DocumentService.secretReadCount()` is a **test-only counter** used to prove rejected calls do not read business data. The counter increments **inside `Mono.defer(...)`**, and does not increment when denied.
- Endpoint `/api/public` is public and holds no secret data.

### 7.1. Directory structure

~~~text
reactive-preauthorize-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/ReactivePreAuthorizeDemo.java
    └── test/java/example/DocumentServiceSecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-preauthorize-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Requires JDK 17+ and a Gradle/Gradle Wrapper version compatible with Spring Boot. Use the wrapper if available in the project for consistent builds. Section 7.2 places all main classes in **one file**; section 8 has a separate test class.

### 7.2. Complete application

File `src/main/java/example/ReactivePreAuthorizeDemo.java`:

~~~java
package example;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactivePreAuthorizeDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactivePreAuthorizeDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Localhost only: {noop} and hardcoded passwords are unsafe.
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-pass")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Service
    public static class DocumentService {

        private final AtomicInteger secretReads = new AtomicInteger();

        // HTTP layer only requires authenticated;
        // service layer requires ROLE_ADMIN.
        @PreAuthorize("hasRole('ADMIN')")
        public Mono<Map<String, Object>> readSecret() {
            return Mono.defer(() -> {
                int count = secretReads.incrementAndGet();
                return Mono.just(Map.of(
                    "classification", "ADMIN_ONLY",
                    "readCount", count));
            });
        }

        // #p0 is the first parameter, independent of parameter names in bytecode.
        @PreAuthorize("#p0 == authentication.name or hasRole('ADMIN')")
        public Mono<Map<String, String>> readOwned(String owner) {
            return Mono.defer(() -> Mono.just(Map.of(
                "owner", owner,
                "content", "demo-only")));
        }

        // This method is for testing only, with no business side effects.
        public int secretReadCount() {
            return secretReads.get();
        }
    }

    @RestController
    static class DocumentController {

        private final DocumentService service;

        DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/api/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/api/docs/secret")
        Mono<Map<String, Object>> secret() {
            return service.readSecret();
        }

        @GetMapping("/api/docs/owner/{owner}")
        Mono<Map<String, String>> owned(@PathVariable String owner) {
            return service.readOwned(owner);
        }
    }
}
~~~

**Explanation of ordering and structure:**

1. `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` activates reactive interceptors. Omitting this line may leave service annotations as inert metadata without enforcement.
2. `DocumentService` is a `@Service` Spring bean injected into the controller via constructor injection. Calls pass through the bean proxy, not internal `this.readSecret()` within the same class.
3. HTTP `anyExchange().authenticated()` allows `reader`/`admin` through when valid Basic credentials are provided. Service-level rules decide who can read secret reports.
4. `.roles("ADMIN")` creates the `ROLE_ADMIN` authority, matching `hasRole('ADMIN')`.
5. `readSecret()` constructs the Mono via `defer`; `secretReads.incrementAndGet()` only happens if the business publisher is subscribed after authorization grants access.
6. `readOwned(String owner)` illustrates SpEL using an argument + identity. **Do not use this path-owner pattern as a production ACL:** real records must be tied to owner/tenant in the database, not merely client-controlled parameters.
7. The controller neither checks `Authentication` itself nor calls `subscribe()`; it returns the publisher for WebFlux and security filters to coordinate.
8. All endpoints are **GET** so the exercise focuses on method authorization without confusing CSRF on POST requests. When adding write endpoints, you must still handle CSRF/sessions/tokens per your threat model.

### 7.3. Testing over HTTP

In the `reactive-preauthorize-demo` directory, with JDK 17 and a compatible Gradle version:

~~~bash
gradle bootRun
~~~

If a Gradle Wrapper exists, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

In another terminal:

~~~bash
# 1. No credentials -> HTTP layer requires login.
curl -i http://localhost:8080/api/docs/secret

# 2. Valid password but lacks ADMIN role.
curl -i -u reader:demo-pass http://localhost:8080/api/docs/secret

# 3. ADMIN is allowed to read.
curl -i -u admin:admin-pass http://localhost:8080/api/docs/secret

# 4. Reader reads data matching their own name.
curl -i -u reader:demo-pass http://localhost:8080/api/docs/owner/reader

# 5. Reader tries another user's name.
curl -i -u reader:demo-pass http://localhost:8080/api/docs/owner/alice

# 6. ADMIN can access any owner in the demo.
curl -i -u admin:admin-pass http://localhost:8080/api/docs/owner/alice

# 7. Public endpoint.
curl -i http://localhost:8080/api/public
~~~

With PowerShell, if `curl` is an unwanted alias, use `curl.exe`. `-i` shows HTTP status/headers; `-u` sends Basic credentials. Use dummy passwords only on localhost; never put real secrets in shell commands on shared machines.

| Request | Expected status | Explanation |
|---|---|---|
| No Basic auth to `/api/docs/secret` | **401** | HTTP security `authenticated()` requires login, Basic challenge. |
| Reader to `/api/docs/secret` | **403** | HTTP passes, method `@PreAuthorize("hasRole('ADMIN')")` denies. |
| Admin to `/api/docs/secret` | **200** | JSON has `classification=ADMIN_ONLY`, `readCount` increments. |
| Reader to `/api/docs/owner/reader` | **200** | `#p0 == authentication.name` allows. |
| Reader to `/api/docs/owner/alice` | **403** | Neither owner nor ADMIN. |
| Admin to `/api/docs/owner/alice` | **200** | `hasRole('ADMIN')` branch allows. |
| Anonymous to `/api/public` | **200** | Endpoint does not require HTTP login; does not call protected service. |

These are **HTTP responses**, not Java stdout. For example, a successful body might be `{"classification":"ADMIN_ONLY","readCount":1}` on the first admin call; the count and JSON key order are not fixed across runs or multiple requests. Tests should assert status codes and meaningful fields rather than comparing raw responses verbatim.

### 7.4. How is the "before business execution" effect verified?

From HTTP, we observe `reader` receives 403. However, status 403 alone does not prove a side effect did not occur, since a controller or method could write data before throwing an exception. Section 8 tests the method directly and compares `secretReadCount()` **before and after** a denied call to prove the business publisher never executed. In production, combine tests with DB transactions, audit side effects, or appropriate mock dependencies.

## 8. Testing @PreAuthorize directly with StepVerifier

The project declares `spring-security-test` and `reactor-test`. At the method layer, `@WithMockUser` creates a test Authentication without making HTTP Basic calls. `StepVerifier` subscribes to the Mono to assert success/error signals.

File `src/test/java/example/DocumentServiceSecurityTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    ReactivePreAuthorizeDemo.DocumentService service;

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerDeniedBeforeSecretRead() {
        int before = service.secretReadCount();

        StepVerifier.create(service.readSecret())
            .expectError(AccessDeniedException.class)
            .verify();

        // Side effect inside Mono.defer is not executed.
        assertEquals(before, service.secretReadCount());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadSecret() {
        int before = service.secretReadCount();

        StepVerifier.create(service.readSecret())
            .expectNextMatches(record ->
                "ADMIN_ONLY".equals(record.get("classification")))
            .verifyComplete();

        assertEquals(before + 1, service.secretReadCount());
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerCanReadOwnRecord() {
        StepVerifier.create(service.readOwned("reader"))
            .expectNextMatches(record ->
                "reader".equals(record.get("owner")))
            .verifyComplete();
    }

    @Test
    @WithMockUser(username = "reader", roles = "USER")
    void readerCannotReadOtherOwner() {
        StepVerifier.create(service.readOwned("alice"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadOtherOwner() {
        StepVerifier.create(service.readOwned("alice"))
            .expectNextMatches(record ->
                "alice".equals(record.get("owner")))
            .verifyComplete();
    }

    @Test
    void anonymousCannotReadSecret() {
        StepVerifier.create(service.readSecret())
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

If a wrapper is present: `./gradlew test` or `gradlew.bat test`. These tests are written for the illustrative configuration; they must actually be executed in your build environment to confirm dependencies and outcomes. With a valid setup, six tests are expected to pass. The test without `@WithMockUser` verifies the method denies access when no suitable Authentication is present.

**Why does @WithMockUser work in reactive tests?** Spring Security Test sets up the appropriate context for method security; `StepVerifier` subscribes to the publisher returned by the proxy. This is not creating a ThreadLocal and hoping it automatically propagates across every reactive scheduler. Spring Security documentation includes `@WithMockUser` + `StepVerifier.expectError(AccessDeniedException.class)` examples for reactive methods.

### 8.1. Also add HTTP integration tests

Method tests verify rules and before-business behavior; HTTP tests verify WebFilter routing and error mapping to 401/403. With `WebTestClient`, include at minimum:

- `GET /api/docs/secret` without Basic auth → 401 and `WWW-Authenticate` per Basic config.
- `reader` with valid Basic auth → 403.
- `admin` with valid Basic auth → 200, JSON response contains only allowed fields.
- `reader` accessing `owner/reader` → 200; accessing `owner/alice` → 403.
- Public endpoint → 200.
- When adding write endpoints, test CSRF and role/method policies separately.

You can bind `WebTestClient` to the `ApplicationContext` with `SecurityMockServerConfigurers.springSecurity()`, or use `@SpringBootTest(webEnvironment=RANDOM_PORT)` + a real HTTP client to verify the security chain.

### 8.2. Robust testing against permission changes

Do not test only users with `ROLE_ADMIN`. For owner/tenant policies, test at least:

1. User in the same tenant + authorized → succeeds.
2. User in a different tenant who knows a valid ID → denied.
3. Non-existent ID → denied/404 per policy without leaking information.
4. User role changes or disabled user → verify against actual refresh/revocation mechanisms.
5. Concurrent updates/ownership changes → enforce at the database/transaction level, not just annotations.

## 9. Places where @PreAuthorize is easily bypassed

### 9.1. Self-invocation inside the same bean

~~~java
@Service
public class ReportService {

    public Mono<String> outerCall() {
        return innerProtected(); // Internal call, may bypass proxy.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> innerProtected() {
        return Mono.just("secret");
    }
}
~~~

This is an **architectural bug example**, not a class to put directly into the demo. Spring AOP proxies typically only intercept when a caller invokes **through the proxy**. `this.innerProtected()` or an internal call from `outerCall()` bypasses the proxy and may **not trigger** the check. Fix by extracting the protected method into a separate Spring bean and injecting it, or redesigning to avoid self-invocation.

### 9.2. Instantiating services with new

~~~java
// WRONG when expecting Spring AOP method security to work:
ReportService raw = new ReportService();
raw.innerProtected();
~~~

Directly instantiating objects bypasses the Spring container/proxy; `@PreAuthorize` does not magically "run" just because the annotation is in bytecode. `private`, `final` methods, or classes that cannot be proxied by AOP also require special caution. Use Spring beans and appropriate public methods.

### 9.3. Annotation on controller while service remains unprotected

Placing `@PreAuthorize` only on a controller protects that route, but does not protect other callers of the service. When rules tie to business operations, place them at the service boundary (while retaining HTTP authorization). Avoid duplicating the same expression across many controllers, which causes rules to drift out of sync.

### 9.4. Returning String/void in a protected reactive method

Spring Security docs emphasize that reactive method security requires methods to return `org.reactivestreams.Publisher` like `Mono`/`Flux` to integrate with Reactor Context (or supported coroutine mechanisms). Do not copy Servlet Java demos with blocking methods returning `String` and expect identical behavior in reactive method security.

### 9.5. Using ThreadLocal to read the principal

ThreadLocal-based `SecurityContextHolder.getContext()` may not hold the right Authentication when reactive pipelines switch threads. Use `ReactiveSecurityContextHolder.getContext()`, framework principal injection, or SpEL `authentication` inside reactive interceptors.

### 9.6. Missing the enable annotation

Without `@EnableReactiveMethodSecurity`, service annotations may not be enforced. This is why **the reader-denied test** is crucial: if misconfigured, the test will fail instead of silently leaving a vulnerability open.

### 9.7. Reading authorization from self-declared body/headers

For instance, `@PreAuthorize("#role == 'ADMIN'")`, where `role` is a client-sent request parameter, is a critical vulnerability. Policies must rely on a verified `Authentication` and authoritative server data. Client input serves as a **resource identifier to query** or requested action, never as the source of truth for permissions.

### 9.8. Mismatched scope/role prefixes

`hasRole('ADMIN')` checks `ROLE_ADMIN` with the default prefix. `hasAuthority('SCOPE_admin')` checks the exact string. If a JWT converter supplies `SCOPE_reports.read` while the expression checks `ROLE_ADMIN`, denial is expected; design the mapping to match policy rather than forcing access with `permitAll`.

### 9.9. Using @PostAuthorize instead of @PreAuthorize for write operations

`@PostAuthorize` checks **after the method executes**/when the value is returned along the pipeline. If the method already performed side effects, denying the return value does not necessarily undo changes in the database or external APIs. For operations with side effects, prefer checking **beforehand** with `@PreAuthorize` and enforcing authorization in transactions/repositories, rather than permitting writes and trying to hide the response.

### 9.10. Turning AccessDeniedException into Mono.empty()

~~~java
// Do not do this in a service if the goal is to protect data:
return protectedService.readSecret()
    .onErrorResume(AccessDeniedException.class, ex -> Mono.empty());
~~~

Illustrative snippet only. Swallowing authorization errors may trick the caller into thinking no record exists rather than access being forbidden; in some flows it could accidentally yield a success status. Handle errors explicitly per policy at the boundary rather than "silently passing".

## 10. Advanced points worth remembering

### 10.1. @PreAuthorize with Mono<Boolean> from an authorization bean

When authorization checks require a non-blocking DB lookup, a bean can return `Mono<Boolean>`. With `@EnableReactiveMethodSecurity(useAuthorizationManager=true)`, Spring Security 6.5 docs show examples of reactive bean functions in expressions. However, ensure:

- The policy bean uses the exact Spring bean name in SpEL.
- Permission data comes from a trusted source, not just from the request.
- `Mono.empty()` has different semantics from `Mono.just(false)` in certain authorization rules; **fail closed** with `defaultIfEmpty(false)` when a resource is absent.
- DB queries are genuinely reactive, with timeouts and safe logging; never call `block()`.
- Permissions changing during processing: consider database constraints or optimistic locking.

### 10.2. Annotations on interfaces and methods

Spring supports reading method security annotations on methods, classes, or interfaces in scenarios compatible with Spring AOP. When multiple interfaces/annotations carry conflicting rules, Spring Security 6.x has mechanisms to detect ambiguous configurations. Good practice is to place consistent policies on the service contract or implementation and test inheritance/overrides, avoiding conflicting copies of expressions.

### 10.3. @PreAuthorize on non-HTTP events

A message consumer or scheduled task does not inherently carry an HTTP request's security context; when calling a protected service, there must be a mechanism attaching a **system-trusted** `Authentication` to the subscriber, or separating system-task processing under a clear service-account policy. Do not remove annotations just because a background task gets denied. In particular, never construct `ROLE_ADMIN` from unverified external message headers or metadata.

### 10.4. Caches, sessions, and JWT permission changes

Method security reads the `Authentication`/authorities currently in the security context. If an admin revokes a user's role yet an existing JWT or session still carries it, rules may continue allowing access until the token/session is revalidated or revoked. For sensitive permissions, define appropriate TTLs, session invalidation, token introspection, or authoritative per-operation lookups.

### 10.5. Combining with tenant isolation

`hasRole('ADMIN')` does not inherently mean an admin can read every tenant. A sound policy might be "matching tenant + appropriate role", based on the **record's tenant in the DB** and the tenant bound to the Authentication. Avoid system-wide bypasses merely because a user holds an ADMIN role within one tenant.

## 11. Code review and testing checklist

Before approving a `@PreAuthorize` method, verify:

1. **Enable:** Did the application enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`?
2. **Proxy:** Is the method on a Spring bean called via its proxy, without self-invocation?
3. **Return type:** Does the method return `Mono`/`Flux` compatible with reactive security?
4. **Authentication:** Are identity/authorities read from the subscription's Reactor SecurityContext, not raw client headers?
5. **SpEL:** Are expression syntax, role prefixes, and parameter names (`#p0`/metadata) correct?
6. **Policy:** Does it require role, scope, ownership, tenant, resource state, or a combination?
7. **Source of truth:** If resource-based, are owner/tenant verified from the DB rather than self-declared arguments?
8. **No side effects on deny:** Do tests confirm denied calls execute zero DB writes, external calls, or business publishers?
9. **Reactive discipline:** No `block()` or manual `subscribe()` in filters/services/policies.
10. **Error semantics:** Direct service tests observe `AccessDeniedException`; HTTP tests observe proper 401/403 per the security chain.
11. **Method vs HTTP:** Are both URL policies and service policies present? Does `permitAll` on URLs leave method-level checks intact?
12. **AOP pitfalls:** No private/final/self-invoked methods, no manual `new` on protected objects?
13. **Time-of-check:** Do sensitive side effects have transactions, optimistic locks, or DB-level enforcement?
14. **Role changes:** Do session/token caches have suitable TTL/revocation if permissions must be revoked quickly?
15. **Data leakage:** Error bodies do not expose sensitive records/resource names; logs never contain credentials/tokens.
16. **Testing:** Do tests cover anonymous, missing role, valid role, matching/mismatched owner, cross-tenant, and missing record in DB-backed policy beans?

## 12. Self-assessment questions

**1.** How does `@PreAuthorize("hasRole('ADMIN')")` differ from `pathMatchers("/admin/**").hasRole("ADMIN")`?

**Answer:** The annotation protects **method invocation** via Spring AOP, whether the caller comes from a controller or another service through a proxy. The URL matcher protects HTTP requests matching paths in the chain. Both should be used.

**2.** What authority does `hasRole('ADMIN')` look for by default?

**Answer:** `ROLE_ADMIN`, unlike `hasAuthority('ADMIN')` which looks for the exact string.

**3.** Why does a method returning Mono/Flux matter?

**Answer:** Reactive method security integrates with the Reactor Context attached to the subscriber to obtain `Authentication`. Publishers also allow controlling execution upon subscription, cancellation, and reactive errors.

**4.** `reader` has valid Basic credentials but calls a secret method requiring ADMIN. What does the client typically receive?

**Answer:** `403 Forbidden` in a standard WebFlux HTTP chain; in direct service-call tests, a reactive `AccessDeniedException`.

**5.** If a controller/service calls `this.protectedMethod()` on the same bean, is the annotation guaranteed to run?

**Answer:** No. Self-invocation can bypass the Spring AOP proxy. Move the protected method to a separate Spring bean and invoke it through an injected proxy.

**6.** Is writing `@PreAuthorize("#p0 == authentication.name")` on an endpoint reading owner records sufficient for production?

**Answer:** Not yet. Client arguments can be self-declared. You must verify the record's true owner in the database and check tenant/roles against trusted sources.

**7.** If a method already wrote to the database and then `@PostAuthorize` denies it, does that undo the write?

**Answer:** Not automatically. `@PostAuthorize` denying the return value does not guarantee rolling back side effects. For write operations, use pre-checks + transaction/DB enforcement.

**8.** Why is testing denied calls with a counter inside `Mono.defer(...)` meaningful?

**Answer:** It proves authorization prevented the business publisher from executing; status 403 alone does not prove zero side effects occurred.

**9.** Can SpEL call a bean returning `Mono<Boolean>`?

**Answer:** Yes, in the reactive `AuthorizationManager` mechanism documented in Spring Security 6.5; the policy must treat missing data as deny and remain non-blocking.

**10.** A JWT still carries the old ADMIN role even though the user was demoted. Does `@PreAuthorize` automatically query the database to know immediately?

**Answer:** Not by default. The expression reads the current Authentication; you need a revocation/revalidation strategy or an authoritative policy lookup per business requirement.

## Official Documentation

- Spring Security 6.5 — Enable Reactive Method Security (`@EnableReactiveMethodSecurity`, `@PreAuthorize`, `Mono<Boolean>`): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Testing Reactive Method Security (`@WithMockUser` + `StepVerifier`): https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html
- Spring Security 6.5 — Testing Reactive Authentication with WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — PreAuthorize annotation: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.5.16 release note / end of 3.5 OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
