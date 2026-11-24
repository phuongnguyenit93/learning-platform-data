# Preventing Cross-Tenant Access When Querying Resources and Checking Permissions

## Learning Objectives

This lesson belongs to the **Gateway and Multi-tenancy** chapter of **Spring Security reactive (Spring WebFlux)**. After studying it, you will be able to:

- Distinguish the **requested tenant** arriving from path/host/header from the **authorized tenant** verified via JWT identity, active membership, and business permissions.
- Explain **cross-tenant access**, **Broken Object Level Authorization (BOLA/IDOR)**, tenant ID spoofing, confused deputy, cache leakage, and the mistake of trusting only the Gateway.
- Establish authorization logic requiring simultaneous conditions: JWT verification, HTTP scope, tenant claim, active membership, resource tenant, owner/ACL, and resource state.
- Use **ServerHttpSecurity**, **SecurityWebFilterChain**, **@EnableReactiveMethodSecurity**, **@PreAuthorize**, and **@AuthenticationPrincipal Jwt** properly in the reactive stack.
- Read and update resources using a composite key **(tenant_id, document_id)**; distinguish middleware checks from SQL/R2DBC/ACL checks.
- Design an API Gateway that never trusts client-sent `X-Tenant-Id`/`X-User-Id`/`X-Roles` headers, while protecting downstream if the Gateway is bypassed.
- Run a **Java 17 + Spring Boot 3.5** example with tenants alpha/beta, colliding document IDs, per-tenant permissions, HTTP GET/PATCH, and `WebTestClient` tests with `mockJwt`.
- Plan protection for search/count/export, Redis/caches, PostgreSQL RLS, background jobs, multi-issuer identities, and security regression tests.

> **Scope:** Application with multiple **business tenants** (alpha, beta) sharing **one trusted JWT issuer**. If each tenant has its own issuer, see the multi-issuer topic. The example uses an in-memory Map to teach the mechanism, **not to replace a production database**. No additional Special Note.

## 1. Tenant Routing Does Not Equal Tenant Authorization

An HTTP request:

~~~http
GET /api/tenants/alpha/documents/doc-001 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

The `alpha` string in the URL only says which tenant the caller **wants to access**; it does not prove they belong to tenant alpha. The Gateway knows how to route, but may not know who owns document `doc-001` or whether the user's membership is still active.

Required flow:

~~~text
Client → API Gateway → Spring WebFlux Resource Server
                         |
                         ├─ JWT valid? (signature, iss, aud, exp/nbf)
                         ├─ Operation scope? (documents.read/write)
                         ├─ Token permits requestedTenant?
                         ├─ Current membership active and allows action?
                         └─ Query document by tenant + ID + owner/ACL
                              |
                              ├─ Wrong/missing permission → 401/403/404
                              └─ Permitted                → minimal DTO
~~~

Concepts:

| Name | Source | Trust Level |
|---|---|---|
| Requested tenant | Path, subdomain, or header from request | Merely an **untrusted** selector |
| JWT subject | `sub` of verified token | Identifier within the issuer's scope |
| JWT `tenant_ids` | Claim signed by trusted issuer | List of tenants permitted by the token; may be stale |
| Active membership | System database/PDP | Up-to-date permissions per tenant and action |
| Resource `tenant_id` | Trusted row/data store | Must match the authorized requested tenant |
| Owner/ACL | Server-side data | **Per-object** permissions |
| `X-Tenant-Id`/`X-Roles` | Headers a client can send | **Never proof of permission on their own** |
| `Forwarded`/`X-Forwarded-*` | Reverse proxy metadata | Does not prove tenant membership |

### 1.1. Authorization rules must be a logical AND

~~~text
ALLOW(user, tenant, action, resource) =
    VALID_JWT(user, expected_issuer, expected_audience)
    AND HAS_SCOPE(user, action)
    AND TOKEN_ALLOWS_TENANT(user, tenant)
    AND ACTIVE_MEMBER(user, tenant)
    AND TENANT_PERMISSION(user, tenant, action)
    AND RESOURCE_TENANT(resource) == tenant
    AND (OWNER(resource) == user OR VALID_ACL(user, resource, action))
    AND RESOURCE_STATE_ALLOWS(action)
~~~

If any single condition fails, **deny by default**. Having a scope does not mean permission to read all tenants. Merely being a tenant member does not mean permission to read another user's private documents within the same tenant.

### 1.2. Two distinct authorization boundaries

**Cross-tenant:** Alice holds a token only for tenant alpha yet tries `beta/doc-003`. Must be rejected before querying beta.

**Cross-object within a tenant:** Alice belongs to alpha and has `documents.read`, yet tries Bob's `alpha/doc-002`. This is **BOLA/IDOR** and must still be denied by owner/ACL checks.

OWASP API Security Top 10 2023 ranks Broken Object Level Authorization as the #1 risk. Hard-to-guess UUID IDs **do not replace** server-side authorization checks.

### 1.3. Identical document IDs across two tenants

~~~text
alpha / doc-001 → owner Alice
beta  / doc-001 → owner Bob
~~~

Never use a lookup or cache key containing only `doc-001`. Use **`TenantDocumentKey(tenant,id)`**, SQL `WHERE tenant_id + id`, composite indexes/constraints, and tenant-aware cache keys. This remains necessary even if IDs are currently globally unique: policies must be explicit to avoid bugs during data integration/imports.

## 2. JWT, Principal, and Scopes

Illustrative payload example, **not a validly signed token**:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["tenant-documents-api"],
  "sub": "alice",
  "tenant_ids": ["alpha"],
  "scope": "documents.read documents.write",
  "exp": 1893456000
}
~~~

The Resource Server must verify signature/JWKS, issuer, audience, and expiration/nbf before Spring Security builds an authenticated principal. Never Base64-decode the payload and trust its claims; never accept scopes/roles/tenants from unprotected headers.

| Claim | Meaning | Does Not Replace |
|---|---|---|
| `iss` | Trusted issuer | Object ownership |
| `aud` | Target Resource API | Tenant membership |
| `sub` | Identity within issuer | Business permissions |
| `scope`/`scp` | Operation-level permissions | Tenant + ACL |
| `tenant_ids` | Token tenant allowlist | Current membership state |
| `exp`/`nbf` | Validity window | Permissions revoked after issuance |

In Spring Security JWT Resource Server, a scope claim like:

~~~json
{"scope":"documents.read documents.write"}
~~~

is mapped to authorities:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

In WebFlux, use **`hasAuthority("SCOPE_documents.read")`** to check scopes rather than `hasRole("documents.read")`, because the `ROLE_` prefix differs from `SCOPE_`.

### 2.1. Tenant membership can change between access tokens

A JWT lists beta in `tenant_ids`, yet Alice was just revoked from beta. Looking only at the JWT would allow access until the token expires. For sensitive resources, use an **active membership store**, policy engine, short-lived access tokens, token versioning, or revocation checks matching your revocation SLA.

The same user may have write access in alpha and read-only access in beta. Never let a global `ROLE_EDITOR` grant write access across all tenants.

### 2.2. Requested tenant is input, not Authentication

Wrong:

~~~java
// ANTI-PATTERN: X-Tenant-Id is untrusted.
String tenant = exchange.getRequest()
    .getHeaders().getFirst("X-Tenant-Id");
return repository.findByTenantId(tenant);
~~~

Better: take the tenant from the path as the target requiring authorization, obtain the **verified `Jwt`** via `@AuthenticationPrincipal`, and verify that the tenant belongs to both the token allowlist and active membership. Only then pass the authorized tenant to the repository.

If the system uses subdomains like `alpha.api.example.test`, the host is also merely a routing selector. Map the hostname via a trusted tenant registry, normalize path/host consistently, and still verify membership.

## 3. Gateway as Defense-in-Depth

The Gateway can:

1. Terminate TLS/mTLS, route, and canonicalize path/host.
2. Validate JWTs or forward tokens for the backend Resource Server to revalidate.
3. Strip/overwrite client-spoofable identity headers (`X-User-Id`, `X-Roles`, `X-Tenant-Id`).
4. Enforce route allowlists, request size limits, timeouts, and rate limits per authorized identity/tenant.
5. Attach a signed internal identity context or mTLS between Gateway and backend if needed, with integrity, expiry, and allowlists.
6. Block direct backend network access if the design relies on the Gateway boundary.
7. Log correlation IDs without logging raw JWTs, Authorization headers, or document contents.

However, the Gateway usually does not know which tenant `doc-001` belongs to, who owns the row, or which ACL was just revoked. **Downstream services must enforce resource-level checks themselves**.

### 3.1. Trusted proxies are not trusted tenant claims

Spring Cloud Gateway WebFlux provides Forwarded and X-Forwarded HTTP headers filters; `trusted-proxies` configuration controls which proxies are trusted for routing headers. That **does not** automatically make `X-Tenant-Id` or `X-User-Id` trustworthy.

If the Gateway passes trusted identity in headers, it must strip original client headers, block direct bypasses, and use mTLS/signed context; never entrust all authorization to a plaintext header. A cleaner alternative is having the backend Resource Server verify the JWT and query membership directly.

### 3.2. When the Gateway rewrites URLs

For example, rewriting `/t/alpha/...` to `/api/tenants/alpha/...`. Test URL encoding, duplicate slashes, casing, dot-segments, Unicode, and Host header spoofing so Gateway and Backend never parse different tenants. Map to a canonical **internal tenant ID**, avoiding display names in authorization.

### 3.3. Broad service tokens create confused deputies

A worker holds `client_credentials` capable of reading multiple tenants. A user belonging only to alpha triggers an export job for beta. If the backend executes using the worker's privileges without checking the caller's permissions, that is a **confused deputy**. Jobs must authorize the service identity, tenant, action, and (where applicable) initiating user separately.

## 4. Scoping Queries Directly at R2DBC/Database

### 4.1. The mistake of looking up solely by ID

~~~java
// ANTI-PATTERN, missing tenant:
return repository.findById(documentId);
~~~

If record IDs collide across tenants or repositories query shared tables, BOLA becomes trivial. With PostgreSQL/R2DBC, enforce a tenant predicate:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :authorized_tenant
  AND d.id = :document_id
  AND (
      d.owner_sub = :verified_subject
      OR EXISTS (
          SELECT 1
          FROM document_acl acl
          WHERE acl.tenant_id = d.tenant_id
            AND acl.document_id = d.id
            AND acl.grantee_sub = :verified_subject
            AND acl.can_read = TRUE
      )
  );
~~~

**`authorized_tenant`** is the requested tenant after membership/policy approval. **`verified_subject`** comes from the verified `Jwt`. Use **bind parameters**; never concatenate query input into SQL strings.

With multi-issuer identities, use `(issuer,subject)` or an internal user ID rather than comparing email or display name alone.

### 4.2. Composite schema keys

~~~sql
CREATE TABLE documents (
    tenant_id VARCHAR(80) NOT NULL,
    id VARCHAR(80) NOT NULL,
    owner_sub VARCHAR(200) NOT NULL,
    title TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id)
);

CREATE INDEX documents_owner_idx
ON documents (tenant_id, owner_sub, id);
~~~

Foreign keys on ACLs/attachments should reference both **`tenant_id` and `document_id`**. Never let a beta attachment point to `alpha/doc-001`.

### 4.3. Conditional updates and TOCTOU

Wrong:

~~~sql
UPDATE documents SET title = :title WHERE id = :id;
~~~

Better:

~~~sql
UPDATE documents
SET title = :title,
    version = version + 1
WHERE tenant_id = :authorized_tenant
  AND id = :document_id
  AND owner_sub = :verified_subject
  AND version = :expected_version
RETURNING id, title, version;
~~~

If editors gain access via ACL, include the ACL predicate within the same transaction/conditional update. Never check ownership with a GET and then execute an unconditional UPDATE by ID, because owner/ACL/tenant can change between the two operations (TOCTOU). Use proper versioning/locking/transactions.

### 4.4. Search, list, count, export, and pagination

Never SELECT everything and filter by tenant in Java **after LIMIT/OFFSET**: page counts will be wrong and metadata can leak. Use:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :authorized_tenant
  AND owner_sub = :verified_subject
ORDER BY created_at DESC, id
LIMIT :page_size;
~~~

The same applies to COUNT, aggregates, Elasticsearch/OpenSearch, files, webhooks, websocket streams, batch updates, and async exports. Tenant scoping must be built into the query/index policy from the start.

### 4.5. PostgreSQL Row Level Security

An additional layer:

~~~sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
~~~

RLS is strictly defense-in-depth:

- `app.tenant_id` must be set from the **authorized tenant**, never from raw `X-Tenant-Id`.
- With R2DBC/connection pooling, set the tenant within the **transaction scope** (e.g., `SET LOCAL` inside a transaction) so it never leaks across connections.
- DB owners/superusers can bypass RLS; evaluate `FORCE ROW LEVEL SECURITY` and database roles.
- RLS does not protect caches, search indexes, object storage, or all business ACLs.
- Run tests against a real database with multiple concurrent tenants and connection reuse.

Separate schemas or databases per tenant offer stronger isolation in some respects, but tenant→schema/datasource routing still requires a **trusted allowlist**—never concatenate a raw path into a SQL identifier or JDBC URL.

## 5. Reactive Context and Auxiliary Systems

### 5.1. Never store tenant in ThreadLocal or mutable singleton state

WebFlux uses **Reactor Context** and can switch threads. A static `ThreadLocal currentTenant` or mutable field on a singleton service easily causes cross-request contamination.

The easiest pattern to audit: **Controller receives `(requestedTenant, authenticatedJwt)` → Service validates → Repository receives explicit `authorizedTenant`**. If using Reactor Context for the trusted tenant, attach it only after authorization and write propagation tests; never populate trusted context from a raw header.

### 5.2. Cache keys

Do not use:

~~~text
document:doc-001
~~~

Because both alpha and beta have `doc-001`. Use at minimum:

~~~text
tenant:alpha:document:doc-001
tenant:beta:document:doc-001
~~~

If responses depend on ACLs/users/field masking, cache keys or strategies must also include identity/policy version; alternatively cache the raw server-side object and check permissions before serialization. Invalidate when membership, owner, or ACL changes; private HTTP responses generally need appropriate `Cache-Control: private/no-store`.

### 5.3. Background jobs and auditing

A scheduled export has no user `ServerWebExchange`/`Authentication`. It must use an explicit service identity and tenant scope:

~~~text
trusted job tenant=alpha
  -> authorize service to export alpha
  -> select alpha-scoped data
  -> write output under alpha namespace
  -> emit alpha-scoped event
  -> audit tenant + service + job ID
~~~

Never put Bearer tokens, emails, or raw document contents into shared logs/traces. If tenants can view logs/audit dashboards, dashboard access must also be tenant-scoped.

### 5.4. Multi-issuer vs. business multi-tenancy

Business tenants alpha and beta can share a single issuer. When there genuinely are multiple JWT issuers, reactive Spring Security provides **`JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)`**. Only allow a trusted issuer allowlist; **never** take an arbitrary `iss` and auto-construct decoders/JWKS, which risks arbitrary trust/SSRF.

If two issuers both have `sub` alice, they are two distinct identities. Membership keys must include `(issuer,sub,tenant)` or map to a verified internal user ID.

## 6. Java 17 Lab: Scope + Tenant Claim + Active Membership + Owner

The demo is a Spring Boot 3.5.16 WebFlux Resource Server with two endpoints:

- `GET /api/tenants/{tenant}/documents/{id}`: requires `SCOPE_documents.read` and membership `documents:read`, then owner or tenant-scoped `documents:read:any`.
- `PATCH /api/tenants/{tenant}/documents/{id}`: requires `SCOPE_documents.write` and membership `documents:write`, then **owner**.
- `GET /api/health`: public.

Data:

| Tenant | Document | Owner | Title |
|---|---|---|---|
| alpha | doc-001 | alice | Alpha Alice document |
| alpha | doc-002 | bob | Alpha Bob document |
| beta | doc-001 | bob | Beta Bob document |
| beta | doc-003 | alice | Beta Alice document |

Server-side membership:

| Tenant | User | Permissions |
|---|---|---|
| alpha | alice | documents:read, documents:write |
| alpha | bob | documents:read |
| beta | alice | documents:read |
| alpha | auditor | documents:read, documents:read:any |

Notice **`doc-001` appears in both alpha and beta**. Auditor has permission to read any document in alpha only, not automatically in beta.

### 6.1. Project

~~~text
tenant-isolation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/TenantIsolationApplication.java
    │   └── resources/application.yml
    └── test/java/example/TenantIsolationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tenant-isolation'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - tenant-documents-api
~~~

The issuer/JWKS URLs are **illustrative only**; verifying real JWTs requires a real IdP with the right issuer/JWKS/audience. When both `issuer-uri` and `jwk-set-uri` are provided, the decoder still validates the issuer and fetches keys on demand without requiring discovery at startup. Offline tests use `mockJwt` and do not contact an IdP.

### 6.2. Standalone Runnable Code in Spring Boot

**src/main/java/example/TenantIsolationApplication.java**

~~~java
package example;

import java.util.Collection;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
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
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class TenantIsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantIsolationApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            // Suitable only for Bearer-header APIs without cookie auth.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/tenants/*/documents/*")
                    .hasAuthority("SCOPE_documents.read")
                .pathMatchers(HttpMethod.PATCH,
                    "/api/tenants/*/documents/*")
                    .hasAuthority("SCOPE_documents.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }

    public record TenantDocumentKey(String tenant, String id) {}
    public record TenantUserKey(String tenant, String sub) {}
    public record TenantMember(
        boolean active, Set<String> permissions) {}
    public record DocumentRecord(
        String tenant, String id, String ownerSub, String title) {}
    public record DocumentView(String id, String title) {}
    public record RenameRequest(String title) {}

    @Service
    public static class DocumentService {

        // LAB DATA: production uses real R2DBC/PDP.
        private final Map<TenantUserKey, TenantMember> members =
            Map.of(
                new TenantUserKey("alpha", "alice"),
                    new TenantMember(true, Set.of(
                        "documents:read", "documents:write")),
                new TenantUserKey("alpha", "bob"),
                    new TenantMember(true, Set.of("documents:read")),
                new TenantUserKey("beta", "alice"),
                    new TenantMember(true, Set.of("documents:read")),
                new TenantUserKey("alpha", "auditor"),
                    new TenantMember(true, Set.of(
                        "documents:read", "documents:read:any"))
            );

        private final ConcurrentMap<TenantDocumentKey, DocumentRecord>
            documents = new ConcurrentHashMap<>(Map.of(
                new TenantDocumentKey("alpha", "doc-001"),
                    new DocumentRecord("alpha", "doc-001",
                        "alice", "Alpha Alice document"),
                new TenantDocumentKey("alpha", "doc-002"),
                    new DocumentRecord("alpha", "doc-002",
                        "bob", "Alpha Bob document"),
                new TenantDocumentKey("beta", "doc-001"),
                    new DocumentRecord("beta", "doc-001",
                        "bob", "Beta Bob document"),
                new TenantDocumentKey("beta", "doc-003"),
                    new DocumentRecord("beta", "doc-003",
                        "alice", "Beta Alice document")
            ));

        private ResponseStatusException denied() {
            return new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        private ResponseStatusException hidden() {
            return new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        private Mono<TenantMember> requireMember(
            Jwt jwt, String tenant, String action) {

            return Mono.defer(() -> {
                if (jwt == null || jwt.getSubject() == null
                    || jwt.getSubject().isBlank() || tenant == null
                    || !tenant.matches("[a-z][a-z0-9-]{0,39}")) {
                    return Mono.error(denied());
                }

                // Jwt was already verified by the resource server; invalid schema → deny.
                Object raw = jwt.getClaim("tenant_ids");
                if (!(raw instanceof Collection<?> ids)
                    || ids.stream().anyMatch(
                        item -> !(item instanceof String))
                    || !ids.contains(tenant)) {
                    return Mono.error(denied());
                }

                // Current server-side permissions take precedence over stale tokens.
                TenantMember member = members.get(
                    new TenantUserKey(tenant, jwt.getSubject()));

                if (member == null || !member.active()
                    || !member.permissions().contains(action)) {
                    return Mono.error(denied());
                }

                return Mono.just(member);
            });
        }

        private DocumentView view(DocumentRecord doc) {
            return new DocumentView(doc.id(), doc.title());
        }

        @PreAuthorize("hasAuthority('SCOPE_documents.read')")
        public Mono<DocumentView> read(
            String tenant, String id, Jwt jwt) {

            return requireMember(jwt, tenant, "documents:read")
                .flatMap(member -> Mono.justOrEmpty(
                    documents.get(new TenantDocumentKey(tenant, id)))
                    .filter(doc ->
                        Objects.equals(
                            doc.ownerSub(), jwt.getSubject())
                        || member.permissions().contains(
                            "documents:read:any"))
                    .map(this::view)
                    .switchIfEmpty(Mono.error(hidden())));
        }

        @PreAuthorize("hasAuthority('SCOPE_documents.write')")
        public Mono<DocumentView> rename(
            String tenant, String id, Jwt jwt,
            RenameRequest request) {

            return requireMember(jwt, tenant, "documents:write")
                .flatMap(member -> Mono.defer(() -> {
                    if (request == null
                        || request.title() == null
                        || request.title().isBlank()
                        || request.title().length() > 120) {
                        return Mono.error(
                            new ResponseStatusException(
                                HttpStatus.BAD_REQUEST, "Invalid title"));
                    }

                    AtomicReference<DocumentRecord> updated =
                        new AtomicReference<>();
                    TenantDocumentKey key =
                        new TenantDocumentKey(tenant, id);

                    // Atomic condition within one map key for demo.
                    // Production: UPDATE WHERE tenant+id+owner+version.
                    documents.computeIfPresent(key, (k, old) -> {
                        if (!Objects.equals(
                                old.ownerSub(), jwt.getSubject())) {
                            return old;
                        }
                        DocumentRecord next = new DocumentRecord(
                            old.tenant(), old.id(),
                            old.ownerSub(), request.title());
                        updated.set(next);
                        return next;
                    });

                    return Mono.justOrEmpty(updated.get())
                        .map(this::view)
                        .switchIfEmpty(Mono.error(hidden()));
                }));
        }
    }

    @RestController
    public static class DocumentController {

        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/api/health")
        public Mono<Map<String, String>> health() {
            return Mono.just(Map.of("status", "ok"));
        }

        @GetMapping("/api/tenants/{tenant}/documents/{id}")
        public Mono<DocumentView> read(
            @PathVariable String tenant,
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
            return service.read(tenant, id, jwt);
        }

        @PatchMapping("/api/tenants/{tenant}/documents/{id}")
        public Mono<DocumentView> rename(
            @PathVariable String tenant,
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody Mono<RenameRequest> body) {
            return body.flatMap(request ->
                service.rename(tenant, id, jwt, request));
        }
    }
}
~~~

### 6.3. Explaining the Safeguards

**JWT Resource Server:** The Spring Security decoder checks signature/issuer/audience/expiry. Invalid or missing tokens typically return 401.

**Operation scope:** HTTP GET requires `SCOPE_documents.read`, PATCH requires `SCOPE_documents.write`. Every other path/method is denied.

**Method security:** `@PreAuthorize` on the service prevents another caller inside the Spring context from bypassing HTTP rules. Reactive methods return `Mono` and read `Authentication` from Reactor Context.

**Token allowlist:** `requireMember` verifies that the `tenant_ids` Collection contains the requested tenant, has the right types, and has a non-null/non-blank subject. Never falls back to a default tenant.

**Current membership:** The server store must contain an active member with `documents:read` or `documents:write` for that exact tenant. The demo uses a Map; production uses a DB/PDP.

**Object isolation:** `TenantDocumentKey(tenant,id)` serves as the composite lookup key. Owner is checked against JWT `sub`; auditor has `read:any` only in alpha. There is no global admin bypass.

**Write:** `computeIfPresent` verifies owner and updates atomically per map key; production uses conditional SQL inside a transaction. Active membership can change between calls, so production needs freshness/invalidation and transactional policies.

**Response minimization:** The DTO exposes only `id`/`title`, omitting internal roles/owner/tenant unless required.

**Header spoofing:** `X-Tenant-Id`/`X-Roles` are never read to grant permissions, so an attacker cannot switch tenants via headers.

**CSRF:** Disabling CSRF in the demo is valid only for a Bearer-header API without browser cookie/session authentication. If session cookies are used, keep proper CSRF/Origin/SameSite protections and never copy `csrf.disable()` unconditionally.

### 6.4. Run and Observe

~~~bash
gradle bootRun
~~~

With wrapper: `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows).

~~~bash
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/tenants/alpha/documents/doc-001
~~~

Expect health HTTP 200 and JSON:

~~~json
{"status":"ok"}
~~~

GET document **without a token** expects HTTP 401. To call the protected API successfully, replace the demo issuer/JWKS with a real IdP and supply a token with the right audience, scope, `tenant_ids`, and subject. No valid access token can be minted from the `idp.example.test` placeholder. Never paste raw tokens into issues, public logs, or shell history.

## 7. WebTestClient Negative Tests Without an IdP

Spring Security Test supports **`mockJwt()`** to inject a JWT Authentication into the mock WebFlux security context. It tests **authorization** for scope, tenant, membership, and owner, but **does not test JWT signatures, issuer, audience, or expiry**. Those require separate tests with a real decoder and signed JWTs/JWKS.

**src/test/java/example/TenantIsolationTest.java**

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class TenantIsolationTest {

    @Autowired
    WebTestClient client;

    private WebTestClient as(
        String sub, List<String> tenants, String... authorities) {

        var granted =
            new SimpleGrantedAuthority[authorities.length];

        for (int i = 0; i < authorities.length; i++) {
            granted[i] =
                new SimpleGrantedAuthority(authorities[i]);
        }

        return client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", sub)
                .claim("tenant_ids", tenants))
            .authorities(granted));
    }

    @Test
    void publicHealthWorks() {
        client.get().uri("/api/health")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void noTokenReturns401() {
        client.get().uri(
            "/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceReadsOwnAlphaDocument() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-001");
    }

    @Test
    void noReadScopeReturns403() {
        as("alice", List.of("alpha"))
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void writeScopeIsNotReadScope() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void alphaTokenCannotAccessBeta() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-003")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tenantClaimWithoutMembershipIsInsufficient() {
        as("charlie", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void aliceCannotReadBobsDocumentInSameTenant() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-002")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void unknownDocumentAlsoReturns404() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/not-there")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void sameIdInDifferentTenantsDoesNotLeak() {
        // doc-001 in alpha belongs to Alice, in beta belongs to Bob.
        as("alice", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-001")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void aliceCanReadOwnBetaDocumentWithBetaToken() {
        as("alice", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-003")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void alphaAuditorCanReadAlphaBobDocument() {
        as("auditor", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-002")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void alphaAuditorCannotReadBeta() {
        as("auditor", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void spoofedTenantHeaderDoesNotChangeAuthorizedPath() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .header("X-Tenant-Id", "beta")
            .header("X-Roles", "SUPER_ADMIN")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void spoofedHeaderDoesNotOpenBeta() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-003")
            .header("X-Tenant-Id", "alpha")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void patchRequiresWriteScope() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .patch().uri("/api/tenants/alpha/documents/doc-001")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "Try update"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void bobReadOnlyMembershipCannotWrite() {
        as("bob", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-002")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "Try update"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void aliceCannotWriteBobsDocument() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-002")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "No access"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void aliceCannotWriteBetaWithAlphaToken() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/beta/documents/doc-003")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "No access"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void aliceCanWriteOwnDocument() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-001")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "Updated by Alice"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Updated by Alice");
    }

    @Test
    void blankTitleReturns400() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-001")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                ""))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void unknownTenantIsNotAutoProvisioned() {
        as("alice", List.of("unknown"), "SCOPE_documents.read")
            .get().uri("/api/tenants/unknown/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test` with the wrapper. There are **22 test methods**, expected to pass on a compatible toolchain; **the code was not executed while authoring this lesson**. These tests need no IdP because they mock WebFlux Authentication, so they do not yet verify a real JWT decoder, SQL RLS, caches, or Gateway security.

### 7.1. Why are negative tests essential?

- 401 for requests without a token.
- 403 for missing scope, requested tenant absent from JWT claim, missing server membership, or missing write permission.
- 404 for wrong owner and non-existent documents, per the existence-hiding policy.
- **Identical document ID across alpha/beta** to catch repository keys missing the tenant.
- Auditor `read:any` applies only to **alpha**, never beta.
- Spoofed `X-Tenant-Id`/`X-Roles` headers never change the authorized identity/tenant.
- PATCH yields 200 for the rightful owner and 403/404 for wrong permission/owner/tenant.
- Public health 200 ensures the test suite does not merely prove the app rejects everything.

The patch test mutates the in-memory title; other tests do not depend on the original title, so no fixed execution order is required.

### 7.2. Additional integration tests required before production

1. Use real signed JWTs from a test JWKS; test bad signature, `iss`, `aud`, and expired/`nbf`.
2. Run R2DBC/Testcontainers PostgreSQL and create identical document IDs across two tenants.
3. Mutation-test removing the tenant predicate to confirm regression tests catch BOLA.
4. Revoke DB membership while a token is still unexpired; subsequent requests must be denied.
5. Test stale ACLs and owner transfers under concurrent transactions.
6. Verify search/count/export/bulk endpoints keep the same tenant predicate as detail GET.
7. Ensure Redis caches warmed by alpha never serve beta.
8. Ensure RLS connection pool `SET LOCAL` never leaks tenants across subscriptions.
9. Verify Gateway strips spoofed identity headers and blocks direct-to-backend bypasses.
10. Test background jobs/service credentials and tenant-scoped outputs.

## 8. 401, 403, and 404 in Multi-Tenant APIs

| Status | Purpose | Example |
|---|---|---|
| **401** | No valid identity | Missing/invalid JWT |
| **403** | Identity present but lacks permission | Missing scope, tenant claim omits requested tenant, revoked membership |
| **404** | Object absent or hidden | Non-existent document ID, document owned by another user within authorized tenant |
| **200** | All safeguards passed | Alice reads `alpha/doc-001` |

To prevent **tenant enumeration**, some APIs return 404 instead of 403 for tenants the caller does not belong to. HTTP semantics must stay consistent and avoid leaking tenant/object existence via error bodies, timing, counts, or audit endpoints. Internal logging should still record the denial reason safely.

## 9. Common Mistakes

**1. Checking only scope:** `documents.read` does not grant access to read all tenants.

**2. Taking tenant solely from path/header:** Those are untrusted selectors.

**3. Checking membership but skipping owner/ACL:** Users in the same tenant could read each other's private documents (BOLA).

**4. Repository using only `findById`:** ID collisions and cross-tenant lookups.

**5. Filtering tenant after LIMIT:** Wrong page counts and metadata leaks.

**6. Enforcing authZ only at the Gateway:** The Gateway does not know row ACLs and can be bypassed.

**7. Treating `X-Forwarded-*` as identity:** Forwarded headers serve only network routing.

**8. Trusting client-sent `X-Tenant-Id`/`X-Roles`:** Easily spoofed; must strip and verify trusted context.

**9. Stale token membership:** Use server-side active entitlement checks when revocation must take effect quickly.

**10. Global admin unscoped by tenant:** Leads to easy privilege escalation.

**11. Missing JWT audience validator:** May accept tokens issued for another resource server.

**12. Keying solely by `sub` with multiple issuers:** Two issuers can share `sub`; use `issuer+sub`.

**13. Building issuer decoders from arbitrary raw token claims:** Risks arbitrary trust and SSRF.

**14. Concatenating tenant path directly into schema/DB URI:** Injection/misrouting; use allowlist mappings.

**15. GET-check followed by UPDATE by ID alone:** TOCTOU; require conditional updates/transactions.

**16. Cache keys with only document ID:** Can serve beta from cached alpha entries.

**17. Unscoped search/count/export:** Data leaks even when detail endpoints are protected.

**18. `ThreadLocal` tenant in Reactor:** Context mixes across thread switches and concurrency.

**19. Broad service token ignoring user permissions:** Confused deputy.

**20. Testing only 200 happy paths:** Fails to prove cross-tenant denial.

**21. Equating `mockJwt` with signature testing:** False; mock bypasses the decoder.

**22. Disabling CSRF in apps using session cookies:** Requires a dedicated browser auth threat model.

**23. Returning raw entities:** May expose internal owner/tenant/private fields; use DTOs.

**24. Logging JWTs, tokens, or document bodies:** Leaks credentials/PII into traces and logs.

**25. Inconsistent tenant ID normalization across hops:** Enables bypasses when gateway and backend parse differently.

**26. Foreign keys lacking tenant:** ACLs/attachments can point across tenants.

**27. RLS not setting tenant properly per transaction:** Connection pool may leak context.

**28. Falling back to a default for unknown tenants:** Fail closed; never auto-provision from a request.

## 10. Deployment Checklist

1. Are JWT issuer/JWKS, audience, signature, and expiry verified?
2. Is the tenant selector in requests always treated as untrusted until authorized?
3. Are tenant IDs canonicalized and mapped through a trusted registry?
4. Are `SCOPE_documents.read`/`write` separated per method with deny-by-default fallback?
5. Is JWT `tenant_ids` schema-checked, denying when missing or malformed?
6. Are active membership and permissions checked per tenant and current subject?
7. Are admin/`read:any` roles tenant-scoped and audited?
8. Do resource queries always include `tenant_id + id + owner/ACL`?
9. Are DB composite primary/foreign keys and indexes properly defined?
10. Do conditional UPDATE/DELETE statements enforce tenant/owner/version/transaction?
11. Are list/count/search/export/batch/attachments properly scoped?
12. Do cache keys, policy versions, and invalidation prevent cross-tenant leaks?
13. Does the Gateway strip spoofed identity headers and block direct bypasses?
14. Is trusted proxy metadata prevented from acting as authorization authority?
15. Are multi-issuer identities keyed by `issuer+sub` or internal user IDs?
16. Do service-to-service calls and background jobs enforce tenant-aware policies?
17. Is reactive context free of mutable globals and `ThreadLocal`?
18. Are HTTP 401/403/404 statuses consistent with the threat model?
19. Does CSRF match browser cookies vs. stateless Bearer tokens?
20. Are logs/traces/metrics scrubbed of raw tokens and sensitive data?
21. Do negative tests cover wrong tenant/owner/scope/membership and colliding IDs?
22. Do integration tests cover signed JWTs, DB/RLS, caches, Gateway, and concurrency?
23. Are ACL/membership revocation and cache invalidation policies in place?
24. Is a tenant/data-access security review performed before adding new endpoints?

## 11. Self-Check Questions

**1.** Does a request with path `beta` prove the caller belongs to beta?

**Answer:** No. That is the requested tenant; verified JWT + membership + permissions are required.

**2.** Alice has `documents.read` in alpha; can she read Bob's document?

**Answer:** No, unless granted an explicit ACL or `read:any` for alpha.

**3.** What if a JWT still lists beta in `tenant_ids` after membership is revoked?

**Answer:** Server-side membership checks must deny access; JWT claims can be stale.

**4.** Why must queries include both `tenant_id` and `id`?

**Answer:** Different tenants can have identical document IDs; a composite predicate prevents returning the wrong row.

**5.** If the Gateway already validated the JWT, can downstream skip object authorization?

**Answer:** No. The Gateway does not know row owners/ACLs and may be bypassed.

**6.** Can client-sent `X-Tenant-Id` be trusted to grant permissions?

**Answer:** No. Trusted identity proof, gateway header stripping, and backend re-verification are required.

**7.** What does Spring map JWT scopes to?

**Answer:** By default, `documents.read` maps to `SCOPE_documents.read`.

**8.** When are 401/403/404 used in the demo?

**Answer:** 401 when unauthenticated; 403 for missing scope/membership/tenant; 404 for wrong owner or missing document.

**9.** Does `mockJwt` test JWS signatures and `aud`?

**Answer:** No. Signed tokens, JWKS, and the real decoder must be tested separately.

**10.** Does RLS replace membership policy in Spring?

**Answer:** No. RLS is DB defense-in-depth; caller authorization, pool context, and cache/search checks remain essential.

**11.** What if two issuers both have `sub` alice?

**Answer:** They are not the same identity; use `issuer+sub` or a trusted internal mapping.

**12.** Why is cache key `document:doc-001` insufficient?

**Answer:** Alpha and beta can share the same ID; caches must be tenant-aware and account for authorization dimensions.

**13.** If a service token has permission across all tenants, can an alpha user trigger an export for beta?

**Answer:** Not automatically. Authorize both the caller and the service operation to prevent confused deputy.

## Official References

- Spring Security — Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security — Reactive HTTP Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security — mockJwt for WebFlux tests: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Boot 3.5 — issuer-uri, jwk-set-uri and audiences properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Cloud Gateway WebFlux — Trusted proxies and Forwarded headers: https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html
- OWASP API1:2023 Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
