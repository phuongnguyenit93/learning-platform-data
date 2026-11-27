# Authorization Lifecycle and the Relationship Between Tokens, Consent, and Sessions

## 1. Why Must These Three Concepts Be Understood Together?

In an OAuth 2.0/OpenID Connect (OIDC) system built with **Spring Security** and **Spring Authorization Server** on Spring Boot, a user may currently be logged in, have previously consented to grant permissions to an application, and hold valid tokens. These three things are related, yet **not synonymous**.

Consider an order management application:

- User **Lan** opens the web app and is redirected to the Authorization Server (AS) to log in.
- The AS asks Lan whether to let the `orders-web` application read her order list (scope `orders.read`). Lan approves.
- The AS issues an authorization code, and then the client exchanges the code for an access token, possibly accompanied by a refresh token and an ID token when using OIDC.
- Lan logs out of the AS login page, yet the newly issued access token can still be used to call the Orders API until it expires or is invalidated by an implemented mechanism.
- Lan logs in again: the AS may recognize **stored consent** and skip prompting again for the same scopes, even though this is a **new login session**.

Lumping session, consent, and tokens into a single concept leads to mistakes: assuming logout always revokes tokens, assuming deleting consent automatically blocks all old access tokens, or assuming possessing an access token means the user has an active browser session.

After this lesson, you will be able to:

1. Explain the lifecycle of an **authorization grant** from authorization request to expiration/revocation.
2. Distinguish **authentication session**, **authorization consent**, **OAuth2Authorization**, and tokens.
3. Describe what actually happens upon **logout**, **session expiration**, **token refresh**, **token revocation**, or **consent withdrawal**.
4. Map these states into Spring Authorization Server and Spring Security.
5. Design proper persistence, lifetimes, testing, and monitoring for multi-instance Spring Boot systems.

## 2. The Big Picture: Four State Layers

A browser-based authorization flow typically traverses four layers:

| State layer | Question it answers | Typical owner/location | Stored data |
|---|---|---|---|
| **Authentication session** | "Who is this browser authenticated as, and is the session still valid?" | AS/OP and/or client application | SecurityContext, cookie, HTTP session, or equivalent session mechanism |
| **Authorization consent** | "Which permissions has the user agreed to grant this client?" | AS/OP | Client, user, approved authorities/scopes |
| **Authorization grant / OAuth2Authorization** | "Which authorization request was processed and which artifacts/tokens are attached to it?" | AS | Client, principal, grant type, authorized scopes, tokens, metadata |
| **Issued tokens** | "Which credential allows the client to perform the next step?" | Issued by AS; held by client; validated by RP/RS | Authorization code, access token, refresh token, ID token if OIDC |

In Spring Authorization Server, `OAuth2Authorization` is the model storing the state of **one authorization**, while `OAuth2AuthorizationConsent` is the **consent** model. The user's login session typically belongs to **Spring Security's** authentication/web session mechanism, not necessarily inside the same record.

```mermaid
flowchart TB
    U["User"] -->|"Logs in"| S["Authentication session at AS<br/>Spring Security / HttpSession"]
    U -->|"Approves permissions"| C["Stored consent<br/>OAuth2AuthorizationConsentService"]
    S -->|"Identifies principal at /authorize"| D["Authorization grant decision"]
    C -->|"Approved permissions"| D
    D --> A["Authorization record<br/>OAuth2AuthorizationService"]
    A --> T["Authorization code / Access token<br/>Refresh token / ID token if present"]
    T --> CL["Client / Relying Party"]
    CL -->|"Access token"| API["Resource Server / API"]
    API -->|"Validates token and permissions"| CL
```

The diagram shows **causal relationships**, not that all four layers share the same lifetime or deletion mechanism. One authorization record may hold multiple token details; one user may have multiple authorizations for multiple clients or multiple authorization grants; one browser session may be used to process multiple authorization requests.

### 2.1. "Authorization" Has Multiple Meanings in Documentation

In OAuth, *authorization* can refer to **the process** of permitting a client to access resources, *authorization grant* is the representation of granted permission (such as an authorization code), and `OAuth2Authorization` is the name of the **state object** in Spring Authorization Server. The word *consent* typically refers to the decision to approve specific permissions when a user is involved.

Do not infer that every authorization requires a consent screen: the **Client Credentials Grant** can issue an access token to a calling service directly with no end user or browser session.

## 3. Lifecycle of Authorization Code + PKCE + OIDC

Consider this setup:

- **Client/Relying Party:** backend-for-frontend (BFF) application `orders-web`, holding tokens server-side.
- **Authorization Server/OpenID Provider:** `https://auth.example.com`.
- **Resource Server:** `https://api.example.com`, providing the Orders API.
- **User:** Lan.
- **Scopes:** `openid`, `profile`, `orders.read`.
- **Flow:** Authorization Code + PKCE; OIDC is activated when the request contains `openid`.

```mermaid
sequenceDiagram
    actor U as Lan
    participant B as Browser
    participant C as Client / RP
    participant AS as Authorization Server / OP
    participant CS as Consent Service
    participant AZ as Authorization Service
    participant API as Orders API / RS

    U->>B: Click Sign In
    B->>C: Request login
    C->>C: Generate state, PKCE verifier/challenge, nonce
    C-->>B: Redirect to /oauth2/authorize
    B->>AS: Authorization request
    AS->>AS: Validate client, redirect URI, scope, session
    opt No login session yet at AS
        AS-->>B: Render login page
        U->>B: Log in
        B->>AS: Submit credentials
        AS->>AS: Create login session
    end
    AS->>CS: Check consent for client + Lan
    opt New consent or additional scopes needed
        AS-->>B: Display requested permissions
        U->>B: Approve permissions
        B->>AS: Submit consent decision
        AS->>CS: Save approved scopes
    end
    AS->>AZ: Save authorization containing short-lived code
    AS-->>B: Redirect containing code and state
    B->>C: Deliver code to callback
    C->>C: Verify state
    C->>AS: POST /oauth2/token (code + code_verifier)
    AS->>AZ: Verify code, client, PKCE; update authorization
    AS-->>C: Access token, ID token, optional refresh token
    C->>C: Validate ID token and create application session
    C->>API: Authorization: Bearer ACCESS_TOKEN
    API->>API: Validate token, scope, and data permissions
    API-->>C: Return permitted data
```

Different steps have different implications for sessions, consent, and tokens.

### 3.1. Step 0 — Client Registration and Grant Policies

Before any authorization request arrives, the AS must know which clients are allowed to participate: `client_id`, client authentication method, grant types, redirect URIs, scopes, PKCE requirements, whether consent is mandatory, and token lifetimes.

In Spring Authorization Server, this is the responsibility of `RegisteredClientRepository` and `RegisteredClient` properties. **Client registration is trust configuration**, not user consent or user login.

### 3.2. Step 1 — Receiving the Authorization Request

The client directs the browser to the Authorization Endpoint:

```http
GET /oauth2/authorize?response_type=code&client_id=orders-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forders-web
    &scope=openid%20profile%20orders.read
    &state=RANDOM_STATE
    &nonce=RANDOM_NONCE
    &code_challenge=BASE64URL_SHA256_VERIFIER
    &code_challenge_method=S256
```

This example is wrapped for readability; an actual URL must be properly encoded and sent over HTTPS. The AS validates client, redirect URI, response type, scopes, and policies. The client retains `state`, `nonce`, and `code_verifier` in the initiating request context.

**There is no access token yet** merely because the AS received the request. The request can be rejected immediately if the client or redirect URI is invalid.

### 3.3. Step 2 — User Authentication and Session at the AS

If the browser does not yet have a valid session with the AS, Spring Security requires login. After successful authentication, an `Authentication`/`SecurityContext` is established; in session-backed servlet apps, this context is usually tied to the HTTP session via the AS cookie.

If an AS session is **already valid**, the AS can proceed to evaluate the authorization request without prompting for the password again, subject to OIDC constraints such as `prompt=login`, `max_age`, and authentication policy.

Key distinctions:

- **Login** proves who the user is within the AS session.
- **Consent** proves the user approved certain permissions for the client, when required by policy.
- **Tokens** are the result of issuance after a valid authorization request.

The login session at the AS also differs from **the user session at the client application**. In OIDC login, the RP typically creates its own session after validating the ID token; clearing one session does not necessarily clear the other.

### 3.4. Step 3 — Checking and Recording Consent

The AS determines which scopes the client requested and which permissions the user previously approved. If the client requires consent and insufficient stored permissions exist, the user is asked to approve or deny.

- **Approved:** the corresponding authorities/scopes are persisted via `OAuth2AuthorizationConsentService`. The AS can proceed to issue the authorization.
- **Denied:** the flow cannot grant the denied permissions; when the request cannot proceed, the AS returns an error such as `access_denied` per protocol rules.
- **Sufficient scopes already approved:** under normal policies, the AS may skip the consent screen on equivalent requests, though parameters like `prompt=consent`, provider policies, and UX settings may prompt again.
- **Requesting additional scopes:** prior consent for `orders.read` does not automatically authorize `orders.write`. The AS must evaluate the new request per grant policy.

Consent is not a mechanism guaranteeing permanent client privileges. The AS can still deny permissions at issuance time, and the Resource Server remains responsible for checking business permissions at usage time.

### 3.5. Step 4 — Issuing the Authorization Code

Once the request is valid, the AS creates a short-lived **authorization code** bound to the client, redirect URI, and PKCE challenge. Spring Authorization Server persists the associated state in `OAuth2AuthorizationService`.

The code is a temporary proof for the client to exchange for tokens; it is **not an access token to call APIs**. The client receives the code via redirect and must verify `state`. The code is short-lived and can be successfully exchanged only once.

At this moment:

| State | Status |
|---|---|
| Session at AS | Usually still active if logged in via browser |
| Consent | May have been saved, depending on policy |
| Authorization | Record exists linking the code and granted context |
| Access/refresh/ID tokens | Not yet handed to the client until the code exchange step |

### 3.6. Step 5 — Exchanging the Code for Tokens

The client sends a request to the Token Endpoint over TLS:

```http
POST /oauth2/token
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Forders-web&code_verifier=ORIGINAL_RANDOM_VERIFIER
```

This example uses a **confidential client** with `client_secret_basic`. Public clients do not send a client secret; client authentication/identification rules at the Token Endpoint must match the registered client. The PKCE verifier is checked against the stored challenge; expired codes, reused codes, mismatched redirect URIs, or failed client authentication must be rejected.

Example response when OIDC is enabled:

```json
{
  "token_type": "Bearer",
  "access_token": "ACCESS_TOKEN_VALUE",
  "expires_in": 600,
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "scope": "openid profile orders.read",
  "id_token": "SIGNED_ID_TOKEN_JWT"
}
```

**Not every grant produces all of the tokens above.** A plain Authorization Code Flow has no `id_token` unless it is an OIDC request; whether a refresh token is issued depends on grant, client, and policy. The Client Credentials Grant has no end-user ID token. In OIDC, the RP must validate the ID token to establish login context; the ID token does not replace the access token for calling the Orders API.

Spring Authorization Server updates `OAuth2Authorization` with the corresponding tokens and metadata. A consumed authorization code cannot be reused, though historical metadata may remain in the record for auditing/status tracking.

### 3.7. Step 6 — Using the Access Token at the API

The client sends the access token to the Resource Server:

```http
GET /orders
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
```

The Orders API validates the token via its configured mechanism (such as JWT signature/claims or opaque token introspection), then verifies scopes like `orders.read` and per-order permissions. **Consent and AS sessions are not queried directly on every API request**, unless the system deliberately designs an additional real-time check.

An access token can remain valid even after the user closes the browser, their AS login session expires, or they log out of the client application.

### 3.8. Step 7 — Renewing with a Refresh Token

When the access token expires, a client holding a valid refresh token can request a new token **without reopening the login page**:

```http
POST /oauth2/token
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
```

The AS validates the client, refresh token, expiration, revocation status, and policy. If allowed, the AS issues a new access token; it may also issue a new refresh token when rotation is enabled. Refreshing a token **does not mean the browser login session at the AS has been extended**.

In particular:

- **Access token expiration** does not automatically expire the refresh token.
- **Refresh token expiration or revocation** does not automatically delete the login session at the AS.
- **Refresh token rotation** reduces the useful window of an old token. It **does not by itself guarantee** full chain-wide replay/reuse detection; achieving a *refresh token family* policy and theft alerting requires verifying your implementation's capabilities and adding appropriate mechanisms.
- Do not store refresh tokens in browser storage when the architecture allows keeping them securely on the backend; public clients must be handled according to policy and actual Authorization Server support.

### 3.9. Step 8 — Expiration, Revocation, and Ending Access

An authorization does not necessarily "end" via a single action. Different events affect different layers: authorization code expires; access token expires; refresh token is revoked; consent is withdrawn; login session is deleted; user account is locked; or permission policies change.

To invalidate access effectively, the system must know **which tokens remain valid where** and whether the Resource Server receives revocation decisions promptly.

## 4. Detailed Comparison: Session, Consent, Authorization, and Token

| Property | Session at AS | Consent | OAuth2Authorization | Token |
|---|---|---|---|---|
| Binding unit | Browser/device or principal's session | User + registered client | One authorization grant instance/context | Token and token recipient |
| Creation condition | Successful authentication per AS mechanism | Permission approval when required by policy | Processed authorization grant flow | Matching grant at the relevant endpoint |
| Purpose | Remembers browser authentication state | Remembers permissions user approved for client | Manages grant state, scopes, tokens, and metadata | Enables code exchange, API access, refresh, or OIDC authentication |
| Spring storage | Spring Security / HTTP session, per architecture | `OAuth2AuthorizationConsentService` | `OAuth2AuthorizationService` | Typically embedded in the authorization record; client also holds issued tokens |
| Can survive logout? | Logged-out session becomes invalid per logout mechanism | **Yes** | **Yes** | **Possibly** |
| Can survive consent withdrawal? | **Yes** | Record modified/deleted | **Possibly** | **Possibly**, depending on coordinated revocation policy |
| Always requires an end user? | Yes if it is a user session | Yes for user consent | **No**: can be Client Credentials | **No**: access token may represent a client |
| Used as credential to call APIs? | Not by default | No | Never send the entire record | **Access token** is used for APIs by design |

Note: "session" in the table refers to **the login session at the AS**, not **the RP's session**. The RP may create its own session cookie after an OIDC login; stateless APIs generally do not maintain user sessions per access token.

### 4.1. Primary Token Types and Lifetimes

| Type | Where used? | Reusable? | Key rules |
|---|---|---|---|
| **Authorization code** | Client sends to Token Endpoint | **No**, exchanged once only | Very short-lived; bound to client/redirect URI/PKCE |
| **Access token** | Resource Server | Yes, while valid and matching audience/scope | Can be JWT or opaque; always protect as a credential |
| **Refresh token** | Client sends to Token Endpoint | Depends on reuse/rotation policy | Longer-lived; requires strict protection; expires/revokes independently |
| **ID token (OIDC)** | OIDC RP verifies authentication result | Never use as an API bearer token | JWT carrying authentication claims; verify signature/issuer/audience/time/nonce when applicable |

In a system with thousands of tokens, do not use the ID token's `sub` or `principalName` as a single key to wipe "all login state"; they represent different layers. Each authorization must be queried, invalidated, or inspected according to its actual data.

## 5. A Timeline: When Is Each State Alive?

Suppose an illustrative policy specifies:

- Login session at AS: maximum **30 minutes of inactivity**.
- Authorization code: **3 minutes**.
- Access token: **10 minutes**.
- Refresh token: **7 days**.
- Consent for `orders.read`: retained until revoked, modified, or expired per policy.

| Hypothetical time | Event | Consequence |
|---|---|---|
| 08:00 | Lan logs into AS | Browser session begins at AS |
| 08:02 | Lan consents to `orders.read` | Consent record is persisted |
| 08:02:00 | AS creates code | Code valid until around 08:05 |
| 08:02:10 | Client exchanges code successfully | Code can no longer be reused; access token expires around 08:12:10 |
| 08:12:10 | First access token expires | Client can use the still-valid refresh token to request a new access token |
| 08:30 | AS session remains inactive and expires | Next `/authorize` request may require logging in again |
| Day 2 | Client uses valid refresh token | Can obtain a new access token even without an AS browser session |
| Day 7 or per policy | Refresh token expires | Client needs a new grant unless another authorization mechanism exists |

These are **chosen example lifetimes**, not universal Spring Authorization Server defaults. Every TTL, session timeout, refresh token rotation, and consent retention setting must be defined by your system.

**Key takeaway:** "The user no longer has a login session" and "APIs must reject all of the user's access tokens" are **two separate statements**. For the second statement to hold immediately, you need a token invalidation mechanism and corresponding lookup/notification at the Resource Server.

## 6. Data Model in Spring Authorization Server

Spring Authorization Server provides key abstractions:

### 6.1. `RegisteredClientRepository` — Who Is Allowed to Request?

Stores client configuration: `clientId`, client authentication, grant types, redirect URIs, scopes, `ClientSettings`, and `TokenSettings`. For example, `requireAuthorizationConsent(true)` enforces an appropriate consent step, while `requireProofKey(true)` enforces PKCE for the client's Authorization Code Grant.

Do not confuse **scopes registered for the client** with **scopes approved by the user** or **scopes actually issued in each access token**. These three sets can differ.

### 6.2. `OAuth2AuthorizationConsentService` — What Did the User Agree To?

`OAuth2AuthorizationConsent` is keyed by **registered client ID** and **principal name**, holding a set of `GrantedAuthority` representing approved permissions; many Spring integrations use authorities like `SCOPE_orders.read`.

Typical operations:

- `findById(registeredClientId, principalName)` — look up consent.
- `save(authorizationConsent)` — save/update consent.
- `remove(authorizationConsent)` — remove consent.

Deleting consent forces the next authorization request to re-evaluate according to policy. **Deleting consent does not automatically locate and revoke all previously issued access/refresh tokens.** If the product offers a "disconnect app" feature, the business flow must coordinate removing consent and invalidating related authorizations/tokens.

### 6.3. `OAuth2AuthorizationService` — What State Are Authorizations and Tokens In?

`OAuth2Authorization` can store data such as:

- `registeredClientId`, `principalName`, `authorizationGrantType`;
- `authorizedScopes` granted in that specific authorization;
- attributes/metadata tied to the grant and authentication process;
- authorization code, access token, refresh token, and OIDC ID token if applicable;
- per-token status: issued timestamp, expiration, invalidation metadata.

Core `OAuth2AuthorizationService` APIs:

```java
// Illustrates API signatures, not a full service implementation.
void save(OAuth2Authorization authorization);
void remove(OAuth2Authorization authorization);
OAuth2Authorization findById(String id);
OAuth2Authorization findByToken(String token, OAuth2TokenType tokenType);
```

`findByToken` supports looking up tokens in the backing store, such as when handling the Token Endpoint, Revocation, or Introspection. Protocol-compliant token invalidation may require **updating metadata/status inside the authorization** rather than arbitrarily deleting a row. Avoid writing direct DB deletion logic that breaks invariants or corrupts refresh/revocation flows.

Never assume there is **one** unique `OAuth2Authorization` per principal. The same user can grant authorization multiple times to the same client or across multiple clients; Client Credentials can also create authorizations without a user session.

### 6.4. `SecurityContext` and HTTP Session — Authentication State at the Web Layer

Spring Security servlet authentication sessions may use a `SecurityContext` bound to the session, `JSESSIONID` cookie, or a custom cookie name. With multiple instances, you need a session-sharing strategy or compatible flow guarantees; **Spring Session** is one option for managing sessions via a shared store.

Persisting `OAuth2AuthorizationService` via JDBC does not automatically make HTTP sessions shared, and storing sessions via Spring Session does not automatically persist consents/tokens. Configure **both persistence needs** for their respective purposes.

### 6.5. Organizing Persistence

| Component | For simple dev/test | Recommended for multi-instance production |
|---|---|---|
| Registered client | `InMemoryRegisteredClientRepository` | Durable config store such as JDBC or equivalent solution |
| Authorization/token state | `InMemoryOAuth2AuthorizationService` | `JdbcOAuth2AuthorizationService` or durable implementation |
| Consent | `InMemoryOAuth2AuthorizationConsentService` | `JdbcOAuth2AuthorizationConsentService` or durable implementation |
| AS login session | Single-instance HttpSession | Shared session store per architecture policy; e.g., Spring Session |
| Token signing keys | Locally configured JWK for demos | Secure key management, synchronized across instances, with a rotation plan |

In-memory storage is convenient for learning, yet restarts wipe consent/refresh token state and sessions; in multi-instance environments, inconsistent state storage causes mysterious `invalid_grant` errors or repeated login prompts.

## 7. Example Configuration for Authorization, Consent, and Token Policies

Assume `orders-web` is a **confidential BFF**, keeping its client secret and tokens on the backend. The Java snippet below focuses on `RegisteredClient`; repositories, key material, the login `SecurityFilterChain`, and OIDC configuration must still be set up separately:

```java
RegisteredClient createOrdersWebClient(
        String clientSecretFromSecureConfiguration,
        PasswordEncoder passwordEncoder) {

    return RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-web")
        .clientSecret(passwordEncoder.encode(clientSecretFromSecureConfiguration))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.com/login/oauth2/code/orders-web")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .requireAuthorizationConsent(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .authorizationCodeTimeToLive(Duration.ofMinutes(3))
            .accessTokenTimeToLive(Duration.ofMinutes(10))
            .refreshTokenTimeToLive(Duration.ofDays(7))
            .reuseRefreshTokens(false)
            .build())
        .build();
}
```

Meaning:

1. `requireProofKey(true)` requires the client to supply and prove a PKCE verifier.
2. `requireAuthorizationConsent(true)` enforces handling consent for the client's proposed scopes per policy.
3. `authorizationCodeTimeToLive`, `accessTokenTimeToLive`, and `refreshTokenTimeToLive` are three independent clocks.
4. `reuseRefreshTokens(false)` directs issuing a new refresh token upon refresh; verify precisely how the old token is handled on your version.
5. Client secrets must come from a secure secret management mechanism; never hardcode plaintext secrets in source code or send them to the browser.

Example JDBC persistence configuration:

```java
@Bean
OAuth2AuthorizationService authorizationService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository) {

    return new JdbcOAuth2AuthorizationService(
        jdbcOperations, registeredClientRepository);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcOperations jdbcOperations,
        RegisteredClientRepository registeredClientRepository) {

    return new JdbcOAuth2AuthorizationConsentService(
        jdbcOperations, registeredClientRepository);
}
```

These snippets assume imports, the `JdbcOperations` bean, and `RegisteredClientRepository` already exist. **The database schema must match your Spring Authorization Server version**, with explicit migrations, protection of sensitive data, and backup/cleanup jobs. This is state configuration only, not a full production-ready Authorization Server.

### 7.1. Aligning Token Lifetimes with Session Lifetimes

There is no universal requirement that `accessTokenTimeToLive` must equal the HTTP session timeout. Choose lifetimes based on threat model and UX:

- Sensitive APIs may need short-lived access tokens and frequent authorization checks.
- Long-lived refresh tokens require revocation capabilities, client binding, and secure storage.
- Browser sessions require inactivity policies, absolute timeouts, session fixation protection, and secure cookies.
- Consent retention must satisfy product rules: which permissions are remembered, where users manage them, and when re-prompting is required.

When changing TTLs, **already issued** tokens typically retain the expiration timestamp computed at issuance; updating policy does not automatically rewrite existing tokens. If immediate invalidation is needed, implement an appropriate revocation mechanism.

## 8. Logout, Revocation, and Deleting Consent: Actual Effects

This is where the most serious operational bugs tend to occur.

| Action taken by user or system | Session at AS | Session at RP | Consent | Issued tokens |
|---|---|---|---|---|
| Logout at RP application | Depends on single-logout mechanism; may remain active | Usually cleared at RP | Usually kept | May remain valid |
| Logout at AS | AS session terminated | May remain if no coordinated logout | Usually kept | Not automatically revoked |
| OIDC RP-Initiated Logout | Triggers OP logout flow if supported/configured | RP must handle its own session | Usually kept | Does not automatically revoke all OAuth tokens |
| Revoking a refresh token via revocation | Not automatically cleared | Not automatically cleared | Usually kept | That refresh token stops working; impact on related access tokens depends on implementation policy |
| Access token expires | No direct impact | No direct impact | No impact | That access token is no longer accepted by APIs |
| User withdraws consent | Not automatically cleared | Not automatically cleared | Consent record modified/deleted | Old tokens may still work unless revocation is also performed |
| Admin locks user account | Depends on session-locking flow | Depends on integration | Depends on policy | Requires active invalidation if immediate effect is needed |

### 8.1. Why Does Logout Not Automatically Revoke Tokens?

An OAuth Bearer access token is a credential independent of session cookies. The Resource Server validates tokens according to format and design:

- **Self-contained JWT:** APIs verify signature, issuer, audience, expiration, and claims without calling back to the AS. If the JWT is unexpired and the API has no revocation check, logging out of the AS **does not automatically invalidate the JWT**.
- **Opaque token + introspection:** the API queries the Authorization Server or related service to check if the token is still `active`; if revocation status was updated and introspection is not overly cached, validity can be cut short.
- **JWT with custom revocation check:** can use a denylist, token version, revocation events, or status checks at the API; must weigh consistency, caching, and performance.

Therefore, a "Sign out of all devices" button requires a holistic workflow: terminating related sessions, invalidating refresh tokens/authorizations as needed, deciding how to block live access tokens, synchronizing state across services, and handling RP sessions if supported by design.

### 8.2. Revocation Differs from Expiration

**Expiration** occurs naturally at `expiresAt`; **revocation** is an active decision making a token unusable before its expiration. RFC 7009 defines the Token Revocation Endpoint; Spring Authorization Server can expose this endpoint, typically at `/oauth2/revoke`. Clients must authenticate per endpoint rules, and the system must define how related tokens are affected.

Revoking a refresh token does not guarantee that self-validating JWT APIs will immediately stop accepting already-issued access tokens. RFCs and implementation configurations vary on how revocation propagates across tokens.

### 8.3. Withdrawing Consent Differs from "Disconnect Access Immediately"

Suppose Lan visits "Connected Apps" and chooses to remove `orders-web`. If the feature only calls `OAuth2AuthorizationConsentService.remove(...)`, then:

1. Stored consent disappears.
2. Future authorization requests may prompt for consent again.
3. An existing access token may still remain valid.
4. An existing refresh token may still obtain new access tokens if the refresh pipeline is not tied to the disconnection policy.

If the product requirement is **completely cutting off access**, business logic must coordinate consent management with authorization/token invalidation. Never show a UI message saying "Access disconnected" when only consent was deleted while tokens still work.

## 9. Scope, Consent, and Permission Changes Over Time

Consider three requests:

| Attempt | Requested scopes | Previously stored consent | Reasonable decision |
|---|---|---|---|
| A | `openid orders.read` | None | Prompt consent if required by policy |
| B | `openid orders.read` | Already has same scopes | Can continue granting without re-prompting |
| C | `openid orders.read orders.write` | Only has `orders.read` | Must evaluate and request approval for the new scope if needed |

The principal may deny `orders.write` while still granting `orders.read` if the server/client supports downscoping; the client must inspect the scopes actually granted. **Never assume the client received every scope it requested.**

Also distinguish **consent** from **authorization policy**:

- Consent answers whether the user agreed to share permissions.
- Client registration and AS policy restrict which permissions a client can request/be granted.
- The Resource Server further enforces resource-level authorization, e.g., a user may only view orders belonging to their account.

If a user's permissions are narrowed after a token is issued, claims already embedded in a JWT may become stale. Design must consider short-lived access tokens, dynamic permission checks, or revocation; consent updates do not automatically refresh roles/scopes inside existing tokens.

## 10. Three Different Sessions Can Coexist

When using OIDC, the word "session" must specify which component owns it:

| Session | When created? | Who maintains it? | What does clearing this session affect? |
|---|---|---|---|
| **AS login session** | User authenticates at Authorization Server | AS/OP's Spring Security | Next `/authorize` request may require login |
| **RP/application session** | Client validates login and creates app session | `orders-web` application | User loses RP session, yet may still have SSO at AS |
| **Resource Server session** (if any) | Per API design | API | Separate; standard bearer-token APIs can be stateless |

Example:

1. Lan logs out of `orders-web`; the RP clears the application's session cookie.
2. Lan clicks Login again; the AS still has a valid SSO session.
3. The AS can authenticate Lan without re-prompting for her password and reuse stored consent.
4. The RP receives a new code and tokens, then creates a **new application session**.

If logout should force re-entering credentials on the next login, implement an appropriate OIDC flow/policy (such as requiring re-authentication), rather than only performing local RP logout.

## 11. Lifecycle Threat Matrix

| Risk | Stage | Primary defense |
|---|---|---|
| Authorization code intercepted | Redirect/code exchange | Authorization Code + PKCE `S256`, short-lived single-use codes, strict redirect URIs |
| CSRF/mix-up attack at callback | Authorization response | `state`, issuer validation when needed, proper callback configuration |
| ID token substituted or replayed | OIDC login | Verify signature, `iss`, `aud`, `exp`, `nonce` if used, request context binding |
| Forged consent or coerced approval | Consent UI | CSRF protection, trustworthy client/scope display, clickjacking defense, event auditing |
| Session hijacking/fixation | Login and session maintenance | HTTPS, proper Secure/HttpOnly/SameSite cookies, session fixation protection, timeouts |
| Access token stolen | API calls | TLS, avoid logging tokens, short token TTL, restrict audience/scope, consider sender-constrained tokens if supported |
| Refresh token stolen | Token renewal | Store securely server-side when possible, client authentication, rotation, reuse detection per design, revocation capability |
| JWT still usable after logout | Post-logout/revocation | Short-lived JWTs, introspection or proper revocation checks, security event synchronization |
| Principal's permissions change | Between token issuances | Short token TTL, dynamic API policies, revocation or re-authorization when needed |
| Token/consent data exposed via DB/logs | Persistence/operations | DB access controls, policy-compliant encryption, log redaction, backups and key rotation |

**Never log plaintext access tokens, refresh tokens, authorization codes, client secrets, or session cookies.** To correlate events, use request IDs, safe authorization IDs, and non-credential attributes.

### 11.1. A Few Design Principles

- Before issuing a code: validate client/redirect, ensure authenticated user, apply consent and PKCE.
- Before issuing an access token: verify valid grant, PKCE/client authentication, allowed scopes, and policies.
- Before granting API access: validate the exact **API-intended access token**, expiration, scopes, and object-level permissions.
- When refreshing: validate the **refresh token** and client; do not confuse with a browser session.
- On logout/disconnect: define which sessions to close, which authorizations/tokens to revoke, and how APIs learn of that decision.
- Across multiple nodes: authorizations, consents, sessions, and signing keys must be managed consistently per deployment model.

## 12. End-to-End Lifecycle Testing

Testing should not stop at "login succeeded and API call worked." The following scenarios uncover mismatches between sessions, consent, and tokens:

| Test case | Setup/action | Expected outcome |
|---|---|---|
| First-time consent | New user requests `openid orders.read`, client requires consent | Displays appropriate permissions; issues only after valid consent |
| Reused consent | Log in again requesting the same approved scopes | Per policy, may skip prompting consent again |
| Expanded scope | Request additional `orders.write` | Prior consent does not automatically grant the new scope |
| Consent denied | User chooses deny | No authorization issued for denied permissions; client receives appropriate error |
| Login session expires | Let AS session expire while keeping token valid | New authorization request requires re-authentication; API may still accept valid token |
| RP logout | Local logout at web client | RP session cleared; AS session and tokens follow their own mechanisms |
| AS logout | Logout at Authorization Server | AS session lost; live access token is not automatically rejected by API |
| Code exchanged twice | Resubmit the same authorization code | Second exchange is rejected |
| Wrong PKCE | Exchange code with incorrect `code_verifier` | Token Endpoint rejects, issues no token |
| Expired access token | Call API with token past `exp` | API rejects; client can refresh if eligible |
| Refresh token rotation | Refresh with `reuseRefreshTokens(false)` | New token issued; verify old token invalidation policy |
| Revoked refresh token | Revoke refresh token then retry | Token Endpoint rejects using the revoked refresh token |
| Consent withdrawn | Delete consent then start a new authorization request | Permissions must be re-evaluated; old tokens blocked only if revocation is implemented |
| Misused token type | Send ID token as Bearer token to Orders API | API rejects |
| Wrong audience/scope token | Send access token meant for another API or missing `orders.read` | API rejects |
| Multi-instance | Login/consent on node A, exchange code on node B | Works consistently if storage and keys are shared properly |

### 12.1. Pay Attention to Error Classification

- `invalid_request` / authorization error: missing parameter, invalid redirect, or malformed request.
- `access_denied`: user/AS refused permission.
- `invalid_grant`: invalid, expired, already-used, or revoked authorization code or refresh token (depending on case).
- `invalid_client`: client authentication failed or invalid client.
- **HTTP 401** at API: missing/invalid/expired token.
- **HTTP 403** at API: authenticated request lacking sufficient permissions.

Actual error presentation depends on component, framework, and configuration. Record **protocol context** when diagnosing rather than assuming every login error is caused by sessions or every `401` is caused by consent.

## 13. Operational Scenario: User Selects "Disconnect App"

Suppose a product requirement states: "When Lan removes permissions for `orders-web`, the app can no longer obtain new tokens and cannot continue calling APIs with existing credentials."

A responsible implementation must:

1. **Identify the user and client** accurately; verify the actor has permission to disconnect.
2. **Locate and delete/update consent** in `OAuth2AuthorizationConsentService`.
3. **Locate related authorizations** via proper data query/management mechanisms without assuming there is only a single record.
4. **Invalidate refresh tokens and necessary tokens** via designed APIs/workflows, ensuring the client cannot continue refreshing.
5. **Handle live access tokens**: if using self-validating JWTs, choose a controlled residual acceptance window or add revocation checks; if using introspection, ensure APIs observe the updated state promptly.
6. **Close application sessions if required by policy**, coordinating RP/OP logout per actually implemented protocols.
7. **Record audit events and test** across AS, client, and API; verify the "disconnected" promise matches actual runtime behavior.

Data across multiple stores may not update within a single atomic transaction. In multi-service architectures, design idempotent handlers, orchestration events, and retry strategies to avoid a state where consent is deleted while refresh tokens remain valid longer than intended.

## 14. Common Misconceptions

**"The user is logged in, so the client already has all permissions."** False. The authentication session proves identity at the AS; permissions still depend on client registration, consent, scopes, and authorization policy.

**"Stored consent means an active access token exists."** False. Consent can remain stored after all tokens expire, and access tokens can be issued in grants without end-user consent.

**"One OAuth2Authorization corresponds to exactly one login session."** False. Authorization records and sessions have independent lifecycles with no fixed cardinality.

**"Logout will make all APIs stop accepting JWTs immediately."** False. Self-validating JWTs generally remain usable until expiration unless APIs check additional revocation state.

**"Withdrawing consent is enough to block old tokens."** False. You must coordinate authorization/token invalidation if the product requires cutting off current access.

**"Refresh tokens are how you extend a login session."** False. A refresh token is a credential to request new tokens; it does not by default extend sessions at the AS or RP.

**"The Resource Server must query consent on every incoming request."** False. APIs usually rely on access tokens and API-side authorization policies; if immediate control is needed, design an appropriate supplementary mechanism.

**"Client Credentials always has consent and a session."** False. That grant represents the client itself, with no End-User login or consent.

## 15. Design Thinking Checklist for an Authorization Server

Before implementing, ensure you can answer:

1. **Authentication:** Who is authenticated? Which sessions are created, where, and when do they end?
2. **Consent:** Does the client require user approval? How long is approved consent kept? Which UI withdraws it?
3. **Authorization:** Which grants are allowed; which repository stores metadata and token state; how many instances handle them concurrently?
4. **Tokens:** Are access/refresh/ID tokens used for their intended purposes? How are TTL, audience, scope, key rotation, and storage managed?
5. **Refresh:** Which clients may refresh; is rotation enabled; how are old tokens and stolen tokens handled?
6. **Logout/revocation:** How specifically do RP logout, OP logout, consent withdrawal, and token revocation affect one another?
7. **Resource Server:** Do APIs verify JWTs or use introspection? If immediate revocation is needed, what is the state synchronization mechanism?
8. **Testing/operations:** Have you tested expired session with valid token, withdrawn consent with valid token, revoked token, and requests spanning multiple instances?

### Core Takeaway

**Session** remembers an authentication state at a specific component. **Consent** records permissions the user agreed to grant a client, when required by protocol/policy. **OAuth2Authorization** manages the state of a single authorization grant, including associated tokens. **Tokens** are credentials used at their proper endpoints and intended recipients.

All four layers interact in an Authorization Code + PKCE + OIDC flow, yet **they do not share the same lifetime and do not automatically terminate together**. Properly separating these layers is the foundation for designing, configuring, securing, testing, and operating a reliable Spring Authorization Server.

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/)
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/)
