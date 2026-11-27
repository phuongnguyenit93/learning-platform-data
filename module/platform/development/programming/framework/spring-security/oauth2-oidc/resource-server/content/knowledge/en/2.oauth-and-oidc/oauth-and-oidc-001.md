# OAuth 2.0 Delegates Access and OIDC Adds the Identity Layer

## 1. The problem: being permitted to access is different from knowing who the user is

Suppose a retail application has a web frontend and a Spring Boot API:

- Users log in through the browser.
- The frontend calls `GET /api/orders` to read orders.
- The API only allows access when the request carries the `orders.read` permission.
- The frontend needs to know which user is logged in to display their name, email, or profile.

These two needs are related but distinct:

- **OAuth 2.0** provides an **authorization** model: an application (client) receives permission to access protected resources via an **access token**. Access is scoped by the token's intended recipient, permission scopes, lifetime, and Authorization Server policies.
- **OpenID Connect (OIDC)** builds an **identity authentication layer** on top of OAuth 2.0: the client can receive a standardized **ID Token** to learn the user's authentication outcome, along with ways to fetch profile information such as the **UserInfo Endpoint**.

> Core takeaway: **OAuth 2.0 answers "what is the client allowed to do with the resource?"; OIDC helps the client answer "who is the user that just authenticated?"** In a real system, both can appear within the same login flow.

In the context of **Spring Security OAuth 2.0 / OIDC Resource Server**, the Spring Boot API typically acts as the **Resource Server**: it receives the access token, validates it, and enforces access control. The Resource Server **does not need to receive or use an ID Token to protect the API**.

## 2. OAuth 2.0 is an access delegation mechanism

### 2.1. Four fundamental roles

| Role | Responsibility | Example |
|---|---|---|
| **Resource Owner** | Entity that owns or controls access to the resource | Owner of the order list |
| **Client** | Application requesting access to the resource | Web frontend, mobile app, backend-for-frontend |
| **Authorization Server (AS)** | Authenticates according to policy, issues authorization codes/access tokens | Identity or authorization server |
| **Resource Server (RS)** | Hosts APIs/resources, receives and validates access tokens | Spring Boot `/api/orders` |

The **Authorization Server** and **Resource Server** can be two separate applications. An Identity Provider (IdP) can simultaneously serve as the OAuth 2.0 Authorization Server and the OIDC **OpenID Provider (OP)**.

An **access token** is an authorization credential for calling a Resource Server. It may be a JWT or an opaque string (without a client-decodable structure). OAuth 2.0 does not require access tokens to be JWTs and does not specify that clients should infer user identity by reading access token contents.

### 2.2. Scope, audience, and lifetime

For example, an Authorization Server issues an access token with these logical attributes:

- `scope = orders.read`: allowed to read orders; `orders.write`: allowed to write orders.
- `aud = orders-api`: token intended for the orders API.
- `exp`: expiration timestamp.
- `iss`: token issuer.
- `sub`: subject of the token (may be a user or a client depending on the grant type).

**Scope** describes granted permissions at a coarse level; **audience** binds the token to its intended recipient resource. The API must both validate the token and enforce access decisions per endpoint and, when needed, per business record. Having `orders.read` does not automatically mean a user can view *everyone else's* orders.

**Example requiring additional business-layer checks:** a token has `orders.read`, yet the API must only return orders belonging to the corresponding `sub`, unless a specific administrative permission is present.

### 2.3. OAuth 2.0 does not always involve an interactive user

With **Authorization Code + PKCE**, a user usually participates in logging in and granting consent. However, with **Client Credentials**, a backend service can obtain an access token to call another service without any logged-in user.

Therefore, "having a valid access token" **is not enough to conclude that a human user just logged in**. This is why authorization and identity authentication must be distinguished.

## 3. OIDC adds identity to the OAuth 2.0 flow

### 3.1. The `openid` scope and ID Token

When a client requests the `openid` scope, an OIDC-compliant flow allows the client to receive an **ID Token** following the OIDC specification. An ID Token is typically a signed JWT with key claims:

| Claim | Meaning when the client validates the ID Token |
|---|---|
| `iss` | Which OpenID Provider issued it |
| `sub` | Subject identifier within the issuer's namespace |
| `aud` | Client ID permitted to receive the ID Token |
| `exp` | Expiration time |
| `iat` | Issued-at time |
| `nonce` | Value originally sent by the client (when used), binding the token to the authentication request |
| `auth_time` | Time when the user authenticated, when requested/provided |
| `email`, `name` | Optional profile claims, not a replacement for the `sub` identifier |

The client must validate the ID Token according to OIDC, including **signature**, **issuer**, **audience**, **expiration**, and **nonce if a nonce was sent**. Some scenarios require additional `azp` checks and flow-specific rules. Rely on a trusted OIDC library to perform these validations rather than manually checking a few JSON fields.

> **Do not send an ID Token as a Bearer token to call an API.** An ID Token proves an authentication outcome **to the client listed in `aud`**; it is not an authorization credential for API resources. An ID Token with `aud = web-client` must not be accepted by the `orders-api` just because its signature is valid.

### 3.2. UserInfo and profile scopes

OIDC defines the **UserInfo Endpoint** so clients can use an appropriate access token to retrieve profile claims. Common scopes include:

- `openid`: enables OIDC semantics.
- `profile`: requests profile claims such as name and avatar picture.
- `email`: requests `email` and `email_verified`.
- `address`, `phone`: other optional claim groups.

These scopes are **not equivalent** to business API permissions like `orders.read`. The provider also decides which claims are actually returned based on configuration and user consent.

`sub` combined with `iss` is generally a more reliable identifier key than email. Emails can change, remain unverified, or be reused; `sub` may also be *pairwise* (different per client/sector) depending on provider policy.

### 3.3. Discovery and standardization

OIDC supports metadata at an endpoint of the form:

~~~text
https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

The exact path depends on the IdP's issuer structure. Metadata describes endpoints such as `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, and `jwks_uri`. JWKS provides the public keys applications use to verify asymmetrically signed JWTs.

Spring Security Resource Server can use the **issuer URI** to locate the appropriate metadata/JWKS. This does not turn the API into an OIDC client; the API still uses access tokens for access control.

## 4. One login, two distinct purposes

A common flow for web applications is the **Authorization Code Flow with PKCE**. Assume the Authorization Server supports OIDC and issues access tokens for `orders-api`.

~~~mermaid
sequenceDiagram
    actor User as User
    participant Client as Web / BFF (OIDC Client)
    participant OP as Authorization Server / OP
    participant API as Spring Resource Server
    User->>Client: Choose to log in
    Client->>OP: /authorize: response_type=code, scope=openid orders.read, state, code_challenge, nonce
    OP->>User: Authenticate and request consent (if needed)
    User-->>OP: Complete
    OP-->>Client: Redirect with code and state
    Client->>Client: Verify state
    Client->>OP: /token: code, redirect_uri, code_verifier (+ client authentication if required)
    OP-->>Client: access_token and id_token (possibly refresh_token)
    Client->>Client: Validate ID Token to confirm user identity
    Client->>API: GET /api/orders + Bearer access_token
    API->>API: Verify signature/expiry/issuer/audience/scope
    API-->>Client: 200 if allowed; 401/403 otherwise
~~~

**Key steps to understand:**

1. The client generates `state` to prevent authorization request forgery; generates `code_verifier` and `code_challenge` for PKCE; with OIDC, it can generate `nonce` and verify it in the ID Token.
2. The browser goes through the Authorization Server's login page, avoiding having the application collect passwords directly.
3. The Authorization Server returns an **authorization code** via redirect. The code is short-lived, single-use, and exchanged at the token endpoint.
4. The client receives an **ID Token** to verify identity within the client scope and an **access token** to call the API.
5. The Spring Resource Server only uses the access token when making access decisions for `/api/orders`.

If the application is a **BFF/confidential client**, the backend holds the tokens and can perform client authentication when exchanging the code. If it is a **SPA/public client**, do not place a client secret in JavaScript; use PKCE and appropriate token protection measures. Choose the architecture and token lifecycle based on the actual threat model.

## 5. Distinguishing token types

| Credential | Primary consumer | Purpose | Sent where? |
|---|---|---|---|
| **Authorization code** | OAuth/OIDC client | Exchanged for tokens, usually combined with PKCE | Authorization Server's token endpoint |
| **Access token** | Resource Server | Proves permission to call a specific resource | `Authorization: Bearer ...` when calling an API |
| **ID Token** | OIDC client / Relying Party | Verifies authenticated user identity | Client; **never used as an API token** |
| **Refresh token** | Client eligible under issuance policy | Obtains new access tokens when permitted | Token endpoint; protect and rotate per policy |

The two *illustrative* JWT payloads below intentionally have **different audiences**. These show only the claims for learning purposes, not real signed tokens:

**Access token for the Resource Server:**

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000000
}
~~~

**ID Token for the web client:**

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": "web-client",
  "email": "user@example.test",
  "email_verified": true,
  "nonce": "client-generated-nonce",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

JWTs are typically only **Base64URL-encoded and signed**, **not encrypted by default**. Therefore, never put passwords, private keys, or unnecessary sensitive data into claims. Do not accept weak or disallowed signing algorithms; verify signatures using keys and algorithms that match your trust policy.

## 6. How does Spring Security Resource Server process access tokens?

### 6.1. Preparing the application

This Spring Boot example uses Spring Security and validates **JWT access tokens**. Add the corresponding starters to `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

If using Maven, use the two equivalent artifacts for `spring-boot-starter-web` and `spring-boot-starter-oauth2-resource-server`; versions are managed by the Spring Boot BOM.

Minimal `application.yml` configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

`issuer-uri` must match the exact `iss` claim value on the token. Depending on the provider and how the application starts, Spring uses the issuer's metadata to find the JWKS and verify JWTs. This is an illustrative URI; in production, replace it with your identity system's issuer.

**The Resource Server must be configured to accept only valid access tokens meant for this API.** Beyond signature, expiration, and issuer, you should validate **audience = orders-api** and any token constraints applicable to your system. If the access token is **opaque**, use introspection (`oauth2ResourceServer(...opaqueToken(...))`) instead of configuring a JWT decoder.

### 6.2. SecurityFilterChain: protecting endpoints by scope

Create `SecurityConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            // Only applies to stateless APIs authenticating via Bearer tokens,
            // not relying on browser cookies/sessions.
            .csrf(csrf -> csrf.disable())
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

When a valid JWT contains `orders.read` in its `scope` claim, Spring Security maps that scope by default to the `SCOPE_orders.read` authority (and similarly for supported `scp` claim formats). That is why we use `hasAuthority("SCOPE_orders.read")` rather than comparing usernames or putting `openid` into business authorization rules.

**Note on CSRF:** disabling CSRF in this example is only appropriate when the API truly authenticates via non-cookie Bearer tokens and does not use browser session-based authentication. If the system uses login cookies or browser session endpoints, appropriate CSRF protection must be configured. CORS must also be configured separately for allowed frontend origins; CORS does not replace authentication and authorization.

### 6.3. Reading the authenticated subject in a controller

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping
    public Map<String, String> myOrders(@AuthenticationPrincipal Jwt jwt) {
        // Illustrative example: you must also enforce per-order permissions
        // and filter data by the actual user.
        return Map.of("authenticatedSubject", jwt.getSubject());
    }
}
~~~

With JWTs, `jwt.getSubject()` reads the `sub` claim of the access token. It is **not an ID Token**; the controller is reading the principal authenticated by the Resource Server filter. Returning data filtered by `sub` is only one step of object-level authorization; multi-tenant systems also need tenant and ownership checks.

### 6.4. Validating audience with a validator

An access token with a valid signature issued by the **same issuer** but intended for a different API should still be rejected by `orders-api`. For example, configure `jwk-set-uri` and the expected audience:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    audience: orders-api
~~~

The JWKS path above is an **example following one common IdP endpoint pattern**, not a universal rule. Retrieve the actual `jwks_uri` from your provider's metadata. Specifying `jwk-set-uri` directly also lets the application configure the public key location explicitly.

Create `JwtValidationConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment env) {
        String issuer = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String jwkSetUri = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri");
        String expectedAudience = env.getRequiredProperty(
            "app.security.audience");

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndLifetime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Invalid audience", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndLifetime, audience));
        return decoder;
    }
}
~~~

This validator adds the `aud` check while preserving the default issuer and timestamp validations from `JwtValidators.createDefaultWithIssuer`. Production systems must also control allowed signing algorithms, handle key rotation, account for how the issuer mints tokens, and enforce other IdP-specific policies. **If you define a custom `JwtDecoder` bean, make sure to retain all validations previously provided by auto-configuration.**

If your provider uses a permission claim other than `scope`/`scp` (for instance, a custom roles array), configure a `JwtAuthenticationConverter` tailored to your provider's format; do not assume every role is a scope. Also, never treat `email` or `preferred_username` as an authorization grant.

## 7. OIDC Login and Resource Server in Spring Security are two separate roles

Spring Security has mechanisms that are easily confused because they all start with "OAuth2":

| Spring Security mechanism | Role the application plays | Primary function |
|---|---|---|
| `oauth2Login()` | OAuth 2.0/OIDC **Client** | Redirects users to the provider, receives the code, exchanges it for tokens, establishes a login session |
| `oauth2Client()` | OAuth **Client** | Manages authorized clients/access tokens for calling other services |
| `oauth2ResourceServer().jwt()` | **Resource Server** | Accepts Bearer access tokens and validates JWTs to protect APIs |
| `oauth2ResourceServer().opaqueToken()` | **Resource Server** | Verifies opaque access tokens via introspection |

An application can be both a client and a resource server, but **each flow** must be configured deliberately. For example:

- **Frontend/BFF:** performs OIDC login to identify the user and holds sessions or tokens according to the architecture.
- **Orders API:** only needs Resource Server functionality to validate Bearer access tokens and enforce `orders.read`.
- **Authorization Server/IdP:** authenticates users, issues ID Tokens to the client, and issues access tokens for the Orders API.

Enabling `oauth2ResourceServer().jwt()` **does not automatically produce an OIDC login page** and does not issue tokens. Conversely, having a login session from `oauth2Login()` does not mean the API is configured to accept Bearer JWTs from external clients.

## 8. Testing access scenarios

Once the Authorization Server issues a **real access token** with the appropriate audience and scope, you can call the API:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Do not use an ID Token in place of `<ACCESS_TOKEN>`. Never commit real tokens to source code, public documentation, or logs; when testing commands, store and handle tokens like temporary login secrets.

Expected outcomes under the example configuration:

| Scenario | Typical result | Reason |
|---|---|---|
| No Bearer token | **401 Unauthorized** | No valid authentication credentials provided |
| Expired token, invalid signature/issuer, or wrong audience | **401 Unauthorized** | Access token is rejected |
| Valid access token, missing `orders.read` on GET | **403 Forbidden** | Authenticated, but insufficient permissions |
| Valid access token with `orders.read` on GET | **200 OK** | Passes endpoint security; still subject to business-logic checks |
| ID Token sent as Bearer instead of access token | **Must be rejected** | Wrong token purpose, typically wrong audience/token type |
| JWT issued by a different issuer | **401 Unauthorized** | Not from a trusted issuer |

These HTTP statuses reflect the expected behavior of the sample configuration; applications may also return errors from other filters, gateways, or business checks.

### Common architectural mistakes

1. **Using OAuth 2.0 for "login" without OIDC:** the client reads user ID/email from the access token and treats it as a standard identity. Claims inside access tokens are not standardized by OAuth 2.0 like ID Tokens; for interoperable login authentication, use OIDC.
2. **Sending an ID Token to an API:** ID Tokens are meant for clients and carry the client ID as `aud`. APIs require access tokens targeted at the API.
3. **Validating only the signature:** a token can have a valid signature yet have the wrong `iss`, wrong `aud`, be expired, or lack required scopes; authentication and authorization are separate layers.
4. **Confusing scope with record ownership:** `orders.read` does not allow bypassing order ownership, tenant isolation, or data access policies.
5. **Embedding a client secret in a SPA/mobile app:** these are public clients and cannot keep secrets embedded in distributed code; use PKCE and appropriate client configuration.
6. **Treating JWTs as encrypted data:** payloads are readable by anyone holding the token string.
7. **Handling refresh tokens like access tokens:** refresh tokens are meant for the token endpoint and must be protected and handled according to the provider's rotation/revocation policies.
8. **Reusing one token across every API without restricting audience:** increases the risk of an API accepting a token issued for somewhere else.

## 9. Takeaways for system design

Start with the question your application is solving:

- **"Should the API allow this call?"** → Resource Server validates the **OAuth 2.0 access token**, expiration, issuer, audience, scope/authority, and object-level permissions.
- **"Who is the user that just logged in?"** → The **OIDC client** validates the **ID Token** and uses `iss` + `sub` as the identifier; fetch additional claims via UserInfo if needed.
- **"Does a backend application need to call another API without a user?"** → OAuth 2.0 **Client Credentials** may fit; do not infer an OIDC login session.

**One sentence connecting to Spring Security:** `oauth2Login` handles the OIDC login experience on the **client** side, while `oauth2ResourceServer` handles **API** access token verification and authorization enforcement. The two mechanisms complement each other, but an ID Token can never replace an access token.

### Standard references

- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750)
- [Proof Key for Code Exchange (PKCE) — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [JWT Profile for OAuth 2.0 Access Tokens — RFC 9068](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
