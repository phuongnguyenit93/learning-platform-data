# Testing Owner Authorization and Cross-Tenant Access in Spring Security WebFlux

> **Topic:** Spring Security - reactive → Advanced Testing → Testing owner authorization and cross-tenant access. This lesson focuses on testing object-level authorization and tenant boundaries in a WebFlux application using Reactor, JWT, and asynchronous data.

## 1. Goal and threat model

After this lesson, learners can design and run tests proving that an authenticated user still cannot read, modify, delete, or list data belonging to another user or another tenant. Distinguish clearly:

- **Authentication:** a valid token proves identity. Missing/invalid credentials typically return HTTP 401.
- **Functional permissions:** roles/scopes determine which APIs may be called. Missing scopes typically return HTTP 403.
- **Object-level authorization:** even with a read/write scope, the user may only act on records permitted by policy. IDOR/BOLA occurs when changing the ID in a URL exposes someone else's data.
- **Tenant isolation:** a user in tenant A must never access tenant B's data, even if both tenants share identical user IDs, resource names, or sequence numbers.
- **Horizontal escalation:** user A reads/modifies user B's resource at the same privilege level. **Cross-tenant escalation:** user A crosses customer/organization boundaries. These are two independent test axes.

Every request must carry a trusted context: for example, **subject** and **tenant_id** from a verified JWT; resource ID from the path; actual owner ID and tenant ID from persistent storage. Never take subject/tenant for authorization decisions from client-supplied headers or JSON bodies.

## 2. Turning policy into test invariants

Assume a private notes management API: **GET /notes/{id}** and **PUT /notes/{id}**. A note has **id, tenant_id, owner_id, content**. This lesson's example policy: only the owner within the matching tenant may read and update; scopes **notes.read** and **notes.write** are mandatory additional conditions. Other policies such as administrator read-on-behalf must be defined and tested separately; never infer admin privileges from holding a generic scope.

A successful request must simultaneously satisfy:

1. Token is authenticated by the security filter.
2. Proper scope is present for the HTTP method.
3. Claims **sub** and **tenant_id** exist, are non-blank, and come from a trusted source.
4. Record is queried within the current **tenant_id**.
5. Record **owner_id** matches **sub** (or satisfies a defined sharing policy).
6. Every mutation checks tenant/owner conditions directly in the write statement; check-then-act in two steps is not automatically safe against race conditions.

Example response policy: **401** when unauthenticated; **403** when authenticated but missing required scope/claim; **404** when the ID does not exist or is invisible due to wrong tenant/wrong owner. Unifying 404 across object-access cases helps limit ID probing; a system may choose 403 for forbidden objects if its published policy permits, but tests must be consistent and must not leak existence via body, timing, logs, or pagination.

### Minimum test matrix

| Principal | Tenant in token | Resource | Scope | Expected |
| --- | --- | --- | --- | --- |
| alice | tenant-a | alice's note in tenant-a | notes.read | GET 200 |
| alice | tenant-a | bob's note in tenant-a | notes.read | GET 404 |
| alice | tenant-a | alice's note in tenant-b | notes.read | GET 404 |
| alice | tenant-b | alice's note in tenant-b | notes.read | GET 200 |
| alice | tenant-a | tenant-b's note, client sends header X-Tenant-Id=tenant-b | notes.read | GET 404 |
| alice | tenant-a | alice's note in tenant-a | different scope | GET 403 |
| No token | — | Any note | — | GET 401 |
| alice with token missing tenant_id | — | Any note | notes.read | GET 403 |
| alice | tenant-a | alice's note in tenant-b | notes.write | PUT 404, data unchanged |
| alice | tenant-a | alice's note in tenant-a | notes.write | PUT 200, data updated |

**Key point:** verify the rejected response AND verify **data state after the request**. An API can return 403/404 yet still have caused a side effect beforehand; that is still a security bug.

## 3. Running tests across HTTP → SecurityWebFilterChain → Service → Repository

The small fixture below uses Spring Boot 3.3.x, Java 17+, JUnit 5, WebFlux, and Spring Security. The repository is in-memory only so the test runs without a database; in real environments, replace it with tenant-scoped queries (Section 5). Tests use `spring-security-test`'s **mockJwt()** to construct a trusted Authentication inside tests. It **does not** verify JWT signatures, issuer, audience, or JWK; those properties require a dedicated decoder/resource server test suite.

Structure:

~~~text
settings.gradle
build.gradle
src/main/java/example/tenant/TenantNoteApplication.java
src/test/java/example/tenant/TenantNoteSecurityTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tenant-note-security-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/example/tenant/TenantNoteApplication.java**

~~~java
package example.tenant;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class TenantNoteApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantNoteApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Suitable for a Bearer JWT demo API without cookie sessions.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/notes/**")
                        .hasAuthority("SCOPE_notes.read")
                        .pathMatchers(HttpMethod.PUT, "/notes/**")
                        .hasAuthority("SCOPE_notes.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}

record Note(UUID id, String tenantId, String ownerId, String content) {}
record NoteView(UUID id, String content) {}
record NoteUpdate(String content) {}

@Repository
class NoteRepository {
    private final ConcurrentMap<UUID, Note> notes = new ConcurrentHashMap<>();

    NoteRepository() {
        reset();
    }

    void reset() {
        notes.clear();
        notes.put(UUID.fromString("00000000-0000-0000-0000-000000000001"),
                new Note(UUID.fromString("00000000-0000-0000-0000-000000000001"),
                        "tenant-a", "alice", "private-a-alice"));
        notes.put(UUID.fromString("00000000-0000-0000-0000-000000000002"),
                new Note(UUID.fromString("00000000-0000-0000-0000-000000000002"),
                        "tenant-a", "bob", "private-a-bob"));
        notes.put(UUID.fromString("00000000-0000-0000-0000-000000000003"),
                new Note(UUID.fromString("00000000-0000-0000-0000-000000000003"),
                        "tenant-b", "alice", "private-b-alice"));
    }

    Mono<Note> findByTenantAndId(String tenantId, UUID id) {
        return Mono.defer(() -> Mono.justOrEmpty(notes.get(id))
                .filter(note -> note.tenantId().equals(tenantId)));
    }

    // Check tenant and owner directly inside the fixture's atomic write operation.
    Mono<Note> updateOwned(String tenantId, String ownerId, UUID id, String content) {
        return Mono.defer(() -> {
            Note result = notes.computeIfPresent(id, (key, existing) ->
                    existing.tenantId().equals(tenantId)
                            && existing.ownerId().equals(ownerId)
                            ? new Note(id, tenantId, ownerId, content)
                            : existing);
            return Mono.justOrEmpty(result)
                    .filter(note -> note.tenantId().equals(tenantId)
                            && note.ownerId().equals(ownerId));
        });
    }
}

@Service
class NoteService {
    private final NoteRepository repository;

    NoteService(NoteRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_notes.read')")
    public Mono<NoteView> read(UUID id, String subject, String tenantId) {
        if (missing(subject) || missing(tenantId)) {
            return Mono.error(new ResponseStatusException(HttpStatus.FORBIDDEN));
        }
        return repository.findByTenantAndId(tenantId, id)
                .filter(note -> note.ownerId().equals(subject))
                .map(note -> new NoteView(note.id(), note.content()))
                .switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    @PreAuthorize("hasAuthority('SCOPE_notes.write')")
    public Mono<NoteView> update(UUID id, String subject, String tenantId,
                                 NoteUpdate request) {
        if (missing(subject) || missing(tenantId)) {
            return Mono.error(new ResponseStatusException(HttpStatus.FORBIDDEN));
        }
        if (request.content() == null || request.content().isBlank()) {
            return Mono.error(new ResponseStatusException(HttpStatus.BAD_REQUEST));
        }
        return repository.updateOwned(tenantId, subject, id, request.content())
                .map(note -> new NoteView(note.id(), note.content()))
                .switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    private static boolean missing(String value) {
        return value == null || value.isBlank();
    }
}

@RestController
@RequestMapping("/notes")
class NoteController {
    private final NoteService service;

    NoteController(NoteService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Mono<NoteView> read(@PathVariable UUID id, @AuthenticationPrincipal Jwt jwt) {
        return service.read(id, jwt.getSubject(), jwt.getClaimAsString("tenant_id"));
    }

    @PutMapping("/{id}")
    Mono<NoteView> update(@PathVariable UUID id, @RequestBody Mono<NoteUpdate> body,
                          @AuthenticationPrincipal Jwt jwt) {
        return body.flatMap(request ->
                service.update(id, jwt.getSubject(), jwt.getClaimAsString("tenant_id"), request));
    }
}
~~~

In the fixture, **findByTenantAndId** filters by tenant before checking ownership; **updateOwned** avoids a separate two-step read-check-write. Methods return **Mono** and never call **block()**. `SecurityWebFilterChain` handles scopes at the HTTP layer; `@PreAuthorize` protects the service if callers exist outside the controller; tenant/owner constraints are still enforced in the domain/data layer.

**src/test/java/example/tenant/TenantNoteSecurityTest.java**

~~~java
package example.tenant;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class TenantNoteSecurityTest {
    private static final UUID ALICE_A =
            UUID.fromString("00000000-0000-0000-0000-000000000001");
    private static final UUID BOB_A =
            UUID.fromString("00000000-0000-0000-0000-000000000002");
    private static final UUID ALICE_B =
            UUID.fromString("00000000-0000-0000-0000-000000000003");

    @Autowired ApplicationContext context;
    @Autowired NoteRepository repository;

    // Sufficient to initialize OAuth2 Resource Server in the HTTP test fixture.
    @MockBean ReactiveJwtDecoder jwtDecoder;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        repository.reset();
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private WebTestClient actor(String subject, String tenant, String scope) {
        return client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject(subject).claim("tenant_id", tenant))
                .authorities(new SimpleGrantedAuthority("SCOPE_" + scope)));
    }

    @Test
    void ownerCanReadWithinOwnTenant() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.content").isEqualTo("private-a-alice");
    }

    @Test
    void peerInSameTenantCannotRead() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", BOB_A)
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void sameSubjectInDifferentTenantCannotRead() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .exchange().expectStatus().isNotFound();

        actor("alice", "tenant-b", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("private-b-alice");
    }

    @Test
    void clientSuppliedTenantAndUserHeadersDoNotOverrideJwt() {
        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .header("X-Tenant-Id", "tenant-b")
                .header("X-User-Id", "bob")
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void noAuthenticationIsUnauthorized() {
        client.get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongScopeIsForbidden() {
        actor("alice", "tenant-a", "unrelated")
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void missingTenantClaimIsForbidden() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt.subject("alice"))
                        .authorities(new SimpleGrantedAuthority("SCOPE_notes.read")))
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void deniedWriteMustNotChangeOtherTenantData() {
        actor("alice", "tenant-a", "notes.write")
                .put().uri("/notes/{id}", ALICE_B)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteUpdate("intrusion"))
                .exchange().expectStatus().isNotFound();

        actor("alice", "tenant-b", "notes.read")
                .get().uri("/notes/{id}", ALICE_B)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("private-b-alice");
    }

    @Test
    void deniedWriteMustNotChangeOtherOwnersData() {
        actor("alice", "tenant-a", "notes.write")
                .put().uri("/notes/{id}", BOB_A)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteUpdate("intrusion"))
                .exchange().expectStatus().isNotFound();

        actor("bob", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", BOB_A)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("private-a-bob");
    }

    @Test
    void ownerCanUpdateOwnNote() {
        actor("alice", "tenant-a", "notes.write")
                .put().uri("/notes/{id}", ALICE_A)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteUpdate("updated-by-owner"))
                .exchange().expectStatus().isOk();

        actor("alice", "tenant-a", "notes.read")
                .get().uri("/notes/{id}", ALICE_A)
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.content").isEqualTo("updated-by-owner");
    }
}
~~~

Run from the directory containing **build.gradle** using **gradle test** (or **./gradlew test** when a compatible Gradle Wrapper is present). The tests need no external HTTP server or real IdP because WebTestClient binds to the Spring ApplicationContext and **mockJwt()** supplies Authentication in tests. Expected outcome: all ten cases pass with HTTP 200/401/403/404 matching the matrix. Do not infer from this test that production JWT signatures are properly verified.

**Implementation note:** the fixture intentionally uses **@MockBean** compatible with Boot 3.3.x; in newer Boot versions you can switch to the corresponding mock bean API. For browser-facing applications using cookies/sessions, do not copy the CSRF-disabled configuration of a Bearer-only API.

## 4. Why testing across multiple layers matters

- **HTTP integration / WebTestClient:** proves `SecurityWebFilterChain`, authentication principal, route mapping, statuses, and service work end-to-end.
- **Service/method security:** use **StepVerifier** or WebTestClient to prove reactive authorization along the publisher chain; with `@PreAuthorize`, callers must carry security context in **Reactor Context**. Never use traditional ThreadLocal **SecurityContextHolder.getContext()** to reason about WebFlux context.
- **Persistence integration:** create real rows for two tenants and two owners, run R2DBC queries against a test database, and verify queries return no out-of-scope rows and mutations touch no out-of-scope rows. Unit tests that over-mock repositories can hide SQL missing a tenant predicate.
- **JWT decoder/resource server:** test signature, issuer, audience, expiration, key rotation, scope/role mapping, and tenant claims separately; **mockJwt()** only tests logic after the principal is created.
- **End-to-end:** with a real API gateway, forwarded headers, tenant resolution, caching, and messaging, test requests through a production-like ingress; never let gateway headers become an unconditional source of authority.

If testing pure service methods:
 
~~~java
// Intentional pseudocode: build application-appropriate Authentication and place it
// into Reactor Context; do not use ThreadLocal for WebFlux.
// StepVerifier.create(service.read(id, subject, tenant)
//         .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth)))
//     .expectErrorMatches(error -> /* expected policy */)
//     .verify();
~~~

The snippet above illustrates Reactor context and is **not** a standalone test: you must define **service**, **id**, **subject**, **tenant**, and **auth**. The WebTestClient tests above are complete examples ready for a demo project.

## 5. Pushing conditions into SQL/R2DBC to prevent data leaks

In database-backed systems, place the tenant predicate in the **WHERE** clause of both reads and writes. Use explicit repository method names or queries; for example, with PostgreSQL/Spring Data R2DBC:

~~~sql
-- Read an owned record within the right tenant.
SELECT id, tenant_id, owner_id, content, version
FROM notes
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :subject;

-- Write with authorization control and lost-update protection.
UPDATE notes
SET content = :content, version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND owner_id = :subject
  AND version = :expectedVersion;
~~~

This is illustrative SQL using data-access-layer named bind parameters; running directly in `psql` requires the appropriate bind syntax. In Spring Data R2DBC, an UPDATE can use **@Modifying @Query** returning **Mono<Integer>** for affected row count. **0 rows** may mean missing ID, wrong tenant, wrong owner, or version conflict; map the response per your chosen policy so attackers cannot deduce whether a record exists.

Persistence tests must seed at least three records: alice/tenant-a, bob/tenant-a, and alice/tenant-b. After an unauthorized UPDATE, inspect the original record using a test fixture with global read access to confirm **row count = 0 and content/version unchanged**. For listing, pagination, and search, tenant filtering must be inside the **query before** applying limit/offset/count; filtering in memory after pagination can leak the count or ordering of another tenant's data. Consider per-tenant unique indexes on natural keys, foreign keys and joins that include tenant, and PostgreSQL Row-Level Security if used as an extra defense-in-depth layer; RLS policies and session/connection pooling must be tested separately.

## 6. Expanding tests for real attack paths

1. **Single-object GET:** non-existent ID, same-tenant peer's ID, cross-tenant ID, matching subject across tenants; test both random and guessable IDs.
2. **List/search/export:** response body, `totalElements`, aggregations, cursors, sorting, and exported files contain only the valid tenant; never return out-of-scope results and filter in Java after pagination.
3. **POST/create:** client sends forged **tenantId** or **ownerId** in the body; server must ignore or reject per contract and assign identity from the trusted source. Inspect the actually persisted record.
4. **PUT/PATCH/DELETE:** tamper with ID in path, tenant/owner in body, or batch multiple IDs mixing two tenants; reject the whole request or handle per item according to a clear contract with zero out-of-scope side effects.
5. **Object relationships:** create a note in tenant A referencing a parent/project/attachment in tenant B; every foreign key capable of crossing tenants must be checked, not only the root record.
6. **Cache and async:** cache keys must include tenant (and principal for personalized results); when Reactor switches schedulers or spawns another publisher, propagate security context properly. Message consumers, scheduled jobs, WebSockets, SSE, and background processes need dedicated trusted tenant context propagation.
7. **Scope/role:** test combinations of missing scopes, excess scopes, tenant A admin accessing tenant B, disabled principals, and locked tenants. Internal operator admin rights and tenant admin rights are distinct policies.
8. **Spoofed requests:** test **X-Tenant-Id**, **X-User-Id** headers, query strings, JSON bodies, and forwarded headers; none may self-elevate privileges. If a gateway asserts tenant via a signed header, trust the header only after verification and block direct bypass requests.
9. **Race / TOCTOU:** send concurrent update, ownership transfer, membership revocation, and delete requests; use constraints/transactions/optimistic locking so mutations enforce permissions at write time.
10. **No leakage:** error responses contain no secret titles/contents/owners/tenants, logs and traces do not leak tokens or other tenants' data; status/timing differences do not disclose IDs per security requirements.

For critical negative cases, build fixtures with a *canary marker* such as **private-b-alice** and assert it never appears in responses; also re-query the database to verify invariants. When using parameterized tests, each case should explicitly name subject, tenant, scope, resource, and action; avoid a catch-all mock returning 404 for everything, which stays green even when routes/services never run.

## 7. Common pitfalls and how to catch them with tests

| Pitfall | Consequence | Test that catches it |
| --- | --- | --- |
| Checking only role or `@PreAuthorize` without checking the record | Holding the scope lets you read any ID | Alice reading Bob's ID in the same tenant → must be denied |
| Checking only `owner_id`, omitting `tenant_id` | Matching subjects across tenants allow cross-tenant access | Alice in tenant-a reading Alice's note in tenant-b → denied |
| Taking tenant from client-supplied header/body | Users pick a victim's tenant themselves | Header spoofing leaves outcome unchanged |
| Repository `findById(id)` followed by in-memory filtering | Risk of data exposure via logs/joins/caches; non-atomic mutation | DB integration and concurrent update tests |
| Asserting only HTTP status | Operation may have partially written before returning an error | Assert value/version unchanged after forbidden request |
| Using a mock service returning 404 for all requests | False-green tests that never test real domain authorization | Require 200 cases and verify legitimate side effects |
| Arbitrary `block()`, manual `subscribe()`, or ThreadLocal | Lost/swapped reactive security context; out-of-band side effects | Test async flows and auth context propagation |
| Cache key by ID without tenant | Previous tenant's data leaks to next tenant | Two tenants sharing a resource key, called interleaved |
| Testing only single-item GET | List, export, batch, and linked objects remain vulnerable to BOLA | Checklist per endpoint and per query path |

## 8. Acceptance checklist and limitations

An implementation passes this lab when: (1) positive GET/PUT 200 cases exist and verify accurate data; (2) all missing auth, scope, owner, and tenant cases match policy; (3) tampering with headers/bodies/IDs fails to escalate privileges; (4) database reads/lists/writes constrain both tenant and owner; (5) forbidden mutations cause no side effects; (6) real JWT/resource server verification is tested separately; (7) races, pagination/caching, and object relationships are tested on implemented endpoints.

**Example limitations:** the in-memory repository is intentionally simplified and does not prove transaction semantics, foreign keys, RLS, isolation levels, or production SQL correctness. Run additional integration tests against a real database or Testcontainers before concluding tenant isolation is sound.