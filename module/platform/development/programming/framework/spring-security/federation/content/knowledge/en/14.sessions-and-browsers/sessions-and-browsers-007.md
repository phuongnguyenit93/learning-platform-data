# Permission Changes or Account Locking While a SAML 2.0 Application Session Remains Active

## 1. Real-World Problem: IdP Locked the Account Yet the Application Still Allows Access?

Suppose an employee logs into a Spring Boot portal via SAML 2.0 at **09:00**. The IdP authenticates the user and sends a validly signed `SAMLResponse`. Spring Security creates an `Authentication`, stores it in `SecurityContext`, and maintains an HTTP session at the **Service Provider (SP)**. At **10:00**, an administrator downgrades their permission from `PAYMENT_APPROVE` to read-only, or locks the account in the identity system. At **10:01**, the browser still holds the SP session cookie and submits a payment approval request.

Critical question: **Does Spring Security automatically know the account was locked or the permission was revoked?** In a standard session model, **not by default**. Spring Security restores the saved `Authentication`; `GrantedAuthority` instances created at login may still reflect the stale permission snapshot. SAML Web Browser SSO **does not continuously query the IdP** for account status on every request to the SP.

This lesson belongs to **Spring Security - federation → Sessions and browsers**, focusing on permission changes and account locking **while the application session still exists**; do not confuse this with the behavior of a brand-new SAML login.

### After This Lesson, You Can

1. Distinguish the **IdP session**, **SP session**, `SAML Assertion`, `SecurityContext`, `Authentication`, and business authorization data.
2. Explain why locking an account at the IdP or changing groups/roles **does not automatically update SP sessions**.
3. Distinguish **authentication** (who is accessing) from **authorization** (what is permitted right now).
4. Apply three defense layers: **live status/permission checks**, **targeted session revocation**, and **session lifetime/reauthentication**.
5. Understand when Spring Session + indexed session repository or Spring Security `SessionRegistry` is needed and each solution's limits.
6. Design ordered, versioned event handling from IAM/SCIM/HR/IdP systems with anti-replay, anti-drop, and multi-node consistency.
7. Build an `AuthorizationManager<RequestAuthorizationContext>` using live state rather than relying solely on stale authorities.
8. Know how to test account locking, permission revocation, multiple devices, concurrent requests, WebSockets, and post-logout re-SSO behavior.
9. Never weaken security by disabling SAML signatures, dropping CSRF, accepting arbitrary logout URLs, or letting client UI decide permissions.

**Example environment:** Java 17+, Spring Boot 3.x, Spring Security 6.x on Servlet/MVC; notes apply to 7.x where APIs align. Domains `app.example.org`, `idp.example.org`, and sample accounts are strictly for educational purposes.

## 2. Underlying Mechanism: After One SAML Login, the SP Keeps Its Own Session

Diagram of a typical session:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as SAML IdP
    participant D as Application identity and permissions
    B->>SP: GET /payments
    SP-->>B: Redirect to IdP
    B->>I: SAML AuthnRequest
    I-->>B: Login succeeds, SAMLResponse
    B->>SP: POST SAMLResponse at ACS
    SP->>SP: Verify signature, issuer, audience, time, InResponseTo
    SP->>SP: Create Saml2Authentication + SecurityContext
    SP-->>B: Session cookie, access /payments
    B->>SP: GET /payments with SP cookie
    SP->>SP: Restore Authentication from SecurityContextRepository
    SP-->>B: /payments page if authorization allows
    Note over I,SP: Does not query IdP by default on every GET/POST
    D-->>D: At 10:00 user permissions or status change
    B->>SP: POST /payments/approve with old cookie
    Note over SP,D: Separate change checking/management mechanism needed
~~~

### Non-Equivalent Objects

| Object | Typical Data | Lifecycle and Meaning |
| --- | --- | --- |
| **IdP session** | Cookie/session on the IdP domain | Remembers the user at the IdP; the SP neither owns nor automatically deletes it |
| **SAMLResponse/Assertion** | NameID, AttributeStatement, AuthnStatement, Conditions, signature | Login proof checked by the SP at callback; **not a continuous permission-update stream** |
| **Saml2Authentication** | Principal, authorities, serialized response per framework API | Authentication result created by Spring after accepting the Assertion |
| **SecurityContext** | Current `Authentication` | Typically restored from session via `SecurityContextRepository` |
| **HttpSession** | Session ID, context/application state | Can survive after the IdP locks the account; timeout depends on the SP |
| **App account/permission store** | `enabled/locked`, roles, tenant, resource permissions, policy version | **Authoritative current permissions** chosen by the application/IAM |
| **SP browser cookie** | Session ID or configured identifier cookie | Merely references the session; a valid cookie does not prove current permissions |
| **Other access tokens** | JWT/OAuth tokens for other APIs | Have independent lifecycles and revocation; not automatically destroyed by SAML SLO |

**Key point:** with SAML, when the user authenticates at the IdP, the SP may extract attributes/groups/authorities and store them in the session. Later when those attributes change at the IdP, the SP **does not receive an event by default** or compare old SAML Responses against new data. Spring Security performs only the checks the application configures.

## 3. Two Events That Look Similar in UI Yet Differ Technically

### 3.1 Revoking or Changing Permissions

For instance, an employee loses the `FINANCE_APPROVE` permission while still allowed to log in. If the app only uses:

~~~java
.requestMatchers("/finance/approve/**").hasAuthority("FINANCE_APPROVE")
~~~

and `Authentication.getAuthorities()` held that authority since 09:00, the 10:01 request may **still be allowed**. `hasAuthority` inspects authorities on the `Authentication` at request time; it is **not a live query of current permissions at the IdP**.

### 3.2 Locking/Disabling an Account

For instance, the IAM team sets `locked=true` or `enabled=false` at the IdP. That usually affects the **next authentication at the IdP**, yet **does not guarantee** active SP sessions terminate immediately. Without local status data or a trusted update channel, the user can still use the SP session until logout, timeout, or other SP controls intervene.

A well-designed system must decide explicitly:
- Does locking an account at the **IdP** automatically block access on **active SP sessions**?
- Which source is **authoritative** for each application permission?
- What is the maximum permissible revocation latency in seconds/minutes?
- Must **all sessions** be severed, or only sensitive actions denied?
- Who emits **events**, who handles failures, and how is versioning controlled?
- Must **tokens, WebSockets, background jobs, and sessions on other devices** besides HttpSession also be revoked?

No single universal SAML 2.0 API makes every app auto-refresh live permission state without dedicated design.

## 4. Distinguishing Permission Snapshots from Live Permissions

| Check Type | Data Source | Advantages | Risk If Used Alone |
| --- | --- | --- | --- |
| **Authorities in Authentication** | Issued when SP authenticates/maps SAML attributes | Fast, integrates with `hasAuthority`/`@PreAuthorize` | Can become **stale** after permission changes |
| **Live local account DB** | Application's DB/store | Business-aligned permissions, runtime queries, auditable | Requires IAM sync management and DB availability |
| **Central authorization service/policy engine** | PDP/OPA/IAM authorization API | Centralized decisions, picks up new policies | Requires designing for latency, availability, caching, and fail-closed |
| **Event-driven local snapshot** | IAM/HR/IdP/SCIM events update cache/DB | Low latency, reduces IdP queries | Possible lost events, reordering, replay, stale cache |
| **Session invalidation** | Session store/registry | Forces subsequent access to drop old SP authentication | Has a delay window, does not lock IdP, does not replace authorization |
| **Reauthentication** | Fresh SAML flow to IdP | Can pick up IdP state on fresh login | Does not update other sessions/permissions if user has an SP session; insufficient alone |

**Rule:** for high-risk actions such as money transfers, granting privileges, accessing secrets, or exporting sensitive data, check **live account state and current permissions close to action time**. Relying solely on `ROLE_ADMIN` cached in the session from earlier may fail emergency revocation requirements.

## 5. Access Outcomes When a User Is Locked Post-Login

A typical policy table:

| Current State | SP Session | Action | Safe Outcome |
| --- | --- | --- | --- |
| Enabled, authorized | Alive | View permitted data | Allow |
| Enabled, permission just removed | Alive, holds old role | Approve payment | **Deny** per current permissions |
| Locked/disabled | Alive | Any protected resource | **Deny**; per policy also actively revoke session |
| Account not found | Alive | Protected resource | **Deny** if account store is the control source |
| Status store temporarily unreachable | Alive | High-risk action | **Fail closed**; do not trust old authorities snapshot |
| SP session deleted | Old cookie remains | Access protected route | No Authentication; typically redirects to login/challenge |
| IdP session alive, SP session deleted | Browser reopens app | Starts new SSO | IdP may auto-login again; **SP must check live local account** |
| User locked at SP yet unlocked at IdP | IdP still has session | SP receives fresh valid SAMLResponse | Do not grant access if SP policy marks account locked |

**Define status/UX clearly:** a user with Authentication yet lacking permission may receive 403; a revoked session may redirect to login; business exceptions can display a generic disabled-account notice. Do not assume a single fixed HTTP status across every filter chain and entry point.

## 6. Why Doesn't Spring Update GrantedAuthority Automatically?

In the Servlet stack, Spring Security uses `SecurityContextHolder` for the current request and `SecurityContextRepository` to restore/save `SecurityContext` across requests. With session-based login, the `Authentication` inside the session holds the `GrantedAuthority` list mapped at login.

After a SAML login:
1. `Saml2WebSsoAuthenticationFilter` receives SAMLResponse at the ACS.
2. The provider/OpenSAML verifies signature, issuer, audience, conditions, subject, and related constraints.
3. Spring builds `Saml2Authentication` and `Saml2AuthenticatedPrincipal`, optionally mapping attributes to authorities.
4. SecurityContext is saved for subsequent requests per configuration.
5. On later requests, `hasRole`/`hasAuthority` reads authorities from the existing `Authentication`.

There is no default behavior of "before every `hasAuthority`, ask the IdP if the user is still in the group". Doing so would couple the SP to network calls to the IdP and fall outside the normal SAML browser SSO contract.

An attribute such as `group=finance-admin` may be true at **the moment the assertion was issued**, without automatically representing **the present**. The assertion's `Conditions@NotOnOrAfter` is checked at login; it does not mean the SP session self-destructs at that exact instant unless the application enforces a specific policy.

## 7. Three Control Layers That Should Work Together

### Layer A — Check Live Status/Permissions on Incoming Requests

Before processing protected routes or sensitive business methods, check:
- Account is still **enabled**, not **locked** or deleted;
- Not isolated by tenant/organization or employment state;
- Action permission still exists in the **current permission source**, not solely in the Authentication snapshot;
- Target resource (order, bank account, document) is still accessible to the user per object policy;
- If needed, the session's account authorization version is not older than the applied version.

### Layer B — Revoke SP Sessions Upon Trusted Events

When IAM signals a user is locked or permissions are revoked, proactively:
- Delete/invalidate corresponding HTTP sessions via Spring Session indexed repository or a session registry mechanism;
- Evict related authorization/permission caches;
- Revoke app tokens/refresh tokens within application scope if applicable;
- Write audit logs and broadcast events to nodes/workers per contract;
- Mark the account disabled before destroying sessions so subsequent re-SSO **does not reopen access**.

### Layer C — Limit Lifetimes and Force Re-Authentication When Needed

Configure:
- Session idle timeout and absolute timeout (if required);
- SecurityContext session fixation protection and CSRF;
- **Reauthentication/step-up** mechanisms for sensitive actions;
- Permission cache lifetimes (TTL or version) and fail-closed policies;
- Monitoring for sessions still used after revocation timestamps.

**Do not treat Layer C as a substitute for A/B.** If an account lock must take effect within 10 seconds, a 30-minute session timeout cannot satisfy it. If a revocation event is dropped, Layer A still blocks access.

## 8. Spring Security Example: Checking Live State with AuthorizationManager

The following example shows **permission changes in the application state store taking effect on the very next request**, even though the old SAML Authentication still holds previously granted roles. It uses an **in-memory lab account store** for illustration. In production, replace the store with an authoritative source like a database/policy engine and proper IAM synchronization.

### 8.1 AccountPolicy Model

File `src/main/java/com/example/federation/AccountPolicy.java`:

~~~java
package com.example.federation;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.stereotype.Component;

@Component
public class AccountPolicy {

    public record AccountState(boolean enabled,
                               Set<String> permissions,
                               long version) {
    }

    private final ConcurrentMap<String, AccountState> states =
            new ConcurrentHashMap<>();

    private static String key(String registrationId, String subject) {
        return registrationId + "\u0000" + subject;
    }

    public boolean allowed(Authentication authentication, String permission) {
        if (authentication == null || !authentication.isAuthenticated()
                || !(authentication.getPrincipal()
                        instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }

        String principalKey =
                key(principal.getRelyingPartyRegistrationId(), principal.getName());
        AccountState current = states.get(principalKey);

        // Unknown/disabled -> deny, irrespective of stale session roles.
        return current != null && current.enabled()
                && current.permissions().contains(permission);
    }

    // Only a trusted IAM/provisioning component should invoke this method.
    public void applyTrustedChange(String registrationId,
                                   String subject,
                                   boolean enabled,
                                   Set<String> permissions,
                                   long version) {
        String principalKey = key(registrationId, subject);
        states.compute(principalKey, (ignored, previous) -> {
            if (previous != null && version <= previous.version()) {
                return previous; // ignore duplicate or out-of-order changes
            }
            return new AccountState(enabled, Set.copyOf(permissions), version);
        });
    }
}
~~~

**This is Java/Spring code within a project**, not a standalone program run with just `javac AccountPolicy.java`. It requires the Spring Security SAML2 dependency and a principal with a registrationId. There is no fixed stdout. `getRelyingPartyRegistrationId()` and `getName()` are used so **users from multiple IdPs are not accidentally merged** merely by sharing a display name.

**Operational limits and rules:**

- `ConcurrentHashMap` lives solely inside one node's JVM, **does not sync across replicas**, and loses data on restart. Move authoritative state to a database or cache with sync and TTL policies.
- `applyTrustedChange` is not a public HTTP endpoint; invoke it only from an IAM/provisioning component whose source, authorization, and event integrity are verified.
- `version` increments in **an order controlled by the data source per account**, never taken from a client-reported timestamp. Incoming events with lower versions are dropped to avoid overwriting newer state with stale data.
- This demo uses `registrationId + NameID` as the key. Some IdPs issue **transient NameIDs** that change across logins, so production must map to a verified **immutable external subject** scoped to the right tenant; never use arbitrary emails as global keys.
- If an account has not been created in the store, **deny**. In the lab, seed the account via a trusted flow before accessing.
- Every protected route must use `allowed`; avoid leaving a separate endpoint accidentally checking only `hasRole` if the app lacks uniform policy enforcement.

### 8.2 Wiring the Policy into SecurityFilterChain

File `src/main/java/com/example/federation/LiveAuthorizationConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LiveAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            AccountPolicy accounts)
            throws Exception {

        return http
                .authorizeHttpRequests(authz -> authz
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .requestMatchers(HttpMethod.POST, "/payments/**")
                        .access((authentication, context) ->
                                new AuthorizationDecision(accounts.allowed(
                                        authentication.get(), "PAYMENT_APPROVE")))
                        .anyRequest()
                        .access((authentication, context) ->
                                new AuthorizationDecision(accounts.allowed(
                                        authentication.get(), "APP_ACCESS"))))
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

**Meaning:**
- `AuthorizationFilter` evaluates HTTP requests using `AuthorizationManager<RequestAuthorizationContext>`.
- `accounts.allowed(...)` checks **live account state in the store**, rather than relying solely on `Authentication.getAuthorities()`.
- `POST /payments/**` requires the live `PAYMENT_APPROVE` permission; other routes require `APP_ACCESS`.
- When IAM removes that permission from the store, the very next request is denied even if the old Authentication still holds `FINANCE_ADMIN`.
- `permitAll` is strictly for genuinely public endpoints; login/ACS endpoints and SAML filter mechanics must remain active per Spring Security.
- The `POST /payments/**` matcher is illustrative and **does not replace business-layer authorization**: GET routes viewing history, PUT creating/updating, or direct method calls from jobs/GraphQL still need matching checks.
- There is no auto-provisioning policy from IdP data for unknown accounts. If IdP login succeeds yet the app does not know the account, **deny** is intentional.
- The application still needs a Spring Boot main class, real `RelyingPartyRegistrationRepository`, and Spring SAML dependencies; these two classes alone do not provide SSO.

### 8.3 Method-Level Authorization

Securing HTTP routes is only one layer. Services can be invoked by multiple adapters (REST, GraphQL, message consumers, scheduled jobs). For Spring-managed beans, add method security:

~~~java
package com.example.federation;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class PaymentApprovalService {

    @PreAuthorize("@accountPolicy.allowed(authentication, 'PAYMENT_APPROVE')")
    public void approvePayment(long paymentId) {
        // Business service implementation goes here.
    }
}
~~~

This is an **annotation-only illustration**; real method bodies need domain validation/transactions. You must enable **`@EnableMethodSecurity`** on a Spring configuration class:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

- `@PreAuthorize` evaluates against the current `Authentication` and the Spring-registered `accountPolicy` bean.
- Sensitive methods still need authorization checks on **specific objects** (such as account/order/tenant), not just broad permissions.
- If a service method is invoked via **self-invocation** within the same bean, Spring proxy method security may not trigger as expected; design clear boundaries.
- `@EnableMethodSecurity` is not enabled automatically just by including Spring Boot Starter Security.
- For background tasks lacking HTTP Authentication, use a **dedicated service identity and policy**, rather than spoofing user permissions from a stale thread-local SecurityContext.

## 9. Improvements Needed to Take This Example to Production

The lab code above illustrates only the decision check; production must add:

| Area | Why It Matters | How to Design |
| --- | --- | --- |
| **Authoritative source** | App cannot know every IdP change on its own | Sync via IAM/HR/SCIM or query a verified account DB |
| **Immutable subject** | NameID can be transient, emails change, usernames get reused | Map IdP entity/tenant + stable external ID to internal account |
| **Multi-node consistency** | ConcurrentMap is not shared | DB/Redis/policy engine, event fan-out/version tracking |
| **Resource-level permissions** | `APP_ACCESS` alone does not decide whether user owns a payment | Check ownership/tenant/object ACL inside transactions |
| **In-flight requests** | Requests started before an event may finish after locking | Check permissions **near commit**, consider concurrency/locking |
| **Stale cache** | Permission cache may lag behind updates | Risk-based short TTL, event invalidation, versions, or no-cache for sensitive actions |
| **Availability** | IAM/DB outage can break every request | Fail closed for dangerous actions, circuit breakers, clear UX |
| **Session revocation** | Old AuthN may remain authenticated | Delete/expire sessions, audit, yet always keep a live gate |
| **WebSocket/API tokens** | Messages bypass HTTP AuthorizationFilter | Add dedicated message authorization/revocation/token policies |
| **Observability** | User reports "still accessible" need proof | Log event/account-version/hashed session ID, deny metrics, replay-safe audit |

**Bottom line:** do not try to "patch" authorities lists inside every live `SecurityContext` ad hoc without a transactional/invalidation strategy. Those objects live across different sessions, may be serialized, and span multiple nodes; mutating an object on one node does not guarantee updates on others. Evaluating decisions against a live permission source is easier to reason about and safer.

## 10. Revoking Sessions with Spring Session

To make locking an account prevent **existing SP sessions from continuing**, you need a session repository able to look up a user's sessions. With Spring Session + Redis **indexed repository** or an equivalent backend, there is the interface:

~~~java
org.springframework.session.FindByIndexNameSessionRepository
~~~

It provides `findByPrincipalName(principalName)` and `deleteById(sessionId)`. Note that **not every `SessionRepository` supports this index**; Redis requires configuring the indexed repo appropriately (depending on version/module, e.g., Spring Session Data Redis indexed sessions).

### 10.1 Java Class Illustrating Indexed Session Revocation

File `src/main/java/com/example/federation/AccountSessionRevoker.java`:

~~~java
package com.example.federation;

import java.util.ArrayList;
import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class AccountSessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public AccountSessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int revokeByIndexedPrincipal(String principalName) {
        Map<String, ? extends Session> matching =
                sessions.findByPrincipalName(principalName);

        var sessionIds = new ArrayList<>(matching.keySet());
        for (String sessionId : sessionIds) {
            sessions.deleteById(sessionId);
        }
        return sessionIds.size();
    }
}
~~~

**This is a Spring component inside an app with Spring Session configured**, not standalone Java. An **indexed `SessionRepository` bean** is required; otherwise dependency injection fails. In multi-IdP systems, `principalName` may not be unique across tenants/IdPs. **Use this approach only when Spring Session's principal naming policy guarantees global uniqueness for the target account.** Otherwise, build a custom index mapping `(tenant, issuer, immutableSubject)` → set of session IDs, re-verifying ownership before deleting. Never invoke the API with an unvalidated email from an admin form allowing arbitrary session deletion.

Explanation:
1. `findByPrincipalName` queries sessions indexed by the principal name stored by the repository. Suitable for per-account session management in appropriate deployments.
2. `deleteById` removes the session from the store: the next request using the old cookie will fail to restore that SecurityContext.
3. Between finding IDs and deleting them, a new session could be created, or an in-flight request may have already loaded context; this is **not system-wide atomic**. A **live account gate** remains necessary.
4. The "account locked" condition must be written to the authoritative source **before** starting revocation. A subsequent SAML login must not slip through the gate just because the IdP still has a session.
5. Do not treat the count of deleted sessions as proof that every session across other apps or all devices is logged out. It reflects only sessions visible in **this repository** at query time.
6. With Spring Session WebSocket support, deleting/expiring a session can trigger cleanup via events; however, custom connections/workers still need dedicated testing and handling.

### 10.2 Warning on Session Principal Indexing

Spring Session builds indexes from the principal recognized by the integration, typically from SecurityContext or `Principal#getName`. In multi-tenant SAML, two IdPs might both return `name=alice`, or an IdP might change NameID format. If the index uses only "alice", `revokeByIndexedPrincipal("alice")` risks deleting sessions of unrelated accounts. Production should use **globally unique stable principal naming** or a dedicated session-mapping table that verifies issuer/tenant/account ID and caller authorization.

In all cases, revocation operations must:
- Be invoked only by authorized IAM/admin systems;
- Be audited (who, why, which account, which event version);
- Have rate limits and idempotency;
- Never return real session IDs to public clients;
- Never log cookies or raw SecurityContexts.

## 11. How Can Spring Security's SessionRegistry Help?

Besides Spring Session, Spring Security provides `SessionRegistry` and `SessionInformation` for managing sessions/concurrent sessions. Sessions can be marked **expired**:

~~~java
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
~~~

This is only a **snippet**, requiring imports, a configured `SessionRegistry` bean, and a matching principal object; it cannot run standalone. In concurrent session control, `ConcurrentSessionFilter` detects an expired session when the next request passes through the filter and executes logout per configuration.

**Key differences:**

| Mechanism | Effect | Conditions / Limitations |
| --- | --- | --- |
| `SessionInformation.expireNow()` | Marks session expired in registry | Depends on filter/config and registry visibility; does not automatically delete cookies across all nodes immediately |
| `Spring Session deleteById` | Deletes record in session store | Requires indexed repository and right account mapping; in-flight requests may finish |
| `HttpSession.invalidate()` | Destroys the session tied to one request/context | Does not automatically destroy other sessions across devices/nodes |
| `Local logout handler` | Clears current user's local SecurityContext/session | Does not automatically notify IdP or other SPs |
| `SAML Single Logout` | SP ↔ IdP coordination protocol; IdP may coordinate other SPs | Requires metadata, signing, browser support; does not guarantee every device/token |

Do not treat `SessionRegistry` as a cluster-wide distributed session index if it is actually a single-node in-memory map. When Spring Session/Redis manages multiple replicas, verify the exact repository, event propagation, and session expiration strategy. Specifically, when **SAML authentication** bypasses the same session-concurrency setup used by username/password login in a project, verify whether the registry is populated properly.

## 12. Locking at IdP vs Locking at SP: What to Do When States Diverge?

An IAM event may alter:
- The account at the **IdP** (blocking new authentications);
- The account record in the **app** (blocking authorization);
- **Permission sets** in HR/IAM and the SP;
- IdP and SP sessions;
- External API tokens or long-lived connections.

Those changes span **separate systems**. To guarantee no access remains, the minimum policy is that the **SP has a live control source** and rejects disabled accounts, regardless of whether the IdP issues a fresh valid SAMLResponse.

### If Only the IdP Is Locked

- Active SP sessions may experience **no immediate impact** on subsequent requests.
- Once the SP session expires and the browser visits the IdP for a new login, the IdP can reject it if the lock is applied.
- If the IdP session persists and lock status is not re-checked when reusing SSO, check IdP behavior; do not assume "account lock automatically blocks all existing SSO".
- The SP **must not** rely on the IdP returning a failed SAMLResponse to block an **already authenticated SP session**.

### If Only the SP Is Locked

- SP sessions can be deleted and new requests rejected.
- The IdP may still hold a session, so the browser returns with a fresh valid SAMLResponse.
- The SP must **check the disabled account state when granting access/authorization**; otherwise, the user can recreate a session.
- Never treat SAML signature validity as proof the account is allowed to use the application.

### If Both Are Locked

Best handled via a reliable sequence:
1. IAM emits an audited, versioned change.
2. App writes `disabled=true` into its authoritative control store.
3. Caches/live authorizers pick up the new version or refuse to allow from stale snapshots.
4. App revokes managed SP sessions and tokens in scope.
5. IdP blocks new authentications and triggers revocation/SLO if supported.
6. System verifies end-to-end; reports any unconfirmed parts.
7. Duplicate or out-of-order events must never inadvertently "unlock" the account.

This is **coordinated design**, not "Spring Security calling all of these steps automatically".

## 13. Does SAML Single Logout Solve Every Case?

Spring Security supports SP-initiated or IdP-initiated SAML 2.0 Single Logout (SLO). It is useful for **coordinating termination of SAML sessions** among participating parties, yet cannot replace live authorization:

- The IdP must publish `SingleLogoutService` and all sides must configure SLO properly.
- IdP-initiated SLO sends a `LogoutRequest` verified by the SP; the SP can destroy matching local sessions.
- The browser may close tabs, omit cookies, or break the redirect chain; front-channel SLO may fail to complete.
- Apps not participating in SLO and API tokens are not automatically revoked.
- SLO may bind to `NameID`/`SessionIndex`, whose scope does not necessarily cover every session on every device.
- Account locking/role changes **do not mean the IdP automatically sends SLO**. Behavior depends on each IdP's policy/capabilities.

**Conclusion:** for urgent privilege revocation, enforce live permission checks at the SP or a revocation marker directly on requests. SLO is a **complementary** measure, not a sufficient standalone guarantee.

## 14. SAML Assertion, AuthnInstant, and "Is the Session Still Valid?"

Three distinct timestamps:

| Timestamp | Meaning | Must Not Be Inferred |
| --- | --- | --- |
| `AuthnInstant` | IdP-asserted time of authentication | That it reflects the app's live permissions on every request |
| `Conditions@NotOnOrAfter` | Assertion condition deadline evaluated by SP per policy | That the SP HTTP session auto-expires at that exact instant |
| `HttpSession lastAccessedTime/maxInactiveInterval` | SP session activity/idle timeout | That a locked account is immediately blocked from requests |
| `IAM authorizationVersion` | Permission version issued by authoritative source | Equivalent to SAML `InResponseTo` or SAML `SessionIndex` |

If the requirement is "a user cannot approve after permissions were revoked at 10:00", checking live permissions at **approval time** matters far more than knowing the assertion was issued at 09:00.

### Does `ForceAuthn` Help?

`ForceAuthn=true` in `AuthnRequest` asks the IdP for direct re-authentication per SAML, **yet does not refresh an existing SP session** unless a new request is initiated. Nor does it mean MFA, automatically sync app permissions, or alter app-local account state. If step-up is a separate requirement, handle timing/methods and transaction binding; revocation requires the account/permission controls above.

## 15. Active Sessions, In-Flight Requests, and Revocation Latency

A "permission revocation takes effect immediately" policy requires understanding timing constraints.

Suppose:
- 10:00:00 user initiates an approval POST request.
- 10:00:01 `AuthorizationFilter` permits it because the account still holds permission.
- 10:00:02 IAM emits a revocation event.
- 10:00:03 service commits the approval.

If permissions are checked **only once before the controller**, an in-flight request can **still commit after permissions were withdrawn**. Depending on risk requirements, check permissions close to the decisive action, or even within the same transaction as authorization state.

Options:
1. **At-request check:** checks on every HTTP request; bounds the window for new requests.
2. **At-action check:** checks inside the service method immediately before the sensitive operation.
3. **At-commit/transactional check:** combines version/locking/CAS on account state inside the transaction to prevent authorization races.
4. **Event revocation:** invalidates sessions, yet does not guarantee aborting already-started requests.
5. **Absolute TTL:** bounds maximum staleness duration; does not replace immediate revocation.

### Define Clear SLAs

Examples:
- Normal read permissions: revocation latency ≤ 60 seconds via cache TTL.
- Financial approval permissions: requests must read current account state from DB/PDP before execution, **failing closed** if unverifiable.
- Account lock due to compromise: disable app account, invalidate sessions/tokens, and monitor attempts/new logins.
- These values are **policy examples**, not Spring Security defaults or SAML spec mandates.

Never promise "instant across every node" when reality is an eventual-consistent event bus with a 5-minute cache TTL.

## 16. Event-Driven Mechanisms: SCIM/IAM Push Is Not a New SAML Assertion

An IdP may simultaneously provide:
- SAML for **login (authentication)**;
- SCIM for **user/group provisioning/deprovisioning**;
- Webhooks/event streams, directory sync, or admin APIs;
- SLO for **federation logout**.

**Do not conflate SCIM with SAML SLO.** An account-lock event via SCIM or HR update is not a signed `LogoutRequest`. Likewise, a new Login Assertion is not a permission update for every existing session.

Event design:

~~~mermaid
flowchart TD
    A[IAM/HR change: lock account or revoke permission] --> B[Publish authenticated versioned event]
    B --> C[Consumer verifies origin and account identity]
    C --> D[Persist disabled/permissions/version into authoritative app store]
    D --> E[Invalidate authz caches and sessions]
    E --> F[Revoke app tokens and long lived connections as required]
    F --> G[Audit and monitor all replicas]
    G --> H[Next request checks current state and denies if revoked]
~~~

### Reference Event Shape

~~~json
{
  "eventId": "revocation-example-001",
  "tenantId": "finance",
  "idpEntityId": "https://idp.example.org/issuer",
  "subjectId": "immutable-external-123",
  "version": 108,
  "state": "DISABLED",
  "permissions": [],
  "effectiveAt": "2026-11-07T10:00:00Z"
}
~~~

This is **JSON illustrating an internal contract**, not a SAML protocol message or literal SCIM standard payload. Production requirements:
- Producers and consumers are authenticated/authorized (mTLS/signatures, IAM roles, broker ACLs).
- `eventId` prevents duplicate processing; `version` enforces per-account ordering.
- Account keys must bind issuer/tenant and immutable subject; never rely solely on email.
- If events arrive out of order, consumers must not overwrite newer state with older versions.
- If events are dropped, run a **reconciliation job** against the authoritative permission source.
- On transient event failures, retry with backoff, dead-letter queues, alerts, and fail-closed defaults for sensitive permissions.
- When permissions change rapidly in succession, logic must never accidentally **re-enable an account** from a stale event.
- Personal data in audits needs retention/access controls; never log raw SAMLResponses.
- When roles change, never treat old sessions' `Authentication.getAuthorities()` as the new source of truth.

## 17. Permission Versioning Technique: Avoiding Replay and Stale Caches

Attach an `authorizationVersion` to accounts from the authoritative source:

~~~text
Version 21: enabled=true,  permissions=[READ, APPROVE]
Version 22: enabled=true,  permissions=[READ]
Version 23: enabled=false, permissions=[]
~~~

An SP session created at version 21 may store `authzVersionAtLogin=21`. When a request arrives:
1. Locate the account by issuer/tenant/subject.
2. If disabled, **deny** immediately.
3. If the current version exceeds the session's version, **do not use the old authorities snapshot to allow**. Evaluate live permissions, trigger a server-side refresh, or invalidate the session.
4. If the store is unavailable, fail closed for high-risk actions.
5. Audit decisions with versions, omitting raw usernames/permissions if sensitive.

**Warning:** account-version is not a protocol token. If stored in SecurityContext/session, it is purely local state compared against the source of truth; never trust a `version` supplied by the browser. If a user is later re-granted permissions, keep incrementing the version rather than resetting it so old events never look fresh.

### Comparing Cache TTL and Events

| Mechanism | Advantages | Limitations |
| --- | --- | --- |
| 30-second Cache TTL | Simple, bounds staleness while source stays reachable | Can allow within TTL window; unsuitable for immediate revocation |
| Push event + cache invalidation | Usually updates quickly with fewer queries | Events can drop/delay; requires ack/retry/reconciliation |
| DB/PDP check per action | Permissions closest to execution time | Latency/availability impact; needs fail-closed and optimization |
| Version check in distributed cache | Cheap, detects stale sessions | Version must come from authoritative source and stay synced |
| Session deletion | Stops continuation of revoked sessions | Does not prevent IdP re-SSO without an account gate |

A strong design typically combines **event invalidation** with **read-through TTL/reconciliation**, plus direct DB checks on especially dangerous transactions.

## 18. Standalone Java 17: Simulating Permission Revocation and Account Locking

The following program uses only the **Java 17 Standard Library**. It models a session holding an **old permission version** while the account store changes. The output demonstrates why **an active session does not mean active permissions**. It does not implement SAML, create HTTP cookies/sessions, verify XML Signatures, or revoke Redis sessions.

File `SessionRevocationDemo.java`:

~~~java
import java.util.Set;

public final class SessionRevocationDemo {

    record Session(String subject, long authorizationVersion,
                   boolean active) {
    }

    record Account(boolean enabled, long authorizationVersion,
                   Set<String> permissions) {
    }

    static String decide(Session session, Account current,
                         String requiredPermission) {
        if (!session.active()) {
            return "DENY_NO_SESSION";
        }
        if (current == null || !current.enabled()) {
            return "DENY_ACCOUNT_DISABLED";
        }
        if (session.authorizationVersion()
                != current.authorizationVersion()) {
            return "DENY_STALE_AUTHORIZATION";
        }
        if (!current.permissions().contains(requiredPermission)) {
            return "DENY_PERMISSION";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Session oldSession = new Session("subject-123", 7L, true);
        Account before = new Account(true, 7L,
                Set.of("READ", "APPROVE"));
        Account roleRemoved = new Account(true, 8L,
                Set.of("READ"));
        Account disabled = new Account(false, 9L,
                Set.of());

        System.out.println("Before: "
                + decide(oldSession, before, "APPROVE"));
        System.out.println("After role change: "
                + decide(oldSession, roleRemoved, "APPROVE"));
        System.out.println("After lock: "
                + decide(oldSession, disabled, "READ"));

        Session refreshed = new Session("subject-123", 8L, true);
        System.out.println("Refreshed without approve: "
                + decide(refreshed, roleRemoved, "APPROVE"));

        Session revoked = new Session("subject-123", 9L, false);
        System.out.println("Revoked: "
                + decide(revoked, disabled, "READ"));
    }
}
~~~

Run on JDK 17+:

~~~bash
javac SessionRevocationDemo.java
java SessionRevocationDemo
~~~

**Exact** stdout:

~~~text
Before: ALLOW
After role change: DENY_STALE_AUTHORIZATION
After lock: DENY_ACCOUNT_DISABLED
Refreshed without approve: DENY_PERMISSION
Revoked: DENY_NO_SESSION
~~~

**Explanation of output:**
- The initial version-7 session held `APPROVE` and was allowed.
- When the permission was removed, the account version incremented to 8. Even though the old session remained active, the system **refused to approve using version 7**.
- Upon locking the account at version 9, all permissions were denied due to disabled status.
- After refreshing the session to version 8 without APPROVE, it was still denied.
- Once the session was revoked, it was denied before even checking the account.
- The program models policy only. Production needs an authoritative source, race protection, multi-node consistency, and per-resource permission checks.

**Alternative policy choice:** instead of returning `DENY_STALE_AUTHORIZATION` on version mismatch, an application can look up live permissions and decide immediately within the same request, or invalidate the session. Either way, never use stale authorities to auto-allow.

## 19. Safe Production Account-Locking Runbook

When support determines a user must be disabled urgently:

1. **Identify the subject:** locate the internal account via `(issuer/tenant, immutable subject)`, never confusing users with similar emails.
2. **Authorize:** only authorized roles/admins/processes may lock accounts; every lock request is audited.
3. **Write authoritative state first:** set `enabled=false`, increment `authorizationVersion`, and commit.
4. **Broadcast updates:** emit a trusted event so authorization caches and replicas invalidate.
5. **Revoke SP sessions:** query indexed sessions for that exact account, delete/invalidate them, and handle app tokens if needed.
6. **Block re-login:** new validly signed SAMLResponses from the IdP still pass through the account gate; locked accounts cannot access resources.
7. **Sync IdP:** if policy requires, block new SSO and revoke IdP sessions using IdP-supported mechanisms; do not assume SLO always fires.
8. **Post-incident verification:** using an old SP session, test data reads/sensitive POSTs and re-login to confirm all are blocked.
9. **Monitor propagation:** track unconfirmed pods/caches/tokens with retries/reconciliation and alerts.
10. **Controlled unlock:** when authorized, increment version again and restore minimal permissions; never auto-restore old admin roles merely because the user was re-enabled.

If revocation events arrive late, the request-time authoritative state check must still suffice to block once effective. If the source is offline for sensitive actions, fail closed; never open access due to "directory timeout".

## 20. Distinguishing 401, 403, Login Redirect, and "Stale UI"

After account locking, users may encounter several outcomes:

- **403 Forbidden:** request has an authenticated principal lacking permission per `AuthorizationManager` or method security.
- **Redirect to SAML login:** SP no longer has a session/Authentication after revocation; the entry point sends the browser to the IdP.
- **SAML login returns then 403:** IdP session remains and issues a valid response, yet the app account gate still blocks. This signals **the SP blocked properly**, not that locking failed.
- **401 Unauthorized:** common at API authentication entry points depending on configuration; not fixed across every Spring MVC/SAML browser flow.
- **200 on a cached SPA page:** UI still renders old buttons/records in the browser, yet the backend must enforce deny when the user acts or reloads data.

Do not equate "hiding a button" with "revoking permission". Frontend feature flags/menus are UX, **not authorization enforcement**. Users can invoke APIs directly via HTTP tools even when buttons are hidden.

### WebSockets and Long-Lived Connections

A WebSocket/STOMP session may be established while the account still had permissions. If authorization is checked only at handshake time, subsequent messages can keep flowing even after the account is locked. You need:
- Authorization on message/broker destinations if the app uses Spring Security messaging;
- Connection termination mechanisms upon revocation;
- Live permission checks on sensitive operations;
- Review of queue consumers, queued jobs, and running tasks.

Similarly, if SAML login at the SP later mints a JWT for another API, **deleting the HttpSession does not automatically revoke still-valid JWTs**. Token lifetimes, revocation lists/introspection, or other environment-specific designs are required.

## 21. End-to-End Testing: Role Changes While Sessions Stay Alive

**Preparation:** test IdP, test SP, test account with approval permission, versioned account store, Redis/session index if testing revocation, and browser DevTools. Never use real accounts or touch production systems for negative tests.

### Test A — Permission Removed, Session Unexpired

1. Log in while `PAYMENT_APPROVE` is still granted.
2. Confirm `POST /payments/approve` succeeds with valid input.
3. Keep cookie/browser intact; do not log out.
4. Through an authorized test IAM/admin channel, remove the permission in the authoritative store and increment version.
5. Send a new POST to the same API with the old cookie.
6. Expect the SP **not to execute the action**; exact status depends on policy (typically 403).
7. Verify DB has no side effects, audit logs the denial, and old authorities snapshot was not trusted.
8. If UI still shows the button, fix UX separately; backend must still enforce.

**Pass:** removing the permission blocks new sensitive requests without requiring the user to log out.

### Test B — Account Locked While Keeping Cookie

1. Log into SP as the test user.
2. In IAM/app store, mark the account disabled, emit event, and revoke sessions per design.
3. Protected requests using the old SP cookie must be denied or challenged.
4. Verify behavior for in-flight requests at lock time per defined policy.
5. Attempt re-login: even if the IdP can silently SSO fast, the app still denies the disabled account.
6. Verify old cookies/sessions grant no access after browser restore/app restart.

**Pass:** a disabled account cannot use the app via old cookies/SP sessions alone.

### Test C — Multiple Devices, Multiple Nodes

1. Log in with the test account from Browser A, Browser B, and Browser C across multiple pods if available.
2. Revoke the account; verify the index finds all sessions belonging to that account.
3. Send concurrent requests from A/B/C after revocation confirmation.
4. All must hit the same deny policy; no pod may retain old permission snapshots indefinitely.
5. Verify sessions of another tenant/IdP sharing the same username are not deleted by mistake.
6. Audit records show processed session IDs without exposing cookies/session IDs to users.

### Test D — Stale Event Arrives After Newer Event

1. Emit `version=10, enabled=false`.
2. Then replay duplicate version 10 or older version 9 `enabled=true`.
3. Store must stay disabled without flipping state back.
4. Once an authorized admin emits version 11 to re-enable, only permissions granted at version 11 take effect.
5. Audit processed source/version.

### Test E — IAM Unavailable

1. Simulate temporary unavailability of the directory/authorization DB.
2. Verify routes requiring financial permissions fail closed instead of falling back to roles in the old Authentication.
3. Public routes keep operating per policy, with appropriate error messages/circuit breakers.
4. Test recovery; caches must not serve stale state beyond policy limits.

### Test F — Logout and Re-SSO

1. Perform local SP logout while keeping the IdP session.
2. Reopen route: IdP may issue a new SAMLResponse if IdP session remains.
3. Disabled accounts at the app must continue to be denied.
4. If business requires blocking the IdP session, coordinate separate IdP revocation/SLO.
5. Do not conclude "logout failed" solely from fast re-SSO; check app authorization.

### Test G — In-Flight Requests

1. Start a long-running operation.
2. Remove permissions while the request is mid-business-logic.
3. Confirm policy defines up to what point permissions remain accepted.
4. For high-risk operations, perform at-commit or transactional authorization checks to prevent post-revocation side effects.
5. Never test only "new requests" and promise all in-flight requests stop too.

## 22. Automated Testing with Spring Security Test

When using `@WebMvcTest` or MockMvc in a project, distinguish **mock Authentication** from **real SAML login**:
- Policy unit tests can use mock `Authentication` / `Saml2AuthenticatedPrincipal` with a test registrationId and stable subject.
- MVC tests can use `SecurityMockMvcRequestPostProcessors.authentication(...)` or your version's security test utilities.
- A mock user carrying `ROLE_ADMIN` **does not prove** Spring processed SAML Assertions properly; it tests authorization only.
- End-to-end SAML tests still require a test IdP, signed assertions/Responses, and trust setup.
- Tests should verify **side effects** do not happen after permissions are withdrawn, not just HTTP status codes.

Illustrative test snippet (not a standalone test class):

~~~java
// Test setup creates an Authentication representing the test SAML user.
// The policy store initially has permission PAYMENT_APPROVE.
mockMvc.perform(post("/payments/approve").with(authentication(samlAuth))
        .with(csrf()))
       .andExpect(status().isOk());

// A trusted admin/provisioning update removes the permission.
accountPolicy.applyTrustedChange("corp", subject, true,
        Set.of("APP_ACCESS"), 2L);

mockMvc.perform(post("/payments/approve").with(authentication(samlAuth))
        .with(csrf()))
       .andExpect(status().isForbidden());
~~~

Prerequisites to run this snippet: `MockMvc`, static imports `post`, `authentication`, `csrf`, `status`, a valid mock `samlAuth`, and a test controller/service returning `200` when allowed. This is only a **test structure fragment**, lacking declarations to copy-paste and run directly. You do not need signed SAML assertions just to unit-test `AccountPolicy`, yet you must still have **SAML integration tests** for the real authentication path.

## 23. Common Implementation Mistakes

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| User lost permission yet admin API still works | Only checking `hasRole` against authorities snapshot | Check live permissions or versions; add revoked-permission tests |
| Account locked at IdP yet SP session keeps working | IdP did not notify/revoke SP session | Add local disabled marker + revoke sessions + request gate |
| After revocation user re-SSOs right back in | Only deleted SP session; IdP session remains | Check disabled state at SP; coordinate IdP if centralized logout needed |
| New role does not appear until next login | Role mapper ran only when receiving SAMLResponse | Use live permissions or controlled refresh/session invalidation |
| Deleted session on pod A yet pod B stays active | Unshared in-memory sessions/`SessionRegistry` | Use distributed session store, indexing, and consistent policy |
| Revoked wrong user sharing the same email | Identity key lacked issuer/tenant | Use stable external subject + issuer/tenant and verify mapping |
| Lock event undone by older event | Consumer did not compare versions | Monotonic versions, idempotency, reject stale updates |
| Authorization API down yet app allows old roles | Fail-open or unbounded cache | Risk-based fail-closed, retries/circuit breakers, staleness policy |
| UI hides button yet API remains callable | Frontend-only enforcement | Enforce backend authorization |
| 403 after fresh SSO by locked user | App disabled gate denied access | Likely intended behavior; distinguish login from authorization |
| Account deleted yet background jobs still run | Jobs bypass HttpSession/AuthorizationFilter | Check permissions/identity at execution boundaries |
| Session expired yet JWT still valid | Tokens and HttpSession have separate lifecycles | Token revocation/short TTL/introspection |
| Socket keeps receiving messages | WebSocket authorized only at connect, never revoked | Close sessions/enforce messaging authorization |
| SAML assertion still valid yet SP denies | App's live account policy blocks access | Do not confuse denial with signature/issuer validation |
| POST returns 403 unrelated to account lock | Missing CSRF token or method security | Check security logs/matchers/CSRF before diagnosing |
| App restart "loses" account state | Used in-memory ConcurrentMap in production | Move authoritative data to persistent storage |
| IdP logout did not lock app | SLO unconfigured or callback missed | SLO has limits; enforce live access controls |

## 24. Before–After Analysis: Employee Transfers Departments

### Before

An employee belongs to `FINANCE_APPROVER` and logs into the SAML portal on Monday. On Tuesday, an admin transfers them to Audit; the IdP removes the `FINANCE_APPROVER` group, yet the portal's HTTP session stays alive. On the portal, `SecurityContext` still holds the old authority. If the service checks only `hasAuthority("FINANCE_APPROVER")`, the employee can still approve despite losing authorization.

### After

1. IAM updates permissions in the app authorization store by immutable subject/tenant.
2. The app inspects `Authentication` to identify the principal, then checks **current** `PAYMENT_APPROVE` in the service/policy.
3. IAM events invalidate related caches or sessions.
4. Old requests can no longer approve; in-flight actions follow the at-commit policy.
5. The user can still access resources granted under their new permissions if enabled; **there is no need to lock the entire account** just because one permission was removed.

**Lesson:** "revoking one permission" and "destroying all sessions" are two distinct behaviors. You can keep the session and update live authorization, or force re-login per policy; never let sensitive actions rely on stale snapshots.

## 25. Before–After Analysis: Account Locked Due to Security Risk

### Before

The security team locks an account at the IdP after suspecting credential compromise. The SP app keeps an 8-hour session and never receives the lock status. Anyone holding the SP cookie can still call APIs. Blocking new logins **is not enough** to protect active SP sessions.

### After

1. The IAM/incident-response event writes `disabled=true` to the app's authoritative store before triggering revocation.
2. The SP checks the live disabled marker on every protected route requiring an active account.
3. The app deletes/revokes SP sessions (and matching tokens/connections) via the verified identity key.
4. The IdP concurrently locks the account and terminates IdP sessions as supported; SLO is purely additive.
5. New requests are denied even if cookies remain or the IdP emits a new SAMLResponse.
6. The incident team verifies across nodes/devices, handles in-flight transactions per risk, and avoids logging sensitive identity data.

**Lesson:** for emergency locks, **denying at request/action time** is the essential last line of defense. Session invalidation narrows reuse windows, yet does not automatically update every other system.

## 26. Sample Policy Matrix for Choosing a Strategy

| Requirement | Preferred Strategy | Avoid |
| --- | --- | --- |
| Public portal / non-sensitive content | Reasonable session timeout, basic live account gate | Treating timeout as instant account revocation |
| Internal HR/Finance systems | Live HTTP/service permission checks + event invalidation | Relying solely on roles from old SAML assertions |
| Finance with irreversible orders | Live permission check near commit + transaction guard | Checking only when the browser loads the page |
| Emergency lock under attack | Disable authoritative account + revoke sessions/tokens + deny new SSO | Calling only IdP logout and assuming all apps stop |
| Multi-tenant / multi-IdP | Scoped identity key: issuer/tenant + immutable external ID | Transient email/NameID as a global key |
| Multiple pods and devices | Distributed indexed session store, consistent authz, reconciliation | Single-node in-memory registry as cluster-wide truth |
| Frequently changing permissions | Authz DB/PDP/cache with TTL/versions/events | Forcing SAML re-login on every request |
| UX must update promptly after revocation | Server-side deny + events/UI updates | Hiding buttons without backend checks |
| SSO from IdP lacking SLO | App-local state gate + revocation | Sending guessed LogoutRequests to IdP URLs |
| IdP enforces disable only on new logins | App consumes IAM events / polls authoritative state | Letting old SP sessions run until idle timeout |

## 27. Implementation Checklist

- [ ] Clearly separated SAML **authentication** from app **authorization** and when permissions take effect.
- [ ] Every sensitive route checks **live** enabled/locked status and permissions, not just login-time `GrantedAuthority`.
- [ ] Account identity lookup uses verified **IdP/issuer + tenant + immutable subject**.
- [ ] Transient usernames/emails/NameIDs are never assumed globally unique by default.
- [ ] Provisioning/deprovisioning or API/DB live-state checks exist instead of expecting SAML to push updates.
- [ ] IAM events are authenticated, idempotent, monotonically versioned, with retries/reconciliation/auditing.
- [ ] Revocation SLAs and fail-closed behavior exist when high-risk permissions cannot be verified.
- [ ] In multi-node clusters, state caches and session stores have appropriate consistency.
- [ ] Session lookup/revocation is restricted to authorized admins/processes; never deletes another user's sessions.
- [ ] Protections exist against event replay/out-of-order delivery, never trusting client timestamps as authority.
- [ ] After account lock, fresh SSO still hits the app disabled policy even when IdP cookies survive.
- [ ] SAML SLO is not treated as a guarantee of logging out all sessions/devices/tokens.
- [ ] Method-level and object-level authorization protect business logic, including non-MVC callers.
- [ ] Where immediacy is required, in-flight actions and near-commit checks are handled.
- [ ] WebSockets, queue consumers, and API tokens/refresh tokens have separate revocation/authorization mechanisms.
- [ ] Tested permission changes on active sessions, account locks, multiple browsers/nodes, surviving IdP sessions, store outages, and stale events.
- [ ] Raw SAMLResponses, session cookies, JWTs, real NameIDs/subjects, or sensitive account permissions are never logged publicly.
- [ ] Signature, issuer, audience, destination, subject/time, and `InResponseTo` SAML login validations remain intact; never weakened for dynamic authorization.

## 28. Review Questions with Answers

**Exercise 1.** The IdP removes the ADMIN group at 10:00, yet the user logged into the SP at 09:00. If the SP only uses `hasAuthority("ADMIN")` on the saved Authentication, is the permission guaranteed to disappear at 10:01?

**Answer:** no. Authorities may be a snapshot. Live authorization, refresh/revocation, or version checks are needed for the new policy to take effect.

**Exercise 2.** Does locking an account at the IdP automatically delete `JSESSIONID` cookies across every SP application?

**Answer:** no default guarantee. IdP and SP maintain separate sessions. SLO/coordinated revocation can help, yet SPs still need an account gate to deny current requests.

**Exercise 3.** The SP deletes all indexed HttpSessions for a user, yet the IdP SSO session remains. The user returns to the portal and immediately logs back in. What prevents access if the account is still disabled?

**Answer:** checking disabled status/permissions **at the SP** on login/use, rather than only deleting sessions.

**Exercise 4.** Why does increasing the session idle timeout to 8 hours worsen the stale role problem?

**Answer:** sessions can survive longer after permission changes; if relying solely on authorities snapshots, the stale-permission window widens. Live gates/revocation are needed, not just timeout tuning.

**Exercise 5.** When is `SessionRegistry.expireNow()` insufficient?

**Answer:** when the registry cannot see all sessions, `ConcurrentSessionFilter` is missing, multiple nodes do not share state, or a request is already in flight. Verify configuration and combine with live authorization.

**Exercise 6.** Can you delete sessions by email if two different IdPs can issue the same email?

**Answer:** dangerous. Ensure identity mapping is scoped by issuer/tenant and an immutable subject or collision-free global principal key.

**Exercise 7.** An authenticated user receives HTTP 403 after permissions are revoked. Does that mean the IdP SAML Response expired?

**Answer:** not necessarily. This may be a **live authorization** denial; distinguish it from SAML login validation.

**Exercise 8.** IAM event version 20 (disabled) arrives first, and version 19 (enabled) arrives afterward. What should the consumer do?

**Answer:** keep version 20 and discard the lower-version event. Resetting to enabled would unintentionally unlock the account.

**Exercise 9.** If approval permission is revoked after `AuthorizationFilter` permits the request yet before transaction commit, should you rely solely on the filter check?

**Answer:** no, if business rules require revocation enforcement up to commit time. At-action/transactional checks, data synchronization, and in-flight handling policies are needed.

**Exercise 10.** Is `@EnableMethodSecurity` required for `@PreAuthorize` to run in Spring Boot?

**Answer:** yes; Spring Boot Starter Security does not automatically enable method-level authorization in every project.

**Exercise 11.** Does SAML Single Logout revoke every JWT issued by other applications?

**Answer:** not automatically. JWT/API tokens require their own lifecycle, expiry, and revocation mechanisms.

**Exercise 12.** The authorization cache can be stale for 5 minutes, yet policy requires emergency locks to take effect within 10 seconds. Is the requirement met?

**Answer:** not yet. You need a low-latency design with invalidation and/or authoritative state checks, fail-closed defaults, and SLA monitoring.

**Exercise 13.** A user loses APPROVE permission yet retains READ. Must you log the user out of every application?

**Answer:** no. They can continue reading under current permissions; the goal is blocking APPROVE. Whether to revoke sessions depends on policy and UX.

**Exercise 14.** A user is disabled at the SP yet the IdP still signs a valid SAMLResponse. Should access be reopened because the signature is valid?

**Answer:** no. The signature only verifies origin/message integrity; the SP must still enforce its disabled-account policy.

**Exercise 15.** A service job running as a system account without a browser session calls the approve method. Does `AuthorizationFilter` protect it?

**Answer:** not by default. Use authorization at service/business boundaries, distinguish system accounts from delegated users, and enforce auditing and transaction policies.

## 29. Key Takeaways

**A SAML assertion verifies a login event; a Spring Security session stores Authentication; permissions and account status can change after that session is created.** Consequently, locking an account or removing a role at the IdP **does not automatically update every existing SP session**. For changes to take effect, the SP must enforce **live status/permissions at request/action time**, combined with **session/token revocation**, manage **propagation latency**, and block fresh IdP SSO logins as well if the local account is disabled.

A quick diagram:

~~~text
IAM changes account/role
    -> app authoritative state + version updated
    -> caches/sessions/tokens invalidated as required
    -> next request/operation checks live state
    -> ALLOW if enabled and authorized, DENY if revoked/disabled
~~~

Never treat stale `Authentication.getAuthorities()` or a signed SAMLResponse as an immutable permission decision for the entire session lifetime.

### Official References

- Spring Security — SAML 2.0 Login Overview, how Saml2Authentication/SecurityContext are created: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authentication Persistence and Session Management, SecurityContextRepository and SessionRegistry: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Authorize HttpServletRequests, AuthorizationFilter/AuthorizationManager: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security, EnableMethodSecurity/PreAuthorize: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Performing SAML 2.0 Single Logout, RP/AP flows and limits: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Session — Redis Configurations, Finding All Sessions of a Specific User: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session — API Documentation, SessionRepository/FindByIndexNameSessionRepository: https://docs.spring.io/spring-session/reference/api.html
- Spring Security API — Saml2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticatedPrincipal.html
