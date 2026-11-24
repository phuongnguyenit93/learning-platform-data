# Revoking Sessions, Remember-Me, or Related Tokens After a Password Change

> **Context:** Spring Security – authentication, **Password Upgrades** group. This lesson explains how to invalidate previously issued login credentials after changing or resetting a password: HTTP sessions, remember-me cookies, refresh tokens, and access tokens. It focuses on real Spring Security/Spring Session behavior, multi-device revocation policies, multi-server consistency, and test scenarios. The standalone runnable example uses **Java 17+** to verify revocation logic; Spring integration snippets clearly note their dependencies.

## 1. Changing a Password Does Not Automatically Log Out All Devices

Suppose An's account is logged in from three places:

- Laptop A holds a `JSESSIONID` pointing to an HTTP session.
- Phone B uses a remember-me cookie to auto-login when its session expires.
- Mobile app C holds an access token and a refresh token.

An discovers the password may have leaked and changes it from laptop A. The database writes **the new password hash**. That is necessary, yet insufficient to guarantee B and C lose access.

**Why?** After the initial login, the system normally relies on **secondary credentials** to identify subsequent requests: session IDs, remember-me tokens, refresh tokens, access tokens, or API keys. They have different lifecycles and storage locations from the password hash.

```text
Old password --(valid login)--> Secondary credential
                                     |
            +------------------------+------------------------+
            |                        |                        |
         HTTP session          Remember-me cookie       OAuth2/OIDC token
            |                        |                        |
    SecurityContext in          TokenBased /          Access token / refresh
    session store              PersistentToken        token / authorization
            |                        |                        |
            +------------------------+------------------------+
                                     |
                         Password change in DB
                                     |
                    Are old credentials rejected?
                  -> Only if the corresponding mechanism checks
                     or the revocation workflow actually ran.
```

One application may allow keeping the current session after a successful password change; another chooses to **log out all devices**. That is a product/security decision. However, if a password change follows suspected compromise, a forgot-password reset, or an admin-forced reset, strong policy usually requires revoking related access grants rather than merely blocking future logins with the old password.

**Article scope:** covers **credential changes initiated by the user or a verified security process**. Automatically rehashing a password from an old BCrypt cost to a new cost via `upgradeEncoding` **does not mean the user changed their password**; normally you should not log out every device over a technical hash upgrade.

## 2. Classify Credentials Before Choosing a Revocation Mechanism

| Mechanism | What does the client hold? | What does the server check on next use? | Typical revocation approach |
| --- | --- | --- | --- |
| HTTP session | Session ID in cookie | Session still exists and holds a valid `SecurityContext` | Delete/invalidate session; or check account security version |
| Token-based remember-me | Cookie carrying data and signature | Signature built from username, expiry, `UserDetails` password, and secret key | Changing password hash invalidates old signature once reloaded; clear current cookie |
| Persistent remember-me | Cookie containing series/token | Token record in `PersistentTokenRepository` | `removeUserTokens(username)` to delete user's tokens; clear cookie on current client |
| JWT access token | Self-contained signed token | Signature, issuer, audience, expiry, policy | Short TTL; `jti` denylist, account security version/epoch, introspection, or gateway policy |
| Opaque access token | Reference token | Token store/introspection | Revoke or mark inactive in authorization/token store |
| Refresh token | Refresh credential | Token store, rotation, token family | Revoke refresh token or entire token family/authorization |
| Dedicated API key | App-issued key | API key repository | Revoke/rotate key via dedicated policy |
| SSO/IdP session | Cookie or token at identity provider | Identity Provider's session policy | Coordinate logout/revocation with IdP; local logout does not log out IdP automatically |

**Revocation** comes in two forms to distinguish: **physical** (deleting token/session records) and **logical** (keeping records while rejecting requests because the account version or timestamp is no longer valid). Both can be combined for fast enforcement followed by cleanup.

### Do Not Confuse Token Types

A refresh token is not an access token; deleting a refresh token **stops new access tokens from being issued**, yet already-issued access tokens may stay valid until expiry. An OIDC ID token carries user login claims and is not automatically a bearer credential for calling APIs. A remember-me cookie differs from a session cookie, even when a client holds both.

### Revocation Is a Verifiable Requirement

Do not just write "logout succeeded". Specify:

- **Which credential types** must be invalidated?
- Revoke **all devices** or **only other devices**?
- **When** access stops: immediately after password-change commit, on the next request, or after TTL?
- Do multi-node services observe the same revocation state?
- How are **in-flight** requests at the time of password change handled?
- Should a fresh session/token be issued with the new password or must the user log in again?
- If token deletion hits a network error, does the system still enforce the policy?

These questions form a security contract and should not be left to implicit framework defaults.

## 3. Two Credential-Change Categories and Default Policies

Not every hash change carries the same meaning.

### 3.1. User-Initiated Password Change While Logged In

An authenticated user provides the old password or an equivalent strong verification step and picks a new password. The system may apply:

- **A – Revoke all, including current device:** easy to reason about, ideal when strong protection is desired. Require re-login after success.
- **B – Revoke other devices, keep current device:** more convenient, yet requires verifying the current request, rotating/renewing the current session cleanly, and avoiding re-authorizing via stale cookies.
- **C – Revoke only selected tokens:** appropriate only when threat model and product contract state it explicitly; avoid by accidental default.

### 3.2. Password Reset or Change Due to Suspected Compromise

When a user goes through forgot-password recovery, an admin forces a reset, or an investigation indicates exposure, assess the risk higher. You normally must **revoke all sessions, remember-me tokens, and refresh tokens belonging to the user**, paired with a policy to reject old access tokens promptly.

Password resets require proving ownership through an appropriate channel. **Never** allow a password-reset token to act as an access token for general API calls, and never leave reset tokens replayable after use.

### 3.3. Automatic Rehash on Login

`DaoAuthenticationProvider` can use `PasswordEncoder.upgradeEncoding` and `UserDetailsPasswordService` to store hashes with updated parameters. When **the raw password did not change**, it is a storage upgrade, not necessarily a logout event. If you wire a listener that "revokes sessions on any `password_hash` column change", separate **PASSWORD_CHANGED** from **PASSWORD_HASH_UPGRADED** events; otherwise, every BCrypt cost bump could unexpectedly log out masses of users.

## 4. Standard Workflow After Verifying the New Password

A safe password-change flow should follow explicit ordering and boundaries:

```text
POST /account/change-password (CSRF-protected if using sessions)
       |
       v
Verify caller + required re-authentication step
       |
       v
Check new password policy, password history/risk (if any)
       |
       v
PasswordEncoder.encode(newRawPassword)
       |
       v
Authoritative TRANSACTION:
  - ensure account and credential version still match
  - update password_hash
  - increment security_epoch / credential_version
  - invalidate tokens/resets/refreshes from same source if in same DB
  - write audit/outbox event to clean up external systems
COMMIT
       |
       v
Revoke sessions/remember-me/refresh tokens in related stores
       |
       v
Clear SecurityContext and cookies of current request if policy is logout-all
       |
       v
Return result: require re-login
```

**Important note:** if deleting sessions/refresh tokens spans a separate store or service, all actions cannot sit inside a single SQL transaction. When requiring "immediately after commit, old credentials must no longer work", a strong design uses **security epoch / credential version as an authoritative check** on the access path, while physical cleanup via events/outbox completes asynchronously. Without that check—relying solely on async workers—you must accept and document a **revocation lag window** rather than claiming instant revocation.

### Do Not Ignore Requests That Already Passed Authorization

An in-flight request already accepted by Spring Security **before** the password change can keep running unless business services re-check the security version. When business actions demand strict revocation—such as money transfers or admin permission edits—enforce checks right at transaction execution. No "delete all sessions" call can undo mutations already committed by an earlier request.

## 5. Revoking the Current HTTP Session

Spring Security Servlet normally saves `SecurityContext` in the HTTP session after form login. The `JSESSIONID` cookie is merely **a reference key to the session**; deleting the cookie in the browser does not ensure the server deleted the session record.

Once the user finishes changing their password and policy requires logging out the current device, invoke `SecurityContextLogoutHandler` to invalidate the current session and clear authentication/context. In standard logout flows, Spring Security also runs handlers for remember-me, CSRF, and events.

Below is an **integration snippet** inside an MVC controller with `request`, `response`, `authentication`, and a password-change service that already committed safely:

```java
SecurityContextLogoutHandler logout =
        new SecurityContextLogoutHandler();

logout.logout(request, response, authentication);
```

Import `org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler`, request/response types from `jakarta.servlet.http`, and `Authentication`. Call this **after** the password change commits successfully; calling it before a failing password-change transaction can log out the user needlessly and produce confusing errors.

### Why Use Spring Security's Logout Components?

`HttpSession.invalidate()` only invalidates a servlet session. `SecurityContextLogoutHandler` also clears `SecurityContextHolder` and `SecurityContextRepository` as configured. With Spring Security 6/7, pay attention to explicit context saving/clearing, especially if the app uses a custom security context repository.

When remember-me cookies exist, calling `SecurityContextLogoutHandler` alone **is not enough** to guarantee all remember-me cookies/tokens are cleared. Spring Security's standard logout chain invokes remember-me handlers; in a custom controller invoking logout handlers manually, invoke the appropriate additional handlers too.

### Prefer Configured Logout URLs When Possible

Spring Security offers `POST /logout` with CSRF protection and a `LogoutHandler` chain. A specialized password change sometimes needs its own endpoint, yet should not omit the logout chain's cleanup steps.

A valid configuration fragment inside `HttpSecurity`, if returning an HTTP status instead of redirecting:

```java
.logout(logout -> logout
        .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler()))
```

This is **not** a complete `SecurityFilterChain`; import `HttpStatusReturningLogoutSuccessHandler` from `org.springframework.security.web.authentication.logout`. Always perform logout over HTTP POST with proper CSRF tokens; state-mutating GETs are risky.

### Clearing Cookies Does Not Equal Server-Side Deletion

`JSESSIONID` cookies normally carry `HttpOnly` and `Secure` over HTTPS. On logout, the app can send an expired `Set-Cookie`, though cookie paths/domains and container/proxy behavior must be verified. Leftover client cookies may trigger "invalid session" requests, yet **access control must rely on server state**, never on trusting that the browser deleted the cookie.

## 6. Revoking Every HTTP Session of an Account

This differs from logging out the current request. `SecurityContextLogoutHandler.logout(...)` only handles the session bound to **the current request**. It has no awareness of sessions on phones or other browsers.

Two common approaches exist.

### 6.1. Spring Session and Principal-Indexed Repositories

If the app uses Spring Session Redis/JDBC and the implementation supports `FindByIndexNameSessionRepository`, you can look up sessions by principal and delete each record:

```java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
class AccountSessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session>
            sessions;

    AccountSessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    void revokeAllForPrincipal(String principalName) {
        var found = sessions.findByPrincipalName(principalName);

        for (String sessionId : found.keySet()) {
            sessions.deleteById(sessionId);
        }
    }
}
```

This is an **integratable Java class** once a Spring Session indexed repository is configured; it is not standalone because it requires Spring Session with Redis or JDBC backing storage. `findByPrincipalName` relies on the **principal index** written for sessions. If the app uses custom principals, multi-tenancy, or unindexed sessions, sessions may be missed. In production, use an **immutable account ID** and matching index to avoid username renames or cross-tenant collisions; the username lookup here illustrates the default API.

`deleteById` removes the session record from the store. Clients presenting old cookies will fail to retrieve that session on their next request. Across multiple nodes sharing a repository, this beats per-node in-memory session maps. Test consistency lag, caches, and in-flight requests.

### 6.2. SessionRegistry / ConcurrentSessionFilter

When concurrent session management is enabled, Spring Security tracks sessions via `SessionRegistry`. Registered sessions can be marked expired:

```java
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
```

This **snippet** requires `SessionRegistry`, `SessionInformation`, a `principal` matching the registry's key, and session registration/listeners. `expireNow()` typically **marks** the session expired; `ConcurrentSessionFilter` or related components detect and enforce it on the next request. Do not describe it as "instantly deleting every session physically across all nodes". An in-memory registry also does not sync across servers automatically.

**Common pitfall:** if a custom `UserDetails` lacks stable `equals()/hashCode()`, or some authentication mechanisms fail to register sessions with the registry, the returned list may be incomplete. When using Spring Session repositories, choose one clear source of truth for session coordination instead of assuming registries know about each other.

### 6.3. Session Version/Epoch as a Defense Layer

Alongside physical deletion, store:

```text
accounts:
  account_id
  password_hash
  security_epoch       BIGINT
```

On password login, the principal/session captures `securityEpochAtAuthentication`. After a valid password change, the transaction increments `security_epoch`. On every authenticated request, a filter/policy compares the session's epoch against the authoritative current epoch.

```text
sessionEpoch == account.securityEpoch  -> may proceed
sessionEpoch != account.securityEpoch  -> reject, log out session
```

This rejects stale sessions even if a session-deletion job lags. However, **if epoch lookups use a cache with a long TTL**, a lag window still exists; if "immediate enforcement" is required, define consistency and fail-closed behavior when the version source is unavailable.

## 7. Remember-Me Comes in Two Types with Different Revocation

Remember-me lets users return authenticated without re-entering passwords on later visits. Spring Security supports two main styles: signed tokens derived from user info and repository-backed tokens. They are not identical.

### 7.1. TokenBasedRememberMeServices: Signature Tied to Password

In the token-based mechanism, the remember-me cookie carries username, expiry, algorithm name, and a signature computed from the current `UserDetails` password plus a secret key. Per Spring Security docs, when the password or key changes, old cookies fail signature verification.

Practical conditions for that to hold:

- On the next auto-login, `UserDetailsService` must load **the new password hash** from an authoritative source rather than an indefinitely stale cache.
- Remember-me secret keys must be securely managed and consistent across nodes.
- Old cookies are rejected at the next auto-login; any **already-issued HTTP session** still needs separate revocation.
- Password hash changes from **technical rehashing** can also invalidate remember-me signatures built from the old hash. Test this side effect when enabling automatic hash upgrades.

There is no way to "delete one specific cookie in browser B" from the server if token-based mode lacks a series-keyed token store. Changing the password/hash or rotating the key invalidates signatures across its scope; with one shared key, rotating the key invalidates remember-me cookies for **all users**.

### 7.2. PersistentTokenBasedRememberMeServices: Server-Side Token Records

With persistent remember-me, cookies carry series/token pairs while the server queries `PersistentTokenRepository`. **Changing the password hash does not automatically delete persistent token records**. If policy requires revoking all remember-me tokens after a password change, delete them explicitly.

Official API:

```java
persistentTokenRepository.removeUserTokens(username);
```

This is an **integration snippet**, with a bean of type `org.springframework.security.web.authentication.rememberme.PersistentTokenRepository` and `username` from the verified identity. `removeUserTokens(String username)` revokes the user's persistent login tokens per the repository contract.

Once deleted, cookies left on other devices cannot authenticate without matching records. Still, **the cookie on the current device** should also be cleared via logout/remember-me handlers and response headers so the client stops sending dead tokens. Deleting remember-me tokens **does not automatically delete** existing sessions.

### Example Persistent Remember-Me Table

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

This is a reference schema from documentation, not a mandatory schema for every app. For mutable usernames, multi-tenancy, auditing, or hashed-at-rest tokens, design an appropriate repository/domain schema. Never put raw persistent tokens into logs, analytics, or support tickets.

### Should Remember-Me Be Enabled for Every App?

Applications handling sensitive data may omit remember-me altogether or require re-authentication for critical actions. Remember-me extends login lifetime and widens cookie-theft exposure; it is not a mandatory Spring Security feature.

## 8. JWT Access Tokens: Changing the Password Does Not Erase the Signature

JWT access tokens are normally signed, self-contained objects carrying claims like `sub`, `iss`, `aud`, `iat`, `exp`, and `jti`. Resource servers can verify signatures and expiry **without querying the accounts database**. Therefore:

> If a JWT was issued before the password change and has not expired yet, updating the password hash in the DB **does not automatically make the JWT fail signature verification**.

Ways to limit exposure:

1. **Short access token TTL:** shrinks the window where old tokens remain usable, though it does not deliver instant revocation.
2. **Denylist by `jti`:** store revoked token IDs until `exp`, checked at the resource server. Requires a datastore/TTL, anti-stale-cache rules, and a fail-closed policy.
3. **Account security epoch / credential version:** the issuer embeds the version in a signed claim; resource servers compare it to the account's current version. Tokens with an old version are rejected even if signature/expiry remain valid.
4. **`valid_after`/`tokensValidAfter` timestamp:** reject tokens issued before that timestamp. Mind `iat` resolution (often seconds), clock skew, and tokens minted mid-change.
5. **Opaque tokens or introspection:** the server can mark tokens inactive; resource servers must actually introspect or cache with an appropriate TTL.
6. **Gateway/policy service:** enforces revocation centrally, though every path to protected resources must traverse the same policy.

**Never read `sub` or `credential_version` from an unverified JWT.** Decoders must verify signature, issuer, audience, and expiry per the token contract. Claims are trustworthy only after valid authentication processing. Version lookups must bind the right issuer/account/tenant to prevent identity collisions.

### Why Not Rely Only on `jti` When Needing "Revoke All"?

If a user had hundreds of JWTs issued and the system did not record every `jti`, listing all tokens for a denylist is hard. Account-scoped security epochs let logic reject every token from older epochs without enumerating individual tokens. Conversely, a `jti` denylist excels when revoking **one specific token**.

### Requests Reaching a Resource Server Before Epoch Changes

Even when resource servers check security epochs per request, a request admitted before the password change may already be inside a business service. Where strict limits matter, re-check version/risk at the sensitive operation's boundary; never promise that changing a password reverses already-committed transactions.

## 9. Refresh Tokens and Token Families: Must Be Revoked Separately

Refresh tokens are used to obtain new access tokens. When changing a password due to suspected credential compromise, if a refresh token stays active, an old client can still mint new access tokens without knowing the current password.

Thus, a logout-all policy normally needs:

- Revoking the user's refresh tokens in the authoritative authorization/token store.
- Revoking the **token family** when refresh-token rotation is used and replay/risk is detected.
- Preventing new tokens from being minted from invalidated old grants/cookies/sessions.
- Defining handling for already-issued access tokens: wait for TTL, denylist, or version check.
- In multi-client/multi-tenant systems, scoping revocation strictly to the target user/context so other clients are not accidentally revoked.

Spring Authorization Server uses `OAuth2AuthorizationService` to store/query authorizations and tokens per protocol. It **does not provide one magic command guaranteeing "changing this username's password deletes every authorization across every system"**. You must model user–client–authorization relationships in storage, query the right records, and define revocation and resource-server enforcement policies.

If tokens are issued by an **external Identity Provider**, your app does not own their refresh-token store. Use the provider's supported revocation/logout endpoints within authorized scopes. Never assume revocation succeeded unless the provider confirms it.

### Refresh Rotation Does Not Replace Password-Change Revocation

Rotation issues a new refresh token on each use, reducing reuse of stolen old tokens. Still, a currently valid token family can keep minting access tokens after a password change unless the issuer binds grants to credential-change events. Policy must terminate the family or force re-authentication.

## 10. OAuth2 Login and OIDC: Local Logout Differs from IdP Logout

In Spring Security `oauth2Login`, a user may hold a **local HTTP session** containing the login result. The Identity Provider also maintains its own session/cookie or refresh tokens.

- **Local logout:** clears the application's session, `SecurityContext`, and cookies.
- **RP-Initiated Logout / provider logout:** asks the IdP to end its session per protocol and provider support.
- **Back-channel / front-channel logout:** mechanisms allowing the IdP to notify participating sessions if supported and configured.
- **Refresh token revocation:** asks the issuer's token store to invalidate re-issuance credentials.

**Changing a password at the IdP does not automatically clear every Relying Party's local session**, unless IdP and RPs coordinate a trusted, tested mechanism. Likewise, local logout may not log out the IdP; the user could auto-login again via a still-valid SSO cookie.

For multi-application suites, define the authoritative source emitting password-change events, a shared account identifier, revocation propagation, and maximum acceptable lag.

## 11. Security Epoch / `credentialVersion`: Account-Wide Logical Revocation

A useful pattern is a monotonically increasing field tied to security events:

```text
accounts
--------
id                  UUID
password_hash       VARCHAR
security_epoch      BIGINT
enabled             BOOLEAN
...

session/token
-------------
account_id          UUID
epoch_at_issue      BIGINT
issued_at           timestamp
...
```

On a valid password change/reset, within the same transaction updating the hash, increment `security_epoch` from 6 to 7. Previously issued sessions/tokens carry epoch 6. When requests use them:

```text
verify signature/session integrity
             |
             v
resolve trusted account ID
             |
             v
read current security_epoch from authoritative source
             |
             +-- equal: continue authorization
             |
             +-- different: reject + clear local context/token
```

**Never accept account IDs and epochs from self-declared request parameters to make decisions.** A token's epoch must come from a verified signed claim or server-side session metadata; the ID must bind to the actual principal.

### Why Use a Version Instead of Timestamps Alone?

Some tokens use second-precision `iat`, meaning two close events share the same second, and clocks skew across machines. Atomically incremented per-account versions express "newer credential" without direct clock dependence. Still, security epochs require resource servers to query the current version or a sufficiently fresh cache.

### States After Changing a Password

Some policies separate multiple versions:

- `credential_version` increments when passwords/keys change.
- `session_revoked_before` or `security_epoch` increments when the user chooses logout-all.
- `role_version` increments when authorities are revoked, if immediate privilege revocation is needed.
- `mfa_version` or `reauth_at` supports step-up authentication.

You do not need every field from day one. Pick a minimal model with a clear contract, and avoid bumping all versions during background migrations that only rehash the same plaintext, which could cause unintended logouts.

## 12. Runnable Java 17+ Example: Revoking Old Sessions, Remember-Me, Refresh Tokens, and JWTs

To focus on **revocation semantics**, this example uses **plain Java without Spring**. It is **not a real authentication system**: it does not hash passwords, sign JWTs, or emit network cookies. It simulates issued grants and an `afterVerifiedPasswordChange` step called **only after** the password service verifies and commits the change. The goal is to prove that once the version increments and token records are removed, old credentials are rejected—even when an old JWT would still pass stateless signature/expiry checks.

Create **`RevocationModelDemo.java`**:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class RevocationModelDemo {

    record Grant(String userId, long securityEpoch) {}

    record SimulatedJwt(
            String userId,
            long securityEpoch,
            Instant expiresAt) {}

    static final class Store {
        private final Map<String, Long> epochs = new HashMap<>();
        private final Map<String, Grant> sessions = new HashMap<>();
        private final Map<String, Grant> rememberMe = new HashMap<>();
        private final Map<String, Grant> refreshTokens = new HashMap<>();

        synchronized long currentEpoch(String userId) {
            return epochs.getOrDefault(userId, 0L);
        }

        synchronized void issueSession(String id, String userId) {
            sessions.put(id, new Grant(userId, currentEpoch(userId)));
        }

        synchronized void issueRememberMe(String id, String userId) {
            rememberMe.put(id, new Grant(userId, currentEpoch(userId)));
        }

        synchronized void issueRefresh(String id, String userId) {
            refreshTokens.put(id,
                    new Grant(userId, currentEpoch(userId)));
        }

        synchronized SimulatedJwt issueJwt(
                String userId, Instant expiration) {
            return new SimulatedJwt(
                    userId, currentEpoch(userId), expiration);
        }

        private boolean validGrant(
                Map<String, Grant> store, String id) {
            Grant grant = store.get(id);
            return grant != null
                    && grant.securityEpoch()
                            == currentEpoch(grant.userId());
        }

        synchronized boolean sessionValid(String id) {
            return validGrant(sessions, id);
        }

        synchronized boolean rememberMeValid(String id) {
            return validGrant(rememberMe, id);
        }

        synchronized boolean refreshValid(String id) {
            return validGrant(refreshTokens, id);
        }

        synchronized boolean jwtAllowed(
                SimulatedJwt token,
                boolean signatureAlreadyVerified,
                Instant now) {

            return signatureAlreadyVerified
                    && now.isBefore(token.expiresAt())
                    && token.securityEpoch()
                            == currentEpoch(token.userId());
        }

        // Call ONLY AFTER the credential change is verified and
        // committed. Never accept revocation commands from untrusted public input.
        synchronized void afterVerifiedPasswordChange(String userId) {
            long next = currentEpoch(userId) + 1;
            epochs.put(userId, next);

            sessions.values().removeIf(
                    grant -> grant.userId().equals(userId));
            rememberMe.values().removeIf(
                    grant -> grant.userId().equals(userId));
            refreshTokens.values().removeIf(
                    grant -> grant.userId().equals(userId));
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        String user = "account-17";
        Instant now = Instant.parse("2026-01-01T00:00:00Z");

        // Simulate a login ALREADY verified validly.
        store.issueSession("session-old", user);
        store.issueRememberMe("remember-old", user);
        store.issueRefresh("refresh-old", user);

        SimulatedJwt oldJwt =
                store.issueJwt(user, now.plusSeconds(3600));

        System.out.println("before-session="
                + store.sessionValid("session-old"));
        System.out.println("before-remember="
                + store.rememberMeValid("remember-old"));
        System.out.println("before-refresh="
                + store.refreshValid("refresh-old"));
        System.out.println("before-jwt="
                + store.jwtAllowed(oldJwt, true, now));

        // Mandatory real-world order:
        // verify change permission -> write new password -> commit -> revoke.
        store.afterVerifiedPasswordChange(user);

        System.out.println("after-session="
                + store.sessionValid("session-old"));
        System.out.println("after-remember="
                + store.rememberMeValid("remember-old"));
        System.out.println("after-refresh="
                + store.refreshValid("refresh-old"));

        // Old JWT in the demo is not expired yet, and assumes
        // signature already verified. The new epoch rejects the request.
        System.out.println("old-jwt-still-not-expired="
                + now.isBefore(oldJwt.expiresAt()));
        System.out.println("after-jwt-with-epoch-check="
                + store.jwtAllowed(oldJwt, true, now));

        // Simulate user re-authenticating with VALID NEW credentials.
        store.issueSession("session-new", user);
        SimulatedJwt newJwt =
                store.issueJwt(user, now.plusSeconds(3600));

        System.out.println("new-session="
                + store.sessionValid("session-new"));
        System.out.println("new-jwt="
                + store.jwtAllowed(newJwt, true, now));
    }
}
```

### Running with Real javac/java

With JDK 17+ and the file named `RevocationModelDemo.java`:

```bash
javac RevocationModelDemo.java
java RevocationModelDemo
```

**Exact stdout of the example:**

```text
before-session=true
before-remember=true
before-refresh=true
before-jwt=true
after-session=false
after-remember=false
after-refresh=false
old-jwt-still-not-expired=true
after-jwt-with-epoch-check=false
new-session=true
new-jwt=true
```

No randomness or system clock appears in the logic; the timestamp is fixed so the output is deterministic.

### Lessons from the Output

- Old sessions, remember-me tokens, and refresh tokens are removed from server-side stores.
- The old JWT is **not yet expired**, yet is rejected **when** the resource server checks the epoch after verifying the token.
- Re-authenticated users receive new sessions/JWTs carrying the new epoch.
- Keeping `signatureAlreadyVerified=true` in the demo only simulates signature verification by a real JWT decoder. **Never replace real signature verification with a client-supplied boolean.**
- `synchronized` and `HashMap` suffice only for single-JVM illustration. Production requires authoritative stores, transactions, distributed caches, plus password authentication, token hashing, expiry, cryptographic signing/verification, and auditing. Strings like `session-old` are not real secret credentials.

## 13. Mapping the Example to Spring Security Architecture

In a real application, each responsibility belongs in the right component:

| Component | Responsibility |
| --- | --- |
| `PasswordChangeService` | Verifies change eligibility, old password/re-auth, new policy; encodes and commits |
| `AccountRepository` | Stores password hash and security epoch keyed by account ID |
| `SecurityContextLogoutHandler` | Logs out current session and clears authentication/context |
| `FindByIndexNameSessionRepository` | Finds/deletes old sessions in indexed Spring Session stores |
| `PersistentTokenRepository` | Deletes user's persistent remember-me tokens |
| `RefreshTokenService` or issuer store | Revokes refresh tokens / token families |
| `AccessTokenRevocationPolicy` | Checks `jti`/epoch/introspection for access tokens |
| `SecurityEpochAuthorizationFilter` or domain policy | Compares verified principal/token epoch against authoritative source |
| Audit/outbox | Records events and coordinates cleanup across multiple services |

An integration sequence in **sketch code** (not a standalone Java file; services are app-defined abstractions):

```java
PasswordChangeResult result = passwordChangeService
        .changePasswordAndAdvanceEpoch(
                trustedAccountId, oldRawPassword, newRawPassword);

// Transaction updating hash + epoch committed successfully.
// Cleanups below need retries/idempotency if stored elsewhere:
sessionRevoker.revokeAll(result.accountId());
rememberMeRevoker.revokeAll(result.accountId());
refreshTokenRevoker.revokeAll(result.accountId());

securityContextLogoutHandler.logout(
        request, response, authentication);
```

**Never turn this into a promise of cross-service atomicity:** after the epoch commits, network failures can hit physical session/token deletions. If resource servers and session filters check the authoritative epoch, old credentials are still logically rejected. Without that gate, define clear failure handling (outbox, retries, alerts, lag limits, fail-closed for high-risk actions).

### The "Keep Current Session" Case

If policy keeps the device performing the password change, issue **the new security version solely to that strongly verified session** while invalidating all others. Never bump the epoch of every existing session in the store; that would revive sessions meant to be revoked. Evaluate rotating session IDs, updating `SecurityContext` and CSRF tokens after re-authentication, session authorities, and step-up checks for sensitive tasks.

### Never Leave the Password-Change Endpoint Without CSRF Protection

Form-login + session/cookie apps normally need CSRF tokens on password-change POST endpoints. Having an authenticated session **does not stop** CSRF if browsers send cookies automatically. Keep Spring Security's CSRF protection enabled properly; never disable it globally just because API tests lack tokens.

For email-based password resets, reset tokens must be verified, time-limited, and single-use. Never let a reset request specify an arbitrary account ID or token version to revoke someone else's access.

## 14. When Using Session Versions, Where Does the Filter Go?

With `SecurityContext`-based flows, an epoch-checking filter must run **after** the authentication mechanism restores/creates `Authentication` for the request and **before** controllers or authorization-sensitive business code execute.

Logic idea:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null
        && authentication.isAuthenticated()
        && authentication.getPrincipal() instanceof VersionedPrincipal p) {

    long currentEpoch =
            accountSecurityService.currentEpoch(p.accountId());

    if (p.securityEpochAtAuthentication() != currentEpoch) {
        securityContextLogoutHandler.logout(
                request, response, authentication);
        response.setStatus(401);
        return;
    }
}

filterChain.doFilter(request, response);
```

This is a **filter logic snippet**, not a complete `OncePerRequestFilter` class: `VersionedPrincipal`, `accountSecurityService`, request/response, `filterChain`, and imports must be implemented. Define an **explicit policy** for anonymous or other principal types; never skip token checks just because a principal does not implement a custom interface. When the epoch store suffers network failures, fail closed or guard sensitive paths rather than accepting every token by default.

**Filter placement matters greatly.** If placed before a remember-me filter that auto-creates `Authentication`, remember-me requests slip through unchecked. A sound design places the filter before `AuthorizationFilter` after relevant authentication filters, or embeds the check inside a custom `AuthorizationManager`/policy. Verify the actual filter order via test frameworks rather than inferring it from source file placement.

Also ensure a user who changed their password cannot mint **a new session from the old password** via a race between verification and session issuance. Principals/tokens must carry the epoch observed **during authentication**, rather than reading a newer epoch afterward and stamping it onto a login verified against the old hash. If the account store changes mid-login, authentication must verify consistency or reject.

## 15. Consistency and Ordering Across Multiple Participating Systems

A multi-node application may use:

- RDBMS holding password hashes and security epochs.
- Redis/Spring Session holding HTTP sessions.
- Separate database holding persistent remember-me tokens.
- Authorization server holding refresh tokens.
- Resource servers verifying JWTs with public keys.
- Queue/outbox publishing `PASSWORD_CHANGED` events.

If the password change commits in the DB while the queue/outbox lags, session/token cleanup may lag behind. Pick a model:

**Model A — Synchronous physical revocation:** every token/session store must confirm deletion before returning success. Hard to keep atomic across systems; timeouts/retries can delay responses or fail partially.

**Model B — Authoritative epoch + asynchronous cleanup:** commit hash + epoch in one transaction; protected requests enforce the epoch with suitable consistency. Physical cleanup via outbox/events retries independently. Usually easier to prove access denial when every consumer enforces the gate.

**Model C — TTL and accepted revocation lag:** some access tokens remain usable until a short expiry; appropriate when product requirements permit. Document maximum lag explicitly and never advertise instant revocation.

### Revocation Event Protocol

An event might look like:

```json
{
  "type": "PASSWORD_CHANGED",
  "account_id": "account-17",
  "new_security_epoch": 7,
  "occurred_at": "2026-11-05T12:00:00Z",
  "event_id": "event-abcdef"
}
```

This is an **event sample**, not a mandatory schema. Never include raw passwords, password hashes, refresh tokens, or remember-me cookies. Consumers must verify trusted event origins, support retries/idempotency, and never let an event with a **lower epoch** downgrade account state. Illustrative timestamps do not replace authoritative versions.

### Handling Partial Failures

Suppose the password commit succeeds while deleting persistent tokens fails. Without an epoch gate on remember-me, cookies could keep authenticating. Therefore you need alerts, retries, and a fallback to close the risky path (e.g., token store returning inactive during state transitions) instead of silently claiming "logged out all devices".

If the credential change fails to commit, **never** publish a `PASSWORD_CHANGED` event as if it succeeded. A transactional outbox ties event recording to the same DB commit; external consumers must still handle at-least-once delivery and idempotency.

## 16. Test Suite That Proves Actual Loss of Access

Do not test only the password-change endpoint's HTTP status. Retain **cookies/tokens issued before the change** and replay them after commit.

| Test case | What to prove |
| --- | --- |
| Old password after change | New login attempts with old password are rejected |
| New password | Can log in under policy without reviving old tokens |
| Session on device A | Invalidated, or retained only if policy specifies |
| Session on device B | Cannot access protected resources after revocation |
| Session on another node | Repository/epoch checks reject consistently |
| Token-based remember-me | Old cookie cannot auto-login once hash changes and cache refreshes |
| Persistent remember-me | Token record deleted; old cookie creates no new session |
| Refresh token | Old token/family cannot mint new access tokens |
| JWT access token | Signature/exp may still be valid, yet rejected if policy demands epoch/denylist |
| Opaque access token | Introspection/token store reports inactive at request time |
| Valid access token with no revocation check | Must document TTL window; never claim instant revocation |
| SSO/IdP | Local logout and IdP logout/revocation tested as two distinct systems |
| Other accounts | Other users' sessions/tokens are **not** revoked |
| Technical rehash | Does not log out users unless policy treats rehash as credential change |
| Verified password reset | Revokes all per policy; reset token is single-use |
| Password change missing CSRF token | Request blocked when using session-based browser auth |
| Concurrent password changes | No lost updates; version increments consistently |
| Old login racing with password change | Never mints a session with the new epoch using the old password |
| Temporary revocation store outage | Retries, fails closed, and alerts per contract |
| Stale version cache | Never revives revoked sessions/tokens |
| Request started before revocation | Re-authorization checked inside sensitive transactions |

### Two-Real-Browsers Test

1. Open browser A, log in, and save session cookie A.
2. Open browser B or a separate profile, log in to the same account, and save cookie B.
3. If the app supports remember-me, enable it on B and retain that cookie after session B is cleared.
4. In A, change the password through the verified flow with logout-all policy selected.
5. Replay protected endpoints with cookies A and B, then attempt auto-login from the old remember-me cookie.
6. If OAuth2 is used, replay the old refresh token and old access token.
7. Log in again with the **new** password; reject the old password.
8. Inspect audit logs and metrics, not just the "Password changed successfully" UI message.

In session tests, avoid accidentally **re-logging in** via HTTP Basic on every request because Basic re-authenticates credentials; it does not simulate a long-lived session cookie. Form-login/session clients or Spring Security MockMvc tests fit better.

### Distinguish "401/403/Redirect" from Actual Access

Form login may redirect to `/login`, Basic APIs may return 401, token resource servers may return `invalid_token`/401, and authenticated users lacking authority receive 403. Verify that **the protected operation is denied**, rather than forcing every mechanism to share the exact same status/body. Never expose account names or sensitive token states on public endpoints.

## 17. Common Mistakes and Consequences

| Mistake | Risk | Fix |
| --- | --- | --- |
| Updating only `password_hash` | Old sessions/tokens keep access | Plan revocation for every related credential |
| Calling `HttpSession.invalidate()` and assuming all devices logged out | Affects only the current session | Spring Session / session registry / epoch |
| Deleting `JSESSIONID` cookie without deleting server session | Stolen cookies remain usable | Revoke server-side state |
| Deleting sessions while forgetting remember-me | Cookie can auto-login again | Revoke remember-me + clear cookie |
| Relying on hash change to clear persistent remember-me | Token records remain | `removeUserTokens` |
| Revoking refresh token and assuming old JWTs died | Issued JWTs stay valid until expiry | TTL / denylist / epoch |
| Doing only local logout with OIDC | IdP session may survive | Coordinate provider logout/revocation |
| Using in-memory `SessionRegistry` in a cluster | Misses sessions on other nodes | Indexed shared store / epoch |
| Using mutable username as long-term revocation key | Wrong scope on rename/multi-tenant | Immutable account ID and proper index |
| Placing epoch filter before remember-me/auth filters | Newly created tokens slip past | Verify filter ordering / policy |
| Stamping new epoch onto login verified with old password | Revives old login past revocation | Bind epoch to authentication snapshot |
| Caching epochs without TTL/invalidation | Delayed revocation | Define consistency model |
| Treating async cleanup as "instant" | Unauthorized access window | Authoritative gate or document lag |
| Bumping epoch on every BCrypt rehash | Unintended mass logouts | Separate security events by semantics |
| Omitting CSRF on session-based password-change endpoints | Cross-site password changes | Keep CSRF protection |
| Writing raw tokens/passwords into audit events | Secret leakage | Log minimal metadata |
| Exposing `GET /change-password` | Prone to unintended triggers | Use POST/PATCH + CSRF defenses |
| Forgetting single-use reset tokens | Password reset replay | Revoke upon consumption |
| Skipping multi-device tests | "Logout all" may be illusory | End-to-end integration tests |
| No fallback when token store fails | Partial logouts | Fail closed / retry / alert per policy |

## 18. Production Handoff Design Checklist

1. Clearly separate **password change** events from automatic **hash rehash** events.
2. Specify logout-current, logout-other-devices, or logout-all per event category.
3. Verify authorization and old password/MFA per risk; reset tokens have TTL and single-use enforcement.
4. Encode the new password with the active encoder; never store plaintext.
5. Update hash + security epoch atomically keyed by immutable account ID.
6. Handle concurrent changes/resets; prevent stale logins from minting new sessions with the new epoch.
7. If using Spring Session, verify principal index, shared repository, deletion/invalidation, and multi-node behavior.
8. If using `SessionRegistry`, verify session registrations, principal equality, and `ConcurrentSessionFilter`.
9. For remember-me, distinguish token-based vs. persistent; clear the right token records/cookies.
10. Revoke refresh tokens/token families and define handling for unexpired access tokens.
11. If using JWT version checks, validate issuer/audience/signature, read trusted epochs, and handle outages.
12. For OIDC/SSO, coordinate IdP logout/revocation beyond local sessions.
13. Never trust arbitrary user IDs, token IDs, or revocation scopes from unverified client inputs.
14. Maintain CSRF protection, cookie flags, HTTPS, and proper CORS policies.
15. Implement auditing/outbox/idempotent retries, revocation-lag telemetry, and failure alerts.
16. Test two browsers, multiple nodes, old tokens, resets, concurrent logins/changes, and stale caches.
17. Never log password hashes, bearer/refresh tokens, remember-me cookies, or session cookies.
18. Document the maximum window during which old credentials can remain valid per design and SLA.

## 19. Self-Check Knowledge

**Question 1.** Does changing the password in the database automatically invalidate another browser's `JSESSIONID`?  
**Answer:** No. HTTP sessions maintain their own `SecurityContext`; you must invalidate/revoke sessions or check a security epoch.

**Question 2.** Does calling `SecurityContextLogoutHandler.logout(...)` in request A delete every session on device B?  
**Answer:** No. By default, the handler clears only the current request's context and session.

**Question 3.** Is `SessionInformation.expireNow()` identical to immediately deleting session records in a shared database?  
**Answer:** No. It marks the session expired in the registry; enforcement/cleanup depends on the corresponding filter and session manager.

**Question 4.** Does changing a password hash automatically delete Spring Security's `persistent_logins` rows?  
**Answer:** No. For persistent remember-me, call `PersistentTokenRepository.removeUserTokens(username)` or an equivalent revocation mechanism.

**Question 5.** Why can a token-based remember-me cookie become invalid after a password change?  
**Answer:** Its signature binds the `UserDetails` password; once the store loads the new hash, the old cookie's signature no longer matches.

**Question 6.** If a signed JWT access token has not expired yet, does changing the password break its signature?  
**Answer:** No. To reject it early, enforce a revocation policy such as an epoch, `jti` denylist, or introspection.

**Question 7.** Does revoking a refresh token always invalidate already-issued access tokens immediately?  
**Answer:** No. Access tokens have their own lifecycle; additional policy enforcement is needed.

**Question 8.** In an SSO setup with an IdP session, does local logout guarantee IdP logout?  
**Answer:** No. You must integrate with the IdP's logout/revocation capabilities.

**Question 9.** Why is `credential_version` helpful for logout-all?  
**Answer:** Old tokens/sessions carry the older version, letting resource servers/authorization checks reject them against the current version without enumerating individual tokens.

**Question 10.** Why shouldn't you increment the epoch on every automatic `upgradeEncoding`?  
**Answer:** Technical rehashing is not a user credential change; bumping the epoch can trigger unwanted mass logouts.

**Question 11.** Can you guarantee every request already admitted before the password change is automatically aborted?  
**Answer:** No. In-flight requests may continue; sensitive operations need boundary re-checks where appropriate.

**Question 12.** Why doesn't "clearing cookies" prove a token was revoked?  
**Answer:** Because cookies on other devices or copied cookies still exist; the server must reject that credential.

**Question 13.** When the password change service commits while Redis session cleanup fails, can you report logout-all complete immediately?  
**Answer:** Only if an authoritative revocation gate guarantees old credentials are rejected. Otherwise, handle failures and report lag clearly.

**Question 14.** Is CSRF protection needed on the password-change endpoint when the app uses session cookies?  
**Answer:** Yes, session-based browser flows need proper CSRF protection—never disable it just because tests find tokens inconvenient.

**Question 15.** When may a new session/token be issued after revoking everything?  
**Answer:** After the caller re-authenticates with the new credential or a policy-approved re-authentication mechanism, and the new token/session receives the current epoch.

## Conclusion

Changing a password hash only stops future verifications against the old password; **it is not a revocation operation for all secondary credentials**. Protecting accounts after a password change/reset requires explicit policies per mechanism: logging out current and other sessions, invalidating remember-me tokens, revoking refresh tokens/token families, and deciding how to reject unexpired access tokens.

In Spring Security, `SecurityContextLogoutHandler` handles the current session; Spring Session or an indexed registry manages other sessions; `PersistentTokenRepository.removeUserTokens` clears persistent remember-me tokens; and JWT/OAuth2 require dedicated issuer/resource-server policies. A security epoch updated alongside the password hash provides a strong model for logical revocation when physical cleanup across multiple systems cannot finish atomically.

**Rule to remember:** *Change the password to block the old password. Revoke sessions, remember-me tokens, and tokens to block **previously granted access**. The two are related, yet distinct.*

### Official References

- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security — PersistentTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html)
- [Spring Security — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html)
- [Spring Session — API: FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api.html)
- [Spring Session — Redis: Finding Sessions of a Specific User](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Security — OAuth2 Authorization Server Core Model Components](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/core-model-components.html)
