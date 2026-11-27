# Purpose of Pushed Authorization Requests

> **Chapter: PAR.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module: learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The focus of this lesson is **what problems Pushed Authorization Requests (PAR) solve**, the protocol flow according to **RFC 9126**, and the security value and limitations of PAR in production deployments.

## 1. The problem with authorization requests going through the browser

In the standard Authorization Code Flow, an OAuth2/OIDC Client directs the user to the Authorization Server's authorization endpoint using a URL containing many parameters:

```http
GET /oauth2/authorize?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal
    &scope=openid%20profile%20orders.read
    &state=STATE_RANDOM
    &nonce=NONCE_RANDOM
    &code_challenge=PKCE_CHALLENGE
    &code_challenge_method=S256
Host: login.example.vn
```

This example is **formatted across multiple lines for readability**; an actual request must be a properly encoded single URL. Uppercase values are placeholders and must not be used directly in real environments.

This mechanism is simple and widely supported, but it has three fundamental drawbacks:

1. **Request integrity before server processing:** the parameters reside in the URL forwarded by the browser. HTTPS protects the connection to the authorization endpoint, but on its own it does not prove that every parameter in the URL was created by the **registered client**. Modifications to `scope`, `redirect_uri`, `claims`, or transaction context must be controlled at the AS.
2. **Privacy:** query strings can appear in browser history, reverse proxy/access logs, telemetry, `Referer` headers, or screenshots. Extended parameters such as `claims`, `authorization_details`, and `login_hint` may contain more sensitive information than a standard scope.
3. **URL length limits:** large authorization requests (many claims, rich authorization details, Request Objects) can hit limits imposed by browsers, gateways, WAFs, or proxies.

**PAR (RFC 9126)** addresses these three issues by moving **most authorization request data out of the browser URL** into a direct connection from the client to the Authorization Server. <https://www.rfc-editor.org/rfc/rfc9126.html>

### 1.1. Practical example

Suppose the system has:

- **Authorization Server/OpenID Provider:** `https://login.example.vn`.
- **Confidential client:** `portal-web` running at `https://portal.example.vn`.
- **Callback:** `https://portal.example.vn/login/oauth2/code/portal`.
- **Resource Server:** `https://api.example.vn` with scope `orders.read`.
- **Requested authorization data:** `openid profile orders.read`, `state`, `nonce`, and PKCE S256.

In the standard flow, all those parameters are in the URL when authentication begins. With PAR, the `portal-web` backend **POSTs the parameter set directly to `/oauth2/par` first**, receives a short-lived reference `request_uri`, and only then redirects the browser to `/oauth2/authorize?client_id=...&request_uri=...`.

As a result, the browser does not need to carry the full initial authorization request content, and the Authorization Server gets an opportunity to authenticate the client and validate input **before user interaction**.

## 2. What PAR is and what it is not

**Pushed Authorization Requests** is a **two-step** mechanism for initiating an authorization request:

1. **Back-channel:** the client sends an HTTP POST to the **Pushed Authorization Request Endpoint** on the AS, containing the authorization request parameters and client authentication credentials according to its registered method.
2. **Front-channel:** the client directs the user agent to the standard authorization endpoint, primarily with `client_id` and the **`request_uri` just issued by the AS**. The AS looks up the pushed request and continues with login/consent/authorization code issuance as usual.

```mermaid
flowchart LR
    Client["OAuth2/OIDC Client<br/>portal-web"] -->|"Direct POST<br/>/oauth2/par + request data"| AS["Authorization Server"]
    AS -->|"201: request_uri + expires_in"| Client
    Client -->|"302 to /oauth2/authorize?<br/>client_id&request_uri"| Browser["Browser"]
    Browser -->|"GET /oauth2/authorize<br/>carries reference only"| AS
    AS -->|"Login / consent, then code + state"| Browser
    Browser -->|"Valid callback"| Client
    Client -->|"POST /oauth2/token<br/>code + code_verifier"| AS
```

| Concept | Meaning |
|---|---|
| **PAR endpoint** | HTTP API that receives the authorization request before redirecting the user; by default in Spring Authorization Server 1.5.x this is `/oauth2/par` when the endpoint is configured |
| **Authorization endpoint** | Endpoint that interacts with the user and proceeds with authorization, defaulting to `/oauth2/authorize` |
| **`request_uri`** | Unpredictable, short-lived reference bound to the exact client and stored request |
| **`expires_in`** | Lifetime in seconds for which the reference is valid; not an access token TTL |
| **OAuth authorization code** | Code issued **after** authorization succeeds, then exchanged for tokens at `/oauth2/token` |
| **ID Token/access token** | Tokens appear only at the appropriate token issuance steps, **not in the PAR response** |

**Key point:** PAR does **not** log the user in by itself, does not issue an authorization code/access token/ID Token, and does not grant consent on its own. A successful `POST /oauth2/par` only means the AS has accepted the **authorization request input** at the preparation stage and returned a reference to continue the flow.

### 2.1. Do not confuse `request_uri` with other URIs/tokens

- PAR's `request_uri` is **not** the client's `redirect_uri`. `redirect_uri` remains the registered callback where the browser returns **after authorization**.
- PAR's `request_uri` is **not** an `authorization_code`, access token, refresh token, ID Token, or client secret.
- A PAR reference like `urn:ietf:params:oauth:request_uri:...` is **not necessarily a URL that can be fetched directly via GET**. That value allows the **Authorization Server itself to look up the request**; the client/user agent does not dereference the URN to retrieve the original data.
- `request_uri` is allowed to appear in the browser URL, but still needs protection against replay, swapping, and unintended logging.

## 3. Comparing the traditional flow and the PAR flow

| Criterion | Direct authorization request | Authorization request using PAR |
|---|---|---|
| Where the client sends request data | URL query via user agent | Direct HTTP POST to AS over HTTPS |
| Browser URL before login | Contains `response_type`, `redirect_uri`, `scope`, `state`, PKCE, and extensions | Usually contains only `client_id` and `request_uri` |
| Client authentication **before login** | Usually no client authentication step at the authorization endpoint | PAR applies token endpoint client authentication rules to the direct request |
| Ability to tamper with parameters in browser URL | Initial parameters are in the front-channel; AS must validate strictly | AS uses the request received over the back-channel, bound to the client |
| Risk of leaking request data via URL | Higher if the request contains sensitive data | Significantly reduced, though it **does not eliminate all leakage** |
| Long requests/rich details | Prone to URL length limits | Large data resides in the POST body; size limits are still needed |
| Infrastructure dependencies | Authorization endpoint | Adds PAR endpoint, persistence/cache, and HTTP client |
| PKCE, `state`, `nonce` | Still required by flow type | **Still required**, not replaced by PAR |
| Login and consent | At the AS | **Unchanged in nature** |
| Token endpoint | Exchange code for tokens | **Same token endpoint**, code must still be verified |

**The greatest benefit of PAR** is that the AS receives **a request with stronger channel-level integrity**, directly from the client (which can be authenticated) before the browser appears. This integrity relies on HTTPS, proper client authentication, and the AS storing/binding the request; **PAR does not create a digital signature over the request payload itself**.

## 4. Full flow according to RFC 9126

### 4.1. Step 1 — Client prepares the request and PKCE

The client creates independent transaction data:

```text
client_id:          portal-web
response_type:      code
redirect_uri:       https://portal.example.vn/login/oauth2/code/portal
scope:              openid profile orders.read
state:              STATE_RANDOM
nonce:              NONCE_RANDOM
code_verifier:      PRIVATE_PKCE_VERIFIER
code_challenge:     BASE64URL(SHA256(code_verifier))
code_challenge_method: S256
```

Keep `code_verifier`, `state`, and `nonce` with the authorization transaction on the client side. **Do not send `code_verifier` in the PAR request**; send only `code_challenge`. Extension parameters such as `resource`, `claims`, or `authorization_details` may be added if supported by both the AS and client.

### 4.2. Step 2 — Client POSTs to the PAR endpoint

For a confidential client registered with the `client_secret_basic` method, an illustrative request is:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_CREDENTIALS_REDACTED
Accept: application/json

client_id=portal-web&response_type=code&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_S256_CHALLENGE&code_challenge_method=S256
```

Notes:

1. The PAR endpoint is an **HTTPS URL** and accepts **POST** with a UTF-8 encoded `application/x-www-form-urlencoded` body per RFC 9126.
2. Client authentication uses the registered method; `Basic ...` is only appropriate for confidential clients using `client_secret_basic`. Mechanisms like `private_key_jwt`/mTLS have their own ways of sending credentials. For public clients, policies on identity, authentication method, and PAR support must be verified against the deployment profile/version.
3. The request body contains **normal authorization request parameters**, except that **the `request_uri` parameter must not be sent in a PAR request**.
4. Do not pass client secrets in URLs, do not leave real tokens/secrets in examples, and do not enable access logs that capture the full POST body on this endpoint.

### 4.3. Step 3 — AS authenticates and performs early validation

RFC 9126 requires the AS to:

- Apply **client authentication** matching how clients authenticate at the token endpoint.
- **Reject** any PAR request containing the `request_uri` parameter.
- Validate the authorization request as if received at the authorization endpoint: for example, `client_id`, `response_type`, `redirect_uri`, and `scope` against the registration, plus PKCE/other policies according to the flow.
- Checks that **require user interaction**, such as login/consent, can be performed later at the authorization endpoint; a PAR POST cannot be treated as having completed them.

Some systems may have special rules for per-transaction redirect URIs of **authenticated clients**, per RFC 9126 §2.4. **Do not relax exact redirect URI matching by default** in Spring Authorization Server; if this exception is truly used, it must have a dedicated profile/policy, validation, and testing. The safe default is that the redirect URI **matches the registration exactly**.

### 4.4. Step 4 — AS returns `request_uri` and `expires_in`

When valid, the RFC requires **HTTP 201 Created** and JSON containing at least:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-cache, no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:PAR_REF_RANDOM",
  "expires_in": 60
}
```

The values above are **illustrative**; the actual URI is generated by the AS and must include an unpredictable cryptographically random component. `expires_in=60` is just an example of 60 seconds; the RFC lets the AS choose the lifetime and suggests a short window such as 5–600 seconds. The AS must **bind the reference to the client** that sent the request. Do not use a predictable sequential counter as the reference.

The client stores `request_uri` in the authorization transaction, uses it **once**, and initiates the browser redirect before it expires.

### 4.5. Step 5 — Browser goes to the authorization endpoint with the reference

```http
GET /oauth2/authorize?client_id=portal-web&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3APAR_REF_RANDOM HTTP/1.1
Host: login.example.vn
```

The AS looks up the stored request, verifies that `request_uri` was issued to `client_id=portal-web`, is still valid, and has not been used contrary to policy. Then:

1. Perform login if there is no session or if policy requires it.
2. Display consent if needed.
3. Enforce validation at the authorization endpoint, especially if client policy has changed since the PAR POST.
4. On success, return the authorization code and `state` to the **redirect URI verified in the original request**.

Do not allow appending `scope=admin`, `redirect_uri=https://evil.test`, or a different `code_challenge` to the browser request to **override** the pushed request. Use only parameters/exceptions actually permitted by the RFC, profile, and server; the safe approach is typically an **immutable permission reference**.

### 4.6. Step 6 — Client verifies the callback and exchanges the code

The client receives the callback:

```http
GET /login/oauth2/code/portal?code=AUTH_CODE&state=STATE_RANDOM HTTP/1.1
Host: portal.example.vn
```

The client must match `state` against the transaction, verify issuer/nonce if OIDC, use the original `code_verifier`, and authenticate the client when exchanging the code via `POST /oauth2/token`. **PAR does not replace Authorization Code, PKCE, single-use codes, or OAuth2/OIDC callback validation**. Access tokens/ID Tokens are received at the code exchange stage, not in the PAR response.

## 5. What risks does PAR help protect against?

### 5.1. Reducing request data exposure in the front-channel

Moving the request payload to the back-channel avoids placing several fields in the URL carried by the browser:

- long and detailed `scope` values;
- OIDC `claims` that may mention requested user information;
- `authorization_details` with transaction details per Rich Authorization Requests (RAR);
- requested `resource`/audience;
- `login_hint` or business context if used by the application;
- large Request Object content when combined with JAR.

**Do not assume that the data is end-to-end encrypted or unobservable on the backend.** The client, PAR endpoint, reverse proxy, WAF, APM, and request storage still process the payload; body logging must be restricted, connections encrypted, read permissions limited, and retention kept short.

### 5.2. Reducing authorization request tampering in the browser

When the client pushes the request over a direct connection and then uses a bound `request_uri`, the browser cannot simply edit `scope`, `redirect_uri`, or `authorization_details` in the URL to alter the stored request at the AS. The AS can also reject invalid scope/redirect requests **before transitioning to login**.

However, an attacker might **steal, guess, or swap `request_uri`**. Therefore:

- The reference must be cryptographically random and unpredictable.
- The reference must be bound to the exact `client_id` and policy.
- The client uses the reference **once**, and the AS should enforce single use (with possible narrow exceptions for browser reloads per the RFC).
- `state`, PKCE, and `nonce` (OIDC) remain essential to defend against **request URI swapping**, CSRF, and transaction mix-ups.

### 5.3. Early client authentication

In the standard Authorization Code Flow, the authorization endpoint typically receives `client_id` without requiring the client to prove possession of a secret/private key. PAR creates a **direct pre-browser communication point** for the AS to authenticate confidential clients using their registered method and verify authorization to submit authorization requests.

This helps block early:

- forged client requests lacking valid credentials;
- redirect URIs or scopes violating policy;
- invalid rich requests;
- unwanted traffic before users go through login/consent.

**Do not confuse client authentication with user authentication.** PAR can run before knowing which user will log in; the server must not treat a user as having approved any scope merely because the PAR request received `201`.

### 5.4. Supporting large authorization requests

PAR uses a POST body instead of a browser URL, which fits requests containing rich context and structured data. Even so, **the server must enforce body size limits, timeouts, and rate limits** to prevent resource abuse. PAR should not be used to store unbounded JSON or large files.

## 6. Comparing PAR, PKCE, JAR, JARM, and OIDC

These technologies protect different parts of the flow:

| Mechanism | Primary problem addressed | Does it replace PAR? |
|---|---|---|
| **PAR — RFC 9126** | Pushes request over back-channel, shortens front-channel, authenticates/validates early | This is the mechanism being studied |
| **PKCE — RFC 7636** | Binds the authorization code to `code_verifier` during token exchange | **No**; used together with PAR |
| **`state`** | Binds the authorization response to the client-side request, protecting against CSRF/transaction mix-up | **No**; should still be included and verified |
| **OIDC `nonce`** | Binds the ID Token to the OIDC authentication request | **No**; still required by the flow |
| **JAR — RFC 9101** | Packages authorization request parameters into a signed and optionally encrypted **JWT Request Object** | Can **combine** JAR + PAR for independent cryptographic guarantees |
| **JARM** | Protects the **authorization response** using a JWT per profile | No; protects the **response** phase, not pushing the request |
| **RAR — RFC 9396** | Expresses richly structured authorization requests via `authorization_details` | No; PAR is a useful channel for carrying RAR |
| **Authorization Code + client auth** | Issues codes and exchanges codes for tokens per the grant | PAR is **not** a new grant type |

### 6.1. PAR does not sign a JWT Request Object by itself

A PAR request can pass **plain form parameters**. With HTTPS and client authentication, the AS has evidence of the receiving channel/sending client and can store an intact request by design. However, if the product requires a **digital signature proof over the request payload itself**, independent verifiability, or non-repudiation, look at **JAR (RFC 9101)** and optionally send the Request Object over PAR.

With JAR + PAR, the `request` parameter containing a signed Request Object can be sent in the PAR POST per a supported profile. When a client must use a signed Request Object, the AS must enforce that policy properly and not fall back to accepting free-form parameters just because the PAR POST was authenticated.

### 6.2. PAR does not eliminate sensitive data at the callback

PAR reduces the amount of **authorization request data** in the browser URL at the **start** of the flow. However, the Authorization Code Flow callback still typically contains `code` and `state`. The client still needs:

- a dedicated callback without embedded third-party scripts/analytics;
- `Referrer-Policy: no-referrer` and `Cache-Control: no-store` where appropriate;
- no logging of sensitive query strings;
- prompt code exchange, PKCE usage, and redirect to a clean URL;
- token/issuer/nonce verification per OAuth2/OIDC.

Do not promote PAR as a solution where "no OAuth data remains in the browser".

## 7. `request_uri` lifecycle, replay, and consistency

RFC 9126 requires a `request_uri` with an **unpredictable** reference **bound to the proper client**; the client **MUST** use it only once. The AS **SHOULD** process it once, optionally allowing certain page reload cases per policy; it **MUST reject expired references**.

An illustrative server-side record might look like:

```text
PushedAuthorizationRequest {
  requestUri:   "urn:ietf:params:oauth:request_uri:PAR_REF_RANDOM"
  clientId:     "portal-web"
  redirectUri:  "https://portal.example.vn/login/oauth2/code/portal"
  scopes:       ["openid", "profile", "orders.read"]
  state:        "STATE_RANDOM"
  nonce:        "NONCE_RANDOM"
  codeChallenge:"PKCE_CHALLENGE"
  method:       "S256"
  issuedAt:     "2026-11-16T10:00:00Z"
  expiresAt:    "2026-11-16T10:01:00Z"
  consumed:     false
  policyVersion:42
}
```

This is a **conceptual model**, not an official Spring schema or API. In production, you need:

1. **TTL and cleanup:** purge expired requests rather than retaining them indefinitely; limit the number of unused PAR requests per client.
2. **Client binding:** when the browser sends `client_id` and `request_uri`, never allow client A to use a reference created for client B.
3. **Replay prevention:** consume references using an appropriate mechanism, preferring atomicity across multiple pods; any browser reload exception must be narrowly designed.
4. **Do not trust modified front-channel parameters:** additional parameters must not silently alter pushed scopes/callback.
5. **Revalidate policy when needed:** if a redirect URI, scope, or client credential is revoked between push and authorize, the AS must apply current rules or reject, rather than treating the POST step as a "permanent approval".
6. **Protect storage:** PAR contents can hold claims or sensitive business data, requiring least-privilege read access, short retention, and no verbatim logging.
7. **Consistency at scale:** every AS pod handling `/oauth2/authorize` must be able to retrieve requests pushed on another pod, or the system must use consistent shared storage/access.

### 7.1. Common attacks and incidents

| Attack/Incident | Risk | Defense mechanism |
|---|---|---|
| Guess `request_uri` | Accessing or abusing someone else's request | CSPRNG reference, high entropy, short TTL |
| URI swapping | Replacing `request_uri` to switch the user to another request | Client state/PKCE/nonce, client binding, transaction validation |
| URI replay | Reusing a reference after the user has authorized | One-time/controlled replay policy |
| Cross-client reference | Client B uses A's reference | Server-side `client_id` binding |
| Open redirect | Steering authorization code to an attacker origin | Validate redirect URI and policy, reject arbitrary URIs |
| Client policy changed | Old request still carries a revoked scope/redirect | Check policy at the authorize step if needed, reject |
| Body/log leakage | Sensitive data exposed via proxy/APM | HTTPS, do not log bodies, minimize retention |
| PAR endpoint DoS | Client pushes many large requests without using them | Rate limiting, body-size bound, TTL, quota |
| Lost PAR response | Client did not receive `request_uri` | Do not redirect browser to a fabricated URL; recreate a safe transaction per policy |

## 8. Metadata: where does the client find the PAR endpoint?

Per RFC 9126, an Authorization Server can advertise PAR capability in **OAuth 2.0 Authorization Server Metadata** (RFC 8414), for example:

```http
GET /.well-known/oauth-authorization-server HTTP/1.1
Host: login.example.vn
Accept: application/json
```

Example metadata structure (abbreviated):

```json
{
  "issuer": "https://login.example.vn",
  "authorization_endpoint": "https://login.example.vn/oauth2/authorize",
  "token_endpoint": "https://login.example.vn/oauth2/token",
  "pushed_authorization_request_endpoint": "https://login.example.vn/oauth2/par",
  "require_pushed_authorization_requests": false
}
```

| Metadata field | Meaning |
|---|---|
| `pushed_authorization_request_endpoint` | Endpoint URL for clients to POST requests directly; its presence indicates the server **may support** PAR |
| `require_pushed_authorization_requests` | If `true`, the AS requires authorization requests to go through PAR under a server-wide policy |
| **Per-client** metadata of the same name | An individual client can be required to use PAR even when not enforced server-wide |

**Note:** The JSON above is **illustrative**. Do not assert that a running instance supports PAR merely because you saw the path in Spring docs or a configuration field in code. Inspect the **actual metadata**, supported methods, and test a PAR POST. If the AS requires PAR, requests to the authorization endpoint **without a PAR-issued `request_uri`** must be rejected with `invalid_request` per RFC 9126.

For OIDC, clients can read the Provider Configuration at `/.well-known/openid-configuration` if the OP supports OIDC; still verify the issuer and advertised endpoints. Do not assume both discovery documents share identical fields across all products/versions.

## 9. How does Spring Authorization Server support PAR?

Spring Authorization Server 1.5.x supports the **RFC 9126** protocol via:

- `OAuth2AuthorizationServerConfigurer.pushedAuthorizationRequestEndpoint(...)`;
- `OAuth2PushedAuthorizationRequestEndpointConfigurer`;
- `OAuth2PushedAuthorizationRequestEndpointFilter`;
- `OAuth2PushedAuthorizationRequestAuthenticationProvider`;
- `AuthorizationServerSettings.Builder.pushedAuthorizationRequestEndpoint(...)`.

The default path listed in server configuration is **`/oauth2/par`**. This is an OAuth2 endpoint, not UserInfo/OIDC logout, and **does not require enabling OIDC** to use PAR for an OAuth2 Authorization Code Flow. For OIDC login, `openid` handling and ID Token processing remain part of the separate OIDC configuration.

### 9.1. Endpoint configuration skeleton

The Java/Spring Boot example below shows **where PAR is configured** in the filter chain (referencing Spring Authorization Server 1.5.x). It does not include all beans needed for a runnable Authorization Server:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerParConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer server =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(server.getEndpointsMatcher())
            .with(server, authorizationServer ->
                    authorizationServer.pushedAuthorizationRequestEndpoint(
                            Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.vn")
                .pushedAuthorizationRequestEndpoint("/oauth2/par")
                .build();
    }
}
```

Key points to understand:

- `securityMatcher(server.getEndpointsMatcher())` scopes the filter chain to the exact set of OAuth2 endpoints, including the endpoint configured via PAR.
- `pushedAuthorizationRequestEndpoint(Customizer.withDefaults())` shows where PAR is configured. Whether the endpoint is active, advertised in metadata, and working in practice must still be verified against your **version and runtime**; do not assume merely calling the configurer completes every policy.
- `issuer("https://login.example.vn")` keeps the public issuer stable when running behind a reverse proxy.
- `pushedAuthorizationRequestEndpoint("/oauth2/par")` in settings sets the **path**; it does not by itself define "require all clients to use PAR".
- This omits `RegisteredClientRepository`, signing keys/JWK (if JWTs are needed), login/consent, token/authorization services, and the user login filter chain. Add them according to your application architecture.

**Distinguish between supporting the endpoint and enforcing PAR:** The RFC allows the AS to require PAR server-wide or per client. Do not assume a `ClientSettings.requirePushedAuthorizationRequests(true)` method exists in every Spring Authorization Server version. If your version does not provide built-in enforcement configuration, implement a policy/validator before processing direct authorization requests and test thoroughly; never publish `require_pushed_authorization_requests=true` in JSON while still accepting regular requests.

### 9.2. Registering a client using Authorization Code + PKCE

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

static RegisteredClient portalClient(String hashedSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientSecret(hashedSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .build();
}
```

This is a **factory method** that must be placed inside a class and persisted via `RegisteredClientRepository`. `hashedSecret` is a hash generated with `PasswordEncoder`; the plaintext secret is only for the client and must be distributed via a secret manager. `requireProofKey(true)` enforces PKCE; **it is not a flag that enables PAR**.

### 9.3. Role of the OAuth2 Client

The `portal-web` side must actually:

1. Generate `state`/`nonce`/PKCE before redirecting the user.
2. Send the PAR POST using an HTTP client with TLS and appropriate client authentication; handle status `201`, `request_uri`, and `expires_in`.
3. Store the transaction linking the reference with the browser/session, issuer, and PKCE verifier.
4. Build the authorization URL using the received `request_uri` (without appending all the request data).
5. On callback, match `state`, use the corresponding verifier to exchange the code, and verify the ID Token if using OIDC.

**Do not assume** a Spring Security OAuth2 Login application automatically routes all authorization requests through PAR just because the Authorization Server advertises the endpoint. Depending on the version, you need a client library/configuration/resolver that supports PAR and must test actual requests. If customizing, preserve Spring Security's state/session/PKCE behavior; do not write a custom callback controller lacking validation.

## 10. Sequence for testing PAR in local/staging environments

### 10.1. Check metadata

```bash
curl -fsS https://login.example.vn/.well-known/oauth-authorization-server \
  | jq '{issuer, authorization_endpoint, pushed_authorization_request_endpoint, require_pushed_authorization_requests}'
```

The `pushed_authorization_request_endpoint` field must match the public HTTPS URL of the running AS. This command only reads metadata; it **does not prove** the entire PAR flow is operational or enforced.

### 10.2. Test a valid PAR request

To avoid putting real secrets into command-line/history, run the test using an HTTP client with a protected credential store. With dummy data, an illustrative example:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic TEST_CREDENTIAL_REDACTED

client_id=portal-web&response_type=code&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20orders.read&state=TEST_STATE&nonce=TEST_NONCE&code_challenge=TEST_S256_CHALLENGE&code_challenge_method=S256
```

The `TEST_*` values above are **placeholders**, not valid PKCE values. Real tests must generate verifier/challenge using a CSPRNG and SHA-256, and supply client credentials per policy. Expect a `201 Created` response with an unpredictable `request_uri` and positive `expires_in`, then have the browser GET the authorization endpoint with the valid reference.

### 10.3. Functional and security test matrix

| Case | Scenario | Expected result |
|---|---|---|
| 1 | Valid PAR, correct client auth, PKCE S256 | `201` with `request_uri` and `expires_in` |
| 2 | Wrong client secret or incorrect method | Reject with `invalid_client`/appropriate error, no reference issued |
| 3 | Send `GET /oauth2/par` | Not processed as a PAR POST; per RFC may return `405` |
| 4 | Send `request_uri` in PAR POST | Rejected |
| 5 | Invalid `redirect_uri` | PAR rejected, no redirect code issued to unknown URI |
| 6 | Scope not in registration | PAR rejected (or appropriate policy error) |
| 7 | Missing `code_challenge` when client requires PKCE | Rejected at the appropriate validation step |
| 8 | Browser uses `request_uri` for matching client within TTL | AS proceeds with login/consent/authorization flow |
| 9 | Browser uses client A's reference with client B's `client_id` | Rejected |
| 10 | Browser uses an expired reference | Rejected per RFC |
| 11 | Browser resubmits an already used reference | Rejected per one-time policy; test reload exception if configured |
| 12 | Append `scope=admin` to browser URL alongside `request_uri` | Does not alter the pushed scope |
| 13 | Append a different `redirect_uri` to browser URL | Does not bypass redirect URI check of the original request |
| 14 | Scope removed from client policy before reference expires | Authorization endpoint detects and rejects/applies current policy |
| 15 | Enable PAR requirement, then send direct `/oauth2/authorize` without reference | Rejected with `invalid_request` |
| 16 | PAR POST on pod A, authorize GET on pod B | Retrieves the same request and valid TTL/consume state |
| 17 | Two browsers use the same reference concurrently | No double authorization outside policy |
| 18 | PAR POST contains sensitive business data | Proxy/logs/tracing do not log the body verbatim |
| 19 | Very large PAR POST or excessive request rate | Body-size quota/rate limit enforced, safe error; no resource exhaustion |
| 20 | Complete Authorization Code + PKCE + OIDC | Callback verifies state/nonce, token exchanged with matching client/verifier |

### 10.4. Common issues

| Symptom | Possible cause | How to verify |
|---|---|---|
| `POST /oauth2/par` returns `404` | AS version does not support it, PAR not configured, wrong proxy route | Check configurer, settings, filter chain, and public route |
| `invalid_client` | Client auth at PAR does not match registration | Check client method/credential, do not log secrets |
| `invalid_request` due to `request_uri` or `redirect_uri` | Sent `request_uri` in POST or invalid redirect | Remove `request_uri` from POST, keep registered callback URI |
| PAR returns `201` but browser authorize fails | URI expired, different client, bad encoding, request lost from cache | Check TTL, client binding, storage/session/multi-node |
| PAR endpoint exists but browser still sends full scope/claims | Client does not use PAR when building authorization URL | Check actual OAuth2 Client request resolver |
| Browser refresh causes `request_uri` error | One-time reference already consumed | Design flow to start a new transaction with a clear error message |
| Redirect URI overwritten by arbitrary payload | PAR redirect validator/exception too permissive | Tighten policy; do not allow open redirects |
| Short URL yet `code` still appears in callback | PAR only protects the initial request | Apply PKCE, safe callback, no-referrer/no-store, do not log queries |
| Works on single AS pod, fails intermittently with multiple pods | Pushed request store is local only | Design shared storage/cluster routing and test TTL/replay |

## 11. Deciding when to require PAR

PAR is especially useful when:

- The application handles personal/sensitive data and should keep permission/claims parameters out of browser URLs.
- There are **rich authorization requests**, fine-grained scopes/consent, or structured transaction data.
- The system requires **client authentication before user interaction**, strengthening protection against spoofing or request tampering.
- The organization follows a high security profile (e.g., financial ecosystems) requiring centralized validation at the AS and additional front-channel control.
- Traditional URLs become too long and risk failing across proxies, browsers, or mobile devices.

**Trade-offs to consider:** adds a direct HTTP round trip before the browser redirect, requires client PAR support, and adds an endpoint, cache/persistence, TTL, and monitoring. If mandatory PAR is enabled and the endpoint is unavailable, the client must not automatically downgrade to a direct authorization request (as that violates policy); it must report an appropriate error or retry in a controlled manner.

### 11.1. Production design checklist

- [ ] Clear policy defined: PAR is **optional**, required per specific client, or enforced server-wide.
- [ ] PAR POST allowed only over HTTPS, enforces proper client authentication, and rejects the `request_uri` parameter.
- [ ] AS validates redirect URI, scope, PKCE, and request format early, and revalidates policy at authorization time when needed.
- [ ] `request_uri` has sufficient entropy, is bound to the client, has a short TTL, and enforces one-time use/replay protection.
- [ ] Pushed request storage is bounded, cleans up TTL, is shared across AS nodes, and protects sensitive data.
- [ ] Front-channel carries only the reference; browser parameters cannot override pushed content.
- [ ] Client keeps `state`, `nonce`, and `code_verifier` bound to the transaction and verifies callback/tokens afterward.
- [ ] Do not confuse PAR with JAR/JARM, Authorization Code grant, PKCE, or client authentication.
- [ ] Metadata accurately reflects the enforced PAR endpoint/policy; verify direct authorize is rejected when PAR is required.
- [ ] Rate/size/timeout limits, observability, auditing, and secret redaction are in place.
- [ ] Integration tests exist on the **exact Spring Authorization Server version**, OAuth2 Client, and actual proxy/cluster topology.
- [ ] Rollout/migration strategy exists for clients not yet supporting PAR; do not abruptly enable enforcement and break valid logins.

## 12. Self-check questions

1. Why does a long `/oauth2/authorize` URL with `claims`/`authorization_details` pose privacy and integrity risks?
2. Which endpoints does PAR use, which endpoint receives POST, and which endpoint still redirects the user agent?
3. Does the PAR `201` response return an access token or authorization code?
4. How does `request_uri` differ from `redirect_uri` and `code_verifier`?
5. Why must `request_uri` be bound to the client that pushed the request?
6. If an attacker swaps `request_uri` in the browser, why do PKCE, `state`, and `nonce` still matter?
7. Once PAR is enabled, can the Authorization Server skip checking scope, redirect URI, and user consent at the authorization endpoint?
8. Does PAR provide a digital signature on the Request Object by itself? When is JAR needed?
9. What sensitive data can still appear in the browser at the callback step even when using PAR?
10. When PAR is mandatory, how must a direct request to the authorization endpoint without a valid reference be handled?
11. Why must a multi-pod AS deployment pay attention to TTL, storage, and access control for `request_uri`?
12. Is configuring the `pushedAuthorizationRequestEndpoint("/oauth2/par")` path alone sufficient to guarantee every client is forced to use PAR?

## References

- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): defines PAR, request URI, client authentication, metadata, one-time usage rules, and security.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, token endpoint, client authentication, and authorization code.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect URI, CSRF/PKCE protection, and OAuth2 threats.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE S256, verifier, and code challenge.
- [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): signed/encrypted Request Object, combined with PAR.
- [RFC 9396 — Rich Authorization Requests (RAR)](https://www.rfc-editor.org/rfc/rfc9396): `authorization_details` for fine-grained authorization requests.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata and PAR endpoint URL.
- [Spring Authorization Server — Configuration Model (1.5.x)](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer` and `AuthorizationServerSettings`.
- [Spring Authorization Server — Protocol Endpoints (1.5.x)](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2PushedAuthorizationRequestEndpointConfigurer`, filter/provider, and validation customization.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): authorization request resolver, PKCE, and client callback.
- [Spring Authorization Server 1.5 GA Announcement](https://spring.io/blog/2025/05/20/spring-authorization-server-1-5-goes-ga/): addition of PAR in Spring Authorization Server 1.5.
