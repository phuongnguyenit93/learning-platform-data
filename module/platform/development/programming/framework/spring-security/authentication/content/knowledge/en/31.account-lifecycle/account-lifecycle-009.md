# Revoking Sessions, Keys, Tokens, and Factors After Account Changes

## 1. Goal in the Account Lifecycle

In Spring Security, changing a password, locking an account, removing a role, or replacing an MFA device does not automatically invalidate every authentication artifact issued earlier. A single system may concurrently hold:

- HTTP sessions across multiple browsers and devices.
- Remember-me cookies or trusted-device tokens.
- OAuth2 refresh tokens and access tokens, either JWT or opaque.
- API keys, personal access tokens, service-account keys, and mTLS certificates.
- TOTP seeds, WebAuthn credentials, recovery codes, pending challenges, and step-up proofs.
- Identity Provider login sessions alongside local SSO application sessions.

**The problem:** updating account status in the database **does not mean** every session, JWT, API key, remember-me token, or SSO session will immediately be rejected. Each credential class has its own storage, lifetime, issuer, and trust boundary.

For example: an account is disabled at 10:00, yet an already-issued access JWT with `exp=10:30` may still be accepted by APIs if the resource server checks only signature and expiry. Meanwhile, another HTTP session still holds a `SecurityContext` with stale authorities. You must explicitly define **revocation paths, enforcement points, and propagation SLAs**.

Lesson objectives:

1. Classify account-change events and the scope of credentials that must be revoked.
2. Distinguish revoking **root credentials**, **sessions**, **tokens**, **MFA factors**, and **authorization**.
3. Explain the limits of Spring Security sessions/logout, offline JWT validation, and OAuth2 revocation.
4. Design synchronization across instances, resource servers, IdP/SSO, and caches without leaving bypass paths.
5. Provide a Java 17 example and tests verifying the system actually rejects stale credentials.

## 2. What to Revoke, Where, and How?

| Artifact | Source of truth | Revocation mechanism |
|---|---|---|
| **Browser HTTP session** | Servlet container / Spring Session Redis, JDBC… | Delete the server-side session by ID; reject old cookies; clear `SecurityContext`. |
| **Session principal/authorities** | `SecurityContextRepository` / session store | Invalidate session or refresh principal/authorities after `authzVersion` bumps. |
| **Remember-me** | Persistent token DB or signed cookie | Delete persistent series/tokens, clear cookies; stateless tokens need a separate mechanism. |
| **Refresh token** | OAuth2 Authorization Server / grant store | Revoke tokens and grants/families; block refresh for disabled accounts. |
| **Access JWT** | Resource servers usually verify offline | Short TTL or online epoch/status check, `jti` denylist, introspection/central gate. |
| **Opaque access token** | Authorization Server + introspection | Revoke at AS; RS shortens or invalidates its `active` cache. |
| **API key** | Credential store with `key_id` + verifier | Mark revoked/expired, check active owner/tenant status, invalidate caches. |
| **MFA authenticator** | TOTP/WebAuthn/device enrollment store | Disable/remove the specific authenticator ID; revoke/reissue recovery codes as appropriate. |
| **MFA proof/challenge** | Challenge/step-up store | Cancel pending challenges; invalidate verified proofs and elevated grants. |
| **IdP SSO session** | OpenID Provider/IdP | Logout at IdP, federated logout; independent from RP sessions. |
| **Local RP session** | Spring Boot/SaaS app | Delete local sessions; support OIDC back-channel logout if integrated. |
| **Service secrets/certificates** | Secret manager, KMS, PKI | Rotate/revoke keys/certs or update trust stores; separate from user logout. |

**There is no single framework `revokeAll` button covering all of the above.** Applications must connect lifecycle policies to enforcement points capable of rejecting stale access.

## 3. Different Events Demand Different Revocation Scopes

| Event | Browser sessions | OAuth grants/tokens | API keys | MFA enrollment / proofs |
|---|---|---|---|---|
| Logout current device | Destroy current session. | Revoke grants tied to that client/device if policy dictates. | Usually keep independent keys. | Clear session-bound proofs; keep enrollment. |
| Logout all devices | Destroy all sessions for the user. | Revoke grants/families, address access tokens. | Per key policy and ownership. | Clear proofs/trusted-device state. |
| Voluntary password change | Usually revoke other sessions; may keep current session after re-auth. | Revoke refresh grants/bump epoch if required. | Do not delete independent integration keys automatically. | Invalidate recent proofs; keep safe factors. |
| Password reset on suspected compromise | Destroy all sessions. | Revoke refresh tokens, cut off old access tokens. | Review and revoke any related credentials. | Cancel pending challenges/proofs; review enrollments. |
| Account disabled | Destroy all sessions, block new logins. | Issue no new refresh/access tokens; RS rejects old tokens within SLA. | Disable keys via owner/account status or revoke. | Reject factors/proofs, cancel challenges. |
| Role/permission change | Re-evaluate authorities. | Old tokens may carry stale roles; require `authzVersion`/TTL. | Narrow effective scopes at enforcement. | Enrollment need not be deleted. |
| MFA factor changed/removed | Force re-auth on high-risk sessions if needed. | Revoke grants relying on prior assurance. | Do not affect M2M keys by default. | Revoke factor, backup codes, challenges, and related proofs. |
| Security incident | Destroy all sessions. | Revoke grants/families and block access tokens. | Rotate/revoke affected secrets/certs. | Disable compromised authenticators, require re-enrollment. |
| Display name change | Usually keep. | Usually keep. | Keep. | Keep. |

This is an **illustrative policy matrix**, not a mandatory standard. The core requirement is knowing **which events signify compromise, which privileges must drop, and which credentials operate independently of a personal password**.

Do not wipe out an active service integration merely because a user edited their display name; conversely, do not leave a full-privilege personal API key working after its owner is disabled for compromise.

## 4. Source-of-Truth and Revocation Architecture

Typical architecture:

~~~text
[Admin / User / HRIS / Security operations]
                   |
                   v
           Account Lifecycle Service
             - validate actor/policy
             - update account state
             - bump security/authz epochs
             - persist outbox event
                   |
          +--------+----------+
          |                   |
          v                   v
   Access enforcement      Async revocation
    - account active?       - sessions
    - token epoch?          - remember-me
    - current roles?        - refresh grants
    - MFA status?           - API keys
          |                 - IdP/RP logout
          v                   |
     allow / deny         ACK / retry / audit
~~~

Two complementary control paths:

- **Synchronous decision path:** on each request, evaluate effective account state, epochs, and permissions. For sensitive APIs, fail closed per policy if current state cannot be verified.
- **Asynchronous cleanup path:** delete sessions, grants, and MFA proofs and revoke API keys after the committed event, retrying and reconciling until every component acknowledges.

Relying solely on queued events leaves a propagation gap. Relying solely on online checks without cleaning up sessions/tokens leaves security debris and risks missing an endpoint that bypasses the gate. Both paths complement each other.

### Version/Epoch vs Timestamps

A `securityEpoch` increments when credentials or assurance change. An `authorizationVersion` increments when roles, tenants, or policies change. Tokens and sessions can embed the version issued with them, which resource servers compare against current state.

~~~text
token issued: user=usr-1042, securityEpoch=5, authzVersion=11
admin revokes admin role:
  account.authzVersion = 12
resource server:
  validate token signature, issuer, aud, exp
  fetch current account state
  reject token version 11 (or recompute permissions)
~~~

**If APIs do not check the current version, incrementing a DB column does not invalidate old JWTs.** Epochs express policy; they are not cryptographic magic.

## 5. HTTP Sessions in Spring Security and Logout Limitations

Spring Security Servlet reads `Authentication` from `SecurityContext`, which may be persisted into the HTTP session by `SecurityContextRepository` per configuration. When a user signs in across multiple browsers or devices, multiple independent sessions exist.

### Logging Out One Session

Spring Security's `logout()` can invalidate the current HTTP session, clear `SecurityContext`, and run logout handlers. Clearing the client cookie stops the browser from resending the session ID, yet **client-side cookie deletion alone is insufficient** if an attacker holds a copy. The session ID must be rejected **server-side**.

Calling:

~~~java
SecurityContextHolder.clearContext();
~~~

clears only the current request thread's context; it **does not destroy sessions persisted in Redis/JDBC or sessions on other devices**.

### Logging Out All Sessions

You need a reliable way to locate **all sessions belonging to a user**, ideally using an **immutable internal user ID** as the principal index. With Spring Session Redis/JDBC and `FindByIndexNameSessionRepository`, you can look up sessions by principal (once indexing is configured) and delete them by session ID.

~~~java
// Spring Session integration snippet, requires specific dependencies/config:
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public class AllSessionsRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> repository;

    public AllSessionsRevoker(FindByIndexNameSessionRepository<S> repository) {
        this.repository = repository;
    }

    public void revokeAll(String stableUserId) {
        Map<String, S> sessions =
                repository.findByPrincipalName(stableUserId);
        for (String sessionId : sessions.keySet()) {
            repository.deleteById(sessionId);
        }
    }
}
~~~

This is integration code: it will not compile or run standalone without Spring Session, repositories, and indexing configured. Verify that the principal index uses a stable ID rather than a mutable email, and test across multiple instances/replicas, TTLs, and in-flight requests.

### `SessionRegistry.expireNow()` Does Not Immediately Purge Every Session

Spring Security provides `SessionRegistry` and `SessionInformation.expireNow()`. Calling it marks the session expired so a session management filter (such as `ConcurrentSessionFilter` when configured) catches it on the next request. It **does not instantly delete `HttpSession` across all nodes**, and it does not revoke access JWTs or refresh tokens.

Similarly, `maximumSessions(1)` is a concurrent-session policy under compatible configuration, not a replacement for a “log out all devices” workflow. To block imminent requests immediately, still enforce account status and security epochs within SLA.

## 6. Remember-Me and Trusted-Device State

Remember-me lets a browser restore login state after the regular HTTP session expires. If password reset clears sessions while a **persistent remember-me token stays active**, an attacker can silently log back in.

- **Persistent-token remember-me:** delete the user's token/series records on the server and clear the cookie when possible. Copied cookies fail once server records are revoked.
- **Stateless remember-me:** selective revocation is harder; you may need auth epochs, signing key rotation with measured blast radius, or short TTLs. Never treat clearing the current browser's cookie as global revocation.
- **Trusted-device:** device cookies/records reduce MFA friction, yet **do not** prove fresh MFA. When a device is lost or MFA is reset, consider invalidating trusted devices and sessions derived from them.

If a user changes their password inside a freshly reauthenticated session, you may keep that session after regenerating the session ID and bumping the security version; enforce explicit policy so stale credentials are not left valid unintentionally.

## 7. OAuth2 Refresh Tokens, Authorization Grants, and Token Families

Refresh tokens typically outlive access tokens. If leaked, a holder can keep minting fresh access tokens until revocation or expiry. Therefore, disabling an account or resetting a password usually requires **stopping token refresh first**, alongside handling active access tokens.

Per **RFC 7009**, OAuth2 authorization servers expose a token revocation endpoint. Whether revoking one token invalidates related tokens or the entire grant depends on server policy; **revoking one token does not automatically revoke every token across all clients**.

Management metadata typically tracks:

~~~text
grantId, clientId, subjectId, tenantId
refreshTokenId / tokenFamilyId
issuedAt, expiresAt, revokedAt
rotationCounter, reuseDetectedAt
scopes, audiences, assuranceContext
~~~

### Rotation and Reuse Detection

~~~text
RT-1 (active)
  | successful refresh
  v
RT-1 (consumed)
RT-2 (active, same family)
  | attacker presents RT-1 again
  v
reuse detected -> revoke family / require re-auth
~~~

Handle atomic transitions, concurrent refresh requests, grace policies suited to client types, and incident responses. Two concurrent requests must never mint two unmanaged valid refresh tokens, while transient network retries should be handled thoughtfully to avoid locking out legitimate users unnecessarily.

**After an account is disabled**, the authorization server must refuse to mint new tokens **even if an old refresh token row still exists in the DB**. Token cleanup jobs never replace checking account status at refresh time.

For already-issued JWT access tokens, revoking a refresh token stops **new token issuance**, not existing access tokens still within `exp`.

## 8. Self-Contained JWT Access Tokens: Still Valid After Account Lockout

Example:

~~~text
10:00:00  JWT issued, exp = 10:15:00
10:02:00  User disabled
10:05:00  Resource Server validates signature, aud, iss, exp
10:05:01  If current account state is not checked -> JWT may still be accepted
~~~

A cryptographically valid, unexpired JWT does not prove the user is still active, still holds their roles, or still has an unrevoked MFA enrollment. Primary mitigation options:

| Approach | Strength | Limitation |
|---|---|---|
| Short access-token TTL | Bounds exposure without online state. | No immediate revocation; lag equals remaining token lifetime. |
| `jti`/fingerprint denylist | Revokes a specific token. | Requires shared store, TTL/cache, and lookups on every RS. |
| Account security epoch | Revokes many user tokens via one version number. | RS must check online; exposed to latency/cache failure modes. |
| Per-request authz policy | Avoids stale roles; validates current tenant/resource rules. | Depends on policy source availability. |
| Opaque tokens / introspection | AS can return `active=false` post-revocation. | Cached results can lag; increases network dependency. |
| Gateway / central enforcement | Centralizes verification logic. | Must prevent all paths bypassing the gateway. |

Never accept an OIDC ID Token as a bearer API access token. JWTs must pass signature, issuer, API audience, expiration, and token-type validation **before** checking account epochs or roles.

**Rotating the system-wide JWT signing key just to revoke one user has a huge blast radius**, disrupting every active token and JWKS cache. Key rotation addresses compromised signing keys or scheduled hygiene, not per-account revocation.

## 9. Opaque Access Tokens and Introspection Caching

With opaque tokens, a resource server calls OAuth2 introspection (RFC 7662) to retrieve `active`, subject, client, and scopes from the trusted Authorization Server. Once revoked, a *fresh* introspection call returns `active=false`.

However, if the resource server caches `active=true` for 2 minutes, **observed revocation can lag by up to 2 minutes**. Align cache TTLs and invalidation with your security SLA.

If the AS/introspection endpoint is unavailable, fail closed on sensitive endpoints rather than honoring stale cached `active=true` entries past allowed bounds. Never trust a client-supplied `active=true` JSON field.

Revocation at the AS and enforcement at the RS are distinct points: **measure SLAs at the actual API serving traffic**.

## 10. API Keys, Personal Access Tokens, and Service Credentials

API keys may belong to users, tenants, integrations, or service accounts. An order-sync integration key may need to keep working when an employee **voluntarily changes their personal password**, whereas it is unsafe to leave a personal key running if its owner is disabled for compromise.

Illustrative PostgreSQL credential table:

~~~sql
CREATE TABLE api_credentials (
    key_id          VARCHAR(64) PRIMARY KEY,
    owner_id        VARCHAR(80) NOT NULL,
    tenant_id       VARCHAR(80) NOT NULL,
    verifier        BYTEA NOT NULL,
    status          VARCHAR(16) NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    security_epoch  BIGINT NOT NULL
);
~~~

For bearer API keys, store a public `key_id` plus a hash/HMAC verifier of a high-entropy secret rather than plaintext. Credential verification alone is not enough: **every request** must check `ACTIVE`, expiry, owner/tenant status, permissions, and policy epoch when applicable.

Distinguish clearly:

- **Account lock:** user/owner state, not deleting every physical key.
- **API key revocation:** invalidating a specific key ID/credential.
- **Signing key rotation:** rotating JWT or client-assertion signing keys and updating `kid`/JWKS/trust.
- **mTLS certificate revocation:** PKI, CA/trust, OCSP/CRL, or short-lived certificates.
- **TOTP secret reset:** replacing an enrollment factor, not a JWT signing key.

Never treat all of these as “just clear the session.”

## 11. MFA Factor Enrollments, Challenges, Proofs, and Recovery Codes

**Enrolled authenticators** (TOTP seeds, WebAuthn public keys, push devices) differ from pending **challenges** and verified **proofs** that a user recently passed a factor.

~~~text
Enrolled authenticator (TOTP / WebAuthn / device)
          |
          v
Challenge issued -> user presents response
          |
          v
Verifier validates and consumes challenge
          |
          v
Verified factor proof (verifiedAt, method, session, purpose)
          |
          v
Step-up authorization with separate freshness/invalidation
~~~

When a password changes, typically invalidate **step-up proofs** and review related sessions; do not wipe TOTP/WebAuthn enrollments by default unless compromise is indicated.

When an **MFA phone is lost** or an authenticator is removed:

1. Verify the actor and require strong recovery/step-up; never accept an old session unconditionally.
2. Disable that exact authenticator ID so its seed/credential is rejected immediately.
3. Cancel pending challenges using that authenticator; guard against concurrency.
4. Invalidate verified-factor proofs and elevated grants derived from it.
5. Revoke or regenerate recovery codes and trusted devices per policy.
6. Audit and send a security alert; re-evaluate sessions/tokens carrying stale assurance and require re-auth.

Never refresh `verifiedAt` merely because an access token refreshed or a form opened. A static `mfa=true` boolean inside a JWT cannot be revoked unless the RS verifies live state or factor versions.

## 12. OIDC SSO: IdP Sessions and Application Sessions Are Different Things

Under OIDC login, there is an **IdP/OpenID Provider session** and a **local Relying Party (RP) session**. Ending one does not automatically end the other.

Common OIDC logout mechanisms:

- **RP-Initiated Logout:** RP asks the OP to terminate its session via supported endpoints.
- **Front-Channel Logout:** browser-mediated signaling, fragile across user-agent and cookie policies.
- **Back-Channel Logout:** OP sends a **signed Logout Token** to an RP endpoint; the RP verifies it and destroys matching local sessions.
- **Token revocation:** OAuth2 grants, refresh tokens, and access tokens form a separate layer.

OIDC Back-Channel Logout 1.0 uses a JWT Logout Token with `iss`, `aud`, `iat`, `events`, and at least `sub` or `sid`. The RP must validate signature, issuer, audience, event/purpose, timestamps, and replay rules before invalidating sessions.

~~~text
IdP -> signed Logout Token -> RP back-channel endpoint
                                  |
                           verify token trust
                                  |
                           find sessions by
                         (iss, sub) and/or (iss, sid)
                                  |
                            invalidate sessions
                                  |
                           audit without token
~~~

Never honor an arbitrary client-sent `POST /logout-all?user=admin`; never key solely by `sub` across multiple issuers/tenants. Spring Security provides OIDC and Spring Session integration points, but verify exact behavior for your version and configuration.

An HRIS/SCIM deprovisioning event updates account state; **it is not by itself a logout protocol**. Complete offboarding requires blocking the account in the app/RS and terminating existing sessions and tokens.

## 13. Password Change and Password Reset: Order of Operations

Safe workflow:

~~~text
User requests password change / recovery
      |
      v
Verify correct actor, recent assurance, password policy
      |
      v
Begin DB transaction
  - write new password hash (strong PasswordEncoder)
  - bump account securityEpoch / credentialVersion
  - record security event in transactional outbox
Commit
      |
      v
Enforcement gate rejects old epochs
      |
      +--> revoke sessions / remember-me
      +--> revoke refresh grants / token families
      +--> invalidate step-up proofs / recovery tokens
      +--> evaluate API keys and IdP SSO
      +--> notify account owner and audit
~~~

For an **emergency password reset**, revoke all sessions per policy. For a **self-service password change after MFA**, you may retain the current session after regenerating the session ID and updating the epoch—ensuring sessions on other devices are invalidated and the app never grants privileges from a stale security context.

Side effects outside the DB transaction should use a durable outbox with retries and reconciliation. Never report “logged out of all devices” merely upon enqueuing an async event if policy requires stronger guarantees.

### In-Flight Requests and TOCTOU

An approval request may pass authorization at 10:01, the account gets disabled at 10:02, and the request tries to commit at 10:03. For sensitive operations, **recheck account status, epoch, and policy right before commit** using appropriate locks/transactions. Checking only in an entry filter is insufficient for long-running actions.

## 14. Disable, Lock, Suspend, and Delete Differ

| Status | Typical business meaning | Suggested enforcement |
|---|---|---|
| `ACTIVE` | Account may authenticate if policies pass. | Normal authentication + authorization. |
| `LOCKED` | Often triggered by login failures or risk. | Reject login; handle existing sessions per policy. |
| `SUSPENDED` | Temporary access halt. | Block login, refresh, API keys, and sessions within defined scope. |
| `DISABLED` | Account no longer permitted to use the system. | Fail closed on all relevant access paths. |
| `DELETED/DEPROVISIONED` | Account terminated. | Revoke credentials; keep audit/tombstone per retention. |

`UserDetails.isEnabled()` and `isAccountNonLocked()` are typically checked **when the authentication provider executes**. Already-authenticated HTTP sessions or JWTs do not automatically re-read `UserDetails` on every request. Add an **authorization/account-status gate** when immediate enforcement is required.

### Offboarding Example

1. HR/IdP confirms user ID and tenant from a trusted source.
2. Account service commits `DISABLED` and bumps `securityEpoch`.
3. Auth server stops issuing new tokens.
4. Destroy sessions, remember-me tokens, refresh families, and MFA challenges/proofs.
5. Revoke personal API keys per policy; transfer approved shared integrations explicitly.
6. Resource servers reject old JWTs via online state/version or equivalent enforcement.
7. Execute IdP/SCIM/federated logout per contract.
8. Audit and reconcile to catch leftover credentials or sessions.

Never use email as the account-linking key across multiple IdPs or after email changes. Use immutable internal user IDs and properly namespaced external identity keys.

## 15. Role/Tenant Changes: Revoking Authorization While Authentication Remains Valid

A user may remain legitimately logged in as themselves yet lose `PAYMENT_APPROVE` after switching teams. If a JWT or session holds only a login-time snapshot of authorities, stale privileges linger too long.

Solutions:

- **Load current policy** at critical endpoints/actions.
- Use `authzVersion` or a permissions epoch checked online against account state.
- Invalidate or refresh sessions on major privilege changes.
- Keep JWT TTLs short where delay is acceptable; use online enforcement for high-risk actions.
- Match tenant claims in credentials against target resources; never take tenant IDs from unverified client headers.

Example:

~~~text
Access token: user=usr-1042, tenant=A, authzVersion=17
Admin removes role PAYMENT_APPROVE:
  account.authzVersion = 18
API request with v17:
  validate JWT and compare current version
  DENY or require refresh with v18 policy
~~~

**Never fix stale roles by rotating the global JWT signing key** unless the signing key itself is compromised.

## 16. Event-Driven Revocation: Idempotency, Ordering, and Outbox

An event should carry:

~~~json
{
  "eventId": "evt-8d12",
  "type": "ACCOUNT_DISABLED",
  "subjectId": "usr-1042",
  "tenantId": "tenant-a",
  "accountVersion": 42,
  "effectiveAt": "2026-11-06T10:00:00Z",
  "reasonCategory": "SECURITY_INCIDENT"
}
~~~

Consumers should be:

- Idempotent: receiving `v42` twice neither creates new tokens nor causes dangerous errors.
- Monotonic: receiving `v41` after `v42` must never regress state backward.
- Re-enabling at `v43` must never resurrect credentials already revoked at `v42`.
- Durable retry with backoff and monitored dead-letter queues.
- Periodic reconciliation comparing account state against active session/grant/key indexes.

Use a **transactional outbox** so account state and revocation intent commit together before a worker publishes the event. Publishing only from memory after DB commit risks losing revocation commands if the queue blips right when disabling an account.

Separate **commands** (“revoke sessions”), **events** (“account disabled at version 42”), and **audits** (who requested, why, which systems acknowledged). Audits must never contain bearer tokens or secrets.

## 17. Spring Security: Enforcing Account State at Method Boundaries

In Spring Boot 3.x / Spring Security 6.x, `Authentication.isAuthenticated()` does not block disabled accounts or recently revoked permissions. Build a policy bean using a **trusted internal user ID**, never taking user IDs from request parameters.

The following is **integration code** requiring application-implemented services and identity mapping, not a standalone `javac` program:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("accountAccessPolicy")
public class AccountAccessPolicy {
    private final AccountStateService states;

    public AccountAccessPolicy(AccountStateService states) {
        this.states = states;
    }

    public boolean active(Authentication auth) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }
        String userId = resolveTrustedInternalUserId(auth);
        return userId != null && states.isActive(userId);
    }

    private String resolveTrustedInternalUserId(Authentication auth) {
        // Depends on verified internal principal/Jwt type.
        // Never read ID from client-supplied headers/JSON.
        throw new UnsupportedOperationException("integration required");
    }
}
~~~

This illustrates only the integration hook; production must implement `resolveTrustedInternalUserId` against trusted state.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    @PreAuthorize(
        "hasAuthority('PAYMENT_APPROVE') and " +
        "@accountAccessPolicy.active(authentication) and " +
        "@factorPolicy.recentForPayment(authentication)")
    public void approve(String paymentId) {
        // Verify resource/tenant, securityEpoch, factor proof,
        // and business invariants at commit time.
    }
}
~~~

Enable `@EnableMethodSecurity` and test Spring AOP proxy interception; **self-invocation** within the same bean bypasses method-security proxies. `hasAuthority` inspects only the authorities attached to the current `Authentication`, whereas policy beans and transactional services enforce live lifecycle state.

### Resource Server JWT

If tokens include `securityEpoch`, a `JwtAuthenticationConverter` or authorization service can resolve the current user/epoch **after `JwtDecoder` verifies the token**. Never trust arbitrary email claims as the user key; bind issuer, subject, tenant, and internal links. Sensitive endpoints can use a dynamic `AuthorizationManager` or method policy to avoid stale permissions.

### Session Store

With Spring Session Redis/JDBC, a shared repository/index enables revoking all sessions. With a single-node in-memory `SessionRegistry`, logout-all will not propagate across nodes unless backed by shared state or distributed coordination.

## 18. Standalone Java 17: Security Epochs and Credential Validity

The following Java 17 example models only **state evaluation**. It does not verify JWT signatures, passwords, HMAC API keys, session cookies, or real MFA. The key takeaway is that credentials issued before an account's security epoch increments are rejected **provided verifiers check the epoch**.

~~~java
import java.time.Instant;

public class AccountRevocationDemo {
    record BrowserSession(long issuedEpoch) {}
    record AccessToken(long issuedEpoch, Instant expiresAt) {}
    record FactorProof(long issuedEpoch, String method) {}
    record ApiKey(boolean revoked) {}

    static final class Account {
        private long epoch = 1;
        private boolean enabled = true;

        synchronized long currentEpoch() {
            return epoch;
        }

        synchronized boolean active() {
            return enabled;
        }

        synchronized void passwordChanged() {
            epoch++;
        }

        synchronized void disabled() {
            enabled = false;
            epoch++;
        }
    }

    static boolean browserValid(Account a, BrowserSession s) {
        return a.active() && s.issuedEpoch() == a.currentEpoch();
    }

    static boolean jwtValid(Account a, AccessToken t, Instant now) {
        return a.active() && t.issuedEpoch() == a.currentEpoch()
                && now.isBefore(t.expiresAt());
    }

    static boolean mfaProofValid(Account a, FactorProof p) {
        return a.active() && p.issuedEpoch() == a.currentEpoch()
                && p.method().equals("TOTP");
    }

    static boolean apiKeyValid(Account a, ApiKey k) {
        return a.active() && !k.revoked();
    }

    public static void main(String[] args) {
        Account account = new Account();
        Instant now = Instant.parse("2026-11-06T10:00:00Z");
        long v = account.currentEpoch();

        BrowserSession session = new BrowserSession(v);
        AccessToken jwt = new AccessToken(v, now.plusSeconds(900));
        FactorProof proof = new FactorProof(v, "TOTP");
        ApiKey integration = new ApiKey(false);

        System.out.println("initial browser: "
                + browserValid(account, session));
        System.out.println("initial jwt: "
                + jwtValid(account, jwt, now));
        System.out.println("initial factor: "
                + mfaProofValid(account, proof));

        account.passwordChanged();
        System.out.println("after password browser: "
                + browserValid(account, session));
        System.out.println("after password jwt: "
                + jwtValid(account, jwt, now.plusSeconds(1)));
        System.out.println("after password factor: "
                + mfaProofValid(account, proof));
        System.out.println("after password api key: "
                + apiKeyValid(account, integration));

        account.disabled();
        System.out.println("after disable api key: "
                + apiKeyValid(account, integration));
    }
}
~~~

Save exactly as `AccountRevocationDemo.java` and run:

~~~bash
javac AccountRevocationDemo.java
java AccountRevocationDemo
~~~

**Exact stdout:**

~~~text
initial browser: true
initial jwt: true
initial factor: true
after password browser: false
after password jwt: false
after password factor: false
after password api key: true
after disable api key: false
~~~

Meaning: after a password change, the session, JWT, and MFA proof bound to the old epoch are rejected. Under this illustrative policy, an independent integration API key is not automatically revoked by a password change; once the account is disabled, the API key is blocked too via owner status.

**Production note:** demo state lives in one JVM without real concurrency, distributed caches, or token issuance. If a JWT resource server validates only signature/`exp` **without checking the epoch**, `passwordChanged()` does nothing to invalidate existing JWTs. Security epochs must persist transactionally, and enforcement/cache invalidation must meet SLA.

## 19. SLAs, Monitoring, and Post-Revocation Verification

Never equate “published a revoke event” with “all stale requests are blocked.” Measure:

1. `t0`: account update/`securityEpoch` commits.
2. `t1`: new requests at APIs/AS start being rejected.
3. `t2`: related sessions, grants, keys, MFA proofs, and RP sessions are cleaned up or gated.
4. `t3`: reconciliation confirms no policy-violating credentials remain.

Only once those milestones are genuinely met should user-facing messaging report “signed out of all devices” in a security sense. If an offline JWT lives 15 minutes with no online checks, you cannot guarantee 30-second revocation simply by updating an `enabled` column.

Suggested metrics:

~~~text
account_security_change_total
revocation_event_lag_seconds
session_revocation_success_total
refresh_grant_revocation_failure_total
stale_access_token_rejected_total
disabled_account_access_attempt_total
mfa_proof_revocation_lag_seconds
revocation_reconciliation_discrepancy_total
~~~

Audits should record actor, subjectId/tenant, reason category, eventId/version, outcome, timestamp, and correlation ID, while **excluding raw access/refresh tokens, session cookies, API key secrets, and MFA recovery codes**.

## 20. Testing and Common Pitfalls

| Scenario | Expected outcome |
|---|---|
| User logs out of browser A while logged in on browser B | Single-device logout affects only A if policy intends |
| User triggers logout all | Both A and B are blocked; old cookies cannot restore sessions |
| Calling only `SecurityContextHolder.clearContext()` | Test demonstrates other sessions remain active |
| Calling `SessionRegistry.expireNow()` | Verify filter/session infrastructure rejects the next request |
| Password reset completes | Sessions, refresh grants, and MFA proofs revoked per policy |
| Refresh token revoked while access JWT is unexpired | API still enforces strategy for old JWT; do not assume refresh revoke stops it |
| JWT carries stale epoch after password change | RS checks current epoch and rejects |
| JWT carries stale ADMIN role after privilege removal | Admin access does not persist past policy latency |
| Cached opaque introspection result | Does not exceed revocation SLA; needs invalidation/TTL |
| Remember-me cookie from an old device | Cannot re-login after incident/reset if policy revokes |
| Account disabled while API key row still shows active | API owner-status check still rejects, or key is revoked |
| TOTP authenticator removed | Related challenges/proofs invalidated; seed no longer trusted |
| Forged OIDC logout token | RP rejects without creating user DoS |
| Valid back-channel logout with `iss/sub/sid` | RP deletes matching sessions without hitting other issuers |
| Duplicate revoke event delivered | Idempotent; creates no new credentials or dangerous errors |
| Disable event `v42` arrives after enable `v43` | Stale event does not disable newer valid state |
| Queue outage right after account disable | Outbox/retries recover; enforcement blocks via version/state |
| Request passed auth before disable but commits afterward | TOCTOU guard at business commit rejects per policy |
| Deleted user's email re-registered | Old credentials never bind to the new user sharing the email |
| Resource server cannot reach status store | Sensitive APIs fail closed per policy |
| Account re-enabled | Previously revoked keys/tokens/factors stay revoked |

Common implementation mistakes: updating only the password hash; deleting only the current browser's cookie; assuming IdP logout logs out every RP; rotating JWT signing keys to revoke one user; bumping auth versions that no consumer checks; caching `account-active` indefinitely; tying service API keys to personal usernames/emails; and lacking audits or reconciliation.

## 21. Operational Checklist

- [ ] Maintain an event → revocation matrix across sessions, remember-me, refresh/access tokens, API keys, MFA, and SSO.
- [ ] Treat account status and security/authz epochs as authoritative, committed before reporting success.
- [ ] Reject disabled accounts across every login and token-refresh path.
- [ ] Back cross-node session stores with a reliable principal index for logout-all.
- [ ] Handle remember-me and trusted devices explicitly on reset/compromise.
- [ ] Revoke refresh grants/families and enable reuse detection where rotation is used.
- [ ] Enforce JWT/opaque token revocation within SLA rather than relying solely on `exp` when rapid denial is required.
- [ ] Ensure resource servers still verify signatures, issuer, audience, expiry, token purpose, and resource permissions.
- [ ] Check live owner/tenant/status on API keys; scope service credentials explicitly.
- [ ] Separate MFA authenticators from challenges and proofs so each invalidates properly.
- [ ] Separate OIDC local sessions, IdP sessions, and OAuth grants.
- [ ] Ensure role/tenant changes affect live authorization instead of trusting stale snapshots.
- [ ] Test outbox, idempotency, version ordering, DLQ/retries, and reconciliation.
- [ ] Align cache invalidation and network failure modes with security SLAs.
- [ ] Recheck privileges near commit on high-risk business actions to prevent TOCTOU.
- [ ] Keep tokens, cookies, OTPs, TOTP seeds, and API key secrets out of logs.
- [ ] Maintain tested runbooks for emergency disables, key rotation, MFA re-enrollment, and safe re-enablement.
- [ ] Run multi-instance integration tests, event-race tests, and revocation-latency monitoring.

## 22. Conclusion

**Account changes do not automatically revoke previously issued authentication artifacts.** Lifecycle management must connect directly to every state layer: HTTP sessions, remember-me tokens, refresh grants, access tokens, API keys, MFA enrollments/proofs, and SSO sessions. Each has its own storage and revocation mechanics.

A reliable operational pattern is **commit account state/epoch → enforce live state on request paths → publish idempotent revocation events → clean up related credentials/sessions → audit, reconcile, and test against SLAs**. Especially for self-contained JWTs, changing a password or revoking a refresh token **never guarantees** an active JWT stops working unless resource servers add online status/epoch/denylist checks or an accepted short TTL.

In Spring Security, logout, `SecurityContext`, `SessionRegistry`, Spring Session, Resource Server, OAuth2 grants, and MFA proofs are distinct boundaries. Security comes from coordinating them under an explicit policy, not from assuming a single framework call revokes everything.

## References

- [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContext`, session concurrency, and `SessionRegistry`.
- [Spring Security – Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout handlers, clearing contexts, and session invalidation.
- [Spring Session – API](https://docs.spring.io/spring-session/reference/api.html): shared session stores and principal indexing.
- [Spring Security – Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation and policy extensions.
- [RFC 7009 – OAuth2 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): AS revocation and authorization grant impact.
- [RFC 7662 – OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): opaque token active state and caching.
- [RFC 9700 – OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): bearer/refresh-token risks and rotation.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): Logout Tokens and RP sessions.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html): OP logout initiated by RPs.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle and revocation.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account recovery, sessions, and credential changes.
- [OWASP – Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA device removal, recovery, and invalidation.
