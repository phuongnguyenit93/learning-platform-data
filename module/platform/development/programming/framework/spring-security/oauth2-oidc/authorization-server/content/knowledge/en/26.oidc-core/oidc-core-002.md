# OIDC Authorization Code Flow and the Issued Token Set

## 1. Context and Objectives

In Spring Boot applications using **Spring Security**, **Spring Authorization Server**, and **OpenID Connect (OIDC) 1.0**, a common scenario is that a user visits a web app, is redirected to the Authorization Server to sign in, and then returns to the application with an established login session. At the same time, the application may receive an access token to call a Resource Server on the user's behalf.

The **OIDC Authorization Code Flow** adds the OIDC identity authentication layer on top of the OAuth 2.0 Authorization Code Grant. The key distinction is that when the request includes the `openid` scope and is processed properly as OIDC, the Token Endpoint returns an **ID Token** alongside the **access token**; a **refresh token** may be issued depending on client registration, policy, and consent.

This lesson belongs to the **OIDC Core and ID Token** chapter and focuses on the Authorization Code Flow lifecycle, the meaning of each token, when each is received, and how to use each safely in Spring Boot.

### 1.1. Questions This Lesson Answers

- How does the OIDC Authorization Code Flow differ from a plain OAuth 2.0 Authorization Code Grant?
- What do the Browser, Relying Party (RP), Authorization Server/OpenID Provider (OP), and Resource Server each do?
- When are the authorization code, ID Token, access token, and refresh token received?
- Why should you not use an ID Token to call APIs and not use an access token as an ID Token?
- Which classes of attacks do `state`, `nonce`, and PKCE prevent?
- How must an ID Token be validated before creating a login session?
- How do you configure Spring Authorization Server to issue the right set of tokens?
- How does Spring Security `oauth2Login` handle this process?
- Which failure and deviation scenarios need testing and operational monitoring?

### 1.2. Terminology

| Term | Meaning in This Lesson |
|---|---|
| End-User | The user who needs to be authenticated |
| User Agent | The browser/application navigating the user |
| RP / OIDC Client | The application wanting to authenticate the user, e.g. `order-web` |
| OP / AS | OpenID Provider / Authorization Server, e.g. `auth.example.com` |
| Resource Server | The API accepting access tokens, e.g. `orders-api` |
| Authorization Code | A temporary grant exchanged for tokens at the Token Endpoint |
| ID Token | A JWT containing the user authentication result intended for the RP |
| Access Token | A credential used to access protected resources |
| Refresh Token | An optional credential used to obtain a new access token |
| Authorization/session | Grant state and login session; not the tokens themselves |

## 2. OAuth 2.0 Code Grant and OIDC Code Flow: Similarities and Differences

OIDC builds on OAuth 2.0's Authorization Code mechanism while adding user authentication semantics and ID Token validation requirements.

| Aspect | OAuth 2.0 Authorization Code | OIDC Authorization Code |
|---|---|---|
| `response_type` | `code` | `code` |
| Flow-defining scope | Resource scopes such as `orders.read` | Must contain `openid` to request OIDC |
| Authorization response | Authorization code (and `state` if sent) | Authorization code (and `state` if sent) |
| Primary token response | Access token; refresh token if issued | **Access token + ID Token**; refresh token if issued |
| Where the ID Token is returned | Not part of plain OAuth 2.0 | **Token Endpoint**, not the redirect in the Code Flow |
| How the RP authenticates the user | Plain OAuth does not define an ID Token | Based on a valid ID Token per OIDC |
| Calling APIs | Access token | Access token |
| Fetching extra user claims | No standard equivalent to OIDC UserInfo | Can use the UserInfo Endpoint |

**Seeing `response_type=code` does not automatically mean OIDC is being executed.** The request must contain `scope=openid`, the AS must have OIDC enabled, and the RP must perform OIDC-specific validation.

### 2.1. Why Choose the Authorization Code Flow?

In this flow, the Authorization Endpoint returns a **short-lived code** via redirect; the ID Token and access token are returned at the **Token Endpoint**. With a confidential web client/BFF, the token exchange can happen backend-to-backend and tokens never appear in browser redirect URLs.

This avoids placing tokens directly in URLs, reducing exposure via browser history, referrer headers, or other apps compared to flows that return tokens on the front-channel. Modern Code Flows should combine PKCE, client authentication where appropriate, and redirect URI validation.

With public clients such as SPAs or mobile apps, the Token Request may originate from the client environment, meaning tokens are still present in the application environment. **The property of "not passing tokens through the authorization redirect" does not mean tokens are always hidden from all JavaScript code.**

## 3. End-to-End OIDC Authorization Code Flow Diagram

Suppose a system has:

- `https://app.example.com`: web application/Relying Party.
- `https://auth.example.com`: OP/Authorization Server.
- `https://orders-api.example.com`: Resource Server.
- Client ID `order-web` and registered redirect URI `https://app.example.com/login/oauth2/code/order-oidc`.

```mermaid
sequenceDiagram
    autonumber
    actor U as End-User / Browser
    participant RP as Relying Party / order-web
    participant OP as OpenID Provider / auth.example.com
    participant API as Resource Server / orders-api

    U->>RP: Open sign-in page
    RP->>RP: Generate state, nonce, PKCE code_verifier/challenge
    RP-->>U: Redirect to Authorization Endpoint
    U->>OP: GET /oauth2/authorize?response_type=code&scope=openid...
    OP->>U: Prompt login if needed
    U->>OP: Authenticate user
    OP->>U: Show consent if policy requires
    U->>OP: Approve
    OP-->>U: 302 to redirect_uri?code=...&state=...
    U->>RP: Callback containing code and state
    RP->>RP: Verify state and correlation
    RP->>OP: POST /oauth2/token + code + code_verifier + client auth
    OP->>OP: Validate code, redirect_uri, PKCE, client, and grant
    OP-->>RP: id_token + access_token (+ refresh_token if issued)
    RP->>RP: Verify ID Token; create login session
    RP->>API: Authorization: Bearer access_token
    API->>API: Verify token, audience, scope, and business rules
    API-->>RP: API response
    RP-->>U: Application content
```

### 3.1. Three Locations to Distinguish

1. **Authorization Endpoint** receives the request from the user agent; after login and consent, it returns an authorization **code**, not directly an ID Token/access token in the OIDC Code Flow.
2. **Token Endpoint** receives the code along with client auth/PKCE; it returns **ID Token + access token** and may return a refresh token.
3. **Resource Server** receives the **access token** and verifies permissions; it does not use an ID Token as an API credential.

### 3.2. Where Do Authentication and Authorization Happen?

- The OP authenticates the End-User: password, passkey, MFA, federated identity, or another mechanism.
- The OP evaluates the grant and consent per policy.
- The RP uses the ID Token to verify the user's sign-in result.
- The API uses the access token to check resource access permissions.
- The service/domain layer must still check ownership, tenant, and business authorization.

A successful login does not mean the user is permitted to access every API.

## 4. Step 1 — RP Constructs the Authentication Request

The RP initiates the Authorization Request sent to the Authorization Endpoint, typically via a browser HTTP redirect.

Illustrative example, wrapped across lines for readability:

```http
GET /oauth2/authorize?
    response_type=code
    &client_id=order-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forder-oidc
    &scope=openid%20profile%20orders.read
    &state=RANDOM_STATE_FOR_THIS_LOGIN
    &nonce=RANDOM_NONCE_FOR_THIS_LOGIN
    &code_challenge=BASE64URL_SHA256_OF_VERIFIER
    &code_challenge_method=S256
HTTP/1.1
Host: auth.example.com
```

This is a logical example; on the wire, the URI must be properly encoded without arbitrary line breaks.

### 4.1. Core Parameters

| Parameter | Requirement / Meaning |
|---|---|
| `response_type=code` | Selects the Authorization Code Flow |
| `client_id` | Identifier of the client registered at the OP |
| `redirect_uri` | RP callback; must match the registered value |
| `scope` | Must include `openid`; may add `profile`, `email`, and API scopes |
| `state` | Unpredictable value binding the response to the request and preventing CSRF/login injection |
| `nonce` | Optional in Code Flow per OIDC Core, but recommended when supported to bind the ID Token to the login request |
| `code_challenge` | PKCE challenge derived from the verifier |
| `code_challenge_method=S256` | Recommended PKCE method |

### 4.2. Why Is `scope=openid` Important?

For example:

```text
scope=orders.read
```

is merely an OAuth scope; it does not request OIDC authentication.

Whereas:

```text
scope=openid profile orders.read
```

requests the OIDC Code Flow along with an API permission. `profile` may allow identity claims subject to consent/policy; `orders.read` is a custom API access permission, not a standard OIDC scope.

### 4.3. How Must `state` Be Generated and Stored?

The RP generates a fresh, unpredictable `state` using a CSPRNG for each Authentication Request, stores it alongside the login transaction in the session or equivalent storage, and performs an exact match when the callback arrives.

Do not use a global static state, predictable timestamp, or an unverified value taken from a query parameter. The RP should invalidate or mark the login transaction as consumed to prevent replay.

### 4.4. `nonce` Is Optional — Do Not Confuse It as Mandatory for Code Flow

OIDC Core defines `nonce` as **OPTIONAL** in the Authorization Code Flow; it is required in certain front-channel flows. However, modern RPs may send a nonce, and if sent, the RP must verify that the ID Token contains the exact same value.

Nonce differs from state:

- State binds the **authorization response** to the pending request.
- Nonce binds the **ID Token** to the authentication transaction.

Do not assume that checking state alone lets you skip ID Token validation.

## 5. PKCE: Protecting the Authorization Code

PKCE per RFC 7636 mitigates the risk of an intercepted or stolen authorization code being used, especially for public clients. Modern Best Current Practice also broadly recommends PKCE for the Authorization Code Flow.

The client generates a high-entropy random `code_verifier` and computes `code_challenge`:

```text
code_challenge = BASE64URL(
    SHA-256(ASCII(code_verifier))
)

code_challenge_method = S256
```

The Authorization Request only sends the challenge; the RP retains the verifier in transaction state and sends the verifier in the Token Request.

### 5.1. Role of PKCE vs. Client Secret

| Mechanism | What Does It Prove or Protect? |
|---|---|
| Client secret / `private_key_jwt` / mTLS | Authenticates a confidential client to the Token Endpoint |
| PKCE | Binds the authorization code to the client instance that initiated the request |
| `state` | Binds the callback to the login transaction and prevents CSRF |
| `nonce` | Binds the ID Token to the authentication request |

PKCE does **not** replace client authentication for confidential clients. Conversely, public clients unable to keep a client secret confidential should not embed a secret in an SPA or mobile app.

### 5.2. Why Use S256?

`plain` does not provide comparable protection when an attacker can observe the challenge. Enforce `S256` and reject downgrades when a client is registered with mandatory PKCE policy.

The code verifier must never be placed in the Authorization Request or logged. If it leaks alongside the code while the code is still valid, PKCE's benefit is severely diminished.

## 6. Step 2 — OP Authenticates the User and Handles Consent

Upon receiving the Authorization Request, the OP validates the client, response type, scopes, redirect URI, PKCE, and related parameters. If the user is not yet authenticated or requires reauthentication, the OP runs its login mechanism (form login, MFA, passkey, or identity federation).

**Authenticating the user at the OP does not mean the client automatically gets all requested scopes.** The OP may require consent and grant only scopes permitted by registration, user policy, and business rules.

### 6.1. OIDC Parameters Supporting Authentication Context

| Parameter | Meaning |
|---|---|
| `prompt=login` | Asks the OP to prompt for reauthentication |
| `prompt=none` | Disallows UI interaction; if unable to complete, must return an appropriate error |
| `prompt=consent` | Requests a consent prompt per protocol/policy |
| `max_age` | Maximum allowable age of the authentication session; `max_age=0` effectively requests reauthentication |
| `login_hint` | Hint for the user identifier, not proof of identity |
| `acr_values` | Requested authentication context class/level per OP policy |

When the request specifies `max_age`, the returned ID Token must include `auth_time` per OIDC Core. Do not blindly set `auth_time` equal to the token's `iat`: the time the user authenticated may be earlier than when the token was issued.

### 6.2. Consent and Granted Scopes

The OP grants only scopes within allowed policies. If the user declines, the OP can redirect with an error such as `access_denied`. Do not return a successful code and then issue tokens exceeding what the user or client was granted.

If a client requests scopes outside its registered range, the OP must handle it per policy and specification rather than defaulting to "whatever scopes the client sent."

## 7. Step 3 — OP Returns the Authorization Code via Callback

After login and consent succeed, the OP redirects the browser back to the registered redirect URI:

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/order-oidc?code=ONE_TIME_AUTHORIZATION_CODE&state=RANDOM_STATE_FOR_THIS_LOGIN
Cache-Control: no-store
```

With the default `code` response type, the code and state are placed in the **query component** of the redirect URI. Other response modes must be explicitly configured if used.

### 7.1. The Authorization Code Is a Temporary Grant, Not an API Token

An authorization code:

- Has a short lifetime.
- Is single-use only.
- Is bound to the client, redirect URI, and PKCE challenge.
- Is exchanged at the Token Endpoint.
- Does not carry semantics that "the caller is allowed to read orders" for direct API acceptance.

Never call a Resource Server with `Authorization: Bearer <authorization-code>`.

### 7.2. Callback Checks the RP Must Perform

At a minimum, the RP should:

1. Verify that the callback matches a pending login transaction.
2. Match `state` against the stored value.
3. If `error` is present, handle it per protocol and do not proceed to token exchange.
4. Confirm that a non-empty, structurally valid authorization code is present.
5. Retrieve the `code_verifier` bound to that exact transaction.
6. Send the code directly to the trusted OP's Token Endpoint.
7. Mark the transaction as consumed.

Never place the code in logs, analytics URLs, external links, or referrer headers. Even though a code is short-lived and PKCE-protected, it must still be kept confidential.

## 8. Step 4 — RP Exchanges the Code at the Token Endpoint

For a confidential web client, the backend sends an HTTP POST to the Token Endpoint over TLS:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_REGISTERED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=ONE_TIME_AUTHORIZATION_CODE
&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forder-oidc
&code_verifier=ORIGINAL_CODE_VERIFIER
```

This illustrates a form URL-encoded body. The `&`-prefixed lines form a single standard body; never send the code in the Token Endpoint query string.

### 8.1. Key Validations at the OP

| Check | Reason |
|---|---|
| Client authentication if confidential client | Ensures the right client is exchanging the code |
| `grant_type=authorization_code` | Selects the right grant |
| Code exists, is unexpired, and is unused | Prevents code replay |
| Code belongs to this client | Prevents cross-client token theft |
| `redirect_uri` matches the code/request | Prevents exchanging a code with a different callback |
| `code_verifier` matches the PKCE challenge | Prevents code interception |
| Consent, subject, and scopes remain valid per policy | Prevents issuing tokens beyond the grant |
| TLS and rate limiting | Reduces credential exposure and brute force |

If a code is reused, the OP must reject it; per OAuth specifications, detecting code reuse may require revoking related tokens according to applicable policy/standards.

### 8.2. Confidential Clients vs. Public Clients

Confidential clients typically use `client_secret_basic`, `private_key_jwt`, or mTLS for authentication. Public SPA/mobile clients lack a trustworthy client secret, use `ClientAuthenticationMethod.NONE` and PKCE, and should never place a client secret in JavaScript or a binary and treat it as confidential.

Do not confuse a client authentication private key with a PKCE verifier. They protect different surfaces.

## 9. Step 5 — Token Endpoint Returns the Token Set

A successful OIDC Code Flow returns an **ID Token** and an **access token** in the Token Response, alongside OAuth metadata and possibly a refresh token:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile orders.read",
  "id_token": "SIGNED_ID_TOKEN_JWT",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN_VALUE"
}
```

`refresh_token` in the JSON above **only illustrates the case where the OP actually issues a refresh token**. If the OP does not issue one, omit the field from the response; never populate an empty string and treat it as valid.

### 9.1. Which Fields Are Required?

| Field | Rule / Meaning |
|---|---|
| `access_token` | Present in a successful Token Response |
| `token_type` | OAuth token type, typically `Bearer`; may differ for sender-constrained tokens |
| `id_token` | **Required in the OIDC Authorization Code Flow** |
| `expires_in` | Access token lifetime in seconds; recommended to return |
| `scope` | May appear per OAuth contract, especially if different from requested scopes |
| `refresh_token` | Optional, depending on policy and client grants |

Do not confuse `expires_in` with the lifetime of the ID Token or refresh token. The ID Token has its own `exp` claim; the refresh token is governed by its own TTL, rotation, and revocation rules.

### 9.2. Why Are There No Tokens in the Authorization Redirect?

With `response_type=code`, the authorization response passing through the browser contains only the code (and state/error). Tokens are returned by the Token Endpoint after a separate request, typically backend-to-backend for a confidential RP. That is the core difference from the Implicit/Hybrid Flow.

## 10. ID Token — Authentication Result for the Relying Party

**An ID Token is a JWT** describing the End-User authentication result provided by the OP to the RP. The ID Token is intended for the **client/RP**, not for the Resource Server.

Illustrative payload:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "order-web",
  "exp": 1794825600,
  "iat": 1794825300,
  "auth_time": 1794825000,
  "nonce": "RANDOM_NONCE_FOR_THIS_LOGIN",
  "acr": "urn:example:loa:2"
}
```

This is an example payload; on the wire the ID Token is signed as a JWS JWT and may be encrypted if the RP/OP configure JWE per a profile. The numeric timestamps merely illustrate NumericDate values.

### 10.1. Required Claims

| Claim | Meaning | Validation at the RP |
|---|---|---|
| `iss` | OP's issuer | Matches the configured trusted issuer |
| `sub` | End-User's subject identifier | Non-empty, stable per OP semantics |
| `aud` | Token audience | Must contain the RP's `client_id` |
| `exp` | ID Token expiration time | Not expired within a small clock skew |
| `iat` | Time the token was issued | Valid timestamp per policy |

### 10.2. Conditional Claims

| Claim | Condition / Meaning |
|---|---|
| `nonce` | If the Authorization Request included a nonce, the RP must verify the exact value in the ID Token |
| `auth_time` | Required when the request uses `max_age` or when mandated by spec; time of user authentication |
| `acr` | Authentication Context Class Reference; trust only if the OP defines its semantics |
| `amr` | Authentication Methods References; describes authentication methods when provided |
| `azp` | Authorized party; must be validated per rules when multiple audiences exist or the claim is present |
| `at_hash` | Access token hash; optional in Code Flow, verify if used per profile/policy |
| `email`, `name` | Identity/profile claims depending on scopes, consent, and policy; not guaranteed to be present |

### 10.3. The ID Token's Audience Is the RP, Not the API

For example:

```text
ID Token:
aud = "order-web"

Access Token:
aud = "https://orders-api.example.com"   (if the token profile includes aud)
```

The ID Token proves the user was authenticated by the OP for the RP `order-web`. It is not a credential for `orders-api` to accept. An API should only accept access tokens issued for that API and conforming to the corresponding token profile.

### 10.4. `sub` Is Not Email

`sub` is a subject identifier defined by the issuer. Do not assume it is a username/email, and do not use email as a primary key if emails can change. OIDC supports public or pairwise subject identifiers; the RP should store identity keyed by the `(iss, sub)` pair to avoid subject collisions across multiple issuers.

## 11. Access Token — Permission to Call a Resource Server

**An access token** is presented by the client to a protected resource. It is not login proof for the RP; its semantics are authorization to access resources.

For example:

```http
GET /orders/123 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
```

The RS must verify the token according to the token type issued by the AS:

- **JWT access token:** verify signature, issuer, audience, expiry, and claims/profile, e.g., RFC 9068 where applied.
- **Opaque access token:** call the Introspection Endpoint per RFC 7662.
- **Sender-constrained token:** additionally verify mTLS/DPoP binding as required by the profile.

### 11.1. Access Tokens Can Be JWT or Opaque

OIDC Core does not mandate that every access token be a JWT. In Spring Authorization Server, `OAuth2TokenFormat.SELF_CONTAINED` typically selects a JWT access token, whereas `OAuth2TokenFormat.REFERENCE` selects a reference/opaque token per configuration.

An ID Token is a JWT governed by OIDC rules; an access token has its format determined by the AS's policy and token profile.

### 11.2. Scope Is Coarse-Grained Authorization

For example, an access token carries the `orders.read` scope. The RS may map it to the authority `SCOPE_orders.read`, yet still must check:

- Does the user own this order?
- Which tenant does the order belong to?
- Does the resource state permit this operation?
- Is the client allowed to access this specific Resource Server?

Never rely on `active=true` or a valid signature to skip business-level authorization.

## 12. Refresh Token — Possible, Not Guaranteed by Default

A refresh token lets the client obtain new access tokens without sending the End-User through the full login/consent flow again. However, **the OIDC Authorization Code Flow does not require the OP to issue a refresh token**.

Issuing a refresh token depends on:

- Whether the client registered the `refresh_token` grant.
- Client type and refresh token protection mechanisms.
- Consent/offline access policy.
- OP security posture.
- Token settings and issuance policy.

### 12.1. `offline_access` Does Not Guarantee a Refresh Token

OIDC defines the `offline_access` scope to request access when the user is not present. For offline access, the OP must enforce consent per OIDC Core rules; `prompt=consent` is typically required unless handled under other standard-compliant grounds.

**Merely adding `offline_access` to `scope` does not guarantee a refresh token will be issued.** The OP may reject or ignore the request if prerequisites are not satisfied.

### 12.2. Refresh Token Grant

Example request with a valid refresh token:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
```

The response includes a new access token and possibly a new refresh token if the server applies rotation. With OIDC, a refresh response may contain an ID Token per OIDC rules; never assume every refresh response always includes a new ID Token.

### 12.3. Rotation and Reuse Detection

For confidential web clients, refresh tokens should be kept in protected server-side storage. For public clients, especially SPAs/mobile apps, consider rotation or sender constraints, reuse detection, expiry, and revocation per OAuth Security BCP.

Never log refresh tokens, pass them in URLs, or return them to the browser if a BFF architecture can keep tokens server-side. Reuse of an old token after rotation must be handled according to the threat model.

## 13. Authorization Code, ID Token, Access Token, Refresh Token, and Session

These components are not interchangeable:

| Component | Who Receives It? | What Is It Used For? | Lifetime / Characteristics |
|---|---|---|---|
| Authorization code | RP callback via browser | Exchanged at the Token Endpoint | Very short-lived, single-use |
| ID Token | OIDC RP | Verifying user authentication result | JWT with its own `exp` |
| Access token | Resource Server when client calls API | API authorization | JWT/opaque, has TTL, scope/audience |
| Refresh token | Authorized OAuth client | Obtaining new access tokens | Optional; rotation/revocation |
| RP session cookie | Browser and RP | Maintaining application login session | Depends on session policy, not OAuth tokens |
| OP login session | Browser and OP | Remembering authentication state at the OP | Relatively independent of RP session/tokens |

### 13.1. Does an Expired ID Token Immediately End the RP Session?

Not necessarily. The ID Token's `exp` governs validity when the RP verifies the token, not automatically the TTL of the session cookie issued by the RP. The RP session is managed by the application's authentication/session policy.

However, the application must never use an expired ID Token as an active valid credential to establish a new authentication. SLO, session invalidation, reauthentication, and logout must be designed consistently.

### 13.2. Logout Is Also More Than Deleting an Access Token

RP logout may require clearing the local session, revoking refresh tokens where appropriate, and using OIDC RP-Initiated Logout / Session Management if supported. Deleting an RP cookie does not automatically invalidate all issued access tokens.

## 14. Verifying the ID Token Before Creating a Login Session

This step cannot be skipped. The RP must never merely Base64URL-decode the payload and trust its claims.

### 14.1. Validation Checklist

1. Receive the token over a trusted Token Endpoint channel; protect with TLS.
2. Parse the ID Token JWT per the registered algorithm and format.
3. Verify the JWS signature using keys appropriate for the issuer/client registration (or decrypt first if JWE is used).
4. Verify `iss` matches the configured OP issuer.
5. Verify `aud` contains the RP's `client_id`.
6. Verify `azp` when present or in multi-audience cases per OIDC Core.
7. Verify `exp` has not expired; verify `iat` is valid per policy.
8. If `nonce` was sent, verify the `nonce` claim matches the login transaction.
9. If `max_age` was sent, verify `auth_time` and reauthentication conditions.
10. Verify additional profile conditions such as `acr` and `at_hash` where applicable.
11. Correlate identity by `(iss, sub)` and only then complete authentication at the RP.

OIDC Core defines specific rules for certain signing algorithms and client authentication contexts. Do not hardcode "accept only RS256" across all RPs if a client registration negotiates a different algorithm; use an allowlist per client/issuer and a standard OIDC library.

### 14.2. Never Trust Arbitrary Algorithms or Key URLs From Tokens

The RP must never fetch `jku` or `x5u` from an attacker-supplied JWT and trust that key. Public keys must come from the configured JWK Set URI or discovery of a trusted issuer.

Protect against `alg=none`/algorithm confusion, and treat `kid` as a key selector within a trust store rather than a source of trust itself.

### 14.3. Checking Nonce and State at Two Different Points

- `state`: checked by the RP when the browser returns to the callback, before exchanging the code.
- `nonce`: checked by the RP after receiving and verifying the ID Token, when a nonce was sent in the request.

If using a nonce, store it alongside the login transaction and clear it after completion. Do not skip nonce verification simply because the ID Token has a valid signature.

### 14.4. When the ID Token Contains `at_hash`

In the Authorization Code Flow, `at_hash` is optional. If the profile/OP includes this claim and the RP performs standard validation, the RP can verify the access token hash using the ID Token's signing algorithm. Do not confuse `at_hash` with the signature or with DPoP's `ath` claim.

## 15. UserInfo Endpoint and Additional Identity Claims

If the RP needs additional user claims, it can call the **OIDC UserInfo Endpoint** with an access token issued for that purpose, per the OP's contract.

For example:

```http
GET /userinfo HTTP/1.1
Host: auth.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
```

Illustrative response:

```json
{
  "sub": "user-42",
  "preferred_username": "user42",
  "name": "User Example"
}
```

### 15.1. The `sub` Binding Constraint

The RP must verify that `sub` in the UserInfo Response **matches exactly** the `sub` of the verified ID Token. If they do not match, never merge claims, as doing so could mix data from two different users.

### 15.2. `profile` and `email` Do Not Guarantee Every Claim Will Appear

Scopes allow requesting data categories per OIDC, but actual returned content depends on the OP, consent, identity source, and policy. Do not assume `email_verified=true` just because an email is present; check each claim's value and semantics.

Do not copy all UserInfo claims into JWT access tokens when APIs do not need them; limit PII and apply data minimization.

## 16. Configuring Spring Authorization Server to Enable OIDC

Spring Authorization Server/Spring Security Authorization Server provides an OIDC configurer, yet **OIDC is not enabled by default in minimal configurations**. You must explicitly enable it when you want to issue ID Tokens in the OIDC Code Flow and support OIDC endpoints.

### 16.1. Newer Spring Security Authorization Server Configuration

Recent Spring Security releases integrate the Authorization Server DSL; the configuration pattern looks like:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .oauth2AuthorizationServer(authorizationServer -> {
            http.securityMatcher(
                authorizationServer.getEndpointsMatcher());
            authorizationServer.oidc(Customizer.withDefaults());
        })
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
```

This is a code skeleton using the newer configuration style; imports and infrastructure beans are omitted. You still need a user authentication chain, `RegisteredClientRepository`, `OAuth2AuthorizationService`, signer/JWK, issuer, and environment-specific services. For the UserInfo endpoint requiring JWT authentication, configure the corresponding Resource Server/`JwtDecoder`.

### 16.2. Spring Authorization Server 1.x

In many older Spring Boot projects, the configurer API is used:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
```

**Choose the single configuration style matching your dependency version**; do not mix APIs across versions. Do not copy Spring Security 7 code into an SAS 1.x project without checking compatibility.

### 16.3. Separate User Authentication Chain

The Authorization Code Flow requires an authenticated End-User. Example AS application chain for form login:

```java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
```

This chain provides the user login mechanism; production may use MFA, WebAuthn/passkeys, or federation. Do not confuse End-User authentication at the OP with client authentication at the Token Endpoint.

### 16.4. JWK, JwtDecoder, and Issuer

OIDC ID Tokens are signed, and RPs need trusted public keys/JWKS. The OP should configure a `JWKSource<SecurityContext>` backed by signing keys protected in a keystore/KMS, along with a stable issuer:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .build();
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
```

The `JwtDecoder` bean is specifically needed for the OIDC UserInfo endpoint and certain other OIDC endpoints depending on framework configuration. Never generate a random new signing key on every production startup without a key rotation strategy; older tokens cannot be verified if their corresponding public key disappears.

### 16.5. OIDC Endpoints

When OIDC is enabled, the OP typically exposes:

| Endpoint | Purpose |
|---|---|
| `/.well-known/openid-configuration` | Provider Configuration Discovery |
| `/oauth2/authorize` | Authorization Request, login/consent |
| `/oauth2/token` | Exchanges code for tokens |
| `/oauth2/jwks` | Public keys for RPs to verify JWTs |
| `/userinfo` | Returns identity claims based on access token |
| OIDC Logout endpoint | Coordinates logout if configured/supported |
| OIDC Client Registration | Optional; not enabled by default in all versions |

Actual URIs depend on `AuthorizationServerSettings` and issuer/endpoint configuration. Do not hardcode all URLs purely from controller defaults; read the OP's OIDC discovery metadata.

## 17. RegisteredClient for OIDC Authorization Code

To allow a client to run the flow, configure a `RegisteredClient` with authorization code grant, redirect URI, client authentication method, the `openid` scope, and token settings.

Example confidential BFF:

```java
RegisteredClient orderWeb = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("order-web")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.com/login/oauth2/code/order-oidc")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .authorizationCodeTimeToLive(Duration.ofMinutes(3))
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build())
    .build();
```

This is a bean/model snippet, not a standalone runnable AS configuration. TTL values and redirect URIs are illustrative. Credentials must come from a secret manager; `PasswordEncoder` must match the client authentication provider.

### 17.1. Meaning of Each Setting

| Setting | Effect |
|---|---|
| `authorization_code` | Client is allowed to use the code grant |
| `refresh_token` | Client is allowed to request new tokens via refresh grant; does not yet guarantee a refresh token will be issued |
| `redirectUri(...)` | Exact callback recognized by the OP |
| `scope(OidcScopes.OPENID)` | Client is allowed to request OIDC |
| `requireProofKey(true)` | Enforces PKCE for this client's code flow |
| `requireAuthorizationConsent(true)` | OP must handle consent per settings |
| `authorizationCodeTimeToLive` | Code TTL |
| `accessTokenTimeToLive` | Access token TTL |
| `refreshTokenTimeToLive` | Refresh token TTL if issued |
| `reuseRefreshTokens(false)` | Requests refresh token rotation per framework mechanism |

### 17.2. Public Clients vs. Confidential Clients

For public SPAs/mobile apps:

- Use `ClientAuthenticationMethod.NONE` instead of a secret.
- Enforce PKCE `S256` per policy.
- Register redirect URIs suited to the app type.
- Never hardcode a shared secret in the client bundle.
- Check refresh token issuance eligibility and version/OP security constraints.
- Do not adapt the confidential client example above for an SPA by copying the secret into it.

### 17.3. Signing ID Tokens and Customizing Claims

Spring Authorization Server provides `OAuth2TokenCustomizer<JwtEncodingContext>` to add permitted claims to JWTs, while separating ID Tokens from access tokens:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer() {
    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        // Only add claims permitted by policy and sourced from a trusted
        // identity source; do not arbitrarily modify iss, sub, aud, or exp.
    };
}
```

This snippet shows the extension point. A single customizer bean may need to handle both access tokens and ID Tokens depending on configuration; do not define multiple beans of the same generic type assuming the framework will merge them automatically.

Never inject email, phone, tenant role, or `auth_time` supplied directly by the client. The ID Token must preserve OIDC semantics, especially `iss`, `sub`, `aud`, `exp`, `iat`, and conditional `nonce`/`auth_time`.

## 18. Configuring the Relying Party with Spring Security oauth2Login

On the RP side (the client web application), Spring Security `oauth2Login` handles the Authorization Code Flow and OIDC steps when `scope` includes `openid`.

Example Spring Boot properties:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          order-oidc:
            provider: local-op
            client-id: order-web
            client-secret: SECRET_INJECTED_FROM_SECURE_CONFIGURATION
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,orders.read
        provider:
          local-op:
            issuer-uri: https://auth.example.com
```

`SECRET_INJECTED_FROM_SECURE_CONFIGURATION` is only a placeholder, not a production secret. Inject the real variable/secret at deployment time.

### 18.1. Enabling OIDC Login

```java
@Bean
SecurityFilterChain relyingPartySecurity(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/", "/public/**").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());

    return http.build();
}
```

With `scope` containing `openid`, Spring Security uses OIDC components when processing login, validating the ID Token, and creating the OIDC principal. The RP does not need a custom controller exchanging codes via an HTTP client when using `oauth2Login` properly.

### 18.2. Initiation and Callback URLs

With Spring Security servlet defaults:

```text
GET /oauth2/authorization/order-oidc
     |
     v
Redirect to OP Authorization Endpoint

GET /login/oauth2/code/order-oidc?code=...&state=...
     |
     v
Spring Security handles callback and Token Request
```

Do not change the redirect URI on the OP without updating the RP's `ClientRegistration`. Redirect URIs must match exactly per policy.

### 18.3. OIDC User in Spring

After login, Spring Security typically supplies an `OidcUser`. Illustrative controller:

```java
@GetMapping("/me")
Map<String, String> currentUser(
        @AuthenticationPrincipal OidcUser user) {

    return Map.of(
        "issuer", user.getIssuer().toString(),
        "subject", user.getSubject(),
        "name", user.getFullName() != null
            ? user.getFullName()
            : user.getSubject());
}
```

This is a minimal illustrative output; do not return the raw ID Token or sensitive claims in the response. `OidcUser.getFullName()` can be null, so provide a fallback.

### 18.4. Spring Security Helps, But Does Not Replace a Full Security Review

Although `oauth2Login` manages many standard steps, the application still must:

- Protect session cookies and CSRF on business endpoints.
- Manage token storage/retention.
- Configure the exact issuer and redirect URIs.
- Restrict scopes and handle consent.
- Define local user mapping by issuer/subject.
- Enforce tenant/business authorization.
- Monitor callback and token exchange errors.

## 19. OIDC Discovery and Issuer Checks

OIDC Provider Configuration at `/.well-known/openid-configuration` gives the RP metadata such as:

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "userinfo_endpoint": "https://auth.example.com/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"]
}
```

This is an abbreviated example, **not a complete discovery response** or a guarantee of endpoint paths across all OPs. For issuers and public keys, use the real OP metadata and verify TLS/trust.

### 19.1. Why Must the Issuer Match Exactly?

The RP must compare the ID Token's `iss` claim against the configured issuer. Do not check "host contains auth.example.com" or accept an arbitrary issuer self-declared by a token; doing so can lead to issuer confusion.

In multi-issuer setups, the application must explicitly map each client registration to its issuer/JWKS. Do not share one JWK Set across all issuers unless a strict trust contract exists.

### 19.2. Key Rotation

The OP must publish public signing keys via JWKS. During rotation:

1. Add the new public key to JWKS before issuing tokens signed with the new key.
2. Ensure RPs can refresh their JWKS cache.
3. Start signing new ID Tokens with the new key.
4. Keep the old public key long enough for still-valid ID Tokens to be verified during the overlap window.
5. Remove the old key only after accounting for TTLs, caches, and rollback needs.

Do not remove the old public key immediately upon switching signers if RPs still have valid ID Tokens to verify.

## 20. Common Misconceptions About the Token Set

| Misconception | Accurate Understanding |
|---|---|
| "OAuth code flow always returns an ID Token" | Only an OIDC flow requesting `openid` returns an ID Token per spec |
| "Authorization code is a temporary access token" | The code is a grant exchanged for tokens, not an API credential |
| "ID Token is a JWT so APIs can use it" | The ID Token is for the RP; APIs accept access tokens |
| "Access tokens are always JWTs" | They can be JWT or opaque |
| "A refresh token is issued in every OIDC login" | Depends on client, grants, consent, and security policy |
| "`offline_access` guarantees a refresh token" | It is only a request; the OP can deny/ignore it per spec |
| "If the ID Token has `email`, email is the primary identifier" | Identify users by `(iss, sub)` |
| "Successful login means all scopes are granted" | APIs still enforce scope, audience, and domain permissions |
| "State and nonce are the same thing" | State binds the callback; nonce binds the ID Token to the request |
| "PKCE replaces client secrets for confidential apps" | PKCE and client authentication protect different surfaces |
| "ID Tokens always travel through browser URLs" | In the Code Flow, the ID Token is returned from the Token Endpoint |
| "ID Token `exp` is the RP session TTL" | The RP session has its own lifetime and policy |
| "Decoding the JWT is validation" | You must verify signature, issuer, audience, timestamps, and nonce |
| "Spring enables OIDC by default for AS" | You must enable the OIDC configurer in minimal AS configurations |
| "A new refresh token means the old one is definitely revoked" | Depends on rotation/reuse policy and server state |

## 21. Security Risks and Mitigations

### 21.1. Authorization Code Interception/Replay

**Risk:** an attacker obtains the code from the callback URL and exchanges it for tokens.

**Mitigation:** PKCE `S256`, client authentication where appropriate, short code TTL and single-use enforcement, exact redirect URI matching, never logging codes, and rejecting code reuse.

### 21.2. Login CSRF and Authorization Response Injection

**Risk:** a callback from one login transaction is injected into another session, logging the user into the wrong account.

**Mitigation:** unpredictable `state`, bound to the right transaction, strictly verified, never reused; `nonce` when used, verified in the ID Token.

### 21.3. Open Redirect and Redirect URI Manipulation

**Risk:** overly permissive redirect URI registration or handling allows an attacker to divert the code to an attacker-controlled domain.

**Mitigation:** exact redirect URI registration, avoiding wildcards, never letting callers control unvalidated `redirect_uri` or `returnUrl` parameters.

### 21.4. Token Substitution and ID-Token-as-Access-Token

**Risk:** an API accepts an ID Token because it shares the same issuer/signing key, or an RP trusts a JWT with the wrong audience.

**Mitigation:** the RP validates that ID Token audience is its client ID; the RS validates that access token audience is the API along with token type/profile; never swap token roles.

### 21.5. Client Secret and Refresh Token Leakage

**Risk:** shared secrets in SPAs, refresh tokens in `localStorage` without a threat model, or access tokens in logs.

**Mitigation:** BFF/server-side storage where appropriate, secret manager, TLS, secure `HttpOnly`/`SameSite` cookies for RP sessions, rotation, least privilege, and redaction.

### 21.6. Discovery/JWKS Trust Confusion

**Risk:** an RP reads an issuer/JWKS URI from a token or arbitrary input and fetches an attacker's keys.

**Mitigation:** configure trusted issuers, verify discovery metadata, fetch JWKS from the confirmed OP, and never let a JWT select its own key source via URL.

### 21.7. XSS and Session Theft

The OIDC Code Flow does not neutralize XSS, application-level CSRF, session fixation, or cookie theft. Protect the RP application with an appropriate CSP, output encoding, CSRF protection, cookie policies, post-login session rotation, rate limiting, and monitoring.

## 22. Test Matrix for the OIDC Authorization Code Flow

### 22.1. Testing Authorization Requests and Callbacks

| Case | Input / Behavior | Expected Result |
|---|---|---|
| Valid OIDC login | `scope=openid`, `response_type=code` | Receive code, exchange for ID/access tokens |
| Missing `openid` | OAuth-only request | Do not treat response as OIDC login |
| Unregistered client ID | Unknown client | Authorization request rejected |
| Wrong redirect URI | Domain/path differs from registration | Rejected |
| Disallowed scope | Client requests beyond policy | Rejected or narrowed per spec |
| Mismatched `state` | Forged callback | RP rejects |
| Missing `state` when RP sent one | Uncorrelated callback | RP rejects |
| Callback with `error` | `access_denied` or login error | Do not exchange code |
| Reused code | Replay Token Request | Rejected |
| Expired code | Exchange code after TTL | Rejected |
| Wrong PKCE verifier | Challenge mismatch | Token Request rejected |
| `plain` used against policy | PKCE downgrade | Rejected |
| Wrong client secret | Confidential client | Token Request rejected |
| `nonce` sent but ID Token missing/wrong nonce | Replay/substitution | RP rejects ID Token |

### 22.2. Testing Token Responses and ID Tokens

| Case | Expected Result |
|---|---|
| Code Flow Token Response missing `id_token` | RP does not treat it as a successful OIDC login |
| ID Token invalid signature | RP rejects |
| ID Token wrong `iss` | RP rejects |
| ID Token wrong `aud` | RP rejects |
| ID Token expired | RP rejects |
| ID Token anomalous `iat` | Handled per validation policy |
| `nonce` mismatch | RP rejects |
| `max_age` sent but `auth_time` missing/invalid | RP rejects per OIDC requirements |
| ID Token `sub=user-1`, UserInfo `sub=user-2` | RP does not merge claims |
| Valid ID Token, access token wrong API audience | RS rejects |
| Valid ID Token, access token missing scope | RS returns 403 |
| No refresh token | RP can still log in if ID/access tokens are valid |
| Rotated refresh token | Test old and new tokens per policy |
| JWKS key rotation | RP verifies tokens signed by valid keys during overlap |

### 22.3. Testing with Spring Security

- Use `MockMvc`/HTTP integration tests for the authorization endpoint, callback, token endpoint, and `SecurityFilterChain`.
- Verify unauthenticated sessions are properly redirected to login.
- Verify `oauth2Login` creates an OIDC principal from a valid ID Token.
- Verify callbacks with invalid `state`/`nonce` do not create an authenticated `SecurityContext`.
- Verify `RegisteredClient` enforces redirect URI and PKCE policies.
- Verify access tokens are sent to the RS, not ID Tokens.
- Verify minimal OIDC scopes and claims.
- Verify refresh tokens are issued only when permitted.
- Verify consent persistence and scope changes.
- Verify each OAuth/OIDC error does not leak raw tokens/secrets in logs.

Do not unit test a customizer bean alone and conclude the end-to-end flow works. Integration tests must traverse the actual filters and providers.

## 23. Operations and Observability

### 23.1. Useful Metrics

- Authorization request and callback success/failure normalized by client.
- `state` mismatch, PKCE failure, redirect URI mismatch, and code reuse errors.
- Token Endpoint latency, ID/access/refresh issuance errors.
- Login/consent latency, MFA prompt rate, user authentication failures.
- JWK signing/validation failures, unknown `kid`, and key rotation rollout.
- API `401` due to audience/expiry/type; `403` due to scope.
- Refresh token rotation/reuse detection and revocation latency.
- Session login/logout events and active session counts per policy.

Never include codes, access/ID/refresh tokens, nonces, states, or client secrets in metric labels or logs.

### 23.2. Sample Audit Events

You can record:

```text
OIDC_AUTHORIZATION_REQUEST_ACCEPTED
END_USER_AUTHENTICATED
OIDC_CONSENT_GRANTED
AUTHORIZATION_CODE_ISSUED
AUTHORIZATION_CODE_REDEEMED
OIDC_ID_TOKEN_ISSUED
ACCESS_TOKEN_ISSUED
REFRESH_TOKEN_ISSUED
OIDC_LOGIN_COMPLETED
OIDC_LOGIN_REJECTED
```

Audit records should contain correlation ID, client ID, issuer, grant type, outcome, timestamp, and a pseudonymized user identifier if needed. Never log raw tokens or code verifiers.

### 23.3. Runbook for Widespread OIDC Login Failures

1. Check the issuer in discovery metadata and the ID Token `iss` claim.
2. Check authorization/token endpoint URLs and TLS.
3. Verify the registered redirect URI matches the RP callback.
4. Check client authentication and secret/key rotation.
5. Check `state`/`nonce` session storage, especially on multi-instance RPs.
6. Check for lost PKCE challenge/verifier due to session/state store issues.
7. Check signing keys/JWKS, caches, and new `kid` values.
8. Check clock drift and ID Token `exp`/`iat`.
9. Check the OP user authentication/consent store.
10. Check browser cookie `SameSite`/`Secure`, proxy forwarded headers, and callback scheme.

Never fix issues by disabling ID Token signature/audience/nonce validation or enabling wildcard redirect URIs.

## 24. Production Deployment Checklist

- [ ] OIDC Authorization Code Flow uses `response_type=code` and a scope containing `openid`.
- [ ] RP stores `state`, PKCE verifier, and `nonce` (if used) per login transaction.
- [ ] PKCE `S256` is enabled and code verifiers are validated at the Token Endpoint.
- [ ] Redirect URIs are registered/matched exactly with no open redirects.
- [ ] OP authenticates the End-User and processes consent per policy.
- [ ] Authorization codes are short-lived, single-use, and bound to client/redirect/PKCE.
- [ ] Token Endpoint enforces client authentication appropriate to the client type.
- [ ] Token Response contains an ID Token and access token; refresh token only when eligible.
- [ ] RP verifies signature, `iss`, `aud`, `exp`, `iat`, and `nonce`/`auth_time` where applicable.
- [ ] RP identifies users by `(iss, sub)`; never treats email as the default subject.
- [ ] RS accepts only access tokens and checks audience/scope/expiry per token profile.
- [ ] ID Tokens are never used as API bearer credentials.
- [ ] Refresh tokens are protected, TTL-bounded, and rotated/revoked per policy.
- [ ] Spring Authorization Server has the OIDC configurer enabled matching its version.
- [ ] OP has a JWK source, stable issuer, and key rotation plan.
- [ ] RP uses `oauth2Login`/an appropriate OIDC client implementation and validates callbacks.
- [ ] RP session cookies are protected, without confusing session TTL with ID Token TTL.
- [ ] UserInfo `sub` is matched against ID Token `sub` if the RP calls the endpoint.
- [ ] Tests cover state/nonce/PKCE/code replay, ID Token validation, and access token audience.
- [ ] Monitoring, auditing, and redaction cover all credentials and tokens.

### Core Takeaways

The **OIDC Authorization Code Flow** builds on OAuth 2.0's Authorization Code Grant to authenticate End-Users and issue tokens cleanly. The browser receives an **authorization code** via redirect; the RP exchanges the code at the Token Endpoint for an **ID Token + access token**, plus a **refresh token only when permitted by the OP**.

The **ID Token** is a JWT containing the authentication result for the RP and must be verified for signature, issuer, audience, expiration, and nonce when present. The **access token** is for the Resource Server and is verified by scope, audience, and API policy; it can be JWT or opaque. The **refresh token** obtains new tokens and has its own protection/rotation requirements. Authorization codes, tokens, and session cookies cannot substitute for one another.

In Spring Authorization Server, enable OIDC, register clients with the right grants/scopes/redirects/PKCE, configure issuer/JWKS, and protect the Token Endpoint. On the Spring Security RP side, use `oauth2Login` to handle the Authorization Code Flow and OIDC ID Token validation. The system is secure only when the client, OP, and RS enforce the same clear protocol contract.

## 25. References

- [OpenID Connect Core 1.0 — Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 — Offline Access](https://openid.net/specs/openid-connect-core-1_0.html#OfflineAccess)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Spring Security — Authorization Server Configuration Model](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/configuration-model.html)
- [Spring Security — Authorization Server Getting Started](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/getting-started.html)
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — OAuth2 Authorization Code Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Authorization Server — Configuration Model (1.x)](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
