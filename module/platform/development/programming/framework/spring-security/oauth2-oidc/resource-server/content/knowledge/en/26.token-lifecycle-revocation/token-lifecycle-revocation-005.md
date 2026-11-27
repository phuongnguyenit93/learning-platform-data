# Client-Side Logout Does Not Automatically Invalidate Every Issued Access Token

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, when a user clicks **Logout** in a web or mobile app, they naturally expect all access for that session to end immediately. Yet in OAuth 2.0/OIDC, "logout" might only delete a session at a single client, end the SSO session at the OpenID Provider (OP), notify Relying Parties (RPs), revoke a refresh token, revoke an access token, or cancel the entire authorization grant. These are distinct actions managed by different components.

**Client-side logout does not automatically invalidate every issued access token.** If the client only clears cookies/sessions or deletes tokens from memory, a stolen copy of an access token can still be accepted by a Resource Server until the token expires or a revocation mechanism actually checked by the Resource Server takes effect. Even ending the OP SSO session does not mean every access token issued across every API, client, and device has been invalidated.

What is required is a deliberate **logout lifecycle**: clearing the local session, logging out of the OP when needed, calling the token revocation endpoint for the appropriate tokens, handling refresh-token families, updating Resource Server state, and accounting for cache and JWT validation delays.

> **Separate three questions:** has the client cleared its own session; which credentials/grants has the Authorization Server revoked; and does the Resource Server observe and reject that token?

This lesson belongs to the **Lifecycle and Revocation** chapter. It focuses on the differences between client logout, OIDC logout, and OAuth token revocation; access tokens and refresh tokens; RFC 7009, introspection, and self-verified JWTs; integrating logout in Spring Security Servlet/WebFlux; revocation options; and testing to prove old tokens are genuinely no longer accepted.

## 1. "Logout" Is Not a Single Operation

An application may involve multiple independent sessions and credentials:

| Component | Managed state | What logout typically affects |
|---|---|---|
| **Browser/mobile client** | Cookies, app session, token cache | Clears local data or ends the app session |
| **Relying Party (RP)** | Application login session | Invalidates RP session, clears SecurityContext/cookies |
| **OpenID Provider (OP)** | User's SSO session | Ends login session at OP via OIDC logout |
| **Authorization Server (AS)** | Access tokens, refresh tokens, authorization grants | Revokes tokens/grants per supported endpoints and policies |
| **Resource Server (RS)** | Token verification state, caches, denylists, sessions | Stops accepting tokens once revocation or expiration is observed |
| **Downstream service** | Own sessions, tokens, jobs, or caches | Must receive events/revocations per system contract |

For example, a user logs into `orders-web`, receives an ID token and access token, and calls `orders-api`. When the user clicks logout, the app may delete `JSESSIONID` and redirect to the OP. Yet if `orders-api` verifies JWTs solely by signature and expiration, it does not automatically know the browser just logged out.

### 1.1. Lifecycle Diagram

~~~mermaid
flowchart TD
    A["User clicks Logout"] --> B["RP clears local session / SecurityContext"]
    B --> C["Clear client-side token cache"]
    C --> D{"OP SSO logout required?"}
    D -->|"Yes"| E["RP-Initiated Logout to end_session_endpoint"]
    D -->|"No"| F["Finish local logout"]
    E --> G["OP ends SSO session per policy"]
    G --> H["May send Front/Back-Channel Logout"]
    H --> I["RPs invalidate related sessions"]
    F --> J["Issued access tokens may still remain valid"]
    I --> J
    J --> K{"RFC 7009 revocation called?"}
    K -->|"No"| L["Token usable until exp or until RS detects"]
    K -->|"Yes"| M["AS revokes token / grant per contract"]
    M --> N{"Does RS check revocation state?"}
    N -->|"Yes"| O["RS rejects token once update takes effect"]
    N -->|"No, offline JWT"| P["JWT may still pass signature validation until exp"]
~~~

The diagram shows that **OIDC logout** and **OAuth token revocation** are two separate flows. Back-channel logout helps RPs destroy sessions, whereas RFC 7009 asks the AS to revoke tokens. The Resource Server only rejects early if its token verification strategy observes revocation state.

### 1.2. A Concrete Example

Suppose:

~~~text
10:00  User logs in to orders-web.
10:01  OP issues access token A, exp = 11:00.
10:02  RP creates session S1.
10:10  User clicks Logout.
10:10  RP deletes session S1 and cookie.
10:10  Browser no longer has token A in storage.
10:11  Attacker uses a previously captured copy of token A.
~~~

If `orders-api` only verifies JWT signature, `iss`, `aud`, and `exp`, token A can still be valid at 10:11. Logout succeeded at the RP, yet **nothing in that flow required the RS to know token A was copied or that the user logged out**.

That is why you should never promise "Logout immediately invalidates every access token" unless the system has a revocation mechanism propagated to all Resource Servers.

## 2. Distinguishing Client Logout, RP Logout, and OP Logout

### 2.1. Client Logout: Clearing the Session in the App Itself

Client logout typically performs:

- Clearing application cookies/sessions.
- Removing access/refresh tokens from the client-managed token cache or storage.
- Clearing displayed user details.
- Stopping local tasks bound to the session.
- Clearing temporary data per app policy.

Deleting the token copy in the browser **does not make copies sent to other clients or captured elsewhere disappear**. An access token is a bearer credential: anyone holding it and accepted by the RS can use it within its granted permissions.

### 2.2. RP Logout: Destroying the Application Session

A Relying Party (e.g., `orders-web`) may hold:

~~~text
JSESSIONID -> server-side session
                  |
                  +-- SecurityContext
                  +-- principal
                  +-- authorized client references
                  +-- CSRF state
~~~

On logout, the RP must invalidate the server-side session, clear cookies with matching `Path`/`Domain`, clear the `SecurityContext`, and remove local authorized-client data if appropriate. For a stateless API, there may be no HTTP session; in that case, web client logout has no effect on a JWT already received by the API.

### 2.3. OP Logout: Ending the SSO Session

OpenID Connect provides **RP-Initiated Logout** so an RP redirects the user to the OP logout endpoint, typically advertised in discovery metadata as `end_session_endpoint`. The RP can send `id_token_hint`, `post_logout_redirect_uri`, and `state` per the spec and OP capabilities.

This flow ends the SSO session at the OP and lets the OP handle related RP sessions. However, it **is not an OAuth token revocation endpoint**. Do not assume ending the SSO session automatically causes every previously issued access token to be rejected by RSs.

### 2.4. What Logout Does Not Do Automatically

Without additional mechanisms, logging out of one client does not necessarily:

- Revoke every access token of the user.
- Revoke every refresh token across all devices.
- Cancel authorization grants/consents of every client.
- End sessions at all other RPs.
- Clear principal caches on every Resource Server.
- Stop background jobs already started with an earlier access token.
- Revoke tokens already exchanged for another resource/audience.

These behaviors must be explicitly defined in logout policies and contracts with the AS/OP.

## 3. Access Tokens and Refresh Tokens Have Separate Lifecycles

### 3.1. Access Token

An access token is the credential a client presents to a Resource Server. It can be:

- **JWT/self-contained token:** the RS can verify signature and claims locally without calling the AS on every request.
- **Opaque/reference token:** the RS typically calls an introspection endpoint to learn whether the token is active and fetch metadata.

Tokens usually have a relatively short lifetime, yet expiration is an independent boundary from when the client logs out. Before expiration, how the RS validates the token determines whether it remains accepted after revocation.

### 3.2. Refresh Token

A refresh token is used by the client at the token endpoint to obtain new access tokens. It typically has a longer lifetime than an access token and is not a credential sent to Resource Servers.

While a refresh token remains valid, a client that logged out locally yet still possesses (or had stolen) a copy of the refresh token can keep obtaining new access tokens, depending on AS policy. Therefore, logout should consider **revoking the refresh token** or authorization grant, especially when the user logs out due to suspected credential compromise.

### 3.3. Token Families and Multiple Access Tokens

One grant can yield multiple credentials:

~~~text
Authorization Grant G
  |
  +-- Access token A1 -> orders-api
  +-- Access token A2 -> billing-api
  +-- Access token A3 -> profile-api
  +-- Refresh token R1
        |
        +-- rotated refresh token R2
              |
              +-- Access token A4
~~~

Revoking one token does not mean all related tokens are revoked with identical semantics on every AS. RFC 7009 recommends that the AS invalidate other tokens tied to the same grant when possible; exact behavior depends on token types, AS capabilities, and grant policies.

### 3.4. Action and Impact Matrix

| Action | Local session | OP SSO session | Issued access tokens | Refresh tokens |
|---|---|---|---|---|
| Clear cookie at RP | Yes | No | Not automatically revoked | Not automatically revoked |
| Clear token in browser storage | Possibly | No | Only deletes client's local copy | Only deletes client's local copy |
| RP-Initiated Logout | RP may clear | OP handles logout | Not revoked by default | Not revoked by default |
| Front/Back-Channel Logout | Notified RPs can destroy sessions | OP session notifications | Not revoked by default | Not revoked by default |
| RFC 7009 revoke access token | Does not auto-destroy RP session | Does not auto-end SSO | AS revokes token; RS must observe it | AS may revoke related tokens per policy |
| RFC 7009 revoke refresh token | Does not auto-destroy RP session | Does not auto-end SSO | AS should revoke related access tokens if supported | Refresh token is revoked |
| Revoke authorization grant / consent | Not necessarily | Not necessarily | May revoke tokens tied to grant | May revoke related refresh tokens |

"May" and "should" in the table reflect differences across protocols, providers, and RS enforcement. Never advertise a logout button as "revokes all tokens" without proving the entire chain end-to-end.

## 4. OAuth 2.0 Token Revocation per RFC 7009

**RFC 7009 — OAuth 2.0 Token Revocation** defines an endpoint for clients to ask the Authorization Server to revoke a token. This is separate from OIDC logout.

Requests are typically HTTP POST with `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=ACCESS_OR_REFRESH_TOKEN&token_type_hint=refresh_token
~~~

This is an illustrative request. Endpoint, client authentication method, and token types must follow the AS metadata/documentation. Clients must use TLS and never place tokens in query strings.

### 4.1. `token` and `token_type_hint`

- `token` is the token to be revoked.
- `token_type_hint` is an optional hint of token type (e.g., `access_token` or `refresh_token`) to help the AS optimize lookup.
- The hint **is not proof** of the token's type; the AS must still identify the actual token per its implementation.
- Client authentication applies per AS registration/policy. Public clients have no secret; confidential clients generally must authenticate.

### 4.2. A 200 Response Does Not Prove the Token Was Previously Active

RFC 7009 specifies that when a token is already revoked or invalid, the endpoint returns HTTP 200. This avoids leaking to callers whether a specific token exists or is active. Therefore:

~~~text
HTTP 200 from revocation endpoint
  => revocation request processed per contract
  != proof that token was previously active
  != proof that every Resource Server updated its cache
~~~

If the AS cannot process the revocation request due to a transient error, the endpoint may return a server error (e.g., 503); the client must handle it per retry/incident policy and must not claim revocation succeeded.

### 4.3. Revoking Related Tokens Under the Same Grant

RFC 7009 recommends that the AS invalidate other tokens derived from the same authorization grant when feasible. Specifically, if a refresh token is revoked and the AS supports revoking access tokens, the AS should invalidate access tokens created from that grant. If a request revokes an access token, the AS may revoke the associated refresh token.

This is behavior the AS must support and implement; a client cannot infer that all related tokens were revoked from a 200 response alone unless the contract/provider defines that scope. When "sign out everywhere" or "revoke entire grant" is required, use the AS's session/grant management features if supported.

### 4.4. The Revocation Endpoint Is Not UserInfo or end_session_endpoint

| Endpoint | Used for | Does not replace |
|---|---|---|
| `/userinfo` | Fetching OIDC End-User claims | Not token revocation |
| `end_session_endpoint` | RP-Initiated Logout / OP session logout | Does not revoke access tokens by default |
| `/oauth2/revoke` | Revoking access/refresh tokens per RFC 7009 | Does not auto-destroy RP sessions or cookies |
| `/oauth2/introspect` | RS querying token state per RFC 7662 | Not a client logout endpoint |
| `/oauth2/token` | Issuing/refreshing/exchanging tokens | Not a revoke endpoint |

Do not confuse URLs just because they belong to the same issuer.

## 5. Why Can a Revoked JWT Still Be Accepted by a Resource Server?

This is the most critical aspect of token lifecycle design.

### 5.1. Offline JWT Validation

A JWT access token can be verified at the RS by:

~~~text
compact JWT
   |
   v
verify signature with trusted JWKS
   |
   v
validate iss, aud, exp, nbf, token profile
   |
   v
create Authentication
~~~

If the RS does not call the AS and does not check external revocation state, it only knows the claims inside the JWT and the signature. **A JWT marked revoked in the AS database still has a mathematically valid signature.** An offline decoder can continue accepting it until `exp`, unless the RS adds a revocation detection mechanism.

Example:

~~~text
10:00  JWT access token A issued, exp = 11:00.
10:10  Client calls RFC 7009 revoke(A); AS marks A revoked.
10:11  RS verifies signature/iss/aud/exp offline.
       If RS has no denylist/event/introspection check,
       A may still be accepted.
~~~

There is no contradiction here: the AS updated state in its own system; the RS was not notified and did not query that state.

### 5.2. Opaque Token Introspection

With opaque tokens, the RS typically queries the AS:

~~~http
POST /oauth2/introspect
Authorization: Basic ...
Content-Type: application/x-www-form-urlencoded

token=opaque-token
~~~

The AS returns:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "aud": ["orders-api"]
}
~~~

After revocation, a fresh introspection call can return:

~~~json
{"active": false}
~~~

If the RS calls introspection on each request (or has its cache invalidated), it can observe revocation faster. Yet if the RS caches `active=true` for 5 minutes, a revoked token can still be accepted until the cache expires or is invalidated.

### 5.3. Comparing the Two Models

| Characteristic | Offline JWT validation | Opaque + introspection |
|---|---|---|
| Check per request | Usually local | Usually network call or cache |
| Knows revoked tokens immediately? | No, unless extra mechanism exists | Possible, if querying AS and cache is not stale |
| Depends on AS availability per request | Lower | Higher if uncached |
| Revocation latency | Typically up to `exp` without denylist/events | Depends on introspection/cache/propagation |
| Cost | Crypto CPU + JWKS refresh | Network, AS capacity, caching |
| Operates during brief AS outage | Can keep verifying already-issued tokens | May fail closed without valid cache |
| Primary risk | Slow revocation | AS outage, stale cache, latency |

Neither option is universally better. Choose based on **maximum acceptable revocation latency**, API sensitivity, traffic scale, and AS operational capacity.

## 6. Strategies to Invalidate Access Tokens Early

### 6.1. Short-Lived Access Tokens

A simple approach is setting a short `exp`, e.g., 5–10 minutes based on risk, UX, and AS capacity. Once the client logs out and stops refreshing, the token expires shortly thereafter.

Advantages:

- The RS does not need to call the AS on every request.
- Less revocation state to manage.
- Shrinks the window during which a stolen access token can be used.

Limitations:

- Not instant revocation.
- A leaked token remains usable until `exp` if the RS only verifies offline.
- If the refresh token stays alive, an attacker can obtain new tokens; revoke the refresh token/grant.
- Too short a TTL increases refresh/token endpoint traffic and can hurt UX when the AS is slow.

**Short TTL limits the risk window; it is not an instant revocation mechanism.**

### 6.2. Opaque Token + Introspection

The RS asks the AS for token status. Once revoked, the AS returns `active=false` on the next introspection call per contract.

Advantages:

- Token state is centralized at the AS.
- Revocation can take effect rapidly without waiting for `exp`.
- Permissions/active state can change without issuing a new JWT, depending on the AS.

Limitations:

- Network calls and load on the AS.
- Timeouts/outages require a fail-closed policy.
- Introspection caching can delay revocation.
- A multi-tenant AS requires proper issuer/resource/audience binding.

### 6.3. JWT Denylist / Revocation Store

The RS can check the token's `jti` (JWT ID) or fingerprint in a revocation store before handling the request:

~~~text
JWT signature/claims valid
        |
        v
extract (iss, jti, exp)
        |
        v
lookup revocation store
        |
        +-- revoked -> reject
        |
        +-- not revoked -> continue authorization
~~~

Requirements:

- JWTs must have a unique `jti` per issuer/token issuance policy.
- Keys must be namespaced by **issuer** (and tenant/resource if needed), since two issuers could generate colliding `jti` values.
- Entries only need to persist until `exp` + clock-skew allowance; after that, the token expires on its own.
- The store must provide appropriate consistency across RS instances.
- Avoid storing raw bearer tokens if a safe hash/fingerprint can be used.
- Every request must check the store before acceptance; local caches must factor invalidation/TTL into the revocation SLA.

Logical key example:

~~~text
revocation-key = hash(verified-issuer || ":" || jti)
value = revoked
ttl = max(0, exp + allowedClockSkew - now)
~~~

This is an application-level design, not an automatic feature of JWT or Spring Security. If tokens lack `jti`, a hash of the token can be used, though privacy, memory, and consistency must be weighed.

### 6.4. Event-Driven Revocation

The AS can emit events when a token, grant, or session is revoked:

~~~text
Authorization Server
  |
  +-- TokenRevoked(issuer, jti, exp, grantId)
  +-- GrantRevoked(issuer, grantId)
  +-- SessionLoggedOut(issuer, sid, sub)
          |
          v
Resource Server / revocation service
  |
  +-- update denylist
  +-- invalidate introspection cache
  +-- clear related session/cache if any
~~~

The advantage is avoiding polling while achieving low revocation latency. However, you must handle:

- Event authentication/signing and authorization between the AS and consumers.
- At-least-once delivery, duplicates, and idempotency.
- Ordering, retries, dead-letter queues, and event loss.
- Replica lag and cache invalidation across all nodes.
- Distinguishing token-revoked events from RP session logout events.
- Whether events carry sufficient identifiers (`iss`, `jti`, `sid`, grant/session ID) per contract.

Never trust an unverified self-asserted `userId` header/message to revoke or grant principal permissions. Logout/revocation events are security data whose origin must be verified.

### 6.5. Introspection Cache with Invalidation

A cache can combine a short TTL with active eviction upon receiving a revoke event. With a 60-second TTL and working event invalidation, revocation time can be much faster; if an event is lost, the TTL acts as the fallback bound.

Define explicitly:

~~~text
Maximum revocation delay
  <= event propagation delay
     + cache invalidation delay
     + request processing delay
~~~

Without events:

~~~text
Maximum revocation delay ~= introspection cache TTL
~~~

These are operational targets to measure, not default guarantees of Spring Security.

## 7. Refresh Token Rotation and Reuse Detection

Refresh tokens typically outlive access tokens. Revoking only the current access token while leaving the refresh token active allows a client or attacker to request new access tokens.

### 7.1. Rotation

With refresh-token rotation:

1. Client sends refresh token `R1` to the token endpoint.
2. AS accepts `R1`, issues a new access token and refresh token `R2`.
3. AS marks `R1` as no longer usable.
4. Client stores `R2` and deletes `R1`.
5. If `R1` is reused, the AS can detect reuse and revoke the token family/grant per policy.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: refresh_token=R1
    AS->>AS: Validate R1, rotate family
    AS-->>C: access_token=A2, refresh_token=R2
    C->>API: Bearer A2
    API-->>C: Resource response
    Note over C,AS: Logout or R1 reuse detected
    C->>AS: Revoke R2 / grant per policy
    AS->>AS: Revoke refresh family and related tokens
    Note over API: RS must observe access token revocation
~~~

### 7.2. Logout Must Clean Up Refresh Tokens

If the client only deletes `R2` from storage, a stolen copy can still be used. On logout, call the revocation endpoint with the refresh token if the AS supports it and the client is authorized to do so. For public clients, token revocation must follow the mechanism provided by the AS; never embed a client secret in a SPA or mobile binary.

### 7.3. Reuse Detection Does Not Default to Logging Out Every Session

The AS may revoke a token family when an old refresh token is reused, as that signals potential token theft. However, whether that revokes all devices/grants depends on the provider. Do not assume one refresh-token family covers every session of a user across all clients.

### 7.4. Concurrency When Multiple Tabs or Devices Refresh

If two tabs use the same refresh token simultaneously, rotation may treat one request as reuse depending on the AS and grace policy. Clients need a refresh coordination mechanism (single-flight/locking) and proper `invalid_grant` handling. Logging out while a refresh is in flight must prevent the newly returned access token from being saved or attached to requests after the session ends.

## 8. OIDC RP-Initiated Logout Is Not Token Revocation

OIDC RP-Initiated Logout lets an RP ask the OP to end the login session. OP metadata may advertise `end_session_endpoint`.

A conceptual request:

~~~text
GET https://identity.example.com/logout
  ?id_token_hint=<ID_TOKEN>
  &post_logout_redirect_uri=https%3A%2F%2Forders.example.com%2Flogged-out
  &state=<random-state>
~~~

Actual parameters follow OIDC RP-Initiated Logout and the OP implementation:

- `id_token_hint`: ID token associated with the RP/OP session; helps the OP identify the right session.
- `post_logout_redirect_uri`: URI registered/permitted at the OP.
- `state`: value preventing request/response mix-up and binding the logout flow to the client session.

**Here, the ID token acts as a hint for the logout endpoint, not as an API authentication token.** Sending `id_token_hint` does not replace calling RFC 7009 to revoke access/refresh tokens.

### 8.1. Ending the OP Session May Affect Other RPs

The OP may log out the SSO session and send Front-Channel/Back-Channel notifications to registered RPs. However, each RP must properly implement the protocol to destroy its own session. It does not mean every access token across every Resource Server is invalidated immediately.

### 8.2. RPs Must Validate Redirect URIs

Never redirect users to an arbitrary URL from a request parameter:

~~~java
// Unsafe: open redirect
handler.setPostLogoutRedirectUri(request.getParameter("returnTo"));
~~~

Use a registered/allowlisted URI and validate `state`. Logout redirects are an attack surface that can be abused for phishing or open redirects.

### 8.3. Local Logout Must Still Happen

Redirecting to the OP should not be the only action. The RP must invalidate the local session and clear the `SecurityContext`/cookies according to its lifecycle so the user cannot keep using the old app session even if the OP logout endpoint is temporarily unavailable. Order steps so revocation calls still have access to the tokens to be revoked before local data is deleted.

## 9. Front-Channel Logout and Back-Channel Logout

OIDC defines mechanisms for the OP to notify RPs of logout. They solve **session logout propagation**, not OAuth token revocation by themselves.

### 9.1. Front-Channel Logout

The OP can open/embed RP logout URLs in the browser (e.g., via iframes) so RPs destroy their sessions. Each RP relies on browser cookies/sessions to locate the session to end.

Limitations:

- Browsers may block third-party cookies or iframe tracking.
- Some browsers block cross-site cookies, preventing RPs from finding the session.
- Users closing the tab or network failures can prevent some RPs from receiving the notification.
- Unsuitable as a guarantee for revoking access tokens at APIs.

### 9.2. Back-Channel Logout

The OP sends a **Logout Token** to the RP over a back-channel. The RP verifies the token per OIDC Back-Channel Logout and locates the session to destroy. A Logout Token is a JWT protocol message with its own contract, including checks for issuer, audience, issued-at time, `jti`, the `events` claim, and `sid` or `sub`; it must never be accepted merely because it has a valid JWT signature.

A Logout Token **is not an access token** and must never be used as a Bearer credential for the Orders API. It is a logout notification message.

### 9.3. `sid` and `sub`

- `sid` identifies a specific OP session; the RP can map it to corresponding local sessions.
- `sub` identifies the subject within the issuer's scope; if `sid` is absent, policy may apply logout to the subject's sessions per the spec and app requirements.
- Mapping keys should be namespaced by issuer, since `sid`/`sub` are not necessarily globally unique.

### 9.4. Back-Channel Logout Diagram

~~~mermaid
sequenceDiagram
    participant U as User
    participant OP as OpenID Provider
    participant RP1 as orders-web
    participant RP2 as billing-web
    participant API as orders-api
    U->>OP: Logout at OP
    OP->>RP1: POST Logout Token (back-channel)
    OP->>RP2: POST Logout Token (back-channel)
    RP1->>RP1: Verify Logout Token + find sid/sub
    RP2->>RP2: Verify Logout Token + find sid/sub
    RP1->>RP1: Invalidate local session
    RP2->>RP2: Invalidate local session
    Note over API: Issued access tokens need separate revocation/introspection/denylist
~~~

### 9.5. Why Does a Logout Notification Not Automatically Revoke Access Tokens?

A back-channel logout message states that an OP session must be logged out at an RP. A Resource Server might not be an RP, holds no browser session, and never receives the logout token. If the RS only verifies JWTs offline, it has no idea the OP just sent a message to `orders-web`.

If you want logout events to invalidate access tokens, the system needs a **controlled bridge**: map OP sessions/grants to token IDs or principal/session state, emit revoke events to RSs/denylists/introspection stores, and scope which tokens are revoked. Never use logout notifications to blindly wipe every token sharing a `sub` if the user has multiple independent clients, devices, or grants.

## 10. Integrating Logout in Spring Security Servlet

An application can act as both an OAuth2/OIDC client (`oauth2Login`) and a Resource Server. Distinguish **local web session logout**, **OP logout redirect**, and **access-token revocation**.

### 10.1. OIDC Client-Initiated Logout

Spring Security provides `OidcClientInitiatedLogoutSuccessHandler` for Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
public class WebLogoutConfiguration {

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {
        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        // URI must be registered/permitted at OP.
        handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");
        return handler;
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/logged-out").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> {})
            .logout(logout -> logout
                .logoutSuccessHandler(oidcLogoutSuccessHandler))
            .build();
    }
}
~~~

This example demonstrates **RP-Initiated Logout** in Spring Security Servlet. `ClientRegistrationRepository` provides metadata/registration, and the handler can include an ID token hint when appropriate. The `{baseUrl}/logged-out` URI must match the OP registration and reverse proxy/base URL configuration. Depending on Spring Security version, exact APIs/packages may differ; check the reference docs for your dependency version.

This handler performs the OP logout redirect. It **does not automatically prove** all access tokens have been revoked. If the app needs to revoke refresh/access tokens, add a step calling the revocation endpoint before or during the logout workflow while the server still holds the tokens.

### 10.2. Local Logout and Authorized-Client Cleanup

Spring Security OAuth2 Client can store `OAuth2AuthorizedClient` in an `OAuth2AuthorizedClientRepository` or `OAuth2AuthorizedClientService`. Removing the authorized client from the local store stops the app from continuing to retrieve tokens from that store:

~~~java
authorizedClientService.removeAuthorizedClient(
    registrationId,
    principalName
);
~~~

This call is **local cleanup**. It does not automatically send an RFC 7009 revocation request to the Authorization Server. To revoke, first retrieve the available access/refresh tokens, call the proper AS endpoint, handle the response, and then delete local copies/sessions per policy.

Never put tokens in logs or URLs. For confidential clients, revocation requests generally must be authenticated server-side; never send a client secret from the browser.

### 10.3. Illustrative Revocation Service

An application can use `WebClient` or an appropriate HTTP client to call the revocation endpoint per provider contract. Conceptual `WebClient` example:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public final class TokenRevocationClient {

    private final WebClient webClient;
    private final String revocationUri;

    public TokenRevocationClient(
            WebClient webClient,
            String revocationUri) {
        this.webClient = webClient;
        this.revocationUri = revocationUri;
    }

    public Mono<Void> revokeRefreshToken(String refreshToken) {
        return webClient.post()
            .uri(revocationUri)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                    "token", refreshToken)
                .with("token_type_hint", "refresh_token"))
            .retrieve()
            .toBodilessEntity()
            .then();
    }
}
~~~

This only illustrates the HTTP form part. Production requires configuring client authentication per the AS (e.g., HTTP Basic or another method), TLS, timeouts, bounded retries, and handling 400/401/429/5xx statuses. Do not assume every provider allows unauthenticated revocation. Never log the form body because it contains the refresh token.

If using `WebClient` in a Servlet app, revocation can be composed asynchronously in an appropriate service/handler; never call `block()` casually on request threads. If a logout handler requires a synchronous API, choose an integration aligned with the execution model and bound timeouts.

### 10.4. Recommended Logout Sequence

~~~text
POST /logout (CSRF-protected for browser session)
  |
  +-- Retrieve authorized client/tokens from server-side store
  |
  +-- Send RFC 7009 revoke(refresh token) if policy requires
  |
  +-- Send revoke(access token) if AS supports/requires it
  |
  +-- Invalidate local session + SecurityContext
  |
  +-- Clear cookie and local authorized-client record
  |
  +-- RP-Initiated Logout redirect to OP if needed
  |
  +-- Render logged-out page
~~~

The exact order depends on whether tokens remain accessible after session invalidation. To call revocation, keep credentials inside a secure server-side logout context long enough to send the request. If the AS is unavailable, decide whether local logout completes immediately while flagging revocation as unconfirmed, or waits for a short timeout. **Never leave the user logged in indefinitely waiting on the AS.**

### 10.5. Logout Endpoints Must Protect Against CSRF

For browser sessions/cookies, logout is a state-changing operation. Use POST and CSRF protection as configured; never expose a GET `/logout?user=...` that lets another site force a user to log out or trigger revocation. RP logout redirects must validate `state`/redirect URIs per the flow.

## 11. Spring Security WebFlux: Logout and Token Cleanup

WebFlux uses `SecurityWebFilterChain`, `ServerHttpSecurity`, and reactive logout handlers. When the app is an OIDC client, Spring Security provides `OidcClientInitiatedServerLogoutSuccessHandler` for RP-Initiated Logout in the reactive stack on supported versions.

### 11.1. Reactive OIDC Logout Handler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout
    .OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout
    .ServerLogoutSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveWebLogoutConfiguration {

    @Bean
    ServerLogoutSuccessHandler oidcLogoutSuccessHandler(
            ReactiveClientRegistrationRepository registrations) {
        OidcClientInitiatedServerLogoutSuccessHandler handler =
            new OidcClientInitiatedServerLogoutSuccessHandler(
                registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");
        return handler;
    }

    @Bean
    SecurityWebFilterChain webChain(
            ServerHttpSecurity http,
            ServerLogoutSuccessHandler oidcLogoutSuccessHandler) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/logged-out").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> {})
            .logout(logout -> logout
                .logoutSuccessHandler(oidcLogoutSuccessHandler))
            .build();
    }
}
~~~

This is a template for a WebFlux/OIDC client; check exact classes, packages, and builders for your Spring Security version. The handler manages the logout redirect to the OP; it does not automatically revoke all issued access/refresh tokens.

### 11.2. Removing Reactive Authorized Clients Locally

In a reactive OAuth2 Client, `ReactiveOAuth2AuthorizedClientService` can remove the authorized client:

~~~java
return authorizedClientService
    .removeAuthorizedClient(registrationId, principalName);
~~~

This removes the local authorized-client record. It does not automatically call the revocation endpoint. If revocation is needed, fetch the token before removal and compose a reactive HTTP POST to the AS endpoint.

### 11.3. Do Not Block in WebFlux Logout

Never call:

~~~java
revocationClient.revoke(token).block();
~~~

on the Netty event loop. Compose `Mono`/`then`/`flatMap` inside the logout workflow, or use an intentional blocking boundary only where required. Never call `subscribe()` fire-and-forget and finish the response before knowing whether the revocation request was even sent.

### 11.4. Pure WebFlux API Resource Servers May Have No Logout Session

A stateless API accepting only Bearer tokens may not need a `/logout` endpoint because the API owns no client session. Logout/revocation is typically performed by the OAuth client at the AS. The Resource Server still needs a way to detect revoked tokens if the SLA requires stopping them before `exp` (opaque introspection, denylists, events).

Never add a logout endpoint to an API solely to clear a per-request `SecurityContext`: a stateless request's `SecurityContext` is not a central token store, and clearing it does not revoke the token elsewhere.

## 12. Client-Side Logout: SPA, Mobile, and BFF

### 12.1. SPA Holding Tokens in Memory

If an SPA keeps access tokens in memory, reloading or closing the tab drops its local copy. Yet a token already sent to an API may still remain valid. Logout should:

- Clear tokens from memory/state.
- Cancel refresh timers and pending requests.
- Clear local user/session data.
- Call the revocation endpoint via an AS-supported flow if needed.
- Redirect to OP logout if the app needs to end SSO.

Never ship a client secret in a JavaScript bundle. A public SPA cannot hold long-lived secrets; revocation endpoint authentication must follow the AS's public-client policy.

### 12.2. Tokens in localStorage/sessionStorage

Deleting a token from storage only removes **the copy in the current browser origin**. It does not delete copies in logs, extensions, malware, other tabs, backend caches, or places an attacker already exfiltrated. XSS can read tokens stored in JavaScript-accessible storage.

Never use "localStorage is empty" as proof a token was revoked. Consider a BFF, memory storage, CSP, cookie flags, and shorter access-token lifetimes.

### 12.3. BFF Holding Tokens Server-Side

A Backend-for-Frontend can store access/refresh tokens in a server-side authorized-client store while the browser holds only a session cookie:

~~~text
Browser -- HttpOnly session cookie --> BFF
BFF -- access token --> Orders API
~~~

Logout:

1. BFF fetches tokens/authorized client from the server-side session.
2. BFF calls the revocation endpoint per policy.
3. BFF deletes the authorized-client record.
4. BFF invalidates the session/cookie.
5. BFF may initiate OP logout.

A BFF reduces token exposure in browser JavaScript, yet **does not automatically revoke tokens**. If a refresh or access token leaked from the backend, corresponding revocation/resource-server enforcement is still required.

### 12.4. Mobile Apps

Mobile apps may store tokens in OS secure storage. Logout should clear local credentials, call revocation if supported by the provider, and handle the OP session/SSO per the SDK. Uninstalling the app or wiping the keychain does not revoke previously copied tokens.

### 12.5. Multiple Tabs and Multiple Devices

A user may have:

~~~text
Phone session A -> refresh family A
Laptop session B -> refresh family B
Tablet session C -> refresh family C
~~~

Logging out on a laptop does not necessarily log out the phone or tablet. Conversely, "Sign out everywhere" requires a user/session/grant-level mechanism at the OP/AS to define scope and emit corresponding events. Never revoke just the current access token and claim every device was logged out.

## 13. Logout, Revocation, and Privacy/Latency

### 13.1. Local Logout Should Be Fast

Users need to exit the app even if the AS is temporarily unavailable. A sensible UX pattern:

- Delete local session/cookies right after safely capturing the token info needed for revocation.
- Execute revocation with a finite timeout.
- If revocation is confirmed, record success.
- If the AS is unavailable, keep the local logout complete and report that server-side revocation is unconfirmed; retry via a secure server-side mechanism if policy permits.

Never keep a user logged in just because a revoke endpoint hangs. At the same time, never claim "all tokens invalidated" when revocation was not confirmed.

### 13.2. Do Not Arbitrarily Persist Raw Tokens for Retries

If revocation must be retried after logout, storing raw tokens to resend later is a security risk. Prefer running within the same server-side workflow with timeouts and idempotency per contract. If queuing is unavoidable, protect payloads like credentials—encrypt, limit retention, enforce access control, and purge after completion.

Never send tokens to dead-letter queues, logs, or telemetry. In some designs, you can store a reference/grant ID to ask the AS to revoke the grant instead of retaining raw tokens, if the AS provides a secure management API.

### 13.3. Revocation and Privacy

Logout/revocation events may carry `sub`, `sid`, grant ID, token ID, or tenant. These are identifying/sensitive data. Share only the minimum necessary, protect event transport, and limit retention. Never broadcast a global "logout user 842" event if the actual semantics are only logging out a single session of one client.

## 14. Caches, Replicas, and Revocation Time Bounds

A distributed API may have multiple instances and caches:

~~~text
AS revocation DB
    |
    +--> Introspection node A
    +--> Introspection node B

Resource Server:
    +--> RS instance 1 / cache 1
    +--> RS instance 2 / cache 2
    +--> RS instance 3 / cache 3
~~~

When revoked:

- The AS database may update immediately.
- Introspection replicas may experience replication lag.
- RS caches may hold `active=true`.
- Denylist events may arrive late or be dropped.
- A downstream service may cache `Authentication` separately.

### 14.1. Defining a Revocation SLA

Avoid the word "immediate" without defining it:

| Mechanism | Typical bound |
|---|---|
| Offline JWT, no denylist/events | Up to `exp` (plus clock skew) |
| JWT + synchronous denylist per request | Governed by store consistency/availability |
| JWT + event-driven denylist | Governed by event propagation/cache invalidation |
| Uncached opaque introspection | Governed by AS revocation visibility + request latency |
| Opaque introspection with 60s cache TTL | Potentially nearly 60s without invalidation |
| Opaque introspection + event invalidation | Governed by delivery/invalidation SLA, with TTL as fallback |

Example policy:

~~~text
Sensitive payment API:
  max revocation delay <= 5 seconds
  -> requires online status or strongly propagated denylist

General read API:
  max revocation delay <= remaining short access-token TTL
  -> short-lived JWT may be acceptable
~~~

These numbers are illustrative product choices, not Spring Security defaults.

### 14.2. Clock Skew and `exp`

If a validator allows 60 seconds of clock skew, a token can remain accepted slightly past its `exp` timestamp. When setting short TTLs to bound the logout window, factor in clock skew and clock drift between the AS and RS.

### 14.3. JWKS Cache Is Not a Token Revocation Cache

Removing a key from JWKS stops the RS from verifying signatures of tokens signed by that key, yet this is a broad **key rotation/compromise response**, not how you revoke a single access token. JWKS cache TTL can alter how long keys stay trusted. Never rotate signing keys on every user logout.

## 15. Spring Security Resource Server: How the RS Learns About Revocation

### 15.1. Default JWT Decoders Do Not Query the AS per Request

Configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
          audiences:
            - orders-api
~~~

enables the Resource Server to verify JWTs by issuer/audience and corresponding validators. It does not automatically query an RFC 7009 endpoint after user logout. If revoked tokens must be rejected promptly, add a mechanism such as:

- `jti` denylist/revocation store.
- Introspection instead of offline JWTs (if the AS supports that token type/profile).
- Revocation events from the AS.
- Very short access token lifetimes paired with refresh token revocation.
- A centralized gateway/policy service checking status.

### 15.2. Opaque Token Introspection

Servlet configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

When the AS returns `active=false` after revocation, the Resource Server can reject the token on the next introspection call. Still, verify caches, timeouts, and the real implementation; never assume merely configuring opaque tokens disables all caching.

### 15.3. Do Not Use ID Tokens or UserInfo to Check Revocation

A valid ID token or a 200 from UserInfo does not prove the access token used for the Orders API is still active. Conversely, a revoked access token does not mean the OP deleted all profile claims or the ID token in the client session. These endpoints have different contracts.

## 16. `jti` Denylist Pattern for JWTs

If JWTs must be revoked before `exp` without calling introspection on every request, a denylist can be added at the authentication/authorization layer. Model:

~~~java
public interface RevokedTokenStore {
    Mono<Boolean> isRevoked(String issuer, String jwtId);
}
~~~

For synchronous Servlet code, the interface can return `boolean`; for WebFlux, return `Mono<Boolean>` and use reactive storage. Never make blocking Redis/DB calls on the event loop.

### 16.1. Conceptual Policy

~~~java
public Mono<Authentication> authenticateWithRevocationCheck(
        Mono<Authentication> authentication) {
    return authentication.flatMap(auth -> {
        if (!(auth instanceof JwtAuthenticationToken jwtAuth)) {
            return Mono.error(
                new BadCredentialsException("JWT authentication required"));
        }

        Jwt jwt = jwtAuth.getToken();
        String issuer = jwt.getIssuer().toString();
        String jti = jwt.getId();

        if (jti == null || jti.isBlank()) {
            return Mono.error(
                new BadCredentialsException("JWT ID is required"));
        }

        return revokedTokenStore.isRevoked(issuer, jti)
            .flatMap(revoked -> revoked
                ? Mono.error(new BadCredentialsException(
                    "Access token is revoked"))
                : Mono.just(auth));
    });
}
~~~

This is a **policy pattern**, not a complete filter/manager you can paste directly into every Spring Security version. Integrate it into the appropriate authentication pipeline and handle error mapping. In Servlet, use the synchronous counterpart or an intentional filter/provider extension; in WebFlux, compose it into the reactive chain.

### 16.2. Updating the Denylist on Logout/Revocation

A trusted revocation service can:

1. Verify the logout request and extract `iss`, `jti`, and `exp` from the verified `Authentication`.
2. Call the AS revocation endpoint per policy if needed.
3. Write the denylist key `(issuer, jti)` with a TTL until token expiration.
4. Emit invalidation events to all RSs/caches.
5. Audit the outcome without logging raw tokens.

**Never accept a `jti` from a request body as the target of revocation** without binding it to an `Authentication`/grant that the caller is authorized to manage. If a client is permitted to revoke its own token, the AS usually has the authoritative permissions and metadata.

### 16.3. What If the Store Is Unavailable?

If policy demands prompt revocation, an unavailable denylist store means the RS cannot verify the token has not been revoked. A fail-closed option rejects or returns service-unavailable for protected operations. Failing open preserves availability but breaks the revocation SLA; that decision must be documented in the threat model, never chosen silently.

## 17. Testing Logout and Token Revocation

A test asserting `logout returns 302` only proves redirect/session behavior. It does not prove access tokens were revoked.

Separate testing into layers:

1. **RP local logout:** session invalidated, cookie cleared, `SecurityContext` gone.
2. **OIDC RP-Initiated Logout:** OP logout redirect has the right endpoint/parameters.
3. **RFC 7009 client behavior:** client sends the proper token, token type hint, and client authentication.
4. **AS behavior:** access/refresh tokens revoked per provider contract.
5. **RS enforcement:** requests with the old token are rejected within the chosen SLA.
6. **Propagation:** caches/events/replicas receive revocation state.

### 17.1. Test Matrix

| Test | Expectation |
|---|---|
RP local logout | Old session is no longer usable |
Old cookie replayed | `Authentication` is not restored from invalidated session |
RP-Initiated Logout | Redirects to the right `end_session_endpoint`; registered redirect URI |
Logout request subject to CSRF | Rejected per CSRF policy |
Revoke refresh token | AS acknowledges per RFC 7009; old refresh token cannot issue new tokens |
Revoke opaque access token | Post-revocation introspection returns inactive |
Revoke offline JWT | RS may still accept until `exp` without denylist/events; test should expose this limit |
JWT denylist update | Token `jti` is rejected across all RS instances after propagation |
Introspection cache | Token is rejected after invalidation or advertised max TTL |
AS timeout during logout | Local logout still completes per policy; revocation status is not falsely reported as succeeded |
Refresh token reuse | AS enforces family/reuse policy; token family handled properly |
Back-channel logout | Logout Token verified, valid `iss`/`aud`/`events`, sessions matching `sid`/`sub` destroyed |
Multi-device user | Logging out one session does not accidentally clear or keep sessions outside policy |
Service/client credentials | Does not require UserInfo/ID token to process M2M access tokens |

### 17.2. Testing Tokens Before and After Revocation

Integration test with an opaque token:

~~~text
1. Obtain access token T from test AS.
2. Send T to /api/orders -> 200.
3. Call RFC 7009 revoke(T) with authorized client.
4. Resend the same T to /api/orders.
5. Expect 401 after introspection/cache propagation takes effect.
~~~

With an offline JWT:

~~~text
1. Obtain JWT T with distant exp.
2. Send T to /api/orders -> 200.
3. Call revoke(T) at AS.
4. Resend T to RS using signature/claims offline only.
5. May still return 200 until exp (without denylist/event).
6. If design uses jti denylist, after denylist update -> 401.
~~~

This test is essential because it prevents teams from claiming that RFC 7009 alone makes an offline JWT disappear across every Resource Server.

### 17.3. MockMvc/WebTestClient with Mock Authentication Is Not Enough

`mockJwt()` or `jwt()` creates a simulated `Authentication`, bypassing real decoders, opaque introspection, and revocation lookups. They are fine for testing HTTP authorization, yet proving old tokens are rejected requires sending a real Bearer token through the filter chain and running production-like decoders, introspectors, and revocation stores (with test keys/test AS).

### 17.4. Testing Back-Channel Logout Tokens

Required cases:

- Logout Token signed by trusted OP, valid issuer/audience, `events` contains back-channel logout event, and valid `jti` → invalidates session.
- Wrong signature/issuer/audience → rejected.
- Invalid `nonce` present per logout token spec → rejected.
- Non-existent `sid` → handled idempotently.
- Duplicate `jti`/notification → produces no dangerous repeated side effects.
- `sid` belonging to a different issuer with the same string → does not delete the wrong issuer's session.
- Logout event only invalidates the RP session; test access-token revocation separately if required by the system.

## 18. Common Mistakes

| Misconception / anti-pattern | Why it is wrong | Right approach |
|---|---|---|
"Deleting the cookie expires the token" | Only deletes the local session | Revoke tokens/grants if needed and ensure RS observes it |
"OP logout auto-revokes all access tokens" | SSO sessions and tokens have separate lifecycles | Combine RP logout with RFC 7009 / RS enforcement |
"200 on revoke endpoint proves an active token was deleted" | RFC 7009 returns 200 even for invalid tokens | Understand response semantics; test RS enforcement |
"A revoked JWT fails signature validation" | Signature remains valid until key/token validation changes | Denylist/event/introspection or short TTL |
"Revoking the refresh token is immediately sufficient" | Old access tokens can remain alive | Revoke related access tokens or enforce at RS |
"UserInfo returning 200 means the API access token is active" | UserInfo and API resources differ | Use introspection or JWT access-token validation |
"The ID token hint is the token to revoke" | `id_token_hint` serves OIDC logout | Call RFC 7009 separately |
"Back-channel logout removes JWTs from all APIs" | Usually destroys RP sessions, does not auto-update RSs | Bridge events/denylists/introspection if needed |
"Logging out one device logs out all devices" | Sessions/grants/token families may be independent | Define session/grant scope explicitly |
"Deleting the local authorized client revokes at the AS" | Only deletes local store | Call the revocation endpoint explicitly |
"If the AS is down, let tokens pass so users can log out" | Fail-open grants access to unverified tokens | Complete local logout quickly, keep APIs fail closed |
"Using `sub` to revoke all tokens of a user" | Can wipe tokens of other clients/devices/grants | Use exact grant/session/token identifiers and policies |
"Rotating JWKS keys on every logout" | Affects many tokens/clients; not per-token revocation | Denylist or introspection |
"Logout endpoint uses GET without CSRF" | Can be forced to log out/revoke from another site | POST + CSRF/session policy |
"Keeping raw tokens in logs for debugging" | Bearer tokens are replayable credentials | Log sanitized IDs and statuses |

## 19. Designing Logout by Assurance Level

Not every application needs the same complexity. Determine the **assurance level** before choosing techniques.

### Level 1 — App-Only Logout

Suitable when the requirement is merely that the user stops using the application session:

- Invalidate RP session.
- Clear cookies/token cache.
- Redirect to logged-out page.
- Accept that access tokens may remain valid until `exp`.

Do not claim immediate token revocation.

### Level 2 — SSO Logout and Preventing New Access Tokens

Suitable when the OP session must end and further refreshes must stop:

- Local RP logout.
- RP-Initiated Logout to OP.
- Revoke refresh token or grant per provider support.
- Handle front/back-channel logout for related RP sessions.
- Old access tokens may live until `exp` if the RS is offline.

### Level 3 — Short-Window Access Token Revocation

Suitable for APIs with sensitive data or operations:

- RFC 7009 revoke access/refresh tokens or grants.
- Opaque introspection with clear TTL/cache policy, or JWT denylist.
- Revoke events/invalidation to shrink lag.
- Resource Server fails closed when state cannot be determined within SLA.
- Integration tests measuring time from revocation to rejected requests.

### Level 4 — Sign Out All Sessions/Devices and Incident Response

Suitable for account compromise or administrative user disablement:

- AS manages sessions/grants/token families and revokes by subject/client/device.
- Back-channel logout to all RPs.
- Revoke refresh token families and associated access tokens.
- Propagate token revocation to Resource Servers.
- Clear BFF/session/authorized-client caches.
- Auditing, rate limiting, idempotency, event delivery, and recovery.
- Distinguish "log out one session," "log out all clients," and "disable account."

A UI button may always say "Logout," yet the backend must know **which level** the user is requesting.

## 20. Implementation Checklist

### 20.1. Client / RP Side

- [ ] Invalidate local server-side session.
- [ ] Clear `SecurityContext` and cookies with matching domain/path.
- [ ] Remove access/refresh tokens from local storage/caches.
- [ ] Prevent in-flight refresh requests from persisting new tokens after logout.
- [ ] Call RFC 7009 for refresh/access tokens per policy and AS support.
- [ ] Never expose client secrets in SPAs or mobile apps.
- [ ] Initiate RP-Initiated Logout when SSO logout is required.
- [ ] Validate `state` and registered post-logout redirect URIs.
- [ ] Use POST and CSRF protection for browser logout.
- [ ] Never report "all tokens revoked" when only clearing the local session.

### 20.2. Authorization Server Side

- [ ] Publish revocation endpoint and client authentication requirements.
- [ ] Define revocation semantics for access tokens, refresh tokens, and grants.
- [ ] Implement refresh-token rotation and reuse detection where appropriate.
- [ ] Support session/grant management for "sign out everywhere" if required.
- [ ] Support back-channel logout endpoint registration when RP session propagation is needed.
- [ ] Emit authenticated revoke events if RSs need to update denylists/caches.
- [ ] Ensure 200/503 responses and errors conform to RFC/provider contracts.

### 20.3. Resource Server Side

- [ ] JWT validation verifies signature, issuer, audience, timestamps, and token profile.
- [ ] Decide whether offline JWTs accept a window up to `exp` or require early revocation.
- [ ] If opaque, define introspection `active` handling and cache TTLs.
- [ ] If using a denylist, use issuer-scoped `jti`/fingerprints and TTLs.
- [ ] If event-driven, verify event origin, idempotency, and propagation.
- [ ] Enforce fail-closed policies on sensitive APIs when revocation state is unknown.
- [ ] Enforce scope, tenant, owner, and object-level authorization independently.
- [ ] Never treat ID tokens, UserInfo, or OP logout events as access-token validation.
- [ ] Never log raw access/refresh/ID tokens.

### 20.4. Operations and Testing

- [ ] Measure maximum revocation delay, not merely endpoint 200 latency.
- [ ] Test multiple RS instances and cache nodes.
- [ ] Test AS timeouts/5xx responses and retries.
- [ ] Test refresh-token reuse and concurrent refreshes.
- [ ] Test single-session logout vs. sign-out-everywhere.
- [ ] Test that revoked JWTs still pass offline unless a denylist exists.
- [ ] Test that revoked opaque tokens transition to `active=false`.
- [ ] Test Back-Channel Logout Tokens and duplicate events.
- [ ] Monitor 401/403 rates, introspection latency, cache hits, and revocation propagation.

## 21. Decision Diagram: Choosing a Revocation Strategy

~~~mermaid
flowchart TD
    A["Logout request"] --> B{"Only need to end app session?"}
    B -->|"Yes"| C["RP local logout + clear cookie/token cache"]
    B -->|"No"| D{"Need to end SSO session?"}
    D -->|"Yes"| E["RP-Initiated Logout / Front-Back Channel"]
    D -->|"No"| F["Keep OP session per policy"]
    E --> G{"Need to prevent issuing new access tokens?"}
    F --> G
    G -->|"Yes"| H["Revoke refresh token / grant per RFC 7009"]
    G -->|"No"| I["Access token lives until exp per contract"]
    H --> J{"Does RS need to reject old access token before exp?"}
    J -->|"No"| K["Short TTL + stop refreshing"]
    J -->|"Yes"| L{"Token type"}
    L -->|"Opaque"| M["Introspection + cache/invalidation"]
    L -->|"JWT"| N["jti denylist / revoke events / online state"]
    M --> O["Measure propagation and fail-closed"]
    N --> O
    K --> P["Test remaining validity window"]
    C --> Q["Do not claim tokens are revoked"]
~~~

## 22. Conclusion

~~~text
LOGOUT LIFECYCLE

CLIENT / RP LOGOUT
  invalidate local session
  clear cookie / local token copy
  optionally redirect to OP logout
          |
          v
OIDC OP LOGOUT
  end_session_endpoint
  front-channel / back-channel notifications
  primarily terminate SSO / RP sessions
          |
          v
OAUTH TOKEN REVOCATION (RFC 7009)
  revoke access token / refresh token / grant
          |
          v
RESOURCE SERVER ENFORCEMENT
  opaque introspection active=false
  JWT denylist / revoke event / online state
  or wait until short exp

LOCAL LOGOUT != TOKEN REVOCATION
OP SESSION LOGOUT != ACCESS TOKEN INVALIDATION
REVOCATION REQUEST != INSTANT RS ENFORCEMENT
~~~

**Client-side logout only guarantees the client/RP ends its local session if that is all the application performs.** RP-Initiated Logout ends the OIDC SSO session; Front/Back-Channel Logout helps RPs receive notifications and destroy sessions. OAuth 2.0 Token Revocation under RFC 7009 is what requests the AS to revoke access/refresh tokens. Even after the AS revokes a token, a Resource Server validating JWTs offline can keep accepting it until `exp` unless a denylist, event propagation, or online state check is in place.

Therefore, a reliable logout lifecycle must clearly define **token/grant/session scope**, revoke refresh tokens to stop new token issuance, and choose how Resource Servers observe revocation within SLA. Always test old tokens **after** logout through the real production-like filter chain, decoder, and introspector; a successful redirect or deleted cookie never proves an access token has stopped working.

## References

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint, `token_type_hint`, client authentication, and response semantics.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, refresh tokens, grants, and token endpoint.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` and metadata for Resource Servers.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, and `state`.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): browser/front-channel logout notifications.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token, `sid`, `sub`, event claim, and RP session invalidation.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `jti`, and JWT claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): token validation, issuer/audience, and cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC client login.
- [Spring Security Reference — Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout, logout handlers, and success handlers.
- [Spring Security API — OidcClientInitiatedLogoutSuccessHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html): Servlet RP-Initiated Logout handler.
- [Spring Security Reference — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): WebFlux OIDC client login.
- [Spring Security Reference — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): reactive local logout.
- [Spring Security API — OidcClientInitiatedServerLogoutSuccessHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/web/server/logout/OidcClientInitiatedServerLogoutSuccessHandler.html): WebFlux RP-Initiated Logout handler.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer/audience validation.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and principal.
- [Spring Security Reference — Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): WebFlux JWT/opaque token resource server.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation, cookies, and logout.
