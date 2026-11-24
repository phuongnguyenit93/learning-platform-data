# Cross-Tenant Access Testing with Identical IDs and Usernames

## 1. Goal and the easiest trap to miss

In a multi-tenant system, two different customers can both own a record with **ID = 42**, and each customer can have a login account named **`alex`**. This is not rare: many systems generate IDs independently per tenant, allow identical usernames/email aliases across organizations, or federate users from multiple identity providers.

If permission checks use only:

```java
// COUNTEREXAMPLE: no tenant scope.
repository.findById(42L);

// COUNTEREXAMPLE: username is not a globally unique identity.
if (document.ownerUsername().equals(authentication.getName())) {
    return document;
}
```

the result can be reading the wrong document, writing the wrong record, accepting an impostor with the same username, exporting mixed data, or authorizing a tenant B user from tenant A's ACE.

Goals of **“Cross-Tenant Access Testing with Identical IDs and Usernames”** in the **Tenant Isolation** group of Spring Security Authorization:

1. Build test fixtures with **deliberately colliding business IDs and usernames**, differing in tenant, subject, and potentially issuer.
2. Distinguish **display username**, **stable subject identity**, **issuer**, and **tenant membership**.
3. Design record keys `(tenant_id, document_id)` and owner keys `(tenant_id, issuer, subject)`.
4. Combine Spring Security Method Security for functional permissions with record-level policies and tenant-scoped JDBC queries.
5. Write positive/negative tests for detail reads, listings, creates, updates, and deletes, proving no cross-tenant data is read or modified despite colliding IDs or usernames.
6. Verify zero side effects when `@PreAuthorize` denies, and ensure SQL UPDATE/DELETE always carry tenant + owner + status.
7. Know what additional tests are required when an application uses JPA, ACLs, caching, JWT/OIDC, PostgreSQL Row-Level Security (RLS), service accounts, or tenant switching.

**Example environment:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring JDBC, H2, and JUnit 5. H2 is used strictly to test **tenant-scoped repositories and method authorization**; it is not presented as a simulation of PostgreSQL RLS.

## 2. Data scenario: colliding IDs and names, distinct identities

Suppose two tenants `TENANT_A` and `TENANT_B` share the same system:

| Tenant | Document ID | Display username | Owning issuer / subject | Status | Content |
| --- | ---: | --- | --- | --- | --- |
| TENANT_A | **42** | **alex** | `https://idp.example.test` / `a-user-100` | DRAFT | `A private 42` |
| TENANT_B | **42** | **alex** | `https://idp.example.test` / `b-user-200` | DRAFT | `B private 42` |
| TENANT_A | 43 | alex | `https://idp.example.test` / `a-user-100` | PUBLISHED | `A public 43` |
| TENANT_B | 44 | alex | `https://idp.example.test` / `b-user-200` | PUBLISHED | `B public 44` |

Two users:

```text
Authentication A:
  username = "alex"
  tenant   = "TENANT_A"
  issuer   = "https://idp.example.test"
  subject  = "a-user-100"
  authorities = DOC_READ, DOC_UPDATE, DOC_DELETE, DOC_CREATE

Authentication B:
  username = "alex"
  tenant   = "TENANT_B"
  issuer   = "https://idp.example.test"
  subject  = "b-user-200"
  authorities = DOC_READ, DOC_UPDATE, DOC_DELETE, DOC_CREATE
```

Both `authentication.getName()` calls can return `"alex"`. Therefore, comparing `getName()` against `owner_username` is **insufficient** to confirm ownership.

### 2.1. Keys required at each layer

| Layer | Safe key illustrated | Never rely solely on |
| --- | --- | --- |
| Business record | `(tenant_id, document_id)` | `document_id` |
| Account/owner | `(tenant_id, issuer, subject)` | `username` or `email` |
| Repository lookup | `WHERE tenant_id = :tenant AND doc_id = :id` | `WHERE doc_id = :id` |
| Owner check | Verified tenant + issuer + subject | Display name sent by client or user profile |
| Data/permission cache | Tenant + type + ID + subject/permission if relevant | `42`, `alex` |
| Object storage | Tenant namespace + authorized object/key | Guessable file keys |
| Audit | Actor issuer/sub + tenant + resource tenant/ID | Logging only `alex:42` |

`issuer` and `sub` are standard stable OIDC concepts; in production, you still must **verify token, issuer, audience, signature, expiry, and membership**. The test setup below constructs synthetic trusted principals to test policy cleanly—it is **not** guidance to read unverified claims straight from HTTP headers.

### 2.2. Intentional policy definition

To make tests crystal clear, choose this policy:

- `DOC_READ`: within the principal's tenant, `PUBLISHED` documents are readable; `DRAFT` documents are readable only by the owner matching `issuer + subject`.
- `DOC_UPDATE`: edit only `DRAFT` within the matching tenant and owner; SQL re-checks owner/status at write time.
- `DOC_DELETE`: delete only `DRAFT` owned by the caller in that tenant.
- `DOC_CREATE`: create documents in the verified tenant; owner's tenant, issuer, and subject come from the server-side principal.
- `LIST`: return only `PUBLISHED` documents or `DRAFT` documents owned by the actor, within the actor's tenant.
- Missing permissions, wrong tenant, wrong subject/issuer, or missing record all **deny by default**.

This is an **example policy** illustrating tenant isolation. Another app might grant READ via groups/ACLs, while still preserving tenant scope and verifying **per-object** permissions.

## 3. Core test matrix

| Actor | Action / ID | Expected outcome | What must be verified |
| --- | --- | --- | --- |
| A / alex / `a-user-100` | READ 42 | Allow, returns **A private 42** | Never returns tenant B content |
| B / alex / `b-user-200` | READ 42 | Allow, returns **B private 42** | Never returns tenant A content |
| A with `DOC_READ` | READ 44 | Deny | 44 exists only in B even though PUBLISHED |
| B with `DOC_READ` | READ 43 | Deny | 43 exists only in A |
| A with `DOC_READ` | READ 43 | Allow | PUBLISHED in same tenant |
| A with subject `a-other`, username still alex | READ 42 | Deny | Same username does not substitute owner |
| B with A's subject, username still alex | READ 42 | Deny | Matching tenant alone is insufficient for DRAFT with different owner |
| A with different issuer, subject still `a-user-100` | READ 42 | Deny | Subjects must be namespaced by issuer |
| A with only `DOC_UPDATE` | READ 42 | Deny before body | Missing `DOC_READ` authority |
| A | UPDATE 42 | Only A changes | B keeps original content |
| B | DELETE 42 | Only B is deleted | A#42 still exists |
| A and B | CREATE 99 | Two separate records | Composite primary key permits same ID in two tenants |
| A | CREATE 99 twice | Reject duplicate in A | Does not overwrite existing data |
| A / B | LIST | Only matching tenant rows | Never leaks other tenant's rows despite identical username |
| Principal lacking trusted tenant identity | READ/LIST | Deny | No fallback by username |
| Repository SQL without tenant | `WHERE doc_id = 42` | Returns 2 rows — **warning** | Never use as a protected lookup |

The matrix includes **two positive paths for the same ID** plus numerous negative paths. If you test only “A cannot read B” while the database uses **globally unique IDs** and globally unique usernames, tests may never trigger true collision bugs.

## 4. Database design: composite keys before writing tests

Minimal schema:

```sql
CREATE TABLE tenant_documents (
    tenant_id VARCHAR(80) NOT NULL,
    doc_id BIGINT NOT NULL,
    owner_issuer VARCHAR(200) NOT NULL,
    owner_subject VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    body VARCHAR(2000) NOT NULL,
    PRIMARY KEY (tenant_id, doc_id)
);
```

Here:

- `doc_id=42` can appear **twice** when `tenant_id` differs.
- `PRIMARY KEY (tenant_id, doc_id)` blocks two records with **the same tenant and same ID**.
- `owner_issuer` and `owner_subject` form owner identity; never use `username` to decide ownership.
- Enforcing tenant in queries remains the responsibility of repositories/SQL and policies; a composite PK **does not automatically prevent** queries omitting `WHERE tenant_id`.

**Right query:**

```sql
SELECT tenant_id, doc_id, owner_issuer,
       owner_subject, status, body
FROM tenant_documents
WHERE tenant_id = ? AND doc_id = ?;
```

**Dangerous query:**

```sql
SELECT * FROM tenant_documents
WHERE doc_id = ?;
```

With the test data, the second query returns **two rows** for ID 42. Calling `queryForObject` may throw due to multiple rows; adding `LIMIT 1` or picking the first row can silently read **the wrong tenant**. Never “fix” a missing tenant predicate with `LIMIT 1`.

In JPA, reflect composite keys with `@EmbeddedId`, `@IdClass`, a global surrogate ID paired with tenant predicates, or a tenant-aware persistence model. Using `JpaRepository<Document, Long>` where `Long` is merely a tenant-local ID invites false uniqueness assumptions. Foreign keys pointing to tenant-scoped entities must also include tenant so joins never link into another tenant's row sharing the same ID.

## 5. Identity: identical usernames do not mean the same principal

### 5.1. Authentication.getName() is often only a label

In Spring Security, `Authentication.getName()` depends on the `Principal`/provider. It **may** be a username, subject, email, or application-defined string. Never assume it is a unique user key across all tenants.

Example:

```java
record TenantPrincipal(
    String issuer, String subject,
    String username, String tenantId
) implements java.security.Principal {

    @Override
    public String getName() {
        return username;
    }
}
```

Two `TenantPrincipal` instances with different `tenantId`/`subject` values can still have `getName() == "alex"`. In this example, `issuer + subject + tenant` is the tenant-scoped identity used to check ownership.

### 5.2. Verify at the authentication boundary

**The Java object above is trustworthy only if constructed from verified authentication.** Production requires:

1. Verifying JWT/OIDC signatures, `iss`, `aud`, `exp`, `nbf`, issuer trust, and required claims.
2. When a user selects an active tenant, checking **membership, roles, and organizational conditions** against a trusted server source before constructing the principal.
3. Never reading `tenantId` and `subject` from request bodies/headers and fabricating a trusted `Authentication`.
4. With multiple issuers, using the `(issuer, subject)` pair; optionally map to a stable internal user ID to decouple from provider username conventions.
5. When memberships are revoked, handling tokens/caches/long-lived sessions within your security SLA.

Tests constructing `TenantPrincipal` directly only **simulate the output of the authentication boundary**; they do not prove the JWT authentication pipeline is secure. Add security-filter integration tests for real tokens in your application environment.

## 6. Separating functional permissions, object permissions, and tenant scope

With Spring Security Method Security, a service can use:

```java
@PreAuthorize(
    "hasAuthority('DOC_READ') and " +
    "@tenantPolicy.canRead(authentication, #docId)"
)
public Document read(@P("docId") long docId) {
    // Query must still be scoped by tenant.
}
```

This is an illustrative **fragment**:

- `hasAuthority('DOC_READ')` decides whether the **function** is permitted.
- `@tenantPolicy.canRead(authentication, #docId)` receives the actual `Authentication` and looks up the record within the right tenant to verify owner/status.
- `@P("docId")` lets SpEL resolve parameter names even if Java compiles without `-parameters`.
- `@EnableMethodSecurity` must be enabled in the context.
- Methods must be invoked via the **Spring-managed proxy**; `this.read(id)` inside the same target can bypass advice.
- **The method body** must continue querying with a tenant predicate; never rely on “passed pre-check” to call an unscoped `findById(id)`.

`@PreAuthorize` guards before entering the body, yet **TOCTOU** remains: owner or status can change between check and write. For UPDATE/DELETE, SQL should repeat tenant + owner + status atomically inside the statement itself.

## 7. Runnable Java 17+ project: Spring Security + JDBC + H2

This example uses a **real schema** and a **real Spring context test**. H2 allows creating two rows with `doc_id=42` across two tenants thanks to `PRIMARY KEY(tenant_id,doc_id)`. The test suite uses `SecurityContextHolder` to simulate two principals sharing a username while differing in issuer/subject/tenant. There is no web server, JWT filter, or PostgreSQL RLS here—those layers require separate dedicated tests.

### 7.1. Project structure

```text
tenant-collision-tests/
├── settings.gradle
├── build.gradle
└── src/test/
    ├── java/demo/TenantCollisionSecurityTest.java
    └── resources/schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'tenant-collision-tests'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
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
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

### 7.2. SQL file creating the table with composite primary key

`src/test/resources/schema.sql`:

```sql
DROP TABLE IF EXISTS tenant_documents;

CREATE TABLE tenant_documents (
    tenant_id VARCHAR(80) NOT NULL,
    doc_id BIGINT NOT NULL,
    owner_issuer VARCHAR(200) NOT NULL,
    owner_subject VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    body VARCHAR(2000) NOT NULL,
    PRIMARY KEY (tenant_id, doc_id)
);

CREATE INDEX ix_tenant_docs_owner
ON tenant_documents
    (tenant_id, owner_issuer, owner_subject, status);
```

This is H2 DDL for tests, not a production migration. The test database initializes via `spring.sql.init.mode=always` and the H2 URL in `@SpringBootTest`. All SQL below uses JDBC `?` placeholders, never user-input string concatenation.

### 7.3. Complete Java integration test

`src/test/java/demo/TenantCollisionSecurityTest.java`:

```java
package demo;

import java.security.Principal;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
    classes = TenantCollisionSecurityTest.App.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.datasource.url=jdbc:h2:mem:tenant_collision_demo;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.sql.init.mode=always"
    }
)
public class TenantCollisionSecurityTest {

    private static final String ISSUER = "https://idp.example.test";

    private static final TenantPrincipal ACTOR_A =
        new TenantPrincipal(
            ISSUER, "a-user-100", "alex", "TENANT_A");

    private static final TenantPrincipal ACTOR_B =
        new TenantPrincipal(
            ISSUER, "b-user-200", "alex", "TENANT_B");

    @Autowired JdbcTemplate jdbc;
    @Autowired DataSource dataSource;
    @Autowired TenantStore store;
    @Autowired TenantDocumentService documents;
    @Autowired Probe probe;

    public record TenantPrincipal(
        String issuer, String subject,
        String username, String tenantId
    ) implements Principal {
        @Override
        public String getName() {
            return username;
        }
    }

    public record Doc(
        String tenantId, long id, String ownerIssuer,
        String ownerSubject, String status, String body
    ) {}

    public static class Probe {
        private final ConcurrentHashMap<String, AtomicInteger> counts =
            new ConcurrentHashMap<>();

        void mark(String action) {
            counts.computeIfAbsent(
                action, x -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String action) {
            AtomicInteger c = counts.get(action);
            return c == null ? 0 : c.get();
        }

        void reset() {
            counts.clear();
        }
    }

    public static class TrustedIdentity {
        public static TenantPrincipal actor(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof TenantPrincipal p)
                || p.tenantId() == null || p.tenantId().isBlank()
                || p.issuer() == null || p.issuer().isBlank()
                || p.subject() == null || p.subject().isBlank()) {
                return null;
            }
            return p;
        }

        public static TenantPrincipal requireActor() {
            TenantPrincipal p = actor(
                SecurityContextHolder.getContext().getAuthentication());
            if (p == null) {
                throw new AccessDeniedException(
                    "Trusted tenant identity required");
            }
            return p;
        }
    }

    public static class TenantStore {
        private final JdbcTemplate jdbc;

        public TenantStore(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private Doc row(
                java.sql.ResultSet rs, int rowIndex)
                throws java.sql.SQLException {
            return new Doc(
                rs.getString("tenant_id"),
                rs.getLong("doc_id"),
                rs.getString("owner_issuer"),
                rs.getString("owner_subject"),
                rs.getString("status"),
                rs.getString("body"));
        }

        public Optional<Doc> find(String tenantId, long id) {
            List<Doc> rows = jdbc.query(
                "SELECT tenant_id, doc_id, owner_issuer, " +
                "owner_subject, status, body " +
                "FROM tenant_documents " +
                "WHERE tenant_id = ? AND doc_id = ?",
                this::row, tenantId, id);
            return rows.stream().findFirst();
        }

        public List<Doc> visible(TenantPrincipal actor) {
            return jdbc.query(
                "SELECT tenant_id, doc_id, owner_issuer, " +
                "owner_subject, status, body " +
                "FROM tenant_documents " +
                "WHERE tenant_id = ? AND " +
                "(status = 'PUBLISHED' OR " +
                "(owner_issuer = ? AND owner_subject = ?)) " +
                "ORDER BY doc_id",
                this::row, actor.tenantId(),
                actor.issuer(), actor.subject());
        }

        public int updateOwnedDraft(
                TenantPrincipal actor, long id, String body) {
            return jdbc.update(
                "UPDATE tenant_documents SET body = ? " +
                "WHERE tenant_id = ? AND doc_id = ? " +
                "AND owner_issuer = ? AND owner_subject = ? " +
                "AND status = 'DRAFT'",
                body, actor.tenantId(), id,
                actor.issuer(), actor.subject());
        }

        public int deleteOwnedDraft(
                TenantPrincipal actor, long id) {
            return jdbc.update(
                "DELETE FROM tenant_documents " +
                "WHERE tenant_id = ? AND doc_id = ? " +
                "AND owner_issuer = ? AND owner_subject = ? " +
                "AND status = 'DRAFT'",
                actor.tenantId(), id,
                actor.issuer(), actor.subject());
        }

        public void createDraft(
                TenantPrincipal actor, long id, String body) {
            jdbc.update(
                "INSERT INTO tenant_documents " +
                "(tenant_id, doc_id, owner_issuer, " +
                "owner_subject, status, body) " +
                "VALUES (?, ?, ?, ?, 'DRAFT', ?)",
                actor.tenantId(), id,
                actor.issuer(), actor.subject(), body);
        }
    }

    public static class TenantPolicy {
        private final TenantStore store;

        public TenantPolicy(TenantStore store) {
            this.store = store;
        }

        public boolean valid(Authentication auth) {
            return TrustedIdentity.actor(auth) != null;
        }

        private boolean owns(TenantPrincipal actor, Doc doc) {
            return doc != null
                && doc.tenantId().equals(actor.tenantId())
                && doc.ownerIssuer().equals(actor.issuer())
                && doc.ownerSubject().equals(actor.subject());
        }

        public boolean canRead(Authentication auth, long id) {
            TenantPrincipal actor = TrustedIdentity.actor(auth);
            if (actor == null) return false;
            return store.find(actor.tenantId(), id)
                .map(doc ->
                    "PUBLISHED".equals(doc.status()) ||
                    owns(actor, doc))
                .orElse(false);
        }

        public boolean canMutate(Authentication auth, long id) {
            TenantPrincipal actor = TrustedIdentity.actor(auth);
            if (actor == null) return false;
            return store.find(actor.tenantId(), id)
                .map(doc ->
                    "DRAFT".equals(doc.status()) &&
                    owns(actor, doc))
                .orElse(false);
        }

        public boolean canCreate(Authentication auth, long id) {
            return valid(auth) && id > 0;
        }
    }

    public static class TenantDocumentService {
        private final TenantStore store;
        private final Probe probe;

        public TenantDocumentService(
                TenantStore store, Probe probe) {
            this.store = store;
            this.probe = probe;
        }

        @PreAuthorize(
            "hasAuthority('DOC_READ') and " +
            "@tenantPolicy.canRead(authentication, #docId)"
        )
        public Doc read(@P("docId") long docId) {
            probe.mark("READ");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            return store.find(actor.tenantId(), docId)
                .orElseThrow(() ->
                    new AccessDeniedException("Not visible"));
        }

        @PreAuthorize(
            "hasAuthority('DOC_READ') and " +
            "@tenantPolicy.valid(authentication)"
        )
        public List<Doc> list() {
            probe.mark("LIST");
            return store.visible(TrustedIdentity.requireActor());
        }

        @PreAuthorize(
            "hasAuthority('DOC_UPDATE') and " +
            "@tenantPolicy.canMutate(authentication, #docId)"
        )
        public Doc update(
                @P("docId") long docId, String body) {
            probe.mark("UPDATE");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            if (store.updateOwnedDraft(actor, docId, body) != 1) {
                throw new AccessDeniedException(
                    "Update denied or stale");
            }
            return store.find(actor.tenantId(), docId)
                .orElseThrow(() ->
                    new AccessDeniedException("Not visible"));
        }

        @PreAuthorize(
            "hasAuthority('DOC_DELETE') and " +
            "@tenantPolicy.canMutate(authentication, #docId)"
        )
        public void delete(@P("docId") long docId) {
            probe.mark("DELETE");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            if (store.deleteOwnedDraft(actor, docId) != 1) {
                throw new AccessDeniedException(
                    "Delete denied or stale");
            }
        }

        @PreAuthorize(
            "hasAuthority('DOC_CREATE') and " +
            "@tenantPolicy.canCreate(authentication, #docId)"
        )
        public Doc create(
                @P("docId") long docId, String body) {
            probe.mark("CREATE");
            TenantPrincipal actor = TrustedIdentity.requireActor();
            store.createDraft(actor, docId, body);
            return store.find(actor.tenantId(), docId)
                .orElseThrow();
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    public static class App {
        @Bean TenantStore tenantStore(JdbcTemplate jdbc) {
            return new TenantStore(jdbc);
        }

        @Bean("tenantPolicy")
        TenantPolicy tenantPolicy(TenantStore store) {
            return new TenantPolicy(store);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean TenantDocumentService tenantDocumentService(
                TenantStore store, Probe probe) {
            return new TenantDocumentService(store, probe);
        }
    }

    private void as(TenantPrincipal actor, String... authorities) {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                actor, "test-only",
                AuthorityUtils.createAuthorityList(authorities)));
        SecurityContextHolder.setContext(context);
    }

    private void alexInA() {
        as(ACTOR_A, "DOC_READ", "DOC_UPDATE",
            "DOC_DELETE", "DOC_CREATE");
    }

    private void alexInB() {
        as(ACTOR_B, "DOC_READ", "DOC_UPDATE",
            "DOC_DELETE", "DOC_CREATE");
    }

    @BeforeEach
    void resetFixture() {
        jdbc.update("DELETE FROM tenant_documents");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_A", 42L, ISSUER,
            "a-user-100", "DRAFT", "A private 42");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_B", 42L, ISSUER,
            "b-user-200", "DRAFT", "B private 42");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_A", 43L, ISSUER,
            "a-user-100", "PUBLISHED", "A public 43");

        jdbc.update(
            "INSERT INTO tenant_documents " +
            "(tenant_id, doc_id, owner_issuer, " +
            "owner_subject, status, body) VALUES (?, ?, ?, ?, ?, ?)",
            "TENANT_B", 44L, ISSUER,
            "b-user-200", "PUBLISHED", "B public 44");

        probe.reset();
        alexInA();
    }

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void sameDocumentIdReallyExistsInTwoTenants() {
        Long matches = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tenant_documents WHERE doc_id = 42",
            Long.class);
        assertThat(matches).isEqualTo(2L);
    }

    @Test
    void sameUsernameDoesNotMeanSameIdentity() {
        assertThat(ACTOR_A.getName()).isEqualTo("alex");
        assertThat(ACTOR_B.getName()).isEqualTo("alex");
        assertThat(ACTOR_A.subject())
            .isNotEqualTo(ACTOR_B.subject());
        assertThat(ACTOR_A.tenantId())
            .isNotEqualTo(ACTOR_B.tenantId());
    }

    @Test
    void injectedServiceIsReallyProxied() {
        assertThat(dataSource).isNotNull();
        assertThat(AopUtils.isAopProxy(documents)).isTrue();
    }

    @Test
    void alexInTenantAReadsOnlyA42() {
        Doc doc = documents.read(42L);
        assertThat(doc.body()).isEqualTo("A private 42");
        assertThat(doc.tenantId()).isEqualTo("TENANT_A");
        assertThat(probe.count("READ")).isEqualTo(1);
    }

    @Test
    void sameNamedAlexInTenantBReadsOnlyB42() {
        alexInB();
        Doc doc = documents.read(42L);
        assertThat(doc.body()).isEqualTo("B private 42");
        assertThat(doc.tenantId()).isEqualTo("TENANT_B");
    }

    @Test
    void switchingAuthenticatedTenantChangesTheResultForId42() {
        assertThat(documents.read(42L).body())
            .isEqualTo("A private 42");
        alexInB();
        assertThat(documents.read(42L).body())
            .isEqualTo("B private 42");
        assertThat(probe.count("READ")).isEqualTo(2);
    }

    @Test
    void sameUsernameWithDifferentSubjectCannotReadA42Draft() {
        as(new TenantPrincipal(
            ISSUER, "a-user-other", "alex", "TENANT_A"),
            "DOC_READ");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void usingASubjectInTenantBDoesNotImpersonateB42Owner() {
        as(new TenantPrincipal(
            ISSUER, "a-user-100", "alex", "TENANT_B"),
            "DOC_READ");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void sameSubjectButDifferentIssuerDoesNotOwnA42() {
        as(new TenantPrincipal(
            "https://other-idp.example.test",
            "a-user-100", "alex", "TENANT_A"),
            "DOC_READ");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void tenantAActorCannotReadBOnlyPublishedId44() {
        assertThatThrownBy(() -> documents.read(44L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void tenantBActorCannotReadAOnlyPublishedId43() {
        alexInB();
        assertThatThrownBy(() -> documents.read(43L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void publishedDocumentInTheSameTenantIsReadable() {
        assertThat(documents.read(43L).body())
            .isEqualTo("A public 43");
    }

    @Test
    void updateAuthorityCannotReplaceReadAuthority() {
        as(ACTOR_A, "DOC_UPDATE");
        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void untrustedStringPrincipalWithSameNameIsDenied() {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "alex", "test-only",
                AuthorityUtils.createAuthorityList("DOC_READ")));
        SecurityContextHolder.setContext(context);

        assertThatThrownBy(() -> documents.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void updateA42DoesNotChangeB42() {
        assertThat(documents.update(42L, "Changed A").body())
            .isEqualTo("Changed A");
        assertThat(store.find("TENANT_B", 42L).orElseThrow().body())
            .isEqualTo("B private 42");
        assertThat(probe.count("UPDATE")).isEqualTo(1);
    }

    @Test
    void updateB42DoesNotChangeA42() {
        alexInB();
        assertThat(documents.update(42L, "Changed B").body())
            .isEqualTo("Changed B");
        assertThat(store.find("TENANT_A", 42L).orElseThrow().body())
            .isEqualTo("A private 42");
    }

    @Test
    void sameNameImpostorCannotUpdateOtherOwnersDraft() {
        as(new TenantPrincipal(
            ISSUER, "a-user-other", "alex", "TENANT_A"),
            "DOC_UPDATE");
        assertThatThrownBy(() ->
            documents.update(42L, "Tampered"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.find("TENANT_A", 42L).orElseThrow().body())
            .isEqualTo("A private 42");
        assertThat(probe.count("UPDATE")).isZero();
    }

    @Test
    void publishedDocumentCannotBeUpdatedAsDraft() {
        assertThatThrownBy(() ->
            documents.update(43L, "Invalid"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(store.find("TENANT_A", 43L).orElseThrow().body())
            .isEqualTo("A public 43");
    }

    @Test
    void deletingA42DoesNotDeleteB42() {
        documents.delete(42L);
        assertThat(store.find("TENANT_A", 42L)).isEmpty();
        assertThat(store.find("TENANT_B", 42L)).isPresent();
        assertThat(probe.count("DELETE")).isEqualTo(1);
    }

    @Test
    void deletingB42DoesNotDeleteA42() {
        alexInB();
        documents.delete(42L);
        assertThat(store.find("TENANT_B", 42L)).isEmpty();
        assertThat(store.find("TENANT_A", 42L)).isPresent();
    }

    @Test
    void create99InBothTenantsProducesTwoSeparateRows() {
        Doc createdA = documents.create(99L, "New A");
        alexInB();
        Doc createdB = documents.create(99L, "New B");

        assertThat(createdA.tenantId()).isEqualTo("TENANT_A");
        assertThat(createdB.tenantId()).isEqualTo("TENANT_B");
        assertThat(createdA.ownerSubject()).isEqualTo("a-user-100");
        assertThat(createdB.ownerSubject()).isEqualTo("b-user-200");
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tenant_documents WHERE doc_id = 99",
            Long.class);
        assertThat(count).isEqualTo(2L);
    }

    @Test
    void duplicate99WithinSameTenantMustNotOverwrite() {
        documents.create(99L, "First");
        assertThatThrownBy(() ->
            documents.create(99L, "Overwrite attempt"))
            .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(store.find("TENANT_A", 99L).orElseThrow().body())
            .isEqualTo("First");
    }

    @Test
    void listInTenantAContainsNoTenantBRows() {
        List<Doc> results = documents.list();
        assertThat(results.stream().map(Doc::id).toList())
            .containsExactly(42L, 43L);
        assertThat(results)
            .allMatch(doc -> "TENANT_A".equals(doc.tenantId()));
    }

    @Test
    void listInTenantBContainsNoTenantARows() {
        alexInB();
        List<Doc> results = documents.list();
        assertThat(results.stream().map(Doc::id).toList())
            .containsExactly(42L, 44L);
        assertThat(results)
            .allMatch(doc -> "TENANT_B".equals(doc.tenantId()));
    }

    @Test
    void aSameNameDifferentSubjectSeesPublicButNotOtherDraft() {
        as(new TenantPrincipal(
            ISSUER, "a-user-other", "alex", "TENANT_A"),
            "DOC_READ");
        assertThat(documents.list().stream().map(Doc::id).toList())
            .containsExactly(43L);
    }

    @Test
    void missingCreateAuthorityDeniesBeforeMethodBody() {
        as(ACTOR_A, "DOC_READ");
        assertThatThrownBy(() ->
            documents.create(99L, "No permission"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("CREATE")).isZero();
    }

    @Test
    void stringPrincipalCannotListEvenWithReadAuthority() {
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "alex", "test-only",
                AuthorityUtils.createAuthorityList("DOC_READ")));
        SecurityContextHolder.setContext(context);

        assertThatThrownBy(documents::list)
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("LIST")).isZero();
    }

    @Test
    void directQueryByIdAloneIsAmbiguousAndMustNotBeUsed() {
        Long matches = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tenant_documents WHERE doc_id = ?",
            Long.class, 42L);
        assertThat(matches).isEqualTo(2L);
        assertThat(store.find("TENANT_A", 42L)).isPresent();
        assertThat(store.find("TENANT_B", 42L)).isPresent();
    }
}
```

### 7.4. Why does this example catch collision bugs properly?

**First, the test fixture does not dodge the hard case.** Two rows share `doc_id=42` and login name `alex`, yet differ in `tenant_id` and `owner_subject`. If a repository accidentally queries by ID alone, `directQueryByIdAloneIsAmbiguousAndMustNotBeUsed` proves two rows match.

**Second, principals are tested across multiple variants.** Same username, different subject in the same tenant; same username and A's subject in tenant B; same subject with a different issuer. DRAFT owner checks must deny all three. This catches weak policies like `owner_username = authentication.name`.

**Third, mutating operations use fully scoped SQL.** `UPDATE` and `DELETE` do not rely solely on pre-checks: they constrain `tenant_id`, `doc_id`, `owner_issuer`, `owner_subject`, and `status='DRAFT'` at write time. This also narrows TOCTOU risk if owner or status changes after pre-authorization.

**Fourth, CREATE never lets clients pick tenant or owner.** The service accepts only `docId` and `body`, while tenant/issuer/subject come from the trusted principal. The composite PK lets tenant A and B both create document 99 without overwriting each other.

**Fifth, both security paths and the data layer are verified.** `AopUtils.isAopProxy(documents)` proves the service is a Spring-managed proxy; `Probe` proves `@PreAuthorize` denies before the method body executes; SQL tests prove the repository remains tenant-scoped even when the method is permitted.

### 7.5. Running the tests and expected output

Inside `tenant-collision-tests`:

```bash
gradle test --tests demo.TenantCollisionSecurityTest
```

If using the Gradle Wrapper, run `./gradlew test --tests demo.TenantCollisionSecurityTest` on Linux/macOS or `gradlew.bat test --tests demo.TenantCollisionSecurityTest` on Windows.

**Expected outcome:** **28 JUnit tests** pass and Gradle reports `BUILD SUCCESSFUL` when dependencies and context are right. This is an **expected outcome from the code**, not logs captured from an execution run. The HTML report lives at `build/reports/tests/test/index.html`.

| Test group | What it proves |
| --- | --- |
| Fixture/identity | Two tenants share ID=42 and username, yet differ in subject/tenant |
| Spring proxy | `@EnableMethodSecurity` operates on the real bean |
| Read A/B #42 | Same ID returns each tenant's own content |
| Switch tenant between calls | Never reuses results from the previous tenant |
| Impostor subject/issuer | Matching username is insufficient to pass owner policy |
| ID only in the other tenant | Unreadable even when the resource is published |
| Authority | `DOC_UPDATE` does not substitute for `DOC_READ` |
| UPDATE/DELETE A/B #42 | Only the matching tenant's record is altered |
| CREATE 99 in A/B | Two independent rows, zero overwrite |
| Duplicate ID in same tenant | Composite key prevents overwrite |
| LIST | Never mixes rows across tenants, even with identical usernames |
| String principal | Trusted tenant is never inferred from `getName()` alone |
| SQL missing tenant | ID alone cannot uniquely locate a row |

**Limitations to remember:** the tests intentionally inject an already-authenticated `TenantPrincipal` into `SecurityContext`. They **do not** prove an HTTP/OIDC auth filter blocks forged tokens/tenants. Nor does H2 include PostgreSQL RLS in this example. You can claim only that this demo tests **Spring Method Security + tenant-aware JDBC repository + composite keys**.

## 8. Extending tests in real applications

### 8.1. Testing HTTP, JWT, and tenant switching

For REST APIs, generate **two real tokens signed by a test IdP**, both carrying username `alex` yet differing in `sub` and active tenant. Send the exact same `GET /documents/42` request with each token and compare responses:

- Tenant A's token receives only body `A private 42`.
- Tenant B's token receives only body `B private 42`.
- Changing only header `X-Tenant-Id` to B without B membership must be blocked.
- Forged/wrong-issuer/wrong-audience/expired tokens must be rejected at the authentication boundary.
- JWTs carrying tenant lists and active tenant must pass membership verification before constructing the principal.

**Never** place a client-supplied `tenantId` into `SecurityContext` as though it were authenticated. If usernames change, owner keys built on stable subjects must preserve permissions; when subject/issuer changes during federated account migrations, follow a controlled mapping workflow.

### 8.2. Testing JPA/Hibernate

When using JPA:

- `findById(42L)` is safe only when `42` is genuinely a global primary key or the persistence layer already enforces tenant.
- When business IDs are unique only **within a tenant**, use `@EmbeddedId` or `@IdClass`, or a global surrogate ID paired with `tenant_id` in lookups/policies.
- Foreign keys/joins must be tenant-scoped; `attachment.document_id=42` is insufficient when 42 exists in both A and B.
- Test EntityManager first-level cache, second-level cache, and Hibernate multi-tenancy tenant resolvers across context switches; caches must never key solely by local ID.
- Write integration tests on your **production DB dialect** covering JPQL, native queries, bulk UPDATE/DELETE, and pagination.

### 8.3. Spring Security ACL, `PermissionEvaluator`, and ObjectIdentity

`hasPermission(#id, 'Document', 'READ')` invokes `PermissionEvaluator` by target ID/type. If the ACL DB uses identical `ObjectIdentity(type='Document', id=42)` across two tenants, **two ACLs risk colliding on identity**. Make ACL keys tenant-aware: use either globally unique surrogate object IDs or a domain identity convention with an explicit tenant namespace, consistent when writing and reading ACLs.

`PrincipalSid("alex")` can also collide across tenants if sharing an ACL store. When ACL policies customize principal SIDs, map by stable tenant-scoped identity/issuer/sub—never assume `PrincipalSid(username)` is globally unique. ACL tests should seed two `ObjectIdentity` rows with identical local IDs across tenants and two SIDs with identical usernames yet distinct logical identities, proving ACEs never cross tenants.

### 8.4. Caches and background jobs

Reliable cache keys must distinguish tenant, object type, ID, and actor/policy context depending on cache semantics. An **unsafe** example:

```java
// Counterexample: may return tenant A's result to tenant B.
@Cacheable("documents")
public Document findById(long id) { ... }
```

If the key is only `42`, A's result can be served to B. Include tenant in cache keys and verify owner/sensitivity at the right layer. Likewise for authorization caches: never key by `(username, id)` when usernames collide across tenants.

Scheduled jobs and message consumers are not HTTP requests carrying a ready `SecurityContext`; propagate tenant context from an **authenticated envelope** or server-side workflow and bound task scope. Never use a convenient “omnipotent default tenant.” Test retries, dead-letter queues, delayed tasks after permission revocation, and per-tenant file exports.

### 8.5. PostgreSQL Row-Level Security (RLS)

RLS can block SQL that accidentally omits a tenant predicate when the app DB role does not bypass policies. However, test on real PostgreSQL using a DB role that is **neither table owner nor SUPERUSER/BYPASSRLS**. When using `set_config('app.tenant_id', ..., true)`, execute it inside the transaction on the same JDBC connection; `false` at session level can leak across connection pools.

Warning: a custom `app.tenant_id` can be set by the DB session itself, so **it is not a PostgreSQL-authenticated identity**; a SQL injection letting an attacker change that setting can bypass intent. RLS and application tests are **two complementary layers**, never substitutes for each other. The H2 test suite in section 7 **does not test RLS**.

## 9. Common mistakes and how to catch them

| Mistake | Why it is dangerous | Detection test |
| --- | --- | --- |
| `findById(42)` alone | Both tenants have ID 42 | Raw count=2; scoped query must return 1 |
| Comparing owner by username `alex` | Two distinct principals share the name | Same username, different subject test |
| Comparing only `subject` | Some IdPs/tenants share subject namespaces | Same subject, different issuer test |
| Checking only tenant on DRAFT reads | Another user in the same tenant reads private data | Same tenant, different subject test |
| Trusting `X-Tenant-Id` | Client selects a non-member tenant | HTTP token/header switch negative test |
| Global cache key `documentId` | A/B cache collision | Same ID in 2 tenants, sequential reads |
| JPA `Long @Id` with local IDs | ID collision in persistence context | `@EmbeddedId` + integration tests |
| SQL UPDATE with `WHERE doc_id` alone | One action edits both tenants | UPDATE A 42, verify B 42 unchanged |
| SQL DELETE with `WHERE doc_id` alone | Deletes another tenant's data | DELETE A 42, verify B 42 remains |
| Role check without object check | `DOC_READ` does not open every DRAFT | Non-owner in same tenant denied |
| Scoped read, unscoped LIST/EXPORT | Bulk endpoint leaks rows | Cross-tenant LIST/EXPORT tests |
| Owner check first, unconditional update later | Race/TOCTOU when owner/status changes | Conditional SQL and version tests |
| Ignoring same-name across tenant switches | Reuses stale token/cache/identity | A then B with same ID 42, distinct content |
| Testing RLS under admin DB role | Table owner/BYPASSRLS bypasses policy | Check `current_user` and role attributes |
| Treating H2 as an RLS test | H2 does not enforce PostgreSQL policies | Testcontainers PostgreSQL with real RLS |

### Key negative-path checklist

1. **Identical local ID in A/B:** both positive reads return distinct bodies, and neither ever reads the opposite tenant's record.
2. **Identical username in A/B:** confirm matching username alongside distinct issuer/sub and tenant; never accept ownership by display name.
3. **Wrong subject in same tenant:** DENY on DRAFT even with `DOC_READ`.
4. **Wrong issuer with same subject:** DENY when ownership is keyed by issuer+subject.
5. **Wrong tenant with another ID:** never return even `PUBLISHED` records from another tenant.
6. **Missing functional authority:** deny before method body, zero side effects.
7. **UPDATE/DELETE:** the other tenant's data must remain **untouched**.
8. **CREATE/duplicate:** same ID allowed in two tenants, duplicate blocked within one tenant without overwriting.
9. **LIST/search/aggregation/export:** never mix tenants or leak counts, metadata, or sensitive fields.
10. **Cache/pool/job:** when switching tenants, every layer uses the right context and never reuses prior-tenant results.

## 10. Exercises

**Exercise A — Colliding email too:** Give both actors the same email `alex@example.test`. Write a test proving policy still distinguishes actors by issuer+subject+tenant rather than using email as the owner key.

**Exercise B — Reviewer role:** Add `DOC_REVIEW` for a non-owner in the same tenant; let them read `SUBMITTED` documents while blocking a same-named user in another tenant.

**Exercise C — Hibernate:** Build an entity with `@EmbeddedId(tenantId,docId)`, add a composite attachment FK, and test that both JPQL and native SQL require tenant.

**Exercise D — Cache collision:** Add `@Cacheable` to a single-ID read in an isolated test and run A/B with 42 to observe the collision risk; fix the key to include tenant and audit cache invalidation.

**Exercise E — Tenant switching:** One actor belongs to two tenants. Design a membership-verification step before switching active tenant; verify caches and repositories never reuse stale context.

**Exercise F — Import/export:** Both tenants own a file named `report-42.csv`. Verify file paths, job IDs, download tokens, and actor permissions cannot cross tenants.

**Exercise G — PostgreSQL RLS:** Write a `USING (tenant_id = current_setting(...))` policy, use a non-bypassing DB role, and test cross-tenant SELECT/UPDATE/DELETE plus transaction-local contexts.

**Exercise H — TOCTOU:** After `@PreAuthorize` permits UPDATE, flip status to `PUBLISHED` in a competing transaction. Verify the conditional UPDATE returns 0 and performs no out-of-policy write.

## 11. Summary

To test tenant isolation properly, **do not pick distinct IDs and usernames everywhere**; deliberately construct colliding fixtures:

```text
TENANT_A / doc_id=42 / username=alex / issuer=I / sub=A100
TENANT_B / doc_id=42 / username=alex / issuer=I / sub=B200
```

Record keys are **tenant + ID**; owner identity is **tenant + issuer + subject**, never username. Spring Security enforces functional permissions and object policies; repositories/SQL maintain tenant predicates; UPDATE/DELETE enforce owner/status at write time. Test both allowed outcomes and blocked paths, and verify the other tenant's data **remains completely untouched**.

A system passes this test only when two people named `alex` read the same ID 42 and **each receives only their own data**, neither can edit or delete the other's record, LIST/cache/export results never mix, and no decision trusts client-supplied tenant claims.

## References

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, `@PreAuthorize`, custom SpEL beans, and `@P`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- OWASP API1:2023 — Broken Object Level Authorization (BOLA), per-object ID permission checks: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API3:2023 — Broken Object Property Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP API5:2023 — Broken Function Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa5-broken-function-level-authorization/
- OpenID Connect Core — Issuer/Subject claims: https://openid.net/specs/openid-connect-core-1_0.html
- PostgreSQL — Row Security Policies: https://www.postgresql.org/docs/17/ddl-rowsecurity.html
- Spring Boot 3.5 — SQL Database Initialization: https://docs.spring.io/spring-boot/3.5/reference/howto/data-initialization.html
