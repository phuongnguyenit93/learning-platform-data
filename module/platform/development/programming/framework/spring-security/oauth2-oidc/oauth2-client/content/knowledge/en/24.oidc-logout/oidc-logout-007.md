# 24.7. OIDC Back-Channel Logout: Concepts, Logout Token, and Linked Sessions

## 1. The Problem: Logging Out at the Identity Provider Leaves Application Sessions Active

In **Spring Security OAuth 2.0 OIDC Client**, a Spring Boot application typically acts as a **Relying Party (RP)**: it logs users in via an **OpenID Provider (OP)**, and then maintains its own login session in the application using `HttpSession`, `WebSession`, or another appropriate session mechanism.

For example, Alice logs into three applications using the same OP:

~~~text
                       OpenID Provider
                      (SSO login session)
                        /     |     \
                       /      |      \
                  Portal    Reports   Billing
                   RP A      RP B      RP C
                   |          |         |
                Session A  Session B  Session C
~~~

When Alice logs out directly at the OP, **the sessions in Portal, Reports, and Billing do not necessarily disappear automatically**. Each RP has its own session cookie, local security context, and session lifecycle. The OP cannot simply delete cookies of each RP across different domains.

**OpenID Connect Back-Channel Logout 1.0** solves this problem via **server-to-server** communication:

1. The OP knows which RPs hold sessions associated with the user.
2. When the OP decides to log out, it sends an HTTP POST directly to the registered logout endpoint of each RP.
3. The POST contains a signed **Logout Token** describing the user or OP session to log out.
4. The RP verifies the token and looks up the corresponding **local sessions**.
5. The RP terminates those sessions without requiring the user's browser to be open.

This lesson focuses on **concepts**, the **Logout Token**, **`sid` / `sub`**, **session mapping**, Spring Security Servlet/Reactive integration, and security/operational considerations.

### Objectives

After this lesson, you will be able to:

- Distinguish local logout, RP-Initiated Logout, Front-Channel Logout, and Back-Channel Logout.
- Interpret the HTTP POST `logout_token` and mandatory JWT claims per the specification.
- Distinguish the OP's `sid` from the RP's local `JSESSIONID` / `SESSION`.
- Understand why an **OIDC session registry** is needed to map OP sessions to application sessions.
- Configure `oidcLogout().backChannel(...)` in Spring Security Servlet and Reactive per the respective APIs.
- Handle session store, cookie name, multi-instance, multi-tenant, and token revocation issues.
- Design validation, idempotency, monitoring, and integration tests without leaking tokens.

> **Version scope:** Examples focus on the back-channel logout API of Spring Security versions supporting `oidcLogout().backChannel(...)`, such as the Spring Security 6.5 and 7.x branches. Class/API names and configuration depend on the Servlet or Reactive stack. Consult documentation matching the Spring Security version managed by your project's BOM; never copy classes from another major version without checking compatibility.

## 2. Terms to Distinguish

| Term | Role |
| --- | --- |
| **OP (OpenID Provider)** | System authenticating users and issuing ID Tokens |
| **RP (Relying Party)** | OIDC Client application trusting verified ID Tokens |
| **SSO session** | Session at OP allowing a user to sign into multiple RPs |
| **RP local session** | Application's own session, e.g., `HttpSession` / `WebSession` |
| **`sub` (subject)** | User identifier scoped to the OP's issuer |
| **`sid` (OP session ID)** | Session identifier at the OP, helping select the exact session |
| **Logout Token** | JWT signed by the OP asking the RP to terminate the described session |
| **Back-Channel Logout URI** | Endpoint registered by RP for OP to send Logout Tokens via HTTP POST |
| **OIDC Session Registry** | Store mapping OP session/subject/client to local RP sessions |
| **`registrationId`** | Spring Security `ClientRegistration` config ID |
| **`aud`** | Audience of the Logout Token; must match the RP's client ID |

### 2.1. An OP Session Is Not an RP Session

Example:

~~~text
OP:
  issuer = https://id.example.net/realms/company
  sub    = user-123
  sid    = op-session-9b1e

RP Portal:
  registrationId = company
  clientId       = portal-web-client
  JSESSIONID     = rp-session-a731

RP Reports:
  registrationId = company
  clientId       = reports-web-client
  JSESSIONID     = rp-session-f028
~~~

**`sid` is not the `JSESSIONID` cookie value**. The OP issues `sid` according to its own session logic; the RP has a separate local session ID. The registry links the two identifier domains.

Never delete an `HttpSession` by treating the `sid` value in a Logout Token directly as `JSESSIONID`.

### 2.2. `sub` Must Be Interpreted Together with Issuer

`sub="user-123"` from:

~~~text
https://id.example.net/realms/company
~~~

is not implicitly the same account as `sub="user-123"` from:

~~~text
https://login.partner.example.org
~~~

When looking up sessions to log out, bind **issuer, audience/client registration, and subject/session**—never just a username or email string.

## 3. How Does Back-Channel Logout Differ from Other Logout Types?

| Mechanism | Who Initiates? | Communication Flow | Target |
| --- | --- | --- | --- |
| **Local Logout** | RP or user at RP | Browser sends request to RP | Terminates RP's local session |
| **RP-Initiated Logout** | RP | Browser is redirected to OP's `end_session_endpoint` | Asks OP to terminate SSO session |
| **Front-Channel Logout** | OP | OP uses browser/iframe/redirect to call RPs | Terminates RP sessions via user agent |
| **Back-Channel Logout** | OP | **OP sends server-to-server HTTP POST** to RP | Terminates RP sessions using Logout Token |

### 3.1. Why Is Back-Channel Useful?

Back-channel does not require the browser to have an open RP tab. The OP can send logout requests even when the user:

- Closed the Portal tab while Portal's cookie was still valid.
- Logged out only in another system using the same OP.
- Had their OP session terminated by an administrator.
- Triggered a global logout policy.

However, **this does not mean back-channel delivery is guaranteed to succeed every time**. If the RP is unreachable from the OP, the network drops, or the session registry loses data, logout may be delayed or fail.

### 3.2. Limitations of Back-Channel

Back-channel **does not**:

- Directly delete cookies stored in the user's browser.
- Automatically push a real-time notification to an open SPA.
- Automatically revoke all issued Access Tokens/Refresh Tokens.
- Automatically end sessions on applications not registered to receive back-channel events.
- Replace local logout mechanisms or token expiration policies.
- Automatically enforce Resource Server permissions.

Typically, the RP **invalidates the server-side session**. Old cookies remaining in the browser become useless; the next request prompts re-authentication. If the product wants an immediate UI update, add a dedicated frontend notification mechanism.

## 4. OP and RP Must Advertise/Register Back-Channel Support

### 4.1. OP Discovery Metadata

An OP may publish:

~~~json
{
  "issuer": "https://id.example.net/realms/company",
  "backchannel_logout_supported": true,
  "backchannel_logout_session_supported": true
}
~~~

Two key fields:

- `backchannel_logout_supported`: whether the OP supports this mechanism; defaults to `false` when omitted.
- `backchannel_logout_session_supported`: whether the OP can issue `sid` in Logout Tokens and matching ID Tokens; if not, `sub`-based logout may be the remaining option.

**Do not assume `sid` is present** if the OP does not support session-based logout. Before enabling the feature, verify the exact issuer metadata and provider contract/console.

### 4.2. RP Registers `backchannel_logout_uri`

The RP must declare an **absolute URI** where the OP can send HTTP POSTs:

~~~text
https://portal.example.net/logout/connect/back-channel/company
~~~

Per the spec, client registration metadata includes:

~~~json
{
  "backchannel_logout_uri":
    "https://portal.example.net/logout/connect/back-channel/company",
  "backchannel_logout_session_required": false
}
~~~

`backchannel_logout_session_required` indicates whether the RP **requires the OP to provide `sid`** on logout. Do not set it to `true` if the OP only supports `sub`-based logout.

The URI must point to the exact **RP deployment** and **Spring Security `registrationId`**; registering the URI with the OP can be done in the admin console or via Dynamic Client Registration. Do not mistake `backchannel_logout_uri` for a standard YAML property that automatically configures the OP just by adding it under `spring.security.oauth2.client.registration.*`.

### 4.3. Network Reachability Is a Real Prerequisite

The OP must be able to **reach the RP endpoint** over the back-channel:

~~~text
OP server network
    |
    | HTTPS POST
    v
Ingress / reverse proxy / WAF
    |
    v
Spring Boot RP endpoint
~~~

If the RP only runs on a laptop's `localhost`, an Internet-hosted OP normally **cannot** reach that address. If the RP sits in a private network, provide a trusted network path (private connectivity, gateway, firewall allowlist, etc.), and never open the endpoint blindly without Logout Token verification.

In production, use HTTPS, TLS checks, and rate limiting; avoid returning raw diagnostic secrets in responses.

## 5. End-to-End Flow of Back-Channel Logout

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant RP as Spring Security RP
    participant Registry as OIDC Session Registry
    participant OP as OpenID Provider
    User->>Browser: Open /dashboard
    Browser->>RP: Unauthenticated request
    RP-->>Browser: Redirect to OP
    Browser->>OP: OIDC Authorization Code Flow
    OP-->>Browser: Callback code/state
    Browser->>RP: /login/oauth2/code/company
    RP->>OP: Token Endpoint, exchange code
    OP-->>RP: ID Token with iss/sub/sid, Access Token
    RP->>RP: Verify OIDC and create local session
    RP->>Registry: Store OP session -> RP session mapping
    RP-->>Browser: Set-Cookie JSESSIONID; redirect
    User->>OP: Log out at OP or admin revokes session
    OP->>RP: POST /logout/connect/back-channel/company
    Note over OP,RP: logout_token = signed JWT
    RP->>RP: Validate signature, iss, aud, exp, events, sid/sub...
    RP->>Registry: Find local sessions by sid or iss+sub+aud
    Registry-->>RP: Matching local session IDs
    RP->>RP: Invalidate matching sessions, run logout hooks
    RP-->>OP: HTTP 200 on success
    Browser->>RP: Next request with old cookie
    RP-->>Browser: No longer has an authenticated session
~~~

Key point: **the OP does not need the local RP cookie**. The RP already saved a mapping between the OP session and the local session **at the time OIDC Login succeeded**. When a Logout Token arrives, the RP has the information needed to pick the right session.

### 5.1. Two Data Stages

Login stage:

~~~text
(issuer, audience/client, sub, sid)
            |
            v
     Local session ID
~~~

Logout stage:

~~~text
Verified Logout Token
     iss + aud + sid/sub
            |
            v
    Query OIDC Session Registry
            |
            v
  Invalidate matching local sessions
~~~

If no matching mapping record exists, the RP **must not guess** which session to delete from an email or an unverified token string. A valid logout request with no remaining matching session can still be treated as completed.

## 6. HTTP Request of Back-Channel Logout

### 6.1. OP Sends POST, Not a Browser Redirect

Per OpenID Connect Back-Channel Logout, the OP sends:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.net
Content-Type: application/x-www-form-urlencoded
Accept: */*

logout_token=SIGNED_LOGOUT_JWT_PLACEHOLDER
~~~

`logout_token` is a **form parameter** whose value is a JWT (JWS/JWE per config), not an Access Token in an `Authorization` header.

**Do not confuse**:

~~~http
GET /logout?sid=op-session-123
~~~

with standard Back-Channel Logout. A GET request with `sid` in the query string does not prove the sender is the OP and **must never be used to invalidate sessions**.

### 6.2. Default Endpoint in Spring Security

For registration ID `company`:

~~~text
POST https://portal.example.net/logout/connect/back-channel/company
~~~

The default path documented by Spring Security is:

~~~text
/logout/connect/back-channel/{registrationId}
~~~

`registrationId` is the **`ClientRegistration` key**, not the real client ID, username, subject, or sid. The OP must be configured to call the exact path exposed by the application.

### 6.3. Response Per Specification

When logout succeeds:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

The spec requires HTTP `200 OK` on success; OPs should also accept `204 No Content` since some frameworks return 204 when there is no body.

If the logout request is invalid/malformed:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_request"}
~~~

This is an illustrative response. Never return raw JWTs, tokens, stack traces, or sensitive details to the caller. Network drops, timeouts, or inability to process sessions require recovery/retry policies; never report fake success if logout was not performed per contract.

### 6.4. What If Already Logged Out?

If the OP resends a valid notification for a session that was already deleted, the **idempotent** behavior is to treat the logout goal as achieved. Never restore the session or use it as an excuse to accidentally delete a new session with the same email.

Replay detection via `jti` can still be used to limit replays; decide how duplicates are handled safely in alignment with OP expectations.

## 7. What Is a Logout Token?

A **Logout Token** is a **JWT signed by the OP**, structurally similar to an ID Token but with a **different purpose**: it carries an event asking the RP to terminate associated sessions.

Typically, the JWS has the form:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

A Logout Token is **not**:

- An ID Token for login.
- An OAuth2 Access Token for calling Resource Servers.
- A Refresh Token for obtaining new Access Tokens.
- A browser session cookie.
- An Authorization Code returned during login.

### 7.1. Illustrative JWT Header

~~~json
{
  "alg": "RS256",
  "typ": "logout+jwt",
  "kid": "op-key-2026-01"
}
~~~

`typ=logout+jwt` is **recommended** to distinguish Logout Tokens from other JWTs. Per the spec, it is not strictly required for every legacy deployment; do not blindly assume older valid OPs always include the `typ` header.

`alg` must be an allowed signing algorithm per OIDC/client registration. **Never accept `alg=none`**, and never let an untrusted payload dictate the algorithm. `kid` helps locate the public signing key from the trusted issuer's JWKS—it is not an invitation to download keys from arbitrary URLs in a JWT header.

### 7.2. Illustrative JWT Claims

~~~json
{
  "iss": "https://id.example.net/realms/company",
  "sub": "user-123",
  "aud": "portal-web-client",
  "iat": 1790000000,
  "exp": 1790000120,
  "jti": "logout-event-7c3d52",
  "sid": "op-session-9b1e",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

**This is only a sample payload**, not a signed JWT, nor valid for logging out a real session. In reality, the OP must issue the JWT using the issuer's signing key. Illustrative timestamps may no longer match runtime clocks; `exp` must be validated against the current clock.

### 7.3. Meaning of Each Claim

| Claim | Required? | Role |
| --- | --- | --- |
| `iss` | Yes | Exact registered OP issuer |
| `aud` | Yes | RP's OAuth2 client ID receiving the Logout Token |
| `iat` | Yes | Timestamp when the JWT was issued |
| `exp` | **Yes per 1.0 incorporating errata set 1** | Expiration deadline for accepting the Logout Token |
| `jti` | Yes | Unique ID of the Logout Token, supporting replay prevention |
| `events` | Yes | Specifies the OIDC back-channel logout event |
| `sub` | Independently optional | User identifier, needed when `sid` is absent |
| `sid` | Independently optional | Specific OP session identifier |
| `nonce` | **Prohibited** | Logout Token **must not contain `nonce`** |

Combined condition: a Logout Token **must contain at least one of `sub` or `sid`**, and may contain both.

**Spec version note:** some docs/implementations based on the 2022 Final edition do not list `exp` the exact same way as the edition **incorporating errata set 1 (2023)**. When building new validators, follow the updated errata and check OP/Spring Security compatibility per deployment—never silently drop expiration checks.

### 7.4. The `events` Claim Must Be Exact

The Logout Token must contain an `events` object with the member:

~~~json
{
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

If a JWT has valid `iss`, `sub`, and signature yet **lacks the back-channel logout event**, it is **not** a valid Logout Token for terminating sessions.

### 7.5. Why Is `nonce` Prohibited?

An OIDC ID Token may carry `nonce` to bind the authentication response to an authorization request. Back-Channel Logout is an **OP-to-RP event outside any login authorization request**, so `nonce` has no place in a Logout Token.

The spec also forbids `nonce` to reduce **JWT confusion** risk: an attacker trying to pass a Logout Token as an ID Token in an authentication flow, or vice versa.

**Never** compare a Logout Token's `nonce` against a login nonce and "accept if matching"; the field must not appear at all.

## 8. Logout Token Validation Rules

This step is **mandatory before modifying any session**. Never process logout simply because base64url-decoding the payload yields plausible-looking JSON.

### 8.1. Spec Validation Procedure

1. **Read form parameter `logout_token`** from the HTTP POST to the right endpoint.
2. If encrypted per JWE contract, **decrypt** with permitted keys/algorithms; verify policy if the client negotiated ID Token encryption.
3. Verify the **JWS signature** using the key of the **exact registered OP issuer**.
4. Accept only permitted `alg` values per OP/client configuration; reject `alg=none`, wrong algorithms, or untrusted keys/issuers.
5. Verify `iss` **matches the issuer** of the registration receiving the event.
6. Verify `aud` contains the RP's **client ID** for that registration, not just `registrationId`.
7. Verify `iat` and `exp` are valid, the token is unexpired, and apply reasonable clock skew.
8. Require valid `jti`; if using a replay cache, verify the ID has not been processed within the window.
9. Verify `events` contains the exact back-channel logout member with a JSON object value.
10. Verify **at least one** of `sub` or `sid` is present.
11. **Reject if the `nonce` claim is present**.
12. Bind `iss` / `sub` / `sid` to stored OIDC session records for the exact provider/client.
13. **Only after all required checks pass**, resolve the sessions and execute logout.

### 8.2. Cases That Must Be Rejected

| Input | Why Invalid |
| --- | --- |
| Unsigned JWT or `alg=none` | Does not prove OP issued the event |
| Invalid signature or `kid` not from issuer | Cannot verify source |
| `iss` belongs to another OP | Must not touch sessions of this issuer |
| `aud` belongs to another client ID | Token is not meant for this RP |
| Missing logout event in `events` | Could be a different kind of JWT |
| Missing both `sub` and `sid` | Cannot identify logout target |
| Contains `nonce` | Logout Tokens must not include nonce |
| Expired `exp` | Outside validity window |
| Unreasonable `iat` outside policy | Risk of stale/future token |
| Unpermitted JWE/alg/key | Violates encryption/signing contract |
| Replayed `jti` rejected per policy | Risk of replayed request |

### 8.3. Do Not Use Token Endpoint Introspection Instead of JWT Validation

A Logout Token is a **logout event JWT**. Never treat it like a Bearer Access Token to call an introspection endpoint while skipping signature/claims validation per the OIDC Back-Channel Logout spec.

When using Spring Security's built-in library/framework support, let it perform validation per contract rather than hand-writing a parser that checks a few fields and calls `session.invalidate()`.

### 8.4. Validator Pseudocode

~~~java
// PSEUDOCODE — this is NOT a complete JWT decoder.
void onBackChannelLogout(SignedJwt incoming, ClientRegistration expected) {
    VerifiedLogoutToken event =
        strictOidcLogoutTokenValidator.verify(incoming, expected);

    // verify() must enforce signature, issuer, audience, timestamps,
    // events, sid/sub, and absence of nonce per spec.
    List<SessionReference> sessions =
        sessionRegistry.findMatchingSessions(
            event.issuer(),
            expected.getClientId(),
            event.subject(),
            event.sessionId());

    // Terminate only validly correlated sessions.
    sessionTerminator.terminate(sessions);
}
~~~

`SignedJwt`, `VerifiedLogoutToken`, `SessionReference`, `strictOidcLogoutTokenValidator`, `sessionRegistry`, and `sessionTerminator` above are **illustrative application concepts**, not Spring Security APIs to copy into a project.

**Prefer Spring Security's `oidcLogout().backChannel(...)` API** for spec validation and session coordination rather than building a custom endpoint.

## 9. How Do `sid` and `sub` Determine Which Sessions to Terminate?

### 9.1. Logout Token with `sid`

Suppose Alice logged into Portal from two browsers:

| Browser | OP issuer | OP `sid` | RP local `JSESSIONID` |
| --- | --- | --- | --- |
| Laptop | company OP | `op-laptop-7a` | `rp-portal-a11` |
| Phone | company OP | `op-phone-9b` | `rp-portal-b22` |

OP issues a Logout Token:

~~~json
{
  "iss": "https://id.example.net/realms/company",
  "aud": "portal-web-client",
  "iat": 1790000000,
  "exp": 1790000120,
  "jti": "logout-laptop-only",
  "sid": "op-laptop-7a",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

The RP looks up the session matching **issuer + audience + sid**, then invalidates `rp-portal-a11`. The phone session is not automatically deleted because its `sid` differs.

### 9.2. Logout Token Without `sid` but with `sub`

Example:

~~~json
{
  "iss": "https://id.example.net/realms/company",
  "aud": "portal-web-client",
  "sub": "user-123",
  "iat": 1790000000,
  "exp": 1790000120,
  "jti": "logout-user-123-all",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Per spec semantics, when **`sid` is absent**, the OP asks the RP to log out **all sessions of that end-user** belonging to the corresponding issuer/client. Both laptop and phone sessions may thus be invalidated.

### 9.3. When Both `sid` and `sub` Are Present

The RP should bind the session to the **exact issuer, client, sid, and identity** rather than honoring an unchecked `sid` against the wrong user. Mismatched correlation can log out the wrong user.

In Spring Security, registry logic uses `sid` to select sessions when provided and `sub` when `sid` is absent; pay attention to the provider session mapping recorded at login.

### 9.4. Impact Scope Table

| Logout Token | Interpretation | Scope at RP |
| --- | --- | --- |
| `sid` only | Log out the specified OP session | Local sessions matching that session ID for the right issuer/client |
| `sub` only | Log out the end-user | All local sessions of that subject for the right issuer/client |
| Both `sub` and `sid` | Identify both user and session | Must not exceed valid matching scope |
| Neither present | Invalid | Reject |
| `sub` from another issuer | Does not belong to this RP session | Reject or no-match per validation/policy |

**Never compare `sid` directly against a browser session ID cookie from an unrelated request.** Back-channel comes from the OP server with no original browser session to compare against.

## 10. OIDC Session Registry: The Bridge Between OP and Local Sessions

On successful login, the RP needs to record correlation data:

~~~text
Local RP Session:
  id = rp-session-a11
  user = Alice
  registration = company

OIDC Login:
  issuer = https://id.example.net/realms/company
  clientId = portal-web-client
  sub = user-123
  sid = op-laptop-7a

Registry:
  (issuer, clientId, sub, sid) -> rp-session-a11
~~~

### 10.1. Why Not Look Up Sessions by Email?

Emails can change, are not always verified, can collide across issuers, or can be recycled. Using email to log out all sessions easily causes cross-tenant mix-ups.

To correlate OIDC identities, prefer verified **issuer + subject**. If the OP issues `sid`, use **issuer + audience/client + sid** for session-specific matching.

### 10.2. The Session Registry Does Not Replace the Session Store

Two distinct data layers:

~~~text
OIDC Session Registry:
  OP sid/sub/iss/aud -> local session id

HttpSession/WebSession Store:
  local session id -> SecurityContext, attributes, CSRF data...
~~~

The registry knows **which sessions to log out**. The session store allows the framework to **invalidate those sessions**. In Servlet, `HttpSession` cannot portably be retrieved arbitrarily by ID from anywhere; Spring Security invokes an internal logout within the proper session context to execute local logout handlers.

### 10.3. Natural Session Expiration Must Also Remove Mappings

When a local session times out, a user performs local logout, or an admin invalidates a session, the registry must be updated. Otherwise stale mappings accumulate and can cause wrong behavior or memory bloat.

In Servlet, Spring Security recommends registering `HttpSessionEventPublisher` to process invalidation/destroy events and clean up unused `OidcSessionInformation`.

### 10.4. Running Multiple Instances

~~~text
                 Load balancer
                  /         \
              Node A       Node B
            Registry A    Registry B
                 \         /
                Shared Session Store
~~~

If Registry A and Registry B live only in memory, an OP sending logout to Node B may fail to find sessions recorded on Node A. **Having a shared `HttpSession`/Redis store alone is not enough** if the OIDC Session Registry remains inconsistently partitioned.

In a cluster, consider a **custom `OidcSessionRegistry`** (Servlet) or **`ReactiveOidcSessionRegistry`** (Reactive), persisting mappings in shared storage with concurrency controls.

## 11. Configuring Spring Security Servlet Back-Channel Logout

### 11.1. Illustrative Dependencies

With Spring Boot 3.x / Spring Security 6.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Spring Boot 4.x has different starter/module organization; use the matching dependencies from your project BOM. To use `oidcLogout().backChannel(...)`, use a Spring Security version that **actually provides this API**.

### 11.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-oidc:
            issuer-uri: https://id.example.net/realms/company
~~~

`company` is the **`registrationId`**; `company-oidc` is the **provider config ID**; `OIDC_CLIENT_ID` is the **audience** the OP must include in Logout Tokens meant for this RP.

The application must configure the exact back-channel URI in the **OP registration**:

~~~text
https://portal.example.net/logout/connect/back-channel/company
~~~

**Configuring OIDC Login in Spring Boot alone does not make the OP send Back-Channel Logout.** The OP must support it and have the endpoint registered.

### 11.3. Servlet SecurityFilterChain

Per Spring Security Servlet documentation, you can configure:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.OidcBackChannelLogoutHandler;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class OidcBackChannelSecurityConfig {

    @Bean
    OidcBackChannelLogoutHandler oidcLogoutHandler() {
        return new OidcBackChannelLogoutHandler();
    }

    @Bean
    HttpSessionEventPublisher sessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Version/API note:** this illustration follows `oidcLogout().backChannel(...)` and `OidcBackChannelLogoutHandler` in Spring Security Servlet documentation. Class packages/imports may change across major versions; in real projects, check the Javadoc/IDE dependencies for your exact version. Do not create a manual controller for the logout endpoint.

`oidcLogout` requires `oauth2Login` to be configured. This is an **OAuth2/OIDC Login feature**, not the `logoutSuccessHandler` of RP-Initiated Logout.

### 11.4. Default Endpoint

For registration `company`, Spring Security exposes:

~~~text
POST /logout/connect/back-channel/company
~~~

The OP calls the endpoint sending form parameter `logout_token`. Spring Security filters/handlers perform verification and session termination.

If the application has multiple `SecurityFilterChain` beans, ensure the chain with `oidcLogout().backChannel(...)` matches this endpoint. Never let another API chain intercept the request first and return a redirect to login or an unexpected 401.

### 11.5. Why Is `HttpSessionEventPublisher` Needed?

When `HttpSession#invalidate()` happens due to logout or timeout, Spring Security needs lifecycle events to evict obsolete `OidcSessionInformation` records.

If the registry retains expired mappings, memory leaks, mistaken lookups, or extra work on back-channel events can occur.

## 12. `JSESSIONID` vs Spring Session `SESSION` Cookie

### 12.1. Cookie Name Depends on Session Configuration

In a servlet container, local sessions typically use:

~~~http
Cookie: JSESSIONID=rp-session-opaque
~~~

When using Spring Session, the default cookie name is typically:

~~~http
Cookie: SESSION=rp-session-opaque
~~~

Spring Security Back-Channel Logout docs emphasize that the default handler's correlation mechanism uses `JSESSIONID` and must be configured when deployments use another cookie name. **Never assume your infrastructure's local session cookie is `JSESSIONID` merely because the app uses Servlet**.

### 12.2. Configuring the Handler with the Matching Cookie Name

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.authentication.logout.OidcBackChannelLogoutHandler;
import org.springframework.security.oauth2.client.oidc.session.OidcSessionRegistry;

@Bean
OidcBackChannelLogoutHandler oidcLogoutHandler(
        OidcSessionRegistry registry) {

    OidcBackChannelLogoutHandler handler =
        new OidcBackChannelLogoutHandler(registry);
    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

This snippet **replaces the no-arg bean** in Section 11—do not declare both and let Spring pick arbitrarily. Verify the package of `OidcSessionRegistry`/handler for your Spring Security version. `"SESSION"` is only appropriate if the cookie is actually named that.

### 12.3. Why Must the Handler Know the Cookie Name?

Spring Security must dispatch an internal logout request targeting the **exact local session** corresponding to `OidcSessionInformation`. If the internal logout request uses the wrong cookie name, the session resolver will not recognize the session to invalidate.

Consequence: the OP gets a response, yet the RP session may fail to terminate as intended. Always test with **browsers holding real session cookies** and **real OP back-channel events** in your deployment topology, not only JWT parser unit tests.

### 12.4. Never Send Browser `JSESSIONID` to the OP

In back-channel logout, the OP uses a Logout Token based on `sid`/`sub` and needs no RP browser cookies. Never put local cookie values into Logout Tokens, provider URLs, or logs to "help the OP find the session."

## 13. Customizing `OidcSessionRegistry` in Servlet

In a single instance, an in-memory registry works for demos. Across multiple instances, register an implementation storing mappings centrally.

### 13.1. Conceptual Contract

Spring Security's `OidcSessionRegistry` supports:

- `saveSessionInformation(OidcSessionInformation info)`.
- `removeSessionInformation(String clientSessionId)`.
- `removeSessionInformation(OidcLogoutToken token)` to look up/remove sessions matching the logout event.

**Structural pseudocode** example (not a ready-to-run class):

~~~java
import org.springframework.security.oauth2.client.oidc.session.OidcLogoutToken;
import org.springframework.security.oauth2.client.oidc.session.OidcSessionInformation;
import org.springframework.security.oauth2.client.oidc.session.OidcSessionRegistry;

public final class DatabaseOidcSessionRegistry
        implements OidcSessionRegistry {

    private final OidcSessionMappingRepository repository;

    public DatabaseOidcSessionRegistry(
            OidcSessionMappingRepository repository) {
        this.repository = repository;
    }

    @Override
    public void saveSessionInformation(OidcSessionInformation info) {
        repository.save(info);
    }

    @Override
    public OidcSessionInformation removeSessionInformation(
            String clientSessionId) {
        return repository.removeByClientSessionId(clientSessionId);
    }

    @Override
    public Iterable<OidcSessionInformation> removeSessionInformation(
            OidcLogoutToken token) {
        if (token.getSessionId() != null) {
            return repository.removeByIssuerAudienceAndSid(token);
        }
        return repository.removeByIssuerAudienceAndSubject(token);
    }
}
~~~

`OidcSessionMappingRepository` and `removeByIssuerAudienceAndSid(...)` / `removeByIssuerAudienceAndSubject(...)` are **application interfaces/methods you must implement yourself**. Spring Security docs illustrate a similar concept; no JPA repository is auto-generated for this.

### 13.2. Registry Query Rules

Logical schema:

~~~text
oidc_session_mapping
  local_session_id
  issuer
  client_id / audience
  subject
  op_session_id (sid, nullable)
  created_at
  expires_at
  version
~~~

Query with `sid`:

~~~sql
-- SAMPLE SQL: needs proper indexes, transactions, and parameter binding.
SELECT local_session_id
FROM oidc_session_mapping
WHERE issuer = :issuer
  AND client_id = :audience
  AND op_session_id = :sid;
~~~

Query when **`sid` is absent**:

~~~sql
SELECT local_session_id
FROM oidc_session_mapping
WHERE issuer = :issuer
  AND client_id = :audience
  AND subject = :sub;
~~~

Never write:

~~~sql
-- ANTI-PATTERN: omitting issuer/client causes cross-tenant/cross-app logout.
DELETE FROM oidc_session_mapping WHERE subject = :sub;
~~~

because `sub` is only stable within an issuer's scope and may exist across different registrations.

### 13.3. Consistency

When the OP sends logout requests across multiple nodes, a shared registry must support:

- Fast lookups by issuer/audience/sid or issuer/audience/sub.
- Idempotent updates/deletions.
- Protection against arbitrary session ID reassignment.
- Cleanup when local sessions expire.
- Appropriate atomic/transactional behavior.
- Access control over session mapping data.
- Never exposing raw `sid`/session IDs in logs or public dashboards.

With a distributed session store, deleting only the mapping record **does not necessarily invalidate the local session**. The session termination layer must still run the framework's configured logout policy.

## 14. Spring Security Reactive/WebFlux Back-Channel Logout

OIDC Back-Channel Logout is also supported on the Reactive stack in compatible Spring Security versions.

### 14.1. Comparing Servlet and Reactive Classes

| Feature | Servlet | Reactive |
| --- | --- | --- |
| Security DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Back-channel handler | `OidcBackChannelLogoutHandler` | `OidcBackChannelServerLogoutHandler` |
| Registry | `OidcSessionRegistry` | `ReactiveOidcSessionRegistry` |
| Repository behavior | Synchronous | `Mono` / `Flux` |
| Default session cookie | Usually `JSESSIONID` | Depends on WebFlux/Spring Session, often `SESSION` |

**Never mix Servlet handlers into Reactive `SecurityWebFilterChain`** or pass a Reactive registry interface to a Servlet DAO without a proper adapter.

### 14.2. Reactive Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 14.3. Illustrative `SecurityWebFilterChain`

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.OidcBackChannelServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOidcLogoutConfig {

    @Bean
    OidcBackChannelServerLogoutHandler oidcLogoutHandler() {
        return new OidcBackChannelServerLogoutHandler();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()))
            .build();
    }
}
~~~

This example follows the Reactive OIDC Logout documentation for versions exposing the `oidcLogout` API. Do not add Servlet's `HttpSessionEventPublisher` merely because it appears in Spring MVC examples; reactive session lifecycles are managed by different components.

### 14.4. Reactive Handler with Matching Cookie Name

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.oidc.session.ReactiveOidcSessionRegistry;
import org.springframework.security.web.server.authentication.logout.OidcBackChannelServerLogoutHandler;

@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler(
        ReactiveOidcSessionRegistry sessionRegistry) {

    OidcBackChannelServerLogoutHandler handler =
        new OidcBackChannelServerLogoutHandler(sessionRegistry);
    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

This **replaces** the no-arg bean in the reactive example above. Only use `SESSION` if your WebFlux/Spring Session setup actually issues that cookie; do not assume it applies to every version.

### 14.5. Reactive Registry Must Be Non-Blocking

A `ReactiveOidcSessionRegistry` implementation can persist mappings in R2DBC/Reactive Redis or a compatible backend:

~~~text
saveSessionInformation(info) -> Mono<Void>
removeSessionInformation(clientSessionId) -> Mono<OidcSessionInformation>
removeSessionInformation(logoutToken) -> Flux<OidcSessionInformation>
~~~

This is a **contract description**, not advice to call `subscribe()` manually. Implementations should return reactive pipelines so the framework manages transactions/completion; never call `block()` on the event loop to query a synchronous JDBC repository.

### 14.6. Do Not Confuse Reactive Back-Channel Logout with WebClient OAuth2 Filter

`ServerOAuth2AuthorizedClientExchangeFilterFunction` helps **WebClient attach Access Tokens when calling APIs**.

`OidcBackChannelServerLogoutHandler` helps the **RP receive Logout Tokens from the OP and end local sessions**.

Both components may appear in the same WebFlux app yet serve **opposite HTTP directions and different token types**.

## 15. How Does Local Session Termination Work in Servlet?

Spring Security stores session info in `OidcSessionRegistry`. When the OP sends a valid Logout Token, the handler must terminate the exact `HttpSession`.

In the Servlet API, there is no portable standard API to look up an arbitrary `HttpSession` by ID and call `invalidate()` outside a request context. Spring Security solves this by **invoking an internal logout matching that session**:

~~~text
Verified back-channel event
    |
    v
OidcSessionRegistry
    |
    +-- localSessionId = A
    +-- localSessionId = B
    |
    v
Spring Security internal logout operations
    |
    +-- Reconstruct matching session context
    +-- Run matching LogoutHandlers
    +-- Invalidate HttpSession
    +-- Clean up mapping
~~~

### 15.1. Role of CSRF and Internal Logout

Local browser logout endpoints in Spring Security typically require CSRF protection. OP back-channel requests **carry no browser CSRF token**, since they do not originate from a browser session.

Spring Security handles this type of request verified by a **signed Logout Token** while running an internal logout flow tied to the session.

**Do not solve this with `csrf.disable()` app-wide.** Disabling CSRF globally opens vulnerabilities on other browser endpoints. Use the framework's built-in back-channel support and customize endpoints/policies only when genuinely required.

### 15.2. Do Not Manually Call Local `/logout` Controller with an Anonymous Request

A homemade pattern such as:

~~~text
OP POST -> /backchannel
         -> HTTP client calls /logout?sid=...
~~~

gives local `/logout` no basis to know which browser session to invalidate without a verified mapping/context. Use `OidcBackChannelLogoutHandler` / session registry instead of building a logout proxy with query parameters.

## 16. Does Back-Channel Logout Revoke OAuth2 Tokens?

This is a critical misconception:

**Terminating the RP session ≠ revoking issued Access Tokens / Refresh Tokens.**

Example:

~~~text
RP HttpSession: INVALIDATED

Issued Access Token:
  10 minutes left until exp
  Resource Server may still accept it

Stored Refresh Token:
  may remain in persistent authorized client service
  requires separate revocation/cleanup policy
~~~

### 16.1. What Does the Spec Say About Refresh Tokens?

OpenID Connect Back-Channel Logout 1.0 recommends:

- Refresh Tokens **without `offline_access`** tied to the logged-out session **should be revoked**.
- Refresh Tokens issued with **`offline_access`** **should generally not be revoked automatically** solely on session logout, as they may represent separately consented offline access.

This is protocol guidance; real Authorization Servers and client implementations may differ in behavior and policy. Never assume Spring Security wipes the entire `OAuth2AuthorizedClient` persistent store and calls revocation endpoints after every back-channel request.

### 16.2. Deleting Local Authorized Client Differs from OP Revocation

| Action | Effect |
| --- | --- |
| `HttpSession.invalidate()` | Ends local browser session |
| Delete entry in `OAuth2AuthorizedClientService` | RP stops loading tokens from that entry |
| Call token revocation endpoint per RFC 7009 | Asks Authorization Server to revoke token if provider supports it |
| Invalidate OP SSO session | OP stops treating browser as logged in under that session |
| Resource Server rejects token | Depends on expiration, introspection, revocation, or API policy |

Never use "Back-Channel Logout revoked all JWT Access Tokens" as a security promise. An already-issued self-contained JWT can still be accepted by a Resource Server until expiration unless additional revocation/introspection/session-binding strategies exist.

### 16.3. Connections and Offline Access

An application might maintain a "Google Calendar connection" or "ERP integration" with an offline Refresh Token in a database, independent of browser sessions. Upon receiving back-channel logout, decide per product policy:

- Terminate only the browser session.
- Should session-scoped delegated authorized clients be deleted?
- Should offline access remain valid?
- If the user clicks "Disconnect account," should tokens be revoked?

**OIDC logout and disconnecting an OAuth2 integration are two different operations.** Do not improperly wipe offline access just because an OP session ended, nor skip revocation when policy demands it.

## 17. Multi-Provider and Multi-Tenant: Never Log Out the Wrong Customer

Suppose an RP supports:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: portal-company-client
            authorization-grant-type: authorization_code
          partner:
            provider: partner-oidc
            client-id: portal-partner-client
            authorization-grant-type: authorization_code
        provider:
          company-oidc:
            issuer-uri: https://id.company.example.net
          partner-oidc:
            issuer-uri: https://login.partner.example.org
~~~

This is **YAML illustrating mapping principles**, not a complete standalone runnable config: a real confidential OIDC client also needs client secret/auth method, redirect URI, and scopes, or matching provider metadata.

Two logout endpoints:

~~~text
/logout/connect/back-channel/company
/logout/connect/back-channel/partner
~~~

### 17.1. Validate Audience by Client ID, Not by `registrationId`

A Logout Token sent to:

~~~text
/logout/connect/back-channel/company
~~~

must contain `aud` matching **`portal-company-client`**, not merely the string `company` from the URL path.

An attacker must not be able to send a validly signed token meant for the partner registration to the company endpoint to wipe company sessions.

### 17.2. Issuer Separates Trust Boundaries

Even when both OPs have user `sub="123"`:

~~~text
company issuer + subject 123 != partner issuer + subject 123
~~~

The registry must use the validated issuer. Never use email or username as a global logout key.

### 17.3. One OP, Multiple Client IDs

An organization might have Portal and Billing both trusting one OP under **two separate client IDs**. Portal's Logout Token must not automatically terminate Billing sessions unless the OP sends an event for Billing or the system has an explicit, valid global logout policy.

### 17.4. Tenant from URL Must Not Dictate Arbitrary Key Trust

Never build:

~~~text
POST /backchannel/{tenantId}
  -> read jwks_uri from caller query
  -> parse JWT and delete session
~~~

If `jwks_uri` or `issuer` comes from an unallowlisted request parameter, an attacker can supply their own key and sign forged JWTs. Trust material must come from **registered `ClientRegistration`/issuer**, never from unverified JWT headers or query strings.

## 18. Replay, Expiration, and DoS Protection

### 18.1. `jti` Supports Replay Prevention

Each Logout Token has a unique `jti`. If infrastructure needs to detect repeated events, you can store:

~~~text
key = hash(issuer | audience | jti)
ttl = validity window + clock skew per policy
~~~

A `jti` store needs a TTL to avoid unbounded growth. Never log raw JWTs or use raw user `jti` values as public metric labels.

Per the spec, `jti` replay checking is an optional extra defense; do not assume every Spring Security deployment ships with a distributed replay cache enabled by default.

### 18.2. Duplicate Events and Idempotency

If the OP retries after a timeout while the RP already invalidated the session, the RP must not accidentally delete another session or fail operationally.

**A valid repeated logout event when the local session is already terminated can return success** under idempotent semantics. With a replay cache, distinguish benign duplicate deliveries from suspicious replays in monitoring without altering session identity.

### 18.3. Short-Lived Logout Tokens

The spec recommends short expiration windows for Logout Tokens—typically a few minutes at most (best-practice guidance mentions around two minutes in security considerations)—to limit the window during which an intercepted token could be abused.

The RP must enforce `exp` and `iat` with bounded clock skew—**never accept tokens indefinitely** because "OP clocks sometimes drift."

### 18.4. Rate Limiting

Since the back-channel endpoint may be reachable over the Internet, apply:

- Request body size limits.
- Strict HTTP method and `Content-Type` checks.
- Rate limiting aligned with trust networks and OP retry policies.
- Careful TLS and WAF rules that do not block valid OPs.
- Bounded JWT parsing/validation workload.
- Metrics for invalid signature/issuer/audience rejections without logging tokens.

Never rely on an IP allowlist **instead of** Logout Token validation. IPs can change or route through proxies; signature and claims verification remain mandatory.

## 19. Reverse Proxy, Base URL, and HTTP Ingress

A typical deployment:

~~~text
https://portal.example.net
    |
    v
Load balancer (TLS termination)
    |
    v
Spring Boot instance on private port 8080
~~~

### 19.1. OP Must Use the Public HTTPS URL

RP registers:

~~~text
https://portal.example.net/logout/connect/back-channel/company
~~~

**Never** register `http://localhost:8080/...` with a cloud OP unless the OP runs in a special environment permitting it.

### 19.2. Proxy Rewrites Can Break Endpoint Matching

If a proxy adds a prefix:

~~~text
Public: /portal/logout/connect/back-channel/company
Internal: /logout/connect/back-channel/company
~~~

verify the OP registers the exact public URI, the proxy forwards the right path, and the `SecurityFilterChain` still matches the internal endpoint.

### 19.3. Never Redirect OP POSTs to Browser Login

Because the OP is a server caller without a browser session, a response like:

~~~http
HTTP/1.1 302 Found
Location: /oauth2/authorization/company
~~~

usually means the endpoint was intercepted by a security matcher or back-channel config is inactive. This is **not** a successful logout. Fix routing/filter-chain order—never try to send the OP through a browser authorization flow.

## 20. Observability: Tracking Events Without Logging Logout Tokens

A safe event log might contain:

~~~text
event=oidc_backchannel_logout
issuer_alias=company-oidc
registration_id=company
outcome=success
match_mode=sid
matched_sessions=1
correlation_id=internal-evt-44ef
~~~

This is an **illustrative format**, not automatic Spring Security logging. Never log:

- Raw `logout_token` or JWT signatures.
- Local session IDs / `JSESSIONID` or `SESSION` cookies.
- Raw `sid`/`sub` unless justified and permitted by privacy policy.
- Client Secrets, ID Tokens, Access Tokens, Refresh Tokens.
- Unredacted HTTP bodies or request headers.

### 20.1. Useful Metrics

| Signal | Operational Meaning |
| --- | --- |
| Valid events received by issuer/registration | OP is emitting events |
| Rejection rate for JWT signature/issuer/aud | Possible misconfiguration or malicious requests |
| Valid events matching zero sessions | Session expired, registry lost mapping, or delayed delivery |
| Session invalidation success rate | Reliability of back-channel integration |
| Database/session store errors | Logout may be incomplete across cluster |
| Registry drift across nodes on scale-out | Need shared registry |
| HTTP 302/401/403 at back-channel endpoint | Likely routing/CSRF/security chain misconfiguration |
| Event processing latency | Monitor risk of OP timeouts/retries |

**Never use session IDs or random `jti` values as metric labels** in high-cardinality systems. Use low-cardinality buckets/classes and access-controlled correlation logs.

### 20.2. Sensitive Audit Data

Back-channel logout may correlate with user offboarding, account lockouts, or admin actions. Audit logs must support investigation while complying with personal-data/retention policies. An event sent by the OP does not prove the user personally clicked "Log Out"; it may stem from an admin or security policy.

## 21. Protocol Test Matrix

**Never use a Logout Token fabricated by Base64url-encoding JSON without a signature** to simulate a passing test. Passing tests must use a JWT signed by a **test issuer key** trusted by the client in the test environment, with matching issuer/audience.

| Scenario | Expected Outcome |
| --- | --- |
| Validly signed Logout Token, `sid` matches one session | Only that session is invalidated |
| Validly signed Logout Token, `sub` only | All local sessions matching issuer/client/sub are terminated |
| Valid Logout Token with both `sub` and `sid` | Only sessions matching both identity and session terminate |
| Token missing both `sub` and `sid` | Reject 400 |
| Token contains `nonce` | Reject |
| Token missing logout event in `events` | Reject |
| Token has wrong `iss` | Reject; delete no sessions |
| Token has `aud` of another client | Reject; delete no sessions of other client |
| Invalid signature or `alg=none` | Reject |
| Expired `exp` or unreasonable `iat` | Reject per validation policy |
| Malformed/missing `jti` | Reject |
| Valid token yet local session already expired | Idempotent success / no unrelated session deleted |
| OP resends event after timeout | No unintended side effects; replay handled per policy |
| Local `JSESSIONID` vs Spring Session `SESSION` | Handler uses matching cookie name to invalidate |
| User has two `sid` values across two devices | Logging out one `sid` preserves the other device |
| Same `sub` across two issuers | No cross-issuer logout |
| Same OP with two client IDs | No cross-client logout |
| Two pods with isolated in-memory registries | Test catches missing mappings |
| Shared registry/session store | Event hitting Node B still invalidates Node A's session |
| OP unreachable or request timeout | Alerts and retry policy triggered |
| API without OIDC login | Do not mistakenly enable `oidcLogout` on OAuth2 Client Credentials apps |
| Spring Session loses mapping | Do not falsely report completion when policy-required invalidation fails |

### 21.1. Unit Tests vs Integration Tests

Unit tests can verify a mapping repository:

~~~text
findByIssuerAudienceSid(iss, aud, sid)
  -> exact local session IDs

findByIssuerAudienceSub(iss, aud, sub)
  -> exact end-user sessions
~~~

However, repository unit tests **do not prove** JWT signature validation, Spring Security filter wiring, or actual `HttpSession.invalidate()`.

Integration tests should run the OIDC Login flow (or populate session registry state per contract), send an HTTP POST signed by the test issuer key, and verify that subsequent requests carrying the old session cookie are no longer authenticated.

### 21.2. Safely Testing Invalid HTTP Requests

For example, sending an **invalid fake token** to confirm the endpoint rejects it:

~~~bash
curl -i -X POST \
  "https://portal.example.net/logout/connect/back-channel/company" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "logout_token=INVALID_TEST_TOKEN"
~~~

**Run only against authorized test/staging environments**, never putting real production Logout Tokens into shell history. The expected result is that the request **is rejected** without logging out any user. Exact HTTP status depends on the filter chain/handler when a request fails JWT parsing; to verify full protocol behavior, sign valid JWTs with a test issuer.

### 21.3. Testing Real Logout from the OP

A solid end-to-end test:

1. Browser A logs into RP via test OP, saving Cookie A.
2. Browser B logs in as the same user under a different OP session, saving Cookie B.
3. RP records mappings `sidA -> sessionA` and `sidB -> sessionB`.
4. OP emits a Logout Token containing only `sidA`.
5. RP returns HTTP success per contract.
6. Browser A requests a protected route and is prompted to re-authenticate.
7. Browser B remains authenticated while OP Session B is still active.
8. OP emits a `sub`-only token for the user; RP terminates remaining matching sessions.
9. Verify sessions of other issuers/clients are untouched.

### 21.4. Testing Token Lifecycle Outside the Session

In integration tests, distinguish:

~~~text
Browser session invalidated        -> expected
Stored Refresh Token still exists  -> possible, depending on policy
Resource Server accepts Access Token -> possible until expiration
~~~

Explicitly test whatever your product promises regarding revocation/cleanup; never treat "redirected back to login" as proof that all OAuth2 credentials are dead.

## 22. Common Implementation Mistakes

### 22.1. Using an ID Token Instead of a Logout Token

A logged-in user's ID Token is not a logout notification from the OP. A JWT having `iss` and `sub` is not enough; it must have the signature and Logout Token claims/events per spec.

### 22.2. Taking `sid` and Deleting an `HttpSession` with the Same Value

`sid` is the **OP session ID**, while `JSESSIONID`/`SESSION` is the **RP session ID**. Look up the registry recorded at login.

### 22.3. Logging Out Using `sub` Only Without Checking Issuer/Client

Another OP can have the exact same `sub`. Omitting `iss` or `aud` easily wipes sessions belonging to other users/tenants.

### 22.4. Decoding the JWT Manually and Trusting the Payload

Base64url decoding only extracts JSON—it **does not verify the signature**. Never invalidate sessions before verifying the Logout Token.

### 22.5. Skipping `events` and `nonce` Checks

That opens **cross-JWT confusion** vulnerabilities. Logout Tokens must contain the exact event and must never contain `nonce`.

### 22.6. Assuming Logout Token `aud` Equals `registrationId`

In Spring, `registrationId="company"` may differ from `clientId="portal-web-client"`. JWT `aud` must match the exact client ID/trust context.

### 22.7. Disabling CSRF App-Wide So the OP Can POST

Back-channel has its own request-handling path. Disabling CSRF across all browser endpoints opens unrelated vulnerabilities; use Spring Security OIDC Logout support and configure it accurately.

### 22.8. Forgetting to Configure the URI in the OP Console

The Spring Security endpoint may be running, yet the OP has nowhere to call. Register the real `backchannel_logout_uri`, not just `oidcLogout()` in code.

### 22.9. OP Calling `localhost` or Unreachable Private IPs

The OP needs a network route to the RP endpoint. Use an appropriate public/trusted ingress and TLS; never assume browser reachability means OP server reachability.

### 22.10. Using the Wrong Cookie Name

RP uses Spring Session `SESSION`, yet the handler defaults to `JSESSIONID`, failing to locate the local session during internal logout. Set `setSessionCookieName(...)` to match your deployment.

### 22.11. Sharing the Session Store Without Sharing the OIDC Registry

Redis-backed sessions do not automatically share an in-memory `OidcSessionRegistry` across pods. Design a cluster-safe registry or compatible routing/affinity and test it.

### 22.12. Equating Logout with Revoking All OAuth2 Tokens

RP session invalidation does not automatically stop JWT Access Tokens from working at APIs. Use short TTLs, revocation/introspection, and dedicated Refresh Token policies.

### 22.13. Logging Logout Tokens for Debugging

JWTs can carry `sub`/`sid`/issuer, signatures, and sensitive claims. Never log raw tokens, queries/bodies, or session cookies.

### 22.14. Letting Browsers Call an Endpoint with Query `sid=...`

That is not valid Back-Channel Logout; attackers can DoS/log out other users without signature verification. The endpoint must accept HTTP POST with a verified `logout_token`.

### 22.15. Failing to Distinguish OP Sessions from Offline OAuth2 Connections

`offline_access` has a different lifecycle from browser sessions. Do not automatically delete all of a user's offline Refresh Tokens on a back-channel event unless product/OP policy requires it.

### 22.16. Returning 302 to the OP Instead of a Server-to-Server Response

The OP is a server caller; a 302 to the login page means the endpoint was blocked by a security filter or misrouted. The back-channel endpoint must validate the JWT and return HTTP success/failure per protocol.

## 23. Troubleshooting by Symptom

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| OP never sends POST | Back-channel not enabled at OP or URI unregistered | Check Discovery and client registration |
| OP gets 404 | Wrong endpoint path/`registrationId`/proxy rewrite | Check `/logout/connect/back-channel/{registrationId}` |
| OP gets 302 to login | `oidcLogout` unconfigured or wrong `SecurityFilterChain` | Check filter chain matching |
| OP gets 403 | Blocked by CSRF/method/security chain | Use framework back-channel support; do not disable CSRF globally |
| OP gets 400 | Malformed JWT, bad signature/iss/aud/claims | Inspect safe error category and provider contract |
| Valid JWT yet RP stays authenticated | Wrong registry, cookie name, session store, or internal logout | Inspect mapping and session lifecycle |
| Logging out one device logs out all devices | OP sent `sub`-only or wrong `sid` mapping | Check `sid` support and verified token payload |
| Logout by `sid` finds no session | Login ID Token lacked `sid`, registry skipped saving, or session expired | Check OP metadata and registry |
| Node A logs out fine, Node B fails | In-memory registry not shared | Shared registry/multi-node integration |
| Cookie still visible in browser | Back-channel does not directly manipulate browser cookies | Verify next request is no longer authenticated |
| Stale `exp` JWT accepted | Broken validation/clock skew | Enforce `exp`/`iat`/signature |
| One OP logs out wrong tenant | Registry queried by `sub` only | Bind issuer/audience/sid/sub |
| API still accepts Access Token after logout | Resource Server token unexpired/unrevoked | Check API token lifecycle; do not blame cookies |
| Refresh Token still exists | Offline policy or uncleaned store | Define `offline_access`/revocation policy |
| OP retries repeatedly | RP timeout/network error/invalid response | Monitor endpoint latency and idempotency |
| Session registry grows unbounded | Expired sessions never cleaned up | Event publisher/session lifecycle, TTL |
| OIDC login works yet logout fails | OIDC login does not imply back-channel is enabled | Verify both sides and run integration tests |

### 23.1. Ordered Investigation Questions

~~~text
1. Does the OP have backchannel_logout_supported = true?
2. Did the RP register backchannel_logout_uri as the right public HTTPS URL?
3. Can the OP network reach the RP endpoint?
4. Which SecurityFilterChain receives this POST?
5. Does the Logout Token have a valid signature and claims?
6. Do iss and aud map to the right ClientRegistration?
7. Do sid/sub match a session recorded in the OIDC registry?
8. Is the registry shared across pods?
9. Can the RP session store invalidate the exact local session?
10. Is the cookie name in internal logout accurate?
11. Is a subsequent request with the old cookie still authenticated?
12. Does the product require revoking/cleaning OAuth2 tokens beyond the session?
~~~

Do not answer these questions by printing JWTs or session cookies to logs. Use controlled metadata and correlation IDs.

## 24. Real-World Scenarios

### Scenario A — User Logs Out in Another Application

Alice has Portal open while logging out at the OP from the Billing app.

**Expected outcome:** OP emits a Back-Channel Logout Token to Portal; Portal invalidates the matching local session. When Alice next loads a Portal page, the old session no longer has access.

### Scenario B — Log Out Laptop Only, Keep Phone

OP holds two sessions `sid=laptop` and `sid=phone` for the same `sub`. OP emits a token with `sid=laptop`.

**Expected outcome:** RP terminates the local session mapped to laptop, without deleting phone unless a corresponding OP event arrives.

### Scenario C — Global Logout by User

OP omits `sid` and sends a Logout Token with `sub=user-123`.

**Expected outcome:** RP terminates all local sessions for that user within the **matching issuer/client audience**, across multiple devices.

### Scenario D — Two IdPs Share the Same Subject

Company OP and Partner OP both have subject `user-123`.

**Expected outcome:** Company's token does not log out sessions authenticated via Partner because issuer and audience differ.

### Scenario E — Spring Session Redis Uses `SESSION`

The app migrated from container sessions to Spring Session, yet the OIDC handler still assumes `JSESSIONID`.

**Resolution:** Configure `OidcBackChannelLogoutHandler.setSessionCookieName("SESSION")` (or the Reactive equivalent) and verify real session termination.

### Scenario F — OP Hits a Node Lacking the Registry

User logged into Node A. OP sends logout to Node B behind a load balancer; Node B lacks the in-memory mapping.

**Resolution:** Custom shared `OidcSessionRegistry` / `ReactiveOidcSessionRegistry` or tested session affinity architecture; do not assume Redis shared sessions automatically share the registry.

### Scenario G — Resource Server Continues Accepting Token

The RP session logged out, yet the prior Access Token is unexpired and the API uses self-contained JWTs.

**Resolution:** This is an Access Token expiration/revocation matter; use short token TTLs, introspection, or revocation/denylisting per architecture rather than concluding back-channel is broken.

### Scenario H — OP Sends Logout Token with Wrong Audience

Issuer matches, yet `aud=billing-client`; the request hits Portal's `company` registration.

**Outcome:** RP must reject it without deleting Portal sessions because the token is not meant for this client.

### Scenario I — Attacker Crafts JSON with `sub`

An attacker sends a `logout_token` that is self-signed or unsigned JWT containing Alice's `sub`.

**Outcome:** RP rejects; **no** sessions are deleted. Signature, issuer, audience, and logout event are mandatory checks.

### Scenario J — Provider Lacks `sid` in ID Token

OP states it supports Back-Channel Logout yet does not support session-specific `sid`, issuing only `sub`.

**Resolution:** Align RP metadata `backchannel_logout_session_required=false`; accept subject-based logout semantics rather than trying to guess `sid`.

### Scenario K — Logout Request Retried

OP times out waiting for a response and retries the same Logout Token. The RP session was already invalidated.

**Outcome:** Logout handling is idempotent and does not delete new/other sessions. With `jti` replay tracking, classify appropriately for monitoring.

### Scenario L — Portal Acts as OP for Downstream Apps

Portal is an RP to Company OP, yet also issues login sessions to downstream applications.

**Design:** After receiving a valid back-channel logout, Portal may need to propagate logout events downstream per architecture—not merely invalidate Portal's session if global SSO logout is promised.

## 25. Pre-Production Checklist

| Question | What to Confirm |
| --- | --- |
| Does the OP support back-channel? | Discovery metadata and provider documentation |
| Does the OP support `sid`? | `backchannel_logout_session_supported` and ID Token behavior |
| Did the RP register the endpoint? | `backchannel_logout_uri` matches public HTTPS route |
| Did the RP enable `oidcLogout().backChannel(...)`? | Right `SecurityFilterChain`, dependency/version |
| Is `oauth2Login` configured? | Back-channel is not a Client Credentials feature |
| Is Logout Token verified? | Signature, alg, iss, aud, iat, exp, jti, events, sid/sub, no nonce |
| Are mappings scoped to owner? | issuer + client + sid/sub -> local session |
| Is the cookie name right? | `JSESSIONID` or `SESSION` per infrastructure |
| Is the registry shared multi-node? | Custom registry when clustering requires it |
| Does the session store actually invalidate? | Integration test with old browser cookie |
| Is session lifecycle cleaned up? | Event publisher/TTL/invalidation |
| Are OP POSTs blocked by CSRF/chain? | Test 200/400 without disabling CSRF globally |
| Rate limit/DoS/replay? | Body limits, TTL, optional `jti` cache, monitoring |
| Are client IDs tenant-isolated? | `aud`/`iss` verification and registry isolation |
| Access/Refresh Token lifecycle? | Separate session logout from revocation/offline access |
| Are logs safe? | No unnecessary raw tokens/`JSESSIONID`/`sub`/`sid` |
| Do OP callbacks/endpoints pass through a proxy? | TLS, paths, forwarding headers, reachability |
| Tested across two devices? | `sid`-scoped vs `sub` all-sessions |
| Tested multi-instance? | Logout hitting any node terminates the right session |

## 26. References

- OpenID Connect Back-Channel Logout 1.0 — **incorporating errata set 1 (2023)**: https://openid.net/specs/openid-connect-backchannel-1_0.html
- OpenID Connect Back-Channel Logout 1.0 — Final 2022 edition (historical comparison): https://openid.net/specs/openid-connect-backchannel-1_0-final.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security 6.5 — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/logout.html
- Spring Security 6.5 — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/logout.html
- Spring Security — `OidcBackChannelLogoutHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/OidcBackChannelLogoutHandler.html
- Spring Security — `OidcSessionRegistry` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/session/OidcSessionRegistry.html
- Spring Security — `OidcBackChannelServerLogoutHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/OidcBackChannelServerLogoutHandler.html
- Spring Security — `ReactiveOidcSessionRegistry` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/session/ReactiveOidcSessionRegistry.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009

## 27. Summary

~~~text
User performs OIDC login
  -> OP issues ID Token (with iss, sub, sid if supported)
  -> RP verifies login and creates HttpSession/WebSession
  -> RP writes OIDC Session Registry:
       OP issuer + client + sid/sub -> RP local session

User or administrator logs out at OP
  -> OP sends POST backchannel_logout_uri
       Content-Type: application/x-www-form-urlencoded
       logout_token = signed JWT
  -> RP validates:
       signature + alg + iss + aud + iat + exp + jti
       backchannel logout events
       sub or sid
       NO nonce
  -> RP looks up local sessions in registry
       sid: exact specific OP session
       sub-only: all user sessions in matching issuer/client
  -> Spring Security runs logout/invalidation
  -> RP responds HTTP 200 on success
  -> Old browser cookie can no longer access authenticated session

Do not equate:
  Logout Token != ID Token != Access Token
  OP sid != RP JSESSIONID / SESSION
  Local session invalidation != Access/Refresh Token revocation
~~~

**Five key takeaways:**

1. **Back-Channel Logout is OP → RP server-to-server HTTP POST communication**, needing no open browser tab. The RP receives `logout_token`, not a query parameter containing a session ID.
2. **The Logout Token must be validated per OIDC Back-Channel Logout**, including signature, issuer, audience, timestamps, `jti`, `events`, at least `sub` or `sid`, and **no `nonce`**. ID Tokens and Access Tokens must never replace Logout Tokens.
3. **`sid` targets a specific OP session, while `sub` without `sid` can log out all sessions of the user** within the right issuer and client. A registry is required to map OP identities to RP local sessions.
4. **Spring Security provides `oidcLogout().backChannel(...)` for Servlet and Reactive**, but you must configure the right cookie name, registry, session lifecycle, network endpoint, and OP registration, especially in clusters.
5. **Session logout does not automatically revoke OAuth2 tokens.** Refresh Tokens, offline access, Access Token TTLs, and Resource Server validation require dedicated policies if the product promises revoking all access.

Clearly understanding the difference between a **Logout Token**, an **OP Session ID**, and an **RP local session** enables reliable Single Sign-Out, prevents cross-user/cross-tenant session deletions, and preserves security boundaries when terminating sessions from outside the browser.
