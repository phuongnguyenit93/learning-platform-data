# Resolving Tenants from Trusted Sources in Spring Security

## 1. The problem: a valid tenant ID is not necessarily an authorized tenant

In a multi-tenant SaaS application, `tenantId` commonly appears in URLs, subdomains, HTTP headers, JWT claims, sessions, message queues, and database columns. A common mistake is seeing `X-Tenant-Id: beta` or the path `/tenants/beta/documents` and treating `beta` as the **authenticated** current tenant.

Headers and paths can both be freely chosen by the caller. They are useful for indicating **which tenant the caller wants to operate on**, but they are **not proof** that the caller has access to that tenant.

A proper request must separate three questions:

1. **Who is the caller?** An identity authenticated via Spring Security (verified JWT, authenticated session, service identity/mTLS, etc.).
2. **Which tenants is the caller allowed to access?** Based on server-side membership, grants, or policies; token information is used only within the issuer's trust contract.
3. **Which tenant does this request select?** URL/header/subdomain is only the *requested tenant*. You must cross-check that selection against the permitted tenant set, then bind subsequent queries and actions to the resolved tenant.

Example:

```text
Verified JWT:
  sub = alice
  tenants = ["alpha", "beta"]

Current Membership DB:
  alice -> tenant alpha (ACTIVE)
  alice -> tenant beta (REVOKED)

Request:
  GET /tenants/beta/documents

=> DENY. A validly signed JWT does not mean the beta tenant membership is still active.
```

The outcome must never be “fall back to default tenant alpha” or “if membership is missing, drop the tenant filter.” **Fail closed** means blocking the operation when authorization info is missing or conflicting, rather than issuing an unrestricted query.

### What you will be able to do after this lesson

- Distinguish trusted identity sources from untrusted tenant selection inputs.
- Verify JWT issuer/audience/signature/timestamps properly before using claims.
- Design a `TenantResolver`/`TenantAccessPolicy` that never accepts client-asserted tenant authorization.
- Handle single-tenant users, multi-tenant users, tenant switching, and machine accounts.
- Propagate the verified tenant into repositories, transactions, DB/RLS, caches, jobs, and auditing.
- Write tests against header/path/JWT spoofing, stale memberships, confused deputy, and cross-tenant data leaks.
- Apply the standalone Java 17 example and the Spring Security Resource Server integration pattern.

## 2. Classification table of tenant sources

| Source | User-controllable? | Trust level | Recommended usage |
| --- | --- | --- | --- |
| `/tenants/{id}/...` | Yes | **Untrusted selector** | Selects requested tenant; must be authorized |
| Query `?tenantId=...` | Yes | **Untrusted selector** | Only for features with a tenant selector |
| `X-Tenant-Id` from the internet | Yes | **Untrusted selector** | Never use as proof of authorization |
| Subdomain `alpha.example.com` | User chooses host | **Untrusted selector** | Map hostname → authorized tenant; guard against host header injection |
| Browser-sent cookie | Browser can send/modify | Depends on auth and signing | Do not treat a tenant-named cookie as sufficient authorization |
| Server-side session principal | Via authentication | Trusted identity source **if session is secure** | Identify subject, then check membership |
| `tenant`/`tenants` claim in a validated JWT | Asserted by a trusted issuer | **Conditional** | Constrained by token contract, expiration, audience, and membership |
| Base64-decoded-only JWT payload | Can be forged | **Untrusted** | Never use for authorization |
| Membership/ACL from server repository | System-managed | Policy source | Verify active membership and scope |
| HTTP header injected by trusted gateway | Trusted only if gateway strips/rewrites and transport is protected | Conditional | Identity propagation with clear trust boundary; still authorize |
| Message metadata/job payload | Job sender can set it | Depends on queue/producer | Re-auth/re-authorize or use verified capability |
| `ThreadLocal` tenant | Any code can set it | **Not proof** | Only a carrier for an already-verified result; must clean up |
| Tenant ID from database record | Authoritative source for resource | Resource data | Match against caller's authorized tenant before reading/writing |

Having a **trusted source** does not mean a value automatically carries **full authorization**. For instance, a trusted issuer may sign a token stating the caller belonged to tenant alpha at issuance time, while an administrator revoked access 5 minutes ago. Policy must specify whether token claims serve as a membership snapshot until expiration or require live membership lookup.

## 3. Terminology: subject, issuer, selected tenant, and authorized tenant

Definitions:

- **Subject**: Stable caller ID within an issuer, typically taken from `sub` of a verified JWT. The same `sub` may appear across two different issuers, so multi-issuer systems must distinguish by the `(iss, sub)` pair or a normalized internal identity.
- **Issuer (iss)**: Token issuing source. It must belong to an **allowlist** and be verified per security configuration.
- **Audience (aud)**: Application/API for which the token was issued; a token meant for another API must not be accepted as a valid access token for the current API.
- **Tenant claim**: Tenant information inside a token; must follow a schema/issuer contract rather than arbitrary string inference.
- **Membership**: Relationship caller ↔ tenant, including ACTIVE/REVOKED state, roles, validity period, and project scope when needed.
- **Requested tenant**: Tenant proposed by the route, subdomain, or header for the current request.
- **Resolved tenant/authorized tenant**: Tenant approved by the resolver after authenticating the caller and evaluating policy.
- **Resource tenant**: Tenant to which a record/task/document actually belongs in server data.

For a single-tenant user, the system may auto-select that tenant if the API contract permits. For a multi-tenant user, require explicit selection (or a re-verified session-selected tenant) and avoid nondeterministic defaults like “pick the first element of a Set.”

### Two distinct policies to specify explicitly

**Tenant claim as an authorization ceiling:** token says `alpha`, DB says `alpha,beta`. The caller can only enter alpha until receiving a token containing beta (unless another contract is designed).

**Tenant claim as preferred tenant only:** token says alpha is default, while DB permits alpha,beta. The caller may select beta after membership verification. These two contracts differ; do not mix them inside one resolver. This article's runnable example chooses the **intersection of token tenants and DB memberships** to illustrate a strict policy.

## 4. Secure tenant resolution flow

```text
HTTP request / message
        |
        v
Security authentication
  - verify signature/session/mTLS
  - JWT: issuer, audience, timestamps, token type
        |
        v
Authenticated principal/subject
        |
        v
Resolve server-side membership / policy
        |
        v
Requested tenant from path/header/subdomain
        |
        v
Authorize requested tenant against memberships + token scope
        |
        +--- DENY ---> AccessDeniedException / 403
        |
        v
Immutable AuthorizedTenantScope
  - canonical tenant ID
  - canonical subject ID
  - permissions and policy version when needed
        |
        v
Repository/DB query/transaction + tenant predicate
        |
        v
Response/caches/jobs/audit always carry the right tenant scope
```

Important: **authenticate first, resolve tenant second, enforce the authorized tenant at every layer**. If you must inspect a tenant *before* authentication to choose an issuer/JWK, treat that value strictly as a **routing hint** to select a verifier **from an allowlist**—never as data access authorization.

## 5. What does a trusted JWT actually mean?

You cannot trust `JWT.decode(token).getClaim("tenant")` if you only base64-decode the payload. A user can tamper with a JWT payload themselves. Minimum requirements for a JWT-accepting API:

1. **Signature** verified with a trusted key/algorithm fetched from a trusted issuer/JWK set. Reject disallowed algorithms, unsigned tokens, and key-confusion attacks.
2. **`iss`** matches a configured/allowlisted issuer.
3. **`aud`** includes the current resource server's audience; this blocks tokens intended for other apps.
4. **`exp`** has not expired and **`nbf`** is valid; clock skew is adjusted only within controlled bounds.
5. **Token purpose/type** is valid: an access token for this API, rather than substituting an ID token as an API bearer token.
6. **`sub`** is present, non-blank, and mapped to a canonical identity in the issuer's context.
7. **Tenant claim** matches the expected type, format, and agreed schema name; never treat an arbitrary claim as admin privilege.
8. **Revocation/validity contract** is explicit: short-lived tokens, introspection, or membership lookup when near-instant revocation is needed.

Spring Security Resource Server verifies JWTs via `oauth2ResourceServer().jwt()` and `JwtDecoder`. Spring Boot configuration example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/company
          audiences: api://documents
```

In Spring Boot releases supporting the `audiences` property, this requires the `aud` claim to contain the matching audience. `issuer-uri` configures JWK discovery and issuer validation alongside token timestamp checks. Your application still must validate custom tenant claims and memberships; Spring does not automatically understand your tenant business rules.

Example security filter chain for a Bearer-token API:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
        );
        http.oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
```

Required imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

This is **integration configuration code** requiring `spring-boot-starter-oauth2-resource-server` and `spring-security-oauth2-jose` (pulled in by the starter depending on setup), a real issuer, and an appropriate trust store. For apps using cookies/sessions or mutating requests, evaluate **CSRF and session policies**; never disable CSRF merely because an example is a REST API.

### Why is audience required?

Suppose an IdP issues a JWT for an analytics app under the same issuer and subject. If the documents API checks `iss` but omits `aud`, an attacker can attempt to use the analytics token against the documents API. Audience forms the boundary between resource servers.

### Tenant claims are authorization state, not immutable identity data

Users can switch teams, get locked out of a tenant, be granted a new tenant, or hold temporary access. If your system reads `tenants` from a JWT, define token lifetime, refresh behavior, live membership checks, and how revoked permissions are handled. Signed tokens **do not automatically update** when the DB changes.

## 6. Never directly trust `X-Tenant-Id`, path, or subdomain

### Client-sent header

```http
GET /api/documents HTTP/1.1
Authorization: Bearer <access-token>
X-Tenant-Id: beta
```

The header says “please serve tenant beta.” The right decision logic is:

```text
authenticatedUser = verifyAccessToken()
requestedTenant = request.headers["X-Tenant-Id"]
authorizedTenants = membershipService.getActiveTenants(authenticatedUser)

if requestedTenant NOT IN authorizedTenants:
    DENY
else:
    setAuthorizedScope(requestedTenant)
```

This is pseudocode, not a built-in Spring API. Do not grant access simply because the header appears “well-formed” or “set by the frontend.”

### Tenant in the URL

`/tenants/{tenantId}/documents` is explicit and clean for REST routing, yet the path variable is still client-chosen. Before calling the service, authorize that tenant. When a resource ID appears in the path, also verify that **the resource belongs to the authorized tenant**:

```sql
SELECT id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :authorized_tenant;
```

A request to `/tenants/alpha/documents/42` must not read document 42 belonging to beta, even if the caller has access to alpha. Checking the URL tenant alone is insufficient: the record's tenant is authoritative.

### Subdomain and Host

`alpha.example.com` can route to tenant alpha. However:

- A Host header from the internet is not proof of authorization.
- Reverse proxies must restrict valid hostnames and trusted forwarded headers.
- Wildcard domains, custom domains, and IDN/punycode require server-side mapping to canonical tenants.
- Domains can change ownership or expire; verify the mapping's status.
- A hostname-derived tenant must still be checked against principal/membership on non-public endpoints.
- Never concatenate `Host` directly into a schema/table name or JDBC connection string.

### Proxy-injected headers

An internal header can be trusted **only when** every request passes through an authenticated gateway, the gateway strips all client headers of the same name before setting them, the gateway → service transport is protected (mTLS/network ACL), the backend cannot be reached directly from the internet, and the service validates the contract. If any condition fails, an attacker can spoof the header.

Even a gateway-signed or gateway-injected header does not necessarily replace verifying the caller's membership in the selected tenant.

## 7. Server-side membership verification

Model table:

```sql
CREATE TABLE tenant_membership (
    subject_id VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    PRIMARY KEY (subject_id, tenant_id)
);
```

Querying active access:

```sql
SELECT tenant_id
FROM tenant_membership
WHERE subject_id = :authenticated_subject
  AND state = 'ACTIVE'
  AND revoked_at IS NULL;
```

This is an **illustrative** SQL schema. Production may need `issuer_id` in the primary key, an internal identity ID, membership roles, validity windows, organization info, and permission versions.

Status must be checked: an existing membership record marked `SUSPENDED`/`REVOKED` does not grant access. Never take a tenant from a request body such as:

```json
{"subjectId":"alice","tenantId":"beta"}
```

and use the client-supplied `subjectId` to query membership. The subject must come from the authenticated principal; if an admin is acting “on behalf of someone else,” that requires a separate audited delegation workflow.

### Multiple tenants in token and DB

| Token claims | Membership DB | Requested | Outcome using intersection |
| --- | --- | --- | --- |
| [alpha] | [alpha] | alpha | ALLOW |
| [alpha] | [alpha,beta] | beta | DENY, token does not grant beta |
| [alpha,beta] | [alpha] | beta | DENY, beta membership is not ACTIVE |
| [alpha,beta] | [alpha,beta] | beta | ALLOW |
| [alpha,beta] | [alpha,beta] | none | DENY if policy requires explicit selection |
| [alpha] | [] | alpha | DENY |
| Missing `tenants` | [alpha] | alpha | DENY if policy requires tenants claim |
| [alpha] | [alpha] | gamma | DENY |
| [alpha] | [alpha] | malformed tenant string | DENY |

This is a **strict illustrative policy**, not a universal Spring default. If an enterprise treats the membership DB as the sole source of truth and uses tokens purely to authenticate the subject, the resolver can omit intersecting with token tenants; however, that choice must be explicit, tested, and never implicitly assumed.

## 8. Designing the `TenantResolver` API

The goal is to prevent every controller from hand-rolling:

```java
String tenant = request.getHeader("X-Tenant-Id");
repository.findAllByTenantId(tenant);
```

Replace that with a central component:

```text
TenantResolver.resolve(
    verifiedAuthentication,
    requestedTenantHint
) -> AuthorizedTenantScope
```

An `AuthorizedTenantScope` should be immutable, minimally:

```java
public record AuthorizedTenantScope(
        String subjectId,
        String tenantId) {
}
```

If roles/permissions are needed, attach only verified values. Do not let controllers instantiate `new AuthorizedTenantScope("alice", "beta")` from raw input and treat it as proof of authorization: restrict construction (package/module boundary, factory) or design services to accept the principal and resolve internally.

### Resolver preconditions

1. Authentication is non-null and authenticated.
2. Not an anonymous identity.
3. Subject is valid, stable, and normalized within the issuer context.
4. Caller holds authority for the intended operation (e.g., READ scope).
5. Token claims are read from `JwtAuthenticationToken` **after decoder validation**, never by decoding a raw bearer string.
6. Allowed tenants are fetched from server membership and policy.
7. Requested tenant must be a canonical ID inside allowed tenants.
8. If no tenant is requested and allowed has exactly one tenant, it may be selected **per API contract**.
9. If multiple tenants are allowed, require an explicit choice or a re-verified session-selected tenant.
10. Only after resolution should you query data, enqueue jobs, or pass the tenant downstream.

Use a custom exception/`AccessDeniedException` for denials; authentication errors map to 401 and authorization errors map to 403 per the filter chain and exception handling configuration. Do not return an empty list to mask an authorization failure and leave clients unaware they lack access.

## 9. Runnable Java 17: token-scoped tenants ∩ server memberships

The program below is **complete with zero dependencies outside JDK 17**. It simulates the step *after authentication has been verified*. `AuthenticatedCaller` represents a trusted principal produced by the authentication layer, not an object the frontend is allowed to submit. Its purpose is to make tenant selection, membership, and fail-closed behavior crystal clear.

File `TenantResolutionLab.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public final class TenantResolutionLab {

    record AuthenticatedCaller(
            String subject,
            Set<String> tokenTenants,
            Set<String> authorities) {}

    record AuthorizedTenantScope(
            String subject,
            String tenant) {}

    record Document(long id, String tenant) {}

    static final Map<String, Set<String>> ACTIVE_MEMBERSHIPS = Map.of(
            "alice", Set.of("alpha"),
            "bob", Set.of("alpha", "beta"),
            "carol", Set.of("alpha")
    );

    static final List<Document> DOCUMENTS = List.of(
            new Document(11L, "alpha"),
            new Document(12L, "alpha"),
            new Document(21L, "beta"),
            new Document(22L, "beta"),
            new Document(31L, "gamma")
    );

    private static AuthorizedTenantScope resolve(
            AuthenticatedCaller caller, String requestedTenant) {

        if (caller == null || caller.subject() == null
                || caller.subject().isBlank()
                || caller.tokenTenants() == null
                || caller.authorities() == null
                || !caller.authorities().contains("DOC_READ")) {
            throw new SecurityException("Denied");
        }

        Set<String> membership = ACTIVE_MEMBERSHIPS.getOrDefault(
                caller.subject(), Set.of());

        Set<String> allowed = caller.tokenTenants().stream()
                .filter(membership::contains)
                .collect(Collectors.toCollection(TreeSet::new));

        if (requestedTenant != null) {
            if (!requestedTenant.matches("[a-z][a-z0-9-]{0,31}")
                    || !allowed.contains(requestedTenant)) {
                throw new SecurityException("Denied");
            }
            return new AuthorizedTenantScope(
                    caller.subject(), requestedTenant);
        }

        if (allowed.size() != 1) {
            throw new SecurityException("Explicit tenant required");
        }

        return new AuthorizedTenantScope(
                caller.subject(), allowed.iterator().next());
    }

    private static List<Long> visibleIds(AuthorizedTenantScope scope) {
        return DOCUMENTS.stream()
                .filter(doc -> doc.tenant().equals(scope.tenant()))
                .sorted(Comparator.comparingLong(Document::id))
                .map(Document::id)
                .toList();
    }

    private static void attempt(
            String label, AuthenticatedCaller caller, String tenant) {
        try {
            AuthorizedTenantScope scope = resolve(caller, tenant);
            System.out.println(label + ": tenant=" + scope.tenant()
                    + " ids=" + visibleIds(scope));
        } catch (SecurityException denied) {
            System.out.println(label + ": DENIED");
        }
    }

    public static void main(String[] args) {
        AuthenticatedCaller alice = new AuthenticatedCaller(
                "alice",
                Set.of("alpha", "beta"),
                Set.of("DOC_READ"));

        AuthenticatedCaller bob = new AuthenticatedCaller(
                "bob",
                Set.of("alpha", "beta"),
                Set.of("DOC_READ"));

        AuthenticatedCaller carol = new AuthenticatedCaller(
                "carol",
                Set.of("alpha"),
                Set.of());

        attempt("alice alpha", alice, "alpha");
        attempt("alice beta", alice, "beta");
        attempt("alice implicit", alice, null);
        attempt("bob beta", bob, "beta");
        attempt("bob no selection", bob, null);
        attempt("carol no authority", carol, "alpha");
        attempt("no authentication", null, "alpha");
        attempt("malformed selection", alice, "Alpha");
        attempt("attempt tenant gamma", alice, "gamma");
    }
}
```

Run:

```bash
javac TenantResolutionLab.java
java TenantResolutionLab
```

Exact stdout from the code:

```text
alice alpha: tenant=alpha ids=[11, 12]
alice beta: DENIED
alice implicit: tenant=alpha ids=[11, 12]
bob beta: tenant=beta ids=[21, 22]
bob no selection: DENIED
carol no authority: DENIED
no authentication: DENIED
malformed selection: DENIED
attempt tenant gamma: DENIED
```

Explanation:

- Alice's token claims alpha,beta, but her current membership is only alpha, so beta is denied.
- Even when Alice omits a tenant selection, she resolves to alpha because the intersection leaves **only one** tenant.
- Bob has both alpha and beta; when selecting beta, only IDs 21,22 are visible. Omitting a selection is denied due to ambiguity.
- Carol holds alpha membership but lacks `DOC_READ`, so she cannot list documents.
- Header/path `Alpha` is denied because canonical IDs in this demo are lowercase; never silently lowercase untrusted input and allow it through.
- Tenant gamma is denied even though a document exists there.
- The program assumes `AuthenticatedCaller` is created only after authentication; **it does not verify JWT signatures**, connect to a database, or implement Spring Security HTTP handling. The Spring integration follows next.

### Why not use `Set.iterator().next()` when two tenants exist?

A `Set` does not represent deliberate user choice, and iteration order can change. Auto-picking “the first tenant” easily causes writes or copies to target an unintended tenant. Auto-select only when **exactly one** valid tenant exists and the API explicitly adopts that contract.

### Membership caching

If `ACTIVE_MEMBERSHIPS` comes from a database/cache, define a TTL/invalidation policy. Suppose an admin revokes Alice from beta: an older JWT may still contain beta, but the resolver reading live membership or an updated cache will deny it. If the membership cache is stale, there is a revocation lag window that must be measured and accepted under your threat model.

## 10. Integrating Spring Security Resource Server with the resolver

This section is an **integration pattern for a Spring Boot application**, not a standalone complete Maven project. It assumes a JWT decoder is already configured/validated by Spring Security, alongside a membership table and a `TenantMembershipRepository` reading trusted data.

### 10.1. Membership lookup interface

```java
public interface TenantMembershipRepository {
    Set<String> findActiveTenantIdsBySubject(String subjectId);
}
```

This is a business interface requiring a real JDBC/JPA implementation. For multi-issuer setups, replace the plain subject string with a canonical principal ID or `(issuer, subject)` pair to avoid collisions. The repository must never take the subject from request input instead of `Authentication`.

### 10.2. TenantScopeResolver reading verified JwtAuthenticationToken

```java
@Component
public class TenantScopeResolver {

    private final TenantMembershipRepository memberships;

    public TenantScopeResolver(TenantMembershipRepository memberships) {
        this.memberships = memberships;
    }

    public AuthorizedTenantScope require(
            Authentication authentication,
            String requestedTenant) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !jwtAuth.isAuthenticated()) {
            throw new AccessDeniedException("JWT authentication required");
        }

        Jwt jwt = jwtAuth.getToken(); // JWT has already passed through the Resource Server's JwtDecoder.
        String subject = jwt.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Missing subject");
        }

        if (jwtAuth.getAuthorities().stream()
                .noneMatch(a -> "SCOPE_documents.read"
                        .equals(a.getAuthority()))) {
            throw new AccessDeniedException("Document read scope required");
        }

        List<String> tenantsClaim = jwt.getClaimAsStringList("tenants");
        if (tenantsClaim == null || tenantsClaim.isEmpty()) {
            throw new AccessDeniedException("Missing tenant claim");
        }

        Set<String> activeMemberships =
                memberships.findActiveTenantIdsBySubject(subject);

        if (activeMemberships == null) {
            throw new AccessDeniedException("Tenant membership unavailable");
        }

        Set<String> allowed = tenantsClaim.stream()
                .filter(activeMemberships::contains)
                .collect(Collectors.toUnmodifiableSet());

        final String tenant;
        if (requestedTenant == null) {
            if (allowed.size() != 1) {
                throw new AccessDeniedException("Select a tenant");
            }
            tenant = allowed.iterator().next();
        } else {
            if (!requestedTenant.matches("[a-z][a-z0-9-]{0,31}")
                    || !allowed.contains(requestedTenant)) {
                throw new AccessDeniedException("Tenant access denied");
            }
            tenant = requestedTenant;
        }

        return new AuthorizedTenantScope(subject, tenant);
    }
}

public record AuthorizedTenantScope(String subjectId, String tenantId) {
}
```

Imports:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
```

Key conditions:

- The resolver **only accepts `JwtAuthenticationToken` from security infrastructure**. Never let a client supply or construct a Java `Jwt` instance passed into the resolver as if it were authenticated.
- Resource server configuration must verify issuer, audience, signature, and token expiration. `JwtAuthenticationToken` itself is just a Java type; tests using mocked tokens do not prove real tokens are verified.
- `getClaimAsStringList("tenants")` requires the issuer contract to provide a list of strings. If the claim has another type, is missing, or contains invalid IDs, reject it rather than coercing arbitrarily. You can also validate each element against your tenant-ID policy.
- Spring by default maps `scope`/`scp` to authorities prefixed with `SCOPE_`. If your project uses a custom converter, keep authority names aligned across the resolver and `@PreAuthorize`.
- Membership `Set`s must not be cached indefinitely; revocation must be managed.
- Claim data in this example is **intersected** with memberships. If your policy differs, update implementation, documentation, and tests together rather than simply deleting one check line.

### 10.3. Controller does not decide the tenant itself

```java
@RestController
@RequestMapping("/tenants/{tenantId}/documents")
class DocumentController {

    private final DocumentQueryService service;

    DocumentController(DocumentQueryService service) {
        this.service = service;
    }

    @GetMapping
    List<DocumentSummary> list(
            @PathVariable String tenantId,
            Authentication authentication) {
        return service.listForTenant(authentication, tenantId);
    }
}
```

`tenantId` in the path remains a **selector** and must never be forwarded straight to an unscoped repository. The controller delegates to the service for verification. `DocumentSummary` is an application-defined DTO; maintain property-level authorization when selecting fields.

### 10.4. Service resolves tenant before querying

```java
@Service
class DocumentQueryService {

    private final TenantScopeResolver resolver;
    private final DocumentRepository repository;

    DocumentQueryService(
            TenantScopeResolver resolver,
            DocumentRepository repository) {
        this.resolver = resolver;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    @Transactional(readOnly = true)
    public List<DocumentSummary> listForTenant(
            Authentication authentication, String requestedTenant) {

        AuthorizedTenantScope scope =
                resolver.require(authentication, requestedTenant);

        return repository.findVisibleSummaries(
                scope.tenantId(), scope.subjectId());
    }
}
```

This is an **integration snippet**; `DocumentRepository.findVisibleSummaries` must implement a query with a tenant predicate plus owner/share/ACL rules. `@EnableMethodSecurity` must be enabled and the service invoked through a Spring-managed proxy for `@PreAuthorize` to take effect. The resolver also checks the authority so bypassing advice will not silently grant access, though that should not replace proper method-security design.

If the principal is a service account authorized for a specific tenant, define a dedicated policy for service identities; do not spoof a user `JwtAuthenticationToken` by copying tokens or assigning an arbitrary subject.

## 11. The verified tenant must reach the data layer

Even after `resolver.require` approves a tenant, cross-tenant bugs can still happen if a repository calls:

```java
repository.findById(documentId);
```

without matching the resource's tenant. Do not assume that because the caller arrived on `/tenants/alpha`, the document ID belongs to alpha.

A properly scoped read query:

```sql
SELECT id, title, status
FROM documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
```

Search and count:

```sql
SELECT id, title
FROM documents
WHERE tenant_id = :authorized_tenant
  AND (owner_id = :subject_id OR visibility = 'TEAM')
ORDER BY id
LIMIT :limit OFFSET :offset;
```

```sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = :authorized_tenant
  AND (owner_id = :subject_id OR visibility = 'TEAM');
```

The same tenant scope and business filters must apply to `Page.content`, `totalElements`, `count`, exports, facets, and statistics. Never filter after pagination, as that can leak counts/metadata and distort results.

### Tenant-scoped update queries

```sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :authorized_tenant
  AND owner_id = :authenticated_subject;
```

The application checks affected rows: only 1 row means success; 0 rows must never be treated as success. If business logic also tracks state/version, add optimistic locking, transactions, or appropriate conditional predicates.

**Rule:** `tenant_id` in `WHERE` comes from **AuthorizedTenantScope**, never directly from query/header/path. Object-level policies within the tenant are still required when users must not see every record in that tenant.

### Joins

All tenant-scoped relationships must be joined consistently:

```sql
SELECT d.id, a.name
FROM documents d
JOIN attachments a
  ON a.document_id = d.id
 AND a.tenant_id = d.tenant_id
WHERE d.id = :id
  AND d.tenant_id = :authorized_tenant;
```

Omitting the tenant condition in a join can attach another tenant's data if local IDs collide. Use composite foreign keys/indexes aligned with your database design.

## 12. Three multi-tenant storage models and trust boundaries

### Shared schema, tenant_id per row

All tenants share tables; tenant predicates must be present on **every read/write/aggregate path**. Pros: simple operations. Risk: one query missing `WHERE tenant_id` can leak data.

### Schema per tenant

Each tenant has its own schema. The tenant resolver must never take an arbitrary schema name from the request. Select schemas only from an allowlisted registry mapped to the authorized tenant. Never concatenate `SET search_path = ` + client input. Pooled connections can retain schema/connection state: reset after every transaction and test for cross-request leakage.

### Database per tenant

Each tenant uses a separate DataSource/database. The `authorizedTenantId → approved datasource` registry must be controlled and audited. Never turn a tenant header into a JDBC URL/host to connect to an arbitrary database (risking SSRF and wrong-data access). Pooling, credential rotation, migrations, and privileged operational tooling must be strictly scoped.

All three models still require identifying the caller, verifying membership, enforcing resource permissions, and propagating the tenant to jobs/caches. Having a separate database does not make a client header trustworthy.

## 13. Database Row-Level Security (RLS) helps, but does not replace authentication

With PostgreSQL RLS, you can add a defense-in-depth layer:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy ON documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

This is a **PostgreSQL integration snippet**, not a complete setup. The application must set `app.tenant_id` to the authorized tenant **within the exact transaction/connection**, ensuring cleanup when the connection returns to the pool. If the setting is missing, design the policy to fail closed; avoid DB roles that bypass RLS or unintended table-owner bypasses. Review `BYPASSRLS`/`FORCE ROW LEVEL SECURITY` and `SET` privileges against your threat model.

**Key limitation:** a connection user may be able to set custom GUCs. RLS using `current_setting` is only as secure as the app/DB role boundary setting it. If clients can run arbitrary SQL under the same role, they can switch the context. Never treat RLS as standalone tenant authentication.

### Transactions and connection pooling

With connection pooling and thread reuse, setting a tenant context without cleanup can cause subsequent requests to reuse the prior tenant. Prefer transaction-local settings, reset per transaction, and run integration tests with pool size 1 to surface leaks easily. Using global session settings without resets poses a severe risk.

## 14. SecurityContextHolder is not a “anyone can set the tenant” bucket

`SecurityContextHolder` in servlet apps typically stores `Authentication` per thread; Spring Security handles protecting and clearing context around each request. Some apps build their own:

```java
private static final ThreadLocal<String> CURRENT_TENANT =
        new ThreadLocal<>();
```

`ThreadLocal` only **carries state**; it cannot verify whether a tenant is valid. Any code with access can call `set("beta")`. If middleware puts `X-Tenant-Id` straight into a ThreadLocal, every repository behind it can execute against the wrong tenant.

Preferred order:

1. Pass an immutable `AuthorizedTenantScope` explicitly as a service/repository parameter.
2. If a persistence framework requires an implicit tenant context, populate it solely from a verified resolver.
3. Keep the scope narrow and clean up in `try/finally`.
4. Never store scope in a singleton field or mutable global static variable.
5. Never copy a raw tenant selector into the security context as an authority.

Example wrapper limiting thread state leaks (integration snippet):

```java
final class TenantContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    static String require() {
        String tenant = CURRENT.get();
        if (tenant == null) {
            throw new IllegalStateException("Missing authorized tenant");
        }
        return tenant;
    }

    static void runWith(AuthorizedTenantScope scope, Runnable job) {
        if (CURRENT.get() != null) {
            throw new IllegalStateException("Unexpected nested tenant scope");
        }
        CURRENT.set(scope.tenantId());
        try {
            job.run();
        } finally {
            CURRENT.remove();
        }
    }
}
```

Only call `runWith` with a scope produced by a trusted resolver. For nested flows or reactive programming, use appropriate context propagation instead of applying ThreadLocal mechanically. The example intentionally rejects nested scopes to avoid silently overwriting a tenant, though not every app must forbid nested calls.

## 15. Async, message queues, and scheduled jobs

### @Async and Executor

Spring Security notes that `SecurityContext` is normally thread-bound; when switching to a new thread, context is **not automatically present**. `DelegatingSecurityContextExecutor` or related wrappers help propagate authentication where appropriate. However, **custom application tenant context** is not automatically propagated by that framework mechanism.

Do not assume:

```text
request thread: tenant=alpha
    |
    +-- @Async worker thread: tenant is probably still alpha
```

Good design: pass the resolved `tenantId` alongside an immutable job command and an explicit identity/authorization snapshot contract, then **re-authorize at job execution time** if permissions can change. For jobs queued for hours, an enqueue-time snapshot is not guaranteed to remain valid.

### Event/message headers

A message containing `tenantId` is not proof of authorization. Brokers/topics may be shared, and consumers may receive messages from multiple producers. Authenticate producer/service identities, bind topics/tenants, verify signatures/capabilities, or check server policy before acting.

### Scheduled jobs

Cron/schedulers have no end-user principal. Design a **service identity** authorized to run for a specific tenant (or an approved administrative cross-tenant workflow). For multi-tenant batches, iterate through each allowlisted tenant in an isolated scope and audit each run; never set `tenant = "*"` and let the repository drop filters unless it is a specialized admin workflow with other controls.

### Downstream HTTP calls

When calling service B, do not assume service B will accept a tenant just because service A authorized it. Use token propagation or service-to-service credentials with proper audience/trust boundaries, forward controlled tenant scopes, and have service B validate independently under its own policy. Avoid confused deputy: a globally privileged service must never serve an arbitrary tenant just because a user sent an optional tenant header.

## 16. Multiple issuers and tenant routing

Spring Security Resource Server supports multi-tenant authentication when an API trusts **multiple authorization servers**. Example selecting a decoder by issuer:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.org",
                "https://idp-b.example.org");
```

This snippet requires importing:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
```

Configure on the resource server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
```

**Two critical points:**

1. When routing by `iss`, the claim may be read before signature verification **solely to pick an AuthenticationManager from an allowlist**; that manager/decoder must then verify the JWT using the chosen issuer's keys/validators. Never treat the raw `iss` value as already authenticated.
2. **Issuer does not necessarily equal tenant.** One issuer can serve multiple tenants, or multiple issuers can represent different identity types. You need a `(issuer, subject) → canonical user → memberships` mapping step and contract-based claim handling.

Spring Security documentation warns against dynamically constructing managers from arbitrary issuer URLs claimed by a token, as that opens the door to trusting unauthorized token sources. For dynamic tenants, the issuer registry must be controlled by trusted administration, never derived from arbitrary request headers.

### Tenant by subdomain vs tenant by issuer

If subdomain `alpha.example.org` selects tenant alpha while JWTs come from a shared issuer, authenticate the issuer against the shared issuer; tenant alpha still requires membership verification.

If each tenant has its own issuer, the authentication routing step picks and verifies the trusted issuer. Afterward, resolve the business tenant from claims and memberships. Do not collapse the two steps into “issuer matched, so read every resource in that tenant.”

## 17. Tenant-switching scenarios

### Single-tenant users

The sole tenant may be selected automatically if that fits the API contract. If the tenant is later locked, membership lookup must deny access rather than continuing to use a stale session-selected tenant.

### Multi-tenant users

The client may send `/tenants/beta` or use a UI tenant selector. The server must verify:

- The user is authenticated.
- Tenant beta has an active membership or delegated permission.
- The token/scope still permits beta under the contract.
- The invoked feature has the required permission in beta.
- The requested record actually belongs to beta.

Never hold the “last selected tenant” in a shared static singleton. If storing the selected tenant in the session, updating the session must re-check membership and guard against CSRF/session fixation accordingly.

### Cross-tenant admins

Do not automatically allow `ROLE_ADMIN` to bypass tenant predicates. There are distinct admin roles: single-tenant admins, support operators covering a subset of tenants, and platform administrators with break-glass procedures. Use a dedicated `CrossTenantAccessPolicy`, audit reason/ticket/TTL, and add tests proving customer-supplied headers cannot expand scope unboundedly.

### Delegated access

For example, an external accountant has read access on a beta tenant's project without full tenant membership. Policy must define the delegated scope (document/project/resource) and never accidentally open the entire tenant by allowing “beta” in the tenant resolver without object-level constraints.

## 18. Tests against tenant spoofing and confused deputy

The test matrix should span from authentication down to the data layer:

| Case | Expected outcome |
| --- | --- |
| Valid JWT, ACTIVE alpha membership, selects alpha | Access allowed to alpha data subject to other permissions |
| Valid JWT, selects beta outside membership | 403 or denied |
| Client alters `X-Tenant-Id` to beta | Cannot open beta without membership |
| Client alters URL `/tenants/beta` | Cannot open beta without membership |
| Missing `Authorization` but valid tenant header | 401 / unauthenticated |
| JWT payload contains beta but invalid signature | 401, business tenant resolver never runs |
| JWT has valid issuer but wrong `aud` | 401 |
| JWT expired or `nbf` not yet valid | 401 |
| JWT issuer not on allowlist | 401 |
| JWT tenants claim is a string instead of a string list | Must not be coerced into arbitrary access |
| Token lists alpha,beta but DB has only alpha | Selecting beta is denied |
| Alpha membership is REVOKED | Denied once state/caches update within SLA |
| User has multiple tenants, makes no selection | Denied or handled per explicit contract, never random |
| User has 1 tenant, makes no selection | May auto-select sole tenant per contract |
| User lacks business authority in alpha | Feature denied despite alpha membership |
| Resource ID belongs to beta, URL specifies alpha | Resource not returned; tenant predicate wins |
| Count/stats/export queries in alpha | Contain zero beta figures |
| Cache key omits tenant | Test detects leak and forces fix |
| Async job membership changed/revoked after enqueue | Re-authorized per policy at execution time |
| Tenant context reused on pooled thread | Must not retain prior request's tenant |
| Trusted gateway fails to strip client-supplied identity header | Header-spoofing test blocks it |
| Cross-tenant admin without break-glass workflow | Denied |

### Mockito/JUnit tests for the resolver

Once you have `TenantMembershipRepository` and `TenantScopeResolver`, test them independently:

```java
@Test
void requestedTenantMustBelongToVerifiedPrincipal() {
    when(memberships.findActiveTenantIdsBySubject("alice"))
            .thenReturn(Set.of("alpha"));

    // Test JwtAuthenticationToken contains tenants alpha,beta
    // and authority SCOPE_documents.read.
    assertThrows(AccessDeniedException.class,
            () -> resolver.require(aliceJwtAuthentication, "beta"));
}
```

This is a **test snippet**, not a standalone file: the `aliceJwtAuthentication` fixture must be built explicitly, and the resolver and mocked repository injected. Unit tests constructing `JwtAuthenticationToken` by hand prove resolver logic only—**they do not prove token signature verification**. Signature/issuer/audience require integration tests with `JwtDecoder`/security filter chains or identity provider tests.

### Spring MVC integration tests

Using `MockMvc`:

- Request without token to `/tenants/alpha/documents` → 401 from the filter chain.
- Mock authenticated Alice belonging to alpha, sending beta path → 403.
- Mock authenticated Alice belonging to alpha, alpha path → 200 containing only alpha IDs.
- Real token signed by an untrusted issuer's test key → 401, never reaches the controller.
- JWT with wrong `aud` → 401, tenant claim unused even if signature is valid.
- If a test uses `SecurityMockMvcRequestPostProcessors.jwt()`, remember it **bypasses token signature verification** by constructing a test authentication; complement it with integration tests that decode real JWTs.

Do not assert only status codes. Assert **specific IDs**, absence of other tenants' data, and `count`/`totalElements`; seed records sharing identical local IDs across two tenants to catch lookup bugs.

## 19. Avoiding fail-open bugs during development

### Never return a null/empty filter when tenant is missing

```java
// Counterexample: missing tenant returns all records.
Specification<Document> scope = requestedTenant == null
        ? null
        : (root, query, cb) -> cb.equal(root.get("tenantId"),
                                        requestedTenant);
```

In many query-builder APIs, `null` means “no condition,” effectively disabling tenant isolation. The resolver must fail closed before reaching the repository; without an `AuthorizedTenantScope`, no query may execute.

### Never use overly broad defaults

```java
// Counterexample.
String tenant = header != null ? header : "all";
```

`"all"` is a highly specialized intentional scope, not a fallback value for normal users. Require a dedicated cross-tenant API and strong permissions instead of turning absence into global access.

### Never rely on UI-enforced constraints

The frontend may hide a tenant switcher button, yet an attacker can still craft HTTP requests. All membership checks belong on the server. CORS is not authorization; API keys/CSRF protection do not replace role/tenant checks.

### Never select a database from an unverified string

```text
header tenant -> "customer-db-" + tenant -> JDBC connection
```

Dangerous if dynamic hostnames/schemas exist or another tenant is reached. Look up from a registry keyed by canonical `AuthorizedTenantScope.tenantId`, never an arbitrary client-sent URL.

## 20. Auditing and observability

Every critical tenant decision should record audit fields:

- Canonical subject ID and issuer (or internal principal ID).
- Requested tenant from route/header (bounded/sanitized against control characters in logs).
- Resolved authorized tenant, or denial reason.
- Action: READ_DOC, EXPORT, UPDATE, SWITCH_TENANT, ADMIN_IMPERSONATE.
- Policy version/membership version if applicable.
- Resource type/ID and correlation/request ID.
- Timestamp, service, and outcome.

Never log raw JWTs, access tokens, session cookies, or sensitive data. Avoid using the requested tenant as an unbounded-cardinality metric label if clients can send arbitrary strings. For anomalous denials on tenant headers, monitor for brute-force/enumeration without returning details about tenant existence to unauthorized callers.

### 401, 403, or 404?

- **401**: no valid authentication.
- **403**: authenticated, but not permitted to access the tenant/feature.
- **404**: may be used for nonexistent resources or to conceal record/tenant existence per API contract.

This classification is a general guideline; actual framework mappings must be configured accurately. Never vary between 403 and 404 in a way that lets attackers enumerate secret tenants when tenant existence itself must remain confidential.

## 21. Risks during membership changes and system synchronization

Memberships change frequently:

```text
t0: Alice has beta access -> JWT is issued
t1: Admin revokes Alice from beta
t2: Alice still holds the old JWT and calls the beta API
```

If the API trusts JWT claims until `exp`, access persists until token expiration. When immediate revocation is needed, use live membership lookups, introspection, token revocation, or entitlement versions.

For membership caches:

- Define TTL/invalidation and a revocation SLA.
- Key caches by issuer+subject, tenant, and policy context.
- Never reuse a cached “Alice has beta access” entry when a different identity shares the same username under another issuer.
- When the policy backend fails, never default to returning all tenants.
- While membership transitions from ACTIVE to REVOKED, do not execute sensitive writes based on a very stale snapshot.

With database replication/read replicas, a membership just revoked on the primary may not yet appear on a replica. Sensitive workflows must choose appropriate consistency. RLS/row predicates must still be applied using the verified scope.

## 22. Common mistakes

**1. Treating `X-Tenant-Id` or `Host` as proof of authorization.** They are selectors; membership must be verified.

**2. Only base64-decoding a JWT to read the tenant claim.** Signature, issuer, audience, and time validity remain unverified.

**3. Verifying the signature while ignoring `aud`.** Tokens meant for other APIs can be misused.

**4. Trusting claims from non-allowlisted issuers.** In multi-issuer setups, pick verifiers solely from a trusted issuer registry.

**5. Assuming token tenant claims remain permanently valid.** Memberships can be revoked; define re-checks and a revocation SLA.

**6. Passing tenant from body/path straight to repositories.** Client input must never become an authorized scope.

**7. Randomly auto-selecting a tenant from a Set.** When a user has multiple tenants, actions easily land on the wrong tenant.

**8. Failing to deny when membership is missing.** A `null` scope can turn into an unrestricted query.

**9. Filtering tenant only on list queries while forgetting count/stats/export.** Leaks counts and aggregated data of other tenants.

**10. Checking only tenant for every record.** Within one tenant, owner, private, ACL/roles, and property-level policies still apply.

**11. Checking only `/tenants/alpha` without verifying the document actually belongs to alpha.** The ID could point to beta.

**12. Storing tenant in ThreadLocal without cleanup.** Thread pools can reuse the previous request's context.

**13. Assuming `@Async` carries the tenant automatically.** Spring Security context and application tenant context require controlled propagation.

**14. Treating a tenant ID on a message/job as trusted by default.** Authenticate producer/service identity and re-authorize per SLA.

**15. Conflating issuer with tenant.** One issuer can serve many tenants, and one tenant may have multiple identity flows.

**16. Omitting tenant from cache keys.** Causes cross-tenant cache poisoning/leakage.

**17. Trusting gateway headers while the backend port is directly reachable.** Attackers can bypass the gateway and spoof headers.

**18. Turning `ROLE_ADMIN` into unchecked global access.** Require cross-tenant policies, auditing, and explicit scopes.

**19. Not locking or re-checking permissions before mutations.** Owner/tenant/membership can change between check and use.

**20. Testing only mock JWTs without testing the decoder.** Mock authentication skips signatures/audience; test the authentication boundary too.

## 23. Pre-production checklist

- [ ] A model clearly separates authenticated subject, requested tenant, and authorized tenant.
- [ ] JWTs are verified for signature, issuer allowlist, audience, exp/nbf, and token purpose.
- [ ] Tenant claim schema is explicit; claims are never taken from decode-only JWTs.
- [ ] Headers/paths/subdomains/cookies are never trusted directly for tenant access.
- [ ] Memberships/grants are fetched from the server and checked for ACTIVE status and validity windows.
- [ ] The resolver defines whether token tenants are intersected with DB memberships.
- [ ] Multi-tenant users must select a tenant explicitly or use a re-verified session selector.
- [ ] Missing authentication, claims, membership, or policy backend errors never yield an unrestricted scope.
- [ ] `AuthorizedTenantScope` is passed into services/repositories as an already-authorized value.
- [ ] Reads/writes/counts/searches/stats/exports all include tenant predicates and object-level scope.
- [ ] ID lookups, joins, attachments, blobs, and background jobs all bind the resource tenant.
- [ ] Schema/database routing never builds from raw tenant selectors; uses an allowlisted registry and pool cleanup.
- [ ] If using RLS, DB roles, transaction settings, connection pooling, and BYPASSRLS are reviewed.
- [ ] Tenant context in ThreadLocal/reactive/async is properly propagated and cleaned up.
- [ ] Trusted proxy headers are stripped/rewritten at the edge, and services accept traffic only via mTLS/trusted networks.
- [ ] Multiple issuers are supported via a trusted issuer registry, never creating verifiers for arbitrary URLs.
- [ ] Membership caches/revocations have explicit TTLs, events, and consistency SLAs.
- [ ] Cross-tenant admins/jobs have dedicated policies, approvals, and auditing.
- [ ] Integration tests cover spoofed headers/paths, wrong JWT iss/aud/signature, stale memberships, and cross-tenant resource IDs.
- [ ] Tests cover counts/stats/caching, concurrency, and identity collisions across issuers/tenants.
- [ ] JWT/session secrets are never logged and secret tenant lists are never disclosed in error responses.

**Conclusion:** *A Tenant ID is a data selector, never authorization on its own.* Trust begins with the authenticated identity; permitted tenant scope comes from a verified token **per contract** and server membership policy; the request's tenant selection must be validated before creating `AuthorizedTenantScope`. Every downstream SQL query, cache, job, statistic, and transaction must use only **the resolved and authorized tenant**, never the raw header/path sent by the client.

## Official references

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Testing OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [OWASP — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
