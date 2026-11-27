# Evaluating Front-Channel vs. Back-Channel Logout Needs and Required Extensions

## 1. Why Must Multi-Application Logout Be Evaluated?

An OpenID Provider (OP) may serve multiple Relying Parties (RPs): a portal, an admin console, a mobile backend, and internal applications. Users log in once at the OP and then create independent sessions at each RP. When the OP ends the SSO session, the RPs may still keep their own cookies/sessions.

**Single Logout (SLO)** is the requirement to coordinate terminating related sessions across multiple RPs. OpenID Connect defines complementary mechanisms to address this problem:

- **RP-Initiated Logout:** an RP asks the OP to terminate the SSO session, usually via a browser redirect to `end_session_endpoint`.
- **Front-Channel Logout:** the OP uses the browser/User Agent to invoke each RP's logout URI, typically through iframes.
- **Back-Channel Logout:** the OP sends an HTTP request directly from server to RP server, carrying a signed Logout Token.
- **Session Management:** the RP monitors OP session status through a browser/iframe mechanism and detects session changes.

Not every system needs to implement all four. The design questions are: **which RPs need their sessions terminated, how reliable must delivery be, over which channels are RPs reachable, and which roles does the framework already support?**

This lesson belongs to the **OIDC Logout** chapter of the `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER` module, aiming to evaluate choosing between Front-Channel and Back-Channel and identify the parts needing extension in Spring Security/Spring Authorization Server applications.

After this lesson, you will be able to:
1. Define SLO requirements across applications, browsers, devices, and tenants.
2. Compare Front-Channel and Back-Channel across reliability, reachability, and operations.
3. Understand metadata, client registration, and how the OP tracks logged-in RPs.
4. Validate Logout Tokens and map `iss`, `aud`, `sub`, and `sid` to local sessions.
5. Identify out-of-the-box Spring Security support and extension boundaries in Spring Authorization Server.
6. Design fan-out, retries, replay protection, session registries, and observability.
7. Write tests proving logout targets the right session and client without deleting other users' sessions.

## 2. Distinguishing Logout Mechanisms

| Mechanism | Initiator | Transport | Primary Effect |
| --- | --- | --- | --- |
| RP-Initiated Logout | RP | Browser redirect to OP | Asks OP to end the SSO session |
| Front-Channel Logout | OP | Browser, usually via iframes | Calls logout URIs at each RP |
| Back-Channel Logout | OP | Server-to-server HTTP | Sends a Logout Token so the RP ends sessions |
| Session Management | RP and OP | Browser/iframe | Detects OP session state changes |
| Local logout | RP | Internal to application | Deletes the RP's current session |

These mechanisms can be combined. For example, a user clicks logout in Portal:
1. Portal ends its local session.
2. Portal navigates the browser to the OP using RP-Initiated Logout.
3. The OP ends the SSO session.
4. The OP notifies other RPs via Back-Channel Logout or Front-Channel Logout.
5. Each RP ends its corresponding local session.

**RP-Initiated Logout does not automatically execute Front-Channel or Back-Channel Logout.** It is only a request from the RP to the OP. The OP notifying other RPs is a separate capability that the OP and RPs must implement, register, and test.

### 2.1. Two Coordination Flows

~~~mermaid
flowchart LR
    U[User] --> P[Logout-initiating RP]
    P -->|Browser redirect| O[OpenID Provider]
    O --> S[End OP session]
    S --> F[Front-channel fan-out]
    S --> B[Back-channel fan-out]
    F -->|Browser iframe| R1[RP A]
    F -->|Browser iframe| R2[RP B]
    B -->|HTTP POST + Logout Token| R1
    B -->|HTTP POST + Logout Token| R2
    R1 --> L1[Invalidate local session]
    R2 --> L2[Invalidate local session]
~~~

Front-channel and back-channel are two distinct notification branches. An OP may enable one, both, or neither; metadata must accurately reflect active capabilities.

## 3. Deciding When Front-Channel Logout Is Needed

Front-Channel Logout is suitable when:
- RPs are primarily browser applications and local logout can be executed via a browser request.
- RPs lack a back-channel endpoint that is public/reachable from the OP.
- You want to leverage existing cookies and browser sessions to clear client-side state.
- The system has few RPs, browser support has been verified, and iframe limitations are acceptable.
- You need to notify legacy applications that only expose an HTTP logout URL.

Front-channel is **not the sole best choice** when guaranteed system-wide logout is required. The OP needs an active browser, and the browser must allow iframes to access the RP's state.

### 3.1. Metadata and Client Registration

An RP supporting Front-Channel Logout registers metadata:
- `frontchannel_logout_uri`: URL at the RP for the OP to open inside an iframe.
- `frontchannel_logout_session_required`: whether the RP requires `iss` and `sid` to identify the session; defaults to `false` if omitted.

The OP advertises in OpenID Provider Configuration:
- `frontchannel_logout_supported`: whether the OP supports Front-Channel Logout; defaults to `false` if absent.
- `frontchannel_logout_session_supported`: whether the OP can send `iss` and `sid` to identify the RP session; defaults to `false` if absent. When supported, `sid` is also included in ID Tokens.

The RP logout URI must be an absolute URI with no fragment. Its scheme, host, and port MUST match the scheme, host, and port of one of the client's Registered Redirect URIs per the specification. Use HTTPS in production.

### 3.2. OP Sends Requests via Iframes

When the OP ends a session, it looks up logged-in RPs and renders a page containing iframes pointing to each `frontchannel_logout_uri`. If session-aware mode is enabled, the OP can include both `iss` and `sid`:

~~~http
GET /oidc/front-channel-logout?iss=https%3A%2F%2Fauth.example.com&sid=SID_VALUE HTTP/1.1
Host: portal.example.com
~~~

If the OP sends either `iss` or `sid`, it **must send both**. `sid` is an opaque session identifier unique within the issuer's scope; the RP must not interpret its structure or use it as a credential.

The RP can match `iss` and `sid` against the ID Token issued for the current or recent session. If they do not match, the RP may ignore the request.

### 3.3. What Must the RP Do at the Front-Channel URI?

The endpoint receiving the iframe request should:
1. Verify the request targets the registered logout route and parse query parameters per contract.
2. If `iss`/`sid` are present, match against the appropriate session mapping.
3. End the corresponding RP session or all sessions for the subject per agreed policy.
4. Clear related state/cookies/local storage controlled by the RP.
5. Return a response with `Cache-Control: no-store`.
6. Handle idempotently: if the session is already gone, treat logout as completed.

Do not prompt the user to log in again or display a confirmation page inside the iframe. Also never return personal data, tokens, or sensitive content from the logout URI.

### 3.4. Browser and Cookie Limitations

Front-channel depends on the browser:
- Browsers may block third-party cookies inside iframes.
- `SameSite=Lax` or `SameSite=Strict` cookies may not be sent in cross-site iframe contexts.
- Storage partitioning can prevent the iframe from seeing state created by the top-level RP.
- Content Security Policy, frame policies, and browser tracking prevention can block or alter behavior.
- Tabs/browsers may be closed or navigated away before the OP finishes fan-out.

Therefore, an iframe request may reach the RP while the RP cannot read the cookie/session to delete. The spec recommends defensive handling to detect when logout could not be performed and notify appropriately when possible.

Do not disable CSP or relax global cookie policies solely to make iframe logout work. Evaluate security and privacy impacts before making changes.

## 4. Deciding When Back-Channel Logout Is Needed

Back-Channel Logout is suitable when:
- Logout notifications must be more reliable than browser-based delivery, including when the RP tab is already closed.
- RPs are server-side web applications, backend APIs, or systems with a central session store.
- The OP can reach the RP endpoint over the network.
- RPs need to map accurately to a single session or all sessions of a subject.
- Browser third-party cookie blocking makes Front-Channel unreliable.
- Organizational policy requires server-to-server auditing, retries, and delivery status tracking.

Back-channel also carries costs:
- The RP must expose an endpoint reachable by the OP to receive notifications.
- The RP must maintain mappings from OIDC identity/sessions to local sessions.
- Logout Tokens must be verified and protected against replay.
- The RP must handle duplicate requests, retries, concurrency, and distributed session invalidation.
- Endpoints must be reachable from the OP; RPs behind NAT/firewalls may need a gateway or private network connectivity.

### 4.1. Metadata and Client Registration

An RP supporting Back-Channel Logout registers:
- `backchannel_logout_uri`: server-side endpoint receiving Logout Tokens.
- `backchannel_logout_session_required`: whether the RP requires Logout Tokens to include `sid`; defaults to `false`.

The OP advertises:
- `backchannel_logout_supported`: whether the OP supports Back-Channel Logout; defaults to `false` if absent.
- `backchannel_logout_session_supported`: whether the OP can include `sid` in Logout Tokens; defaults to `false` if absent. When supported, `sid` is also included in ID Tokens.

The logout URI must be an absolute URI with no fragment. HTTPS should be used. For confidential clients using HTTP, accept only if OP policy permits and it complies with the spec.

### 4.2. OP Tracks Logged-In RPs

The OP needs to know which RPs participated in the session to send notifications. A structure can store relationships such as:

~~~text
OP session:
  issuer
  subject
  sid
  authenticated_at
  active_rp_sessions:
    - client_id
    - backchannel_logout_uri
    - frontchannel_logout_uri (optional)
    - rp_local_session_reference (if available)
    - registration_version
~~~

This can use a visited-sites cookie, session store, or database. In distributed systems, a database/session event log is usually easier to audit and retry than relying solely on browser cookies.

Each RP must be bound to the right client registration. Never broadcast Logout Tokens to arbitrary URIs seen in requests; target lists must come from trusted client registrations and the OP's session tracking.

### 4.3. OP Sends the Logout Token via HTTP POST

The OP sends a request to the registered `backchannel_logout_uri` via HTTP POST with a form body:

~~~http
POST /oidc/back-channel-logout HTTP/1.1
Host: portal.example.com
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN
~~~

The body carries a `logout_token` parameter containing the JWT. The OP may send additional parameters, and the RP must ignore unrecognized values. The Logout Token must be signed; it may also be encrypted if the client negotiated encryption.

## 5. Comparing Front-Channel and Back-Channel

| Criterion | Front-Channel | Back-Channel |
| --- | --- | --- |
| Channel | Browser/iframe | Server-to-server HTTP |
| Browser must be active | Yes | No |
| Third-party cookies | Can heavily impact delivery | Independent of browser cookies |
| RP endpoint reachability | URI reachable by browser | URI reachable by OP |
| Session lookup | Can rely on cookies + `iss`/`sid` | Requires mapping `issuer`/`client`/`sub`/`sid` to local sessions |
| Spoofing protection | Check `iss`/`sid` and protect endpoint | Verify Logout Token signature/claims |
| Retry | Hard to observe and hard to confirm completion | Supports controlled queuing/retries |
| Best suited for | Web UIs, legacy browser logout | Backend/server-side sessions, higher-reliability SLO requirements |
| Primary limitation | Browser privacy/cookie policies | Reachability, state mapping, higher implementation complexity |

### 5.1. Decision Matrix

| Business Condition | Recommended Choice |
| --- | --- |
| Apps are browser UIs only, cookies can be cleared in iframes, and high assurance is not required | Front-Channel may suffice |
| Browser privacy policies block third-party cookies or users often close tabs | Back-Channel |
| RP sits behind a firewall/NAT that a public OP cannot reach | Front-Channel or a private network/gateway for Back-Channel |
| RP needs to log out a specific device/session accurately | Back-Channel with `sid`; Front-Channel also requires session-aware mapping |
| RP manages only one session per subject/client | Either can fit; identity mapping is still needed |
| System requires auditing, retries, and per-RP completion confirmation | Back-Channel |
| Legacy RP cannot implement token validation yet has a simple iframe endpoint | Front-Channel, with assessment of browser constraints |
| Both web UIs and backend session stores exist | Hybrid can be deployed: Back-Channel as primary, Front-Channel as supplementary |

Do not pick Back-Channel solely because it is "more secure" if the OP cannot reach the RP. Do not pick Front-Channel merely because it is easy to demo if logout must work when the browser is closed. Start from the threat model, topology, browser support, session architecture, and logout completion criteria.

## 6. Identity and Session Model: iss, aud, sub, sid

Multi-RP logout frequently fails due to ambiguous session mapping. Key values:

| Claim | Role | Scope |
| --- | --- | --- |
| `iss` | OP issuer that issued the ID Token/Logout Token | Trust domain |
| `aud` | Client/RP receiving the token | Distinguishes RPs |
| `sub` | Subject identifier of the End-User | Issuer-scoped |
| `sid` | Session ID at the OP | Issuer-scoped |
| `jti` | Unique ID of the Logout Token | Replay detection |

Do not use `sub` alone as a global key. Two OPs can issue the same subject string for two different people. Do not use `sid` alone because it is unique only within an issuer's scope. A proper mapping key is typically:

~~~text
session_key = (issuer, client_id, sid)
subject_key = (issuer, client_id, sub)
~~~

If an RP uses pairwise subject identifiers, `sub` can differ per client/sector. Therefore, subject mapping must include the specific issuer and client registration. When receiving a Logout Token:
- `sid` present: terminate local sessions linked to `(iss, aud/client, sid)`.
- Only `sub` present: terminate all local sessions of that subject at the corresponding RP/client.
- Both `sid` and `sub` present: verify both claims describe the same session/subject before processing.

### 6.1. One Subject with Multiple Sessions

For example, the same user logs in from a laptop and a phone:

~~~text
Issuer: https://auth.example.com
Subject: user-123

Laptop:
  sid = sid-laptop
  RP local session = rp-session-A

Phone:
  sid = sid-phone
  RP local session = rp-session-B
~~~

A Logout Token with `sid=sid-laptop` ends only the laptop session. If the Logout Token has only `sub=user-123`, the RP must end all sessions of this subject at the RP. This is a major business distinction: never turn a `sid`-targeted logout into a full-subject logout automatically.

## 7. Structure and Validation of a Back-Channel Logout Token

A Logout Token is a JWT signed by the OP carrying claims describing the logout action. It is **not an ID Token** and must never be accepted in an authentication response.

### 7.1. Required Claims

| Claim | Requirement | How to Validate |
| --- | --- | --- |
| `iss` | REQUIRED | Exact match against configured OP issuer |
| `aud` | REQUIRED | Contains the client ID of the RP receiving the notification |
| `iat` | REQUIRED | Reasonable issued-at timestamp per clock skew/policy |
| `jti` | REQUIRED | Unique token ID to prevent replay |
| `events` | REQUIRED | JSON object containing the back-channel logout event key |
| `sub` | OPTIONAL | Subject being logged out |
| `sid` | OPTIONAL | Session being logged out |
| `nonce` | PROHIBITED | Must not be present |

The Logout Token **MUST** contain at least `sub` or `sid`; it may contain both. If `sid` is absent, the intent is to terminate all sessions of the subject identified by `iss` and `sub` at the RP.

The `events` claim has the key:

~~~text
http://schemas.openid.net/event/backchannel-logout
~~~

The corresponding value must be a JSON object and SHOULD be an empty object:

~~~json
{
  "http://schemas.openid.net/event/backchannel-logout": {}
}
~~~

The Logout Token MUST be signed. `typ=logout+jwt` is RECOMMENDED to avoid confusing this token with ID Tokens in other JWT validation paths. `alg=none` MUST NOT be used.

### 7.2. Logout Token Example

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "portal-web",
  "iat": 1794800100,
  "jti": "logout-event-2b7d5f",
  "sid": "op-session-a91",
  "sub": "user-123",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

The payload above only illustrates claims. Real tokens must be signed by the OP's signing key, and the RP must obtain keys from verified trust configuration/JWKS. Never accept a token simply because its JSON payload looks right.

### 7.3. Validation Sequence at the RP

The RP must perform:
1. If encrypted, decrypt using algorithms/keys agreed during client registration. If the RP negotiated ID Token encryption with the OP at registration yet receives an unencrypted Logout Token, the RP SHOULD reject the token.
2. Verify the signature as done for ID Tokens, using an algorithm allowlist.
3. Verify `iss` and `aud` against the active issuer/client registration.
4. Verify `iat` according to timing policy and clock skew.
5. Confirm at least one of `sub` or `sid` is present.
6. Confirm `events` contains the back-channel logout event URI.
7. Confirm `nonce` is absent.
8. Check whether `jti` was processed recently; use a shared, atomic replay store.
9. Optionally cross-check `iss`, `sub`, and `sid` against current or recent ID Tokens/sessions for extra assurance.
10. Only after validation succeeds, locate and invalidate local sessions.

If any required validation fails, reject the token and return HTTP 400 per the specification. Never delete sessions before validation completes.

### 7.4. Do Not Mistake exp for a Required Claim

Back-Channel Logout Tokens require `iat` and `jti`, whereas `exp` is not in the Logout Token profile's required claims list. The RP can enforce a freshness window based on `iat` and clock skew to reject old tokens. If the OP and RP also agree on `exp`, agree on semantics without breaking the OIDC contract.

## 8. Safe and Idempotent Logout Handling at the RP

After validation, the RP looks up sessions:
- Prefer the `(iss, client_id, sid)` mapping if the token has `sid`.
- If only `sub` is present, look up all local sessions by `(iss, client_id, sub)`.
- Never use email, username, or display name to locate sessions.
- Never delete sessions belonging to another client or another issuer.

### 8.1. Idempotency and Replay

Two concepts must be separated:
- **Idempotent session invalidation:** logging out the same session multiple times causes no errors and affects no other sessions.
- **Replay protection:** never reprocess the same Logout Token as a brand-new event.

The RP should store processed `jti` values for a duration aligned with the freshness window. Check-and-insert must be atomic so two nodes do not simultaneously accept a replayed token. If a valid token is resent by the OP after a network error, the RP can return success when the session state is already gone, while still recording duplicates per policy.

### 8.2. Invalidating Sessions Properly

Do not merely delete a mapping row and leave the HTTP session active. You need to:
1. Mark the session mapping as logout-pending or revoked.
2. Invalidate the actual session store/session ID.
3. Clear `SecurityContext` and session-associated data.
4. Revoke or delete refresh-token/session credentials under separate policy if required.
5. Publish an internal event so other nodes/caches synchronize.
6. Write an audit event without including the raw Logout Token.

With distributed sessions, handle races between in-flight requests and logout events. You may need to mark the principal/session revoked so subsequent requests are rejected immediately even while physical session deletion is pending.

## 9. Designing OP Fan-Out: Sending Logout to the Right RPs

The OP must maintain the relationship between sessions and logged-in RPs. One design can include entities/aggregates such as:

| Entity | Key Fields |
| --- | --- |
| `op_session` | `issuer`, `sub`, `sid`, `created_at`, `status`, `ended_at` |
| `client_registration` | `client_id`, `backchannel_logout_uri`, `frontchannel_logout_uri`, `session_required` |
| `op_session_client` | `issuer`, `sid`, `client_id`, `rp_session_ref`, `last_authenticated_at` |
| `logout_delivery` | `event_id`, `client_id`, `target_uri`, `jti`, `attempt`, `status`, `next_attempt_at` |

When an OP session terminates:
1. Within the same transaction, mark the OP session as ended.
2. Create logout event/outbox records for each associated client.
3. Workers pick up delivery records and send notifications over each client's registered channel.
4. Record HTTP status, timestamp, attempt count, and error class.
5. Retry transient failures with exponential backoff/jitter and a max attempt limit.
6. Route prolonged delivery failures to a dead-letter queue for operational handling.

Do not call every RP synchronously inside the login/session logout transaction. A slow or down RP should never hold an OP session transaction open for long.

### 9.1. Generating a Logout Token per Client

A Logout Token binds `aud` to the receiving RP. Therefore, the OP should mint a separate token per client:
- `iss`: the OP's issuer.
- `aud`: the target RP's client ID.
- `iat`: issuance timestamp.
- `jti`: unique random ID for the event/token.
- `events`: back-channel logout event.
- `sid` and/or `sub`: session/subject per client metadata and session mapping.

If an RP registered `backchannel_logout_session_required=true`, the OP must have `sid` to send a compliant token; if it cannot supply `sid`, it must not pretend to support session-specific logout for that client. If the token has only `sub`, the semantics are to log out all RP sessions of the subject.

Each RP receives a token with its own audience. Do not mint a single JWT with `aud` listing all clients when deployment contracts expect per-client exact audience verification and isolated sessions.

Example creating an RSA-signed Logout Token with Nimbus JOSE + JWT:

~~~java
String eventType =
        "http://schemas.openid.net/event/backchannel-logout";

JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
        .issuer("https://auth.example.com")
        .audience(clientId)
        .issueTime(new Date())
        .jwtID(UUID.randomUUID().toString())
        .claim("events", Map.of(eventType, Map.of()));

if (subject != null) {
    claims.subject(subject);
}
if (sessionId != null) {
    claims.claim("sid", sessionId);
}

JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
        .type(new JOSEObjectType("logout+jwt"))
        .keyID(signingJwk.getKeyID())
        .build();

SignedJWT logoutToken = new SignedJWT(header, claims.build());
logoutToken.sign(new RSASSASigner(signingJwk.toRSAKey()));
String compactLogoutToken = logoutToken.serialize();
~~~

This snippet assumes `clientId`, `subject`, `sessionId`, and `signingJwk` come from trusted registration/session/key management. Reject cases where both `subject` and `sessionId` are null. The private key stays inside the OP only; RPs verify with the public key. Choose the algorithm based on your actual key/policy and registration rather than hardcoding RSA if the OP uses another key type.

Each token is minted for a single client so `aud` names the exact target RP. Never reuse the same `jti` across different clients; each JWT needs a unique ID.

### 9.2. Delivery, Retries, and Outcomes

| HTTP Result | Recommended Handling |
| --- | --- |
| 2xx | Mark delivered; keep audit event |
| 400 | Invalid token/request; do not retry infinitely, alert on integration |
| 401/403 | Check endpoint authentication/network policy/client config |
| 404 | Wrong registered URI or undeployed endpoint; mark permanent/configuration error |
| 429 | Retry per `Retry-After`/backoff |
| 5xx/network timeout | Bounded retry with jitter and circuit breaker |
| Timeout after RP processed it | May resend; RP must be idempotent/replay-aware |

The Back-Channel Logout spec recommends that the OP retransmit only when there is reason to suspect the previous attempt failed due to a recoverable error, and delay appropriately to avoid overloading the RP.

### 9.3. Hybrid Fan-Out

If the OP supports both:
- Back-channel server-to-server notifications serve as the primary channel.
- Front-channel can help browser UIs/local storage clear faster.
- The RP must handle logout for the same session arriving via both channels without deleting the wrong session or raising errors.
- Both paths need separate audit correlation and completion tracking.
- Never assume front-channel succeeded if back-channel failed, or vice versa.

## 10. Support in Spring Security and Spring Authorization Server

You must distinguish **RP receiving logout** from **OP sending logout**. These are two separate roles.

### 10.1. Spring Security: RP Support for Back-Channel Logout

Spring Security 7.1.x documentation provides the `oidcLogout(...).backChannel(...)` DSL for OAuth2 Login applications acting as RPs. Spring Security includes:
- `OidcBackChannelLogoutHandler` to handle session invalidation per OIDC Back-Channel Logout.
- `OidcSessionRegistry` to link ID Tokens/`sid`/`sub` to local sessions.
- Default endpoint pattern `/logout/connect/back-channel/{registrationId}`.
- `HttpSessionEventPublisher` to remove `OidcSessionInformation` entries when sessions are invalidated.

Example:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcBackChannelLogoutHandler() {
    return new OidcBackChannelLogoutHandler();
}

@Bean
HttpSessionEventPublisher sessionEventPublisher() {
    return new HttpSessionEventPublisher();
}

@Bean
SecurityFilterChain rpSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .oidcLogout(oidc -> oidc
            .backChannel(Customizer.withDefaults())
        );
    return http.build();
}
~~~

This is an **RP-side** configuration. `oidcLogout` requires `oauth2Login` to also be configured. Verify cookie names and session stores against your version; Spring Security's default setup uses `JSESSIONID` to correlate local sessions. If using Spring Session with the `SESSION` cookie, configure `OidcBackChannelLogoutHandler.setSessionCookieName("SESSION")` or the equivalent setting for your version.

Spring Security validates the Logout Token and looks up sessions by `sid`; if `sid` is absent, it can terminate sessions of the subject for the corresponding client. Verify your active dependency version's behavior and review `OidcSessionRegistry` lifecycle in clustered environments.

### 10.2. Spring Security: OP Logout Is Not an RP Back-Channel Receiver

`OidcBackChannelLogoutHandler` is used in an RP application receiving notifications. It does not turn the application into an OP and does not send Logout Tokens to other RPs.

If an application uses only `oauth2Login` and `oidcLogout`, it still needs a separate OP to emit notifications. Never mistake the RP's receiver endpoint for a fan-out endpoint on the Authorization Server.

### 10.3. Spring Authorization Server: RP-Initiated Logout and Current Boundaries

In Spring Authorization Server 1.5.x, `OidcLogoutEndpointConfigurer` configures the OIDC RP-Initiated Logout Endpoint. Extension points include the converter, authentication provider, logout response handler, and error handler; the provider uses `SessionRegistry` to locate sessions to end.

SAS 1.5.8 Protocol Endpoints documentation describes `OidcLogoutEndpointConfigurer` for RP-Initiated Logout. That documentation does not list a complete built-in configurer/endpoint for the OP to automatically fan out Front-Channel or Back-Channel Logout. Therefore, never assume that enabling `oidc(...).logoutEndpoint(...)` means the OP already:
- Tracks all logged-in RPs per OP session.
- Publishes full frontchannel/backchannel metadata.
- Consistently includes `sid` in ID Tokens/sessions.
- Mints per-audience Logout Tokens.
- Sends notifications, retries, and tracks delivery outcomes to RPs.

With SAS 1.5.x, if OP fan-out is required, design custom extensions/integrations or use an OP that natively supports the full feature set. Verify actual documentation/version capabilities before committing to support.

### 10.4. Components Needed to Extend the OP

An extension design typically includes:

| Component | Responsibility |
| --- | --- |
| `Session correlation service` | Links OP session, `sid`, `sub`, clients, and RP sessions |
| `Client logout metadata registry` | Stores registered backchannel/frontchannel URIs and flags |
| `ID Token customizer` | Emits `sid` when the OP advertises session-specific logout |
| `Logout event publisher` | Emits events when an OP session ends |
| `Logout Token issuer` | Creates and signs tokens per client audience |
| `Fan-out dispatcher` | Sends POSTs to backchannel URIs and manages retries |
| `Front-channel page renderer` | Renders iframes to registered frontchannel URIs |
| `Delivery/outbox store` | Tracks attempts, status, next retry, and audits |
| `Revocation/session policy` | Decides which refresh tokens/authorizations are revoked alongside logout |

Do not put all of these responsibilities inside a synchronous `LogoutSuccessHandler`. Emit an event/outbox record from the transaction ending the OP session and let a dispatcher handle delivery independently.

## 11. End-to-End Architecture Example with Two RPs

Suppose we have:
- Web Portal using Spring Security OAuth2 Login.
- Admin Console using Spring Security OAuth2 Login.
- OP using Spring Authorization Server 1.5.x plus a custom-built fan-out module.
- Both RPs register a Back-Channel Logout URI; Portal also supports Front-Channel.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Portal RP
    participant O as OP / Spring Authorization Server
    participant D as Logout Dispatcher
    participant A as Admin RP
    P->>O: RP-Initiated Logout (id_token_hint)
    O->>O: Validate hint, end OP session
    O->>O: Persist logout event + recipients
    O-->>P: Post-logout redirect
    O->>D: Outbox event
    par Back-channel delivery
        D->>P: POST logout_token (aud=portal)
        P->>P: Validate JWT, map sid, invalidate session
        D->>A: POST logout_token (aud=admin)
        A->>A: Validate JWT, map sid, invalidate session
    and Optional front-channel
        O-->>P: Browser iframe frontchannel_logout_uri
    end
~~~

Each RP receives its own Logout Token with matching `aud`. If Portal already performed local logout first, the subsequent notification must still be handled idempotently. If Admin RP holds multiple sessions for the same subject, `sid` identifies the specific session; if only `sub` is present, all sessions of that subject at Admin RP are terminated.

## 12. Security, Privacy, and Operations

### 12.1. Front-Channel Endpoint

- Never let a front-channel request arbitrarily delete sessions based on unverified `sub`/`sid`.
- If receiving `iss` and `sid`, verify both and map by issuer.
- Handle idempotently and return `Cache-Control: no-store`.
- Do not rely on third-party cookies being enabled in the browser as the sole guarantee of logout.
- Restrict response content; do not render user data or unnecessary scripts.
- Verify CSP/frame behavior and avoid loosening global frame policies.

### 12.2. Back-Channel Endpoint

- Accept only form POSTs with `logout_token` per contract.
- Verify JWT signatures using trusted OP keys; never fetch keys from arbitrary `jku`/`x5u` headers in the token.
- Validate `iss`, `aud`, `iat`, `jti`, `events`, `sub`/`sid`, and the absence of `nonce`.
- Enforce an allowlist of signing algorithms; reject `none`.
- Replay stores must be atomic and shared across nodes.
- Enforce request size limits, timeouts, rate limits, and auditing.
- mTLS/network allowlists between OP and RP can be added as a transport layer; they do not replace Logout Token validation.
- Never log raw Logout Tokens in access logs or tracing.

### 12.3. Session and Tenant Isolation

Every mapping must preserve issuer/client context:
- Never delete all sessions merely because `sub` strings collide across two issuers.
- Never process a Logout Token whose `aud` does not contain the current registration's client ID.
- Never use email or username to identify sessions.
- Never accept a `sid` from another issuer.
- If pairwise subjects differ per client, mappings must preserve client/sector context.
- When a tenant/client registration is deleted, clean up mappings and delivery records per policy.

### 12.4. Auditing and Privacy

Record:
- Issuer, client ID, internal session correlation ID.
- Logout channel and receive/send timestamps.
- Validation outcome, count of invalidated sessions.
- Delivery attempts, HTTP result, retry count, and terminal status.

Do not record raw tokens, cookies, access tokens, refresh tokens, or unnecessary PII. `sub`/`sid` are also sensitive identifiers; hash/pseudonymize them in operational logs and keep raw mappings in controlled audit stores.

### 12.5. Logout Does Not Replace Token Revocation

Back-channel logout terminates RP sessions. It does not automatically invalidate already-issued JWT access tokens across all Resource Servers. If APIs must stop accepting tokens:
- Revoke corresponding refresh tokens/authorizations per policy.
- Use short access token lifetimes.
- Use introspection or revocation-aware validation when needed.
- Propagate revocation state to Resource Servers.
- Test post-logout token behavior separately.

## 13. Front-Channel Test Matrix

| Scenario | Expected Result |
| --- | --- |
| OP calls frontchannel URI in iframe | RP ends session per policy |
| Both valid `iss` and `sid` present | Ends only the corresponding session |
| Only `iss` or only `sid` present | Invalid request per contract; do not guess session |
| `iss` from wrong OP | Ignore/reject request |
| `sid` does not map to a local session | Idempotent; does not delete other sessions |
| Session already logged out | Treated as success, no fatal error |
| Third-party cookies blocked | Detect correlation failure; do not falsely report global logout success |
| Proxy/browser caching | Response includes `Cache-Control: no-store` |
| Repeated request | Does not mistakenly delete a newer session created after the old one |
| URL has fragment or mismatched origin | Registration rejected |

## 14. Back-Channel Test Matrix

| Scenario | Expected Result |
| --- | --- |
| Validly signed token, right `iss`/`aud` | Proceed to validate claims and session |
| Invalid signature or untrusted key | HTTP 400, no session deleted |
| `alg=none` | Rejected |
| Wrong `iss` | Rejected |
| `aud` does not contain current client ID | Rejected |
| Missing `iat`, `jti`, or `events` | Rejected |
| Missing both `sub` and `sid` | Rejected |
| `nonce` present | Rejected |
| Wrong event URI | Rejected |
| Valid `sid` | Invalidates only sessions mapped to that `sid` |
| Only `sub` present | Invalidates all local sessions of that subject for that client |
| Inconsistent `sub` and `sid` | Does not delete session; audits and handles per validation policy |
| Already-processed `jti` | Does not re-execute event; responds per idempotency contract |
| Two nodes receive same token concurrently | Atomic replay store ensures at-most-once logical processing |
| Local session already deleted | Handled idempotently |
| RP session cookie is `SESSION` | Handler/registry configured properly, does not assume `JSESSIONID` |
| OP times out after RP already processed | Retry does not delete other sessions |
| Stale Logout Token | Rejected per freshness policy |
| Oversized request body | Rejected before expensive JWT parsing |

## 15. OP Fan-Out and Operations Test Matrix

| Scenario | Expected Result |
| --- | --- |
| OP session ends | Outbox event created within transaction |
| One session has multiple RPs | Sends to each RP's registered URI |
| Client requires `sid` yet OP lacks `sid` | Does not send non-compliant token; logs capability/config error |
| Each RP receives a token | `aud` matches the exact target client |
| RP returns 2xx | Delivery succeeds |
| RP returns 5xx/timeout | Retries with backoff/jitter and cap |
| RP returns 400 | Marks token/contract error; does not retry infinitely |
| Worker restarts | Outbox resumes processing without losing events |
| Two dispatchers claim the same event | Locking/leasing or optimistic concurrency prevents uncontrolled duplicate sends |
| Front + Back channel both arrive | RP handles idempotently |
| OP signing key rotation | RP verifies tokens during overlap window per JWKS policy |
| Client registration revoked | Stops sending notifications to untrusted URIs |
| RP URI changed | Delivery uses only newly validated registration metadata |
| User across multiple tenants/issuers | No cross-trust-domain fan-out |
| Audit query | Can trace deliveries by event/client without exposing raw tokens |

## 16. Case Study

An enterprise has an OP and three applications:
- Web Portal using Spring Security sessions.
- Admin Console using Spring Session with the `SESSION` cookie.
- Mobile API using access tokens, holding no browser session.

A user logs into all three applications. The OP terminates the SSO session because an administrator locks the account. Requirements:
- Portal and Admin Console must end local sessions even if the browser tab is closed.
- Mobile API must reject tokens per revocation policy.
- The system needs auditing for each application that received logout.
- The OP runs Spring Authorization Server 1.5.x.

Analyze the following:

1. Can Front-Channel satisfy the requirement when browser tabs are closed?
2. How does Back-Channel fit, and what network conditions must be met?
3. How does Spring Security configure the Back-Channel receiver for Portal/Admin Console?
4. Why must Admin Console verify the `SESSION` session cookie name?
5. What mappings must the OP store to send Logout Tokens to the right clients?
6. How must `aud` be set on tokens for Portal and Admin Console?
7. Since Mobile API has no local web session, what mechanism is needed for tokens to be rejected?
8. Why does enabling SAS's `OidcLogoutEndpointConfigurer` not complete OP fan-out by itself?
9. How should outbox/retry be designed so one down RP does not block logging out other RPs?
10. Propose tests for `sid` single-session logout and `sub` all-sessions logout.

**Hint:** Back-Channel is the primary channel for requirements when the browser is closed. Spring Security provides the RP-side receiver, while the OP needs its own session/RP registry and dispatcher if your SAS version does not supply a corresponding sender/fan-out. Admin using Spring Session must configure cookie correlation. Mobile API requires token revocation/introspection or token-status checking policies; Logout Tokens do not automatically revoke access tokens at Resource Servers.

## 17. Production Deployment Checklist

1. **Requirement:** define which sessions must end, on which RPs, and within what latency.
2. **Mechanism:** select Front-Channel, Back-Channel, or hybrid based on browsers, network, and assurance.
3. **Metadata:** accurately publish `frontchannel_logout_supported`, `backchannel_logout_supported`, and session-supported flags.
4. **Client registration:** store logout URIs and session-required flags per client; verify URIs before use.
5. **Session model:** emit `sid` when advertising session-specific logout; persist `issuer`/`client`/`sub`/`sid` mappings.
6. **Logout Token:** sign with OP key, per-RP audience, include `iss`/`aud`/`iat`/`jti`/`events` and appropriate `sub`/`sid`; omit `nonce`.
7. **RP validation:** verify signature/alg/issuer/audience/time/event/`sub`-or-`sid` before invalidating.
8. **Replay:** store `jti` atomically/distributed; handle duplicates and retries idempotently.
9. **Spring Security RP:** enable `.oidcLogout(...).backChannel(...)` per version, with `oauth2Login`, registry, and session event cleanup.
10. **Cookie/session store:** verify `JSESSIONID` vs. `SESSION`, Spring Session, clustering, and real session invalidation.
11. **SAS OP:** distinguish RP-Initiated Logout Endpoint from OP fan-out; design extensions where needed.
12. **Delivery:** use outbox/queue, parallel dispatch, backoff retries, dead-lettering, and dashboards.
13. **Front-channel:** test iframes, `SameSite`, third-party cookies, CSP, `no-store`, and fallbacks.
14. **Token lifecycle:** design separate revocation/introspection if access tokens must become invalid after logout.
15. **Security:** never use email/username in place of subject; verify issuer/client/tenant isolation.
16. **Observability:** track delivery success/failure, latency, retries, duplicates, and invalidated session counts.
17. **Testing:** run unit, integration, and end-to-end tests across browsers/ingress/multi-node; test network outages and key rotation.
18. **Incident response:** support forced logout, signing key rotation, token revocation, and compromised client registration handling.

## 18. Standards and Spring References to Consult

- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): `frontchannel_logout_uri`, `iss`, `sid`, iframe behavior, metadata, and browser limitations.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): client registration, Logout Token, validation, delivery, and session logout actions.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): mechanism for an RP to request that the OP end a session.
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html): browser-based session state.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): JWT structure, `iss`, `aud`, `iat`, `jti`.
- [Spring Security 7.1 — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): RP-Initiated and Back-Channel Logout receiver, `OidcBackChannelLogoutHandler`, `OidcSessionRegistry`.
- [Spring Authorization Server 1.5 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcLogoutEndpointConfigurer` for RP-Initiated Logout and endpoint extension points.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): session tracking and `SessionRegistry`.

**Key Takeaway:** Front-Channel Logout uses browsers/iframes, making it easy to integrate with web UIs yet dependent on third-party cookies, browser state, and iframe policies. Back-Channel Logout uses HTTP POST with signed Logout Tokens, making it better suited for server-side sessions and logout requirements when browsers are inactive, though it requires reachable endpoints, session mapping, token validation, replay protection, and delivery/retry infrastructure. Spring Security 7.1.x provides a Back-Channel receiver for RPs; Spring Authorization Server 1.5.x provides the RP-Initiated Logout Endpoint, whereas OP Front/Back-Channel fan-out requires checking your version and typically adding a session/RP registry, Logout Token issuer, dispatcher, and delivery tracking. Choose mechanisms based on real requirements, never advertise unimplemented capabilities, and never confuse session logout with token revocation.
