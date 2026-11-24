# Checking Ownership with Reactive Data at the Service Layer

## Learning Objectives

This lesson belongs to **Method Authorization** in **Spring Security - reactive**. An application may have authenticated a user and required `ROLE_USER`, yet **must still verify whether that user owns the specific resource**. If you only check "logged in" on the HTTP route and then read data by any ID, the system can suffer from **IDOR/BOLA** (Insecure Direct Object Reference / Broken Object Level Authorization).

Objectives:

1. Distinguish **authentication**, **role permissions**, **resource ownership**, and **tenant scope**.
2. Read the principal from `ReactiveSecurityContextHolder` instead of trusting a client-sent `ownerId`.
3. Perform **reactive data lookups** via Spring Data R2DBC/`Mono` inside permission checks without calling `block()`.
4. Enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` and place `@PreAuthorize` on **service beans**.
5. Use a permission bean returning `Mono<Boolean>` in method security SpEL, properly handling missing users, missing records, and database errors.
6. Prevent TOCTOU via queries **scoped directly in the WHERE clause by owner**, especially for updates/deletes.
7. Build a runnable example with **Java 17+, Spring Boot 3.3.13, Spring WebFlux, Spring Security, Spring Data R2DBC, and H2**.
8. Test both HTTP access and **direct service method calls** with `WebTestClient`/`StepVerifier`.
9. Identify issues with Spring AOP self-invocation, schedulers, Reactor Context, cross-tenant access, permission caching, audit logging, and 401/403/404 responses.

**Focus:** Ownership must be verified using **server-controlled** data, never URLs, headers, cookies, or JSON fields that a client can modify.

## 1. Problem: a valid user does not mean access to every record

Suppose the system stores two documents:

| ID | owner_id in database | Title |
| --- | --- | --- |
| 101 | alice | Alice's private document |
| 202 | bob | Bob's private document |

The API exposes `GET /api/documents/{id}`. HTTP security specifies:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/documents/**").authenticated()
    .anyExchange().denyAll());
```

This rule only guarantees the request carries a valid `Authentication`. If the controller directly calls:

```java
// WRONG: relies solely on client-supplied id.
@GetMapping("/api/documents/{id}")
public Mono<Document> getDocument(@PathVariable Long id) {
    return documentRepository.findById(id);
}
```

then Alice (already logged in) can try `/api/documents/202` and view Bob's document. This is an object-level authorization vulnerability even though the endpoint requires authentication.

An additional condition is needed:

```text
ALLOW = authenticated(actor)
    AND actor has permission "document:read"
    AND resource exists
    AND resource.ownerId == trustedActorId
    AND resource.tenantId == trustedTenantId (if multi-tenant)
```

In a single-tenant example, `trustedActorId` is the username read from the Spring Security-verified `Authentication`. In real products, prefer an **immutable user ID** and **tenant ID** from a signature-verified token/identity provider or server-side data; avoid using mutable usernames as stable identities.

## 2. Why check at the service layer?

If you only check ownership in an HTTP filter or controller, a business service method can still be invoked from:

- A WebFlux REST controller;
- An RSocket handler or GraphQL resolver;
- A message consumer;
- A scheduled job/batch;
- A test or internal integration flow;
- Another service within the application.

Not every call path goes through HTTP's `AuthorizationWebFilter`. **Method security** ensures policy is enforced **at the service bean boundary**, where the resource is accessed.

```text
HTTP request
   |
   +-- WebFlux SecurityWebFilterChain
   |     +-- Authentication (Basic/Form/Bearer)
   |     +-- HTTP authorization: authenticated()
   |
   v
DocumentController
   |
   v
Spring AOP proxy of DocumentService
   |
   +-- @PreAuthorize("@documentPermission.canRead(#p0)")
   |      |
   |      +-- ReactiveSecurityContextHolder -> Authentication
   |      +-- Reactive DocumentRepository
   |              -> SELECT by id and verified owner
   |      +-- Mono<Boolean> -> ALLOW / DENY
   |
   v
DocumentService.read(id)
   |
   +-- SELECT by id and owner a second time
   |
   v
DocumentView -> response
```

The `@PreAuthorize` path **protects before the method body runs**. In this example, the service still performs an owner-scoped query after passing AOP so it does not rely purely on the earlier lookup if data changed in between (time-of-check to time-of-use).

**In return, the example executes two SELECT queries.** That is intentional for teaching two layers of defense. Applications needing optimization can choose **@PreAuthorize checking only the role** + **owner-scoped query directly inside the service** to save a round trip; see section 8.

## 3. Reactor Context: reading trusted identity in services

In WebFlux, `SecurityContext` travels via **Reactor Context**. A pipeline can switch threads; therefore do not rely on Servlet-style `SecurityContextHolder.getContext()`/`ThreadLocal` in reactive services.

```java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

This retrieves the username from the current subscriber's `Authentication`, created by Spring Security after authentication. It does not query a database or open a new login session.

**Distinguishing values:**

| Value | Source | Use to grant permissions? |
| --- | --- | --- |
| `authentication.getName()` | Verified authentication mechanism | Can serve as actor ID in demos |
| `authentication.getAuthorities()` | Verified/mapped roles/scopes | Yes, per policy |
| `@PathVariable Long id` | Client-selected resource | Only identifies the target object to check |
| `?ownerId=alice` | Client-supplied | Not proof of ownership |
| `X-User-ID: alice` | Client-supplied header | Never use as principal |
| `document.ownerId()` in DB | Server-stored data | Source of truth for ownership |
| `document.tenantId()` in DB | Server-stored data | Source of truth for tenant when membership is verified |

If a request has no `SecurityContext`, `ReactiveSecurityContextHolder.getContext()` can return `Mono.empty()`. In this lesson's policy, that case must **DENY**, never treating "no context" as "public".

Anonymous authentication must be rejected. `AnonymousAuthenticationToken` can report `isAuthenticated()==true` per its object contract, yet does not represent a logged-in user. Therefore never check that flag **alone**.

## 4. Method security in WebFlux: annotations and reactive beans

### 4.1. Enabling method security

With Spring Security 6.x, the explicit approach is:

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

The annotation resides in `org.springframework.security.config.annotation.method.configuration`. It enables Spring AOP-based method security interceptors, including `@PreAuthorize` and `@PostAuthorize`.

**Constraint to remember:** In reactive applications, protected methods should return `Mono<T>` or `Flux<T>` (a `Publisher`). Spring Security uses Reactor Context to retrieve `Authentication`. Synchronous methods returning `T` and trying to read ThreadLocal are a different model; do not mix them with this flow.

### 4.2. Simple role rule

```java
@PreAuthorize("hasRole('READER')")
public Mono<Document> read(Long id) {
    return documents.findById(id);
}
```

This rule checks only the role. A user with `ROLE_READER` can still read someone else's document if the service body uses an unscoped `findById`.

### 4.3. Integrating a check returning Mono<Boolean>

Reactive Spring Security supports referencing a bean in SpEL:

```java
@PreAuthorize("@documentPermission.canRead(#p0)")
public Mono<DocumentView> read(Long documentId) {
    // only runs when canRead check permits
}
```

- `@documentPermission` is the bean named `documentPermission`.
- `#p0` is the **first parameter** of the protected method, here `documentId`. This syntax avoids depending on whether builds retain `-parameters` names.
- `canRead` can return `Mono<Boolean>`, allowing reactive repository lookups.
- Spring Security's manager/interceptor awaits the publisher's outcome before allowing the method to execute.
- If it returns `false`, method security denies and emits an authorization error; in the HTTP pipeline Spring Security normally turns this into 403 for authenticated users.

**Spring Security 6.3 compatibility note:** Do not arbitrarily combine a `Mono<Boolean>`-returning expression with synchronous SpEL boolean operators such as `hasAuthority(...) && @bean.canRead(...)` in the same `@PreAuthorize`, as some versions hit expression type conversion issues. In the example, **the entire role + ownership decision** lives inside one `Mono<Boolean>` bean. When upgrading the framework, re-run integration tests on the exact version instead of relying on code that merely looks plausible.

### 4.4. Using a dedicated bean instead of authorization code in controllers

Place permission checks in a `@Component` so that:

- It can be tested in isolation;
- Logic is not duplicated across every controller;
- It can be reused across services;
- Repositories and tenant policies are easy to swap/evolve;
- Decision latency can be measured, audited, and new rules added cleanly;
- Controllers avoid loading data first and checking permissions afterward once data is already at risk of leaking.

Never turn this bean into a static helper calling `.block()`, as that blocks the event loop and risks losing Reactor Context.

## 5. Designing an ownership check with Mono

Suppose `DocumentRepository` provides the query:

```java
Mono<Document> findByIdAndOwnerId(Long id, String ownerId);
```

When the repo returns `Mono<Document>`, use `hasElement()` to convert it to `Mono<Boolean>`:

```java
Mono<Boolean> owned =
    documents.findByIdAndOwnerId(documentId, actorId)
             .hasElement();
```

This is a reactive query: the R2DBC adapter fetches data asynchronously without `block()`. In production, if only existence is needed, you can optimize the query to return just a Boolean or use `SELECT EXISTS(...)` / a derived exists repository query depending on the database.

### What inputs are verified?

1. `documentId` is valid in type/format and within the resource domain.
2. There is a verified, non-anonymous `Authentication`.
3. `Authentication` holds the required authority, e.g., `ROLE_READER`.
4. The server takes actor ID **from Authentication**, never from query params or headers.
5. The repository checks for a record matching **both document ID and owner ID**.
6. If the record does not exist or belongs to another owner, the result is **false**.
7. If the DB fails, never return `true`; errors must fail closed and be operationally observable.

### Mono<Boolean> differs from Mono.empty()

| Signal from check | Meaning | Handling |
| --- | --- | --- |
| `Mono.just(true)` | Conditions satisfied for access | ALLOW |
| `Mono.just(false)` | Conditions not satisfied | DENY |
| `Mono.empty()` | No check result emitted | Avoid unintended abstain; convert missing context to false |
| `Mono.error(ex)` | Lookup/policy evaluation error | Never emit ALLOW; respond with controlled error |

`defaultIfEmpty(false)` only converts **empty** to false; it does not swallow **errors**. This aligns with fail-closed design: a lost DB connection must never be treated as "no info, let it pass".

**Do not write:**

```java
// WRONG: database error grants access.
return documents.findByIdAndOwnerId(id, userId)
    .hasElement()
    .onErrorReturn(true);
```

When policy depends on a DB, timeouts and circuit breakers (if present) protect resources and report errors clearly; they never grant access when ownership cannot be verified.

## 6. Complete example: Spring Boot WebFlux + Spring Data R2DBC H2

The sample uses **Java 17+, Spring Boot 3.3.13**, HTTP Basic for quick permission testing, and an **H2 database via R2DBC** for async lookups. Method security blocks Alice when requesting Bob's document even if the controller is permitted to call the service.

### 6.1. Project structure

```text
reactive-ownership-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/
        OwnershipApplication.java
        Document.java
        DocumentView.java
        DocumentRepository.java
        DocumentPermission.java
        DocumentService.java
        DocumentController.java
      resources/
        application.yml
        schema.sql
        data.sql
    test/
      java/example/
        OwnershipApplicationTests.java
```

### 6.2. settings.gradle

```groovy
rootProject.name = 'reactive-ownership-demo'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web` (MVC/Servlet). `spring-boot-starter-data-r2dbc` provides reactive repositories, and `r2dbc-h2` is the R2DBC driver for sample data. The Spring Boot BOM selects compatible framework, driver, and Reactor versions.

### 6.4. application.yml

Create `src/main/resources/application.yml`:

```yaml
spring:
  r2dbc:
    url: "r2dbc:h2:mem:///ownerlab?options=DB_CLOSE_DELAY=-1"
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
      data-locations: classpath:data.sql
```

`spring.sql.init` supports initializing R2DBC `ConnectionFactory` as well in Spring Boot. `always` mode and sample data here are **for demo only**; production uses real migration tools/DBs per policy rather than inserting users/documents on every startup.

For in-memory H2, `DB_CLOSE_DELAY=-1` keeps the database alive when no connections are open during the lab. The R2DBC H2 syntax uses `?options=...`, not JDBC URL `jdbc:h2:...`.

### 6.5. SQL schema and sample data

Create `src/main/resources/schema.sql`:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    owner_id VARCHAR(100) NOT NULL,
    title VARCHAR(200) NOT NULL
);

CREATE INDEX idx_documents_owner ON documents(owner_id);
```

Create `src/main/resources/data.sql`:

```sql
INSERT INTO documents (id, owner_id, title)
VALUES (101, 'alice', 'Alice private');

INSERT INTO documents (id, owner_id, title)
VALUES (202, 'bob', 'Bob private');

INSERT INTO documents (id, owner_id, title)
VALUES (303, 'alice', 'Alice notes');
```

This data is **server-stored source of truth**. Clients cannot become owners merely by changing `owner_id` in the URL. Service queries must compare against the verified identity.

### 6.6. OwnershipApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails
        .MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}read")
                .roles("READER")
                .build();

        UserDetails visitor = User.withUsername("visitor")
                .password("{noop}visit")
                .roles("GUEST")
                .build();

        return new MapReactiveUserDetailsService(
                alice, bob, visitor);
    }
}
```

The imports above are intentionally wrapped at `.` for readability; Java allows line breaks between tokens in import syntax. If an IDE formatter joins them onto one line, the meaning does not change.

**Why only `authenticated()` at HTTP?** To clearly demonstrate two layers:

- The HTTP filter checks for a valid identity to enter the route.
- Method security on `DocumentService` checks **ROLE_READER and real ownership in the DB**.

The `visitor` account is authenticated yet lacks `ROLE_READER`, so the service method rejects it. This distinguishes "logged in" from "authorized to read documents".

`{noop}` is for local demos only; production uses strong password encoders, HTTPS, and proper user management. HTTP Basic sends username/password on every request; it is a quick observation tool, not a default recommendation for all production APIs.

### 6.7. Document.java

```java
package example;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("documents")
public record Document(
        @Id Long id,
        String ownerId,
        String title) {
}
```

Spring Data R2DBC maps `ownerId` to column `owner_id` per default naming rules; if a project uses a custom `NamingStrategy`, keep `@Column` annotations/mappings consistent.

**Do not treat this record as a public DTO.** `ownerId` is security/domain metadata. The example returns a separate `DocumentView` to avoid accidentally exposing unnecessary fields.

### 6.8. DocumentView.java

```java
package example;

public record DocumentView(Long id, String title) {
}
```

Separating a DTO restricts serialized data. If a document holds sensitive content, the service must load **only the authorized subset of data** before returning it.

### 6.9. DocumentRepository.java

```java
package example;

import org.springframework.data.repository.reactive
        .ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Document> findByIdAndOwnerId(
            Long id, String ownerId);
}
```

Spring Data derives the query from the method name. Most importantly: the WHERE clause filters on **both id and ownerId**. If no matching record exists, the `Mono` completes empty. The query uses R2DBC and never calls `block()` on the Netty event loop.

For real databases with millions of documents, design appropriate indexes for owner/id queries and inspect query plans. With a primary key ID, the DB can use the ID index first and then check owner; index selection depends on workload rather than blindly indexing every column.

### 6.10. DocumentPermission.java — reactive permission bean

```java
package example;

import org.springframework.security.authentication
        .AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("documentPermission")
public class DocumentPermission {

    private final DocumentRepository documents;

    public DocumentPermission(DocumentRepository documents) {
        this.documents = documents;
    }

    public Mono<Boolean> canRead(Long documentId) {
        if (documentId == null || documentId <= 0L) {
            return Mono.just(false);
        }

        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(this::isReader)
            .flatMap(authentication ->
                documents.findByIdAndOwnerId(
                        documentId, authentication.getName())
                    .hasElement())
            .defaultIfEmpty(false);
    }

    private boolean isReader(Authentication auth) {
        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return false;
        }

        return auth.getAuthorities().stream()
                .anyMatch(granted ->
                    "ROLE_READER".equals(
                        granted.getAuthority()));
    }
}
```

**Step-by-step analysis:**

1. Invalid/null `documentId` → `Mono.just(false)`, no DB query.
2. Reads `Authentication` from **Reactor Context**, never trusting client-sent `ownerId`.
3. `filter(this::isReader)` rejects anonymous, unauthenticated tokens, or users lacking `ROLE_READER`.
4. Query `findByIdAndOwnerId(id, authentication.getName())` requires the record to both match the ID and belong to the verified actor.
5. `hasElement()` emits true when found, false when the repository returns empty.
6. `defaultIfEmpty(false)` explicitly handles missing context or missing authenticated reader.
7. R2DBC errors are not converted to true. By default they propagate down the error pipeline; requests are never granted access on the basis of a failed query.
8. No manual `subscribe()` and no `block()`: all evaluation occurs when the method security chain is subscribed.

This snippet illustrates **read-only-own-documents** permission. For supervisor/auditor privileges, design explicit policies, verify permission types and tenants, and write negative tests for overrides instead of scattering inconsistent `|| roleAdmin` checks.

### 6.11. DocumentService.java — protection at the service boundary

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPermission.canRead(#p0)")
    public Mono<DocumentView> read(Long documentId) {
        // Second-layer protection via scoped query,
        // do not switch to global findById(documentId).
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .flatMap(auth -> documents.findByIdAndOwnerId(
                        documentId, auth.getName()))
                .map(doc -> new DocumentView(
                        doc.id(), doc.title()))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND)));
    }
}
```

**Why still query by owner even though `@PreAuthorize` already checked?** Because ownership could change between the two steps, or the service might later be refactored to fetch data differently. Scoped queries ensure no record is returned if the owner changed by the time the actual read executes, avoiding sole reliance on a pre-method check.

For systems performing business updates/deletes, **checking first and then running `UPDATE WHERE id=?` is not enough against TOCTOU**. Put owner/tenant into the `UPDATE`/`DELETE` condition in the same atomic statement; see section 10.

**The method must be called through the Spring bean proxy** for the annotation to take effect. In the demo, the controller injects `DocumentService`, so Spring AOP intercepts calls. Calling `this.read(id)` from another method **in the same class** can bypass Spring proxy-based method security; never assume annotations automatically protect internal Java calls.

### 6.12. DocumentController.java — thin controller

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping("/api/documents/{id}")
    public Mono<DocumentView> document(
            @PathVariable("id") Long id) {
        return service.read(id);
    }
}
```

The controller merely forwards the client's `id` to the service. It does **not** assert the caller owns that ID itself. Method security at the service performs the real lookup.

### 6.13. Starting up

Requires **JDK 17+**, Gradle 8.x compatible with Spring Boot 3.3.13, and no external Redis/PostgreSQL since the demo uses in-memory R2DBC H2.

```bash
gradle bootRun
```

If the project has a Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Boot loads `schema.sql` and `data.sql` at startup. If DB initialization fails, inspect the R2DBC URL/driver and scripts; do not skip initialization assuming sample data is present.

### 6.14. Testing HTTP with curl

```bash
curl -i http://localhost:8080/public/ping

curl -i http://localhost:8080/api/documents/101

curl -i -u alice:learn \
  http://localhost:8080/api/documents/101

curl -i -u alice:learn \
  http://localhost:8080/api/documents/202

curl -i -u bob:read \
  http://localhost:8080/api/documents/202

curl -i -u visitor:visit \
  http://localhost:8080/api/documents/101

curl -i -u alice:learn \
  http://localhost:8080/api/documents/999
```

**Expected results with the exact demo configuration:**

| Request | Status | Explanation |
| --- | --- | --- |
| `GET /public/ping`, guest | 200, `PONG` | Public |
| `GET /api/documents/101`, guest | 401 + Basic challenge | Unauthenticated, blocked at HTTP layer |
| Alice reads 101 | 200 | Alice is owner and holds ROLE_READER |
| Alice reads 202 | 403 | Bob is owner, method security DENY |
| Bob reads 202 | 200 | Bob is owner and holds ROLE_READER |
| Visitor reads 101 | 403 | Logged in, yet lacks ROLE_READER |
| Alice reads 999 | 403 in demo | Resource not found, so permission check returns false |

Expected JSON body when Alice reads 101:

```json
{
  "id": 101,
  "title": "Alice private"
}
```

JSON key ordering and whitespace depend on the serializer. Do not assert byte-for-byte formatting; verify status, `id`, and `title`.

**Why does 999 return 403 instead of 404?** In the demo design, `@PreAuthorize` runs **before** the service body reads the record and cannot verify ownership for a non-existent ID, so it returns DENY. An existence-hiding policy may intentionally return the same response for "missing" and "unauthorized" to curb enumeration. If your product wants 404 here, design explicit error mapping or scoped lookups rather than blindly turning every 403 into 404 and losing operational visibility.

## 7. Testing with WebTestClient and StepVerifier

### 7.1. Create the test class

Create `src/test/java/example/OwnershipApplicationTests.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority
        .SimpleGrantedAuthority;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.boot.test.context.SpringBootTest
        .WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class OwnershipApplicationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    DocumentService service;

    @Test
    void publicPing() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/documents/101")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceMayReadOwnDocument() {
        client.get().uri("/api/documents/101")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(101)
                .jsonPath("$.title").isEqualTo("Alice private");
    }

    @Test
    void aliceCannotReadBobDocument() {
        client.get().uri("/api/documents/202")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void bobMayReadBobDocument() {
        client.get().uri("/api/documents/202")
                .headers(h -> h.setBasicAuth("bob", "read"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(202);
    }

    @Test
    void authenticatedGuestWithoutRoleIsDenied() {
        client.get().uri("/api/documents/101")
                .headers(h -> h.setBasicAuth("visitor", "visit"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void nonExistingDocumentDeniedBeforeServiceBody() {
        client.get().uri("/api/documents/999")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void directServiceCallStillEnforcesOwnership() {
        Authentication alice =
                UsernamePasswordAuthenticationToken.authenticated(
                    "alice", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(
                service.read(202L).contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void directServiceCallWithOwnerIsAllowed() {
        Authentication bob =
                UsernamePasswordAuthenticationToken.authenticated(
                    "bob", "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_READER")));

        StepVerifier.create(
                service.read(202L).contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(bob)))
            .assertNext(view -> {
                assertEquals(202L, view.id());
                assertEquals("Bob private", view.title());
            })
            .verifyComplete();
    }
}
```

Run:

```bash
gradle test
```

Tests use H2 data via R2DBC initialized from `schema.sql`/`data.sql` when the Spring context starts. Direct tests use `contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))` to simulate an authenticated identity in a **non-HTTP** pipeline; the point to prove is that Spring AOP method security **still blocks `service.read(202)`** when the actor is not the owner.

**Do not treat `mockUser` or HTTP Basic as sole proof of method security.** HTTP Basic tests the whole pipeline well; direct service-call tests show protection does not come solely from the `authenticated()` route. When the method is called via proxy, `AccessDeniedException` signals permission denial.

### 7.2. Testing reactive data and fail-closed behavior

Additional cases to cover:

- Permission bean receives invalid ID → `Mono.just(false)`, no query.
- Actor lacks `ROLE_READER` → false.
- Missing Reactor SecurityContext → false.
- ID exists yet has another owner → false.
- Repository returns `Mono.empty()` → `hasElement()` emits false.
- Repository emits `Mono.error(new RuntimeException("DB down"))` → permission **never emits true**, request does not enter service body; test asserts the proper error path.
- When DB owner changes or is revoked, new requests must be denied; never cache allow indefinitely.

You can use `StepVerifier` against the standalone permission bean in unit tests with a mocked repository. However, when integration-testing real ownership, do not mock owner data to match the desired user and conclude DB queries are safe; use an R2DBC test database or PostgreSQL container with real data.

### 7.3. Critical authorization matrix

| Actor | Role | Resource | Expected |
| --- | --- | --- | --- |
| Guest | none | 101 | 401 at HTTP |
| Alice | READER | 101 | ALLOW |
| Alice | READER | 202 | DENY |
| Bob | READER | 202 | ALLOW |
| Bob | READER | 101 | DENY |
| Visitor | GUEST | 101 | DENY |
| Alice | READER | 999 | DENY since owner cannot be verified |
| Alice | READER | negative/malformed id | Disallowed from data; HTTP code may be 400/403 per layer |
| Alice | READER | 101 after transferring owner to Bob | DENY on new requests |
| Direct service call | Alice in Reactor Context | 202 | AccessDeniedException |
| Direct service call | Bob in Reactor Context | 202 | DocumentView |

## 8. Choosing a strategy at the service layer

There are multiple ways to implement object-level authorization. Choose based on security and performance requirements rather than stacking random query layers.

| Approach | Mechanism | Pros | Limitations |
| --- | --- | --- | --- |
| `@PreAuthorize("hasRole('READER')")` + `findById(id)` | RBAC only, unscoped lookup | Easy to write | **Insufficient** to protect ownership |
| Custom `Mono<Boolean>` bean in `@PreAuthorize` | Checks owner before method | Centralized policy, protects service boundary | May require an extra query to load content |
| `@PreAuthorize("isAuthenticated()")` + `findByIdAndOwnerId(id, actor)` | Scoped inside SELECT | Single round trip, avoids reading others' records | Permission logic lives in service body; must stay consistent across methods |
| Reactive repository query by tenant + owner + ID | DB enforces scope condition | Prevents cross-tenant leaks, scales well | Needs proper index/schema and identity mapping |
| `@PostAuthorize` on result | Checks after method builds data | Useful when inspecting returned object | Data was already loaded; does not replace pre-side-effect checks |
| DB Row-Level Security (PostgreSQL RLS) | Enforced inside database | Strong defense in depth | Requires setting tenant/actor on DB session/tx cleanly and testing pool reuse |

### When to drop one of the two SELECTs from the example?

If the goal is optimizing READs:

```java
// Snippet: service has documents available.
@PreAuthorize("isAuthenticated()")
public Mono<DocumentView> read(Long id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(auth -> hasReaderAuthority(auth))
        .flatMap(auth -> documents.findByIdAndOwnerId(
                id, auth.getName()))
        .map(doc -> new DocumentView(
                doc.id(), doc.title()))
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
}
```

`hasReaderAuthority` is a helper you must define; the snippet above is **illustrative only**, not a standalone source file. The owner condition sits **directly inside the SELECT**, so the DB never returns documents outside the caller's ownership; if permissions are missing, an empty publisher drives the response per policy.

In trade-off, this approach does not put ownership inside `@PreAuthorize`. It remains a service-layer authorization check, yet must be applied consistently across all methods/services touching the resource. A shared policy service class can centralize rules rather than duplicating them.

## 9. Why @PostAuthorize does not replace all @PreAuthorize?

`@PostAuthorize` runs after the method executes to inspect the returned object before handing it to the caller. It is helpful when authorization depends on the object's fields (e.g., `ownerId` inside the returned document). However:

1. If the method already updated the database, sent emails, or published events, post-checking **does not undo side effects**.
2. The object may already have been loaded into memory even if ultimately denied; do not accidentally log or cache it beforehand.
3. For `Flux<T>`, verify the exact semantics of the annotation and per-element behavior in your Spring Security version; do not assume one check safely filters every row.
4. Complex owner policies sometimes need multiple DB fields; restrict queries before returning data to minimize exposure.

Conceptual post-check example:

```java
// Illustrative snippet: confirm @PostAuthorize semantics
// with reactive return types and the Spring Security version in use.
@PostAuthorize("returnObject.ownerId == authentication.name")
public Mono<Document> readForPostAuthorization(Long id) {
    return documents.findById(id);
}
```

**Do not copy this snippet into the runnable demo** without verifying annotation/`returnObject` behavior on your specific version and writing negative tests; the most reliable ownership protection remains scoped lookups or policy services. If queries already filter by owner and tenant, post-authorization is only an explicitly conditioned extra layer.

### For multi-document Flux streams

An API listing `Flux<Document>` should use a repository query such as:

```java
Flux<Document> findAllByOwnerId(String ownerId);
```

or include tenant in multi-tenant apps. Never run `findAll()` followed by `filter(doc -> owner.equals(...))` after loading everyone else's documents. Application-side filtering cannot replace database-level scoping and optimization, especially when pagination, sorting, total counts, or caches might leak metadata.

## 10. On update/delete: check owner and mutate data atomically

For READs, checking twice (before method and in SELECT) provides defense in depth. For WRITEs, TOCTOU risk is greater:

```text
T0: SELECT document WHERE id=101 -> owner alice -> ALLOW
T1: Ownership transferred from alice to bob
T2: UPDATE documents SET title='...' WHERE id=101
    -> Alice can still modify the record now owned by Bob if owner is missing in WHERE
```

**Do not** merely use `@PreAuthorize("@documentPermission.canWrite(#p0)")` and then run an unrestricted update. Use conditional mutation:

```sql
UPDATE documents
SET title = :title
WHERE id = :documentId
  AND owner_id = :trustedActorId;
```

Snippet using Spring `DatabaseClient` and `ReactiveSecurityContextHolder`, **not a standalone file**:

```java
Mono<Long> updatedRows =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(this::isValidWriter)
        .flatMap(auth ->
            databaseClient.sql(
                "UPDATE documents SET title = :title "
              + "WHERE id = :id AND owner_id = :owner")
                .bind("title", newTitle)
                .bind("id", documentId)
                .bind("owner", auth.getName())
                .fetch()
                .rowsUpdated())
        .defaultIfEmpty(0L);
```

This snippet requires defining `databaseClient`, `isValidWriter`, `newTitle`, and `documentId` with validation, as it is a guide fragment. **The security lies in the conditional UPDATE statement**: if ownership no longer matches at update time, updated row count is 0. Do not naively check `updatedRows > 0` when a policy allows multi-row updates; the demo targets a single record by primary key.

For tenant-aware records, WHERE must include **`tenant_id = :trustedTenantId` as well**. With complex ACLs, use transactions or permission-conditioned SQL so no gap exists between check and write.

### Permission changes between check and write

Even when `@PreAuthorize` checked membership, membership can be revoked before the write executes. For sensitive operations, enforce permissions inside the **same transaction/mutation** or use appropriate row locks/versioning. Reactive transactions should use `TransactionalOperator` or `@Transactional` on Spring AOP-managed publishers with `ReactiveTransactionManager`; never switch to Servlet's ThreadLocal JDBC transactions.

**Note:** Transactions alone do not make every check-then-act safe if isolation or statements are inadequate. Designing atomic predicates and race tests remains essential.

## 11. Multi-tenancy: owner does not mean tenant

In SaaS systems, two users can share the same username in two different tenants, or one principal may belong to multiple tenants. A lone `WHERE owner_id = :username` query can cause cross-tenant data leaks.

A stronger model:

```text
Document:
  id
  tenant_id
  owner_user_id
  title

Authenticated principal:
  immutable user_id
  allowed_tenants (verified)
  authorities/scopes

Authorized READ:
  requested document id
  AND document.tenant_id in allowed tenants
  AND (
       document.owner_user_id == principal.user_id
       OR holds valid read permission within that tenant
  )
```

**Never trust `X-Tenant-ID` headers or `?tenant=...` query params as proof of membership.** The client only selects the target tenant; the service must verify via token/DB/identity provider that the user holds rights in that tenant. If tokens carry tenant claims, verify signature, issuer, audience, expiration, and claim-mapping rules.

In queries, prefer:

```sql
SELECT id, title
FROM documents
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_user_id = :trustedUserId;
```

For admin/cross-tenant support accounts, design dedicated rules with auditing, scopes, and approval workflows where needed; never let a tenant's `ADMIN` role access every tenant via a global OR condition.

### Role and ownership are two distinct axes

- `ROLE_READER` indicates the caller has functional reading privileges.
- `owner_user_id` indicates the user has rights to that **specific record**.
- `tenant_id` bounds the data space.
- ACL/sharing grants can permit non-owners within the same tenant.
- Resource states (locked, archived, legal hold) can impose further restrictions.

In production software, authorization checks should not be simple string comparisons; model permissions aligned with the data lifecycle.

## 12. Common architectural mistakes

### 12.1. Self-invocation prevents annotations from running

```java
@Service
class DangerousService {
    public Mono<Document> outer(Long id) {
        return this.securedRead(id); // same instance, may bypass AOP proxy
    }

    @PreAuthorize("@documentPermission.canRead(#p0)")
    public Mono<Document> securedRead(Long id) {
        // ...
        return Mono.empty();
    }
}
```

This is a trap in Spring AOP proxy-based method security. **Fix:** move the protected method to a separate injected bean; call through the proxy; or enforce ownership inside domain queries/services that do not rely on proxy interception.

Do not place annotations on `private` helpers assuming Spring AOP will intercept them. Final classes/methods also require care depending on proxy strategy; in the demo, Java classes are non-final and methods are invoked through Spring beans.

### 12.2. Using ThreadLocal security context in reactive pipelines

```java
// WRONG for reactive logic depending on Reactor Context:
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

This code can return the wrong or missing context when a pipeline switches threads. In Spring WebFlux, use `ReactiveSecurityContextHolder.getContext()` inside publishers, never calling `block()` or detaching with `subscribe()`.

### 12.3. Using client-supplied ownerId

```java
// WRONG: client self-declares ownerId and service trusts it.
Mono<Document> read(Long id, String ownerId) {
    return documents.findByIdAndOwnerId(id, ownerId);
}
```

Even with `owner_id` in the query, it is still broken if `ownerId` comes straight from query params, headers, or request bodies without comparing against the principal. Take actor ID from verified `Authentication`, or verify membership in the DB.

### 12.4. Checking only roles

`@PreAuthorize("hasRole('READER')")` does not know whether document 101 belongs to Alice or Bob. Use ownership lookups or scoped queries.

### 12.5. Checking permissions then reading by unscoped ID

`@PreAuthorize(...)` checks at time T0, yet `findById(id)` at time T1 could return a resource whose owner changed. For sensitive data, both reads and writes should be scoped by owner/tenant right inside the executing query.

### 12.6. Querying the database with block()

```java
// WRONG: can block the event loop, losing reactive benefits.
boolean allowed =
    documents.findByIdAndOwnerId(id, actor).block() != null;
```

Use `Mono<Boolean>` and return the publisher; Spring Security's reactive method interceptor supports it. If a library is genuinely blocking, use a dedicated bounded executor and thread-offloading strategy — never call `block()` on the Netty event loop.

### 12.7. Treating Mono.empty as ALLOW

A permission bean returning `Mono.empty()` when a user/record is missing can trigger unintended abstain semantics in some layers. Ownership policies should explicitly return **false** when data is missing rather than silently skipping protection.

### 12.8. Swallowing database errors and granting access

`onErrorReturn(true)` or `onErrorResume(e -> Mono.just(true))` turns an outage into a security bypass. Failing closed and recording infrastructure error metrics are mandatory.

### 12.9. Using @PostAuthorize after side effects

Never let a method send notifications, transfer funds, or update documents and only deny afterward in `@PostAuthorize`. Verify permissions **before/atomically with mutation** and use atomic DB predicates.

### 12.10. Testing only the controller

When HTTP rules already require `authenticated()`, a controller might return 403 for another reason, failing to prove the AOP method owner check actually ran. Write tests **calling the service bean directly** with Reactor Context and negative cases.

### 12.11. Caching permissions without invalidation

If a user once owned a document and `canRead=true` is cached by `documentId` without user/tenant, after transferring ownership the former owner retains access. Authorization caches (if needed) must use exact keys, short TTLs/eviction, and invalidation on permission changes; never let `ALLOW` persist indefinitely.

### 12.12. Existence leaks via 403/404 differences

Returning 403 for existing unauthorized records and 404 for missing ones allows ID enumeration. Decide error mapping per threat model, avoid leaking content/metadata, and audit denied accesses. The demo returns 403 for both absent and wrong-owner because the gate runs before the service.

### 12.13. Allowing by default when services are called from jobs

Scheduled jobs and message consumers may lack a `ReactiveSecurityContextHolder`. When a protected method requires an actor, missing context must DENY; jobs with legitimate needs should use a **system actor** with explicit permissions, never hardcoded full-access `ROLE_ADMIN` or secret annotation bypasses.

## 13. Performance and observability when ownership lookup is reactive

Checking ownership before every method can add an extra database round trip:

```text
Request
  -> authentication
  -> permission SELECT EXISTS/SELECT scoped
  -> service SELECT scoped
  -> response
```

Controlled optimizations:

- **Query count:** two SELECTs in the demo are intentional; production can switch to one scoped SELECT in the service if functional/actor checks stay strict.
- **Avoid loading full documents just for a Boolean** when the backend supports efficient `EXISTS` or `SELECT 1 ... LIMIT 1`.
- **Index by ID, tenant, and owner** based on explain plans and workload; avoid blindly adding redundant indexes.
- **Genuine reactive drivers:** R2DBC enables non-blocking I/O; never pretend blocking JDBC is reactive by wrapping it in `Mono.just(...)`.
- **Rate limiting:** prevent authenticated clients from probing thousands of random IDs and overloading the permission DB; apply rate limits, pagination, and backpressure.
- **Timeouts:** enforce DB timeouts per SLO, failing closed when permissions cannot be verified; never wait indefinitely.
- **N+1 with Flux:** do not issue one owner query per element when the list can be scoped by a server-side query.
- **Caching:** slowly changing metadata can be cached, keyed by actor/tenant/permission version with invalidation; never cache global "allow" by document ID alone.
- **Auditing:** record actor ID, resource ID, decision, and policy version as needed; never log raw JWTs, passwords, cookies/session IDs, or private document contents.
- **Metrics:** track permission lookup p50/p95/p99, allow/deny/error counts, DB pool wait, query latency, and retry rates, not just total HTTP latency.
- **Preventing TOCTOU:** mutations need owner/tenant conditions in SQL; caches or read-before-write cannot replace atomic predicates.

Some systems also use PostgreSQL Row-Level Security (RLS) for additional defense; with reactive connection pools, set session/transaction variables for the actor **scoped to the exact connection and transaction lifecycle**, preventing a prior request's tenant context from leaking to the next request.

## 14. Self-check questions

**Question 1.** Why is `authenticated()` on `/api/documents/**` insufficient?  
**Answer:** It only authenticates identity for the route; it does not check who owns a specific document. Alice could still access Bob's ID if the service runs an unscoped `findById(id)`.

**Question 2.** Where should a reactive service reliably obtain the current user?  
**Answer:** `ReactiveSecurityContextHolder.getContext()` inside the publisher, then reading the system-verified `Authentication`/immutable user ID.

**Question 3.** What does `@PreAuthorize("@documentPermission.canRead(#p0)")` mean?  
**Answer:** It calls bean `documentPermission` with the method's first argument; the bean returns `Mono<Boolean>` performing an async lookup before allowing the method to run.

**Question 4.** Should you write `@PreAuthorize("hasRole('READER') && @documentPermission.canRead(#p0)")` without testing?  
**Answer:** No. Some Spring Security 6.3 versions have issues combining Boolean expressions and `Mono<Boolean>`. Put both role and owner checks inside the reactive bean and test on your actual version.

**Question 5.** If `findByIdAndOwnerId(id, auth.getName())` returns `Mono.empty`, what do you conclude?  
**Answer:** No document belongs to that actor with that ID; the permission converts `hasElement()` to false. Do not distinguish missing records from wrong-owner records unless authorized to do so.

**Question 6.** Why is `defaultIfEmpty(false)` better than letting `Mono.empty()` escape the permission bean?  
**Answer:** It explicitly signals DENY when context or records are missing, avoiding abstain or unintended default behavior.

**Question 7.** Should a DB timeout use `onErrorReturn(true)` to avoid disrupting users?  
**Answer:** No. If permissions cannot be verified there is no basis to ALLOW; respond with a controlled error and audit/alert.

**Question 8.** Can self-invocation `this.read(id)` bypass the annotation?  
**Answer:** Yes, in proxy-based Spring AOP. Call through an injected proxy/bean or enforce permission predicates in queries/domain logic.

**Question 9.** Why can READs use a scoped SELECT while WRITEs require extra caution?  
**Answer:** Because owner/permissions can change between check and mutation. `UPDATE`/`DELETE` should include owner/tenant predicates in the same statement or appropriate transaction/isolation.

**Question 10.** When is `@PostAuthorize` useful?  
**Answer:** When inspecting the returned object to decide before handing it to the caller. However, it cannot undo side effects that already occurred inside the method.

**Question 11.** Why is `ownerId` in the URL/header insufficient?  
**Answer:** Clients can forge it. Use the verified actor ID and match against the real owner in the DB.

**Question 12.** Two tenants both have username `alice`; is comparing `owner_id='alice'` enough?  
**Answer:** No. Use verified immutable user IDs and tenant IDs combined with properly scoped membership/ACLs.

**Question 13.** How do you test the service without relying solely on HTTP?  
**Answer:** Invoke the Spring-injected service bean through its proxy inside `StepVerifier`, attach `Authentication` to Reactor Context, and test allowed/denied paths; wrong owner must emit `AccessDeniedException`.

**Question 14.** Why is using `Flux.findAll().filter(...)` by owner dangerous?  
**Answer:** It loads excessive data before filtering, risking leaks via logs/caches/counts and hurting performance; scope in the DB query instead.

**Question 15.** Does an admin privilege in tenant A automatically permit reading tenant B's documents?  
**Answer:** No, unless policy explicitly permits cross-tenant access. Tenant scope must be checked via trusted claims/DB rather than relying on a generic role.

**Conclusion:** In Spring Security WebFlux, **method security combined with reactive data lookups** stops wrong-owner access right at the service boundary. Put policies in beans returning `Mono<Boolean>` when needed for `@PreAuthorize`, read actors from Reactor SecurityContext, have repositories match **ID + owner (+ tenant)**, and enforce fail-closed behavior. For state-mutating operations, place authorization predicates inside the mutation itself to defeat TOCTOU; test both HTTP and direct service paths.

## References

- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`/`@PostAuthorize`, beans returning `Mono<Boolean>`, and reactive interceptors.
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): reading and propagating SecurityContext in Reactor.
- [Spring Security — PreAuthorize API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html): declaring method-protection expressions.
- [Spring Security — Reactive Method Security Spring AOP](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): proxy invocation behavior and custom expressions.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): state-changing requests and CSRF alongside authorization.
- [Spring Data Relational — R2DBC Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html): `ReactiveCrudRepository`, derived queries, and reactive publishers.
- [Spring Boot — R2DBC SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): configuring `spring.r2dbc.url` and embedded H2.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`, `data.sql`, and `spring.sql.init.mode`.
- [R2DBC H2 — ConnectionFactory URI](https://github.com/r2dbc/r2dbc-h2): `r2dbc:h2:mem:///...` syntax and in-memory H2 configuration.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` and Reactor Context in tests.
