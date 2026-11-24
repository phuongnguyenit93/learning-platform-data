# Publisher Return Type Requirement When Applying Reactive Method Security

**Topic:** Spring Security – reactive · **Section:** Method Authorization  
**Focus:** The `org.reactivestreams.Publisher` return type requirement for Java methods protected by `@PreAuthorize`, how Spring Security uses Reactor Context, and mistakes made even when code looks asynchronous.

When protecting an endpoint with `authorizeExchange`, Spring Security checks permissions as the HTTP request passes through the filter chain. For a service that may be called from multiple places, we also need **method security**: placing authorization conditions directly on Spring-managed methods. For example:

```java
@PreAuthorize("hasRole('READER')")
public Mono<String> read(String id) {
    return repository.findById(id).map(Document::content);
}
```

This is a fragment, not a standalone Java file. The decisive point: the method returns `Mono<String>`, and `Mono` implements `org.reactivestreams.Publisher`. Spring Security Reactive relies on the Publisher contract and the **Reactor Context attached to the subscription** to read `Authentication` and apply `@PreAuthorize` at the right time.

**Core rule:** For Java methods using reactive method security in Spring WebFlux, declare the return type as a `Publisher<T>` — typically `Mono<T>`, `Flux<T>`, or `Mono<Void>`. Do **not** rely on a `@PreAuthorize` annotation attached to a method returning `String`, `List<T>`, `void`, or `CompletableFuture<T>` and assume it is intercepted properly. Those types do not follow the Publisher contract of reactive method security. Depending on the version, an error may be emitted upon invocation/subscription; do not treat the program continuing to run as proof of safety.

One intentional exception: the `AuthorizationManager` mechanism in modern Spring Security has **support for Kotlin coroutines/suspend functions** per the documentation. That is a dedicated coroutine integration, not a blanket guarantee that all Java Futures or synchronous methods are accepted.

## 1. Why is Publisher a critical requirement?

In WebFlux, requests A and B may be processed interleaved on the same event-loop thread; signals of a single request may also switch schedulers after an I/O call or `Mono.delay`. Therefore Spring Security Reactive cannot rely on the idea of "one ThreadLocal user per request".

`ReactiveSecurityContextHolder` reads `SecurityContext` from the **subscriber's** Reactor `Context`:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This is a fragment. Method security needs to connect the authorization check with the **Publisher chain** carrying that context. When a method returns `Mono` or `Flux`, the interceptor can attach the access decision to the pipeline. With a Java method returning `String` or `void` directly, there is no method Publisher to coordinate subscription in the way reactive method security documentation requires.

```text
HTTP / service caller
        |
        v
Spring AOP proxy of @Service
        |
        v
method with @PreAuthorize(...)
        |
        v
Publisher wrapped by reactive authorization
        |
        v
subscriber + Reactor Context with Authentication
        |
        +--> insufficient permissions -> AccessDeniedException / onError
        |
        +--> sufficient permissions  -> executes Mono/Flux source
                                            |
                                            v
                                       onNext/onComplete
```

The diagram describes the *logical meaning*, without committing to a specific Java call/bytecode order across all versions. The point to preserve is that **sensitive work must stay inside the pipeline and happen only after authorization**, rather than running eagerly before the pipeline has a subscriber.

### 1.1. Return type identification table

| Return type on annotated Java method | Is it a Publisher? | How to handle |
| --- | --- | --- |
| `Mono<User>` | Yes | Suitable for a single async result |
| `Flux<User>` | Yes | Suitable for multiple results or a stream |
| `Mono<Void>` | Yes | Suitable for operations signaling only completion/error |
| `Publisher<User>` | Yes | General contract; in Reactor apps prefer Mono/Flux for clarity |
| `Mono<ResponseEntity<String>>` | Yes | When a method needs an async HTTP response wrapper |
| `ResponseEntity<String>` | No | Not a Publisher boundary |
| `String`, `User`, `List<User>` | No | Synchronous results; do not use as return type of reactive secured methods |
| `void` | No | Change to `Mono<Void>` if the method needs reactive protection |
| `CompletableFuture<User>` | No | Needs deferred bridging to `Mono<User>` at the method boundary |
| `CompletionStage<User>` | No | Asynchronous does not mean Reactive Streams |
| Kotlin `suspend fun` | Special case | Check Spring Security version, coroutine integration, and proxy |

**Distinction:** A WebFlux controller **can** return plain Java objects and WebFlux will handle HTTP fine; the Publisher requirement in this lesson refers to **Java methods protected by reactive method security**. Do not infer that every utility/private function in a WebFlux project must return `Mono`.

### 1.2. Publisher does not mean running on a separate thread

`Mono.just("hello")` can still run synchronously on the subscribing thread. `Flux` does not automatically create concurrency. `Mono.delay` and `publishOn` may change execution scheduling, yet Reactor Context remains attached to the pipeline's regular subscriber. Security depends on the right context, not thread names or thread counts.

## 2. Enabling method security with the right WebFlux API

The Spring Boot Security starter **does not automatically enable** annotation-based method authorization merely by having the dependency. Spring Security 6.x uses the configuration:

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfig {
    // @Bean SecurityWebFilterChain, user store...
}
```

The snippet above is a fragment; section 6 has the complete project. `@EnableReactiveMethodSecurity` in Spring Security 6.x uses the `AuthorizationManager` mechanism by default; for older 5.x releases, documentation may mention `useAuthorizationManager=true`. Do not copy legacy options without checking your version.

Distinguish the three annotations:

- `@EnableWebFluxSecurity` enables WebFlux/HTTP security filters.
- `@EnableReactiveMethodSecurity` enables **reactive method** security interceptors.
- `@EnableMethodSecurity` is the standard method security configuration in the synchronous/Servlet stack; it does not automatically replace reactive configuration when you need Reactor Context.

Then place `@PreAuthorize("hasRole('READER')")` on a **public method** of a Spring-managed service. The Spring AOP proxy must be the caller's actual path. `@PreAuthorize` is not an arbitrary HTTP header permission: the expression reads the trusted `Authentication` established by Spring Security.

### 2.1. Separating HTTP policy from method policy

A clear design:

```java
// In SecurityWebFilterChain:
.authorizeExchange(ex -> ex
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll())

// In service:
@PreAuthorize("hasRole('ADMIN')")
public Flux<String> auditEvents() { ... }
```

These are two illustrative fragments, not standalone compilable Java files. The HTTP policy says **the caller must be logged in**; the method policy says **must have ROLE_ADMIN**. If the service has additional non-HTTP entry points, the method rule still applies. If you only test that the API returns 401 without credentials, you have not proven `@PreAuthorize` works — because the request may have been blocked at the HTTP layer.

## 3. Writing Publisher types for the right purpose

### 3.1. Mono<T>: a single result

```java
@PreAuthorize("hasRole('READER')")
public Mono<Report> report(String id) {
    return reportRepository.findById(id);
}
```

This is a hypothetical fragment with `Report` and `reportRepository`. `Mono` represents zero or exactly one result. Owner/tenant permissions must also be enforced; the READER role does not automatically grant access to every report.

### 3.2. Flux<T>: multiple elements

```java
@PreAuthorize("hasAuthority('audit:read')")
public Flux<AuditRecord> auditHistory() {
    return auditRepository.findRecent();
}
```

`Flux` is a Publisher emitting multiple signals. Merely allowing the method call does not filter individual records by owner. If streaming across multiple tenants, the repository/data policy must constrain the data source rather than relying solely on a role.

### 3.3. Mono<Void>: operations without a response body

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteRecord(String id) {
    return reactiveRepository.deleteById(id);
}
```

Switching to `void` and calling `deleteById(id).subscribe()` is **not** equivalent: it detaches the task from the pipeline and authorization. `Mono<Void>` expresses completion/error; the WebFlux controller can await it to respond properly. Write operations must protect owner/tenant, transactions, idempotency, and execute writes only after authorization.

### 3.4. When a method needs an HTTP status

An annotated method can return `Mono<ResponseEntity<DTO>>` if an HTTP wrapper is genuinely needed:

```java
@PreAuthorize("hasRole('READER')")
public Mono<ResponseEntity<String>> preview(String id) {
    return service.loadText(id).map(ResponseEntity::ok);
}
```

The above is a fragment. `Mono<ResponseEntity<String>>` is a Publisher; plain `ResponseEntity<String>` is not. Usually you should place method security on the business service and let the controller handle status mapping, so the service can be reused across entry points.

## 4. Choosing execution timing: assembly vs. subscription

The highest-risk mistake is **a method returning Mono that already performs sensitive work before returning**.

### 4.1. Wrong: eager side effects

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteNow(String id) {
    legacyDeleteBlocking(id);  // may run immediately when target method is invoked
    return Mono.empty();
}
```

This is an *anti-pattern*. Even though the return type is `Mono<Void>`, calling `legacyDeleteBlocking` is not a deferred Publisher operator. Even if the proxy may defer certain steps in some versions, that is no reason to rely on side effects occurring before publisher subscription. Avoid side effects outside the protected stream, and especially avoid blocking on the Netty event loop.

### 4.2. Right: deferring the reactive source

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteAfterAuthorization(String id) {
    return Mono.defer(() -> reactiveRepository.deleteById(id));
}
```

`Mono.defer` only creates the inner publisher upon subscription. If the repository itself is reactive/cold, you can return `reactiveRepository.deleteById(id)` directly, though `defer` makes the creation boundary clearer when initialization logic exists.

### 4.3. Legacy blocking calls must be isolated

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Void> deleteLegacy(String id) {
    return Mono.fromRunnable(() -> legacyDeleteBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
}
```

This is a fragment requiring imports/implementations of `Schedulers` and `legacyDeleteBlocking`; use it as a **temporary bridge** in legacy systems, not a permanent optimal solution. Do not use `Mono.just(blockingRepository.load(id))`: Java evaluates the argument **before** `Mono.just` is constructed, so blocking I/O already ran at assembly time. Whenever possible, use R2DBC/reactive drivers or libraries that do not block the event loop.

### 4.4. Future does not automatically become a Publisher

`CompletableFuture<T>` does not implement `org.reactivestreams.Publisher`. If an external library returns a future, the annotated method should convert it **inside the reactive boundary**:

```java
@PreAuthorize("hasRole('READER')")
public Mono<String> export(String id) {
    return Mono.fromFuture(() -> externalClient.exportAsync(id));
}
```

This is a Reactor fragment using the `Supplier` overload. Unlike `Mono.fromFuture(alreadyStartedFuture)`, creating the future inside a `Supplier` defers execution until subscription. You must manage cancellation, timeouts, retries, and idempotency; cancelling a future does not guarantee rolling back third-party operations.

**Anti-patterns that fail to satisfy the Publisher contract:**

```java
@PreAuthorize("hasRole('ADMIN')")
public String exportNow() {
    return costlyExport();
}

@PreAuthorize("hasRole('ADMIN')")
public void clearCache() {
    clearSensitiveCache();
}

@PreAuthorize("hasRole('ADMIN')")
public CompletableFuture<String> exportAsync() {
    return CompletableFuture.supplyAsync(this::costlyExport);
}
```

These are **incorrect patterns to fix**, not functions you should ship to production. Spring Security reactive method interceptors do not promise direct support for these return types. Use `Mono<String>`, `Mono<Void>`, and corresponding deferred sources when defining a method security boundary.

## 5. Spring AOP proxy is the second critical requirement

A correct return type is only a **necessary** condition, not sufficient. Spring reactive method security uses **AOP interception**. Practical requirements:

1. **Spring-managed bean:** the `@Service` class is created and injected by Spring. If a controller calls `new DocumentService()` itself, there is no security proxy.
2. **External invocation through proxy:** calling `documentService.read(...)` from a controller or another bean passes through the proxy. `this.read(...)` inside the same class is *self-invocation*; with standard Spring AOP proxies, it is not advised again.
3. **Proxyability:** public methods, non-final, appropriate class/interface structure. `private` and `final` have limitations depending on the proxy strategy.
4. **Correct annotations and dependencies:** `@EnableReactiveMethodSecurity` must be present, configured for WebFlux, not just HTTP security.
5. **Do not detach subscription:** do not call `subscribe()` manually in a controller and then return a separate `Mono.just("accepted")`.
6. **Test the real entry path:** at least one negative test using the Spring-injected bean or real HTTP expecting an error/403 when lacking a role.

Risky self-invocation example:

```java
@Service
class IncorrectFacade {
    public Mono<String> callInternal(String id) {
        return guarded(id); // internal call on this
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> guarded(String id) {
        return Mono.just("secret:" + id);
    }
}
```

This is an intentionally architecturally flawed fragment. When a caller invokes `callInternal` through the proxy, `guarded` inside is **not automatically re-proxied**. Fix by placing the annotation on `callInternal`, or moving `guarded` into a second Spring-injected bean and calling through that bean. Test the indirect call path separately.

## 6. Complete Java 17+ Spring Boot WebFlux example

This exercise uses HTTP Basic to avoid mixing the topic with UI login. Focused solely on method security:

- `GET /public/ping` is public → `200 pong`.
- Anonymous `GET /api/documents/R7` → `401` due to HTTP `authenticated()`.
- User `reader`, role `ROLE_READER`, calling `/api/documents/R7` → `200 document:R7:reader`.
- User `admin`, role `ROLE_ADMIN`, calling **the same URL** → `403` due to `@PreAuthorize("hasRole('READER')")`.
- User `reader` calling `/api/audit` → `403` due to `@PreAuthorize("hasRole('ADMIN')")` on a `Flux`.
- User `admin` calling `/api/audit` → `200` and a JSON array with two elements.

Each user has only **one distinct role**, ensuring negative role tests actually catch unconfigured method security.

### 6.1. Structure and pom.xml

```text
reactive-method-publisher/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/method/
    │   │   ├── MethodSecurityApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── DocumentService.java
    │   │   └── DocumentController.java
    │   └── resources/application.properties
    └── test/java/demo/method/
        └── MethodSecurityTests.java
```

The example uses JDK 17+ and Spring Boot **3.5.7** to illustrate a configuration consistent with Spring Security 6.5.x. In real applications, upgrade to a supported version with patches according to project policy.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-method-publisher</artifactId>
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

Do not add `spring-boot-starter-web` (Servlet MVC) for a WebFlux lesson. No database, Docker, or external accounts are needed. Passwords are only for localhost testing; never reuse them in production products.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-method-publisher
server.port=8080
```

### 6.2. Application entry point

`src/main/java/demo/method/MethodSecurityApplication.java`:

```java
package demo.method;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
```

### 6.3. SecurityConfig: URL authentication, method authorization

`src/main/java/demo/method/SecurityConfig.java`:

```java
package demo.method;

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

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

Explanation:

- HTTP `/api/**` only requires `authenticated()`; **there are no role rules at HTTP**. If method security is turned off, many URLs would still allow any logged-in user.
- `@EnableReactiveMethodSecurity` activates reading annotations on Spring beans.
- `PasswordEncoderFactories` hashes demo passwords using a delegating encoder with BCrypt; it does not store `{noop}` plaintext.
- `formLogin` is disabled for the demo API to observe HTTP Basic 401/403; real applications may use sessions/OAuth2, yet the Publisher requirement remains central.
- `anyExchange().denyAll()` prevents new routes from being open by default.

### 6.4. Service: Mono and Flux actually protected

`src/main/java/demo/method/DocumentService.java`:

```java
package demo.method;

import java.time.Duration;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    @PreAuthorize("hasRole('READER')")
    public Mono<String> read(String id) {
        return Mono.delay(Duration.ofMillis(10))
            .then(ReactiveSecurityContextHolder.getContext())
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "document:" + id + ":" + name);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Flux<String> audit() {
        return Flux.just("audit-open", "audit-close")
            .delayElements(Duration.ofMillis(5));
    }
}
```

`Mono.delay`/`delayElements` demonstrate that signal emission time differs from the Java method invocation time. `ReactiveSecurityContextHolder` still reads the subscriber's Context. Both `public` methods belong to a `@Service` bean and are invoked by the controller via dependency injection, allowing the AOP proxy to run.

### 6.5. Controller connecting Publishers to HTTP

`src/main/java/demo/method/DocumentController.java`:

```java
package demo.method;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {
    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/documents/{id}",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> read(@PathVariable String id) {
        return documents.read(id);
    }

    @GetMapping(value = "/api/audit",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<String> audit() {
        return documents.audit();
    }
}
```

Do not call `new DocumentService()`, `documents.read(id).block()`, or `documents.audit().subscribe()`. The controller returns the Publisher so WebFlux manages subscription, Reactor Context, and the HTTP response. If a 404 status is needed, map `Mono.empty()`/domain errors at the HTTP boundary rather than turning the annotated service method into a synchronous `ResponseEntity`.

## 7. Running and verifying with curl

In the project directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Open another terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/documents/R7
curl -i --user reader:reader123 http://localhost:8080/api/documents/R7
curl -i --user admin:admin123 http://localhost:8080/api/documents/R7
curl -i --user reader:reader123 http://localhost:8080/api/audit
curl -i --user admin:admin123 http://localhost:8080/api/audit
```

Expected results:

| Request | Status | Content/meaning |
| --- | --- | --- |
| Public anonymous | 200 | `pong` |
| Anonymous document | 401 | Rejected by URL policy `authenticated()` |
| Reader document | 200 | `document:R7:reader` |
| Admin document | 403 | HTTP authenticated but lacks READER role on method |
| Reader audit | 403 | Method returning Flux requires ADMIN role |
| Admin audit | 200 | JSON list containing `audit-open` and `audit-close` |

Error bodies/messages may depend on handlers. The admin/document and reader/audit test pairs are essential **negative role tests**: if method security is not enabled or calls bypass the AOP proxy, they may return 200 even though HTTP authentication works.

On PowerShell, use `curl.exe` if `curl` is aliased. Basic auth uses Base64 and does not encrypt transport; outside localhost always use HTTPS and avoid placing real credentials in logs/shell history.

## 8. WebTestClient + StepVerifier: verifying Publishers and permissions

`@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a real server on a random port. `WebTestClient` passes through HTTP filters, while `StepVerifier` tests the Publisher of the **Spring-injected service bean** under an `Authentication` in a test Reactor Context.

`src/test/java/demo/method/MethodSecurityTests.java`:

```java
package demo.method;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MethodSecurityTests {

    @Autowired
    WebTestClient client;

    @Autowired
    DocumentService documents;

    @Test
    void publicPingWorksWithoutLogin() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousDocumentGets401() {
        client.get().uri("/api/documents/R7")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerReceivesAuthorizedMonoValue() {
        client.get().uri("/api/documents/R7")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("document:R7:reader");
    }

    @Test
    void adminWithoutReaderRoleGets403ForMono() {
        client.get().uri("/api/documents/R7")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readerGets403ForAdminFlux() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminReceivesBothFluxValues() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(String.class)
            .hasSize(2)
            .contains("audit-open", "audit-close");
    }

    @Test
    void directServiceProxySeesReaderContextAtSubscription() {
        Authentication reader = new TestingAuthenticationToken(
            "reader", "unused", "ROLE_READER");

        StepVerifier.create(
                documents.read("R8")
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(reader)))
            .expectNext("document:R8:reader")
            .verifyComplete();
    }

    @Test
    void directServiceProxyRejectsMissingReaderRole() {
        Authentication admin = new TestingAuthenticationToken(
            "admin", "unused", "ROLE_ADMIN");

        StepVerifier.create(
                documents.read("R8")
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(admin)))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

Run:

```bash
mvn test
```

With only the test class above, the target is **8 passing tests** when the JDK/Maven/dependencies environment is correct. This is sample code for learners to run themselves; **do not claim tests were already executed in the reader's project**. If a version changes the exception subtype, check the actual exception: Spring Security includes types in the `AccessDeniedException` and `AuthorizationDeniedException` family; do not relax tests to accept arbitrary exceptions.

### 8.1. Meaning of each test group

- The anonymous 401 test proves the **HTTP layer** requires authentication, not that annotations work.
- The reader Mono 200 test proves a Publisher is processed successfully with the right principal.
- The admin Mono 403 / reader Flux 403 tests prove the **method-level role policy** is truly enforced, because HTTP only requires authentication.
- The admin Flux 200 test verifies the JSON HTTP body contains the exact two values.
- Direct `StepVerifier` tests invoke the **Spring-injected proxy** and attach `Authentication` via `contextWrite`. Using `new DocumentService()` bypasses AOP; attaching context outside the right subscription breaks the test.
- `withAuthentication` in tests is data trusted by the test harness to populate Reactor Context. Never allow HTTP clients to attach roles via an `X-Role` header in production.

### 8.2. Verifying side effects are blocked

If a project method writes to a database or calls an external API, add a test: when an unauthorized caller subscribes to the method, the Publisher emits an access-denied signal **and the database/side effects remain unchanged**. Checking 403 alone is insufficient if code runs eagerly before returning the Publisher. For user-scoped Flux streams, add tests verifying no records belonging to another tenant are returned, not just status 200.

## 9. Protecting data even when the Publisher is valid

`@PreAuthorize("hasRole('READER')")` is a role policy; it does **not** automatically filter individual resources by owner or tenant. For instance, `findById(id)` could return someone else's report even if the caller has the role. You must pass the authenticated identity into the query:

```java
@PreAuthorize("hasRole('READER')")
public Mono<Report> readMine(String id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .flatMap(username ->
            reports.findByIdAndOwnerUsername(id, username));
}
```

This is a hypothetical fragment with `Report` and repository `reports`, not a standalone Java file. The repository must **actually filter owner at the data source** and check tenant ID in multi-tenant systems. Never trust a client-supplied `ownerId` unless policy has verified it against a trusted `Authentication`.

### 9.1. Asynchronous authorization decisions with Mono<Boolean>

Spring Security with `AuthorizationManager` supports custom method authorization expressions/beans returning `Boolean` or `Mono<Boolean>` per the 6.5 docs. This is the **return type of the authorization decision**, distinct from the protected method's return type.

```java
@Component("reportPolicy")
class ReportPolicy {
    public Mono<Boolean> canRead(String id) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(user -> permissionRepository.isAllowed(user, id))
            .defaultIfEmpty(false);
    }
}

@Service
class ReportService {
    @PreAuthorize("@reportPolicy.canRead(#id)")
    public Mono<Report> read(String id) {
        return reportRepository.findById(id);
    }
}
```

This is a **fragment** requiring `permissionRepository`, `reportRepository`, `Report`, and appropriate imports/beans. `isAllowed` must return `Mono<Boolean>` and must not block. If `Authentication` is missing, the policy defaults to `false`. This pattern makes the entire expression an async result; combining it with other SpEL boolean operators must be tested against your exact version.

### 9.2. PostAuthorize does not replace pre-side-effect checks

`@PreAuthorize` is useful when blocking **before an action**. `@PostAuthorize` inspects the result after the method is invoked / the Publisher produces a value, depending on the interceptor mechanism; if the pipeline already wrote data or processed a payment, denying afterward **does not automatically roll back** side effects. For sensitive resources, prefer authorization checks before or within the query, treating post-checks as an additional layer with dedicated tests.

### 9.3. Caches/Hot Publishers can also leak data

`Mono.cache()` can replay the first subscription's result to subsequent subscribers; `Flux.share()` or hot `Sinks` can share signals. If results carry principal, account, or tenant data, an unpartitioned singleton cache will expose data even when the method has a valid role annotation. Partition caches by principal/tenant/resource and check permissions per request; or do not cache sensitive results.

### 9.4. Retry, re-subscription, and Reactor Context

A cold Publisher can re-execute on multiple subscriptions, `retry`, or `repeat`. Every subscription needs the proper Context, and write operations must handle idempotency/transactions where needed. `Mono.delay` or `publishOn` within a normal Reactor chain does not lose Context; however, spawning `CompletableFuture.supplyAsync` and reading `ThreadLocal` may fail to propagate identity. Never use `ThreadLocal currentUser` as the source for reactive authorization.

## 10. Common errors and fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Method has `@PreAuthorize` but returns `String` or `void` | Return type contract mismatch | Change to `Mono<T>` / `Mono<Void>` |
| Method returns `CompletableFuture` | Future is not a Publisher | Use `Mono.fromFuture(Supplier)` and a deferred source |
| Wrong role still gets 200 | Annotation not enabled, self-invocation, bypassing Spring proxy | Enable `@EnableReactiveMethodSecurity`, inject bean, test 403 |
| Unauthorized call still writes to DB | Eager side effect before Publisher | Move into `Mono.defer`/reactive repository, test side effects |
| Thread switch loses username | Using ThreadLocal / detached pipeline | Use `ReactiveSecurityContextHolder` and Reactor Context |
| Direct test with `new Service()` is permitted | No AOP proxy | Inject Spring bean in test |
| Reader receives Bob's record | Role-only policy, query lacks owner/tenant | Filter data in repository, test cross-tenant access |
| Flux accidentally emits shared data | Hot/cached singleton Publisher | Isolate streams/caches per user or remove shared state |
| Slow API during queries | `Mono.just(blockingCall())` or `block()` | Use reactive I/O, isolate blocking calls when unavoidable |
| Logged in but gets 403 | Incorrect method role/scope | Check authorities/SpEL/proxy, do not delete policies carelessly |
| 403 error turns into empty 200 | `onErrorResume` swallows access-denied | Handle authorization errors intentionally at the boundary |
| Has `@PostAuthorize` yet still transfers money | Post-check does not undo side effects | Use pre-authorization and proper transactions |

### 10.1. Do not fix 403 by removing annotations

If `admin` lacks READER and gets 403 on `/api/documents`, that is an intentional demonstration test. Replacing `@PreAuthorize("hasRole('READER')")` with `permitAll` just to make tests pass breaks the policy. Distinguish configuration bugs from actual product permission requirements.

### 10.2. Do not use onErrorResume indiscriminately

`onErrorResume(Throwable.class, e -> Mono.empty())` can swallow `AccessDeniedException`, making the client think there is no data instead of being denied. Manage 403 responses, log metadata safely, and distinguish authorization errors from 404/not found, I/O failures, or invalid input.

### 10.3. Do not treat annotations as a substitute for tests

An annotation may exist in code yet Spring AOP may not intercept it due to self-invocation, final methods, non-bean classes, or disabled config. Negative tests with wrong roles are mandatory checks to prove rules are enforced.

## 11. Special cases and limitations

**Kotlin coroutines:** Modern Spring Security with AuthorizationManager supports `suspend fun`; check Spring Security/Kotlin versions, WebFlux coroutine integration, `open` classes/all-open plugin, and write dedicated tests. Do not overgeneralize the Java Publisher requirement into "Kotlin suspend is always forbidden".

**Reactive policy beans:** Can return `Mono<Boolean>` for user/resource allow/deny logic; must not block threads while looking up permissions. If combining multiple expressions, test SpEL/authorization manager semantics.

**Publisher.empty():** `Mono.empty()` or `Flux.empty()` are still valid Publishers. "Not emitting onNext" does not mean bypassing method security; the pipeline must still be subscribed and complete/error per policy.

**Mono<Void>:** Emits no value, yet subscription/completion is real. This is the right shape for WebFlux to know when an async operation finishes, rather than using `void` + `subscribe()`.

**Partitioned data storage:** A permitted Flux may contain many records; per-record viewing rights are not automatically solved by `@PreAuthorize("hasRole('USER')")`. Put guards at the service/repository level.

**Methods called from scheduled/background jobs:** Non-HTTP calls may lack a Reactor SecurityContext. You must explicitly design the job's identity/authorization; never blindly grant ADMIN to every Publisher just to avoid errors.

**Publisher return type does not prove non-blocking:** `Mono.fromCallable(blockingOperation)` can still block a thread upon subscription. Use a controlled `boundedElastic` bridge with timeouts, capacity limits, and performance testing if you haven't migrated to a reactive driver yet.

## 12. Implementation checklist

1. Identify annotated methods and their **declared return types**. For reactive Java, use `Mono<T>`, `Flux<T>`, or `Mono<Void>`.
2. Enable `@EnableReactiveMethodSecurity`; retain `@EnableWebFluxSecurity`/`SecurityWebFilterChain` for HTTP per your architecture.
3. Place rules on public Spring service beans called via AOP proxy, avoiding self-invocation/`new`/private/final pitfalls.
4. Keep side effects inside deferred Publishers; never call `subscribe()` manually or `block()` on the event loop.
5. Obtain principals from `ReactiveSecurityContextHolder` and never trust self-declared headers or singleton fields.
6. Test methods with Spring-injected proxies using `StepVerifier` and Reactor Context; test HTTP with `WebTestClient`.
7. Include negative tests: anonymous 401, authenticated wrong role 403, no cross-owner/tenant data leaks.
8. For write methods, test that **no side effects occur** when the role is denied.
9. For Flux/hot Publishers/caches/retries, test for zero leaks between subscribers and verify writes are not re-executed unintentionally.
10. When using Kotlin coroutines or `Mono<Boolean>` policies, consult documentation for your exact version rather than blindly copying Servlet config.
11. Add resource/tenant-level authorization rather than treating method role-only checks as sufficient for all data.
12. Upgrade framework versions per policy and re-run tests when changing proxies, annotations, or schedulers.

## 13. Self-assessment questions

**Question 1.** Is `CompletableFuture<User>` a `Publisher<User>`?  
**No.** Java Future does not implement Reactive Streams Publisher. Return `Mono<User>` and defer the source when integrating.

**Question 2.** Why is `Mono.just(blockingSave())` dangerous?  
Because Java executes `blockingSave()` before `Mono.just(...)` is created. That is an eager side effect/blocking call, failing to respect the subscription boundary.

**Question 3.** Is `Mono<Void>` a valid return type for applying `@PreAuthorize`?  
**Yes.** It is a Publisher that completes or errors and suits async operations without a body.

**Question 4.** Does enabling `@EnableWebFluxSecurity` automatically enable `@PreAuthorize` on services?  
**No.** `@EnableReactiveMethodSecurity` is required.

**Question 5.** Is `@PreAuthorize` on a method returning Mono safe if a controller calls `new Service()`?  
**Not under normal Spring AOP proxy mechanics.** The service must be a Spring-managed bean called through its proxy.

**Question 6.** An authenticated user lacking a role calls an endpoint and receives 403; how does this differ from 401?  
401 typically relates to missing valid authentication, whereas 403 for a logged-in user indicates authorization denied by policy.

**Question 7.** Does `Flux<Report>` annotated with `@PreAuthorize("hasRole('READER')")` automatically filter records by tenant?  
**No.** Owner/tenant checks must be enforced in the query or domain policy.

**Question 8.** Are Java methods returning `String` protected identically to reactive `Mono<String>`?  
**Do not assume so.** Reactive method security requires the Publisher contract to integrate with Reactor Context.

**Question 9.** Does a denied `@PostAuthorize` automatically roll back an already sent email or processed payment?  
**No.** Enforce authorization before side effects and design proper transactions/idempotency.

**Question 10.** Must Kotlin `suspend fun` always declare `Mono` in source code to be supported?  
**Not strictly.** Spring Security AuthorizationManager mode supports coroutines on compatible versions; test that integration separately.

### Official documentation

- Spring Security 6.5, *EnableReactiveMethodSecurity*: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security, `EnableReactiveMethodSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html
- Spring Security, `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Project Reactor, *Adding a Context to a Reactive Sequence*: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor `Mono` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework, *AOP Proxying Mechanisms*: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Conclusion:** For **reactive** method security in Java, a `Publisher` return type is the requirement enabling interceptors to connect authorization with the subscription's Reactor Context. Prefer `Mono`, `Flux`, and `Mono<Void>`; yet the right return type alone is not enough — code must be invoked through a Spring AOP proxy, must not run side effects before authorization, and must have negative tests proving unauthorized users are truly blocked.