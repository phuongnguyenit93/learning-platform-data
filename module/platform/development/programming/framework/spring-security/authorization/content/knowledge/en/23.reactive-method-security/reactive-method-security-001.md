# Enabling @EnableReactiveMethodSecurity by Spring Security Version

## 1. The Problem: HTTP Is Protected, Yet Methods Can Still Be Unprotected

A WebFlux application has a `SecurityWebFilterChain`, configures an OAuth2 Resource Server or HTTP Basic, and has an endpoint requiring authentication. A developer puts `@PreAuthorize("hasAuthority('DOC_READ')")` on a service method, yet a user without `DOC_READ` can still read the document. The cause can be very simple: **reactive method security has not been enabled**, the wrong Servlet annotation was used by mistake, or the service was called without going through a Spring AOP proxy.

Spring Security separates two boundaries:

- **Reactive HTTP security**: `@EnableWebFluxSecurity` / auto-configuration, `ServerHttpSecurity.authorizeExchange`, and `SecurityWebFilterChain` decide who can invoke a URL.
- **Reactive method security**: `@EnableReactiveMethodSecurity` registers interceptors for `@PreAuthorize`, `@PostAuthorize`, and method-level policies on Spring-managed beans.

Enabling the HTTP layer **does not prove** that the method layer is enabled; the Spring Boot Security starter does not automatically activate all method security annotations. Conversely, enabling method security does not mean every HTTP path is configured against unauthorized access. You need both and must test each boundary separately.

Goals of this chapter:

1. Identify how to enable `@EnableReactiveMethodSecurity` across Spring Security 5.0–5.7, 5.8, 6.x, and 7.x.
2. Understand `useAuthorizationManager` and why **its default value changed in 6.0**.
3. Write proper WebFlux configuration, with services returning `Mono`/`Flux` and executing through a Spring AOP proxy.
4. Distinguish `@EnableReactiveMethodSecurity` from `@EnableMethodSecurity` and `@EnableWebFluxSecurity`.
5. Write `StepVerifier`/`WebTestClient` tests that prove authorization checks actually run, including when authorities are missing.
6. Diagnose wrong versions, dependencies, Reactor Context, self-invocation, test mocks, blocking calls, and unsuitable method signatures.

## 2. Reactive Method Security Architecture

```text
Client
  |
  v
WebFlux HTTP SecurityWebFilterChain
  |  Authentication + HTTP authorization
  v
@Controller / @RestController
  |
  v
Spring AOP proxy for service bean
  |
  +-- @PreAuthorize / custom reactive authorization interceptor
  |       |
  |       v
  |    Reactor Context -> Authentication
  |       |
  |       +--> DENY: AccessDeniedException (does not proceed)
  |       |
  |       +--> GRANT: subscribe/continue Publisher
  |
  v
@Service method -> Mono<T> / Flux<T>
  |
  +-- (if present) @PostAuthorize / @PostFilter
  v
Reactive repository / response
```

Reactive Spring Security reads the security context from the **Reactor Context**, via `ReactiveSecurityContextHolder`. A method security expression can use `authentication`, `principal`, `hasRole(...)`, `hasAuthority(...)`, or properly exposed policy beans.

Important notes:

- `ReactiveSecurityContextHolder` does not simply read the current ThreadLocal. A reactive chain can switch threads, so you cannot rely on servlet-style `SecurityContextHolder.getContext()`.
- The Spring AOP proxy must actually be invoked. If a controller manually calls `new SomeService()` or a method in the same bean calls `this.protectedMethod()`, the interceptor may not be applied.
- Methods protected by reactive annotations should have a return type implementing `org.reactivestreams.Publisher`, commonly `Mono<T>` or `Flux<T>`. Kotlin coroutines are supported on the corresponding AuthorizationManager branch.
- A service returning `Mono` that calls `block()` to fetch data before the guard can break the non-blocking design; keep policies and repositories inside the reactive pipeline.
- Method-level authorization only protects methods that are actually matched and invoked through the proxy; it does not automatically add `tenant_id` to SQL queries.

## 3. Version Matrix: The Most Important Differences

| Spring Security | How to enable reactive method security | Default `useAuthorizationManager` | Recommendation |
| --- | --- | --- | --- |
| 5.0–5.7 | `@EnableReactiveMethodSecurity` | Does not have this new attribute yet | Uses legacy infrastructure; consult the exact minor version docs |
| **5.8.x** | `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` | **false** | Explicitly enable the new engine when preparing to upgrade to 6.x |
| **6.0–6.5.x** | `@EnableReactiveMethodSecurity` | **true** | No need to specify `useAuthorizationManager = true` |
| **7.0.x** | `@EnableReactiveMethodSecurity` | **true** | Attribute still exists per 7.0 JavaDoc; verify the specific API when upgrading |
| 7.1+ | Check the JavaDoc for the version pinned in the build | Do not rely on 5.8 tips | Prefer the default AuthorizationManager configuration if JavaDoc confirms it |

**Basis:** Spring Security 5.8.16 JavaDoc states that `useAuthorizationManager` defaults to `false`. The 6.5.11 and 7.0.8 JavaDocs state that it defaults to `true`. The 6.0 reactive migration guide notes that `useAuthorizationManager = true` can be removed when upgrading from 5.8 to 6.0.

Do not infer the Spring Security version solely from the Spring Boot or JDK name. Inspect the project's actual dependency tree/BOM. Spring Boot 2.x typically pairs with Security 5.x, Boot 3.x with Security 6.x, and Boot 4.x with Security 7.x; if a project overrides versions, compatibility must be verified.

### Quick Selection Rules

- **On 5.8 and want the new AuthorizationManager**: explicitly write `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`.
- **On 6.x**: use `@EnableReactiveMethodSecurity`; `true` is the default.
- **On 7.x with verified JavaDoc**: use `@EnableReactiveMethodSecurity` according to that version; avoid keeping the legacy `false` configuration unless there is a documented reason and matching dependencies.
- **On 5.7 or earlier**: do not copy the `useAuthorizationManager` syntax because it may fail to compile; upgrade to 5.8 first if following the infrastructure migration path.

If a project uses Security 5.8 and only places `@EnableReactiveMethodSecurity`, the annotation still enables method security **in the default legacy mode**, rather than "disabling method security". Distinguish **whether method security is enabled** from **which engine executes it**.

## 4. Why Does Spring Security 5.8 Have Two Mechanisms?

In 5.8, the Spring Security team prepared to replace the method authorization engine. The legacy path relied more heavily on metadata sources, config attributes, and AccessDecisionManager/voters. The new mechanism uses `ReactiveAuthorizationManager`, interceptors, and Spring AOP.

```java
// Spring Security 5.8: explicitly enable the new engine.
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

Benefits of the AuthorizationManager branch noted in the official documentation:

- A cleaner `AuthorizationManager`/`ReactiveAuthorizationManager` API for composition and customization.
- Supports reactive values in expressions when using the proper contract, including beans returning `Mono<Boolean>`.
- Uses standard Spring AOP components instead of multiple legacy abstractions.
- Performs annotation conflict checks and provides corresponding framework standard support.
- Smooths the upgrade path to 6.x when the default flips to `true`.

### Default 5.8 Configuration Without the Flag

```java
// Spring Security 5.8: enable legacy reactive method security.
@Configuration
@EnableReactiveMethodSecurity
class LegacyReactiveMethodSecurityConfig {
}
```

It can still enforce `@PreAuthorize` on reactive beans, but specific extension points and behaviors do not necessarily match the AuthorizationManager branch. Do not treat "a test with @PreAuthorize passes" as proof that the new engine is active; check the annotation parameter and/or infrastructure beans.

### When Upgrading from 5.8 to 6.x

```diff
- @EnableReactiveMethodSecurity(useAuthorizationManager = true)
+ @EnableReactiveMethodSecurity
```

The diff above is **a configuration cleanup step**, not a mandatory requirement for the code to run. In 6.x, specifying `true` remains valid as long as the attribute exists, but it is unnecessary. More importantly, run method security regression tests after changing defaults.

## 5. Spring Security 6.x Configuration (and Corresponding 7.x)

Minimal template:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Java allows breaking an import line **after a dot** if syntactically valid, though to avoid copy-paste errors you can keep it on one line:

```java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

Place the annotation on a class included in the Spring application context: a `@Configuration` class picked up by component scan or `@Import`. Placing it on a class in an unscanned package may **activate nothing**.

You do not need to place `@EnableReactiveMethodSecurity` on each `@Service`. It is a global configuration annotation that registers the interceptors.

### Do Not Confuse with @EnableMethodSecurity

```java
// Servlet/synchronous method security; does not replace reactive setup.
@EnableMethodSecurity

// Reactive method security, with Reactor Context.
@EnableReactiveMethodSecurity

// HTTP WebFlux security configuration; does not automatically enable method-level security.
@EnableWebFluxSecurity
```

`@EnableMethodSecurity` is for standard synchronous method authorization, whereas `@EnableReactiveMethodSecurity` is for reactive services. In a pure WebFlux application, prefer the reactive annotation when protecting services returning `Mono`/`Flux`.

### Do Not Guess Attributes

The 6.5/7.0 JavaDoc for `@EnableReactiveMethodSecurity` includes `proxyTargetClass`, `mode`, `order`, and `useAuthorizationManager`. Do not blindly copy attributes like `prePostEnabled`, `securedEnabled`, or `jsr250Enabled` from `@EnableMethodSecurity`, as they belong to a **different annotation** and are not shared default attributes.

Example that **does not compile** (counterexample):

```java
// WRONG: @EnableReactiveMethodSecurity does not have prePostEnabled as above.
@EnableReactiveMethodSecurity(prePostEnabled = true)
```

Verify the annotation signature for your exact version via your IDE or JavaDoc rather than relying on a servlet example.

## 6. Distinguishing HTTP Security and Reactive Method Security

WebFlux HTTP:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveHttpSecurityConfig {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This is an **integration snippet**; it requires imports for `Bean`, `Configuration`, `EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `Customizer`. It only requires authentication for `/api/**`; it **does not** require DOC_READ at the HTTP layer.

Service:

```java
@Service
class DocumentService {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> readDocument(long id) {
        return Mono.just("document " + id);
    }
}
```

When `@EnableReactiveMethodSecurity` is enabled, an authenticated user lacking `DOC_READ` must be blocked at the **service layer**. This is a clear test that the method annotation is active.

If the HTTP layer already uses `.pathMatchers("/api/**").hasAuthority("DOC_READ")`, then an unauthorized test only proves the HTTP guard works; it **does not prove method security is enabled**. Include at least one test where the HTTP layer allows an authenticated user through, and the method layer denies them.

## 7. Dependencies and Spring Boot Compatibility

A real application needs:

- Spring Boot WebFlux starter for the non-blocking HTTP server.
- Spring Security starter/core/config/web for authentication and authorization.
- Reactor and Spring AOP infrastructure; method security interception operates via a Spring-managed proxy.
- Starter test and reactor-test for testing with `WebTestClient` and `StepVerifier`.
- If using a JWT Resource Server: `spring-boot-starter-oauth2-resource-server` and reliable issuer/audience configuration.

The Spring Boot BOM should manage Spring Security, Reactor, and Spring Framework together as a compatible set of versions. Do not force `spring-security-config` 7.x into Spring Boot 3.x using Framework 6.x, or mix Reactor major versions without verification.

### Maven Dependency Tree

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework:spring-aop
mvn dependency:tree -Dincludes=io.projectreactor
```

Verify the actual resolution output before choosing how to enable features. For Gradle projects, run `./gradlew dependencies --configuration runtimeClasspath` or `dependencyInsight` for the specific module.

### Spring Boot 3.x and 4.x

Spring Boot 3.x/Spring Security 6.x and Boot 4.x/Spring Security 7.x both require modern Java; the Boot 4.0 migration guide specifies Java 17 or newer and Spring Framework 7.x. This chapter uses **Java 17** for the Boot 3.5.x example because it is straightforward to learn and test. For Boot 4.x, use the dependency management and plugin versions provided by the corresponding Boot 4 BOM; do not assume a Boot 3.5 pom works as a Boot 4 pom.

### Do Not Try to "Fix" Issues by Adding Both Annotations

```java
// Avoid registering both method security styles for the same logic without a
// clear design; this can cause duplicate or unpredictable interceptors.
@EnableMethodSecurity
@EnableReactiveMethodSecurity
```

In a mixed application that has both synchronous and reactive services, explicitly design which interceptors guard each group, their ordering, and corresponding tests; do not add both just to make a random test stop returning 403.

## 8. Runnable Example: Spring Boot WebFlux + Reactive Method Security Application

The project below illustrates an easily verifiable scenario:

- The HTTP filter chain requires **authenticated only** for `/api/**`.
- Method `DocumentService.read` requires the **exact authority DOC_READ**.
- Method `DocumentService.audit` requires `ROLE_ADMIN` via `hasRole('ADMIN')`.
- User `reader` can read documents but cannot view audit.
- User `viewer` can log in but gets method-level denied when reading.
- User `admin` can view audit but **does not automatically have DOC_READ**.
- Requests without credentials receive 401 at the HTTP layer.

The project uses Spring Boot **3.5.16**, Java 17, and Spring Security managed by the BOM. This version is a **pinned example of the 3.5 line**; for real projects, use an actively supported maintenance version and update consistently.

```text
reactive-method-security-lab/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/
    │   ├── ReactiveMethodSecurityLab.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/demo/reactive/
        └── ReactiveMethodSecurityLabTest.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-method-security-lab</artifactId>
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
</project>
```

No Servlet MVC starter is needed in this project. Do not hardcode a separate Spring Security 6.x version in the pom because the Boot parent already provides compatible dependency management.

### 8.2. ReactiveMethodSecurityLab.java

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityLab {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveMethodSecurityLab.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchange -> exchange
                    .pathMatchers(HttpMethod.GET, "/api/**").authenticated()
                    .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}pass")
                .authorities("DOC_READ")
                .build();

        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}pass")
                .roles("VIEWER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}pass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, viewer, admin);
    }
}
```

**Explanation:**

- `@SpringBootApplication` is also a Spring configuration class; `@EnableReactiveMethodSecurity` here registers method security for beans scanned in package `demo.reactive`.
- `@EnableWebFluxSecurity` explicitly enables WebFlux security; `@EnableReactiveMethodSecurity` enables method annotations.
- The filter chain only requires authenticated access for GET `/api/**`, so a 403 test for `viewer` proves the service layer enforced it.
- `{noop}pass` is strictly for demo/testing; production must hash passwords securely and configure real users/IdP.
- `.anyExchange().denyAll()` avoids accidentally leaving remaining HTTP routes open.
- `hasAuthority('DOC_READ')` matches `DOC_READ` exactly; `roles("ADMIN")` creates the `ROLE_ADMIN` authority so `hasRole('ADMIN')` succeeds.

### 8.3. DocumentService.java

```java
package demo.reactive;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<DocumentView> read(String id) {
        return Mono.just(new DocumentView(id, "Document " + id));
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> audit() {
        return Mono.just("audit-ready");
    }

    public record DocumentView(String id, String title) {
    }
}
```

`Mono` is the publisher that WebFlux will subscribe to. In a real application, this logic typically uses `Mono.defer` or a reactive repository, possibly with access checks by document ID, tenant, and ownership. `@PreAuthorize("hasAuthority('DOC_READ')")` only checks a **functional authority**; it does not automatically check permissions per ID.

### 8.4. DocumentController.java

```java
package demo.reactive;

import demo.reactive.DocumentService.DocumentView;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/documents/{id}")
    public Mono<DocumentView> document(@PathVariable String id) {
        return service.read(id);
    }

    @GetMapping("/audit")
    public Mono<String> audit() {
        return service.audit();
    }
}
```

The controller receives the **Spring-managed bean** via constructor injection. Do not instantiate `new DocumentService()` because doing so bypasses the proxy. `@PathVariable` here only passes an ID for demonstration; production code must validate it and constrain queries by tenant/resource.

### 8.5. ReactiveMethodSecurityLabTest.java

```java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveMethodSecurityLabTest {

    @Autowired
    WebTestClient web;

    @Test
    void readerWithDocReadCanReadDocument() {
        web.get()
            .uri("/api/documents/42")
            .headers(headers -> headers.setBasicAuth("reader", "pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.title").isEqualTo("Document 42");
    }

    @Test
    void viewerIsAuthenticatedButMethodDeniesDocRead() {
        web.get()
            .uri("/api/documents/42")
            .headers(headers -> headers.setBasicAuth("viewer", "pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousRequestIsRejectedAtHttpBoundary() {
        web.get()
            .uri("/api/documents/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void adminRoleCanCallAuditMethod() {
        web.get()
            .uri("/api/audit")
            .headers(headers -> headers.setBasicAuth("admin", "pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("audit-ready");
    }

    @Test
    void readerCannotCallAdminAuditMethod() {
        web.get()
            .uri("/api/audit")
            .headers(headers -> headers.setBasicAuth("reader", "pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleDoesNotImplicitlyHaveDocReadAuthority() {
        web.get()
            .uri("/api/documents/42")
            .headers(headers -> headers.setBasicAuth("admin", "pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Meaning of each test case:**

- `readerCanRead`: the configuration works for a matching authority.
- `viewerIsAuthenticatedButMethodDeniesDocRead`: HTTP only requires authentication, so 403 proves the method-level check.
- `anonymousRequestIsRejectedAtHttpBoundary`: the HTTP filter requires authentication.
- `adminRoleCanCallAuditMethod`: `hasRole('ADMIN')` matches `ROLE_ADMIN`.
- `readerCannotCallAdminAuditMethod`: roles and authorities are not conflated.
- `adminRoleDoesNotImplicitlyHaveDocReadAuthority`: the admin role does not automatically bypass `hasAuthority('DOC_READ')` unless an explicit role hierarchy or additional policy exists.

These are **six integration tests**. Run them to verify both proxy registration and actual Reactor Context propagation. If you remove `@EnableReactiveMethodSecurity` and re-run, the method-layer 403 tests should fail—that is a useful negative control, not something to perform on a production system.

### 8.6. Running the Project

```bash
mvn clean test
mvn spring-boot:run
```

Once the server is running on `localhost:8080`, test:

```bash
curl -i -u reader:pass http://localhost:8080/api/documents/42
curl -i -u viewer:pass http://localhost:8080/api/documents/42
curl -i -u admin:pass  http://localhost:8080/api/audit
curl -i http://localhost:8080/api/documents/42
```

Expected results:

| Request | HTTP | Notable output |
| --- | --- | --- |
| reader GET document | 200 | JSON `{"id":"42","title":"Document 42"}` |
| viewer GET document | 403 | Does not return document JSON |
| admin GET audit | 200 | Body `audit-ready` |
| anonymous GET document | 401 | No document returned |

With `curl`, actual headers/body and error responses depend on the Spring Boot/Spring Security version, so exact header bytes are not guaranteed. The code above is designed for Java 17, though **Maven tests were not executed while writing this guide**; if your project environment uses different dependency artifacts/versions, use compatible versions and run the tests.

## 9. Directly Testing Reactor Context with StepVerifier

The official documentation explains that `ReactiveSecurityContextHolder` operates on the Reactor Context. In WebFlux, Spring Security populates the context from the request's authentication; in a unit test without HTTP, you must provide it explicitly.

```java
Authentication auth = new TestingAuthenticationToken(
        "alice", "n/a", "DOC_READ");

Mono<String> currentUser = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

StepVerifier.create(currentUser
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth)))
        .expectNext("alice")
        .verifyComplete();
```

This is a **unit test snippet**; it requires imports for `Authentication`, `TestingAuthenticationToken`, `ReactiveSecurityContextHolder`, `SecurityContext`, `Mono`, and `StepVerifier`. It verifies carrying `Authentication` within a reactive subscription, **not that @PreAuthorize is enabled**. Test real method security by injecting the protected service bean and subscribing with users that do and do not have permission.

Example:

```java
Mono<DocumentService.DocumentView> actual = service.read("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(actual)
        .expectNextMatches(view -> view.id().equals("42"))
        .verifyComplete();
```

`service` in this snippet must be a **Spring-managed proxied bean** and the configuration must have `@EnableReactiveMethodSecurity`. If you simply call `new DocumentService()`, this test may allow a user without the authority without proving a framework bug—because the proxy was bypassed.

### Testing DENY

```java
Authentication viewer = new TestingAuthenticationToken(
        "viewer", "n/a", "ROLE_VIEWER");

StepVerifier.create(service.read("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer)))
        .expectErrorMatches(error ->
            error instanceof AccessDeniedException)
        .verify();
```

This is also an **integration test snippet**; it requires importing `AccessDeniedException` and a proxied service bean. Newer Spring Security branches may use a specific subtype of `AccessDeniedException`; check the exception hierarchy for your version.

## 10. @PreAuthorize and Synchronous/Reactive Expressions

Simple example:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<Document> read(String id) {
    return documentRepository.findById(id);
}
```

The expression returns a boolean without blocking. With AuthorizationManager-based reactive method security, the Spring docs also show a policy bean returning `Mono<Boolean>`, for example:

```java
@Component("docPolicy")
class DocPolicy {

    Mono<Boolean> canRead(String id) {
        return externalPolicyClient.checkRead(id)
                .defaultIfEmpty(false)
                .onErrorReturn(false);
    }
}
```

And:

```java
@PreAuthorize("@docPolicy.canRead(#id)")
public Mono<Document> read(String id) {
    return documentRepository.findById(id);
}
```

Both snippets are **integration snippets**; `externalPolicyClient`/`Document`/repository must be provided by the app, and the policy needs verified subject/tenant/action/resource inputs so decisions are not made solely from a client-supplied ID. Returning `Mono<Boolean>` from a policy bean fits the AuthorizationManager mechanism in the documented versions; legacy 5.7 may require a different approach.

### Do Not Call block() Inside SpEL Policies

```java
// WRONG: can block the event loop and break the reactive context.
@PreAuthorize("@docPolicy.canRead(#id).block()")
```

Keep the result reactive so the infrastructure handles it instead of synchronizing with `block()`. If the policy backend times out, a `Mono.empty()` or `Mono.error()` must not be treated as PERMIT; the policy adapter/PEP must fail closed and audit according to contract.

### Policy Beans Can Use Authentication

An expression can pass `authentication` to the bean method:

```java
@PreAuthorize("@docPolicy.canRead(authentication, #id)")
```

This is a better approach when access depends on subject/roles/tenant; the policy bean must check that the input is the framework-provided, verified `Authentication` rather than taking this information from a user-provided header.

## 11. @PostAuthorize, @PreFilter, and @PostFilter

The AuthorizationManager branch of reactive method security supports both before- and after-method authorization; the documentation describes these interceptors:

- `AuthorizationManagerBeforeReactiveMethodInterceptor.preAuthorize()`.
- `AuthorizationManagerAfterReactiveMethodInterceptor.postAuthorize()`.
- `PreFilterAuthorizationReactiveMethodInterceptor`.
- `PostFilterAuthorizationReactiveMethodInterceptor`.

Purpose:

| Annotation | Timing | Key considerations |
| --- | --- | --- |
| `@PreAuthorize` | Before the method is allowed to execute | Suitable for blocking calls based on authorities/parameters |
| `@PostAuthorize` | After method invocation/emitted value to evaluate | Data may already have been fetched; does not protect side effects already executed |
| `@PreFilter` | Filters input collections according to policy | Does not replace tenant policies at the repository layer |
| `@PostFilter` | Filters output elements according to policy | Does not fix SQL counts/pagination/aggregations |

Illustrative example:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public Mono<Document> loadIfOwner(String id) {
    return repository.findById(id);
}
```

This is an **integration snippet** requiring the proper model/mapper and compatible security configuration. For sensitive data, prefer queries with a tenant/owner predicate **before reading** rather than relying solely on `@PostAuthorize`, because the data fetch may already occur even if the emitted value is later rejected.

Do not randomly duplicate the same annotation on both a class and a method with conflicting rules; the AuthorizationManager mechanism may check for ambiguity. When combining annotations, test the required aggregate logic—typically all required guards must pass.

## 12. Spring AOP Proxy: When Annotations Are Enabled Yet Tests Still Do Not Deny

Common causes of bypass:

### Self-invocation

```java
@Service
class ArchiveService {

    public Mono<String> outer() {
        return inner(); // this.inner(): does not go through the proxy.
    }

    @PreAuthorize("hasAuthority('ARCHIVE')")
    public Mono<String> inner() {
        return Mono.just("archived");
    }
}
```

If a controller calls `outer()`, `inner()` is invoked **inside the same object**, so `@PreAuthorize` on `inner` may not be applied. Solution: move the protected method to a separate Spring bean and inject it, or enforce authorization directly at the proxied entry point; avoid patching around it by pulling proxies from the context everywhere.

### Instantiating Objects with new

```java
DocumentService service = new DocumentService();
service.read("42");
```

There is no interceptor on an instance you construct yourself. Use constructor dependency injection and invoke the bean.

### private/final and Proxy Mode

Spring AOP proxies do not intercept `private` methods as external method joinpoints. `final` classes or methods also restrict subclass proxying; when using JDK interface proxies, intercepted methods must be invoked through the proxied interface. `@EnableReactiveMethodSecurity(proxyTargetClass = true)` requests class-based proxies when `mode=PROXY`, but it **does not make private/final methods interceptable**.

The JavaDoc notes that changing `proxyTargetClass=true` can affect **all Spring-managed beans that require proxying**, not only security. Do not enable it blindly to fix an issue whose root cause is not understood.

### Advice Order and @Transactional

Method security, reactive transactions, and tracing/caching can be separate advices. `order` configures ordering according to the version's API, though exact defaults should be tested on real beans. If a transaction starts after authorization or authorization needs to read data inside a transaction, specify the requirement explicitly rather than inferring from annotation names.

## 13. Reactor Context, Coroutines, and Avoiding ThreadLocal in WebFlux

In servlet applications, `SecurityContextHolder` binds to a thread by default. In WebFlux:

```java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

The Reactor Context follows the **subscription**, not a single thread. If execution switches from the event loop to `Schedulers.boundedElastic()`, do not call `SecurityContextHolder.getContext()` expecting it to hold the caller's identity on the new thread.

### When Tenant Context Is Needed

Application-derived tenant scope must be resolved from a verified `Authentication` plus server-side membership before use:

```java
Mono<Document> read(String id) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth -> tenantPolicy.authorizedScope(auth))
            .flatMap(scope -> documentRepository
                    .findByIdAndTenant(id, scope.tenantId()));
}
```

This is an **integration snippet**; the beans and record must be provided by the app; it illustrates tenant authorization at the data layer rather than enabling method security itself. `@PreAuthorize` checks functional permissions, but it does not automatically add tenant conditions to queries.

### Kotlin Coroutines

Recent Spring Security documentation describes support for Kotlin `suspend` methods on the AuthorizationManager mechanism. Do not copy Kotlin `suspend fun` code into a Java 17 project, and do not assume legacy 5.7 provides the same support as 6.x. In Kotlin, Spring AOP requires proxy compatibility, and classes/methods generally must be open for proxying (via the `all-open` plugin or equivalent rules).

## 14. Reading Configuration Correctly in 7.x

Spring Security 7.x introduces additional API and dependency changes compared to 6.x. However, the `@EnableReactiveMethodSecurity` annotation still appears in the 7.0 JavaDoc, and `useAuthorizationManager` defaults to `true` per the 7.0.8 JavaDoc. Therefore, **do not claim this annotation was removed in 7.0**.

Primary template:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveSecurityConfiguration {
}
```

Migration cautions:

1. Read the JavaDoc for the **exact minor version** managed by the BOM, rather than relying on another snapshot.
2. Do not override Spring Security modules with different major versions in the same application.
3. Avoid using `useAuthorizationManager=false` to retain legacy infrastructure when the corresponding module/dependency is gone; newer branches may require `spring-security-access` or a separate migration path.
4. Check all custom extensions: `ReactiveAuthorizationManager`, interceptors, expression handlers, and event hooks may have different method signatures across major versions.
5. Run integration tests proving `@PreAuthorize` both denies and grants after upgrading.
6. With Boot 4.x, verify dependency/module splits against the migration guide, especially Spring Framework 7/Jakarta and the Java baseline.

### Why Do Docs Still Mention the 5.8 Syntax Sometimes?

Reference guides sometimes show `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` in sections recounting Spring Security 5.8 to explain the feature's history. That syntax may still be valid in 6.x/7.0, but it is **no longer necessary** once the default is `true`. Prefer the JavaDoc defaults and the reactive migration page when deciding whether to set the flag.

## 15. Extension Points When Customizing Authorization Logic

Most applications only need `@EnableReactiveMethodSecurity` with `@PreAuthorize`. If policies require per-document ABAC/ACL, you can:

1. Invoke a bean with a reactive method in SpEL that returns `Mono<Boolean>` and fails closed.
2. Create a custom `ReactiveAuthorizationManager<MethodInvocation>`.
3. Register a custom reactive method interceptor/pointcut with the infrastructure roles according to the version's API.
4. Configure an expression handler or role hierarchy using appropriate Spring beans.

Example of `@PreAuthorize` calling a bean:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public Mono<DocumentView> document(String docId) {
    return repository.findVisibleDocument(docId);
}
```

The policy bean must not simply return `true` based on a caller-supplied `docId`. It must verify tenant/resource ownership and call policy services with valid deadlines and failure handling.

### Avoid Duplicate Custom Interceptors

If you enable default reactive interceptors via the annotation while also exposing extra interceptors for the same pointcut without defining ordering, the same method may be checked multiple times with different semantics. Never "fix" a 403 error by bypassing a denying interceptor without understanding the rule. Test evaluation counts, before/after placement, and all sensitive actions.

### Synchronous Managers and Reactive Managers Are Different Contracts

For WebFlux, choose APIs that support reactive decisions rather than calling a blocking `AuthorizationManager<MethodInvocation>` and invoking `block()` on the event loop. Match the exact `MethodInvocation` generics and version signatures. Do not automatically convert a servlet example to reactive simply by wrapping with `Mono.just(...)` while ignoring the Context.

## 16. Diagnosing When Annotations Appear to Have No Effect

### Step 1. Verify the Version

Run:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Check `@EnableReactiveMethodSecurity` in the actual `spring-security-config` artifact. On 5.8, if you want AuthorizationManager, confirm the flag is `true`; on 6.x it defaults to `true`.

### Step 2. Verify Configuration Is Scanned

The class annotated with `@EnableReactiveMethodSecurity` must be loaded in the startup context. A file present in the repository in an unscanned package activates nothing. Check whether `@SpringBootApplication(scanBasePackages=...)` or `@Import` includes that class in the context.

### Step 3. Verify the Service Is Proxied

The annotated method belongs to a Spring bean, and the controller invokes that bean via constructor injection. If using `this.method()`, `private`/`final`, or `new`, re-check AOP proxying.

### Step 4. Verify the Proper Reactive Interface

The service returns `Mono`/`Flux`; the WebFlux subscriber executes with the Reactive SecurityContext. If a method returns a plain Java `String` instead of a `Publisher` in Java reactive method security, do not assume safe interception under the documented contract. For Kotlin coroutines, use a supported version and verify Kotlin AOP configuration.

### Step 5. Verify Roles and Authorities

`hasRole('ADMIN')` typically checks for `ROLE_ADMIN`. `hasAuthority('ADMIN')` checks for `ADMIN` literally. Do not configure `roles("ADMIN")`, test `hasAuthority('ADMIN')`, and conclude the annotation is broken.

### Step 6. Test an Authenticated User Without Permission

This test is more valuable than only testing an ADMIN user getting 200. When the HTTP filter only requires authentication, the method must return 403 if permission is missing. Do not let the HTTP layer also deny the same authority and lose the ability to tell which layer blocked the request.

### Step 7. Verify Context at Subscription Time

`Mono` is lazy. A caller can construct a `Publisher` in context A and subscribe to it in context B. Test with `StepVerifier` and `ReactiveSecurityContextHolder.withAuthentication(...)`; do not capture raw `Authentication` into static fields or global caches.

### Step 8. Verify Errors and HTTP Status Codes

Missing/invalid authentication usually yields 401; an authenticated user lacking permission usually yields 403. For policy backend errors, 503 may be chosen by contract while still failing closed. In direct method tests, you will typically observe `AccessDeniedException` rather than an HTTP status.

### Step 9. Verify Object Policies in the Repository

A 200 response—even with working method security—can still leak another tenant's document if `@PreAuthorize` only checks `DOC_READ`. Test resource isolation separately, for example via a `findByIdAndTenant` query.

## 17. Common Configuration Errors Table

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@PreAuthorize` does not deny | Forgot `@EnableReactiveMethodSecurity` | Negative integration test with `viewer` |
| Annotation present, not proxied | Class outside component scan, manual `new` instance | Inspect bean and call path |
| Proxy exists, internal method not blocked | Self-invocation via `this` | Extract into separate bean |
| `WebTestClient` test returns 403 despite wrong method annotation | HTTP guard denied first | Test authenticated `viewer` against authenticated-only HTTP route |
| 401 when expecting 403 | Authentication failed/missing | Basic/token headers, entry point |
| 403 when expecting 200 | Authority `DOC_READ` differs from role `ROLE_DOC_READ` | Print authorities and check contract |
| Spring Security 5.8 does not use new manager | Forgot `useAuthorizationManager=true` | Check 5.8 JavaDoc default |
| `prePostEnabled` fails to compile | Confused with `@EnableMethodSecurity` | Read 6.5 annotation JavaDoc |
| Missing `Authentication` in reactive check | Read from ThreadLocal or missing Context | Test Reactor `contextWrite` |
| `Mono<Boolean>` SpEL not handled properly | Legacy engine/different extension | Enable AuthorizationManager or change adapter |
| Runtime error upgrading to Boot 4 | Mixed Security/Framework major versions | Inspect BOM/dependency tree |
| Method returns non-Publisher | Violates Java reactive contract | Switch to `Mono`/`Flux` or separate synchronous bean |
| Remote policy timeout grants access | Fallback `onErrorReturn(true)` | Fail closed and fault injection |
| Valid 200 API leaks another tenant | Function-level guard only | Scope at repository/query |
| No details in HTTP error | Different filter/exception mapping | Integration test, controlled logs |

## 18. Migration Sequence: 5.8 → 6.x → 7.x

If currently on legacy 5.8:

1. Pin BOM/Security/Framework versions and run baseline tests.
2. Replace `@EnableReactiveMethodSecurity` with `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` on 5.8 to switch engines in a controlled manner.
3. Update custom method-security beans/SpEL/extensions for the AuthorizationManager API if needed.
4. Test grant/deny, absence of authentication, Reactor Context, context switching, and role prefixes.
5. Upgrade to 6.x using a compatible BOM; the annotation can be simplified to `@EnableReactiveMethodSecurity`.
6. Verify all services are still invoked through proxies and the HTTP chain protects properly.
7. When moving to 7.x/Boot 4.x, review the migration guide for APIs, dependencies, and the Java baseline; do not set `useAuthorizationManager=false` to revert to legacy without a clear contract.
8. Re-run integration tests (especially negative paths), performance/cancellation checks, and cross-tenant tests.

If already on 6.x and simply looking to enable reactive method security, you do not need all migration steps above. Adding `@EnableReactiveMethodSecurity` to a configuration class and adding a negative test is the shortest path.

### Maintain Compatibility Through Tests Instead of Guesswork

Documentation across versions may keep 5.8 examples for historical context. Never rely on a general guide page to infer artifact defaults. On every version bump, checking the JavaDoc and running tests under the actual dependency tree gives the accurate answer.

## 19. Comprehensive Test Design for Production

A strong test suite should cover:

| Case | Method / context | Expected |
| --- | --- | --- |
| User with DOC_READ | `@PreAuthorize("hasAuthority('DOC_READ')")` | PERMIT |
| Authenticated VIEWER user | Same method | DENY |
| Anonymous caller | Authenticated HTTP route | 401 |
| Admin role | `hasRole('ADMIN')` | PERMIT |
| DOC_READ authority only, no ROLE_ADMIN | Admin method | DENY |
| ROLE_ADMIN without DOC_READ | Read method | DENY |
| Caller via Spring bean directly | Inject service and `StepVerifier` | Interceptor takes effect |
| Caller creating `new Service()` | No Spring proxy | Test detects bypass |
| Internal self-invocation | `this.inner()` | Do not assume inner advice ran |
| Context switches across threads | Reactor `publishOn` | Identity still follows subscription |
| SpEL bean returns `Mono.empty()` | No decision | Do not permit |
| SpEL bean returns `Mono.error` | PDP failure | Do not permit |
| Different tenant | Query resource with tenant mismatch | No data leaked |
| Method returning `Flux` | Multiple items | Do not emit protected items on deny |
| Reactive after-check deny | `@PostAuthorize` | Do not return protected result |
| HTTP public match | `permitAll` | Only public endpoints allowed |
| Method security disabled | Negative control in test isolation | Viewer no longer blocked at method; test catches it |
| Version bump | Security 5.8/6.x/7.x individually | Same truth table with corresponding config |

In WebFlux integration tests, use `WebTestClient` rather than instantiating controllers with `new`. In unit/reactive pipeline tests, use `StepVerifier` and `contextWrite`. For JWT, mock authentication tests do not replace signature/issuer/audience verification tests.

**Important:** test method security by invoking methods **through the proxy**; if you mock the service or replace the real service with `@MockBean`, the service's `@PreAuthorize` may not execute.

## 20. Common Mistakes to Avoid

**1. Adding `@PreAuthorize` without `@EnableReactiveMethodSecurity`.** The annotation may have no effect if interceptors are not registered.

**2. Assuming `@EnableWebFluxSecurity` automatically enables method security.** It serves HTTP security.

**3. Using `@EnableMethodSecurity` instead of the reactive annotation.** The two method authorization paths target different execution models.

**4. Claiming 5.8 defaults `useAuthorizationManager=true`.** The 5.8 JavaDoc specifies **false**; 6.0 changed the default to `true`.

**5. Claiming 7.0 removed `@EnableReactiveMethodSecurity`.** The 7.0 JavaDoc still includes this annotation.

**6. Copying `prePostEnabled=true` to `@EnableReactiveMethodSecurity`.** It is not an attribute of the reactive annotation in the referenced JavaDocs.

**7. Reading 6.x docs while using 5.7 artifacts.** Syntax and extension points may not exist.

**8. Instantiating services with `new` or calling `this.protectedMethod()`.** Bypasses proxy-based interception.

**9. Expecting `private`/`final` methods to be protected by proxies.** AOP proxies have structural limits.

**10. Using thread-local `SecurityContextHolder` inside a reactive chain.** It may not represent the active subscriber.

**11. Calling `block()` inside SpEL policies or reactive services on the event loop.** Causes blocking and breaks the non-blocking model.

**12. Testing only with an ADMIN user.** Fails to catch inactive annotations or authority mismatches.

**13. Checking the same authority in the HTTP guard and treating 403 as proof of method security.** Test the method boundary separately.

**14. Using `hasAuthority("ADMIN")` when the user only has `ROLE_ADMIN`.** Authority names must match exactly.

**15. Relying on `@PostAuthorize` to prevent all DB data from being read.** It runs after invocation; scope queries beforehand.

**16. Returning `Mono`/`Flux` from an unscoped repository query.** Functional authorization does not automatically protect individual records.

**17. Treating a `Mono.empty()` policy result as PERMIT.** Absence of a decision is not a grant; fail closed.

**18. Trying to keep `useAuthorizationManager=false` across major upgrades when legacy dependencies are gone.** Check supported paths and do not mix modules.

**19. Placing `@EnableReactiveMethodSecurity` on an unscanned class.** Spring will not initialize the annotation.

**20. Skipping regression tests after upgrading Security/Boot.** Defaults, custom interceptors, and proxy semantics can change.

## 21. Pre-Deployment Activation Checklist

- [ ] Verified the actual Spring Security version using Maven/Gradle dependency reports.
- [ ] For 5.8, explicitly decided between legacy (default `false`) and AuthorizationManager (`true`).
- [ ] For 6.x/7.x per JavaDoc, confirmed `@EnableReactiveMethodSecurity` uses AuthorizationManager (`true` by default).
- [ ] Did not mistakenly apply `@EnableMethodSecurity` attributes to the reactive annotation.
- [ ] Configuration is Spring-scanned or imported into the right application context.
- [ ] Separate `SecurityWebFilterChain` exists for HTTP authentication and route matching.
- [ ] Services with `@PreAuthorize` are Spring beans invoked through proxies.
- [ ] Java reactive methods return `Mono`/`Flux`, avoiding blocking SpEL.
- [ ] `ReactiveSecurityContextHolder` handling properly follows Reactor subscriptions.
- [ ] Tested authenticated user lacking permission → 403 at method level.
- [ ] Tested anonymous user → 401 at HTTP layer.
- [ ] Tested `hasAuthority` and `hasRole` with the proper `ROLE_` prefix.
- [ ] Tested behavior when policy beans return empty/error/timeout—never fails open.
- [ ] Tested self-invocation/`final`/`private` cases if present in the architecture.
- [ ] Tested resource ID/tenant/owner isolation and query-level authorization separately.
- [ ] Re-tested HTTP/method integration after every BOM/Security major version upgrade.
- [ ] Did not grant an "ADMIN bypasses all policies by default" rule without an explicit contract.
- [ ] Audited denied decisions without logging credentials or secret tokens.

**Conclusion:** `@EnableReactiveMethodSecurity` is the activation step for method-level authorization in WebFlux applications. The key version distinction is that **5.8 has `useAuthorizationManager` defaulting to `false`**, while **6.x and the 7.0 JavaDoc default to `true`**. Enabling the annotation correctly is only the first step: ensure Spring-managed proxies are invoked, Reactor Context carries authentication, methods return reactive types, and negative integration tests genuinely block unauthorized users. HTTP security and method security complement each other and do not replace one another.

## Official References

- [Spring Security 5.8.16 — EnableReactiveMethodSecurity JavaDoc](https://docs.spring.io/spring-security/site/docs/5.8.16/api/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5.11 — EnableReactiveMethodSecurity JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 7.0.8 — EnableReactiveMethodSecurity JavaDoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 7.0 — Reactive Method Security](https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/method.html)
- [Spring Security — Reactive Migration Guide](https://docs.spring.io/spring-security/reference/6.5/migration/reactive.html)
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
