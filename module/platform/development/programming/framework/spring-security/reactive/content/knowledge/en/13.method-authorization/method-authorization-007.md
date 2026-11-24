# Using Beans Returning Mono<Boolean> for Authorization Conditions

> **Scope:** Method authorization in **Spring Security reactive / Spring WebFlux**, specifically invoking a **Spring bean containing asynchronous authorization logic returning `Mono<Boolean>`** from a `@PreAuthorize` expression. Examples follow **Spring Boot 3.x, Spring Security 6.x (AuthorizationManager-based), and Java 17+**. The goal is checking user permissions based on document ownership in a reactive repository without blocking threads with `block()` and without confusing `Mono.empty()` with an explicit denial.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Explain why `@PreAuthorize("hasRole('READER')")` is sometimes insufficient for checking **ownership**, tenants, or database-backed conditions.
2. Properly enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` for reactive Spring Security supporting `Mono<Boolean>` conditions.
3. Create a Spring bean `@Component("documentAccess")` with `canRead(Authentication, String)` returning `Mono<Boolean>` and reference it via `@PreAuthorize("@documentAccess.canRead(authentication, #p0)")`.
4. Integrate a reactive repository into the policy using `map` / `flatMap` / `defaultIfEmpty(false)`, never calling `block()` inside a WebFlux request.
5. Distinguish `Mono.just(true)`, `Mono.just(false)`, `Mono.empty()`, and `Mono.error(...)` signals regarding decisions and error handling.
6. Understand Spring AOP proxies, subscription timing, Reactor Context, and how HTTP authorization combines with method authorization.
7. Write unit tests using `StepVerifier` and integration tests using `WebTestClient` covering 200 / 401 / 403 scenarios.
8. Avoid mistakes involving self-invocation, SpEL roots, method parameters, repository errors, data leakage, and fail-closed behavior.

## 2. Why use a reactive authorization bean?

Imagine an API:

```http
GET /documents/doc-a
Authorization: Basic ...
```

HTTP security has verified the identity and knows the user holds the `READER` role. However, document `doc-a` belongs to **alice**. If **bob** also has `ROLE_READER`, a rule requiring only login/role will not stop Bob from reading Alice's document.

These scenarios require **data-driven permissions**:

- Users may only read documents they own; administrators may read any existing document.
- Staff may only view orders belonging to their assigned tenant.
- A money transfer is allowed only if the actor has permission on the source account.
- Only the assigned account can edit a task.
- Policy must query permissions from a reactive database or cache before deciding.

You can use a Java bean to express this policy cleanly, separated from controllers and services. If the data lookup returns `Mono<Document>`, the bean can return **`Mono<Boolean>`** without blocking a thread.

### 2.1 Comparison with other approaches

| Approach | When appropriate | Limitations |
| --- | --- | --- |
| `@PreAuthorize("hasRole('ADMIN')")` | Static conditions based on authorities | Insufficient for per-document ownership |
| `@PreAuthorize("#p0 == authentication.name")` | Direct comparison of argument to principal | Suitable only when owner is already a trusted parameter; does not query DB |
| `@PreAuthorize("@documentAccess.canRead(authentication, #p0)")` | Complex domain logic, reactive DB/cache, reusable | Requires reactive method security enabled properly and tested |
| `ServerHttpSecurity.authorizeExchange` | Blocks HTTP requests at the WebFilter layer | Usually lacks the resource/domain object to decide |
| Calling policy manually in service | Certain specialized workflows wanting a result rather than an exception | Easy to forget on other call paths without strict conventions |
| Custom `ReactiveAuthorizationManager` | Need detailed results, custom interceptors | More complex; unnecessary for standard cases |

**Lesson choice:** Retain HTTP-level authorization to require login, while placing `@PreAuthorize` on a **service bean** to enforce per-document permissions. Both protection layers complement rather than replace each other.

## 3. API version: what to verify before writing

For Spring Security 6.x examples, explicitly enable **AuthorizationManager**-based method security:

```java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
```

Spring Security 6.5 officially documents that `@PreAuthorize` expressions can reference a bean/function returning **`Boolean` or `Mono<Boolean>`** when using the reactive AuthorizationManager infrastructure. This allows a rule to await a decision publisher before executing the protected method.

Contract example:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
public Mono<String> readText(String documentId) {
    // ... document access logic
}
```

This is a **method snippet** (without class/bean), valid only when `documentAccess` is a Spring bean with a matching method and reactive method security is enabled. Complete runnable files are presented in section 5.

**Common confusion across doc generations:** Older `@EnableReactiveMethodSecurity` examples had synchronous Boolean expression limitations. To use **`Mono<Boolean>` in SpEL**, follow the `useAuthorizationManager = true` path on Spring Security 6.x and ensure protected methods return reactive publishers like `Mono<T>` / `Flux<T>`.

Do not substitute Servlet's `@EnableMethodSecurity` for `@EnableReactiveMethodSecurity`. Similar APIs may exist in Spring Security 7.x, yet this lesson stays consistent with the Spring Security 6.x baseline.

### 3.1 Bean, SpEL, and reactive publisher

In the annotation:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
```

the parts mean:

- `@PreAuthorize`: evaluated by Spring Security **before executing the protected method**.
- `@documentAccess`: references the bean named `documentAccess` in the Spring application context.
- `canRead(...)`: invokes the policy bean's method; returns `Mono<Boolean>`.
- `authentication`: the `Authentication` object placed in the security expression root from the method invocation's context.
- `#p0`: first parameter of the protected method (`documentId`); avoids depending on Java variable names when builds omit `-parameters`.
- `true`: policy grants access; `false`: policy denies access.
- `Mono.empty()`: means **abstain (no decision)** per current docs; should not be used to mean "document not found".
- `Mono.error(...)`: failure executing policy; not a grant decision.

**Do not call `subscribe()` manually and do not block with `block()`.** The reactive method security infrastructure subscribes to the decision publisher via its own lifecycle and propagates access-denied signals to callers when needed.

## 4. Security flow from HTTP to the authorization condition

```text
Client GET /documents/doc-a, alice's Basic credentials
       |
       v
SecurityWebFilterChain (WebFlux)
       |
       +-- Authentication manager verifies username/password
       |
       +-- authorizeExchange("/documents/**").authenticated()
       |
       v
DocumentController -> calls DocumentService.readText("doc-a")
                               |
                               v
                  Spring AOP method security proxy
                               |
                      @PreAuthorize expression
                               |
                      @documentAccess.canRead(
                          authentication, "doc-a")
                               |
                      DocumentRepository.findById
                               |
                         Mono<Document>
                               |
                        map owner/role
                               |
                      Mono<Boolean> decision
                       /              \
                  true               false
                   |                   |
                   v                   v
             Call service        Access denied
             readText()          (HTTP usually 403)
                   |
                   v
             Mono<String>
                   |
                   v
             HTTP 200 body
```

This flow shows **HTTP WebFilters** handling authentication and path rules, followed by **method security** protecting the service method via Spring AOP. If another controller, reactive/scheduled entrypoint, or another service invokes the same bean through its Spring proxy with a valid `SecurityContext`, method security still enforces the policy. This helps prevent "new HTTP route forgot to call the authorization check" bugs.

### 4.1 When is evaluation performed?

Reactor publishers are normally **lazy**: a `Mono` is constructed at assembly time, while most logic executes upon subscription. Reactive method security interacts with Reactor Context to obtain identity at subscription time. This is why protected methods must have a **reactive return type**.

For example, `Mono<Boolean>` from a repository does not run I/O until subscribed. Never turn async into sync just to satisfy `@PreAuthorize`:

```java
// Do not use in WebFlux:
boolean allowed = documentRepository.findById(id)
    .map(doc -> doc.owner().equals(username))
    .block(); // Can block the event loop or create a subscription with wrong context.
```

The lines above are an **error-illustration snippet**, not standalone code. Write policies returning `Mono<Boolean>` for Spring Security to consume rather than waiting with `block()`.

## 5. Sample Spring Boot 3 / Java 17+ project

Let's build a small API backed by immutable in-memory data accessed through a reactive `Mono` interface. The repository is kept intentionally simple; when replaced with Spring Data R2DBC or reactive MongoDB, the policy API does not need to become blocking.

Requirements: JDK 17+, a Spring Boot 3.x project with Spring Reactive Web and Spring Security.

In `build.gradle` of a project configured with the Spring Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use **`spring-boot-starter-webflux`** as the server. If `spring-boot-starter-web` (MVC) is also present, Spring Boot typically defaults to MVC/Servlet; having `Mono` on the classpath **is not enough** to prove requests use `SecurityWebFilterChain`.

Complete layout:

```text
src/
  main/java/com/example/reactivepolicy/
    ReactivePolicyApplication.java
    SecurityConfig.java
    DocumentRepository.java
    DocumentAccessPolicy.java
    DocumentService.java
    DocumentController.java
  test/java/com/example/reactivepolicy/
    DocumentAccessPolicyTest.java
    DocumentMethodSecurityTest.java
    DocumentHttpTest.java
```

`public` classes reside in **separate files matching their names** under package `com.example.reactivepolicy`. The example uses a demo repository and dummy passwords; **never use static users/secrets in production**.

### 5.1 ReactivePolicyApplication.java

`src/main/java/com/example/reactivepolicy/ReactivePolicyApplication.java`:

```java
package com.example.reactivepolicy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactivePolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactivePolicyApplication.class, args);
    }
}
```

### 5.2 SecurityConfig.java: HTTP and method security

`src/main/java/com/example/reactivepolicy/SecurityConfig.java`:

```java
package com.example.reactivepolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/documents/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-demo-password"))
            .roles("READER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-demo-password"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }
}
```

**Explanation:**

- `@EnableWebFluxSecurity` enables HTTP security in WebFlux; `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` enables reactive method security supporting decision publishers.
- `/documents/**.authenticated()` **requires only login**. Checking owner/ADMIN role per document is delegated to the service's policy bean.
- `.httpBasic(...)` handles authentication so a principal exists in Reactor Context. `.formLogin(...disable)` turns off form redirects in API tests. HTTP Basic requires **HTTPS** when sending real credentials; use plain HTTP on localhost only with dummy data.
- `User.roles("ADMIN")` adds authority `ROLE_ADMIN`. Demo usernames/passwords are one-way hashed with the encoder before being stored.
- `anyExchange().denyAll()` is a safe fallback. Do not replace it with `permitAll()` for convenience.

### 5.3 DocumentRepository.java: document ownership data

`src/main/java/com/example/reactivepolicy/DocumentRepository.java`:

```java
package com.example.reactivepolicy;

import java.util.Map;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentRepository {

    private final Map<String, DocumentRecord> records = Map.of(
        "doc-a", new DocumentRecord(
            "doc-a", "alice", "Alice private document"),
        "doc-b", new DocumentRecord(
            "doc-b", "bob", "Bob private document")
    );

    public Mono<DocumentRecord> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(records.get(id)));
    }
}

// Package-private record, in the same Java file as DocumentRepository.
record DocumentRecord(String id, String owner, String content) {}
```

**Why use `Mono.defer(...)`?** So lookups happen upon subscription, matching reactive repository semantics. For a small `Map`, `Map.get` itself is not blocking I/O. In production, swap in a reactive database client. Never wrap a blocking JDBC call in `Mono.just(jdbcCall())` and assume it is non-blocking.

`DocumentRecord` is a **package-private** record at the bottom of the file, avoiding a separate `DocumentRecord.java`. Because all example classes share the same package, `DocumentService` and `DocumentAccessPolicy` can call `owner()` / `content()`.

### 5.4 DocumentAccessPolicy.java: bean returning Mono<Boolean>

`src/main/java/com/example/reactivepolicy/DocumentAccessPolicy.java`:

```java
package com.example.reactivepolicy;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("documentAccess")
public class DocumentAccessPolicy {

    private final DocumentRepository repository;

    public DocumentAccessPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(Authentication authentication, String id) {
        // Reject null/anonymous identities at the policy layer.
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Mono.just(false);
        }

        return repository.findById(id)
            .map(document -> {
                boolean owner =
                    document.owner().equals(authentication.getName());

                boolean admin = authentication.getAuthorities().stream()
                    .anyMatch(authority ->
                        "ROLE_ADMIN".equals(authority.getAuthority()));

                return owner || admin;
            })
            // Document does not exist: return an explicit deny decision.
            .defaultIfEmpty(false);
    }
}
```

This is a **complete Spring bean**, not pseudocode. `canRead` returns **`Mono<Boolean>`**, not a synchronous `Boolean`.

Meaning of each part:

1. Checks null `Authentication`, `isAuthenticated`, and anonymous tokens before inspecting data. `AnonymousAuthenticationToken` may technically have `isAuthenticated() == true`, yet is still **not** a verified user identity.
2. `repository.findById(id)` returns `Mono<DocumentRecord>` as the async decision source.
3. `map(document -> ...)` combines two conditions: the caller is the **owner** or holds a trusted `ROLE_ADMIN`.
4. `defaultIfEmpty(false)` converts **document not found** into an explicit deny decision. Do not treat `Mono.empty()` as equivalent to `Mono.just(false)` in method security.
5. The code **neither subscribes manually nor blocks**, keeping it compatible with Reactive Method Security AOP and the WebFlux runtime.
6. `Authentication` must be issued by a manager/provider that verified credentials. Never build authenticated/role tokens from unverified query params, request bodies, or headers.

A production-ready policy must also verify **tenant, document status, version, sharing permissions, org hierarchy, or lock state**. Checking simple ownership merely illustrates combining data lookups with async decisions.

### 5.5 DocumentService.java: referencing the bean from @PreAuthorize

`src/main/java/com/example/reactivepolicy/DocumentService.java`:

```java
package com.example.reactivepolicy;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentAccess.canRead(authentication, #p0)")
    public Mono<String> readText(String id) {
        return repository.findById(id)
            .map(DocumentRecord::content)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found"
                )
            ));
    }
}
```

**Reading the annotation:**

- `@documentAccess` matches the bean name in `@Component("documentAccess")`.
- `authentication` in SpEL is the identity from the method-security evaluation context, **not a client-supplied parameter**.
- `#p0` is the first method parameter (`String id`), which works even if the build omits parameter names for reflection. To use `#id`, ensure parameter name discovery is properly configured/compiled.
- The policy returns `Mono<Boolean>`; `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` evaluates it **before permitting document content retrieval**.
- `readText` returns `Mono<String>` and resides on a `@Service` Spring bean. Controllers must invoke the bean via its Spring proxy; never instantiate `new DocumentService(...)` in the app expecting AOP to run.

**Why does the service still have `switchIfEmpty(404)`?** If data is deleted between the policy check and the service read, the service could see empty and return 404. In this example, when `id` is missing **already during the policy check**, `defaultIfEmpty(false)` denies first, typically resulting in 403 for logged-in callers. This is a demo choice that avoids disclosing document existence; real products must intentionally choose a 403/404 policy.

### 5.6 DocumentController.java: HTTP endpoint

`src/main/java/com/example/reactivepolicy/DocumentController.java`:

```java
package com.example.reactivepolicy;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping(
        value = "/documents/{id}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> getDocument(@PathVariable String id) {
        return documents.readText(id);
    }
}
```

Do **not rewrite** `if (doc.owner().equals(...))` in the controller. The controller calls the Spring-managed `DocumentService`; the method-security proxy enforces the same policy even if other controllers or functional routes call the service bean later.

Using `Mono<String>` end-to-end allows Spring Security to preserve the authenticated request's Reactor Context. Never call `block()`, `subscribe()`, `toFuture()`, or spawn manual threads to inspect username/roles in handlers.

## 6. Expected application behavior

| HTTP request | Credentials | Document | Bean decision | Expected outcome |
| --- | --- | --- | --- | --- |
| GET `/documents/doc-a` | None | Exists | HTTP chain blocks before policy | **401** with HTTP Basic |
| GET `/documents/doc-a` | alice, valid password | Owned by Alice | `Mono.just(true)` | **200**, body `Alice private document` |
| GET `/documents/doc-a` | bob, valid password | Owned by Alice | `Mono.just(false)` | **403 Forbidden** |
| GET `/documents/doc-b` | bob, valid password | Owned by Bob | `Mono.just(true)` | **200**, body `Bob private document` |
| GET `/documents/doc-b` | alice, valid password | Owned by Bob | `Mono.just(false)` | **403** |
| GET `/documents/doc-a` | admin, valid password | Exists | `Mono.just(true)` via `ROLE_ADMIN` | **200**, body `Alice private document` |
| GET `/documents/unknown` | admin, valid password | Missing | `defaultIfEmpty(false)` | **403** under demo policy |
| POST `/documents/doc-a` | alice, valid password | No POST route | Fallback HTTP rule/CSRF may block | Never infer permissions from GET |

Difference between 401 and 403:

- **401**: request is not validly authenticated in HTTP security, or lacks credentials matching the Basic challenge.
- **403**: user is authenticated, yet the **method policy** denies access, or CSRF/another HTTP policy rejects the request.
- **200**: both HTTP authentication/authorization and method authorization grant access, and the handler returns data successfully.

Because `DocumentAccessPolicy` returns a Boolean when a document exists rather than generating HTTP statuses itself, the **Spring Security method interceptor** translates denials into exceptions for WebFlux security infrastructure to handle.

## 7. Unit testing the bean with StepVerifier

The policy class is a standalone bean, so its business branches can be tested **without an HTTP server**. With `reactor-test` and `spring-boot-starter-test` in the project:

`src/test/java/com/example/reactivepolicy/DocumentAccessPolicyTest.java`:

```java
package com.example.reactivepolicy;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import reactor.test.StepVerifier;

class DocumentAccessPolicyTest {

    private DocumentAccessPolicy policy;

    @BeforeEach
    void setUp() {
        policy = new DocumentAccessPolicy(new DocumentRepository());
    }

    private Authentication user(String name, String role) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_" + role))
        );
    }

    @Test
    void ownerIsAllowed() {
        StepVerifier.create(policy.canRead(user("alice", "READER"), "doc-a"))
            .expectNext(true)
            .verifyComplete();
    }

    @Test
    void otherUserIsDeniedEvenWithSameRole() {
        StepVerifier.create(policy.canRead(user("bob", "READER"), "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void adminIsAllowedForExistingDocument() {
        StepVerifier.create(policy.canRead(user("admin", "ADMIN"), "doc-a"))
            .expectNext(true)
            .verifyComplete();
    }

    @Test
    void missingDocumentIsDeniedEvenForAdmin() {
        StepVerifier.create(policy.canRead(user("admin", "ADMIN"), "missing"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void missingAuthenticationIsDenied() {
        StepVerifier.create(policy.canRead(null, "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void unauthenticatedTokenIsDenied() {
        var request = UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", "not-verified"
        );
        StepVerifier.create(policy.canRead(request, "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void anonymousAuthenticationIsDenied() {
        var anonymous = new AnonymousAuthenticationToken(
            "test-key",
            "anonymousUser",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS"))
        );
        StepVerifier.create(policy.canRead(anonymous, "doc-a"))
            .expectNext(false)
            .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test --tests '*DocumentAccessPolicyTest'
```

Expected outcome is 7 passing tests. This is the **expected result of the lesson source code**, not a build execution result from this environment.

**Unit test security note:** `UsernamePasswordAuthenticationToken.authenticated(...)` constructs an object marked as authenticated **to simulate a valid login**. In production, never treat an object constructed directly from client input as proven credentials. Policy tests do not replace authentication/WebFilter tests.

### 7.1 Why not just assert with blocking code?

`StepVerifier` subscribes to the publisher, asserting both values and completion signals:

```java
StepVerifier.create(policy.canRead(user, "doc-a"))
    .expectNext(true)
    .verifyComplete();
```

This is a **method snippet in a test defining `user`**, not standalone code. It beats `policy.canRead(...).block()` in tests because it checks `onNext`/`onComplete` and extends cleanly to `onError` assertions. Never put `block()` on the WebFlux event loop; `StepVerifier` unit tests avoid breaking reactive pipelines.

## 8. Testing Spring AOP method security with Reactor Context

Unit testing the bean alone does not prove `@PreAuthorize` **is actually enforced by Spring Security**. Add a test invoking the **Spring-managed service bean** with an `Authentication` in Reactor Context.

`src/test/java/com/example/reactivepolicy/DocumentMethodSecurityTest.java`:

```java
package com.example.reactivepolicy;

import static org.assertj.core.api.Assertions.assertThat;

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
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService documents;

    private Authentication authentication(String name, String authority) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name,
            null,
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    @Test
    void methodProxyGrantsAccessToOwner() {
        Mono<String> result = documents.readText("doc-a")
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                authentication("alice", "ROLE_READER")
            ));

        StepVerifier.create(result)
            .expectNext("Alice private document")
            .verifyComplete();
    }

    @Test
    void methodProxyDeniesAccessToOtherOwner() {
        Mono<String> result = documents.readText("doc-a")
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                authentication("bob", "ROLE_READER")
            ));

        StepVerifier.create(result)
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void methodProxyGrantsAccessToAdmin() {
        Mono<String> result = documents.readText("doc-b")
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(
                authentication("admin", "ROLE_ADMIN")
            ));

        StepVerifier.create(result)
            .expectNext("Bob private document")
            .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test --tests '*DocumentMethodSecurityTest'
```

Important explanations:

- `@SpringBootTest` boots the context and AOP method-security interceptors. `documents` is an **injected bean**, not `new DocumentService(...)`.
- `ReactiveSecurityContextHolder.withAuthentication(...)` creates a **test context**, supplying a controlled mock Authentication.
- `contextWrite(...)` **downstream** of `documents.readText(...)` lets the upstream publisher and authorization logic read the reactive SecurityContext during subscription.
- Denied tests expect `AccessDeniedException` (or a subtype) raised by method security when `Mono<Boolean>` emits `false`.
- In production HTTP handling, Spring Security WebFlux populates Reactor Context from login/token verification; controllers **never inject authentication themselves** to bypass checks.

**AOP proxy note:** If a test simply runs `new DocumentService(new DocumentRepository()).readText(...)`, `@PreAuthorize` **is not applied by Spring AOP**. That is a critical test mistake. Never conclude method security is broken when you aren't calling through the Spring bean/proxy.

## 9. HTTP integration tests with WebTestClient

Verify authentication, HTTP rules, and the method policy bean together using an HTTP server started in tests.

`src/test/java/com/example/reactivepolicy/DocumentHttpTest.java`:

```java
package com.example.reactivepolicy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class DocumentHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void withoutCredentialReturns401() {
        client.get()
            .uri("/documents/doc-a")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadHerOwnDocument() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "alice", "alice-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Alice private document");
    }

    @Test
    void bobCannotReadAlicesDocument() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "bob", "bob-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void bobCanReadHisOwnDocument() {
        client.get()
            .uri("/documents/doc-b")
            .headers(h -> h.setBasicAuth(
                "bob", "bob-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Bob private document");
    }

    @Test
    void adminCanReadExistingDocument() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Alice private document");
    }

    @Test
    void unknownDocumentIsDeniedByPolicy() {
        client.get()
            .uri("/documents/not-found")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordDoesNotReachMethodPolicy() {
        client.get()
            .uri("/documents/doc-a")
            .headers(h -> h.setBasicAuth(
                "alice", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
./gradlew test --tests '*DocumentHttpTest'
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*DocumentHttpTest'
```

These are 7 HTTP tests showing **expected outcomes from the sample configuration**. They were not executed in the authoring environment. If a project adds a different authentication entry point, multiple `SecurityWebFilterChain` beans, custom method exception handling, or a different Spring Security version, verify HTTP statuses against the actual configuration.

**Differences across the 3 test layers:**

| Test | Verifies | Does not prove |
| --- | --- | --- |
| `DocumentAccessPolicyTest` | Standalone `Mono<Boolean>` bean logic | Whether AOP/SpEL executes |
| `DocumentMethodSecurityTest` | `@PreAuthorize` invoking bean via Spring proxy and Reactor Context | Whether HTTP authentication filters run |
| `DocumentHttpTest` | Integrated Basic auth, HTTP authorization, method security, and routing | Production security with real IdP/database/proxy |

These three layers complement each other; testing only mock principals is not enough to prove HTTP credentials are verified in practice.

## 10. Signal table: true, false, empty, and error

`Mono<Boolean>` can emit the following signals:

| Publisher | Meaning when used as an authorization expression | Should it be used in ownership policies? |
| --- | --- | --- |
| `Mono.just(true)` | Grants access per policy | Yes, once all conditions are verified |
| `Mono.just(false)` | Explicit denial | **Yes**, for insufficient permissions or missing resources under fail-closed policy |
| `Mono.empty()` | Emits no Boolean; per method security docs may be treated as **abstain** | **No** for "document not found" when default-deny is required |
| `Mono.error(exception)` | Policy execution failed or hit infrastructure error | Does not grant access; handle observable error, never turn into true |

If the repository returns empty for a non-existent document, e.g.:

```java
return repository.findById(id)
    .map(document -> document.owner().equals(authentication.getName()))
    .defaultIfEmpty(false);
```

`defaultIfEmpty(false)` turns **absence** into an explicit deny decision. Conversely, omitting `defaultIfEmpty(false)` lets the bean return `Mono.empty()`; that is not synonymous with Boolean `false`, so avoid relying on interceptor abstention handling when designing resource security.

### 10.1 Do not turn database errors into grants

**Dangerous mistake:**

```java
return repository.findById(id)
    .map(document -> document.owner().equals(authentication.getName()))
    .onErrorReturn(true);
```

This is a warning snippet **never to use**. If the DB loses connectivity, a policy like this could grant access to users **whose ownership was never verified**.

**Better:** Let errors propagate so the request returns no data, log and observe at the infrastructure layer; or map specific errors to denial **after** evaluating the impact of masking failures. Do not assume `onErrorReturn(false)` is always ideal either: it can hide outages that ought to return 5xx and trigger alerts. The non-negotiable rule is **never grant access when conditions cannot be verified**.

### 10.2 Do not combine Mono with SpEL boolean operators carelessly

Example **to avoid due to unclear/unsuitable semantics**:

```java
@PreAuthorize("hasRole('READER') and @documentAccess.canRead(authentication, #p0)")
```

`hasRole` returns a synchronous Boolean while the bean returns `Mono<Boolean>`. Do not assume SpEL will await a publisher **inside** an `and` operator like normal Java logic; boolean coercion may fail depending on expression handling and version. Keep the **reactive result as the final output of the expression** and combine conditions **inside the bean** using reactive operators.

For example, the bean can check roles first and then query the repository:

```java
public Mono<Boolean> canRead(Authentication auth, String id) {
    if (auth == null || !auth.isAuthenticated()) {
        return Mono.just(false);
    }

    boolean reader = auth.getAuthorities().stream()
        .anyMatch(a -> "ROLE_READER".equals(a.getAuthority()));
    boolean admin = auth.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    if (!reader && !admin) {
        return Mono.just(false);
    }

    return repository.findById(id)
        .map(doc -> admin || doc.owner().equals(auth.getName()))
        .defaultIfEmpty(false);
}
```

This is an **alternative method snippet inside `DocumentAccessPolicy`**, not a standalone class. It illustrates returning `Mono.just(false)` early for ineligible roles, then querying the DB reactively. Exact logic depends on policy: in the original demo config, the owner is permitted regardless of role, whereas this variant requires READER or ADMIN.

### 10.3 Can Mono<Boolean> check conditions involving I/O?

Yes. This is the exact sweet spot for reactive method security: `documentRepository.findById(id)` can be an async database call, or an authorization service call via `WebClient` returning a publisher. The requirement is being **genuinely non-blocking**, with proper timeouts/retries/circuit breakers and zero side effects inside the permission check.

If I/O is **blocking** (legacy JDBC), never write `Mono.just(blockingPermissionCheck())`; the blocking function runs **before** the Mono is created. Use reactive drivers/clients or isolate blocking onto an appropriate scheduler under controlled architecture.

## 11. Replacing the bean with Function<String, Mono<Boolean>>

Besides a `DocumentAccessPolicy` bean class, Spring Security 6.5 illustrates `@Bean Function<T, Mono<Boolean>>` invoked via `@functionName.apply(...)` in `@PreAuthorize`.

The separate configuration example below permits reading **documents owned by the principal**, using `ReactiveSecurityContextHolder` to obtain `Authentication` from Reactor Context:

```java
package com.example.reactivepolicy;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class FunctionPolicyExample {

    @Bean("ownsDocument")
    Function<String, Mono<Boolean>> ownsDocument(DocumentRepository repository) {
        return id -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth ->
                repository.findById(id)
                    .map(doc -> doc.owner().equals(auth.getName()))
            )
            .defaultIfEmpty(false);
    }
}
```

Then in a method on a Spring bean:

```java
@PreAuthorize("@ownsDocument.apply(#p0)")
public Mono<String> readOwnText(String id) {
    return repository.findById(id)
        .map(DocumentRecord::content);
}
```

This is a **method snippet**, placed inside a service with a `repository` field and importing `@PreAuthorize`. Both snippets are **illustrative alternatives**, unnecessary alongside the main `DocumentService.readText`. The function style offers a compact signature aligned with official docs; the difference is that `FunctionPolicyExample` reads security context itself instead of receiving `Authentication` from SpEL.

**When to choose which?**

- `@documentAccess.canRead(authentication, #p0)`: convenient for **plain Java unit tests** with a specific `Authentication`, easily passing principal and document ID.
- `@ownsDocument.apply(#p0)`: useful if the function actively uses `ReactiveSecurityContextHolder`, though unit tests must supply Reactor Context; missing authentication must fail closed.
- `@authz.decide(#root)`: variant using `MethodSecurityExpressionOperations` per Spring Security guides, keeping logic in a bean with access to the security expression root. Must import the right Spring Security types and avoid unintended request state dependencies.

Do not confuse `@documentAccess` with the `@Component` annotation. The `@` prefix inside SpEL **only references a Spring bean by name**; it does not turn an arbitrary class into a bean.

## 12. Spring AOP: why might annotations fail to execute?

One of the hardest bugs to spot is **self-invocation**: code inside a class calling `this.readText(id)` internally. When an internal call bypasses the Spring proxy, the interceptor guarding the method may be skipped. Example:

```java
@Service
public class RiskyService {

    public Mono<String> outer(String id) {
        return this.inner(id); // self-invocation: bypasses method security proxy
    }

    @PreAuthorize("@documentAccess.canRead(authentication, #p0)")
    public Mono<String> inner(String id) {
        return Mono.just("sensitive");
    }
}
```

**This is a risk-illustration class**, requiring imports for `Service`, `PreAuthorize`, and `Mono`. When `outer` is called via proxy, `outer` has no annotation; calling `this.inner(...)` can bypass `inner`'s interceptor. Never use this pattern to protect sensitive data.

**Fix:** Move the `@PreAuthorize` method to another `@Service` and inject that bean into the caller, or design interfaces/layers so every external data access goes through a **Spring-managed proxy**. Ensure methods are public, beans are component-scanned, never manually constructed with `new`, and do not rely on proxying private/final methods.

### 12.1 Reactive return type

With reactive Spring Security method authorization, use `Mono<T>` / `Flux<T>` or an appropriate Publisher on protected methods; the infrastructure needs Reactor Context during subscription.

Right example:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
public Mono<DocumentRecord> findById(String id) {
    return repository.findById(id);
}
```

This is a service method snippet. Never change it to:

```java
@PreAuthorize("@documentAccess.canRead(authentication, #p0)")
public DocumentRecord findById(String id) {
    return repository.findById(id).block();
}
```

The second pattern both blocks the thread and breaks the expected Publisher contract; it is **not** a safe way to apply reactive Spring Security.

### 12.2 Reactor Context differs from ThreadLocal

`ReactiveSecurityContextHolder` uses **Reactor Context** bound to the subscription, not Servlet-style `ThreadLocal` in `SecurityContextHolder`. Reactor operators like `map`, `flatMap`, and `publishOn` within the same reactive chain preserve context within scope. Conversely, manual `subscribe()`, detaching into arbitrary callbacks, or `CompletableFuture` without explicit context propagation can lose authentication.

In normal WebFlux HTTP requests, Spring Security creates/restores context for the request. In `StepVerifier` unit tests, we explicitly supply context with `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` to simulate an authenticated user.

## 13. Distinguishing pre-authorization and post-authorization

`@PreAuthorize` decides **before the method executes**: ideal when you can decide from parameters and permission lookups prior to reading/writing data.

`@PostAuthorize` evaluates after the method returns a result, useful if policy needs the returned object itself, yet in reactive streams you must understand exactly how the method-security interceptor handles publishers/results and supported versions. Data already computed/queried before the decision may have caused side effects or consumed resources; never assume "blocking the return afterward" rolls back side effects inside the method.

**In the document example, `@PreAuthorize` is better** because it can verify owner/role via the repository before allowing `readText`. For **write** operations, pre-checks alone may still suffer from race conditions (TOCTOU): permissions could change between check and update. Consider transactions, row-level security, conditional owner/tenant update statements, optimistic locking, or checking policy right at the write statement.

### 13.1 Do not put checks only on controllers and forget services

If a service reading sensitive data is invoked from REST controllers, GraphQL resolvers, message consumers, or batch jobs, using only HTTP route matchers leaves other call paths unprotected. Placing policy at the **service boundary** provides defense in depth. Still, non-HTTP workflows must be given a **trusted Authentication in context** if permitted to run tasks; never "impersonate admin" from arbitrary input.

## 14. Error handling, latency, and observability

### 14.1 Fail closed while distinguishing real errors

When the repository finds no document, the demo chooses `Mono.just(false)` via `defaultIfEmpty(false)` so policy denies access. When the repository **genuinely errors** (DB outage, timeout), propagate the error to be handled at an appropriate layer **without granting access**; never turn errors into `true` to "avoid disruption".

In production you may return HTTP 503 instead of 403 when permissions cannot be verified due to unavailable infrastructure, as long as **no data is returned**. Define system policy clearly: separate "user lacks permission" from "unable to evaluate permission", while ensuring neither **leaks sensitive resources**.

### 14.2 Timeouts, retries, and caching

When policy queries a DB or external policy service:

- Set bounded timeouts and instrument permission evaluation latency.
- Retry only transient recoverable errors with bounded attempts; never retry invalid authentication or denied decisions.
- Cache permission decisions keyed by **principal, tenant, resource ID, action, and policy version**; never cache a Boolean solely by document ID and reuse it for another user.
- Maintain an invalidation policy when owners, roles, or tenant memberships change.
- Never log passwords, tokens, secret details, or full document contents.
- For lists of documents, consider batch authorization instead of N lookups causing N+1 queries.

### 14.3 Avoid data leaks via status or timing

An unauthorized request to view a document can accidentally reveal document existence by distinguishing 403 vs. 404, or via response timing. The demo returns 403 for missing documents to keep fail-closed simple; this is an **intentional** choice, not a mandatory rule for all APIs. For real APIs, choose 404/403 responses consistent with privacy policy and threat model.

## 15. Common error table

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using Servlet `@EnableMethodSecurity` instead of reactive | Bean returning `Mono<Boolean>` is not handled as expected | Enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` in WebFlux |
| Using legacy reactive method security supporting only Boolean | SpEL returning publisher is misinterpreted | Use Spring Security 6.x AuthorizationManager infrastructure |
| `@PreAuthorize("@documentAccess.canRead(...)")` with different bean name | SpEL cannot find bean | Set `@Component("documentAccess")` or `@Bean("documentAccess")` |
| SpEL `#id` when build strips parameter names | `id` null / unresolved | Use `#p0` or configure parameter name discovery |
| Bean returns `Mono.empty()` when document missing | Abstain differs from explicit denial | `defaultIfEmpty(false)` |
| Policy calls `block()` | Blocks event loop, wrong context | Return `Mono<Boolean>` and use reactive operators |
| Calling `subscribe()` inside bean | Spring Security misses decision lifecycle | Return publisher for the framework to subscribe |
| Internal call via `this.method()` | Bypasses Spring AOP interceptor | Go through bean/proxy or extract service |
| Manual `new DocumentService(...)` | No Spring proxy | Inject bean via constructor |
| Using user/role from unverified query/header | Authentication bypass / privilege escalation | Use only provider-verified `Authentication` |
| `onErrorReturn(true)` in policy | DB failure becomes grant | Fail closed, propagate/handle errors safely |
| Testing bean directly and assuming annotations work | Skips AOP/SpEL | Add `@SpringBootTest` calling injected service |
| Testing only permitted users | Misses cross-owner leaks | Add negative tests for other users |
| HTTP layer `permitAll` with method security disabled | Controller may return data directly | Verify both HTTP policy and method security are active |
| Checking document ID without tenant ID | Cross-tenant access | Verify composite ownership/tenant on real data |
| Caching Boolean policy by resource ID only | Alice's result wrongly reused for Bob | Key cache by principal/tenant/action/policy version |
| Pre-check only before writing without rechecking | TOCTOU / race condition | Use conditional updates/transactions/DB constraints |
| Assuming Spring AOP proxy protects private/final/self-calls | Interceptor does not run | Design public service boundaries and test proxy |

## 16. Self-check exercises

**Question 1.** Why is `@PreAuthorize("hasRole('READER')")` insufficient to protect `GET /documents/{id}`?

**Answer:** A role only states the user holds general READER privileges; it does not prove they own the **specific document ID**. A policy bean querying reactive data can compare owner/tenant against the principal before granting access.

**Question 2.** Is `@documentAccess` in SpEL a Java annotation?

**Answer:** No. It is **Spring bean reference** syntax inside a SpEL expression. A Spring-managed bean named `documentAccess` must exist.

**Question 3.** If the repository returns `Mono.empty()` for a non-existent ID, what is the safe way to handle ownership checks?

**Answer:** `defaultIfEmpty(false)` to return **`Mono.just(false)`**. Do not rely on empty's abstain semantics for sensitive permission handling.

**Question 4.** Why is `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` explicitly highlighted?

**Answer:** AuthorizationManager-based reactive method security supports Boolean or `Mono<Boolean>` expression results; the legacy path had synchronous expression limitations. Enable and test compatibility with your project's Spring Security version.

**Question 5.** If `DocumentAccessPolicy.canRead` returns `Mono.just(false)`, will Spring Security still invoke `DocumentService.readText`?

**Answer:** No, when method security works properly; before-method authorization denies with an exception. Authenticated HTTP callers typically receive 403.

**Question 6.** Is `this.readText("doc-a")` inside the same class guaranteed to pass through the method-security proxy?

**Answer:** No. Self-invocation can bypass the proxy. Invoke through a Spring-managed bean/proxy or move the protected method to another service.

**Question 7.** If all `policy.canRead(...)` unit tests pass with `StepVerifier`, is that enough to prove HTTP security?

**Answer:** No. You also need Spring proxy `@PreAuthorize` tests and HTTP filter/credential tests with `WebTestClient` to verify all three layers.

**Question 8.** Should you combine `hasRole('READER') and @policy.check(...)` when `check` returns `Mono<Boolean>`?

**Answer:** Avoid relying on SpEL resolving nested publishers automatically; combine conditions inside the bean so the reactive result is the **final result** of the authorization expression.

**Question 9.** If a user with `ROLE_ADMIN` accesses a non-existent ID, does the demo policy allow it?

**Answer:** No, because `findById` is empty and `defaultIfEmpty(false)` runs. This policy requires the document to exist **before** checking owner/admin.

**Question 10.** If the database has an outage, should you use `onErrorReturn(true)` to keep the system running?

**Answer:** Absolutely not. Never grant access when permissions could not be verified. Return a server/503 error and alert operations, never expose sensitive data.

## 17. Implementation checklist

- [ ] Using genuine reactive Spring WebFlux, not accidentally running MVC/Servlet.
- [ ] Enabled `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` for Spring Security 6.x patterns.
- [ ] Protected methods live on **Spring-managed public service beans**, returning `Mono<T>`/`Flux<T>`.
- [ ] Annotation references the exact bean name and method signature: `@documentAccess.canRead(authentication, #p0)`.
- [ ] Policy bean returns **`Mono<Boolean>`**, without calling `block()` or manual `subscribe()`.
- [ ] User/role data in `Authentication` was verified by an authentication provider.
- [ ] Missing resource or insufficient permission → explicit `false` decision, never accidentally returning empty.
- [ ] Database errors are never mapped to `true`.
- [ ] HTTP `authorizeExchange` still requires appropriate authentication/roles as the first line of defense.
- [ ] Have unit bean tests, Spring-proxy AOP method security tests, and end-to-end HTTP tests.
- [ ] Negative tests cover cross-owner, anonymous, non-existent ID, missing role, and wrong credentials.
- [ ] Checked self-invocation, parameter name lookup, async context propagation, caching, and timeouts.
- [ ] For write operations, re-check permissions inside transactions/updates to prevent TOCTOU.
- [ ] Protect secrets, TLS, audit logs, and avoid leaking document info via status codes or exceptions.

**Takeaway:** Reactive Spring Security allows beans invoked from `@PreAuthorize` to return **`Mono<Boolean>`** when using **AuthorizationManager-based reactive method security**. That enables **asynchronous, non-blocking** database/network permission checks. Return `true` when authorized, `false` when unauthorized or missing, handle `empty` and `error` intentionally, and **test through the Spring proxy** to ensure annotations genuinely take effect.

### Official references

- [Spring Security 6.5 — EnableReactiveMethodSecurity, Method Security Reactive Boolean Expression, Using a Custom Bean in SpEL](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — EnableReactiveMethodSecurity annotation Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5 — ReactiveSecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Framework — Spring AOP proxy semantics](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
