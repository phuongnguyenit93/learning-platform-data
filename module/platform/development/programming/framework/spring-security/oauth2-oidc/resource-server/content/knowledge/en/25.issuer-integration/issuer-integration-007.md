# Introspection, JWKS, and Capabilities to Verify Per Environment

When integrating a **Spring Security OAuth 2.0/OIDC Resource Server** with an Authorization Server (AS), knowing the `issuer-uri` URL or receiving an access token is not enough to declare the integration ready. The Resource Server also depends on specific issuer capabilities: **metadata discovery**, **JWK Set (JWKS)** to verify JWTs, **token introspection** to check token status, client authentication mechanisms at the introspection endpoint, audience policies, key rotation, TLS, caching, timeouts, and resilience during AS outages.

Those capabilities can differ across development, integration test, staging, and production. An endpoint available in test may not be exposed on production networks; an issuer may support JWTs in staging while production still uses opaque tokens; a JWKS endpoint may return a new key while the Resource Server holds an old cache; an introspection endpoint may return `active=true` without scoping tokens to the exact API.

> **Principle:** verify each capability with actual endpoints, responses, credentials, tokens, and runtime behavior in the target environment. Never assume an AS supports JWKS, introspection, revocation, audience, or key rotation merely from its product name or another environment.

This lesson focuses on three groups of components:

- **Metadata/discovery:** how the Resource Server locates the issuer, endpoints, and AS capabilities.
- **JWKS:** how the Resource Server fetches public keys and verifies JWT access tokens.
- **Introspection:** how the Resource Server queries the AS about a token's current status.

Primary examples use **Spring Security Servlet Resource Server** with Spring Boot and Spring Authorization Server. WebFlux APIs have corresponding Reactive classes; never copy Servlet's `JwtDecoder`, `OpaqueTokenIntrospector`, `RestClient`, or `SecurityFilterChain` into a Reactive stack without checking versions.

## 1. Three Concepts to Keep Distinct

| Component | Question It Answers | Common Data |
|---|---|---|
| Issuer metadata / OIDC discovery | Who is the AS, which endpoints does it advertise, and what capabilities does it support? | `issuer`, `jwks_uri`, `introspection_endpoint`, token endpoint |
| JWKS | Which public keys are used to verify signatures on tokens issued by this issuer? | `keys[]`, `kid`, `kty`, `use`, `alg`, `n`, `e`, `x`, `y` |
| Token introspection | Is the submitted token currently active and what context does the AS return for it? | `active`, `sub`, `client_id`, `scope`, `aud`, `exp` |

These three components relate to one another yet do not replace each other:

- Metadata can advertise `jwks_uri`; it is not the JWK Set itself.
- JWKS provides public keys; it does not tell whether an opaque token has been revoked.
- Introspection reports token status as decided by the AS; it does not automatically supply endpoint discovery or public keys.
- `issuer` identifies who issued the token; `aud` identifies the resource the token is sent to.
- OIDC Provider Configuration and OAuth Authorization Server Metadata overlap, yet are not interchangeable names across every deployment.

An integration may use **JWT + JWKS**, **opaque token + introspection**, or **JWT yet still introspect every request** if the AS supports it and the system needs fresher revocation state.

## 2. Metadata Discovery: Identify the Exact Issuer Before Calling Endpoints

### 2.1. Issuer Is an Identifier, Not Just a Hostname

Example issuer:

~~~text
https://login.example.com/realms/shop
~~~

JWT access tokens issued for the API must carry the claim:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

The Resource Server must compare `iss` against the configured issuer per the exact contract. Never strip paths, downgrade HTTPS to HTTP, add/remove trailing slashes, or lowercase the entire string to make two different issuers match.

RFC 8414 requires the returned metadata `issuer` to exactly match the issuer identifier used to construct the metadata URL. If they do not match, the metadata response must not be used. This prevents confusion across Authorization Servers.

### 2.2. OIDC Discovery and OAuth Authorization Server Metadata

Two common metadata types:

- **OpenID Connect Provider Configuration:** typically published at an endpoint named `/.well-known/openid-configuration`, per OIDC discovery rules.
- **OAuth 2.0 Authorization Server Metadata:** standardized in RFC 8414, using the well-known URI `/.well-known/oauth-authorization-server` per the RFC's URL construction rules.

For issuers with a path, the well-known location can differ from simple string concatenation `issuer + "/.well-known/..."`. Spring Security supports several discovery patterns, yet each AS may publish URLs per its own profile/version. Always obtain the **official discovery URL** from the issuer's documentation or configuration.

Illustrative metadata response:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "authorization_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs",
  "introspection_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/token/introspect",
  "revocation_endpoint": "https://login.example.com/realms/shop/protocol/openid-connect/revoke",
  "scopes_supported": ["openid", "profile", "orders.read", "orders.write"],
  "grant_types_supported": ["authorization_code", "client_credentials"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "private_key_jwt"],
  "introspection_endpoint_auth_methods_supported": ["client_secret_basic"]
}
~~~

This is an **illustrative** response, not default metadata for every issuer. Several fields are optional; an absent field does not uniformly prove whether a feature exists or not. Cross-check AS documentation and test the live endpoint.

### 2.3. Metadata Fields to Record

| Field | Meaning | What to Verify |
|---|---|---|
| `issuer` | Canonical issuer identifier | Does it match the token's `iss` claim? |
| `jwks_uri` | JWK Set URL | Is it HTTPS and reachable from the Resource Server? |
| `introspection_endpoint` | Introspection URL | Is it published, or obtained from another official config? |
| `introspection_endpoint_auth_methods_supported` | How the Resource Server authenticates at the introspection endpoint | Does it support the method the app intends to use? |
| `token_endpoint_auth_methods_supported` | How OAuth clients authenticate at the token endpoint | Do not confuse with Resource Server introspection credentials |
| `grant_types_supported` | Grant types advertised by the AS | Is the client registration permitted to use that grant? |
| `scopes_supported` | Scopes advertised by the AS | Is the API granted the required scopes? |
| `revocation_endpoint` | Token revocation endpoint | Is it supported and effective for the token type in use? |
| `code_challenge_methods_supported` | PKCE methods | Can public clients use `S256`? |
| `authorization_endpoint` / `token_endpoint` | OAuth flow endpoints | Do host, path, and TLS certificate match the environment? |

Metadata is an **advertised capability contract**, not a substitute for end-to-end testing. For instance, metadata listing `introspection_endpoint` does not prove the Resource Server client is authorized to call it.

### 2.4. Metadata May Not Publish Enough Information

An AS might:

- Lack discovery support and require manual endpoint configuration.
- Publish JWKS yet omit `introspection_endpoint`.
- Publish `introspection_endpoint` yet require a client authentication method absent from metadata.
- Support OIDC Provider Configuration while omitting certain OAuth extensions.
- Permit metadata/JWKS access only from internal networks.
- Expose different public issuer and internal network endpoints.

If a metadata field is missing, record it as an **unconfirmed capability**. Never guess URLs by appending `/jwks`, `/certs`, `/introspect`, or `/oauth2/introspect` to the issuer.

## 3. JWKS: Source of Public Keys to Verify JWTs

### 3.1. What Are JWK and JWK Set?

A **JWK (JSON Web Key)** describes a cryptographic key. A **JWK Set (JWKS)** is a JSON object containing an array of keys.

Example RSA public key JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "orders-signing-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Components:

| Field | Meaning |
|---|---|
| `kty` | Key type, such as `RSA`, `EC` |
| `kid` | Key ID, used to select the matching key |
| `use` | Key usage, such as `sig` |
| `alg` | Algorithm associated with the key, if published |
| `n`, `e` | RSA public modulus/exponent |
| `crv`, `x`, `y` | EC curve and public key coordinates |
| `key_ops` | Permitted key operations, if present |
| `x5c` | Certificate chain, if published |

Strings inside `<...>` are placeholders, not usable keys. The Resource Server's JWKS must contain only the **public key material** needed for verification; never publish private parameters such as RSA `d`, `p`, `q`, or EC private scalars.

### 3.2. JWKS Is Neither a Token Nor an Introspection Endpoint

~~~text
JWT access token
   |
   +-- header.kid
   +-- payload.iss / aud / exp / scope
   +-- signature
          |
          v
Resource Server fetches JWKS from trusted issuer
          |
          v
Locate public key matching kid/alg/key type
          |
          v
Verify signature + validate claims
          |
          v
Authentication
~~~

JWKS supplies verification keys. It does not contain a list of issued access tokens and is not a mechanism to check whether a token has been revoked.

### 3.3. `kid` Is Not Proof of Trust

A JWT header can contain:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-2026-a",
  "typ": "at+jwt"
}
~~~

`kid` is merely a key-selection hint within a **trusted key source**. Never:

- Fetch keys by calling an arbitrary `jku` or `x5u` URL sent by a token.
- Accept a key solely because `kid` matches a string.
- Use `kid` as a global cache key across issuers.
- Add public keys from a token into the trust store.
- Permit arbitrary algorithms requested by the JWT header.

Two issuers can share the same `kid` with different public keys. Key source namespaces must bind to the configured issuer/JWKS URI.

### 3.4. What Must a JWKS Endpoint Satisfy?

In each environment, check:

1. URL matches the issuer and AS documentation.
2. HTTPS with valid certificate chain and hostname.
3. Resource Server can resolve DNS and connect from the right network segment.
4. Response succeeds with valid JSON content type and JWK Set schema.
5. Public keys have `kid`s matching issued JWTs.
6. `kty`, `use`, `alg`, and `key_ops` are compatible with the signing algorithm.
7. No private key parameters are exposed.
8. JWKS updates cleanly during key rotation.
9. Cache headers/TTL and behavior when a new `kid` appears are well understood.
10. Rate limits, timeouts, and egress policies do not disrupt key refreshes.

RFC 8414 specifies that `jwks_uri`, when published, must use HTTPS. Each issuer's JWK Set URI may follow its own path; never hardcode paths based on product names.

## 4. Spring Security Verifies JWTs via Issuer and JWKS

### 4.1. Default Authentication Flow

In a Servlet Resource Server:

~~~text
HTTP Authorization: Bearer <JWT>
                 |
                 v
BearerTokenAuthenticationFilter
                 |
                 v
JwtAuthenticationProvider
                 |
                 v
JwtDecoder
                 |
                 +-- Fetch JWKS (if needed)
                 +-- Select public key
                 +-- Verify JWS signature
                 +-- Validate exp / nbf
                 +-- Validate iss
                 +-- Validate aud if configured
                 |
                 v
JwtAuthenticationToken
                 |
                 v
HTTP authorization / method security
~~~

Spring Security uses `JwtAuthenticationProvider`, `JwtDecoder`, and `JwtAuthenticationConverter` on the JWT authentication path. By default, scopes from the `scope` or `scp` claim map to authorities prefixed with `SCOPE_` per convention.

### 4.2. Configuring `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences: orders-api
~~~

`issuer-uri` tells Spring which issuer to trust and uses discovery to find public keys. `audiences` is a Spring Boot configuration property in supporting versions used to verify the token targets `orders-api`.

Current Spring Security versions can defer discovery until the **first request carrying a JWT**, so application startup does not necessarily fail immediately if the AS is down. That does not guarantee the first request will succeed if the metadata/JWKS endpoint is broken.

### 4.3. Configuring `issuer-uri` and `jwk-set-uri` Directly

If the AS lacks discovery or the Resource Server must start independently of the AS:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://keys.internal.example/realms/shop/jwks
          audiences: orders-api
~~~

With this configuration:

- `jwk-set-uri` specifies where to fetch public keys.
- `issuer-uri` preserves `iss` claim validation.
- The Resource Server needs no discovery to locate the JWKS URI.
- The internal network address of the JWKS can differ from the public issuer if that mapping is governed and protected.

Never remove `issuer-uri` just because the JWKS endpoint sits on an internal hostname. Issuer identity and the transport path for public keys are two separate pieces of information.

### 4.4. Configuring SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

This example illustrates HTTP authorization after token authentication. In real applications, split rules by HTTP method and read/write/delete scopes; tenant permissions and object ownership must still be enforced in services.

### 4.5. When Is a Custom `JwtDecoder` Needed?

A custom decoder helps when you need:

- A dedicated audience validator.
- An explicit JWS algorithm allowlist.
- Custom clock skew or token profile policies.
- A custom HTTP client, proxy, or timeout.
- Custom JWKS caching.
- Multiple issuers with distinct decoders/validators.

When you declare a custom `JwtDecoder` bean, Spring Boot may back off from decoder auto-configuration. Therefore, re-configure **all** required issuer, audience, timestamp, and contract validators; never assume a custom bean only swaps the HTTP client while automatically retaining every YAML validation property.

Example audience validator:

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public AudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(this.requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null
            )
        );
    }
}
~~~

Wiring alongside the default validator:

~~~java
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri,
        @Value("${app.security.audience}") String audience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .build();

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            new AudienceValidator(audience)
        )
    );

    return decoder;
}
~~~

The example requires imports for `Value`, `Bean`, `NimbusJwtDecoder`, `JwtDecoder`, `JwtValidators`, `DelegatingOAuth2TokenValidator`, and `OAuth2TokenValidator`. Add validators for RFC 9068/token type or business contracts if required by the API. Never replace all default validators with a standalone audience check.

## 5. Key Rotation: A Capability You Must Verify with Real Tokens

An AS may rotate signing keys periodically or upon compromise. A rotation workflow typically has an overlap phase:

~~~text
T0: JWKS publishes key-A
    Token-A signed with key-A

T1: JWKS publishes key-A + key-B
    Resource Server has time to pick up key-B

T2: AS begins signing new tokens with key-B
    Token-B must verify with key-B

T3: Old Token-A may still be valid
    JWKS keeps key-A during the overlap window

T4: Token-A expires per policy
    AS can remove key-A once no valid tokens need it
~~~

The overlap window must account for:

- Maximum access-token lifetime.
- Resource Server clock skew.
- JWKS cache TTL.
- When replicas refresh keys.
- Potential AS rollback to the old key.
- Emergency key-compromise response procedures.

### 5.1. Spring Security Auto-Rotating Keys Does Not Mean Instant Updates

Spring Security Resource Server supports refreshing keys when the AS publishes new keys. However, when a specific instance sees a new key depends on caching, request patterns, and how the key source refreshes.

Do not just check JWKS in a browser and conclude every Resource Server replica sees the new key. Issue tokens signed with the new key in staging, route requests across instances or through the load balancer, and verify outcomes.

### 5.2. JWKS Caching in Spring Security Servlet

Current Servlet documentation notes:

- `NimbusJwtDecoder` caches the JWK Set in memory for roughly **5 minutes** by default.
- You can pass a Spring `Cache` via `.cache(...)` on the builder to tune caching and use another cache provider.
- The cache keys by JWK Set URI and stores the JSON JWK Set as its value.

Example:

~~~java
@Bean
JwtDecoder jwtDecoder(
        CacheManager cacheManager,
        @Value("${app.security.issuer}") String issuer) {

    return NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .cache(cacheManager.getCache("authorization-server-jwks"))
        .build();
}
~~~

This is the **Servlet `NimbusJwtDecoder`** API in versions documenting this configuration. WebFlux uses `NimbusReactiveJwtDecoder` with different APIs/cache extensions; never copy `.cache(Cache)` to the Reactive builder unless your version's Javadoc provides that method.

Spring Cache is not a cache provider itself. The application must include an appropriate implementation and define eviction, TTL, serialization, namespacing, and failure behavior.

### 5.3. Verifying Key Rotation Per Environment

| Test | What to Observe |
|---|---|
| Token using current key | Verification succeeds |
| JWKS adds new key | Response contains new `kid` and right public key |
| New token using new `kid` | Resource Server picks up new key per refresh policy |
| Old token during overlap | Still verifies if unexpired and key remains published |
| Old key removed too early | Detects 401s on unexpired tokens |
| One replica has not refreshed | Detects inconsistent behavior across instances |
| Temporary JWKS error | Cached-key tokens and new-key tokens behave per policy |
| Key compromise | Emergency revocation/deny and rotation process exists, not just waiting for TTL |

Do not test by merely editing JSON in a local file. Verify the entire path from AS and proxies/caches to the running decoder.

## 6. Token Introspection: Asking the AS About Current Token Status

### 6.1. What Problem Does Introspection Solve?

Opaque tokens typically contain no claims the Resource Server can verify locally. The Resource Server sends the token to an **introspection endpoint** to query the AS for token status and metadata.

RFC 7662 defines the introspection response as JSON describing the token, including the `active` status. `active` semantics are determined by the AS; typically the token was issued by the AS, is unexpired, has not been revoked, and is permitted at the querying Resource Server.

An RFC 7662 request is typically an HTTP POST:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=OPAQUE_ACCESS_TOKEN
~~~

The introspection endpoint must be protected by TLS and authenticate the Resource Server per AS policy.

### 6.2. Illustrative Response

~~~json
{
  "active": true,
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "storefront-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.create",
  "exp": 2000000300,
  "iat": 1999999700
}
~~~

Not every introspection response must include all claims shown in the example. RFC 7662 defines `active` as the core element; remaining fields depend on the AS and token context.

The Resource Server must clearly know:

- Under what conditions `active` is computed.
- Whether the AS checks the token's audience/resource.
- Whether the AS checks expiry, not-before, and revocation.
- Whether scopes are filtered for the Resource Server calling introspection.
- Whether the Resource Server's client credentials are permitted to introspect that token type.
- Whether the response supplies the issuer/subject/tenant required for authorization.

### 6.3. `active=true` Is Not Permission to Call Every Endpoint

A token can be active yet:

- Lack `orders.write`.
- Be issued for `billing-api`, not `orders-api`.
- Belong to a client disallowed from calling admin endpoints.
- Lack membership in the requested tenant.
- Have object access revoked by business policy.

Introspection returns token status; Spring Security maps scopes/authorities, and HTTP/service authorization decides resource permissions.

### 6.4. `active=false` Responses

For non-existent, expired, or revoked tokens, the AS may return:

~~~json
{
  "active": false
}
~~~

Per RFC 7662, inactive responses should minimize extra fields to avoid leaking internal AS state. The Resource Server must never synthesize a principal when `active=false`, when the response violates schema, or when the introspection call fails.

## 7. Configuring Opaque Tokens in Spring Security

### 7.1. Spring Boot Properties

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/realms/shop/introspect
          client-id: orders-resource-server
          client-secret: "${ORDERS_INTROSPECTION_CLIENT_SECRET}"
~~~

All three values must match the environment:

- `introspection-uri`: endpoint published by the AS or confirmed by the integration team.
- `client-id`: OAuth client dedicated to **Resource Server introspection**, not confused with web/mobile app client IDs.
- `client-secret`: matching secret, sourced from a secret manager or controlled environment.

Never commit secrets to Git, public YAML, Docker images, logs, or pipeline artifacts.

### 7.2. SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

When a Bearer token arrives, Spring Security uses `OpaqueTokenAuthenticationProvider` and `OpaqueTokenIntrospector`. The introspector sends the token and client credentials to the endpoint; when the response confirms `active=true`, scopes map to authorities under the `SCOPE_` convention.

The default principal is typically `OAuth2AuthenticatedPrincipal`, and `Authentication` is typically `BearerTokenAuthentication`. This differs from JWT's `Jwt` principal inside `JwtAuthenticationToken`.

### 7.3. Using `SpringOpaqueTokenIntrospector` Explicitly

If defining a custom bean:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${app.security.opaque.introspection-uri}") String uri,
        @Value("${app.security.opaque.client-id}") String clientId,
        @Value("${app.security.opaque.client-secret}") String clientSecret) {

    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

A custom bean replaces the corresponding auto-configured introspector. When configuring manually, verify credentials and endpoint match the environment, TLS is validated, timeouts are tuned, and authority mappings never grant permissions beyond the contract.

## 8. Introspection with JWTs: Token Format Does Not Dictate Endpoint

An important point: **introspection is not strictly for opaque tokens**.

Spring Security's Opaque Token support does not care whether a token is a JWT; it sends the token to the configured introspection endpoint. If the AS supports introspecting JWT access tokens and returns appropriate status, the Resource Server can use introspection to validate JWTs.

Example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${ORDERS_INTROSPECTION_CLIENT_SECRET}"
~~~

Even though the token is a JWT, `Authentication` is produced through the opaque-token authentication flow and principal attributes come from the introspection response.

This option is useful when you need to ask the AS about token status on every request—such as when revocation must take effect sooner than JWT expiration. In return, each request may depend on network, latency, and introspection service availability.

**Do not confuse the two approaches:**

| Verification Method | JWT + JWKS | JWT + Introspection |
|---|---|---|
| Where is signature verified? | Resource Server | AS per introspection contract, if performed fully by AS |
| Network call per API request? | Usually no once keys are cached | Usually yes, unless introspection is cached |
| Revocation before `exp` | Needs extra mechanism or separate policy | Can be reflected via `active=false` |
| Default Spring Principal | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Authority source | Verified JWT claims | Attributes from introspection response |
| Runtime AS dependency | When discovery/key refresh needs network | When introspection is called |
| What must be verified | Issuer/JWKS/signature/claims | Endpoint/client auth/active/resource context |

## 9. Caching: JWKS Caches and Introspection Caches Carry Different Risks

### 9.1. JWKS Caching

A JWKS cache holds public keys or JWK Set JSON. It avoids fetching public keys on every JWT processed by the Resource Server.

Factors to agree upon:

- Default TTL and desired TTL.
- Per-instance cache vs. shared cache.
- Namespacing by issuer/JWK Set URI.
- Refresh behavior when the AS publishes a new key.
- Behavior when an old key is removed.
- Eviction when issuer/JWKS URL changes.
- Serialization and cache access controls.
- Behavior when the cache backend is unavailable.

**A JWKS cache is not a token validation cache.** The Resource Server must still verify the signature and claims of every JWT.

### 9.2. Introspection Caching

An introspection response contains token status and potentially scopes/roles/tenant attributes. Caching responses reduces AS call volume, yet can allow stale state to be accepted after a token is revoked or permissions change.

RFC 7662 highlights the trade-off:

- Short TTL: fresher status, higher traffic and AS load.
- Long TTL: lower load, wider window where revoked tokens remain accepted.
- No cache: highest freshness, every request depends on the introspection endpoint.

A caching policy should set TTL no longer than the remaining time until `exp` if the response includes expiry, and within the organization's acceptable revocation SLA.

Illustrative principle:

~~~text
effectiveCacheTTL =
    min(configuredTTL, remainingTokenLifetime, revocationSLA)
~~~

This is a design formula, not a built-in Spring Security function.

### 9.3. Cache Keys Must Protect the Token

If implementing custom introspection caching, avoid putting raw access tokens into:

- Cache metric labels.
- Logs.
- Distributed traces.
- Easily readable keys in admin UIs.

Use a keyed digest or secure cache-key scheme, namespaced by introspection endpoint/resource server. Ensure two distinct tokens cannot collide in a way that lets one token reuse another token's active status or authorities.

### 9.4. Never Cache Past Expiry or Across Wrong Audiences

An introspection response active for Resource Server A is not necessarily valid as a decision for Resource Server B. RFC 7662 permits the AS to return different responses depending on which protected resource queries introspection.

Therefore, caches must bind to **resource server context** and client credentials, never shared indiscriminately across APIs with different audiences/permissions.

## 10. Timeouts, Retries, and Availability

### 10.1. Two Distinct Network Paths

JWT + JWKS may require network calls when:

- Discovery metadata has not been fetched yet.
- JWKS cache is empty.
- Keys need refreshing.
- A new key appears.

Opaque introspection typically requires network calls on every token unless the application adds custom caching/decorators.

Consequently, JWKS timeouts and introspection timeouts should be configured and measured separately; they have different latency profiles and call frequencies.

### 10.2. Introspection Timeouts in Spring Security

Current Servlet documentation notes default connect/socket timeouts of roughly **30 seconds each** when the Resource Server communicates with the AS. That can be far too long for APIs with tight latency budgets.

Current Spring Security provides `RestClientOpaqueTokenIntrospector`, which accepts a `RestClient` configured with a dedicated `ClientHttpRequestFactory`.

Example for Spring Framework/Spring Security versions providing these APIs:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${app.security.opaque.introspection-uri}") String uri,
        @Value("${app.security.opaque.client-id}") String clientId,
        @Value("${app.security.opaque.client-secret}") String clientSecret) {

    SimpleClientHttpRequestFactory requestFactory =
        new SimpleClientHttpRequestFactory();

    requestFactory.setConnectTimeout(Duration.ofSeconds(2));
    requestFactory.setReadTimeout(Duration.ofSeconds(3));

    RestClient restClient = RestClient.builder()
        .requestFactory(requestFactory)
        .defaultHeaders(headers ->
            headers.setBasicAuth(clientId, clientSecret))
        .build();

    return new RestClientOpaqueTokenIntrospector(uri, restClient);
}
~~~

This example uses current `RestClientOpaqueTokenIntrospector` APIs. If your project runs an older Spring Security/Spring Framework version, check the Javadoc/BOM: you may need `SpringOpaqueTokenIntrospector` with `RestOperations` instead.

The 2- and 3-second values are examples only. Choose timeouts based on p95/p99 latency, network topology, API SLOs, and gateway timeout budgets.

### 10.3. JWKS Timeouts for Servlet Decoders

In a Servlet Resource Server, customize the HTTP client used by `NimbusJwtDecoder` via `RestOperations`:

~~~java
@Bean
JwtDecoder jwtDecoder(
        RestTemplateBuilder builder,
        @Value("${app.security.issuer}") String issuer) {

    RestOperations rest = builder
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(3))
        .build();

    return NimbusJwtDecoder
        .withIssuerLocation(issuer)
        .restOperations(rest)
        .build();
}
~~~

This follows the Servlet builder. WebFlux uses `WebClient`/Reactive decoder APIs. Connect/read timeouts are not necessarily total end-to-end deadlines; discovery, DNS, TLS, retries, body parsing, and connection pooling all add latency.

### 10.4. Retries Must Be Bounded

Never retry all errors indefinitely:

- HTTP 401/403 from bad client credentials will not heal on retry.
- Invalid JWT signatures should not re-fetch JWKS infinitely.
- DNS/TLS misconfigurations are not cured by continuous retries.
- An outage can trigger a retry storm if every API request retries simultaneously.
- Timeouts need a total retry budget and backoff/jitter if policy permits retries.

When trusted keys cannot be fetched or active status cannot be confirmed, **authentication must fail**. Never convert a network error into an authorization grant.

## 11. Capabilities on the Authorization Server Side

### 11.1. Endpoints That May Be Needed

An AS commonly exposes OAuth/OIDC endpoints:

| Endpoint | Purpose | Needed by Resource Server? |
|---|---|---|
| Authorization endpoint | Browser/user authorization flows | Not directly for JWT verification |
| Token endpoint | Issues access tokens | Used by OAuth clients |
| Provider Configuration / AS Metadata | Publishes issuer and endpoints/capabilities | Needed if using discovery |
| JWK Set endpoint | Publishes public keys | Needed if verifying JWTs via JWKS |
| Introspection endpoint | Queries token status | Needed if using introspection |
| Revocation endpoint | Revokes tokens | Useful when policy requires revocation |
| UserInfo endpoint | Returns OIDC user claims | Usually for OIDC clients, not JWT key verification |
| End-session/logout endpoint | OIDC logout | Does not replace API token validation |

Not every AS exposes every endpoint or enables the same profile.

### 11.2. Spring Authorization Server

Spring Authorization Server includes default configuration supporting protocol endpoints like token, introspection, revocation, AS metadata, and JWK Set. However:

- **The JWK Set endpoint is only configured when a `JWKSource<SecurityContext>` bean exists.**
- **OIDC 1.0 endpoints are disabled by default** in minimal configurations; enable the OIDC configurer if Provider Configuration/UserInfo/Logout endpoints are needed.
- Endpoint paths can be customized via `AuthorizationServerSettings`.
- Endpoint existence does not prove clients or Resource Servers are properly configured.

Example JWK source in an AS:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey rsaKey = loadOrCreateSigningKeyFromSecureKeyManagement();

    JWKSet jwkSet = new JWKSet(rsaKey);

    return (jwkSelector, securityContext) ->
        jwkSelector.select(jwkSet);
}
~~~

`loadOrCreateSigningKeyFromSecureKeyManagement()` is a placeholder for application-implemented key management; never generate a brand-new signing key on every startup. Production requires key persistence, HSM/KMS or secret storage, rotation, and access control.

### 11.3. The JWK Set Endpoint Must Never Expose Private Keys

The AS retains private signing keys and publishes public keys in JWKS. Verify:

- Does the public key match the key signing tokens?
- Does `kid` in JWTs match a published key?
- Does the JWK contain zero private parameters?
- Does key rotation avoid overwriting the old key too early?
- Are private signing keys stored separately from the public JWKS JSON?

### 11.4. The Introspection Endpoint Must Be Protected

The Resource Server acts as an OAuth client when calling the introspection endpoint. Verify:

- Which client authentication method the endpoint requires.
- Whether the client ID/secret or key/certificate is correct.
- Whether credentials are scoped strictly to introspection permissions.
- Whether the endpoint enforces TLS and certificate validation.
- Whether rate limiting and auditing are enabled.
- Whether the response checks full token status.
- Whether tokens meant for another API are marked inactive or properly scoped.

## 12. Capability Matrix by Environment

Do not use a test result from dev as a proxy for production. Build a matrix with clear owners and evidence.

| Capability | Development | CI/Integration Test | Staging | Production |
|---|---|---|---|---|
| Canonical issuer | Dedicated dev issuer | Stub/test issuer | Dedicated staging issuer | Official production issuer |
| Discovery metadata | URL and issuer match | Contract-backed mock response | Real endpoint, real DNS/TLS | Real endpoint, HA and monitoring |
| `jwks_uri` | Dev/test public keys | JWKS stub or test AS | Staging keys | Production keys |
| JWK algorithms | Matches contract | Tests both valid/invalid algs | Matches production | Approved allowlist |
| Key rotation | Fast trigger possible | Tests old/new keys | Rotation rehearsals | Rotation/rollback runbook |
| Introspection endpoint | Dev AS optional | Mock `active=true/false` | Real endpoint | HA, rate limits, auth |
| Introspection auth method | Dev credentials | Tests auth success/failure | Staging credentials | Production secrets/keys |
| Audience/resource binding | Dev API | Wrong-audience tokens must fail | Mirrors production | Mandatory policy |
| Revocation | Can revoke test tokens | Tests active -> inactive | Checks propagation | SLA and emergency runbook |
| Cache/TTL | Short for testing | Deterministic | Near production | Aligned with revocation/SLO |
| Timeout/retry | Short to surface errors | Injects timeout/5xx | Realistic network | Aligned with SLO and budget |
| TLS/trust chain | Dev CA | Dedicated test CA | Prod-like certificates | Official CA, rotation |
| Network/egress | Developer network | CI allowlist | Firewall/service mesh | Approved egress policy |
| Monitoring | Local logs | Assertions | Test dashboards | Alerts/on-call/runbook |

Each cell should have at least one piece of evidence:

- Confirmed URL/issuer.
- Safely archived sample HTTP response.
- Test report with redacted requests/responses.
- AS owner confirmation of capability.
- Key rotation/revocation runbook.
- Metrics/dashboards from that environment.

### 12.1. Environment Differences That Commonly Cause Failures

**Different issuers:** staging tokens cannot verify in production when `iss` and signing keys differ. That is usually by design.

**Different audiences:** a token with `aud=orders-api-staging` must not be accepted by `orders-api`.

**Different JWK Sets:** dev public keys must never enter production trust stores.

**Different client credentials:** staging introspection clients must not work in production.

**Different endpoint paths:** an issuer might expose `/oauth2/introspect` in staging and another path in production; pull paths from managed configuration, never guess.

**Different TLS:** internal certificates, CA chains, or mTLS can make one environment succeed while another fails.

**Different capability flags:** some ASs enable introspection or revocation in production but not in dev, or vice versa.

## 13. Procedure for Verifying Discovery Metadata

Before configuring a Resource Server, verify metadata in each environment.

### 13.1. Checking the HTTP Response

~~~bash
curl --fail --show-error --silent \
  "$AUTH_SERVER_METADATA_URL"
~~~

`AUTH_SERVER_METADATA_URL` must be the official discovery URL for that environment. Do not assume `issuer + "/.well-known/..."` always produces the right URL.

Verify:

- HTTP status 200.
- `Content-Type: application/json`.
- `issuer` field equals the canonical issuer.
- `jwks_uri` is present if using JWT/JWKS.
- `introspection_endpoint` is present or configured via official documentation if using introspection.
- Advertised auth methods match client credentials.
- No endpoint points to another environment's host.
- URLs use HTTPS as required by the profile.

### 13.2. Verifying Metadata Issuer Equality

If metadata returns:

~~~json
{
  "issuer": "https://login.example.com/realms/shop"
}
~~~

that must be the canonical issuer used by JWTs. If a token carries:

~~~json
{
  "iss": "https://login.example.com/realms/other"
}
~~~

the Resource Server must reject it unless that issuer is explicitly trusted.

Never fix an issuer mismatch by disabling the issuer validator or rewriting claims.

### 13.3. Metadata Is Not an Unconditionally Trusted Endpoint List

Discovery documents are part of trust bootstrap. Fetch metadata only from pre-approved issuers over proper TLS. Never let a request's bearer token control the issuer URL so the server fetches arbitrary metadata; that creates SSRF and trust injection vulnerabilities.

## 14. Procedure for Verifying JWKS

### 14.1. Obtaining the JWKS URL from Metadata

Do not hardcode URLs by vendor name. Use the `jwks_uri` from a verified issuer or the official URL provided by the AS.

### 14.2. Checking the Response

~~~bash
curl --fail --show-error --silent \
  "$JWKS_URI"
~~~

Verify:

- HTTP 200.
- JSON has a `keys` array.
- Each key has `kty` and required public material.
- `kid` matches the key ID in test tokens.
- Algorithm matches signing policy.
- No private key material is present.
- Response does not redirect to an unfamiliar host.
- Reachable from the Resource Server's runtime network, not just a developer laptop.

### 14.3. Checking Real Tokens

A test JWT access token must be signed by the private key matching a public key in the JWKS.

Verify on the token:

- `iss` matches the issuer.
- `aud` contains the current API.
- `exp` and `nbf` are valid.
- `alg` is in the allowlist.
- `kid` exists in the JWKS.
- Token type/profile matches access tokens, not ID tokens.
- Right scopes are granted.

Never use `jwt.io` or Base64 decoding as proof of signature verification. Inspecting claims is fine for debugging, yet trust decisions must come from the real decoder and validators.

## 15. Procedure for Verifying Introspection

### 15.1. Verifying Endpoint and Client Authentication

Use a test token issued in the exact environment and the Resource Server's client credentials. Example:

~~~bash
curl --fail --show-error \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --request POST \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=$ACCESS_TOKEN" \
  "$INTROSPECTION_URI"
~~~

Use only dedicated test tokens and credentials. Avoid enabling shell tracing or saving raw command output containing secrets/tokens in CI logs.

### 15.2. Responses to Verify

| Submitted Token | Expected Response per Contract |
|---|---|
| Unexpired access token for right API | `active=true`, matching scopes/resource |
| Expired token | `active=false` |
| Revoked token | `active=false` per revocation policy |
| Non-existent token | `active=false` |
| Token issued for another API | `active=false` or response granting no access to this API |
| Token from another issuer | Per trust federation/introspection contract; never accept automatically |
| Wrong client credentials | Endpoint rejects client, typically 401/403 |
| Missing/malformed token | Never creates an authenticated principal |
| Introspection endpoint timeout | Authentication unconfirmed |
| Malformed JSON/schema response | Fail closed and log dependency error |

Not every AS returns the exact same status for every failure. Distinguish **client authentication failure**, **inactive token**, and **upstream infrastructure failure**.

### 15.3. Verify Whether `active` Truly Reflects Revocation

Do not stop at a normal active token. Always:

1. Issue a test token.
2. Confirm introspection returns `active=true`.
3. Revoke the token via the AS-supported mechanism.
4. Call introspection again.
5. Measure how long it takes from revocation until `active=false`.
6. If the Resource Server caches results, determine how long the old token remains accepted.
7. Compare against your revocation SLA.

If the AS only checks expiration time when returning `active=true` without checking revocation state per contract, introspection does not deliver the expected immediate revocation.

## 16. Integration Testing with Spring Security

### 16.1. `MockMvc.with(jwt())` Tests Authorization, Not JWKS

Example:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

This is useful for testing HTTP `hasAuthority` rules. However, mock JWTs bypass:

- Metadata discovery.
- Network requests to JWKS.
- JWS signature verification.
- Issuer/audience validators.
- Key rotation.
- TLS and timeouts.

Never use this test alone to claim issuer integration works.

### 16.2. Testing Real JWTs with Test Keys and a JWKS Stub

An integration test should:

1. Generate an RSA/EC key pair exclusively for tests.
2. Run a JWKS stub publishing only the public key.
3. Build JWT access tokens signed with the test private key.
4. Point `NimbusJwtDecoder` to the JWKS stub and test issuer.
5. Send real requests through `BearerTokenAuthenticationFilter`.
6. Verify tokens with valid signature/issuer/audience authenticate.
7. Verify bad signatures are rejected.
8. Verify wrong issuers are rejected.
9. Verify wrong audiences are rejected.
10. Verify expired tokens or future `nbf` are rejected.
11. Count JWKS HTTP calls to understand caching/refresh behavior.
12. Update JWKS with a new key and test new tokens after refresh.

Private keys live solely in test fixtures—never use production keys.

### 16.3. Testing Opaque Introspection with a Stub

Use a mock HTTP server or test AS:

- Token A returns `active=true`.
- Token B returns `active=false`.
- Token C has read scope without write scope.
- Token D returns a different audience.
- Token E triggers an endpoint timeout.
- One case returns HTTP 401 from wrong client credentials.
- One case returns a malformed response.

Send tokens through the real Bearer filter path to test `OpaqueTokenIntrospector` and `OpaqueTokenAuthenticationProvider`.

### 16.4. Testing Caching and Revocation

If introspection caching is used:

~~~text
1. Token T -> introspection active=true.
2. Resource Server caches response.
3. AS revokes T.
4. Request with T before cache expires.
5. Request with T after cache expires.
~~~

Measure the exact window during which a revoked token stays accepted. If it exceeds SLA, reduce TTL or change the cache strategy.

### 16.5. Environment-Isolated Testing Without Shared Credentials

CI, staging, and production need separate credentials. Never run tests against production introspection endpoints using real tokens or client secrets. Production contract verification should use approved synthetic accounts/tenants and a controlled verification process.

## 17. Interpreting Common Errors

| Symptom | Possible Cause | What to Check |
|---|---|---|
| App starts yet first JWT returns 401 | Discovery/JWKS failure or invalid token | Metadata, JWKS, issuer, key ID |
| `Unable to resolve Configuration with issuer` | Wrong discovery URL or incompatible metadata | Canonical issuer and well-known path |
| `Unable to resolve JWK Set` | Wrong `jwks_uri`, DNS/TLS/HTTP error | Metadata response, egress, certificates |
| `No matching key(s) found` | `kid` absent from JWKS/cache or unsynced rotation | JWT header and JWKS |
| Invalid signature | Signed with different key or wrong algorithm | Signing key, `kid`, `alg`, key type |
| Issuer validation failed | `iss` claim mismatch | Exact issuer equality |
| Audience validation failed | Token intended for another API | `aud` and AS audience mapping |
| Opaque token inactive | Token expired/revoked/invalid | Introspection response and AS state |
| Introspection 401/403 | Wrong Resource Server credentials or auth method | Client registration, credentials |
| Introspection timeout | Network issue or overloaded AS | Connect/read timeouts, DNS, proxy, SLO |
| Revoked token still works briefly | Introspection cache still valid | TTL and invalidation |
| Staging works, production fails | Different endpoints, keys, issuers, secrets, or egress | Environment capability matrix |
| `SCOPE_*` missing | AS emits scope in another field or wrong mapper | `scope`/`scp` and authority converter |
| User token works, service token fails | Different client scopes/audience/token profile | AS client registration and token claims |
| Valid token accesses another tenant | Missing business authorization | Tenant membership, owner/ACL |

**401** usually relates to authentication failure; **403** usually relates to a valid principal lacking permissions. Network outages may map to authentication errors or infrastructure errors depending on exception handling; never lump every failure into "token invalid."

## 18. Security and Operations Across Multiple Environments

### 18.1. Trust Boundary

- Trust only pre-approved issuers.
- Fetch metadata and JWKS only from governed issuers/URLs.
- Never allow JWT `jku`, `x5u`, unverified `iss`, or request headers to drive arbitrary outbound URLs.
- Verify TLS server certificates/hostnames.
- Restrict egress from Resource Servers to AS/JWKS/introspection.
- Never disable TLS verification to work around certificate errors.
- Never use dev keys or dev client credentials in production.

### 18.2. Secrets and Token Handling

- Store introspection client secrets in a secret manager.
- Never log `Authorization` headers or raw tokens.
- Never place tokens in query strings.
- Prefer POST for introspection per RFC 7662.
- Never log full introspection responses if they contain PII.
- Never include private signing keys in JWKS.
- Rotate introspection client credentials.
- Restrict access to secrets and audit reads.

### 18.3. Availability and Fail Closed

When the JWKS endpoint fails:

- Tokens matching already-cached keys can continue verifying per decoder/cache behavior.
- Tokens needing a new key that the Resource Server cannot fetch cannot be verified.
- Never accept unverified signatures.

When the introspection endpoint fails:

- The Resource Server cannot confirm token status from the authoritative source.
- Return an authentication/dependency error per handler.
- Never fabricate principals or treat timeouts as `active=true`.

### 18.4. Monitoring Metrics

Separate metrics by group:

| Metric/Event | Purpose |
|---|---|
| Metadata discovery success/failure | Track bootstrap and metadata health |
| JWKS fetch count/duration/failure | Track network/key-source health |
| Unknown `kid` | Detect rotations or anomalous tokens |
| JWT signature/issuer/audience failures | Categorize token validation errors |
| Introspection request count/latency | Monitor AS load and dependency latency |
| Introspection `active=false` | Track inactive tokens |
| Introspection 401/403 | Detect client credential/config issues |
| Introspection timeout/5xx | Monitor availability |
| Cache hit/miss/eviction | Understand freshness and network load |
| Authentication 401 | Token/authentication errors |
| Authorization 403 | Missing scope/role/policy |

Exact metric names depend on Micrometer, Spring Security version, and instrumentation. This table lists observability signals to track, without claiming every metric exists automatically.

Never use raw tokens, emails, or full claims as metric labels due to data-exposure and high-cardinality risks.

## 19. Capability Checklist Before Onboarding a New Environment

### Issuer and Metadata

- [ ] Canonical issuer confirmed by the issuer team.
- [ ] Discovery URL is accurate and returns HTTP 200.
- [ ] Metadata `issuer` exactly matches configured issuer.
- [ ] Metadata does not point to unexpected hosts/environments.
- [ ] `jwks_uri` confirmed if the API uses local JWT verification.
- [ ] `introspection_endpoint` confirmed if the API uses introspection.
- [ ] Client authentication methods and relevant scopes/grants recorded.

### JWKS/JWT

- [ ] JWKS returns valid JWK Set JSON.
- [ ] Token `kid` has a matching public key.
- [ ] `kty`, `use`, `alg`, and key operations match the contract.
- [ ] Zero private key material exposed.
- [ ] Issuer validator enabled.
- [ ] Audience/resource validator enabled.
- [ ] Allowed algorithms restricted.
- [ ] `exp`, `nbf`, clock skew, and token profile validated.
- [ ] Key rotation tested with old/new keys and overlap window.
- [ ] Cache TTL, timeouts, and AS outage behavior defined.

### Introspection

- [ ] Endpoint matches environment and enforces TLS.
- [ ] Resource Server client authentication succeeds.
- [ ] Credentials pulled from a secret manager.
- [ ] `active=true` and `active=false` tested.
- [ ] AS validates expiry, revocation, signature (if applicable), and resource binding.
- [ ] Scope/audience/issuer attributes satisfy the API contract.
- [ ] Revoked tokens tested.
- [ ] Timeouts/retries/cache TTL defined.
- [ ] Introspection failures do not fail open.
- [ ] Raw tokens absent from logs/traces.

### Environment and Operations

- [ ] Dev/staging/prod use environment-specific issuers, keys, audiences, and credentials.
- [ ] CI uses test keys or stubs, never calling production with real secrets.
- [ ] Network egress, DNS, proxies, and CA chains verified from runtime.
- [ ] Dashboards/alerts in place for discovery, JWKS, and introspection.
- [ ] AS and Resource Server owners have key rotation/revocation runbooks.
- [ ] Procedure exists to disable compromised issuers/clients.
- [ ] Per-environment integration tests or contract tests exist.
- [ ] Unconfirmed capabilities have assigned owners and deadlines.

## 20. Self-Check Questions

**1.** How do metadata discovery, JWKS, and introspection differ?

> Metadata advertises the issuer, endpoints, and capabilities; JWKS supplies public keys to verify JWTs; introspection returns token status and metadata as decided by the AS.

**2.** Are `issuer` and `jwks_uri` the exact same URL?

> No. `issuer` is the AS identifier; `jwks_uri` is the public keys endpoint. They can have different hosts/paths, provided the mapping is governed and the issuer is still validated.

**3.** Is `jwks_uri` mandatory in every metadata response?

> No. In RFC 8414, `jwks_uri` is optional; if the AS uses JWT/JWKS, the Resource Server still needs a confirmed key source.

**4.** Is `introspection_endpoint` guaranteed to be published in metadata?

> No. RFC 8414 defines it as optional; if using introspection when metadata omits the field, obtain the endpoint from another official configuration/document.

**5.** Does JWKS contain private signing keys?

> No. The Resource Server only needs public key material to verify signatures.

**6.** Is `kid` proof that a token is valid?

> No. It only helps select a key within an already-trusted JWK source.

**7.** Must JWTs hit the JWKS endpoint on every request?

> No. Public keys can be cached; every token must still be verified using the matching key.

**8.** Why still configure `issuer-uri` when `jwk-set-uri` is already known?

> To preserve `iss` claim validation; the JWK Set URI only tells where to fetch keys.

**9.** Does introspection `active=true` mean the token can call every endpoint?

> No. Audience/resource binding, scopes, roles, and business authorization still apply.

**10.** Can JWT access tokens be introspected?

> Yes, if the AS supports it. Spring Security Opaque Token support can send any token to the configured introspection endpoint; verification then rests with the AS.

**11.** Why is a long introspection cache TTL risky?

> Revoked tokens or modified permissions can remain accepted while stale cached responses are valid.

**12.** Why must `active=false` be tested?

> To prove the Resource Server actually rejects inactive tokens, rather than testing only the happy path.

**13.** Can `issuer-uri` differ between staging and production?

> Yes, and using per-environment issuers is generally recommended; staging tokens must never be trusted in production.

**14.** Does Spring Authorization Server always expose a JWKS endpoint in every configuration?

> No. The JWK Set endpoint is only configured when a `JWKSource<SecurityContext>` bean is present.

**15.** Are OIDC endpoints enabled by default in a minimal Spring Authorization Server config?

> No. You must enable the OIDC configurer if Provider Configuration/UserInfo/Logout endpoints are needed.

**16.** If JWKS or introspection endpoints time out, should requests pass through to preserve availability?

> No. When a token's validity cannot be proven, the Resource Server must fail closed.

## 21. References

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, JWKS, JWT validation, audience, key rotation, caching, and timeouts.
- [Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, `active`, `OpaqueTokenIntrospector`, timeouts, and introspecting JWTs.
- [Spring Security — WebFlux Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): corresponding Reactive APIs.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): endpoint metadata, tokens, introspection, revocation, and JWK Sets.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer, `jwks_uri`, `introspection_endpoint`, and metadata validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration and OIDC discovery.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims like `iss`, `aud`, `exp`, `nbf`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, `active`, client authentication, and cache trade-offs.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token JWT profile and audience.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience/algorithm validation and token confusion.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): configuring HTTP clients and request factories.

**Conclusion:** A Resource Server successfully integrating with an AS must verify three things: **metadata identifies the right issuer and capabilities**, **JWKS supplies trusted public keys to verify JWTs**, and **introspection returns contract-compliant token status when current state must be checked**. These capabilities must be verified in every environment because issuers, keys, credentials, endpoint paths, audiences, TLS, caches, and network policies can differ. Test both valid and invalid tokens, key rotation, revocation, timeouts, and outages; keep issuer/audience validation intact and fail closed whenever tokens cannot be verified.