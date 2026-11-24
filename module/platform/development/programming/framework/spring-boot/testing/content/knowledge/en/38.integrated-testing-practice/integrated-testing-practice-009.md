# Testing Authentication, Ownership, and Cross-Tenant Access — Spring Boot Security

## 1. Problem: successful login does not mean access to every resource

Suppose a platform stores documents for multiple organizations (tenants). Users **alice** and **bob** belong to tenant `acme`; **carol** belongs to tenant `beta`. Alice owns document A, and Bob owns document B. Each tenant has an administrator allowed to view/edit documents of members within **that tenant**, while forbidden from touching documents of another tenant.

An API can enforce login yet still suffer from a severe vulnerability:

~~~http
GET /tenants/acme/documents/123
Authorization: Basic ...
~~~

If the code merely runs `repository.findById(123)` and returns the result, Bob or Carol can swap the ID to read Alice's document. This is **Broken Object Level Authorization (BOLA)**, commonly called **Insecure Direct Object Reference (IDOR)**. If the API grants admin privileges while omitting tenant boundaries, a tenant admin can also read or delete another tenant's data. This is not a password bug: it is an **authorization bug at the resource level and tenant context**.

This lesson guides you through designing an **integration test suite** for Spring Boot 3.5 / Java 17, covering illustrative HTTP Basic authentication, the Spring Security filter chain, ownership/tenant policy, a real JPA repository, MockMvc HTTP requests, and negative security cases. Data runs on in-memory H2 so the example stays reproducible without Docker; when production uses PostgreSQL and database-level isolation, add a PostgreSQL/Testcontainers integration suite as an extension. Never claim H2 substitutes for production database-layer security testing.

### Learning outcomes

1. Distinguish **authentication**, **function-level authorization**, **object-level authorization**, **ownership**, and **tenant isolation**.
2. Resolve principals, authorities/roles, and tenant memberships from **server-authenticated sources**, never from client-supplied headers or bodies.
3. Write explicit policies for owners, other members, same-tenant admins, and cross-tenant admins.
4. Distinguish HTTP `401 Unauthorized`, `403 Forbidden`, and `404 Not Found` when designing APIs that avoid leaking existence.
5. Test reading, listing, creating, updating, and deleting against other users' IDs and other tenants.
6. Prevent **mass assignment**: clients must never set `ownerUsername` or `tenantId` on an entity.
7. Test CSRF on create/update/delete requests; never disable security filters in MockMvc.
8. Verify JSON responses leak no sensitive fields and lists never mix tenants.
9. Understand the strengths and limits of `@WithMockUser`, `httpBasic`, `csrf()`, MockMvc, `@WebMvcTest`, and `@SpringBootTest`.
10. Run full context + JPA in integration tests, keep fixtures isolated, and avoid tests fooled by mocks.
11. Extend tests to JWT resource servers, PostgreSQL RLS, caches, async jobs, and multi-tenant reports.
12. Design CI gates and security test matrices aligned with OWASP API Security Top 10.

## 2. Terminology and attack surface

### 2.1 Authentication

Answers **“who is calling?”**. For example, HTTP Basic credentials are processed by Spring Security to build an `Authentication` with principal name `alice`. Production may use session cookies, OIDC login, or JWT bearer tokens after validating signature, issuer, audience, expiration, and claims.

- No credentials sent: request is treated as anonymous.
- Wrong password/token: authentication fails.
- Valid credentials: caller has an `Authentication`, **not automatic permission to read any document ID**.

### 2.2 Function-level authorization

Answers **“is the caller permitted to perform this kind of action?”**. For instance, `ROLE_TENANT_ADMIN` allows managing documents in one's own tenant; `ROLE_USER` allows editing one's own documents.

Checking `hasRole("USER")` on a URL alone is insufficient: every user has `USER`, yet must not edit every record.

### 2.3 Object-level authorization / ownership

Answers **“does the caller have permission on this exact record?”**. For example:

- Alice reads A: allowed.
- Bob reads A in the same tenant: denied if policy allows only owner/admin.
- Carol reads A via a guessable ID: denied even though the ID exists.
- Acme's admin reads Alice's document: allowed if policy grants that privilege.

Never rely on “unguessable IDs” as a substitute for ownership checks. UUIDs make enumeration harder, not replace authorization.

### 2.4 Tenant isolation

Answers **“does the caller belong to the tenant holding this record?”**. When a URL contains `/tenants/{tenantId}`, `tenantId` is still **client-chosen input**. The server must check it against trusted memberships in the authenticated principal, then query the DB **by both tenant and record ID**.

Never trust a client-sent `X-Tenant-Id` header as the authenticated tenant. A header is at most a requested context switch that must still be verified against memberships if supported.

### 2.5 BOLA, BFLA, and mass assignment

| Risk | Example | Test suite check |
| --- | --- | --- |
| BOLA/IDOR | Bob swaps ID to GET/PATCH Alice's document | Swap object IDs across accounts |
| BFLA | Regular user calls disallowed admin endpoint | Swap roles on the same function |
| Cross-tenant leak | Beta admin GETs acme document | Swap tenant paths/record IDs |
| Broken object property auth | POST sets `ownerUsername=alice` | Reject/ignore protected attributes |
| List/query isolation | GET list returns another tenant's docs | Inspect every row/aggregate |
| CSRF | Authenticated browser forced to POST/PATCH | Missing/invalid CSRF => 403 |
| Authentication bypass | Anonymous request returns data | 401 before service |
| Cache bleed | User B gets A's cached response | Cache key/context tests |

## 3. Demo policy: a concrete permission matrix

Sample dataset:

| Principal | Role | Membership | Ownership |
| --- | --- | --- | --- |
| alice | ROLE_USER | TENANT_acme | document “Alpha draft” |
| bob | ROLE_USER | TENANT_acme | document “Bob notes” |
| carol | ROLE_USER | TENANT_beta | document “Beta plan” |
| admin-acme | ROLE_TENANT_ADMIN | TENANT_acme | needs no ownership to administer acme |
| admin-beta | ROLE_TENANT_ADMIN | TENANT_beta | must not touch acme |
| guest | ROLE_USER | no tenant membership | cannot view any tenant's documents |

Specific rules:

1. Every `/tenants/{tenantId}/documents/**` endpoint requires authentication.
2. Callers must hold authority `TENANT_{tenantId}` to act within the tenant in the URL.
3. Regular users can only read/list/edit/delete documents where `ownerUsername == authentication.getName()`.
4. `ROLE_TENANT_ADMIN` can view/edit/delete other members' documents **if within the same tenant**.
5. POST accepts only `title`; the server sets `tenantId` from the verified route and `ownerUsername` from the authenticated principal.
6. Non-existent documents and failed ownership checks both return `404` to avoid confirming whether an ID exists to unauthorized callers.
7. Lacking membership in the route's tenant returns `403`, regardless of record ID.
8. Unauthenticated requests or bad passwords return `401` via the HTTP Basic entry point.
9. CSRF remains enabled in the demo; POST/PATCH/DELETE with credentials but missing a CSRF token are rejected.
10. JSON output exposes only `id` and `title`; owner and tenant are not serialized automatically.

### 3.1 Why use both 403 and 404?

This is a policy choice, **not the only valid HTTP rule**. `403` indicates the caller is identified yet lacks tenant membership/permission. `404` on failed owner checks prevents callers from distinguishing “ID does not exist” from “ID belongs to someone else”. A system seeking zero existence leakage may return `404` even on tenant mismatches, provided the policy is consistent and tested accurately.

**Important:** never let GET return 404 while PATCH returns 403 revealing record existence if hiding existence is the goal. Reads, edits, and deletes must share the same record visibility check.

## 4. In-JVM end-to-end test architecture

~~~text
MockMvc request
    |
    +-- Spring Security FilterChainProxy
    |     +-- HTTP Basic authentication
    |     +-- SecurityContext/Authentication
    |     +-- CSRF for unsafe methods
    |     +-- anyRequest().authenticated()
    |
    v
DocumentController
    |
    +-- route tenantId treated as untrusted input
    +-- authenticated principal resolved from security context
    |
    v
DocumentService
    |
    +-- validates tenant membership
    +-- checks owner OR same-tenant admin
    +-- scopes database lookup/list by tenantId
    |
    v
DocumentRepository (real Spring Data JPA)
    |
    v
H2 in-memory database for runnable demo
~~~

Use `@SpringBootTest` + `@AutoConfigureMockMvc` so the filter chain, controller, service, repository, transactions, and JSON serialization all execute together. Never use `@MockitoBean DocumentService` in the primary test, because mocking the service bypasses the very authorization logic we must prove.

H2 serves here purely as a simple persistence fixture. When production uses PostgreSQL RLS, stored procedures, JSONB, or database-specific tenant constraints, add a supplementary integration suite on **the real production database engine**.

## 5. File tree for the Java 17+ / Spring Boot 3.5 project

~~~text
tenant-security-demo/
  settings.gradle
  build.gradle
  src/main/java/example/tenant/
    TenantSecurityApplication.java
    SecurityConfig.java
    TenantDocument.java
    TenantDocumentRepository.java
    TenantDocumentService.java
    TenantDocumentController.java
  src/main/resources/
    application.properties
  src/test/java/example/tenant/
    TenantDocumentSecurityTest.java
  .github/workflows/
    security-tests.yml
~~~

This lesson creates **one integration test class** covering multiple users and tenant scenarios. No Docker is needed to run the demo. In production, replace in-memory test users with real authenticated identities/authorization policies and add a database-isolation integration suite.

## 6. `settings.gradle`

~~~groovy
rootProject.name = 'tenant-security-demo'
~~~

## 7. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    // Database fixture for this runnable demonstration.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Deterministic baseline for mutable database fixtures.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
    reports {
        html.required = true
        junitXml.required = true
    }
}
~~~

Why are these dependencies needed?

- `spring-boot-starter-web`: MVC controllers, Jackson JSON, MockMvc infrastructure.
- `spring-boot-starter-security`: HTTP Basic authentication, `SecurityFilterChain`, CSRF, authorization.
- `spring-boot-starter-data-jpa`: real repository and transactions.
- `spring-boot-starter-validation`: `@Valid`, `@NotBlank`, `@Size` on request DTOs.
- `h2`: in-process sample database requiring no Docker or credentials.
- `spring-boot-starter-test`: JUnit Jupiter, Spring testing/MockMvc.
- `spring-security-test`: `httpBasic()` and `csrf()` request post-processors.
- `junit-platform-launcher` and `useJUnitPlatform()`: run Jupiter on Gradle.

**Never disable Spring Security filters** with `@AutoConfigureMockMvc(addFilters=false)`. Doing so turns tests “green” while authentication, CSRF, and authorization filters never execute.

## 8. `application.properties`

`src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:tenant_security_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false

# A strict request DTO contract rejects attempts to add owner/tenant fields.
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

`create-drop` suits an ephemeral demo database **with no production migrations**. Real systems should use Flyway/Liquibase schemas and `ddl-auto=validate` per policy rather than letting ORM generate production schemas.

`spring.jackson.deserialization.fail-on-unknown-properties=true` ensures JSON containing properties outside the request record (like `ownerUsername` or `tenantId`) is rejected rather than silently bound. Even if an organization chooses **ignore unknown properties** for backward compatibility, the DTO itself must **never expose** sensitive fields for clients to set.

## 9. `TenantSecurityApplication.java`

`src/main/java/example/tenant/TenantSecurityApplication.java`:

~~~java
package example.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantSecurityApplication.class, args);
    }
}
~~~

Package `example.tenant` holds the controller, service, repository, entity, and security config so component scanning finds all required beans.

## 10. `TenantDocument.java` — entity with `tenant_id` and `owner`

`src/main/java/example/tenant/TenantDocument.java`:

~~~java
package example.tenant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

@Entity
@Table(
    name = "tenant_documents",
    indexes = @Index(
        name = "idx_document_tenant_owner",
        columnList = "tenant_id,owner_username"))
public class TenantDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 32)
    private String tenantId;

    @Column(name = "owner_username", nullable = false, length = 80)
    private String ownerUsername;

    @Column(name = "title", nullable = false, length = 120)
    private String title;

    protected TenantDocument() {
        // JPA constructor.
    }

    public TenantDocument(
            String tenantId,
            String ownerUsername,
            String title) {
        this.tenantId = tenantId;
        this.ownerUsername = ownerUsername;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerUsername() {
        return ownerUsername;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

### 10.1 Why must the entity never serve directly as `@RequestBody`?

If a controller accepts `@RequestBody TenantDocument`, a client can send:

~~~json
{
  "title": "Report",
  "ownerUsername": "someone-else",
  "tenantId": "different-tenant"
}
~~~

That creates a **mass assignment / broken object property-level authorization** vulnerability. Even if service authorization blocks some cases, the safer design is a **DTO allowlist**: put only client-editable fields in the request record; the server assigns tenant and owner.

In the demo, `tenantId` and `ownerUsername` lack public setters; still, never rely on missing setters as your sole defense. The service remains responsible for setting identity from verified authentication, and the strict JSON request DTO blocks injecting protected fields.

### 10.2 Why does every document need `tenant_id`?

In shared-table multi-tenancy, every record needs a trustworthy partition key for queries and filtering. Storing only `ownerUsername` and assuming usernames never collide across tenants is unsafe: two tenants might share display names or local account IDs. Production should use immutable tenant IDs and subject/account IDs from the identity provider rather than mutable usernames as ownership keys.

## 11. `TenantDocumentRepository.java` — queries must be tenant-scoped

`src/main/java/example/tenant/TenantDocumentRepository.java`:

~~~java
package example.tenant;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface TenantDocumentRepository
        extends JpaRepository<TenantDocument, Long> {

    Optional<TenantDocument> findByIdAndTenantId(
            Long id, String tenantId);

    List<TenantDocument>
        findByTenantIdAndOwnerUsernameOrderByIdAsc(
                String tenantId, String ownerUsername);

    List<TenantDocument> findByTenantIdOrderByIdAsc(
            String tenantId);
}
~~~

Key methods:

- `findByIdAndTenantId`: includes both object ID and tenant ID in the SQL lookup, reducing the risk of fetching another tenant's row and forgetting to check it.
- `findByTenantIdAndOwnerUsernameOrderByIdAsc`: regular users list only their own docs inside the current tenant.
- `findByTenantIdOrderByIdAsc`: called only by the service for a tenant admin whose membership and role were verified.
- `JpaRepository.findById` still exists by inheritance; **never** use it as the default lookup in multi-tenant endpoints without tenant checks.

This provides defense in depth at the data-access layer, though the repository itself cannot stop other code from calling `findAll` or `findById`. Real projects should enforce policy at service/query boundaries, review code carefully, and consider database Row Level Security (RLS) for stronger tenant isolation.

### 11.1 Avoid concatenating SQL with tenant IDs manually

Never build native SQL via string concatenation with `tenantId` or `ownerUsername`. Spring Data derived queries and parameter binding prevent SQL injection. Tenant membership **must still be verified** before binding; parameterized SQL does not perform authorization for you.

## 12. `SecurityConfig.java` — HTTP Basic, users, and CSRF

`src/main/java/example/tenant/SecurityConfig.java`:

~~~java
package example.tenant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String password = encoder.encode("test-secret");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(password)
                .authorities("ROLE_USER", "TENANT_acme")
                .build(),
            User.withUsername("bob")
                .password(password)
                .authorities("ROLE_USER", "TENANT_acme")
                .build(),
            User.withUsername("carol")
                .password(password)
                .authorities("ROLE_USER", "TENANT_beta")
                .build(),
            User.withUsername("admin-acme")
                .password(password)
                .authorities(
                    "ROLE_TENANT_ADMIN", "TENANT_acme")
                .build(),
            User.withUsername("admin-beta")
                .password(password)
                .authorities(
                    "ROLE_TENANT_ADMIN", "TENANT_beta")
                .build(),
            User.withUsername("guest")
                .password(password)
                .authorities("ROLE_USER")
                .build()
        );
    }
}
~~~

### 12.1 Why use in-memory accounts?

So the entire demo stays independent of an external identity provider. The fixed `test-secret` credential is a **test fixture**, not a production password. Never expose this in-memory configuration on a public network or use it in production. HTTP Basic is **safe only over HTTPS** because Base64 does not encrypt secrets.

In production, depending on architecture, replace this bean with Spring Security OAuth2 Resource Server JWT, OIDC login/session, or a real `UserDetailsService`. **JWT signatures, issuer, audience, expiry, key rotation, and claim mappings must be verified from trusted sources** before extracting tenant memberships.

### 12.2 Why is `anyRequest().authenticated()` not enough?

It stops anonymous requests at the filter chain. Once Alice logs in, however, the filter chain **does not know** whether Alice may read document 123; record/tenant policies live in the service. Tests must exercise **both layers**.

### 12.3 `ROLE_TENANT_ADMIN` does not mean global admin

A tenant admin must also hold authority `TENANT_acme`. If the caller holds the admin role without membership in tenant beta, the service denies access. **Role scopes always require tenant scopes**, preventing the classic bug where “company A's admin becomes admin of the entire platform”.

### 12.4 Why not `csrf.disable()`?

The demo uses HTTP Basic, which browsers can cache and send automatically in certain contexts; the CSRF threat model must be evaluated seriously. Keep default CSRF enabled for unsafe methods and verify `csrf()` in MockMvc. For stateless bearer-token APIs that never rely on cookies or browser-auto-sent credentials, a different CSRF policy may fit, yet **never** blindly disable CSRF across the app just to make POST tests pass.

## 13. `TenantDocumentService.java` — policy at the service boundary

`src/main/java/example/tenant/TenantDocumentService.java`:

~~~java
package example.tenant;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TenantDocumentService {

    private final TenantDocumentRepository repository;

    public TenantDocumentService(
            TenantDocumentRepository repository) {
        this.repository = repository;
    }

    private void requireTenant(
            String tenantId, Authentication authentication) {

        if (authentication == null
                || !authentication.isAuthenticated()) {
            throw new AccessDeniedException(
                    "Authentication required");
        }

        String required = "TENANT_" + tenantId;

        boolean member = authentication.getAuthorities()
                .stream()
                .anyMatch(authority ->
                    required.equals(authority.getAuthority()));

        if (!member) {
            throw new AccessDeniedException(
                    "Tenant membership required");
        }
    }

    private boolean isTenantAdmin(Authentication authentication) {
        return authentication.getAuthorities()
                .stream()
                .anyMatch(authority ->
                    "ROLE_TENANT_ADMIN".equals(
                            authority.getAuthority()));
    }

    private TenantDocument visibleDocument(
            String tenantId, Long documentId,
            Authentication authentication) {

        requireTenant(tenantId, authentication);

        return repository
                .findByIdAndTenantId(documentId, tenantId)
                .filter(doc ->
                    isTenantAdmin(authentication)
                    || doc.getOwnerUsername()
                          .equals(authentication.getName()))
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));
    }

    @Transactional(readOnly = true)
    public TenantDocument read(
            String tenantId, Long documentId,
            Authentication authentication) {
        return visibleDocument(
                tenantId, documentId, authentication);
    }

    @Transactional(readOnly = true)
    public List<TenantDocument> list(
            String tenantId, Authentication authentication) {

        requireTenant(tenantId, authentication);

        if (isTenantAdmin(authentication)) {
            return repository.findByTenantIdOrderByIdAsc(tenantId);
        }

        return repository
                .findByTenantIdAndOwnerUsernameOrderByIdAsc(
                        tenantId, authentication.getName());
    }

    @Transactional
    public TenantDocument create(
            String tenantId, String title,
            Authentication authentication) {

        requireTenant(tenantId, authentication);

        TenantDocument document = new TenantDocument(
                tenantId, authentication.getName(), title);

        return repository.save(document);
    }

    @Transactional
    public TenantDocument rename(
            String tenantId, Long documentId,
            String newTitle, Authentication authentication) {

        TenantDocument document = visibleDocument(
                tenantId, documentId, authentication);

        document.rename(newTitle);
        return document;
    }

    @Transactional
    public void remove(
            String tenantId, Long documentId,
            Authentication authentication) {

        TenantDocument document = visibleDocument(
                tenantId, documentId, authentication);

        repository.delete(document);
    }
}
~~~

### 13.1 Check order must be fail-closed

1. `requireTenant` verifies the caller holds membership in the requested tenant.
2. `findByIdAndTenantId` restricts the database lookup to that tenant.
3. Only the record owner or same-tenant admin may read, modify, or delete the record.
4. Both failed ownership checks and non-existent document IDs return `404`.
5. `CREATE` assigns principal name from `Authentication`, ignoring any client-supplied owner.
6. `LIST` queries only by tenant + owner (or tenant-only for a verified admin).

If a service calls `repository.findById(id)` and returns or logs the entity before checking authorization, sensitive data can leak through responses, logs, or events even if the controller later errors out. **Enforce authorization as close to data access as possible.**

### 13.2 `Authentication` must come from `SecurityContext`, not request JSON

The controller receives `Authentication` supplied by Spring Security after the request passes through the filter chain. The service receives it as a trusted server-side argument **from the controller**, never constructing an `Authentication` from client-provided `username`/`roles`. For public service APIs invoked by multiple callers (batch jobs, GraphQL, message consumers), build a policy abstraction reading validated identity from security context and decoupling HTTP status translation so callers cannot forge arbitrary roles.

### 13.3 Why not use `@PreAuthorize` in the demo?

Method security `@PreAuthorize` (with `@EnableMethodSecurity`) is a valid approach, yet does not automatically make repository queries tenant-scoped. This lesson keeps explicit service checks so record visibility and write paths stay clear. In larger systems, you can extract `DocumentPolicy.canRead/canEdit`, adopt `AuthorizationManager`/`@PreAuthorize`, and test both method security and query scoping.

### 13.4 How does `@Transactional` help?

- `create`: repository saves inside a transaction and commits when the method succeeds.
- `rename`: entity is loaded in managed state; calling `rename` triggers JPA dirty checking and flushes an `UPDATE` on commit.
- `remove`: `DELETE` runs inside the transaction.
- `read/list`: read-only transaction supports consistency/lazy loading if needed, though it is not an authorization check.
- Never place `@Transactional` on the whole MockMvc test class: HTTP request/service transactions should behave as they do in production, without test-managed rollbacks masking authorization bugs.

### 13.5 Service should not leak raw entities to clients

While the service returns the internal JPA entity here, the controller maps it to a defined response DTO. Never serialize entities directly if they contain `ownerEmail`, `tenantId`, internal flags, or lazy associations holding sensitive data.

## 14. `TenantDocumentController.java` — DTO allowlist and status codes

`src/main/java/example/tenant/TenantDocumentController.java`:

~~~java
package example.tenant;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/tenants/{tenantId}/documents")
public class TenantDocumentController {

    private final TenantDocumentService service;

    public TenantDocumentController(TenantDocumentService service) {
        this.service = service;
    }

    public record DocumentView(Long id, String title) {
        static DocumentView from(TenantDocument doc) {
            return new DocumentView(
                    doc.getId(), doc.getTitle());
        }
    }

    public record CreateDocumentRequest(
            @NotBlank @Size(max = 120) String title) {
    }

    public record RenameDocumentRequest(
            @NotBlank @Size(max = 120) String title) {
    }

    @GetMapping("/{id}")
    public DocumentView get(
            @PathVariable String tenantId,
            @PathVariable Long id,
            Authentication authentication) {

        return DocumentView.from(
                service.read(tenantId, id, authentication));
    }

    @GetMapping
    public List<DocumentView> list(
            @PathVariable String tenantId,
            Authentication authentication) {

        return service.list(tenantId, authentication)
                .stream()
                .map(DocumentView::from)
                .toList();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public DocumentView create(
            @PathVariable String tenantId,
            @Valid @RequestBody CreateDocumentRequest request,
            Authentication authentication) {

        return DocumentView.from(
                service.create(
                    tenantId, request.title(), authentication));
    }

    @PatchMapping("/{id}")
    public DocumentView rename(
            @PathVariable String tenantId,
            @PathVariable Long id,
            @Valid @RequestBody RenameDocumentRequest request,
            Authentication authentication) {

        return DocumentView.from(
                service.rename(
                    tenantId, id, request.title(),
                    authentication));
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(
            @PathVariable String tenantId,
            @PathVariable Long id,
            Authentication authentication) {

        service.remove(tenantId, id, authentication);
    }
}
~~~

### 14.1 Never let the controller trust body owner or tenant

Create/Rename request records accept only `title`. Clients cannot use valid DTO payloads to reassign ownership or tenants, even if they know someone else's ID. The service still independently assigns identity from `authentication.getName()` after verifying membership.

### 14.2 What does `@Valid` protect, and what does it not protect?

`@NotBlank` and `@Size(max=120)` protect input shape, rejecting blank or oversized titles. They **do not** prove the caller has permission to modify the document. Validators will PASS valid JSON sent by an attacker; the service still needs object/tenant authorization.

### 14.3 Response DTO restricts exposed fields

`DocumentView` exposes only `id` and `title`. Tests assert the JSON response omits `tenantId` and `ownerUsername`, and that lists contain no cross-tenant records. Remember that **omitting protected fields** is no substitute for **blocking unauthorized reads**: even `title` is sensitive if ownership checks fail.

## 15. Test fixtures and attack matrix

A security test suite needs **at least two accounts in the same tenant** and **at least one account in another tenant**. With only Alice and one document, tests cannot catch horizontal privilege escalation or cross-tenant leaks.

Data is reset in `@BeforeEach`:

~~~text
acme
  - alice owns "Alpha draft"  [aliceId]
  - bob owns   "Bob notes"    [bobId]

beta
  - carol owns "Beta plan"    [carolId]

admin-acme -> can administer acme only
admin-beta -> can administer beta only
guest      -> authenticated but has no tenant membership
~~~

Never assume sequential IDs equal 1, 2, 3: identity sequences keep advancing between tests even after table cleanup. Always grab real IDs returned by `repository.saveAllAndFlush`.

### Expected outcome matrix

| Principal/request | Target | Expectation |
| --- | --- | --- |
| Anonymous GET | Alice doc | 401 |
| Wrong password GET | Alice doc | 401 |
| Alice GET | Alice doc | 200 |
| Bob GET | Alice doc in acme | 404 |
| Alice GET /tenants/beta | Carol doc | 403 |
| Alice GET /tenants/acme | Carol doc ID | 404 |
| admin-acme GET | Bob doc in acme | 200 |
| admin-beta GET /tenants/acme | Alice doc | 403 |
| guest GET acme | Alice doc | 403 |
| Alice GET list acme | Alice doc only | 200, length 1 |
| admin-acme GET list acme | Alice+Bob only | 200, length 2 |
| Alice POST acme | New doc | 201, owner alice |
| Alice POST protected fields | Fake owner/tenant | 400 |
| Alice POST without CSRF | New doc | 403 |
| Alice PATCH | Alice doc | 200 |
| Bob PATCH | Alice doc | 404 |
| admin-acme PATCH | Bob doc | 200 |
| Alice DELETE | Alice doc | 204 |
| Bob DELETE | Alice doc | 404 |
| admin-beta DELETE acme | Alice doc | 403 |
| admin-acme DELETE acme | Bob doc | 204 |

The table emphasizes **negative cases** because they provide the strongest proof that the API rejects unauthorized access. Re-evaluate the policy when real models introduce multi-tenant users, teams, delegated access, or sharing.

## 16. `TenantDocumentSecurityTest.java` — full Spring Boot + MockMvc integration tests

This is the complete JUnit Jupiter file. It neither mocks `TenantDocumentRepository` or `TenantDocumentService` nor disables Spring Security filters.

`src/test/java/example/tenant/TenantDocumentSecurityTest.java`:

~~~java
package example.tenant;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantDocumentSecurityTest {

    private static final String ACME =
            "/tenants/acme/documents";
    private static final String BETA =
            "/tenants/beta/documents";

    @Autowired
    MockMvc mvc;

    @Autowired
    TenantDocumentRepository repository;

    private Long aliceId;
    private Long bobId;
    private Long carolId;

    private static SecurityMockMvcRequestPostProcessors
            .HttpBasicRequestPostProcessor login(String username) {
        return httpBasic(username, "test-secret");
    }

    @BeforeEach
    void seedIsolatedDocuments() {
        repository.deleteAllInBatch();

        List<TenantDocument> saved =
                repository.saveAllAndFlush(List.of(
                    new TenantDocument(
                        "acme", "alice", "Alpha draft"),
                    new TenantDocument(
                        "acme", "bob", "Bob notes"),
                    new TenantDocument(
                        "beta", "carol", "Beta plan")
                ));

        aliceId = saved.get(0).getId();
        bobId = saved.get(1).getId();
        carolId = saved.get(2).getId();
    }

    @Test
    void anonymousCannotRead() throws Exception {
        mvc.perform(get(ACME + "/" + aliceId)
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordCannotAuthenticate() throws Exception {
        mvc.perform(get(ACME + "/" + aliceId)
                    .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerCanReadOwnDocument() throws Exception {
        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("alice")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                    .value("Alpha draft"))
                .andExpect(jsonPath("$.id")
                    .value(aliceId.intValue()))
                .andExpect(jsonPath("$.tenantId")
                    .doesNotExist())
                .andExpect(jsonPath("$.ownerUsername")
                    .doesNotExist());
    }

    @Test
    void anotherUserSameTenantCannotReadOwnersDocument()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("bob")))
                .andExpect(status().isNotFound());
    }

    @Test
    void memberCannotSwitchToDifferentTenantPath()
            throws Exception {

        mvc.perform(get(BETA + "/" + carolId)
                    .with(login("alice")))
                .andExpect(status().isForbidden());
    }

    @Test
    void changingOnlyDocumentIdCannotCrossTenant()
            throws Exception {

        mvc.perform(get(ACME + "/" + carolId)
                    .with(login("alice")))
                .andExpect(status().isNotFound());
    }

    @Test
    void tenantAdminCanReadAnotherOwnerInOwnTenant()
            throws Exception {

        mvc.perform(get(ACME + "/" + bobId)
                    .with(login("admin-acme")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                    .value("Bob notes"));
    }

    @Test
    void tenantAdminCannotUseAdminRoleOutsideMembership()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("admin-beta")))
                .andExpect(status().isForbidden());
    }

    @Test
    void loggedInWithoutTenantMembershipIsForbidden()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .with(login("guest")))
                .andExpect(status().isForbidden());
    }

    @Test
    void userListContainsOnlyOwnedDocuments()
            throws Exception {

        mvc.perform(get(ACME).with(login("alice")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].title")
                    .value("Alpha draft"));
    }

    @Test
    void adminListContainsOnlyItsTenant()
            throws Exception {

        mvc.perform(get(ACME)
                    .with(login("admin-acme")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].title")
                    .value("Alpha draft"))
                .andExpect(jsonPath("$[1].title")
                    .value("Bob notes"));
    }

    @Test
    void forgedTenantHeaderCannotOverrideMembership()
            throws Exception {

        mvc.perform(get(BETA + "/" + carolId)
                    .header("X-Tenant-Id", "beta")
                    .with(login("alice")))
                .andExpect(status().isForbidden());
    }

    @Test
    void forgedUsernameHeaderCannotOverrideOwner()
            throws Exception {

        mvc.perform(get(ACME + "/" + aliceId)
                    .header("X-User", "alice")
                    .with(login("bob")))
                .andExpect(status().isNotFound());
    }

    @Test
    void ownerIsServerAssignedWhenCreatingDocument()
            throws Exception {

        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New plan\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title")
                    .value("New plan"));

        TenantDocument created = repository
            .findByTenantIdAndOwnerUsernameOrderByIdAsc(
                "acme", "alice")
            .stream()
            .filter(doc -> "New plan".equals(doc.getTitle()))
            .findFirst()
            .orElseThrow();

        assertEquals("acme", created.getTenantId());
        assertEquals("alice", created.getOwnerUsername());
        assertEquals(4L, repository.count());
    }

    @Test
    void clientCannotMassAssignTenantOrOwner()
            throws Exception {

        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"Injected\","
                        + "\"tenantId\":\"beta\","
                        + "\"ownerUsername\":\"carol\"}"))
                .andExpect(status().isBadRequest());

        assertEquals(3L, repository.count());
    }

    @Test
    void blankTitleFailsValidation() throws Exception {
        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"  \"}"))
                .andExpect(status().isBadRequest());

        assertEquals(3L, repository.count());
    }

    @Test
    void missingCsrfBlocksAuthenticatedPost()
            throws Exception {

        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Without csrf\"}"))
                .andExpect(status().isForbidden());

        assertEquals(3L, repository.count());
    }

    @Test
    void invalidCsrfIsAlsoRejected() throws Exception {
        mvc.perform(post(ACME)
                    .with(login("alice"))
                    .with(csrf().useInvalidToken())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Bad csrf\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanRenameOwnDocument() throws Exception {
        mvc.perform(patch(ACME + "/" + aliceId)
                    .with(login("alice"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Renamed\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title")
                    .value("Renamed"));

        assertEquals(
            "Renamed",
            repository.findById(aliceId)
                    .orElseThrow().getTitle());
    }

    @Test
    void anotherOwnerCannotRenameDocument()
            throws Exception {

        mvc.perform(patch(ACME + "/" + aliceId)
                    .with(login("bob"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Take over\"}"))
                .andExpect(status().isNotFound());

        assertEquals(
            "Alpha draft",
            repository.findById(aliceId)
                    .orElseThrow().getTitle());
    }

    @Test
    void crossTenantUserCannotRenameDocument()
            throws Exception {

        mvc.perform(patch(ACME + "/" + aliceId)
                    .with(login("carol"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Wrong tenant\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void tenantAdminCanRenameSameTenantDocument()
            throws Exception {

        mvc.perform(patch(ACME + "/" + bobId)
                    .with(login("admin-acme"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Reviewed\"}"))
                .andExpect(status().isOk());

        assertEquals(
            "Reviewed",
            repository.findById(bobId)
                    .orElseThrow().getTitle());
    }

    @Test
    void ownerCanDeleteOwnDocument() throws Exception {
        mvc.perform(delete(ACME + "/" + aliceId)
                    .with(login("alice"))
                    .with(csrf()))
                .andExpect(status().isNoContent());

        assertFalse(repository.existsById(aliceId));
    }

    @Test
    void anotherOwnerCannotDeleteDocument()
            throws Exception {

        mvc.perform(delete(ACME + "/" + aliceId)
                    .with(login("bob"))
                    .with(csrf()))
                .andExpect(status().isNotFound());

        assertTrue(repository.existsById(aliceId));
    }

    @Test
    void otherTenantAdminCannotDeleteDocument()
            throws Exception {

        mvc.perform(delete(ACME + "/" + aliceId)
                    .with(login("admin-beta"))
                    .with(csrf()))
                .andExpect(status().isForbidden());

        assertTrue(repository.existsById(aliceId));
    }

    @Test
    void tenantAdminCanDeleteSameTenantDocument()
            throws Exception {

        mvc.perform(delete(ACME + "/" + bobId)
                    .with(login("admin-acme"))
                    .with(csrf()))
                .andExpect(status().isNoContent());

        assertFalse(repository.existsById(bobId));
    }

    @Test
    void unknownIdIsHiddenForValidTenantMember()
            throws Exception {

        mvc.perform(get(ACME + "/999999999")
                    .with(login("alice")))
                .andExpect(status().isNotFound());
    }
}
~~~

### 16.1 Do tests use real authentication?

Yes, within demo boundaries. `httpBasic("alice", "test-secret")` emits a real HTTP Basic header; Spring Security's `BasicAuthenticationFilter`, `UserDetailsService`, and `PasswordEncoder` execute rather than faking a context via `@WithMockUser`. Wrong passwords must return `401`. JSON/URL/header inputs traverse Spring Security filters, the controller, and the service.

### 16.2 Are database writes actually checked?

Yes. Tests do not mock the repository or service. After both allowed and denied POST/PATCH/DELETE requests, tests query the real JPA repository to assert rows were created/updated/deleted or **left untouched**. This catches the classic bug where “the endpoint returned 403 yet already updated the DB before checking authorization”.

H2 keeps the demo simple; PostgreSQL constraints, RLS, and SQL dialects need dedicated PostgreSQL Testcontainers integration tests in projects running Postgres.

### 16.3 Why not put `@Transactional` on the test class?

A test-managed transaction wrapping MockMvc requests can mask service commit/rollback discrepancies or restrict fixture data to the test thread. This lesson lets controller/service transactions follow normal application semantics and resets the DB in `@BeforeEach`. Under `@SpringBootTest(RANDOM_PORT)`, the server runs on another thread/transaction and is **not** automatically rolled back by a client test transaction.

### 16.4 Why set `maxParallelForks=1`?

Fixtures share one H2 database inside one application context. Tests delete and re-seed rows before every method; enabling parallel JUnit methods would let test A wipe test B's rows. The demo stays sequential in one Gradle fork. If parallelizing, isolate DBs/schemas/tenant data per test worker instead of resetting shared tables indiscriminately.

### 16.5 Where do Mockito/`@WithMockUser` fit?

`@WithMockUser(username="alice", authorities={"TENANT_acme", "ROLE_USER"})` is useful for policy/unit tests, yet it **bypasses real credential verification**. To test “wrong password returns 401”, use real Basic/login/JWT flows. Never rely solely on `@WithMockUser` and claim login, password checking, issuer validation, or JWT filters were tested.

## 17. Test summary and expected results

The test class contains **27 `@Test` methods** running on JUnit Jupiter; all assertions reflect expectations derived from the source code and policy, **not observed output from an executed run**.

| Group | What is tested | Highlights |
| --- | --- | --- |
| Authentication | Anonymous, bad password | 401 |
| Ownership | Owner GET, Bob GET Alice's ID | 200/404 |
| Cross-tenant | Swapped tenant path or ID | 403/404 |
| Vertical privilege | Same-tenant admin vs other-tenant admin | 200/403 |
| Lists | Owner-only vs tenant-wide admin | Complete/no row leaks |
| Spoofing | `X-Tenant-Id` / `X-User` headers | Do not alter principal |
| Document creation | POST & server-assigned owner/tenant | 201 + DB assertions |
| Mass assignment | `ownerUsername`/`tenantId` in JSON | 400 |
| Input validation | Blank title | 400 |
| CSRF | Missing/invalid token | 403 |
| Editing | owner/other owner/tenant/admin | 200/404/403 |
| Deleting | owner/other owner/tenant/admin | 204/404/403 |
| Unknown ID | Non-existent | 404 |

**Counting test cases is not coverage quality:** include real negative scenarios, assert DB state after denied requests, and assert responses leak no forbidden fields.

## 18. Running the app and tests

Prepare a Gradle wrapper matching a Boot 3.5-compatible toolchain. On Linux/macOS:

~~~bash
./gradlew clean test
./gradlew test --tests '*TenantDocumentSecurityTest'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests '*TenantDocumentSecurityTest'
~~~

Test reports:

~~~text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
~~~

These are run commands, with no fabricated stdout or benchmarks. When a task is marked `UP-TO-DATE`, Gradle may skip re-running tests; use `--rerun-tasks` when a fresh run is needed.

### 18.1 Launching the app directly

~~~bash
./gradlew bootRun
~~~

The app uses demo accounts and H2, so **never deploy this configuration to the Internet**. Even though demo HTTP Basic hashes passwords with BCrypt, HTTP Basic still requires TLS and test credentials belong strictly in local/CI environments. Never use test accounts in production.

### 18.2 Distinguishing statuses and payloads

- `401`: missing/bad credentials, with an HTTP Basic challenge where applicable.
- `403`: authenticated caller lacks tenant membership or CSRF token.
- `404`: missing object **or** owner check denied inside a valid tenant.
- `400`: invalid DTO, unknown property, or malformed JSON.
- `201`: valid POST created a record.
- `200`: valid GET/PATCH.
- `204`: successful DELETE with no body.

Never rely on status alone: verify both persisted state and response JSON to detect side effects occurring before denial.

## 19. Testing cross-access requires swapping across multiple dimensions

A suite checking only “Carol reading Alice returns 403” is **far from enough**. Swaps you must test separately:

1. **Swap user within same tenant**: Bob requests Alice's ID under `/tenants/acme` (horizontal escalation).
2. **Swap tenant path**: Alice accesses `/tenants/beta` (membership boundary).
3. **Keep tenant path, swap ID to another tenant's record**: Alice requests `carolId` under `/tenants/acme` (object-level tenancy scope).
4. **Swap role**: `admin-acme` can read Bob, while `admin-beta` cannot read Bob.
5. **Swap HTTP verb**: blocking GET does not guarantee PATCH/DELETE are blocked.
6. **Swap operation**: LIST can leak even when GET-by-ID works; same for export/search/count.
7. **Spoof headers**: client-supplied `X-Tenant-Id`, `X-User`, and `X-Role` are not authenticated identity.
8. **Spoof body**: `tenantId`/`ownerUsername` in POST/PATCH must not reassign ownership.
9. **Swap credentials**: anonymous/bad password/expired bearer token must never reach the service.
10. **CSRF**: mutating requests with credentials but no CSRF token must be rejected under session/Basic policies.

### 19.1 Do not rely on IDs being unguessable

OWASP recommends “swap tests”: create two accounts/tenants, grab a **real object ID** from a fixture or response, and replay the exact request under another identity. Attackers do not need brute force; IDs surface in emails, lists, logs, caches, URLs, and audit trails.

### 19.2 Do not forget nested resources

If documents have comments or attachments:

~~~http
GET /tenants/acme/documents/123/attachments/456
~~~

verify **both document 123 and attachment 456** belong to the tenant and owner. Permission to view a document does not imply any arbitrary attachment ID may be downloaded. Scope lookups by `tenantId`, `parentId`, and `resourceId`, not merely a route prefix.

## 20. Different permissions for create, edit, and delete

A policy may specify:

- Owner reads and renames title.
- Tenant admin reads/edits/deletes any document in the same tenant.
- Viewer is read-only.
- Auditor sees metadata without document content.
- Global support user requires approval + audited break-glass access.
- Document shared with a group, not the whole tenant.

Never build one `isAdmin || isOwner` predicate and reuse it across every verb when business rules differ. In this demo, it is an **explicitly defined policy** for instructional clarity. In a real system, draw a `principal × tenant × object owner × action × state` matrix and write positive and negative tests for every cell.

### 20.1 “Read-only” is not automatically safe

GET endpoints can leak data through bodies, headers, timing, pagination totals, or file exports. An unscoped count/list endpoint can leak document existence even when GET-by-ID returns 404. Always test list/search/aggregate endpoints, not just CRUD-by-ID.

### 20.2 Authorize before mutating

On PATCH/DELETE, the service must verify tenant + ownership **before calling rename/delete**. Tests assert the row remained unchanged after denied requests. Placing the policy check after `saveAndFlush` can leave persisted side effects or published external events even when returning 403.

## 21. 401, 403, and 404 in the JWT/OIDC world

The demo uses HTTP Basic to make real authentication easy to reproduce in MockMvc. Production resource servers usually accept bearer tokens:

~~~http
GET /tenants/acme/documents/123
Authorization: Bearer eyJ...
~~~

Never base64-decode a JWT payload and trust `tenantId`/`roles` without verification. Before using claims:

- Verify signature/algorithm and trusted keys, preventing algorithm-confusion attacks.
- Verify `iss`, `aud`, `exp`, `nbf`, and token type per system policy.
- Map stable `sub` to an internal account ID.
- Resolve tenant memberships/roles from a trusted issuer or membership database.
- Handle revoked accounts / changed tenant memberships: do stale tokens keep access until expiry or is introspection needed?
- Never trust user-supplied `X-Tenant-Id` over role claims.
- Test that Alice's token cannot access tenant beta just by changing the URL path.

`@WithMockUser` does not test signatures, issuers, or audiences. Dedicated JWT suites need `spring-security-test` JWT request post-processors for authorization mapping **plus** at least one `JwtDecoder`/bearer-filter integration test or mocked trusted issuer matching real security config.

### 21.1 A JWT claim is not the `userId` in the URL

If `/users/{userId}/documents` takes `userId` from the path, verify `path userId == trusted principal subject` (or delegated permission). A valid token plus an existing path ID never proves the caller may read another user's data.

### 21.2 Multi-tenant identity providers

When one user belongs to multiple tenants, permissions can depend on the active tenant. The server must validate “user belongs to tenant T and holds role R in T”, not simply “user holds role R somewhere”. Test with a principal who is admin in acme and viewer in beta to catch role-scope confusion; never grant global admin by flattening authorities without tenant bindings. In this demo each user has one membership for readability, whereas production policies must support multiple memberships accurately.

## 22. `@WebMvcTest` and `@MockitoBean`: when to use them?

`@WebMvcTest(TenantDocumentController.class)` loads only the MVC slice; you can mock `TenantDocumentService` via `@MockitoBean` to quickly test JSON, validation, and HTTP mappings. However, a mocked service returning 404 or 200 per stub **does not prove the service queries with tenant scoping**.

Sound strategy:

- **Policy unit tests**: `DocumentPolicy.canRead` across Principal/Document combinations, no database.
- **MVC slice**: controller request binding, DTOs, status/responses, and security filter rules if fully imported.
- **Full MockMvc integration (this lesson)**: `SecurityFilterChain` + `UserDetailsService` + Service + JPA + H2.
- **PostgreSQL Testcontainers integration**: SQL/RLS/isolation, unique constraints, and transactions on the production DB engine.
- **Real HTTP deployed environment**: session cookies, reverse proxies, CORS, TLS, API gateways, token issuance/revocation, and cross-service propagation.

Never use `@AutoConfigureMockMvc(addFilters=false)` in security tests. `@WebMvcTest` might not load custom `UserDetailsService`/`SecurityConfig` automatically like the full context; when using a slice, import/configure the right filter chain or state the narrower goal explicitly.

## 23. CSRF: test both with and without a token

Spring Security Test supports:

~~~java
mvc.perform(post("/tenants/acme/documents")
        .with(httpBasic("alice", "test-secret"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Safe\"}"));
~~~

And negative testing:

~~~java
mvc.perform(post("/tenants/acme/documents")
        .with(httpBasic("alice", "test-secret"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"No CSRF\"}"))
    .andExpect(status().isForbidden());
~~~

These are fragments from the complete test class. `csrf()` injects a valid token generated by Spring Security Test; `csrf().useInvalidToken()` simulates a bad token. When the CSRF filter rejects a request, the controller/service **must not run**, and DB data must stay unchanged.

A system using pure bearer `Authorization` headers that browsers never send automatically may use a different CSRF strategy; evaluate cookies, refresh tokens, and browser flows explicitly. Never generalize “REST = disable CSRF” or “MockMvc = no CSRF needed”.

## 24. Mass assignment and object property-level authorization

Dangerous payloads:

~~~json
{
  "title": "My document",
  "ownerUsername": "admin-acme",
  "tenantId": "beta",
  "isSystemDocument": true
}
~~~

If code binds JSON straight onto a JPA entity and calls `save`, an attacker can hijack ownership or move documents across tenants. Defenses:

1. **Request DTO allowlist**: expose only client-editable fields like `title`.
2. **Strict unknown fields** where contract permits, returning 400 when a client sends `ownerUsername`.
3. **Server-side assignment**: `tenantId` after membership check; `ownerUsername` from the authenticated principal.
4. **Record-level authorization** before updates/deletes.
5. **Database tenant scoping** in WHERE clauses; layer RLS on top where supported.
6. **Audit** who changed which fields, without treating auditing as a substitute for preventive checks.

Even with UUIDs instead of sequential IDs, mass assignment does not vanish. Enforce authorization on both the object **and** every sensitive property.

## 25. Caches, search, and async jobs: tenant leaks outside CRUD

A correct CRUD-by-ID controller does not make the whole system tenant-safe.

### 25.1 Cache keys

Wrong:

~~~text
cache key = "document:" + documentId
~~~

If `documentId` is not globally unique across stores, or cached responses carry personalized data, cache keys can bleed across tenants and permissions. Safer keys include `tenantId` + `resourceId` + policy/version/user scope as needed; always test invalidation and access checks **before returning cached values**.

### 25.2 Search, indexing, and filters

A search endpoint `GET /documents?q=...` might query Elasticsearch/OpenSearch without a tenant filter. Test by indexing identically titled documents in two tenants, searching as Alice, and asserting zero beta hits, facets, counts, suggestions, or exports appear.

### 25.3 Exports and background workers

An export job created during an acme request may run asynchronously without the request thread's `SecurityContext`. Never copy tenant context blindly from unvalidated `ThreadLocal`s. Persist job ownership/tenant and re-validate when the worker runs, writes files, or serves downloads. “Request acme export → worker reads beta data” is a worthwhile negative test.

### 25.4 Object storage URLs

A presigned attachment download URL can bypass application authorization at download time. Test object key/bucket scoping, TTL, response caching, redirect headers, and user/tenant policies before issuing URLs. Never equate unguessable URLs with access control.

## 26. Data isolation: application checks and PostgreSQL Row Level Security

The demo uses H2 to verify application security policies. When production runs PostgreSQL shared-table multi-tenancy, **Row Level Security (RLS)** adds a second defense layer:

~~~sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;
~~~

This is illustrative PostgreSQL SQL, **not executed in the H2 demo**. Real RLS policies must account for DB roles, session identity, tenant settings, `USING`/`WITH CHECK`, table-owner bypass / `FORCE ROW LEVEL SECURITY`, and superuser privileges. Never deploy a simplistic RLS policy and assume isolation is guaranteed.

### 26.1 Mandatory PostgreSQL/Testcontainers tests when using RLS

- The real app DB user must not bypass the policy.
- `SELECT` returns zero rows from other tenants even if a query forgets the tenant predicate.
- `UPDATE`/`DELETE` cannot modify other tenants' rows.
- `INSERT`/`UPDATE` with a mismatched `tenant_id` is rejected by `WITH CHECK`.
- Transactions and cgroups never bleed tenant context across sessions.
- Connection pool reuse does not carry stale session tenant variables into the next request.
- `SET LOCAL` scoping and reset/rollback behave properly with session variables.
- Migration/admin DB roles are never used as the app runtime role.
- Tests run against real PostgreSQL, not H2 compatibility mode.

**Note:** RLS does not replace service-level ownership checks when policies distinguish owners vs admins inside the same tenant. DB and application defense in depth complement each other rather than hiding gaps in one another.

## 27. Test isolation: preventing negative tests from failing due to dirty fixtures

Full-context tests hold database state and security contexts; reset them carefully:

- `@BeforeEach` clears suite-owned seed data and recreates acme/beta fixtures.
- Never assert sequential IDs starting at 1.
- Never wrap the entire test in `@Transactional` when verifying real application commits.
- Never use `@DirtiesContext` per method to clean up rows; clean up at the DB layer.
- Never run JUnit methods in parallel alongside `deleteAllInBatch()`, or they will delete each other's fixtures.
- Never share static mutable authentication across tests; supply credentials per MockMvc request.
- Never mock the service or repository in the core integration test.
- Verify both the HTTP response and persisted state after denied writes.
- If tests trigger async events or background jobs, await completion and clean up separately.
- Never let production data, accounts, or keys enter test fixtures or CI logs.

### 27.1 Why not put `@WithMockUser` on the whole class?

Class-level `@WithMockUser` gives an “anonymous request” a security principal, breaking 401 tests. Pass explicit credentials per request like `httpBasic` in the demo so anonymous, bad-password, and valid-password states stay distinct.

### 27.2 Never run security tests with filters turned off

`@AutoConfigureMockMvc(addFilters=false)` speeds up controller tests by removing `SecurityFilterChain`, CSRF, `AuthenticationEntryPoint`, and `AccessDeniedHandler`. For authentication/authorization tests, keep filters active and test negative flows.

## 28. App-level authentication vs reverse-proxy security

MockMvc runs the Servlet filter chain **in-JVM** without opening a real HTTP port. It proves Spring Security and application routing behavior, yet does not test:

- Real HTTPS/TLS termination.
- Proxy-injected `X-Forwarded-*` headers.
- API gateway JWT signature/issuer forwarding.
- Browser session cookies, `SameSite`, `Secure`, `HttpOnly`.
- Rate limiting, MFA, account lockouts, password resets.
- Network egress and service-to-service authorization.
- Edge CORS preflight configurations.
- Real OAuth2 authorization code/PKCE or token exchanges.

Add appropriate integration/E2E tests instead of marking “security fully tested” from MockMvc alone.

### 28.1 Beware forwarded identity headers

If a reverse proxy injects `X-Authenticated-User` or `X-Tenant-Id`, the gateway must **strip** client-supplied headers and re-inject them only over a trusted channel (mTLS/network allowlist). Apps must enforce trust boundaries. The demo deliberately ignores `X-User` and `X-Tenant-Id` to illustrate this rule.

## 29. CI workflow: security tests as a mandatory gate

File `.github/workflows/security-tests.yml`:

~~~yaml
name: Tenant authorization integration tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  security-tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Run full security suite
        shell: bash
        run: |
          chmod +x ./gradlew
          ./gradlew --no-daemon clean test --stacktrace

      - name: Upload JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: tenant-security-junit-results
          path: |
            build/test-results/test/
            build/reports/tests/test/
          if-no-files-found: error
          retention-days: 7
~~~

Because the lesson uses H2, this workflow needs no Docker and runs fast on every pull request. For production database-specific RLS tests, add a **separate** job with PostgreSQL Testcontainers on a Docker-enabled runner and mark both jobs as required checks for merge/deploy.

### 29.1 Never drop negative tests just to turn CI green

If a test fails due to a cross-tenant authorization bug, fix the policy/query and keep a regression test; never add `@Disabled` or weaken assertions to pass CI. Security regressions are often far costlier than functional bugs.

### 29.2 Report executed tests

JUnit XML/HTML must reflect discovered, executed, skipped, and failed counts. If a Gradle `includeTag` filter silently excludes the entire security suite, `BUILD SUCCESSFUL` proves nothing about authorization. CI can enforce minimum test counts or package-based selection to prevent accidental omission.

## 30. How to simulate JWTs in Spring Security Test?

For production resource servers, Spring Security Test provides request post-processors like `jwt()` to populate an authenticated token/authorities in the test context. It is great for testing **authorization mapping**:

~~~java
mvc.perform(get("/tenants/acme/documents/123")
        .with(jwt().jwt(jwt ->
            jwt.claim("tenant_id", "acme"))
            .authorities(
                new SimpleGrantedAuthority("TENANT_acme"))));
~~~

This is a **separate snippet**, not part of the demo source, requiring proper JWT imports and config. `jwt()` does not verify signatures or issuers; it simulates an already-authenticated JWT. Keep separate tests for `JwtDecoder`/bearer filters checking invalid signatures, wrong issuers/audiences, expired tokens, and missing tokens. Never copy principal names from Basic tests to JWT tests while forgetting `sub`/name mapping.

### 30.1 Role mapping for JWTs may differ from Basic auth

JWT claims may use `roles`, `scope`, `realm_access.roles`, or tenant-keyed maps. A `JwtAuthenticationConverter` may add `SCOPE_` or `ROLE_` prefixes; tests must verify the resulting authorities match the service policy. Never grant a system-wide `ROLE_ADMIN` when the token role applies only to one tenant.

## 31. Expanding the matrix for complex multi-tenant models

In production environments, also cover:

- One user belonging to **two tenants** with different roles (admin in acme, viewer in beta).
- Users whose membership is revoked while their token has not expired yet.
- Temporary document sharing between two users or tenants.
- A tenant admin account locked mid-session.
- Ownership transfer workflows requiring extra approval/authorization.
- Soft-deleted, archived, and published/private states.
- Nested comments, attachments, and object-storage keys.
- Search, pagination, sorting, report exports, and aggregate counts.
- Bulk updates/deletes over mixed ID lists containing both acme and beta records.
- GraphQL data loaders / batch readers lacking automatic tenant scoping.
- WebSocket/SSE subscriptions and reconnects across tenant switches.
- Async jobs, email notifications, and event-streaming/outbox payloads.
- Cache serialization/invalidation when switching identity or tenant.
- Database RLS policies alongside pooled connections.
- Error responses leaking zero internal details, stack traces, or SQL.
- Security audit logs capturing user/tenant/request correlation without passwords/tokens.
- Rate limiting to slow down ID enumeration attacks.

### 31.1 Bulk operations are especially error-prone

If an API accepts `ids=[10, 11, 12]`, never call `deleteAllById(ids)` without filtering tenant and owner on **every single record**. Test with a mixed array of acme and beta IDs and verify zero unauthorized records change, even under partial-success semantics. Explicitly define and test all-or-nothing vs per-item transactional behavior.

### 31.2 Search facets and metadata can leak too

Even if the item list shows only acme docs, returning a global `totalCount` across the whole DB or an `ownerNames` facet containing Carol from beta is still a tenant information leak. Test paging, search, and export metadata as well as item arrays.

## 32. Diagnosing test failures by layer

| Symptom | Typical layer | What to inspect |
| --- | --- | --- |
| Anonymous GET returns 200 | HTTP security | Is filter chain active? `anyRequest().authenticated()`? |
| Wrong password returns 200 | Authentication | Is `@WithMockUser` bypassing? Which `UserDetailsService`? |
| Alice GET own returns 403 | Tenant membership | Authority name/prefix or path mismatch |
| Bob GET Alice returns 200 | Object authorization | Missing owner check? Unscoped `findById`? |
| Carol GET acme returns 200 | Tenant isolation | Trusting client-supplied tenant? |
| `admin-beta` reads acme | Role scoping | Misusing global `ROLE_ADMIN`? |
| GET list includes beta | Repository queries | Missing `WHERE tenant_id` |
| POST sets owner from body | Mass assignment | DTO/entity binding/identity assignment |
| Denied PATCH mutates DB | Ordering/transaction | Mutation executed before authorization |
| Missing CSRF still allows POST | Security filter | CSRF disabled or `addFilters=false`? |
| POST with CSRF returns 403 | CSRF setup | Token, request session/handler |
| Valid request gets 400 | JSON/validation | DTO fields, strict unknown props, `contentType` |
| Missing document GET returns 500 | Error mapping | `ResponseStatusException` 404 configured? |
| SQL fixtures collide | Parallelism | Shared H2 reset in `@BeforeEach` |
| MockMvc passes yet live API leaks | Layer gap | Gateway/JWT/cache/RLS/E2E |
| JUnit XML omits security tests | Discovery/filtering | Gradle tags, class names, task config |

### 32.1 Testing 401 while `@WithMockUser` is active

If a test class or method is annotated with `@WithMockUser`, a request lacking a Basic header can **still look authenticated**. To test the authentication filter, send real request credentials like `httpBasic` rather than an injected `SecurityContext` test principal.

### 32.2 A 403 from CSRF does not prove tenant authorization

A PATCH missing a CSRF token is rejected early by the CSRF filter. Testing “Bob gets 403” without CSRF never even reaches the owner policy. **Negative ownership/tenant tests must send a valid CSRF token** and assert the expected 404/403 from the right layer. That is a frequent test-design bug.

### 32.3 A 404 can come from the wrong URL

If the controller mapping or fixture ID is wrong, a test expecting 404 can PASS without exercising the owner check. Guard against false positives with positive controls: the exact same object ID must return 200 for Alice and 404 for Bob. The sample suite checks both.

## 33. Workflow for applying this in real projects

1. Identify principal identity sources, authentication mechanisms, and tenant membership stores.
2. Write a policy matrix covering actor, tenant, owner, role, object state, and operation.
3. Provision at least two users in the same tenant, one user in another tenant, and an admin per tenant.
4. Create fixtures with real IDs and recognizable names/fields to catch leaks.
5. Enforce authorization at service/data boundaries, not solely on URL roles.
6. Mandate tenant scoping on every database query; consider PostgreSQL RLS.
7. Restrict all POST/PATCH DTOs to editable fields; assign protected fields server-side.
8. Keep Spring Security filters enabled in MockMvc and test real authentication.
9. Test 401 on anonymous/bad credentials alongside positive authenticated paths.
10. Swap owners within the same tenant to catch BOLA.
11. Swap both tenant paths **and** object IDs to catch cross-tenant access.
12. Verify tenant admins are never treated as global admins.
13. Verify LIST/SEARCH/COUNT/EXPORT endpoints have zero tenant leaks.
14. Test POST/PATCH/DELETE with valid CSRF and add negative CSRF tests.
15. Verify DB state remains unchanged after every denied write.
16. Test spoofed identity headers, bodies, and mass assignment.
17. Avoid test-managed `@Transactional` hiding real service commits.
18. Never run in parallel if fixtures reset shared tables.
19. With JWTs, test decoder verification and authorization claim mapping separately.
20. If using PostgreSQL RLS, add Testcontainers tests running as the real app DB role.
21. Retain test reports and ensure CI filters never skip security suites.
22. Review 403/404 error semantics to prevent user/resource enumeration.
23. Verify audit logs capture useful context without leaking passwords or tokens.
24. Re-run cross-tenant matrices for every new resource type, not just documents.

### Final QA Checklist

- [ ] Unauthenticated or wrong credentials cannot read data.
- [ ] HTTP Security `FilterChain` actually runs inside MockMvc.
- [ ] Valid CSRF tokens are supplied on owner/tenant authorization tests for unsafe methods.
- [ ] Same-tenant non-owners cannot read, edit, or delete another user's records.
- [ ] Cross-tenant users cannot switch tenants via URL or header.
- [ ] Admin roles are strictly bound to matching tenant membership.
- [ ] Both GET-by-ID **and** LIST/SEARCH/BULK endpoints enforce tenant scoping.
- [ ] Positive controls return 200 for the owner on the same ID that returns 404 for strangers.
- [ ] Client-supplied owner/tenant values are never trusted as source of truth.
- [ ] Request DTOs prevent mass assignment of sensitive fields.
- [ ] Denied PATCH/DELETE requests leave the database untouched.
- [ ] Responses omit unnecessary protected fields.
- [ ] The H2 demo is never mistaken for testing PostgreSQL RLS/dialect.
- [ ] Tests include at least two users in one tenant and one in another tenant.
- [ ] Fixture IDs come from the repository rather than hardcoded sequence numbers.
- [ ] Neither transactions nor parallelism mask behavior or leak fixtures.
- [ ] JWT signature/issuer/audience checks are tested at the appropriate layer.
- [ ] Caches, search, exports, nested resources, and async jobs are evaluated.
- [ ] CI enforces running the security integration suite and archives JUnit reports.
- [ ] Security logs never leak credentials or sensitive tenant data.

## 34. Conclusion

**Authentication is only the prerequisite; ownership and tenant isolation protect individual records.** A Spring Boot API must know how the caller was authenticated, which tenant they belong to, what role they hold in that specific tenant, and whether they have rights to the target object.

The demo uses HTTP Basic and BCrypt test users to exercise authentication through Spring Security filters, MockMvc for in-JVM requests, JPA repository/H2 to verify side effects, and negative tests covering BOLA, cross-tenant leaks, admin scoping, mass assignment, CSRF, list isolation, and unauthorized writes. Policies for returning 401/403/404 are stated explicitly and verified consistently.

Moving to production requires more than switching to JWTs: validate identities and claims, enforce service-level authorization, write tenant-scoped queries, lock down DTO allowlists, consider database RLS, audit search/cache/async paths, and run CI regression suites on every real resource type. **Every endpoint accepting an object ID needs an object-level authorization check**, not merely a URL-level role check.

### Official references

- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): object ID swapping and per-resource authorization.
- [OWASP REST Assessment — BOLA testing](https://cheatsheetseries.owasp.org/cheatsheets/REST_Assessment_Cheat_Sheet.html): swap tests for GET/PUT/PATCH/DELETE.
- [OWASP IDOR Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): IDs never replace access checks.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, object checks.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `authenticated`, `AccessDeniedException`.
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): `httpBasic()` request post-processor.
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): valid/invalid `csrf()`.
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): Spring Security filters in MockMvc.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, and `SpringExtension`.
- [Spring Boot 3.5 — Spring Security](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): `SecurityFilterChain` and `UserDetailsService` auto-configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): Jackson deserialization settings.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT issuer/signature validation.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS scope/roles.
- [Gradle — Testing Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, reporting, and test filters.
