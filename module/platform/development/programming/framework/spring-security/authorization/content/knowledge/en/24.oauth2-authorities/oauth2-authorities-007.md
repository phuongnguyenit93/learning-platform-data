# Combining OAuth2 Scopes with Ownership and Tenancy

## 1. The problem: having a scope does not mean viewing every document

An OAuth2 access token carrying the `documents:read` scope indicates the issuer granted the client/user the **functional capability** to read documents per the API contract. It **does not prove** that the token bearer owns `Document#42`, belongs to the right tenant, has access to someone else's draft, or is allowed to export sensitive fields.

Consider two customers:

```text
TENANT_A / documentId=42 / owner=(issuer-1, sub-a) / DRAFT
TENANT_B / documentId=42 / owner=(issuer-1, sub-b) / DRAFT

Alice: JWT scope = "documents:read documents:write"
       member TENANT_A, subject sub-a
Bob:   JWT scope = "documents:read documents:write"
       member TENANT_B, subject sub-b

Both may have display username = "alex".
```

If you rely solely on `@PreAuthorize("hasAuthority('SCOPE_documents:read')")` and call `repository.findById(42)`, you can accidentally expose tenant B's data to Alice or allow another user in the same tenant to read a DRAFT. You must **combine three layers**:

1. **OAuth2 scope:** the verified token holds the functional authority, e.g., `SCOPE_documents:read`.
2. **Tenant membership/scope:** the verified principal is actually permitted to operate in the requested tenant.
3. **Object-level authorization:** the resource belongs to the right tenant, and its state and owner/ACL satisfy the specific rule; writes re-check conditions at update time.

This lesson belongs to the **Authorities from OAuth2** group of Spring Security Authorization, covering the mechanisms, Spring Security Resource Server configuration, policy design, and a Java 17+ project tested with real Spring AOP Method Security.

### Learning outcomes

After this lesson, you can:

- Explain the relationship between `scope`/`scp` claims and `SCOPE_` authorities in Spring Security Resource Server.
- Distinguish *API call permissions* from *resource permissions* and *tenant membership*.
- Use `@EnableMethodSecurity`, `@PreAuthorize`, and a policy bean receiving `Authentication` + tenant + ID to make decisions.
- Model identity using `(issuer, subject)` and owner/tenant instead of display usernames.
- Deliberately test two tenants sharing **the same document ID 42** and users sharing the same username, ensuring zero cross-tenant access.
- Prevent races on WRITE using SQL conditional updates/optimistic locking, rather than pre-method checks alone.
- Distinguish 401, 403, and 404; understand the limits of token lifetimes, revoked permissions, and machine-to-machine cases.
- Write Java 17+, Spring Security 6.5.x, Gradle, and JUnit 5 tests; separate authorization tests from cryptographic/JWT verification tests.

## 2. Scope, authority, role, ownership, and tenant are distinct concepts

| Factor | Example | What question does it answer? | Enough to read DRAFT#42? |
| --- | --- | --- | --- |
| OAuth2 scope | `documents:read` | Which operation category was the token granted? | **No** |
| GrantedAuthority | `SCOPE_documents:read` | Which functional permission does Spring Security see? | **No** |
| Role | `ROLE_EDITOR` | Which organizational role does the actor hold? | No, if unbound to the resource |
| Tenant membership | Alice belongs to TENANT_A | Which data scope may the actor access? | No, if someone else's DRAFT |
| Owner | `issuer/sub-a` | Who owns the document? | No, if lacking functional scope |
| Object state | `DRAFT`, `PUBLISHED` | Which actions does business policy allow? | Must evaluate with other conditions |
| Explicit ACL | ACE `READ` for actor/group | Does the actor have an object-specific grant? | Depends on full policy |
| Resource database isolation | `WHERE tenant_id=? AND doc_id=?` / RLS | Which rows can actually be seen/written? | Mandatory additional layer |

Scopes typically **do not carry a list of allowed document IDs**. An access token may hold `documents:read`, yet only be allowed to view a subset of documents per tenant and owner. In multi-tenant APIs, a `tenantId` in the URL/header is also **not inherently trustworthy**.

### 2.1. OAuth2 scopes belong to the token issuer; object permissions belong to the domain

The OAuth2 Authorization Server issues tokens and scopes per the contract among client, user, and resource server. The Resource Server receives the Bearer token, validates it, and translates scopes into `GrantedAuthority` instances. Application policy must still look up owner, tenant, resource state, and internal permission grants.

**Do not confuse:**

- `SCOPE_documents:read` is **not** `ROLE_documents:read`.
- `hasRole('ADMIN')` checks for the `ROLE_` prefix by default; `hasAuthority('SCOPE_documents:read')` checks the exact scope authority string.
- A token with `documents:write` does **not** imply `documents:read` unless explicitly defined by Authorization Server/app policy.
- A scope does not span all tenants; if a token is issued for a user belonging to multiple tenants, **membership and active tenant must be enforced server-side**.
- `sub` is stable within a single issuer; identical `sub` values from two issuers can refer to two different people. Avoid using `preferred_username` as a system-wide owner key.

## 3. From JWT scope to `SCOPE_` in Spring Security

### 3.1. Example JWT claims (illustrative data, not a real signed token)

```json
{
  "iss": "https://idp.example.test",
  "sub": "sub-a",
  "aud": ["documents-api"],
  "exp": 2000000000,
  "scope": "documents:read documents:write",
  "preferred_username": "alex"
}
```

With standard Resource Server JWT configuration, Spring Security reads `scope` or `scp` and converts each scope into an authority prefixed with `SCOPE_`:

```text
JWT scope="documents:read documents:write"
        |
        v
JwtAuthenticationConverter / JwtGrantedAuthoritiesConverter
        |
        +-- SCOPE_documents:read
        +-- SCOPE_documents:write
```

Spring Security 6.5 documentation confirms this default mapping for JWTs and also describes `scope` mapping from opaque token introspection. For providers using custom claims or prefixes, configure `JwtGrantedAuthoritiesConverter`—**do not assume every IdP emits identical claims**.

Example checking a scope at the HTTP layer:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(r -> r
            .requestMatchers("/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("SCOPE_documents:read")
            .requestMatchers(HttpMethod.PUT, "/api/documents/**")
                .hasAuthority("SCOPE_documents:write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

This is a **fragment**, requiring imports such as `HttpMethod`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, plus resource-server dependencies and issuer configuration. It gates only functional access at the HTTP layer. When a client calls `GET /api/documents/42`, **tenant/owner** policies are still required in the service/repository.

### 3.2. Configuring issuer and audience

In Spring Boot Resource Server JWT you can configure:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test
```

Resource Server uses the configured mechanism to fetch public keys and check signatures/timestamps/issuer. **Audience (`aud`) matching your API must also be validated** according to your version and configuration; never treat `issuer-uri` alone as sufficient for audience validation. You can define an `OAuth2TokenValidator<Jwt>` combining `JwtValidators` with an explicit audience validator.

Beyond signatures and basic claims, verify token type, trusted algorithms, scope semantics, tenant membership, and session/permission revocation per your threat model. Never base64-parse a JWT manually and treat claims as authenticated. A JWT is a **bearer credential**: anyone holding a valid token can use it during its lifetime unless sender-constrained or revocation controls are present.

### 3.3. JWT, opaque tokens, and custom claims

- JWT: resource server verifies signature, issuer, and lifetime; scopes are mapped via `JwtAuthenticationConverter`.
- Opaque token: resource server introspects with the Authorization Server; introspection scopes are typically mapped to `SCOPE_` authorities.
- Custom `roles` or `permissions` claims: do not appear as `SCOPE_` automatically without a configured converter.
- `scp` may be a list instead of a string depending on the provider; test the real claim shape from your IdP.
- Scopes granted by the Authorization Server may describe **client** permissions rather than strictly per-user permissions. Especially with `client_credentials`, there is no human user owner in the usual sense.

## 4. Three-layer rule: function + tenant + object

For a multi-tenant document management service:

```text
           Verified OAuth2 JWT
                    |
                    v
        hasAuthority(SCOPE_documents:read)
                    |
             ALLOW? | NO -> 403
                    v YES
   Principal = verified (issuer, subject)
                    |
                    v
           server-side tenant membership
                    |
             ALLOW? | NO -> DENY
                    v YES
     Load document by (tenant_id, document_id)
                    |
                    v
      Resource exists in same tenant?
                    |
             NO -> DENY/404 according to API
                    v YES
  PUBLISHED OR (DRAFT and owner issuer/sub matches)?
                    |
             NO -> DENY
                    v YES
     Service returns authorized DTO/projection
```

### 4.1. READ policy

`canRead(A, T, D)` requires **all** of:

1. Actor A is authenticated from a valid JWT source.
2. Holds authority `SCOPE_documents:read`.
3. A's issuer/sub is server-verified to hold membership in tenant T.
4. D belongs to T; queried by **tenant + document ID**, never by ID alone.
5. D is `PUBLISHED` or, if DRAFT, owner matches **the same issuer/sub** as the actor.

`PUBLISHED` in this lesson means "visible to same-tenant members holding the READ scope," **not public to the internet**.

### 4.2. WRITE policy

`canWrite(A,T,D)` requires:

1. Authority `SCOPE_documents:write` and membership in T.
2. D belongs to T, is **DRAFT**, and its owner equals A's `(issuer,sub)`.
3. At write time, SQL re-enforces tenant, owner, state (and version if present).

Why check twice? A `@PreAuthorize` check passes at t0, yet between t0 and the UPDATE statement, the document's owner/state can change or the ACL can be revoked. This is **TOCTOU (time-of-check/time-of-use)**. For state, conditional UPDATEs help; for strict grant/revocation, use transactions and version re-checks against the appropriate authority source.

### 4.3. CREATE and LIST

`CREATE` has no existing object to look up beforehand; check `SCOPE_documents:write` + membership in the requested tenant. The server sets **owner issuer/sub, tenant, and status=DRAFT**; the client must never specify an arbitrary owner.

`LIST` uses `SCOPE_documents:read` + membership, then filters in the query by **tenant** and per-row visibility. Never load all tenants and rely solely on `@PostFilter` or Java filtering when data volume or pagination matters.

### 4.4. Decisions that must never be inferred

| Single check | Why is it insufficient? |
| --- | --- |
| Only `SCOPE_documents:read` | Ignores tenant and owner |
| Only TENANT_A membership | Ignores scope and DRAFT ownership |
| Only `ownerUsername == auth.getName()` | Display usernames can collide; `JwtAuthenticationToken.getName()` defaults to `sub`, not guaranteeing matching owner format |
| Only `WHERE document_id = 42` | Two tenants can have the same ID |
| Only `@PreAuthorize` before WRITE | Race; UPDATE must constrain owner/state |
| Only JWT `tenant_id` claim | A signed claim does not guarantee active membership or permission to select that tenant |
| Only `ROLE_ADMIN` | Does not prove scope, tenant, or object grant |
| Only RLS | RLS limits rows, but does not decide READ/WRITE business rules by itself |

## 5. Identity and tenant membership at the right trust boundary

An identity should be represented by `(issuer, subject)`, or a **stable internal user ID** linked to those two attributes. `preferred_username`, email, and display names are neither guaranteed unique nor immutable. In tests, both Alice and Bob are named `alex`, yet have different subjects:

```text
Identity Alice: (iss=https://idp.example.test, sub=sub-a)
Membership: TENANT_A

Identity Bob:   (iss=https://idp.example.test, sub=sub-b)
Membership: TENANT_B

Request Alice: GET /api/tenants/TENANT_B/documents/42
-> READ scope valid, but membership wrong -> DENY.
```

Production systems must resolve **active tenant** server-side or verify tenant-switch permissions before handling a tenant-scoped URL. An `X-Tenant-Id` header never elevates privileges; JWT claims must not be used outside issuer/audience/membership bounds. If a user belongs to two tenants, verify the requested tenant is in their active membership list.

When using **tenant-scoped roles**, even a global `ROLE_ADMIN` does not imply permission to manage every tenant. Authority/role mappings should be tenant-scoped or checked alongside membership.

### 5.1. Data isolation layers

- Repository `findByTenantAndId(tenant,id)`: always scope queries.
- SQL `UPDATE ... WHERE tenant_id=? AND owner_issuer=? AND owner_sub=? AND status='DRAFT'`: guard writes at execution time.
- Tenant-scoped foreign keys/joins, preventing `attachment.document_id=42` from pointing across tenants.
- Cache keys containing tenant+resource+actor/action/policy revision when caching decisions or personalized data.
- PostgreSQL RLS can supplement; runtime DB roles must not be table owners or `BYPASSRLS`, and tenant context must be set properly per transaction/connection.

**RLS does not replace scope/owner permissions**, and an `app.tenant_id` session setting configured by the app role is not a database-authenticated identity against SQL injection.

## 6. Spring Method Security: putting business policy in a bean

You can protect the service:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_documents:read') and " +
    "@docAuthz.canRead(authentication, #tenant, #id)"
)
public DocumentView read(
        @P("tenant") String tenant,
        @P("id") long id) {
    return store.readVisible(tenant, id);
}
```

`@docAuthz.canRead(...)` receives `authentication` from the expression root and checks tenant membership + owner/status. `@P("tenant")`/`@P("id")` ensure parameter names are resolved even when not compiled with `-parameters`.

Enable it:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
    // Policy beans and services must be Spring-managed.
}
```

Spring Boot Starter Security **does not automatically enable Method Security**. `@EnableMethodSecurity` registers interceptors for `@PreAuthorize`. You must invoke the service **through a Spring proxy**, never `new DocumentService(...)` expecting annotations to run. Self-invocation `this.read(...)` inside the same bean can bypass proxy advice.

When combining HTTP and method security, check scopes in HTTP to fail fast and re-check in the service to protect jobs, consumers, and internal calls that bypass HTTP. Duplication can be reduced with shared custom authorization managers and single-source-of-truth designs, but never omit object checks.

### 6.1. Why not use `@PostAuthorize` alone for WRITE?

`@PostAuthorize` evaluates after the method body runs. If the body already wrote data or emitted events, denying afterward **does not automatically roll back**. For READ, post-checks can work when an object must be fetched before evaluation, though you must still watch for data leaks, transaction side effects, and N+1 queries. For WRITE/DELETE, prefer pre-checks plus **conditional mutations** at the data layer.

## 7. Runnable Java 17+ project: JWT scope + tenant + owner

The following project uses **real Spring Method Security/AOP**, real `JwtAuthenticationConverter` to map scopes, and an **in-memory document store** to focus on authorization logic. Tests construct `Jwt` objects and place `JwtAuthenticationToken` into `SecurityContextHolder`, so they **do not** test JWT signatures or real `Authorization: Bearer` headers. A production resource server must configure `JwtDecoder`, issuer/audience validation, a security filter chain, and real persistence.

### 7.1. File layout and Gradle

```text
oauth2-scope-tenant-ownership/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/OAuth2ScopeTenantOwnershipTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'oauth2-scope-tenant-ownership'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Because sources exist only under `src/test/java`, dependencies are in `testImplementation`. For a production app, move the resource-server starter to `implementation`. Requires JDK 17+, Gradle, and access to Maven Central.

### 7.2. Complete integrated Java source

Create `src/test/java/demo/OAuth2ScopeTenantOwnershipTest.java`:

```java
package demo;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(OAuth2ScopeTenantOwnershipTest.Config.class)
public class OAuth2ScopeTenantOwnershipTest {

    private static final String ISSUER = "https://idp.example.test";

    public record Identity(String issuer, String subject) {}
    public record Key(String tenant, long id) {}

    public record Doc(
        String tenant, long id, Identity owner,
        String state, String body
    ) {
        public View view() {
            return new View(tenant, id, state, body);
        }
    }

    // DTO does not expose owner subject/issuer.
    public record View(
        String tenant, long id, String state, String body
    ) {}

    public static class Memberships {
        private final Map<Identity, Set<String>> tenants = Map.of(
            new Identity(ISSUER, "sub-a"), Set.of("TENANT_A"),
            new Identity(ISSUER, "sub-b"), Set.of("TENANT_B"),
            new Identity(ISSUER, "sub-reviewer"),
                Set.of("TENANT_A", "TENANT_B"),
            new Identity(ISSUER, "sub-other"), Set.of("TENANT_A")
        );

        public boolean contains(Identity actor, String tenant) {
            return actor != null && tenants.getOrDefault(
                actor, Set.of()).contains(tenant);
        }
    }

    public static class Documents {
        private final Map<Key, Doc> rows =
            new ConcurrentHashMap<>();

        public void reset() {
            rows.clear();
            rows.put(new Key("TENANT_A", 42L),
                new Doc("TENANT_A", 42L,
                    new Identity(ISSUER, "sub-a"),
                    "DRAFT", "A private 42"));
            rows.put(new Key("TENANT_B", 42L),
                new Doc("TENANT_B", 42L,
                    new Identity(ISSUER, "sub-b"),
                    "DRAFT", "B private 42"));
            rows.put(new Key("TENANT_A", 43L),
                new Doc("TENANT_A", 43L,
                    new Identity(ISSUER, "publisher"),
                    "PUBLISHED", "A public 43"));
            rows.put(new Key("TENANT_B", 44L),
                new Doc("TENANT_B", 44L,
                    new Identity(ISSUER, "publisher"),
                    "PUBLISHED", "B public 44"));
        }

        public Doc find(String tenant, long id) {
            return rows.get(new Key(tenant, id));
        }

        public List<Doc> listVisible(
                String tenant, Identity actor) {
            return rows.values().stream()
                .filter(doc -> tenant.equals(doc.tenant()))
                .filter(doc ->
                    "PUBLISHED".equals(doc.state())
                    || doc.owner().equals(actor))
                .sorted(Comparator.comparingLong(Doc::id))
                .toList();
        }

        public boolean updateOwnedDraft(
                String tenant, long id,
                Identity actor, String newBody) {
            AtomicBoolean updated = new AtomicBoolean();
            rows.computeIfPresent(new Key(tenant, id), (key, old) -> {
                if (!"DRAFT".equals(old.state())
                        || !old.owner().equals(actor)) {
                    return old;
                }
                updated.set(true);
                return new Doc(
                    old.tenant(), old.id(), old.owner(),
                    old.state(), newBody);
            });
            return updated.get();
        }

        public boolean createDraft(
                String tenant, long id,
                Identity owner, String body) {
            if (id <= 0) return false;
            Doc created = new Doc(
                tenant, id, owner, "DRAFT", body);
            return rows.putIfAbsent(
                new Key(tenant, id), created) == null;
        }

        public void publish(String tenant, long id) {
            rows.computeIfPresent(new Key(tenant, id),
                (key, doc) -> new Doc(
                    doc.tenant(), doc.id(), doc.owner(),
                    "PUBLISHED", doc.body()));
        }
    }

    public static class DocumentPolicy {
        private final Memberships memberships;
        private final Documents documents;

        DocumentPolicy(
                Memberships memberships, Documents documents) {
            this.memberships = memberships;
            this.documents = documents;
        }

        public Identity trustedIdentity(Authentication auth) {
            if (auth == null || !auth.isAuthenticated()
                || !(auth instanceof JwtAuthenticationToken token)) {
                return null;
            }

            Jwt jwt = token.getToken();
            String issuer = jwt.getClaimAsString("iss");
            String subject = jwt.getSubject();

            // Demo: policy layer also checks the specific issuer.
            // Production: decoder must validate signature, iss,
            // exp, nbf, aud before creating Authentication.
            if (!ISSUER.equals(issuer)
                || subject == null || subject.isBlank()) {
                return null;
            }
            return new Identity(issuer, subject);
        }

        public Identity requireIdentity() {
            Identity actor = trustedIdentity(
                SecurityContextHolder.getContext()
                    .getAuthentication());
            if (actor == null) {
                throw new AccessDeniedException(
                    "Trusted identity required");
            }
            return actor;
        }

        public boolean canList(
                Authentication auth, String tenant) {
            Identity actor = trustedIdentity(auth);
            return memberships.contains(actor, tenant);
        }

        public boolean canRead(
                Authentication auth, String tenant, long id) {
            Identity actor = trustedIdentity(auth);
            if (id <= 0 || !memberships.contains(actor, tenant)) {
                return false;
            }

            Doc doc = documents.find(tenant, id);
            return doc != null
                && doc.tenant().equals(tenant)
                && ("PUBLISHED".equals(doc.state())
                    || doc.owner().equals(actor));
        }

        public boolean canWrite(
                Authentication auth, String tenant, long id) {
            Identity actor = trustedIdentity(auth);
            if (id <= 0 || !memberships.contains(actor, tenant)) {
                return false;
            }

            Doc doc = documents.find(tenant, id);
            return doc != null
                && doc.tenant().equals(tenant)
                && "DRAFT".equals(doc.state())
                && doc.owner().equals(actor);
        }

        public boolean canCreate(
                Authentication auth, String tenant, long id) {
            Identity actor = trustedIdentity(auth);
            return id > 0 && memberships.contains(actor, tenant);
        }
    }

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger writes = new AtomicInteger();
        private final AtomicInteger lists = new AtomicInteger();
        private final AtomicInteger creates = new AtomicInteger();

        public void read() { reads.incrementAndGet(); }
        public void write() { writes.incrementAndGet(); }
        public void list() { lists.incrementAndGet(); }
        public void create() { creates.incrementAndGet(); }

        public int reads() { return reads.get(); }
        public int writes() { return writes.get(); }
        public int lists() { return lists.get(); }
        public int creates() { return creates.get(); }

        public void reset() {
            reads.set(0);
            writes.set(0);
            lists.set(0);
            creates.set(0);
        }
    }

    public static class DocumentService {
        private final Documents documents;
        private final DocumentPolicy policy;
        private final Probe probe;

        DocumentService(
                Documents documents,
                DocumentPolicy policy, Probe probe) {
            this.documents = documents;
            this.policy = policy;
            this.probe = probe;
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:read') and " +
            "@docAuthz.canRead(authentication, #tenant, #id)"
        )
        public View read(
                @P("tenant") String tenant,
                @P("id") long id) {
            probe.read();
            Doc doc = documents.find(tenant, id);
            if (doc == null) {
                throw new AccessDeniedException("Not visible");
            }
            return doc.view();
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:write') and " +
            "@docAuthz.canWrite(authentication, #tenant, #id)"
        )
        public View write(
                @P("tenant") String tenant,
                @P("id") long id, String newBody) {
            probe.write();

            Identity actor = policy.requireIdentity();
            if (!documents.updateOwnedDraft(
                    tenant, id, actor, newBody)) {
                throw new AccessDeniedException(
                    "Write denied or stale");
            }

            return documents.find(tenant, id).view();
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:read') and " +
            "@docAuthz.canList(authentication, #tenant)"
        )
        public List<View> list(
                @P("tenant") String tenant) {
            probe.list();
            Identity actor = policy.requireIdentity();
            return documents.listVisible(tenant, actor)
                .stream().map(Doc::view).toList();
        }

        @PreAuthorize(
            "hasAuthority('SCOPE_documents:write') and " +
            "@docAuthz.canCreate(authentication, #tenant, #id)"
        )
        public View create(
                @P("tenant") String tenant,
                @P("id") long id, String body) {
            probe.create();
            Identity actor = policy.requireIdentity();

            if (!documents.createDraft(
                    tenant, id, actor, body)) {
                throw new IllegalStateException(
                    "Duplicate or invalid document ID");
            }

            return documents.find(tenant, id).view();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {
        @Bean Memberships memberships() {
            return new Memberships();
        }

        @Bean Documents documents() {
            return new Documents();
        }

        @Bean("docAuthz")
        DocumentPolicy documentPolicy(
                Memberships membership, Documents docs) {
            return new DocumentPolicy(membership, docs);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentService documentService(
                Documents docs, DocumentPolicy policy,
                Probe probe) {
            return new DocumentService(docs, policy, probe);
        }
    }

    @Autowired Documents documents;
    @Autowired DocumentPolicy policy;
    @Autowired DocumentService service;
    @Autowired Probe probe;

    private static JwtAuthenticationToken token(
            String issuer, String subject,
            String displayName, String scope) {
        Jwt jwt = Jwt.withTokenValue("test-token-" + subject)
            .header("alg", "RS256")
            .claim("iss", issuer)
            .claim("sub", subject)
            .claim("preferred_username", displayName)
            .claim("scope", scope)
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .build();

        // Use real converter to test scope -> SCOPE_ mapping,
        // without signing/verifying token via JwtDecoder.
        return (JwtAuthenticationToken)
            new JwtAuthenticationConverter().convert(jwt);
    }

    private void as(
            String issuer, String subject,
            String username, String scopes) {
        JwtAuthenticationToken authenticated = token(
            issuer, subject, username, scopes);
        SecurityContext ctx =
            SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(authenticated);
        SecurityContextHolder.setContext(ctx);
    }

    private void alice(String scopes) {
        as(ISSUER, "sub-a", "alex", scopes);
    }

    private void bob(String scopes) {
        as(ISSUER, "sub-b", "alex", scopes);
    }

    private void reviewer(String scopes) {
        as(ISSUER, "sub-reviewer", "reviewer", scopes);
    }

    @BeforeEach
    void reset() {
        documents.reset();
        probe.reset();
        alice("documents:read documents:write");
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void serviceUsesARealSpringMethodSecurityProxy() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void jwtScopeConverterAddsScopePrefix() {
        JwtAuthenticationToken t = token(
            ISSUER, "sub-a", "alex",
            "documents:read documents:write");

        assertThat(t.getAuthorities().stream()
            .map(a -> a.getAuthority()).toList())
            .contains("SCOPE_documents:read")
            .contains("SCOPE_documents:write");
    }

    @Test
    void jwtAuthenticationNameDefaultsToSubjectNotUsername() {
        JwtAuthenticationToken a = token(
            ISSUER, "sub-a", "alex", "documents:read");
        JwtAuthenticationToken b = token(
            ISSUER, "sub-b", "alex", "documents:read");

        assertThat(a.getName()).isEqualTo("sub-a");
        assertThat(b.getName()).isEqualTo("sub-b");
        assertThat(a.getToken().getClaimAsString(
            "preferred_username")).isEqualTo("alex");
        assertThat(b.getToken().getClaimAsString(
            "preferred_username")).isEqualTo("alex");
    }

    @Test
    void aliceReadsOnlyHerTenantADraft42() {
        View view = service.read("TENANT_A", 42L);
        assertThat(view.tenant()).isEqualTo("TENANT_A");
        assertThat(view.body()).isEqualTo("A private 42");
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void bobWithSameScopesReadsDifferentTenantB42() {
        bob("documents:read documents:write");
        View view = service.read("TENANT_B", 42L);
        assertThat(view.tenant()).isEqualTo("TENANT_B");
        assertThat(view.body()).isEqualTo("B private 42");
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void aliceCannotReadTenantB42EvenWithReadScope() {
        assertThatThrownBy(() -> service.read("TENANT_B", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void bobCannotReadTenantA42EvenWithReadScope() {
        bob("documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void tenantAActorCannotReadPublishedTenantB44() {
        assertThatThrownBy(() -> service.read("TENANT_B", 44L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void reviewerCanReadPublishedDocumentsInBothTenants() {
        reviewer("documents:read");
        assertThat(service.read(
            "TENANT_A", 43L).body()).isEqualTo("A public 43");
        assertThat(service.read(
            "TENANT_B", 44L).body()).isEqualTo("B public 44");
    }

    @Test
    void reviewerCannotReadAliceDraftEvenInSameTenant() {
        reviewer("documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void sameDisplayedUsernameOtherSubjectCannotReadDraft() {
        as(ISSUER, "sub-other", "alex", "documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void sameSubjectFromDifferentIssuerIsRejected() {
        as("https://other-idp.example.test", "sub-a",
            "alex", "documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void missingReadScopeStopsBeforeServiceBody() {
        alice("documents:write");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void genericAdminRoleIsNotDocumentReadScope() {
        alice("admin");
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void missingMembershipIsDeniedEvenWithReadScope() {
        as(ISSUER, "unknown-sub", "alex", "documents:read");
        assertThatThrownBy(() -> service.read("TENANT_A", 43L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void wrongDocumentIdIsDenied() {
        assertThatThrownBy(() -> service.read("TENANT_A", 999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void unauthenticatedRequestCannotUseMethod() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> service.read("TENANT_A", 42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void readScopeDoesNotGrantWrite() {
        alice("documents:read");
        assertThatThrownBy(() ->
            service.write("TENANT_A", 42L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.writes()).isZero();
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void aliceCanWriteOwnDraftWithoutChangingTenantB() {
        View changed = service.write(
            "TENANT_A", 42L, "Changed A");
        assertThat(changed.body()).isEqualTo("Changed A");
        assertThat(documents.find(
            "TENANT_B", 42L).body()).isEqualTo("B private 42");
        assertThat(probe.writes()).isEqualTo(1);
    }

    @Test
    void bobCanWriteOwnDraftWithoutChangingTenantA() {
        bob("documents:write");
        assertThat(service.write(
            "TENANT_B", 42L, "Changed B").body())
            .isEqualTo("Changed B");
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void reviewerCannotWriteAnotherOwnersDraft() {
        reviewer("documents:write");
        assertThatThrownBy(() ->
            service.write("TENANT_A", 42L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.writes()).isZero();
    }

    @Test
    void publishedDocumentCannotBeChangedAsDraft() {
        documents.publish("TENANT_A", 42L);
        assertThatThrownBy(() ->
            service.write("TENANT_A", 42L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(documents.find(
            "TENANT_A", 42L).body()).isEqualTo("A private 42");
    }

    @Test
    void listShowsOnlyTenantAVisibleRecords() {
        List<View> results = service.list("TENANT_A");
        assertThat(results.stream().map(View::id).toList())
            .containsExactly(42L, 43L);
        assertThat(results).allMatch(
            d -> "TENANT_A".equals(d.tenant()));
    }

    @Test
    void listShowsOnlyTenantBVisibleRecords() {
        bob("documents:read");
        List<View> results = service.list("TENANT_B");
        assertThat(results.stream().map(View::id).toList())
            .containsExactly(42L, 44L);
        assertThat(results).allMatch(
            d -> "TENANT_B".equals(d.tenant()));
    }

    @Test
    void reviewerListHidesDraftsOwnedByOtherUsers() {
        reviewer("documents:read");
        assertThat(service.list("TENANT_A").stream()
            .map(View::id).toList()).containsExactly(43L);
    }

    @Test
    void listWithoutReadScopeIsDeniedBeforeBody() {
        alice("documents:write");
        assertThatThrownBy(() -> service.list("TENANT_A"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.lists()).isZero();
    }

    @Test
    void createDerivesTenantAndOwnerFromTrustedIdentity() {
        View created = service.create(
            "TENANT_A", 99L, "New A");
        assertThat(created.tenant()).isEqualTo("TENANT_A");
        assertThat(created.state()).isEqualTo("DRAFT");
        assertThat(documents.find(
            "TENANT_A", 99L).owner())
            .isEqualTo(new Identity(ISSUER, "sub-a"));
        assertThat(probe.creates()).isEqualTo(1);
    }

    @Test
    void bothTenantsMayCreateSameLocalDocumentId() {
        service.create("TENANT_A", 99L, "A 99");
        bob("documents:write");
        service.create("TENANT_B", 99L, "B 99");

        assertThat(documents.find(
            "TENANT_A", 99L).body()).isEqualTo("A 99");
        assertThat(documents.find(
            "TENANT_B", 99L).body()).isEqualTo("B 99");
    }

    @Test
    void duplicateIdInSameTenantCannotOverwriteDocument() {
        service.create("TENANT_A", 99L, "First");

        assertThatThrownBy(() ->
            service.create("TENANT_A", 99L, "Overwrite"))
            .isInstanceOf(IllegalStateException.class);
        assertThat(documents.find(
            "TENANT_A", 99L).body()).isEqualTo("First");
    }

    @Test
    void createWithoutWriteScopeStopsBeforeMethodBody() {
        alice("documents:read");
        assertThatThrownBy(() ->
            service.create("TENANT_A", 99L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }

    @Test
    void cannotCreateInsideAnotherTenant() {
        assertThatThrownBy(() ->
            service.create("TENANT_B", 99L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }

    @Test
    void invalidIdCannotBeCreated() {
        assertThatThrownBy(() ->
            service.create("TENANT_A", 0L, "Blocked"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.creates()).isZero();
    }
}
```

### 7.3. Run instructions and how to interpret results

Inside the `oauth2-scope-tenant-ownership` directory:

```bash
gradle test --tests demo.OAuth2ScopeTenantOwnershipTest
```

Or with the Gradle Wrapper: Linux/macOS `./gradlew test --tests demo.OAuth2ScopeTenantOwnershipTest`, Windows `gradlew.bat test --tests demo.OAuth2ScopeTenantOwnershipTest`.

**Expected result:** all JUnit tests succeed and Gradle outputs `BUILD SUCCESSFUL` given a compatible environment and dependencies. This is an **expectation based on the sample code, not an actual execution report**. HTML report: `build/reports/tests/test/index.html`.

| Test group | What is proven |
| --- | --- |
| Method Security proxy | `@PreAuthorize` executes on a Spring-managed bean |
| JWT converter | Scopes `documents:read` / `documents:write` become `SCOPE_`-prefixed authorities |
| JWT subject | `getName()` defaults to `sub`; display usernames can collide |
| READ A/B #42 | Same local ID returns the result for the right tenant |
| Cross-tenant/membership | Valid scope with wrong tenant is still denied |
| Owner | DRAFT cannot be read by others in the same tenant, even with scope |
| Different issuer/subject | Cannot borrow the document owner's rights |
| Missing scope | Rejected before the method body |
| WRITE | Requires WRITE scope and matching owner/state; never mutates another tenant |
| LIST | Shows only records matching tenant and visibility |
| CREATE | Owner, tenant, and state come from policy/server; prevents same-tenant overwrite |
| Negative paths | Unknown resource, missing auth, invalid ID, wrong issuer, duplicate |

### 7.4. What this example does *not* prove

The JUnit tests manually place `JwtAuthenticationToken` into `SecurityContextHolder`—simulating **completed authentication** without verifying JWT signatures, JWT headers, issuer discovery, JWK rotation, audience validators, or HTTP Bearer challenges. Testing the scope converter **does not replace** integration tests with a real `JwtDecoder` and authentication filter.

The store uses `ConcurrentHashMap` to illustrate composite tenant keys and conditional writes, which does not replace real database transactions, RLS, or multi-node concurrency testing. `DocumentPolicy` hardcodes the trusted issuer solely for clarity; production code must receive issuers already validated by the resource server and check memberships from a trusted source.

To test the HTTP resource server, add Spring MVC/MockMvc and Spring Security Test with `jwt()` or test-signed tokens; distinguish mock JWT tests from real signature-validation tests:

```java
// Fragment: MockMvc test for the scope/HTTP layer (mock JWT,
// does not verify signatures).
mockMvc.perform(get("/api/tenants/TENANT_A/documents/42")
        .with(jwt().jwt(j -> j
            .claim("scope", "documents:read")
            .claim("sub", "sub-a"))
        .authorities(new SimpleGrantedAuthority(
            "SCOPE_documents:read"))))
    .andExpect(status().isOk());
```

This snippet requires MockMvc, static `jwt`/`get`/`status` imports, controllers, and full beans; it is **not a standalone test**. Because `.authorities(...)` is supplied manually, it tests the HTTP permission gate **without proving `JwtGrantedAuthoritiesConverter` ran**. The test suite in Section 7 directly uses the real `JwtAuthenticationConverter` to test mapping.

## 8. From in-memory to SQL repositories and PostgreSQL RLS

A safe tenant-keyed data schema:

```sql
CREATE TABLE tenant_documents (
    tenant_id TEXT NOT NULL,
    document_id BIGINT NOT NULL,
    owner_issuer TEXT NOT NULL,
    owner_subject TEXT NOT NULL,
    status TEXT NOT NULL,
    body TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, document_id)
);
```

READ query:

```sql
SELECT tenant_id, document_id, status, body
FROM tenant_documents
WHERE tenant_id = :tenant
  AND document_id = :id
  AND (
      status = 'PUBLISHED'
      OR (
          owner_issuer = :actor_issuer
          AND owner_subject = :actor_subject
      )
  );
```

This condition must run **after** verifying `SCOPE_documents:read` and tenant membership. If business rules also include group/share ACLs, add the corresponding predicates and tests.

Conditional UPDATE:

```sql
UPDATE tenant_documents
SET body = :new_body,
    version = version + 1
WHERE tenant_id = :tenant
  AND document_id = :id
  AND owner_issuer = :actor_issuer
  AND owner_subject = :actor_subject
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Verify that affected rows equal **1**. If 0, the operation may be stale, missing, wrong tenant, or wrong owner; return 403/404/409 per API contract without leaking cross-tenant resources. This condition prevents writing when owner/status/version changes between precheck and update, though **it does not automatically cover grants revoked between the two moments**; if needed, combine policy revisions or authorization re-checks inside the same transaction.

### 8.1. RLS is a supplemental defense layer

With PostgreSQL, RLS can enforce the tenant predicate in the DB:

```sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_guard ON tenant_documents
FOR ALL TO app_role
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), '')
)
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), '')
);
```

This is a **fragment**; you must create the DB role and proper GRANTs, use transaction-local tenant context, and ensure the DB role is neither table owner, superuser, nor `BYPASSRLS`. `app.tenant_id` set by the app role **is not a DB-authenticated identity**, so still guard against SQL injection. RLS does not replace scopes, ownership, or field-level permissions.

## 9. Caching, token lifetimes, and revoking permissions

An issued JWT is a time-bounded credential. If Alice's membership in tenant A is revoked, `SCOPE_documents:read` may remain in her token until expiration. Therefore, **the scope gate must be paired with the current membership/policy store**, or version/revocation-aware caching within SLA.

A decision cache needs a complete key:

```text
(tenant, issuer, subject,
 resourceType, resourceId,
 action, policyRevision)
```

Never cache solely by `documentId=42` or username `alex`: tenant A/B and other users can share IDs or names. TTLs bound entry lifetimes but **do not guarantee immediate revocation**. You may need post-commit invalidation when ACLs/owners/tenant memberships change, multi-node event broadcasts, or direct re-checks on sensitive WRITE/APPROVE operations.

With OAuth2 **`client_credentials`**, the access token can represent a **service/client** with no human owner subject. Never assume the client owns a document just because it has a scope. Use workload identities, service account permissions, allowed tenant sets, actor delegation when truly acting for a user, and clear caller/subject auditing.

## 10. HTTP outcomes: 401, 403, 404, and 409

| Scenario | Common outcome | Notes |
| --- | --- | --- |
| Missing or invalid Bearer token | **401 Unauthorized** | Configure resource-server entry point / Bearer challenge properly |
| Valid token missing `SCOPE_documents:read` | **403 Forbidden** | Do not prompt re-login by default |
| Token has scope, not a member of requested tenant | **403** or **404** | Depends on resource-existence concealment policy |
| Token has scope and tenant, someone else's DRAFT | **403** or **404** | Never disclose owner/data in error body |
| Resource genuinely does not exist in tenant | **404** or uniform deny | API contract must stay consistent |
| Conditional update affected rows=0 due to version change | **409 Conflict** or equivalent | Never leak cross-tenant objects |
| PDP/membership service unavailable | Fail closed; usually **503** or safe authz deny | Never fall back to ALLOW |
| Valid READ scope, missing CSRF in cookie-based app | May be **403 due to CSRF** | Do not mistake for object authorization |

Resource Servers typically emit `WWW-Authenticate: Bearer ...` per RFC 6750 for applicable errors. Never return 200 with `{"allowed":false}` or a 403 leaking tokens, internal issuers, or SQL/ACL expressions. For cross-tenant APIs, do not reveal owner differences in error payloads if concealment is required by contract.

## 11. Common mistakes

| Anti-pattern | Why it is dangerous | Fix |
| --- | --- | --- |
| Has READ scope so calls `findById(id)` | Scope does not guard objects; IDs can collide across tenants | Scope + member + tenant-scoped lookup |
| Owner = display username | Usernames/email aliases are non-unique or mutable | Issuer/sub or stable internal user ID |
| Using `ROLE_ADMIN` for all-tenant permissions | Roles do not imply tenant membership | Tenant-scoped role/policy and exact authorities |
| Checking raw `scope` from unverified JWT | Client can send forged tokens | Resource Server `JwtDecoder`/introspection |
| Validating issuer without audience | Valid tokens for other APIs can be replayed | Per-API audience validator |
| Treating `scope=documents:write` as READ | Scopes are independent unless contract specifies inheritance | Check each `SCOPE_` authority explicitly |
| Trusting `tenantId` in URL/header alone | Client can swap tenant | Resolve from verified principal + membership |
| Using only `@PreAuthorize` for UPDATE | Owner/status/version race | Conditional SQL and affected-row check |
| Testing with all unique IDs and usernames | Misses collision bugs | Test shared ID=42 and colliding usernames across tenants |
| Assuming `getName()` is username | `JwtAuthenticationToken.getName()` defaults to `sub` | Use explicit identity from issuer/sub |
| Valid scope but list/export omits filtering | Leaks entire tenant or sensitive fields | Query-time filtering + DTO allow-list |
| Caching `ALLOW` until JWT expires | Slow revocation, stale privileges | TTL, invalidation, policy revision, re-check |
| Enabling Method Security then calling `new Service()` | Loses Spring proxy | Inject bean and test `AopUtils.isAopProxy` |
| Calling `this.write(...)` | Self-invocation bypasses proxy advice | Clean service boundaries |
| Checking only in HTTP filter | Internal jobs bypass HTTP API | Object policy in service/repository |
| Testing JWT with mocks and claiming signature is safe | Mocks bypass decoding/verification | Add test-signed tokens and `JwtDecoder` integration tests |

## 12. Acceptance checklist

- [ ] Spring Resource Server validates issuer, signature, expiry/`nbf`, audience, and trusted algorithms per config.
- [ ] Every endpoint/method checks the exact `SCOPE_documents:read/write` scope; never infer roles/authorities from similar names.
- [ ] Principal is `(issuer,sub)` or a stable user ID; `preferred_username` is display-only.
- [ ] Tenant membership is verified from a trusted source and active tenant is validated.
- [ ] Objects are looked up by `(tenant_id,document_id)`; DRAFTs are readable only when owner/ACL permits.
- [ ] List/export/count and caches enforce tenant, visibility, and field-level policies.
- [ ] CREATE never trusts client-supplied owner or tenant.
- [ ] WRITE/DELETE/APPROVE use conditional SQL, versioning, or in-transaction re-checks where needed.
- [ ] Permission service/DB failures never yield ALLOW; metrics/alerts and error contracts are clear.
- [ ] Negative tests cover missing scope, wrong tenant, wrong owner/issuer/sub, wrong ID, cross-tenant shared ID, and invalid tokens.
- [ ] Real HTTP Bearer JWT/introspection tests complement unit tests using mocked `JwtAuthenticationToken`.
- [ ] Token lifecycle, membership revocation, machine-to-machine, and multi-node caching are threat-modeled.
- [ ] Never rely solely on HTTP authorization; Method Security and repositories protect data too.

## 13. Extension exercises

1. **Separate scopes:** add `documents:approve` for reviewers, verify makers cannot self-approve, and ensure `documents:write` does not imply approval rights.
2. **Tenant switch:** give Alice membership in A+B, create a server-verified active tenant session claim, and test valid/invalid tenant switches.
3. **JWT audience:** configure `JwtDecoder` with an audience validator, send a validly signed token for `another-api`, and assert 401.
4. **Opaque tokens:** use introspection with a `scope` claim, confirming `SCOPE_` authorities are still produced and mapped consistently.
5. **PostgreSQL Testcontainers:** replace `ConcurrentHashMap` with a composite-key table and RLS; test queries missing a tenant predicate directly using the runtime DB role.
6. **Concurrent writes:** add a version column and test status changing DRAFT→PUBLISHED between precheck and UPDATE; affected rows=0.
7. **Shared ACL:** share a DRAFT document for READ with a same-tenant non-owner; require scope + membership + ACL simultaneously.
8. **Client credentials:** design service account scopes and an authorized tenant list; never treat service tokens as human owners.
9. **Cache collision:** deliberately key a cache by ID 42, reproduce the A/B leak, and fix the key to include tenant, actor, action, and version.
10. **HTTP tests:** add `MockMvc` with `jwt()`, clearly distinguishing scope authorization from real resource-server signature verification.

## 14. Conclusion

A token with the `documents:read` scope tells you only the allowed **operation category**, not that the caller can view every document. To protect real data, check **all of these together**:

```text
allow = token authenticated and right scope
        and verified tenant membership
        and resource belongs to tenant
        and object owner/ACL/status policy passes
```

In Spring Security 6.5, scopes are typically mapped to `SCOPE_` authorities, `@EnableMethodSecurity` lets `@PreAuthorize` combine authorities with policy beans, and repositories/SQL need tenant predicates plus conditional writes to prevent data leaks and TOCTOU races.

The Java test suite in this lesson intentionally reuses the same local ID and username across two tenants to catch flawed assumptions. Before shipping to production, test real JWT validation through the resource-server filter, database transactions, revocation, rate/cache behavior, and machine-to-machine permissions for your target environment.

## Official references

- Spring Security 6.5 — OAuth2 Resource Server JWT and `SCOPE_` mapping: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server Opaque Token and scope authorities: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — Method Security and custom SpEL beans: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security Test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Security 6.5 — Mock JWT Resource Server Test: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- OAuth 2.0 Framework — Scopes, RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Tokens — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OpenID Connect Core — Issuer/Subject claims: https://openid.net/specs/openid-connect-core-1_0.html
- OWASP API1:2023 — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
