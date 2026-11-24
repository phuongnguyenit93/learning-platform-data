# Combining HTTP Authorization with Method Authorization in Spring Security WebFlux

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **authorization at HTTP/WebFilter** from **authorization on Spring bean method invocations**; understand why a single business operation may require both protection layers.
2. Configure `ServerHttpSecurity.authorizeExchange(...)` alongside `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` and `@PreAuthorize` for methods returning `Mono`/`Flux`.
3. Describe how `Authentication` propagates through Reactor Context and the role of `ReactiveSecurityContextHolder` for calls inside and outside HTTP requests.
4. Combine roles, authorities, and per-document permissions using a `Mono<Boolean>` check backed by R2DBC, never calling `block()` in WebFlux.
5. Design policies where **both layers must allow** (logical AND), default-deny, and avoid self-invocation that bypasses AOP.
6. Write and test a Java 17+ example with Spring Boot WebFlux, method security, an H2 R2DBC database, `WebTestClient`, `StepVerifier`, and distinguish 401/403/404.
7. Identify risks involving multi-tenancy, TOCTOU, permission caching, missing context, and the limits of HTTP authorization alone.

> **Reference versions:** Spring Boot 3.x, Spring Security 6.5.x, Java 17+. Code uses **reactive** APIs: `SecurityWebFilterChain`, `ServerHttpSecurity`, `@EnableReactiveMethodSecurity`, `Mono`, and `ReactiveSecurityContextHolder`. Do not replace them with Servlet/MVC APIs such as `HttpSecurity`, `SecurityFilterChain`, or manual `ThreadLocal` when handling Reactor streams.

## 1. Two protection layers solve two kinds of risk

An application can enforce policies right when an HTTP request enters the system:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated()
)
```

This rule defines which URLs are exposed. However, the same data-reading business logic can also be called from another HTTP endpoint, an internal job, a message consumer, or other service code. If you only guard URLs and forget to guard the service, other call paths can bypass permission checks.

Conversely, if you place `@PreAuthorize` on one service yet carelessly leave HTTP `anyExchange().permitAll()`, resources and endpoints that do not invoke that service may be exposed. Good security requires defining **separate boundaries** for both layers.

| Layer | Location | Typical conditions | Primary responsibility |
| --- | --- | --- | --- |
| HTTP authorization | Security WebFilter before controller | HTTP method, path, logged-in status, functional scope roles | Block invalid requests at the perimeter |
| Method authorization | Spring AOP around public bean methods | Roles, authorities, method arguments, object/tenant, business state | Block unauthorized operations regardless of caller origin |
| Data access guard | Data-access queries/services | Owner/tenant/ACL/row-level policy | Retrieve or mutate only genuinely permitted records |
| Authentication | Before authorization decisions | HTTP Basic, session, OAuth2/JWT | Establish a trustworthy identity |

**If an HTTP request must pass both an HTTP rule and a method rule, it succeeds only when both grant access.** One layer does not "unlock" the other. A `permitAll()` at HTTP does not bypass `@PreAuthorize`; a permitted method does not bypass HTTP `denyAll()`.

### Clear example

Suppose the API has:

- `GET /documents/100`: logged-in users can **reach the controller**, yet the service allows reading the document only if the user holds the READER role and an ACL entry for document 100.
- `GET /documents/100/audit`: HTTP requires `ROLE_AUDITOR`; the service additionally requires authority `AUDIT_VIEW`.
- `GET /public/ping`: HTTP is public and the controller performs no sensitive operations.

A user with `ROLE_AUDITOR` lacking `AUDIT_VIEW` passes the HTTP layer and is denied by the service. A user holding only `ROLE_READER` is blocked at the HTTP layer immediately when calling the audit URL, regardless of other endpoints.

### Decision matrix

| HTTP rule | Method rule | Outcome when endpoint calls that method |
| --- | --- | --- |
| Allow | Allow | Controller/service proceeds, subject to data/business constraints |
| Allow | Deny | Method does not execute protected work; HTTP usually returns 403 if authenticated |
| Deny | Hypothetical allow | HTTP blocks first; method is never called from this request |
| Deny | Deny | HTTP blocks first; never rely solely on the second check |
| No auth required | Method requires identity | Method still blocks if valid context is absent |
| Non-HTTP call (job/message) | Method allows or denies | Only method/data guards remain to enforce; context must be set intentionally |

Do not describe these as two steps that always run sequentially for **every request**: if HTTP blocks early, the method is never invoked; endpoints without method security have no second check.

## 2. Reactive method security mechanism and Reactor Context

To enable method authorization, add to your Spring configuration:

```java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
```

Spring Security registers **AOP interceptors** for annotations such as `@PreAuthorize` and `@PostAuthorize`. When a bean is called through its Spring proxy, the interceptor can check permissions before or after the operation, reading authentication from **Reactor Context**.

Key points:

- Protected methods in reactive programs generally must return `org.reactivestreams.Publisher`, such as `Mono<T>` or `Flux<T>`. This lets authorization use the right context at subscription time.
- `ReactiveSecurityContextHolder` reads `SecurityContext` from Reactor Context rather than relying on Servlet thread-local `SecurityContextHolder.getContext()`.
- `@PreAuthorize` checks **before** protected work; when denied, Spring Security emits `AccessDeniedException` in the publisher, and the method is not executed per contract.
- `@PostAuthorize` checks **after** a result exists, before returning it to the caller. For write operations with side effects, it does **not** replace pre-authorization because side effects may have already occurred.
- `@EnableWebFluxSecurity` does not automatically enable method security. You must enable `@EnableReactiveMethodSecurity` for the target methods.
- Do not mechanically copy `@EnableMethodSecurity` from Servlet examples when your app is intended to use reactive method support.

### Authentication propagation path

```text
HTTP request
  |
  +--> Authentication WebFilter (Basic/Session/JWT)
  |       |
  |       v
  |   Reactor Context containing SecurityContext/Authentication
  |
  +--> AuthorizationWebFilter
  |       |
  |       +--> HTTP matcher / role rule -> pass / deny
  |
  +--> Controller calls Spring service bean (via proxy)
          |
          +--> Reactive method security interceptor
          |       |
          |       +--> @PreAuthorize reads Authentication from Reactor Context
          |       +--> Checks role/permission/ACL
          |       +--> Deny -> AccessDeniedException
          |
          +--> Service executes Mono/Flux logic
                  |
                  +--> Data access with owner/tenant constraint
                  +--> Returns result, optionally with additional @PostAuthorize
```

When switching threads via `publishOn(...)` or `subscribeOn(...)` while **keeping the Reactor chain intact**, Reactor Context normally travels with the subscription. Conversely, calling `subscribe()` manually, creating publishers outside a request without context, or hopping to unmanaged executors can make method security see anonymous/missing authentication. Never "fix" this by stuffing a fake Authentication into a global variable.

### How to use @PreAuthorize?

```java
// Methods in a Spring bean, illustrating declaration:
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOnly() {
    return Mono.just("restricted");
}

@PreAuthorize("hasAuthority('AUDIT_VIEW')")
public Flux<String> auditItems() {
    return Flux.just("entry-1", "entry-2");
}
```

`hasRole("ADMIN")` in SpEL corresponds to authority `ROLE_ADMIN` (default prefix), whereas `hasAuthority("AUDIT_VIEW")` compares the exact string without adding a prefix. Role/permission naming conventions must stay consistent across your identity provider, user database, JWT authorities mapping, and policies.

## 3. Sample policy: HTTP routes + service-level document permissions

Let's build a demo project:

- Uses HTTP Basic for easy testing, without HTML pages or form login.
- HTTP `GET /documents/{id}` requires **`authenticated`** without deciding every ACL itself.
- Service `readDocument(id)` carries `@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")`. Bean `documentPolicy` returns `Mono<Boolean>` after checking roles and querying permissions in H2 R2DBC.
- The content-fetching query still includes the ACL predicate to avoid bugs if permissions change after the method check.
- URL `GET /documents/{id}/audit` requires `ROLE_AUDITOR` at HTTP; method `auditDocument(id)` additionally requires `AUDIT_VIEW`.
- All other URLs/methods hit `denyAll()`, leaving only `GET /public/ping` open publicly.

### Expected data

| Account | Authorities | Document read ACL | Outcome |
| --- | --- | --- | --- |
| `alice` | `ROLE_READER` | READ document 100 | Reads 100; 200 is denied |
| `bob` | `ROLE_READER` | READ document 200 | Reads 200; 100 is denied |
| `charlie` | `ROLE_VIEWER` | Has READ row for document 100 | Still denied because `ROLE_READER` is missing |
| `auditor` | `ROLE_AUDITOR` | No ACL needed in demo | Passes HTTP audit yet denied by method for lacking `AUDIT_VIEW` |
| `chief` | `ROLE_AUDITOR`, `AUDIT_VIEW` | No ACL needed in demo | Allowed into audit endpoint |
| Anonymous | No valid Authentication | None | 401 with HTTP Basic on protected URLs |

These are **local fixtures**, not roles and passwords suitable for production. Specific policies vary by organization; this lesson demonstrates composing **AND conditions across multiple layers**.

## 4. Preparing the Spring Boot WebFlux + R2DBC project

### 4.1. Dependencies

In a Gradle project with the Spring Boot plugin, dependency management, and Java 17+, include these dependencies:

**`build.gradle`** (`dependencies` block):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Do not add `spring-boot-starter-web` to this example: when MVC and WebFlux share the classpath, Spring Boot usually selects Servlet, breaking the reactive security/config runtime types.

Source layout:

```text
src/main/
  java/example/layered/
    LayeredSecurityApplication.java
    ReactiveSecurityConfiguration.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  resources/
    application.yml
    schema.sql
    data.sql
src/test/
  java/example/layered/
    LayeredSecurityIntegrationTest.java
```

### 4.2. H2 R2DBC configuration

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: layered-webflux-security
  r2dbc:
    url: "r2dbc:h2:mem:///layereddb?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
  sql:
    init:
      mode: always
      schema-locations: "classpath:schema.sql"
      data-locations: "classpath:data.sql"

server:
  port: 8080
```

- `r2dbc:h2:...` is the R2DBC driver URL, **distinct** from `jdbc:h2:...`.
- `spring.sql.init.mode=always` runs schema/data fixtures at app startup. Use only for exercises or controlled test environments.
- In-memory H2 does not replace migrations and backups for production PostgreSQL.
- `DB_CLOSE_DELAY=-1` keeps the in-memory DB alive when connections temporarily close.

### 4.3. Schema and sample data

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT PRIMARY KEY,
    body VARCHAR(1000) NOT NULL
);

CREATE TABLE IF NOT EXISTS document_permissions (
    document_id BIGINT NOT NULL,
    username VARCHAR(120) NOT NULL,
    permission VARCHAR(20) NOT NULL,
    PRIMARY KEY (document_id, username, permission),
    CONSTRAINT fk_doc_permission
        FOREIGN KEY (document_id) REFERENCES documents(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_doc_permission_username
    ON document_permissions(username);
```

**`src/main/resources/data.sql`**:

```sql
INSERT INTO documents(id, body)
VALUES
    (100, 'Internal plan A'),
    (200, 'Private plan B');

INSERT INTO document_permissions(document_id, username, permission)
VALUES
    (100, 'alice', 'READ'),
    (200, 'bob', 'READ'),
    (100, 'charlie', 'READ');
```

The `ROLE_READER` role is declared in the Security Configuration's user store; it is **not** in the demo ACL table. Reason: the role answers whether a user may use the reading capability in general; the ACL answers whether that user may read **a specific record**.

Production schemas need immutable user IDs, tenant IDs, proper indexes, foreign keys to users/tenants, and versioned migrations. Usernames in the demo table are solely for readability; they are suboptimal when usernames can change.

### 4.4. Main class

**`src/main/java/example/layered/LayeredSecurityApplication.java`**:

```java
package example.layered;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LayeredSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(LayeredSecurityApplication.class, args);
    }
}
```

## 5. Configuring HTTP and reactive method security together

**`src/main/java/example/layered/ReactiveSecurityConfiguration.java`**:

```java
package example.layered;

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
public class ReactiveSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-test-password"))
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("local-test-password"))
                .roles("READER")
                .build();

        UserDetails charlie = User.withUsername("charlie")
                .password(encoder.encode("local-test-password"))
                .roles("VIEWER")
                .build();

        UserDetails auditor = User.withUsername("auditor")
                .password(encoder.encode("local-test-password"))
                .roles("AUDITOR")
                .build();

        UserDetails chief = User.withUsername("chief")
                .password(encoder.encode("local-test-password"))
                .authorities("ROLE_AUDITOR", "AUDIT_VIEW")
                .build();

        return new MapReactiveUserDetailsService(
                alice, bob, charlie, auditor, chief);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/documents/{id}/audit")
                            .hasRole("AUDITOR")
                        .pathMatchers(HttpMethod.GET, "/documents/{id}")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**This is where both security layers are activated:**

1. `@EnableWebFluxSecurity` creates the HTTP security filter infrastructure.
2. `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` registers Spring AOP method interceptors, including `@PreAuthorize`. The Spring Boot Security starter alone does not ensure method annotations run without this annotation.
3. HTTP Basic verifies usernames/passwords; demo accounts use `PasswordEncoder` to generate algorithm-prefixed BCrypt hashes instead of `{noop}`.
4. The path matcher for `/documents/{id}/audit` precedes the document-read matcher to keep specificity clear; `anyExchange().denyAll()` is the catch-all rule.
5. On `GET /documents/{id}`, HTTP requires only authentication; **role and ACL checks live in the service**. This is intentional rather than a flaw, because every document-retrieval path must go through the protected service and the repository filters data as well.
6. On the audit URL, HTTP requires `ROLE_AUDITOR` and the method also requires `AUDIT_VIEW`. There is no "either/or" behavior here.
7. Demo usernames/passwords are strictly for localhost and integration tests; production uses a properly managed user store.
8. Default CSRF is not disabled. The example uses only GET; for POST/PUT/DELETE and cookie-based auth, CSRF design must be verified separately.

### Warning when adding rules

If you place `.anyExchange().permitAll()` before protected matchers, subsequent rules will never be reached. If you declare multiple `SecurityWebFilterChain` beans, Spring Security picks **one** chain by matcher and order, so verify which chain receives each URL. Method security is independent of HTTP matchers, yet does not automatically protect endpoints that never invoke an annotated method.

## 6. Reactive repository reading ACLs and conditioned data

**`src/main/java/example/layered/DocumentRepository.java`**:

```java
package example.layered;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentRepository {

    private final DatabaseClient database;

    public DocumentRepository(DatabaseClient database) {
        this.database = database;
    }

    public Mono<Boolean> hasReadPermission(String username, long id) {
        return database.sql("""
                    SELECT 1 AS allowed
                      FROM document_permissions
                     WHERE document_id = :documentId
                       AND username = :username
                       AND permission = 'READ'
                    """)
                .bind("documentId", id)
                .bind("username", username)
                .fetch()
                .first()
                .hasElement();
    }

    public Mono<String> findVisibleBody(String username, long id) {
        return database.sql("""
                    SELECT d.body
                      FROM documents d
                     WHERE d.id = :documentId
                       AND EXISTS (
                           SELECT 1
                             FROM document_permissions p
                            WHERE p.document_id = d.id
                              AND p.username = :username
                              AND p.permission = 'READ'
                       )
                    """)
                .bind("documentId", id)
                .bind("username", username)
                .map((row, metadata) -> row.get("body", String.class))
                .one();
    }
}
```

**Why are there two queries?**

- `hasReadPermission` checks the ACL in **method authorization**. `.fetch().first().hasElement()` returns a `Mono<Boolean>` that always emits `true/false` when the query succeeds. If no row exists, it emits `false`; if the DB errors, the publisher signals `onError`.
- `findVisibleBody` returns document content only if the data query **still** satisfies the ACL. This extra guard prevents controllers or other callers from reading a body if permissions changed or a code path bypassed the method check.
- Queries use `.bind(...)` for parameter binding rather than concatenating username/id into SQL, preventing SQL injection.
- There is no `block()` or `subscribe()`. Spring WebFlux and method interceptors subscribe to the needed publishers during the request.
- When performance matters, you can optimize query count, yet never drop owner/tenant/ACL predicates in data access simply because HTTP already checked once.

**TOCTOU:** permissions can be revoked between the authorization query and the body query. `findVisibleBody` ensures every data read re-enforces the ACL at query execution time. If business rules demand stronger snapshots or atomicity, use transaction isolation and concurrency tests rather than relying merely on two separate reads.

## 7. Permission-checking bean returning Mono<Boolean>

Spring Security 6.5 supports expressions invoking a bean whose method can return **`Boolean` or `Mono<Boolean>`** for `@PreAuthorize`. This separates complex SQL/logic from SpEL while staying non-blocking.

**`src/main/java/example/layered/DocumentPolicy.java`**:

```java
package example.layered;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<Boolean> canRead(Authentication authentication, Long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken
                || id == null || id <= 0) {
            return Mono.just(false);
        }

        boolean readerRole = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        "ROLE_READER".equals(authority.getAuthority()));
        if (!readerRole) {
            return Mono.just(false);
        }

        return repository.hasReadPermission(authentication.getName(), id);
    }
}
```

**How to read the logic:**

1. `Authentication` must be non-null, valid, and not an `AnonymousAuthenticationToken`. Do not trust `isAuthenticated()` alone: anonymous tokens in Spring Security can be constructed with authenticated set to true.
2. ID must be meaningful; null/non-positive IDs are denied.
3. The functional layer requires authority `ROLE_READER`.
4. The data layer checks the ACL by username + id, returning `Mono<Boolean>`. Spring Security method authorization awaits this decision without blocking the event loop.
5. Missing ACL -> `Mono.just(false)` via `hasElement()`, ensuring **explicit denial**.
6. SQL timeout/connection error -> `Mono.error(...)` is propagated, **never** turned into `true` or silent access grants.

### Never do this

```java
// Anti-pattern: blocks the WebFlux processing thread
boolean allowed = repository
        .hasReadPermission(authentication.getName(), id)
        .block();

// Anti-pattern: database error grants access
return repository.hasReadPermission(authentication.getName(), id)
        .onErrorReturn(true);

// Anti-pattern: mutates async variable and returns immediately
AtomicBoolean allowed = new AtomicBoolean(false);
repository.hasReadPermission(authentication.getName(), id)
        .subscribe(allowed::set);
return Mono.just(allowed.get());
```

The snippet above only illustrates **mistakes**, not a standalone program. Wrapping `Mono.just(blockingCall())` does not make a blocking library non-blocking either: the call executes before the `Mono` is created.

If an application cannot replace JDBC yet, isolate blocking I/O with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with resource bounds, timeouts, and load testing; that is a transitional workaround, **not equivalent** to an R2DBC driver.

### What does Mono.empty() mean in method authorization?

Per Spring Security reactive method security docs, an authorization bean can return `Mono.empty()` to **abstain** (make no decision). For "no ACL found", we want **deny**, so we return `Mono.just(false)`. Never accidentally return `Mono.empty()` on the branch where a user lacks an ACL assuming it always means "deny".

## 8. Service protected by @PreAuthorize

**`src/main/java/example/layered/DocumentService.java`**:

```java
package example.layered;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public Mono<String> readDocument(Long id) {
        return ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        context.getAuthentication().getName())
                .flatMap(username ->
                        repository.findVisibleBody(username, id));
    }

    @PreAuthorize("hasAuthority('AUDIT_VIEW')")
    public Mono<String> auditDocument(Long id) {
        return Mono.just("Audit document " + id);
    }
}
```

### Why use #p0?

`#p0` refers to the **first parameter** in Spring Method Security expressions, avoiding dependence on whether the compiler retains Java parameter names via `-parameters`. You can also use `#id` when parameter names are discoverable, such as via `@P("id")` or builds configured with parameter metadata. If renaming a parameter drifts from the expression, policy may misbehave or fail; write tests for variables used in authorization.

### Why does readDocument check the ACL twice?

On the service, `@PreAuthorize` calls `DocumentPolicy.canRead(authentication, id)` before executing the method body. If it passes, `readDocument` reads the username via `ReactiveSecurityContextHolder` and queries the repository with the ACL condition. Two queries are a trade-off between **defense-in-depth** and performance; in production systems, you can consolidate the check + data fetch into one service-controlled query while keeping role/entry checks explicit.

### Why does auditDocument have only one annotation?

The HTTP rule `hasRole("AUDITOR")` and method rule `hasAuthority("AUDIT_VIEW")` form a two-layer AND. You don't need to stuff both into one annotation when illustrating boundaries. However, if `auditDocument` is also called from batches/messages where **no HTTP filter exists**, `ROLE_AUDITOR` is not checked by the current method alone. For business policies requiring both privileges regardless of caller origin, put both right on the method:

```java
// Stricter option for services with multiple entry points:
@PreAuthorize("hasRole('AUDITOR') and hasAuthority('AUDIT_VIEW')")
public Mono<String> auditDocument(Long id) {
    return Mono.just("Audit document " + id);
}
```

This is an **alternative variant** of `auditDocument` in the file above; do not declare two methods with the same signature. For this lesson, the primary snippet intentionally checks only `AUDIT_VIEW` on the service to highlight the two layers' distinct responsibilities; in production, **put mandatory business conditions at the service layer** and use HTTP filters as a perimeter pre-filter.

### About @PostAuthorize

`@PostAuthorize` checks permissions on the **result**. Conceptual example:

```java
// Illustrative snippet using a Document type with an owner property:
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Document> findDocument(Long id) {
    return repository.findById(id);
}
```

This is an **illustrative** snippet; the `Document` class and `findById` repository method are not defined in the demo app. In reactive method security, `@PostAuthorize` can inspect the element emitted by a publisher before the caller receives it; however, the read has already happened, and prior side effects may have occurred. For money transfers, document deletions, or database updates, **never use `@PostAuthorize` alone to stop dangerous actions**. Prefer `@PreAuthorize` + query/transaction conditions.

## 9. WebFlux controller calling the service through a Spring proxy

**`src/main/java/example/layered/DocumentController.java`**:

```java
package example.layered;

import org.springframework.http.ResponseEntity;
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

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/documents/{id}")
    public Mono<ResponseEntity<String>> read(@PathVariable Long id) {
        return documents.readDocument(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping("/documents/{id}/audit")
    public Mono<String> audit(@PathVariable Long id) {
        return documents.auditDocument(id);
    }
}
```

Constructor injection provides the Spring-managed `DocumentService`, meaning calls to `documents.readDocument(id)` go **through the method-security proxy**. Avoid `new DocumentService(...)` inside controllers, which skips the bean lifecycle and interceptors. `read` neither checks authorities manually in the controller nor accepts a username from query strings as a trusted principal.

If `readDocument` emits `AccessDeniedException`, WebFlux security exception translation can return 403 for **authenticated** users. If an anonymous user hits an authentication-required URL, the HTTP Basic entry point usually returns 401. If the query returns `Mono.empty()` because data disappeared after the pre-check passed, the controller can return 404. Never write `onErrorResume(AccessDeniedException.class, ... return ResponseEntity.ok(...))`, as that serves data upon denial.

### Flow of a typical request

```text
GET /documents/100 - Basic alice/password
    -> HTTP authenticated()                  PASS
    -> method @PreAuthorize
          ROLE_READER                       PASS
          ACL Alice reads document 100      PASS
    -> repository query with ACL            PASS
    -> 200 "Internal plan A"

GET /documents/200 - Basic alice/password
    -> HTTP authenticated()                  PASS
    -> method @PreAuthorize
          ROLE_READER                       PASS
          ACL Alice reads document 200      DENY
    -> controller receives no body
    -> 403

GET /documents/100/audit - Basic auditor/password
    -> HTTP hasRole("AUDITOR")               PASS
    -> method hasAuthority("AUDIT_VIEW")     DENY
    -> 403

GET /documents/100/audit - Basic alice/password
    -> HTTP hasRole("AUDITOR")               DENY
    -> method does not run
    -> 403
```

HTTP-before-method ordering is the **order for this HTTP request**. When a service is invoked outside HTTP, it has no HTTP gate step and must enforce appropriate rules right at the method/data level.

## 10. Testing HTTP and standalone methods

The project adds `spring-security-test` and `reactor-test` to verify each layer. A test that only mocks roles at HTTP can miss bugs in SQL ACLs. This lesson uses real H2 R2DBC in tests to verify both policies and data.

**`src/test/java/example/layered/LayeredSecurityIntegrationTest.java`**:

```java
package example.layered;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LayeredSecurityIntegrationTest {

    @Autowired WebTestClient client;
    @Autowired DocumentService documents;
    @Autowired DocumentRepository repository;

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotReadDocument() {
        client.get().uri("/documents/100").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceCanReadHerDocument() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth(
                        "alice", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Internal plan A");
    }

    @Test
    void aliceCannotReadBobsDocument() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth(
                        "alice", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void bobCanReadHisDocument() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth(
                        "bob", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Private plan B");
    }

    @Test
    void aclWithoutReaderRoleIsNotEnough() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth(
                        "charlie", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void httpAuditorWithoutMethodPermissionIsDenied() {
        client.get().uri("/documents/100/audit")
                .headers(h -> h.setBasicAuth(
                        "auditor", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerIsDeniedAuditAtHttpLayer() {
        client.get().uri("/documents/100/audit")
                .headers(h -> h.setBasicAuth(
                        "alice", "local-test-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void auditorWithAdditionalAuthorityCanReadAudit() {
        client.get().uri("/documents/100/audit")
                .headers(h -> h.setBasicAuth(
                        "chief", "local-test-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Audit document 100");
    }

    @Test
    void wrongPasswordCannotReadDocument() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth(
                        "alice", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void repositoryReturnsExplicitAclDecision() {
        StepVerifier.create(repository.hasReadPermission("alice", 100))
                .expectNext(true).verifyComplete();
        StepVerifier.create(repository.hasReadPermission("alice", 200))
                .expectNext(false).verifyComplete();
    }

    @Test
    void serviceDirectCallSucceedsWithMatchingReactorContext() {
        Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(documents.readDocument(100L)
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(alice)))
                .expectNext("Internal plan A")
                .verifyComplete();
    }

    @Test
    void serviceDirectCallIsDeniedWithoutAcl() {
        Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(documents.readDocument(200L)
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(alice)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void serviceDirectCallWithoutPrincipalIsDenied() {
        StepVerifier.create(documents.readDocument(100L))
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
```

Command to run from a project with Gradle Wrapper:

```bash
./gradlew test --tests example.layered.LayeredSecurityIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.layered.LayeredSecurityIntegrationTest
```

**Expected result:** 14 PASSing tests on a project properly configured with matching files and dependencies compatible with Spring Boot 3.x/Spring Security 6.5. This is an **expected outcome**, not a log of an actual test run in your environment.

### What did the tests prove?

| Test group | What was verified |
| --- | --- |
| Public and anonymous | HTTP filter allows public; `authenticated` blocks anonymous |
| Alice/Bob/Charlie | HTTP authentication alone is insufficient; method also checks ROLE_READER and real ACL |
| Auditor/chief | HTTP role gate + method authority gate are two independent conditions |
| Wrong password | Authentication fails before reaching the service |
| `repositoryReturnsExplicitAclDecision` | R2DBC query returns `true/false` for permitted or unpermitted data |
| Direct service call with Reactor Context | Spring proxy method security applies even without a controller |
| Direct service call lacking permission | Method denies with `AccessDeniedException`, without needing an HTTP status |
| Direct service call without context | Does not invent an identity; denies access |

**Do not conclude `WebTestClient` tests alone are enough.** Direct service tests matter because they catch inactive annotations caused by missing `@EnableReactiveMethodSecurity`, unproxied calls, or lost Reactor Context.

### About HTTP status when unauthorized/forbidden

In the HTTP Basic demo:

- Anonymous requests to authenticated URLs usually receive **401** with an HTTP Basic challenge.
- Authenticated requests denied at HTTP or method layers usually receive **403**.
- When a service/controller intentionally returns `Mono.empty()` after being permitted, the controller can return **404**.
- When the database fails, return an appropriate system error response (usually 5xx); **never turn SQL errors into 200 or "forbidden", losing telemetry**.

If switching to form login, anonymous requests are normally **redirected to the login page** instead of 401. With a JWT resource server, invalid/expired tokens may return 401 depending on the entry point. Do not hardcode one status table as an immutable API contract when changing authentication mechanisms.

## 11. AOP mistakes that cause @PreAuthorize to be skipped

Reactive method security uses Spring AOP proxies. Therefore you must understand **calls through proxies**.

### 11.1. Self-invocation

```java
@Service
public class BadExampleService {

    public Mono<String> outer() {
        // Anti-pattern: internal call via this, may bypass proxy.
        return this.sensitive();
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> sensitive() {
        return Mono.just("secret");
    }
}
```

This is a **standalone anti-pattern class for explanation**, not to be added to the main demo. When `outer()` calls `this.sensitive()` on the same instance, the call normally bypasses the proxy, so `sensitive()`'s interceptor does not run. If `outer()` is exposed, that is a vulnerability. Fix: extract `sensitive()` to a separate bean and call the injected bean, or place protection on the entry method itself; write tests calling that exact code path.

### 11.2. Instantiating services with `new`

```java
// Anti-pattern: bean does not go through Spring context/proxy.
DocumentService service = new DocumentService(repository);
service.readDocument(100L);
```

This illustrative code **bypasses AOP**, unlike `@Autowired DocumentService` or Spring constructor injection. Never manually create protected beans with `new` and expect annotations to enforce rules.

### 11.3. Private, final, and misplaced annotations

A Spring AOP proxy cannot intercept arbitrary calls:

- Private methods cannot be called externally through normal proxies.
- Final classes/methods can prevent subclass-based (CGLIB) proxies from intercepting; JDK interface proxies have different constraints.
- Annotations on methods that are not the actual entry point may never execute.
- When changing class/interface proxies, test actual bean wiring paths.
- Calling methods from code running **inside constructors/`@PostConstruct`** before the proxy is finalized is unsuitable for relying on method security.

**Rule:** place annotations on public service methods, invoke via Spring beans, guard every entry point capable of reaching business operations, and test direct service calls.

### 11.4. @PreAuthorize not enabled at all

You can write `@PreAuthorize` accurately yet have zero interceptors if you forgot `@EnableReactiveMethodSecurity`. Enable the annotation on a `@Configuration` class and use failing tests to confirm. Do not infer that "HTTP Basic works" means method security is active too.

## 12. Context for non-HTTP callers: schedulers, messages, and WebSockets

HTTP Basic/session/JWT filters usually populate `Authentication` in Reactor Context when requests flow through WebFlux. However, scheduled tasks or message consumers do not automatically carry an HTTP user's identity.

Example calling a service in tests with an **intentional** mock Authentication:

```java
Authentication principal =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "unused",
            List.of(new SimpleGrantedAuthority("ROLE_READER")));

Mono<String> result = documents.readDocument(100L)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(principal));
```

This fragment needs the imports already shown in the test, **and is not a way for clients to pick their own identity**. Only test infrastructure or a trusted component may supply such an `Authentication`. In production, background workers should use a service identity or a dedicated audited policy; never assign fake `ROLE_ADMIN` just to "make the job run".

If you invoke `documents.readDocument(100L)` in a job without context:

- Method security may deny it (which is desired if policy requires an end user).
- Or you must design a dedicated API/service with a system policy rather than blindly deleting annotations.
- Never call `subscribe()` inside a service expecting HTTP's Reactor Context to carry over into a completely independent subscription.

When exposing WebSockets, RSocket, or consumers, enforce entry-point controls, identity mapping, cross-tenant permissions, and method security as well; HTTP authorization only covers HTTP requests it actually handles.

## 13. Performance, transactions, and consistency

### 13.1. Multiple queries per request may occur

A valid GET document request in the example typically runs:

1. HTTP Basic authenticating the user in memory (production may add I/O).
2. `DocumentPolicy.canRead` querying the ACL via R2DBC.
3. Repository `findVisibleBody` querying the document with the ACL predicate.

Two data queries protect well yet carry cost. Under high traffic:

- Measure p50/p95/p99 for authorization + DB, as well as connection pool acquisition wait.
- Design queries with proper indexes on `document_id, username, permission`; check query plans on real PostgreSQL.
- You can merge ACL and body retrieval into a single service query if policy stays clear and object-level checks remain enforced.
- For sensitive data, never remove SQL owner/tenant barriers just to save one query.
- If caching ACLs, enforce TTL/invalidation upon permission revocation; stale caches can continue granting access wrongly.
- Bound connection pools, query timeouts, concurrency, and retries. Reactive non-blocking **does not create infinite DB capacity**.

### 13.2. Database failures must fail closed

When permissions are decided by a database:

- Missing ACL row means **deny**.
- SQL timeouts, lost connections, and exhausted pools mean **unable to verify permissions**. The request must not be permitted; errors must be logged/monitored safely.
- Never use `onErrorReturn(true)`, `onErrorResume(ex -> Mono.just(true))`, or any fallback granting access because the system "needs high availability".
- If you want 503 instead of 500 when the authorization DB is unavailable, map infrastructure exceptions to service-unavailable **without returning protected content**. Avoid collapsing all errors into 403 and losing operational visibility.
- Never log raw passwords, Authorization headers, JWTs, password hashes, cookies/sessions, or full document contents in error traces.

### 13.3. TOCTOU: permissions changing between two points in time

*Time-of-check to time-of-use* happens when an ACL is valid during the method check yet revoked before the body query. A second query with the ACL reduces this window. For write operations like money transfers or document deletions, enforce permissions inside the same transaction or use SQL `UPDATE ... WHERE id=:id AND tenant_id=:tenantId AND EXISTS (...)` so conditions are checked atomically at write time.

Do not assume reactive transactions are created by `@Transactional` on a method that returns no publisher and calls `subscribe()` manually. With R2DBC, use a reactive transaction manager and preserve subscription context; design isolation per business rules and test real race conditions.

### 13.4. Role changes between request and service

HTTP authorization reads the request's `Authentication`; roles inside `Authentication` may have been loaded earlier from a token/session. If an admin revokes a role, an old session/JWT may still hold stale authorities. Method security using the **same Authentication** will not detect the revoked role automatically unless designed to re-query or revoke tokens/sessions.

Therefore:

- Define acceptable permission-revocation latency.
- Consider short-lived tokens, forced re-authentication, cache invalidation, live lookups, or version-based permission models.
- Separate static roles in Authentication from dynamic resource ACLs in the database; test revocation policies.
- Never trust client-set `X-User`/`X-Tenant` headers as principals, and never use unverified tenant IDs to query ACLs.

## 14. Testing strategy to prevent "fake" protection

A thorough test suite should verify **both directions**:

| Scenario | HTTP test | Service test |
| --- | --- | --- |
| Anonymous hits protected URL | 401/login redirect | Missing Reactor Context must deny |
| Logged in yet lacks HTTP role | 403 before controller | Says nothing about method unless called separately |
| Passes HTTP yet lacks method authority | 403 | Direct call with matching role throws `AccessDeniedException` |
| Has role yet lacks ACL | 403 | Direct call is denied |
| Has ACL yet lacks role | 403 | Policy denies |
| Has both role and ACL | 200, expected body | Publisher emits expected data |
| Wrong ID/tenant | 400/403/404 per policy | Never returns out-of-scope data |
| Database error | Does not return protected data | Publisher errors; never grants access |
| Self-invocation | May go undetected by controller test alone | Write tests specifically for internal call paths |
| Stale cache after revocation | Measure behavior across sequential requests | Verify policy expiration/invalidation |

`@WithMockUser`/`mockUser()` are helpful for testing roles and method authorization, yet **do not verify real password/token ingestion**. For sensitive features, add integration tests with real authentication, expired/invalid tokens, and role mapping.

### 401, 403, and 404 are not interchangeable

- **401 Unauthorized:** authentication failed or was omitted when using an appropriate Basic or Bearer entry point.
- **403 Forbidden:** authenticated, yet authorization failed at the HTTP or method layer. CSRF filters can also yield 403 on unsafe methods lacking a token — distinguish the root cause.
- **404 Not Found:** resource does not exist or policy intentionally hides existence. Never convert 403 to 404 without consistent design.

In reactive WebFlux, `AccessDeniedException` is translated into an HTTP response by Web Security exception handling when raised in the HTTP pipeline. When calling a service directly without HTTP, the caller receives the error from the publisher with **no HTTP status** to inspect.

## 15. Common mistakes

| Implementation mistake | Consequence | Fix |
| --- | --- | --- |
| Only `authorizeExchange`, omitting method security | Service can be called from jobs/other endpoints without checks | Enable `@EnableReactiveMethodSecurity`, guard public service methods |
| Only `@PreAuthorize` while HTTP is overly permissive | Other endpoints not calling that service are exposed | Use specific rules and `anyExchange().denyAll()` |
| Mistakenly using Servlet `@EnableMethodSecurity` | Config/semantics mismatch reactive method flow | Use `@EnableReactiveMethodSecurity` |
| Service returns plain object, blocks Mono manually | Can lose reactive context or block event loop | Return `Mono`/`Flux` on protected methods |
| `this.protectedMethod()` | Call bypasses proxy so annotations don't run | Extract bean, invoke through Spring proxy |
| `new DocumentService(...)` | No Spring AOP proxy | Inject Spring-managed bean |
| Private/final methods or wrong proxy | Interceptor fails to execute as expected | Public methods, check proxy and test |
| Passing username from request param into ACL | Users can spoof principals | Read from trusted `Authentication` |
| Only `hasRole("READER")` for all documents | Users read documents they don't own | Add object-level ACL checks |
| Has ACL without role / has role without ACL | OR logic accidentally grants access | Design AND conditions, test all combinations |
| `Mono.empty()` when wanting deny | May be interpreted as abstain in method-security expressions | Return `Mono.just(false)` |
| `onErrorReturn(true)` on DB failure | Data leak on connection loss | Fail closed with clear telemetry |
| Manual `block()` or `subscribe()` | Event loop blocking, races/lost Reactor Context | Compose publishers properly |
| Using `map` with a function returning `Mono` | Produces `Mono<Mono<T>>` | Use `flatMap` |
| Misplaced `anyExchange().permitAll()` | Bypasses HTTP restrictions | Put specific rules first, catch-all last |
| Caching permissions without invalidation | Revoked users retain access | TTL/invalidation/live checks |
| Omitting tenant predicate in SQL | Cross-tenant data leakage | Verified tenant context + query constraints |
| Tests asserting only 200 | Fails to catch security holes | Test 401/403 denials, direct service, revocation, missing context |
| Using `@PostAuthorize` to guard write commands | Side effects may occur before denial | Check beforehand and enforce in transactions/queries |

## 16. Extension exercises

1. Add user `dave` with `ROLE_READER` but no ACL; prove HTTP lets him pass while the method denies. Then add an ACL row and verify the result becomes 200.
2. Place `@PreAuthorize("hasRole('AUDITOR') and hasAuthority('AUDIT_VIEW')")` on the audit service; write direct service tests proving missing either condition denies even outside HTTP.
3. Create a separate `DocumentAdminService` with `@PreAuthorize("hasRole('ADMIN')")`; write a `public` method in another service calling it via bean proxy and an internal self-invocation anti-pattern. Compare results.
4. Temporarily remove `@EnableReactiveMethodSecurity` in a test branch: confirm direct service tests fail, proving tests catch missing interceptors.
5. Switch principal from username to verified ID/tenant; add `tenant_id` to ACL and document tables, blocking Alice of tenant A from reading tenant B's documents.
6. Use R2DBC PostgreSQL and versioned migrations; measure ACL method latency, connection pool acquisition, timeouts, and compare two queries vs. a single predicated query.
7. Add a database-unavailable test and prove the endpoint never returns 200 even when the `Authentication` role is valid.
8. Add a `Flux<Document>` listing multiple documents: enforce policy directly in SQL rather than loading everything and calling `filter` too late on the stream.
9. Design a message consumer path calling the document service: define permitted service identities, attach Reactor Context only from trusted sources, and test denial when context is absent.
10. Upgrade Spring Security version; review docs for `@EnableReactiveMethodSecurity`, `@PreAuthorize`, reactive `Mono<Boolean>` beans, request matchers, and deprecation changes before editing code.

## Summary

- **HTTP authorization** decides which requests reach controllers: path, HTTP method, authenticated status, roles/authorities.
- **Reactive method authorization** guards business invocations whether initiated by controllers, other services, or messages/jobs; it relies on Spring AOP and Reactor Context.
- For the same HTTP request, **HTTP must allow and the method must allow**; neither layer automatically unlocks the other.
- `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` enables proxies/interceptors; `@PreAuthorize` can invoke beans returning `Mono<Boolean>` for non-blocking ACL checks.
- **Never use** `block()`, manual `subscribe()`, permit-on-DB-error fallbacks, internal `this` calls to protected methods, or client-declared usernames/tenants.
- Sensitive data needs additional constraints in queries/transactions, because HTTP and method checks do not replace full data-access security.
- Test both HTTP and direct service paths with `WebTestClient`/`StepVerifier`; after permissions are revoked, verify old data is no longer accessible.

## Official documentation

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — EnableReactiveMethodSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Framework — R2DBC DatabaseClient](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Boot — SQL Databases and R2DBC](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Security — Reactive Method Security migration/latest](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
