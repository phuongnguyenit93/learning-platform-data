# Never Trust Client-Supplied Claims or Unverified Tokens

## 1. Core problem: a string saying "admin" does not make the caller an admin

A Spring Security application receives a request:

~~~http
PATCH /api/tenants/finance/documents/42
Authorization: Bearer <access-token>
X-User-Id: ceo
X-Role: ADMIN
X-Tenant-Id: finance
Content-Type: application/json

{
  "ownerId": "ceo",
  "roles": ["ADMIN"],
  "approved": true,
  "title": "New title"
}
~~~

A caller can modify any value in the **URL, headers, and body under their control**. Strings like `ceo`, `ADMIN`, `finance`, or `approved=true` are merely **claims/assertions**, not proof. A JWT attached by the client is also untrusted until the Resource Server genuinely verifies its signature or introspection status, issuer, audience, timestamps, token type, and application conditions.

The most important rule:

> **Never derive a principal, role, tenant membership, or ALLOW decision from client-supplied claims or unverified token contents.** Use only verified identities, permission data from trusted sources, and server-side resource attributes to authorize the actual operation.

This lesson belongs to the **Authorities from OAuth2** group; the focus is the trust boundary between browser/client, OAuth2 Authorization Server, Spring Security Resource Server, and domain authorization. Even with a validly signed JWT, the API must still check owner/ACL/tenant for the object the caller tries to access.

## 2. Learning objectives

After this lesson, you can:
- Distinguish a **claim**, **authentication proof**, and an **authorization decision**.
- Detect privilege escalation caused by taking `role`/`isAdmin` from the HTTP request.
- Explain why Base64URL-decoding a JWT is not signature verification.
- Configure Spring Security JWT Resource Server with issuer, audience, timestamps, and signing-key trust.
- Understand risks from `alg=none`, algorithm confusion, `kid`/`jku`, and token-type confusion.
- Convert **verified claims** into `GrantedAuthority` instances without turning tenant A's role into global privilege in tenant B.
- Distinguish OAuth2 access tokens from OIDC ID tokens, opaque tokens, and client-credentials workload identities.
- Design actor/tenant resolvers and query-time owner/ACL checks.
- Protect trust boundaries when using gateways, reverse proxies, background jobs, or microservices.
- Test both a real JWT decoder and HTTP/resource authorization, without confusing mocks with cryptographic verification.
- Handle missing/invalid claims on the **fail-closed** principle.

## 3. Data source trust classification table

| Data | Source | Safe to use directly for ALLOW? |
|---|---|---|
| `userId` from JSON body | Caller-written | **No** |
| `X-Role: ADMIN` | Self-sent header | **No** |
| `tenantId` in path | Tenant requested by caller | **No**, must verify membership |
| `isOwner=true` in form | Self-asserted by caller | **No** |
| JWT payload after Base64URL decode | Unverified token | **No** |
| `iss`/`sub` read from unverified JWT header/payload | Untrusted strings | **No** |
| `Jwt` verified by Resource Server decoder and built by converter | Trusted authentication pipeline | **Trusted input**, not object permission by itself |
| `Authentication.getAuthorities()` built by trusted provider | Verified authentication context | **Can check coarse actions**, insufficient for ACL/tenant if lacking scope |
| Tenant membership from controlled DB | Trusted PIP/repository | Usable per policy/freshness |
| Resource owner/tenant/status from DB | Trusted resource data | Usable once bound to exact resource/transaction |
| Token claim from trusted issuer that may be stale | Time-bounded evidence | Needs revocation/freshness review |
| Header from reverse proxy protected by a trust boundary | Gateway that authenticates and strips spoofed headers | Only under a strictly verified contract |
| Client-sent Correlation ID | Operational metadata | Never an entitlement |

**Claims are not inherently bad**: a claim is a statement about a subject/token. Claim values carry appropriate trust only after transport/issuer/validators are verified and then **interpreted with accurate semantics**. A `scope=documents.read` claim can prove the token received a functional scope, yet does not prove the caller owns Document #42.

## 4. Threat model: what can an attacker control?

Assume an attacker can:
1. Send any HTTP request, altering URL/path/query/body/headers.
2. Craft a three-part JWT-like string and Base64URL-encode arbitrary claims.
3. Tamper with the payload of a signed JWT without holding the signing key.
4. Send a **real** JWT meant for another API or from another issuer.
5. Send an OIDC client's ID token in place of an access token.
6. Replay a stolen access token or one whose permissions were revoked before expiry.
7. Probe requests across many document IDs and tenant IDs.
8. Inject headers resembling those normally added by an internal gateway.
9. Send malicious `kid`/`jku` strings inside the token header.
10. Use a role claim issued for tenant A to attempt accessing tenant B.

The defensive goal is maintaining one single path from **credential verification** to **trusted principal**, then enforcing permissions on **the exact action–resource–tenant**. Never allow requests to supply "already verified" fields themselves.

### Direct attack example

~~~http
POST /api/users/promote
Authorization: Bearer <regular-user-token>
Content-Type: application/json

{
  "targetUserId": "attacker",
  "role": "SUPER_ADMIN",
  "performedBy": "security-admin",
  "approved": true
}
~~~

The server must treat `role=SUPER_ADMIN` only as **the requested change**, never as approval for that change. The actor must come from the verified `Authentication`; `ROLE_SECURITY_ADMIN`, MFA/approval, and tenant policies must be checked server-side.

## 5. A JWT has header, payload, and signature—decoding is not verifying

A JWS compact JWT typically takes the form:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Header and payload can be Base64URL-decoded **without knowing any secret or public key**. Therefore:
- Reading `sub`, `roles`, or `scope` by decoding produces only **untrusted strings**.
- A sender can alter the JSON and re-encode it without a valid signature.
- The mandatory step is verifying the signature with a trusted algorithm/key **and** validating claims/profile for this API.
- Encrypted JWE tokens have different structure and encryption; encrypted does not mean "authorized." Authenticate/decrypt per profile and still authorize afterward.

Forged payload example:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "admin",
  "aud": "documents-api",
  "scope": "documents.read documents.write",
  "roles": ["SUPER_ADMIN"]
}
~~~

If a Spring application builds `UsernamePasswordAuthenticationToken` from the raw payload alone, the attacker becomes admin. Let Spring Security's `JwtDecoder` or introspection implementation establish identity after validation—never build principals manually from a user-attached JWT string.

### Broken code pattern to recognize

~~~java
// WRONG: no signature/issuer/audience/time verification.
String[] sections = bearerToken.split("\\.");
String json = new String(
        java.util.Base64.getUrlDecoder().decode(sections[1]),
        java.nio.charset.StandardCharsets.UTF_8);
// Creating roles from json here is privilege escalation.
~~~

This is an **illustrative anti-pattern**, never to be run in production. The parser can crash on malformed tokens, and worse, trusts forged claims by relying on decoding.

## 6. Even a valid signature does not guarantee the token is trusted for this API

A Resource Server can verify a signature and still be wrong if:
- The public key belongs to an issuer **not** in the trust registry.
- The token has `aud=payments-api` but is sent to `documents-api`.
- `exp` has passed or `nbf` is in the future.
- The JWT is an OIDC ID token meant for a frontend client.
- The token uses an algorithm disallowed by the API.
- The token fails the active token type/profile.
- The token was revoked per contract.
- The token represents **client credentials**, with no human user.
- A validly signed scope/role has lost business validity because the ACL or membership was revoked.

Therefore two clear layers are required:

~~~text
TOKEN ACCEPTED =
  trusted issuer/key
  AND permitted cryptographic algorithm
  AND valid signature/active status
  AND valid exp/nbf and required temporal rules
  AND expected audience and token type/profile
  AND required token schema

ALLOW ACTION =
  TOKEN ACCEPTED
  AND action permission/scope
  AND verified subject or client identity
  AND verified tenant membership
  AND resource policy (owner/ACL/status)
  AND current business constraints
~~~

Never collapse the second formula into `TOKEN ACCEPTED` or `scope.contains("admin")`.

## 7. Algorithm configuration: never trust the token's self-declared "alg"

A JWT header can state:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

or a signing algorithm outside the application's allow-list. Historical vulnerabilities include:
- `alg=none` paired with a library that skips signature verification.
- Confusing `RS256` with `HS256`, treating an RSA public key as an HMAC secret.
- Letting the token dictate the algorithm instead of server-configured trust.
- Reusing a single key across algorithms outside its intended profile.

Per **RFC 8725 JSON Web Token Best Current Practices**, libraries/applications must restrict supported algorithms and match the executed algorithm against the declared header, never accepting arbitrary token-suggested algorithms.

With Spring Security, configure `NimbusJwtDecoder`/`NimbusReactiveJwtDecoder` to trust only the right issuer/JWKS and algorithms. Test with tokens signed using unexpected algorithms; requests must be rejected. Never hand-roll JWS verification with regexes or string comparisons.

## 8. `kid`, `jku`, `x5u`: untrusted headers can cause SSRF/injection

JWT headers can also include:
- `kid`: key ID used to select a key.
- `jku`: JWK Set URL.
- `x5u`: certificate chain URL.

**Never** fetch `jku`/`x5u` directly from a caller-supplied token to load public keys. Attackers can point to controlled hosts or internal addresses (**SSRF**) and make the API verify tokens with the attacker's key.

Instead:
1. Configure trusted issuers and JWK Set URIs/metadata from trusted configuration.
2. Select `kid` only within the key set bound to an approved issuer.
3. Configure algorithm allow-lists and cache/key-rotation lifetimes.
4. Never let tokens trigger arbitrary outbound network requests.
5. Sanitize/bound `kid` if it enters logs, queries, or cache keys.
6. Test anomalous `kid` values, missing JWKS keys, rotated keys, and unreachable issuers.

RFC 8725 includes a **Do Not Trust Received Claims** section specifically warning about `kid` injection and `jku/x5u` SSRF. A token header can guide the verifier, yet is **never trusted configuration**.

## 9. `iss`, `aud`, `exp`, `nbf`, `typ` must be validated per contract

| Field | Meaning | Pitfall |
|---|---|---|
| `iss` | Token issuer | Merely reading the string and treating the issuer as trusted |
| `aud` | Intended recipient/API | Token for API A accepted at API B |
| `exp` | Expiration time | Accepting expired tokens |
| `nbf` | Not-before time | Accepting before validity window opens |
| `iat` | Issued-at, used when policy needs it | Failing to reject excessively old tokens |
| `typ` | JWT kind/profile | Accepting ID tokens in place of access tokens |
| `sub` | Subject per issuer | Collisions across issuers |
| `scope`/`scp` | OAuth2 permissions | Confusing scopes with object ownership |
| `azp`/`client_id` | Authorized party/client per profile | Assuming every token represents a human user |
| `jti` | Token identifier if emitted by issuer | Thinking `jti` prevents replay without actually tracking it |

The actual token profile dictates which fields are required. For instance, **RFC 9068 JWT Access Token Profile** mandates access token typing and profile fields. Not every access token is a JWT, and not every JWT follows RFC 9068.

**Audience is critical:** if an issuer mints tokens for multiple APIs, the RS must verify `aud` contains its own identifier. Missing or wrong `aud` → reject the token even when the signature is valid.

## 10. Access tokens differ from OIDC ID tokens and refresh tokens

| Token | Purpose | Never use as |
|---|---|---|
| **OAuth2 access token** | Calling a Resource Server with matching audience | License to bypass object ACLs |
| **OIDC ID token** | Proving a user authentication event to an OAuth client | Bearer access token for an API |
| **Refresh token** | Obtaining new access tokens via Authorization Server | Credential sent to resource endpoints |

An OIDC ID token and a JWT access token can share similar `iss`, `sub`, and signatures. However, `aud` typically differs. An API must not check "is this a valid JWT?" and accept an SPA's ID token. Enforce a distinct accepted token profile.

Client-credentials tokens authenticate a **service client**, not a human user. If code reads `sub` and blindly constructs a "human user" without checks, it risks assigning wrong data permissions.

## 11. Spring Security Resource Server is the trusted starting point

In Spring Servlet, for example:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentsSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

**Spring integration snippet**: requires Spring Security Resource Server/Jose dependencies, JWT decoder/issuer, controllers, and appropriate CSRF/session policies. Not standalone Java 17.

The security pipeline extracts the Bearer credential, runs the trusted decoder, builds `JwtAuthenticationToken`/`Authentication`, and enforces authorities. Never read `X-User-Id` headers or manually decode JWTs inside controllers to identify callers.

Spring Boot configuration can start with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
~~~

The URI is illustrative. The default decoder typically validates signatures/timestamps/issuer and maps scopes; **application-specific audience and token-type rules must be verified per your configuration and version**. Never conclude all validators are active merely because the app boots.

## 12. Configuring an audience validator while keeping default validators

A Spring Security Servlet example:

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
                            "Audience not accepted", null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audienceRequired));
        return decoder;
    }
}
~~~

Properties:

~~~yaml
app:
  security:
    issuer: https://idp.example.test/issuer
    audience: documents-api
~~~

This is **integration code**; issuer and audience must come from trusted server config, **never from HTTP headers or unverified token payloads**. Using `JwtValidators.createDefaultWithIssuer(issuer)` alongside audience validation prevents accidentally overwriting baseline validators with an `aud`-only predicate.

If the system uses RFC 9068, also validate accepted `typ`/access-token profiles per your Spring Security version. Spring Security 6.5 and 7.x differ in token-type handling APIs; consult the Javadocs for your running dependency rather than disabling validation to accept tokens from an unexpected profile.

## 13. `JwtAuthenticationConverter`: map claims after verification, never before

Spring Security typically converts `scope` or `scp` into `GrantedAuthority` instances prefixed with `SCOPE_`. For example, a valid token contains:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

After validation, `Authentication` can contain:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

Hence `hasAuthority("SCOPE_documents.read")` matches, whereas `hasRole("documents.read")` looks for `ROLE_documents.read` and fails. Never turn raw client JSON `roles:["ADMIN"]` into a `GrantedAuthority`.

If the issuer uses a custom authority claim, you can configure:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorityConverter =
            new JwtGrantedAuthoritiesConverter();
    authorityConverter.setAuthoritiesClaimName("scope");
    authorityConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(authorityConverter);
    return converter;
}
~~~

**Integration snippet**, wired via `oauth2ResourceServer(...jwt(jwt -> jwt.jwtAuthenticationConverter(...)))` or equivalent configuration. It only maps **issuer-verified** claims to authorities and does not decide object ownership.

Even a validly signed claim can **lose freshness**: roles or group memberships may have changed after token issuance. Permissions needing rapid revocation should consult current membership/ACLs or use explicit authz revisions/TTLs.

## 14. Header/body `"isAdmin"` is requested data, not proof

Dangerous code pattern:

~~~java
@PostMapping("/documents/{id}/share")
public void share(@PathVariable long id,
                  @RequestBody ShareRequest request) {
    if (request.isAdmin()) {
        grants.shareWithEveryone(id);
    }
}
~~~

If `isAdmin` is passed by the caller, the caller simply sets it to `true` in JSON.

A request model should describe **what the user wants to do**, e.g.:
~~~java
public record ShareRequest(
        String targetUserId, String permission) { }
~~~

Server code extracts the actor from the Spring-verified `Authentication`, identifies the requested SHARE action, and checks owner/tenant/service policy before creating a grant. Never let the client supply `performedBy`, `ownerId`, or `approved=true` as proof of permission.

An owner field in a create request is occasionally permitted by business rules (e.g., creating a document on behalf of a team). Even then, it is only a **proposed value** requiring approval/delegation policy checks, not proof of existing privilege.

## 15. `Authentication` from Spring: read from the right source at the right time

In Spring MVC Resource Server, once the security filter chain verifies the JWT, a handler can obtain the `Jwt` principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MyIdentityController {

    @GetMapping("/api/me")
    String me(@AuthenticationPrincipal Jwt jwt) {
        return jwt.getIssuer().toString() + "|" + jwt.getSubject();
    }
}
~~~

**Integration snippet**: use only on routes protected by the resource server; check for null/issuer per token profile. Returning subject/issuer to the caller themselves on `/api/me` can be fine, but never return full token claims or secrets in public responses.

Crucially, a `Jwt` received via Spring-authenticated principal comes from the **verification pipeline**. Conversely, manually calling `new Jwt(...)` on a request body does not make the token trustworthy. Identical Java types do not establish trust provenance.

In services, prefer receiving `Authentication`/verified actor from the security context or method parameters; never pass a `String userId` read from a raw header in a controller and rename the variable `verifiedUserId`.

## 16. Request tenants must be verified—never trust `X-Tenant-ID`

Suppose An has role EDITOR in tenant `north` but only VIEWER in tenant `south`. Request:

~~~http
POST /api/tenants/south/documents/42
Authorization: Bearer <token-of-an>
X-Tenant-ID: south
X-Role: EDITOR
~~~

`south` can only be treated as the **target tenant**, not membership proof. The server must:
1. Extract validated issuer+subject from Spring `Authentication`.
2. Normalize the target tenant (validated path/header).
3. Query the actor's ACTIVE membership in the target tenant.
4. Resolve roles/permissions **within that tenant**.
5. Load resource tenant/owner/status from the database.
6. Check the WRITE action against owner/ACL and state.
7. Mutate using a scoped query/transaction guard.

If a JWT has a custom claim `roles:["EDITOR"]` without tenant context, never map it to a global `ROLE_EDITOR` applied across all tenants. A signed token never adds scoping details the issuer did not grant.

## 17. Subject claims can collide across multiple issuers

~~~text
Issuer A, sub=123 -> Alice
Issuer B, sub=123 -> Bob
~~~

If the ACL stores only `subject=123`, Bob can inherit Alice's permissions. Identity keys should be `(validatedIssuer, subject)` or an internal principal ID mapped from that pair. Avoid using email as a primary key unnecessarily, as emails can change, collide, or be recycled.

When multi-issuer:
- Trusted issuers belong to a managed allow-list/registry.
- Each issuer has its own JWKS/algorithms/decoder per trust contract.
- Each API's token audience must still match.
- Never trust an issuer merely because `iss` string decoded cleanly.
- Account linking requires verification and auditing—never auto-link simply because names/emails match.
- Roles from issuer A do not become roles in tenant B.

Spring Security offers multi-tenancy/issuer resolver mechanisms depending on Servlet/Reactive version. Invariant rule: **derive identity only after the token is verified by a trusted issuer**.

## 18. Opaque tokens: introspection must also sit inside the trust boundary

Not every OAuth2 access token is a JWT. For opaque tokens, the Resource Server can call the Authorization Server's introspection endpoint (RFC 7662):

~~~text
Resource Server
    |
    | authenticated token introspection request
    v
Authorization Server
    |
    | active, scope, sub, aud, exp...
    v
Resource Server maps trusted result to Authentication
    |
    v
HTTP + service + resource authorization
~~~

Spring Boot Servlet example:

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

Illustrative configuration; secrets come from environment variables/KMS/secret managers, never source code.

Be careful:
- `active=true` has meaning per the issuer/introspection contract, not "permission for every object."
- Check audience/required metadata when needed by the Resource Server.
- Never let a client submit JSON `{"active":true}` instead of a real AS response.
- Introspection must be authenticated over TLS with proper client credentials.
- AS unavailable/timeout → never assume the token is active by default.
- If caching introspection results, define TTL and revocation SLAs.

Reading raw JSON from a caller-specified endpoint or object does not make introspection trustworthy. HTTPS endpoints and mutual trust must reside in server configuration, never chosen by tokens or headers.

## 19. Gateways and reverse proxies: internal headers can also be forged

A system has an API gateway that validates JWTs and adds:

~~~http
X-Authenticated-User: an
X-Authenticated-Issuer: issuerA
X-Authenticated-Tenant: north
X-Authenticated-Roles: EDITOR
~~~

If a backend service accepts these headers **directly from the internet**, or if the gateway fails to strip client-sent headers before attaching its own, attackers can spoof users and roles.

Two valid architectures depending on environment:

**A. Each service verifies the Bearer token itself** with matching issuer/audience and runs domain authorization. Clear trust boundaries; requires consistent JWKS/key rotation and policy management.

**B. Gateway verifies and propagates authenticated identity** over a protected service-to-service channel:
- Only the gateway can reach the backend, with no bypass paths.
- mTLS or service identity / cryptographically authenticated context.
- Gateway strips/overwrites all identity headers from public requests.
- Backend verifies the request genuinely came from the trusted gateway.
- Identity propagation carries clear issuer, subject, tenant scope, expiry, audience, and provenance.
- Never trust headers from an arbitrary proxy simply because it runs on an "internal network."
- Add integration tests calling the backend directly with forged headers; they must be rejected.

**Zero trust** requires verifying identity at every appropriate trust boundary. An `X-Role` header is never a signed assertion, no matter how official its name looks.

## 20. Forwarded headers are not authorities

`X-Forwarded-For`, `X-Forwarded-Host`, `Forwarded`, and similar headers can be useful for routing or client IP detection behind trusted reverse proxies. However, they **do not prove roles, users, token issuers, or owners**.

If a system restricts admin APIs by IP, it must configure trusted proxies, header stripping, ingress auth, and clear policies. Clients can easily send `X-Forwarded-For: 127.0.0.1` if network boundaries allow it.

The `Origin` header is also not authentication:
- Browsers use `Origin`/CORS to constrain cross-origin scripts.
- Non-browser clients can forge any `Origin`.
- A CORS allow-list does not grant admin roles.
- A CSRF token does not verify object ownership.

Never treat every "security-looking" header as a trusted claim.

## 21. OAuth2 scopes do not prove ownership or ACLs

A valid token contains:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

An calls `GET /documents/42`. Document #42 is in tenant `south` and owned by Binh. HTTP rule `hasAuthority("SCOPE_documents.read")` may PASS, yet the object check must DENY.

Example policy:

~~~text
ALLOW_READ =
    validAccessTokenForDocumentsApi
    AND hasScope("documents.read")
    AND activeMember(subject, requestedTenant)
    AND resource.tenant == requestedTenant
    AND (
        subjectIsOwner(resource)
        OR activeShareReadGrant(subject, resource)
        OR activeProjectReadPermission(subject, resource)
    )
    AND resourceStateAllowsRead
~~~

A raw `ownerId` in a request body **must never** replace `resource.owner` read from the DB. If a project needs break-glass/system admin access, define an audited exception policy with dedicated authentication rather than inferring it from `X-Is-Admin: true`.

This is the core of OWASP **Broken Object Level Authorization (BOLA)**: every endpoint receiving an object ID must verify the actor may perform the action on that specific object.

## 22. DB queries must bind the verified actor and resource scope

Owner-only:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND d.owner_subject_key = :verified_subject;
~~~

With READ share:

~~~sql
SELECT d.id, d.title
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

Conditions on `id`, `tenant`, and `status` must apply to **both owner and ACL branches**. Writing `id AND tenant AND owner OR share` without parentheses lets the OR branch bypass tenant isolation.

Parameter sources:
- `:verified_subject` from authenticated issuer/sub or internal principal ID.
- `:verified_tenant` from a verified membership resolver, never a bare header.
- `:id` is the client-chosen target, bound to tenant/ACL.
- `:now` is server time, never a client clock.

**Never substitute hard-to-guess IDs for object authorization.** Using UUIDs does not eliminate IDOR/BOLA if a caller obtains someone else's ID.

## 23. Spring service: use `Authentication`, not self-asserted claims

A service method can be protected with method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final VerifiedActorResolver actorResolver;
    private final DocumentRepository repository;

    public DocumentService(
            VerifiedActorResolver actorResolver,
            DocumentRepository repository) {
        this.actorResolver = actorResolver;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    @Transactional(readOnly = true)
    public DocumentView read(String requestedTenant, Long documentId) {
        VerifiedActor actor =
                actorResolver.requireActiveTenantMember(requestedTenant);

        Document document = repository
                .findReadableByIdAndTenant(
                    documentId, actor.tenantId(), actor.subjectKey())
                .orElseThrow(ResourceNotFoundException::new);

        return new DocumentView(document.getId(), document.getTitle());
    }
}
~~~

**Spring integration snippet**: `VerifiedActorResolver`, `VerifiedActor`, `DocumentRepository`, `DocumentView`, and exceptions are domain types to implement. `@EnableMethodSecurity` must be enabled. `actorResolver` must obtain identity from the authenticated context, never reading `X-User-Id`.

Order:
1. JWT/opaque token is verified.
2. `@PreAuthorize` checks coarse scope.
3. Resolver checks active tenant membership.
4. Repository runs a resource-scoped query.
5. Return a DTO restricted to permitted fields.

Self-invocation via `this.read(...)` can bypass method interceptors in proxy mode; tests must call through the Spring-managed proxy. Non-HTTP adapters (workers, message consumers) also need an appropriate service policy boundary.

## 24. WRITE/DELETE must be guarded at mutation time

Even if a token is valid and ownership is checked at T1, permissions can change at T2 before the DB UPDATE at T3.

~~~text
T1: token valid, owner=an -> ALLOW WRITE
T2: document changes owner or WRITE grant is revoked
T3: repository.updateById(42) executes unguarded
~~~

This is time-of-check/time-of-use (TOCTOU). For owner-only writes, use guarded SQL:

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

A result of affected rows = 0 means **failure**—never return a fake 200/204. If WRITE is granted via an ACL in another table, use an `EXISTS` predicate, transaction, lock, or revision protocol; `@Version` on the document alone does not re-check grants elsewhere.

Never use `jwt.getClaim("isAdmin")` to skip mutation guards. Even a valid claim can be stale or lack object scope.

## 25. Token roles and ACLs can change after token issuance

Suppose:
~~~text
T0: AS issues token valid for 15 minutes
    role=EDITOR, scope=documents.write

T1: Admin revokes WRITE permission on Document 42
T2: User calls API with unexpired token
~~~

The JWT may still be valid by signature/issuer/exp. Yet the domain grant is gone; depending on policy, the request must DENY. Distinguish:
- Token lifetime.
- Permission/membership/ACL lifetime.
- Authorization cache TTL.
- Revocation propagation/consistency SLA.
- Policy version.

Solutions may include short-lived access tokens, introspection, ACL/version lookups, revocation lists, or decision cache invalidation. Never promise immediate revocation while the server keeps honoring long-lived cached ALLOWs.

**"Signed by a trusted issuer" does not mean "every claim stays valid forever."**

## 26. JWTs in cookies, CSRF, and CORS

If a JWT is stored in a cookie automatically sent by browsers, endpoints remain exposed to CSRF because browsers attach ambient credentials to forged requests. If a Bearer token is explicitly sent by the frontend in an `Authorization` header for a stateless API, the CSRF threat model differs.

Do not argue:
- "JWT is signed so CSRF isn't needed" — false if a cookie carries the token automatically.
- "CORS blocks evil sites so CSRF can't happen" — CORS does not block all requests from being sent.
- "Having a CSRF token means having ADMIN role" — CSRF tokens are not identity.
- "`Origin: app.example` means the user owns the document" — Origin is not an ACL proof.

Defending against XSS, CSRF, credential theft, token validation bypasses, and broken domain authorization are separate layers that may all be needed together.

## 27. Trust boundaries in Reactive WebFlux

With Spring WebFlux, use `ServerHttpSecurity` and `SecurityWebFilterChain`:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .pathMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

This is a **WebFlux integration snippet**, requiring `ReactiveJwtDecoder`/issuer config, OAuth2 Resource Server dependencies, and business service checks. Servlet's ThreadLocal `SecurityContextHolder` does not replace `ReactiveSecurityContextHolder`/Reactor Context.

Notes:
- Reactive authorization's `Mono<Authentication>` must come from the framework, never from a request body identity.
- Avoid `block()` on event loops when checking tokens/ACLs.
- Never cache the current principal in a mutable singleton or shared `Mono.cache()` that leaks users across requests.
- When async messages/workers run outside a request, use workload/verified delegation contracts rather than trusting a `requestedUser` string.
- `ServerWebExchange` attributes and Reactor Context are **per-request/subscription containers**; they do not make claims trustworthy on their own.

## 28. Server-issued context must never be accepted from clients

A controller may receive:

~~~http
X-Requested-Tenant: north
X-Acting-User: admin
X-Policy-Override: allow
X-Request-Id: req-999
~~~

These headers never make a user an admin. If the server supports impersonation/support:
- Require an explicit admin/act-as capability verified via a trusted `Authentication`.
- Enforce approval, reason, TTL, auditing, and scope limits.
- Keep resource access protected.
- Treat intent headers strictly as **proposed requests**, never proof.

Correlation IDs help trace incidents, yet **must never** be used as permission evidence. Even a client-sent header named "Verified" must never be trusted without a trusted gateway contract.

## 29. Standalone Java 17: forged assertions cannot alter permissions

The following program **runs on JDK 17** without Spring. It models a trust boundary using a **server-owned** token → verified identity table. Strings like `bearer-an` are fixtures demonstrating that the code ignores `clientClaimedSubject`, `clientClaimedRole`, and `clientClaimedTenant` as permission proofs. **This is not JWT cryptographic verification**; never use hardcoded token markers in production.

Create `ClaimTrustBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class ClaimTrustBoundaryDemo {
    enum Action { READ, WRITE }

    record RawRequest(
            String bearerRef,
            String clientClaimedSubject,
            String clientClaimedRole,
            String clientClaimedTenant,
            String targetTenant,
            long targetId,
            Action action) { }

    record VerifiedToken(
            String issuer,
            String subject,
            String audience,
            Set<String> scopes) { }

    record Document(
            long id, String tenant,
            String ownerKey, boolean locked) { }

    record Membership(
            String subjectKey,
            String tenant,
            Set<Action> allowedActions) { }

    record Grant(
            String tenant, long documentId,
            String subjectKey, Action action) { }

    // Server-owned stub only. Production uses JwtDecoder/introspection.
    static final class TrustedTokenVerifier {
        private final Map<String, VerifiedToken> issued = Map.of(
            "bearer-an",
            new VerifiedToken("issuerA", "an", "documents-api",
                    Set.of("documents.read", "documents.write")),
            "bearer-binh",
            new VerifiedToken("issuerA", "binh", "documents-api",
                    Set.of("documents.read")),
            "bearer-carol",
            new VerifiedToken("issuerA", "carol", "documents-api",
                    Set.of("documents.read", "documents.write")),
            "wrong-aud",
            new VerifiedToken("issuerA", "an", "payments-api",
                    Set.of("documents.read", "documents.write")),
            "wrong-iss",
            new VerifiedToken("issuerB", "an", "documents-api",
                    Set.of("documents.read", "documents.write")),
            "no-scope",
            new VerifiedToken("issuerA", "an", "documents-api",
                    Set.of("documents.read"))
        );

        VerifiedToken verify(String marker) {
            return issued.get(marker);
        }
    }

    static final Set<Membership> MEMBERSHIPS = Set.of(
        new Membership(
            "issuerA|an", "north", Set.of(Action.READ)),
        new Membership(
            "issuerA|binh", "north", Set.of(Action.READ)),
        new Membership(
            "issuerA|carol", "north",
            Set.of(Action.READ, Action.WRITE))
    );

    static final Set<Grant> GRANTS = Set.of(
        new Grant("north", 47, "issuerA|an", Action.READ)
    );

    static String check(
            TrustedTokenVerifier verifier,
            RawRequest request,
            Document document) {

        if (request == null || request.action() == null) {
            return "DENY_INVALID_INPUT";
        }

        VerifiedToken token = verifier.verify(request.bearerRef());
        if (token == null
                || !"issuerA".equals(token.issuer())
                || !"documents-api".equals(token.audience())
                || token.subject() == null
                || token.scopes() == null) {
            return "DENY_UNVERIFIED_TOKEN";
        }

        String neededScope = request.action() == Action.READ
                ? "documents.read" : "documents.write";
        if (!token.scopes().contains(neededScope)) {
            return "DENY_SCOPE";
        }

        if (document == null
                || document.id() != request.targetId()
                || request.targetTenant() == null
                || !request.targetTenant().equals(document.tenant())) {
            return "DENY_RESOURCE_SCOPE";
        }

        String subjectKey =
                token.issuer() + "|" + token.subject();
        boolean memberCanAct = MEMBERSHIPS.stream().anyMatch(m ->
            m.subjectKey().equals(subjectKey)
            && m.tenant().equals(request.targetTenant())
            && m.allowedActions().contains(request.action())
        );
        if (!memberCanAct) {
            return "DENY_TENANT_ROLE";
        }

        if (document.locked() && request.action() == Action.WRITE) {
            return "DENY_LOCKED";
        }

        boolean owner = subjectKey.equals(document.ownerKey());
        boolean shared = GRANTS.contains(new Grant(
                document.tenant(), document.id(),
                subjectKey, request.action()));
        return owner || shared ? "ALLOW" : "DENY_OBJECT";
    }

    public static void main(String[] args) {
        TrustedTokenVerifier verifier =
                new TrustedTokenVerifier();

        Document own = new Document(
                42, "north", "issuerA|an", false);
        Document binh = new Document(
                43, "north", "issuerA|binh", false);
        Document shared = new Document(
                47, "north", "issuerA|binh", false);
        Document locked = new Document(
                44, "north", "issuerA|carol", true);
        Document south = new Document(
                45, "south", "issuerA|an", false);

        System.out.println("owner-read=" + check(
            verifier, new RawRequest(
                "bearer-an", "admin", "SUPER_ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("forged-admin-write=" + check(
            verifier, new RawRequest(
                "bearer-an", "admin", "SUPER_ADMIN", "north",
                "north", 42, Action.WRITE), own));

        System.out.println("spoofed-owner=" + check(
            verifier, new RawRequest(
                "bearer-an", "binh", "ADMIN", "north",
                "north", 43, Action.READ), binh));

        System.out.println("shared-read=" + check(
            verifier, new RawRequest(
                "bearer-an", "an", "VIEWER", "north",
                "north", 47, Action.READ), shared));

        System.out.println("unsigned-or-unknown=" + check(
            verifier, new RawRequest(
                "made-up-jwt", "admin", "ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("wrong-audience=" + check(
            verifier, new RawRequest(
                "wrong-aud", "an", "ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("wrong-issuer=" + check(
            verifier, new RawRequest(
                "wrong-iss", "an", "ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("missing-write-scope=" + check(
            verifier, new RawRequest(
                "no-scope", "an", "ADMIN", "north",
                "north", 42, Action.WRITE), own));

        System.out.println("cross-tenant=" + check(
            verifier, new RawRequest(
                "bearer-an", "an", "ADMIN", "south",
                "north", 45, Action.READ), south));

        System.out.println("locked-write=" + check(
            verifier, new RawRequest(
                "bearer-carol", "carol", "ADMIN", "north",
                "north", 44, Action.WRITE), locked));
    }
}
~~~

Compile and run:

~~~bash
javac ClaimTrustBoundaryDemo.java
java ClaimTrustBoundaryDemo
~~~

Exact stdout:

~~~text
owner-read=ALLOW
forged-admin-write=DENY_TENANT_ROLE
spoofed-owner=DENY_OBJECT
shared-read=ALLOW
unsigned-or-unknown=DENY_UNVERIFIED_TOKEN
wrong-audience=DENY_UNVERIFIED_TOKEN
wrong-issuer=DENY_UNVERIFIED_TOKEN
missing-write-scope=DENY_SCOPE
cross-tenant=DENY_RESOURCE_SCOPE
locked-write=DENY_LOCKED
~~~

Explanation:
1. The request asserts `subject=admin` and `role=SUPER_ADMIN`, yet the verified token is `issuerA|an`; An reads her own document **not because of the forged claims**.
2. An has only READ tenant permission despite the token carrying WRITE scope: `forged-admin-write` is blocked.
3. An claiming `clientClaimedSubject=binh` does not make An the owner of document 43.
4. An holds a READ share grant on document 47, so `shared-read` ALLOWs.
5. An unknown token marker not in the trusted verifier ⇒ unauthenticated, even when claiming admin.
6. Wrong audience/issuer are blocked at the token boundary.
7. Missing WRITE scope is blocked before object checks.
8. A document in `south` when targeting `north` → blocked.
9. A locked document blocks WRITE even when Carol holds both scope and tenant permission.

**Critical limitation:** The demo's verifier is a server-held fixture table merely simulating trusted token identity. Production must use a cryptographically verified `JwtDecoder` or OAuth2 introspection over TLS with required validators. Never let an attacker pick or modify a server-issued lookup table, and never accept a `verified=true` boolean from the body. These results do not replace framework integration tests.

## 30. Test real token validation—do not only mock `Jwt`

Spring Security Test provides a convenient `jwt()` helper to create mock `Authentication` objects when testing HTTP/method authorization:

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
class ScopeAuthorizationTests {
    @Autowired MockMvc mvc;

    @Test
    void noReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/42")
                .with(jwt().authorities()))
            .andExpect(
                org.springframework.test.web.servlet.result
                    .MockMvcResultMatchers.status().isForbidden());
    }
}
~~~

**Spring Test snippet** requiring Spring Boot Test/Security Test dependencies and matching endpoints/filter chain. Mocks can bypass the real JWT decoding path, so the test verifies only authority/service behavior for the fixture—**it does not prove signature, issuer, audience, or `exp` are verified**.

To verify token verification, use signed test tokens and a test issuer/JWKS or decoder tests checking validators:
- Valid/invalid token signatures and algorithms outside the allow-list.
- `kid` missing from trusted JWKS and malicious `jku`/`x5u`.
- Wrong issuer/audience; expired or future `nbf`.
- OIDC ID token submitted in place of OAuth access token.
- Token from another issuer with the same `sub`.
- Wrongly typed/missing scope claims and unusual whitespace.
- Opaque introspection `active=false`, malformed responses, and endpoint timeouts.
- Responses lacking verification proof never create an `Authentication`.
- Controller paths cannot bypass the security filter chain.

When testing endpoints, **also assert that database/outbox/side effects remain unchanged** on denied requests, not just the status code.

## 31. Trust-boundary test matrix

| Request/token | Trusted identity? | Coarse action? | Resource policy? | Expected |
|---|---|---|---|---|
| Valid JWT + owner + right tenant | Yes | Pass | Pass | ALLOW |
| Body `isAdmin=true`, regular user | Regular user | Unchanged | Per real policy | No self-escalation |
| Header `X-Role=ADMIN`, regular user | Regular user | Unchanged | Per real policy | DENY if lacking rights |
| Different tenant URL | Identity still valid | May pass | Membership/tenant FAIL | DENY |
| Base64URL-decoded JWT without verification | **No** | Not evaluated | Not evaluated | 401 |
| Tampered JWT payload, invalid signature | **No** | Not evaluated | Not evaluated | 401 |
| Valid signature, wrong issuer | **No** | Not evaluated | Not evaluated | 401 |
| Valid issuer, wrong audience | **No** | Not evaluated | Not evaluated | 401 |
| Expired JWT or future `nbf` | **No** | Not evaluated | Not evaluated | 401 |
| Frontend ID token sent to API | **No** | Not evaluated | Not evaluated | 401 |
| JWT missing WRITE scope | Yes | FAIL | Not evaluated | 403 |
| JWT has WRITE scope, tenant role is READ only | Yes | HTTP may pass | Tenant role FAIL | DENY |
| JWT READ scope, another owner's object, no grant | Yes | Pass | FAIL | 403/404 |
| JWT READ scope, resource in another tenant | Yes | Pass | FAIL | 403/404 |
| JWT WRITE scope, resource LOCKED | Yes | Pass | FAIL | DENY/conflict |
| Opaque token `active=false` | No | Not evaluated | Not evaluated | 401 |
| Introspection timeout | Unverifiable | Not evaluated | Not evaluated | Fail closed |
| Client credentials, no human user | Workload | Depends on scope | Workload policy | Do not assign human owner |
| Spoofed identity header sent directly to backend | Untrusted | Not evaluated | Not evaluated | Blocked at gateway/backend |
| Token revocation occurs after issuance | JWT may be unexpired | May pass | Membership/ACL re-check | DENY per revocation SLA |
| Issuer B JWT shares `sub` with issuer A | B if trusted | Depends on scope | Different namespace | No owner confusion |
| Token meant for API A sent to API B | No at B | Not evaluated | Not evaluated | 401 |

Also test boundary protections, not only validators:
- Bypassing the gateway with a direct backend request.
- Self-invocation in method security.
- Queues/jobs taking an actor from a message body without verifying delegation.
- Cache keys failing to distinguish user, tenant, action, and resource.
- Concurrent grant revocation while a request is executing.
- Policy backend errors where code accidentally returns `true`.

## 32. Distinguishing 401, 403, 404, and technical errors

| Error | Meaning | Typical HTTP |
|---|---|---|
| Missing/invalid Bearer token | Authentication not established | 401/challenge |
| JWT wrong issuer/audience/signature/time | Invalid credential | 401 |
| Valid token lacking scope/role | Authorization denial | 403 |
| Valid token and scope, out-of-scope resource | Object-level denial | 403/404 per anti-disclosure policy |
| Stale resource version | Concurrency/business | 409 or appropriate code |
| Decoder/introspection unavailable | Technical authn failure | 5xx/503, do not execute |
| PDP/ACL DB unavailable | Technical authz failure | 5xx/503, do not execute |

RFC 6750 defines Bearer token errors such as `invalid_token` and `insufficient_scope`. Never expose raw exception messages, token strings, or ACL graphs to clients.

An issuer mismatch must never be "fixed" by granting `ROLE_ADMIN`. An object ACL failure must never be "fixed" by dropping the audience validator. Diagnosing at the right layer avoids replacing security controls with `permitAll()` upon seeing 401/403.

## 33. Logs, telemetry, and protecting personal information

Do not log:
- Raw `Authorization: Bearer`, access/refresh/ID tokens.
- Cookie/session tokens or query parameters containing credentials.
- Full `Jwt` claims/`Authentication` objects from requests.
- Private signing keys, JWKS secrets, or introspection credentials.
- Owners, ACLs, confidential document titles, or out-of-scope tenants.
- Exception stack traces in public responses.

Safe to log in a controlled manner:
- Events `AUTHN_INVALID_SIGNATURE`, `AUTHN_INVALID_AUDIENCE`.
- `AUTHZ_INSUFFICIENT_SCOPE`, `AUTHZ_RESOURCE_DENIED`.
- Policy version/decision ID, request correlation ID.
- Opaque actor alias if needed, tenant/resource type per audit permissions.
- HTTP endpoint/service and enforcement outcome.

Audit stores must also be protected with least privilege, retention, and export controls; a correlation ID is not permission to read audits. Never log all headers merely to prove a caller tried spoofing `X-Role`; if incident logging is needed, sanitize, bound, and redact tokens/PII.

## 34. Common mistakes

**1. Trusting `roles` or `isAdmin` from JSON body.** Clients can alter them. Use verified `Authentication` and trusted policy.

**2. Trusting `X-User-Id`/`X-Role` from public requests.** Headers are unsigned. Use trusted gateway propagation protected against bypass/forgery.

**3. Base64URL-decoding a JWT and granting roles.** Decoding does not verify. Use `JwtDecoder`/introspection.

**4. Verifying only signature while skipping issuer/audience/type/expiry.** Tokens may belong to another API or be expired.

**5. Accepting `alg=none` or token-chosen algorithms.** Restrict allowed algorithms and trusted keys.

**6. Fetching arbitrary `jku/x5u` URLs.** SSRF/key injection. Use trusted JWKS only.

**7. Treating `kid` as safe path/SQL input.** Attacker-controlled headers require validation and bounds.

**8. Accepting an OIDC ID token as an OAuth access token.** Wrong type and audience. Enforce token profiles.

**9. Thinking `SCOPE_documents.read` grants read access to all documents.** BOLA. Enforce tenant/owner/ACL.

**10. Turning tenant A roles into global `ROLE_ADMIN`.** Cross-tenant leakage. Scope roles to their tenant.

**11. Relying on `sub` without an issuer namespace.** Multi-issuer collision.

**12. Using `Authentication.isAuthenticated()` in place of policy.** Only establishes authentication state.

**13. Ignoring membership revocation because the JWT is unexpired.** Token validity differs from permission freshness.

**14. Treating introspection timeout as `active=true`.** Fail-open.

**15. Using `@PreAuthorize` followed by bare-ID UPDATE.** Missing mutation guard/TOCTOU.

**16. Testing with mock `jwt()` and assuming crypto passes.** Requires validator integration tests.

**17. Caching tokens/`Authentication` in singletons.** Can leak identities across requests.

**18. Forwarding an `aud=serviceA` token to `serviceB`.** B must validate its own audience or use token exchange.

**19. Fixing every 403 with `permitAll()`.** Opens access instead of fixing the root cause.

**20. Logging full Bearer tokens to debug.** Credential leakage and replay risk.

## 35. Pre-merge checklist

- [ ] No authorization grant relies on client-asserted `X-Role`, `X-User-Id`, `isAdmin`, `ownerId`, or `approved`.
- [ ] Raw tokens are validated before building principals or authorities.
- [ ] Decoder/introspector trusts only the right issuer, keys, algorithms, and token profile.
- [ ] `iss`, `aud`, `exp`, `nbf`, and access token type are validated per contract.
- [ ] JWT headers `kid`/`jku`/`x5u` cannot cause injection, SSRF, or key substitution.
- [ ] Access tokens are distinguished from ID tokens and refresh tokens.
- [ ] Only verified scope/role claims are mapped to `GrantedAuthority`.
- [ ] Tenant roles are never applied globally out of scope.
- [ ] Multi-issuer identities are namespaced by `issuer+subject`.
- [ ] Request tenants are verified via active membership.
- [ ] Owner/ACL/resource state comes from a trusted server DB/PIP.
- [ ] READ/list/export/count and WRITE/DELETE all enforce object policies.
- [ ] Guarded transactions protect against stale permissions and TOCTOU as needed.
- [ ] Opaque token introspection never fails open on timeout/`active=false`.
- [ ] Gateways strip/overwrite client identity headers, and backends cannot be bypassed.
- [ ] Downstream services validate their own audiences instead of blindly forwarding credentials.
- [ ] Client-credentials workloads are distinguished from human users.
- [ ] Cookie-based JWTs and Bearer-only APIs have appropriate CSRF threat models.
- [ ] Security contexts stay scoped per request/subscription without cross-request identity caching.
- [ ] Unit tests cover claim forgery and object owner/tenant checks.
- [ ] Integration tests exercise real JWT validation, not only mock `jwt()`.
- [ ] Verify 401/403/404/5xx behavior and zero side effects when denied.
- [ ] No unnecessary tokens/PII/secrets in logs; audit stores have access control.
- [ ] Security regression tests cover key rotation, revocation, and policy outages.

**Conclusion:** A client can put any string like `ADMIN`, `owner`, or `verified` into an HTTP request; doing so creates zero authority. A JWT payload can be decoded, yet remains **untrusted** until cryptographic trust, issuer, audience, timestamps, and token type are verified. Once Spring Security validates the token, the application has a trusted actor/client identity **for the next authorization step**: scopes, tenant roles, owner/ACLs, and resource state must still be verified independently. Enforcing this boundary with fail-closed behavior, scoped queries, guarded mutations, and thorough tests prevents privilege escalation and BOLA even when an attacker crafts convincing claims.

## References

- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decode/verify, issuer, JWKS, authorities, and audience.
- [Spring Security — OAuth2 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and WebFlux.
- [Spring Security — OAuth2 Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and active status.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` and method policies.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithms, issuer/audience, token typing, `kid`/`jku`/`x5u`, and claim trust.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token profile and token type.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials and errors.
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active status and metadata.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): checking permissions on object IDs.
- [OWASP — JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): keys, token handling, claim validation, and revocation.
