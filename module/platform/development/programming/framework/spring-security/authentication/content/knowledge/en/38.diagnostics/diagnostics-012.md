# Account Lock or Logout Fails to Revoke Still-Valid Sessions and Tokens

## 1. Symptoms and What to Diagnose

An administrator sets `user.status = LOCKED`, or a user clicks **Sign Out** and sees the UI return to the login screen. Yet another browser can still access the API, a refresh token can still exchange for a new access token, or a validly signed JWT is still accepted by the Resource Server. This is common because **locking an account, logging out the current session, revoking other sessions, and revoking tokens are separate mechanisms**.

This lesson belongs to the **Diagnostics** section of the Spring Security authentication module. The goal is not just knowing how to call `logout()` or `deleteById()`, but **pinpointing which authentication path remains valid, why, who owns the state store, and where revocation outcomes must be verified**.

### Learning Outcomes

1. Trace requests after lock/logout to distinguish HTTP sessions, remember-me, JWT access tokens, opaque access tokens, refresh tokens, OAuth authorized clients, and IdP SSO sessions.
2. Understand **Spring Security Servlet default logout**: clearing `SecurityContext`, invalidating the **current session**, and cleaning up remember-me/CSRF in the logout flow; it does not mean "logout all devices".
3. Find why other sessions survive: local session registries, missing/wrong principal indexes, shared Spring Session stores, concurrent requests, multi-node caches, sticky sessions, and re-created authentications.
4. Explain why **offline JWT validation** still accepts validly signed tokens after an account is locked; build policies checking account/version, `jti` denylists, or accepting transparent residual lifetimes.
5. Distinguish **revoking refresh tokens/grants at the Authorization Server** from revoking access tokens on Resource Servers; understand RFC 7009 and the `active` property in RFC 7662 introspection.
6. Design multi-credential revocation workflows with transactions, outboxes, idempotency, race checks, cache TTLs, and evidence from real tests.
7. Write before/after reproduction tests with Java 17 and separate HTTP clients, never treating a single HTTP `200` or `302` as proof all credentials are dead.

**Scope:** Spring Boot 3.x / Spring Security 6.x (Servlet) and OAuth2/Resource Server variants; where WebFlux or Spring Security 7.x applies, check matching APIs. The Java 17 example in Section 9 runs standalone; Spring Framework snippets need real dependencies/projects. There is no built-in default Spring method that automatically finds and revokes **every** JWT, refresh token, and IdP session for a user.

## 2. Credential Lifecycle Map

~~~text
                        LOCAL ACCOUNT
                        userId = u-123
                        status = ACTIVE/LOCKED
                        securityVersion = 12
                                |
                    +-----------+------------+
                    |           |            |
                Browser A   Browser B     Mobile app
                    |           |            |
              HttpSession A HttpSession B   refresh token R1
                    |           |                |
              SecurityContext SecurityContext   Authorization Server
                    |           |                |
                 API session  API session       access JWT J1
                                                   |
                                                   v
                                           Resource Server X/Y
                                              verify signature
                                              iss/aud/exp/...
                                                   |
                                         optional account check
                                         or revocation/denylist

Other independent state:
- SSO session at IdP (OIDC/SAML)
- OAuth2AuthorizedClient access/refresh tokens for downstream API
- persistent remember-me tokens
- device/API keys and passwordless authenticators
~~~

**Key point:** `user.status` is a business record; sessions/authentications may have been issued while the user was still `ACTIVE`. If protected requests merely read an existing `SecurityContext`, they do not automatically re-call `UserDetailsService.loadUserByUsername(...)` or check `isAccountNonLocked()` every time. Likewise, a JWT verifier checking only signatures/claims does not automatically query the user database. You need **status checkpoints** on each access path.

### Action Impact Matrix

| Action | Current HTTP Session | Sessions on Other Devices | Issued JWT Access Token | Refresh Token | IdP SSO |
| --- | --- | --- | --- | --- | --- |
| `user.status=LOCKED` | May **still survive** if status is unchecked | May still survive | Still verifies offline if signature/exp valid | May still refresh if AS does not check lock | Does not vanish automatically |
| Default Servlet `POST /logout` | Invalidates/clears per logout chain | Does not delete automatically | Does not revoke automatically | Does not revoke all grants automatically | Does not log out automatically |
| `SessionRegistry.expireNow()` | Only marks session in registry | Effective where matching filter/registry checks, not global default | No | No | No |
| Delete sessions in shared Spring Session store | Blocks deleted session ID on nodes sharing that store | Yes, with right index and consistency | No | No | No |
| Revoke refresh token at AS | No | No | May stay valid until `exp` if offline JWT | Blocks refresh per AS policy | Not necessarily |
| Revoke opaque access token at AS | No | No | N/A unless API introspects | Depends on grant | No |
| Increment account `securityVersion` | Only if verifier checks | Only if verifier checks | Only if token binds version / is checked | Only if AS checks | No |
| RP-initiated/back-channel logout | Depends on RP/IdP integration | Depends on integration | Not automatic | Not automatic | Depends on IdP support |

This table shows **typical defaults**, not absolute guarantees for every deployment. An AS with cascade-revocation policies may revoke access tokens along with grants; an app with a per-request account-status filter may block sessions after lock. **Measure actual behavior** rather than guessing from method names.

## 3. Ordered Diagnostics: Which Credential Is Still Accepted?

Before editing code, use **two separate sessions** and a test Bearer token to reproduce accurately. Record UTC timestamp, internal account ID, hashed session reference, pseudonymized token `jti`/`sub`, request ID, node ID, realm/tenant, and outcome. Never log raw cookies or Access Tokens into logs/tickets.

### Step 1 — Identify the Actual Authentication Type Used

- **`JSESSIONID`/`SESSION` cookie:** is the request authenticated via `HttpSession` and `SecurityContextRepository`, or another mechanism? Spring Session can change the cookie name.
- **`Authorization: Bearer ...`:** does the resource server use `oauth2ResourceServer().jwt()` or `opaqueToken()`? A JWT can also be sent to introspection; inspecting token shape alone does not confirm the mechanism.
- **Remember-me cookie:** after session logout, did `RememberMeAuthenticationFilter` or custom remember-me log the browser right back in?
- **SSO redirect:** was the user logged out of the RP yet immediately re-logged in because the IdP session stayed active?
- **API key/client credentials:** is it a separately provisioned machine identity independent of a human user account's status?
- **A concurrent request already past authorization** before the revocation timestamp: revocation does not roll back in-flight responses by default.

### Step 2 — Observe the Right Trust Points

| Question | Evidence to Gather |
| --- | --- |
| Which filter chain did the endpoint enter? | Matched `SecurityFilterChain`, matcher, `SecurityFilterChain` order |
| Where did the principal come from? | Session repository, JWT decoder, opaque introspector, custom filter |
| Is `account.status` checked on the request? | `AuthorizationManager`/filter/service checks or AS grant validation |
| Was the current session invalidated? | Does `HttpSession` still exist? Does the shared store have the session key? |
| Were other sessions found? | Spring Session principal index, active `SessionRegistry` |
| Is the token unexpired with valid signature? | `exp`, `iss`, `aud`, `kid`, signature validation result |
| Does the Resource Server check revocation? | `jti` denylist, `securityVersion`, account status, introspection `active` |
| Did revocation propagate to AS/IdP? | API response, outbox state, retries, post-action active check |
| Do caches introduce delay? | Redis/local cache TTL, JWT validator cache, introspection cache, replica lag |
| Are network errors failing open? | Circuit-breaker behavior, 5xx/timeouts, policy when revocation store is unavailable |

**Avoid diagnostic fallacies:** you cannot conclude an account was not locked just because a token still passes. The **database may be locked cleanly** while the request never reads that status. Conversely, a 401 does not prove all sessions were deleted; the endpoint may have been blocked by a different authorization rule.

### Step 3 — Test in a Safe Environment

Use test accounts and test credentials, confirm access succeeds before revocation, mark the revocation commit time, and retry **the same old credentials** from every device/client. Never paste real tokens/cookies into issue trackers, browser consoles, shell history, or potentially public logs. Test **post-revocation refresh** too, not just replaying the old access token against the API.

If the SLO target is revocation within 5 seconds, measure from **committed revoke command** to **rejection by all relevant verifiers**. A 60-second cache makes an "immediate revocation" promise empirically false.

## 4. Spring Security Servlet: Where Logout Stops and Why Other Sessions Survive

### 4.1. What Does the Default Logout Chain Handle?

Per Spring Security 6.5 docs, under default logout configuration, `POST /logout` with a valid CSRF token runs through `LogoutFilter` and `LogoutHandler`s:

- `SecurityContextLogoutHandler` invalidates the **current request's HTTP session** and clears `SecurityContextHolder`/repository.
- Configured remember-me services handle cleaning up the request's remember-me cookie.
- `CsrfLogoutHandler` clears the saved CSRF token; `LogoutSuccessEvent` may be published.
- `LogoutSuccessHandler` handles the response, typically redirecting to `/login?logout` by default.

Under default CSRF settings, `GET /logout` may be a confirmation page, **not a completed logout action**; a valid POST is required. Deleting cookies in browser JavaScript leaves the server session alive until revoked. Conversely, invalidating the session on the server makes the old cookie useless for that session even if the client retains it.

~~~text
Browser A -- POST /logout + CSRF -->
    LogoutFilter
      -> SecurityContextLogoutHandler
           HttpSession A.invalidate()
           clear SecurityContext
      -> remember-me / CSRF cleanup
      -> redirect/204

Browser B holds HttpSession B -- NOT deleted by default above -->
    Requests authenticated with session B can still continue.
~~~

If an app writes `@PostMapping("/logout")` returning 200 directly, it may have **bypassed** `LogoutFilter` or skipped `SecurityContextLogoutHandler`. Spring docs advise preferring the logout DSL; custom endpoints must perform complete cleanup with proper routing/CSRF.

### 4.2. Very Common Diagnostic Causes

1. `GET` logout never executed due to CSRF. Check method/status/server logs instead of judging by "UI switched pages".
2. Frontend cleared only Redux/`localStorage` state while the server session or refresh token remained valid.
3. Browser B's `JSESSIONID` cookie is a **different session**, unaffected by logging out A.
4. App uses multiple `SecurityFilterChain`s and the logout endpoint sits in another chain or has a mismatched matcher.
5. **Remember-me** or an SSO redirect silently issued a new session, making users think the old session came back to life.
6. Session registry is in-memory per node; revoking on node A knows nothing about sessions on node B.
7. Principal index uses an unstable username/email or omits tenant isolation; lookups miss or hit the wrong user.
8. Calling `SessionRegistry.expireNow()` without a filter/mechanism checking expired sessions on later requests; mistaking marking for physical deletion.
9. App uses Spring Session yet invalidates only the current request's `HttpSession`, leaving other sessions in the repository untouched.
10. Custom authentication filter rebuilds `SecurityContext` from a token/remember-me independently of the deleted session.
11. Admin flips `account.locked` in the DB, yet sessions holding saved `Authentication` never re-check account state.
12. Account-status caches, user-role caches, or session indexes were not invalidated.

### 4.3. `SessionRegistry` Is Not a Distributed Session Store by Default

`SessionRegistry` tracks sessions registered inside a Spring Security app. `SessionInformation.expireNow()` marks it expired; concurrent-session filters and matching session management can reject that session on its next request. **Do not treat it as an immediate kill switch across all nodes** when `SessionRegistry` is an in-memory per-JVM `SessionRegistryImpl`.

~~~java
// Illustrative snippet; requires matching SessionRegistry/session config.
// Not a standalone Java class.
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
~~~

In a project, `SessionInformation` is in `org.springframework.security.core.session.SessionInformation` and `SessionRegistry` is in `org.springframework.security.core.session.SessionRegistry`. The principal needs stable `equals()/hashCode()` when using `SessionRegistryImpl`, or the registry may fail to match sessions. After `expireNow()`, test a real request with the old session and filter rather than merely asserting the flag flipped.

With a **shared session store** like Spring Session Redis/JDBC, you can delete server-side sessions by ID through an indexed repository. Verify all nodes use **the same namespace/config/cluster** and indexes store a stable local principal. Spring Session does not automatically understand every custom authentication flow; indexes can stay unpopulated under custom security flows.

## 5. Spring Session: Deleting All Sessions Belonging to a User Properly

### 5.1. Principles

Spring Session provides `FindByIndexNameSessionRepository<S extends Session>` and `findByPrincipalName(principalName)` to list sessions indexed under `PRINCIPAL_NAME_INDEX_NAME`. `deleteById(sessionId)` deletes a session by ID in that repository. These APIs genuinely exist in Spring Session 3.5.x. **They apply only to sessions in that indexed store**; they cannot see Bearer JWTs, refresh tokens, IdP sessions, or sessions in other stores.

**Indexes can be missing:** in customized systems, verify `PRINCIPAL_NAME_INDEX_NAME` is populated properly. Some implementations use a resolver reading the Spring Security context to build the index. Depending on version/driver, finding sessions by principal can have consistency/indexing caveats; verify with integration tests and monitoring.

### 5.2. Java Code for a Spring Project

File `src/main/java/example/SessionRevocationService.java` (requires Spring Session dependency and injecting an appropriate repository elsewhere; class models the session operation only):

~~~java
package example;

import java.util.Map;
import java.util.Objects;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public final class SessionRevocationService {

    private SessionRevocationService() { }

    public static <S extends Session> int revokeIndexedSessions(
            FindByIndexNameSessionRepository<S> repository,
            String principalName) {

        Objects.requireNonNull(repository, "repository");
        Objects.requireNonNull(principalName, "principalName");
        if (principalName.isBlank()) {
            throw new IllegalArgumentException("blank principal");
        }

        Map<String, S> found =
            repository.findByPrincipalName(principalName);

        for (String sessionId : found.keySet()) {
            repository.deleteById(sessionId);
        }
        return found.size();
    }
}
~~~

This snippet is valid Java generics, yet only a **utility function** over a configured repository. It **does not guarantee atomic global revocation**, because a new login/session can be created between enumeration and deletion. In suspected takeover incidents, combine **account security version / account state checks** at session creation/acceptance points with appropriate database transactions/outbox/locking.

**Architectural warning:** principal name should be a **stable, tenant-scoped local user ID**. If `Principal.getName()` is just an email or mutable username, session indexes can drift from `userId`. Never pass a browser-supplied username to delete someone else's sessions; admin revocation commands require authorization/approval and auditing.

### 5.3. Verifying Outcomes Instead of Just Return Values

~~~text
Given:
  - User u-123 has session S1 (browser A) and S2 (browser B).
  - Spring Session repository index finds S1 and S2 cleanly.
When:
  - Admin locks u-123 and runs revokeIndexedSessions(...).
Then:
  - findById(S1) and findById(S2) return no valid session.
  - GET protected route with old cookies on browser A/B gets 401 or login redirect.
  - No silent remember-me/SSO re-login occurs in this test.
  - Another user u-999 can still log in.
~~~

If the session count returned is 0 while browser B is authenticated, check **principal index**, repository instance, session namespace, serializer, Redis/JDBC data, deployment region, session TTL, and custom authentication. Never conclude "there are no active sessions" from an empty map alone.

### 5.4. Multiple Regions and Caches

- A Spring Session repository gives consistency for shared sessions, yet apps can have separate regions/stores or L1 caches.
- New session IDs created **after** enumerate/delete are unaffected if the account is still allowed to log in. Block at the **session-issuance point** and check account state.
- Offline devices hold old cookies; once back online the server must reject them — you do not need a way to wipe cookies from that device.
- App DB locks and session deletions do not automatically share a distributed transaction; use clear policies for partial failures, idempotent retries, and post-verification.

## 6. Locking Account Still Fails to Block JWT: Where Is the Gap?

### 6.1. A JWT Is an Already-Issued Credential

A standard JWT access token carries `iss`, `sub`, `aud`, `exp`, `iat`, optionally `jti`, and scopes/roles. The Resource Server verifies the signature and claim validators. If the verifier **does not check account status/revocation**:

~~~text
t0: User ACTIVE, AS issues JWT T (exp = t0 + 15 minutes)
t1: Admin sets user LOCKED in app DB
t2: Client calls API with JWT T
t3: Resource Server verifies only signature/iss/aud/exp => token still valid
t4: JWT T expires => Resource Server starts rejecting due to exp
~~~

Tokens can still be rejected earlier with extra controls, yet **changing passwords, locking accounts, or deleting HTTP sessions does not alter the signature** of JWT T. `JwtDecoder` also does not automatically query `UserDetailsService` by `sub` on every call.

### 6.2. Checking the Right Places

- Does the Resource Server actually have `.oauth2ResourceServer(oauth -> oauth.jwt(...))` on this API's chain?
- Is the decoder properly validating issuer, audience, expiry/`nbf`, keys, and algorithm allowlist?
- After the decoder, does the app enforce an `account.active`/`securityVersion`/`tokenFamily` policy? Does the check run **before authorization** on every sensitive endpoint rather than just one controller?
- Is token `sub` a local ID or an IdP subject? Is there trusted identity mapping and tenant binding before checking local accounts?
- What is the account-state cache TTL? Did node B refresh its cache after the lock?
- Are there long-lived endpoints or WebSocket/SSE streams that **skip revocation checks** mid-stream?
- Do some APIs use opaque introspection while others use offline JWT? Mixed policies create "half-revocation".

### 6.3. Three Approaches to Controlling Access JWTs

| Approach | How It Works | Tradeoff |
| --- | --- | --- |
| **Short TTL** | Token expires quickly; refresh tokens blocked on lock | Leaves a residual window until `exp`; not immediate revocation |
| **`jti`/token-family denylist** | Every request checks token identifier against a shared revocation store | Lookup latency, storage/TTL, consistency, failure policy |
| **Security version / account-state check** | Token binds `userId` + `version` at issuance; every verifier compares current version/state | Needs online/shared state; external IdP tokens may lack that claim |

Another strategy is **opaque tokens + introspection**: the Resource Server asks the AS for `active`, trading latency/availability; introspection caches still leave a window if TTL is large. You need not pick only one mechanism; layer defenses per risk and latency budgets.

**If using a denylist:** never log raw tokens. `jti` must be unique and scoped to issuer/audience; revocation record TTL must be no shorter than the remaining lifetime the token could be accepted. If using account versions, ensure **all** Resource Servers and batch consumers enforce them, not just the gateway. Prevent stale caches and silent fail-open on high-risk endpoints.

### 6.4. Post-Lock Account Status and Live Sessions

A `UserDetails` loaded at login and saved in a session reflects old state; later DB updates **do not automatically mutate the object inside `SecurityContext`**. To make locks take effect immediately, use one of:

- Log out/delete known sessions via a shared session repository, **paired with blocking new session creation**.
- On every sensitive request/endpoint, verify account status and security version against a trusted service/store.
- Store a session security version at session creation, increment it on lock/unlock/recovery, and compare before granting access.
- For WebSockets/long-lived connections, enforce policies to close connections or re-validate periodically per risk budget.

**Do not rely solely on `UserDetails.isAccountNonLocked()` at initial authentication** if locks must apply to already-issued sessions. That initial check helps at login, yet existing sessions do not re-authenticate on every request.

## 7. Refresh Tokens, OAuth Revocation, Opaque Tokens, and IdP Sessions

### 7.1. Refresh Tokens Live at the Authorization Server

Resource Servers normally **do not** manage or issue refresh tokens. Under OAuth2/OIDC login, refresh tokens may live at the Authorization Server, OAuth client, or a separate token store. A backend that deletes only its local session without telling the AS to revoke the grant lets other devices keep calling the token endpoint for fresh access tokens.

Check:

1. Where are the client/grant ID and the user's refresh-token family managed?
2. Does the AS check disabled/locked account status before refreshing? Have you tested with an old refresh token?
3. Does refresh-token rotation detect **reuse** and revoke the family per policy?
4. Race: a refresh starting **right before** lock/revocation can issue a new token **after** commit if the AS does not block concurrent issuance.
5. Does a successful revoke response mean it took effect across all verifiers/token stores? Are there retries/queues/replica lags?

### 7.2. RFC 7009 and the "Revoke Everything" Myth

RFC 7009 defines a **token revocation endpoint**; the RFC encourages Authorization Servers to revoke related grants. Yet **revoking a refresh token does not guarantee already-issued JWT access tokens are rejected immediately** if Resource Servers verify offline without denylists/status checks.

On the client, deleting `OAuth2AuthorizedClient` removes only **client-stored** token data; it stops that client from calling APIs with the discarded token, yet it is not an AS token-revocation call. Conversely, AS revocation of refresh/access grants does not automatically invalidate all live HTTP sessions inside the app.

Never paste raw tokens into incident logs; call the revocation endpoint only over HTTPS with proper client authentication. Retries need idempotency. HTTP 200 from the revocation endpoint **is insufficient** to prove offline API access JWTs are blocked.

### 7.3. Opaque Token Introspection

With opaque tokens, the Resource Server calls `OpaqueTokenIntrospector`; the AS returns `active=true` or `false`. On account lock, the AS must update grant/token state, and then the Resource Server must **re-query** or use a cache with an appropriate TTL. If `active=true` is cached for 10 minutes, revocation takes guaranteed effect only after that cache expires or is invalidated.

Symptom:

~~~text
t0: Resource Server introspects opaque token => active=true
t1: Response cached TTL=300s
t2: Authorization Server revokes => active=false
t3: Resource Server still accepts cached active=true
t4: TTL expires / cache invalidated, re-introspects => active=false
~~~

Verify whether the system runs a real `OpaqueTokenIntrospector` or if tests/staging mocked it to always return a principal. **Never treat Spring Security Test's `opaqueToken()` or `mockOpaqueToken()` as proof that HTTP introspection executed.**

### 7.4. Identity Provider Sessions and Silent SSO Login

With OIDC `oauth2Login()`, the app has a **Relying Party session** and the IdP has an **OP/SSO session**. Logging out the RP does not automatically log out the IdP. A user clicks logout, clicks "Login with Provider", and gets signed right back in: that may be a **new valid RP session minted from an active IdP SSO session**, not an undeleted old cookie.

When coordinated logout is needed, evaluate RP-initiated logout, back-channel logout, or front-channel logout per IdP capabilities, assurance policies, and IdP disable events. Do not conflate RP's `logoutSuccessHandler` with OAuth grant revocation; keep those operations distinct. When external IdPs do not support it or fail, record `PENDING_EXTERNAL_LOGOUT/REVOKE` with bounded handling.

### 7.5. Remember-Me: An Overlooked Session-Recreation Channel

If the app uses persistent remember-me tokens, the browser can mint a fresh `Authentication` when the main session/cookie expires. Spring's default logout includes remember-me cleanup handlers when configured, yet **logging out one device does not necessarily delete persistent tokens across all devices**. During compromise incidents, inspect the persistent-token/series store or design per-user remembered-device grants so all can be revoked. Never declare "all sessions are dead" while browsers can silently re-login via remember-me or IdP SSO.

## 8. Thorough Remediation Workflow: Transactions, Propagation, and Verifiable Guarantees

### 8.1. Multi-Credential Revocation Workflow

~~~text
Authorized operator / verified account owner requests REVOKE_ALL
    |
    v
Check authorization, step-up, incident ID, scope
    |
    v
DB transaction:
   lock account row; mark LOCKED (if policy)
   increment securityVersion once per incident
   mark known session/refresh grants revoked
   write incident + outbox events
   commit
    |
    v
Asynchronous workers (idempotent):
   delete indexed Spring Sessions
   invalidate other local sessions/remember-me tokens
   call Authorization Server token-family/grant revoke
   call IdP logout/revoke APIs if supported
   broadcast cache invalidation / denylist update
    |
    v
All authenticators/verifiers:
   reject old securityVersion, old session/grant, revoked jti
   reject new authentication if account LOCKED
    |
    v
Re-test from every device/API/node/region
    |
    +-- all effective -> CONFIRMED
    +-- some pending -> PARTIAL / PENDING_EXTERNAL + alert
~~~

**A DB transaction cannot atomically span multiple remote IdPs/ASs**, so you need outboxes, idempotent retries, dead-letter handling, partial states, deadlines, and auditing. Never report "everything revoked" while an IdP token still lacks confirmation. Locking an account must block **issuing new sessions/tokens** under the exact same status-check mechanism; otherwise a race can mint new sessions right after enumerate/delete.

### 8.2. Dangerous Race: Lock Racing With Concurrent Refresh

~~~text
Request A: refresh token -> reads account ACTIVE
Admin B:   lock account -> commits LOCKED + version=13
Request A: signs new access token (version=12 or unversioned)
Resource Server: token has valid signature/exp -> ACCEPT!
~~~

Fix: enforce account status/version near or **inside the token-issuance transaction** at the AS using locks/CAS/version policies; Resource Servers check `version`/revocation state against a trusted source. If external IdP tokens cannot carry a local version, use a local denylist/check or bounded token lifetime. Test concurrency with barriers rather than sequential unit tests alone.

### 8.3. Cache and Multi-Region Warnings

- A node caching account status for 5 minutes still admits old sessions even after the DB marks `LOCKED`.
- Redis session stores in region A while server B points to another Redis namespace leave sessions undeleted.
- Offline JWTs on Resource Server C lacking revocation checks still accept tokens; a gateway check alone does not close bypass paths.
- Invalidation event buses can drop or reorder events; fresh sessions issued after recovery must not be wiped by stale revocation events.
- Persistent connections (WebSocket/SSE) do not close automatically on DB changes; define re-evaluation/close policies.
- On high-risk endpoints, never silently **fail open** during a revocation-store outage when immediate enforcement is required.

### 8.4. Designing Post-Fix Evidence

Instead of logging "called revoke", record per incident: action ID, account ref, commit timestamp, affected credential types, status per store/AS/IdP, sessions found/deleted, retry count, verified nodes/regions, retried requests with old credentials, and time-to-rejection. Protect records from PII/secret leakage and restrict access by role.

**Never delete audit/evidence logs** to "clean up" after an incident; keep separate retention, integrity, and access controls. Never place raw tokens, cookies, OTPs, or session IDs into public telemetry.

## 9. Standalone Java 17: Simulating Why Account Lock Does Not Kill Offline JWTs

The following code runs on **plain Java 17** without Spring. It models one user holding a session, refresh grant, and issued JWT. On account lock, the session and refresh grant are deleted and version increments; **an offline expiry-only JWT check** still admits the JWT until expiration, whereas **an added account version/status check** rejects it. This illustrates the trust boundary; it has **no** real JWS signatures/decoders, networks, caches, or databases, so **never use it as a production security implementation**.

Create `RevocationDiagnosisDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class RevocationDiagnosisDemo {

    record Token(String userId, long issuedVersion,
                 long expiresAtEpochSeconds) {
    }

    private static final long NOW = 1_700_000_000L;

    private final Map<String, Long> versions = new HashMap<>();
    private final Map<String, Boolean> locked = new HashMap<>();
    private final Map<String, Token> sessions = new HashMap<>();
    private final Map<String, Token> refreshGrants = new HashMap<>();

    private long version(String userId) {
        return versions.getOrDefault(userId, 0L);
    }

    private boolean isLocked(String userId) {
        return locked.getOrDefault(userId, false);
    }

    synchronized Token issueAccess(String userId) {
        Objects.requireNonNull(userId);
        if (isLocked(userId)) {
            throw new IllegalStateException("locked");
        }
        return new Token(userId, version(userId), NOW + 900);
    }

    synchronized void issueSession(String userId, String id) {
        Objects.requireNonNull(id);
        Token issued = issueAccess(userId);
        sessions.put(id, issued);
    }

    synchronized void issueRefresh(String userId, String id) {
        Objects.requireNonNull(id);
        Token issued = issueAccess(userId);
        refreshGrants.put(id, issued);
    }

    synchronized boolean sessionValid(String id) {
        Token token = sessions.get(id);
        return token != null
            && !isLocked(token.userId())
            && token.issuedVersion() == version(token.userId());
    }

    synchronized boolean refreshValid(String id) {
        Token token = refreshGrants.get(id);
        return token != null
            && !isLocked(token.userId())
            && token.issuedVersion() == version(token.userId());
    }

    // Simulates a decoder checking expiry only; DOES NOT verify signatures.
    static boolean offlineExpiryOnly(Token token) {
        return token.expiresAtEpochSeconds() > NOW;
    }

    synchronized boolean withAccountVersion(Token token) {
        return offlineExpiryOnly(token)
            && !isLocked(token.userId())
            && token.issuedVersion() == version(token.userId());
    }

    synchronized void lockAndRevoke(String userId) {
        Objects.requireNonNull(userId);
        locked.put(userId, true);
        versions.put(userId, version(userId) + 1);
        sessions.entrySet().removeIf(
            entry -> entry.getValue().userId().equals(userId));
        refreshGrants.entrySet().removeIf(
            entry -> entry.getValue().userId().equals(userId));
    }

    synchronized void unlockAfterVerifiedRecovery(String userId) {
        Objects.requireNonNull(userId);
        locked.put(userId, false);
        // Do NOT reset version to 0; old tokens stay blocked.
    }

    public static void main(String[] args) {
        RevocationDiagnosisDemo store = new RevocationDiagnosisDemo();
        store.issueSession("alice", "session-old");
        store.issueRefresh("alice", "refresh-old");
        Token jwtOld = store.issueAccess("alice");

        System.out.println("before.session="
            + store.sessionValid("session-old"));
        System.out.println("before.refresh="
            + store.refreshValid("refresh-old"));
        System.out.println("before.offlineJwt="
            + offlineExpiryOnly(jwtOld));
        System.out.println("before.checkedJwt="
            + store.withAccountVersion(jwtOld));

        store.lockAndRevoke("alice");

        System.out.println("after.session="
            + store.sessionValid("session-old"));
        System.out.println("after.refresh="
            + store.refreshValid("refresh-old"));
        System.out.println("after.offlineJwt="
            + offlineExpiryOnly(jwtOld));
        System.out.println("after.checkedJwt="
            + store.withAccountVersion(jwtOld));

        store.unlockAfterVerifiedRecovery("alice");
        System.out.println("recovered.oldCheckedJwt="
            + store.withAccountVersion(jwtOld));
        store.issueSession("alice", "session-new");
        System.out.println("recovered.newSession="
            + store.sessionValid("session-new"));
    }
}
~~~

Run:

~~~bash
javac RevocationDiagnosisDemo.java
java RevocationDiagnosisDemo
~~~

**Exact stdout** per the model (fixed clock, no randomness):

~~~text
before.session=true
before.refresh=true
before.offlineJwt=true
before.checkedJwt=true
after.session=false
after.refresh=false
after.offlineJwt=true
after.checkedJwt=false
recovered.oldCheckedJwt=false
recovered.newSession=true
~~~

**Meaning:** `after.offlineJwt=true` is the diagnostic point: an issued access token can still pass a verifier **that does not re-check account state**. `after.checkedJwt=false` shows that adding a state check rejects the old token, not that Spring does this automatically. Unlocking after verification **does not resurrect old JWTs** because the version incremented. Allowing new session issuance in the demo is purely illustrative: production requires re-authentication/step-up at sufficient assurance, with no unchecked `unlockAfterVerifiedRecovery` endpoint.

**Limitations:** `NOW` is fixed for deterministic stdout, RSA/JWT signatures are not checked, and `Map`/`synchronized` operate within a single JVM. Never log real session/token `id`s or use this in-memory map instead of Redis/DB/Authorization Server in production.

### 9.1. JUnit Jupiter: Verifying Key Invariants

If JUnit 5 is present, place `RevocationDiagnosisDemoTest.java` in the same package as the demo (if the demo omits a `package` declaration, omit it in the test file too):

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RevocationDiagnosisDemoTest {

    @Test
    void revokedSessionAndRefreshAreRejected() {
        var store = new RevocationDiagnosisDemo();
        store.issueSession("alice", "s1");
        store.issueRefresh("alice", "r1");

        assertTrue(store.sessionValid("s1"));
        assertTrue(store.refreshValid("r1"));
        store.lockAndRevoke("alice");
        assertFalse(store.sessionValid("s1"));
        assertFalse(store.refreshValid("r1"));
    }

    @Test
    void offlineTokenMaySurviveWhileVersionCheckBlocksIt() {
        var store = new RevocationDiagnosisDemo();
        var issued = store.issueAccess("alice");
        store.lockAndRevoke("alice");

        assertTrue(RevocationDiagnosisDemo.offlineExpiryOnly(issued));
        assertFalse(store.withAccountVersion(issued));
    }

    @Test
    void unlockDoesNotResurrectOldAccessToken() {
        var store = new RevocationDiagnosisDemo();
        var issued = store.issueAccess("alice");
        store.lockAndRevoke("alice");
        store.unlockAfterVerifiedRecovery("alice");

        assertFalse(store.withAccountVersion(issued));
    }

    @Test
    void accountLockDoesNotRevokeOtherUserSessions() {
        var store = new RevocationDiagnosisDemo();
        store.issueSession("alice", "s-a");
        store.issueSession("bob", "s-b");

        store.lockAndRevoke("alice");
        assertFalse(store.sessionValid("s-a"));
        assertTrue(store.sessionValid("s-b"));
    }

    @Test
    void lockedAccountCannotIssueNewAccessToken() {
        var store = new RevocationDiagnosisDemo();
        store.lockAndRevoke("alice");
        assertThrows(IllegalStateException.class,
            () -> store.issueAccess("alice"));
    }
}
~~~

These tests verify only **the domain simulation**. You still need integration tests against Spring Session stores, Resource Server JWT decoders, AS refresh endpoints, opaque introspection, and real clients replaying old credentials. Never write a test using `jwt()`/`mockJwt()` and claim you tested denylists, signatures, or refresh revocation: those helpers inject mock `Authentication` and bypass the decoder path.

## 10. HTTP/Integration Test Matrix to Find Real Bugs

### Two Sessions and Tokens Must Be Completely Independent

~~~text
PRECONDITION:
  User alice ACTIVE.
  Device A login -> cookie S1.
  Device B login -> cookie S2.
  OAuth client obtains access token T1 + refresh token R1.

ACTION:
  Admin locks alice (with authorization and audit).
  Revocation policy executes.

ASSERT:
  GET /private with cookie S1 -> unauthenticated/denied.
  GET /private with cookie S2 -> unauthenticated/denied.
  GET /private with Bearer T1 -> 401/403 as designed by revocation policy.
  POST token refresh using R1 -> token endpoint rejects.
  A login using old credential while LOCKED -> rejected.
  Account bob's valid session remains accepted.
  Repeat on every node/region and after caches warm.
~~~

When a resource server uses offline JWTs with finite TTL and **no immediate revocation guarantee**, tests must reflect the exact contract: T1 may work until `exp`, while high-risk endpoints are guarded or the residual risk is formally signed off. Never assert 401 as proof if the actual policy permits a "15-minute residual window".

### Matrix: Symptom → Cause → Verification Test

| Symptom | High Likelihood | Verification Test |
| --- | --- | --- |
| Logout UI redirects to login yet old cookie still calls API | Request missed logout filter, controller redirected itself, or API uses another Bearer | Trace matcher/`LogoutFilter`, test POST with CSRF, inspect auth source |
| Browser A logs out, browser B still gets in | Local logout invalidated only S1 | Compare session ID refs and shared store |
| `SessionRegistry.expireNow()` yet session still works | Expiration marking not enforced by filter, wrong node/principal in registry | Check registry, filter chain, session requests after expiry |
| `findByPrincipalName` returns empty map | Missing index or wrong local ID/tenant/store namespace | Check Spring Session index and repository config |
| User `LOCKED` yet old session requests still return OK | Account status/security version not re-evaluated | Enable guard on protected paths, delete indexed sessions |
| JWT still works after password change | Offline JWT signature/time still valid | Check decoder vs denylist/version and TTL |
| JWT blocked at gateway yet internal API still accepts it | Service bypassed gateway or validator configs diverged | Test direct service path/mTLS/authz policies |
| Old refresh token still mints new tokens | AS did not revoke family or omits account-lock check | Test token endpoint, grant store/issuer |
| Opaque token stays `active` after revocation | AS did not update `active` or introspection cache still holds `true` | Re-introspect from clean client, measure TTL |
| SSO auto-logs back in after logout | OP session still alive, minting a new RP session | Inspect new session ID and OIDC authorization flow |
| Remember-me recreates login | Persistent remember-me grant not revoked | Delete/mark series/device, test old cookie |
| Node A rejects, node B allows | Session/revocation/cache stores out of sync | Test load balancer pinned per node, namespace, consistency |
| 401 at first then 200 seconds later | Refresh/re-login race or cached principal | Correlate token issue time, new session ID, and events |
| Revoke API returns 200 yet AS has not finished | Pending async outbox, partial failure | Track per-provider status and retries/audits |
| WebSocket keeps streaming after lock | Long-lived connection does not re-check auth | Test close/revalidate on account lock |
| Still 200 under `MockMvc.with(jwt())` | Test injected mock `Authentication`, skipping decoder | Send raw Bearer JWT / real client in tests |

### Quality Testing Checklist

- Do not assert only DB flag `LOCKED`; assert HTTP with **old credentials** after commit.
- Test across different nodes/regions/gateways along legitimate traffic paths.
- Assert unrelated accounts and new post-recovery sessions follow policy without accidental deletion.
- Test refresh/revoke races, login/revoke races, and delayed outbox deliveries.
- Measure `revocation_lag_p95/p99` per credential type and authentication mechanism.
- Check Bearer `WWW-Authenticate`/HTTP status on invalid tokens without exposing internal reasons in responses.
- Every test credential uses dedicated test accounts and test-generated tokens; never copy raw tokens into CI logs.
- With Spring Security Test, separate authorization tests using mock principals from **real decoder/introspection tests**.
- Test behavior when Redis/DB/AS are down: sensitive endpoints must fail closed per threat model.
- If policy allows residual JWT lifetimes, verify the maximum bound and notify operations rather than calling it immediate revocation.

## 11. Quick Diagnostic Runbook for On-Call

### Receiving the Incident

1. **Classify:** Was the user `LOCKED` or logged out? Logout on one or all devices? JWT, opaque, refresh token, or cookie session? Never say "token" vaguely.
2. **Collect safely:** account ID, incident ID, request ID, UTC time, issuer/audience, pseudonymized fingerprint/`jti` reference; **never** collect raw secrets.
3. **Reproduce:** use a test account and two independent clients; verify access works pre-revoke; capture post-revoke HTTP statuses.
4. **Follow the filter chain:** which chain does the endpoint match, which auth source, which principal/tenant mapping, and is there an account-state guard?
5. **Inspect state stores:** shared Spring Session/registry/remember-me, refresh family and AS, JWT denylist/version, opaque introspection, SSO sessions, and caches.
6. **Find propagation gaps:** pending outboxes, queue retries, other nodes, mismatched Redis namespaces, failing AS/IdP APIs, cache TTLs, or refresh races.
7. **Contain immediately per policy:** block high-risk endpoints/refresh issuance, revoke families/sessions, bump version, restrict account, audit. Never wipe all data blindly to "fix".
8. **Verify post-remediation:** old credentials on every verifier must be rejected or obey residual-lifetime SLAs; record any pending items.
9. **Recover safely:** verify user identity/step-up, rotate compromised credentials, re-enroll factors if needed; never resurrect old sessions/tokens after unlock.
10. **Postmortem:** update runbooks, add multi-node CI tests, monitor lag, and require explicit encoding of partial states.

### Metrics Worth Tracking

- `time_to_detect`, `time_to_contain`, `revocation_lag` split by session/JWT/refresh/opaque.
- Active sessions found vs deleted; session index misses.
- Old JWTs still passing after lock within permitted windows.
- Refresh reuse attempts and AS rejections/issuances after revocation.
- `introspection_cache_ttl`, cache-invalidation misses, fail-open counts.
- Outbox backlog, pending external revocations awaiting confirmation, retry counts.
- Verifiers/nodes/regions lacking revocation guards.
- Cases of "re-login via SSO/remember-me" misclassified as "undeleted session".

Never use emails or raw tokens as high-cardinality metric labels; store forensic context in access-controlled, retention-bounded logs.

## 12. Common Remediation Mistakes

1. **Setting only `enabled=false`/`locked=true` in the DB and assuming all sessions die:** sessions/JWTs do not auto-recheck.
2. **Clearing only `SecurityContextHolder`:** clears the current thread/request context without deleting sessions on other devices.
3. **Calling `HttpSession.invalidate()` once:** affects only the current session, not global logout.
4. **Using local `SessionRegistryImpl`** in multi-node apps and claiming "logged out everywhere".
5. **Assuming `SessionInformation.expireNow()` deletes from repositories immediately:** it only marks expiration and needs checks/cleanup.
6. **Trusting an empty `findByPrincipalName` map means zero sessions:** indexes may be missing or namespaces mismatched.
7. **Deleting client cookies while keeping remember-me/refresh tokens:** allows automatic re-authentication.
8. **Locking the user while the AS still mints new refresh tokens** because account status/grants went unchecked.
9. **Revoking refresh tokens and claiming access JWTs died immediately** while Resource Servers verify offline.
10. **Skipping `aud`/`iss` in validators** and locking the wrong tenant/issuer, creating new security bugs.
11. **Denylist TTL shorter than remaining JWT lifetime:** revoked tokens come back to life once the denylist record expires.
12. **Checking `securityVersion` only at the gateway:** internal services can be reached around the gateway.
13. **Caching account status too long or failing open** when the revocation store is unreachable.
14. **Calling IdP logout and assuming app sessions vanished:** IdP SSO and RP sessions are independent.
15. **Seeing the browser auto-relogin and blaming the logout handler:** a fresh session may be created from remember-me/SSO.
16. **Omitting concurrent revoke/refresh tests:** new tokens keep being issued inside the race window.
17. **Pasting real tokens/cookies into tickets** to debug: exposes live credentials.
18. **Asserting only `status=401` in MockMvc with mock principals:** does not test real token revocation.
19. **Conflating revoke-command success with verified revocation enforcement:** remote providers/stores may still be pending.
20. **Letting locked users unlock themselves with an old session:** bypasses assurance/recovery policy.

## 13. Diagnostic Conclusion Checklist

- [ ] Identified the `Authentication` source of surviving requests: session, remember-me, JWT, opaque, refresh, IdP, or API key.
- [ ] Confirmed the logout handler/HTTP method/CSRF/filter chain actually ran on the endpoint.
- [ ] Where global logout is required, located/deleted sessions in a shared repository using a tenant-scoped principal index.
- [ ] All critical protected requests verify account status/revocation version per policy, not only at initial login.
- [ ] AS blocks old refresh-token families after lock and prevents refresh/revoke races.
- [ ] Offline JWTs have an approved short TTL or denylist/security-version enforcement across **every** Resource Server.
- [ ] Opaque introspection reflects revocation with cache TTLs aligned to SLA.
- [ ] Remember-me, OAuth authorized clients, and IdP SSO are handled per scope and provider capability.
- [ ] Outbox/retry/idempotency logic never deletes fresh post-recovery sessions by mistake.
- [ ] Tested old credentials across two clients and multiple nodes, recording actual revocation lag.
- [ ] No raw credentials logged, no account existence/internal reasons leaked, while preserving audit trails.
- [ ] Recovery runbooks and false-positive/dispute workflows exist for legitimate users.

**Remember:** an account lock or logout command is only an **intent to change access**. It becomes **effective revocation** only when **every live authentication path** checks state or deletes state in the right store, and post-remediation tests prove old credentials can no longer open resources outside the approved risk window.

## 14. Official Documentation

- Spring Security 6.5 — Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — `SecurityContextLogoutHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
- Spring Session 3.5 — `FindByIndexNameSessionRepository`: https://docs.spring.io/spring-session/reference/3.5/api/java/org/springframework/session/FindByIndexNameSessionRepository.html
- Spring Session — Using `SessionRepository` and Principal Index: https://docs.spring.io/spring-session/reference/api.html
- Spring Security — JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security — Opaque Token Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- RFC 7009 — OAuth2 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009.html
- RFC 7662 — OAuth2 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662.html
- RFC 6750 — OAuth2 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
