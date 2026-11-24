# Non-Blocking Reactive Data Permission Lookup in Spring Security WebFlux

## Learning Objectives

After this lesson, you can:

1. Distinguish **authentication** (who is calling), **authorization** (whether access is allowed), and **per-resource permission checks** (ABAC/ACL) in an HTTP request.
2. Understand the role of `ReactiveAuthorizationManager<AuthorizationContext>` and how to wire it into `ServerHttpSecurity.authorizeExchange(...).access(...)`.
3. Read the principal and path variables from the request context, query ACLs via R2DBC/`DatabaseClient`, and return `Mono<AuthorizationDecision>` **without calling `block()`**.
4. Enforce **deny by default**, distinguishing missing permissions from database errors; never accidentally grant access due to `Mono.empty()`, timeouts, or SQL injection.
5. Build a Java 17+ Spring Boot WebFlux application with two users, an H2 R2DBC database, a document-reading API, and `WebTestClient` tests.
6. Evaluate performance, TOCTOU, caching, auditing, and service-layer authorization for PostgreSQL deployments.

> Illustrated versions: **Spring Boot 3.x with Spring Security 6.5.x**, Java 17+. Reactive APIs use `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveAuthorizationManager`, `Mono`, and `Flux`. Spring Security 6.5 marks `check(...)` as deprecated in favor of `authorize(...)`; the 6.5 example uses `check(...)` because it remains the interface's abstract method in this version. If upgrading to Spring Security 7.x, verify the interface contract before migrating code.

## 1. Practical Problem: A Generic Role Is Not Enough

Suppose a system has the API:

```text
GET /documents/100
GET /documents/200
```

Both `alice` and `bob` have role `ROLE_READER`. If you only write:

```java
.pathMatchers("/documents/**").hasRole("READER")
```

then **both** can read every document, unless business logic at a later layer checks further. In reality, Alice may only read document 100 and Bob may only read document 200. The rule must inspect both **principal** and **document ID**:

```text
CanRead(username, documentId) =
  user is authenticated
  AND has ROLE_READER
  AND database has READ permission for username + documentId
```

This is **object-level authorization**, implementable via ACLs (Access Control Lists) or attributes (ABAC). URL checks do not replace applying the same principle in the service/repository where actual data is fetched.

| Decision Type | Example | Common Approach |
| --- | --- | --- |
| Authentication only | Any logged-in user can view `/profile` | `authenticated()` |
| Static role/authority | Only ADMIN enters `/admin/**` | `hasRole("ADMIN")` |
| Per-resource permission | Alice reads document 100 but not 200 | `.access(customReactiveManager)` querying ACL |
| Attribute-based permission | Order handler in same department and order is OPEN | Business rules + conditional data query |
| Service-layer permission | Fetch only records allowed for owner/tenant | Query filtered by principal, method security, or both |

**Principle:** client-supplied data (IDs, tenant headers, query params) is never proof that the caller has permission. Always compare against the authenticated identity and server-side policy.

## 2. Why Non-Blocking Is Mandatory in WebFlux

Spring WebFlux builds on Reactor to express asynchronous pipelines. When an HTTP request flows through the authorization `WebFilter`, Spring Security awaits a **publisher** returning the decision. If you call blocking JDBC or `.block()` directly on the Reactor Netty event loop, the thread is held waiting on the database, increasing latency and limiting concurrent requests.

| Approach | Issue / Benefit |
| --- | --- |
| `jdbcRepository.find(...);` inside an HTTP filter | Synchronous I/O can block the event loop |
| `Mono.just(jdbcRepository.find(...))` | Still calls JDBC **eagerly when creating the Mono**, not non-blocking |
| `databaseClient.sql(...).fetch().first()` from R2DBC | Returns a `Mono` and executes on subscription |
| `permissionMono.block()` | Waits synchronously; may error on non-blocking threads |
| `permissionMono.flatMap(...)` or `map(...)` | Chains authorization logic onto the same pipeline |
| Manual `permissionMono.subscribe()` in manager | Detaches from request lifecycle; may return decision before DB finishes |
| `Mono.fromCallable(blockingIo).subscribeOn(boundedElastic())` | **Isolates blocking** when a blocking library is unavoidable; does not make the driver reactive |

R2DBC (Reactive Relational Database Connectivity) queries relational databases through a reactive driver. With Spring Boot, `ConnectionFactory` is configured via `spring.r2dbc.*`; `DatabaseClient` builds SQL statements and returns publishers. When a query fails, the publisher emits `onError`—never turn all errors into `true` or silently fall back to allowing access.

### Authorization Chain Diagram

```text
Client GET /documents/100 + HTTP Basic
           |
           v
Spring Security WebFilter chain
           |
           +--> Authentication filters:
           |      verify username/password -> Authentication
           |
           +--> AuthorizationWebFilter
                  |
                  +--> Path matcher /documents/{id}
                  |        -> AuthorizationContext:
                  |           {id = "100"}
                  |
                  +--> ReactiveAuthorizationManager.check(
                  |        Mono<Authentication>, context)
                  |              |
                  |              +--> username = alice
                  |              +--> verify ROLE_READER
                  |              +--> database check (R2DBC)
                  |                       |
                  |                       +--> ACL row exists -> true
                  |                       +--> no ACL row     -> false
                  |
                  +--> Mono<AuthorizationDecision>
                          |
                          +--> granted=true  -> controller
                          +--> granted=false -> 403 (authenticated)
                          +--> no identity   -> 401 (Basic entry point)
```

The same manager can also be applied to multiple URLs, but verify each matcher's path variables and semantics; never create a manager that misreads a variable and permits by default.

## 3. Contract of ReactiveAuthorizationManager

Spring Security 6.5 defines `org.springframework.security.authorization.ReactiveAuthorizationManager<T>`. For WebFlux HTTP, `T = AuthorizationContext` is typically used.

Corresponding signatures in 6.5:

```java
// Interface signature for explanation, not a standalone program:
Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        AuthorizationContext context);

// From 6.4 onward, a new default method was added:
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication,
        AuthorizationContext context);
```

In Spring Security 6.5, `check` is marked deprecated, yet it remains the abstract method many existing implementations override; `authorize` by default can delegate to `check`. When coding to the 6.5 baseline, implementing `check` remains valid. In newer versions, check the API docs before switching to `authorize`; do not mechanically change the return type from `Mono<AuthorizationDecision>` to `Mono<AuthorizationResult>` if the compiler does not match.

In HTTP rules:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/documents/{id}")
            .access(documentAuthorizationManager)
        .anyExchange().denyAll()
)
```

- `pathMatchers(...)` selects requests by HTTP method and path pattern; rule order matters.
- `AuthorizationContext.getVariables()` provides template variables, e.g., `id`.
- `AuthorizationContext.getExchange()` provides request/headers/remote address and other data if needed; never trust caller-set headers as permissions.
- `authentication` is a publisher and may be empty; never call `authentication.block()` or Servlet-style `authentication.get()`.
- `AuthorizationDecision(true)` grants access, `AuthorizationDecision(false)` denies. `Mono.empty()` can be interpreted as **abstain/no decision**, and should not be used to handle missing users or missing ACLs when a policy intends explicit denial.

### Fail Closed vs. "Hiding All Errors"

Two situations must be kept separate:

1. Missing ACL row: this is an **unauthorized decision**, returning `AuthorizationDecision(false)`.
2. Database timeout/connection failure: this is an **infrastructure error**; the request must not be granted access, and the error should be recorded as a system failure rather than coerced into "no ACL exists" and hiding monitoring signals.

Never write `onErrorReturn(new AuthorizationDecision(true))` or `onErrorResume(ex -> Mono.just(new AuthorizationDecision(true)))`. In the demo, R2DBC errors **propagate** up the pipeline to be handled by server error handling; thus access is never granted when the outcome is unknown. If a system wants to map permission-check errors to 503 instead of 500, add appropriate exception mapping/telemetry, never falling back to permit.

## 4. Building a Complete Demo: Reactive ACL Data with H2 R2DBC

We use three illustrative elements:

- `documents`: documents with an ID and body.
- `document_permissions`: which username has READ permission on which document.
- Users are authenticated with `MapReactiveUserDetailsService` **purely to demo HTTP Basic**. Per-document permissions are queried separately from the database via R2DBC.

The design separates **login** from **permission lookup**. In production, usernames should be replaced with an **immutable principal ID** from the identity provider/database, with proper tenant constraints, rather than mutable display names.

### 4.1. Gradle Dependencies

A Java 17 Spring Boot 3.x project with Spring Boot/Dependency Management plugins already configured needs:

**`build.gradle`** (dependencies section):

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

Do not add `spring-boot-starter-web` in a pure WebFlux demo because Spring Boot usually prefers Servlet if both MVC and WebFlux starters exist.

### 4.2. R2DBC Configuration and Test Data

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: reactive-document-authorization
  r2dbc:
    url: "r2dbc:h2:mem:///permissiondb?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
  sql:
    init:
      mode: always
      schema-locations: "classpath:schema.sql"
      data-locations: "classpath:data.sql"

server:
  port: 8080
```

The `r2dbc:h2:...` URL is for R2DBC, not `jdbc:h2:...`. In-memory H2 is used for learning and testing; `spring.sql.init.mode=always` is only appropriate when intentionally seeding demo schema/data. Production should use versioned migrations and dedicated secrets/DBs.

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS documents (
    id BIGINT PRIMARY KEY,
    body VARCHAR(2000) NOT NULL
);

CREATE TABLE IF NOT EXISTS document_permissions (
    document_id BIGINT NOT NULL,
    username VARCHAR(120) NOT NULL,
    permission VARCHAR(30) NOT NULL,
    PRIMARY KEY (document_id, username, permission),
    CONSTRAINT fk_document_permissions_doc
        FOREIGN KEY (document_id) REFERENCES documents(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_permissions_username
    ON document_permissions(username);
```

**`src/main/resources/data.sql`** — **non-sensitive** demo data only:

```sql
INSERT INTO documents(id, body)
VALUES (100, 'Plan A: internal'), (200, 'Plan B: private');

INSERT INTO document_permissions(document_id, username, permission)
VALUES (100, 'alice', 'READ'), (200, 'bob', 'READ');
```

Each document can be granted multiple permissions across rows. The composite primary key prevents duplicate permission rows; the foreign key prevents ACLs from pointing to nonexistent documents. In real systems, separate tenant, owner, actions (READ/EDIT/DELETE), permission-grant auditing, and controls over who may write this table.

**Behavior verified in this lesson:**

| User | Role | Document 100 | Document 200 |
| --- | --- | --- | --- |
| `alice` | `ROLE_READER` | READ | Not granted |
| `bob` | `ROLE_READER` | Not granted | READ |
| anonymous | Not logged in | No | No |

Note not to infer document permissions from `ROLE_READER` alone; the role is a necessary condition, while the ACL identifies the **specific document**.

### 4.3. Main Class

**`src/main/java/example/reactiveauthz/ReactiveAuthzApplication.java`**:

```java
package example.reactiveauthz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthzApplication.class, args);
    }
}
```

Project structure:

```text
src/
  main/
    java/example/reactiveauthz/
      ReactiveAuthzApplication.java
      DocumentPermissionRepository.java
      DocumentReadAuthorizationManager.java
      SecurityConfiguration.java
      DocumentController.java
    resources/
      application.yml
      schema.sql
      data.sql
  test/
    java/example/reactiveauthz/
      DocumentAuthorizationTest.java
```

### 4.4. Repository Querying ACL via DatabaseClient

**`src/main/java/example/reactiveauthz/DocumentPermissionRepository.java`**:

```java
package example.reactiveauthz;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentPermissionRepository {

    private final DatabaseClient client;

    public DocumentPermissionRepository(DatabaseClient client) {
        this.client = client;
    }

    public Mono<Boolean> hasReadPermission(
            String username, long documentId) {
        return client.sql("""
                    SELECT 1 AS allowed
                      FROM document_permissions
                     WHERE username = :username
                       AND document_id = :documentId
                       AND permission = 'READ'
                    """)
                .bind("username", username)
                .bind("documentId", documentId)
                .fetch()
                .first()
                .hasElement();
    }

    public Mono<String> readVisibleDocument(
            String username, long documentId) {
        return client.sql("""
                    SELECT d.body
                      FROM documents d
                      JOIN document_permissions p
                        ON p.document_id = d.id
                     WHERE d.id = :documentId
                       AND p.username = :username
                       AND p.permission = 'READ'
                    """)
                .bind("username", username)
                .bind("documentId", documentId)
                .map((row, metadata) -> row.get("body", String.class))
                .one();
    }
}
```

**Detailed explanation:**

- `DatabaseClient` uses the Spring Boot–configured R2DBC `ConnectionFactory`, returning publishers instead of blocking results.
- `:username` and `:documentId` are bound via `.bind(...)`. Never concatenate usernames or path variables directly into SQL due to SQL injection risk.
- `.fetch().first()` yields `Mono<Map<String,Object>>` for the first row; `.hasElement()` turns it into `Mono<Boolean>`: `true` if a row exists, `false` otherwise. SQL errors still emit `onError`, rather than being blindly turned into `false`.
- `readVisibleDocument` uses a **JOIN with the ACL inside the body-reading query itself**. This is *defense in depth*: even if prior HTTP authorization allowed access, the business data query still enforces the reading user. Avoid relying solely on filters when other entry points can call services/repositories directly.
- `.one()` returns `Mono<String>` for a single document. The schema's primary key/ACL prevents duplicate rows in the example.
- The repository contains no `.block()`, `.subscribe()`, or custom `ExecutorService`; the framework subscribes to the publisher when handling requests.

**Consistency note:** The authorization filter and controller run two queries, so the ACL could change between them (TOCTOU). The second query still includes the ACL to prevent reading after revocation. If security rules require an atomic snapshot or strong consistency, use business-appropriate transactions/isolation and a unified design rather than relying solely on an initial request check.

### 4.5. HTTP ReactiveAuthorizationManager

**`src/main/java/example/reactiveauthz/DocumentReadAuthorizationManager.java`**:

```java
package example.reactiveauthz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DocumentReadAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final DocumentPermissionRepository permissions;

    public DocumentReadAuthorizationManager(
            DocumentPermissionRepository permissions) {
        this.permissions = permissions;
    }

    @Override
    @SuppressWarnings("deprecation") // check() is still the abstract contract in 6.5
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object rawId = context.getVariables().get("id");
        if (rawId == null) {
            return denied();
        }

        final long documentId;
        try {
            documentId = Long.parseLong(String.valueOf(rawId));
        } catch (NumberFormatException invalidId) {
            return denied();
        }

        if (documentId <= 0) {
            return denied();
        }

        return authentication
                .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .filter(auth -> auth.getAuthorities().stream()
                        .anyMatch(authority ->
                                "ROLE_READER".equals(authority.getAuthority())))
                .map(Authentication::getName)
                .flatMap(username ->
                        permissions.hasReadPermission(username, documentId))
                .map(AuthorizationDecision::new)
                .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private Mono<AuthorizationDecision> denied() {
        return Mono.just(new AuthorizationDecision(false));
    }
}
```

**Key points in the manager:**

1. `context.getVariables().get("id")` receives the `/documents/{id}` rule's path variable. If missing or not a positive number, **return deny**; do not throw `NumberFormatException` into a 500 just because a client sent `/documents/abc`.
2. `authentication` is `Mono<Authentication>`. We use `filter` to exclude unauthenticated principals and `AnonymousAuthenticationToken`. Never rely on `isAuthenticated()` alone: anonymous tokens can also be flagged authenticated by token semantics.
3. Checking `ROLE_READER` is the functional permission layer; then `flatMap` chains the database ACL lookup.
4. `permissions.hasReadPermission(...)` returns `Mono<Boolean>`, mapped into `AuthorizationDecision`. No `block()`.
5. `defaultIfEmpty(new AuthorizationDecision(false))` guarantees an **explicit deny decision** when authentication is missing or fails the role filter, rather than leaving `Mono.empty()` as abstain and accidentally relying on another policy.
6. If R2DBC emits `onError`, the pipeline **does not grant access**; the error goes to system error handling. Never use `onErrorReturn(true)`, and never disguise it as "ACL does not exist".
7. `@SuppressWarnings("deprecation")` only suppresses compiler warnings for an example **matching the 6.5 baseline**. When upgrading to Spring Security 7.x, check the new `authorize(...)`/`AuthorizationResult` API and update tests; never copy an old interface signature to a version with a changed contract.

### Why Not Call `subscribe()` Manually?

Wrong:

```java
// Anti-pattern: callback mutates variable after decision was already returned.
AtomicBoolean allowed = new AtomicBoolean(false);
permissions.hasReadPermission(username, id)
        .subscribe(allowed::set);
return Mono.just(new AuthorizationDecision(allowed.get()));
```

At the moment `allowed.get()` runs, the value is usually still `false`; if the callback arrives later, there is also a data race and risk of losing context. A small test might "appear to work" due to timing, yet it is architecturally broken. The right way is **returning a composed `Mono`**, letting Spring Security await the publisher's decision.

### Why Not Use `block()`?

Wrong:

```java
// Anti-pattern: blocking inside WebFlux authorization
boolean granted = permissions.hasReadPermission(username, id).block();
return Mono.just(new AuthorizationDecision(granted));
```

On the Reactor Netty event loop, `block()` may be forbidden by Reactor or stall threads. If data lives in a JDBC/LDAP SDK that only supports blocking, evaluate switching drivers or isolating bounded blocking work on `Schedulers.boundedElastic()`; never wrap `Mono.just(blockingCall())` and call it reactive.

## 5. Wiring the Manager into SecurityWebFilterChain

**`src/main/java/example/reactiveauthz/SecurityConfiguration.java`**:

```java
package example.reactiveauthz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
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
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demo-only-password"))
                .roles("READER")
                .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            DocumentReadAuthorizationManager documentAuthorizationManager) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/documents/{id}")
                            .access(documentAuthorizationManager)
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

- `GET /public/ping` is open to anonymous callers.
- `GET /documents/{id}` is delegated to the custom reactive authorization manager.
- `anyExchange().denyAll()` denies other paths/methods **rather than automatically opening every request**.
- HTTP Basic illustrates authentication; production must enable TLS/HTTPS. Basic sends credentials on every request, and Base64 is not security encryption.
- `formLogin` is disabled so API clients receive a consistent HTTP Basic challenge instead of an HTML login redirect.
- CSRF **is not disabled**, though the demo only defines GET. If adding POST/PUT/DELETE with browser cookies, evaluate CSRF rather than using R2DBC as an excuse to disable protection.
- Identities `alice` and `bob` are **local fixtures**; never keep demo credentials in production. `UserDetails` contains `ROLE_READER`, yet read access to each document is still decided by the ACL table.

### Rule Order and HTTP Status

Matchers are evaluated in declaration order inside the chain. The catch-all `anyExchange().denyAll()` rule must be **last**. If you add `pathMatchers("/documents/**").permitAll()` **before** the ACL rule, every document becomes publicly open and the custom manager will not be invoked for those requests.

With HTTP Basic:

| Scenario | Expected | Reason |
| --- | --- | --- |
| `GET /public/ping` anonymous | 200 | Public |
| `GET /documents/100` anonymous | Usually 401 | Unauthenticated; Basic entry point |
| `GET /documents/100` Alice | 200 | Valid role and ACL present |
| `GET /documents/200` Alice | 403 | Logged in, missing ACL |
| `GET /documents/200` Bob | 200 | ACL present |
| `GET /documents/abc` Alice | 403 per sample policy | Invalid ID denied by manager |
| `GET /documents/999` Alice | 403 | No ACL for ID |
| `POST /documents/100` Alice | Denied (usually 403; CSRF may block first) | Catch-all deny; method not open |

Note the exact status for anonymous callers depends on the authentication entry point/configuration. With plain Basic in the demo, 401 is expected. If switching to form login or a custom entry point, anonymous callers may receive a 302 redirect instead of 401.

## 6. Controller: Fetch Only Data the Principal Is Allowed to See

A common mistake is letting the filter allow the request and then having the controller query the document **by ID alone**, omitting owner/tenant conditions. If the ACL changes between the two operations, or the controller is invoked via another business path, this can cause IDOR (Insecure Direct Object Reference).

**`src/main/java/example/reactiveauthz/DocumentController.java`**:

```java
package example.reactiveauthz;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    private final DocumentPermissionRepository documents;

    public DocumentController(DocumentPermissionRepository documents) {
        this.documents = documents;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/documents/{id}")
    public Mono<ResponseEntity<String>> read(@PathVariable long id) {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .flatMap(username ->
                        documents.readVisibleDocument(username, id))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Here, `ReactiveSecurityContextHolder.getContext()` reads the context from the **current subscription's Reactor Context**, not Servlet's thread-local `SecurityContextHolder.getContext()`. The repository only returns content if the `JOIN document_permissions` query finds a matching row for username + document ID. If permission was revoked right before the second query, the API returns no body.

`.defaultIfEmpty(ResponseEntity.notFound().build())` represents the controller finding no **still-visible** record. However, with the filter ACL rule, callers lacking permission are usually blocked earlier and receive **403**, never reaching the controller. If a product wants to always return 404 to hide resource existence, design verified exception mapping/policies rather than defaulting every ACL miss to 404 ad hoc.

### Why Does Checking Twice Still Make Sense?

- **HTTP filter**: blocks unauthorized requests before entering the controller.
- **Repository/service**: retrieves only data the user is truly allowed to view; defends against calls from other flows or permission changes after the filter check.

For more sensitive data, centralize authorization in a reusable service while ensuring every query enforces tenant/owner conditions; consider reactive method security or a dedicated policy engine. Never rely solely on URL regexes to protect object-level data.

## 7. Integration Testing via WebTestClient

The demo uses in-memory H2; `schema.sql` and `data.sql` are initialized by Spring Boot at startup. Tests invoke HTTP Basic and verify statuses and bodies. Because the tests use real R2DBC (in-memory H2), this is not merely a mocked manager returning true/false.

**`src/test/java/example/reactiveauthz/DocumentAuthorizationTest.java`**:

```java
package example.reactiveauthz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class DocumentAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    DocumentPermissionRepository permissions;

    @Test
    void repositoryReturnsTrueWhenAclExists() {
        StepVerifier.create(permissions.hasReadPermission("alice", 100L))
                .expectNext(true)
                .verifyComplete();
    }

    @Test
    void repositoryReturnsFalseWhenAclIsMissing() {
        StepVerifier.create(permissions.hasReadPermission("alice", 200L))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousDocumentRequestIsUnauthorized() {
        client.get().uri("/documents/100")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceReadsDocument100() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Plan A: internal");
    }

    @Test
    void aliceCannotReadDocument200() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void bobReadsDocument200() {
        client.get().uri("/documents/200")
                .headers(h -> h.setBasicAuth("bob", "demo-only-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Plan B: private");
    }

    @Test
    void invalidIdIsDenied() {
        client.get().uri("/documents/not-a-number")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void missingAclIsDenied() {
        client.get().uri("/documents/999")
                .headers(h -> h.setBasicAuth("alice", "demo-only-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/documents/100")
                .headers(h -> h.setBasicAuth("alice", "incorrect"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run from the project directory containing the Gradle Wrapper:

```bash
./gradlew test --tests example.reactiveauthz.DocumentAuthorizationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.reactiveauthz.DocumentAuthorizationTest
```

**Expected:** ten tests PASS with compatible project/demo versions. The result above is the **expected outcome** when running the code, not a log of a test run already executed in the workspace. Tests use local password fixtures; never reuse them in production.

**Additional tests needed for production**:

- ACL revoked while a request is in flight.
- Database timeout/unavailable: request **must not be granted permission**, telemetry records DB error (never pretend it is a nonexistent account).
- High concurrency, connection pool limits, and p95/p99 latency.
- User with role but no ACL, and user with ACL but missing role.
- Multi-tenant: same username in a different tenant must never read the wrong data.
- Retries, connection exhaustion, cache invalidation, and auditing when policies change.

## 8. Performance and Non-Blocking Considerations

### 8.1. A Single Request Can Perform Multiple I/O Operations

In the demo, when `GET /documents/{id}` succeeds:

1. HTTP Basic authenticates the in-memory user (real apps may call an IdP or database).
2. `DocumentReadAuthorizationManager` queries the ACL via R2DBC.
3. The controller queries the body with the ACL condition again.

Thus a document-read request in the demo typically runs **two SQL queries** after authentication. This improves observability and defense-in-depth, though production must measure the cost. You can optimize into a single business query that checks the ACL and returns data, using the manager only on endpoints where filter-level checks are genuinely needed—or share a verified result via a controlled exchange attribute. Any optimization must guarantee no TOCTOU/IDOR gaps are introduced.

### 8.2. Non-Blocking Does Not Mean Infinite Capacity

Even though R2DBC does not block the event loop, the database still has finite connections and CPU. If 10,000 concurrent requests each open 1–2 queries, the pool/DB can be overwhelmed.

Pay attention to:

- **Connection pool**: cap connection count, acquisition timeout, and idle timeout; use an R2DBC pool matching your driver.
- **Timeouts**: bound query/authorization duration; on timeout, never grant permission.
- **Backpressure and concurrency**: bound concurrent requests or queries, avoiding unbounded `flatMap` over large collections.
- **Indexes**: ACL queries by `username`, `document_id`, and `permission` must have proper indexes verified via query plans; the demo primary key is `(document_id, username, permission)`, and a separate index on `username` can help depending on load.
- **Metrics**: authz decision counts by outcome and reason *without sensitive data*; query duration, connection wait time, timeouts/errors.
- **Retries**: do not blindly retry every DB error; that can amplify load on an overloaded or disconnected database.
- **Caching**: carefully consider TTL and invalidation when permissions are revoked; stale authorization decisions can leak data.
- **Tenant isolation**: add `tenant_id` to ACL constraints and queries (taking tenant from a verified source), never trusting an unverified `X-Tenant-Id` header from the caller.
- **Service-layer authorization**: ensure gRPC endpoints, message consumers, batch jobs, or background processes cannot bypass the HTTP filter and fetch data without ACL checks.

### 8.3. Do Not Mix Blocking Libraries into Reactive Pipelines

Anti-pattern snippet:

```java
return authentication.map(auth -> {
    // JDBC/JPA: blocking and executes immediately inside map.
    boolean allowed = jdbcPermissions.canRead(auth.getName(), documentId);
    return new AuthorizationDecision(allowed);
});
```

If you cannot replace JDBC with R2DBC yet, a transitional approach can be:

```java
return authentication.flatMap(auth ->
        Mono.fromCallable(() ->
                jdbcPermissions.canRead(auth.getName(), documentId))
            .subscribeOn(Schedulers.boundedElastic())
            .map(AuthorizationDecision::new));
```

This is an **illustrative snippet**: import `Mono`, `Schedulers`, and `AuthorizationDecision`, and ensure missing principals still deny with proper timeouts and error handling. `boundedElastic` isolates **blocking code** off the event loop with bounded resources, rather than turning JDBC into non-blocking R2DBC. Whenever possible, prefer an R2DBC driver and keep queries non-blocking end-to-end.

### 8.4. Do Not Put Heavy I/O Inside `map`

When an operation returns `Mono<Boolean>`, use `flatMap` to chain the publisher:

```java
// Right: returns Mono<AuthorizationDecision>.
return authentication
        .map(Authentication::getName)
        .flatMap(name -> permissions.hasReadPermission(name, documentId))
        .map(AuthorizationDecision::new);
```

If you use `map(name -> permissions.hasReadPermission(...))`, you get `Mono<Mono<Boolean>>`, and the filter cannot obtain the intended `AuthorizationDecision`. Also guard anonymous/missing-role/missing-ACL cases with `defaultIfEmpty(deny)` as in the full manager above.

## 9. Tricky Authorization Decisions and How to Handle Them

### 9.1. Missing Resource: 403 or 404?

In the demo, the manager checks the ACL before the controller reads the document. If document 999 does not exist **or exists without an ACL for Alice**, both can return 403. This reduces disclosing whether a resource exists, though it is not every product's API contract.

Some systems want 404 for both "does not exist" and "not permitted to view" to prevent enumeration. In that case, design the behavior clearly in the service/exception handler and test it thoroughly; never simply flip `AuthorizationDecision(false)` to true so the controller returns 404 while accidentally exposing data.

### 9.2. Who Is the Subject of the Decision?

`authentication.getName()` in the demo is the username. In production, usernames can change and collide across tenants; prefer an immutable ID and verified tenant, such as a claim validated by a JWT decoder or an ID from an identity provider. Never use `?user=bob` or `X-User: bob` from the client as the principal.

### 9.3. Missing Data Decisions vs. Infrastructure Errors

| Repository Result | Mono | Meaning | Proper Handling |
| --- | --- | --- | --- |
| ACL match | `Mono.just(true)` | Permitted | `AuthorizationDecision(true)` |
| ACL miss | `Mono.just(false)` | Not permitted | `AuthorizationDecision(false)` |
| Missing principal | `Mono.empty()` from auth source | Unauthenticated | Explicit manager deny or 401 entry point |
| Database unreachable | `Mono.error(...)` | Outcome unknown | **Do not grant access**, record operational error |
| Authenticated user lacking role | Excluded by `filter` | Insufficient role | Explicit deny and 403 status |

Never log the entire `Authentication`, tokens, `Authorization` headers, or document bodies in error logs. Auditing only needs a policy-compliant principal ID, resource ID, decision, elapsed time, correlation ID, and safe error class.

### 9.4. "Permit on Database Error" Is a Critical Vulnerability

Wrong:

```java
permissions.hasReadPermission(username, documentId)
    .onErrorReturn(true) // NEVER use this for permission checks!
```

When the database loses connectivity, that statement grants access to every user who passes the role check. Likewise, never turn `Mono.empty()` or exceptions into `AuthorizationDecision(true)` just to "keep the app working." Availability matters, **but never at the cost of leaking data**.

### 9.5. Reactive HTTP Authorization vs. Method Security

If all data access goes through HTTP filters with custom managers, URL checks provide the first layer. However, services can also be invoked by scheduled jobs, WebSockets, message consumers, or RPCs; you need policies at the service/data layer too.

Spring Security also supports `@EnableReactiveMethodSecurity` with `@PreAuthorize` on methods returning `Mono`/`Flux`. A custom bean inside an expression can return `Mono<Boolean>` for a rule. Still, method security is a separate scope; if used, ensure the Reactor context propagates properly without detaching subscriptions or calling `block()`.

This lesson focuses on **HTTP authorization with `ReactiveAuthorizationManager<AuthorizationContext>`**, without forcing every system onto method security.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only writing `hasRole("READER")` for all documents | Users read resources they do not own | Query ACL by principal + resource ID |
| Using JDBC/JPA directly inside a `WebFilter` | Blocks the event loop | R2DBC or bounded blocking isolation |
| Calling `.block()` inside a manager | Blocks thread or throws Reactor error | Return a complete `Mono` pipeline |
| Calling `.subscribe()` and reading a mutated variable | Race condition, lost context, wrong result | Compose via `flatMap`/`map` |
| Using `Mono.just(blockingCall())` | Blocking already happened before creating publisher | Switch data source or `fromCallable + boundedElastic` when unavoidable |
| Using `map` for a method returning `Mono` | Produces `Mono<Mono<T>>` | Use `flatMap` |
| Empty auth `Mono` turns into abstain | May behave differently from explicit deny | `defaultIfEmpty(new AuthorizationDecision(false))` |
| Trusting `Authentication.isAuthenticated()` for anonymous | Anonymous tokens can carry `true` | Exclude `AnonymousAuthenticationToken` / use trust resolver |
| Not validating path ID | `NumberFormatException` -> 500 | Parse safely, deny or return 400 per API contract |
| Concatenating id/username into SQL | SQL injection | Use `DatabaseClient.bind(...)` |
| Omitting tenant in ACL | Cross-tenant data reads possible | Add verified tenant to queries/indexes |
| DB error falls back to permit | Opens access when DB is down | Fail closed, clear telemetry/error handling |
| Swallowing all DB errors as ACL miss | Masks outages, hard to operate | Distinguish missing permissions from infrastructure errors |
| Caching permissions forever | Users retain access after revocation | TTL, invalidation, policy versioning, or live queries |
| Controller reads by ID alone after filter allows | TOCTOU/IDOR if invoked elsewhere or permissions change | Query data with ACL/tenant conditions |
| Placing `anyExchange().permitAll()` too early | Bypasses all subsequent rules | Specific rules first, deny/authenticated last |
| Testing only with `mockUser`, never hitting DB | Misses mapping/ACL query bugs | Integration tests with `WebTestClient` + real R2DBC |
| Using HTTP Basic without TLS | Credentials exposed in transit | Always use HTTPS on real networks |
| Using Spring Security 7.x API in a 6.5 project | Compiler signature mismatch | Pin versions, read Javadoc and migration guide |

## 11. Practice Exercises

1. Add a `tenant_id` column to `documents` and `document_permissions`. Write a test ensuring two users with the same username in different tenants **cannot** access each other's documents.
2. Create a separate `EDIT` permission for `PUT /documents/{id}`, keeping CSRF if clients use cookies; never use GET to mutate data.
3. Add user `charlie` with `ROLE_READER` but no ACL. Verify login succeeds and GET document returns 403.
4. Add a user with a database ACL but lacking `ROLE_READER`: authorization still denies. Never let an ACL bypass a required role.
5. Measure the latency of two SQL queries per request, optimize to read the body using a single ACL-filtered query, and compare security guarantees.
6. Simulate a database timeout in `DocumentPermissionRepository`; prove the result never becomes 200 and the system logs the error properly.
7. Revoke Alice's ACL while the service is processing; verify the ACL-filtered body query still returns no data once permission is removed.
8. Upgrade the demo from Spring Security 6.5 to 7.x, inspect `ReactiveAuthorizationManager.authorize(...)` and `AuthorizationResult`, and update the manager and tests per your active Javadoc.
9. If your application also has WebSockets or message consumers, identify where to place service-layer rules so non-HTTP paths are still checked.

**Conclusion:** Data-driven HTTP authorization in WebFlux does not need to block threads. Accept `Mono<Authentication>` from Spring Security, extract URL variables via `AuthorizationContext`, query ACLs via R2DBC, and return a fully composed `Mono<AuthorizationDecision>`. Missing user/role/ACL must **deny**, database errors must never turn into permit; for sensitive data, enforce additional checks in the service/repository and write real tests.

## Official Documentation

- [Spring Security 6.5 — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — AuthorizationContext API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html)
- [Spring Security 6.5 — AuthorizeExchangeSpec.Access API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Boot 3.x — SQL Databases and R2DBC](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Framework — R2DBC and DatabaseClient](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Data R2DBC — Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
