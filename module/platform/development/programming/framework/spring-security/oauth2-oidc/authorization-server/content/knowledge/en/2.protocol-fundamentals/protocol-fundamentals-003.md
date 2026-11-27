# Authorization Code, Access Token, Refresh Token, and ID Token

In OAuth 2.0 and OpenID Connect (OIDC), the four artifacts **Authorization Code**, **Access Token**, **Refresh Token**, and **ID Token** serve distinct purposes. Understanding the boundaries between them is fundamental to designing, configuring, securing, testing, and operating an **OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application**.

## 1. Context: Who Issues What, and Who Uses What?

A typical system includes the following actors:

- **Resource Owner / End User:** the user who owns the data and performs login and consent approval when required.
- **Client:** the application seeking to access APIs on behalf of the user; it can be a backend-backed web app, an SPA, a mobile app, or a server-side application.
- **Authorization Server (AS):** authenticates the user, processes authorization requests, and issues and manages codes/tokens. This is the role handled by Spring Authorization Server.
- **Resource Server (RS):** the API protecting resources; validates the Access Token and enforces access policies. Spring Security Resource Server typically handles this role.

**OAuth 2.0** solves *resource access authorization*. **OIDC**, built on top of OAuth 2.0, adds *identity authentication* and issues ID Tokens. Therefore, an application receiving an Access Token does not automatically mean it has completed a full OIDC login flow.

| Artifact | What is it used for? | Primary user | Typical characteristics |
| --- | --- | --- | --- |
| **Authorization Code** | Temporary representation of the authorization step result to exchange for tokens | Client sends to AS | Short-lived, single-use, bound to one authorization transaction |
| **Access Token** | Permits calling resources/APIs within granted scopes | Client sends to RS | Time-limited; can be a JWT or an opaque string |
| **Refresh Token** | Obtains a new Access Token without repeating login/authorization interaction | Client sends to AS | Typically outlives Access Tokens; must be strictly protected |
| **ID Token** | Conveys user authentication information from the AS to the OIDC Client | OIDC Client validates and consumes | Usually a signed JWT containing standard claims such as `iss`, `sub`, `aud` |

Do not infer functionality just because artifacts look similar: **JWT is a token format, not a permission type**. An Access Token can be a JWT, an ID Token is typically a JWT, while an Authorization Code and a Refresh Token are usually strings understood only by the AS.

## 2. Where Do They Appear in the Authorization Code Flow?

Example: a web application uses OIDC to log in and then calls `/api/orders` with the `orders.read` permission.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Client (backend/BFF)
    participant AS as Authorization Server
    participant RS as Resource Server (API)
    U->>B: Click Sign In
    B->>C: Request page requiring login
    C-->>B: Redirect to /oauth2/authorize
    B->>AS: response_type=code, state, PKCE, scope=openid ...
    AS->>U: Authenticate and request consent (if needed)
    AS-->>B: 302 redirect_uri?code=...&state=...
    B->>C: Deliver Authorization Code to callback
    C->>C: Verify state, retrieve stored code_verifier
    C->>AS: POST /oauth2/token: code + code_verifier + client authentication
    AS-->>C: Access Token; ID Token (OIDC); Refresh Token (if issued)
    C->>C: Validate ID Token and create application session
    C->>RS: Authorization: Bearer <access_token>
    RS->>RS: Validate token and orders.read permission
    RS-->>C: Order data
    C-->>B: Page or result for the user
```

Key takeaways:

1. **The Authorization Code passes through the browser** during the redirect step, whereas the **Access Token does not need to appear in the redirect URL** of the Authorization Code Flow.
2. The client exchanges the code at the **Token Endpoint**; that is the step where tokens are received.
3. **An ID Token appears only when OIDC is performed** (e.g., `openid` scope is present, OIDC is enabled, and the request is valid). **A Refresh Token depends on grant type and token issuance policy**, and is not guaranteed in every response.
4. Once the Access Token expires, the client can use the Refresh Token at the Token Endpoint if one was issued and remains valid.

## 3. Authorization Code: A One-Time Ticket to Exchange for Tokens

### 3.1. Creating an Authorization Request

With Spring Authorization Server, the default Authorization Endpoint is `/oauth2/authorize`. Illustrative example (values in `<...>` are placeholders):

```http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fclient.example.com%2Fcallback
    &scope=openid%20profile%20orders.read
    &state=<random-state>
    &code_challenge=<base64url-sha256-verifier>
    &code_challenge_method=S256
    &nonce=<random-nonce>
Host: auth.example.com
```

| Parameter | Role |
| --- | --- |
| `response_type=code` | Requests the Authorization Code Flow |
| `client_id` | Identifies the client registered with the AS |
| `redirect_uri` | Where the AS returns the browser; must match a registered URI |
| `scope` | Permissions/scopes requested by the client; `openid` marks an OIDC request |
| `state` | Random value generated by the client to bind the response to the request session and prevent CSRF |
| `code_challenge` and `code_challenge_method=S256` | PKCE proof derived from the secret `code_verifier` held by the client |
| `nonce` | Value binding the OIDC authentication request to the received ID Token to prevent replay |

After processing authentication/authorization, the AS redirects:

```http
HTTP/1.1 302 Found
Location: https://client.example.com/callback?code=<authorization-code>&state=<same-state>
```

The client must verify `state` before using `code`. If the user denies consent or an error occurs, the AS may return `error` at the redirect URI instead of `code`.

### 3.2. Exchanging the Code for Tokens

The backend of a **confidential client** (a client capable of keeping secrets) typically authenticates via `client_secret_basic`. Condensed example:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fclient.example.com%2Fcallback&
code_verifier=<original-random-verifier>
```

The AS verifies that the code is active, unused, belongs to the right client, and matches the redirect URI; if PKCE is used, it must verify that `code_verifier` matches the earlier challenge. **Public clients** (such as SPAs/native apps) have no trustworthy `client_secret`: they typically send `client_id`, use PKCE, and do not pretend to protect a secret in frontend code.

An illustrative response:

```json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "openid profile orders.read",
  "refresh_token": "<refresh-token-if-issued>",
  "id_token": "<id-token-if-oidc>"
}
```

The `refresh_token` and `id_token` fields in this example appear only when their corresponding issuance conditions are met. `expires_in` is the Access Token's validity in seconds. This is an illustrative response, not a usable token.

### 3.3. Why Is PKCE Needed Even with a Code?

If an Authorization Code leaks via the callback, browser history, or an insecure redirect mechanism, an attacker could attempt to exchange the code at the Token Endpoint. PKCE binds the code to the party holding `code_verifier`:

```text
code_verifier  = high-entropy random string kept secret by the client
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
```

The client sends the **challenge** first; when exchanging the code, it sends the **verifier**. The AS compares them. Never place `code_verifier` in the authorization URL, and never reuse the same verifier across transactions. PKCE (`S256`) should be used for both public clients and confidential clients.

These three mechanisms mitigate different threats: `state` binds the callback to the client-initiated request, **PKCE** binds code exchange to the client holding the verifier, and `nonce` binds the **ID Token** to the OIDC request. They are not interchangeable.

## 4. Access Token: Proof of API Access Permission

The Access Token is presented by the client to the Resource Server, usually via an HTTP header:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

The Resource Server decides whether to accept the request based on the token and the API's policies. A cryptographically valid signature on an Access Token **is not sufficient** if the token is expired, does not come from a trusted issuer, is not intended for that API, or lacks the required scope.

### 4.1. JWT or Opaque Token?

| Access Token type | How the Resource Server verifies it | Operational characteristics |
| --- | --- | --- |
| **Signed JWT** | Verifies signature via public key/JWKS, issuer, expiration, audience if applied, and relevant permissions | Fast local verification; self-contained tokens are usually not revoked immediately merely by deleting a record on the AS side |
| **Opaque token** | Calls the Token Introspection Endpoint on the AS (or another validation lookup mechanism) | Validity state can be checked centrally; depends on connectivity to the AS and caching policy |

Do not decode a JWT and immediately trust its payload: normal JWT contents are simply Base64URL-encoded for transport, **are not secret**, and claims are trustworthy only after verifying the signature and required conditions.

For a JWT Access Token, common claims include `iss` (issuer), `sub` (subject), `exp` (expiration), `iat` (issued at), `aud` (audience, if issued), and `scope` or `scp`. Not every JWT Access Token carries the same claim set; it depends on the AS's profile and configuration. An API must check the appropriate audience **if the system uses audience to bind tokens to APIs**; never assume that every token from the same issuer is allowed to call every API.

### 4.2. Scope Is Not the Same as Role or Identity

For example, `orders.read` represents the order-reading permission granted to the token. In Spring Security Resource Server, scopes are converted into authorities like `SCOPE_orders.read` in standard JWT configurations. An API can configure:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
```

The snippet above is **a partial `SecurityFilterChain` configuration**, not a standalone runnable application. Beyond scope, APIs typically also enforce resource ownership or business policies—for instance, user A must not read user B's private orders merely because both hold `orders.read`.

## 5. Refresh Token: Obtaining New Tokens Without Logging In Again

Access Tokens should have a relatively short lifetime to reduce blast radius if leaked. When an Access Token expires, the client can send its received Refresh Token back to the **Authorization Server**—never send a Refresh Token to an API:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<refresh-token>
```

The AS validates the Refresh Token, client, and granted permissions, then returns a new Access Token; depending on configuration, it may also return a **new Refresh Token**. A refresh request does not allow arbitrarily escalating scopes. If the user has revoked consent, the session has been invalidated, or the Refresh Token is expired/revoked, the AS may return an error such as `invalid_grant` and the client must re-request authorization.

### 5.1. Refresh Token Rotation and Storage Protection

**Rotation** means that on every successful refresh, the AS issues a new Refresh Token and invalidates the previous one. This reduces the window for reusing a stolen token; to detect replay and revoke the entire token chain effectively, the system needs an appropriate token family/reuse-detection policy. Do not assume that enabling rotation alone automatically builds complete intrusion detection.

- For a backend/BFF, store Refresh Tokens server-side with restricted read permissions and appropriate encryption at rest.
- For native apps, use the OS secure storage; use the system browser and PKCE for the login flow.
- For browser-only apps, treat tokens as sensitive data against XSS; prefer a BFF/server-side session architecture where suitable. Avoid long-term storage of Refresh Tokens in `localStorage`.
- Never write Access Tokens, Refresh Tokens, codes, or client secrets to logs, URLs, analytics systems, or error messages.
- Revoking self-contained JWTs generally requires additional design (short TTL, denylist, or status checks); **revoking a Refresh Token does not automatically invalidate all previously issued JWT Access Tokens immediately**.

A Refresh Token is neither proof for an API to allow access nor an ID Token. A client might not be issued a Refresh Token depending on client type, grant, consent, and Authorization Server policy.

## 6. ID Token: Authentication Result in OpenID Connect

When a client requests and completes **OIDC** login (e.g., `scope` includes `openid`), the AS issues an **ID Token** to the OIDC Client. An ID Token is a JWT containing claims that let the client verify **who was authenticated, by which issuer, for which client, and within what time window**.

Example payload (header and signature omitted):

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1893455700,
  "exp": 1893456000,
  "nonce": "nonce-in-original-request",
  "auth_time": 1893455500
}
```

| Claim | Meaning and usage |
| --- | --- |
| `iss` | Issuer identifier; the client must compare it against the configured trusted issuer |
| `sub` | User identifier at the issuer; combine `iss` + `sub` as a stable identity key |
| `aud` | Recipient Client ID (may be a list); must contain the current client ID |
| `exp`, `iat` | Expiration and issued-at timestamps; must enforce time constraints per policy |
| `nonce` | If the request sent a nonce, the client must compare it with the value stored for that transaction |
| `auth_time` | Authentication timestamp, present when requested/applicable; useful for policies requiring recent login |
| `azp` | Authorized party when OIDC needs to specify the authorized presenter; must be validated per OIDC rules when present |

The client must **verify the signature**, valid algorithm, `iss`, `aud`, `exp`, `nonce` if requested, and related OIDC conditions. Public keys can be fetched via the JWKS advertised in discovery metadata. Never extract user data from an unverified ID Token to establish a login session.

**An ID Token is not used as a Bearer Token to call APIs.** The `aud` of an ID Token targets the *OIDC Client*, whereas a Resource Server requires an Access Token issued for resource access. An API should not accept an ID Token just because its signature was signed by the same Authorization Server.

An ID Token may omit email, name, or all user profile attributes. Scopes like `profile`, `email`, and the OIDC UserInfo Endpoint define how additional attributes are requested; the actual attributes received depend on consent, claim mapping, and AS configuration. A `sub` stable within an issuer is a better anchor than an email address, which can change.

## 7. Mapping to Spring Authorization Server and Spring Security

### 7.1. Relevant Endpoints

When using Spring Authorization Server with default endpoint configurations:

| Endpoint | Responsibility |
| --- | --- |
| `/oauth2/authorize` | Receives authorization requests, generates Authorization Codes |
| `/oauth2/token` | Exchanges codes for tokens, refreshes tokens |
| `/oauth2/jwks` | Publishes public keys for recipients to verify JWTs when JWK is configured |
| `/oauth2/introspect` | Checks token status per OAuth 2.0 Token Introspection |
| `/oauth2/revoke` | Accepts token revocation requests per OAuth 2.0 Token Revocation |
| `/.well-known/openid-configuration` | OIDC discovery metadata when OIDC is enabled |
| `/userinfo` | OIDC UserInfo Endpoint when OIDC is enabled |

These are default paths; they can be customized via `AuthorizationServerSettings`. OIDC is not automatically enabled just because OAuth 2.0 is configured: OIDC configuration must be enabled and the appropriate scopes registered.

### 7.2. Example Client Registration and Token Policy

The illustrative configuration below uses Spring Authorization Server types; imports and infrastructure setup are omitted:

```java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder,
        @Value("${security.demo.client-secret}") String clientSecret) {

    RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
            .clientId("web-client")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri("https://client.example.com/callback")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(10))
                    .refreshTokenTimeToLive(Duration.ofDays(7))
                    .reuseRefreshTokens(false)
                    .build())
            .build();

    return new InMemoryRegisteredClientRepository(client);
}
```

The configuration above has these direct effects:

- **`AUTHORIZATION_CODE`** enables the code-to-token exchange flow; **`REFRESH_TOKEN`** allows using the refresh grant when a refresh token is issued.
- **`requireProofKey(true)`** enforces PKCE; **`requireAuthorizationConsent(true)`** requires the consent screen according to configuration.
- **`accessTokenTimeToLive`** and **`refreshTokenTimeToLive`** set lifetimes; **`reuseRefreshTokens(false)`** requires issuing a new Refresh Token upon refresh instead of reusing the old one.
- `client_secret_basic` is suitable only for confidential clients keeping the secret on the backend. An SPA must never embed this secret in JavaScript distributed to users.

`InMemoryRegisteredClientRepository` and reading a client secret from configuration are learning examples. In production operations, use durable stores for clients/authorizations/consents, store secrets securely, and manage signing keys under strict control. You can explicitly configure the issuer so tokens, discovery, and Resource Servers remain consistent:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
```

To enable OIDC with the `OAuth2AuthorizationServerConfigurer` configuration matching your version:

```java
authorizationServerConfigurer.oidc(Customizer.withDefaults());
```

This is a call plugged into the Authorization Server's `SecurityFilterChain`, **not a complete configuration**. Issuing signed ID Tokens also requires proper JWK/signing key configuration.

### 7.3. Resource Server Side Verifying Access Tokens

With JWT and issuer discovery, a Spring Boot API application can configure:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
```

Spring Security uses the appropriate metadata/keys to verify JWTs per the Resource Server configuration. You must still configure **authorization rules** and audience validation when the architecture requires binding tokens to specific APIs. If using opaque tokens, the Resource Server must configure introspection instead of `jwt`.

## 8. Three Commonly Confused Scenarios

### Scenario A: Client Has an ID Token, API Returns 401

The application uses the ID Token to call `GET /api/orders`. The API rightly rejects it: it needs an appropriate **Access Token**. The fix is to send the Access Token in `Authorization: Bearer ...`, while checking issuer, audience, expiration, and order-reading permissions.

### Scenario B: Token Endpoint Returns `invalid_grant`

The code may already have been exchanged, expired, mismatched with the client/redirect URI, or have an incorrect PKCE verifier. In a refresh flow, the Refresh Token may be expired, revoked, or already replaced after rotation. Check logs selectively using correlation IDs and safe error details; **never log raw codes, tokens, or verifiers**.

### Scenario C: Client Receives an Access Token Without an ID Token or Refresh Token

Check `scope=openid`, whether OIDC is enabled, whether the client/grant type is registered, and whether the response belongs to a valid OIDC flow. A Refresh Token requires the corresponding grant type and issuance policy. Receiving an Access Token alone does not mean the AS performed OIDC or promised a Refresh Token.

## 9. Design, Testing, and Operations Checklist

1. **Client registration:** allow only necessary redirect URIs, the right client authentication method, and grant types; distinguish public vs. confidential clients.
2. **Flow protection:** use Authorization Code + PKCE `S256`, a random `state` per transaction, and `nonce` for OIDC requests; validate them when processing responses.
3. **Issuance:** set reasonably short Access Token lifetimes, configure Refresh Tokens per client risk, scope issuance rules, and key-signing policies.
4. **Verification:** the OIDC Client verifies the ID Token; the Resource Server verifies the Access Token, access rights, and per-resource permissions; never swap the two tokens.
5. **Negative testing:** test expired/reused codes, invalid verifiers, invalid `state`, wrong issuer/audience, expired tokens, insufficient scopes, revoked Refresh Tokens, and old tokens after rotation.
6. **Operations:** protect secrets/signing keys/tokens, monitor OAuth errors safely, establish signing key rotation and JWKS handling, define revocation policies for JWT/opaque tokens, and control system clock skew.

**Remember:** Authorization Code is *a one-time ticket to exchange for tokens*; Access Token is *permission to call APIs*; Refresh Token is *permission to request a new Access Token*; ID Token is *proof of authentication for the OIDC Client*. Placing each artifact in its rightful step and recipient makes Spring Security OAuth2/OIDC system design clear and testable.

## Authoritative References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/)
