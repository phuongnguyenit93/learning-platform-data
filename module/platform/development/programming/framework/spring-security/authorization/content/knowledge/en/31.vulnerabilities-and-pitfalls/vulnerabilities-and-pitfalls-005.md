# Confusing `ROLE_` with `SCOPE_` and Mapping Broader Authorities Than the Source

## 1. The Vulnerability to Identify

In Spring Security, a system can **validate a JWT correctly** yet **grant the wrong permissions** if token claims are converted into `GrantedAuthority` instances without preserving their meaning. A common mistake is taking an OAuth 2.0 scope such as `documents.read` or `ADMIN` and creating a `ROLE_...` authority, or treating a generic role like `USER` as proof that the caller has permission to read, edit, and delete all documents.

For example, an authorization server issues a valid access token with `scope: "ADMIN"` under a custom OAuth convention (the scope name does not prove the bearer is an application administrator). The resource server configures `JwtGrantedAuthoritiesConverter#setAuthorityPrefix("ROLE_")`. After conversion, the token carries `ROLE_ADMIN`; an endpoint protected by `hasRole("ADMIN")` becomes accessible. **Administrative privilege emerged from a prefix conversion, whereas the token source only granted a scope.**

Another more common scenario: a token carries `scope: "documents.read"`, yet application code automatically adds `ROLE_EDITOR` for every logged-in user. A `DELETE` endpoint only checks `hasRole("EDITOR")`, so an access token meant only for reading is allowed to delete. Both flaws are **privilege escalation via authority mapping or authorization policy**, not necessarily JWT signature bugs.

**Learning objective:** distinguish role, scope, and authority; trace the flow claim → converter → authority → policy; identify mappings that create broader authorities than the source; configure and test so final authorities accurately reflect the verified policy.

## 2. Distinguishing the Three Concepts, Avoiding Confusing Names with Permissions

| Concept | Typical Source/Semantics | Example | Meaning in Spring Security |
| --- | --- | --- | --- |
| OAuth 2.0 **scope** | Scope of access granted to a client's access token, per contract between authorization server and resource server | `documents.read`, `documents.write` | With default JWT resource server, typically becomes `SCOPE_documents.read`, `SCOPE_documents.write` |
| Application **role** | Role defined by the target system or a trusted delegated source | `READER`, `EDITOR`, `ADMIN` | Typically represented as `ROLE_READER`, `ROLE_EDITOR`, `ROLE_ADMIN`; JWTs do not auto-create these roles unless configured |
| Spring Security **GrantedAuthority** | String representing a permission that policies can check | `SCOPE_documents.read`, `ROLE_EDITOR`, `invoice:approve` | `hasAuthority("...")` matches the authority; prefixes only carry meaning when converter and policy agree on the convention |

**Prefixes are not proof of privilege:** both `ROLE_` and `SCOPE_` are just parts of a `GrantedAuthority` string; Spring Security does not guarantee that `ROLE_ADMIN` actually originated from a trusted admin role. Where the authority is created determines its trustworthiness.

In a typical default configuration:

- `hasAuthority("SCOPE_documents.read")` requires **that exact string**.
- `hasAuthority("ROLE_ADMIN")` requires **that exact string**.
- `hasRole("ADMIN")` is shorthand looking for `ROLE_ADMIN` when using the default `ROLE_` prefix. It **does not read `roles` or `scope` claims directly**.
- `hasRole("SCOPE_documents.read")` is not the way to check a scope; with the default prefix it searches for `ROLE_SCOPE_documents.read`.
- `hasRole("ROLE_ADMIN")` is not standard usage where the API already prepends the prefix. Pass the role name `ADMIN`, or use `hasAuthority("ROLE_ADMIN")`.
- An application can change the default role prefix; therefore during review verify the **actual configuration**, but never alter prefixes to hide permission classification bugs.

The JWT example used in the sections below is an **illustrative payload**; do not treat this JSON itself as a validly signed token:

~~~json
{
  "iss": "https://login.example.org",
  "aud": ["documents-api"],
  "sub": "alice",
  "scope": "documents.read",
  "app_roles": ["READER"],
  "tenant_id": "A"
}
~~~

If the converter is configured according to contract: `scope` produces `SCOPE_documents.read`; `app_roles` (if it is a role claim controlled by a trusted issuer) produces `ROLE_READER`. `tenant_id` is merely a fact for data-scope policies to verify, not an automatic grant over all documents belonging to A.

## 3. Execution Flow: Where Does the Bug Appear?

~~~text
Authorization Server (scopes/claims determined)
      |
      v
Access token (scope, scp, app_roles, aud, sub, ...)
      |
      v
JwtDecoder: verifies signature, expiration, issuer, and required validators
      |
      v
JwtAuthenticationConverter / JwtGrantedAuthoritiesConverter
      |           (point where a scope may be wrongly promoted to a role)
      v
Authentication.getAuthorities(): set of GrantedAuthority strings
      |
      v
authorizeHttpRequests / @PreAuthorize / AuthorizationManager
      |
      v
Resource-specific check: tenant, owner, membership, ACL
      |
      v
ALLOW or DENY
~~~

Spring Security OAuth 2.0 resource server JWT reads scopes by default from common claims like `scope` or `scp` and prepends `SCOPE_`. For instance, `scope: "documents.read documents.write"` normally becomes two authorities `SCOPE_documents.read` and `SCOPE_documents.write`. It does not turn them into `ROLE_...` by default. When configuring `JwtGrantedAuthoritiesConverter#setAuthoritiesClaimName(...)` or `setAuthorityPrefix(...)`, you are actively changing this rule.

**Two distinct decisions** need protection:

1. *Authority mapping*: does the data source/token actually authorize generating each authority?
2. *Authorization*: does the endpoint or business operation require the right authorities **and** the right permissions on the data object?

Mistakes at step 1 cause multiple endpoints to trust the user wrongly. Mistakes at step 2 can permit using a valid authority too broadly, e.g., requiring only `ROLE_USER` to delete any invoice.

## 4. Comparison Table of Easily Confused Cases

Assume the default role prefix is `ROLE_` and the resource server uses the default scope converter unless noted otherwise.

| Input token/authority | Resulting authority | Policy check | Result and reason |
| --- | --- | --- | --- |
| `scope: "documents.read"` | `SCOPE_documents.read` | `hasAuthority("SCOPE_documents.read")` | Correct: permitted by scope |
| `scope: "documents.read"` | `SCOPE_documents.read` | `hasRole("READER")` | Denied: `ROLE_READER` is absent |
| `scope: "ADMIN"` | `SCOPE_ADMIN` | `hasRole("ADMIN")` | Denied under default converter: `ROLE_ADMIN` is absent |
| `scope: "ADMIN"` + **wrong converter using `ROLE_`** | `ROLE_ADMIN` | `hasRole("ADMIN")` | **Vulnerability** if scope ADMIN lacks admin-role semantics |
| Trusted role claim `app_roles:["EDITOR"]` + dedicated role converter | `ROLE_EDITOR` | `hasRole("EDITOR")` | Correct when source, audience, and role semantics are verified |
| Only `ROLE_USER` from app login | `ROLE_USER` | `hasAuthority("SCOPE_documents.delete")` | Denied: a role does not automatically grant delete scope |
| `SCOPE_documents.delete` but document belongs to tenant B | `SCOPE_documents.delete` | Scope check passes; object policy denies | Correct: scope is insufficient to cross tenant boundaries |

Note: an OAuth scope is a string defined by the **contract between issuer and resource server**. A word matching a role name, such as `ADMIN`, does not automatically carry the same meaning. Conversely, a claim named `roles` is not necessarily a local admin privilege either: it may be a realm role, another client's role, a self-assigned group, or metadata not intended for this API.

## 5. Ways Authorities Are Mapped Broader Than the Source and Their Consequences

### 5.1. Converting All OAuth Scopes to `ROLE_...`

A configuration snippet that **runs yet is dangerous when the source is OAuth scopes**:

~~~java
JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
scopes.setAuthorityPrefix("ROLE_"); // Wrong semantics: scope -> role!

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(scopes);
~~~

The API allows setting any prefix, yet here turning `scope=ADMIN` into `ROLE_ADMIN` inadvertently satisfies `hasRole("ADMIN")`. Being configurable does not equate to being a safe mapping. **Never change the prefix just because a route uses `hasRole` and rejects requests**; fix the route to check scopes or separate an authoritative roles source.

### 5.2. Implicitly Creating Roles from a Scope or Simply Because of Login

Anti-pattern example:

~~~java
// Bug illustration: every valid access token receives write role.
if (authentication.isAuthenticated()) {
    authorities.add(new SimpleGrantedAuthority("ROLE_EDITOR"));
}
~~~

If `ROLE_EDITOR` allows writing/deleting, a token issued only a read scope gains write/delete permissions too. Similarly, mapping `documents.read` → `ROLE_EDITOR`, or `SCOPE_*` → `ROLE_ADMIN` is unfounded privilege expansion. `authenticated()` only verifies login status; it does not substitute for operation permissions.

### 5.3. Mixing Roles/Scopes into One Namespace and Using OR Conditions

~~~java
// Bug illustration: generic USER role suffices to delete, even without delete scope.
@PreAuthorize("hasAuthority('SCOPE_documents.delete') or hasRole('USER')")
public void deleteDocument(long id) { /* ... */ }
~~~

`or` makes either condition sufficient to enter the method; `hasAnyAuthority(...)` also checks “at least one”. If the specification requires **both delete scope and specific data permissions**, use an AND condition and object-level policy. A generic role cannot replace a specialized scope.

### 5.4. Trusting a Role Claim from the Wrong Source or Wrong Audience

An access token issued for service X may carry the `ADMIN` role of **X**, not of the documents API. If service Y reads any `roles`/`groups` claim and creates an internal `ROLE_ADMIN`, users can escalate privileges on Y. Restrict valid issuers, target audiences, token types, claim sources, claim names/namespaces, and role meanings per contract. Never read roles from HTTP headers, query parameters, local storage, or unverified JWTs.

Even a signed JWT can contain data the issuer pulled from user-editable profiles or client registration fields. Digital signatures verify integrity and issuer; **they do not prove a claim is trustworthy enough to serve as application admin privilege**.

### 5.5. Uncontrolled Expansion via Hierarchy or Merging

A role hierarchy like `ROLE_ADMIN > ROLE_EDITOR > ROLE_READER` can be valid. However, a converter that accidentally produces `ROLE_ADMIN` from a scope spreads the bug across all inherited permissions. Combining authorities from multiple sources via `DelegatingJwtGrantedAuthoritiesConverter` or custom mappers should only be done after verifying the trust boundary and contract of **each source**; a union operation does not prove the combined permissions are valid.

Normalization operations like `toUpperCase()`, stripping prefixes, wildcards such as `SCOPE_documents.*`, splitting claims with the wrong delimiter, or collapsing all roles into `ADMIN` must also be tested. If policy does not publish wildcards, the string `documents.*` must be treated as an ordinary literal value, not automatically granting all operations.

### 5.6. Endpoint Protected Too Broadly Even with a Correct Converter

~~~java
// Insufficient policy example: any logged-in user can call the write endpoint.
.requestMatchers(HttpMethod.DELETE, "/api/documents/**").authenticated()
~~~

This policy does not require the delete scope. A request with a read-only token still passes the HTTP layer if no other checkpoint exists. Similarly, `anyRequest().authenticated()` or `permitAll()` on sensitive routes, misordered pattern matchers, and methods lacking `@PreAuthorize` can all let operations slip through.

### 5.7. Right Scope Present Without Data-Scope Checks

`SCOPE_documents.read` permits **attempting** a read operation under the contract; it does not prove permission to read every `documentId` or tenant. If `GET /api/documents/B-202` only checks scope and runs `findById("B-202")`, an actor in tenant A can read B's data. Policy must check `tenant`, ownership/ACL, resource status, and active permissions at the service/query layer.

## 6. Illustrating Attack Paths from Token to Endpoint

Assume an application has two endpoints: `GET /api/documents/{id}` requires `documents.read`; `DELETE /api/documents/{id}` requires `documents.delete` and ownership policy.

**Expected contract:** Alice's token only has `scope: "documents.read"`, without `documents.delete`. Even if Alice belongs to tenant A, she cannot delete document A-101 and certainly cannot delete B-202.

**Faulty flow 1 — self-adding a role:**

1. Alice receives an access token with only `documents.read`.
2. An internal converter always adds `ROLE_EDITOR` for any authenticated principal.
3. The delete endpoint uses `hasRole("EDITOR")`, ignoring the `documents.delete` requirement.
4. The request to delete A-101 succeeds even though the original token lacks delete permission. If the endpoint also lacks an object policy, B-202 is also at risk of deletion.

**Faulty flow 2 — confusing prefixes:**

1. The issuer emits an OAuth scope named `ADMIN` to control a separate task.
2. The converter uses `setAuthorityPrefix("ROLE_")` for all scopes.
3. Runtime sees `ROLE_ADMIN`, and `hasRole("ADMIN")` returns true.
4. Any route granting admin access through that authority becomes broadly exposed.

**Correct flow:** JWT is validated for proper issuer/audience; scope becomes `SCOPE_documents.read`; roles are taken solely from a trusted role source; delete requires `SCOPE_documents.delete` and checks permissions on the document ID. Alice receives `403` (or the uniform denial code in the contract) when lacking the delete scope; the request causes no side effects. For an out-of-scope ID, many APIs return `404` to avoid disclosing existence, provided it is applied consistently.

## 7. Configuring Spring Security: Separating Scope and Role Sources

The following example applies to **Servlet + JWT resource server** in Spring Security 6.x/7.x, with Java 17+; it requires Spring Security web, OAuth2 resource server/Jose dependencies, and a valid `JwtDecoder`/issuer configuration in the application. This is a **Spring integration configuration snippet**, not a standalone Java program.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class AuthorizationSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();
        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        // Enable only if issuer/audience and app_roles are a trusted role source.
        JwtGrantedAuthoritiesConverter appRoles =
            new JwtGrantedAuthoritiesConverter();
        appRoles.setAuthoritiesClaimName("app_roles");
        appRoles.setAuthorityPrefix("ROLE_");

        var authorities =
            new DelegatingJwtGrantedAuthoritiesConverter(scopes, appRoles);

        var converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authorities);
        return converter;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, JwtAuthenticationConverter jwtConverter)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET,
                "/api/documents", "/api/documents/**")
                .hasAuthority("SCOPE_documents.read")
            .requestMatchers(HttpMethod.POST,
                "/api/documents", "/api/documents/**")
                .hasAuthority("SCOPE_documents.write")
            .requestMatchers(HttpMethod.DELETE,
                "/api/documents", "/api/documents/**")
                .hasAuthority("SCOPE_documents.delete")
            .anyRequest().denyAll()
        ).oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt -> jwt.jwtAuthenticationConverter(jwtConverter))
        );
        return http.build();
    }
}
~~~

Explanation of each decision:

1. `scopes.setAuthoritiesClaimName("scope")` explicitly identifies the source claim. If the issuer uses `scp` as a collection, adjust according to the contract and test the exact structure; do not arbitrarily merge both by default.
2. `scopes.setAuthorityPrefix("SCOPE_")` preserves the scope boundary.
3. `appRoles` should only run when `app_roles` is genuinely issued by a trusted issuer for the **documents API** and those roles carry meaning inside the application. If there is no trusted role source, **remove the role converter entirely** and rely solely on scopes + business policies.
4. `DelegatingJwtGrantedAuthoritiesConverter` merges authorities from two converters; merging **does not add source validation**. Validate the token before running converters.
5. `jwt.jwtAuthenticationConverter(jwtConverter)` wires the converter into the resource server; writing a `@Bean` without wiring it to the right filter chain can leave the runtime using another converter.
6. HTTP rules require the scope matching the HTTP method. Real systems must also account for PATCH/PUT, export, batch, async, and other endpoints rather than falling back to a broad `anyRequest().authenticated()`. `denyAll()` in the example is a cautious default for undeclared routes.
7. Route rules remain coarse-grained controls. Before reading/writing a document, the service must check object-level policies, e.g., `canRead(actor, document)` or repository queries constrained by tenant, owner, and permission. Method security placed on a Spring bean runs via proxy when using `@PreAuthorize`.

Example checking **scope and data** in method security (illustrative snippet, requiring a real policy bean in the application):

~~~java
@Service
class DocumentService {
    private final DocumentPolicy policy;
    private final DocumentRepository repository;

    DocumentService(DocumentPolicy policy, DocumentRepository repository) {
        this.policy = policy;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.delete')")
    @Transactional
    public void delete(long documentId, Authentication actor) {
        // Policy must use verified principal/tenant, not trust a client-sent tenantId.
        policy.requireCanDelete(actor, documentId);
        repository.deleteById(documentId);
    }
}
~~~

Add imports for `@Service`, `@Transactional`, `@PreAuthorize`, `Authentication`, and the two collaborators per project. `DocumentPolicy#requireCanDelete` must deny when the actor lacks permission on the record. To avoid race/TOCTOU between checking and deleting, for sensitive data consider DELETE/UPDATE queries with scope predicates inside the transaction, row locking or RLS, and checking the actual affected row count. If the business contract also requires a role, e.g., a manager role within the **right tenant**, add the approved condition; do not automatically let `ROLE_ADMIN` bypass scope/object policies.

### Establishing Sources of Truth and Trust Boundaries

- Token issuers must be trusted; validate signature, `iss`, `exp`, `nbf`. Validate `aud` **for the current API** according to your threat model; `issuer-uri` alone does not automatically verify the expected application audience in every setup.
- `scp`/`scope` represents OAuth authorization; `app_roles` represents application roles if contracted. Any claim indirectly controllable by an end user/client must be scrutinized before granting sensitive authorities.
- Do not authorize based on values decoded from unverified tokens, do not read roles from client-sent `X-Role`/`X-Tenant` headers, and do not accept authority lists from request bodies.
- Do not add permissions when claims are empty, wrong type, wrong audience, contain unusual characters, or lack roles. Correct behavior is to deny or produce no sensitive authorities (**fail closed**).
- Permissions inside tokens can become stale once roles/memberships are revoked. For critical operations, consider short-lived tokens, revocation/introspection, or checking current policy state on the server.

## 8. Standalone Java 17+ Example: One Prefix Change Creates `ROLE_ADMIN`

The following program simulates the application's own mapping logic to observe the consequence **without needing Spring Boot**. This is an exercise in authority semantics: `safe` places only recognized scopes into the `SCOPE_` namespace and the `READER` role into the `ROLE_` namespace; `unsafe` turns every scope into a role. The illustrative whitelist depends on each system's contract; this code does not verify JWTs, issuers, or real data permissions.

Save as `AuthorityMappingDemo.java`, run:

~~~bash
javac AuthorityMappingDemo.java
java AuthorityMappingDemo
~~~

Full source code:

~~~java
import java.util.*;

public class AuthorityMappingDemo {
    record Claims(List<String> scopes, List<String> appRoles) {}

    static Set<String> safe(Claims c) {
        Set<String> out = new LinkedHashSet<>();
        Set<String> permittedScopes = Set.of("documents.read", "documents.write");
        for (String scope : c.scopes()) {
            if (permittedScopes.contains(scope)) out.add("SCOPE_" + scope);
        }
        for (String role : c.appRoles()) {
            if (role.equals("READER")) out.add("ROLE_" + role);
        }
        return out;
    }

    static Set<String> unsafe(Claims c) {
        Set<String> out = new LinkedHashSet<>();
        for (String scope : c.scopes()) out.add("ROLE_" + scope);
        return out;
    }

    public static void main(String[] args) {
        Claims reader = new Claims(List.of("documents.read"), List.of("READER"));
        System.out.println("safe = " + safe(reader));
        System.out.println("can-read = " + safe(reader).contains("SCOPE_documents.read"));
        System.out.println("can-write = " + safe(reader).contains("SCOPE_documents.write"));

        Claims unusual = new Claims(List.of("ADMIN"), List.of());
        System.out.println("unsafe = " + unsafe(unusual));
        System.out.println("unsafe-admin = " + unsafe(unusual).contains("ROLE_ADMIN"));
        System.out.println("safe-admin = " + safe(unusual).contains("ROLE_ADMIN"));
    }
}
~~~

Stdout:

~~~text
safe = [SCOPE_documents.read, ROLE_READER]
can-read = true
can-write = false
unsafe = [ROLE_ADMIN]
unsafe-admin = true
safe-admin = false
~~~

Explanation: given the same `ADMIN` scope, `unsafe` synthesizes `ROLE_ADMIN`; `safe` does not create an admin role because the `appRoles` source did not grant it. The `safe` method still simulates only the mapping step; in production, both scopes and roles must be issued by an authoritative source and checked at the specific resource/method.

## 9. Testing to Catch the Exact Bug Instead of Checking Only HTTP Status

Build a set of tokens/fixtures containing at least: user Alice in tenant A; a valid admin of A; user Bob in tenant B; a read-scope-only token; a write-scope token; a token with a role-like scope name (`ADMIN`) without an app role; a token with an app role without delete scope; a token with wrong issuer/audience; a token without scope/roles; and a token with malformed claims.

### Test Matrix

| Token/actor | Expected authorities | GET documents | DELETE documents | Result on document B |
| --- | --- | --- | --- | --- |
| Alice: `documents.read`, `READER`, in A | `SCOPE_documents.read`, `ROLE_READER` | Allowed to read A's object per policy | Denied (missing delete scope) | Denied by object policy |
| Alice: `documents.delete`, no app role, in A | Only `SCOPE_documents.delete` | Denied if missing read scope | Allowed only if data policy permits | Denied when document belongs to B |
| Token with OAuth scope `ADMIN`, no role | `SCOPE_ADMIN` (if scope valid under contract) | Does not automatically get read scope | Does not automatically get delete scope or admin role | Denied |
| Real admin: `documents.delete` + valid role per policy | `SCOPE_documents.delete` + `ROLE_ADMIN` if source trusted | Per read scope | Per policy, within granted scope | Does not cross tenants unless explicitly defined special privilege |
| Token with wrong issuer/audience or invalid | Does not create trusted `Authentication` | Typically `401` | Typically `401` | No data access |
| Token missing required claims | Does not create operation authorities | Denied for scope-gated operations | Denied for scope-gated operations | No data access |

Exact status codes depend on the API contract: missing/invalid access tokens typically return `401`; authenticated but missing authorities typically return `403`; out-of-scope resources may return `404` to avoid revealing existence. Tests must check against the published policy and confirm **no data changes** occur upon denial.

### Testing the Converter Directly

In an application with the `JwtAuthenticationConverter` bean from Section 7, the JUnit 5 + AssertJ example below checks mapping using a `Jwt` *constructed inside the test*, without needing a real signed JWT. This is a **test snippet**, using `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose`, and project imports.

~~~java
@Test
void readScopeMustNotBecomeAdminRole() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "none")
        .claim("sub", "alice")
        .claim("scope", "documents.read")
        .claim("app_roles", List.of("READER"))
        .build();

    JwtAuthenticationConverter converter = jwtAuthenticationConverter();
    var auth = converter.convert(jwt);

    assertThat(auth.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains("SCOPE_documents.read", "ROLE_READER")
        .doesNotContain("ROLE_ADMIN", "SCOPE_documents.delete");
}
~~~

Test further with `scope: "ADMIN"` and **no** `app_roles`: assert `ROLE_ADMIN` does not appear. Also check `scp` as a list, missing claims, empty strings, duplicates, whitespace delimiters, unusual characters, non-whitelisted roles, and case-sensitive matching per IdP contract. If a custom converter produces any dangerous authority not granted by source claims, the test must fail.

### Testing HTTP + Policy Without Relying Entirely on Mock Authorities

`spring-security-test` supports `MockMvc` with `jwt()`, for example:

~~~java
mvc.perform(delete("/api/documents/{id}", 101L)
        .with(jwt().jwt(j -> j
            .subject("alice")
            .claim("scope", "documents.read"))
            .authorities(new SimpleGrantedAuthority("SCOPE_documents.read"))))
    .andExpect(status().isForbidden());
~~~

The snippet above is an **integration test fragment**: it needs `MockMvc`, fixtures, static imports, and real routes. For applications enabling CSRF on state-changing requests, supply a valid CSRF token to avoid hitting the CSRF layer instead of testing scopes. When passing `jwt().authorities(...)`, you **explicitly supply authorities in the test**; this only tests behavior after authorities exist and **does not prove the runtime JWT converter is correct**. You need separate converter unit tests and integration tests with a real bearer token/decoder to verify wiring, issuer, audience, and signature.

Comprehensive tests should cover:

1. **Converter contract:** exact authority list for read-only tokens, write-only tokens, legitimate roles, identically named roles/scopes, empty claims, and unexpected claims. Assert exact expected/forbidden authorities, not just counts.
2. **Request authorization:** `GET`, `POST`, `PATCH`, `DELETE`, and export/bulk endpoints require their specific scopes; read-only tokens cannot write or delete. Having only `ROLE_USER` is insufficient to pass `hasAuthority("SCOPE_documents.delete")`.
3. **Object authorization:** the same token with valid scope accessing a document in tenant B must be denied. Check repository rows, soft-delete, version, and event/outbox after denial.
4. **Token trust:** signed tokens with wrong issuer, wrong audience, expired, invalid signature, or untrusted role claims are rejected. Test error status codes and ensure no privileged context is created.
5. **Method security and proxy:** sensitive methods are invoked via Spring beans so `@PreAuthorize` actually runs. Internal calls via `this.method()` can skip AOP interception; use appropriate service boundaries.
6. **Regression when changing configuration:** rerun the matrix when modifying `JwtGrantedAuthoritiesConverter`, `GrantedAuthoritiesMapper`, role hierarchy, custom authentication providers, IdP claim mapping, and default role prefix.
7. **Checking signs of privilege expansion:** with a read-only token, any non-contracted `ROLE_ADMIN`, `ROLE_EDITOR`, `SCOPE_documents.write`, or `SCOPE_documents.delete` must fail tests, even on endpoints not currently using them.

A single denied **negative test** is insufficient: an endpoint that always returns `403` would also pass. Always include a **positive control** on the same endpoint using a token with valid permissions and object scope to prove the policy genuinely works.

## 10. How to Audit, Fix, and Prevent Recurrence in Existing Projects

Start from the real authorization contract and trace down to the code; do not blindly change a prefix just to “make tests pass”:

1. **List operations and permissions:** build a matrix `endpoint/method → required scope → required app role (if any) → object/data policy`. Clearly separate read, edit, delete, export, and admin permissions.
2. **Document claim sources:** issuer, audience, token type, `scope`/`scp`, role claims, and who is authorized to issue each value. With Keycloak, Auth0, or other IdPs, claim names/namespaces may differ; do not assume `realm_access.roles`, `resource_access`, or `groups` equal permissions for the current API.
3. **Trace authority creation:** inspect `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, `setAuthorityPrefix`, `setAuthoritiesClaimName`, `GrantedAuthoritiesMapper`, custom filters, `UserDetailsService`, role hierarchy, and code manually adding `SimpleGrantedAuthority`. Find any expansion not permitted by the contract.
4. **Fix mapping logic:** keep OAuth scopes in the scope namespace; map app roles only from approved sources and restrict names/capabilities. When the role source is untrusted, remove that mapping; if internal permissions are needed, look up server-side policy using the verified principal.
5. **Fix resource access policies:** routes require exact scopes by HTTP method; service/DB check owner, tenant, membership, ACL, and update permissions. Do not replace object checks with a generic `hasRole("ADMIN")` unless there is an explicit cross-tenant policy.
6. **Add regression tests:** demonstrate before–after for read-only tokens, tokens with role-like scope names, tokens with untrusted role claims, tenant B, background jobs, and exports. Assert zero side effects and ensure logs/audits do not leak raw tokens.
7. **Deploy with observability:** audit clients relying on buggy behavior; update token contracts/issuers if needed; measure anomalous denied requests with safe metrics. Never enable fallback authority grants just to avoid widespread 403 errors.

For live APIs, align owners of `ROLE_*` and `SCOPE_*`; authority naming must be code-reviewed as security policy. Any change to a role hierarchy or converter alters system-wide permissions and can impact many endpoints simultaneously.

## 11. Common False Claims

| False Claim | Truth to Remember |
| --- | --- |
| “The JWT has a valid signature so its `roles` claim can grant admin.” | A technically valid JWT does not prove that claim has authority for this API's admin role; verify source, audience, and semantics. |
| “`hasRole("ADMIN")` reads the JWT role directly.” | It checks the corresponding `GrantedAuthority`; a converter or authentication source must generate that authority. |
| “Changing `SCOPE_` to `ROLE_` is just renaming.” | Renaming can cause `hasRole` routes to accept a previously denied token. |
| “Scope `documents.write` allows editing any document.” | Policies on document, tenant, owner, and status are still required. |
| “`hasAnyAuthority(...)` requires all listed permissions.” | It uses OR; if AND is needed, use an appropriate policy/SpEL. |
| “Having `ROLE_USER` means having write permission.” | Only true if the business contract explicitly grants write permission to that role. Do not generalize automatically. |
| “Testing `jwt()` in MockMvc tests the real token.” | Mock tests may bypass runtime token validation/converter paths; test the trust path separately. |
| “Whenever a claim is invalid, assign a default permission.” | Sensitive permissions must fail closed; never auto-add roles or scopes. |
| “One passing GET test proves no data leaks.” | Also test out-of-tenant IDs, queries/searches, exports, caches, and state after write denials. |

## 12. Lesson Acceptance Checklist

- [ ] Correctly distinguish `scope`, `role`, and `GrantedAuthority`; able to explain `hasRole` vs `hasAuthority`.
- [ ] A token with only `scope: "ADMIN"` does **not** automatically obtain `ROLE_ADMIN` under expected policy.
- [ ] No converter automatically turns all `SCOPE_*` into `ROLE_*` or assigns stronger roles than the source granted.
- [ ] Role claims have clear issuer, audience, owner, and contract; never use roles from another system or client-controlled claims.
- [ ] Each endpoint requires the appropriate functional scope; never use `authenticated()`, `ROLE_USER`, or OR conditions as shortcuts for write/delete.
- [ ] Policies also check permissions on individual resources, tenants, owners, and ACLs; missing scope or data policy denies access.
- [ ] Converter tests assert **absence** of non-source authorities; request/method/database tests prove no out-of-scope access.
- [ ] Tests cover both real JWTs and properly layered mocks; clearly understand `jwt()` does not replace signature, issuer/audience, and custom runtime converter checks.
- [ ] When changing mappings/role hierarchies, regression tests exist and impact on all routes using affected authorities is reviewed.

**Conclusion:** `ROLE_` and `SCOPE_` are naming conventions at the `GrantedAuthority` layer. Secure policy requires every authority to have a verified source, clear business meaning, and scope no broader than granted; endpoints must also verify specific resource boundaries. A single mapping from scope to role can escalate privileges across many APIs.

### References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): default scope-to-authority behavior, `JwtAuthenticationConverter`, custom claims/prefixes, and combining converters.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, `hasRole`, and request rules.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, expressions, and method-level controls.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, customizing claims and authorities in MockMvc.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authorities, role hierarchy, and authorization components.
