# Authorizing by Scope, Business Claims, and Resource Ownership

## Learning Objectives

This lesson belongs to **Resource Server JWT** in **Spring Security reactive / Spring WebFlux**. After studying it, you can:

- Explain the differences among **Authentication** (is the JWT valid and who is calling?), **scope authorization** (what action scope was the token granted?), **business claims** (role/permission policy from a trusted issuer), and **resource ownership** (who owns the actual record, and in which tenant?).
- Understand how Spring Security converts `scope` or `scp` claims into `SCOPE_`-prefixed authorities and uses `ServerHttpSecurity.authorizeExchange(...)` per HTTP method/path.
- Customize `JwtAuthenticationConverter` + `ReactiveJwtAuthenticationConverterAdapter` to add an **allowlist of business permissions** while **preserving default scope authorities**.
- Use `@EnableReactiveMethodSecurity` and `@PreAuthorize` for business permissions on methods returning `Mono`/`Flux`.
- Extract the verified JWT principal using `@AuthenticationPrincipal Jwt`, matching `sub` and `tenant_id` against **server-side** data instead of trusting client-supplied IDs.
- Prevent **Broken Object Level Authorization (BOLA/IDOR)**: block users from merely changing `/documents/{id}` to read/modify another user's or tenant's record.
- Build a runnable Java 17 WebFlux application with Spring Boot, configuring issuer/JWKS/audience, GET/PATCH APIs, an illustrative reactive store, and `WebTestClient` `mockJwt()` tests.
- Distinguish 401 (unauthenticated token), 403 (missing scope/permission), and 404 (not found or intentionally hiding resource existence), along with the limits of offline mocked JWT tests.

> **Scope:** **Reactive** JWT Bearer Resource Server—not Servlet `HttpSecurity`, not OAuth2 Login, and not “adding a role claim to a JWT grants read access to every record”. Authorization must bind **operation + policy + actual resource**. Examples use test accounts/tokens/data; do not adopt as production policy without verifying tenant models, resource lifecycles, and IdP behavior.

## 1. Four Layers of Access Decisions

Suppose the API receives `GET /api/documents/D-101`:

~~~text
HTTP Authorization: Bearer <JWT>
            |
            v
1. Authentication: Resource Server verifies signature,
   issuer, audience, exp/nbf, token format.
            |
            +-- Invalid -> 401
            |
            v
2. Scope: Does the token have SCOPE_documents.read?
            |
            +-- No -> 403
            |
            v
3. Business permission: Does the token have PERM_documents:view?
            |
            +-- No -> 403
            |
            v
4. Actual data: document D-101
      document's tenant_id == verified tenant_id?
      document's owner_sub == verified sub?
            |
            +-- No -> 404 (existence-hiding policy)
            |
            v
200 OK: return field-restricted DTO
~~~

General condition:

\[
\text{ALLOW}(u,a,r) =
  \text{ValidJWT}(u)
  \land \text{ScopeAllowed}(u,a)
  \land \text{BusinessPermission}(u,a)
  \land \text{RelationshipAllowed}(u,r)
\]

Where `u` is the caller, `a` is the action, and `r` is the resource. Different checking layers should never be collapsed into one.

| Layer | Where does the data come from? | Example | Decision |
|---|---|---|---|
| JWT authentication | Signature, claims, issuer/JWKS, validator | `iss`, `aud`, `sub`, `exp` | Whether the token is trusted |
| Scope | Signed `scope` or `scp` inside the access token | `documents.read` | Which action categories the token allows |
| Business claim/permission | Claim issued by a **trusted issuer**, per app policy | `app_permissions=["documents:view"]` | Whether the role/business capability permits the action |
| Ownership/tenant | Record in repository/DB and verified principal | `owner_sub="alice"`, `tenant_id="org-a"` | Whether specific resource D-101 belongs to the caller's scope |
| Field-level policy | Specific rules for sensitive fields | `salary`/`bank_account` | Which fields of the resource may be viewed/edited |

**Ownership cannot be inferred from having `documents.read`.** That scope typically permits “attempting to access document-type resources”, not reading *every document*.

### 1.1. Signs of BOLA/IDOR Vulnerability

If both calls below return 200 solely because the token has the scope, the API is exposed to BOLA:

~~~http
GET /api/documents/D-101
Authorization: Bearer <alice-token>

GET /api/documents/D-102
Authorization: Bearer <alice-token>
~~~

Suppose D-101 belongs to Alice while D-102 belongs to Bob. **Changing the ID in the URL is untrusted input**; to protect it, the server must fetch row D-102 and check its relationship to Alice **before returning data**. This cannot be fixed by hiding UI buttons or encoding identifiers with a guessable scheme.

### 1.2. Independent AuthN and AuthZ

- **401 Unauthorized:** missing Bearer token, tampered token, expired, wrong signature/issuer/audience, or unauthenticated (depending on backend error mapping).
- **403 Forbidden:** verified token lacking required scope/permission/role per policy; insufficient privilege for the operation.
- **404 Not Found:** record does not exist, or the application **deliberately returns 404** for records not belonging to the caller to reduce existence leakage. This is a **policy decision**, not a mandatory Spring rule.
- **200 OK:** must pass **all** checks, then return a minimal representation.

Avoid creating side channels: if unauthorized resources return 403 while non-existent IDs return 404, an attacker can enumerate valid IDs. For sensitive APIs, a unified response (404) is often chosen for both branches. Still, 404 does not replace logging/auditing and real permission checks.

## 2. A JWT Is Verified Data, Not Every Claim Is a Permission

An illustrative access token—only a JSON payload, **not a validly signed JWT**:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "alice",
  "tenant_id": "org-a",
  "scope": "documents.read documents.write",
  "app_permissions": ["documents:view", "documents:edit"],
  "exp": 1893456000,
  "iat": 1893452400,
  "jti": "fixture-123"
}
~~~

Important fields:

| Claim | Meaning | Authorization notes |
|---|---|---|
| `iss` | Issuer that minted the token | **Trust only configured issuers**; with multiple issuers, user identity should be `iss + sub`. |
| `aud` | API/token recipient | Must include the audience for **documents-api**; reject access tokens issued for other services. |
| `sub` | Subject/resource owner identity | Use stable ID from issuer; do not assume email is the ownership key. |
| `scope` / `scp` | Granted token scopes | Typically mapped to `SCOPE_...` authorities. |
| `app_permissions` | Business claim **agreed between IdP/API** | No standard forces every IdP to emit a claim with this name. |
| `tenant_id` | Defined/controlled tenant claim | Must match the **row tenant**; never trust an external `X-Tenant-Id`. |
| `exp`/`nbf` | Token validity window | Expired or not-yet-valid tokens must not create Authentication. |
| `jti` | JWT ID, if present | Does not automatically enforce revocation unless a denylist/introspection exists. |

**A signed JWT does not guarantee claims reflect the latest privileges.** Roles or tenant memberships can be revoked after an access token was issued. For sensitive actions, consider short-lived access tokens, claim versioning, request-time policy/ACL/DB checks, denylists, or introspection. A valid signature does not turn an outdated `tenant_id` into “current membership”.

### 2.1. Verify the JWT Before Using Claims

The Resource Server must verify signature/JWKS, accepted algorithms, issuer, audience, timestamps (and extra validators as needed) **before** using claims for authorization. Never:

- Base64-decode a JWT payload and trust its fields without verifying the JWS.
- Allow callers to supply `scope`, `roles`, `tenant_id`, or `ownerId` in HTTP headers instead of a JWT.
- Accept JWTs from arbitrary issuers just because scope names match.
- Treat an OIDC login `id_token` as an access token for a resource API.
- Accept `alg=none` or arbitrary token-supplied algorithms/`kid` without provider/JWKS controls.
- Verify signature only while skipping `aud`; the token could be meant for another resource server.

Spring Boot supports `issuer-uri`, `jwk-set-uri`, and `audiences` to enforce baseline constraints. The hands-on lab uses all three.

## 3. Scope-Based Authorization in a Reactive Resource Server

Spring Security JWT Resource Server by default reads `scope` or `scp` claims and turns them into `GrantedAuthority` instances prefixed with **`SCOPE_`**.

Example:

~~~json
{
  "scope": "documents.read documents.write"
}
~~~

From the verified token, authentication has authorities:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

If the issuer uses:

~~~json
{
  "scp": ["documents.read", "documents.write"]
}
~~~

Spring Security also supports the `scp` convention. Exact claim interpretation depends on issuer/token type; verify during real integration. Never assume every provider emits the exact same field name/type.

### 3.1. Protecting APIs by Path and HTTP Method

A WebFlux configuration fragment:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAuthority("SCOPE_documents.read")
    .pathMatchers(HttpMethod.PATCH, "/api/documents/**")
        .hasAuthority("SCOPE_documents.write")
    .anyExchange().denyAll())
~~~

- GET requires read scope.
- PATCH requires write scope.
- DELETE is disallowed unless explicitly declared.
- **Specific** rules must precede `anyExchange().denyAll()`.
- Matching HTTP methods prevents “same endpoint where read scope accidentally allows write”.
- Even if a user holds both read and write scopes, business permissions and ownership must still be checked at subsequent layers.

`SCOPE_documents.read` is the post-mapping authority string; never write `hasRole("SCOPE_documents.read")` because `hasRole` applies the `ROLE_` prefix, not `SCOPE_`. Use `hasAuthority(...)` or reactive `hasScope(...)` authorization managers where appropriate.

### 3.2. Scopes Do Not Guarantee the Right Audience

A JWT carrying `scope=documents.read` with `aud=["billing-api"]` must be rejected **right at authentication/validation** when your API expects `aud=documents-api`. Never work around this by adding a granted authority; audience defines **who the token was issued for**, not merely a business permission label.

### 3.3. Scopes Are Granted Token Privileges, Not Universal User Rights

A confidential client using `client_credentials` may hold `scope=documents.read` yet **lack a user subject matching document owners**. The API must explicitly define service-account policies: e.g., an authorized and audited read-all service role rather than accidentally writing a branch that “skips ownership checks when no owner matches”.

## 4. Business Claims: Converting IdP Data into Controlled Authorities

Many systems require more granular permissions than OAuth2 scopes:

~~~json
{
  "app_permissions": ["documents:view", "documents:edit"],
  "tenant_id": "org-a"
}
~~~

Some providers use `roles`, `realm_access.roles`, `groups`, `permissions`, or custom claim names. No single mapper fits every IdP. A **schema contract** between issuer and Resource Server is essential.

This lesson uses the convention:

~~~text
scope "documents.read"            -> authority SCOPE_documents.read
app_permissions "documents:view"   -> authority PERM_documents:view
app_permissions "documents:edit"   -> authority PERM_documents:edit
~~~

Distinct prefixes prevent a value inside `app_permissions` from accidentally granting a scope or role meant for a different source.

### 4.1. Why Not Map Arbitrary Strings to ROLE_ADMIN?

Wrong:

~~~java
// ANTI-PATTERN, do not apply directly:
jwt.getClaimAsStringList("roles").stream()
   .map(role -> new SimpleGrantedAuthority("ROLE_" + role));
~~~

With multiple token issuers/clients/tenants or an issuer letting users edit profile claims, this can elevate untrusted roles. Even with a trusted issuer, a **global role** does not make a user an admin of *every tenant*.

Safer approach:

- Validate issuer + audience and agree on the claim schema.
- **Strictly allowlist** the permission strings the API understands.
- Keep authorities in separate namespaces (e.g., `PERM_`).
- Cross-check tenant/ownership against real data after business permission checks.
- Never map arbitrary claims to `ROLE_SUPER_ADMIN` just because the name looks similar.

### 4.2. Preserving Default Scope Mapping When Adding Business Claims

A default `JwtGrantedAuthoritiesConverter` converts `scope`/`scp` into `SCOPE_`-prefixed authorities. If a custom converter **replaces** it with only business roles, you drop scope authorities and cause `hasAuthority("SCOPE_documents.read")` rules to always return 403.

Pattern used in the demo:

~~~java
JwtGrantedAuthoritiesConverter scopeConverter =
    new JwtGrantedAuthoritiesConverter();

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setJwtGrantedAuthoritiesConverter(jwt -> {
    Collection<GrantedAuthority> authorities =
        new ArrayList<>(scopeConverter.convert(jwt));

    Object raw = jwt.getClaim("app_permissions");
    if (raw instanceof Collection<?> permissions) {
        for (Object permission : permissions) {
            if ("documents:view".equals(permission)) {
                authorities.add(
                    new SimpleGrantedAuthority("PERM_documents:view"));
            }
            if ("documents:edit".equals(permission)) {
                authorities.add(
                    new SimpleGrantedAuthority("PERM_documents:edit"));
            }
        }
    }
    return authorities;
});
~~~

This is a **code fragment** inside a config method. It keeps default scopes and adds only **two** declared permissions. If `app_permissions` is absent or the wrong type, no business permissions are granted—deny by default.

In **WebFlux**, the DSL's `jwtAuthenticationConverter(...)` expects a reactive converter. You can wrap the synchronous converter:

~~~java
new ReactiveJwtAuthenticationConverterAdapter(converter)
~~~

Never bring Servlet-only filters directly into a reactive security chain. Spring Security provides this adapter to convert the result into `Mono<AbstractAuthenticationToken>`.

### 4.3. Roles and Business Rules Still Need Additional Checks

`PERM_documents:edit` only says an account may perform an **edit-type operation**; it does not prove resource D-102 belongs to that account. In multi-org apps, a user may hold edit permission in tenant A but not in tenant B. **Tenant/record ownership** checks are mandatory in the data/service layer.

When business claims change frequently (membership removed, role revoked, account locked), unexpired access tokens may carry **stale permissions**. Systems needing immediate revocation require server-side authorization state checks or short token lifetimes rather than relying solely on JWT claims.

## 5. Checking Resource Ownership and Tenant

Suppose we have this data table:

| document_id | tenant_id | owner_sub | title |
|---|---|---|---|
| `D-101` | `org-a` | `alice` | Alice's document |
| `D-102` | `org-a` | `bob` | Bob's document |
| `D-201` | `org-b` | `alice` | Alice's document in another tenant |

Caller holds a JWT:

~~~json
{
  "sub": "alice",
  "tenant_id": "org-a",
  "scope": "documents.read",
  "app_permissions": ["documents:view"]
}
~~~

Outcomes **after the JWT is verified**:

| Request | Demo outcome | Why |
|---|---|---|
| GET D-101 | **200** | Valid scope + permission, owner Alice, tenant org-a. |
| GET D-102 | **404** | Same tenant, but owner is Bob. |
| GET D-201 | **404** | Owner Alice, but tenant org-b differs from tenant claim. |
| GET D-999 | **404** | No record exists. |
| GET D-101, missing scope | **403** | WebFlux chain denies before reading resource. |
| GET D-101, missing permission | **403** | Method security denies. |
| GET D-101, no token | **401** | Bearer authentication failed. |

**Key takeaway:** JWT `sub`/`tenant_id` are **verified inputs to the authorization decision**, whereas ownership resides in the **actual row** or server-managed ACL.

### 5.1. DB Query Pattern Should Filter Permissions Upfront

In production with R2DBC, the query pattern is:

~~~sql
SELECT id, title
FROM documents
WHERE id = :id
  AND tenant_id = :tenant_id_from_verified_jwt
  AND owner_sub = :sub_from_verified_jwt;
~~~

Parameters must be bound via the database driver; never concatenate user input into SQL. This query ensures the DB never even returns rows from another tenant/owner. In shared databases, proper indexes/composite keys and tenant data isolation are also needed.

If the app supports **document sharing / ACLs**, expand the predicate carefully:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :trusted_tenant
  AND (
        d.owner_sub = :trusted_subject
        OR EXISTS (
          SELECT 1
          FROM document_acl a
          WHERE a.document_id = d.id
            AND a.grantee_sub = :trusted_subject
            AND a.can_read = TRUE
        )
      );
~~~

This is conceptual SQL, not a complete repository implementation. With multiple issuers, ACL identities should include issuer alongside subject. For updates, use `UPDATE ... WHERE id=? AND tenant_id=? AND owner_sub=?` or a policy predicate inside the **same transaction**; checking permissions first and then updating unconditionally introduces race/TOCTOU vulnerabilities.

### 5.2. Never Trust “owner” in the Request Body

Wrong:

~~~http
PATCH /api/documents/D-102
Authorization: Bearer <alice-token>
Content-Type: application/json

{"ownerSub":"alice","tenantId":"org-a","title":"Rename"}
~~~

If the backend trusts caller-supplied `ownerSub`/`tenantId`, an attacker can claim ownership of any record. Instead, the request payload should accept only editable business fields (e.g., `title`). The server extracts `sub` and `tenant_id` from the **verified** Authentication and matches against the stored row.

### 5.3. Ownership Is Not Merely Display-Name Comparison

Do not use username/email as default identity because they can change or collide. Usually **issuer + subject** (`iss` + `sub`) serves as the long-term identifier; if the system uses internal user IDs, maintain a stable mapping from verified identity → internal user. `tenant_id` also requires a clear convention: whether the claim represents an active tenant or a list of memberships, each with its own validity/revocation lifecycle.

### 5.4. Use 403 or 404 for Resources Not Owned by the User?

There is no single universal rule:

- **403**: transparent that the resource exists but the caller lacks permission; fits some internal APIs.
- **404**: hides resource existence when the caller has no relationship to it. Useful for APIs with guessable object IDs.
- **Keep responses consistent** between “does not exist” and “not visible” when anti-enumeration policy requires it.
- Whichever status you pick, server-side auditing should log the safe reason internally without exposing owner/tenant details in error bodies.

The hands-on example chooses **404** when a document does not exist or does not belong to `sub + tenant_id`, and 403 for missing scope/permission.

## 6. Reactive Method Security: Business Claims at Method Level

Spring Security supports:

~~~java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
~~~

On Spring configuration, paired with:

~~~java
@PreAuthorize("hasAuthority('PERM_documents:view')")
public Mono<DocumentView> findDocument(...) {
    // ...
}
~~~

**WebFlux specifics:** Methods with reactive authorization should return `Mono` or `Flux` so Spring reads `Authentication` from Reactor Context. Never mechanically apply blocking method security to a service returning direct values and calling `block()`.

`@PreAuthorize` can sit on controllers or services depending on architecture. If the same business action is invoked from HTTP endpoints, scheduled jobs, and message listeners, placing policies at the **service boundary** prevents missing an entrypoint. Still, record ownership must be enforced in the repository/service holding actual data, not solely via role checks on controllers.

### 6.1. Why Use Both Path Rules and @PreAuthorize?

Example:

~~~text
SecurityWebFilterChain:
    GET /api/documents/** → SCOPE_documents.read

Method security:
    GET document → PERM_documents:view

Data/service:
    document.tenantId == jwt.tenant_id
    document.ownerSub == jwt.sub
~~~

These three conditions combine with **AND** logic. If the scope rule passes but the business claim fails, the request is denied. If scope + permission pass but the owner differs, the backend still withholds the row.

### 6.2. Is @PostAuthorize Enough to Replace Ownership Queries?

`@PostAuthorize` can inspect data after a method returns a publisher, but should not be the sole defense if the query already loaded sensitive rows, caused side effects, or fetched large result sets. For multi-tenant data, **filtering at the query/repository level** lowers leakage risk and avoids wasted work. Use `@PostAuthorize` only where appropriate and test failure paths without assuming `returnObject` is synchronous.

## 7. Java 17 Example: WebFlux Resource Server, Scope + Permission + Ownership

This example uses **Spring Boot 3.5.16**, Java 17, Spring WebFlux, and Spring Security. The app is a **JWT Resource Server**:

- Validates `iss` and `aud` via Spring Boot config, reading public keys from a JWKS URI.
- `GET /api/documents/{id}` requires `SCOPE_documents.read` and `PERM_documents:view`.
- `PATCH /api/documents/{id}` requires `SCOPE_documents.write` and `PERM_documents:edit`.
- Documents are returned/modified **only when** `sub` and `tenant_id` match the document row.
- No real database; the demo uses `ConcurrentHashMap` wrapped in reactive `Mono`. In production, replace with R2DBC queries enforcing tenant/owner in SQL.
- Tests use `mockJwt()` to check authorization **without an IdP**, plus a separate test for the scope/claim converter.

**Warning:** `mockJwt()` skips real signature/issuer/audience verification of Bearer tokens. The unit/integration tests below **do not prove** the Spring JWT decoder accepts tokens from an IdP. Real signed JWT, mock JWKS, or staging IdP tests are required before production.

### 7.1. Project Structure

~~~text
reactive-document-authz/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/DocumentAuthzApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/DocumentAuthzTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-document-authz'
~~~

`build.gradle`:

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use JDK 17+ and a compatible Gradle/Gradle Wrapper. `spring-boot-starter-oauth2-resource-server` brings JWT/JWS verification via Spring Security OAuth2 Resource Server + JOSE. **Do not** include Servlet `spring-boot-starter-web` in a reactive demo.

### 7.2. application.yml

File `src/main/resources/application.yml`:

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
            - documents-api
~~~

This is an **illustrative configuration**: issuer/JWKS must be replaced by a real IdP in integration/production environments. When both issuer URI and JWKS URI are configured, Spring Boot skips discovery at startup yet still fetches keys when processing real JWTs. It also uses `issuer-uri` to validate `iss` and `audiences` to validate `aud`.

**Never take a JWKS URI from a JWT header or arbitrary user query.** Trust only configured provider metadata. Use real HTTPS, exact issuer/audience, and an appropriate algorithm policy. Reject `alg=none` JWTs.

### 7.3. Complete Application

File `src/main/java/example/DocumentAuthzApplication.java`:

~~~java
package example;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
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
public class DocumentAuthzApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentAuthzApplication.class, args);
    }

    @Bean
    JwtAuthenticationConverter authorizationClaimsConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            // Preserve scope/scp -> SCOPE_... mapping.
            Collection<GrantedAuthority> result =
                new ArrayList<>(scopes.convert(jwt));

            // Recognize only an allowlist of business permissions.
            Object raw = jwt.getClaim("app_permissions");
            if (raw instanceof Collection<?> permissions) {
                for (Object permission : permissions) {
                    if ("documents:view".equals(permission)) {
                        result.add(new SimpleGrantedAuthority(
                            "PERM_documents:view"));
                    }
                    if ("documents:edit".equals(permission)) {
                        result.add(new SimpleGrantedAuthority(
                            "PERM_documents:edit"));
                    }
                }
            }

            return result;
        });

        return converter;
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        JwtAuthenticationConverter authorizationClaimsConverter) {

        return http
            // Valid ONLY when API uses Bearer headers and NO
            // browser cookie/session authentication.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .pathMatchers(HttpMethod.PATCH, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    new ReactiveJwtAuthenticationConverterAdapter(
                        authorizationClaimsConverter))))
            .build();
    }

    public record DocumentRecord(
        String id, String tenantId, String ownerSub, String title) {
    }

    public record DocumentView(String id, String title) {
    }

    public record RenameDocument(String title) {
    }

    @Service
    public static class DocumentService {

        // DEMO DATA: replace with an R2DBC repository in production.
        private final Map<String, DocumentRecord> documents =
            new ConcurrentHashMap<>(Map.of(
                "D-101", new DocumentRecord(
                    "D-101", "org-a", "alice", "Alice's document"),
                "D-102", new DocumentRecord(
                    "D-102", "org-a", "bob", "Bob's document"),
                "D-201", new DocumentRecord(
                    "D-201", "org-b", "alice", "Tenant B document")));

        private boolean owns(Jwt jwt, DocumentRecord document) {
            // JWT here has already been verified by the authentication filter.
            String sub = jwt.getSubject();
            String tenant = jwt.getClaimAsString("tenant_id");

            return sub != null && !sub.isBlank()
                && tenant != null && !tenant.isBlank()
                && Objects.equals(document.ownerSub(), sub)
                && Objects.equals(document.tenantId(), tenant);
        }

        private DocumentView toView(DocumentRecord document) {
            // Return only needed fields; do not leak tenant/owner.
            return new DocumentView(
                document.id(), document.title());
        }

        public Mono<DocumentView> getForOwner(
            String id, Jwt jwt) {

            return Mono.justOrEmpty(documents.get(id))
                .filter(doc -> owns(jwt, doc))
                .map(this::toView)
                .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                        HttpStatus.NOT_FOUND)));
        }

        public Mono<DocumentView> renameForOwner(
            String id, Jwt jwt, RenameDocument request) {

            return Mono.defer(() -> {
                if (request == null
                    || request.title() == null
                    || request.title().isBlank()
                    || request.title().length() > 120) {
                    return Mono.error(
                        new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "Invalid title"));
                }

                // Atomic compute ensures ownership check
                // and update share the same critical section on the demo Map.
                AtomicReference<DocumentRecord> accepted =
                    new AtomicReference<>();

                documents.computeIfPresent(id, (key, current) -> {
                    if (!owns(jwt, current)) {
                        return current;
                    }

                    DocumentRecord updated = new DocumentRecord(
                        current.id(),
                        current.tenantId(),
                        current.ownerSub(),
                        request.title());

                    accepted.set(updated);
                    return updated;
                });

                return Mono.justOrEmpty(accepted.get())
                    .map(this::toView)
                    .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                            HttpStatus.NOT_FOUND)));
            });
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

        @GetMapping("/api/documents/{id}")
        @PreAuthorize("hasAuthority('PERM_documents:view')")
        public Mono<DocumentView> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

            return service.getForOwner(id, jwt);
        }

        @PatchMapping("/api/documents/{id}")
        @PreAuthorize("hasAuthority('PERM_documents:edit')")
        public Mono<DocumentView> rename(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody Mono<RenameDocument> body) {

            return body.flatMap(request ->
                service.renameForOwner(id, jwt, request));
        }
    }
}
~~~

### 7.4. How to Read Each Protection Layer Accurately

1. **JWT authentication:** `oauth2ResourceServer(...jwt(...))` extracts the Bearer header and uses the Boot-configured decoder/JWKS and validators. Unverified JWTs never become authenticated `Jwt` principals.
2. **Scopes:** `JwtGrantedAuthoritiesConverter` keeps the `SCOPE_` prefix. GET/PATCH are protected by **method + path** in `SecurityWebFilterChain`.
3. **Business permissions:** The custom converter recognizes only `documents:view` or `documents:edit` from `app_permissions`, while keeping scope authorities. `@PreAuthorize` on controllers enforces the matching `PERM_` authority.
4. **Ownership:** `DocumentService.owns(...)` compares trusted `sub`/`tenant_id` against the **demo row**. Never read `ownerSub` from the request body.
5. **Output:** `DocumentView` exposes only `id` and `title`, withholding internal permission/tenant fields.
6. **404 policy:** If a row does not exist or does not belong to the owner/tenant, the service returns the same 404. Missing scope/permission returns 403; missing authentication returns 401.
7. **PATCH:** Title edits validate 1–120 chars; read-check-update logic runs inside `ConcurrentHashMap.computeIfPresent` to avoid per-key races in the demo. With a DB, use transactions/conditional updates and inspect affected row counts.
8. **Reactive:** APIs return `Mono` without calling `block()`/`subscribe()` inside WebFlux handlers; `@EnableReactiveMethodSecurity` runs method authorization on the Reactor Context.
9. **CSRF:** `csrf.disable()` here **is valid only for stateless Bearer-header APIs with no browser cookie/session authentication**. If you also accept session cookies, browser-cached HTTP Basic, or form login, evaluate CSRF separately rather than copying `disable()` mechanically.
10. **Demo data:** The in-memory map resets on restart and is not equivalent to multi-instance R2DBC. Never use it for production authorization state.

### 7.5. Running the Application

~~~bash
gradle bootRun
~~~

Or `./gradlew bootRun` / `gradlew.bat bootRun` if using the wrapper. Once started, check health:

~~~bash
curl -i http://localhost:8080/api/health
~~~

Expect HTTP **200** and JSON:

~~~json
{"status":"ok"}
~~~

The documents API requires a valid Bearer JWT issued by the configured issuer with audience `documents-api`. Because `idp.example.test` is an illustrative domain, **protected API calls cannot succeed with a real token until you replace issuer/JWKS URIs with a valid IdP**. Without a token:

~~~bash
curl -i http://localhost:8080/api/documents/D-101
~~~

Expect HTTP **401**; responses may include `WWW-Authenticate: Bearer`. With a real JWT to test:

~~~bash
# Illustrates passing a JWT issued by a real IdP:
curl -i \
  -H "Authorization: Bearer <VALID_ISSUED_ACCESS_TOKEN>" \
  http://localhost:8080/api/documents/D-101
~~~

Never put production access tokens in shared files, screenshots, shell history, or issue trackers. Replace the placeholder with a test token issued for the right issuer/audience/scope/permission. The `Authorization` header must carry an **access token**, not an OIDC login ID Token.

### 7.6. Testing Without an IdP Using mockJwt

Spring Security Test provides `mockJwt()` for **WebTestClient**. It places a JWT Authentication into the test `ServerWebExchange`, convenient for testing authorization decisions without minting signed JWTs.

**Very important:** `mockJwt()` can pre-populate authorities via `.authorities(...)`. It **bypasses the decoder and typically bypasses the production filter's custom JWT converter**, so a **separate test for `JwtAuthenticationConverter`** is needed to prove claim mapping. This lesson includes both.

File `src/test/java/example/DocumentAuthzTest.java`:

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class DocumentAuthzTest {

    @Autowired
    WebTestClient client;

    @Autowired
    JwtAuthenticationConverter authorizationClaimsConverter;

    private WebTestClient as(
        String subject, String tenant, String... authorities) {

        SimpleGrantedAuthority[] grants =
            new SimpleGrantedAuthority[authorities.length];

        for (int i = 0; i < authorities.length; i++) {
            grants[i] = new SimpleGrantedAuthority(authorities[i]);
        }

        return client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", subject)
                .claim("tenant_id", tenant))
            .authorities(grants));
    }

    @Test
    void noTokenReturns401() {
        client.get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void scopeIsNecessaryEvenWithBusinessPermission() {
        as("alice", "org-a", "PERM_documents:view")
            .get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void businessPermissionIsNecessaryEvenWithScope() {
        as("alice", "org-a", "SCOPE_documents.read")
            .get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void ownerWithScopeAndPermissionCanRead() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("D-101");
    }

    @Test
    void cannotReadAnotherOwnersDocument() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-102")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void cannotReadDifferentTenantsDocument() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-201")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void missingDocumentAlsoReturns404() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void patchRequiresWriteScope() {
        as("alice", "org-a", "PERM_documents:edit")
            .patch().uri("/api/documents/D-101")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "New title"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void patchRequiresEditBusinessPermission() {
        as("alice", "org-a", "SCOPE_documents.write")
            .patch().uri("/api/documents/D-101")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "New title"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void cannotEditOtherOwnersDocument() {
        as("alice", "org-a",
           "SCOPE_documents.write", "PERM_documents:edit")
            .patch().uri("/api/documents/D-102")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "Not allowed"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void ownerCanEditWhenAllChecksPass() {
        as("alice", "org-a",
           "SCOPE_documents.write", "PERM_documents:edit")
            .patch().uri("/api/documents/D-101")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "Renamed by Alice"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Renamed by Alice");
    }

    @Test
    void converterPreservesScopeAndAllowlistsPermissions() {
        Jwt jwt = Jwt.withTokenValue("not-a-signed-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("scope", "documents.read documents.write")
            .claim("app_permissions", List.of(
                "documents:view", "some-untrusted-admin"))
            .build();

        var authentication =
            authorizationClaimsConverter.convert(jwt);

        assertNotNull(authentication);
        assertTrue(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority("SCOPE_documents.read")));
        assertTrue(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority("SCOPE_documents.write")));
        assertTrue(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority("PERM_documents:view")));

        // Unknown business claim must not be elevated into a permission.
        assertFalse(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority(
                "PERM_some-untrusted-admin")));
    }
}
~~~

Run:

~~~bash
gradle test
~~~

With Gradle Wrapper use `./gradlew test` or `gradlew.bat test`. **12 tests** are expected to pass with compatible Spring Boot 3.5.x / Spring Security 6.5.x, though **execution on a real machine/CI is required to confirm**. The `mockJwt` tests check scopes, business permissions, and ownership across Spring Security + controller/service; the final test checks the converter. They do **not** test JWT signatures, `iss`, `aud`, or remote JWKS because mocking bypasses the decoder.

Note: tests modify D-101's title in the in-memory map. GET tests avoid asserting the original title to remain independent of test ordering; 403/404 authorization tests do not mutate data.

### 7.7. Additional End-to-End Checklist for Real JWTs

Before deploying to production, test against a test/staging IdP or locally signed fixtures with a trusted test JWKS:

1. Valid JWT with matching `iss`/`aud` is accepted by the decoder.
2. JWT with wrong `aud` even with the right scope **returns 401**, never reaching authorization.
3. JWT with wrong `iss`, wrong signature, expired, or future `nbf` is rejected.
4. Token using a non-allowlisted algorithm or `alg=none` is rejected.
5. Token from the right issuer with wrong-typed or missing `app_permissions` → grants no business permissions.
6. Token with valid permissions after the issuer revoked user/tenant membership → policy checks live status if business rules require immediacy.
7. Service account token lacking a user owner **cannot automatically access** every document.
8. PATCH checks row count/version/ACLs; concurrent updates cannot trigger cross-tenant races.
9. All errors return standard status codes without leaking tokens in traces/logs.
10. Verify gateway/proxy tests never trust `X-User`, `X-Tenant-Id`, or `X-Roles` headers unless protected by a trusted identity boundary.

## 8. Upgrading to an R2DBC Repository and Multi-Tenant Policy

The in-memory demo is strictly for learning. With PostgreSQL/R2DBC, enforce security close to the data:

~~~sql
-- Read: never return rows with the wrong tenant/owner.
SELECT id, title
FROM documents
WHERE id = :doc_id
  AND tenant_id = :tenant_id
  AND owner_sub = :owner_sub;

-- Write: update with the same permission predicate,
-- while guarding concurrent writes via version.
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :doc_id
  AND tenant_id = :tenant_id
  AND owner_sub = :owner_sub
  AND version = :expected_version;
~~~

Placeholders like `:doc_id` are **named parameters** of the illustrative query and must be bound from the verified context via the driver/framework. If `UPDATE` affects **0 rows**, it may mean non-existent, wrong owner/tenant, or a version conflict; response policy should distinguish only without introducing enumeration leaks.

### 8.1. When Users View Shared Documents

Pure `owner_sub == sub` ownership is insufficient for all products. It can be extended to:

~~~text
resource.tenantId == jwt.tenant_id
AND (
    resource.ownerSub == jwt.sub
    OR exists active ACL(resource.id, jwt.sub, "read")
    OR hasTrustedTenantRole(jwt.sub, tenant, "document-auditor")
)
~~~

However, the auditor role must be scoped to the **current tenant**, not a global role at the issuer. ACL/tenant membership should be verified against a DB/policy engine with proper versioning/cache invalidation; token permissions are a **necessary** condition, not automatically **sufficient**.

### 8.2. When a Token Carries Multiple Tenants

A JWT with `tenant_ids=["org-a","org-b"]` does not mean endpoints can skip tenant checks. When a client picks an active tenant via path/header, the server must:

1. Treat the request's tenant ID strictly as the **requested access target**.
2. Verify that tenant belongs to the caller's **trusted and currently active** memberships.
3. Query data with the tenant predicate.
4. Prevent users from switching tenants to view another tenant's data even with the same `documents.read`.

If memberships change frequently, verify server-side state rather than relying on long-lived tokens.

### 8.3. Multiple IdPs/Issuers

`sub="alice"` from issuer A is **not** the same entity as `sub="alice"` from issuer B. Use a composite `issuer + subject` identity or map each issuer's subject to a verified internal user ID. When supporting multi-issuer, security config needs a trusted issuers resolver and proper validators. Never let tokens from an unknown issuer supply a `tenant_id` matching an internal tenant to bypass controls.

### 8.4. Pagination and Search Must Also Enforce Permissions

Not just `GET /documents/{id}`. Every endpoint—`GET /documents?query=...`, `GET /documents/count`, `GET /documents/export`, `GET /documents/{id}/attachments`, `PATCH`, `DELETE`, batch APIs, and background jobs—must enforce the same data-scope policy.

For list queries, **filter at the DB before LIMIT/OFFSET**. Loading all documents and filtering in Java after pagination skews page counts, leaks metadata, and wastes resources. Search indexes, caches, CDNs, and event streams must enforce equivalent tenant/owner policies.

## 9. Roles of Scopes, Business Claims, Roles, and Ownership in Design

An access policy for the documents API can be stated explicitly:

~~~text
GET /documents/{id}
  require JWT trusted for documents-api
  AND SCOPE_documents.read
  AND PERM_documents:view
  AND active tenant membership
  AND (same owner OR explicit read ACL)
  AND not soft-deleted / document active

PATCH /documents/{id}
  require JWT trusted for documents-api
  AND SCOPE_documents.write
  AND PERM_documents:edit
  AND same tenant
  AND (owner OR approved editor ACL)
  AND allowed document state (not locked)
  AND optimistic lock/version matches
~~~

The “resource owner” condition sometimes generalizes to RBAC/ABAC/relationship-based access control:

| Model | Example | Things to watch |
|---|---|---|
| **RBAC** | `ROLE_DOCUMENT_EDITOR` | Must know which tenant the role applies to; avoid accidental globalization. |
| **ABAC** | Tenant org-a + finance department + internal classification | Claims/attributes must be trusted and fresh. |
| **ReBAC/ACL** | User shared via ACL row | Read permissions from live relationships; revocations must take effect. |
| **Owner-only** | `document.ownerSub == jwt.sub` | Simple, but does not support sharing/assistants/delegation if needed. |
| **Service account** | `client_credentials` token for approved batch export | Service privileges separated from users; audited and minimal scope. |

Any role/permission must have a **bounded applicability scope**. `documents:edit` might only allow editing documents within an allowed tenant and state, not blanket system-wide edits.

### 9.1. Field-Level Security and Mass Assignment

Never return raw JPA/R2DBC entities with all fields and rely on the frontend to hide sensitive ones. Use explicit DTOs and reviewed mappings. In PATCH, accept only editable fields; never bind raw JSON directly onto entities containing `ownerSub`, `tenantId`, `createdBy`, or `status=APPROVED`.

If permission to read metadata differs from reading content, split `documents.metadata.read` and `documents.content.read` per API/use case; never return confidential bodies merely because a token holds broad `documents.read`.

### 9.2. Be Careful with “roles” Claims Derived from User Profiles

Spring Security can map JWT business claims to authorities, **yet those still come from the issuer's token**. Never expose a profile endpoint where clients can update `role=admin` and have the IdP copy it straight into tokens to grant privileges. Security claims must originate from trusted identity/authorization workflows. Audit who is permitted to modify claim mappings/groups at the IdP.

### 9.3. Permission Revocation Timing

Access tokens live until `exp`. When a user changes tenants or loses permissions after issuance:

- An API trusting only old claims may still permit operations until the token expires.
- High-risk APIs can query live membership/ACLs in the DB or PDP per request.
- Manage cache TTL/invalidation, protect the policy backend against outages, and decide fail-open vs. fail-closed.
- Never overwrite `role`/`tenant` in HTTP context to keep things working until token expiry in ways that bypass validators.

## 10. Common Mistakes

**1. Checking only `SCOPE_documents.read` without checking owner.** Users with the scope can still read Bob's documents → BOLA. Row ownership/ACL predicates are required.

**2. Checking only a request-supplied owner ID.** Users can alter `ownerId` or `tenantId` in URLs/bodies. Take verified identity from Authentication and check server-side records.

**3. Trusting unverified JWT claims.** Base64 decoding is not signature verification. Use a Resource Server JWT decoder with trusted issuer/JWKS.

**4. Skipping audience validation.** Access tokens meant for another API could be misused. Configure `audiences` or a custom validator.

**5. Using `hasRole("documents.read")` instead of `hasAuthority("SCOPE_documents.read")`.** Role and scope prefixes differ, causing wrong denials or policy confusion.

**6. Custom claim converter dropping scopes.** If a converter maps only `permissions`, `SCOPE_` rules stop seeing scopes. Combine default `JwtGrantedAuthoritiesConverter` with a custom allowlist.

**7. Arbitrarily mapping all business strings to `ROLE_ADMIN`.** Unchecked claim schemas/issuers/tenants cause privilege escalation. Use an allowlist.

**8. Using tenant A's permission claims in tenant B.** Tenant permissions must be scoped, not global role names.

**9. Confusing email with `sub`.** Emails change, collide, or may be unverified; use stable subject + issuer or internal ID mappings.

**10. Assuming an unexpired JWT means privileges are still valid.** Roles/ACLs can be revoked; check fresh policy when required.

**11. Checking permissions only in controllers while repositories expose cross-tenant reads.** Other entrypoints can bypass controllers. Guard in services/repositories and test all paths.

**12. Fetching a row and emitting a response before checking the owner.** Check before emitting data; better yet, filter in SQL.

**13. Fetching 1,000 rows and filtering ownership after pagination.** Breaks page counts and leaks metadata; filter in the query before LIMIT.

**14. Hiding frontend buttons and assuming the API is secure.** Attackers call HTTP directly; the server must enforce access.

**15. Returning 403 for owner mismatch and 404 for missing IDs unintentionally.** Can allow ID enumeration; pick a unified response policy when needed.

**16. Updating via find→check→save without transactions or conditional predicates.** Causes TOCTOU races if ownership/permissions change; use conditional UPDATEs/transactions/versions.

**17. Forgetting to protect export, search, count, attachment, or batch endpoints.** BOLA often hides in secondary routes.

**18. Enabling `csrf.disable()` on apps with cookies/sessions.** Disable only on bearer-only stateless APIs vetted by a CSRF threat model; cookie auth still requires protection.

**19. Using `mockJwt()` and claiming JWT signatures were tested.** Mock tests bypass the decoder; test signed tokens/issuer/audience separately.

**20. Treating an `authorization_code` user token like a cross-tenant service account.** Separate delegated user access from `client_credentials` service policies.

**21. Logging raw `Authorization`/JWTs for debugging.** JWTs often carry PII and Bearer credentials; sanitize logs/traces.

**22. Missing negative tests.** A 200 happy path does not prove BOLA is blocked; test Bob, other tenants, and missing scopes/permissions.

**23. Not guarding claim parsers against unexpected types.** If `app_permissions` is a string/map violating schema, deny by default rather than crashing or granting access.

**24. Running blocking JDBC on the Reactor event loop.** Use R2DBC or a proper isolation bridge, never `block()` in WebFlux chains.

**25. Mixing multiple issuers while keying users solely by `sub`.** Two issuers can share the same `sub`; bind to issuer too.

## 11. Production Checklist

1. **Trusted issuer/JWKS:** Are JWTs accepted only from configured issuers and signed with trusted algorithms/keys?
2. **Audience:** Does `aud` match the resource API? Are there negative tests with another API's audience?
3. **Expiry:** Are `exp`/`nbf`/clock skew controlled? Is a revocation/denylist policy needed?
4. **Scope mapping:** Do `scope`/`scp` map cleanly to `SCOPE_` authorities without mixing up `ROLE_`?
5. **HTTP methods:** Do GET/PATCH/POST/DELETE have distinct permissions, with undeclared routes denied?
6. **Business claims:** Is the schema controlled by a trusted issuer, permissions allowlisted, and wrong-type/missing claims denied?
7. **Method security:** Does `@PreAuthorize` enforce on `Mono/Flux` without bypasses via other entrypoints?
8. **Ownership:** Are resources queried using trusted `sub` + `tenant_id`/issuer rather than client-supplied owners?
9. **Multi-tenancy:** Are tenant filters enforced across databases, indexes, caches, search, and exports?
10. **ACLs:** If sharing/transferring ownership, are permissions clearly defined and revocations effective?
11. **Data minimization:** Do DTOs withhold unnecessary owner/tenant/private fields?
12. **Write safety:** Conditional UPDATEs, optimistic locking, transactions, validation, and mass-assignment protection?
13. **Response policy:** Are 401/403/404 meaningful and free of enumeration leaks?
14. **Security tests:** Do tests cover missing token/scope/permission, wrong owner/tenant, valid owner, and positive/negative writes?
15. **Decoder tests:** Are signature, issuer, audience, expiry, and JWKS rotation tested with real/forged signed tokens?
16. **Service accounts:** Are M2M tokens restricted to explicit privileges without bypassing user ownership?
17. **Token freshness:** Could permissions be revoked mid-lifetime; are live membership/ACL lookups or short TTLs in place?
18. **HTTP security:** HTTPS/HSTS, no token logging, header/size/rate limits, and proper 401/403 handling?
19. **CSRF:** Clearly separated Bearer-only vs. browser cookie auth; no improper CSRF disabling?
20. **Reactive correctness:** No `block()` or manual `subscribe()`; R2DBC/async DB ops in the chain?
21. **Observability:** Server-side denial auditing without leaking raw JWTs/PII?
22. **Periodic review:** Update policy tables and regression tests whenever adding claims, permissions, scopes, or APIs.

## 12. Self-Check Questions

**1.** A JWT has `scope="documents.read"`. May the caller GET every document?

**Answer:** No. Scope permits an operation type; business permissions and resource-level ownership/tenant/ACLs are still required.

**2.** What does Spring Security turn `scope="documents.read"` into by default?

**Answer:** Authority `SCOPE_documents.read`, checkable via `hasAuthority("SCOPE_documents.read")`.

**3.** Why isn't `hasRole("SCOPE_documents.read")` equivalent?

**Answer:** `hasRole` normally prepends `ROLE_`, whereas OAuth scopes use the `SCOPE_` prefix.

**4.** If a token has both scope and `app_permissions`, do you still need to check the DB row?

**Answer:** Yes. A JWT cannot hold reliable live ownership for mutable resources; check rows/ACLs server-side.

**5.** What happens if a user uses Alice's token to read Bob's row in the same tenant?

**Answer:** Denied by the owner predicate; the demo returns 404 to hide resource existence.

**6.** What if the token has `tenant_id="org-a"` while the row belongs to `org-b`, even though `ownerSub` is Alice in both?

**Answer:** Denied; the same user across two tenants cannot automatically read the other tenant's data.

**7.** Why must `audiences` be configured on the Resource Server?

**Answer:** To reject access tokens issued for another resource/API even when signature and scopes look valid.

**8.** When should 401, 403, and 404 be returned?

**Answer:** 401 when unauthenticated/unverified; 403 for a verified token lacking scope/permission; 404 when the row does not exist or is not owned and policy hides existence.

**9.** Does using `mockJwt()` test decoder signature/issuer/audience checks?

**Answer:** No. `mockJwt` mostly sets up a simulated `SecurityContext`; separate signed JWT/JWKS tests are needed.

**10.** Why test the converter separately from `WebTestClient` `mockJwt` tests?

**Answer:** Because `mockJwt` authorities can bypass the Resource Server's real converter; unit-testing the converter proves scope + business claim mappings work properly.

**11.** Why not let clients send `ownerSub` in JSON PATCH?

**Answer:** Clients can tamper with it to impersonate owners; the server must use verified JWT claims and inspect the real row.

**12.** If JWT roles change while the token is unexpired, do permissions update immediately?

**Answer:** No. JWTs carry claims from issuance time; reasonable TTLs or server-side authorization state are needed when rapid revocation is required.

**13.** With multiple issuers, should users be identified by `sub` alone?

**Answer:** No. Use composite `issuer + subject` or map to internal user IDs because `sub` is only unique within an issuer.

**14.** If HTTP GET is protected by a scope while DELETE on the same path has no rule, what should happen?

**Answer:** Deny DELETE via fallback; if adding a delete use case, declare its own scope/permission and enforce ownership/ACL checks.

## Official References

- Spring Security — Reactive Resource Server JWT, `scope` → `SCOPE_` claims, converters, signature/issuer validation: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Method Security, `@EnableReactiveMethodSecurity` and `@PreAuthorize`: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security — Reactive OAuth2 Resource Server API: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/index.html
- Spring Security — Reactive OAuth2 Testing with `mockJwt()`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot 3.5 — Resource Server properties `issuer-uri`, `jwk-set-uri`, `audiences`: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- `JwtGrantedAuthoritiesConverter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- `ReactiveJwtAuthenticationConverterAdapter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html
- OWASP API Security — Broken Object Level Authorization (API1:2023): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
