# Stale Permissions Remaining in Session, Token, or Cache After Revocation

## 1. Security Problem: Revoked Yet Still Permitted

In a system using Spring Security, an administrator might remove the **EXPORT_REPORT** permission from a user in the database at 10:00, yet the user can still export reports at 10:05. The execution path may have zero authentication errors: the session still holds the old authority, the JWT is still valid in signature and expiration, or a cache still stores an **allow** result from a prior check.

This is **stale authorization**: an access decision based on a snapshot of an old policy while the current policy has already changed. The fact that a user is validly authenticated (**authentication**) does not mean they are still permitted to perform a specific action (**authorization**). This risk is especially acute for downloading sensitive data, administration, money transfers, changing ownership, editing ACLs, or accessing another tenant.

After this lesson, you should be able to explain where stale permissions live, when they are re-read, why logout/role changes do not automatically revoke every token, how to apply fresh-state checks, and how to test sessions, tokens, and caches under multi-device/multi-node conditions.

**Knowledge boundary:** focuses on defects and mitigations ensuring permissions *after revocation* in Spring Security authorization. It does not implement a full authorization server or OAuth/OIDC protocols; it uses only the token concepts needed to understand the stale-permission window.

## 2. Distinguishing Three Easily Confused State Locations

| Where State Lives | Example of Stale Data | Why Access Continues | How to Force Fresh Checks |
| --- | --- | --- | --- |
| **Session / SecurityContext** | `Authentication` with `ROLE_ADMIN` or `ROLE_EXPORT` at login time | Subsequent requests may restore the old `Authentication` from `SecurityContextRepository` | Invalidate the relevant sessions; refresh `Authentication`; or check current permissions whenever needed |
| **Access token** | JWT containing scopes/roles at issuance and not yet expired | Resource Server verifies signature, timestamps, issuer… without inherently querying newly changed DB permissions | Short-lived tokens combined with validity policies; version/revocation checks; or introspection against live state |
| **Authorization cache** | Decision that user X may READ resource Y, or cached ACL/role lists | Cache hits skip re-reading revoked data | Evict/key by version; synchronize multi-node invalidation; avoid stale data on sensitive decisions |

The same request can traverse *multiple* layers: session cookie → `SecurityContext` → authorities from `Authentication` → service authorization → ACL/decision cache → data. Refreshing one layer does not guarantee the next layer is fresh. Conversely, a Resource Server using **SessionCreationPolicy.STATELESS** may store no HTTP session yet still suffer from stale permissions in JWTs and application caches.

**A concrete scenario**

- **09:00**: Mai logs in; session A and JWT T1 are issued with `EXPORT_REPORT` permission. Cache on node B stores allow for report 42.
- **09:30**: administrator revokes `EXPORT_REPORT`; the change commits in the permission source.
- **09:31**: requests using session A or T1 still present valid identity; node B still returns allow if reading only snapshot/cache.
- **09:32**: current-permission checks, token revocation, or cache invalidation can block the request — *if the system actually implements and verifies those mechanisms*.

Clearly define the effective commitment point: e.g., “every authorization request **starting after the revocation transaction commits** must be denied”. Requests already started before commit are a separate concurrency scenario needing handling policies; avoid vague phrases like “immediately” without defining boundaries.

## 3. Session: Authentication Does Not Auto-Refresh Permissions Every Request

In Servlet applications, Spring Security uses **SecurityContextHolder** for the request's context. **SecurityContextRepository** can save/restore `SecurityContext` across requests; a common implementation is **HttpSessionSecurityContextRepository**. The `Authentication` inside holds the principal and the set of **GrantedAuthority** created at authentication or the most recent update. When roles change in the database, there is no default rule that every `Authentication` saved across all sessions is immediately rebuilt.

Example policy check:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void approveReport(long reportId) {
    // ...
}
~~~

This is a **non-standalone illustrative snippet**. The **hasRole('ADMIN')** expression primarily checks the **ROLE_ADMIN** authority currently in the call's `Authentication`. If `Authentication` still carries the old `ROLE_ADMIN`, the method can be allowed even though the user-role table removed the permission. Merely adding **@EnableMethodSecurity** does not turn `hasRole` into a fresh database query every time.

Operations to distinguish:

1. **SecurityContextHolder.clearContext()** clears the context bound to the current execution thread; it does not revoke JWTs and does not guarantee clearing all of a user's `HttpSession`s across devices.
2. **Logging out** in a standard flow may invalidate the current session and clear `Authentication`. That does not mean other sessions of the same user were destroyed or separate bearer tokens were invalidated.
3. **Invalidating `HttpSession`** server-side prevents continued use of that session when session mechanisms are genuinely used. Deleting cookies in the browser without invalidating the server session does not provide the same guarantee.
4. **Changing permissions in `UserDetailsService`** or the DB does not automatically refresh every existing `Authentication`. A `UserDetails` cache during re-authentication can also hold stale data if not invalidated.
5. **Remember-me, refresh tokens, or SSO sessions** can mint a new `Authentication` after a session is destroyed. If the permission source or re-login mechanism still retains old grants, the user can regain permissions.

In Spring Security 6+, persistence mechanics changed from version 5: when setting `SecurityContext` manually in custom authentication flows, saving into **SecurityContextRepository** may require an explicit **saveContext(...)** call. This relates to session persistence, *not* automatic permission revocation. Consult documentation for your exact running version.

**Handling per product requirements:** if an account must be locked out across all devices, track sessions by principal across controllable nodes, invalidate the exact sessions, and disable minting new credentials if needed. **SessionRegistry** does not guarantee full distributed session tracking without proper session-tracking configuration; with Spring Session, you can use a repository and principal index if supported/configured. Test using two browsers/devices and two application nodes rather than inferring from a single local logout.

## 4. Token: A Valid Signature Does Not Prove Permissions Remain Valid

### 4.1. A JWT Access Token Is a Permission Snapshot at Issuance Time

A JWT self-contains claims such as **sub**, **scope/scp**, **roles**, **iat**, **nbf**, **exp**, **iss**, **aud**. With a JWT Resource Server configuration, **JwtDecoder** verifies the signature and configured validity constraints; scopes are typically mapped to authorities like **SCOPE_x**. If a claim records an old role, a valid signature with **exp** still in the future means **the JWT inherently has no idea that roles changed in the DB**.

Example: an access token has **SCOPE_reports.export**, expires at 10:15, yet export permission was revoked at 10:00. At 10:01, if the resource server only checks that the token is valid and uses authority **SCOPE_reports.export**, it can still allow exporting reports. Neither signature nor timestamp is wrong; the error lies in assuming token-recorded scopes reflect real-time permission changes.

Short-lived JWTs **reduce the maximum length of the stale window** when all other validations are sound, yet do not prove instant revocation. Clock skew settings can shift `exp`/`nbf` acceptance relative to wall clocks; verify effective lifetimes in tests. When using JWTs, still verify issuer, target audience, signing algorithm, keys, and all relevant validations; revocation checks are an extra step, not a replacement for basic token protection.

### 4.2. Refresh Tokens and Access Tokens Have Different Lifecycles

Revoking a **refresh token** prevents using that refresh token to request new access tokens (per authorization server policy), yet **previously issued access tokens may remain usable** until expiration or until the resource server detects revocation. RFC 7009 specifies servers must support refresh token revocation and recommends supporting access token revocation; exact effects on related tokens depend on server implementation and policy.

Do not write a test “revoke refresh token → old JWT access token must immediately 401” if the system has no actual access-token revocation mechanism. Conversely, if the product requires immediate multi-device logout/account lockout, design a verification path at the resource server.

### 4.3. Opaque Tokens and Introspection

With opaque bearer tokens, Spring Security Resource Server can call **OpaqueTokenIntrospector** on the authorization server to confirm the token is currently **active=true**. This fits when the server must track token state and allow revocation. However, immediacy is not guaranteed if the authorization server returns stale status, the resource server caches introspection results too long, or a network partition occurs.

A system can configure introspection even for JWTs if server-side status checks are desired, yet **default JWT Resource Server mode does not auto-introspect every request**. Explicitly choose and configure policy, round-trip cost, SLA, and behavior when the introspection endpoint is unreachable.

## 5. Cache: Stale Allow Can Outlive Both Session and Token

Caches that commonly affect authorization:

- **UserDetails/authorities cache:** principal loaded from DB and reused across authentications; changing roles without evicting/reloading can keep issuing `Authentication` with old permissions.
- **ACL cache:** an `ObjectIdentity`'s ACL, ACE list, parent ACL, or policies are cached; updating child/parent ACLs without sufficient invalidation can preserve revoked inherited permissions.
- **Authorization decision cache:** stores true/false outcomes of `canRead`/`canExport`/`hasPermission`; cached **true** values easily create vulnerabilities if keys or lifetimes are not tied to policy revisions.
- **Caches at API gateway/edge/sub-applications:** layers outside Spring Security may cache responses, entitlements, or policy decisions. Invalidating inside a Spring service does not automatically invalidate external caches.
- **Distributed caches and per-pod local caches:** deleting a Redis key does not automatically clear a Caffeine copy inside the process; invalidation messages may arrive late or be lost.

**Key design flaw:** caching “userId:action” without **tenantId/resourceId** can mis-grant access across documents. Keying only by `resourceId` without `userId` is also dangerous. Keys containing user, tenant, resource, and action yet lacking **policy revision** can still go stale after revocation.

A conceptual key:

~~~text
tenantId / principalId / resourceType / resourceId / action / policyRevision
~~~

Putting revision into the key helps only if **every request obtains the current revision from a sufficiently fresh source**. If the revision itself sits in a stale local cache, the system still hits the old key and the vulnerability remains. Similarly, updating DB then publishing an invalidation leaves a gap between commit and event; define the consistency level and mechanisms to close the window as required.

Caching **deny** outcomes also needs a clear policy: after re-granting permissions, a stale deny can block legitimate users until TTL expires. That is a correctness/availability bug, though distinct in severity from a stale allow.

### 5.1. Race Conditions During Invalidation

One thread reads old permissions right before revocation; another thread commits revocation and clears the cache; the first thread then writes the stale **allow** back into the cache. This is why “we called evict” can still be insufficient.

Mitigation: use a **policy revision**/etag from authoritative data, verify revision before accepting a cache write, tag cache entries with revision, and discard entries whose revision mismatches on read. With event-driven architectures, emit events after commit, use an outbox/queue with retries and version ordering to avoid older events overwriting newer state. Any mechanism must be measured and tested under multi-node conditions.

## 6. Revocation Strategies: Choosing by Consistency Window

There is no single “revoke tokens and caches” recipe fitting every application. Define requirements:

| Goal | Feasible Mechanism | Limitations to Recognize |
| --- | --- | --- |
| Deny permissions immediately on **new requests after commit** | Query live policy; session invalidation; token revocation check/introspection; policy-version guard | Requires a consistent state store and live verification path on every node |
| Accept a very short, measured window | Short access token TTL; bounded cache TTL; event invalidation | TTL is a relative delay bound, not instant revocation; account for clock skew/event failures |
| Block re-login / token refresh | Disable account; revoke refresh tokens; revoke remember-me/SSO sessions per mechanism | Existing access tokens/sessions may stay valid if not handled separately |
| Per-document permission changes | Recheck current ACL/policy at read/edit point; invalidate parent/child ACLs | Per-user token versions can miss resource/ACL changes unless corresponding versions bump |
| Multi-instance systems | Shared authoritative store or introspection; acknowledged event delivery, revision checks | Evicting on node A does not guarantee node B sees it instantly |
| Long-running sensitive operations | Check permissions at start and at commit/data emission | Permissions can change between check and use (TOCTOU) |

**Two common designs:**

**A. Live permissions at the service layer.** Bearer token/session identifies who is calling; **@PreAuthorize** or `AuthorizationManager` queries current policy by subject, tenant, and resource. For sensitive actions, check within the proper transaction and/or right before outputting data. Avoid querying a decision cache without an invalidation strategy.

**B. Versioned credentials/authorization.** Each user has an **authzVersion** incremented in the same transaction that changes permissions. Sessions/tokens carry the version at issuance. Requests compare against the current version; if different, reject old credentials or reload permissions per policy. When revoking permissions per **resource**, tenant, group, or parent ACL, a user-only version is insufficient unless all affected versions increment. You can combine `userVersion`, `membershipVersion`, and `resourcePolicyVersion`.

The critical guarantee is **reading the new version from a source whose consistency meets the SLA**. Reading lagging replicas, caching revisions too long, or handling events asynchronously before deciding can render versioning ineffective. If state lookup fails on a high-risk operation, never treat “unable to look up = permitted”.

## 7. Standalone Java 17+ Example: Seeing Snapshot Bugs and Version Guards

The program below **simulates** three stale sources: session-held permissions, self-contained token claims, and an authorization cache. The **freshGuard** function queries live policy with revision. Its purpose is illustrating logic: the program does not sign JWTs, use Spring Security, or replace real security tests.

Create file **StalePermissionDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class StalePermissionDemo {
    record Policy(long version, boolean canExport) {}
    record Credential(String user, long version, boolean exportClaim) {}

    private static final Map<String, Policy> currentPolicies =
            new ConcurrentHashMap<>();

    private static Credential issue(String username) {
        Policy p = currentPolicies.get(username);
        if (p == null) {
            throw new IllegalStateException("No policy for " + username);
        }
        return new Credential(username, p.version(), p.canExport());
    }

    // Illustrates reusing role/claim captured at login time.
    private static boolean snapshotAllow(Credential c) {
        return c.exportClaim();
    }

    // Safe only if currentPolicies is a sufficiently fresh permission source.
    private static boolean freshGuard(Credential c) {
        Policy now = currentPolicies.get(c.user());
        return now != null
                && now.version() == c.version()
                && now.canExport()
                && c.exportClaim();
    }

    public static void main(String[] args) {
        currentPolicies.put("mai", new Policy(1, true));
        Credential session = issue("mai");
        Credential token = issue("mai");

        Map<String, Boolean> decisionCache = new HashMap<>();
        String key = "mai:report-42:EXPORT";
        decisionCache.put(key, snapshotAllow(token));

        System.out.printf(
                "before session=%s token=%s cache=%s guard=%s%n",
                snapshotAllow(session), snapshotAllow(token),
                decisionCache.get(key), freshGuard(token));

        // Simulate revocation: update permission and version together.
        currentPolicies.put("mai", new Policy(2, false));
        System.out.printf(
                "after session=%s token=%s cache=%s guard=%s%n",
                snapshotAllow(session), snapshotAllow(token),
                decisionCache.get(key), freshGuard(token));

        // Re-grant permission: old credential still mismatches version.
        currentPolicies.put("mai", new Policy(3, true));
        Credential newToken = issue("mai");
        System.out.printf(
                "regrant old=%s new=%s%n",
                freshGuard(token), freshGuard(newToken));
    }
}
~~~

Run in the file's directory with JDK 17 or newer:

~~~bash
javac StalePermissionDemo.java
java StalePermissionDemo
~~~

Expected output:

~~~text
before session=true token=true cache=true guard=true
after session=true token=true cache=true guard=false
regrant old=false new=true
~~~

Lesson from the output: sessions/tokens/caches holding an old **allow** do not vanish automatically when policy changes; checking the current version and live policy catches revocation. After re-granting, the old token remains blocked due to version mismatch; a fresh token/`Authentication` is needed if the strategy rejects old credentials.

**Simulation limits:** `ConcurrentHashMap` stands in for a database and transactions, there is no race between two nodes, the token here is a record rather than a real JWT, and there is no signature verification. In real applications, updating **policy + version** must be atomic; version checks must read trusted state; session/token checks must occur on the real authorization path.

## 8. Applying to Spring Security Authorization

For resource-based permissions, the clean pattern is letting **Authentication identify the user** and then checking live policy at the business layer. Enable method security with **@EnableMethodSecurity**; the snippet below is **illustrative code needing a Spring project and real repositories**, not a standalone Java program:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityMethodsConfiguration {
}

@Service
class ReportService {
    @PreAuthorize("@freshReportPolicy.canExport(authentication, #reportId)")
    public byte[] exportReport(long reportId) {
        return reportRepository.generateExport(reportId);
    }
}
~~~

The **freshReportPolicy** bean must genuinely query permission conditions at request time: user still active, current roles/groups, right tenant/resource, active EXPORT permission, report status, and any blocking policies. Never write an implementation that only inspects **authentication.getAuthorities()** and call it “fresh”. For expressions referencing **#reportId**, ensure Spring can resolve parameter names (e.g., compiling with **-parameters**). Method security checks calls through the Spring AOP proxy; self-invocation inside the same instance can bypass advice without proper design.

If the endpoint also requires an OAuth scope, use an AND condition:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.export')"
    + " and @freshReportPolicy.canExport(authentication, #reportId)"
)
public byte[] exportReport(long reportId) {
    return reportRepository.generateExport(reportId);
}
~~~

The scope in the token **does not replace** active permission checks; the live policy clause prevents stale allows. If a permission was *newly granted* after token issuance, the old scope may keep denying access until a new token is issued — usually intentional conservative behavior.

In real deployments, choose the API response contract on revocation: invalidated/blocked credentials may yield **401**, whereas a valid identity lacking permission to a resource typically yields **403**. For resources whose existence must stay hidden, the application may intentionally return **404**. Lock down the API contract and test the exact paths; never rely on a single code for every denial type.

### Why Not Just Unconditionally “Reload Authorities from DB”?

Fetching current authorities on every request can suit strict requirements, yet increases query cost and does not automatically solve decisions based on resource ACLs, downstream caches, or in-flight requests. Good designs pick **the minimal permission data needed per action**, a tested versioning/invalidation mechanism, and a state source with clear consistency guarantees. Sensitive decisions may need to read the primary DB rather than a lagging replica.

## 9. Mandatory Regression Test Scenarios

The following cases verify **real access paths**, not just a check function with mock data. Each case needs a **pre-revocation: allow** state to prove setup validity, then commits revocation, and verifies **post-revocation: deny** using the exact old credential/cache.

| Code | Warm State Before Revoke | Action | Expectation After Revoke |
| --- | --- | --- | --- |
| S1 | Browser A holds session with `ROLE_EXPORT` | Remove role and commit | Browser A can no longer export reports |
| S2 | Two browsers/devices A and B hold two sessions | Lock user or revoke all sessions per requirement | Both A and B blocked; session B does not slip through |
| S3 | Session A logged out yet remember-me remains active | Attempt automatic re-login | Does not restore revoked permissions |
| J1 | JWT T1 unexpired, holds `SCOPE_reports.export` | Revoke role in DB | T1 blocked per committed freshness/revocation mechanism |
| J2 | T1 unexpired; refresh token revoked | Use T1 then attempt refresh | T1 follows configured access policy; refresh cannot mint new tokens |
| J3 | Old JWT at node B; new JWT at node A | Update policy and issue new token | Old blocked, new has only current permissions |
| O1 | Opaque token introspection `active=true` | Revoke token at authorization server | Next check returns inactive/deny per SLA |
| C1 | Decision cache on one node holds allow | Revoke + invalidate | Next request does not receive stale allow |
| C2 | Nodes A and B both hold cached allow | Revoke at A, call B | B does not retain permission beyond committed window |
| C3 | Child ACL cache inherits permission from parent | Revoke ACE on parent | Child no longer inherits revoked grant |
| C4 | Permission revoked then re-granted | Run two-way policy change | Old allow does not leak; old deny does not block forever |
| R1 | User X has permission on document 42 | Revoke X on 42 | Does not unexpectedly affect user Y or document 43 |
| T1 | Two requests concurrent with revocation | Record order/commit boundary | Matches consistency contract; no stale allow after committed point |
| F1 | Introspection/permission-store/invalidation fails | Invoke sensitive operation | Does not fail-open when permission source cannot be verified |

**Sample workflow for multi-node integration tests:**

1. Create real user and grant in the policy source; issue session/token before changes; verify requests through service/API are allowed.
2. Warm caches across **all nodes participating in the test**, recording versions and cache hit status; if testing ACLs, create both parent and child.
3. Through the real admin path, revoke permission and commit; record commit timestamp, new revision, and invalidation event if any.
4. Resend the **exact old session ID/cookie or token** to each node with the same resource/action; verify responses are blocked and no sensitive data appears in body/stream.
5. Verify other users and resources retain proper permissions; re-grant permission and verify new tokens/sessions or live policies work.
6. Inject event/network faults and concurrent request/revoke races to detect stale cache insertion; if SLA allows eventual consistency, measure the actual window against the defined threshold.

**Testing pitfall with Spring Security:** using **@WithMockUser(roles="ADMIN")** alone creates a mock `Authentication` in the test and does not prove real sessions were refreshed after DB changes. For servlet sessions, write tests retaining **MockHttpSession** or real login cookies; for bearer JWTs, issue valid tokens matching Resource Server config and retry the exact old token. JUnit/MockMvc are great for regression tests, yet unit tests mocking `Authentication` cannot prove token validation, revocation, or multi-node caching.

For REST APIs, check **401/403/404** responses per contract alongside **zero returned data**. A 200 response with wrongly truncated data or an export that wrote a file before policy blocked it is still a defect. For WebSocket/SSE, async jobs, and long downloads, authorization at handshake/start is insufficient if the product requires revoking active streams; decide where rechecks happen and how in-flight work cancels.

## 10. Deployment Prevention Checklist

**Permission source and transactions**

- [ ] Clearly identify whether permissions live in user-roles, group memberships, ACLs, tenants, a policy engine, or multiple sources.
- [ ] Revocation updates every grant source; do not remove only one role while inherited or alternate grants remain.
- [ ] Write policy versions/permission mutations in clearly bounded transactions; emit invalidation events after commit with retry mechanisms.
- [ ] Avoid reading permissions from replicas or caches whose lag exceeds the operation's security SLA.

**Credentials and sessions**

- [ ] Check all sessions/devices needing revocation, remember-me, and refresh tokens; distinguish current-session logout from global logout.
- [ ] JWT validator checks signature, issuer, audience, exp/nbf per configuration; revocation/freshness mechanisms are designed independently.
- [ ] For permissions requiring immediate revocation, never rely solely on JWT expiration or refresh token revocation.
- [ ] If using a **jti** denylist, verify issuer, token scope, entry retention until end of validity window, and cross-node consistency; never log raw tokens.

**Caching and enforcement**

- [ ] Cache keys include identity, tenant, resource, action, and revision/policy dependencies as needed.
- [ ] Invalidation covers parent/child caches, local caches, and distributed caches; multi-instance tests exist.
- [ ] Never default to allow when permission stores/introspection fail or revisions cannot be verified.
- [ ] Permissions are checked at the executing service, not just frontend/menus; list, search, export, batch, and background jobs are audited.
- [ ] Do not trust authorities stored in `Authentication` alone when dynamic permissions are required; distinguish static authorities from live ACL/policy lookups.

**Observability and auditing**

- [ ] Log revoking actor, subject, tenant/resource, permission, commit timestamp, revision, and post-revocation access outcomes.
- [ ] Measure cache hit/miss, invalidation delay, post-revoke allowed requests, and node divergence.
- [ ] Keep session IDs, bearer tokens, and refresh tokens secret; never write these credentials into logs.
- [ ] Alert when post-revoke authorization keeps allowing or when permission checks run in degraded mode.

## 11. Common Mistakes to Identify

1. **“I deleted the role in the DB, so the session lost the permission.”** False if `Authentication` holds an unrefreshed authority snapshot.
2. **“I called logout, so all devices and API tokens are revoked.”** True only if policy implements full invalidation for all those credentials/sessions.
3. **“The JWT signature is valid, so the role in the token is still right.”** Signature proves integrity/issuer per config, not role changes after issuance.
4. **“Revoking the refresh token immediately disables old access tokens.”** Must check policy and how the resource server detects access token revocation.
5. **“A 10-minute cache TTL supports immediate revocation.”** TTL only bounds part of the stale window; it does not guarantee denying the next request after commit.
6. **“We ran `@CacheEvict` on node A, so node B definitely knows.”** Depends on cache topology, pub/sub, versioning, and delivery guarantees.
7. **“Putting `policyVersion` in the key is enough by itself.”** If the version itself comes from a stale cache or lagging replica, the check still fails.
8. **“Blocking the admin web endpoint is enough.”** Other URLs, internal calls, background jobs, or export channels can bypass that checkpoint.
9. **“Authorization server is unreachable, so let requests pass temporarily.”** For sensitive operations, this is fail-open; clear, conservative error rules are required.
10. **“`@WithMockUser` tests pass, so revocation is complete.”** Mock tests cannot prove existing sessions, old JWTs, DB commits, or multi-node caches.

## 12. Practice Exercises

**Exercise A — Stale session:** write an integration test logging in with session A, removing `ROLE_EDITOR`, and calling the edit-document endpoint again using **the exact same session A**. Implement one of two grounded approaches: invalidating relevant sessions, or having the service always query fresh entitlements. State the post-commit boundary clearly.

**Exercise B — JWT and refresh token:** issue a JWT with an export claim; revoke permission, test the old JWT before `exp`, test the refresh token before/after revocation, and test a new JWT after update. Build a 401/403 result matrix matching the resource server's real policy. Ensure old JWTs do not keep allowing access if immediate revocation is required.

**Exercise C — Cache and race:** warm allow caches on A/B, revoke permission, trigger a read-old/evict/write-back-old race, and prove revision guards or invalidation eliminate stale allows. Add a case where a parent ACL is revoked while a child ACL was previously cached.

**Acceptance criteria:** able to explain *why* sessions/tokens/caches still hold old permissions; identify the exact fresh permission source and effective decision boundary; measure the revocation window; verify requests with credentials **issued before revocation** are blocked per SLA; avoid breaking other users'/resources' permissions; and never overlook cache/multi-node bugs.

## Official References

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
