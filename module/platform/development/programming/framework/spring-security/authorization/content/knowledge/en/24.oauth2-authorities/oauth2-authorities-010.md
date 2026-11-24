# Permission Changes While a Session or Access Token Is Still Valid in Spring Security

## 1. Opening scenario: an admin revokes access, yet the user can still access data

Alice signs in to the reporting admin app at 09:00 and receives the `reports:read` permission. The system stores `Authentication` in an HTTP session, or the Authorization Server issues an access token with the `reports:read` scope.

At 09:10, an administrator revokes Alice's read permission. However, the HTTP session is still alive and the JWT access token does not expire until 10:00.

If the endpoint checks only the authority snapshotted at sign-in or token issuance:

```java
@PreAuthorize("hasAuthority('SCOPE_reports:read')")
public String readReport(long reportId) {
    return reportRepository.read(reportId);
}
```

then **the old JWT still carries `SCOPE_reports:read`**. Similarly, **the old session may keep holding an `Authentication` with the pre-revocation authorities**. Updating a row in the users/roles table does not automatically mutate every active session and every already-issued access token.

This is the problem of **when a permission change takes effect** (*permission change propagation*), not merely "did login succeed?"

This Knowledge lesson belongs to the **Authorities from OAuth2** group, topic **Permission changes while a session or access token is still valid**, module *Spring Security – authorization*.

By the end of this lesson, you will:

1. Distinguish an **active session**, an **unexpired JWT access token**, an **opaque access token**, a **refresh token**, and **database permissions**.
2. Explain why changing roles/scopes in the Authorization Server or database **does not automatically rewrite** permissions baked into sessions or JWTs.
3. Choose among **waiting for expiration**, **session invalidation**, **token revocation**, **introspection**, **denylist**, **policy version/epoch**, and **live authorization**.
4. Define **permission revocation latency** targets, identifying where immediate synchronization is required and where bounded delay is acceptable.
5. Configure Spring Security 6.5 / Spring Boot 3.5.x for JWT Resource Server, method security, and **checking the current permission version**.
6. Understand `SecurityContextRepository`, `HttpSession`, `SecurityContextHolder`, `SessionRegistry`, and Spring Session when refreshing or revoking sessions.
7. Distinguish HTTP `401` (unauthenticated token/session) from `403` (insufficient permissions) and `404` (concealing resource existence).
8. Run a **standard-library Java 17** example with no Spring dependency and deterministic stdout simulating revoke/regrant.
9. Understand a Spring Boot **Servlet Resource Server** example featuring JWT `authz_ver`, a permission directory, a tenant-scoped service, and `MockMvc` tests.
10. Re-test the exact **same unexpired access token** after revocation and after regrant.
11. Design caching, multi-node propagation, refresh, long-running jobs, WebSockets/SSE, and DB updates to avoid stale authorization.
12. Avoid dangerous "fixes": clearing a cookie on one machine, rotating JWT keys en masse, defaulting to allow when PDP fails, trusting client-supplied claims, or only hiding a button on the frontend.

**Core idea:** An identity/session/token proves **who is calling and what grant snapshot existed at issuance**. Whether permission still holds **at the moment of the current operation** is a separate question. For revocable permissions or sensitive operations, enforce a **current permission state** check or a governed policy version.

---

## 2. First distinguish five "still-valid things"

| Component | When created? | Where do permissions live? | After admin changes a role? |
| --- | --- | --- | --- |
| HTTP session | At login when session is created | `SecurityContext` holding `Authentication` | May retain old authorities until refreshed or invalidated |
| JWT access token | When Authorization Server issues token | Signed scope/roles/permissions claims | Old JWT contents **do not change automatically** |
| Opaque access token | When Authorization Server issues token | Status/scopes metadata at AS or introspection service | Can reflect `active=false`/new info **if** introspection state updates and is not cached stale |
| Refresh token | When AS issues offline/long-lived grant | Token used to obtain new access tokens | Revoking refresh **does not guarantee** already-issued access tokens are rejected immediately |
| Policy/ACL/membership store | When admin updates permissions | Database, IAM, PDP, or directory | Can be the **latest source of truth**, if components actually query it |

**Distinguish authentication from authorization:**

- **Authentication:** Who is Alice, and is her credential/token valid?
- **Authorization:** Is Alice allowed to read report #101 in tenant T1 **right now**?
- **Token validity:** A JWT with valid signature/`iss`/`aud`/`exp` does not guarantee its embedded grants remain accepted under current policy.
- **Data policy:** Scope `reports:read` does not grant access to another tenant's report or a document whose owner changed.

Two-point timeline example:

```text
09:00  Authorization Server mints JWT:
       sub=alice
       scope="reports:read"
       authz_ver=7
       exp=10:00

09:10  Admin revokes Alice's READ permission:
       policy store grants={}
       authz_ver=8

09:11  Alice calls GET /api/reports/101 with old JWT:
       JWT signature valid
       exp not reached
       scope is still "reports:read"
       but authz_ver=7 != current 8
```

If Resource Server checks only `JwtGrantedAuthoritiesConverter` -> `SCOPE_reports:read`, the request slips past the scope check. Adding a **version check** or **live grant lookup** rejects it.

**Do not confuse:** `authz_ver` is simply a **custom claim designed for this example**, not a mandatory OAuth2/JWT standard claim. Both the Authorization Server and Resource Server must agree on this contract.

---

## 3. HTTP session: updating user/role does not mutate stored `Authentication`

Spring Security Servlet loads/saves `SecurityContext` via a `SecurityContextRepository`; the standard session implementation is `HttpSessionSecurityContextRepository`.

At sign-in:

```text
Credentials -> AuthenticationManager
            -> Authentication(principal, authorities)
            -> SecurityContext
            -> SecurityContextRepository / HttpSession
            -> subsequent requests restore this Authentication
```

Initial snapshot example:

```text
Session ABC:
  principal = alice
  authorities = [ROLE_USER, REPORT_READ]
  authenticated = true
```

Admin edits the database:

```text
user_grants[alice] = [ROLE_USER]
```

**Session ABC does not automatically notice this change.** If subsequent requests restore the old `Authentication` and code checks only `.hasAuthority("REPORT_READ")`, Alice can still read.

### 3.1. Options for sessions

**Option A — Force re-login:** find Alice's sessions and invalidate them. Subsequent requests lack a valid session and must re-authenticate to build a fresh `Authentication`.

**Option B — Refresh Authentication:** reload grants from the authoritative source, build a new authentication **via a trusted mechanism**, replace `SecurityContext`, and save it back to `SecurityContextRepository`.

**Option C — Dynamic per-request permission checks:** the session proves identity only; methods/services query the grant store/PDP to decide, rather than relying solely on snapshotted authorities.

**Option D — Session carrying `authzVersion`:** store the grant version in the session at login; compare against the current version on each request. On mismatch, deny, re-authenticate, or refresh.

High-risk systems often combine A or D with C for sensitive operations. Systems checking only token/session validity without current grants must accept a **stale-permission window** until the session ends.

### 3.2. `SecurityContextHolderFilter` and explicit saving

In Spring Security 6, the default flow reads `SecurityContext` from the repository, and code that **replaces** the context in a custom authentication flow is responsible for **saving** it if changes must persist across requests.

Illustrative snippet once a verified `Authentication fresh` is obtained:

```java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(fresh);
SecurityContextHolder.setContext(context);

// Must match the repository used by the active SecurityFilterChain.
securityContextRepository.saveContext(
    context, request, response
);
```

**This is an integration snippet, not a standalone file:** `fresh`, `securityContextRepository`, `request`, and `response` must come from a valid authentication flow. Never write:

```java
UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest, "ignored",
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
```

to mint new authorities from client input. Refreshing authorities must rely on a verified trusted identity + directory/authorization provider.

### 3.3. Invalidating one session is not invalidating all sessions

Calling:

```java
request.getSession(false).invalidate();
```

invalidates only **the session bound to that specific request** if present; it does not revoke Alice's other sessions on her phone, a second browser, or other server nodes.

Across multiple devices and instances, you need:

- A shared session registry or session store.
- Mapping from principal/stable subject -> active session IDs.
- Authority to delete/expire all related sessions.
- Invalidation propagation to all nodes.
- Handling for requests **already in flight** before revocation.
- Auditing who revoked, when, and why.

### 3.4. `SessionRegistry` and Spring Session

Conceptual snippet using `SessionRegistry`:

```java
// SNIPPET; principal must match the exact object/identity
// stored by SessionRegistry; concurrent session control /
// expiry filter must be configured and active.
for (SessionInformation item :
        sessionRegistry.getAllSessions(principal, false)) {
    item.expireNow();
}
```

`expireNow()` marks the session expired in the registry; it **does not delete every cookie or immediately abort every running request**. Session expiry filters must be properly configured so the next request is blocked.

With Spring Session, `FindByIndexNameSessionRepository` helps look up sessions by principal to delete by ID (when indexed appropriately). This is effective for multi-instance deployments backed by Redis/JDBC session stores; a single in-JVM delete does not guarantee every node sees updates immediately if backend/cache replication lags.

### 3.5. Logging out on the current device differs from revoking everything

Spring Security's default `SecurityContextLogoutHandler` invalidates the current HTTP session and clears `SecurityContext`. `/logout` in a session-based app is important, yet **does not automatically revoke every OAuth2 access token** held by the user.

If another API accepts Bearer JWTs unrelated to the app's session cookie, those JWTs remain accepted unless dedicated revocation, expiration, or live policies apply.

---

## 4. JWT access tokens: signed claims are immutable over the token's lifetime

A self-contained JWT has a payload like:

```json
{
  "iss": "https://issuer.example.invalid/tenant",
  "sub": "alice",
  "aud": ["reports-api"],
  "scope": "reports:read",
  "authz_ver": 7,
  "iat": 1799996400,
  "exp": 1800000000,
  "jti": "token-abc-001"
}
```

This is **JSON illustrating claims**, not a signed JWT. Timestamps are illustrative and do not imply the token is valid at the time of reading.

Resource Server typically verifies:

- Signature with a trusted key/algorithm.
- `iss` matching a trusted issuer.
- `aud` containing the API's audience.
- `exp`/`nbf` against current time and configured clock skew.
- Other claims per application validators.

After decoding, `JwtGrantedAuthoritiesConverter` can create `SCOPE_reports:read` from `scope="reports:read"`. When permissions are revoked in the database, the signed scope claim inside the JWT **is not modified**, and default `JwtDecoder` **does not query the IAM database on every request to check whether roles still exist**.

### 4.1. "Unexpired token" does not mean "still authorized"

Three distinct checks:

```text
JWT.validSignatureAndTime(token)     -> true
JWT.scopeContains("reports:read")    -> true
CURRENT_POLICY.allows(alice, report) -> false
```

A safe authorization decision for a sensitive resource:

```text
ALLOW =
  JWT verified for right issuer/audience/lifetime
  AND granted scope suffices for action
  AND current account is still enabled
  AND authz version/epoch is still accepted
  AND tenant membership/ACL/resource policy permits
```

These conditions may be evaluated across multiple components, yet **updating permission checks must never be skipped** merely because the JWT is validly signed.

### 4.2. Should you wait for the JWT to expire?

Waiting can be acceptable when:

- Scopes are low-risk and expose no sensitive data.
- Token TTL is short.
- Product policy **explicitly tolerates stale permissions up to the TTL**.
- Immediate revocation on offboarding, token compromise, membership removal, or incidents is not required.

If a token has 55 minutes remaining, the stale-permission window can last up to 55 minutes **when Resource Server trusts only token claims**. Short JWT TTLs shrink the window, but never reduce it to zero.

### 4.3. Never rotate JWT signing keys as a per-user revocation mechanism

Deleting or rotating a signing key invalidates **huge numbers of tokens** signed by that key, impacting other users. Moreover, Resource Servers have JWK caches and key rollover behavior. Key rotation is for key lifecycle management and key-compromise runbooks, **not a routine way to revoke Alice's role**.

### 4.4. Frontend logout does not remove the JWT from other servers

A frontend deleting an access token from local storage/cookies stops **that client** from sending it, yet anyone who copied the Bearer token can keep calling the Resource Server.

For the server to reject it, you need token expiry, a denylist, introspection, a policy-version check, or revoked session/grant enforcement at the Resource Server.

---

## 5. Opaque tokens and introspection: checking current status

OAuth2 token introspection per RFC 7662 lets the Resource Server ask the Authorization Server:

```http
POST /oauth2/introspect
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-credentials>

token=opaque-token-value
```

This is an **HTTP illustration**, not a real endpoint or credentials.

Conceptual response:

```json
{
  "active": false
}
```

If the Authorization Server marked the token revoked/inactive, a properly configured introspection Resource Server will refuse to turn that token into a valid `Authentication`.

Spring Security Servlet Resource Server supports:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://issuer.example.invalid/introspect
          client-id: reports-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

And the DSL:

```java
http.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
);
```

This is an **alternative configuration replacing the JWT Resource Server**; do not copy it straight into the JWT sample app unintentionally.

### 5.1. Introspection does not automatically guarantee updated scopes

If the AS returns:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports:read"
}
```

then Resource Server will still produce authority `SCOPE_reports:read`. When an admin edits roles, confirm **whether the Authorization Server updates scopes in introspection responses or returns the grant snapshot from token issuance**. `active=true` usually means the token has not been revoked, not that dynamic domain grants are still valid.

If policy requires immediate permission updates, you can:

- Revoke the token so introspection returns `active=false`.
- Configure the AS to return dynamic permission details under a controlled contract.
- Use introspection for token validity while Resource Server queries the policy/ACL store **for the current object/action**.

### 5.2. Introspection is also subject to caching and availability

Caching an `active=true` introspection response for 60 seconds means immediate AS revocation may not take effect at the Resource Server until the cache expires or is invalidated. Cross-node caches introduce further failure modes.

SLAs must account for:

```text
revoke propagation delay
+ introspection cache TTL / invalidation lag
+ policy-store consistency lag
+ request/in-flight processing time
```

When the introspection endpoint is down, **never fall back to `permitAll`**. For sensitive operations, fail closed; for high availability, design an explicit, risk-assessed, time-bounded offline policy.

### 5.3. Can JWTs also be introspected?

Yes. Spring Security's opaque-token support can **send any token string to introspection**; it does not strictly require an opaque format. Use introspection for JWTs when you want the AS to confirm whether a token has been revoked.

In that case, the validation strategy is **online introspection**, not the default local JWT decoder pipeline. Verify claims/metadata and resource authorization per the introspection service contract—never treat "the JWT has dots" as proof of local cryptographic verification.

---

## 6. Token revocation (RFC 7009) and refresh tokens

### 6.1. What does the revocation endpoint do?

RFC 7009 defines an endpoint where clients send tokens to the Authorization Server to request revocation:

```http
POST /oauth2/revoke
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <oauth-client-credentials>

token=<REFRESH_OR_ACCESS_TOKEN>&token_type_hint=refresh_token
```

This is illustrative syntax per the RFC; actual endpoints, client authentication, and token types depend on the Authorization Server implementation.

**Critical boundary:**

- Revoking a **refresh token** typically prevents using that refresh token to obtain **future access tokens**.
- Already-issued **access tokens** can remain usable until expiry if Resource Servers verify JWTs offline and receive no revocation signal.
- Some AS implementations revoke linked tokens in the same grant; verify actual policy/behavior rather than assuming.
- Revoking access tokens requires Resource Servers to **observe revocation status** via introspection, denylists, or grant versions.

### 6.2. Does refresh token rotation fix old tokens?

No. When a client uses a refresh token to get a new access token, the AS may recompute scopes/claims from current grants, yet **the old JWT access token is not altered**. Refresh token rotation mitigates reuse/replay risks; it does not invalidate previously issued JWTs across Resource Servers.

Example:

```text
09:00 AT1(scope=read, exp=10:00) + RT1
09:10 READ revoked in IAM
09:11 AT1 still exists on device/client
09:20 client refreshes RT1
09:20 AS issues AT2(scope=none) or denies refresh
09:21 Client gets AT2 without READ, yet AT1 may
      still be accepted if RS has no live revocation
```

**Never rely on the frontend rotating tokens on schedule** as a security boundary: an attacker holding AT1 can keep sending AT1 directly.

### 6.3. ID tokens, session cookies, and OAuth access tokens are distinct

An OIDC app can hold simultaneously:

- The **application's own** session cookie.
- An ID token confirming the login event to the client.
- An OAuth access token for calling APIs.
- A refresh token for obtaining new tokens.
- A separate session at the Identity Provider.

Logging out in one place does not automatically revoke all of them. "Log out everywhere" requires coordinating session invalidation, OAuth token revocation, and IdP session logout/back-channel logout if supported. Verify each channel explicitly.

---

## 7. Choosing a strategy based on revocation latency

| Strategy | How it works | Stale-permission window / tradeoff |
| --- | --- | --- |
| Short token TTL | Wait for `exp`; mint new tokens with fresh claims | Up to remaining TTL; simple, stale risk |
| Invalidate sessions | Delete/expire sessions indexed by user | Next request must re-auth; needs shared store and in-flight handling |
| Recreate Authentication | Reload authorities and save `SecurityContext` | Must update all sessions/auth paths and sync caches |
| JWT `jti` denylist | RS checks issuer+`jti` in denylist | Per-request lookup, retention at least until `exp`, HA and consistency |
| Token/user `authzVersion` | Compare token/session version to current store | Old tokens denied as soon as store changes; needs version lookup/cache |
| Opaque introspection | RS queries AS for active/claims | Network latency, AS availability, cache freshness |
| Live policy/ACL lookup | RS checks permissions for actor+resource+action | Accurate to DB policy, adds query cost and race considerations |
| Admin change event | Push invalidation over event bus/cache | Delivery/replay/reconciliation lag still exists |
| Forced re-authentication | Client must sign in again | Server must detect and block old tokens/sessions |
| Short TTL + live checks | Both coarse and fine-grained | Ideal for sensitive APIs; extra ops/observability |

**No single choice fits every application.** Classify operations:

- `GET` public/low-risk info: very short stale window may be acceptable.
- Reading customer/tenant data: use live tenant/ACL lookups.
- Approving transactions, changing roles, deleting, transferring funds: version checks + transaction guards and fast revocation.
- Streaming services: per-subscriber policies and stream cancellation on revocation.
- Compromise incidents: an independent kill switch per account/client/tenant is a mandatory operational capability.

Define explicit SLAs:

```text
Critical revoke: new requests must be denied within X seconds.
Noncritical revoke: maximum lag of Y minutes permitted.
In-flight write: must not commit if grant was revoked
                 before the defined transaction checkpoint.
```

Never pick X/Y by guesswork; base them on risk assessment, data sensitivity, consistency model, and measurable telemetry.

---

## 8. Permission versioning (`authzVersion`) as a simple, explicit mechanism

A policy store can record:

```text
User: issuer=https://issuer.example.invalid/tenant, sub=alice
Tenant: T1
Enabled: true
Scopes/current permissions: [reports:read]
authzVersion: 7
```

When an admin revokes:

```text
Scopes/current permissions: []
authzVersion: 8
```

When issuing an access token, the Authorization Server can embed `authz_ver=7` in the JWT. After verifying the token, the Resource Server queries the store:

```text
token.authz_ver == store.authzVersion ?
```

If unequal -> **reject token / deny operation** per contract. If equal -> proceed to check **current grants, tenant, and object permissions**.

### 8.1. Why increment version even when re-granting permissions?

Suppose revocation increments version 7 → 8, and a later re-grant increments 8 → 9. The old version-7 JWT still carries the READ scope. If you checked only "does the user currently have READ?" without version, the old token could **suddenly start working again** after the re-grant. With strict version checks, old tokens never come back to life.

```text
t1  JWT1 version=7, scope=read -> ALLOW
t2  revoke, store version=8       -> DENY JWT1
t3  regrant, store version=9      -> JWT1 STILL DENIED
t4  issue JWT2 version=9          -> ALLOW if current policy permits
```

**Note:** Versioning is an app-specific design. It can attach to a user, user+tenant, grant family, client, or session depending on required revocation granularity. Keys should include issuer/tenant/client where ID namespaces collide.

### 8.2. `iat` or `authzVersion`?

You can store `revokedBefore`/`notBeforeEpoch` on a user and require `iat` greater than that threshold. This works well, but requires handling:

- Exact second vs. millisecond timestamp precision.
- Clock skew between AS and RS.
- Tokens minted concurrently with admin revocation.
- Tokens lacking `iat` or carrying forged `iat` (before signature verification).
- Permission changes scoped to a single tenant/client rather than every token.

An explicit **monotonic version** is typically easier to test for user grant changes. For single-token kills, use a dedicated `jti` denylist.

### 8.3. Caching versions while understanding lag

If the Resource Server caches the current version for 30 seconds, old JWTs remain accepted until the cache invalidates. If the requirement is "revoke within 2 seconds," a 30-second cache violates it.

You need:

- Version lookups with HA and bounded timeouts.
- Cache invalidation broadcast to all nodes on admin grant changes.
- Metrics for `policy_version_mismatch`, cache age, and revoke propagation.
- Reviewed max TTLs aligned with SLA.
- Fail-closed behavior on sensitive operations when current version cannot be read.

### 8.4. `authzVersion` still does not replace object-level policies

Matching a user's version is **insufficient** if the report changed tenant/owner after token issuance or its object ACL changed. Verify resource-specific facts in the repository/transaction.

---

## 9. Standard-library Java 17 example: observing stale permissions and version checks

This example **runs on JDK 17** with no Spring, JWT keys, or network. It simulates session and access token snapshots to demonstrate when permissions change.

**Limitation:** `AccessToken` in this example is a **simulated Java record**, **not a signed JWT**, with no real token verification capability. Production authentication and signature verification must be handled by Spring Security Resource Server/Authorization Server.

### 9.1. Create `PermissionChangeDemo.java`

```java
import java.util.HashSet;
import java.util.Set;

public class PermissionChangeDemo {

    private static final String READ = "reports:read";

    record SessionSnapshot(
            Set<String> authorities,
            long issuedVersion,
            boolean active) {

        SessionSnapshot {
            authorities = Set.copyOf(authorities);
        }
    }

    record AccessToken(
            Set<String> scopes,
            long issuedVersion,
            long expiresAtEpochSecond) {

        AccessToken {
            scopes = Set.copyOf(scopes);
        }
    }

    static final class Directory {

        private final Set<String> current = new HashSet<>();
        private long version = 1;

        Directory() {
            current.add(READ);
        }

        long version() {
            return version;
        }

        boolean has(String scope) {
            return current.contains(scope);
        }

        Set<String> snapshot() {
            return Set.copyOf(current);
        }

        void revokeRead() {
            current.remove(READ);
            version++;
        }

        void restoreRead() {
            current.add(READ);
            version++;
        }
    }

    static boolean sessionSnapshotAllows(
            SessionSnapshot session) {
        return session.active()
            && session.authorities().contains(READ);
    }

    static boolean tokenSnapshotAllows(
            AccessToken token, long now) {
        return now < token.expiresAtEpochSecond()
            && token.scopes().contains(READ);
    }

    static boolean sessionLiveAllows(
            SessionSnapshot session, Directory directory) {
        return sessionSnapshotAllows(session)
            && session.issuedVersion() == directory.version()
            && directory.has(READ);
    }

    static boolean tokenLiveAllows(
            AccessToken token, Directory directory, long now) {
        return tokenSnapshotAllows(token, now)
            && token.issuedVersion() == directory.version()
            && directory.has(READ);
    }

    public static void main(String[] args) {
        long now = 100L;
        Directory directory = new Directory();

        SessionSnapshot sessionV1 = new SessionSnapshot(
            directory.snapshot(), directory.version(), true);

        AccessToken tokenV1 = new AccessToken(
            directory.snapshot(), directory.version(), 200L);

        System.out.println("SESSION_INITIAL: "
            + sessionSnapshotAllows(sessionV1));
        System.out.println("TOKEN_INITIAL: "
            + tokenSnapshotAllows(tokenV1, now));

        directory.revokeRead();

        System.out.println("SESSION_STALE_AFTER_REVOKE: "
            + sessionSnapshotAllows(sessionV1));
        System.out.println("TOKEN_STALE_AFTER_REVOKE: "
            + tokenSnapshotAllows(tokenV1, now));
        System.out.println("SESSION_LIVE_AFTER_REVOKE: "
            + sessionLiveAllows(sessionV1, directory));
        System.out.println("TOKEN_LIVE_AFTER_REVOKE: "
            + tokenLiveAllows(tokenV1, directory, now));

        AccessToken tokenV2 = new AccessToken(
            directory.snapshot(), directory.version(), 200L);

        System.out.println("NEW_TOKEN_AFTER_REVOKE: "
            + tokenLiveAllows(tokenV2, directory, now));

        directory.restoreRead();

        System.out.println("OLD_TOKEN_AFTER_REGRANT: "
            + tokenLiveAllows(tokenV1, directory, now));

        AccessToken tokenV3 = new AccessToken(
            directory.snapshot(), directory.version(), 200L);

        System.out.println("NEW_TOKEN_AFTER_REGRANT: "
            + tokenLiveAllows(tokenV3, directory, now));

        System.out.println("NEW_TOKEN_EXPIRED: "
            + tokenLiveAllows(tokenV3, directory, 201L));
    }
}
```

### 9.2. Compile and run

In the directory containing `PermissionChangeDemo.java`:

```bash
javac -encoding UTF-8 PermissionChangeDemo.java
java PermissionChangeDemo
```

**Exact output from the program:**

```text
SESSION_INITIAL: true
TOKEN_INITIAL: true
SESSION_STALE_AFTER_REVOKE: true
TOKEN_STALE_AFTER_REVOKE: true
SESSION_LIVE_AFTER_REVOKE: false
TOKEN_LIVE_AFTER_REVOKE: false
NEW_TOKEN_AFTER_REVOKE: false
OLD_TOKEN_AFTER_REGRANT: false
NEW_TOKEN_AFTER_REGRANT: true
NEW_TOKEN_EXPIRED: false
```

Reading the results:

- Both initial snapshots contain READ, so `true`.
- Revoking in the directory **does not alter** already-created sessions/tokens: snapshot-only checks still return `true`.
- Live checks compare versions and current permissions, returning `false`.
- A new access token issued after revocation lacks READ.
- When READ is re-granted, the old-version JWT **remains invalid under the strict version contract**.
- The new version-3 JWT is allowed, until it expires past `expiresAt`.

**This stdout is derived from the source code, not proof of execution on the learner's machine.** Run the commands yourself to confirm and resolve any local Java setup issues.

### 9.3. Why use `Set.copyOf`?

Session and token snapshots must be **immutable** in this example; if the code kept a mutable `Set` referencing the directory, mutating `directory.current` would inadvertently mutate the snapshots too. That would hide the exact problem this lesson demonstrates: **old tokens/sessions carry old permissions**.

In real JWTs, claims are signed and do not change when the IAM database changes. Session `Authentication` is an object stored in the session; code can replace it, provided explicit update/persistence/replication mechanisms are in place.

---

## 10. Spring Security 6.5 demo: old JWT denied even when signature and lifetime remain valid

This project includes:

- `Spring Boot 3.5.8`, Java 17, Servlet JWT Resource Server.
- `@EnableMethodSecurity` and `@PreAuthorize`.
- JWT scope `reports:read` mapped to `SCOPE_reports:read`.
- `GrantDirectory` holding **current authorities + authzVersion**.
- `LiveReportPolicy` checking JWT scope, trusted issuer/audience, `authz_ver`, user enabled flag, and tenant/resource.
- `ReportService` returning reports protected by method security.
- `MockMvc` tests sending a **Bearer header** with a test-only `JwtDecoder` to exercise the real JWT-claims -> authorities -> method-policy flow.
- Mutating permissions directly in the directory mid-test, then re-sending the **exact same Bearer token**.

**Distinguishing production from tests:** In real runs, Spring Security must use a `JwtDecoder` with signature/issuer/time/audience validators. In tests, a fake decoder simulates already-decoded JWTs solely to test **permission-change logic**, not JWT cryptography.

### 10.1. Directory structure

```text
live-permissions-resource-server/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── LivePermissionsApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── GrantDirectory.java
    │   │   ├── ReportStore.java
    │   │   ├── LiveReportPolicy.java
    │   │   ├── ReportService.java
    │   │   └── ReportController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        └── PermissionChangeSecurityTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'live-permissions-resource-server'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This demo uses only the Servlet web starter. For Spring WebFlux, switch to `ServerHttpSecurity`/`SecurityWebFilterChain` and reactive policy lookups rather than copying this `HttpSecurity` as-is.

### 10.4. `application.yml`

**`src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/tenant
          audiences:
            - reports-api
```

`issuer.example.invalid` is an intentionally **non-working sample address**, not a real Identity Provider. Main execution requires a real issuer with matching JWK endpoints. Tests define a fake decoder in test sources so they do not depend on a live issuer.

**Production must validate** signature, issuer, audience, `exp`, and `nbf`. The `authz_ver` contract runs **after** those checks, never replacing them.

### 10.5. Application

**`src/main/java/demo/LivePermissionsApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LivePermissionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            LivePermissionsApplication.class, args
        );
    }
}
```

### 10.6. Spring Security configuration

**`src/main/java/demo/SecurityConfig.java`:**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**"
                ).hasAuthority("SCOPE_reports:read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

By default, JWT `scope="reports:read"` becomes authority `SCOPE_reports:read`. The HTTP check serves as a **coarse scope guard**. Method security below enforces the **live version/tenant check**.

**CSRF:** The demo project exposes only HTTP GET, so CSRF is not disabled. For APIs exposing POST/DELETE and using browser cookies/sessions, evaluate CSRF explicitly. A strictly stateless Bearer-header API has a different threat model, though blanket CSRF disabling should never be applied blindly across architectures.

**`STATELESS` does not mean tokens expire when roles change.** It merely states that Resource Server does not use HTTP sessions for this authentication mechanism; current policy must still be enforced.

### 10.7. Versioned grant store

**`src/main/java/demo/GrantDirectory.java`:**

```java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class GrantDirectory {

    public static final String ISSUER =
        "https://issuer.example.invalid/tenant";

    public record Grant(
            String tenantId,
            long version,
            boolean enabled,
            Set<String> permissions) {

        public Grant {
            permissions = Set.copyOf(permissions);
        }
    }

    private final Map<String, AtomicReference<Grant>> grants =
        Map.of(
            "alice", new AtomicReference<>(
                new Grant(
                    "T1", 1L, true, Set.of("reports:read")
                )
            ),
            "bob", new AtomicReference<>(
                new Grant(
                    "T2", 1L, true, Set.of("reports:read")
                )
            )
        );

    public Grant find(String issuer, String subject) {
        if (!ISSUER.equals(issuer)) {
            return null;
        }

        AtomicReference<Grant> value = grants.get(subject);
        return value == null ? null : value.get();
    }

    public void revokeRead(String subject) {
        AtomicReference<Grant> reference = require(subject);

        reference.updateAndGet(old -> new Grant(
            old.tenantId(),
            old.version() + 1,
            old.enabled(),
            Set.of()
        ));
    }

    public void restoreRead(String subject) {
        AtomicReference<Grant> reference = require(subject);

        reference.updateAndGet(old -> new Grant(
            old.tenantId(),
            old.version() + 1,
            old.enabled(),
            Set.of("reports:read")
        ));
    }

    private AtomicReference<Grant> require(String subject) {
        AtomicReference<Grant> value = grants.get(subject);

        if (value == null) {
            throw new IllegalArgumentException(
                "Unknown trusted principal"
            );
        }
        return value;
    }
}
```

`GrantDirectory` is an in-memory **demo-only** store. It intentionally exposes `revokeRead`/`restoreRead` to test permission-change events; **never expose these methods as public APIs**.

In production:

- Use a database/IAM/authorization policy service with a defined consistency contract.
- Identity keys should include **issuer + stable subject**, plus tenant/client when scopes are bound to them.
- `version` must be monotonic and never reset on restart.
- Grant updates and version increments should be **one atomic transaction**.
- Cache invalidations must reach all instances.
- Every grant/revoke endpoint must enforce administrative checks and auditing.
- Never trust a client-sent JSON `authz_ver`; read it only from a **verified JWT**.

### 10.8. Immutable resource store in the demo

**`src/main/java/demo/ReportStore.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.stereotype.Repository;

@Repository
public class ReportStore {

    public record Report(
            long id,
            String tenantId,
            String title) {
    }

    private final Map<Long, Report> reports = Map.of(
        100L, new Report(100L, "T1", "Quarterly-T1"),
        200L, new Report(200L, "T2", "Quarterly-T2")
    );

    public Report find(long id) {
        return reports.get(id);
    }
}
```

An immutable store keeps focus on **grant** changes. In real applications, permissions may also depend on resource state and ownership; queries/transactions must reflect current data together.

### 10.9. Policy checking both claims and current grants

**`src/main/java/demo/LiveReportPolicy.java`:**

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("livePolicy")
public class LiveReportPolicy {

    private final GrantDirectory directory;
    private final ReportStore reports;

    public LiveReportPolicy(
            GrantDirectory directory,
            ReportStore reports) {
        this.directory = directory;
        this.reports = reports;
    }

    public boolean canRead(
            Authentication authentication, long reportId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()) {
            return false;
        }

        boolean scopeGranted = authentication.getAuthorities()
            .stream()
            .anyMatch(a ->
                "SCOPE_reports:read".equals(a.getAuthority())
            );

        if (!scopeGranted) {
            return false;
        }

        var jwt = jwtAuth.getToken();

        String issuer = jwt.getClaimAsString("iss");

        if (!GrantDirectory.ISSUER.equals(issuer)
                || !jwt.getAudience().contains("reports-api")) {
            return false;
        }

        Object rawVersion = jwt.getClaim("authz_ver");

        if (!(rawVersion instanceof Number version)) {
            return false;
        }

        GrantDirectory.Grant current =
            directory.find(issuer, jwt.getSubject());

        ReportStore.Report report = reports.find(reportId);

        if (current == null || report == null) {
            return false;
        }

        return current.enabled()
            && current.version() == version.longValue()
            && current.permissions().contains("reports:read")
            && current.tenantId().equals(report.tenantId());
    }
}
```

**Core logic:**

1. Only JWTs that passed the Resource Server authentication flow reach `LiveReportPolicy`.
2. Scope `SCOPE_reports:read` is checked against the mapped authorities.
3. Policy re-checks issuer and audience as **defense in depth**; production must enforce real decoder validators.
4. `authz_ver` must be a number per contract; missing or wrong type -> deny.
5. Directory looks up the current grant by trusted issuer+sub.
6. If the user is disabled, version mismatches, or READ was revoked -> deny.
7. If the report belongs to another tenant -> deny.
8. Missing data -> deny; never fall back to an old role.

In real systems, version checks should be cached/queried within SLA freshness; when the policy store is down, design **fail-closed** behavior for sensitive operations. The demo makes no remote calls and therefore does not simulate network failures.

**TOCTOU warning:** After the check, the report, tenant, or permission can still change before the DB action. With the demo's immutable report reads, there is no resource race; for writes or mutable data, add DB guards and locking/versioning.

### 10.10. Method security at the service layer

**`src/main/java/demo/ReportService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportStore reports;

    public ReportService(ReportStore reports) {
        this.reports = reports;
    }

    @PreAuthorize(
        "@livePolicy.canRead(authentication, #p0)"
    )
    public String read(long reportId) {
        return reports.find(reportId).title();
    }
}
```

`#p0` refers to the first method argument without depending on Java reflection parameter names. `@EnableMethodSecurity` in `SecurityConfig` enables the interceptor.

**Crucial point for testing:** `ReportService` must be called through its Spring-managed proxy (`@Service` injected into the controller); `new ReportService(...)` or `this.read()` from inside the same bean can bypass Spring AOP. In production, domain/repository protections must remain solid across all entry points.

`reports.find(...).title()` is safe here only because `LiveReportPolicy` checked existence and the store is immutable. For concurrently mutable real data, do not write it this way; load the resource scoped by tenant/permissions inside a transaction or authoritative query.

### 10.11. Controller

**`src/main/java/demo/ReportController.java`:**

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/api/reports/{id}")
    public String read(@PathVariable long id) {
        return service.read(id);
    }
}
```

The controller never reads `sub`, roles, or tenant from the request body to grant access. Spring Resource Server validates the Bearer token, then the service enforces current grants.

---

## 11. Testing: same old JWT, changed permissions

The tests below do not fake `SCOPE_` authorities directly; they send `Authorization: Bearer ...` through Spring Security filters and let the real `JwtAuthenticationConverter` read `scope`/`authz_ver` from the test JWT fixture.

**Never use a fake `JwtDecoder` in production.** Token strings `alice-v1` and `alice-v3` below **exist only in the test fixture**. They are not real signed JWTs.

### 11.1. `src/test/java/demo/PermissionChangeSecurityTest.java`

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(PermissionChangeSecurityTest.DecoderForTest.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class PermissionChangeSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    GrantDirectory grants;

    @TestConfiguration(proxyBeanMethods = false)
    static class DecoderForTest {

        @Bean
        @Primary
        JwtDecoder jwtDecoder() {
            return raw -> switch (raw) {
                case "alice-v1" -> issue(
                    raw, "alice", "reports:read", 1, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "alice-v3" -> issue(
                    raw, "alice", "reports:read", 3, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "alice-no-scope" -> issue(
                    raw, "alice", "profile", 1, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "bob-v1" -> issue(
                    raw, "bob", "reports:read", 1, "reports-api",
                    GrantDirectory.ISSUER
                );
                case "alice-wrong-aud" -> issue(
                    raw, "alice", "reports:read", 1, "other-api",
                    GrantDirectory.ISSUER
                );
                case "alice-wrong-issuer" -> issue(
                    raw, "alice", "reports:read", 1, "reports-api",
                    "https://untrusted.example.invalid"
                );
                case "alice-no-version" -> Jwt
                    .withTokenValue(raw)
                    .header("alg", "RS256")
                    .claim("iss", GrantDirectory.ISSUER)
                    .claim("sub", "alice")
                    .claim("aud", List.of("reports-api"))
                    .claim("scope", "reports:read")
                    .build();
                default -> throw new BadJwtException(
                    "Invalid token in test fixture"
                );
            };
        }

        private static Jwt issue(
                String token,
                String sub,
                String scope,
                int version,
                String audience,
                String issuer) {

            return Jwt.withTokenValue(token)
                .header("alg", "RS256")
                .claim("iss", issuer)
                .claim("sub", sub)
                .claim("aud", List.of(audience))
                .claim("scope", scope)
                .claim("authz_ver", version)
                .build();
        }
    }

    private static String bearer(String raw) {
        return "Bearer " + raw;
    }

    @Test
    void sameOldTokenIsDeniedAfterRevoke()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Quarterly-T1"));

        // Admin operation in test updates the CURRENT store.
        grants.revokeRead("alice");

        // Fixture token alice-v1 still carries scope "reports:read".
        // HTTP scope guard may pass, yet live policy DENIES.
        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isForbidden());

        grants.restoreRead("alice");

        // Regrant must not resurrect version-1 JWT.
        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isForbidden());

        // New version-3 token while current grant includes READ.
        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v3")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Quarterly-T1"));
    }

    @Test
    void currentScopeStillRequiresCurrentTenant()
            throws Exception {

        mvc.perform(get("/api/reports/200")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("alice-v1")
                ))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/200")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("bob-v1")
                ))
            .andExpect(status().isOk())
            .andExpect(content().string("Quarterly-T2"));
    }

    @Test
    void tokenWithoutReadScopeIsForbidden()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-no-scope")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void tokenMissingVersionIsForbidden()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-no-version")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongIssuerOrAudienceIsNotAuthorized()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-wrong-aud")
                ))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION,
                    bearer("alice-wrong-issuer")
                ))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenGetsUnauthorized()
            throws Exception {

        mvc.perform(get("/api/reports/100")
                .header(
                    HttpHeaders.AUTHORIZATION, bearer("not-a-token")
                ))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingTokenGetsUnauthorized()
            throws Exception {

        mvc.perform(get("/api/reports/100"))
            .andExpect(status().isUnauthorized());
    }
}
```

### 11.2. Why does this test verify the right problem?

- The first test sends the **exact same Bearer string `alice-v1`** before and after revocation. It does not mint a new token for the second check.
- Resource Server processes the Bearer header and uses the **real `JwtAuthenticationConverter`** to produce `SCOPE_reports:read`.
- The HTTP scope guard may still pass for the old token; **`LiveReportPolicy` checks the current version** and denies.
- Regranting to version 3 still rejects the version-1 JWT, while issuing a new version-3 token succeeds.
- Tests verify Alice reading T2's report is denied while Bob/T2 succeeds.
- Tests verify missing scope, missing `authz_ver`, and wrong issuer/audience are denied.
- Tests verify undecodable tokens and missing tokens return 401 via the Bearer entry point.

**Important testing boundary:** The fake decoder in `@TestConfiguration` does not test real signature, `exp`, `nbf`, or issuer/audience validators. The issuer/audience branch inside `LiveReportPolicy` returns 403 in tests, whereas a **proper production decoder must reject wrong-issuer/audience tokens at authentication**, typically returning 401. Write dedicated tests with a real `NimbusJwtDecoder`, JWK fixtures, and a test clock to prove cryptographic and temporal validators work.

### 11.3. Running Gradle tests

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

If no Gradle Wrapper exists yet, use a compatible installed Gradle version to generate it first, or run `gradle test` with an installed Gradle.

**Expected result:** seven integration tests in `PermissionChangeSecurityTest` pass. This expectation is based on the source code, **not a claim of having compiled or executed it** in the authoring environment.

To run the main API via `./gradlew bootRun`, configure a **real** Authorization Server in place of `issuer.example.invalid`. Without a live IdP, the sample project defines the configuration structure and runs tests via the fake decoder.

---

## 12. Refreshing permissions in a session-based application

The Resource Server example in Section 10 is **stateless JWT**, using no HTTP session for authentication. In a **different application** using form-login/sessions, you can refresh authorities in several ways.

### 12.1. Option 1 — expire related sessions

When an admin updates a role:

```text
Transaction updates grants + increments policyVersion
             |
             v
Commit database
             |
             v
Emit "UserGrantsChanged" event
             |
             +--> Expire/delete sessions by issuer+subject
             |
             +--> Invalidate caches across all app nodes
             |
             +--> Audit, metrics, retry events
```

Subsequent requests using old sessions are forced to re-authenticate or rejected immediately by a version gate. If you only emit an event and delete sessions asynchronously, a **propagation window** remains; for sensitive use cases, add a version/policy lookup directly inside the use case.

### 12.2. Option 2 — reload `Authentication` and save `SecurityContext`

Snippet:

```java
Authentication fresh =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            verifiedUsername, verifiedCredential
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(fresh);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context, request, response
);
```

**Not a standalone file:** beans, requests, and verified credentials must come from a real authentication flow. If credentials are unavailable to re-authenticate, use a trusted directory/provider to rebuild authorities from a verified principal via a separate mechanism—never build an authenticated token from a user ID in the request body.

Saving the new session context also does not update **other active sessions**. To revoke everywhere, track a version or locate and delete every session.

### 12.3. Option 3 — separate session identity from live permissions

Instead of treating authorities inside the session as the full source of truth:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "@liveGrantService.canRead(authentication, #p0)"
)
public ReportView read(long reportId) {
    // Repository checks real tenant/ACL.
}
```

Snippet for a **session-based application**; `liveGrantService` must handle `UsernamePasswordAuthenticationToken`/the appropriate principal, not just `JwtAuthenticationToken` as in the JWT demo.

This approach avoids updating every `Authentication` snapshot on role changes. However, you need clear lookup latency, availability, and caching policies, plus fail-closed handling when the policy service fails to respond.

### 12.4. Option 4 — session stores `policyVersion`

Store in the session:

```text
userId = alice
sessionPolicyVersion = 7
```

When current version increments to 8, new requests can be blocked **right before** sensitive methods run. After re-authentication or session refresh, the new version is stored. Implement a custom filter/`AuthorizationManager` using the trusted session identity; avoid relying solely on `@PreAuthorize` on one endpoint while forgetting others.

---

## 13. `jti` token denylist and revocation by token, user, or tenant

If you must revoke **one specific access token** without forcing all of the user's other tokens to sign in again, a denylist can store:

```text
key: revoked:{issuer}:{jti}
value: revoked
expiry: token.exp + allowedClockSkew
```

Upon receiving a verified JWT, Resource Server checks the denylist for trusted `issuer+jti`. If present, reject.

### 13.1. Benefits and limitations

- Allows revoking one specific token/session, e.g., a leaked token.
- Avoids bumping every user's policy version when killing just one token.
- Requires `jti` to be unique per issuer/tenant/grant family, or a safe token fingerprint.
- Must retain denylist entries until the token definitely expires, including clock skew.
- Multi-node cache/replication must stay consistent within SLA.
- When Redis/denylist store is unavailable, fail closed for sensitive operations or follow an approved degraded-mode policy.
- All signature/issuer/audience/time validations must still run before reading `jti` as a security key.

Do not store raw access tokens in logs or denylists unnecessarily. If tokens lack `jti`, design a dedicated alternative: hash tokens with an appropriate algorithm, or use `authzVersion` for whole-user revocation. Never trust a client-supplied `jti` query parameter for authorization decisions.

### 13.2. Differences between revoking a user vs. revoking a token

- **Revoke user grants:** the user loses READ; version/policy store blocks old tokens from READ.
- **Revoke one token:** only token `jti=x` is rejected; another valid token for the same user may continue working.
- **Disable account:** usually requires blocking all sessions/tokens for the subject per the identity store, even low-scope tokens.
- **Revoke tenant membership:** only operations targeting that tenant are blocked; keys/versions can be `user+tenant` for fine granularity.
- **Compromised client:** may require revoking all client grants/token families, not just a single user.

Distinguish these scopes so a revocation command is neither overly broad nor too narrow.

---

## 14. Race conditions: permission revoked between check and DB commit

Even when Resource Server queries current policy on every request:

```text
T1: GET current grant -> reports:approve = ALLOW
T2: Admin revokes reports:approve
T3: Service UPDATES report to APPROVED
T4: Transaction COMMITS
```

An authorization check before a business method does not form an atomic transaction with concurrent grant changes.

### 14.1. Conditional mutation

Database guard example:

```sql
UPDATE reports
SET status = 'APPROVED',
    approved_by = :trustedSubject,
    version = version + 1
WHERE id = :reportId
  AND tenant_id = :trustedTenantId
  AND status = 'PENDING'
  AND version = :expectedVersion;
```

**This SQL guards resource facts** such as tenant, state, and version; if permissions live in a separate grant table, you still need a mechanism synchronizing the permission/authorization version with the write transaction.

### 14.2. When grants are also in the database

You can use shared transactions/locking or synchronized version checks:

1. Read user/tenant grant version inside the transaction.
2. Read the resource row constrained by tenant/owner/ACL.
3. Verify current permissions and invariants.
4. Execute UPDATE with `WHERE version = :expectedVersion` or lock rows in a consistent order.
5. Ensure **revocation** transactions participate in the same locking/version protocol if immediate revocation relative to commits is required.

If the revoker updates only Redis while the writer locks only the report row in SQL, those two locks **do not** coordinate with each other. Define explicitly whether "revocation takes effect upon grant-store commit" or "after events reach all Resource Servers."

### 14.3. Never rely on `@PostAuthorize` alone for writes

`@PostAuthorize` evaluates after the method has already executed side effects. It is no substitute for `@PreAuthorize` and conditional DML/transaction guards when approving, deleting, or transferring funds.

### 14.4. Background jobs and streaming

Sessions/tokens can expire or permissions can be revoked while:

- A message consumer processes a task minutes after the HTTP request.
- A batch job uses a delegated token.
- A WebSocket/SSE stream stays connected for hours.
- A file download has started while chunks are still streaming.

Never treat an ALLOW at connection time as a permanent grant. Design job identities, policy refreshes, per-item/batch re-checks, and cancellation per data sensitivity. Once a stream has started sending response bytes, you cannot always switch the status to 403; cancel the stream and audit it.

---

## 15. Caches, network failures, and revocation SLAs

Caches directly affect propagation latency:

| Cache | Contents | Risk |
| --- | --- | --- |
| JWT decoder/JWK cache | Public keys/metadata | Does not replace grant lookups; key rotation cannot target one user |
| Session cache | `SecurityContext`/authorities | Misses new roles unless session refreshes |
| Introspection cache | `active=true`, scopes | Revoked tokens remain accepted until cache expires |
| User/grant cache | Roles/permissions/epoch | Version mismatches may be missed |
| ACL cache | Object-level permissions | Owner/tenant/ACL changes not yet propagated |
| Response/data cache | Already-authorized results | Reused across users/tenants, risking data leaks |

**Authorization cache keys** typically require:

```text
issuer, subject, tenant, action,
resourceType, resourceId, resourceVersion,
policyVersion / authzVersion
```

Never cache boolean `canRead` keyed solely by `reportId`; Alice and Bob have different identities and tenants.

When policies span multiple nodes:

```text
Admin revoke
    |
    +--> update authoritative store atomically
    |
    +--> publish invalidation event
    |       +--> Node A local cache
    |       +--> Node B local cache
    |       +--> Node C local cache
    |
    +--> metrics/alerts for propagation lag
```

Provide fallback or reconciliation in case a node misses an event; fire-and-forget invalidation events are insufficient. For ultra-sensitive permissions, read directly from a strongly consistent store or block when the latest version cannot be confirmed.

### 15.1. `fail closed` is the default for high risk

If a policy lookup times out:

```java
// INTENTIONALLY WRONG:
try {
    return policyService.canApprove(actor, report);
} catch (Exception ex) {
    return true;
}
```

That code turns a PDP outage into granted access. Handle errors/denials appropriately for your system, e.g.:

```java
// SNIPPET, requires dedicated policyService and exception mapping.
try {
    return policyService.canApprove(actor, report);
} catch (PolicyUnavailableException unavailable) {
    return false;
}
```

If offline operation is desired, design an explicit policy snapshot/TTL and an approved operation subset—never accidentally `allow` inside a `catch` block.

### 15.2. Short TTL + introspection may still fall short

Measure real propagation latency under scenarios like:

```text
09:10:00 admin commits revoke
09:10:01 Node A denies request with old token
09:10:07 Node B still accepts old token from stale cache
09:10:11 Node B cache refreshes, starts denying
```

If the admin-permission SLA is 3 seconds, this system **violates its SLA** despite great average latency. Measure p95/p99, multi-node skew, cache invalidation lag, and in-flight work—not just "token expires after 5 min."

---

## 16. 401, 403, and 404: avoid reporting the wrong cause

| Scenario | Common HTTP status | Where to fix? |
| --- | --- | --- |
| Missing access token on private endpoint | 401 | Authentication/client token |
| Invalid signature, expired, wrong issuer/audience | 401 | Decoder trust/validators, AS |
| Token has scope but stale `authz_ver` | 403 at policy layer, or 401 if treated as revoked token at authentication | Version gate and contract |
| Expired/invalidated session | 401 or login redirect | Session authentication entry point |
| Valid token missing `SCOPE_reports:read` | 403 | Scope grant/mapping |
| Current tenant differs from report tenant | 403 or 404 | Data authorization |
| Disabled account with unexpired token | 403/401 depending on check layer | Current account state |
| Introspection endpoint unreachable | Do not execute operation; code per error contract | Fail closed, retry/deadline |
| Access token refreshed while old token remains alive | May still access if unrevoked | Revocation/version/introspection |

**Never fix every 403 by disabling `@PreAuthorize` or changing `.hasAuthority(...)` to `.authenticated()`.** First distinguish token validity, authority mapping, current grants, tenant/ACL, and domain state errors.

When forcing users to refresh/re-authenticate after a role change, the API can standardize an application error code such as `AUTHZ_VERSION_STALE`; clients then request a new token or redirect to login. Crucially, **the server must reject the old token**, not merely ask the frontend to refresh politely.

Never let error messages leak details about other-tenant accounts, object existence, internal roles, policy engines, or JWK configs.

---

## 17. Post-permission-change test matrix

| Case | What must be proven |
| --- | --- |
| Session at login has READ | Succeeds before revocation |
| Admin revokes READ while session is active | Stale session cannot read past SLA |
| Current session invalidated | Next request must re-authenticate |
| User has multiple sessions/devices | Revocation applies across all related scopes |
| Version-1 JWT has READ | GET succeeds before revocation |
| Same version-1 JWT after revocation | Must DENY even though unexpired |
| Regrant READ incrementing to version 3 | Version-1 JWT still does not regain access |
| New version-3 JWT | ALLOWs when current grants/tenant match |
| JWT missing `authz_ver` | DENY when version contract is mandatory |
| JWT missing READ scope | DENY, even with new version |
| JWT wrong issuer/audience | Rejected by decoder in production |
| Unverifiable/expired JWT | 401 per Bearer auth |
| Token `jti` in denylist | DENY before touching protected resources |
| Opaque introspection `active=false` | DENY |
| Stale introspection cache `active=true` | Test propagation lag and TTL |
| Stale policy cache | Within revocation SLA |
| Policy service error/timeout | Never falls back to allow |
| T1 user with READ token probes T2 ID | DENY or 404, zero data leaked |
| Owner/ACL changes between check and use | DB mutation blocked per consistency contract |
| Refresh token revoked | Cannot mint new access tokens with old RT |
| Old AT after RT revocation | Rejected if system **supports** access-token revocation |
| Multi-node A/B | All nodes converge within SLA |
| Background job after revocation | Re-authorizes at execution time |
| WebSocket/SSE after revocation | Cancels or re-checks per item per policy |

A test suite should include **ALLOW before revoke**, **DENY after revoke**, **ALLOW with new token**, and **DENY old token after regrant**. If you test only deny-after-revoke, a broken manager that always returns `false` would pass while rendering the system unusable.

---

## 18. Common mistakes

| Mistake | Why is it wrong? | Solution |
| --- | --- | --- |
| "Changing role in DB updates the session" | Sessions hold an `Authentication` snapshot | Refresh/invalidate sessions or use live policy |
| "Valid JWT signature means roles are still valid" | Signature proves issuance state, not current grants | `authzVersion`/denylist/introspection/live ACL |
| "Deleting a cookie revokes the token" | Token may have been copied | Server-side revocation |
| "Revoking refresh token revokes access token" | Issued AT can keep living | AT-specific revocation policy |
| "`exp` has 1 hour left, no big deal" | Long stale-permission window | Short TTL + dynamic checks per risk |
| Using `iat` without clock-skew handling | Races/timestamp precision | Monotonic version and tests |
| Re-granting READ revives old tokens | Checked only current grant | Strict version checks |
| Caching version by colliding `userId` across issuers | Cross-issuer confusion | Issuer + subject + tenant |
| Unit testing only `hasAuthority` | Skips converter/HTTP path | `MockMvc` Bearer integration |
| Leaving fake `JwtDecoder` in `main` | Skips signature verification | Test-only decoder; prod Nimbus decoder |
| Caching introspection for too long | Revoked tokens stay stale | TTL/invalidation within SLA |
| Policy service down -> ALLOW | Fail-open | Deny/fail operation |
| Assuming `SessionRegistry.expireNow` kills instantly | Marks expired; still needs filters/lifecycle | Configure expiry, test multi-node |
| Logging out one session and thinking user is logged out everywhere | Other sessions/tokens persist | Shared session registry + token revocation |
| JWT scope suffices -> read any tenant | Scope is functional only | Tenant + ACL/data guards |
| Checking in-memory ACL then running unscoped UPDATE | TOCTOU/cross-tenant | Conditional DML/transactions |
| Taking JWT roles from client-supplied JSON | Broken trust boundary | Verified tokens + trusted issuers only |
| Bumping version without atomic commit | Token issuance vs. policy update race | Transactional grant/version updates |
| Firing invalidate events with no retries | Nodes miss events | Reconciliation + max TTL |
| Checking WebSocket ALLOW only on connect | Permissions can be revoked mid-stream | Re-check/cancel |
| Logging tokens for debugging | Exposes Bearer credentials | Hash/correlation IDs, redact |
| Rotating JWT signing key to revoke 1 role | Wide blast radius and cache issues | Per-user version/`jti` denylist |

---

## 19. Self-assessment questions

### Question 1. Active session after role removal

Alice's session holds `ROLE_MANAGER`; an admin deletes that role in the database. If code checks only authorities already inside `SecurityContext`, what can happen?

**Answer:** Alice may still be treated as a manager until `Authentication`/session is refreshed/invalidated or current policy is checked.

### Question 2. JWT has `SCOPE_reports:read`, yet admin revoked access

The token is unexpired and validly signed. Is `hasAuthority("SCOPE_reports:read")` alone enough?

**Answer:** No, if revocation must take effect before token expiry. You need versioning, a denylist, introspection, or current policy checks.

### Question 3. Revoking a refresh token

A client revokes RT while AT1 is still unexpired. Will an offline JWT decoder automatically reject AT1?

**Answer:** Not by default. You need an access-token revocation mechanism enforced by the Resource Server.

### Question 4. An opaque token returns `active=false`

Introspection returns `active=false`; should the Resource Server build a granted `Authentication`?

**Answer:** No. Inactive tokens must be rejected.

### Question 5. `active=true` while permissions changed

Does `active=true` mean all actions from the old scopes are still allowed?

**Answer:** No. `active` only indicates the AS considers the token active per contract; you still need action scope, current grants, tenant, and resource policies.

### Question 6. Version comparison after regrant

Token v1 had READ, was revoked to v2, then re-granted to v3. Can v1 still be used?

**Answer:** No under strict `authzVersion` design: `1 != 3`. A new token/session is required.

### Question 7. `jti` denylist

Why retain denylist entries until at least `expiry + skew`?

**Answer:** A revoked token may remain unexpired; expiring the denylist entry too early allows the token to be accepted again.

### Question 8. `SessionRegistry.expireNow()`

Does calling `expireNow()` guarantee every running request is immediately aborted?

**Answer:** No. It marks the session expired; filters, request lifecycles, and multi-node consistency must still be designed.

### Question 9. Should JWT scopes determine the tenant?

Does JWT scope `reports:read` prove the user belongs to T2?

**Answer:** No. Tenant membership must come from a trusted source or verified claims checked against policy; resources also need tenant scoping.

### Question 10. Why test the old token after regrant?

**Answer:** To catch designs that check only current permissions, which would inadvertently let an old JWT come back to life once READ is granted again.

### Question 11. Policy service timeout

Can delete operations be allowed because "the policy system is down"?

**Answer:** No when policy requires fail-closed. The system must deny/abort the mutation or follow an explicitly SLA-approved offline policy.

### Question 12. Document owner changes between authorization and UPDATE

JWT has the right scope and user version is current. Do you still need to re-check?

**Answer:** Yes. Token/user versions do not replace current resource/ACL/owner checks and transaction guards.

### Question 13. Wrong audience

A JWT is signed by a trusted issuer, yet `aud` targets another API. Should its `scope` be trusted?

**Answer:** No. The decoder must validate the Resource Server's audience before issuing an `Authentication`.

### Question 14. Single-device logout

Alice logs out on browser A while browser B and a CLI still hold tokens/sessions. Are they logged out automatically?

**Answer:** Not by default. Implement a "logout everywhere" protocol across sessions, token families, and the IdP if required.

### Question 15. Where does `authzVersion` come from?

Does Spring Security require every JWT to carry `authz_ver`?

**Answer:** No. It is an application-designed claim that the Authorization Server must emit from a trusted policy version and the Resource Server must validate under the same contract.

### Question 16. Does lowering JWT TTL alone meet a 1-second revocation SLA?

**Answer:** No if the token TTL exceeds 1 second; you need current-state checks or token revocation propagation within the SLA.

---

## 20. Implementation and operations checklist

### Authentication / token validity

- [ ] Accept tokens only from trusted issuers.
- [ ] Verify signature/key/algorithm, `exp`, `nbf`, `iss`, and `aud`.
- [ ] Never use ID tokens in place of OAuth2 access tokens.
- [ ] Never trust claims read from payloads before verification.
- [ ] Distinguish user tokens from client-credentials/machine tokens.
- [ ] Maintain a JWK rotation and incident response plan.

### Current grants / revocation

- [ ] Identify the authoritative source for roles/scopes/ACLs.
- [ ] Define permission revocation SLAs per action category.
- [ ] Understand session `Authentication` snapshots and refresh/invalidation mechanisms.
- [ ] For JWTs, pick TTL, `authzVersion`, denylist, or introspection based on risk.
- [ ] For opaque tokens, verify introspection semantics, cache TTL, and outage behavior.
- [ ] Coordinate refresh-token revocation with access-token revocation where needed.
- [ ] Make grant changes and version bumps atomic.
- [ ] Implement invalidation events/retries/reconciliation and multi-node tests.
- [ ] Fail closed when current permissions cannot be verified for sensitive actions.

### Data authorization

- [ ] Treat scopes/roles solely as coarse-grained gates.
- [ ] Source tenant membership and account enabled state from trusted stores.
- [ ] Include appropriate tenant/owner/resource policies in repository queries.
- [ ] Guard state/version in DML to prevent TOCTOU.
- [ ] Define transaction/locking consistency when grants change concurrently.
- [ ] Never share authZ cache entries across users or tenants.

### Tests and observability

- [ ] Test ALLOW before revocation and DENY with the exact same token/session after revocation.
- [ ] Test that old tokens stay DENIED after regrant when using strict versioning.
- [ ] Test that new tokens with the current version ALLOW.
- [ ] Test 401/403/404 behavior per contract.
- [ ] Test invalid JWT signatures/issuers/audiences/expiries through a real decoder.
- [ ] Test session logout, multi-device, and Spring Session multi-node behavior.
- [ ] Test introspection `active=false`, timeouts, and stale caches.
- [ ] Test that policy store outages never fail open.
- [ ] Audit actor, action, resource, current version, token version, revoke time, decision, and mutation outcome.
- [ ] Never log bearer tokens, refresh tokens, passwords, or credentials.

---

## 21. Official references

1. [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, session persistence, explicit save, and session management.
2. [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): `SecurityContextLogoutHandler`, HTTP session invalidation, clearing context, and CSRF logout.
3. [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContextHolder`, and `GrantedAuthority`.
4. [Spring Security 6.5 – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT verification, issuer/expiry validation, and scope authority mapping.
5. [Spring Security 6.5 – OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection, `active`, and scope mapping.
6. [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, protecting services.
7. [Spring Security – Session Registry API](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/session/SessionRegistry.html): looking up sessions by principal.
8. [Spring Session – Reference](https://docs.spring.io/spring-session/reference/): distributed session repositories and finding sessions by principal.
9. [Spring Security – Testing OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `MockMvc`, JWT test helpers, and authorities.
10. [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation protocol and token families.
11. [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, metadata, and introspection caching.
12. [RFC 7519 – JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `exp`, `iat`, `jti`, and signature-related token structure.
13. [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims and validation in access tokens.
14. [OAuth 2.0 Security Best Current Practice – RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): refresh token security, rotation, and OAuth threat models.
15. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and object-level checks.

**Conclusion:** When permissions change while a session or OAuth2 access token is still valid, never assume the change automatically appears inside an old `Authentication` or JWT. Sessions must be refreshed/invalidated or paired with live-grant checks; JWTs require policies for TTL, revocation, denylists, introspection, or `authzVersion`; refresh token rotation does not automatically revoke already-issued access tokens. Most importantly, the Resource Server must distinguish a **valid token** from **current permissions**, combining scopes with trusted user/tenant/ACLs and protecting DB mutations via transactions/conditional updates. Test with the exact same old token before and after revocation, after regrant, and across multiple nodes to prove your revocation SLA is genuinely met.