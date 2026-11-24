# Selecting JWT Issuers from a Trusted Allowlist

## 1. Context and Learning Objectives

This lesson belongs to **Gateway and Multi-tenancy** in the **Spring Security - reactive** module. A WebFlux API gateway or Resource Server may accept access tokens from **multiple JWT issuers**, such as a system serving Partner A and Partner B or multiple realms of an identity provider. Rather than configuring a single `issuer-uri`, the server must determine **which issuer a token comes from**, pick the corresponding verifier, and **trust only explicitly configured issuers**.

The `iss` field in a JWT declares **which issuer the token claims to come from**. Before verifying the signature, however, `iss` is only **untrusted data**. Reading `iss` to pick a decoder **does not mean** the issuer has been authenticated. A proper design must:

1. Read `iss` as a **routing hint**.
2. Match `iss` **exactly** against a **trusted allowlist**.
3. Pick only a `ReactiveAuthenticationManager`/`ReactiveJwtDecoder` registered from **server configuration**, never constructing arbitrary discovery/JWKS URLs from a client-supplied `iss` string.
4. Verify the **signature** using the key/JWK source belonging to that issuer, while also verifying **issuer, `exp`/`nbf` timestamps, `aud` audience, token type, and scopes** per API requirements.
5. After authentication, enforce **tenant/resource ownership**; a valid JWT for tenant A must not automatically access tenant B's data just because the gateway accepts both issuers.

After this lesson, you will be able to:
- Understand the boundary between **JWT routing**, **authentication**, and **authorization** in a multi-tenant system.
- Properly use `JwtIssuerReactiveAuthenticationManagerResolver` and `ReactiveAuthenticationManagerResolver<ServerWebExchange>` in **reactive** Spring Security.
- Choose between simple `fromTrustedIssuers(...)` and an **explicit manager registry** for extra audience/JWKS checks.
- Build a Java 17, Spring Boot 3.3.5, Spring WebFlux application with two sample issuers and a tenant-restricted route.
- Write **genuinely signed** RSA/JWT tests to verify issuer/key/audience/time rather than pretending `mockJwt()` tests signatures.
- Test URL-tenant authorization with `WebTestClient`.
- Know how to update the issuer list and defend against SSRF, key confusion, token substitution, and cross-tenant data leakage.
- Analyze caching/JWKS rotation, failure handling, metrics, and rollout for a production gateway.

**Limitation:** `issuer-alpha.example.test` and `issuer-beta.example.test` in the code are **illustrative domains with no real OP**. The app can start and serve its public endpoint, and unit/HTTP mock tests need no network issuer, but testing real access tokens via `curl` requires **two properly configured HTTPS Authorization Servers/JWKS endpoints**. Never use the test suite's RSA keys in production systems.

## 2. What Makes Multi-Issuer JWTs Challenging?

A single Resource Server may serve:

```text
                          +------------------------+
                          |  API Gateway / WebFlux |
Client Alpha -- Bearer -->|                        |
                          |     Read iss (hint)    |
Client Beta  -- Bearer -->|        |               |
                          |    TRUSTED LIST        |
                          |     /          \       |
                          | Manager A   Manager B  |
                          |   |             |      |
                          | JWKS A        JWKS B   |
                          | Verify sig, iss, aud,  |
                          | exp/nbf, policy        |
                          |          |             |
                          | Tenant/resource guard  |
                          +------------+-----------+
                                       |
                                     API data
```

Example token from issuer A:

```json
{
  "iss": "https://issuer-alpha.example.test/realm/alpha",
  "sub": "partner-100",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "alpha",
  "iat": 1730000000,
  "exp": 1730000600
}
```

Issuer B may issue tokens using **the exact same `sub` or `scope`** under a different policy:

```json
{
  "iss": "https://issuer-beta.example.test/realm/beta",
  "sub": "partner-100",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "beta",
  "iat": 1730000000,
  "exp": 1730000600
}
```

These are **illustrative payloads**, not signed JWTs and not currently valid. A real JWT is a compact JWS `header.payload.signature` verified by the Resource Server using trusted public keys.

**`sub=partner-100` in A is not automatically the same identity as `sub=partner-100` in B.** When building principal records, audits, and caches, key by **(issuer, subject)** or a proven internal identity mapping rather than `sub` alone.

### An example of the "trust every issuer" mistake

Anti-pattern:

```java
// ANTI-PATTERN: never use an arbitrary iss
// to construct a trusted decoder.
String userSuppliedIssuer = getUnverifiedIssuer(rawJwt);
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(userSuppliedIssuer);
```

This is a **warning fragment**, not a standalone class. If a client can set `iss=https://attacker.example.test`, the system may call the attacker's discovery URL (risking SSRF/outbound traffic) and then use the attacker's public key to accept a token signed by the attacker. A JWT whose signature matches "an attacker-hosted issuer" **does not become a trusted token for your application**.

**Key question:** Who decides which issuers are permitted? The answer must be **governed configuration**, never the token itself and never a request header like `X-Tenant`.

## 3. Concepts to Distinguish

| Field / Object | Role | Trust Level When Request Arrives |
| --- | --- | --- |
| Raw Bearer JWT | Credential received from client | Untrusted |
| Unverified `iss` | Hint to pick an issuer manager | Untrusted, must be allowlisted |
| `kid` in JWS header | Hint to pick a key **inside the issuer's bound JWKS** | Untrusted, not a URL |
| `jku`/`x5u` in header | May point to a key URL | **Never** auto-fetch arbitrary token-supplied URLs |
| Trusted issuers list | Server policy | Governed source of truth |
| Configured JWK Set URI | Location of public keys for an issuer | Trusted only when taken from approved config |
| `ReactiveJwtDecoder` | Verifies signature and JWT validators | Decides acceptance |
| `ReactiveAuthenticationManager` | Converts verified token into Authentication | May build principal/authorities |
| `aud` | Which API/client the token was issued for | Must be verified per API |
| `scope`/`scp` | Scopes signed into token by issuer | Used after signature/claim validation |
| `tenant_id` | Tenant claim issued by issuer | Trust only after verification and match against business policy |
| Tenant in URL/path/header | Resource context client wants to access | **Not** proof of entitlement |
| `sub` | Subject within the issuer's scope | Should not be used as a standalone global identity |

**Distinguish Authentication from Authorization:**
- Authentication: was the token issued by a trusted issuer with the right key, timestamps, and audience?
- Authorization: is that principal/tenant/scope allowed to access `/api/tenants/alpha/orders`? And does it have permission on the specific order?

A token genuinely signed by issuer Alpha attempting to access `/api/tenants/beta/orders` must receive **403** from tenant policy once authenticated, rather than being allowed merely because it holds a generic `orders:read` scope.

## 4. Correct Processing Flow in Reactive Spring Security

```text
GET /api/tenants/alpha/orders
Authorization: Bearer <JWS>

     |
     v
BearerToken AuthenticationWebFilter
     |
     v
JwtIssuerReactiveAuthenticationManagerResolver.resolve(exchange)
     |
     +-- Read JWT iss to pick manager [UNVERIFIED]
     |
     +-- iss not in allowlist -> 401 invalid_token
     |
     +-- iss approved -> fetch manager A / B from registry
                                 |
                                 v
                   JwtReactiveAuthenticationManager
                                 |
                                 v
                   NimbusReactiveJwtDecoder for issuer
                     - configured issuer keys
                     - signature / algorithm
                     - exact iss
                     - exp, nbf
                     - API audience
                                 |
                         failed -> 401
                                 |
                                 v
                   JwtAuthenticationToken + SCOPE_*
                                 |
                                 v
                   ReactiveAuthorizationManager
                     - path tenant matches issuer?
                     - orders:read scope sufficient?
                     - resource ownership/policy?
                                 |
                         denied -> 403
                                 |
                                 v
                             Controller
```

**Trust boundary rule:** Using unverified `iss` as an **index into a trusted static map** is safe because it **grants no permissions**; the selected decoder subsequently must validate the entire token. If the issuer is absent from the map, **never fall back to an inferred issuer URL**.

### Standard HTTP Outcomes

- Missing Bearer token on a private route: typically **401**.
- Malformed token, unknown issuer, bad signature, expired token, wrong audience: **401** (JWT authentication failed).
- Valid token with insufficient scope: **403**.
- Valid Alpha-issuer token accessing tenant Beta: **403**.
- Valid user/tenant/token failing resource ownership: **403 or 404** per resource-hiding policy.
- Valid token satisfying all policies: **200**.
- Public `/health` or `/public`: **200** without Bearer.

Never return issuer key details, raw tokens, or internal policy reasons in error responses. Log audit reasons with internal error codes, never logging credentials.

## 5. Reactive Spring Security API: `JwtIssuerReactiveAuthenticationManagerResolver`

### 5.1. Simple approach: `fromTrustedIssuers`

Example from the official guide:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp.example.org/issuerOne",
                "https://idp.example.org/issuerTwo");

return http
        .authorizeExchange(exchanges ->
                exchanges.anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(resolver))
        .build();
```

This is a **configuration fragment inside a `SecurityWebFilterChain` Bean**, not a standalone class. It is the **reactive** API; the Servlet counterpart is named `JwtIssuerAuthenticationManagerResolver` with a different `HttpSecurity` DSL.

**Advantages:**
- Issuer allowlist is explicit; URLs are never taken arbitrarily from tokens.
- Spring Security automatically selects the matching `JwtReactiveAuthenticationManager`.
- Per the documentation, managers/metadata may be **created/fetched lazily** on first use of an issuer, reducing startup coupling to every OP.
- Concise when verification policies are identical and only an issuer allowlist is needed.

**Limitations to consider:**
- If each issuer requires **different audiences**, distinct controlled JWK Set URIs, different allowed algorithms, or special token-type policies, provide an **explicit registry of managers/decoders**.
- Never assume `fromTrustedIssuers` automatically enforces **business tenant isolation** or API-specific audiences.
- Check OP support, TLS, metadata, and your **Spring Security version**.
- A large/unbounded number of issuers increases JWKS/manager cache cost and potential rate abuse.

### 5.2. Full-control approach: registry of approved managers

Use `JwtIssuerReactiveAuthenticationManagerResolver` with a `ReactiveAuthenticationManagerResolver<String>` that pulls managers strictly from a map:

```java
Map<String, ReactiveAuthenticationManager> trustedManagers =
        Map.of(
                "https://issuer-a.example.test",
                managerA,
                "https://issuer-b.example.test",
                managerB);

var resolver =
        new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(
                        trustedManagers.get(issuer)));
```

Above is a **fragment**: `managerA`/`managerB` were already constructed by the app with decoders **carrying signature/iss/aud/expiry validators**, not "accept-all" managers. Unknown issuers return empty during manager lookup; the resolver rejects the token instead of fabricating a decoder.

**Advantages:** controls:
- **Issuer → trusted JWK Set URI** pairs.
- Allowed signing algorithms (e.g., RS256 only per policy).
- Expected audience per issuer.
- Optional token type `typ=at+jwt`/RFC 9068 or `azp`, `client_id`, `tid` per agreed token profile.
- Caching/metrics and lifecycle of each manager.
- Audited disabling of an issuer.

**Never accept** any manager created dynamically from an un-allowlisted `iss`; if dynamic onboarding is needed, configuration must come from an **authorized control plane** through validation and approval.

### 5.3. Why might `iss` need to be read twice?

In the route-by-claim model:
1. The resolver reads unverified `iss` to pick manager A or B.
2. The chosen decoder parses the JWS, verifies the signature, and **validates the exact signed `iss`**.

This is not a bug. Step 1 decides **how to verify**; step 2 decides whether the token **is actually trustworthy**.

**Key confusion warning:** Never take `kid` or `jku` from a JWT to fetch keys from an arbitrary host. `kid` is only used to pick within the **approved issuer's JWKS**; having the same `kid` on issuer A and B does not make A's key valid for B.

## 6. Issuer, JWK Set URI, and URL Matching

### 6.1. Exact issuer string

The following values should be treated as **distinct** unless the registration policy explicitly defines normalization:
- `https://idp.example.test/realm/a`
- `https://idp.example.test/realm/a/`
- `https://IDP.example.test/realm/a`
- `http://idp.example.test/realm/a`
- `https://idp.example.test/realm/b`

With OIDC, `iss` must match the issuer declared in documentation and metadata. **Never use `startsWith("https://idp.example.test")`**; that can accept wrong paths or hostnames like `https://idp.example.test.attacker.example`. Nor does a hostname or issuer automatically identify a tenant if one OP serves multiple realms.

### 6.2. HTTPS, discovery, and JWKS

A trusted configuration must bind an issuer to its public key source. Options:
- Use issuer discovery and validate metadata/`jwks_uri`.
- Configure an explicit `jwk-set-uri` from the control plane, never fetching URLs from tokens.

When configuring a static JWK URI, **set an issuer validator explicitly**, because a decoder created via `withJwkSetUri(...)` does not know the expected issuer on its own.

```java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withJwkSetUri("https://idp.example.test/jwks")
                .build();

decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
                "https://idp.example.test/realm/a"));
```

This is a fragment. In the full demo, we **combine issuer, timestamp, and audience validation**.

**Version security note:** Spring disclosed **CVE-2026-22748** regarding misconfigured issuer validation when using `NimbusReactiveJwtDecoder.withIssuerLocation(...)` on older versions. Even when using discovery, always **verify that the issuer validator is active**, and upgrade to a patched, supported Spring Security version. The example uses Spring Boot 3.3.5 solely to illustrate historical APIs; that release is **not a recommended 2026 production version**.

### 6.3. Audience check is mandatory per API contract

A JWT's `aud` indicates which resource server the token was issued for. An ID Token for a browser client or an access token meant for another API might have:
- A valid signature.
- An `iss` in the allowlist.
- An unexpired `exp`.

Yet it **must still be rejected** if `aud` does not contain the current API's audience. The demo requires `aud=orders-api` for both tenants; in practice each issuer/tenant may use a different audience.

Never treat `client_id` or `azp` as a default substitute for `aud`. The OAuth2/JWT token profile issued by the IdP must be agreed upon and explicitly tested.

### 6.4. Verify algorithms and token types

- Reject `alg=none`.
- Never allow HMAC symmetric secrets to be confused with JWK RSA public keys.
- Restrict allowed JWS algorithms to prevent algorithm confusion.
- If the API requires an **RFC 9068 JWT access token**, consider checking `typ=at+jwt` and profile claims (issuer/audience/client_id...) per framework version. An OIDC ID Token is **not** an access token for a Resource Server.
- In this example, the decoder defaults to RS256 with issuer/time/audience validators; it **does not claim to check `typ=at+jwt`**. Production must add type checks if required by the provider/profile and keep the framework upgraded.

## 7. Gateway, Tenants, and Authorization Boundaries

### 7.1. Issuer does not necessarily equal tenant

Two common models:

**One issuer per tenant:**

```text
issuer A -> tenant alpha
issuer B -> tenant beta
```

An authoritative mapping can be maintained in configuration. The demo uses this model for clarity.

**One issuer serving multiple tenants:**

```text
shared issuer -> tenant alpha
              -> tenant beta
              -> tenant gamma
```

In that case **you cannot infer the tenant from `iss` alone**. You must rely on a verified tenant claim (`tid`/`tenant_id` per OP profile) and policies verifying account-to-tenant membership, audience, and resource ownership. A trusted issuer **does not mean every subject from that issuer can access every tenant**.

### 7.2. Client-selected URL tenant does not prove permission

Anti-pattern:

```java
// ANTI-PATTERN: ignores the URL tenant as soon as a valid token is present.
@GetMapping("/api/tenants/{tenant}/orders")
public Mono<?> orders(@PathVariable String tenant) {
    return repository.readAllOrdersForTenant(tenant);
}
```

This is a fragment, not a standalone class. If Authenticated A passes `tenant=beta`, the backend could leak B's data. You need a guard verifying the issuer/subject/tenant mapping and resource permissions.

In the demo:
- Issuer alpha is permitted only on tenant `alpha` URLs.
- Issuer beta is permitted only on tenant `beta` URLs.
- `SCOPE_orders:read` is required.
- The rule lives in a **ReactiveAuthorizationManager<AuthorizationContext>** running before the Controller.
- A real business service must also check ownership of each individual order at the data layer, not just at the route guard.

### 7.3. Principal identifier keys

Never build cache/audit keys from `sub` alone. Use a composite key:
- `(issuer, subject)`;
- plus tenant ID/partner client ID if the app needs it;
- or a verified, authorized internal mapping.

If two issuers both issue `sub=alice`, they may be two completely different users. Using an un-namespaced subject causes cross-tenant identity confusion.

## 8. Runnable Project: Spring Boot 3.3.5 / Java 17 / WebFlux

The demo uses **two statically configured issuers**, verifies **issuer + signature + exp/nbf + audience**, and restricts the tenant in the request path.

Structure:

```text
trusted-issuer-webflux/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/trustedissuers/
    │   │   ├── TrustedIssuerApplication.java
    │   │   ├── TrustedIssuerProperties.java
    │   │   ├── IssuerRouting.java
    │   │   ├── TenantGuard.java
    │   │   ├── SecurityConfig.java
    │   │   └── OrdersController.java
    │   └── resources/application.yml
    └── test/
        └── java/dev/example/trustedissuers/
            ├── IssuerRoutingTests.java
            └── TenantHttpTests.java
```

### 8.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'trusted-issuer-webflux'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
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
```

`spring-boot-starter-oauth2-resource-server` brings in JWT/JWS/JOSE dependencies via the Boot BOM. Do not add `spring-boot-starter-web` (the Servlet starter) to a WebFlux demo; when both are present, Spring Boot typically selects Servlet/MVC.

**Version note:** Boot 3.3.5/Spring Security 6.3.x is the API baseline for this lesson, not a current production security recommendation. Use a supported version with security advisories patched and check API differences when upgrading.

### 8.2. `application.yml`: server-managed allowlist

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

app:
  security:
    tenants:
      alpha:
        issuer: https://issuer-alpha.example.test/realm/alpha
        jwk-set-uri: https://issuer-alpha.example.test/jwks
        audience: orders-api
      beta:
        issuer: https://issuer-beta.example.test/realm/beta
        jwk-set-uri: https://issuer-beta.example.test/jwks
        audience: orders-api
```

**Why is there no single `spring.security.oauth2.resourceserver.jwt.issuer-uri`?** Because the app accepts **multiple issuers**. We register an explicit resolver/manager registry; leaving a single default JWT config could recognize only one issuer or apply mismatched validators across tenants.

**`.example.test` is illustrative only**: to validate real Bearer access tokens, replace all `issuer` and `jwk-set-uri` values with real HTTPS URLs for your OPs and tenants, and verify `audience`. App startup does not call the test URLs thanks to static JWKS config; **real Bearer requests** will require a reachable JWK Set URI to verify signatures.

Never let users/queries/headers pick `jwk-set-uri`. Any edit to this list is a **security-sensitive control-plane change** requiring review, auditing, and controlled rollout.

### 8.3. Main class

`src/main/java/dev/example/trustedissuers/TrustedIssuerApplication.java`:

```java
package dev.example.trustedissuers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TrustedIssuerApplication {
    public static void main(String[] args) {
        SpringApplication.run(TrustedIssuerApplication.class, args);
    }
}
```

### 8.4. Trusted configuration properties + fail-fast validation

`src/main/java/dev/example/trustedissuers/TrustedIssuerProperties.java`:

```java
package dev.example.trustedissuers;

import java.net.URI;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record TrustedIssuerProperties(
        Map<String, Tenant> tenants) {

    public TrustedIssuerProperties {
        if (tenants == null || tenants.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one trusted issuer is required");
        }

        tenants = Map.copyOf(tenants);
        Set<String> seenIssuers = new HashSet<>();

        for (var entry : tenants.entrySet()) {
            String tenantId = entry.getKey();
            Tenant policy = entry.getValue();

            if (tenantId == null || tenantId.isBlank()
                    || policy == null) {
                throw new IllegalArgumentException(
                        "Invalid tenant configuration");
            }

            validateHttpsUrl(policy.issuer());
            validateHttpsUrl(policy.jwkSetUri());

            if (policy.audience() == null
                    || policy.audience().isBlank()) {
                throw new IllegalArgumentException(
                        "Audience must not be empty");
            }

            if (!seenIssuers.add(policy.issuer())) {
                throw new IllegalArgumentException(
                        "Duplicate issuer: one issuer per tenant "
                      + "is required by this example");
            }
        }
    }

    private static void validateHttpsUrl(String url) {
        if (url == null || url.isBlank()) {
            throw new IllegalArgumentException(
                    "Trusted URL must not be empty");
        }

        URI uri = URI.create(url);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "Trusted issuer and JWKS URLs must be HTTPS "
                  + "without user info, query or fragment");
        }
    }

    public record Tenant(
            String issuer,
            String jwkSetUri,
            String audience) {
    }
}
```

**Points to note:**
- `@ConfigurationProperties` binds configuration managed by the **server/operator**, never from incoming user requests.
- Reject an empty trusted list: if the app has no trusted issuers, it must fail fast rather than falling back to "allow all issuers."
- `Map.copyOf(...)` snapshots the list to prevent mid-request mutation.
- URIs must be HTTPS with a host and no userInfo/query/fragment, reducing the risk of misconfiguring an unsafe source.
- Duplicate issuers are rejected because the demo models **1 issuer → 1 tenant**; if an issuer serves multiple tenants, update the guard to verify the tenant claim instead of duplicating issuers in the map.
- `audience` must be configured explicitly rather than trusting whatever `aud` the client sends.
- **HTTPS and allowlists are necessary but insufficient against all SSRF** if untrusted actors can write the config itself. Production should also apply network egress policies, private-IP/DNS-rebinding controls on outbound traffic, and strict config write permissions.

**Additional config needed in production:** allowed signing algorithms, token profile, `typ`, client/tenant-specific policies, cache timeouts, JWKS refresh cadence, and an emergency issuer kill switch.

### 8.5. IssuerRouting: manager registry and validators

`src/main/java/dev/example/trustedissuers/IssuerRouting.java`:

```java
package dev.example.trustedissuers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class IssuerRouting {

    private IssuerRouting() {
    }

    public static OAuth2TokenValidator<Jwt> validators(
            String expectedIssuer, String expectedAudience) {

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "JWT audience is not accepted",
                            null));
        };

        return new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(
                        expectedIssuer),
                audience);
    }

    public static ReactiveAuthenticationManagerResolver<ServerWebExchange>
            fromTrustedDecoders(
                    Map<String, ReactiveJwtDecoder> approvedDecoders) {

        if (approvedDecoders == null
                || approvedDecoders.isEmpty()) {
            throw new IllegalArgumentException(
                    "Trusted decoders must not be empty");
        }

        Map<String, ReactiveAuthenticationManager> managers =
                new HashMap<>();

        approvedDecoders.forEach((issuer, decoder) -> {
            if (issuer == null || issuer.isBlank()
                    || decoder == null) {
                throw new IllegalArgumentException(
                        "Invalid trusted issuer mapping");
            }
            managers.put(issuer,
                    new JwtReactiveAuthenticationManager(decoder));
        });

        Map<String, ReactiveAuthenticationManager> trusted =
                Map.copyOf(managers);

        return new JwtIssuerReactiveAuthenticationManagerResolver(
                issuer -> Mono.justOrEmpty(trusted.get(issuer)));
    }
}
```

**Critical safeguards:**
1. `JwtValidators.createDefaultWithIssuer(expectedIssuer)` checks the issuer **and default validators**, including timestamps, after the decoder verifies the signature.
2. The audience validator checks `jwt.getAudience().contains(expectedAudience)` and will not accept a different audience merely because the issuer matched.
3. The map is built from server-owned **approvedDecoders**, never from a dynamic untrusted `iss`.
4. Each manager wraps `JwtReactiveAuthenticationManager(decoder)` so tokens must pass decoder verification before becoming an authenticated principal.
5. The resolver inspects unverified `iss` only to select **a manager present in `Map.copyOf(managers)`**. Unknown issuers trigger no outbound discovery/JWKS HTTP requests.
6. Managers do not share public keys unless intentional key sharing is explicitly justified; in the A/B demo each issuer has its own JWKS.
7. `ReactiveJwtDecoder` can be injected in tests with an in-memory RSA public key without needing network URLs; tests must still genuinely sign tokens to prove the decoder rejects wrong signatures.

**Never roll your own decoder with `Base64.getUrlDecoder` and skip JWS signatures**. `iss` is an untrusted index; security comes from cryptographic verification + validators.

### 8.6. TenantGuard: authorization based on verified issuer

`src/main/java/dev/example/trustedissuers/TenantGuard.java`:

```java
package dev.example.trustedissuers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.authorization.AuthorizationContext;

import reactor.core.publisher.Mono;

public final class TenantGuard
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final Map<String, String> tenantByIssuer;

    public TenantGuard(TrustedIssuerProperties properties) {
        Map<String, String> trusted = new HashMap<>();
        properties.tenants().forEach((tenant, policy) ->
                trusted.put(policy.issuer(), tenant));
        this.tenantByIssuer = Map.copyOf(trusted);
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object pathValue = context.getVariables().get("tenant");
        String requestedTenant =
                (pathValue instanceof String value) ? value : null;

        return authentication
                .map(auth -> {
                    if (!auth.isAuthenticated()
                            || !(auth.getPrincipal()
                                    instanceof Jwt jwt)
                            || jwt.getIssuer() == null
                            || requestedTenant == null) {
                        return new AuthorizationDecision(false);
                    }

                    String verifiedIssuer =
                            jwt.getIssuer().toString();
                    String boundTenant =
                            tenantByIssuer.get(verifiedIssuer);

                    boolean hasScope = auth.getAuthorities().stream()
                            .anyMatch(granted ->
                                    "SCOPE_orders:read".equals(
                                            granted.getAuthority()));

                    boolean allowed = boundTenant != null
                            && boundTenant.equals(requestedTenant)
                            && hasScope;

                    return new AuthorizationDecision(allowed);
                })
                .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
```

**Analysis:**
- `AuthorizationContext.getVariables().get("tenant")` comes from the `/api/tenants/{tenant}/orders` path matcher.
- The URI path tenant is **not** an authentication source; it is merely the tenant the client wishes to read.
- `auth.getPrincipal() instanceof Jwt` is meaningful at runtime **only because the real JWT Authentication Manager verified the token**. In `mockJwt()` tests it is simulated.
- `tenantByIssuer` is a server-side mapping restricted to approved issuers, never trusting an arbitrary `tenant_id` from request/headers.
- Requires `SCOPE_orders:read`, mapped by Spring Security from the JWT's scope claim **after signature verification**.
- Missing principal, missing issuer, missing scope, or tenant mismatch → returns false with no permissive fallback.
- The demo maps 1 issuer to 1 tenant; if one issuer serves multiple tenants, check the verified tenant claim **and current membership/ownership**.
- With varied JWT token profiles, configure the corresponding authentication converter and authorities mapping; never assume every OP uses the `scope` claim identically.

### 8.7. SecurityConfig: wiring the issuer list into WebFlux Resource Server

`src/main/java/dev/example/trustedissuers/SecurityConfig.java`:

```java
package dev.example.trustedissuers;

import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.server.ServerWebExchange;

@Configuration
@EnableWebFluxSecurity
@EnableConfigurationProperties(TrustedIssuerProperties.class)
public class SecurityConfig {

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange>
            trustedIssuerResolver(TrustedIssuerProperties properties) {

        Map<String, ReactiveJwtDecoder> approved =
                new HashMap<>();

        properties.tenants().forEach((tenant, policy) -> {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder
                            .withJwkSetUri(policy.jwkSetUri())
                            .build();

            decoder.setJwtValidator(
                    IssuerRouting.validators(
                            policy.issuer(),
                            policy.audience()));

            approved.put(policy.issuer(), decoder);
        });

        return IssuerRouting.fromTrustedDecoders(approved);
    }

    @Bean
    TenantGuard tenantGuard(TrustedIssuerProperties properties) {
        return new TenantGuard(properties);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange>
                    trustedIssuerResolver,
            TenantGuard tenantGuard) {

        return http
                // Bearer-token-only stateless API; see CSRF caveat below.
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/tenants/{tenant}/orders")
                            .access(tenantGuard)
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationManagerResolver(
                                trustedIssuerResolver))
                .build();
    }
}
```

**Points that must not be overlooked:**
1. Every tenant is bound to a **trusted issuer, JWKS, and audience**.
2. `NimbusReactiveJwtDecoder.withJwkSetUri(...)` is constructed from **server config**, never from the JWT's `iss`.
3. `setJwtValidator(...)` **must** include issuer/time validators plus the audience validator.
4. `fromTrustedDecoders(...)` builds the manager map and resolver; unverified requests can only pick an existing manager in that map.
5. `oauth2ResourceServer(...authenticationManagerResolver(...))` is the **reactive** DSL, not the Servlet DSL.
6. `NoOpServerSecurityContextRepository` prevents persisting authentication in a WebSession; each Bearer request must present its own token.
7. `csrf.disable()` is appropriate only if the API is strictly **stateless and does not rely on automatically sent cookies/browser credentials**. For WebFlux apps with browser logins/sessions, keep CSRF enabled and split chains; never copy `csrf.disable()` into mixed apps.
8. `GET /public` requires no Bearer token, private tenant routes use `TenantGuard`, and undeclared paths hit `denyAll()`.
9. JWT signature validation is handled by the decoder; there is no need to parse/verify RSA manually in controllers.
10. **Do not expose a default global `ReactiveJwtDecoder` bean** to avoid confusion about whether all issuers share validators; the resolver manages its decoders directly.
11. In production, trusted issuer configuration is a security-sensitive change: require review, change history, monitoring, and rollback.
12. The app can start without contacting `.example.test` because the decoder fetches the JWK Set over HTTP only when verifying a Bearer token. However, **requests targeting non-existent issuers will fail**; this is not a pre-built live OP.

### 8.8. Sample controller

`src/main/java/dev/example/trustedissuers/OrdersController.java`:

```java
package dev.example.trustedissuers;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/tenants/{tenant}/orders")
    public Mono<Map<String, String>> orders(
            @PathVariable String tenant,
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.just(Map.of(
                "tenant", tenant,
                "issuer", jwt.getIssuer().toString(),
                "subject", jwt.getSubject(),
                "result", "orders-read-ok"));
    }
}
```

This is a demo response with no database access. **TenantGuard runs before the controller**, so issuer Alpha cannot invoke the Beta route. When querying real orders, services/repositories must **filter by tenant/ownership and authorize resource IDs** rather than relying solely on the endpoint guard.

**Data exposure risk:** The demo response displays issuer/subject for learning visibility. In production, return only fields permitted by the API contract; never return raw tokens, unnecessary claims, or internal issuer metadata.

## 9. Running the App Against Real Issuers

With the illustrative `application.yml`, run:

```bash
gradle bootRun
```

Or `./gradlew bootRun` / `gradlew.bat bootRun` if the project has a Gradle Wrapper. The public route can be called via:

```bash
curl -i http://localhost:8080/public
```

Expect `200 OK` with body:

```text
public-ok
```

Calling the protected route without a token:

```bash
curl -i http://localhost:8080/api/tenants/alpha/orders
```

Expect `401 Unauthorized`.

**To test real Bearer JWTs:**
1. Configure two **real** HTTPS issuer/JWKS URLs instead of `.example.test`.
2. Each IdP must issue a **signed access token** with `iss` matching config, `aud=orders-api`, valid `exp`, and `scope=orders:read`.
3. Store test tokens in a controlled secret store/environment; never put tokens into committed scripts, URLs, or screenshots.
4. Call the API over HTTPS in a real environment:

```bash
# ACCESS_TOKEN_ALPHA is assumed to have been securely issued in the test environment.
curl -i -H "Authorization: Bearer $ACCESS_TOKEN_ALPHA" \
  https://api.example.test/api/tenants/alpha/orders
```

When an Alpha token has the right issuer, signature, timestamps, audience, and scope, expect HTTP **200**. Using an Alpha token on `/api/tenants/beta/orders` yields HTTP **403**. A token from a third issuer outside the allowlist yields **401**. A token from a valid issuer with another API's audience yields **401**.

These are **expected results based on the code and protocol**; testing real access tokens depends on live issuers/JWKS, valid TLS/certificates, and accurate OP configuration. No real token data is included in this document.

## 10. Offline RSA Signature and Issuer Routing Tests

A common mistake is writing only `mockJwt()` and claiming issuer trust has been tested. `mockJwt()` creates a synthetic Authentication that **bypasses the signature/decoder**; it works for testing authorization rules, not proving a token was signed by the right issuer.

Here we write **unit tests generating two distinct 2048-bit RSA key pairs**, sign real JWTs with `NimbusJwtEncoder`, and verify them using the matching issuer's `NimbusReactiveJwtDecoder.withPublicKey(...)`. While this **does not fetch JWKS over HTTP**, it verifies:
- Issuer A's signature is valid only with public key A.
- Issuer B's token is valid with public key B.
- An unknown `iss` has no manager in the allowlist.
- A token claiming `iss=A` yet signed with key B is rejected.
- A wrong audience is rejected **after** signature verification.
- Expired tokens are rejected.

File `src/test/java/dev/example/trustedissuers/IssuerRoutingTests.java`:

```java
package dev.example.trustedissuers;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IssuerRoutingTests {

    private static final String ALPHA =
            "https://issuer-alpha.example.test/realm/alpha";
    private static final String BETA =
            "https://issuer-beta.example.test/realm/beta";
    private static final String OTHER =
            "https://untrusted.example.test";

    private static KeyPair alphaKeys;
    private static KeyPair betaKeys;

    @BeforeAll
    static void createKeys() throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        alphaKeys = generator.generateKeyPair();
        betaKeys = generator.generateKeyPair();
    }

    private String sign(
            KeyPair signer,
            String signingKid,
            String claimedIssuer,
            String audience,
            Instant expiresAt) {

        RSAKey signingKey = new RSAKey.Builder(
                (RSAPublicKey) signer.getPublic())
                .privateKey((RSAPrivateKey) signer.getPrivate())
                .keyID(signingKid)
                .build();

        JwtEncoder encoder =
                new NimbusJwtEncoder(
                        new ImmutableJWKSet<SecurityContext>(
                                new JWKSet(signingKey)));

        JwsHeader header =
                JwsHeader.with(SignatureAlgorithm.RS256)
                        .keyId(signingKid)
                        .build();

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(claimedIssuer)
                .subject("test-subject")
                .audience(List.of(audience))
                .issuedAt(Instant.now().minusSeconds(60))
                .expiresAt(expiresAt)
                .claim("scope", "orders:read")
                .build();

        return encoder.encode(
                JwtEncoderParameters.from(header, claims))
                .getTokenValue();
    }

    private ReactiveJwtDecoder decoder(
            RSAPublicKey publicKey,
            String expectedIssuer,
            String expectedAudience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withPublicKey(publicKey)
                        .build();

        decoder.setJwtValidator(
                IssuerRouting.validators(
                        expectedIssuer, expectedAudience));
        return decoder;
    }

    private ReactiveAuthenticationManagerResolver<ServerWebExchange>
            resolver() {

        return IssuerRouting.fromTrustedDecoders(Map.of(
                ALPHA, decoder((RSAPublicKey) alphaKeys.getPublic(),
                        ALPHA, "orders-api"),
                BETA, decoder((RSAPublicKey) betaKeys.getPublic(),
                        BETA, "orders-api")));
    }

    private Mono<Authentication> authenticate(String rawJwt) {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest
                        .get("https://gateway.example.test/api")
                        .header(
                                HttpHeaders.AUTHORIZATION,
                                "Bearer " + rawJwt)
                        .build());

        return resolver().resolve(exchange)
                .flatMap(manager -> manager.authenticate(
                        new BearerTokenAuthenticationToken(rawJwt)));
    }

    private Instant future() {
        return Instant.now().plusSeconds(600);
    }

    @Test
    void alphaTokenSignedByAlphaKeyIsAccepted() {
        String token = sign(alphaKeys, "alpha-key", ALPHA,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .assertNext(auth -> {
                    assertTrue(auth.isAuthenticated());
                    assertEquals("test-subject", auth.getName());
                    assertTrue(auth.getAuthorities().stream()
                            .anyMatch(granted ->
                                    granted.getAuthority().equals(
                                            "SCOPE_orders:read")));
                })
                .verifyComplete();
    }

    @Test
    void betaTokenSignedByBetaKeyIsAccepted() {
        String token = sign(betaKeys, "beta-key", BETA,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .assertNext(auth ->
                        assertTrue(auth.isAuthenticated()))
                .verifyComplete();
    }

    @Test
    void issuerOutsideAllowlistIsRejected() {
        String token = sign(alphaKeys, "alpha-key", OTHER,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void tokenClaimingAlphaButSignedByBetaIsRejected() {
        String token = sign(betaKeys, "beta-key", ALPHA,
                "orders-api", future());

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void correctSignatureWrongAudienceIsRejected() {
        String token = sign(alphaKeys, "alpha-key", ALPHA,
                "unrelated-api", future());

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void expiredJwtIsRejected() {
        String token = sign(alphaKeys, "alpha-key", ALPHA,
                "orders-api", Instant.now().minusSeconds(180));

        StepVerifier.create(authenticate(token))
                .expectError()
                .verify();
    }

    @Test
    void malformedBearerValueIsRejected() {
        StepVerifier.create(authenticate("not-a-jws"))
                .expectError()
                .verify();
    }
}
```

Run:

```bash
gradle test --tests dev.example.trustedissuers.IssuerRoutingTests
```

**Expected result:** 7 tests pass given matching code/dependencies. They use real RSA signatures without an HTTP JWKS server. This is an **expected outcome derived from the code**, not a claim that Gradle was executed in your workspace.

### Limitations of this RSA suite

The suite uses `withPublicKey(...)` and production-like validators, but **does not test JWKS URI/TLS/metadata discovery or key rotation from a real OP**, since there is no network. Production testing needs properly configured mock HTTP issuer/JWKS servers, real OP contracts, or gateway E2E tests.

If an "unknown issuer" test fails before signature verification, that is expected behavior: the system has no manager for unknown issuers. If a token claims issuer A while signed with key B, the resolver must select **manager A** from the allowlist and manager A must **reject the signature**. That is the key test against key confusion.

## 11. HTTP Tests with WebTestClient for Tenant Isolation

This test suite uses `mockJwt()` **solely to verify authorization/HTTP behavior** without needing two OPs. It **bypasses the resolver and cryptographic decoder**, so it must never be used to claim unknown-issuer tokens return 401. Issuer trust and cryptography are verified separately in `IssuerRoutingTests` with real RSA.

File `src/test/java/dev/example/trustedissuers/TenantHttpTests.java`:

```java
package dev.example.trustedissuers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class TenantHttpTests {

    private static final String ALPHA =
            "https://issuer-alpha.example.test/realm/alpha";
    private static final String BETA =
            "https://issuer-beta.example.test/realm/beta";

    @Autowired
    WebTestClient client;

    private WebTestClient authenticated(
            String issuer, String scope) {

        return client.mutateWith(
                mockJwt()
                        .jwt(jwt -> jwt
                                .issuer(issuer)
                                .subject("test-user")
                                .claim("scope", scope))
                        .authorities(
                                new SimpleGrantedAuthority(
                                        "SCOPE_" + scope)));
    }

    @Test
    void publicEndpointIsAccessibleWithoutJwt() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateEndpointRequiresAuthentication() {
        client.get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void alphaIssuerCanReadAlphaTenant() {
        authenticated(ALPHA, "orders:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("alpha")
                .jsonPath("$.subject").isEqualTo("test-user");
    }

    @Test
    void betaIssuerCanReadBetaTenant() {
        authenticated(BETA, "orders:read")
                .get().uri("/api/tenants/beta/orders")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("beta");
    }

    @Test
    void alphaIssuerCannotReadBetaTenant() {
        authenticated(ALPHA, "orders:read")
                .get().uri("/api/tenants/beta/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void betaIssuerCannotReadAlphaTenant() {
        authenticated(BETA, "orders:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void correctTenantWithoutRequiredScopeIsForbidden() {
        authenticated(ALPHA, "profile:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unrecognizedIssuerInMockPrincipalDoesNotPassGuard() {
        authenticated("https://unknown.example.test",
                "orders:read")
                .get().uri("/api/tenants/alpha/orders")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        authenticated(ALPHA, "orders:read")
                .get().uri("/api/hidden")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

**Expected result:** 9 HTTP tests plus 7 RSA/decoder tests = **16 tests**. They cover distinct scopes:
- `IssuerRoutingTests`: RSA-signed JWTs, trusted issuer selection, audience, expiration, key confusion.
- `TenantHttpTests`: WebFlux security authorization/path variables, scopes, and cross-tenant boundaries.
- The mock `unknown issuer` test yields **403 from TenantGuard**, not 401, because `mockJwt()` simulates an already-succeeded Authentication. A **real Bearer token** with an unknown issuer must be rejected by the resolver inside the authentication pipeline and typically receives 401.

**Gradle was not executed while authoring this Knowledge lesson**, so all test outputs in the document are expected outcomes rather than actual test reports.

### Additional Tests Required Before Production

1. HTTP integration **without mockJwt**: run a local JWKS HTTP test server/IdP, sign real JWTs, send Bearer headers through the Gateway.
2. Valid issuer A token → 200 on Alpha; valid issuer B → 200 on Beta.
3. Issuer outside allowlist → 401 and **zero outbound calls to the token-chosen host**.
4. Issuer A signed with key B → 401.
5. Issuer A with `aud=unrelated-api` → 401.
6. Stale `exp` / future `nbf` JWT → 401.
7. Token A + tenant B URL → 403.
8. Missing `scope=orders:read` → 403.
9. Test JWKS fetching and `kid` rotation; retry/timeout behavior during IdP outages.
10. Test duplicate/malformed Bearer headers and authorization error normalization.
11. Test resource ownership (which tenant owns an order?) at the DB layer.
12. Test rollback when disabling an issuer without accidentally opening wildcard trust.

## 12. Security Pitfalls of Multi-Issuer JWTs

### 12.1. SSRF via `iss`

**Dangerous scenario:** Code invokes issuer discovery for a URL taken from an unverified token.

Potential consequences:
- Outbound HTTP requests from the backend to an attacker's host.
- Accidental access to internal metadata or cloud metadata endpoints.
- Trusting public keys published by the attacker.
- Flooding the system with decoder/HTTP calls to exhaust resources.

**Mitigation:** Allowlist exact `iss` before constructing/fetching a manager; preferably **pre-register URLs** from a control plane. Never pull `jwks_uri` or `jku` from untrusted tokens. For dynamic onboarding, require an admin-approved registry, egress allowlists/network policies, strict URL parsing, DNS and redirect safeguards, and quotas.

### 12.2. Algorithm confusion and JWK trust

- Reject `alg=none`.
- Never allow an RSA JWK public key to be used as an HMAC secret via the `alg` header.
- Never fetch attacker-controlled `jku` URLs.
- Allow only appropriate JWS algorithms (RS256 in the demo), along with matching key use/ID and issuer policies.
- Treat `kid` strictly as a **key selector inside the chosen JWKS**, never as an issuer selector.
- Validate JWT libraries and patch promptly when CVEs are disclosed.

### 12.3. Token substitution / ID Token used as an access token

An OIDC ID Token can carry `iss`, `sub`, `aud`, and a valid signature. However, it is issued for an **OAuth client**, not an API resource server. If a Resource Server checks only signature/issuer without verifying **audience and token type per profile**, an ID Token can be mistaken for an access token.

The demo requires `aud=orders-api`; production should require `typ=at+jwt` per RFC 9068 if the issuer follows that profile, and validate `azp`/`client_id` and grant-appropriate scopes. Never assume an ID Token can stand in for an API Bearer credential.

### 12.4. Identity mix-up across issuers

Two issuers may both issue `sub=123`. If the account index uses `sub` alone, an Alpha user can collide with a Beta user. Use a composite identity `(issuer, subject)`, add tenant/owner context, and scope authorization per resource.

### 12.5. Global vs. tenant scope

`scope=orders:read` may look identical in A and B without granting cross-tenant rights. Issuer-signed scopes must be combined with tenant mapping, resource ownership, and business policies. Never let the route path determine tenant authorization on its own.

### 12.6. `X-Tenant` header is not authentication

If the gateway receives:

```http
GET /api/tenants/beta/orders HTTP/1.1
X-Tenant: beta
Authorization: Bearer <TOKEN_ALPHA>
```

`X-Tenant` may help select pre-authentication context **if explicitly designed**, but it cannot escalate permissions. In the demo, even with `X-Tenant: beta`, an Alpha token cannot read tenant Beta because `TenantGuard` relies on the verified issuer and URL tenant.

If a proxy forwards an `X-Verified-Issuer` header, the backend **may trust it only when** the gateway authenticates the token, strips all client-supplied headers of the same name, and enforces mTLS/network authentication across hops. External clients must never be able to spoof this header.

### 12.7. Never omit per-issuer audience checks

A single issuer may mint access tokens for several different APIs. Configure `audience` per issuer and fail closed on mismatch. If issuers use distinct `aud` values, never build a universal wildcard audience. **A token meant for the Billing API must never call the Orders API simply because it was signed by an approved issuer**.

### 12.8. Expired JWTs can linger in caches

If a gateway caches Authentication or authz decisions longer than `exp`/revocation SLAs, invalid tokens may keep working from cache. Enforce TTL limits, key caches by issuer/token/authz context, and never cache grants past token expiry. Authorization errors and revocations both need metrics and refresh policies.

## 13. JWKS Discovery, Caching, and Rotation

### Why do per-issuer managers cache keys?

Public keys are typically fetched from JWKS and cached to reduce network overhead. A proper cache balances:
- OP key rotation (publishing the new `kid` before signing tokens with it).
- Network timeouts and OP outages.
- Preventing untrusted issuers from flooding cache entries.
- Eviction/failure policies, TTLs, and lifecycle metrics.

**Standard rotation timeline:**

```text
T0  OP JWKS has key K1; tokens are signed with K1
T1  OP publishes K2 alongside K1 (JWKS contains K1 + K2)
T2  OP starts signing new tokens with K2
T3  RS cache refreshes and can verify K2
T4  Once K1 tokens expire, OP removes K1
```

If the OP removes K1 too early, in-flight K1 tokens within their TTL will fail. If the gateway caches K1 too long after a key-compromise incident, forged tokens may continue to be accepted. Rotation policies and emergency responses must align with your threat model.

### Fail-closed and availability

If an issuer's JWKS endpoint is unavailable:
- Tokens requiring an uncached key cannot be verified → request authentication fails.
- Never fall back to **another issuer's keys** or "skip signature verification."
- Avoid unbounded retries and blocking the event loop.
- Enforce timeouts, connection pools, and monitor p95/p99 latency and error rates.
- Use health/readiness semantics aligned with multi-issuer realities: do not mark the whole gateway dead just because one tenant's OP is down if service policy allows other tenants to continue serving.

### Accurate per-issuer caching

Cache keys must bind **issuer/JWK URI/algorithm/kid** appropriately to prevent mixing keys across issuers or tenants. If the registry updates dynamically, handle invalidation atomically with versioned config and auditing.

## 14. Dynamic Issuer Onboarding/Offboarding

A static allowlist is easy to audit, yet multi-customer gateways often need to add/remove tenants without restarts. Design a **control plane**:

1. Admin verifies the OP's identity, issuer URI, and customer/tenant contact.
2. Validate HTTPS/TLS, exact issuer, metadata/JWKS URI, audience, and algorithms.
3. Ensure the issuer is not erroneously mapped to multiple tenants against design.
4. Approve the record (issuer, tenant, jwks, aud, key policy) and persist it in an access-controlled store.
5. Build decoders/managers **exclusively from approved records**, never from unverified JWTs.
6. Publish versioned config/atomic snapshots to gateway instances.
7. Health-check issuer readiness and test a sample signed JWT.
8. Audit who added, edited, or disabled records; support rollback.
9. Offboard: remove the manager/trust channel, purge caches, and verify old-issuer JWTs return 401.
10. Ensure stale nodes/regions do not keep honoring disabled issuers past SLA.

Spring Security docs show a `JwtIssuerReactiveAuthenticationManagerResolver` constructor backed by a runtime-modifiable repository. However, that repository must enforce **allowlist/trust validation**. Never use a lambda like:

```java
// ANTI-PATTERN: issuer from an unverified JWT used as an arbitrary URL.
issuer -> Mono.just(
        new JwtReactiveAuthenticationManager(
                ReactiveJwtDecoders.fromIssuerLocation(issuer)))
```

When adding an issuer, the manager must be built from an **approved policy record**; never let the resolver accept arbitrary observed `iss` values automatically.

### Disabling a tenant vs. key rotation

- **Disable issuer/tenant:** must reject all tokens from that issuer, even validly signed ones. Delete the trust record and push updated config across the gateway fleet.
- **Rotate JWK keys:** keep the issuer valid while updating the key set per the OP.
- **Revoke an individual token:** self-contained JWTs do not support instant revocation on their own; use a `jti` denylist/introspection/`authz_version` depending on SLA.
- **Remove user permissions:** JWT scope snapshots can become stale; use current-state authorization if immediate effect is required.

## 15. Reactive WebFlux: Avoiding Blocking and Managing Errors

### 15.1. Never block the event loop

`ReactiveJwtDecoder` and `ReactiveAuthenticationManagerResolver` run inside the reactive pipeline. Never call `.block()`, `Thread.sleep`, or synchronous JDBC directly inside an auth filter.

If the tenant registry lives in a database:
- Use R2DBC, reactive Redis, or WebClient.
- Bound concurrency and set timeouts; never retry indefinitely against identity sources.
- Cache managers from approved registry snapshots.
- Repository errors must never turn into "accept the token anyway."
- Never call `.subscribe()` manually in a security chain; Spring manages subscriptions.

### 15.2. Why 401 and 403 must stay distinct

If an unknown-issuer JWT returns 403 "permission denied," monitoring may mistake an authentication failure for an authorization failure. Following the pipeline:
- Resolver finds no trusted issuer/manager, or decoder rejects → 401.
- Authenticated Jwt fails tenant/path/scope checks → 403.
- Public route → 200 even without Bearer.
- JWKS unavailable errors may surface as 401/5xx depending on framework/cause handling; the API must never leak key endpoints or tokens.

Never write a catch-all `onErrorResume(e -> allow)`. If customizing error responses, preserve Bearer-token authentication semantics and `WWW-Authenticate` headers where appropriate without exposing sensitive details in the body.

### 15.3. Proxy/Gateway forwarding

If the gateway authenticates at the edge and forwards requests:
- Use mTLS or network identity for edge → backend.
- The backend must not trust `X-User`/`X-Tenant` headers that external clients could spoof.
- The gateway must strip/sanitize client-supplied headers before attaching verified identity.
- Explicitly design token forwarding vs. identity propagation; if the backend verifies JWTs independently, forward the right token or use token exchange.
- CORS preflights carry no Bearer token; handle CORS before authentication when browser clients are supported.
- Never include raw Authorization values in logs, traces, public cache keys, or metric labels.

### 15.4. Multi-tenant logging

Safe logs should include only:
- request ID/correlation ID,
- route/template and status code,
- allowlisted issuer alias or post-auth tenant ID,
- authorization outcome code, latency, cache hit/miss, and key ID if allowed by audit policy.

**Never log:** raw JWTs, signatures, Authorization headers, unsanitized raw unverified `iss`, full JWK material beyond necessary public metadata, email/PII from claims, or full exception messages containing tokens.

## 16. Anti-Pattern Analysis

| Anti-pattern | Why It Is Dangerous | Replace With |
| --- | --- | --- |
| Accepting any issuer and discovering from `iss` | Attacker-supplied token specifies its own issuer and public key | Exact approved allowlist/registry |
| `iss.startsWith("https://idp")` | Prefix/hostname/path confusion | Exact string match against issuer metadata |
| Using one decoder without issuer check | Tokens from another key source under wrong policy may slip through | Per-issuer validators |
| Checking signature only and skipping `aud` | Tokens issued for another API work here | Expected audience validation |
| Using `kid` as a URL to fetch keys | JKU/KID injection/SSRF | Key selection inside trusted JWKS |
| Using `sub` as a global user ID | User ID collisions across issuers | Composite `(iss, sub)` identity |
| `scope=orders:read` grants access to all tenants | Cross-tenant IDOR | TenantGuard + DB ownership |
| Trusting client `X-Tenant` as a verified claim | Header spoofing | Verified issuer/tenant policy |
| Accepting ID Tokens for APIs | Token substitution | Access-token audience/type validation |
| Combining trusted issuers A/B into one wildcard JWKS | Key confusion | Per-issuer managers and keys |
| Letting unknown issuers instantiate new managers | Dynamic trust/DoS/SSRF | Deny unknown; admin onboarding |
| Disabling validation during OP outage | Severe fail-open | Fail closed, reliability policy |
| Skipping cross-signed JWT tests | Key confusion goes undetected | Signed A/B RSA tests |
| Testing only with `mockJwt()` | Bypasses decoder, skips signatures | Unit signed-JWT + HTTP auth tests |
| Disabling CSRF globally on browser apps | Removes protection on cookie-auth actions | Separate chains/CSRF per client model |
| Omitting expiry/nbf checks | Stale/future tokens accepted | JwtValidators + clock skew policy |
| Allowing tenant users to edit trust config | Enables self-approval of issuers | Admin control plane, review/audit |

## 17. Production Deployment Checklist

- [ ] Issuer list comes from a **trusted source**, operator/admin-governed, with clear versioning/auditing.
- [ ] Unknown `iss` is rejected, **never triggering discovery against unapproved issuers**.
- [ ] `JwtIssuerReactiveAuthenticationManagerResolver` is used properly in **WebFlux**; not confused with Servlet.
- [ ] Each issuer maps to the right JWKS/key source, algorithm policy, and validators.
- [ ] JWT signatures are verified **before trusting claims to grant permissions**.
- [ ] Exact `iss` matching is explicitly validated, not just "manager selected."
- [ ] `exp` and `nbf`/clock skew are validated under an explicit contract.
- [ ] `aud` matches the resource server and per-issuer/tenant policy.
- [ ] If using RFC 9068, `at+jwt` token type and profile claims are evaluated.
- [ ] `jku`/`x5u`/`kid` are never trusted outside the approved key source.
- [ ] Tenants are never taken solely from URL/query/header; always reconciled with verified identity and policy.
- [ ] `scope` does not replace DB/resource-level ownership permissions.
- [ ] Principal/audit keys combine issuer+subject; no multi-issuer collisions.
- [ ] TLS/hostname validation on every hop/JWKS fetch; outbound egress is restricted.
- [ ] Maintain JWKS cache/rotation policies and an emergency key-compromise runbook.
- [ ] Issuer disable/offboarding purges trust/caches across the entire cluster.
- [ ] Revocation/permission changes have an explicit freshness SLA for self-contained JWTs.
- [ ] Never block the event loop when fetching keys/registry; no unbounded retries.
- [ ] 401/403 and error responses never leak raw tokens/claims/keys.
- [ ] Never log Authorization/raw JWTs, query tokens, or verbatim unverified issuers.
- [ ] Real tests for two RSA issuers, cross-key, unknown issuer, wrong audience, exp/nbf.
- [ ] Tests for cross-tenant URLs/ownership and missing scopes at the gateway.
- [ ] Tests for multi-node deployments, JWKS cache misses/rotation/outages, and control-plane updates.
- [ ] Upgrade to a Spring Security release patched for advisories (especially issuer validation) and run the regression suite.

## 18. Self-Check Questions

**1. Can `iss` be trusted immediately after Base64-decoding a JWT?**  
No. It is an unverified claim and may only be used as a hint to select a **trusted manager**, never to grant privileges.

**2. What is the job of `JwtIssuerReactiveAuthenticationManagerResolver`?**  
It reads `iss` from the Bearer token to pick the matching `ReactiveAuthenticationManager` in a multi-issuer reactive architecture.

**3. What benefit does `fromTrustedIssuers(...)` provide?**  
It creates a resolver that accepts only allowlisted issuers and initializes/fetches managers lazily per the documentation.

**4. Why must the issuer match exactly?**  
To prevent prefix/path/hostname confusion and ensure the token belongs to a registered issuer.

**5. Is checking the signature alone enough?**  
No. You also need issuer, expiry/nbf, audience, token type/scopes, and tenant/resource authorization.

**6. Can issuer A's key be used to verify a token claiming `iss=B`?**  
No. Manager B must use key source B; cross-signed tokens are rejected.

**7. What role does `kid` play?**  
Selecting a key inside the trusted JWKS; not permission to fetch an arbitrary key URL.

**8. Why is `aud` critical?**  
It prevents tokens issued for another API/client from being accepted by the current API.

**9. If the same issuer serves 10 tenants, can the issuer serve as the tenant ID?**  
No. You need a verified tenant claim plus current membership/resource authorization.

**10. Are two issuers both issuing `sub=123` the same user?**  
Not automatically. Use the composite identity `(iss, sub)`.

**11. Can token A with `orders:read` read tenant B?**  
No, if TenantGuard and business policies enforce cross-tenant checks.

**12. What must an unknown issuer return?**  
A 401 authentication failure, without fetching metadata from an arbitrary issuer.

**13. Does `mockJwt()` verify signatures?**  
No. It simulates an authenticated JWT principal to test authorization.

**14. How do you test real key confusion?**  
Sign a JWT with private key B while claiming `iss=A`, and verify manager A's decoder rejects the signature.

**15. Does `NimbusReactiveJwtDecoder.withJwkSetUri` automatically know the expected issuer?**  
No; you must configure an explicit issuer validator.

**16. If the JWKS endpoint is down, should signature checks be skipped?**  
No. Fail closed with safe error details; maintain separate caching/reliability policies.

**17. Is updating the issuer allowlist from user input safe?**  
No. Trusting issuers is a control-plane change requiring authorization, validation, review, and auditing.

**18. Does a valid JWT missing a required scope return 401 or 403?**  
Typically 403, because it is authenticated yet unauthorized.

**19. Why test egress behavior on unknown issuers?**  
To confirm the code does not turn an untrusted `iss` into a URL and cause SSRF.

**20. Does a validly signed JWT automatically reflect user permissions that were just revoked?**  
No. Self-contained claims are a snapshot; revocation/current-state checks are needed for immediate effect.

### Practice Exercises

1. In `IssuerRoutingTests`, modify an Alpha token to claim Beta while signed by Alpha. Explain why routing picks manager Beta and the signature is rejected.
2. Add issuer Gamma to app config and the approved registry; write signed-RSA tests where valid Gamma passes and unknown Delta is rejected.
3. Change Alpha's expected audience to `billing-api`; send an `orders-api` token and observe the error.
4. Create a JWT with a future `nbf` and test authentication failure via the timestamp validator.
5. Test an `iss` with a trailing slash or altered path; verify the exact matcher does not normalize it away.
6. Add a `tenant_id` claim for the shared-issuer model, reconciling it against tenant/path/resource ownership after verification.
7. Create Alpha and Beta tokens both having `sub=employee-1`; design a composite identity key.
8. Stand up a local JWKS HTTP test server and signed tokens, send Bearer headers via WebTestClient without mocking auth, and verify 200/401/403.
9. Simulate JWKS rotation from K1 → K2 and inspect key cache behavior before and after refresh.
10. Simulate issuer B being unavailable; verify token A succeeds without calling B and B requests fail closed.
11. Design a procedure to disable issuer A and test that every instance stops accepting token A after rollout.
12. Evaluate why `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` suffices for uniform setups yet a custom registry is needed when audiences/JWKS differ.
13. Verify in DevTools/proxy logs that raw Authorization headers are never recorded.
14. Configure trusted proxies and verify clients cannot spoof verified tenant headers.
15. Write a policy enforcing **scope + tenant + order ownership**, not just the scope claim.
16. Create an alert for spikes in unknown-issuer 401s without storing raw untrusted issuers/tokens.
17. Review CVE-2026-22748 and explain why calling `setJwtValidator(JwtValidators.createDefaultWithIssuer(...))` is necessary when building custom decoders on older versions.
18. Compare a multi-issuer gateway against deploying one Resource Server per tenant in terms of isolation, latency, operations, and blast radius.

## 19. Official References

- [Spring Security — Reactive Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): `JwtIssuerReactiveAuthenticationManagerResolver`, trusted issuers, dynamic managers, and warnings about untrusted issuers.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): signatures, issuer/exp/nbf, `ReactiveJwtDecoder`, validators, and audience.
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/site/docs/6.2.3/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html): `fromTrustedIssuers` and manager-repository constructor.
- [Spring Security API 6.3 — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): `withJwkSetUri`, `withPublicKey`, and `setJwtValidator`.
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange` and custom reactive authorization.
- [Spring Security API — AuthorizationContext](https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/web/server/authorization/AuthorizationContext.html): URI path variables via `getVariables()`.
- [Spring Security — Reactive OAuth2 Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` tests authorization, not decoder signatures.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `@ConfigurationProperties` and map binding.
- [Spring Security Advisory CVE-2026-22748](https://spring.io/security/cve-2026-22748): risk of missing issuer validation when configuring per-issuer decoders on unpatched versions.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `nbf`.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key confusion, JWT substitution, and validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token type, audience, and access-token claims.
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer and JWK Set metadata.
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): TLS, authn/authz, and token validation.

**Remember:** In a multi-tenant gateway, `iss` from an **unverified JWT is only a hint for picking a manager**. The server must select **exclusively from issuers in an allowlist it manages**, then use the matching issuer's decoder/keys to **verify signature, exact issuer, `exp/nbf`, audience, and token profile**. Only after authentication should claims/authorities be used to **authorize the tenant and resource**; a valid JWT for Alpha must never automatically access Beta. **Never** construct discovery/JWKS URLs from an arbitrary issuer inside a token.