# JWT, Opaque Tokens, and Verification Choices in Spring Security OAuth 2.0 Resource Server

A **Resource Server** is an API that receives access tokens issued by an **Authorization Server** and decides whether a request is allowed to access a resource. Two common approaches for handling bearer access tokens are **local JWT verification** and **calling an introspection endpoint to check the token**. This difference directly impacts latency, access revocation capability, availability, and system trust boundaries.

A distinction to make right from the start: **JWT and opaque token describe how a token is represented; local verification and introspection describe how the Resource Server validates the token**. JWTs are typically verified locally via digital signatures; opaque tokens typically require introspection. However, a JWT can still be sent to an introspection endpoint if the system wants to confirm its active status from the Authorization Server.

## 1. Where does the Resource Server sit in the OAuth 2.0 flow?

Core components:

- **Client**: web app, mobile app, or service calling the API.
- **Authorization Server (AS)**: authenticates/authorizes according to an appropriate OAuth 2.0 flow and issues access tokens.
- **Resource Server (RS)**: API protecting resources; validates tokens and enforces access permissions for each endpoint.

Overall flow:

~~~text
  Client                    Authorization Server                  Resource Server
    |                                |                                   |
    |--- request/issue token ------->|                                   |
    |<--------- access token --------|                                   |
    |                                                                    |
    |------------- GET /api/orders ------------------------------------->|
    |             Authorization: Bearer <access_token>                   |
    |                                                                    |
    |                     RS verifies token and checks permissions       |
    |<------------------- 200 / 401 / 403 -------------------------------|
~~~

A Resource Server **must not trust a token merely because the request carries an `Authorization: Bearer ...` header**. It must establish that the token is valid, issued by a trusted source, intended for the right API, and carries appropriate permissions.

**Distinguishing an access token from an OpenID Connect (OIDC) ID token:**

- **Access token** is meant for the Resource Server; used to call APIs within granted permission scopes.
- **ID token** is meant for the OIDC Client (relying party), proving details about the user's authentication session to the Client. Do not substitute an ID token into the Bearer header to protect an API.
- ID tokens are usually JWTs, yet **the JWT format does not turn a token into an access token**. Inspect its purpose, issuer, audience, token type, and identity provider contract.

### Token authentication and authorization are two separate decisions

A token can be authenticated successfully yet still be denied permission for a specific operation. For example:

- JWT has a valid signature, is unexpired, and is intended for `orders-api`: **token authentication succeeds**.
- Token only carries the `orders.read` scope, yet the client sends `POST /api/orders` requiring `orders.write`: **authorization fails**.

In HTTP APIs, outcomes are typically represented as **401 Unauthorized** when valid authentication credentials are missing/invalid and **403 Forbidden** when authenticated but lacking permissions. Exact error mapping depends on configuration and exception-handling paths.

## 2. JWT access tokens: structure and meaning

**JWT (JSON Web Token)** is a format for representing claims as JSON. JWTs commonly appear as compact JWS strings with three parts joined by dots:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Example decoded contents of the first two parts (illustrative only, not a verifiable real token):

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1794700000,
  "nbf": 1794700000,
  "exp": 1794703600,
  "scope": "orders.read orders.write",
  "client_id": "shop-web"
}
~~~

Several claims are especially important:

| Claim | Meaning | Typical validation rule |
|---|---|---|
| `iss` | Token issuer | Must match the issuer trusted by the API |
| `sub` | Subject bound to the token | Used as an identifier per AS contract; does not automatically imply permissions |
| `aud` | Target resource/service receiving the token | Must contain the current API's identifier |
| `exp` | Expiration time (Unix timestamp) | Expired tokens must be rejected |
| `nbf` | Not-before time | Must not be accepted prior to this timestamp |
| `iat` | Issued-at time | Useful for lifetime policies and observability |
| `scope` / `scp` | Granted permissions | Must be converted per the AS's conventions |
| `client_id` | Client issued the token (if present) | Additional per-client policies can be applied |

**Not every JWT access token contains the exact claim set above.** Specific claims and `scope`/`scp` structures vary by Authorization Server and token profile. Some systems add `roles`, `groups`, `tenant_id`, or custom claims. The Resource Server must rely on an explicit contract rather than guessing.

### JWTs are signed, not encrypted by default

With JWS, the header and payload are merely **Base64URL encoded**. Anyone holding the token can read the data inside. The signature detects tampering, yet **does not hide information**. Never put passwords, secrets, sensitive personal data, or unnecessary data into access token claims.

JWTs can be encrypted with JWE, though that is a separate mechanism; standard JWT Resource Server configurations focus on signed JWTs.

### Asymmetric signatures and JWK Sets

In the common model, the AS signs JWTs with a **private key** (such as RSA or EC), while the RS uses the corresponding **public key** to verify the signature. Public keys are typically published at a **JWK Set URI (JWKS)**. The `kid` header helps select the matching key from the key set.

~~~text
Authorization Server                        Resource Server
       |                                          |
       | -- JWT signed with private key --------> |
       |                                          | -- fetch/cache JWKS from AS
       | <------------ (public keys) ------------ |
       |                                          | -- select public key by kid
       |                                          | -- verify signature + claims
~~~

This approach does not require the Resource Server to possess the Authorization Server's private key. When the AS rotates signing keys, the Resource Server can load new public keys from JWKS via the decoder's cache/refresh mechanism.

**Never treat `alg`, `kid`, or URLs in the JWT header as trusted client-supplied configuration.** Algorithm policies, issuer, and key retrieval endpoints must be configured from trusted sources. Never accept unsigned tokens (`alg: none`), and never arbitrarily use a key specified by the token itself.

## 3. How does a Resource Server verify JWTs locally?

Suppose the API receives:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

A conceptually secure validation flow consists of:

1. **Extract the bearer token** from an accepted location, typically the `Authorization` header.
2. **Decode the JWT structure** to determine the token type and valid format.
3. **Verify the algorithm and signature** against public keys belonging to the configured issuer; never use keys/issuers arbitrarily supplied by the client.
4. **Validate time claims** such as `exp` and `nbf`, with controlled clock skew tolerance.
5. **Validate issuer** (`iss`) and **audience** (`aud`) matching the API.
6. **Apply additional policies** if required: token type, tenant, client, MFA requirement, or application constraints.
7. **Convert scopes/claims into authorities** and check the accessed endpoint or method.

Actual checks are performed by Spring Security and configured validators; the list above serves as a model to separate responsibilities. If you verify the signature yet skip `aud`, a valid JWT meant for API A could still be sent to API B within the same ecosystem.

### JWTs do not require calling the AS on every request

Once the appropriate public keys are cached, the Resource Server can verify JWTs without contacting the Authorization Server on every request. This benefits latency, throughput, and resilience against network failures.

In return, **a valid signature does not by itself prove the token has not been revoked**. A token can still pass signature and `exp` checks even if the user just logged out, was locked, or had access rights withdrawn. If a system relies solely on local JWT verification, such changes usually take effect at the latest when the token expires, unless additional mechanisms exist such as revocation lists, status checks, or short-lived tokens.

## 4. Opaque tokens: verifying via introspection

An **opaque token** is a string whose **internal structure the Resource Server does not need to know**. It is typically a random value serving as a reference to state stored on the Authorization Server.

~~~text
Authorization: Bearer 8f25e86a3b6d4e48b907f20e92a5f...
~~~

You cannot determine expiration, subject, or permissions merely by splitting and decoding the string. The Resource Server typically calls **OAuth 2.0 Token Introspection** (RFC 7662) over a server-to-server backchannel:

~~~text
Client                          Resource Server               Authorization Server
  |                                   |                                |
  |-- Bearer opaque token ----------->|                                |
  |                                   |-- POST /introspect ------------>|
  |                                   |   token + RS credentials       |
  |                                   |<-- active, scope, sub, ... -----|
  |                                   |                                |
  |                                   |-- check permissions & handle   |
  |<------------ 200/401/403 ---------|                                |
~~~

Example HTTP request from Resource Server to AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic <credentials-of-resource-server>
Content-Type: application/x-www-form-urlencoded

token=<access_token>
~~~

Example response for an active token:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop",
  "exp": 1794703600
}
~~~

Response for an inactive token can simply be:

~~~json
{
  "active": false
}
~~~

**`active: true` is the Authorization Server's conclusion about token status at the moment of introspection.** The Resource Server must still enforce the API's own policies, especially audience, scope, and business conditions if applicable. Never assume every AS returns the exact same set of claims; rely only on the actual attributes the AS commits to returning.

### Why can introspection satisfy fast revocation requirements?

The AS can check whether a token has been revoked, expired, or invalidated due to account or policy changes. If the Resource Server calls introspection on every request, the very next call observes the AS's updated decision.

This capability has a cost: an extra network call, load on the introspection endpoint, securing client credentials, timeouts, and dependency on AS availability. If introspection results are cached to reduce load, **the cache TTL also becomes the maximum potential delay before token revocation takes effect**, depending on caching and invalidation policies.

### Opaque token does not mean weak security

A random token string with sufficient entropy, transmitted strictly over TLS, stored properly, and validated with the AS can provide very strong security. Conversely, a JWT with a strong signature but missing `aud`, misconfigured keys, or excessive lifetime still introduces risk. Security comes from the entire authentication, authorization, token lifecycle, and operational setup—not merely from how the token looks.

## 5. How do JWT, opaque tokens, and introspection differ?

| Aspect | Locally verified JWT | Token verified via introspection |
|---|---|---|
| Verification method | Verify signature and claims using trusted keys | Query the AS for token status and attributes |
| Input token | Typically a signed JWT | Opaque token **or JWT** supported by AS introspection |
| Typical latency | Low once keys are cached | Adds a network call to the introspection endpoint |
| AS dependency per request | Usually only needed for metadata discovery / key fetch or refresh | Needed on introspection, unless results are cached |
| Early revocation | Not immediate with local verification alone | Can be fast if AS reflects revocation and cache TTL is short |
| Data exposed in token | JWS payload is readable | Token string does not necessarily expose claims |
| Scalability | High for heavy traffic and many RS instances | Requires corresponding introspection capacity |
| Permission changes mid-lifetime | Old claims stay in JWT until expiration or extra checks | AS can return updated status/permissions by design |
| Handling AS connectivity issues | Tokens with cached keys can still be verified | Requests may fail authentication if endpoint is unreachable |
| Operations | Manage JWKS, key rotation, TTL, validators | Manage introspection, client credentials, timeouts, caching |

This is not a comparison of "JWT is safer than opaque" or vice versa. It is a trade-off between **distributed verification** and **centralized state decisions**.

## 6. Configuring a Spring Boot Resource Server with JWT

The following examples apply to a **Spring MVC servlet application** with modern Spring Security configured via `SecurityFilterChain`. When using WebFlux, substitute the corresponding reactive components.

### 6.1. Declaring dependencies

In a Spring Boot project using Gradle, add the required starters:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The Resource Server starter typically brings in the components needed for JWT handling. If declaring individual Spring Security modules directly instead of the starter, JWT support requires both `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose`.

### 6.2. Specifying issuer and audience

Example `application.yml` for an `orders-api` trusting a fixed issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

- `issuer-uri` defines the valid `iss` value and lets Spring discover AS/JWKS configuration via metadata endpoints supported by the AS.
- `audiences` requires the token to have an audience matching the Resource Server. This property is available in modern Spring Boot; in older versions lacking support, configure a custom `OAuth2TokenValidator<Jwt>`.
- Replace illustrative values with the actual issuer and audience issued by your AS rather than copying them mechanically.

If you need to specify JWKS explicitly (for example, when the AS does not publish standard metadata), you can configure both:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

`jwk-set-uri` must be a trusted address published by the identity provider, not an arbitrary URL read from a JWT. Keeping `issuer-uri` continues enforcing `iss`. How and when metadata/keys are fetched can vary across versions and configurations; verify against your running stack.

### 6.3. Protecting endpoints by scope

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This example depicts endpoints that strictly use bearer tokens without sessions for authentication. For APIs that do not use cookies to authenticate requests automatically, you can consider an appropriate CSRF setup; never disable CSRF unconditionally if the application also serves web sessions or cookie-based browser flows.

For a JWT with the claim:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security by default converts scopes into authorities prefixed with `SCOPE_`, namely `SCOPE_orders.read` and `SCOPE_orders.write`. Therefore, the configuration above does not directly write `hasAuthority("orders.read")`.

**Note:** `roles`, `groups`, or custom permission claims from an IdP do not automatically become `ROLE_ADMIN`. If custom mapping is needed, configure a corresponding `JwtAuthenticationConverter` and establish explicit policies.

### 6.4. Reading the authenticated principal

In the JWT branch, you can retrieve the principal with `@AuthenticationPrincipal Jwt`:

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/me")
public class MeController {

    @GetMapping
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        );
    }
}
~~~

This snippet assumes the token has been authenticated and `iss` exists per contract. Return only the fields needed by the client; avoid returning all claims or raw tokens in API responses. With opaque tokens, the principal has a different type (see the next section), so do not reuse the exact JWT controller example across both modes.

## 7. Configuring a Resource Server with opaque tokens

### 7.1. Specifying the introspection endpoint and credentials

With the same Resource Server starter, configure introspection as follows:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

This is an **alternative configuration** replacing the JWT configuration in the previous example, which can live in a separate profile; do not mix the two mechanisms merely by declaring both property groups simultaneously without clearly defining the `SecurityFilterChain`.

- `introspection-uri`: actual AS endpoint per IdP documentation.
- `client-id` and `client-secret`: identifier/secret used by the RS to authenticate when calling introspection; **distinct from the API caller's bearer token**.
- Supply secrets via a secret manager or environment variables; never commit credentials to the repository.
- RS ↔ AS communication must use HTTPS with certificate verification.

### 7.2. SecurityFilterChain for introspection

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this mode, Spring Security uses `OpaqueTokenIntrospector` to validate the token. When the AS returns `active: true` and a valid list of scopes, Spring by default maps scopes to authorities prefixed with `SCOPE_`. Thus the `hasAuthority` rules above can stay identical to the JWT branch.

An introspection response with `active: true` but lacking the `orders.write` scope still lacks sufficient permission for `POST /api/orders`.

### 7.3. Reading the principal from introspection

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/me")
public class MeController {

    @GetMapping
    public Map<String, Object> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("subject", principal.getName());
    }
}
~~~

With opaque tokens, `Authentication#getPrincipal()` defaults to `OAuth2AuthenticatedPrincipal`; the subject name is typically taken from `sub` if returned by the AS. If the AS contract does not include `sub`, agree on how identity is determined, and never assume this name is an email or username.

### 7.4. JWTs can also be introspected

Suppose the AS issues JWT-formatted access tokens, yet business requirements demand blocking a token immediately when a device is reported stolen. If the AS supports introspection for JWTs, the Resource Server can still configure the `opaqueToken` branch to **send the raw JWT string to the introspection endpoint**.

In that case, **JWT is the token format; introspection is the verification method**. Spring Security will use the introspection result as the source of authentication details instead of decoding the JWT locally into a `Jwt` principal. Verify whether the AS supports this and returns sufficient attributes for the API's authorization policies.

## 8. Choosing a verification strategy based on system requirements

There is no single best choice for every Resource Server. You can decide using the following questions.

### Question 1: How fast does token revocation need to take effect?

If the requirement is **near-immediate access revocation** (locked users, potentially compromised sessions, withdrawn financial privileges), introspection is the right direction if supported by the AS and permitted by performance constraints. Introspection caching, if enabled, needs a TTL aligned with the acceptable revocation window.

If the API can tolerate tokens expiring after a short interval, JWTs with a **short TTL** and tightly scoped permissions can be a simpler choice. Client-side logout only deletes the token on the client; it does not automatically invalidate circulating JWTs at the Resource Server.

### Question 2: Are latency and request throughput strict?

For high-traffic, multi-instance APIs requiring low latency, verifying JWTs with cached keys typically saves one network round-trip per request. You must still account for key rotation lifecycles and fetching fresh JWKS.

Introspection places additional load on the AS or a dedicated introspection tier. If choosing this option, design appropriate timeouts, connection pools, quotas, caching, error monitoring, and AS capacity. Never **fail open** automatically (allowing requests when the AS is unreachable), as that turns a connectivity outage into an authentication bypass vulnerability.

### Question 3: Do claims and permissions change frequently?

Self-contained JWT claims let the RS decide quickly, yet permissions baked into a JWT can become stale. For dynamic permissions, you can:

- Use introspection so the AS returns status/permissions reflecting updated policies.
- Use short-lived JWTs so clients obtain fresh access tokens when needed.
- Keep JWTs for authentication, then query a dedicated authorization service for sensitive decisions.
- Design tokens to carry only coarse identifiers/scopes, while resource ownership is checked inside the API.

Do not confuse the `orders.read` scope with permission to read **every** order. The Resource Server usually must also check whether the order belongs to the right user/tenant.

### Question 4: Can the API tolerate per-request dependency on the Authorization Server?

If requests must continue being served when network connectivity to the AS is disrupted, JWTs can allow the RS to verify already-issued tokens using cached keys. However, this does not eliminate the need to design key refresh, token lifetimes, token compromise handling, and fallback behavior when keys cannot be fetched.

If security requirements prioritize up-to-date central state, rejecting requests when tokens cannot be introspected may be acceptable. Surface AS failure modes clearly in monitoring instead of lumping every outage under "invalid token."

### Quick selection table by scenario

| Scenario | Starting option to consider | Why |
|---|---|---|
| Authenticated public-facing read API, high traffic, short-lived tokens | Locally verified JWT | Reduces network dependency during processing |
| API involving sensitive privileges needing near-instant revocation | Introspection | Status is determined by the AS at call time |
| Internal microservices trusting the same issuer, each with its own audience | JWT + `iss`, `aud`, scope verification | Fits distributed verification, prevents misdirected tokens |
| Partner API using reference tokens issued by an IdP | Opaque + introspection | RS does not need to understand token internals |
| JWTs that must undergo per-request revocation checks | Introspection for JWTs | JWT format does not prevent centralized status checking |
| High traffic **and** fast revocation needed | Controlled hybrid design | Balances short TTL, cache/denylist, or sensitive-path checks as needed |

**Practical approach:** start from the AS's access token contract, revocation requirements, and API SLAs; only then pick `jwt()` or `opaqueToken()`.

## 9. Things to validate beyond signature or `active`

### 9.1. Audience must match the target Resource Server

Suppose the same issuer mints tokens for `inventory-api` and `orders-api`. A token with `aud: ["inventory-api"]` must never automatically work on `orders-api`, even when `iss` matches and the signature is valid.

With JWTs, add an audience validator. In Spring Boot versions supporting `audiences`, you can configure it directly as in Section 6.2.

With introspection, if the response includes `aud`, the API should enforce audience conditions per the AS contract. Never assume the default introspector's `active` check automatically enforces all project-specific audience/tenant policies. When needed, wrap `OpaqueTokenIntrospector` with additional validation logic or configure an appropriate authentication converter/authorization policy.

### 9.2. Do not confuse scope with role, or role with data ownership

- `scope` such as `orders.read` is typically an API permission granted to the client/token.
- `role` such as `ADMIN` may represent an organizational or application permission model.
- **Data ownership** is a condition on a specific resource—for example, customer A may read order A but not order B.

These layers can coexist. A token carrying `SCOPE_orders.read` is not enough to query someone else's order.

### 9.3. Prevent bearer token leakage

Bearer tokens operate on the principle that anyone holding a valid token can use it, unless additional token-sender binding is enforced. Therefore:

- Mandate TLS from client to API and from API to introspection/JWKS endpoints.
- Never write raw bearer tokens into logs, exceptions, traces, analytics, or URL query parameters.
- Keep access token lifetimes proportional to risk; restrict scopes and audiences.
- Protect refresh tokens and introspection client secrets according to their respective roles.
- If using sender-constrained token mechanisms such as mTLS/DPoP, implement the corresponding verification; a plain Bearer header does not enforce that binding on its own.

### 9.4. Signing keys, caching, and clock skew

For JWTs, operational planning must account for:

- **Key rotation**: the AS may publish new keys before using them to sign; the RS must update JWKS while still handling older unexpired tokens during the transition window.
- **JWKS caching**: caching reduces load but requires a refresh strategy and handling of unknown `kid` values.
- **Clock skew**: servers with drifted clocks may reject tokens near `nbf`/`exp`; synchronize clocks and allow only small, intentional tolerances.
- **Allowed algorithms**: allow only trusted algorithms matching the AS; never let token headers downgrade security standards.

For introspection, response caching must explicitly define **how long an active status may be trusted**. Never cache past `exp`; also consider revocation limits and dynamic permissions.

## 10. Reading HTTP outcomes to isolate failures

Suppose an API specifies that `GET /api/orders` requires `SCOPE_orders.read`.

| Request | Expected | Where to check |
|---|---|---|
| No `Authorization` header sent | Typically 401 | Whether client sent a bearer token |
| Malformed JWT, bad signature, expired, wrong issuer/audience | Typically 401 | Decoder, validators, JWKS, clock |
| Opaque token introspection returns `active: false` | Typically 401 | Token status at the AS |
| Valid token, missing `orders.read` | Typically 403 | Scope mapping and authorization rules |
| Valid token, right scope, does not own resource | 403 or 404 per API policy | Data-level permission checks |
| Introspection timeout or AS error | Depends on exception config/mapping | Connectivity, TLS, credentials, timeouts, and AS health |

Example API call with `curl`:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

When debugging, distinguish between:

1. **Token authentication failure:** expired token, wrong issuer/audience, stale JWKS keys, AS introspection reporting inactive.
2. **Authenticated but insufficient permissions:** missing scope, authority mapping mismatching convention, rule applied to the wrong endpoint.
3. **External dependency failure:** JWKS/introspection unreachable, DNS/TLS error, wrong secret, or overloaded AS.

The `WWW-Authenticate` response header can carry standardized bearer error details, yet must never disclose internal data or raw tokens in error messages.

## 11. Architectural decision example for an ordering system

Suppose a company has:

- `orders-api` for the shopping application;
- `billing-api` handling payments;
- a single IdP issuing access tokens for both;
- a requirement to disable compromised accounts immediately for payment operations.

One possible design is:

1. **Define distinct audiences** `orders-api` and `billing-api` so the two APIs cannot mistakenly accept each other's tokens.
2. `orders-api` uses **short-lived JWTs** verified locally against the proper issuer, audience, timestamps, and scopes.
3. `billing-api` uses **introspection** for sensitive operations, with explicit timeout policies and AS dependency monitoring. The AS must genuinely reflect revocation as quickly as required.
4. Both APIs enforce **per-resource permissions**: customers only operate on orders/invoices they are authorized to access.
5. Even if the AS issues JWTs for both, `billing-api` can still introspect JWTs if the IdP supports it. There is no need to force the AS to issue opaque strings just to use introspection.

The deciding factor is **each API's security and operational goals**, not forcing the entire system to use a single token format.

## 12. Misconceptions to avoid

**"Once a JWT's signature is verified, it can call any API."** False. You must verify issuer, audience, and relevant claims, then enforce endpoint and data permissions.

**"Opaque tokens have no signature, so they are less secure."** Incorrect. Opaque tokens typically rely on unguessable values and AS status confirmation over a trusted channel; evaluate the mechanism end-to-end.

**"JWTs cannot be revoked."** Inaccurate. JWTs can be rejected via introspection, denylists, or other policies. **Local signature verification alone** simply does not learn about revocation events occurring after issuance.

**"JWTs only work with OAuth, and opaque tokens only work with OIDC."** Incorrect. OAuth 2.0 does not mandate JWT access tokens; OIDC adds identity concepts such as ID tokens. Access token format depends on the Authorization Server and system contract.

**"Introspection always checks all access permissions."** Incorrect. `active: true` only establishes token status according to the AS; the Resource Server remains responsible for enforcing audience, scope, and resource conditions.

**"If the AS fails, accept requests anyway to boost availability."** Unsafe. Any degradation strategy must be designed upfront within trust boundaries—never silently bypass authentication when introspection fails.

## 13. Standards and references

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Boot — OAuth2 Resource Server configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

When implementing in a real system, cross-check both your Spring Security/Spring Boot version and your Authorization Server's documentation: metadata endpoints, JWKS, `scope` formatting, audience handling, revocation behavior, and introspection contracts can vary across providers.
