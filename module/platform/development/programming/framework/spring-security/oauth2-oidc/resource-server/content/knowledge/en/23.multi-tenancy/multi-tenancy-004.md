# Reading unverified claims only to select a strategy, never to grant permissions

In a **Spring Security OAuth 2.0/OIDC Resource Server** serving **multiple tenants**, an API may accept access tokens from multiple Authorization Servers or from multiple realms of the same identity platform. The Resource Server must decide **which decoder, keys, and issuer policy** to use to verify the token before constructing an `Authentication`.

A common implementation pattern is **preliminarily reading the `iss` (issuer) claim from an unverified JWT** to look up the right verification configuration. This step sometimes worries engineers: "If an attacker can tamper with the JWT payload, why read `iss` before checking the signature?"

The answer lies in distinguishing **using untrusted data for routing** from **using untrusted data for authorization decisions**:

- **You may read an unverified claim as a *hint* to select from a list of server-preapproved verification strategies.** This selection **creates no principal, grants no authorities, and allows no API access**.
- **You must never use an unverified claim to grant permissions, determine an accepted tenant, pick an arbitrary key URL, or skip signature/issuer/audience checks.** Trusted values only exist **after the token has passed all required verification**.

This is the topic of the lesson **"Reading unverified claims only to select a strategy, never to grant permissions"**, in the **Multi-tenancy** chapter. It covers the trust model, decoder selection techniques, Spring Security Servlet/WebFlux configuration, cross-tenant attack scenarios, testing, and operating an issuer registry.

> **Scope:** OAuth 2.0 **access tokens** received by a Resource Server via `Authorization: Bearer ...`. OIDC **ID tokens** meant for an OIDC client are not inherently valid as API access tokens. URLs, IDs, and tenant names here are illustrative placeholders, not live services.

## 1. Why does a Resource Server need authentication routing?

Suppose a shared API handles data for three tenants:

| Tenant | Trusted issuer | Resource audience |
|---|---|---|
| North | `https://login.example.test/realms/north` | `orders-api` |
| South | `https://login.example.test/realms/south` | `orders-api` |
| Partner | `https://identity.partner.test/tenant/acme` | `orders-api` |

The client sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <JWT_ACCESS_TOKEN>
~~~

The Resource Server cannot use *just any* public key in the system to accept any JWT. It needs to know which issuer the token purports to come from in order to:

1. Select the matching **trusted JWKS/public key**.
2. Select the **right set of allowed JWS algorithms**.
3. Check that the `iss` claim matches the selected issuer.
4. Check `aud`/`azp`/`client_id`/token type per the issuer and Resource Server contract.
5. Convert **verified** claims into a principal and authorities.
6. Check tenant/resource ownership and business operation permissions.

A compact JWS JWT normally has three parts:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(JWS_SIGNATURE)
~~~

The payload is easy to read via Base64URL decoding. **Readable does not mean trustworthy**: an attacker can construct a JWT-shaped string and write:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "admin",
  "tenant_id": "north",
  "scope": "orders.read orders.delete",
  "aud": ["orders-api"]
}
~~~

without being able to sign the token using North's real key. Prior to signature verification, `iss`, `sub`, `tenant_id`, `scope`, and `aud` are all **sender-controlled data**.

### 1.1. What is allowed with an unverified `iss`

~~~text
Unverified JWT:
    iss = "https://login.example.test/realms/north"
              |
              v
Look up EXACT issuer in server-controlled trusted registry
              |
       +------+------+
       |             |
    Absent       Exact match
       |             |
       v             v
     Reject      Select North decoder
                       |
                       v
               Verify JWS + claims
                       |
                +------+------+
                |             |
             Invalid        Valid
                |             |
                v             v
              Reject     Create Authentication
                           then authorize
~~~

**Right mental model:** an unverified `iss` is a **routing hint**, much like reading a label on a parcel **before** inspecting the tamper seal. The label tells you which inspection desk to send the parcel to; the label **does not prove** the parcel's contents have been verified.

### 1.2. What is strictly forbidden

~~~text
Unverified JWT:
    scope = "orders.delete"
    tenant_id = "north"
              |
              v
Create GrantedAuthority("SCOPE_orders.delete")   ← WRONG
Trust user belongs to tenant north               ← WRONG
Allow GET/DELETE on Orders API                   ← WRONG
~~~

If the system grants permissions like that, an attacker only needs to edit the payload, with no need for the Authorization Server's key.

## 2. Distinguishing four levels of trust

Instead of vaguely treating a token as "trusted" or "untrusted," separate the stages clearly:

| Stage | Handler | Data state | What can it do? |
|---|---|---|---|
| **T0: receive string** | Bearer token resolver | Untrusted HTTP header string | Check size limits, Bearer format, prepare authentication |
| **T1: preliminary parse** | Issuer/tenant strategy resolver | **Unverified** claims/header | Select **from the trusted allowlist** or reject |
| **T2: verify** | `JwtDecoder` / `ReactiveJwtDecoder` | JWS + issuer/time/audience/profile verified per policy | Return a verified `Jwt` or an error |
| **T3: authorize** | Authentication converter, authorization managers, domain services | Principal/authorities from verification output | Allow/deny actions on endpoints and data |

Security bugs appear when an application shortcuts from **T1 → T3**.

### 2.1. Parsing is not verifying

These two snippets have completely different meanings:

~~~java
// PARSE ONLY, no evidence the token is trustworthy.
var parsed = com.nimbusds.jwt.JWTParser.parse(token);
String issuerHint = parsed.getJWTClaimsSet().getIssuer();
~~~

~~~java
// VERIFY through a Spring Security decoder with trusted keys/validators.
Jwt verifiedJwt = decoder.decode(token);
~~~

In WebFlux, `ReactiveJwtDecoder.decode(token)` returns `Mono<Jwt>` and must be subscribed to actually execute:

~~~java
Mono<Jwt> verifiedJwt = reactiveDecoder.decode(token);
~~~

Never rely on `JWTParser` as a claims validator in place of JWS verification. `issuerHint` is only enough to **look up the strategy**, never enough to identify the user, tenant, or scopes.

### 2.2. Every claim before verification is untrusted

| Unverified claim/header | What may it select? | What must it never do? |
|---|---|---|
| `iss` | Look up issuer in an approved registry | Conclude that the issuer actually signed the token |
| `kid` | Hint for key selection **inside a trusted JWKS** | Automatically fetch a token-supplied key URL |
| `alg` | Check whether it is in the allowlist | Let the token pick an arbitrary trusted algorithm |
| `tenant_id` | Hint for tenant lookup **inside the registry** if designed for it | Assert the principal belongs to or can read the tenant |
| `aud` | Optionally help select among **trusted** resource configs if truly needed | Skip audience validation or trust scopes from self-declared aud |
| `scope`, `roles` | **Should not be used for security routing** normally | Create `GrantedAuthority` prior to verification |
| `sub` | Not needed to select a decoder | Establish user identity prior to verification |
| `jku`, `x5u` | Must never determine trusted URLs | Perform outbound HTTP calls to attacker-specified URLs |

Even a claim matching a value in the trusted registry **is not a verification result**. It only locates the configured verifier. If the token's signature is invalid, it must still be rejected.

## 3. Two boundaries: choosing a strategy vs. verifying with that strategy

~~~mermaid
flowchart TD
    C["Client sends Bearer JWT"] --> P["Minimally parse unverified iss"]
    P --> A{"Is iss in trusted issuer registry?"}
    A -->|No| X["Reject: do not trust token"]
    A -->|Yes| D["Select registered decoder for that issuer"]
    D --> V{"Valid JWS + alg + iss + exp/nbf + aud + profile?"}
    V -->|No| X
    V -->|Yes| T["Verified Jwt"]
    T --> M["Map authorities from verified claims"]
    M --> B{"Does requested tenant match confirmed tenant?"}
    B -->|No| F["Deny: cross-tenant"]
    B -->|Yes| R["HTTP/method/object authorization"]
    R --> O["Return data if authorized"]
~~~

**There is no shortcut from "parse `iss`" to "map authorities."** Every permission passes through token verification and tenant policy.

### 3.1. What if an attacker spoofs tenant North's `iss`?

For example, an attacker crafts a JWT with:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "tenant_id": "north",
  "scope": "orders.admin"
}
~~~

The resolver sees `iss` in the registry and **picks North's decoder**. However, the attacker lacks North's private signing key, so the decoder rejects the JWS. This is the **right** behavior: allowing untrusted data to influence **which verifier is selected**, while **never allowing it to influence the verification outcome**.

### 3.2. What if an attacker sets `iss` to a URL they own?

Example:

~~~json
{
  "iss": "https://attacker.example.test/issuer",
  "scope": "orders.admin"
}
~~~

If the system does:

~~~java
// ANTI-PATTERN: do not create a decoder from an arbitrary issuer URL.
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuerHint);
return decoder.decode(token);
~~~

then the attacker can operate their own issuer and signing keys, trying to get the API to accept tokens **outside the authorized issuers**. Furthermore, arbitrary URLs introduce **SSRF**, DNS/redirect abuse, internal endpoint probing, and connection pool exhaustion.

**Right policy:** `issuerHint` must match a **pre-registered/pre-approved issuer**. Never automatically trust a new issuer simply because a token declares an address.

### 3.3. What is a "trusted registry"?

A trusted registry is **server-side controlled** configuration:

~~~text
https://login.example.test/realms/north
    → trusted JWKS: https://login.example.test/realms/north/jwks
    → allowed algorithms: RS256
    → accepted audience: orders-api
    → tenant binding: north

https://login.example.test/realms/south
    → trusted JWKS: https://login.example.test/realms/south/jwks
    → allowed algorithms: RS256
    → accepted audience: orders-api
    → tenant binding: south
~~~

This list is managed via configuration, a protected tenant admin system, or an approved onboarding workflow. It is **not** an issuer list automatically "learned" from JWTs passing through the API.

When adding a new tenant/issuer, verify metadata/trust, keys, audience, token profile, ownership, and lifecycle before transitioning the tenant to active.

## 4. Three multi-tenant models to distinguish

Not every multi-tenant architecture needs to read an unverified `iss` to pick a decoder.

### 4.1. Each tenant has its own issuer

~~~text
Tenant north → iss=https://login.example.test/realms/north
Tenant south → iss=https://login.example.test/realms/south
Tenant west  → iss=https://identity.partner.test/west
~~~

This is the clearest model for an issuer resolver: **`iss` is the routing hint**, and each issuer has its own trust configuration. Once the decoder is chosen, the JWT must be validated against **that exact issuer**.

Example JWT for North:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "user-123",
  "aud": ["orders-api"],
  "tenant_id": "north",
  "scope": "orders.read",
  "exp": 1933459200
}
~~~

The `exp` value is illustrative only. Even with `tenant_id` set to `north`, the Resource Server must still match the tenant in the **verified** token against the requested tenant, and if needed, against the issuer ↔ tenant mapping.

### 4.2. Multiple tenants share one issuer

~~~text
Tenant north ─┐
Tenant south ─┼── iss=https://login.example.test/company
Tenant west  ─┘
~~~

In this case, **`iss` is not enough to pick a tenant policy** because all tenants share the same issuer and public keys. You can use a single trusted decoder and read the `tenant_id` claim **after verification**, enforcing tenant binding and data permissions.

If you ever select a pre-decode per-tenant policy using an unverified `tenant_id`, that policy must remain **a constrained choice within a trusted registry**, and final validation must verify the signed tenant claim matches the selection. Never turn an unverified `tenant_id` into access to that tenant.

### 4.3. Selecting tenant from path/hostname

Example:

~~~http
GET /tenants/north/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <JWT>
~~~

The path can specify **which tenant is being requested**, yet **does not prove the caller belongs to that tenant**. Authentication must still verify the token, and authorization matches the requested tenant against the verified identity.

If using a hostname like `north.api.example.test` as a tenant selector, configure explicit trusted host routing/gateway rules. Never arbitrarily trust client-sent `Host` or `X-Forwarded-Host` as permission evidence; forwarded headers are only trustworthy when normalized by a trusted proxy.

### 4.4. Model and trust boundary matrix

| Architecture | Data allowed for pre-verify routing | Evidence required post-verify |
|---|---|---|
| One issuer per tenant | Unverified `iss` to pick decoder from allowlist | Signature for that issuer, `aud`, timestamps, tenant binding |
| One issuer for all tenants | Usually no claim routing needed | Shared issuer signature, valid `tenant_id`, tenant permissions |
| Tenant in path | URL path to select application context | Verified token permitted to access tenant path |
| Tenant from trusted reverse proxy | Gateway-approved/controlled context | Verified token bound to tenant context |
| Multiple issuers + multiple token types | Hint matching trust registry, or separate endpoints/chains | Each profile fully validated by its dedicated verifier |

**Preliminary reading** is a dispatch mechanism. It never eliminates the responsibility for **verification** and **tenant authorization** in any model.

## 5. Spring Security Servlet example: accepting only trusted issuers

Spring Security provides `JwtIssuerAuthenticationManagerResolver` when a Resource Server accepts JWTs from multiple issuers. Instead of hand-parsing claims/tokens inside a custom filter, use the framework-provided resolver with a list of trusted issuers.

### 5.1. Dependencies

Spring Boot Servlet / Spring MVC example:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

JWT verification also requires an appropriate JOSE library; modern Spring Boot Resource Server starters usually pull in the needed dependencies. If declaring modules manually, check `spring-security-oauth2-jose` and a compatible Nimbus version.

### 5.2. Using `fromTrustedIssuers(...)`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultiIssuerServletSecurity {

    private static final String NORTH =
        "https://login.example.test/realms/north";
    private static final String SOUTH =
        "https://login.example.test/realms/south";

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            NORTH,
            SOUTH
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver issuerResolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(issuerResolver))
            .build();
    }
}
~~~

This example uses the `fromTrustedIssuers(...)` API available in modern Spring Security versions; when building against an older version, check the matching factory/constructor instead of copying method names absent from your dependency.

### 5.3. Execution sequence

When a client sends a JWT with `iss=NORTH`:

1. The resolver reads the issuer hint from the **unverified** JWT.
2. The resolver checks whether the issuer hint matches **one of the two trusted issuer strings**.
3. If not in the list: reject authentication, **make no outbound calls to unknown URLs**.
4. If it is North: select/create the authentication manager and decoder for North.
5. The decoder uses North's trust configuration to verify the JWS and claims, including the expected issuer.
6. If the JWT was genuinely issued by North and all token validators pass: build principal and authorities.
7. HTTP authorization checks `SCOPE_orders.read`, and the service proceeds to verify tenant/object ownership.

`JwtIssuerAuthenticationManagerResolver` handles **selecting the authentication manager**; it does not automatically enforce every API-specific audience, tenant ownership, or token profile policy. In production, add those checks according to each issuer's contract.

### 5.4. Do not declare a global `JwtDecoder` and assume the resolver uses it

If an application declares both `@Bean JwtDecoder` and `authenticationManagerResolver(...)`, check **which authentication manager the resolver actually picks**. Never assume validators attached to one decoder bean are automatically used by every manager created by the resolver.

For example, an audience validator configured on decoder bean A **does not automatically propagate** to decoder B created by the resolver. Therefore, to enforce audience across all issuers:

- Configure validators on **each decoder/manager actually selected by the resolver**, or
- Use a verification check operating on the **verified** token within the contract's authentication/authorization pipeline, **never** on unverified claims.

The next section demonstrates building authentication managers from a registry to actively govern issuer/audience checks.

## 6. Servlet example with a decoder registry and dedicated audience validator

When each issuer has its own JWKS URI, algorithm, or audience, the Resource Server can build a **map of pre-configured authentication managers**. The `iss` claim is preliminarily parsed **solely to look up the map**; each manager must still verify the token.

### 6.1. First, build a manager for one trusted issuer

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

final class IssuerManagers {

    static AuthenticationManager jwtManager(
            String issuer,
            String jwksUri,
            String requiredAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        return provider::authenticate;
    }
}
~~~

Here:

- `issuer` and `jwksUri` must come from a **trusted registry**, never directly from the JWT.
- `SignatureAlgorithm.RS256` is an illustrative allowlist; the real algorithm must match the issuer's token profile.
- `JwtValidators.createDefaultWithIssuer(...)` applies issuer and version-appropriate default timestamp checks.
- `audienceValidator` guarantees the token was issued for `orders-api` or the configured audience.
- `setJwtValidator(...)` **replaces** the existing validator set, so you must compose all needed validators rather than setting only audience.
- `JwtAuthenticationProvider` creates an `Authentication` only after the decoder succeeds.

These are Servlet components, not WebFlux: synchronous `JwtAuthenticationProvider` and `AuthenticationManager`.

### 6.2. Registry mapping issuer → manager

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;

@Configuration
class TrustedIssuerManagerRegistry {

    @Bean
    Map<String, AuthenticationManager> trustedIssuerManagers() {
        return Map.of(
            "https://login.example.test/realms/north",
            IssuerManagers.jwtManager(
                "https://login.example.test/realms/north",
                "https://login.example.test/realms/north/jwks",
                "orders-api"
            ),
            "https://login.example.test/realms/south",
            IssuerManagers.jwtManager(
                "https://login.example.test/realms/south",
                "https://login.example.test/realms/south/jwks",
                "orders-api"
            )
        );
    }
}
~~~

This map is built from a **fixed server-owned list**. There is no "auto-create a decoder for any other issuer" fallback and no URL taken from unverified headers or claims.

When the registry is managed from a database or onboarding service, the requirement is identical: **only approved ACTIVE records** may act as trust sources; client-submitted or unreviewed issuer records must never participate in authentication.

### 6.3. Have the resolver select only registered managers

Spring Security provides resolver mechanisms for selecting by issuer in a registry. A common form across supported versions is:

~~~java
// Concept: bind the registry as the per-issuer manager source.
JwtIssuerAuthenticationManagerResolver resolver =
    new JwtIssuerAuthenticationManagerResolver(
        issuer -> trustedIssuerManagers.get(issuer)
    );
~~~

This illustrates the constructor taking a function/`AuthenticationManagerResolver<String>` used in several Spring Security versions. Check the constructor signature against your actual dependency: newer versions favor `fromTrustedIssuers(...)` for issuer lists, while injecting custom managers uses the corresponding API or a dedicated resolver.

**Critical security boundary independent of factory name:** if `trustedIssuerManagers.get(issuer)` has no entry, never auto-create a new manager from an arbitrary issuer URL. Never return a default manager that accepts all tokens.

### 6.4. Never use an unverified `scope` to select a manager

Anti-pattern:

~~~java
// ANTI-PATTERN: token self-declares scope to pick a weaker manager.
if (unverifiedClaims.getStringClaim("scope").contains("admin")) {
    return managerWithoutAudienceValidation;
}
return ordinaryManager;
~~~

An attacker can set `scope=admin` to enter the weaker policy branch. Even if both branches verify signatures, choosing **a looser validator set based on an unverified claim** creates trust asymmetry and token confusion risks. Route by **trusted issuer/profile/endpoint policy**, then enforce full validation and authorization.

## 7. Spring Security WebFlux: issuer resolver in reactive applications

WebFlux does not use Servlet `HttpSecurity`/`SecurityFilterChain`. It uses `ServerHttpSecurity`/`SecurityWebFilterChain`, `ReactiveAuthenticationManager`, and `ReactiveJwtDecoder`. Yet the trust rule is identical: **an unverified routing hint may only pick a trusted manager; the manager actually verifies before creating authentication**.

### 7.1. WebFlux dependencies

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Do not use Servlet `SecurityFilterChain` beans in place of `SecurityWebFilterChain` in a reactive application. When a project mixes Spring MVC and WebFlux starters, confirm which application type is active so you do not test the wrong pipeline.

### 7.2. `JwtIssuerReactiveAuthenticationManagerResolver`

In Spring Security versions supporting `fromTrustedIssuers(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class MultiIssuerReactiveSecurity {

    private static final String NORTH =
        "https://login.example.test/realms/north";
    private static final String SOUTH =
        "https://login.example.test/realms/south";

    @Bean
    JwtIssuerReactiveAuthenticationManagerResolver
    trustedReactiveIssuerResolver() {
        return JwtIssuerReactiveAuthenticationManagerResolver
            .fromTrustedIssuers(NORTH, SOUTH);
    }

    @Bean
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            JwtIssuerReactiveAuthenticationManagerResolver resolver) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

In this configuration, the resolver can read the unverified `iss` to pick **one of the two issuers**. It must never grant permissions solely because `iss=NORTH` is present. Each manager must verify the JWT against its corresponding issuer, keys, and validators.

Depending on the Spring Security version, the reactive resolver's constructors/factories may vary; the goal of the snippet is using the **trusted-issuer API**, not automatically trusting any issuer declared in a token. If your version lacks that factory, implement the resolver with a trusted registry preserving the same fail-closed behavior.

### 7.3. Why not `Mono.just(...)` from unverified claims?

WebFlux anti-pattern:

~~~java
// ANTI-PATTERN: building a principal from unverified data.
return Mono.just(
    new UsernamePasswordAuthenticationToken(
        unverifiedClaims.getSubject(),
        token,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    )
);
~~~

`Mono` is merely an asynchronous wrapper. Using Reactor **does not make data trustworthy**. If `unverifiedClaims` has not passed through a decoder, this code still grants invalid access inside a reactive pipeline.

### 7.4. Building a reactive manager with a custom audience validator

An illustrative helper:

~~~java
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;

final class ReactiveIssuerManagers {

    static ReactiveAuthenticationManager create(
            String trustedIssuer,
            String trustedJwksUri,
            String requiredAudience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(trustedJwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Wrong resource audience",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(trustedIssuer),
                audience
            )
        );

        return new JwtReactiveAuthenticationManager(decoder);
    }
}
~~~

With this manager, a North-issued JWT **cannot pretend to be South** and pass South's decoder merely by changing `iss`, because signature, issuer, timestamp, and audience validators must all satisfy South's trust configuration.

If multiple issuers have different audiences, configure each manager with its matching audience. If an issuer mints access tokens with a specific profile (such as `typ=at+jwt`, `client_id`, `tenant_id`, or requiring `exp`), add the corresponding validators to that issuer's decoder.

### 7.5. Never block the event loop just to pick an issuer

If the trusted registry lives in a database, do not execute blocking JDBC or synchronous HTTP calls directly inside the reactive issuer resolver on the event loop. You can:

- Maintain a safely updated **in-memory registry snapshot**.
- Use a **reactive** repository/client for registry data when needed.
- If blocking operations are unavoidable, dispatch properly onto a bounded scheduler with load limits.

Remember: good performance never relaxes trust policy. A stale cached registry still holding a **disabled** issuer affects authentication, so plan invalidation/versioning and freshness bounds.

### 7.6. One issuer with multiple tenants on WebFlux

If all tenants share one issuer, typically use a single `ReactiveJwtDecoder` with issuer/audience validators, then verify the tenant post-authentication. Do not spin up hundreds of decoders keyed by unverified `tenant_id` when the keys and issuer are identical without a real design reason.

A service pattern:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

Mono<Boolean> tokenAllowsTenant(
        Authentication authentication,
        String requestedTenant) {

    if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
            || !authentication.isAuthenticated()) {
        return Mono.just(false);
    }

    // Jwt here has already been verified by ReactiveJwtDecoder.
    String verifiedTenant =
        jwtAuth.getToken().getClaimAsString("tenant_id");

    return Mono.just(
        requestedTenant != null
            && requestedTenant.equals(verifiedTenant)
    );
}
~~~

This example method takes an `Authentication` **that has already passed Spring Security authentication**. It illustrates post-verification tenant binding rather than a complete authorization policy: if a principal has multiple valid tenants, check membership via verified claims or a trusted entitlement system; also check access on the specific record/order.

Never take `authentication.getName()` and treat it as a tenant ID; `sub` and tenant are two separate concepts.

## 8. Selecting by unverified issuer must not skip subsequent issuer validation

Suppose the resolver does:

~~~text
unverified iss = north → select North decoder
~~~

What happens if North's decoder checks only the JWS signature without verifying the `iss` claim?

In multi-issuer setups with **shared keys or overly broad key trust**, a token signed by another issuer might still pass signature verification. Without checking the **verified** issuer, the API risks mixing token profiles.

### 8.1. Why re-verify `iss` after choosing the decoder?

The minimum trust policy should be:

~~~text
issuer hint selects North manager
AND JWT signature valid using trusted North keys
AND verified iss == configured North issuer
AND token timestamps valid
AND aud/resource matches Orders API
AND token type/profile matches
~~~

The issuer hint only selects the strategy; it can never replace the **verified issuer** condition.

### 8.2. What if two issuers share a key?

Some environments reuse the same signing key across multiple realms or tenants. That is not ideal for every threat model, and where it exists, **signature verification alone cannot distinguish the issuing source**. The Resource Server must strictly validate both the issuer and token profile, alongside post-verification tenant mapping.

Never conclude "valid key → token definitely belongs to North." A key is evidence within a **configured trust scope**, and the verified issuer claim must match that scope.

### 8.3. Audience and issuer are independent conditions

Example:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

The token has North as issuer, valid signature, and valid timestamps, yet its audience is Billing API. **Orders API must not accept the token just because the issuer is allowlisted.** Check the resource audience and token type/profile per contract.

### 8.4. A South route called with a North token

Request:

~~~http
GET /tenants/south/orders/42 HTTP/1.1
Authorization: Bearer <VALID_NORTH_ACCESS_TOKEN>
~~~

After the North decoder verifies the token, authentication may be **valid**. Yet access to tenant South must be denied if the principal lacks South permissions:

~~~text
Token: verified issuer=north, verified tenant=north
Request: tenant=south

Authentication: succeeds for North JWT
Tenant authorization: cross-tenant denied
~~~

That is why **multi-tenant authorization** must compare the tenant in the path/record against the **verified** token and business policy, rather than assuming "a token valid under any trusted issuer can access every tenant."

## 9. Tenant binding must happen after authentication

There are at least three distinct concepts:

1. **Requested tenant**: from the route, domain name, request parameter, or resource record.
2. **Token-asserted tenant**: from a decoder-verified claim, or from a server-trusted issuer-to-tenant mapping.
3. **Authorized tenant(s) for the principal**: determined by identity, membership, roles, consent, and business policy.

These three values are not automatically equal. One user may belong to multiple tenants, one issuer may serve multiple tenants, and a token may be issued under a policy that does not authorize the requested tenant.

### 9.1. Spring MVC example: post-authentication tenant guard

Suppose a simple contract: **each issuer maps to one tenant** and the JWT includes a `tenant_id` claim re-confirming that tenant. We can define a guard:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public class TenantAccess {

    private static final Map<String, String> TENANT_ISSUER = Map.of(
        "north", "https://login.example.test/realms/north",
        "south", "https://login.example.test/realms/south"
    );

    public boolean allowed(
            Authentication authentication,
            String requestedTenant) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()
                || requestedTenant == null) {
            return false;
        }

        Jwt verifiedJwt = jwtAuth.getToken();
        String expectedIssuer = TENANT_ISSUER.get(requestedTenant);
        String tokenTenant =
            verifiedJwt.getClaimAsString("tenant_id");

        return expectedIssuer != null
            && verifiedJwt.getIssuer() != null
            && expectedIssuer.equals(verifiedJwt.getIssuer().toString())
            && requestedTenant.equals(tokenTenant);
    }
}
~~~

`JwtAuthenticationToken` in the guard is only trustworthy if it comes from a **real Spring Security JWT authentication pipeline**, never an object the client can construct. In unit tests using `Jwt.withTokenValue(...)` solely to test guard logic, explicitly note that it is **not a signature test**.

### 9.2. Using method authorization

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}

@RestController
class TenantOrdersController {

    private final TenantOrderService orders;

    TenantOrdersController(TenantOrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/tenants/{tenantId}/orders/{orderId}")
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "@tenantAccess.allowed(authentication, #tenantId)"
    )
    OrderView get(
            @PathVariable String tenantId,
            @PathVariable String orderId) {

        return orders.loadForTenant(tenantId, orderId);
    }
}
~~~

This pattern **separates tenant permission logic from the controller**; it is not a standalone compilable Java file since `TenantOrderService` and `OrderView` are application types you must implement. Placing `@EnableMethodSecurity` must match your project's Servlet configuration; in WebFlux, use the corresponding reactive method security.

More importantly, `orders.loadForTenant(tenantId, orderId)` must query/verify that **the order actually belongs to that tenant**, not rely solely on the client-sent ID. If the domain service looks up an order by global ID and immediately returns another tenant's row, a URL-based guard can still be bypassed at the record layer.

### 9.3. Queries must keep the tenant inside the data access predicate

A safe mental model:

~~~sql
SELECT id, tenant_id, status, total
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantContext;
~~~

`:verifiedTenantContext` must be derived from **verified authentication + user/tenant policy**. If a query only runs:

~~~sql
SELECT * FROM orders WHERE id = :orderId;
~~~

then receiving `tenantId` in the controller URL does not guarantee the record belongs to that tenant. You still need object-level authorization and the system's multi-tenant data isolation policies.

### 9.4. What if a user can access multiple tenants?

Do not force every application into a "token has exactly one `tenant_id`" rule. When the contract permits a principal to access multiple tenants, establish:

- Verified issuer/subject identity.
- **Signed and verifiable** membership/tenant list claims, or a trusted entitlement service.
- The principal's scopes/roles **within each tenant**, not unrestricted global roles.
- Which tenant the request targets and whether it is among the permitted tenants.
- Resource-specific permissions and freshness checks if memberships can change.

Anti-pattern:

~~~text
Verified JWT:
  tenant_ids = ["north", "south"]
  global role = "ADMIN"

Wrong:
  ADMIN has permissions across all tenants regardless of context

Right:
  requested tenant = south
  valid issuer/profile
  principal holds south membership/permission
  action has valid scope/role inside south
  record actually belongs to south
~~~

If the system only carries an unscoped `orders.read` string without tenant context, decide whether it is global or constrained to the token/resource-confirmed tenant. Never infer multi-tenant privileges from an uncontextualized scope.

## 10. Multi-issuer user identity: `sub` is not enough

In OAuth/OIDC, `sub` is normally a subject identifier scoped to the issuer's namespace. Two different Authorization Servers **can issue the exact same `sub` value to two different people**.

Example:

~~~text
Issuer North: iss=https://login.example.test/realms/north
              sub=123

Issuer South: iss=https://login.example.test/realms/south
              sub=123
~~~

These two tokens **do not prove the same person**. If the Resource Server keys users by `sub` alone, tenant data can collide.

### 10.1. Identity should be scoped to the issuer namespace

A basic identity key:

~~~text
IdentityKey = (verifiedIssuer, verifiedSubject)
~~~

Example:

~~~java
record PrincipalKey(String issuer, String subject) {}

PrincipalKey fromVerifiedJwt(Jwt jwt) {
    if (jwt.getIssuer() == null || jwt.getSubject() == null) {
        throw new IllegalArgumentException("Required identity claim missing");
    }
    return new PrincipalKey(
        jwt.getIssuer().toString(),
        jwt.getSubject()
    );
}
~~~

This method **only accepts a `Jwt` verified by a decoder** in a trusted context. Never extract `iss`/`sub` from a raw JWT parser and build `PrincipalKey` prior to authentication.

In systems with identity federation or account linking, linking multiple issuers to a single account must follow a **dedicated trusted process**, never just matching `sub` or email values.

### 10.2. Do not use email as a default tenant identity

An email in a JWT can change over time, may not be verified across every issuer, and is less stable than a subject ID. Never assume:

~~~text
email=user@example.test
  → has access to tenant example
~~~

Any email/domain → tenant/role mapping must be defined by an approved policy using verified claims, not a heuristic extracted from unverified tokens.

## 11. Decision order: authentication, tenant authorization, domain authorization

A protected API should pass through three gates:

~~~mermaid
flowchart TD
    A["Request + Bearer token"] --> B["Routing hint only to select trusted decoder"]
    B --> C{"JWT verification succeeds?"}
    C -->|No| X["Reject authentication"]
    C -->|Yes| D["Principal from verified claims"]
    D --> E{"Principal allowed in requested tenant?"}
    E -->|No| Y["Deny tenant authorization"]
    E -->|Yes| F{"Has scope/permission for operation?"}
    F -->|No| Y
    F -->|Yes| G{"Resource belongs to allowed tenant/owner?"}
    G -->|No| Y
    G -->|Yes| H["Return data / execute action"]
~~~

| Layer | Question | Data used |
|---|---|---|
| Routing | Which verifier is allowed to inspect this token? | Unverified hint + trusted registry |
| Authentication | Are the issuer/key/signature/claims trustworthy? | Decoder, validators, trusted keys |
| Tenant authorization | Does the identity have access in the requested tenant? | Verified claims + trusted membership/tenant policy |
| HTTP authorization | Which scope/role does the API operation require? | `GrantedAuthority` from authenticated principal |
| Domain authorization | Does the record belong to the permitted tenant/subject? | Trusted DB resource ownership + verified identity |

Never collapse the first two rows into "if a decoder was found, it's authenticated." An issuer in the registry only means the system **knows how to verify tokens for that issuer**, not that every token naming that issuer is valid.

### 11.1. Error classification examples

| Scenario | Failing layer | Typical outcome |
|---|---|---|
| `iss` not in registry | Authentication routing | 401 |
| `iss` in registry but invalid JWS | Decoder authentication | 401 |
| Validly signed JWT but wrong `aud` | JWT validator authentication | 401 |
| Valid signature, issuer, and time, but missing scope | HTTP authorization | 403 |
| Valid North JWT accessing disallowed South tenant | Tenant authorization | 403 or 404 per API anti-enumeration policy |
| JWT with valid scope, order belongs to another tenant | Domain/object authorization | Denied per policy |
| JWKS endpoint unavailable and no trusted cached key | Cannot verify | Not authenticated; HTTP status depends on infrastructure handling |

**Do not rely on status codes alone to prove the right verifier ran.** Tests must verify the actual security chain and matching positive controls.

## 12. If parsing claims manually before verification, constrain it tightly

Spring Security provides built-in issuer resolvers for routing. If your architecture requires writing a custom selector, treat it as a component **processing untrusted input prior to authentication**.

### 12.1. Example selector that only queries a trusted registry

The Java snippet below illustrates **only the manager selection step** for a compact JWS JWT; it does not replace the full OAuth 2.0 Resource Server filter:

~~~java
import java.text.ParseException;
import java.util.Map;

import com.nimbusds.jwt.JWTParser;
import com.nimbusds.jwt.SignedJWT;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

final class TrustedIssuerChooser {

    private final Map<String, AuthenticationManager> managers;
    private static final int MAX_EXAMPLE_TOKEN_CHARS = 8192;

    TrustedIssuerChooser(
            Map<String, AuthenticationManager> trustedManagers) {
        this.managers = Map.copyOf(trustedManagers);
    }

    AuthenticationManager choose(String token) {
        if (token == null || token.isBlank()
                || token.length() > MAX_EXAMPLE_TOKEN_CHARS) {
            throw invalidToken();
        }

        try {
            // PARSE ONLY: signature not verified yet!
            var jwt = JWTParser.parse(token);
            if (!(jwt instanceof SignedJWT signedJwt)) {
                throw invalidToken();
            }

            String issuerHint =
                signedJwt.getJWTClaimsSet().getIssuer();

            AuthenticationManager trusted =
                managers.get(issuerHint);
            if (trusted == null) {
                throw invalidToken();
            }

            // Do not create Authentication from unverified claims.
            return trusted;
        } catch (ParseException | IllegalArgumentException ex) {
            throw invalidToken();
        }
    }

    private static OAuth2AuthenticationException invalidToken() {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token")
        );
    }
}
~~~

`managers` must contain managers **registered and configured by the server**. Once selected, the Spring Security authentication pipeline must pass the raw token to that manager to verify JWS and claims. The code above **is not** an authentication provider and **grants no permissions**.

The `8192` limit is an **example parameter**, not a standard OAuth/JWT limit. Choose bounds based on your actual token profile sizes, proxy/web-server header limits, parsing performance, and risk policy. Huge JWTs or malformed JSON inputs can burn CPU/memory prior to verification; enforce bounds at the gateway/server and parser.

### 12.2. Missing issuer in registry must reject immediately

~~~text
Unverified token claim:
    iss=https://unknown.example.test/issuer

Trusted manager registry:
    North → North manager
    South → South manager

Lookup = null → Reject
~~~

Never add a fallback that automatically calls `JwtDecoders.fromIssuerLocation(issuerHint)` when the map lacks an issuer. An unverified URL must never become a source of trust or keys. Beyond accepting tokens from attacker-controlled issuers, that behavior risks SSRF and key-cache resource exhaustion.

### 12.3. Parse errors must fail closed

Cases to reject:

- Strings that are not compact JWTs matching the accepted profile.
- Base64URL/JSON/JOSE parsing failures.
- Missing, blank, wrong-typed, or non-allowlisted `iss`.
- Tokens exceeding input size/shape bounds.
- JWE/opaque tokens when the current resolver only contracts for JWS and has no matching strategy.

Never guess the issuer from `scope`/`email`/`sub` or fall back to a permissive "generic" manager when routing fails.

### 12.4. Exact issuer matching

These two strings are not necessarily the same issuer:

~~~text
https://login.example.test/realms/north
https://login.example.test/realms/north/
~~~

Never strip slashes, rewrite hosts, alter paths, or match "close enough" outside the issuer contract. The trusted registry, metadata discovery, and post-verification `iss` claim must be consistent. Any issuer URI change is a trust policy change requiring review.

### 12.5. Minimize information leakage from selector errors

Never return the list of registered issuers or internal JWKS endpoints to clients. Bearer authentication error responses should be informative enough without exposing private configuration. In metrics, only use issuer aliases **matched in the trusted registry**; never use raw unverified issuers, tokens, or subjects as labels.

## 13. Threat model: attacks exploiting unverified claims

### 13.1. Forged issuer and attacker-controlled JWKS

An attacker can:

1. Stand up a fake Authorization Server at `https://evil.example.test`.
2. Publish a JWKS containing their own public key.
3. Sign a JWT with `iss=https://evil.example.test`, `scope=orders.admin`.
4. Send this Bearer JWT to the Resource Server.

If the API automatically runs discovery for any token-declared issuer, it risks trusting the attacker's key. Safe policy:

~~~text
unverified iss = https://evil.example.test
    |
    v
trusted registry contains issuer?
    |
    +-- NO --> reject, make no discovery/JWKS call
~~~

An arbitrary issuer hint used as an HTTP URL also introduces **Server-Side Request Forgery (SSRF)** against metadata services, loopback, private networks, or internal endpoints. Outbound JWKS/discovery requests must only target approved sources with bounded connections, timeouts, and TLS trust.

### 13.2. Cross-issuer key confusion

Two issuers can publish a JWK with the same `kid`, such as `kid=key-1`. `kid` is not a global namespace and does not prove which issuer a token belongs to.

Trust must be isolated:

~~~text
Issuer North:
    JWKS North
    allowed algorithms North
    expected iss North

Issuer South:
    JWKS South
    allowed algorithms South
    expected iss South
~~~

Never use a shared key cache unpartitioned by issuer that picks arbitrary public keys just because `kid` matches. Nor should you assume a valid JWS means the right issuer when multiple tenants reuse the same signing key; always check the verified `iss`.

### 13.3. Role/scope escalation via modified payload

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "attacker",
  "scope": "orders.read orders.admin"
}
~~~

If code creates `SCOPE_orders.admin` from raw JWT claims before verification, an attacker needs no private signing key to escalate privileges. **Only map authorities from the verified JWT** returned by the decoder, and only within the permitted issuer/profile trust scope.

### 13.4. Tenant spoofing

An attacker can put:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "tenant_id": "south",
  "scope": "orders.read"
}
~~~

An unverified `tenant_id=south` is just attacker-supplied text. Even if the token was actually signed by North with a South claim, it **does not automatically grant South access**: check whether North is authorized to assert South tenant membership under your federation policy/issuer registry. Many systems only allow North's issuer to grant North access.

### 13.5. Token confusion: ID token in place of access token

An OIDC ID token can have a valid issuer and JWS signature while its `aud` is the client application, not the Resource Server. If the API only verifies issuer/key while ignoring audience and token profile, ID tokens can be misused.

~~~text
Required:
    signature valid
AND issuer trusted
AND aud contains expected Resource Server
AND token type/profile fits access token contract
AND time claims valid
AND operation has required scope/permission
~~~

If the token profile follows RFC 9068, you may need explicit rules for `typ=at+jwt` and required claims. Never assume every JWT from the same issuer is an OAuth access token meant for your API.

### 13.6. Algorithm confusion

Never let a JWT pick an arbitrary JWS `alg` from its unverified header:

~~~text
Trusted North decoder: RS256 only

Incoming alg=none        → reject
Incoming alg=HS256       → reject
Incoming RS256 wrong sig → reject
Incoming unsupported alg → reject
~~~

An unverified JOSE header may only assist in locating a candidate key within **the server-approved keys and algorithms**. Never fetch `jku`/`x5u` URLs from the header and trust the returned public key.

### 13.7. Falling back from a strong verifier to a weak verifier

~~~java
// ANTI-PATTERN: an unverified JWT falls back to a plain parser.
try {
    return signedJwtDecoder.decode(token);
} catch (Exception failure) {
    return insecureClaimsReader.createAuthentication(token);
}
~~~

Never "try every verifier until one accepts." Any fallback path must be an intentionally designed trusted mechanism that still enforces signature, audience, and issuer validation; an authentication failure must never turn into success.

### 13.8. DDoS via random issuers

If every new `iss` creates a decoder/JWKS HTTP client cached forever:

~~~text
iss=random-1...
iss=random-2...
...
iss=random-100000...
~~~

an attacker can exhaust memory, connection pools, and metadata caches. A bounded issuer allowlist rejects unknown issuers fast. For dynamic registries, enforce active issuer limits, TTL/cache eviction, concurrency caps, onboarding authorization, and rate limiting.

### 13.9. Host/header spoofing

If the tenant is derived from `Host` or `X-Forwarded-Host`, ensure a trusted reverse proxy/gateway normalizes those headers. A client can trivially send:

~~~http
X-Forwarded-Host: south.api.example.test
~~~

That value does not prove the caller has South access. Only use trusted routing context to select the tenant, then validate the verified JWT and domain permissions.

### 13.10. Replaying a valid-issuer JWT against the wrong resource

A North JWT with `aud=billing-api` and `scope=orders.read` must not be accepted by Orders API just because it has issuer North. Audience binding stops an access token meant for one API from being replayed against another. This is an issue **an issuer allowlist alone cannot solve**.

### 13.11. Data leakage across records despite a valid JWT

A verified JWT for tenant North with `SCOPE_orders.read` still does not grant access to read an order belonging to South. Enforce tenant/owner filters in the domain layer and never let client-supplied order IDs bypass isolation.

### 13.12. Logging raw JWTs/claims

Never log full JWTs, Bearer headers, unverified claims, JWK secrets, or full identities in logs/traces. Even unverified claims can contain PII or attacker-crafted payloads intended to pollute logs. Log a request ID, trusted registry issuer alias, and normalized error category instead.

## 14. Select by `iss`, tenant path, or another strategy?

| Selection method | Pre-verify signal | When appropriate? | Post-verify evidence |
|---|---|---|---|
| Issuer resolver | Unverified `iss` | One endpoint receiving tokens from multiple issuers | Signature + `iss` + audience/token type + tenant policy |
| Path-based resolver | `/tenants/{id}/...` | API separating URLs per tenant | Signature from mapped issuer, tenant permission, and resource ownership |
| Trusted host routing | Gateway-approved host | Service with per-tenant subdomains | Verified JWT matching tenant/host context |
| One shared decoder | No claim routing needed | Multiple tenants sharing issuer/keys | Signed tenant claim and membership/authorization |
| Introspection resolver | Trusted endpoint/tenant context | Opaque tokens or profiles requiring introspection | Active response and metadata from trusted endpoint |

In a multi-issuer system, do not substitute `kid` for `iss`, because `kid` only has meaning inside a JWKS trust scope. When picking a strategy by tenant path, remember **the path is a client request**, not proof the user belongs to that tenant.

### 14.1. Route-based selection still requires verification

~~~text
GET /tenants/south/orders
    → trusted route registry selects South verifier
    → Bearer JWT signed by North
    → South verifier checks issuer/key
    → reject
~~~

The presence of "south" in the URL does not grant the caller South membership. It only selects the **appropriate verifier**.

### 14.2. Opaque tokens with no readable `iss`

A random opaque access token typically provides no issuer claim parseable before verification. Therefore, select the introspection endpoint from a trusted tenant route, host, client context, or trusted authorization gateway/service, then invoke `OpaqueTokenIntrospector`.

Never probe every issuer's introspection endpoint and accept whichever returns `active=true` without an explicit contract; doing so risks token confusion, SSRF, leaking Bearer credentials, and amplification load. Opaque token verification must still follow a **known trust policy**, not token-format guesswork.

## 15. Testing the routing hint and authentication boundary

A multi-tenant test suite must prove **two separate things**:

1. The unverified `iss` claim only selects a **verifier from the registry**; unknown issuers are rejected before any discovery/JWKS request.
2. The selected verifier **genuinely checks signature, issuer, audience, and timestamps**; verified tokens still pass through tenant and domain authorization.

If tests only use `mockJwt()`, `Jwt.withTokenValue(...)`, or a mocked `JwtDecoder` returning a fixed principal, **they do not prove JWT signatures are verified**. Authentication tests must use real JWTs signed with test keys and a real decoder flowing through the HTTP Bearer filter chain or direct decoder unit tests.

### 15.1. Scenario matrix with North and South

Assume each issuer has its own RSA key pair and each decoder requires `aud=orders-api`.

| Case | Token / request | Resolver selects | Expected result |
|---|---|---|---|
| T01 | Validly signed North JWT, `iss=NORTH`, GET North tenant | North manager | 200 if authorized |
| T02 | Validly signed South JWT, `iss=SOUTH`, GET South tenant | South manager | 200 if authorized |
| T03 | Forged JWT `iss=NORTH` signed with wrong key | North manager | **401** due to signature |
| T04 | North signer signs JWT claiming `iss=SOUTH` | South manager | **401** due to failing South trust |
| T05 | Self-declared JWT `iss=https://evil.example.test` | No manager | **401**; no call to attacker key URL |
| T06 | JWT missing `iss` | No manager | **401** |
| T07 | Malformed JWT | No manager | **401** |
| T08 | Validly signed North JWT, `aud=billing-api` | North manager | **401** due to audience |
| T09 | North JWT valid key, expired `exp` | North manager | **401** due to expiration |
| T10 | Valid North JWT with only `scope=orders.create` | North manager | **403** missing read scope |
| T11 | Valid North JWT, GET South tenant | North manager | **403/404** per tenant policy |
| T12 | JWT matching tenant path, accessing another tenant's order | Manager for issuer | Denied in domain layer |
| T13 | JWT with `tenant_id` altered after signing | Manager by `iss` | **401** due to signature mismatch |
| T14 | Issuer disabled in trusted registry | No manager | **401** even with valid prior signed token |
| T15 | Request without Bearer token | Unauthenticated | **401** on protected API |

These are typical HTTP status codes and may vary with entry points, security chains, and anti-enumeration policies. More important than the status code is verifying that **no principal or authority is created from unverified claims** and **no token from another issuer bypasses trust policy**.

### 15.2. Each negative case should vary only one condition

A JWT that fails signature, issuer, audience, and expiration all at once will be rejected at the very first check; HTTP 401 **does not prove every validator ran**. To test audience specifically, sign the JWT with the **right private key**, valid issuer/time/scope, and vary only `aud`.

To test the issuer validator, use a JWT whose signature the test decoder can verify, then supply an `iss` not matching the configured issuer. When North and South use different keys, testing "North signer with `iss=SOUTH`" mainly tests **key/manager isolation**; it does not prove South's issuer validator works because the signature fails first.

### 15.3. Verifying zero outbound calls to unknown issuers

Suppose the registry only contains:

~~~text
NORTH → trusted JWKS North
SOUTH → trusted JWKS South
~~~

A JWT with `iss=https://evil.example.test` must be rejected **before** any network request goes to that URL. In integration tests, use an HTTP mock server or network interceptor to assert **zero discovery/JWKS requests reach non-allowlisted domains**. Asserting 401 alone does not prove no SSRF attempt happened before failing.

### 15.4. Post-authentication tenant binding

~~~text
JWT A:
    verified issuer = North
    verified tenant_id = north
    verified scope = orders.read
Request:
    GET /tenants/south/orders
Expected:
    deny South

JWT B:
    verified issuer = South
    verified tenant_id = south
    verified scope = orders.read
Request:
    GET /tenants/south/orders
Expected:
    allow when domain permissions suffice
~~~

If the strategy picks the decoder by `iss`, JWT A may **pass authentication** and then **be denied by tenant authorization**. If the API picks the decoder by South's path, JWT A will be **rejected at authentication** by South's verifier. Both designs must block cross-tenant access.

### 15.5. Testing a shared issuer across multiple tenants

With a shared issuer:

~~~text
Issuer = https://login.example.test/company
Signed JWT tenant_id=north
Request tenant_id=south
~~~

This is not a decoder failure: signature, issuer, and audience may all be valid. It must be rejected **at tenant authorization**. Also test users with multi-tenant memberships per policy, tenant-scoped permissions, and object ownership.

## 16. JUnit test: forged issuer hint fails signature verification

The next example directly tests the **issuer selector → JWT authentication manager** boundary. It uses `TrustedIssuerChooser` from section 12, managers built with real `NimbusJwtDecoder`, and separate RSA key pairs for two issuers. This is a **unit/integration test at the authentication provider**, not an HTTP filter-chain test; HTTP integration requires `MockMvc`/`WebTestClient` at the application layer.

### 16.1. Test fixture signing JWTs with test keys

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class UnverifiedIssuerHintTest {

    static final String NORTH =
        "https://login.example.test/realms/north";
    static final String SOUTH =
        "https://login.example.test/realms/south";

    KeyPair northKeys;
    KeyPair southKeys;
    TrustedIssuerChooser chooser;

    @BeforeEach
    void setUp() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        northKeys = generator.generateKeyPair();
        southKeys = generator.generateKeyPair();

        Map<String, AuthenticationManager> managers = Map.of(
            NORTH, IssuerManagers.jwtManagerWithPublicKeyForTest(
                (RSAPublicKey) northKeys.getPublic(), NORTH, "orders-api"),
            SOUTH, IssuerManagers.jwtManagerWithPublicKeyForTest(
                (RSAPublicKey) southKeys.getPublic(), SOUTH, "orders-api")
        );
        chooser = new TrustedIssuerChooser(managers);
    }

    private String signedToken(
            KeyPair keyPair,
            String issuer,
            String tenant,
            String audience,
            String scope) throws Exception {

        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("test-user")
            .audience(List.of(audience))
            .claim("tenant_id", tenant)
            .claim("scope", scope)
            .issueTime(Date.from(now.minusSeconds(30)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID("test-key")
                .build(),
            claims
        );

        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) keyPair.getPrivate()));
        return jwt.serialize();
    }

    private Authentication authenticate(String token) {
        AuthenticationManager selected = chooser.choose(token);
        return selected.authenticate(
            new BearerTokenAuthenticationToken(token));
    }

    @Test
    void validNorthJwtIsAuthenticated() throws Exception {
        String token = signedToken(
            northKeys, NORTH, "north", "orders-api", "orders.read");

        Authentication result = authenticate(token);
        assertThat(result).isInstanceOf(JwtAuthenticationToken.class);
        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getAuthorities())
            .extracting("authority")
            .contains("SCOPE_orders.read");
    }

    @Test
    void forgedNorthHintWithUntrustedSignerIsRejected()
            throws Exception {
        // Token claims iss=NORTH but was signed using SOUTH private key.
        String token = signedToken(
            southKeys, NORTH, "north", "orders-api", "orders.read");

        assertThatThrownBy(() -> authenticate(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }

    @Test
    void northSignerCannotImpersonateSouthIssuer()
            throws Exception {
        String token = signedToken(
            northKeys, SOUTH, "south", "orders-api", "orders.read");

        assertThatThrownBy(() -> authenticate(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }

    @Test
    void unknownIssuerHintDoesNotSelectManager()
            throws Exception {
        String token = signedToken(
            northKeys,
            "https://evil.example.test/issuer",
            "north",
            "orders-api",
            "orders.read");

        assertThatThrownBy(() -> chooser.choose(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }

    @Test
    void wrongAudienceIsRejectedEvenWithTrustedSigner()
            throws Exception {
        String token = signedToken(
            northKeys, NORTH, "north", "billing-api", "orders.read");

        assertThatThrownBy(() -> authenticate(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }
}
~~~

To supply the `jwtManagerWithPublicKeyForTest(...)` helper method used above, add this **test-only** helper:

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

// Can be placed in the IssuerManagers helper class from section 6.
static AuthenticationManager jwtManagerWithPublicKeyForTest(
        RSAPublicKey publicKey,
        String expectedIssuer,
        String expectedAudience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withPublicKey(publicKey)
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT audience not accepted",
                    null
                )
            );

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(expectedIssuer),
            audienceValidator
        )
    );

    return new JwtAuthenticationProvider(decoder)::authenticate;
}
~~~

This is an **additional method for the helper class**; if placed in its own Java file, wrap it in an appropriate class. In production, trusted keys may come from HTTPS JWKS; tests use static public keys to isolate verification from networking.

### 16.2. What this test actually proves

When `chooser.choose(token)` sees `iss=NORTH`, it can return North's manager **before verifying the signature**. However, `forgedNorthHintWithUntrustedSignerIsRejected` proves the next step remains mandatory:

~~~text
Token signed by South private key
JWT payload iss=NORTH
      |
      v
Chooser selects North manager
      |
      v
North NimbusJwtDecoder verifies using North public key
      |
      v
Signature invalid → Authentication fails
~~~

This is precisely **the difference between choosing a strategy and granting permissions**. Likewise, a token signed with North's real key but carrying the wrong audience must still be rejected.

### 16.3. What these tests do not yet prove

These tests do not invoke:

- HTTP `BearerTokenAuthenticationFilter` or `AuthorizationFilter`.
- The `/tenants/{tenantId}/orders` controller.
- Object ownership queries in the database.
- JWKS HTTP discovery/rotation.
- Reverse proxy host/path routing.

Therefore, add corresponding **HTTP integration tests** and domain authorization tests. Never conclude from a selector unit test alone that the entire multi-tenant API is secure.

### 16.4. Which tests to add for the HTTP chain?

`MockMvc` example:

~~~java
// JWT REALLY signed with a test RSA private key.
mockMvc.perform(
        get("/tenants/north/orders/42")
            .header("Authorization", "Bearer " + validNorthJwt))
    .andExpect(status().isOk());

mockMvc.perform(
        get("/tenants/north/orders/42")
            .header("Authorization", "Bearer " + forgedNorthJwt))
    .andExpect(status().isUnauthorized());

mockMvc.perform(
        get("/tenants/south/orders/42")
            .header("Authorization", "Bearer " + validNorthJwt))
    .andExpect(status().isForbidden());
~~~

This is a **test outline**, assuming a real controller, a security chain with the real resolver, test data/service containing an allowed record for the first case, and the tenant guard from section 9. The South case may return 404 if an anti-enumeration policy hides resource existence. Never attach Spring Security Test's `jwt()` request post-processor when testing real RSA signature verification; that post-processor mocks authentication and can skip the decoder.

### 16.5. WebFlux tests must use a real `WebTestClient`

In a reactive application, a similar approach:

~~~java
webTestClient.get()
    .uri("/tenants/north/orders/42")
    .headers(headers -> headers.setBearerAuth(validNorthJwt))
    .exchange()
    .expectStatus().isOk();

webTestClient.get()
    .uri("/tenants/north/orders/42")
    .headers(headers -> headers.setBearerAuth(forgedNorthJwt))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Ensure the WebFlux test context uses `JwtIssuerReactiveAuthenticationManagerResolver` and a **real `NimbusReactiveJwtDecoder`**, not `mockJwt()`. You can test the decoder's `Mono<Jwt>` separately with `StepVerifier` to isolate cryptographic validation from HTTP wiring.

## 17. Operating a trusted issuer registry

The trusted issuer registry is the **trust boundary** between an unverified claim and an authorized verifier. Whether stored in a configuration file or a database, it must be governed as **security configuration**, never as a self-declared user option.

### 17.1. Issuer onboarding workflow

~~~mermaid
flowchart TD
    A["Tenant requests onboarding"] --> B["Verify tenant admin privileges"]
    B --> C["Approve issuer URL and ownership"]
    C --> D["Validate metadata, TLS, JWKS, allowed algorithms"]
    D --> E["Define audience, scopes, token profile, tenant mapping"]
    E --> F["Test valid and invalid tokens"]
    F --> G["Transition issuer to ACTIVE"]
    G --> H["Monitor keys, metadata, errors, and offboarding"]
~~~

A user simply submitting `https://my-new-idp.example.test` is not enough for the API to add that issuer to the allowlist. Running an IdP and signing JWTs with their own key **is not proof the organization has agreed to trust that IdP**.

### 17.2. Registry records must express policy

~~~yaml
tenantId: north
status: ACTIVE
issuer: https://login.example.test/realms/north
jwksUri: https://login.example.test/realms/north/jwks
allowedJwsAlgorithms:
  - RS256
requiredAudiences:
  - orders-api
acceptedTokenProfile: access-token
authoritiesClaim: scope
authoritiesPrefix: SCOPE_
approval: security-reviewed
~~~

This is an **illustrative application schema**, not built-in Spring Boot properties. Every record must be change-controlled and activated only upon policy approval and verification.

### 17.3. Possible lifecycle states

| State | Meaning | Selectable in production? |
|---|---|---|
| `PENDING` | Not yet approved | No |
| `TESTING` | Allowed only in controlled test environments | No |
| `ACTIVE` | Verified and permitted issuer | Yes |
| `SUSPENDED` | Temporarily untrusted due to incident or policy | No |
| `RETIRED` | Offboarded / end of lifecycle | No |

Never automatically promote `PENDING` to `ACTIVE` upon receiving a JWT with a valid signature from that issuer. A signature only proves the token was signed by a key, not that the server intentionally trusts the issuer.

### 17.4. Removing an issuer while tokens remain unexpired

If a tenant is suspended, JWTs with unexpired `exp` may still exist. To stop accepting that issuer, the Resource Server must update the registry and manager/decoder cache per freshness policy:

- Update the registry version or snapshot atomically.
- Trigger invalidation/refresh across every instance.
- Never keep managers trusted indefinitely after the registry disables an issuer.
- Track synchronization metrics and detect instance lag.
- Test a validly signed JWT whose issuer has moved to `SUSPENDED`.

**Changing the trust registry** differs from **key rotation**: an issuer can stay trusted while public keys rotate, or be suspended even while its public key remains valid.

### 17.5. Lazy discovery has operational trade-offs

A resolver can instantiate a decoder the first time it sees a JWT with a trusted `iss`:

~~~text
first JWT for North
   → issuer North is in allowlist
   → create/retrieve North manager
   → discovery/JWKS fetch if needed
   → JWS + claims verification
~~~

This avoids requiring every issuer to be available at startup, at the cost of higher first-request latency. Configure timeouts, concurrency limits, bounded caches, monitor first-request latency, and prevent creating duplicate managers for the same issuer under concurrent traffic.

If discovery/JWKS experiences a temporary outage and no trusted cached key exists, **the token cannot be verified**; never treat the issuer's presence in the registry as an excuse to accept it anyway.

### 17.6. JWKS/discovery URLs must be governed by trust policy

A trusted issuer URI is not a license to make HTTP requests to any URL self-declared by an unverified JWT. Metadata retrieval requires TLS, trusted egress, redirect policies, and request bounds. For external partner issuers, consider allowlisting/pinning JWKS URIs per security contract.

## 18. Caching and synchronizing issuer managers without weakening verification

A multi-tenant Resource Server may cache:

- Trusted issuer registry snapshots.
- Per-issuer decoders/authentication managers.
- JWK Sets/public keys.
- Issuer metadata/discovery responses.
- Certain audience, token type, and scope mapping policies.

Distinguish caching **trusted configuration** from caching **unverified data**.

### 18.1. Cache only after the issuer passes the allowlist

~~~text
RIGHT:
    unverified issuer hint
       → trusted registry lookup
       → issuer ACTIVE?
       → create/reuse approved decoder

WRONG:
    every unique unverified iss
       → create decoder / HTTP client
       → cache forever
~~~

Caching arbitrary `iss` values lets an attacker create hundreds of thousands of entries, exhausting memory, connection pools, and metadata caches. Only **approved and ACTIVE** issuers may instantiate managers, with appropriate cardinality and concurrency bounds.

### 18.2. Key caching vs. authentication caching

~~~text
JWKS/public-key cache:
    still verifies the JWS signature of each incoming JWT

Authentication cache:
    may reuse the principal of an already-verified token
    requires its own lifecycle, expiry, revocation, and sender-binding policy
~~~

A decoder using a trusted cached public key **does not skip signature verification**. In contrast, caching `Authentication` by `sub` or an unverified issuer hint can introduce severe authorization flaws. If you design authentication caching, key it by the token/verified identity and enforce expiry, audience, revocation, and tenant context.

### 18.3. Issuer suspended while a snapshot is stale

A stale registry snapshot can cause the API to keep trusting a disabled issuer. Enforce freshness bounds on the trust registry: TTL-based polling, push invalidation, version checks, or another appropriate sync mechanism.

If policy requires near-real-time issuer revocation, define what happens when an instance cannot fetch the updated registry. Never use stale config indefinitely when trust may already have been revoked.

### 18.4. Fault isolation per issuer

If South's JWKS returns 503 while North is healthy:

~~~text
North → trusted cached key available → verify North JWTs normally
South → no trusted key available      → fail closed for South
~~~

A South outage should not necessarily halt authentication for North. Isolate pools, timeouts, and circuit breakers by trusted issuer alias/endpoint. Never use unverified issuer URLs from JWTs as unbounded metric labels or SSRF vectors during troubleshooting.

### 18.5. Registry administration privileges

Actions such as adding an issuer, changing `jwksUri`, allowing HS256, removing an audience validator, or mapping admin scopes expand the set of tokens trusted by the API. Require proper authorization, auditing, and approval; never allow an unprivileged tenant admin to modify shared trust policies affecting other tenants.

## 19. Step-by-step attack scenarios

Suppose an attacker is a legitimate South user trying to read North's Orders. The attacker holds a validly signed JWT:

~~~json
{
  "iss": "https://login.example.test/realms/south",
  "sub": "user-777",
  "tenant_id": "south",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

### 19.1. Tampering issuer/tenant claims while keeping the signature

The attacker modifies the payload:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "user-777",
  "tenant_id": "north",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

while keeping the old JWS signature.

~~~text
Unverified iss=NORTH
    → resolver selects North manager
    → North decoder verifies JWS
    → signature mismatch
    → authentication rejected
~~~

Having the resolver select North **does not grant North permissions**; it merely chose the right verifier according to the hint.

### 19.2. Keeping the valid South JWT, changing the URL to North

~~~http
GET /tenants/north/orders/42
Authorization: Bearer <VALID_SOUTH_JWT>
~~~

Under an `iss`-based decoder selector:

~~~text
Unverified iss=SOUTH
    → resolver selects South manager
    → South decoder verifies JWS/claims successfully
    → identity = (South issuer, user-777)
    → requested tenant = north
    → tenant authorization denies
~~~

The JWT **may succeed at authentication**, yet the caller still lacks permission for tenant North. If the API picks the decoder from the tenant path, the request is rejected at authentication by North's verifier. Both designs must block reading North's data.

### 19.3. Standing up a custom issuer and key pair

~~~text
Attacker owns evil.example.test
JWT iss=https://evil.example.test
JWT signed using attacker's own private key
    → issuer not in trusted registry
    → reject before discovery/JWKS
~~~

Never "conveniently support multi-issuer" by building decoders from arbitrary Bearer JWT URLs.

### 19.4. Holding a real North token while the order belongs to South

Even if an attacker obtains a genuine North JWT with `SCOPE_orders.read`, `orderId=42` belonging to South must still be blocked in the domain layer. Checking issuer/tenant at authentication never replaces tenant isolation queries and object ownership checks.

**Result of sound design:** tokens provide only a *verifier selection hint* before verification; **access is decided exclusively from verified identity, verified permissions, and tenant/domain policies**.

## 20. Common implementation pitfalls

### 20.1. "Reading `iss` from the JWT and building a decoder means it is verified"

False. `JWTParser.parse(...)` only reads client-supplied content. Picking a decoder is a **preparatory step**; the decoder still has to verify signature, issuer, audience, token type, expiry, and required claims. A JWT claiming `iss=NORTH` can be **routed to North's decoder** and still fail when the signature is invalid.

### 20.2. "If the issuer URL looks valid, just run discovery"

False. Any attacker can run an HTTPS issuer with a JWKS they control. Only issuers **already in the trusted registry** may participate in authentication. A valid-looking URL is never sufficient, and fetching arbitrary URLs increases SSRF risk.

### 20.3. "If the signature passes, checking issuer isn't needed"

False. Some systems have key reuse, misconfigured key caches, or multiple token profiles sharing keys. Always validate the verified `iss` via a validator on the corresponding decoder. Key selection never replaces issuer validation.

### 20.4. "If the issuer is right, checking audience isn't needed"

False. The same issuer can mint tokens for Billing, Orders, and Admin APIs. A JWT meant for Billing must not be accepted by Orders API just because it shares the same signer. Validate `aud`/resource and token profile per contract.

### 20.5. "A self-declared `tenant_id` claim grants tenant access"

False. Before verification, the claim may be attacker-crafted. After verification, it must still match the issuer-to-tenant mapping, membership/entitlement policy, and requested tenant. An issuer not authorized for South cannot open tenant South just by signing a `south` claim.

### 20.6. "Matching `sub` across two issuers means the same user"

False. `sub` is normally scoped to the issuer's identity namespace. Use **(verified issuer, verified subject)** or a trusted account-linking mechanism; never merge users or tenant memberships by matching `sub`.

### 20.7. "If a JWT fails to parse, fall back to a lighter validator"

False. Falling back without signature, audience, or token-type checks creates downgrade risks. Different access token formats must be handled strictly according to a defined **trusted routing contract**. Never try strategies until a lenient one accepts.

### 20.8. "`kid` alone identifies the issuer"

False. `kid` is not a global identifier and can collide across issuers. It only hints which key to pick inside the **selected issuer's trusted JWK Set**. Never load public keys from untrusted `jku` or `x5u` headers.

### 20.9. "Adding a new issuer when the first token arrives is convenient"

False. That is **trust-on-first-use from client-controlled input**, which is inappropriate when a Resource Server must trust only approved issuers. Onboarding requires verifying ownership, metadata, keys, audience, roles, resource policies, and lifecycle.

### 20.10. "Setting `permitAll()` and checking claims manually in the controller"

Wrong when used to replace Bearer authentication for a protected API. A controller reading an unverified raw JWT and trusting `scope` to return data bypasses the entire Spring Security pipeline. Let authentication filters and decoders verify the token before business logic runs.

### 20.11. "A mocked `Jwt` object is enough to prove security"

False. `mockJwt()` and `Jwt.withTokenValue(...)` are great for authorization tests, yet prove nothing about signature, issuer, or audience verification. Multi-tenant authentication tests require **real JWTs signed with test keys** and real decoders.

### 20.12. "An admin-scoped token is admin for all tenants"

Not automatically true. A privilege may apply only within a specific issuer or tenant. Map authorities with tenant context, never assuming global roles unless the token profile explicitly guarantees cross-tenant rights.

### 20.13. "Updating the registry database is enough; caches don't matter"

False. Instances retaining cached managers or issuer snapshots past suspension time can keep accepting tokens from a revoked issuer. Enforce cache invalidation, refresh, and freshness policies, and test registry state transitions.

### 20.14. "Every authentication exception means a bad token"

Not necessarily. Bad signatures, wrong audiences, or expired tokens are token errors, whereas JWKS discovery timeouts/503s, TLS errors, or bad issuer configs are operational failures. Either way, the Resource Server **must not create an authenticated principal without sufficient proof**, while telemetry and HTTP statuses should categorize failures accurately.

### 20.15. "Tenant North in the URL proves the caller belongs to North"

False. The URL/host is the **requested context**, not membership. Compare that context against the verified token and domain policy.

## 21. Self-check questions

### Question 1. Can you read `iss` from an unverified JWT?

**Yes, if used solely to select a verifier from a trusted allowlist.** At that point `iss` is only a routing hint. Never grant a principal, authorities, or access from it before signature, issuer, audience, and claims are verified.

### Question 2. What if `iss` matches a trusted issuer, yet the JWT has an invalid signature?

The resolver can pick the manager for that issuer, and the decoder must **reject authentication**. An issuer being on the allowlist does not prove that a specific token was signed by it.

### Question 3. Can you automatically create a `JwtDecoder` for any `iss` found in a token?

**No** for a Resource Server with a strict trust boundary. Issuers must be pre-approved in the registry. Auto-discovering URLs from tokens enables trust injection, SSRF, and DoS.

### Question 4. Once a JWT is verified, can you immediately use `scope` and `tenant_id` to grant access to all resources?

**No.** Verified claims are trustworthy within the issuer/profile contract, yet you must still map authorities in context and verify audience, tenant membership, and per-resource permissions. A valid token does not mean "access every record."

### Question 5. What happens when a valid North JWT calls `/tenants/south/orders`?

If the verifier is chosen by `iss`, North authentication may succeed and then **tenant authorization rejects it**. If the verifier is chosen by the South path, authentication rejects it because the token fails South's trust checks. Either way, South data must never be returned unless the principal has access.

### Question 6. If all tenants share one issuer, do you need a per-tenant issuer resolver?

Usually **not** if they share the same decoder, keys, and profile. Verify the JWT with the shared issuer, then enforce the signed `tenant_id` and membership/permissions post-authentication. Add tenant-specific strategies only when real trust/policy differences exist.

### Question 7. Why can't an unverified `kid` serve as an issuer key?

`kid` is only a key-selection label within a JWK Set and can collide or be forged by an attacker. Select the **issuer's trusted JWKS** first, then use `kid` to look up the key inside that trusted set.

### Question 8. Are two JWTs from two issuers with the same `sub=123` the same user?

You cannot assume so. Identity is normally distinguished by **(issuer, subject)**. Linking accounts across issuers must be performed by a trusted system.

### Question 9. When an allowlisted issuer's JWKS has an outage, should tokens pass through?

Without a trusted key or validator result, **authentication must not succeed**. You may rely on still-valid trusted cached keys per policy; never fall back to reading raw claims and granting access.

### Question 10. Once `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` runs, does the API automatically check tenant ownership and audience?

Never assume so. The issuer resolver selects the manager; issuer, audience, and token profile validation must be configured on the decoder, and domain authorization must enforce tenant/resource ownership. Test each condition explicitly.

### Question 11. Should unverified `iss` values be used as metric labels?

Do not use raw client values because an attacker can generate unbounded labels, causing cardinality explosion and polluting observability with untrusted data. Use a trusted registry issuer alias when lookup succeeds, or an `unknown` label for unrecognized issuers.

### Question 12. Why shouldn't you test exclusively with `mockJwt()`?

`mockJwt()` skips cryptographic verification to test authorization. It does not prove the resolver picks the right decoder, rejects bad signatures, or runs audience/issuer validators. Use real signed test JWTs and real decoders for authentication tests.

## 22. Checklist for a multi-tenant Resource Server

### 22.1. Strategy selection and trusted issuer registry

- [ ] A server-side managed list of trusted issuers exists.
- [ ] Only issuers in ACTIVE state may select a manager.
- [ ] Unverified `iss` is used **solely as a routing hint**, never to create `Authentication`.
- [ ] No discovery/JWKS requests are made to unapproved issuer URLs.
- [ ] Issuer lookup uses exact matching semantics without arbitrary URI normalization.
- [ ] Unknown, malformed, or missing issuers are rejected.
- [ ] JWT size and parsing cost are bounded at the pre-auth boundary.
- [ ] No fallback to a weaker verifier on parse/verify failure.
- [ ] Unverified `scope`, `roles`, `sub`, or `tenant_id` never grant permissions.
- [ ] Path/host selection acts only as a context selector, never as tenant authorization.

### 22.2. Actual JWT verification

- [ ] Each issuer manager has properly scoped trusted keys/JWKS.
- [ ] Allowed JWS algorithms are restricted per issuer profile.
- [ ] JWT signatures are verified by a trusted library/decoder.
- [ ] Verified `iss` matches the selected issuer.
- [ ] `aud` is validated for this Resource Server.
- [ ] `exp`, `nbf`, timestamps, and required claims are validated.
- [ ] Token type/profile is enforced; OIDC ID tokens are not accepted as access tokens.
- [ ] `setJwtValidator(...)` does not unintentionally drop default validators.
- [ ] `kid` only selects keys inside a trusted JWKS, never determining issuer globally.
- [ ] JWKS/discovery errors never bypass verification.

### 22.3. Tenant and data authorization

- [ ] Principal and authorities are created **after** JWT verification.
- [ ] Identity includes the issuer namespace, e.g., `(verified issuer, verified subject)`.
- [ ] Issuer-to-tenant mapping is governed reliably.
- [ ] Signed `tenant_id` is compared against the requested tenant per contract.
- [ ] If a principal has multiple tenants, membership/permissions are checked per tenant.
- [ ] HTTP/method authorization uses scoped/prefixed authorities from trusted sources.
- [ ] Order/resource tenant and owner are verified in the service/DB.
- [ ] Admin roles never apply across all tenants unless allowed by profile.
- [ ] Responses never leak other tenants' data or raw tokens/sensitive claims.

### 22.4. Testing

- [ ] Positive control: JWT with valid issuer/key/audience/time/scope succeeds.
- [ ] JWT signed with wrong key while matching a trusted `iss` → rejected.
- [ ] JWT signed with valid key but wrong audience/issuer/expiry → rejected.
- [ ] Unregistered issuer → rejected with zero outbound calls to unknown URLs.
- [ ] Valid North token requesting South tenant → denied.
- [ ] Valid JWT missing required scope → authorization denied.
- [ ] Object-level cross-tenant access test → denied.
- [ ] Real HTTP tests traverse the security chain/decoder, not just `mockJwt()`.
- [ ] Resolver/manager selection tests exist when custom routing is used.
- [ ] Suspended issuer and registry cache refresh tests exist for dynamic registries.

### 22.5. Operations

- [ ] Issuer onboarding/offboarding has approval and auditing.
- [ ] Registry and manager caches have TTL, freshness, and invalidation policies.
- [ ] JWKS/discovery HTTP clients enforce TLS, timeouts, and egress controls.
- [ ] Unbounded managers are never created from attacker-supplied issuers.
- [ ] Metrics use bounded-cardinality issuer aliases.
- [ ] Raw Bearer tokens, credentials, and unverified claims are never logged.
- [ ] An issuer/JWKS outage never turns an unknown JWT into an authenticated token.
- [ ] Key rotation, token TTL overlap, and issuer suspension procedures are in place.

## 23. Summary diagram: no shortcut from unverified claims to permissions

~~~mermaid
flowchart LR
    U["Raw Bearer JWT"] --> H["Parse unverified iss"]
    H --> L{"Trusted registry allowlist?"}
    L -->|No| X["Reject"]
    L -->|Yes| S["Select registered decoder"]
    S --> V{"Verify signature, alg, iss, aud, time, profile?"}
    V -->|No| X
    V -->|Yes| J["Verified JWT"]
    J --> A["Create Authentication + authorities"]
    A --> T{"Allowed in requested tenant?"}
    T -->|No| D["Deny"]
    T -->|Yes| O{"Scope and object ownership valid?"}
    O -->|No| D
    O -->|Yes| R["Access protected resource"]
~~~

In the flow above, **an unverified issuer has only one legitimate use: helping select a verifier from the trusted list**. Every step affecting identity, tenant, scope, role, resource owner, and returned data happens **after** the decoder's verification result.

### A rule to remember

~~~text
Before JWT verification:
    issuer/tenant/header = hint, not authority

After JWT verification:
    claims = evidence within a trusted issuer/token profile

After authorization:
    access = decision for this tenant, action and resource
~~~

In a multi-tenant system, picking the right decoder is a necessary condition, **never an authorization decision**. A secure policy combines a **trusted issuer allowlist**, **JWT signature and claims validation**, **tenant binding**, **scope-based authorization**, and **object-level access control**.

## References

- [Spring Security — Multitenancy, Servlet Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Multitenancy, Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security — JwtIssuerReactiveAuthenticationManagerResolver API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
