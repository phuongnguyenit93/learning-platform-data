# Target Recipients and Intended Purpose of Each Token Type in OAuth 2.0 and OpenID Connect

In systems using **OAuth 2.0**, tokens enable an application to obtain permission to access resources. When **OpenID Connect (OIDC)** is added, the application can also authenticate users and receive information about the login session. These tokens may all be returned by the same Authorization Server, yet they **do not share the same intended recipient, do not serve the same purpose, and cannot substitute for one another**.

Three types must be distinguished first:

- **Access token**: intended for the **Resource Server/API**, to decide whether to accept a request to access a resource.
- **ID token**: intended for the **OIDC Client/Relying Party (RP)**, to confirm the result of user authentication.
- **Refresh token**: intended for the **Authorization Server**, so the client can request new access tokens under the granted policy.

A common source of confusion: all three are typically **issued to the client** in the protocol, yet **the systems that consume and process them** are three different places. "Who holds the token?" and "Who is the token meant for?" are two separate questions.

## 1. Placing tokens into their proper OAuth 2.0/OIDC roles

| Role | Responsibility | Relationship to tokens |
|---|---|---|
| **Resource Owner / End User** | Entity owning the data or authenticating user | May be the subject (`sub`) of a token, but is not by default the token's recipient |
| **Client** | Web app, mobile app, backend, or service requesting access | Receives tokens from the Authorization Server and uses each for its intended purpose |
| **Authorization Server (AS)** | Authenticates when needed, grants authorization, and issues tokens | Issues access/refresh tokens; receives refresh tokens at the token endpoint |
| **OpenID Provider (OP)** | Authorization Server supporting OIDC | Additionally issues ID tokens; provides user identity mechanisms |
| **Resource Server (RS)** | API hosting or serving protected resources | Receives, validates **access tokens**, and enforces authorization policies |
| **Relying Party (RP)** | OIDC Client relying on authentication results from the OP | Receives and validates **ID tokens** to establish or update a login session |

A single application can play multiple roles: a backend may act as both an **OIDC Client** when handling login and a **Resource Server** when exposing an API. Roles must be distinguished **per request**; never assume that because it is the same backend, tokens can be used interchangeably.

### "Recipient" can mean three different things

1. **The party issued the token**: typically the client that requested it; the client holds and presents it when needed.
2. **The party consuming the token as proof**: the Resource Server consumes the access token; the RP consumes the ID token; the AS consumes the refresh token.
3. **The entity the token describes**: usually a user in the `sub` claim, or a client/service in certain machine-to-machine flows.

With JWTs, the `aud` (*audience*) claim usually identifies the party the token was issued to serve. The `sub` (*subject*) claim states **who** the token is about, not **where** the token should be sent. The `iss` (*issuer*) claim identifies the issuing party.

## 2. Quick comparison table of the three token types

| Criterion | Access token | ID token | Refresh token |
|---|---|---|---|
| Specification | OAuth 2.0 | OIDC extending OAuth 2.0 | OAuth 2.0 |
| Issued to | Client | OIDC Client / RP | Client permitted to use refresh tokens |
| **Intended consumer** | **Resource Server/API** | **OIDC Client / RP** | **AS at the token endpoint** |
| Purpose | Grants permission to access resources/APIs | Confirms user authentication outcome and identity to the RP | Requests a new access token without repeating interactive consent |
| Typical usage | `Authorization: Bearer ...` when calling an API | RP processes OIDC outcome and establishes a login session | `grant_type=refresh_token` at the token endpoint |
| Format | Can be JWT, opaque, or another format | **JWT** per OIDC | Usually opaque, though format is not mandated |
| Key fields to check | `aud`, permissions/`scope`, validity, issuer, token binding | `iss`, `aud=client_id`, `sub`, `exp`, `iat`, `nonce` when applicable | Binding to client/grant, validity, revocation or rotation state per AS |
| Lifetime | Usually short | Usually short | May be longer, subject to rotation or revocation |
| Sent directly to business APIs? | **Yes**, if the API is the intended recipient | **No** | **No** |
| Handled by Spring Security Resource Server? | **Yes**: JWT validation or opaque-token introspection | **Never used in place of an access token** | **No** |

Actual lifetimes, formats, and whether a refresh token is issued are **identity provider policies**. Do not infer from a token's name that it is always a JWT, always tied to a human user, or guaranteed to be issued in every flow.

## 3. Access token: granting access to resources

### Who receives and uses the access token?

The Authorization Server **issues the access token to the client**. When calling a protected API, the client includes the token in the request; the **Resource Server** receives it, validates the token, and determines whether the request is authorized.

For example, `web-client` wants to read an order:

```http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer ACCESS_TOKEN
```

The `orders-api` must verify at least:

- The token was issued by a **trusted issuer** and is still valid.
- The token **is intended for this API** (e.g., `aud` contains `orders-api`), when the system uses audiences.
- The token carries the **appropriate permission**, such as `orders.read` to read orders.
- If sender-constraining is in use (e.g., DPoP or mTLS), the request satisfies that binding.
- Business rules still permit access to the **specific order**: having `orders.read` does not mean permission to read every user's orders.

An access token conveys **access authorization**. It does not by itself prove a user just logged in interactively. In the `client_credentials` flow, a token may represent an application or service with **no end user**.

### What permissions does an access token represent?

Common fields, depending on the Authorization Server and token profile:

| Field | Meaning |
|---|---|
| `iss` | Who issued the token |
| `aud` | API/resource the token is intended for |
| `sub` | Subject concerned; may be a user or a client/service |
| `exp`, `nbf`, `iat` | Expiration, not-before time, issued-at time |
| `scope` or `scp` | Granted permission scopes |
| `client_id` or equivalent claim | Client to which the token was issued, if provided by the profile/provider |
| `jti` | Token identifier, when provided |

**Scopes do not replace per-resource permission checks.** A token with `orders.read` typically only indicates the allowed operation at the API level; the application must still check whether the caller is allowed to view `orderId=123`.

### JWT access tokens and opaque access tokens

- **JWT access token**: The Resource Server can usually verify the signature and claims locally using the issuer's public keys/JWKS. JWTs consist of Base64URL-encoded segments and are **not encrypted by default**. Do not place sensitive data in a JWT just because it is signed.
- **Opaque access token**: A token string that the API cannot interpret by decoding locally. The Resource Server typically queries the Authorization Server via the **token introspection endpoint** or a custom verification mechanism.
- **JWT is a format; access token is a role.** An access token can be a JWT or opaque; seeing a three-part JWT-like string is not enough to determine the token's purpose.

With bearer tokens, **anyone who obtains a valid token can use it**, within its granted permissions. Therefore, HTTPS, appropriate lifetimes, avoiding logging tokens, and controlled storage are essential. Sender-constrained mechanisms such as DPoP/mTLS change the conditions for using a token, but must be supported consistently by the issuer, client, and API.

## 4. ID token: confirming login outcome for the OIDC Client

### Who receives and uses the ID token?

An ID token is **issued by the OpenID Provider to the OIDC Client/RP** during a compliant OIDC flow. The RP validates the token to determine which subject the OP authenticated and what authentication assertions are made.

For example, `web-client` logs in via an OP:

1. The client initiates an OIDC request, typically with the `openid` scope.
2. The OP authenticates the user and completes the flow.
3. The client receives the ID token according to the flow used and **validates the ID token itself**.
4. The client creates the application's login session, optionally fetching additional details from the UserInfo endpoint.
5. When calling business APIs, the client uses an **access token with the appropriate audience**, never substituting the ID token.

A JWT ID token might carry claims like:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1910000000,
  "iat": 1909996400,
  "nonce": "client-generated-nonce"
}
```

This example only illustrates structure and is not a real token. `aud` is `web-client` because **the ID token is intended for that client**. It is not an authorization grant for `orders-api`.

### What must the RP validate?

Depending on the OIDC flow and how the token is received, the RP must apply the OIDC Core validations, including:

- Signature/algorithm matching the OP's configuration and trusted keys; `iss`, `aud`, `exp`, and `iat` claims.
- `aud` containing the RP's **client_id**; handling `azp` when required by multi-audience conditions.
- `nonce` matching the value originally sent when the OIDC request used a nonce.
- Additional flow-related claims such as `auth_time`, `at_hash`, and `c_hash`, when required by the flow's conditions.

`sub` gives the RP a stable subject identifier **within the issuer's scope**, though `sub` alone without `iss` should not be used as a cross-provider key. `name`, `email`, `picture`, and other profile claims are **not guaranteed to be present** in the ID token.

### Why must an ID token not be used to call APIs?

- **Wrong recipient:** An ID token typically has `aud=client_id`, whereas an access token targets the API's `aud`.
- **Wrong purpose:** An ID token asserts authentication, not an API authorization contract like an access token.
- **Opens confused-deputy / token substitution vulnerabilities:** An API that accepts any valid JWT from the same issuer without checking audience and token type may mistakenly accept an ID token as an access token.

**Successful login** does not equal **permission to read/modify every resource**. If an API needs to know who the user is, the Resource Server obtains the identity from the **validated access token** or an appropriate trusted mechanism, while continuing to enforce access control.

### How do ID tokens and UserInfo differ?

In OIDC, the UserInfo endpoint is a protected resource; the client calls it with an **appropriate access token** to retrieve claims about the user according to scopes and OP policy. The ID token is the authentication proof issued to the RP. Do not assume the ID token always contains full user profile data, nor assume an access token always carries profile claims needed by the UI.

## 5. Refresh token: obtaining a new access token

### Who receives and uses the refresh token?

The Authorization Server **issues a refresh token to the client** if policy and the flow allow it. When the access token expires or is nearing expiration, the client sends the refresh token **back to the Authorization Server's token endpoint**:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN
```

The endpoint and client authentication method depend on the Authorization Server. Confidential clients usually must **authenticate as a client** via their registered method; public clients must not rely on an embedded client secret as confidential.

The AS validates validity, client binding, grant state, and policy before issuing a new access token. The response **may** include a new refresh token; if **refresh-token rotation** is enabled, the client must replace the old token with the new one and comply with the provider's reuse detection rules.

### What are refresh tokens used for—and not used for?

- Used to **maintain the ability to obtain new access tokens** without forcing the user to repeat interactive consent every time a short-lived access token expires.
- **Never send refresh tokens to a Resource Server** and never place them in `Authorization: Bearer` when calling business APIs.
- **Never use a refresh token as proof of login at the RP** and never treat it as a "long-lived access token."
- **Not every flow issues a refresh token.** For example, `client_credentials` typically only obtains access tokens using client credentials. In OIDC, `offline_access` relates to requesting access when the user is no longer present, though issuance still depends on OP conditions and policies.

Because a refresh token can mint multiple access tokens, exposure often has high impact. Apply secure storage tailored to client type, session protection, rotation/revocation, or sender constraints when appropriate; never log tokens or put them in URLs. For browser-based apps, a BFF / secure session cookie architecture helps avoid exposing tokens in JavaScript; if a public client holds refresh tokens directly, follow the AS's security requirements and supported rotation/binding mechanisms.

## 6. Following the complete login and API call flow

Example: a user logs into `web-client`, and then the client reads orders from `orders-api`. The standard flow is **Authorization Code + PKCE**:

```mermaid
sequenceDiagram
    actor U as User
    participant C as OIDC Client / RP
    participant AS as Authorization Server / OP
    participant API as Resource Server: orders-api

    U->>C: Request login
    C->>AS: Authorization request (openid, orders.read, PKCE)
    AS->>U: Authenticate and request consent when needed
    AS-->>C: Authorization code via redirect
    C->>AS: Exchange code + code_verifier at token endpoint
    AS-->>C: access_token + id_token (+ refresh_token if issued)
    Note over C: Validate ID token; establish login session
    C->>API: GET /api/orders/123 with access_token
    Note over API: Verify token, audience, and access permissions
    API-->>C: Order data or 401/403 error
    Note over C,AS: When needed, client sends refresh_token to AS
    C->>AS: grant_type=refresh_token
    AS-->>C: New access token (possibly new refresh token)
```

**An authorization code is not an access token.** The code is a short-lived value the client exchanges at the token endpoint; PKCE uses `code_verifier` to protect that exchange. The code must never be placed in an `Authorization` header to call an API.

### Two illustrative JWT examples showing the `aud` difference

Access token (a JWT if the AS chooses the JWT format):

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1909996400,
  "exp": 1910000000
}
```

ID token, issued in the same OIDC flow:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1909996400,
  "exp": 1910000000,
  "nonce": "client-generated-nonce"
}
```

Both may share `iss`, `sub`, and `exp`, but their **audience and function are completely different**. The JSON payloads above are *illustrative payloads*, not signed tokens, and cannot be used to make real requests. A refresh token, if issued, may simply be an opaque string whose claims cannot be read.

### Not every flow produces all three tokens

| Scenario | Typical tokens | Key point |
|---|---|---|
| OAuth 2.0 API access without OIDC | Access token; sometimes refresh token | No requirement to issue an ID token |
| OIDC login via Authorization Code + PKCE | Access token, ID token; refresh token per policy | RP uses ID token for login; API receives access token |
| Service-to-service communication with `client_credentials` | Access token | No ID token needed to confirm a user; usually no refresh token |
| Client needs to renew access permissions | Refresh token sent to AS, receiving new access token | API still only receives the new access token |

## 7. Applying this in Spring Security OAuth 2.0 Resource Server

In Spring Security, the **Resource Server** protects APIs and accepts **access tokens** from requests. It does not replace `oauth2Login()`/OIDC Client for user login, nor does it use refresh tokens to auto-renew on each API request.

### Case A: API accepts JWT access tokens

With modern Spring Boot and Spring Security, add the `spring-boot-starter-oauth2-resource-server` dependency. Example issuer configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

Setting `issuer-uri` allows Spring Security to discover the issuer's metadata/JWKS and validate JWTs accordingly. **Validating only signature, issuer, and lifetime is not enough to confirm a token belongs to this API**: you must enforce the expected audience (or an equivalent resource-binding mechanism), then check application permissions.

The Java example below demonstrates explicitly validating `aud=orders-api` and `scope=orders.read`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    private static final String ISSUER =
            "https://id.example.com/realms/demo";

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> defaultChecks =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> correctAudience = jwt ->
                jwt.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token is not intended for orders-api",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaultChecks, correctAudience));
        return decoder;
    }
}
```

Key takeaways:

- `JwtDecoder` verifies the signed JWT along with issuer/lifetime conditions through the validator attached to the decoder.
- The `correctAudience` validator rejects JWTs whose `aud` does not include `orders-api`; thus the example ID token with `aud=web-client` cannot pass the API gate.
- Spring Security typically maps scopes from the `scope`/`scp` claim to authorities prefixed with `SCOPE_`; `hasAuthority("SCOPE_orders.read")` checks read permission at the endpoint layer.
- The code above illustrates **protecting one HTTP endpoint**. The application still needs business-layer authorization (e.g., checking whether the order belongs to the caller) and must configure other HTTP methods per actual requirements.

Different systems may use custom claims or token profiles (such as `typ=at+jwt`, `token_use=access`), but **do not assume** these claims are always present across all providers. If your provider standardizes a token-type indicator, validate it according to their contract.

> **Operational note:** If an application declares its own `JwtDecoder` bean, that bean replaces Spring Boot's default configuration. Make sure to preserve all validators for issuer, lifetime, and audience; never replace everything with a validator that only checks scopes.

### Case B: API accepts opaque access tokens

When the Authorization Server issues opaque tokens, configure the Resource Server to introspect tokens per the provider's protocol and parameters:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
```

The API sends the token to the introspection endpoint using its configured credentials. The Authorization Server returns status and metadata per policy, typically including `active`. The Resource Server uses that result to decide validity and permissions; it must still ensure the token **is intended for this API**, verify scopes, and enforce business permissions. Never send ID tokens or refresh tokens through API calls just because the introspection endpoint might respond about them.

### Distinguishing Spring Security roles within a single application

| Component | What does it handle? | Related token |
|---|---|---|
| `oauth2Login()` / OIDC Client | Logs users in via the OP and establishes application authentication | **ID token** and OIDC mechanisms |
| OAuth2 Client support | Calls APIs as a client, managing authorized clients per configuration | **Access token**, possibly using a **refresh token** to obtain new ones |
| `oauth2ResourceServer().jwt()` | Protects APIs receiving bearer JWTs | **JWT access token** |
| `oauth2ResourceServer().opaqueToken()` | Protects APIs receiving opaque bearer tokens via introspection | **Opaque access token** |

A backend acting as both an OIDC Client and a Resource Server must still configure this boundary properly. Never forward an ID token created for the web UI to an API endpoint and treat it as an access token.

## 8. Common misconceptions that cause bugs or vulnerabilities

| Misconception | Consequence | Resolution |
|---|---|---|
| "Any validly signed JWT can call the API" | ID tokens are mistakenly accepted as access tokens | Verify issuer, validity, **audience**, permissions, and token profile when applicable |
| "`sub` is the token's recipient" | Fails to distinguish users from APIs/clients | `sub` is the subject; `aud` is the intended recipient |
| "The ID token has email/roles so use it directly to authorize the API" | Uses login proof in place of an authorization contract | APIs accept **access tokens**, checking appropriate scopes/roles and business permissions |
| "Having an access token proves the user just logged in" | Confuses authorization with interactive authentication | Distinguish OAuth 2.0 from OIDC; inspect the actual flow and claims |
| "Send the refresh token with every API request for convenience" | Increases exposure risk of a credential that mints new tokens | Only send refresh tokens to the **AS token endpoint** |
| "Access tokens are always JWTs" | API tries to decode opaque tokens, or trusts unverified payloads | Configure JWT validation or introspection per the AS contract |
| "Having a scope grants access to every record" | Exposes other users' data | Combine scope checks with ownership, roles, tenant isolation, and object-level authorization |
| "With HTTPS we can log tokens" | Tokens leak into logs, telemetry, or support systems | Never log full tokens; minimize collection, storage, and transmission of tokens |

For API requests, **401 Unauthorized** typically indicates missing or invalid authentication credentials, while **403 Forbidden** typically indicates authenticated but insufficient permissions. Actual classification depends on your security chain and policies, and neither error should ever be "fixed" by swapping an access token for an ID token.

## 9. How to choose a token by purpose

When designing an endpoint or reading a trace, ask in order:

1. **Calling an API to read or modify a resource?** Use an **access token** issued for that API. The Resource Server validates lifetime, audience, scopes, and resource-level permissions.
2. **Client handling an OIDC login?** Receive and validate the **ID token** issued for its own `client_id`; use the result to manage the login session.
3. **Client needing a new access token?** Use the **refresh token** (if issued) at the AS token endpoint, with appropriate client authentication/binding.
4. **Receiving an authorization code, DPoP proof, client assertion, or logout token?** These are protocol artifacts with distinct duties; never substitute them for one of the three core tokens just because they are also strings or JWTs.

Memory diagram:

```text
                Authorization Server / OpenID Provider
                    |          |             |
           access token    ID token     refresh token
                    |          |             |
             Client sends  OIDC Client   Client sends back
                    |      validates     when renewing
                    v          v             v
             Resource      Relying       Authorization
             Server/API     Party          Server
           (permissions)   (login)      (token endpoint)
```

**Core principle:** tokens must be delivered to the **right recipient** and validated according to their **intended issuance purpose**. In a Spring Security Resource Server, data protected by bearer tokens should only be unlocked when an **access token intended for the API** passes both token validation and authorization policies.

### Authoritative references for deeper study

- **RFC 6749 — OAuth 2.0 Authorization Framework**: access tokens, refresh tokens, and grants.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: how to present bearer access tokens when calling resources.
- **OpenID Connect Core 1.0**: ID tokens, OIDC authentication, claims, audience, and validation rules.
- **RFC 7662 — OAuth 2.0 Token Introspection**: checking token metadata/active status.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**: JWT access token profile when adopted by a system.
- **Spring Security Documentation — OAuth 2.0 Resource Server**: protecting APIs with JWT or opaque tokens.
