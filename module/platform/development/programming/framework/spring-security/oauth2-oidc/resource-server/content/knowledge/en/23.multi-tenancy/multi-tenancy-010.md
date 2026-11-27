# Adding, revoking tenants, and the trusted configuration lifecycle

A **Spring Security OAuth 2.0 / OIDC Resource Server** serving multiple tenants may need to validate Access Tokens from multiple Authorization Servers (AS), OIDC realms, or issuers. A bigger problem than configuring multiple JWT decoders is **determining when a tenant or issuer is permitted to become a trusted source**, and **how to stop trusting it once suspended or revoked**, even when old tokens remain unexpired and decoders are already cached.

Example order-management SaaS serving:

| Tenant | Approved issuer | Trust status |
| --- | --- | --- |
| `alpha` | `https://id.alpha.example.test/realms/main` | ACTIVE |
| `beta` | `https://login.beta.example.test/oauth2` | ACTIVE |
| `gamma` | `https://identity.gamma.example.test` | SUSPENDED |

A validly signed JWT from gamma **must not continue granting access** once gamma is suspended. Likewise, a JWT from a brand-new issuer **must not automatically make the Resource Server fetch JWKS and accept that issuer**, even if its signature verifies against a key published by that issuer itself.

**Core principle:** *Issuer, JWKS URI, audience, and tenant acceptance rights are security configurations managed by the control plane—not data that an unauthenticated request or token can self-declare to gain trust.*

This lesson focuses on **adding, activating, suspending, revoking, migrating, and retiring tenants**, designing a **versioned trusted registry**, JWT verification boundaries, `AuthenticationManager`/`JwtDecoder` caching, multi-replica synchronization, issuer-confusion/SSRF flaws, state testing, and operational procedures. Examples use **Java 17+, Spring Boot 3.x, and Spring Security 6.x**, primarily with a **Servlet Resource Server**; the end covers the WebFlux equivalent.

## 1. Distinguishing tenant, issuer, audience, and principal

A **Tenant** is the customer/organization and data boundary within the application. An **Issuer** is the entity minting Access Tokens, identified by `iss`. **Audience** specifies which resource the token targets. **Subject** `sub` identifies the principal within the issuer's scope. A **JWT signature** proves the token was signed by the corresponding key, yet only has meaning after the Resource Server determines **which keys/issuers are trusted**.

~~~text
Tenant alpha
  localTenantId = 6dca...
  issuer        = https://id.alpha.example.test/realms/main
  audience      = orders-api
  users/orders  = alpha's private data

Tenant beta
  localTenantId = a28e...
  issuer        = https://login.beta.example.test/oauth2
  audience      = orders-api
  users/orders  = beta's private data
~~~

Do not assume a strict 1-to-1 relationship:

- **One issuer serving many tenants:** e.g., companies sharing one IdP. Here `iss` is insufficient to determine the tenant.
- **One tenant with multiple temporarily valid issuers:** e.g., during migration to a new IdP; manage each binding with time limits and separate policies.
- **One issuer with multiple client IDs and multiple audiences:** a validly signed token is not necessarily meant for the current API.
- **Same `sub` across two issuers:** may represent two completely different people. To link internal accounts, use the **verified `(iss, sub)` pair**, not `sub` or email alone.

### 1.1. Four independent security questions

| Question | Where does the decision come from? | Example |
| --- | --- | --- |
| Is the tenant currently served? | Approved **trusted tenant registry**. | Gamma SUSPENDED → reject. |
| Is the token trustworthy? | Decoder/introspection from trusted issuer/JWKS, `aud`, `exp`, algorithms. | Alpha JWT has valid signature and audience. |
| Does the principal have access to this tenant? | Verified claims + local account/membership. | User-42 is an alpha employee. |
| Does the principal have access to the specific resource? | HTTP scopes + domain authorization. | Order-77 belongs to alpha and caller may read it. |

An **ACTIVE tenant** is only the first condition. It does not automatically grant all scopes or turn that tenant's records into public property.

## 2. Why must you never trust an issuer taken from a JWT?

The JWT payload is readable before signature verification. An attacker can easily craft:

~~~json
{
  "iss": "https://id.attacker.example.test",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "admin.manage"
}
~~~

Suppose the application has this flawed logic:

~~~text
Receive JWT
   |
   v
Read unverified iss
   |
   v
Automatically fetch /.well-known/openid-configuration of iss
   |
   v
Retrieve jwks_uri of attacker-controlled issuer
   |
   v
Verify JWT using attacker's public key
   |
   v
Accept token and scope admin.manage  <-- VULNERABILITY
~~~

A signature valid against a public key **is insufficient** if the token itself gets to choose its own public key. An issuer may only be used for authentication after **control-plane approval**.

### 2.1. Inputs that can be spoofed

| Input | Trusted before token validation? | Safe usage |
| --- | --- | --- |
| JWT `iss` claim | **No** | May act as a *routing hint* when matched against a trusted allowlist; must be re-validated post-decode. |
| JWT `kid` header | **No** | Selects a key inside **configured JWKS**, never selecting a new JWKS source. |
| JWT `jku` or `x5u` header | **No** | Never send HTTP requests to token-declared URLs. |
| Pre-verification `tenant_id`, `sub`, `scope` claims | **No** | Use only after JWT signature/issuer/audience validation. |
| Path `/api/tenants/alpha` | **Not a permission** | Selects *tenant candidate* in registry, followed by token/membership verification. |
| `X-Tenant-ID` header | **No** | Never replaces login, issuer, or account membership. |
| `Host`/`X-Forwarded-Host` from Internet | Can be spoofed / misconfigured proxy | Use only with trusted gateway/canonical host routing. |
| Approved registry snapshot | **Yes**, when source, integrity, and version are controlled | Selects issuer/JWKS/audience and allowed policies. |

### 2.2. Risks to design against from the start

1. **Issuer confusion:** an arbitrary issuer is accepted simply because the JWT claims `iss`.
2. **SSRF:** the app fetches metadata/JWKS from client-controlled URLs, hitting localhost, private IPs, cloud metadata endpoints, or internal hosts.
3. **Algorithm confusion:** switching issuers or permitting algorithms outside policy approval.
4. **Cross-tenant BOLA:** A's valid token reads B's orders because only scope was checked.
5. **Stale trust cache:** a cached `AuthenticationManager` keeps accepting an issuer after the tenant is REVOKED.
6. **Configuration replay:** a node receives an older ACTIVE event after a newer REVOKED event and accidentally re-enables the tenant.
7. **Unauthorized administration:** a public API or business admin is allowed to edit issuer/JWKS URIs without security approval.

## 3. Separating the control plane from the data plane

A multi-tenant system should maintain **two boundaries**:

~~~text
                 CONTROL PLANE
  Tenant onboarding / Security administration
          |
          +-- Verify ownership
          +-- Verify issuer/JWKS/audience/alg
          +-- Approval / audit / revision
          +-- ACTIVE / SUSPENDED / REVOKED
          |
          v
   Trusted configuration snapshot
          |
      +---+--------------------+
      |                        |
 Resource Server A        Resource Server B
      |                        |
      +------------+-----------+
                   |
                DATA PLANE
                   |
 HTTP Bearer -> trusted tenant check -> JWT verification
                   |
              scope + domain policy
                   |
              customer data
~~~

The **control plane** controls *which issuers the system will trust*. The **data plane** only consumes approved snapshots to authenticate requests and never auto-registers an issuer upon seeing a new token.

The configuration source can be a database with an admin service, reviewed GitOps, or a configuration service. Whatever technology is chosen, require **RBAC/approval**, auditing, validation, versioning, distribution, and revocation mechanisms.

### 3.1. Security configuration is not a regular "tenant profile"

Changing a tenant's display name carries far less risk than changing `jwkSetUri`: anyone able to point the JWKS URI to their own key can make the Resource Server trust self-signed tokens. Therefore, fields like:

- Issuer/JWKS URI and JWS algorithms.
- Audience/resource and token profile.
- Introspection auth policies for opaque tokens.
- ACTIVE/SUSPENDED/REVOKED status.

must be governed as **trust configuration**, never editable via normal business profile endpoints.

## 4. State machine of the tenant trust lifecycle

A system may define:

~~~text
REQUESTED
    |
    v
VERIFYING
    |
    v
APPROVED
    |
    v
ACTIVE -------------------> REVOKED --> RETIRED
    |
    v
SUSPENDED
    |
    +-- re-verification / approval --> ACTIVE (new revision)
    |
    +-----------------------------> REVOKED
~~~

This is an **application state machine**, not built-in Spring Security or OAuth states.

| State | Meaning | Are tokens allowed to authenticate? |
| --- | --- | --- |
| `REQUESTED` | Tenant creation requested. | **No.** |
| `VERIFYING` | Checking IdP, ownership, and security contract. | **No.** |
| `APPROVED` | Approved but not yet activated/distributed. | **No.** |
| `ACTIVE` | Permitted to proceed to JWT validation per active config. | **Conditionally yes.** |
| `SUSPENDED` | Temporarily paused due to incident or business process. | **No.** |
| `REVOKED` | Trust revoked. | **No.** |
| `RETIRED` | Decommissioned, retaining tombstone/audit. | **No.** |

The code rule must be **allow only ACTIVE**, never "allow any state except REVOKED." If the state is null, unknown, or corrupted, **fail closed**.

### 4.1. SUSPENDED differs from REVOKED, yet both must block traffic

`SUSPENDED` can be re-enabled after review; `REVOKED` typically ends trust or responds to a serious incident. Nevertheless, both must block **new requests** on the data plane. The difference lies in **reactivation policy, approval, and auditing**, never in letting tokens slip through while awaiting review.

### 4.2. Why are tombstones needed?

If a tenant row is hard-deleted from the database, a delayed old `ACTIVE` event could recreate the record and re-enable the tenant. Retaining `REVOKED`/`RETIRED` with a **higher revision** prevents replay attacks and uncontrolled reuse of slugs or issuers.

## 5. Trusted configuration data format

Example of an approved record:

~~~yaml
tenantKey: alpha
localTenantId: tenant-alpha-uuid
issuer: https://id.alpha.example.test/realms/main
jwkSetUri: https://id.alpha.example.test/realms/main/protocol/openid-connect/certs
audience: orders-api
allowedJwsAlgorithms:
  - RS256
status: ACTIVE
revision: 18
approvedBy: security-approver
approvedAt: "2026-11-15T08:30:00Z"
~~~

| Field | Meaning | Requirement |
| --- | --- | --- |
| `tenantKey` | Routing slug. | Canonical, unique, never used as permission proof. |
| `localTenantId` | Tenant ID in database. | Used to partition data, never taken from client bodies. |
| `issuer` | Permitted JWT `iss`. | Exact match, approved URL. |
| `jwkSetUri` | JWKS fetching public keys. | HTTPS/allowlist, never taken from JWT headers. |
| `audience` | Required resource ID in `aud`. | Mandatory check. |
| `allowedJwsAlgorithms` | Allowed algorithm list. | Reject `none`/downgrades. |
| `status` | Tenant acceptance state. | **ACTIVE only**. |
| `revision` | Tenant config version. | Incremented whenever issuer/JWKS/audience/status changes. |
| Approval/audit | Who approved, when, why. | Trusted source with RBAC and integrity. |

**Configuration must have a single trusted source.** A token carrying a matching `tenant_id` or issuer string can never alter the contents of this table.

## 6. Workflow to add a tenant from scratch to ACTIVE

Suppose tenant `delta` wants to use `https://id.delta.example.test/realm`.

### 6.1. Accepting the request does not activate trust

~~~text
createTenant(
  tenantKey = delta,
  candidateIssuer = https://id.delta.example.test/realm
)

status = REQUESTED
revision = 1
canAuthenticateInProduction = false
~~~

This is only a **request**. Never let `POST /admin/tenants` automatically build a JWT decoder on arrival, even if the requester presents an unexpired token.

### 6.2. Verifying ownership and administrative authority

Depending on the system:

- Confirm the requester is authorized to represent the organization.
- Verify domain ownership or IdP registration control.
- Cross-check contracts, organization IDs, and tenant owners.
- Require two-person approval for sensitive trust changes.
- Separate **security platform admin** privileges from employee/order management privileges.

An email matching the tenant's domain or an `email_verified=true` claim **does not prove** the caller is authorized to make the SaaS trust a new issuer.

### 6.3. Validating issuer and metadata in the control plane

Only after the candidate passes administrative checks do you query metadata/discovery. Verify:

1. **HTTPS** with full TLS certificate and hostname verification.
2. Host satisfies egress policies/allowlists.
3. Disallow URLs resolving to loopback, link-local, private IPs, or cloud metadata endpoints without an approved network mechanism.
4. Never follow redirects to disallowed hosts.
5. Protect against DNS rebinding and resolve hostnames per network policy.
6. Published metadata `issuer` **matches the approved issuer**.
7. `jwks_uri` is an allowed HTTPS endpoint; cap response size, redirect depth, and timeouts.
8. Never use user-submitted JWT `iss` claims or `jku` headers to pick fetch targets.

OIDC Discovery and OAuth Authorization Server Metadata help locate configuration for an **already trusted** issuer; they do not replace the approval workflow.

### 6.4. Validating the token contract

Agree on:

- Exact `iss` issuer string (including path/realm).
- Audience `aud` targeting the right Resource Server.
- Token type: **OAuth 2.0 Access Token**, never substituting an ID Token.
- Signing algorithms, JWKS key rotation, and `kid`.
- `exp`, `nbf`, clock skew, and token lifetime.
- Mapping `scope`/`scp` → `SCOPE_...` authorities.
- Identifying user/service principals, tenant membership, and local accounts.
- Sender-constrained tokens if the architecture uses mTLS or DPoP.

**A valid signature is not enough** when `aud` targets another API or the token type is wrong.

### 6.5. Sandbox testing before activation

In an isolated test environment:

~~~text
Valid signed Access Token with matching issuer/aud -> accepted
Invalid signature -> rejected
Wrong issuer -> rejected
Wrong audience -> rejected
Expired token -> rejected
Unknown tenant -> rejected
Other tenant's account/order -> rejected
~~~

Never enable a new issuer in production merely to test whether token signing works.

### 6.6. Approval, publication, and activation

Transitioning `VERIFYING → APPROVED → ACTIVE` must involve:

1. Administrative permissions and approvals.
2. Monotonically increasing tenant revision.
3. A new immutable trusted configuration snapshot.
4. Auditing actor, approver, timestamp, reason, and old/new states.
5. Distributing the snapshot to Resource Server instances.
6. Canary/health checks for decoder/JWKS and tenant routing.
7. Confirming rollout completion before sending production tenant traffic.

In asynchronously distributed systems, the Admin UI should distinguish **"control-plane change committed"** from **"applied by all serving nodes"**; never declare rollout complete while stale replicas remain.

## 7. Publishing configuration via immutable snapshots and revisions

If `issuer`, `jwksUri`, `audience`, and `status` are updated independently, a request can observe a **new issuer with an old JWKS**. A safer pattern is **building a new validated snapshot**, then swapping atomically.

### 7.1. Java model

~~~java
import java.net.URI;
import java.util.Map;

enum TenantState {
    REQUESTED, VERIFYING, APPROVED,
    ACTIVE, SUSPENDED, REVOKED, RETIRED
}

record TenantTrustConfig(
    String tenantKey,
    String localTenantId,
    String issuer,
    URI jwksUri,
    String audience,
    long revision,
    TenantState state
) {
    boolean acceptsTokens() {
        return state == TenantState.ACTIVE;
    }
}

record TenantTrustSnapshot(
    long generation,
    Map<String, TenantTrustConfig> tenants
) {
    TenantTrustSnapshot {
        tenants = Map.copyOf(tenants);
    }
}
~~~

`Map.copyOf` keeps the map immutable for consumers. These records hold **trusted values post-validation**; they do not prove on their own that a URI is safe or that the snapshot came from an authorized control plane.

### 7.2. Atomic registry

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

public final class TrustedTenantRegistry {

    private final AtomicReference<TenantTrustSnapshot> current =
        new AtomicReference<>(
            new TenantTrustSnapshot(0, Map.of()));

    public Optional<TenantTrustConfig> findActive(String key) {
        TenantTrustConfig config =
            current.get().tenants().get(key);

        return config != null && config.acceptsTokens()
            ? Optional.of(config)
            : Optional.empty();
    }

    public long generation() {
        return current.get().generation();
    }

    public void publishApprovedSnapshot(
            TenantTrustSnapshot candidate) {

        // Call ONLY from a trusted control-plane adapter:
        // verify origin, approval, schema, and integrity first.
        for (;;) {
            TenantTrustSnapshot old = current.get();

            if (candidate.generation() <= old.generation()) {
                throw new IllegalArgumentException(
                    "Old or replayed tenant trust configuration");
            }

            if (current.compareAndSet(old, candidate)) {
                return;
            }
        }
    }
}
~~~

**Effect:** a node never accidentally accepts a **lower-generation** snapshot after receiving a newer revocation. Publishing via `AtomicReference` ensures requests within a JVM see **one consistent snapshot**, never mixing old and new fields.

**Limitations:** this sample code omits admin authorization, persistent storage, and snapshot signatures. Production must protect the update adapter and prevent calling public methods with unverified data. `generation` must be generated **monotonically at the source of truth**; per-replica counters are insufficient for cluster-wide consistency.

### 7.3. Two kinds of version numbers

**Tenant revision** increments when a specific tenant's state, issuer, JWKS, audience, or policy changes.

**Global generation** increments whenever the entire trusted config snapshot changes.

Cache managers by `(tenantKey, revision)` so an old decoder is never used after a tenant's config changes. Use global generation to handle out-of-order snapshots, node recovery, and rollout verification.

## 8. Locating a tenant from the request: a locator is not authorization

Applications commonly route using:

- URL path: `/api/tenants/alpha/orders/42`.
- Hostname: `alpha.api.example.test` behind a trusted gateway.
- Unverified `iss`, **strictly as a hint** to pick an issuer already in the registry.

Path example:

~~~http
GET /api/tenants/alpha/orders/42
Authorization: Bearer ACCESS_TOKEN
~~~

Flow:

~~~text
Route alpha
   |
   v
registry.findActive("alpha")
   |
   +-- empty -> reject
   |
   v
alpha's issuer/JWKS/audience config
   |
   v
JWT verification (signature, iss, aud, exp, alg)
   |
   v
Cross-check principal against alpha membership
   |
   v
Read order by (tenantId=alpha, orderId=42, permissions)
~~~

Simply changing the path from `alpha` to `beta` **must never switch permissions to beta**. Beta's decoder must reject alpha's issuer if issuers differ; if they share an issuer, **membership and domain policy** must block access.

### 8.1. Trusted routers and Host headers

When deriving the tenant from `Host`/`X-Forwarded-Host`, the gateway must:

- Permit only registered hosts and matching SNI/TLS.
- Strip or overwrite `Forwarded`/`X-Forwarded-Host` from untrusted Internet sources.
- Never let user headers dictate issuer/JWKS URLs.
- Canonicalize hostnames, paths, and URL encoding prior to routing.
- Ensure the locator and API domain authorization use the same internal tenant ID.

The slug in the URL only identifies a tenant candidate. It **does not prove the user is a member** of that tenant.

## 9. Caching `AuthenticationManager`: pitfalls when revoking a tenant

In Spring Security Servlet, **`AuthenticationManagerResolver<HttpServletRequest>`** can select an authentication manager per tenant. Each issuer's manager may contain a `NimbusJwtDecoder`, JWKS cache, and validators.

The problem:

~~~text
T0: alpha ACTIVE, revision 7
T1: Resolver creates manager and caches in map["alpha"]
T2: Control plane moves alpha to REVOKED
T3: map["alpha"] still holds the old manager
T4: alpha JWT still has valid exp and signature
T5: If resolver returns old manager without checking status
    -> Tokens for a revoked tenant could still be accepted!
~~~

Simply **removing an issuer from a list** or **deleting a DB row** does not guarantee cached managers stop working. You need a **runtime ACTIVE gate on every request**, paired with revisioned caching/invalidation.

### 9.1. Tenant locator contract

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;

public interface TenantRequestLocator {
    Optional<String> locate(HttpServletRequest request);
}
~~~

Implementations of `locate` must extract canonical tenant keys from trusted routing, validate slugs/paths/URL encoding, and never treat the result as a permission. Never concatenate URLs from a tenant key.

### 9.2. Versioned manager cache and runtime gate

Example using Caffeine to bound memory:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Duration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

record ManagerKey(String tenantKey, long revision) {}

public final class TrustedTenantManagerResolver
        implements AuthenticationManagerResolver<HttpServletRequest> {

    private final TrustedTenantRegistry registry;
    private final TenantRequestLocator locator;

    private final Cache<ManagerKey, AuthenticationManager> managers =
        Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterAccess(Duration.ofMinutes(30))
            .build();

    public TrustedTenantManagerResolver(
            TrustedTenantRegistry registry,
            TenantRequestLocator locator) {
        this.registry = registry;
        this.locator = locator;
    }

    @Override
    public AuthenticationManager resolve(HttpServletRequest request) {
        String tenantKey = locator.locate(request)
            .orElseThrow(() -> new BadCredentialsException(
                "Tenant is not accepted"));

        TenantTrustConfig config = registry.findActive(tenantKey)
            .orElseThrow(() -> new BadCredentialsException(
                "Tenant is not accepted"));

        ManagerKey key =
            new ManagerKey(tenantKey, config.revision());

        AuthenticationManager delegate = managers.get(
            key, ignored -> createManager(config));

        // Never return the cached delegate directly.
        // Re-check so stale config cannot serve as fresh trust.
        return authentication -> {
            requireCurrentRevision(tenantKey, config.revision());
            var result = delegate.authenticate(authentication);
            requireCurrentRevision(tenantKey, config.revision());
            return result;
        };
    }

    private void requireCurrentRevision(
            String tenantKey, long expected) {
        TenantTrustConfig now = registry.findActive(tenantKey)
            .orElseThrow(() -> new BadCredentialsException(
                "Tenant is not accepted"));

        if (now.revision() != expected) {
            throw new BadCredentialsException(
                "Tenant trust revision changed");
        }
    }

    private AuthenticationManager createManager(
            TenantTrustConfig config) {

        // Only the JWKS URI approved by the control plane.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(config.jwksUri().toString())
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(config.audience())
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        OAuth2ErrorCodes.INVALID_TOKEN,
                        "Audience not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(
                    config.issuer()),
                audienceValidator));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        return provider::authenticate;
    }
}
~~~

**Rationale behind these decisions:**

- `registry.findActive` checks **ACTIVE on every request**, not only when the manager is first created.
- The cache key includes **tenant revision**, preventing reuse of an old manager after issuer/JWKS/audience/status changes.
- `requireCurrentRevision` re-checks before and after calling the manager to narrow race windows.
- The decoder takes the JWKS URI **solely from approved config**, never from a `jku` token header.
- `JwtValidators.createDefaultWithIssuer` enforces issuer and default checks; a dedicated validator checks audience.
- `jwsAlgorithm(RS256)` is an illustrative policy; if an issuer uses ES256, configure an approved algorithm allowlist rather than inferring algorithms from JWT headers.
- Caffeine bounds manager counts, yet you still need eviction/invalidation after configuration changes.

**Important limitation:** checking revision twice does not create an atomic barrier across revocation and the entire business operation. A request might finish authentication right before the control plane revokes, or a replica may not have received the new snapshot yet. When in-flight work must be halted, re-check domain state at sensitive steps or before commit; across replicas, enforce a rollout consistency policy.

### 9.3. Using `ConcurrentHashMap` also needs invalidation

`ConcurrentHashMap.computeIfAbsent` prevents constructing duplicate managers simultaneously. However, keying solely by tenant slug without revisions or eviction retains stale trust indefinitely. Whether using Caffeine or a plain map, a **per-request active check** is essential.

## 10. Integrating `AuthenticationManagerResolver` into `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiTenantApiSecurity {

    @Bean
    SecurityFilterChain tenantApiChain(
            HttpSecurity http,
            TrustedTenantManagerResolver resolver)
            throws Exception {

        http
            .securityMatcher("/api/tenants/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.authenticationManagerResolver(resolver));

        return http.build();
    }
}
~~~

**Note:** `securityMatcher("/api/tenants/**")` selects this chain for matching URLs; applications with other URLs must define corresponding chains or fallbacks. `anyRequest().denyAll()` inside this chain does not protect URLs outside the chain's matcher.

Disabling CSRF in this example is suitable only for **pure Bearer Authorization header APIs that do not rely on session cookies**; never copy that config to session-based OIDC Login web apps.

### 10.1. Spring Security provides `JwtIssuerAuthenticationManagerResolver`

Spring Security supports **`JwtIssuerAuthenticationManagerResolver`** to pick managers by JWT issuer. The issuer read from the JWT during routing remains an **unverified hint**, so trusted issuers are mandatory.

Example for versions with the matching factory method:

~~~java
// For a fixed, vetted set of issuers;
// verify exact API against your Spring Security version.
var issuerResolver =
    JwtIssuerAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://id.alpha.example.test/realms/main",
            "https://login.beta.example.test/oauth2");
~~~

Never use a resolver that creates decoders for **any self-declared `iss`**. If a resolver uses a `trustedIssuers.contains(issuer)` predicate that is evaluated **only when creating the manager initially** and then caches that manager, removing the issuer from the set may **fail to revoke the old manager**. For dynamic lifecycles, inspect your version's cache behavior, add a per-request trust gate, and test revoking a warmed manager.

### 10.2. Do not equate issuer with tenant

If alpha and beta share **the same issuer**, an issuer resolver authenticates both through one decoder. Afterward, the API **must still determine and enforce tenant membership** from verified data. A token with a valid `iss` does not grant access to every tenant sharing that issuer.

## 11. Domain authorization: an ACTIVE tenant is still not enough

Suppose the API receives:

~~~http
GET /api/tenants/alpha/orders/77
Authorization: Bearer TOKEN_OF_USER_A
~~~

After JWT validation:

~~~text
Valid and ACTIVE issuer
  AND valid signature/audience/lifetime
  AND has SCOPE_orders.read
  AND user A holds ACTIVE membership in alpha
  AND order 77 actually belongs to alpha
  AND user A is allowed to read order 77
~~~

**Never call `orders.findById(77)` and return it directly** when the database holds orders for multiple tenants. SQL must constrain records by internal tenant ID:

~~~sql
SELECT o.*
FROM app_order o
WHERE o.id = :orderId
  AND o.tenant_id = :trustedLocalTenantId
  AND o.owner_user_id = :trustedLocalUserId;
~~~

`:trustedLocalTenantId` comes from the **trusted registry**, and `:trustedLocalUserId` from mapping the **verified `(iss, sub)`** and membership. Never take `ownerUserId` from the client request body as proof of ownership.

For systems with support staff or admins, define explicit exceptions and enforce tenant boundaries; never create a global `ADMIN` role that accidentally bypasses all isolation.

### 11.1. Using `@PreAuthorize`

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @tenantPolicy.canRead(" +
    "authentication, #tenantKey, #orderId)")
public OrderDto readOrder(String tenantKey, UUID orderId) {
    return loadAuthorizedOrder(tenantKey, orderId);
}
~~~

`tenantPolicy` and `loadAuthorizedOrder` are application components **you must implement**; policy must rely on the verified Authentication, ACTIVE tenant config, and live database state. `@EnableMethodSecurity` must be enabled, methods invoked via Spring-managed proxies, and sensitive updates must re-check permissions/state inside the transaction.

## 12. Workflow to suspend or revoke a tenant

When tenant `gamma` must be blocked immediately:

~~~text
Security administrator
        |
        v
Control plane: gamma.status = REVOKED
               gamma.revision += 1
               globalGeneration += 1
               append audit event
        |
        v
Publish trusted snapshot / revocation event
        |
   +----+-----------------+
   |                      |
Replica A              Replica B
   |                      |
ACTIVE gate -> deny    ACTIVE gate -> deny
   |                      |
   +-----------+----------+
               |
               v
Unexpired gamma JWTs are still rejected
~~~

**Tenant trust revocation differs from revoking a single Access Token.** With self-contained JWTs, the Authorization Server may not revoke every token prior to `exp`; the Resource Server can still **stop trusting the entire tenant** via its registry gate.

### 12.1. Old managers and JWKS still sit in RAM

After revocation:

~~~text
Cached JwtDecoder gamma: still in memory
Cached JWKS keys gamma: still in memory
JWT gamma: valid signature, 20 minutes left on exp

registry.findActive("gamma") -> empty

Result: new authentication rejected
~~~

You do not have to wait for the JWK cache to expire to revoke trust. Evicting managers for resource hygiene is good, yet **one-time eviction cannot replace active checks**, because events can be dropped or concurrent requests may hold references.

### 12.2. Already-authenticated requests and running tasks

~~~text
T0: gamma request passes JWT authentication.
T1: Control plane revokes gamma.
T2: gamma request is updating an order.
~~~

A per-request trust gate protects **incoming requests**, without automatically rolling back committed transactions or cancelling running background jobs. When SLAs require halting work immediately:

- Re-check tenant state at critical domain/transaction boundaries.
- Consider kill-switches for streams, WebSockets, and scheduled jobs.
- Drain nodes still serving old generations out of load balancers.
- Handle idempotency, auditing, and transactions with existing side effects.

Never claim setting a tenant to REVOKED automatically undoes completed business operations.

## 13. Multiple replicas: revocation must reach all serving nodes

Example:

~~~text
Replica A: generation 92, gamma REVOKED
Replica B: generation 91, gamma ACTIVE
Replica C: disconnected, generation 88
~~~

If the load balancer keeps routing requests to B or C, the revoked tenant can still authenticate against **stale trust config**. This is a consistency/lifecycle issue, not a JWT signature failure.

| Approach | Pros | Risks to handle |
| --- | --- | --- |
| Periodic snapshot polling | Simple to implement. | Stale window equals polling interval. |
| Pub/sub events + reconciliation | Fast updates, recovers missed events. | Out-of-order events, offline nodes. |
| Centralized per-request ACTIVE check | Shrinks stale window. | Adds network dependency; fail closed on outage. |
| Push + acknowledged rollout barrier | Knows which nodes updated. | Needs orchestration / draining slow nodes. |
| Snapshots with max age / fail-closed expiry | Stale nodes stop trusting indefinitely. | Reduces availability if control plane goes down. |

A **revocation SLA** must state clearly: how quickly after REVOKED must **all new requests** be blocked? May stale snapshots serve traffic during a control-plane outage? For financial or administrative operations, answers must be stricter than for low-risk APIs.

### 13.1. Monotonic generation and stale deadlines

A snapshot can carry:

~~~text
generation: 92
issuedAt: 10:00:00
validUntil: 10:00:30
~~~

A node receiving a generation-90 `ACTIVE` event **must never roll back** its active generation-92 state. If a snapshot passes its deadline without updates, policy may require **failing closed** or pulling the node from traffic. Never keep trusting an ACTIVE state from a stale cache file indefinitely.

### 13.2. Emergency blocking and tombstones

On JWT signing key compromise:

1. Write `SUSPENDED` or `REVOKED` and increment revision.
2. Emit an emergency deny event and new snapshot.
3. Require acknowledgements or drain stale instances.
4. Prevent replay of older configs.
5. Keep tombstone/revocation records at least until all stale caches have expired per policy.

## 14. SSRF and JWKS rotation

Do not do this:

~~~java
// DO NOT DO THIS:
String issuer = unverifiedTokenClaims.getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

If the issuer is unapproved, the server can send outbound requests to attacker-controlled addresses. **Discovery must target only approved issuers**, with TLS, host/IP egress restrictions, redirect checks, timeouts, and response caps.

### 14.1. JWT `kid` is not a trust root

JWT header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

`kid` must only pick a key from the **control-plane-approved JWKS URI**. On an unknown `kid`, the decoder may refresh from the **trusted source**, never switching to an arbitrary `jku` URL inside the token.

### 14.2. Routine rotation vs. key compromise

**Routine rotation:** the issuer adds a new key, maintains an overlap of old and new keys per procedure, and decoders refresh JWKS from the existing trusted endpoint.

**Key compromise:** an attacker holds the old private key. Consider suspending the tenant, disabling the old key at the IdP, revoking tokens, shortening JWKS cache staleness, and inspecting manager caches. Never merely add a new key and assume old-key tokens are harmless.

Changing the **JWKS endpoint** or **issuer** itself is a **trust configuration revision change**, requiring re-validation and approval—not a routine cache refresh.

## 15. Migrating to a new issuer

Suppose `alpha` migrates:

~~~text
old issuer: https://old-idp.alpha.example.test/realm
new issuer: https://new-idp.alpha.example.test/realm
~~~

Safe workflow:

1. Register the new issuer binding in **VERIFYING**, not enabled yet.
2. Verify ownership, HTTPS, discovery, JWKS, algorithms, audience, and Access Token profile.
3. Prepare user linking by **`(iss, sub)`**, never auto-merging by matching email.
4. Approve a **dual-trust window** if needed, with a clear deadline and policy.
5. Never let the new issuer auto-grant tenant-wide permissions to unlinked users.
6. Monitor old vs. new issuer traffic ratios and mapping errors.
7. Stop issuing tokens from the old issuer and handle refresh/session/expiry per contract.
8. Revoke the old issuer binding, bump revision, and invalidate old managers.
9. Test that **old-issuer tokens with remaining `exp` are rejected**.
10. Retain audit/tombstone records and never roll back trust revoked for key compromise.

If old and new issuers assign different `sub` values for a user, do not infer the same person from `email_verified` alone; use an evidence-backed identity-linking/provisioning workflow.

### 15.1. Reactivation needs a new revision

Moving `SUSPENDED → ACTIVE` requires approval and re-verification. For `REVOKED`, policy may require **full re-onboarding**. Merely flipping status back to ACTIVE can allow **old unexpired JWTs** to authenticate again if they still validate against the issuer/JWKS. If old tokens must stay blocked, enforce a **minimum token issuance epoch**, denylist, IdP revocation, or issuer/key migration—bumping the Resource Server's config revision alone does not invalidate old JWTs.

## 16. Tenant trust vs. business data lifecycle

~~~text
Security trust:
  ACTIVE -> SUSPENDED -> REVOKED

Business/data:
  OPERATING -> OFFBOARDING -> ARCHIVED
  -> EXPORTED/DELETED per retention/legal hold
~~~

Revoking an issuer does not automatically mean deleting all customer data. Data may still need to be retained for audits, contracts, and retention policies. Conversely, still holding tenant data **is no reason** to keep an issuer ACTIVE.

Beyond JWT APIs, consider:

- Web sessions/cookies after OIDC Login.
- Long-lived SSE/WebSocket subscriptions.
- Message consumers and background jobs.
- Client-credentials service principals.
- Opaque token introspection caches.
- Local user/tenant memberships.

When a tenant is revoked, each channel needs a corresponding policy. Removing a JWT decoder does not automatically destroy previously created session cookies.

## 17. HTTP error handling and avoiding control-plane information leaks

| Scenario | Typical outcome |
| --- | --- |
| No Bearer token sent to protected endpoint | **401** Bearer challenge. |
| Untrusted issuer or non-ACTIVE tenant | Rejected; **401/404** per tenant anti-enumeration policy. |
| JWT wrong issuer/audience/signature/expiration | **401 invalid_token**. |
| Valid token missing OAuth scope | **403 insufficient_scope** where appropriate. |
| Valid scope, user outside tenant / wrong order owner | **403 or 404** per domain policy. |
| JWKS or config dependency unavailable | **Fail closed**; operational failures may map to 5xx/503. |
| Replica holding overly stale snapshot | Rejected or node removed from traffic per revocation SLA. |

Never expose details like `issuer=...`, `jwksUri=...`, or `revocationReason=compromised-key` to unauthenticated callers. Admin UIs may display status to **authorized administrators**, while Bearer APIs should emit safe, neutral messages.

**Fail closed:** whenever evidence is insufficient to prove a token is accepted, create no default principal and never fall back to an "accept any issuer" decoder.

## 18. State testing: always test warmed managers

| Test | What must be proven |
| --- | --- |
| Unknown issuer in token | No auto-registration, zero discovery calls to token-supplied URLs. |
| Tenant REQUESTED/VERIFYING/APPROVED | Not accepted on the data plane. |
| ACTIVE + valid issuer/aud/key/scope JWT | Passes authentication; domain policy still enforced. |
| ACTIVE + JWT from another issuer | **401**. |
| ACTIVE + wrong audience or expired | **401**. |
| JWT with internal URL in `jku` | Never fetched; uses trusted JWKS only. |
| Alpha token on beta route | Denied by issuer/membership checks. |
| Two tenants sharing an issuer | No membership/owner mixing. |
| ACTIVE → SUSPENDED, unexpired JWT | New requests are rejected. |
| ACTIVE → REVOKED with cached manager | **Still rejected**, even with valid signature and unexpired `exp`. |
| JWKS/issuer revision changed | Old-revision manager never treated as current trust. |
| Old-revision ACTIVE event arrives after REVOKED | Never downgrades version or reactivates. |
| Stale node past deadline | Fails closed or leaves traffic. |
| Control-plane outage while tenant non-ACTIVE | Tenant is not auto-activated. |
| Issuer migration, new `sub` and old email | Users not auto-linked by email alone. |
| Tenant reactivated while old tokens must stay blocked | Epoch/revocation policy blocks old tokens. |

### 18.1. The most important test: revoking after caches are warmed

~~~text
1. Registry: alpha ACTIVE, revision 10.
2. Send genuinely signed alpha JWT with valid issuer/aud.
3. Resolver creates and caches manager (alpha, 10).
4. Resend JWT -> authentication succeeds.
5. Publish snapshot alpha REVOKED, revision 11.
6. Send that exact same still-unexpired JWT.
7. Must be rejected, even though (alpha, 10) remains in cache.
8. Replay old ACTIVE snapshot -> does not reactivate.
~~~

If step 7 still succeeds, "deleting the tenant from the registry" **has not truly revoked trust**.

### 18.2. MockMvc `jwt()` does not verify the issuer registry

Example:

~~~java
mockMvc.perform(get("/api/tenants/alpha/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

`jwt()` in `spring-security-test` creates a mock `Authentication` for **authorization tests**, bypassing the JWT decoder and dynamic trust registry. It cannot test onboarding or revocation. Write integration tests sending **raw Bearer JWTs signed with test private keys** through a real decoder and test JWKS server, swapping snapshots between requests. Assert request/fetch counts on trusted endpoints and **zero fetches to attacker-declared issuers/JWKS**.

### 18.3. Testing multiple nodes

Simulate:

~~~text
Replica A: generation 92, alpha REVOKED
Replica B: generation 91, alpha ACTIVE

Expected:
  A denies new requests.
  B drains / fails closed before exceeding revocation deadline.
  Generation-90 ACTIVE event does not downgrade A or B.
  Control plane does not report rollout complete while B still serves.
~~~

For SSRF tests, use isolated test HTTP endpoints and fake DNS/redirects—**never call production cloud metadata URLs**.

## 19. WebFlux and opaque tokens: same trust principles

When implementing **Spring WebFlux**, replace Servlet components with:

- `SecurityWebFilterChain` / `ServerHttpSecurity`.
- `ReactiveAuthenticationManagerResolver<ServerWebExchange>` or the corresponding reactive issuer resolver.
- `ReactiveJwtDecoder` and validators.

The policy remains:

~~~text
ServerWebExchange
  -> Trusted tenant locator + ACTIVE gate
  -> Approved reactive decoder/config revision
  -> JWT signature/issuer/audience validation
  -> Reactive SecurityContext
  -> authorizeExchange + reactive domain authorization
~~~

Never call `block()` to load control-plane config on the event loop; use trusted snapshots with staleness policies or proper reactive sources. Never manually `subscribe()` and let the request proceed before tenant state is resolved.

With **opaque tokens**, trusted config must manage **introspection endpoint + Resource Server client credentials**. RFC 7662 `active:false` results are rejected; `active:true` introspection caches need bounded TTLs and must never keep admitting a REVOKED tenant. An **independent tenant status gate** is essential even when the Authorization Server does not yet know the tenant was offboarded.

## 20. Auditing, observability, and readiness

An internal audit event:

~~~json
{
  "eventType": "TENANT_TRUST_REVOKED",
  "tenantKey": "gamma",
  "previousRevision": 31,
  "newRevision": 32,
  "generation": 94,
  "actor": "security-admin-id",
  "reasonCode": "SECURITY_INCIDENT",
  "occurredAt": "2026-11-15T09:00:00Z"
}
~~~

**Never expose events with sensitive reasons to unauthorized callers.** Audits need integrity, retention, and RBAC.

Monitor:

- Current config generation on each serving instance.
- Nodes lagging behind the minimum accepted generation.
- Time from control-plane revocation to cluster-wide denial.
- Requests rejected due to inactive/unknown tenants.
- JWT issuer/audience/signature validation error categories.
- JWKS fetch latency, unknown `kid`, cache manager sizes, and evictions.
- Cross-tenant domain denials and 401/403 rates.

Never log raw Bearer Access Tokens, client secrets, private keys, or full personal JWT claims. Never use tokens or token fingerprints as public metric labels.

Instances should **fail readiness or be drained** when lacking a valid trusted snapshot, when a snapshot exceeds max staleness, or when a mandatory revocation generation fails to apply.

## 21. Operational runbooks

### 21.1. Adding a tenant

1. Create `REQUESTED` without enabling API token acceptance.
2. Verify ownership and admin permissions.
3. Validate HTTPS issuer/JWKS and SSRF protections.
4. Confirm token contract: issuer, audience, algorithms, scopes.
5. Run sandbox tests with both positive and negative tokens.
6. Perform approval/audit and create a new revision.
7. Publish the new immutable snapshot/generation.
8. Confirm serving replicas received the config.
9. Transition to `ACTIVE` and allow traffic.
10. Monitor 401/403s, JWKS errors, and cross-tenant denials.

### 21.2. Emergency tenant suspension or revocation

1. Authorized operator records reason and chooses `SUSPENDED` or `REVOKED`.
2. Increment tenant revision and global generation.
3. Publish state and emergency deny signal.
4. `ACTIVE` gate must reject **before invoking any cached JWT manager**.
5. Drain or fail closed replicas that miss the update deadline.
6. Address sessions, streams, jobs, service tokens, and opaque introspection caches.
7. Test a **validly signed, unexpired JWT** for the REVOKED tenant.
8. Inspect in-flight transactions/work and audit logs.
9. Record the time all nodes began denying and retain tombstone.

### 21.3. Reactivating or switching issuers

1. Verify the cause of suspension/revocation has been resolved.
2. Verify issuer/JWKS and address any key compromise.
3. Re-run approval; **never blindly roll back revoked trust**.
4. Plan for old tokens: revocation, minimum issuance epoch, or issuer rotation.
5. Link local identities safely without auto-mapping by email.
6. Publish a **new revision** and test both old and new tokens.
7. Monitor the rollout and business account/tenant states.

## 22. Common mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Trusting any `iss` from a token and running discovery. | Issuer confusion / SSRF. | Trusted issuer registry, pre-approved. |
| Trusting `jku`/`x5u` in JOSE headers. | Token dictates where public keys load from. | Approved JWKS URI, network allowlist. |
| Assuming valid signature suffices without checking `aud`. | Tokens for other APIs get accepted. | Issuer + audience + token profile validation. |
| Treating tenant slug in URL as permission. | Cross-tenant access. | Membership and owner/domain checks. |
| Mapping users solely by `sub` or email. | User collision / account takeover. | `(iss, sub)` and evidence-backed account linking. |
| Keying manager caches permanently by `tenantKey`. | Old decoder keeps working after revocation. | Revisioned keys + per-request ACTIVE gate. |
| Only removing issuer from a dynamic predicate. | Cached resolver may still hold old manager. | Test/invalidate + runtime state check. |
| Deleting tenants without tombstones. | Old ACTIVE events can re-enable them. | Monotonic revisions, REVOKED/RETIRED tombstones. |
| Non-atomic field-by-field updates. | New issuer + old JWKS, broken policy. | Immutable approved snapshots. |
| Offline nodes trusting ACTIVE config forever. | Stale trust post-revocation. | Snapshot max age/watermark/fail closed. |
| Enabling issuers in prod before ownership checks. | Attacker registers their own IdP. | REQUESTED/VERIFYING/APPROVED workflow. |
| Rolling back an issuer after key compromise. | Re-trusts compromised key. | Re-approval and key/token migration. |
| Assuming reactivation invalidates old tokens. | Unexpired old JWTs get accepted again. | Revocation/epoch policy, test old tokens. |
| Treating tenant revocation as deleting all data. | Loss of retention/audit/legal holds. | Separate trust lifecycle from data lifecycle. |
| Testing only with MockMvc `jwt()`. | Bypasses real resolver and decoder. | Signed-JWT integration + warmed-cache revoke tests. |
| Letting requests pass when control plane errors. | Fail-open. | Trust snapshot policy and fail closed. |

## 23. Summary

Three layers of defense must work together:

1. **Trusted configuration lifecycle:** tenants/issuers are added solely via ownership validation, approval, and versioned publication; only **ACTIVE** state proceeds.
2. **Token authentication:** JWTs are verified against configured keys, checking signature, issuer, audience, lifetime, and algorithms; unverified `iss` is only a hint, never a trust root.
3. **Tenant/domain authorization:** principals must hold membership and privileges for the specific tenant/resource; revocation state and owner/tenant predicates must be checked at the proper enforcement points.

**Tenant revocation must beat both cached managers and unexpired JWTs.** Use a **per-request ACTIVE gate, revisioned manager caches, immutable snapshots, monotonic generations, fail-closed staleness policies, auditing, and ACTIVE → REVOKED tests against warmed managers**. A multi-replica system can only declare revocation complete once every traffic-serving node applies the new decision within SLA.

## References

- [Spring Security — Servlet Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html).
- [Spring Security — Reactive Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html).
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
