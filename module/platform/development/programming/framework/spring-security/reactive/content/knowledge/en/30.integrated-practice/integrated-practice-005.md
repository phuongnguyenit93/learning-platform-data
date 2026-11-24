# Protecting Resources by Owner with Reactive Service-Layer Authorization

## Objectives and Practice Scenario

This integrated lab belongs to **Spring Security – reactive**. Suppose a WebFlux application manages documents: each document has `id`, `ownerId`, and `text`. Both Alice and Bob log in successfully with role `USER`. Alice may read, list, and edit Alice's documents, but **must not read or edit** Bob's documents, even if Alice knows Bob's exact document ID.

After completing this lab, you will be able to:

1. Distinguish **authentication** (who is calling?), **coarse role/authority permissions** (which feature may they use?), and **owner-based authorization** (which *specific record* may they access?).
2. Read the trusted identity from `ReactiveSecurityContextHolder` inside a service, pass it through `Mono`/`Flux`, and emit the right error when unauthorized.
3. Prevent data leaks before emitting `onNext`; avoid using `filter(...)` without handling the unauthorized case.
4. Protect **READ**, **LIST**, and **UPDATE** operations; for UPDATE, keep ownership verification and data mutation in a single atomic operation to mitigate TOCTOU vulnerabilities.
5. Configure WebFlux Security, run the Java 17+ example, and test both allowed and denied paths using `StepVerifier`/`WebTestClient`.
6. Know when to choose HTTP `403` vs. hiding resource existence with `404`; prevent IDOR/BOLA (Broken Object Level Authorization).

**Core focus:** enforce authorization at the **service layer**, because the same service can be called from HTTP controllers, event handlers, internal jobs, or other APIs. `SecurityWebFilterChain` guards the HTTP perimeter but does not inspect each document's owner in the data store.

## 1. Define the Permission Policy Before Writing Code

Given authenticated user `alice`, assume two records:

| ID | Owner in data store | Initial content |
| --- | --- | --- |
| `doc-a` | `alice` | `Alice's content` |
| `doc-b` | `bob` | `Bob's content` |

Example policy:

| Actor | Operation | Resource | Outcome |
| --- | --- | --- | --- |
| Alice (role USER) | GET | `doc-a` | Allowed, returns data |
| Alice (role USER) | GET | `doc-b` | Denied, emits no data |
| Bob (role USER) | GET | `doc-b` | Allowed |
| Alice (role USER) | PUT content | `doc-a` | Allowed, owner unchanged |
| Alice (role USER) | PUT content | `doc-b` | Denied, Bob's data unchanged |
| Alice (role USER) | LIST | all documents | Sees only Alice's documents |
| Unauthenticated user | any protected operation | any | No trusted principal to grant access |
| Alice | GET | non-existent ID | 404, distinct from unauthorized per demo policy |

**Role USER is necessary, not sufficient.** `hasRole('USER')` at the HTTP layer only proves the actor belongs to the group allowed to use the API. Alice and Bob share the exact same role, so role checks cannot replace `document.ownerId == authenticatedUserId`.

**Identity source:** obtain it from the `Authentication` created by Spring Security after verifying credentials/tokens. Never take the claimed owner from `?owner=alice`, an `X-User` HTTP header, or a client-supplied `ownerId` field. The URL ID names the **target object**, not proof that the caller owns it.

**Regarding `authentication.name`:** in this demo, the username is the owner ID. Real applications should use a **stable subject/user ID** from the authenticated principal (e.g., an account UUID or JWT `sub`), because usernames/emails can change, and scope it by tenant in multi-tenant data. All comparisons must use the same identifier space as the database's `owner_id` column.

## 2. Placing the Check Correctly in the Reactive Pipeline

Document read flow under the demo policy:

~~~text
HTTP GET /documents/doc-b
    |
    v
SecurityWebFilterChain
    |  verifies authenticated + ROLE_USER
    v
DocumentController
    |
    v
DocumentService.readById("doc-b")
    |  reads principal from ReactiveSecurityContextHolder
    |  repository.findById("doc-b") -> Mono<Document>
    |  compares ownerId with trusted principal
    +-- equal --> Mono.just(document) --> onNext + onComplete
    |
    +-- different -> Mono.error(AccessDeniedException)
                        --> does not emit onNext(document)
~~~

In the service, use `flatMap` to compare **once the repository emits the object**, before passing it to the caller. If unauthorized, emit `Mono.error(new AccessDeniedException(...))`; never use `doOnNext(logicCheck)` while letting the data continue downstream. You can also query `WHERE id=? AND owner_id=?` directly so another user's record is never even loaded from the database, especially for sensitive data.

**Why check ownership in the service and not just the controller?** Controllers can be reused or new endpoints added later. A public service method exposing `repository.findById(id)` without ownership checks invites IDOR if another controller calls it directly. Enforcing the policy at the service boundary ensures every caller obeys the same rule.

**Why isn't `@PostAuthorize` alone suitable for UPDATE?** Checking the result after the method executes can block returning the value, yet **the write/delete side effect has already happened**. For mutations, authorization must run **before or atomically with the write**; prefer an atomic conditional query in the database.

## 3. Configuring Dependencies and WebFlux Security

The example assumes a Spring Boot 3.x / Java 17+ project with Boot plugin/BOM and Gradle Wrapper configured. Required dependencies in `build.gradle`:

~~~groovy
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

Create package `demo.ownership` and the files listed below. This is a **runnable demo** backed by an in-memory `ConcurrentHashMap` to focus on security logic. Production applications should replace the repository with R2DBC/a reactive driver and enforce conditional queries in the database.

### File 1 — `src/main/java/demo/ownership/OwnershipApplication.java`

~~~java
package demo.ownership;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class OwnershipApplication {

    public static void main(String[] args) {
        SpringApplication.run(OwnershipApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Demo accounts; DO NOT hardcode passwords in production.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/documents", "/documents/**")
                    .hasRole("USER")
                .anyExchange().denyAll())
            .httpBasic(withDefaults())
            .build();
    }
}
~~~

`@EnableWebFluxSecurity` and `ServerHttpSecurity` configure a **reactive HTTP filter chain**; they differ from Servlet's `@EnableWebSecurity` and `HttpSecurity`. `hasRole("USER")` requires the `ROLE_USER` authority by default. Passwords are hashed with `PasswordEncoder`; fixed usernames and passwords are for demo use only. `anyExchange().denyAll()` avoids accidentally exposing out-of-scope routes.

Here we **keep default CSRF protection**. For HTTP `PUT` tests, a valid CSRF token must be supplied (`WebTestClient` below uses `csrf()`). A `curl` PUT with Basic credentials but no CSRF token can return 403 **before even reaching the service**; that does not prove ownership checks work. Do not disable CSRF for apps accepting credentials sent automatically by browsers without assessing the auth model and CSRF risk.

### File 2 — `src/main/java/demo/ownership/Document.java`

~~~java
package demo.ownership;

public record Document(
    String id,
    String ownerId,
    String text
) {}
~~~

`Document` is an immutable Java record. In this demo, `ownerId` is persisted in the store and **cannot be modified from text-edit requests**. This prevents mass assignment, where a client sends JSON with an `ownerId` field to hijack someone else's document. In real systems, separate persistence entities from read/write DTOs instead of binding every client-supplied field onto entities.

### File 3 — `src/main/java/demo/ownership/InMemoryDocuments.java`

~~~java
package demo.ownership;

import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public final class InMemoryDocuments {

    private final ConcurrentHashMap<String, Document> data =
        new ConcurrentHashMap<>();

    public InMemoryDocuments() {
        data.put("doc-a", new Document(
            "doc-a", "alice", "Alice's content"));
        data.put("doc-b", new Document(
            "doc-b", "bob", "Bob's content"));
    }

    public Mono<Document> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(data.get(id)));
    }

    public Flux<Document> findByOwner(String ownerId) {
        return Flux.defer(() -> Flux.fromIterable(data.values())
            .filter(doc -> doc.ownerId().equals(ownerId)));
    }

    // Check ownership and write in a single atomic operation.
    public Mono<Document> replaceTextIfOwned(
            String id, String trustedOwner, String newText) {

        return Mono.fromSupplier(() -> {
            Document result = data.computeIfPresent(id, (key, old) -> {
                if (!old.ownerId().equals(trustedOwner)) {
                    throw new AccessDeniedException("Not the owner");
                }
                if (newText == null || newText.isBlank()) {
                    throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Text must not be blank");
                }
                return new Document(old.id(), old.ownerId(), newText);
            });

            if (result == null) {
                throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found");
            }
            return result;
        });
    }
}
~~~

`ConcurrentHashMap.computeIfPresent` locks per-key mutation for the demo; it replaces `text` only if the **current value's** owner matches `trustedOwner`, leaving no window between “check owner” and “write.” In a database, use a query with an equivalent owner predicate rather than replacing cross-instance transactions with `ConcurrentHashMap` or JVM locks.

`Mono.defer` and `Mono.fromSupplier` create **lazy** publishers: reads or writes execute only on subscription. This in-memory repo performs no blocking I/O; if replaced by synchronous JDBC/JPA, never call them directly on the event loop. Use R2DBC/a reactive driver or isolate legacy blocking calls properly instead of simply wrapping them in `Mono.just(...)`.

**Demo limitation:** `findByOwner` scans the entire map, which is fine for a few fixtures; production must filter by owner and paginate in the database rather than loading everyone's records and applying `Flux.filter` in app memory.

### File 4 — `src/main/java/demo/ownership/DocumentService.java`

~~~java
package demo.ownership;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public final class DocumentService {

    private final InMemoryDocuments documents;

    public DocumentService(InMemoryDocuments documents) {
        this.documents = documents;
    }

    private Mono<String> trustedUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .filter(Authentication::isAuthenticated)
            .filter(auth ->
                !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Authentication required")));
    }

    public Mono<Document> readById(String id) {
        return trustedUsername().flatMap(username ->
            documents.findById(id)
                .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found")))
                .flatMap(doc -> doc.ownerId().equals(username)
                    ? Mono.just(doc)
                    : Mono.error(new AccessDeniedException(
                        "Not the owner"))));
    }

    public Flux<Document> listMine() {
        return trustedUsername()
            .flatMapMany(documents::findByOwner);
    }

    public Mono<Document> replaceText(String id, String newText) {
        return trustedUsername().flatMap(username ->
            documents.replaceTextIfOwned(id, username, newText));
    }
}
~~~

**Read `trustedUsername()` carefully:** authentication is read from the Reactor Context, filtered to exclude null, unauthenticated state, and anonymous tokens; only then is the username extracted. `Authentication.isAuthenticated()` does not necessarily exclude every `AnonymousAuthenticationToken`, so an explicit check is needed. In OAuth2/JWT applications, extract a stable user ID from the verified principal instead of defaulting to username.

In `readById`, the record enters `Mono.just(doc)` only if owned by the caller. Otherwise, downstream receives `AccessDeniedException` via `onError`, **never receiving `onNext(doc)`**. If the document does not exist, the service returns `ResponseStatusException(HttpStatus.NOT_FOUND)`. This is a **demo policy**: authenticated callers can distinguish `403` (ID exists but not owned) from `404` (does not exist). To prevent ID enumeration, adopt a policy that unifies both into 404 while logging internally, applied consistently across read/list/update.

`listMine` obtains the trusted owner and calls the repository filter by owner. With multi-page results, ensure **every page** applies the owner predicate rather than filtering inside a page fetched from shared data. “Query all + filter afterward” also risks empty pages, wrong total counts, and pulling unnecessary data.

`replaceText` also extracts the principal inside the **service**; clients cannot pass a username to claim ownership. The repository's owner check runs inside the same update step, remaining safe even when two concurrent requests race to edit the same ID.

### File 5 — `src/main/java/demo/ownership/DocumentController.java`

~~~java
package demo.ownership;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/documents")
public final class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Document> get(@PathVariable String id) {
        return service.readById(id);
    }

    @GetMapping
    public Flux<Document> mine() {
        return service.listMine();
    }

    @PutMapping("/{id}")
    public Mono<Document> update(
            @PathVariable String id,
            @RequestBody Mono<ReplaceText> body) {
        return body.flatMap(request ->
            service.replaceText(id, request.text()));
    }

    public record ReplaceText(String text) {}
}
~~~

The controller **never accepts `ownerId` from the request** and does not duplicate permission comparison logic. `PUT` accepts only `text`; the service identifies the caller from context and the repository protects record mutation. Every method returns a publisher; never call `subscribe()` or `block()` in the controller. WebFlux subscribes to the publisher during the request lifecycle.

## 4. Manual HTTP Verification

Run the application from the configured project containing the files above:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `gradlew.bat bootRun`. With default port 8080:

~~~bash
# Alice reads her own document: 200.
curl -i -u alice:alice-pass http://localhost:8080/documents/doc-a

# Alice tries to read Bob's document: 403.
curl -i -u alice:alice-pass http://localhost:8080/documents/doc-b

# Bob reads Bob's document: 200.
curl -i -u bob:bob-pass http://localhost:8080/documents/doc-b

# Missing credentials on protected endpoint: 401.
curl -i http://localhost:8080/documents/doc-a

# Non-existent ID: 404 for an authenticated user.
curl -i -u alice:alice-pass http://localhost:8080/documents/no-such-id

# Alice lists only Alice's documents: 200, single item.
curl -i -u alice:alice-pass http://localhost:8080/documents
~~~

Expected HTTP codes correspond to the **demo configuration**. The JSON response for the first valid call looks like:

~~~json
{"id":"doc-a","ownerId":"alice","text":"Alice's content"}
~~~

On denial, the actual error body can vary by Spring Boot version and error handlers; do not rely on a specific stack trace or English message string. The key expectation is the status code and **not leaking Bob's document body**.

For `PUT`, Basic authentication **does not substitute for a CSRF token**. `curl` commands without a CSRF token can return `403` from the CSRF layer before reaching the service. To prove updates by valid/invalid owners, use the `WebTestClient` test with `csrf()` below or build an app-appropriate token fetch/submit flow. Never conclude “the ownership guard works” merely because a CSRF-less `PUT` was rejected.

## 5. Testing the Service with StepVerifier

File **`src/test/java/demo/ownership/DocumentServiceTest.java`** is a standalone test class that runs without an HTTP server or Spring context because owner protection is written **explicitly in the service**, rather than relying on Spring proxies. The test injects authentication into the Reactor Context with `ReactiveSecurityContextHolder.withAuthentication(...)`.

~~~java
package demo.ownership;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentServiceTest {

    private final InMemoryDocuments repository =
        new InMemoryDocuments();
    private final DocumentService service =
        new DocumentService(repository);

    private Authentication user(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username,
            "ignored-test-credential",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void aliceCanReadHerOwnDocument() {
        StepVerifier.create(
            service.readById("doc-a")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .assertNext(doc -> {
                assertEquals("doc-a", doc.id());
                assertEquals("alice", doc.ownerId());
                assertEquals("Alice's content", doc.text());
            })
            .verifyComplete();
    }

    @Test
    void aliceCannotReadBobsDocumentEvenWithSameRole() {
        StepVerifier.create(
            service.readById("doc-b")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void missingAuthenticationIsDenied() {
        StepVerifier.create(service.readById("doc-a"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void aliceCanEditOnlyHerText() {
        StepVerifier.create(
            service.replaceText("doc-a", "Alice updated")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .assertNext(doc -> {
                assertEquals("Alice updated", doc.text());
                assertEquals("alice", doc.ownerId());
            })
            .verifyComplete();

        StepVerifier.create(repository.findById("doc-a"))
            .assertNext(doc -> {
                assertEquals("Alice updated", doc.text());
                assertEquals("alice", doc.ownerId());
            })
            .verifyComplete();
    }

    @Test
    void aliceCannotEditBobsDocumentAndNothingChanges() {
        StepVerifier.create(
            service.replaceText("doc-b", "stolen")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .expectError(AccessDeniedException.class)
            .verify();

        // Postcondition check: genuinely denied, no data written.
        StepVerifier.create(repository.findById("doc-b"))
            .assertNext(doc -> {
                assertEquals("bob", doc.ownerId());
                assertEquals("Bob's content", doc.text());
            })
            .verifyComplete();
    }

    @Test
    void listReturnsOnlyAlicesDocuments() {
        StepVerifier.create(
            service.listMine()
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .assertNext(doc -> {
                assertEquals("alice", doc.ownerId());
                assertEquals("doc-a", doc.id());
            })
            .verifyComplete();
    }

    @Test
    void missingDocumentReturnsNotFound() {
        StepVerifier.create(
            service.readById("not-present")
                .contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(user("alice"))))
            .expectErrorSatisfies(error -> {
                ResponseStatusException exception =
                    (ResponseStatusException) error;
                assertEquals(HttpStatus.NOT_FOUND,
                    exception.getStatusCode());
            })
            .verify();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.ownership.DocumentServiceTest
~~~

The test suite has seven cases. With compatible dependencies and the source from section 3, expect **seven PASS tests**; exact Gradle stdout depends on version/build. Notable points:

- `StepVerifier` actually subscribes to the `Mono`/`Flux`; simply asserting the publisher is non-null never executes authorization logic.
- `contextWrite(withAuthentication(...))` puts authentication into the **Reactor Context**, where `ReactiveSecurityContextHolder` reads it. The test does not rely on `ThreadLocal` `SecurityContextHolder`.
- Because Alice and Bob both have `ROLE_USER`, `aliceCannotReadBobsDocumentEvenWithSameRole` catches **role-only authorization** bugs.
- The UPDATE test does not stop at `expectError`; it re-reads the store and verifies **Bob's text is unchanged**.
- The LIST test confirms another user's data is absent from the returned publisher. When adding more fixtures, use `recordWith`/`collectList` or per-item assertions plus item count checks.
- The not-found test illustrates the 404 policy; if you choose to “hide IDs” by returning 404 to non-owners as well, update both service and HTTP expectations consistently.

`@PreAuthorize`/`@PostAuthorize` (if added later) require methods to be called through a **Spring-managed proxy** for interceptors to fire. The `new DocumentService(...)` test above proves **explicit authorization logic**, not that method-security annotations are active. To test annotations, enable `@EnableReactiveMethodSecurity` and obtain the service bean from the Spring context.

## 6. Testing the WebFlux Security Chain with WebTestClient

To ensure the HTTP controller, filter chain, CSRF, and service are wired properly, add integration test **`src/test/java/demo/ownership/DocumentHttpTest.java`**:

~~~java
package demo.ownership;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@SpringBootTest
class DocumentHttpTest {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(
                applicationContext)
            .apply(SecurityMockServerConfigurers.springSecurity())
            .build();
    }

    @Test
    void httpReadDeniesNonOwner() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/documents/doc-b")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void httpReadAllowsOwner() {
        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/documents/doc-b")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ownerId").isEqualTo("bob");
    }

    @Test
    void httpPutWithValidCsrfStillDeniesNonOwner() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .put().uri("/documents/doc-b")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"stolen\"}")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("bob").roles("USER"))
            .get().uri("/documents/doc-b")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.text").isEqualTo("Bob's content");
    }
}
~~~

**Import syntax note:** Java does not allow line breaks between `import static` and the package name. When copying the test, the two wrapped `import static` lines above must each be written **on a single line**, like this:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
~~~

`@SpringBootTest` defaults to a mock web environment with `WebTestClient.bindToApplicationContext(...).apply(springSecurity())`; it does not open a Netty port. `mockUser` attaches a test principal to the request; `csrf()` legitimately satisfies the CSRF barrier **for isolating ownership checks**. Without a simulated CSRF token, a failing `403` PUT test could be a CSRF failure masking an ownership bug.

Additional items to check in real projects: non-HTTP callers (schedulers/message handlers) can invoke services; `WebTestClient` does not replace `StepVerifier` for service logic. Mutable in-memory tests should isolate fixtures or use separate contexts when tests perform successful mutations to avoid execution-order dependencies. In the file above, the PUT test only executes a denied update and asserts the data stayed intact.

## 7. Upgrading to R2DBC: Putting the Owner Check Inside the Query

The in-memory repository in section 3 illustrates atomicity via `computeIfPresent`. With a real database, it is better to **filter by the authenticated user directly in the query**.

Read one document:

~~~sql
SELECT id, owner_id, text
FROM documents
WHERE id = :document_id
  AND owner_id = :trusted_user_id;
~~~

List documents with pagination:

~~~sql
SELECT id, owner_id, text
FROM documents
WHERE owner_id = :trusted_user_id
ORDER BY id
LIMIT :limit OFFSET :offset;
~~~

Atomic update:

~~~sql
UPDATE documents
SET text = :new_text,
    version = version + 1
WHERE id = :document_id
  AND owner_id = :trusted_user_id;
~~~

`trusted_user_id` must come from `Authentication` in the service and be passed to the repository as a server-side parameter. Never pass a client-declared owner value. If UPDATE affects **0 rows**, the record either does not exist **or** the caller lacks ownership. Choose a uniform 404 policy to avoid leaking existence, or use a controlled follow-up query when distinguishing 403/404 is genuinely required; never return 200 silently when zero rows were modified.

**Why include `WHERE owner` directly on UPDATE?** The pattern below leaves a risk window:

~~~java
// TOCTOU-prone pattern: do not use as the final authorization check.
return repository.findById(id)
    .flatMap(doc -> {
        if (!doc.ownerId().equals(trustedUser)) {
            return Mono.error(new AccessDeniedException("Not owner"));
        }
        return repository.save(doc.withText(newText));
    });
~~~

Between the read/check step and the write step, the record's owner or version may have changed, or another request may have modified it. Adding a transaction helps manage consistency, yet **does not automatically guarantee** ownership remains valid under default isolation levels. An UPDATE query with `WHERE owner_id = ...` checking affected row counts is the final barrier; add `AND version = :expected_version` when optimistic locking is needed.

In multi-tenant applications, add `AND tenant_id = :trusted_tenant_id` to the predicate. Child resources (attachments/comments) must also verify they belong to the document and the document belongs to the user/tenant, rather than trusting an attachment ID alone. Every copy/export/delete/archive API must enforce the matching policy; securing GET while leaving download/export unprotected is still a vulnerability.

## 8. Comparing Three Authorization Approaches and Their Risks

| Check location | Best suited for | Limitations to address |
| --- | --- | --- |
| `SecurityWebFilterChain` / `authorizeExchange` | Login, coarse roles/scopes, URL groups | Unaware of per-row ownership unless backed by custom backend queries |
| `@PreAuthorize` on services | Roles/authorities and simple pre-invocation expressions | Requires proxy invocation; if ownership lives in DB, check against real data and mind async/reactive semantics |
| `@PostAuthorize` on return values | Certain object-level read policies | Runs after business logic produced a result; cannot prevent write/delete side effects |
| Explicit service authorization + repository predicates | Ownership/tenant-dependent rules and live data constraints | Must be applied consistently across all entry points without unguarded repository calls |

Layers can be combined. For instance, a service with `@PreAuthorize("hasAuthority('document:write')")` to enforce feature permission **still must** enforce ownership before or atomically with UPDATE. Enabling annotations requires `@EnableReactiveMethodSecurity`, methods returning `Mono`/`Flux`, and invocation through a Spring bean proxy; calling `this.securedMethod()` inside the same instance bypasses AOP advice.

**Be careful with `@PostAuthorize("returnObject.ownerId == authentication.name")`:** after a method loads an object, the rule can block emitting it to the subscriber, yet it cannot replace query predicates to avoid loading sensitive records and certainly cannot replace pre-UPDATE checks. In this lab, explicit service-level ownership checks keep the code readable, easy to test with `StepVerifier`, and compatible with atomic UPDATE queries.

Another option is a dedicated policy bean:

~~~java
public boolean isOwner(String trustedUserId, Document doc) {
    return doc != null && trustedUserId.equals(doc.ownerId());
}
~~~

This is an illustrative method (not a complete file). For checks requiring I/O, avoid blocking repository calls inside boolean methods; policies should compose reactive publishers in services or use reactive Spring Security authorization APIs. A policy bean lets multiple services share the same rule, provided it stays consistent with data-store predicates.

## 9. 403 or 404? No Single Answer Fits Every Product

When an authenticated user attempts to access someone else's document:

- **403 Forbidden:** clearly states “authenticated but not permitted,” which is convenient for testing and operations. However, the caller learns that the ID likely exists.
- **404 Not Found:** reduces ID enumeration signals when the same response is returned for “does not exist” and “unauthorized.” If adopting this policy, unify GET/PUT/DELETE/LIST and avoid leaks via timing, error bodies, sizes, or counts.
- **401 Unauthorized:** per HTTP authentication semantics, applies when a request is **unauthenticated** or credentials are invalid; do not use 401 arbitrarily for ownership errors when the caller is already signed in.

In the demo, the service uses 403 for owner mismatch and 404 for missing IDs. That is an **illustrative choice**, not a mandatory Spring Security standard. At the direct service test layer, 403/404 are not HTTP statuses yet: `AccessDeniedException` or `ResponseStatusException` is emitted via Reactor, and WebFlux filters/exception handlers translate them into HTTP responses. Verify HTTP behavior with `WebTestClient` or integration requests.

## 10. Common Mistakes and How to Fix Them

1. **Checking only role USER.** Two users with the same role will cross-read each other's data. Add object-specific checks: owner ID or tenant/relationship policies.
2. **Reading owner from body/query.** Clients can send `ownerId=bob` to impersonate. Read the authenticated principal from Reactor Context and compare against the database's owner.
3. **Forgetting to subscribe to `Mono`.** Calling `service.readById(id)` and asserting `assertNotNull` never runs authorization logic. Use `StepVerifier` or `WebTestClient` to activate the pipeline.
4. **Using `filter(doc -> isOwner(doc))` without handling empty.** Can silently turn 403 into 404 or an empty 200 depending on the controller. Explicitly choose `switchIfEmpty`/`Mono.error` per policy.
5. **Relying on `ThreadLocal SecurityContextHolder` in WebFlux.** Reactor switches threads; the user can disappear or bleed across requests. Use `ReactiveSecurityContextHolder` and avoid breaking the chain with manual `subscribe()`.
6. **Checking ownership after save/delete.** Even if the response is blocked, the data was already mutated. Enforce owner predicates atomically inside UPDATE/DELETE.
7. **Separate read, check, and save steps.** Concurrent ownership/permission changes cause TOCTOU races. Use `WHERE owner_id` and check affected row counts.
8. **Filtering LIST after pagination.** Fetching 100 global rows and filtering to the user's items causes empty pages, wrong totals, and over-fetching. Filter in the query before `LIMIT/OFFSET`.
9. **Confusing CSRF 403 with ownership 403.** A PUT test missing CSRF fails early. Use `csrf()` in `WebTestClient` and verify data after the denied path.
10. **Checking only 403 without checking side effects.** An endpoint might mutate data before throwing an exception. Re-assert repository/database state after the request.
11. **Using only `@PostAuthorize` for writes.** The rule runs too late for side effects. Move write authorization to preconditions/persistence predicates.
12. **Testing via `new Service()` while expecting AOP annotations to run.** Explicit logic can be unit-tested that way, whereas `@PreAuthorize` requires a Spring proxy. Use a context-managed bean when testing method security.
13. **Tenant mismatch.** Matching owner IDs across two tenants cause cross-tenant leaks if queries omit tenant. Match both tenant and stable subject per data model.
14. **Caches or search indexes forgetting owner.** A Redis/search/cache key containing only `documentId` that reuses a response built for Bob can leak to Alice. Cache keys and queries must include permission scope or re-apply policies before returning data.
15. **WebSocket/event/message handlers calling the repository directly.** HTTP filters do not protect non-HTTP paths. Place policies in the service or use-case boundary that every caller traverses.
16. **Securing only read endpoints.** Update/delete/upload/export or owner-transfer endpoints each need their own policy; never infer safety from a secured GET.

When troubleshooting “valid logged-in user gets denied,” check in order: (a) authentication and authorities in context, (b) subject/username/tenant ID mapping, (c) owner in the actual data source, (d) `switchIfEmpty`/`onError` branches, (e) proxies if using method security, and (f) web filters/CSRF if errors occur only over HTTP. Never print full JWTs, passwords, or sensitive document contents to logs while debugging.

## 11. Lab Completion Criteria

The system meets requirements only when there is evidence for all of the following:

- Alice and Bob share role `USER` yet **cannot** cross-access each other's documents, while the true owner can still operate normally.
- A missing principal/reactive security context never causes the service to grant access.
- Denied READ never emits `onNext(Document)`; LIST emits only documents belonging to the authenticated owner.
- Unauthorized UPDATE modifies neither text, owner, nor version, verified by re-reading data after denial.
- Clients do not control `trustedUserId`; the service reads it from authentication and the repository checks ownership against current state.
- With a database, UPDATE/DELETE include `WHERE owner_id = :trustedUserId` and handle `rowsUpdated=0` per policy; multi-tenant schemas add a tenant condition.
- WebFlux HTTP tests exercise the real security filter chain, distinguishing 401 authentication, 403 ownership, 404 missing, and 403 CSRF.
- Permission checks never invoke blocking APIs on the event loop; use reactive repositories or properly scheduled adapters when needed.
- Tests cover non-controller service callers, child objects, and cache/search policies whenever real features use them.

## References

- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security – Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – Testing WebFlux: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- Spring Security – Reactive SecurityContextHolder API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- OWASP – Broken Object Level Authorization (BOLA) in API Security: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- Project Reactor – Reactor Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
