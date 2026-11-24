# Revoking Permissions, Locking Accounts, and Invalidating Active Sessions

> **Topic:** Spring Security – federation. **Knowledge group:** Directories and Accounts. This Knowledge article explains how to handle **authorization revocation**, **account lock/disable**, and **active session invalidation** in a Spring Security system integrating LDAP/Active Directory with SAML, OIDC, CAS, or Kerberos. The central point: these three operations **are not equivalent** and do not automatically propagate across directories, IdPs, session stores, API tokens, and business data.

## 1. Learning Objectives

After completing this lesson, learners can:

1. Distinguish "removing a group/role", "temporarily locking login", "disabling an account", and "revoking all sessions/tokens" by what each affects.
2. Understand why a user disabled in LDAP/AD **can still hold an `HttpSession`, JWT access token, or issued service ticket** if the application lacks revalidation or revocation mechanisms.
3. Identify the **source of truth** for user status, tenant membership, permissions, app sessions, SSO sessions, refresh tokens, and access tokens.
4. Model the security lifecycle as **account state + policy version + lifetime + revocation events**, and fail closed when checks are uncertain.
5. Configure Spring Security for login-account checks and Spring Session Redis to **find/delete sessions by principal**, including across multi-pod deployments.
6. Avoid confusing `SessionRegistry.expireNow()` with directly deleting sessions from the datastore, and avoid confusing `HttpSession.invalidate()` with remote logout across all applications.
7. Compare how revocation works for **server-side sessions**, **opaque token introspection**, **self-contained JWTs**, **refresh tokens**, **OIDC Back-Channel Logout**, **SAML SLO**, **CAS logout**, and **Kerberos tickets**.
8. Prevent race conditions when revocation coincides with login, token refresh, permission grants, or in-flight multi-step transactions.
9. Write standalone Java 17 tests demonstrating account states, privilege removal, authorization version increments, and session invalidation.
10. Build runbooks for employee offboarding, suspected account compromise, single-tenant permission revocation, and forced reauthentication.

**Overarching takeaway:** **Blocking new logins ≠ blocking existing sessions ≠ revoking all tokens ≠ immediately losing access to data.** The system must enforce each security guarantee separately, at the exact component protecting the resource.

## 2. Four Distinct Security Goals

Suppose `alice@corp.example` is using a financial management application:

| Action | What changes? | Desired effect | Does NOT automatically guarantee |
| --- | --- | --- | --- |
| **Revoke `APPROVE_PAYMENT`** | Membership/permission in authorization store | Alice cannot approve new transactions | Logout from all apps; password lock; invalidating old JWTs |
| **Lock account** | `accountNonLocked=false` or directory lockout | Rejects new authentication while lock is active | Existing web sessions terminate immediately |
| **Disable account** | `enabled=false` or AD account disabled | Prevents continued login and service use per policy | All RPs auto-logout; issued access tokens expire immediately |
| **Invalidate active sessions** | Delete/expire `HttpSession`/session registry and/or revoke tokens | Old session ID can no longer continue authentication | Directory account disabled; permissions in another tenant changed |
| **Revoke refresh token/grant** | Authorization Server refuses new token exchange | Client can no longer obtain new access tokens from that grant | Already-issued JWT access token seen as revoked by RS itself |
| **Revoke access token** | Resource Server has a mechanism to detect revoked tokens | That specific token can no longer access resources | All local web sessions/IdP sessions log out |
| **OIDC/SAML/CAS SSO logout** | IdP/OP/SP and RPs coordinate logout | Participating login sessions may be terminated | Every offline RP receives it; every JWT access token invalidates immediately |
| **Close local app session** | Clear session of the current application | User is no longer authenticated in that app | Browser loses TGT/TGC or SSO session at the IdP |

**Real-world example:** An admin removes `ROLE_FINANCE_APPROVER` from the Directory at 14:00, yet Alice logged in at 09:00 and her local session's `SecurityContext` still holds the old authority. If the controller only checks `@PreAuthorize("hasRole('FINANCE_APPROVER')")` against `GrantedAuthorities` cached since 09:00, Alice **can keep approving** until the app refreshes authorities/invalidates sessions or checks live permissions from the authoritative source.

**Minimum policy for high-risk operations:** Verify active account, membership, and permission for the **exact tenant + resource + action at commit time**. A valid session or token is necessary, not sufficient.

## 3. Account Lifecycle Semantics in Directories

### 3.1. Three common states that must not be conflated

| State | Interpretation | Example |
| --- | --- | --- |
| **ACTIVE** | Account is permitted to sign in per policy | Current employee |
| **LOCKED** | Temporarily blocks authentication, often due to failed logins/risk | Locked due to brute-force or admin security action |
| **DISABLED** | Account disabled per workflow, potentially long-term | Employee offboarded / contract ended |
| **EXPIRED** | Account or credential past directory policy validity | Contractor account past end date |
| **DELETED** | Directory object removed/replaced; note IDs may be reused in some systems | Offboarding, cleanup |
| **MISSING/UNKNOWN** | Account not found or directory source untrusted/out-of-date | Replication lag, outage, wrong mapping |

Each state leads to a different policy:

- `LOCKED` from repeated bad passwords may be auto-unlocked by the directory after a cooldown or admin check; do not assume it equals `DISABLED`.
- `DISABLED` must be reflected in **each application's authorization checks and session invalidation**. Deleting an LDAP user does not immediately destroy local sessions.
- `EXPIRED` may mean account expiration or password expiration; an expired password may sometimes allow a governed password-change flow, but must not grant sensitive permissions as a normal session.
- `MISSING` must never be treated as `ACTIVE` just because the app holds a previously cached `UserDetails`.

### 3.2. Spring Security `UserDetails` checks

Spring Security `UserDetails` defines the contract:

```java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
```

With authentication providers based on `AbstractUserDetailsAuthenticationProvider` (e.g., DAO provider), pre/post checks can reject disabled, locked, expired, or credential-expired accounts **when authentication occurs**.

**Do not assume they are automatically called on every request** carrying a `JSESSIONID`: Spring Security may load the saved `Authentication` from `SecurityContextRepository` and go straight to authorization without re-authenticating through the provider. To achieve "lock immediately", add **request-time account status enforcement**, event-driven invalidation, or a policy-versioning mechanism.

### 3.3. Active Directory account disable and account lockout

Microsoft Active Directory has the `userAccountControl` attribute with the `ACCOUNTDISABLE` flag (bit `0x0002`). A normal user account can carry `NORMAL_ACCOUNT` (bit `0x0200`); multiple flags are bitwise ORed. Never write logic checking `value == 514` for all accounts because other flags may coexist.

**Readable** example:

```text
userAccountControl = 512   (0x0200 NORMAL_ACCOUNT, not disabled)
userAccountControl = 514   (0x0202 = NORMAL_ACCOUNT | ACCOUNTDISABLE)
```

**Note:** These are examples of common combinations, **not advice to set raw LDAP attributes directly**. Account lockout differs from disable; in modern AD, `LOCKOUT` and certain password-expiry states are exposed via the computed attribute `msDS-User-Account-Control-Computed` alongside lockout timestamps/policies. `lockoutTime` may remain non-zero even after a lockout window has expired; use directory APIs/effective state rather than inspecting a single raw attribute.

Non-AD LDAP servers use different schemas/policies (e.g., `pwdAccountLockedTime` in password policy overlays)—there is **no universal `userAccountControl` flag across all LDAP servers**. Use an adapter matching your directory and organizational policy contract rather than copying AD conditions onto OpenLDAP.

### 3.4. Revoking Directory Group permissions

A user may belong to:

```text
cn=Finance-Approvers,ou=Groups,dc=corp,dc=example
cn=Finance-Readers,ou=Groups,dc=corp,dc=example
```

Removing `Finance-Approvers` membership may drop the approval entitlement at the IdP/directory, yet the application must check:

- Is there group nesting/transitive membership? `memberOf` in AD/LDAP does not automatically return all nested groups across all queries/drivers.
- When were groups synced into the local DB, session, or JWT claims?
- Does the OIDC/SAML Identity Provider emit fresh group claims, and does the RP recheck them or keep using the session?
- Was the permission also granted directly inside the app via another role or a tenant-level grant?
- Does the user have another linked account/federation issuer to log back in with?

Therefore, a revocation workflow must evaluate **effective permissions**, not merely remove one membership entry in the Directory.

## 4. Boundaries Across Directory, IdP, App Session, and API Tokens

```text
                 Directory / Identity Source
              account status, groups, affiliations
                          |
              LDAP/AD sync or event
                          v
                 IdP / OP / CAS / KDC
           auth sessions, login policy, TGT/tokens
                 |              |
          SAML/OIDC/CAS       Kerberos
                 |              |
                 +-------+------+
                         v
              Spring Security Web App
               SecurityContext + HttpSession
                         |
             +-----------+------------+
             |                        |
           Spring Session        API Resource Server
           Redis/JDBC            JWT or opaque token
             |                        |
             +-----------+------------+
                         v
               Authoritative local
           account/tenant/permission policy
                         |
                         v
               Business data mutation
```

From the diagram, **four separate stores** may require independent revocation:

1. **Directory/account database**: account status, roles, memberships, entitlements.
2. **IdP/OP**: SSO sessions, sign-in sessions, refresh tokens, and federation credentials.
3. **Web application**: `HttpSession`/`SecurityContext`/remember-me cookies/Spring Session records.
4. **Resource Server and APIs**: access tokens/JWTs, token introspection caches, API keys/service credentials.

**Locking only store 1** does not automatically clear stores 3/4. **Logging out only from store 3** does not stop the IdP at store 2 from issuing new authorization codes/tokens if the Directory is not updated or the OP still holds an SSO session.

### 4.1. "Immediacy" must be precisely defined

Do not write vague policies like "permissions are revoked immediately" when the system has caches, event buses, and distributed nodes. Define a clear **revocation propagation SLA**:

- `T0`: admin action commits in the authoritative store.
- `T1`: event/outbox commits; consumers receive the new version.
- `T2`: web session store deletes affected sessions and permission caches are invalidated.
- `T3`: IdP/grants/refresh tokens are revoked if policy requires.
- `T4`: all new app/resource server requests/actions are blocked, **verified by tests**.

For sensitive business actions, the goal is typically **no action commits after T0 with a lost permission**, even if the session-deletion event at T2 has not yet completed. Achieve this via authoritative authorization checks, transaction semantics, or a security epoch fence—never rely solely on eventual event delivery.

## 5. Why Locking an Account Does Not Automatically Kill Old Sessions

A typical web flow:

```text
09:00 User login SAML/OIDC/LDAP
      -> Spring builds Authentication with ROLE_APPROVER
      -> Stores SecurityContext in HttpSession id S-123

14:00 Directory disables Alice
      -> New LDAP login may fail
      -> BUT session S-123 still exists in Redis

14:01 Browser sends Cookie: SESSION=S-123
      -> Spring loads old Authentication
      -> Controller checks cached ROLE_APPROVER
      -> Operation may still succeed unless extra enforcement exists
```

Reasons:

- `SecurityContextRepository` may store `Authentication` in a local session without querying LDAP on every request.
- `UserDetails.isEnabled()` is typically checked by the provider at login, **not automatically re-invoked** on every already-authenticated request.
- Session timeouts have no awareness that the user was disabled mid-session in the Directory.
- Applications may cache group memberships, authority mappings, or token claims for minutes or hours.
- A self-contained JWT carrying scopes/roles, while validly signed and unexpired, still passes signature verification; it carries no fresh revocation status unless the resource server consults a state source.
- With browser SSO, if the app session is deleted while the IdP still holds an SSO session, the browser can immediately log back in without entering a password; OP/IdP sessions must be handled per policy.

**Wrong:** "We disabled the user in AD, so surely all open tabs were kicked out." **Right:** "We disabled the user in AD; the system must prove existing web sessions/tokens can no longer execute forbidden actions."

## 6. Choosing a Strategy by Severity

No single measure fits every action:

| Event | Appropriate scope | Preferred mechanism | Why? |
| --- | --- | --- | --- |
| Remove read permission on 1 project | Project/resource | Live permission check + bump entitlement version; invalidate cache | No need to log the user out everywhere |
| Remove `ROLE_APPROVER` in tenant A | Tenant A | DB policy check at commit + bump version; optionally revoke related sessions | Does not invalidate legitimate tenant B access |
| Account locked due to brute force | Account/login | Block new logins; evaluate whether active sessions must be terminated | Lockout policy may target credential attempts only |
| Admin locks account due to suspected compromise | Entire account | Disable/lock, revoke all local sessions, grants/tokens, and OP sessions | Prioritize containment |
| Employee offboarded | Entire organization | Disable IdP/Directory, deprovision apps, revoke sessions/tokens/devices | Prevent re-login via federation |
| Email/display name change | Profile | Update attributes; do not auto-logout unless risky | Not every profile edit is a security event |
| Password change | Per security policy | May revoke refresh tokens/other sessions, require step-up | Needs explicit policy; never assume |
| Compromised refresh token detected | Client/grant/device or entire account by risk | Revoke refresh token family/grant, resource token defenses | Block further token issuance |
| User caught performing risky action | Transaction/session | Step-up + fresh auth and recheck permissions | Existing session alone does not prove sufficient assurance |

Distinguish **"all sessions for the account"** from **"one device session"**, **"sessions for one RP"**, and **"all sessions for one tenant"**. Management APIs must specify scope instead of calling a vague `logoutUser()`.

## 7. Designing Authoritative Security State and Policy Versions

Maintain an application-level data source (an account-access service or database transaction) governing effective status and permissions:

```text
AccountAccessState
  accountKey           = immutable internal account ID
  sourceIdentity       = (issuer/realm, immutable external subject)
  enabled              = true | false
  accountNonLocked     = true | false
  accountExpired       = true | false
  entitlementVersion   = monotonic integer
  sessionsValidAfter   = timestamp or monotonically increasing epoch
  tenantMemberships    = tenantId -> role/permission set
  updatedAt            = UTC timestamp
  updatedBy            = authorized admin or source event
  reasonCode           = ROLE_REVOKED | LOCKED | DISABLED | INCIDENT
  policyVersion        = version of security rules
```

A `SessionEvidence` or authenticated principal should retain:

```text
sessionId            = opaque session key from server
accountKey           = stable local ID
federatedSource      = verified issuer/realm/registration
externalSubject      = verified sub/NameID/directory ID
authenticatedAt      = instant of authentication when available
entitlementVersion   = version at last trusted authorization refresh
sessionEpoch         = epoch when issued (not a mutable browser header)
tenantContext        = resolved and authorized tenant, not user-supplied grant
```

**Policy:**

1. When an account is `disabled`/`locked`, new requests must be rejected via active-state checks.
2. When `entitlementVersion` increments, sessions holding old authorities **must not continue sensitive actions**; refresh authoritative permissions or require reauth/block until synced.
3. When `sessionsValidAfter` advances, any session with an older timestamp/epoch is invalid even if the Redis deletion event has not run yet.
4. A browser-sent `tenantId` is only **tenant intent**, never proof of membership.
5. When the state store is unreachable, fail closed for sensitive actions; an evaluated low-risk read-only mode may exist, but never rely on cached `ADMIN` to commit.
6. Never reset `entitlementVersion` to a smaller number when re-enabling an account; use monotonic generations or event ordering.
7. Account and issuer identifiers must be stable; **emails can change or be recycled**, so never use email as a shared revocation key across issuers.

### 7.1. Why are both session deletion and epoch checks needed?

Deleting a session in Redis alone leaves a **race window**:

```text
T0: Request A already loaded session into JVM pod-1
T1: Admin revokes; worker deletes session key from Redis
T2: Request A still holds old Authentication in thread
T3: Request A commits business operation
```

If the transaction at T3 relies only on authorities cached at T0, the user still completes the action after revocation. **Deleting a Redis key cannot roll back an in-flight request.** High-risk actions must check the entitlement version/state at business commit time or within a transaction boundary synchronized with authority state.

Conversely, relying only on version checks without deleting sessions causes the app to repeatedly reject stale contexts while junk sessions linger, retaining unnecessary credentials/attributes and allowing IdP re-entry. Use **both active enforcement and session cleanup**.

## 8. Reliable Permission Revocation Workflow

### 8.1. Admin event recorded in the authoritative store

```text
Admin (MFA + authorized) revokes role:
  target = acct-42, tenant-A, APPROVE_PAYMENT
                 |
                 v
Transaction:
  UPDATE entitlement / account access state
  INCREMENT entitlementVersion
  INSERT durable outbox security event
                 |
                 v
COMMIT (T0)
                 |
                 +--> API authorization checks current version
                 |
                 +--> Outbox worker publishes AccountAccessChanged
                                |
                 +--------------+----------------+
                 v              v                v
           Session Revoker   Token/Grant Revoker  Cache Invalidation
                 |              |                |
                 v              v                v
           Redis/DB session  OP authorization    permission caches
           index delete      server / IdP        at pods/APIs
                 |
                 v
          Readback/verification/audit
```

**Ordering correctness:** Security events must be emitted **only after** the authoritative transaction commits, via a transactional outbox/durable queue, avoiding scenarios where a "revoke" is emitted before a DB rollback leaves permissions intact. Consumers must be idempotent and tolerate duplicate/out-of-order events using monotonic versions. Never use a fire-and-forget controller thread as the sole session-revocation mechanism.

### 8.2. Illustrative transaction pseudocode (not a complete SQL migration)

```sql
BEGIN;

UPDATE account_tenant_permissions
SET permission_granted = FALSE
WHERE account_id = :account_id
  AND tenant_id = :tenant_id
  AND permission_code = 'APPROVE_PAYMENT';

UPDATE account_access_state
SET entitlement_version = entitlement_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = :account_id;

INSERT INTO security_outbox
    (event_id, event_type, account_id, tenant_id,
     reason_code, occurred_at)
VALUES
    (:event_id, 'ENTITLEMENT_REVOKED', :account_id,
     :tenant_id, 'ADMIN_REVOKE', CURRENT_TIMESTAMP);

COMMIT;
```

This is **SQL pseudocode**: table/column names, duplicate suppression, version handling, and transaction isolation depend on your RDBMS. Production must verify affected row counts, idempotency keys, target/tenant existence, admin authorization, and auditing. Never allow users to send raw SQL or forge event reasons to revoke others.

### 8.3. "Role removed" may not require a system-wide logout

If a user only loses `APPROVE_PAYMENT` in tenant A, they may continue reading reports in tenant B per policy. Preferred approach:

- Record the lost permission in the authoritative store.
- Increment `entitlementVersion` and clear cached permissions.
- Every protected action checks fresh effective authorization.
- If the app relies solely on a role snapshot in `Authentication` without live authorization, **you must invalidate sessions or regenerate authentication** to purge the old grant.
- If account compromise is suspected, incident policy may revoke **all** sessions/tokens to be safe.

Accurate scoping minimizes operational disruption while never retaining revoked permissions.

## 9. Spring Security: Sessions, SecurityContext, and Login Checks

### 9.1. Key components to know

| Component | Function | Limitation for revocation |
| --- | --- | --- |
| `AuthenticationProvider` | Verifies credentials at login | Does not recheck directory on every request |
| `UserDetails` | `enabled`/`locked`/`expired` and authorities | Cached `Authentication` may hold stale state |
| `SecurityContextHolder` | `Authentication` in current request thread | Clearing current context does not delete all sessions |
| `SecurityContextRepository` | Saves/loads context across requests | Does not auto-refresh directory permissions |
| `HttpSession` | App's browser session | `invalidate()` affects only the called session, not all devices |
| `SessionRegistry` | Tracks sessions in Spring Security | Depending on implementation, may be in-JVM only |
| `SessionInformation.expireNow()` | Marks session expired | Typically enforced by `ConcurrentSessionFilter` on the next request, **not an immediate Redis key delete** |
| `Spring Session` | Uses Redis/JDBC/etc. to store sessions | Requires proper principal indexing to look up by user |
| `FindByIndexNameSessionRepository` | API to find sessions by principal index | If index is missing/wrong principal, returns empty even when sessions exist |
| `AuthorizationManager` / `@PreAuthorize` | Checks permissions | If relying only on cached `GrantedAuthorities`, can still go stale |

### 9.2. Local logout is not global revocation

```java
// This is a Spring Security DSL (fragment), not a complete app.
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true));
```

Normally, when a user logs out of one browser session, Spring clears `Authentication` and destroys the local `HttpSession`. However:

- It is not a command to revoke all sessions of the user across all devices.
- It does not automatically clear the SSO session at the IdP, CAS TGT, or AD/KDC tickets.
- It does not automatically revoke refresh tokens or issued JWT access tokens at the Authorization Server.
- With CSRF enabled, local logout should use **POST with a CSRF token** to prevent logout CSRF.
- Deleting the session does not stop the browser from establishing a new session if IdP SSO remains alive.

## 10. Spring Session Redis: Deleting Sessions by Principal in a Cluster

For multi-pod server-side Spring Security apps, **Spring Session Redis Indexed** lets all pods share session visibility. Session deletion must match the **exact principal name actually indexed by Spring Session**.

### 10.1. Dependencies and Redis configuration

In a Spring Boot 3.x / Java 17 project with an appropriate parent/BOM, add this `pom.xml` fragment:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
  </dependency>
</dependencies>
```

Sample `src/main/resources/application.yml`:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example.org
      port: 6379
      ssl:
        enabled: true
  session:
    timeout: 30m
    redis:
      repository-type: indexed
      namespace: "security:portal:sessions"

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**This is a topology example**; replace DNS/credentials/secret manager settings and secure Redis with TLS, auth, ACLs, and network policies. `repository-type: indexed` selects `RedisIndexedSessionRepository` (verify for your Spring Boot/Spring Session version) instead of the basic Redis repository which **does not** natively support finding sessions by principal. `namespace` isolates sessions across multiple apps sharing Redis.

If using plain `RedisSessionRepository` (default in some Spring Boot setups) or a custom store without a principal index, `FindByIndexNameSessionRepository` may not be provided. **Never fall back to scanning Redis with `KEYS *`** in production to hunt for sessions—it is expensive, risks touching other apps' keys, and is unsafe.

### 10.2. Determining the exact principal value

Spring Session defines `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME`. It can extract the principal from the session's `SPRING_SECURITY_CONTEXT` when integration/indexing is properly configured; the Spring Session API also allows explicitly managing index data per application strategy.

**Common pitfall:** From OIDC, `Authentication#getName()` may be `sub` rather than the local `accountId`. From SAML it may be `NameID`; from LDAP username it may be `sAMAccountName`. Two different issuers can emit the same `sub` or the same `alice`. Therefore:

- Verify the **exact actual index value** stored in Spring Session records.
- Prefer setting the principal name in `Authentication` to the mapped **internal stable account key** for that app, or maintain a separate session index mapped by `accountKey`.
- If the auth principal remains an external name, look up the verified **issuer+subject→accountKey** mapping and query those exact index values—never delete another user's sessions because of a matching email.
- If per-tenant revocation is required, add custom session index/metadata and verify scope, or revoke the account's sessions more broadly per clear policy; do not assume `findByPrincipalName` distinguishes tenants.

**Mandatory testing:** Log in from two browsers, confirm lookup returns both session IDs for the test principal; confirm logging out one browser does not delete another user's sessions; test revocation across pods.

### 10.3. Service deleting sessions by index, Java 17+ Spring

File `src/main/java/com/example/security/AccountSessionRevoker.java`:

```java
package com.example.security;

import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public final class AccountSessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public AccountSessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    /**
     * principalIndexValue is the ACTUAL principal value stored
     * in the Spring Session index, not a raw email from the browser.
     *
     * Call only after security-admin authorization and
     * accountKey -> principalIndexValue have been verified.
     */
    public int deleteAllIndexedSessions(String principalIndexValue) {
        if (principalIndexValue == null ||
                principalIndexValue.isBlank()) {
            throw new IllegalArgumentException(
                "A verified principal index value is required");
        }

        Map<String, ? extends Session> found =
            sessions.findByPrincipalName(principalIndexValue);

        for (String sessionId : found.keySet()) {
            sessions.deleteById(sessionId);
        }
        return found.size();
    }
}
```

Requires a real Spring Session indexed repository bean. `deleteById` removes the session record; old session cookies may remain in the browser, yet **no valid session is found** in the shared store. Browser-facing APIs will observe unauthenticated/401 or a login redirect depending on app configuration.

**Mandatory caveats:**

1. The returned count is the number of session IDs **found in that snapshot**, not a certificate that every session/token across the whole system is revoked.
2. If the principal index is missing or wrong, an empty map does not prove the user has no sessions.
3. If the user concurrently creates a new session, lookup-then-delete has a race. **Set the authoritative revoked/disabled flag or bump the security epoch first**, blocking new auth/session reuse, and use cleanup as the secondary step.
4. If a request already loaded its context before `deleteById`, it may proceed until the next policy check; fence at the business action.
5. With Redis Cluster, Spring Session docs note caveats around keyspace events and cluster nodes for session indexes/cleanup events; verify your version/topology rather than assuming indexes are flawless.
6. If `RedisIndexedSessionRepository` uses a low TTL or a session just expired, the snapshot map and actual count may differ; test semantics/idempotency.
7. Never expose this method as an arbitrary browser `GET /admin/revoke?principal=...`. Admin APIs require phishing-resistant MFA, scoped authorization, CSRF/anti-replay, auditing, and verification.
8. Never wipe other RPs'/apps' sessions via `FLUSHDB`/wildcard deletes; stick to the app's namespace/index.
9. If the app holds identity in WebSockets, scheduled jobs, or offline tokens, deleting web sessions **does not** close them automatically; build separate control planes.
10. If an event retries, `deleteById` must never re-grant permissions; revocation must be idempotent and account state remains the source of truth.

### 10.4. SecurityFilterChain example for web sessions

File `src/main/java/com/example/security/WebSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(
            HttpSecurity http,
            AccountAccessLookup accountAccess) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // Check account status AFTER authentication filters,
        // BEFORE AuthorizationFilter. Does not replace tenant/resource
        // authorization and is not credential validation.
        http.addFilterBefore(
            new AccountStatusFilter(accountAccess),
            AuthorizationFilter.class);

        return http.build();
    }
}
```

**This is an illustrative configuration for web login.** It requires a real provider/`UserDetailsService`, session persistence, CSRF/HTTPS, Redis, and a secured `AccountAccessLookup` implementation; it is not a complete runnable app on its own. For `oauth2Login`, `saml2Login`, or CAS/SPNEGO federation, substitute the appropriate authentication mechanism—do **not** assume `formLogin` is required in SSO.

## 11. Blocking Old Sessions When an Account Is Locked: Per-Request Check

Event-driven session deletion is necessary, yet during the propagation window a request-path **account-status gate** prevents disabled users from continuing to operate.

### 11.1. Authoritative lookup contract

File `src/main/java/com/example/security/AccountAccessLookup.java`:

```java
package com.example.security;

public interface AccountAccessLookup {

    /**
     * Return true ONLY WHEN the account is permitted to use the app.
     * Fail-closed when user does not exist, is locked, disabled,
     * or authoritative state cannot be verified.
     *
     * accountKey must be the Authentication's stable internal ID;
     * never use an unverified browser header / email.
     */
    boolean isActive(String accountKey);
}
```

A production implementation can read the account-access DB with a short-TTL cache and tested event invalidation, or call a dedicated authorization service. For high-risk tasks, check permissions at the transaction boundary; `isActive` alone does not tell you action/tenant entitlements.

### 11.2. Filter checks only account status, never self-grants permissions

File `src/main/java/com/example/security/AccountStatusFilter.java`:

```java
package com.example.security;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AccountStatusFilter extends OncePerRequestFilter {

    private final AccountAccessLookup accounts;

    public AccountStatusFilter(AccountAccessLookup accounts) {
        this.accounts = accounts;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        boolean userAuthenticated = authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);

        if (userAuthenticated) {
            // Only valid when Authentication#getName() is already the
            // stable internal account key in this system.
            String accountKey = authentication.getName();

            if (!accounts.isActive(accountKey)) {
                SecurityContextHolder.clearContext();

                HttpSession session = request.getSession(false);
                if (session != null) {
                    session.invalidate();
                }

                response.sendError(
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication no longer valid");
                return;
            }
        }

        chain.doFilter(request, response);
    }
}
```

**Limitations/warnings:**

- `Authentication#getName()` **is not by default the internal account ID** for OIDC/SAML. Before using this, your auth mapper must translate the external identity `(issuer,sub)` or qualified `NameID` into a stable local ID, or the filter must use a verified principal adapter.
- `isActive` should fail closed if the directory/account state is unavailable per policy; a boolean method hides distinctions between DB outage, missing account, lock, or disable, so production should use typed decisions/audits.
- Instantiate the filter inside `SecurityFilterChain`, **not** annotated with `@Component` unless you want Spring Boot to auto-register a duplicate servlet filter outside the security chain.
- `SecurityContextHolder.clearContext()` clears only the current thread; `session.invalidate()` invalidates only the current app session, not other sessions. `AccountSessionRevoker` handles other sessions in the shared store.
- `401` fits resources requiring reauthentication; browser MVC flows may need dedicated login redirect/error UX. Disabled accounts **must not infinitely auto-retry SSO login**.
- The filter runs as requests traverse the chain. A **request already past the filter** or a background job can keep running; sensitive actions need authoritative authorization at commit.
- With cached roles, the filter checks only active status; it **does not** refresh `GrantedAuthorities` when a group is removed. You still need security epochs/entitlement versions or a live `AuthorizationManager`/method security.
- For WebSockets/long-lived streams, scheduled tasks, message consumers, gRPC, and APIs on other security chains, add equivalent enforcement or terminate connections/tasks per policy.
- Never disable CSRF just to simplify a filter; cookie-backed `POST`/`PUT`/`PATCH`/`DELETE` still need CSRF protection.
- This is a **Spring Boot fragment** needing a project, beans, and real provider, unlike the pure Java program in section 16.

### 11.3. Do not place checks solely in the "login success handler"

If you check only in `AuthenticationSuccessHandler`, existing sessions never re-run the success handler. If you check only in an LDAP provider, federated sessions can bypass LDAP. A complete design spans:

```text
LOGIN:     validate credentials + directory/IdP account status
SESSION:   request-time state/epoch checks + current session invalidation
ACTION:    live tenant/resource authorization at commit
EVENT:     durable revocation event + delete indexed sessions + token revocation
```

## 12. `SessionRegistry.expireNow()` and `maximumSessions` Are Not Remote Delete

Spring Security concurrent-session management offers `SessionRegistry` and `SessionInformation`. Example:

```java
// Fragment, used when SessionRegistry already tracks the right principal.
for (var information :
        sessionRegistry.getAllSessions(principal, false)) {
    information.expireNow();
}
```

**Meaning:** `expireNow()` marks `SessionInformation` as expired. `ConcurrentSessionFilter` can detect that on the **next request** and execute logout/invalidation accordingly. Never claim `expireNow()` always deletes the Redis session key immediately or halts already-running requests instantly.

`maximumSessions(1)` governs **concurrent session count**: when a user logs in a second time, default behavior may expire the old session. It **does not run automatically when an admin revokes a role or disables an account**.

### 12.1. Clustered environments

Spring Security's default `SessionRegistryImpl` tracks state **in the node's memory**. Across multiple pods, one node does not inherently know about sessions created on another pod. Spring Session provides `SpringSessionBackedSessionRegistry` to integrate an indexed repository with concurrent-session control:

```java
// Fragment when FindByIndexNameSessionRepository<S>
// and appropriate SessionRegistry/SessionRepository beans exist:
SessionRegistry registry =
    new SpringSessionBackedSessionRegistry<>(indexedSessionRepository);
```

**Distinction:**

- `getAllSessions`/`expireNow` serves an expiry model.
- `findByPrincipalName`/`deleteById` operates on the session repository to delete records.
- Both require accurate principal mapping/indexing and race/fail-closed handling.
- Never instantiate a separate `SessionRegistryImpl` on each pod and claim you have "global logout".

Spring Session Redis Indexed supports lookups, but Redis Cluster keyspace notifications/index cleanup have topology/version caveats; verify documentation and integration tests in HA setups. If the index is wrong, fix indexing before trusting session counts.

## 13. Revoking JWTs, Opaque Access Tokens, and Refresh Tokens

### 13.1. JWT access tokens: a valid signature does not mean the account is still active

A JWT access token may contain:

```json
{
  "iss": "https://op.example.org",
  "sub": "user-42",
  "aud": ["api://finance"],
  "scope": "reports:read payments:approve",
  "iat": 1901613600,
  "exp": 1901617200,
  "jti": "jwt-identifier-example"
}
```

When a Spring Resource Server checks only signature, `iss`/`aud`/`exp`, and scopes, a token can still appear protocol-valid **after the user was disabled or stripped of a role**. Thus, a self-validated JWT **does not automatically have online revocation**.

Strategies:

1. **Short access-token TTL** + refresh tokens with rotation/revocation. Shrinks the risk window, but does not guarantee an **immediate stop** for unexpired access tokens.
2. **Introspection/active check** at the Resource Server when supported by the Authorization Server and token architecture; `active=false` must be rejected. With JWTs, you can add account security epoch/denylist checks, or use opaque tokens for centralized checks.
3. **Denylist by `jti`/token hash** until `exp`, backed by an HA, fail-closed DB/cache; never store raw bearer tokens in logs or readable cache keys.
4. **Account/token version**: token carries a generation; Resource Server checks against authoritative state or a consistency/SLA-bounded cache, rejecting older generations.
5. **Online scope/tenant authorization**: never treat `payments:approve` in an old token as up-to-date permission during risky transactions.
6. **Sender-constrained tokens** like mTLS-bound or DPoP reduce stolen-token usability, **but do not replace revocation**.
7. **Emergency key rotation** invalidates many tokens sharing a key, with wide blast radius; reserve for policy-governed incidents, not routine single-user actions.

A system choosing offline JWTs for latency must define **maximum revocation delay** and per-action risk. Never promise "disabling an account immediately invalidates JWTs" if the RS has no channel for fresh state.

### 13.2. RFC 7009 token revocation does not automatically invalidate all JWTs at Resource Servers

OAuth 2.0 Token Revocation (RFC 7009) provides an endpoint for clients to ask the Authorization Server to revoke a token. The spec requires supporting **refresh tokens** and recommends supporting access tokens depending on deployment. Once a refresh token is revoked, the Authorization Server will not mint new tokens from that token/grant; already-issued self-contained JWT access tokens at an RS may still be accepted unless the RS has revocation state/denylists/introspection.

An **illustrative** request without real secrets:

```http
POST /oauth2/revoke HTTP/1.1
Host: op.example.org
Content-Type: application/x-www-form-urlencoded

token=REDACTED_REFRESH_TOKEN&token_type_hint=refresh_token
```

- Obtain the real revocation endpoint from trusted Authorization Server metadata/config, using HTTPS and proper client authentication.
- `token_type_hint` is only a hint, not proof of token type.
- Never log raw refresh/access tokens in URLs, bodies, tracing, or CI output.
- Per RFC, servers may return 200 even if the token does not exist to prevent token enumeration; **HTTP 200 does not prove all downstream APIs stopped accepting issued access tokens**.
- Never send issuer A's token to issuer B's revocation endpoint.

### 13.3. Opaque tokens and introspection

RFC 7662 allows a Resource Server to ask the Authorization Server whether a token is still `active`.

```text
API receives opaque token
     |
     v
TLS authenticated introspection
  (RS client credentials, trusted AS)
     |
     +-- active=false -> reject
     |
     +-- active=true + aud/scope/expiry/account checks -> evaluate action
```

Watch out for introspection caching: caching `active=true` for 10 minutes means a newly revoked token remains accepted from cache. Cache TTL/invalidation policy is part of your **revocation SLA**; never claim instant introspection if stale caching is enabled.

### 13.4. Refresh-token rotation and token families

On suspected compromise, revoke the current refresh token, the **related token family/grant**, and other devices/sessions per risk. Rotation helps detect reuse, though exact token-family behavior depends on the OP's implementation; never rely on "password changed" to skip explicit grant revocation when policy demands it.

Do not store plaintext refresh tokens in Redis sessions just for debugging convenience. Use a secure token store, encryption/key rotation, auditing, expiry, and data minimization.

## 14. Federated SSO: Logging Out at OP/IdP Differs from Local Session Cleanup

### 14.1. OIDC: RP-Initiated Logout and Back-Channel Logout

OpenID Connect defines several logout capabilities:

- **Local logout**: destroys only the session at the RP application.
- **RP-Initiated Logout**: the RP directs the user agent to the OP's `end_session_endpoint` to terminate OP SSO, subject to OP support/parameters.
- **Back-Channel Logout**: the OP sends a **signed Logout Token** to the RP server-to-server; the RP verifies it and locates/logs out sessions matching `sid` or `sub`.
- **Front-channel logout**: relies on user-agent redirects/iframes per spec and support; limited when the browser closes or cookie policies block it.

Spring Security provides `oidcLogout(...backChannel(...))` for Servlet OIDC RPs in supported versions. Per current reference docs, the default endpoint format is:

```text
POST /logout/connect/back-channel/{registrationId}
```

With OIDC Back-Channel Logout, the Logout Token must be verified per spec: signature, `iss`, `aud`, `iat`/`exp`, `jti`, and `events`, containing `sid` or `sub`, and no `nonce`. When `sid` is present, target that provider session; when only `sub` is present, the RP locates sessions for that user within the issuer/client scope. **Never** accept `GET /logout?sub=alice` from a browser as a trusted global logout.

Example **Spring Security Servlet fragment for versions supporting OIDC back-channel**:

```java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(logout -> logout
        .backChannel(Customizer.withDefaults()));
```

**Do not paste this fragment into a `formLogin`-only app.** It requires `oauth2Login`, a valid `ClientRegistration`, and OP metadata/support. Spring Security notes differences between the default `JSESSIONID` cookie name and Spring Session's `SESSION`; configure `OidcBackChannelLogoutHandler`, session events, and a cluster-appropriate session registry accordingly. Exact APIs vary across Spring Security versions (6.x/7.x); consult the reference matching your dependency.

**Important:** OIDC Back-Channel Logout **does not automatically revoke all OAuth2 access tokens across all Resource Servers**. Logging out web RPs and revoking tokens/grants are two distinct coordinated operations.

### 14.2. SAML 2.0 Single Logout

SAML supports:

- **SP/RP-Initiated SLO**: the app sends `<saml2:LogoutRequest>` to the IdP and processes `LogoutResponse`.
- **IdP/AP-Initiated SLO**: the IdP sends `LogoutRequest` to the SP; the SP verifies signature/issuer/destination/correlation per profile and destroys the local session.
- **`SessionIndex`** from `AuthnStatement` identifies the SAML session between IdP/SP, but is not the browser's `HttpSession` ID.
- SLO can be **partial** if an RP is offline, the browser flow aborts, or a partner lacks `SingleLogoutService` metadata.

Spring Security supports `saml2Logout` when `RelyingPartyRegistration` has signing credentials and matching SLO/IdP metadata. Never accept unsigned XML `LogoutRequest`s to kill another user's session—that is logout CSRF/DoS. Likewise, **SLO does not clear stateless JWTs** issued by other systems.

### 14.3. CAS Global Logout

CAS local logout in App A does not automatically clear the CAS TGT/TGC. The CAS Server supports Single Logout / service notifications per protocol/config, yet each application needs proper CAS SLO integration, session correlation, and failure handling. A consumed `Service Ticket` is not a session ID; you cannot "revoke all sessions by deleting a validated ST".

When an account is disabled in the Directory, the CAS SSO session/TGT may persist depending on policy and caches; coordinate CAS session invalidation and check user status when issuing new STs.

### 14.4. Kerberos/Active Directory

KDC-issued TGTs and Service Tickets have their own lifetimes. Disabling an AD user or changing group memberships does not guarantee **all issued tickets or Spring local web sessions expire immediately**. The KDC may refuse new tickets per domain policy, yet a service app may keep accepting an unexpired service ticket via GSS/JAAS/keytab without querying AD on every request. Manage ticket lifetimes, account lookup/revocation, and local app sessions—especially during incident-driven disables.

**Never rotate an HTTP service account's keytab just to "kick one user"**: service key rotation impacts every user of that SPN, not a single user.

## 15. Concurrency: Resolving Races and Preventing Session Resurrection

### 15.1. Race 1 — login concurrent with revocation

```text
T0 Auth thread reads enabled=true
T1 Admin disables user; commits authoritative state, epoch=2
T2 Auth thread creates HttpSession under old epoch=1
T3 Revocation worker queries sessions that existed at T1 only
T4 New session created at T2 not found in snapshot
```

**Protection:** Bind the session epoch upon successful authentication; right before issuing the session or first business action, recheck the latest epoch/account state; the event worker can delete discovered sessions, while the authoritative gate rejects epoch 1 after T1.

### 15.2. Race 2 — in-flight business request

```text
T0 Alice loads approval page
T1 Alice sends POST /payments/123/approve
T2 Application checks cached ROLE_APPROVER
T3 Admin revokes role at authoritative store
T4 Application commits approval
```

If business rules require zero commits after revocation at T3, **place access checks and the business operation inside the same appropriate transaction boundary**, or use a compare-and-set version/fencing token at commit:

```text
Transaction APPROVE:
  load current AccountAccessState (authorized source)
  assert enabled && nonLocked
  assert tenant membership, effective permission for payment 123
  assert entitlementVersion/current policy at commit boundary
  assert resource state, amount, payee and optimistic lock
  commit approval only if all conditions still hold
```

When directory/permissions live in a different service/database, use a policy store/cache with a strong-enough consistency contract or risk-appropriate commit protocol. **Calling a single LDAP query before multi-second work creates no atomic guarantee.**

### 15.3. Race 3 — missed cache/Redis events

- Outbox worker down: DB account state is disabled while sessions linger in Redis.
- One pod drops an event: its caches retain old authorities.
- Redis Cluster keyspace notifications miss events: stale principal index.
- Mobile app offline: refresh grant revoked yet old access token remains unexpired.
- IdP back-channel logout to RP times out: RP local session remains undeleted.

**Mitigations:** Idempotent durable retries, monotonic versions, bounded cache TTLs, authoritative request/action checks, periodic reconciliation, and measurable SLAs. Never rely on a best-effort event bus without revalidation.

### 15.4. Race 4 — same email across two issuers

```text
Issuer A: (https://op-a.example.org, sub=alice)
Issuer B: (https://op-b.example.org, sub=alice)
```

If sessions are deleted by the string `alice` without distinguishing issuer in the app index, another account's sessions can be wiped by mistake. Map verified identities → stable internal `accountKey`; if one person has two legitimately linked identities, revoke by `accountKey` when targeting the whole account, or scope strictly by issuer/connection when revoking one federation credential.

## 16. Standalone Java 17: Account State, Tenant Permissions, and Session Versions

To demonstrate the logic without a real LDAP/IdP/Spring Session setup, create a **Java 17 console program**. All accounts/sessions in the example live in in-memory test maps—**no password, JWT, SAML, Kerberos, or Redis verification is performed**. The program shows **three distinct outcomes**: revoked role, locked/disabled account, and deleted session IDs.

### 16.1. Example policy

- Account `acct-42` is active with `approve` permission in tenant `red`.
- Session `s1` stores `entitlementVersion=1`.
- Removing the role bumps the version to 2. The old session is considered **stale** and cannot approve.
- A new version-2 session still exists, yet lacks `approve` permission.
- Locking the account blocks requests even while the session ID still exists.
- Revoking sessions removes `s1`/`s2`; a browser sending the old cookie is no longer authenticated.
- Unlocking does not automatically restore the lost role.
- Disabling the account later blocks even fresh sessions.
- Repeating session deletion must be idempotent.

File `AccessRevocationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class AccessRevocationDemo {

    enum Decision {
        ALLOW,
        DENY_NO_SESSION,
        DENY_ACCOUNT_DISABLED,
        DENY_ACCOUNT_LOCKED,
        DENY_STALE_AUTHORITY,
        DENY_PERMISSION
    }

    record Account(
        boolean enabled,
        boolean locked,
        long entitlementVersion,
        Set<String> permissions
    ) { }

    record SessionEvidence(
        String sessionId,
        String accountId,
        long entitlementVersion
    ) { }

    private static final String ACCOUNT = "acct-42";

    private static final Map<String, Account> accounts =
        new HashMap<>();

    private static final Map<String, SessionEvidence> sessions =
        new HashMap<>();

    static Decision evaluate(
            String sessionId, String tenant, String action) {

        SessionEvidence session = sessions.get(sessionId);
        if (session == null) {
            return Decision.DENY_NO_SESSION;
        }

        Account account = accounts.get(session.accountId());
        if (account == null || !account.enabled()) {
            return Decision.DENY_ACCOUNT_DISABLED;
        }

        if (account.locked()) {
            return Decision.DENY_ACCOUNT_LOCKED;
        }

        if (session.entitlementVersion() !=
                account.entitlementVersion()) {
            return Decision.DENY_STALE_AUTHORITY;
        }

        String permission = tenant + ":" + action;
        if (!account.permissions().contains(permission)) {
            return Decision.DENY_PERMISSION;
        }

        return Decision.ALLOW;
    }

    static int revokeAllSessions(String accountId) {
        int before = sessions.size();
        sessions.entrySet().removeIf(
            e -> e.getValue().accountId().equals(accountId));
        return before - sessions.size();
    }

    public static void main(String[] args) {
        accounts.put(ACCOUNT,
            new Account(true, false, 1,
                Set.of("red:approve", "red:view")));

        sessions.put("s1",
            new SessionEvidence("s1", ACCOUNT, 1));

        System.out.println("before=" +
            evaluate("s1", "red", "approve"));
        System.out.println("crossTenant=" +
            evaluate("s1", "blue", "approve"));

        // Admin revokes APPROVE: increment entitlementVersion.
        accounts.put(ACCOUNT,
            new Account(true, false, 2,
                Set.of("red:view")));

        System.out.println("oldAuthority=" +
            evaluate("s1", "red", "approve"));

        sessions.put("s2",
            new SessionEvidence("s2", ACCOUNT, 2));

        System.out.println("freshNoRole=" +
            evaluate("s2", "red", "approve"));

        // Admin locks account; session ID has not been deleted yet.
        accounts.put(ACCOUNT,
            new Account(true, true, 3,
                Set.of("red:view")));

        System.out.println("locked=" +
            evaluate("s2", "red", "view"));

        System.out.println("invalidated=" +
            revokeAllSessions(ACCOUNT));

        System.out.println("oldSession=" +
            evaluate("s1", "red", "view"));

        // Unlocking does not restore approval permission.
        accounts.put(ACCOUNT,
            new Account(true, false, 4,
                Set.of("red:view")));

        sessions.put("s3",
            new SessionEvidence("s3", ACCOUNT, 4));

        System.out.println("unlockedViewer=" +
            evaluate("s3", "red", "view"));

        // Disable account: rejected even though s3 remains in store.
        accounts.put(ACCOUNT,
            new Account(false, false, 5,
                Set.of("red:view")));

        System.out.println("disabled=" +
            evaluate("s3", "red", "view"));

        System.out.println("disabledRevoke=" +
            revokeAllSessions(ACCOUNT));
        System.out.println("repeatRevoke=" +
            revokeAllSessions(ACCOUNT));
    }
}
```

Compile and run:

```bash
javac --release 17 AccessRevocationDemo.java
java AccessRevocationDemo
```

Deterministic stdout:

```text
before=ALLOW
crossTenant=DENY_PERMISSION
oldAuthority=DENY_STALE_AUTHORITY
freshNoRole=DENY_PERMISSION
locked=DENY_ACCOUNT_LOCKED
invalidated=2
oldSession=DENY_NO_SESSION
unlockedViewer=ALLOW
disabled=DENY_ACCOUNT_DISABLED
disabledRevoke=1
repeatRevoke=0
```

**Explanation:**

- `before=ALLOW`: session and account share `entitlementVersion`, holding `approve` on tenant `red`.
- `crossTenant=DENY_PERMISSION`: same user lacks permission in tenant `blue`.
- `oldAuthority=DENY_STALE_AUTHORITY`: role revoked and version incremented; refuses to keep using cached version-1 authority.
- `freshNoRole=DENY_PERMISSION`: fresh version-2 session lacks `approve`, so it is still denied.
- `locked=DENY_ACCOUNT_LOCKED`: blocks without waiting for session deletion.
- `invalidated=2`: both session IDs for the account were removed from the demo store.
- `oldSession=DENY_NO_SESSION`: old cookie/session ID is no longer usable.
- `unlockedViewer=ALLOW`: admin unlocks, user still only has `view`.
- `disabled=DENY_ACCOUNT_DISABLED`: session exists, but account is disabled.
- `disabledRevoke=1` and `repeatRevoke=0`: session cleanup is idempotent in the simulation.

**Extremely important limitations:** The demo uses `HashMap` and is not thread-safe, multi-node-safe, or transactional; `entitlementVersion` is simulated. Production requires atomic DB commits, Spring Session Redis/JDBC, a durable outbox, issuer-scoped identities, clock/epoch policies, real account lookups, and real authorization. **Never accept the demo's booleans from a browser as proof of an active account or valid session.**

## 17. Test Matrix: Revoking Permissions, Locking Accounts, and Session Invalidation

Test in staging with **at least two browsers/devices, two pods, two tenants, and one API client**. Each test must clearly distinguish account source, local session, IdP session, access/refresh tokens, and authorization.

| Case | Test action | Expected result |
| --- | --- | --- |
| **ACTIVE login** | Active user with permissions logs in anew | Succeeds with right authorities |
| **Directory LOCKED, new login** | Lock account before login | Provider/IdP denies per policy |
| **Directory DISABLED, new login** | Disable before login | No local authenticated session created |
| **Directory DISABLED, old session** | Log in, then disable, send new request | Controlled 401/redirect or deny; session cleaned up |
| **Directory LOCKED, old session** | Lock while user holds cookie | Per policy; if containment required, deny/revoke |
| **Role removed, old session** | Remove APPROVE while session remains | Cannot approve; never relies on cached `GrantedAuthorities` |
| **Role removed in one tenant** | Revoke tenant A while retaining tenant B | A denied; B works per policy, no cross-tenant leak |
| **AD account status changed** | `ACCOUNTDISABLE` flag via directory API | App reads right effective state; never assumes raw `UAC == 514` |
| **LDAP lockout vs. disable** | Trigger temporary lockout | Proper behavior per directory policy; not confused with permanent disable |
| **Nested AD group** | Remove membership in child group | Effective roles from nested groups update properly |
| **User renamed/email changed** | Change email/UPN | Does not revoke another account due to email collision |
| **Same username across two issuers** | Users `alice` from OP A and B | Scoped by `issuer+sub`; never deletes wrong user's session |
| **Two browser sessions** | Log into A and B, revoke account | Neither session remains usable |
| **Two pods sharing Redis** | Session A created on pod1, revoked on pod2 | Session A deleted/denied when hitting pod1 |
| **Missing principal index** | Session lacks principal index | Revoker does not treat `0` as success; fix index/add detection |
| **Only current `HttpSession` invalidated** | Log out browser A | Browser B remains unless policy revokes all |
| **`SessionRegistry.expireNow`** | Mark session expired | Handled on next request via filter/strategy; never claim instant hard delete |
| **Login/revoke race** | Login concurrent with admin disable | Session minted under old epoch is still blocked |
| **In-flight approve request** | Revoke after initial check, before commit | Business commit denied/rolled back if policy requires immediacy |
| **Outbox worker down** | Disable commits, event has not reached worker | Active request gate/epoch still denies |
| **Duplicate/out-of-order events** | Deliver v3 then v2 | Does not lower `entitlementVersion` or restore role |
| **Redis Cluster index cleanup** | Expiry event on another node | Reconciliation and fail-closed exist; never assume flawless indexes |
| **OIDC SSO still alive** | Delete local session, browser re-logs in | Account state gate/IdP policy withholds new access |
| **OIDC Back-Channel Logout** | OP sends signed Logout Token with valid `aud`/`sid`/`sub` | RP revokes matching sessions for issuer/client |
| **Forged Logout Token** | Bad signature/`aud`/`issuer`/`events`/`jti` policy | Reject; never log out other users |
| **Signed SAML SLO** | IdP sends valid `LogoutRequest` | SP verifies and logs out the right session |
| **Unsigned/foreign-issuer SAML SLO** | Spoofed request hits SLO endpoint | Reject; never destroy other sessions |
| **CAS local logout** | App local logout | CAS TGT/TGC may persist; test separate SLO mechanism |
| **Old Kerberos ticket** | AD user disabled while holding service ticket | Never assume ticket dies instantly; app gate/role policy denies |
| **Unexpired JWT** | Disable user, send previously issued access JWT | If immediacy required, RS denies via status/epoch/introspection |
| **Revoked refresh token** | Call token endpoint with revoked refresh token | No new access token issued |
| **Inactive opaque token** | Introspection returns `active=false` | RS returns 401 |
| **Stale introspection cache** | `active` cached prior to revocation | Blocked within configured SLA/invalidation |
| **WebSocket/long-lived stream** | Lock account mid-connection | Disconnect/recheck per policy without waiting for a web GET |
| **Queued background job** | User queued export before revocation | Job checks current entitlement before execution/commit |
| **Audit/on-call** | Admin bulk-revokes account | Evidence captures event ID, actor, scope, latency, and outcomes |
| **Re-enable account** | Unlock after incident | Never auto-restores previously revoked roles/sessions/grants |
| **State store outage** | DB unavailable during high-risk action | Fail closed; never fall back to old admin authority |
| **Multi-device revocation** | iOS app + browser + API token | Clear policy coverage across local sessions and refresh/access tokens |
| **Admin API abuse** | Non-admin calls revoke endpoint | 403, CSRF/MFA/rate limit/audit per policy |

**Pass criterion:** Do not stop at seeing a "You have been logged out" page. Test the **old session cookie**, **unexpired access token**, **refresh token**, **action in the target tenant**, and **requests to another pod**. For role revocation, the requirement is accurate business authorization; a full-screen logout may be a side effect, never sufficient proof that permissions are gone.

## 18. Security Logging and Incident Investigation

Suggested security audit record revealing no credentials:

```json
{
  "eventId": "evt-example-42",
  "eventType": "ACCOUNT_DISABLED",
  "accountKey": "acct-42",
  "issuerOrRealm": "directory-corp",
  "scope": "ACCOUNT",
  "tenantId": null,
  "actorKey": "sec-admin-17",
  "newEntitlementVersion": 23,
  "effectiveAt": "2030-05-10T08:00:00Z",
  "sessionRevocation": {
    "sessionsDiscovered": 3,
    "sessionsDeleted": 3,
    "verified": true
  },
  "tokenRevocation": {
    "refreshTokenFamiliesRequested": 2,
    "completed": false
  },
  "requestGatePolicy": "deny-if-disabled-or-stale",
  "traceId": "trace-example"
}
```

The payload above is an **illustrative example**, not live system state. Never log raw `SESSION`/`JSESSIONID` cookies, JWT access/refresh tokens, `SAMLResponse`s, LDAP passwords, CAS TGTs, Kerberos keytabs, or unnecessary PII.

**A revocation report should state clearly:** "account disabled at T0; HTTP sessions deleted at T2; refresh-token families revoked at T3; JWT RS epoch enforcement enabled; SAML/other RPs pending confirmation" rather than claiming "all logged out" without evidence.

### 18.1. Metrics to monitor

- `revocation_event_lag_seconds`: T0 → event consumer ack, p95/p99 distribution.
- `session_revoke_lookup_count`, `deleted_count`, `index_miss_count`: never treat `0` as unconditional success.
- `disabled_account_request_denied` / `stale_authority_denied` by application/pod (without logging overly sensitive IDs).
- `refresh_grant_revoke_success`/`failure` by issuer/client.
- `jwt_revocation_or_epoch_check_latency` and failures; cache TTL/consistency.
- `oidc_backchannel_logout_valid_invalid`, `saml_slo_signature_failures`, CAS logout failures.
- `cross_tenant_permission_denied` and unexpected success anomalies.
- `outbox_retries`/`dead_letter_age`, DB/Redis availability.
- `long_lived_connections_disconnected`, queued job cancellation count.
- Unauthorized admin revocation calls and scope violations.

Never advertise an unmeasured SLA. For sensitive APIs, business stakeholders should sign off on the maximum revocation window, and tests must prove it under load, clustering, and IdP outages.

## 19. Runbook: Revoking Permissions and Handling Compromise

### 19.1. Case A — removing approval permission in one tenant

1. Verify the actor/admin is authorized to manage **that exact tenant** with MFA and change approval.
2. Resolve the target by stable internal account ID and verified source identities—never search by email alone.
3. Update permissions for tenant A and increment `entitlementVersion` in the authoritative transaction; write outbox/audit.
4. Clear cached entitlements and enforce live authorization checks on `approvePayment` at transaction commit.
5. If apps still rely on cached role snapshots, revoke relevant sessions or force authentication refresh.
6. Verify requests with old cookies/tokens **cannot approve** in tenant A; tenant B continues only if membership remains.
7. Inspect activity logs and pending approvals to ensure none committed after T0.
8. Confirm event consumers processed the right version and reported outcomes.

### 19.2. Case B — account locked for low/temporary risk

1. Determine whether the lockout is anti-brute-force policy or an admin security block.
2. If blocking only new authentication, document policy scope; if compromise is suspected, escalate to full-account containment.
3. Never auto-unlock via an app timer while the directory account still reports locked.
4. Verify new authentication is blocked; if policy requires, invalidate active web sessions and related grants/tokens.
5. Require recovery/step-up/review before unlocking; never restore unapproved revoked roles.

### 19.3. Case C — suspected account compromise or offboarding

Suggested containment order:

1. Open an incident/ticket and lock/disable the account in the **authoritative directory/IdP**.
2. Advance `sessionsValidAfter`/security epoch and enforce immediate denial at apps/APIs.
3. Revoke app web sessions across all managed pods/RPs; verify using an old cookie.
4. Revoke refresh tokens/grants and OP sessions, using Back-Channel/SAML SLO where configured; identify unconfirmed RPs.
5. For unexpired JWT access tokens, enforce RS denylist/epoch/introspection per risk; do not wait for expiry if SLA forbids it.
6. Terminate/isolate WebSockets, long-running jobs, offline access, API keys, and device sessions per inventory.
7. Audit permission/tenant actions during the suspected compromise window; rotate related credentials/secrets if needed.
8. Verify the account cannot log back in via another federated link, alias/guest account, or old SSO.
9. Record timestamps/traces/outcomes and obtain confirmation from RP owners.
10. When re-enabling, follow a separate approval workflow and **never auto-restore prior sessions, refresh tokens, or high-risk roles**.

**Never wipe the entire Redis database or rotate all OIDC signing keys just to lock one user** when scoped account/session/token controls exist. Those actions carry a massive blast radius and require incident commander and security policy approval.

## 20. Review Questions with Answers

**Q1.** The Directory sets `enabled=false` for Alice, yet her browser still holds a Redis `SESSION` authenticated by Spring Security earlier that morning. Is that an LDAP bug?

**Answer:** Not necessarily; updated LDAP status does not automatically destroy local app sessions. You need request-time status checks and/or session deletion via Spring Session, then test with the old cookie.

**Q2.** An admin removes `ROLE_APPROVER`, yet the app only checks `hasRole('APPROVER')` against the cached `Authentication`. Can the user still execute the action?

**Answer:** Potentially yes. Refresh authorities/`entitlementVersion`, invalidate sessions, or run live permission checks at action/commit time.

**Q3.** Does `SessionInformation.expireNow()` mean the Redis key was deleted immediately?

**Answer:** Not by default. It marks the session expired in the registry; enforcement typically happens on the next request via `ConcurrentSessionFilter`. Even with explicit session deletion via a repository supporting `deleteById`, you must still handle races and in-flight requests.

**Q4.** The app stores sessions in Redis—does calling `findByPrincipalName("alice")` guarantee deleting all of Alice's sessions?

**Answer:** No. You need an indexed repository and the right index value, stable internal identities, and issuer mappings; sessions on other RPs or standalone JWTs may still persist.

**Q5.** The OP revoked the refresh token. Will unexpired issued JWT access tokens definitely be rejected by every API?

**Answer:** No. Self-validated JWTs at an RS may keep passing; you need RS revocation awareness, a denylist/epoch/introspection, or an accepted TTL window per policy.

**Q6.** A SAML IdP sends an unsigned `LogoutRequest` through the browser. Should you trust it and log out multiple users?

**Answer:** No. The SP must validate SAML SLO against IdP issuer, signature, destination/correlation, and configured metadata; forged requests must not cause logout DoS.

**Q7.** An OIDC Back-Channel Logout Token contains only `sid`, without `sub`. What should the RP do?

**Answer:** If the token is valid per spec and client/issuer scope, terminate sessions correlated with that provider session `sid`; do not guess or log out other users. When only `sub` is present, scope by issuer/client to terminate that user's sessions.

**Q8.** A user loses permissions in tenant A while keeping permissions in tenant B. Must the entire account be disabled?

**Answer:** Not necessarily. Policy may revoke per tenant and enforce accurate permissions/epochs. However, compromise incidents may require locking the entire account.

**Q9.** A revoke event is published while the Redis worker is temporarily down. Can sensitive actions proceed using cached roles until the queue recovers?

**Answer:** No, when immediate revocation is required. Enforce authoritative state/version fences at the action or fail closed; async cleanup is only secondary reinforcement.

**Q10.** A user is disabled in AD while an issued Kerberos Service Ticket remains unexpired and the Spring app still holds a session. Can we conclude the user is blocked?

**Answer:** No. Kerberos tickets and app sessions have independent lifecycles; enforce account status checks, clear sessions/credentials, and verify empirically.

## 21. Production Acceptance Checklist

- [ ] Clearly distinguish **revoke permission**, **lock account**, **disable account**, **local session invalidation**, **IdP logout**, and **refresh/access token revocation**.
- [ ] Every action has an owner, threat/risk level, scope (account/issuer/tenant/device/session), policy, and target latency/SLA.
- [ ] Directory/AD/LDAP status is read per proper schema and policy—never compare raw `userAccountControl==514` or equate lockout with disabled.
- [ ] Effective directory groups and nested memberships are updated, not just a naive `memberOf` cache.
- [ ] Revocation keys use a stable internal `accountKey` linked to `issuer+subject`/immutable directory ID, never email/username alone.
- [ ] `UserDetails.isEnabled`/`isAccountNonLocked` are enforced at login, with separate protection against stale sessions.
- [ ] Disabled/locked users cannot use existing sessions to continue forbidden actions.
- [ ] Role/permission revocations bump `entitlementVersion`/authoritative authorization, with action-time checks at the right tenant/resource.
- [ ] Transactions/outbox/idempotent events, monotonic versions, retries, and reconciliation handle down consumers.
- [ ] Spring Session Redis/JDBC indexing and `FindByIndexNameSessionRepository` are verified in a cluster with exact principal names.
- [ ] Session revoker does not just invalidate the current `HttpSession`; multi-device/multi-pod revocation exists where required.
- [ ] `SessionRegistry.expireNow` is not confused with instant hard deletion.
- [ ] Session deletion handles races and blocks sessions minted before/after T0 using a security epoch.
- [ ] RPs handling in-flight requests/jobs/WebSockets fence at commit or enforce connection lifecycle policies.
- [ ] OIDC Back-Channel Logout / RP-Initiated Logout are configured when supported by the OP; Logout Tokens are verified and scoped by issuer/client/`sid`/`sub`.
- [ ] SAML SLO has metadata/keys and validates signatures/correlation; never promise success on offline RPs.
- [ ] CAS TGT/TGC and Kerberos tickets are recognized as separate from local app sessions.
- [ ] Unexpired JWT access tokens are bounded by TTL or RS revocation/epochs; refresh grants are revoked separately.
- [ ] Opaque token introspection `active` checks and cache TTLs are factored into the revocation SLA.
- [ ] Unverified tokens/headers/emails are never used to delete another user's sessions.
- [ ] Admin revocation APIs enforce MFA, scoped/tenant authorization, CSRF/anti-replay, rate limiting, and auditing.
- [ ] Never run `FLUSHDB`/broad Redis key deletes or global signing-key rotations for a single-user incident without approval.
- [ ] Session cookies set appropriate `Secure`, `HttpOnly`, and `SameSite`, and app logout uses CSRF-safe POST for browsers.
- [ ] Redis/DB/queues/TLS are secured, and credentials/tokens/session IDs never appear in logs.
- [ ] Tested across multiple devices, pods, issuers, tenants, and token/grant types, including login/revoke races.
- [ ] Negative tests pass: disabled-account old cookie fails, revoked-permission old JWT fails within SLA, stale role cannot commit.
- [ ] Alerts exist for revoke lag, index misses, expired sessions, OP logout failures, stale JWT authorization, and outbox backlogs.
- [ ] Re-enabling an account requires approval and **never** auto-restores previously revoked roles/grants/sessions.
- [ ] Offboarding/incident runbooks define T0–T4 and acceptance evidence across all downstream systems.

**Conclusion:** Within **Directories and Accounts**, revoking permissions, locking accounts, and invalidating active sessions must be designed as **a cross-system security lifecycle**. The Directory governs status and entitlements; the IdP/Authorization Server manages SSO sessions and token grants; the Spring app manages `SecurityContext`/`HttpSession`; and the Resource Server enforces permissions on JWT/opaque tokens. **No single action guarantees every system has revoked access.** A safe architecture requires authoritative account status, monotonic security/entitlement versions, scoped session/token revocation, business authorization at commit, and tests measuring propagation time.

## 22. References

1. [Spring Security – Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContext`, `SessionRegistry`, concurrent sessions, and session expiry.
2. [Spring Security – Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout, `SecurityContextLogoutHandler`, session invalidation, and CSRF.
3. [Spring Session – Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html): `SpringSessionBackedSessionRegistry` and indexed session management.
4. [Spring Session – Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html): `RedisIndexedSessionRepository` vs. `RedisSessionRepository`, indexed repository mode, namespaces, and Redis Cluster caveats.
5. [Spring Session – HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html): session repositories, events, and Spring Security integration.
6. [Spring Session API – FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/FindByIndexNameSessionRepository.html): `findByPrincipalName`/principal index semantics.
7. [Spring Security – UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): `isEnabled`, `isAccountNonLocked`, and credentials/account expiry flags.
8. [Microsoft Learn – UserAccountControl property flags](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/useraccountcontrol-manipulate-account-properties): `ACCOUNTDISABLE`, lockout flags, and `msDS-User-Account-Control-Computed`.
9. [Spring Security – OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): RP-Initiated Logout, Back-Channel Logout, and `sid`/`sub` session correlation.
10. [OpenID Connect – Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): signed Logout Tokens, validation, per-RP sessions, and security.
11. [Spring Security – SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): SP/AP initiated SLO, signing, metadata, and validation.
12. [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoking refresh/access tokens and revocation endpoint behavior.
13. [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` check, RS queries, and token metadata.
14. [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token protection, PKCE, and authorization server/resource server security practices.
15. [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature/issuer/claims validation and roles.
16. [Spring Security – Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): token introspection integration.
17. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege, and resource/tenant authorization.
18. [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation, cookies, and lifecycle.
19. [NIST SP 800-63B – Digital Identity Guidelines, Authentication and Lifecycle](https://pages.nist.gov/800-63-4/sp800-63b.html): account/session handling, reauthentication, and risk-based requirements.
