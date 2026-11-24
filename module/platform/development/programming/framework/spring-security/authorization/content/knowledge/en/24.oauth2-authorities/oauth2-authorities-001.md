# The Boundary Between Token Verification and Access Decisions

## 1. A valid token is not a license to access every resource

Suppose An signs in via OAuth2 and receives an access token with a valid signature, unexpired lifetime, and the `documents.read` scope. An requests:

~~~http
GET /api/tenants/north/documents/42
Authorization: Bearer <access-token>
~~~

Spring Security Resource Server verifies the token and creates an `Authentication`. Should Document #42 be returned immediately? **No**. The document may belong to the `south` tenant, be owned by Binh, not be shared with An, be locked, or reside in a private project.

Two separate questions must be answered:

1. **Token verification (validation/authentication):** does this credential come from a trusted issuer, have a valid signature or active status, match the API's expected issuer and audience, remain unexpired, have the right token type, and satisfy token policy?
2. **Access decision (authorization):** is the verified actor/client allowed to perform the READ/WRITE/DELETE action on **this exact resource, tenant, and current state**?

Successful token validation is the foundation for authorization decisions, **not a replacement** for object-level authorization. In Spring Security, `JwtDecoder`/opaque introspection handles token verification; HTTP/method security checks functional permissions; and the service/repository typically knows the owner, ACL, membership, and resource state.

This lesson in the **Authorities from OAuth2** group explores that boundary in depth, covering OAuth2 access/ID/refresh tokens, JWT vs. opaque tokens, issuer/audience, `SCOPE_` mapping, client credentials, multi-tenancy, concurrency, API errors, and testing strategies.

## 2. Authentication and authorization flow diagram

~~~text
Browser / mobile / service client
                |
                | Authorization: Bearer <access-token>
                v
Spring Security authentication
  JWT decoder: signature + iss + aud + exp + nbf + type...
  OR opaque introspection: active + trusted metadata
                |
                v
Authentication (verified subject/client + authorities)
                |
                v
HTTP authorization: method/path/scope
                |
                v
Service authorization:
  verified tenant membership
  role/action
  resource owner/ACL/project/status
                |
                v
Scoped query / guarded UPDATE/DELETE
                |
                v
DTO / commit / authorized side effect
~~~

A request can fail at multiple points:
- JWT with wrong signature, issuer, audience, or expiry → authentication failure, typically 401.
- Valid JWT but missing WRITE scope → authorization failure, typically 403.
- Valid token and WRITE scope, but object belongs to another tenant → object denial, possibly 404 to avoid disclosing existence.
- Correct permission but LOCKED state → business rule denial.
- Introspection or policy backend unavailable → do not infer ALLOW; block the action and handle the error.

**Do not use an earlier layer's result as a way to bypass a later layer.** An accepted token does not imply sufficient scope; sufficient scope does not imply ownership; and ownership alone does not bypass a locked state.

## 3. Actors in OAuth2

| Component | Role | Does not automatically cover |
|---|---|---|
| Authorization Server (AS) | Issues tokens, JWKS/introspection, and metadata | Every object ACL in the Resource Server |
| OAuth2 Client | Application requesting/using an access token | Proving by client ID alone that it is the owner |
| Resource Server (RS) | API that verifies tokens and protects data | Issuing tokens merely by configuring a decoder |
| Resource Owner | Principal associated with data permissions per the OAuth flow | Always having a human user in client credentials |
| PEP | Point that intercepts and enforces permissions | Allowing side effects without an ALLOW decision |
| PDP/domain policy | Evaluates subject, tenant, action, resource, and context | Trusting self-asserted owner/role data from the client |

An authorization server can grant the `documents.read` scope to a client. It **does not automatically** provide the list of documents belonging to An and Binh if the ACL resides in the API's database.

Some systems embed fine-grained entitlements into the access token; in that case, the token must carry the exact audience/object/action, and the resource server still needs to check expiry/revocation/consistency per policy. There is no rule that "because the AS signed it, every resource must be allowed."

## 4. Access token, OIDC ID token, and refresh token are different

| Token | Audience/primary purpose | Where used |
|---|---|---|
| OAuth2 **access token** | Intended for Resource Server/API | API endpoints accepting Bearer tokens |
| OpenID Connect **ID token** | Intended for OIDC client/relying party | Proving the login event to the client |
| **Refresh token** | Intended for obtaining new tokens | Client/Authorization Server per grant |

Both ID tokens and access tokens **can be JWTs**. The fact that a token consists of three Base64URL segments does not indicate which type it is.

~~~text
ID token:
  iss = https://idp.example.test/issuer
  aud = frontend-client
  sub = user-72

Access token:
  iss   = https://idp.example.test/issuer
  aud   = documents-api
  sub   = user-72
  scope = documents.read
~~~

If a resource server checks only the signature and skips audience/type, an OIDC ID token can be mistakenly accepted as an API Bearer credential. For systems following the **RFC 9068 JWT Access Token Profile**, a JWT access token requires `typ=at+jwt` or `application/at+jwt`, in addition to issuer, audience, expiry, and other claims. Not every issuer follows RFC 9068; you must verify the actual issuer's profile and not force a generic JWT into RFC 9068 if the authorization server does not support it.

**Do not send a refresh token or ID token to `documents-api`** simply because the client signed in successfully.

## 5. Decoding is not validating a JWT

These steps carry different levels of trust:

~~~text
Base64URL decode JWT header/payload
  -> only reads JSON, not yet trustworthy

Parse claims
  -> identifies fields, does not prove the issuer

Verify signature and trusted algorithm
  -> content matches a trusted signing key

Validate issuer/audience/time/token type
  -> token matches the profile and is meant for this API

Authorize request and resource
  -> is the actor allowed to perform the current action on this object?
~~~

An attacker can craft a payload:

~~~json
{
  "sub": "admin",
  "scope": "documents.write",
  "tenant": "finance"
}
~~~

If the server merely decodes it and creates `ROLE_ADMIN`, it is trusting attacker-supplied data. Use a trusted `JwtDecoder`/introspection mechanism and make authorization decisions only after authentication.

A valid signature does not prove the user is the owner of Document #42; nor does it guarantee the token has not been stolen. It only establishes one property of the token according to the trust/crypto configuration.

## 6. Essential checklist for JWT access token validation

| Condition | Reason | Reject when |
|---|---|---|
| Signature/MAC | Verifies token has not been tampered with, key is trusted | Invalid signature |
| Signing algorithm | Do not trust an `alg` self-declared by the header | `none` or an `alg` outside the allowlist |
| Key/JWKS/`kid` | Select key from the issuer's trust store | Unknown key or key not belonging to the issuer |
| `iss` | Allowed token issuer | Untrusted issuer |
| `aud` | Token intended for the current Resource Server | Access token meant for another API |
| `exp` | Token expiration | Current time is past expiry |
| `nbf` | Not-before timestamp | Token is not yet valid |
| `iat` | Reasonable issued-at time if required by policy | Anomalous or too-old token |
| `typ`/token kind | Prevent JWT type confusion | ID token used instead of access token |
| `sub` or client identity | Subject/workload per token profile | Missing required identity |
| `active`/revocation | Token status per AS/RS | Token has been revoked |
| Sender constraints | Presenter binding if used | Token used by wrong holder |

Do not allow a JWT to supply an arbitrary `jku`/`x5u` URL and fetch keys from it. `kid` is meaningful only within an issuer/JWKS trusted by the server. Verify `alg`, key rotation, and issuer metadata strictly.

**A valid issuer is not enough if the audience is wrong.** Default Resource Server validation typically includes signature, `exp`, `nbf`, and issuer when configured with an issuer; application-specific audience/type checks may require additional validators.

## 7. Audience prevents token substitution across APIs

~~~text
documents-api:
  aud = "documents-api"
  GET /api/documents/42

payments-api:
  aud = "payments-api"
  POST /api/payments
~~~

An has an access token issued by the same issuer with a valid signature and unexpired lifetime, but `aud=payments-api`. Sending it to `documents-api` must **fail token validation**. If an API omits `aud`, a token from a low-privilege API can be replayed against a sensitive API (token substitution/confused deputy).

A token with multiple audiences needs a clear policy: the API must only accept tokens containing its own contracted audience, not an arbitrary string. A multi-valued `aud` also does not automatically grant every scope or resource permission.

Wrong pattern:

~~~java
boolean trusted = jwt.getIssuer().toString()
        .equals("https://idp.example.test/issuer");
return trusted; // Missing audience, expiry, type, object checks.
~~~

This is an **anti-pattern**, not a production validator. Use full token verification from the library/framework.

## 8. Servlet Resource Server with Spring Security

Example HTTP configuration for JWT:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentApiSecurity {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
        return http.build();
    }
}
~~~

**Spring Servlet integration code**, requiring Resource Server/Jose dependencies, authentication setup, JWT decoder/issuer, and real controllers. Not a standalone Java 17 file.

Flow:
1. `BearerTokenAuthenticationFilter` extracts the Bearer token.
2. The JWT provider/decoder validates the token using configured validators.
3. An `Authentication` is created with authorities mapped by the converter.
4. `AuthorizationFilter`/HTTP rules check scopes by path/method.
5. The service must still verify tenant/owner/ACL for Document #42.

With Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
~~~

This is an example URI; the application must know its real audience/type/claims profile. Do not assume `issuer-uri` checks all domain authorization.

**CSRF warning:** if the API supports session/cookie/HTTP Basic browser authentication, an appropriate CSRF policy is required. Do not copy-paste disabling CSRF just because you see Resource Server.

## 9. JwtDecoder with explicit audience validation

A Servlet integration class can add an `aud` validator:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceRequired = jwt -> {
            if (jwt.getAudience() != null
                    && jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                            "Required audience not present", null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audienceRequired));
        return decoder;
    }
}
~~~

Application configuration:

~~~yaml
app:
  security:
    issuer: https://idp.example.test/issuer
    audience: documents-api
~~~

**This is a Spring integration class**, not for standalone `javac`. Issuer/audience are trusted configuration values, never taken from headers or an unverified claim.

Keep `JwtValidators.createDefaultWithIssuer(issuer)` when adding audience validation; avoid accidentally replacing all default validators with only an `aud` predicate. If RFC 9068 is needed, use a token-type/profile validator appropriate for your Spring Security version (6.5/7.x differ regarding `typ`), and do not treat generic JWT defaults as sufficient for every issuer.

Do not place public/private signing keys or secrets in source code. Decoder/JWKS trust and allowed algorithms must be configured accurately.

## 10. Scopes are converted into GrantedAuthority

JWT:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

Spring Security Resource Server by default typically converts scopes into:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

Therefore:

~~~java
.hasAuthority("SCOPE_documents.read")
~~~

checks the exact authority string. `hasRole("documents.read")` looks for `ROLE_documents.read`, which is **not the same** as `SCOPE_documents.read`.

Notes:
- Custom `roles:["ADMIN"]` does not automatically become `ROLE_ADMIN` without a converter.
- A token scope does not prove ownership or ACL for an individual document.
- `hasAnyAuthority(a,b)` is an OR; do not use it to require both.
- Token access scope and tenant role are different concepts.

## 11. JwtAuthenticationConverter does not replace object policy

You can explicitly configure the claim and prefix:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter documentJwtConverter() {
    JwtGrantedAuthoritiesConverter granted =
            new JwtGrantedAuthoritiesConverter();
    granted.setAuthoritiesClaimName("scope");
    granted.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
~~~

Attach it to the Resource Server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
        jwt.jwtAuthenticationConverter(documentJwtConverter())))
~~~

**Integration snippet**, to be wired into a complete Spring configuration. The converter runs after JWT validation; it maps claims to authorities and **does not** look up the owner/ACL of Document #42.

If a role represents a tenant-specific permission, do not turn a role from tenant `north` into a global `ROLE_ADMIN` and apply it in `south`. Token roles can become stale when membership is revoked, requiring a revocation SLA or re-checking in the service.

## 12. Spring Security layers and responsibilities

| Component | Responsibility |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts Bearer token in Servlet requests |
| `JwtAuthenticationProvider` | Invokes decoder and builds Authentication |
| `JwtDecoder/NimbusJwtDecoder` | Verifies JWT and configured validators |
| `OpaqueTokenAuthenticationProvider` | Introspects token / builds Authentication |
| `SecurityContextHolder` | Holds Authentication during Servlet processing |
| `AuthorizationFilter/AuthorizationManager` | Decides HTTP authorization |
| `@PreAuthorize` | Intercepts method invocation per policy |
| Domain service/repository | Tenant, owner, ACL, and state permissions |
| Guarded transaction | Protects mutation/concurrency when action executes |

**`Authentication.isAuthenticated()` does not prove permission to view every object.** It represents authentication status, while functional and resource authorization must be checked separately.

WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, `ReactiveSecurityContextHolder`, and Reactor publishers. Do not copy Servlet `HttpSecurity` into WebFlux.

## 13. Opaque tokens and OAuth2 introspection

An access token can be an opaque string rather than a JWT that the RS can read locally. The Resource Server queries the AS via the introspection endpoint (RFC 7662):

~~~text
Resource Server                         Authorization Server
     |  Bearer token                           |
     +-- introspect(token, client credentials)->|
     |<-- active=true, scope, sub, aud... ------+
     |
     v
Authentication if token satisfies contract
     |
     v
Scope + domain/object authorization
~~~

Spring Boot Servlet:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/introspect
          client-id: documents-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Secrets come from environment variables or a secret manager, never hard-coded. `active=true` lets the RS know the AS considers the token active. Spring Security typically maps introspection scopes to `SCOPE_...`. However:
- `active` does not automatically prove the API's `aud` if the resource profile requires checking it separately.
- `active` does not prove An owns Document #42.
- Introspection timeouts/5xx must not be turned into allow.
- Caching introspection results can extend the window before revocation takes effect.

**An opaque access token is not automatic authorization.** It simply uses a different token validation path than local JWT validation.

## 14. JWT-formatted tokens can also be introspected

A JWT can be sent to the introspection endpoint if the architecture wants the AS to confirm active/revoked status on every request. Spring opaque-token integration can introspect a Bearer string regardless of whether it is opaque or JWT-shaped.

Comparison:

| Aspect | Local JWT | Introspection |
|---|---|---|
| Token validation | Signature, configured validators/JWKS | AS returns `active` and trusted attributes |
| Request-time network dependency | Usually lower once keys are cached | Usually present unless cached |
| Revocation | Requires TTL/revocation/version mechanism | Can reflect AS status faster |
| Object owner/ACL | **Still must be checked** | **Still must be checked** |
| Caching | JWKS/decision per contract | Active result has a stale window |

Do not claim "JWTs cannot be revoked," nor claim introspection automatically means instant revocation if results are cached for long periods.

## 15. 401, 403, 404: at which layer does an error originate?

| Scenario | Classification | Typically appropriate HTTP |
|---|---|---|
| No token on protected API | Unauthenticated | 401/challenge |
| Wrong signature/issuer/aud/exp | Invalid token | 401 |
| Opaque token `active=false` | Invalid token | 401 |
| Valid token but missing write scope | Authorization/insufficient_scope | 403 |
| Valid scope but object in another tenant | Object authorization denial | 403 or 404 anti-enumeration |
| Valid scope and ACL, resource LOCKED | Business state | 403/409 depending on API |
| Introspection/PDP unavailable | Technical error | 5xx/503, do not execute |

RFC 6750 defines the Bearer challenge and error codes such as `invalid_token` and `insufficient_scope`. Whether object denials map to 403 or 404 depends on the application's disclosure policy.

Do not return raw JWT claims, owner names, other tenants, ACL graphs, or stack traces to explain errors to an unauthorized caller. Internal audits may record reason codes/policy versions under separate protection.

## 16. A valid token can still lead to BOLA/IDOR

Valid JWT:

~~~json
{
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

Document:
~~~text
id=42
tenant=south
owner=binh
shares=[]
~~~

An endpoint:

~~~java
Document document =
        documentRepository.findById(42L).orElseThrow();
return mapper.toView(document);
~~~

even when protected by `hasAuthority("SCOPE_documents.read")` can still expose Binh's document if there is no object policy. This is **Broken Object Level Authorization**.

A more complete formula:

~~~text
ALLOW_READ =
    verifiedAccessTokenForThisApi
    AND tokenScopeAllowsRead
    AND activeTenantMembership(subject, requestedTenant)
    AND document.tenantId == requestedTenant
    AND (
        document.owner == subject
        OR validShareReadGrant(subject, document)
        OR permittedProjectMembership(subject, document)
    )
    AND resourceStateAllowsRead
~~~

Do not treat `SCOPE_all` or `ROLE_ADMIN` as a default cross-tenant bypass. Global support/break-glass access, if needed, must define dedicated scopes, authentication, auditing, and restrictions.

## 17. Queries by ID must include tenant and ACL/owner

Owner-only SQL:

~~~sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND d.owner_subject_key = :verified_subject;
~~~

With READ share:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND d.status = 'ACTIVE'
  AND (
      d.owner_subject_key = :verified_subject
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.tenant_id = d.tenant_id
            AND g.document_id = d.id
            AND g.subject_key = :verified_subject
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

ID, tenant, and status stay **outside the OR parentheses**. If written as `(id AND tenant AND owner) OR share`, the grant branch can bypass tenant/ID because `AND` has higher precedence than `OR`.

Tenant and subject must come from verified identity/membership, not self-asserted request bodies/headers. List, count, search, export, and file download endpoints must also filter in the query, not just a single detail endpoint.

## 18. Multi-issuer: sub must be namespaced

Two issuers can both issue `sub="123"`:

~~~text
issuerA / sub 123 -> Alice
issuerB / sub 123 -> Bob
~~~

If the ACL stores only `user_id=123`, Bob can inherit Alice's permissions. Use `(validated issuer, subject)` as the identity key or map to a unique internal actor ID.

Email/name also do not guarantee stable identity across account linking, email changes, or multiple IdPs. Account linking requires verification and auditing, not automatic merging simply because emails match.

In client credentials, `sub`/`client_id` can represent a workload rather than an end-user. Service account policies must differ from user policies when business permissions differ.

## 19. Tenant role is different from OAuth scope

An:
~~~text
tenant north: EDITOR
tenant south: READER
~~~

JWT custom claim contains only:

~~~json
{
  "sub": "an",
  "roles": ["EDITOR"]
}
~~~

If the converter turns `EDITOR` into a global `ROLE_EDITOR`, a WRITE request to `south` can slip past an improperly scoped coarse role gate. You need:
1. Roles claims scoped by tenant and verified by the issuer.
2. Or the service queries active membership by subject + current tenant.
3. Or tokens scoped to a single tenant, validating tenant against the resource.
4. And always check object owner/ACL/status.

The tenant in the path or `X-Tenant-ID` is a **client-chosen target**, not proof of membership. The issuer is not automatically the resource tenant either.

## 20. Safe Spring Data JPA service example

Owner-only repository:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {
    Optional<Document> findByIdAndTenantIdAndOwnerSubjectKey(
            Long id, String tenantId, String ownerSubjectKey);
}
~~~

Service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final VerifiedActorResolver actors;
    private final DocumentRepository documents;
    private final DocumentMapper mapper;

    public DocumentQueryService(
            VerifiedActorResolver actors,
            DocumentRepository documents,
            DocumentMapper mapper) {
        this.actors = actors;
        this.documents = documents;
        this.mapper = mapper;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    @Transactional(readOnly = true)
    public DocumentView read(Long documentId, String requestedTenant) {
        VerifiedActor actor = actors.requireTenantMember(
                requestedTenant, "DOCUMENT_READ");

        Document document = documents
                .findByIdAndTenantIdAndOwnerSubjectKey(
                    documentId, actor.tenantId(), actor.subjectKey())
                .orElseThrow(ResourceNotFoundException::new);
        return mapper.toView(document);
    }
}
~~~

**Integration code**, requiring real domain components, entity, and Spring configuration. `@EnableMethodSecurity` must be enabled; self-invocation can bypass proxy-based method security.

Boundaries:
- JWT validated before the service is called.
- `@PreAuthorize` checks the functional scope.
- The resolver extracts issuer/sub from the verified Authentication and checks membership.
- The repository filters by exact tenant/object.
- The mapper creates a DTO after the scoped query.

When supporting shares/grants, use a query for owner OR valid grant without dropping the object check.

## 21. @PreAuthorize scope check is insufficient for WRITE

Faulty pattern:

~~~java
@PreAuthorize("hasAuthority('SCOPE_documents.write')")
public void rename(long documentId, String title) {
    repository.updateTitleById(documentId, title);
}
~~~

A valid JWT and WRITE scope do not prove ownership/ACL of that document ID. The API could perform unauthorized writes.

Model:
~~~text
HTTP    -> verify token + audience + coarse WRITE scope
Service -> verified actor/tenant + role/action + owner/ACL
DB      -> guarded UPDATE/DELETE on exact document
Audit   -> authorization decision + mutation execution outcome
~~~

If ownership is checked beforehand, the owner can change between check and use (TOCTOU); guarded mutations or a lock/version protocol are necessary for sensitive actions.

## 22. Guarded UPDATE at mutation time

Owner-only example:

~~~sql
UPDATE documents
SET title = :title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_subject_key = :verified_subject
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

A result of 0 affected rows → no record satisfied the guard; do not return a fake success. Possible causes: ID does not exist, wrong tenant, not owner, locked, or stale version.

If WRITE depends on ACLs in another table or a remote PDP, an owner guard alone is not enough. Use `EXISTS`/transaction/lock/version/revocation protocols per the consistency contract; `@Transactional` alone does not lock a remote ACL.

**A token verified at T1 does not prove permissions have not changed at T2.** For revoked grants, the service must enforce according to the effective timing defined by the product.

## 23. Token TTL and current permissions are two separate clocks

~~~text
T0: Access token issued
     scope=documents.write, exp=T0+15 minutes
T1: An granted WRITE on document 42
T2: Admin revokes grant
T3: An uses unexpired token
~~~

At T3, signature/issuer/aud/exp and scope may still be valid. Yet the ACL has been revoked. If policy requires immediate permission updates, object authorization must DENY.

Distinguish between:
- Token expiration.
- Session/refresh token revocation.
- ACL/membership expiry and `revoked_at`.
- ALLOW cache TTL.
- Policy revision rollout.
- Concurrent transaction state.

Short-lived access tokens shrink the window, and introspection can verify active status faster, but neither replaces owner/ACL queries nor proves all caches have been invalidated.

## 24. Client credentials: access token represents a workload

The client credentials flow typically yields a token representing a service/client rather than a human user. For example, an export worker with `invoices.export` scope and `aud=billing-api`.

The API must check:
- Verified client/workload identity.
- Audience, scope, and accepted grant/profile.
- Which tenants and resources the workload is allowed to access.
- Quotas, purpose, audit, and service identity.
- Sender constraints (mTLS/DPoP) if applicable.

Do not assume `jwt.getSubject()` is a user ID with access to all records. If token exchange/on-behalf-of is used, verify the actor chain and audience; a self-asserted `X-Acting-User` header is not sufficient.

## 25. Multi-issuer and trust policy

With multiple authorization servers:
- Trusted issuers must be in a managed allowlist/registry.
- Keys, algorithms, issuer, and audience are bound to their corresponding trust profile.
- Do not fetch an arbitrary JWKS URL requested by the token itself.
- Identity keys must be namespaced by issuer+subject.
- Role claims from issuer A do not automatically grant access in tenant B.
- Do not trust `iss` merely from decoding; verify it before treating it as an identity.

Spring Security Servlet supports `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` depending on version, and reactive has its own counterparts. Do not copy Servlet classes to WebFlux.

## 26. Bearer tokens are possession-based credentials

Anyone holding a valid Bearer token can present it to the API within its granted scope. Therefore:
- Use TLS and avoid tokens in URLs.
- Do not log Authorization headers, raw JWTs, or refresh tokens.
- Protect token storage from XSS/leaks.
- Grant minimal scopes and reasonable TTLs.
- Use revocation/session versions when needed.
- Consider sender-constrained tokens (mTLS/DPoP) for appropriate environments.
- Do not forward tokens to services with different audiences; consider token exchange.

**An untampered token does not mean an unstolen token.** And token possession still does not prove resource ownership.

## 27. Downstream API calls: audience must match each hop

Service A receives a token with `aud=api-a`. When calling service B, if the token is only for A, B must reject it even if the signature is valid.

Wrong:
~~~text
API A receives valid aud=api-a
   -> forwards original access token to API B
API B validates signature but ignores aud
   -> accepts and accesses resource
~~~

Solution: token exchange/OBO for `aud=api-b`, client credentials for B with dedicated scopes, or trusted identity propagation with validation and auditing. Spring helpers that propagate Bearer tokens do not automatically guarantee consent or audience.

## 28. Missing attributes in token: do not guess ALLOW

A token may contain only issuer, subject, audience, and a read scope, **without**:
- Current tenant membership.
- Owner/ACL/group permissions.
- Resource classification/status.
- Business subscriptions/limits/expiries.

When missing, the Resource Server can query a trusted DB/PIP/PDP or use versioned/expiring embedded entitlements by design. When the permission backend fails, it must fail closed—never grant "temporary" access just because the token has a scope.

Avoid optional SQL guards:

~~~sql
WHERE id=:id
  AND (:tenant IS NULL OR tenant_id=:tenant)
~~~

Because a null tenant can cause the predicate to skip tenant checks. For object authorization, a missing tenant is a denial/error, not a "broaden the search."

## 29. Decision tree for READ document

~~~text
GET /api/tenants/north/documents/42
          |
          v
Access token validated for documents-api?
 no -> 401
 yes
          |
          v
Has SCOPE_documents.read?
 no -> 403
 yes
          |
          v
Active tenant membership in north?
 no -> deny
 yes
          |
          v
Document belongs to north and owner/share READ permits?
 no -> 403/404
 yes
          |
          v
State and field classification permit READ?
 no -> deny
 yes
          |
          v
Return allowed DTO, not arbitrary entity fields
~~~

List/search/export/download must also scope queries and field projections properly. A READ scope does not automatically allow reading salary/secret fields if object policy requires separate filtering.

## 30. Standalone Java 17: a valid token does not guarantee access

The following example **runs on JDK 17** without Spring. `ValidatedToken` represents a token **already verified for signature/claims by a trusted authentication layer**; the demo only simulates the verification result and does not implement JWT algorithms itself.

Create `TokenAccessBoundaryDemo.java`:

~~~java
import java.util.Set;

public class TokenAccessBoundaryDemo {
    enum Action { READ, WRITE }

    record ValidatedToken(
            boolean signatureAndClaimsValid,
            String issuer,
            String subject,
            String audience,
            Set<String> scopes) { }

    record Document(
            long id, String tenant, String ownerKey, boolean locked) { }

    record Grant(
            String tenant, long documentId,
            String subjectKey, Action action) { }

    static boolean tokenAccepted(
            ValidatedToken token, String audience) {
        return token != null
                && token.signatureAndClaimsValid()
                && token.issuer() != null
                && !token.issuer().isBlank()
                && token.subject() != null
                && !token.subject().isBlank()
                && audience.equals(token.audience())
                && token.scopes() != null;
    }

    static boolean scopeAllows(ValidatedToken token, Action action) {
        String needed = action == Action.READ
                ? "documents.read" : "documents.write";
        return token.scopes().contains(needed);
    }

    static String authorize(
            ValidatedToken token,
            String requestedTenant,
            Document document,
            Action action,
            Set<Grant> grants,
            Set<String> activeMemberships) {

        if (!tokenAccepted(token, "documents-api")) {
            return "INVALID_TOKEN";
        }
        if (action == null || !scopeAllows(token, action)) {
            return "INSUFFICIENT_SCOPE";
        }

        String subjectKey = token.issuer() + "|" + token.subject();
        if (requestedTenant == null || requestedTenant.isBlank()
                || document == null || document.id() <= 0
                || grants == null || activeMemberships == null
                || !requestedTenant.equals(document.tenant())
                || !activeMemberships.contains(
                    requestedTenant + "|" + subjectKey)) {
            return "DENIED_RESOURCE_SCOPE";
        }

        if (document.locked() && action == Action.WRITE) {
            return "DENIED_RESOURCE_STATE";
        }

        boolean owner = subjectKey.equals(document.ownerKey());
        boolean grant = grants.contains(new Grant(
                document.tenant(), document.id(), subjectKey, action));
        return owner || grant
                ? "ALLOW" : "DENIED_OBJECT_PERMISSION";
    }

    public static void main(String[] args) {
        ValidatedToken an = new ValidatedToken(
                true, "issuerA", "an", "documents-api",
                Set.of("documents.read", "documents.write"));

        ValidatedToken wrongAudience = new ValidatedToken(
                true, "issuerA", "an", "payments-api",
                Set.of("documents.read", "documents.write"));

        ValidatedToken readOnly = new ValidatedToken(
                true, "issuerA", "an", "documents-api",
                Set.of("documents.read"));

        ValidatedToken badSignature = new ValidatedToken(
                false, "issuerA", "an", "documents-api",
                Set.of("documents.read", "documents.write"));

        ValidatedToken otherIssuer = new ValidatedToken(
                true, "issuerB", "an", "documents-api",
                Set.of("documents.read", "documents.write"));

        Document ownerDoc =
                new Document(42, "north", "issuerA|an", false);
        Document sharedDoc =
                new Document(43, "north", "issuerA|binh", false);
        Document southDoc =
                new Document(42, "south", "issuerA|an", false);
        Document lockedDoc =
                new Document(44, "north", "issuerA|an", true);

        Set<String> members = Set.of(
                "north|issuerA|an", "north|issuerB|an");
        Set<Grant> grants = Set.of(
                new Grant("north", 43, "issuerA|an", Action.READ));

        System.out.println("owner-read=" + authorize(
                an, "north", ownerDoc, Action.READ, grants, members));
        System.out.println("shared-read=" + authorize(
                an, "north", sharedDoc, Action.READ, grants, members));
        System.out.println("shared-write=" + authorize(
                an, "north", sharedDoc, Action.WRITE, grants, members));
        System.out.println("wrong-audience=" + authorize(
                wrongAudience, "north", ownerDoc,
                Action.READ, grants, members));
        System.out.println("read-scope-write=" + authorize(
                readOnly, "north", ownerDoc, Action.WRITE, grants, members));
        System.out.println("bad-signature=" + authorize(
                badSignature, "north", ownerDoc,
                Action.READ, grants, members));
        System.out.println("cross-tenant=" + authorize(
                an, "north", southDoc, Action.READ, grants, members));
        System.out.println("same-sub-other-issuer=" + authorize(
                otherIssuer, "north", ownerDoc,
                Action.READ, grants, members));
        System.out.println("locked-write=" + authorize(
                an, "north", lockedDoc, Action.WRITE, grants, members));
        System.out.println("revoked-membership=" + authorize(
                an, "north", ownerDoc, Action.READ, grants, Set.of()));
    }
}
~~~

Run:

~~~bash
javac TokenAccessBoundaryDemo.java
java TokenAccessBoundaryDemo
~~~

Exact stdout:

~~~text
owner-read=ALLOW
shared-read=ALLOW
shared-write=DENIED_OBJECT_PERMISSION
wrong-audience=INVALID_TOKEN
read-scope-write=INSUFFICIENT_SCOPE
bad-signature=INVALID_TOKEN
cross-tenant=DENIED_RESOURCE_SCOPE
same-sub-other-issuer=DENIED_OBJECT_PERMISSION
locked-write=DENIED_RESOURCE_STATE
revoked-membership=DENIED_RESOURCE_SCOPE
~~~

The output demonstrates:
1. Token with valid signature/claims, right `aud`, READ scope + membership + owner → ALLOW.
2. READ grant for document 43 does not grant WRITE.
3. Wrong audience and bad signature are both blocked at the token gate.
4. A READ-only token cannot WRITE even when the user is the owner.
5. Wrong tenant, different issuer despite matching `sub`, locked resource, and revoked membership all deny independently of token validity.

**Limitation:** The boolean `signatureAndClaimsValid` is merely a fixture simulating verification by the authentication layer; never accept this boolean from a client. The demo does not implement signature/exp/nbf/JWKS/introspection and does not simulate DB concurrency. Use real Spring Security `JwtDecoder`/introspection in your application.

## 31. Spring Security Test: mock JWT does not prove signature verification

Spring Security Test supports `jwt()` for MockMvc. Example:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentsScopeTests {
    @Autowired
    MockMvc mvc;

    @Test
    void missingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/42")
                  .with(jwt().authorities()))
           .andExpect(org.springframework.test.web.servlet.result
                   .MockMvcResultMatchers.status().isForbidden());
    }
}
~~~

**Spring Test snippet** requiring imports placed on valid lines in a Java file, MockMvc, Security Test, real endpoints, and a real filter chain. Test helpers can inject an `Authentication` without verifying a raw Bearer JWT signature; therefore, use them only to test scope/authorization policy, not as proof of signature/issuer/audience validation.

Test real validation using Bearer requests through the configured decoder with a test issuer/JWKS/keys:
- Invalid signatures and disallowed algorithms.
- Wrong issuer/audience.
- Expired or future `nbf`, wrong token type.
- Key rotation and `kid` not in the trust store.
- Introspection `active=false` and backend unavailable.
- Integrated scope conversion, audience checks, and resource-specific authorization.

## 32. Two-boundary test matrix

| Token/permission | Token accepted? | Scope gate? | Object policy? | Result |
|---|---|---|---|---|
| JWT right aud, READ scope, owner | PASS | PASS | PASS | ALLOW |
| JWT valid signature, aud for another API | FAIL | Not evaluated | Not evaluated | 401 |
| JWT invalid signature | FAIL | Not evaluated | Not evaluated | 401 |
| JWT expired | FAIL | Not evaluated | Not evaluated | 401 |
| OIDC ID token aud frontend | FAIL | Not evaluated | Not evaluated | 401 |
| Valid JWT missing WRITE scope | PASS | FAIL | Not evaluated | 403 |
| JWT WRITE scope, someone else's object | PASS | PASS | FAIL | 403/404 |
| JWT admin north accessing document south | PASS | Coarse may PASS | FAIL | DENY |
| JWT with READ scope, ACL revoked | PASS | PASS | FAIL | DENY |
| JWT with READ scope, membership revoked | PASS | PASS | FAIL | DENY |
| JWT WRITE scope, document locked | PASS | PASS | FAIL | DENY/conflict |
| Opaque active=false | FAIL | Not evaluated | Not evaluated | 401 |
| Opaque active=true, missing scope | PASS if other checks pass | FAIL | Not evaluated | 403 |
| Introspection timeout | Unverifiable | Not evaluated | Not evaluated | Fail closed |
| Two issuers with same sub | PASS if issuer trusted | Depends | Namespace | No owner confusion |
| Client credentials token | PASS if profile valid | Depends | Workload policy | Do not assume user owner |
| Same local document ID across two tenants | PASS | May PASS | Tenant guard | No data leakage |
| aud=api-a sent to API-B | FAIL at B | Not evaluated | Not evaluated | 401 |
| Permission backend outage | PASS | May PASS | Unverifiable | No side effect |

In addition to HTTP responses, assert that database state/outbox/files remain unchanged after denial. A 403 response is insufficient if the service mutated the DB before denying.

## 33. Debugging errors at the right layer

- **401 when switching issuers:** check `issuer-uri` and trusted keys; do not enable `permitAll`.
- **401 only at service B:** check whether the token's `aud` targets B; do not add roles.
- **401 due to expired token:** client refreshes/re-authenticates through a secure flow.
- **403 due to missing `SCOPE_...`:** check token scopes and converter; do not assign ADMIN.
- **403/404 due to object ACL:** check tenant/owner/grant; do not blame JWT.
- **409 due to stale version:** concurrency, not authentication.
- **503 due to introspection timeout:** fail closed; do not treat tokens as "active by default."

Do not log raw JWTs for debugging; use safe reason codes, correlation IDs, and policy revisions. Do not return real tenant/owner names to unauthorized callers.

## 34. JWT in cookies: CSRF and browser notes

A JWT passed via an explicit Bearer header and a JWT stored in an automatically sent cookie have different threat models:
- Bearer-only stateless API where the frontend explicitly sends the header, with no cookie/session fallback: CSRF may not apply the same way as cookie auth.
- JWT/session in cookies, refresh-cookie endpoints, or browser-managed HTTP Basic credentials: CSRF can still be a risk.
- A CORS allowlist does not replace CSRF, authentication, or object authorization.

Do not disable CSRF by default just because the token is a JWT. How the browser sends the credential matters more than the token format.

## 35. Logging, privacy, and error disclosure

Do not log:
- Raw access/refresh/ID tokens.
- Cookies/sessions, Authorization headers, or signed URLs.
- Introspection client secrets or private keys.
- Full token claims/ACLs containing unnecessary PII.
- Owners/tenants outside the caller's permissions.
- Exceptions containing internal URLs or credentials in responses.

Safe to record as classification codes:
- `AUTHN_INVALID_AUDIENCE` / `AUTHN_EXPIRED_TOKEN`.
- `AUTHZ_INSUFFICIENT_SCOPE` / `AUTHZ_RESOURCE_DENIED`.
- Policy revision, request/decision ID, masked actor/tenant alias.
- Enforcement outcome and commit/rollback.

Audit stores are sensitive data; support staff viewing audits need dedicated tenant/case permissions, not just knowledge of a request ID.

## 36. Common mistakes

**1. Base64-decoding a JWT and trusting claims.** Unverified. Use `JwtDecoder`/introspection.

**2. Verifying only the signature and skipping audience.** Tokens for other APIs get accepted improperly. Check `aud`.

**3. Calling an API with an OIDC ID token.** Wrong purpose. Check type/audience.

**4. Assuming `authenticated()` allows every endpoint.** Scope/role/action checks are required.

**5. Assuming `SCOPE_documents.read` grants read access to any ID.** BOLA. Requires owner/ACL/tenant checks.

**6. Using `hasRole("documents.read")` for an OAuth scope.** Wrong prefix. Use `SCOPE_` authority.

**7. Expecting a custom `roles` claim to automatically become `ROLE_`.** Requires an explicit converter.

**8. Letting tenant A's ADMIN role become global in tenant B.** Requires tenant-scoped policy.

**9. Using `sub` without an issuer namespace.** Identity collision.

**10. Using an unscoped `findById` and returning a DTO.** Missing object check.

**11. Using `@PreAuthorize` followed by a bare ID UPDATE.** TOCTOU/IDOR.

**12. Skipping revoked ACL checks because the JWT is unexpired.** Token TTL differs from permission freshness.

**13. Assuming active on introspection timeout.** Fail-open.

**14. Treating a client credentials token as an end-user token.** Workload identity confusion.

**15. Forwarding an `aud=api-a` token to API-B.** Token substitution.

**16. Testing with mock `jwt()` and concluding token crypto works.** Mocks do not replace the real decoder.

**17. Logging Bearer tokens to debug.** Credential leakage/replay.

**18. Enabling `permitAll` to fix a 403.** Fixes the wrong layer and opens up access.

## 37. Resource Server implementation checklist

- [ ] Distinguish access tokens, ID tokens, and refresh tokens.
- [ ] Validate tokens via a trusted decoder/introspection, never by parsing raw claims.
- [ ] Verify signature/key/algorithm, `iss`, `aud`, `exp`, `nbf`, and token type/profile.
- [ ] Maintain an explicit issuer/JWKS trust allowlist; never fetch arbitrary URLs from JWT headers.
- [ ] Map scopes/custom roles accurately to authorities.
- [ ] Require appropriate scopes per HTTP method/action, with deny fallback.
- [ ] Prevent multi-tenant roles from merging into global admin.
- [ ] Derive tenant and subject key from verified Authentication/membership.
- [ ] Source resource ID+tenant+owner/ACL/status from server-side storage.
- [ ] Apply query-time scoping to list/count/export/download as well.
- [ ] Guard WRITE/DELETE operations with version/lock/revocation protocols.
- [ ] Enforce dedicated policies for client credentials/workload tokens.
- [ ] Validate each downstream API's own audience.
- [ ] Fail closed on introspection timeout/`active=false` and PDP errors.
- [ ] Define effective timing and SLAs for token/session/ACL revocation.
- [ ] Ensure 401/403/404/5xx errors do not leak tokens, owners, or tenants.
- [ ] Test token validators with test issuers/keys, not only mock `jwt()`.
- [ ] Test wrong audience, expired tokens, missing scopes, cross-tenant access, and revoked ACLs.
- [ ] Verify denied requests do not mutate DB, files, or queues.
- [ ] Check Spring Security API/`typ` validators when upgrading versions.

**Conclusion:** Token verification answers **"is this credential trustworthy and intended for this API?"**; authorization answers **"is this verified actor/client allowed to perform this action on this exact resource, tenant, and current state?"**. These two boundaries must stay separate. A valid token does not guarantee object permissions; scopes do not replace owner/ACL checks; a valid signature does not replace revocation. Only the combination of audience validation, tenant/object scoping, guarded mutations, fail-closed handling, and testing at both layers keeps a Resource Server secure.

## References

- [Spring Security — Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature, issuer, audience, and scope mapping.
- [Spring Security — Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, active status, revocation.
- [Spring Security — Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and WebFlux.
- [Spring Security — Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): Bearer credentials and downstream propagation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and method authorization.
- [Spring Security — OAuth2 Migration](https://docs.spring.io/spring-security/reference/migration/servlet/oauth2.html): `typ` validation changes across versions.
- [RFC 6750 — Bearer Token Usage](https://datatracker.ietf.org/doc/html/rfc6750): Bearer errors, challenges, and security.
- [RFC 7662 — Token Introspection](https://datatracker.ietf.org/doc/html/rfc7662): active status and metadata.
- [RFC 9068 — JWT Profile for Access Tokens](https://datatracker.ietf.org/doc/html/rfc9068): access token type, issuer, audience.
- [RFC 8725 — JWT Best Current Practices](https://datatracker.ietf.org/doc/html/rfc8725): algorithms, audience, and token confusion.
- [OWASP API Security Top 10 — BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object-level checks.
