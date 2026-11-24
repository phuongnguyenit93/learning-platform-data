# Handling Users Valid at the IdP Yet Locked or Unauthorized at the Application

In **Spring Security federation**, a user may log in successfully at the **Identity Provider (IdP)**, complete MFA, and receive a validly signed SAML 2.0 assertion, yet still **be denied application access by the Service Provider (SP)**. Reasons: the organization may have locked the internal account, not yet provisioned the user, left them pending approval, exhausted licenses, excluded them from the target tenant, or not granted feature/resource permissions.

Example: an employee still holds an active account in the corporate IdP, yet was locked in the finance app due to a security review. If the SP automatically creates a session and grants `ROLE_USER` right after SAML verification without checking local status, the result **bypasses the application's lock decision**, even though the IdP was completely valid.

**Principle:** `SAML authentication` answers "who is the subject according to the IdP?", **application admission** answers "may they enter this application?", and **authorization** answers "which actions may they take on which resources?". All three checks must be enforced independently and combined under **deny by default**.

## 1. Three distinct verification layers

| Layer | What must be known | Mechanism/decision point | Outcome |
| --- | --- | --- | --- |
| **Federated authentication at IdP** | Who authenticated? Is the response/assertion trustworthy and unexpired? | Signature, issuer, audience, destination/recipient, conditions, subject confirmation, `InResponseTo`, replay. | Produces **verified federated identity**. |
| **Application admission** | Does this identity have a local account? Is it LOCKED/DISABLED/PENDING? Is it permitted into this product? | Lookup local identity binding, account status, license, onboarding approval, tenant, and lifecycle policy. | **Allows or denies establishing an application session**. |
| **Resource authorization** | May the account view/edit this report, order, or tenant's data? | RBAC, ABAC, permissions, ownership, tenant policy, current account state. | **Allow or 403** for a specific operation. |

The same valid SAML assertion can lead to different outcomes:

- **LOCKED/DISABLED:** do not create a new app session; never treat IdP login as unlocking the account.
- **PENDING_APPROVAL/NO_LOCAL_ACCOUNT:** disallow business functions; allow JIT provisioning only under explicit policy and prerequisites.
- **ACTIVE yet missing `reports:read`:** may allow landing page access while denying the reports API.
- **ACTIVE with tenant A report access:** cannot read tenant B resources merely because the URL has `tenantId=B`.

In particular, **application-decided permissions** must be revocable independently of the IdP SSO session. Valid SAML never turns a user into an administrator.

## 2. SAML login flow and account check placement

~~~text
Browser                 SP / Spring Security                     IdP
   |                            |                                  |
   | GET /reports/42            |                                  |
   |--------------------------->|                                  |
   |                            | AuthnRequest                     |
   |<---------------------------|                                  |
   |------------------------------------------------------------->|
   |                            |                           SSO/MFA |
   |<-------------------------------------------------------------|
   | POST SAMLResponse to ACS   |                                  |
   |--------------------------->|                                  |
   |                            v                                  |
   |               Saml2WebSsoAuthenticationFilter                |
   |                            |                                  |
   |               AuthenticationManager / OpenSAML                |
   |                 - issuer, signature, expiry                   |
   |                 - audience, recipient, InResponseTo          |
   |                 - subject confirmation, replay               |
   |                            |                                  |
   |                    VALIDATED IDENTITY                         |
   |                            |                                  |
   |                  Lookup local identity binding                |
   |                            |                                  |
   |                 +----------+-----------+                      |
   |                 |                      |                      |
   |          LOCKED/DISABLED/           ACTIVE +                  |
   |          PENDING/NO ACCOUNT        admitted                   |
   |                 |                      |                      |
   |           reject login           Authentication +             |
   |           do not create session  SecurityContext              |
   |                                        |                      |
   |                              Authorization /reports/42       |
   |                                   ALLOW or 403                |
~~~

`Saml2WebSsoAuthenticationFilter` receives the response at the **ACS**, the converter routes to the `RelyingPartyRegistration` config, and the authentication manager delegates to the OpenSAML provider for verification. **Application admission** should hook in **after SAML verification succeeds, yet before the Authentication/session is published as successful**. Resource authorization remains necessary even when admission succeeds.

**Avoid this mistake:** checking account status only on the home page after Spring Security has already stored the session, redirecting locked users to an error page. If other APIs or controllers lack the same check, the session cookie can still fetch data. Nor should you replace SAML validators with a `user.status == ACTIVE` query skipping signature and issuer checks.

## 3. Mapping federated identity cleanly to an internal account

### 3.1. Do not rely solely on email or display name

An IdP may issue `NameID`, `email`, `groups`, and other attributes. Not every value is stable and fit as an account key. Emails can change, be reassigned, or collide across environments; SAML `NameID` also has a transient format that is not reused across logins.

An identity-linking table might store:

~~~text
federated_identity
  issuer_id        = "urn:example:idp:corporate"
  stable_subject   = "employee-9732a..."
  tenant_scope     = "tenant-acme"
  local_user_id    = "user-42"
  binding_status   = "VERIFIED"

local_account
  local_user_id    = "user-42"
  status           = "LOCKED"
  reason_code      = "SECURITY_REVIEW"
  entitlements     = []
~~~

Linking keys should combine **trusted IdP/issuer + stable subject**, plus tenant/organization scope where appropriate. The stable subject can be a persistent NameID or an immutable attribute guaranteed and issued by the IdP inside verified assertions; choose based on the real federation contract. **Never take a self-asserted issuer/subject from an HTTP request to look up a local account and grant login.**

A locked account must still be discoverable through this binding. If queries filter only `status=ACTIVE`, the system may mistakenly conclude "no account exists" and **auto-JIT-provision a new account**, bypassing the lock.

### 3.2. Multi-IdP and identity migrations

In multi-IdP setups, the same email may come from different issuers. Never auto-merge `alice@example.org` at IdP A with `alice@example.org` at IdP B. For migrations changing issuer/NameID, require an **evidenced re-linking** plan with approvals and auditing. When no binding is found, follow `NO_LOCAL_ACCOUNT` policy rather than granting access from a "similar" email record.

| Verified data from IdP | Appropriate use | Inappropriate use |
| --- | --- | --- |
| `Issuer` and registration | Identifying the trusted identity source. | Auto-adding an unapproved new issuer. |
| Persistent NameID / immutable subject | Internal linking key per policy. | Assuming every NameID format is immutable. |
| Email | Contact info and controlled onboarding. | Sole proof to attach/restore old privileges. |
| Group attributes | One input for approved permission mapping. | Auto-granting any role sharing that name. |
| `RelayState` | Correlation/login navigation. | Account ID, tenant ID, or admin privileges. |

## 4. Account state policy: local deny takes precedence

Recommended internal state set:

| Status | Can IdP still be valid? | Application handling |
| --- | --- | --- |
| `ACTIVE` | Yes | Allow admission if tenant/license/other conditions pass. |
| `LOCKED` | Yes | **Deny new login**; never unlock based on SAML. Revoke existing sessions/tokens within SLA. |
| `DISABLED` / `DEPROVISIONED` | Yes | Reject; never recreate the account via JIT. |
| `PENDING_APPROVAL` | Yes | Awaiting approval; may show limited status page, grant no product rights. |
| `NO_LOCAL_ACCOUNT` | Yes | Deny by default or strictly governed JIT, with no default privileges bypassing policy. |
| `ACTIVE` without roles | Yes | May enter minimal shell or deny admission per policy; all features require explicit permissions. |
| `ACTIVE` in wrong tenant | Yes | Deny cross-tenant resources; never treat URL tenant IDs as membership proof. |
| `UNKNOWN` due to DB/status store failure | Yes | **Fail closed** on mandatory permission decisions; never assume the account is active. |

**Safe evaluation order:** resolve exact identity binding → check `DISABLED/LOCKED` → check approval/admission status → check tenant membership/license → check role/permission/resource. When multiple conditions apply, **deny overrides allow**. For instance, a SAML assertion containing an admin group for a locked local account must still be denied.

### 4.1. Application entry permission differs from feature permission

There are two valid patterns, which must stay consistent with product behavior:

1. **No entitlement to use the application → deny admission.** Suits licensed or product-wide-approved applications.
2. **Allow general/onboarding pages while restricting features → limited admission, deny resources via authorization.** Ensure general pages do not invoke sensitive APIs and never grant business permissions via default `ROLE_USER`.

Someone lacking report-viewing permission **is not necessarily a locked account**, so guidance and support paths differ. However, if business rules mandate "unapproved users cannot access any page", the admission gate must block right at login.

## 5. Conditional JIT provisioning without auto-opening privileges

**JIT (Just-in-Time) provisioning** may create a local account upon first SAML login. A valid `SAMLResponse` must never be treated as an unconditional grant of permissions.

Require at minimum:

1. **Allowlisted issuer** and a verified, stable subject.
2. **Explicit eligibility:** approved tenant, license, organization, approved group, or verified invitation; never check email domain alone.
3. **Unique constraint** on `(issuer, stableSubject, tenantScope)`; account creation must withstand concurrent callback/click races.
4. **Lock/deprovision history check:** binding queries must include LOCKED/DISABLED/tombstone records. Never create a new account that bypasses an existing lock.
5. **Safe initial state:** `PENDING_APPROVAL` or least-privilege `ACTIVE` only when policy permits.
6. **Audit:** record decision at creation time, policy version, identity source, tenant, and approver if any.
7. **Error handling:** on quota exhaustion, unknown tenant, or datastore errors, reject/leave pending; never fall back to admin rights.
8. **Deprovisioning:** plan disable/revocation when HR/IAM revokes rights; do not wait passively for the next SAML login.

If administrators want accounts pre-created via **SCIM**, SAML and SCIM have distinct duties: **SCIM** syncs lifecycle/provisioning, while **SAML** proves identity at login time. During sync lag windows, local denials must still be respected.

## 6. Standalone Java 17: verifying local policy

This Java 17 example simulates an identity **already verified by SAML earlier**, looks up the local account, and checks status/tenant/permissions. It is **not an OpenSAML implementation**, parses no XML, and populates no `SecurityContext`; its goal is to illustrate valid SAML identity paired with denied application access.

File `FederatedAccountPolicyDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class FederatedAccountPolicyDemo {

    record Identity(String issuer, String subject) {}
    enum Status { ACTIVE, LOCKED, DISABLED, PENDING_APPROVAL }
    enum Decision {
        ALLOW, NOT_PROVISIONED, ACCOUNT_LOCKED,
        ACCOUNT_DISABLED, PENDING_APPROVAL,
        TENANT_DENIED, PERMISSION_DENIED
    }
    record Account(Status status, String tenant,
                   Set<String> permissions) {}

    static Decision decide(Identity verified, String tenant,
                           String permission,
                           Map<Identity, Account> accounts) {
        Account account = accounts.get(verified);
        if (account == null) {
            return Decision.NOT_PROVISIONED;
        }
        if (account.status() == Status.LOCKED) {
            return Decision.ACCOUNT_LOCKED;
        }
        if (account.status() == Status.DISABLED) {
            return Decision.ACCOUNT_DISABLED;
        }
        if (account.status() == Status.PENDING_APPROVAL) {
            return Decision.PENDING_APPROVAL;
        }
        if (!account.tenant().equals(tenant)) {
            return Decision.TENANT_DENIED;
        }
        if (!account.permissions().contains(permission)) {
            return Decision.PERMISSION_DENIED;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        String issuer = "urn:example:idp:corporate";
        Identity alice = new Identity(issuer, "subject-alice");
        Identity bob = new Identity(issuer, "subject-bob");
        Identity carol = new Identity(issuer, "subject-carol");
        Identity dave = new Identity(issuer, "subject-dave");

        Map<Identity, Account> accounts = Map.of(
            alice, new Account(Status.ACTIVE,
                               "tenant-A", Set.of("reports:read")),
            bob, new Account(Status.LOCKED,
                             "tenant-A", Set.of("reports:read")),
            carol, new Account(Status.PENDING_APPROVAL,
                               "tenant-A", Set.of())
        );

        System.out.println(decide(
            alice, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            bob, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            carol, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            dave, "tenant-A", "reports:read", accounts));
        System.out.println(decide(
            alice, "tenant-A", "reports:write", accounts));
        System.out.println(decide(
            alice, "tenant-B", "reports:read", accounts));
    }
}
~~~

Compile and run:

~~~bash
javac FederatedAccountPolicyDemo.java
java FederatedAccountPolicyDemo
~~~

Exact output:

~~~text
ALLOW
ACCOUNT_LOCKED
PENDING_APPROVAL
NOT_PROVISIONED
PERMISSION_DENIED
TENANT_DENIED
~~~

The last two lines show **even an ACTIVE account cannot access every resource**. The demo uses a static `Map`, supports only one tenant per account, and omits license checks, session revocation, DB persistence, and SAML validation; production requires dedicated storage and policies. **Identities passed to `decide` must come from a verified assertion**, never directly from untrusted HTTP headers/URLs.

## 7. Spring Security: admission gate must wire into the SAML flow

### 7.1. Why doesn't `UserDetailsService` solve this automatically?

In form login, `DaoAuthenticationProvider` uses `UserDetailsService`/account-status checkers and checks `isEnabled()`, `isAccountNonLocked()` on `UserDetails`. By contrast, the **SAML** flow uses an **OpenSAML authentication provider**, not `DaoAuthenticationProvider` by default. Merely adding `enabled=false` in the DB or declaring a `UserDetailsService` bean **does not guarantee** SAML users are blocked.

Spring Security defines `DisabledException` and `LockedException` for invalid account states. When customizing the SAML provider/converter or admission component, throw an appropriate `AuthenticationException` so the request goes through the **authentication failure path**, rather than creating a successful `Authentication` and leaving the UI to sort it out.

### 7.2. Admission gate architectural pattern

~~~text
verifyWithOpenSaml(samlResponse, trustedRegistration, pendingRequest)
    -> verified issuer + persistent subject + claims

binding = localIdentityRepository.findIncludingDisabled(issuer, subject)

if no binding:
    if explicit JIT policy passes:
        binding = createAccountWithUniqueConstraint(leastPrivilege)
    else:
        throw AuthenticationException(NOT_PROVISIONED)

account = accountRepository.loadCurrent(binding.localUserId)

if account.status == LOCKED:
    throw LockedException(ACCOUNT_LOCKED)
if account.status == DISABLED:
    throw DisabledException(ACCOUNT_DISABLED)
if account.status == PENDING_APPROVAL:
    throw AuthenticationException(APPROVAL_REQUIRED)
if account.status != ACTIVE:
    throw AuthenticationException(ADMISSION_DENIED)
if not account.hasApplicationEntitlement:
    throw AuthenticationException(APP_NOT_ASSIGNED)

authorities = mapOnlyApprovedApplicationEntitlements(account)
return authenticatedResultWithLocalAccountId(authorities)
~~~

This is **pseudocode**, not a built-in API or copy-pasteable runnable snippet. Run the admission check **after** SAML validation yet **before** successful authentication is published. Avoid creating sessions in a custom controller before status checks finish.

Spring Security documentation supports customizing `OpenSamlXAuthenticationProvider#setResponseAuthenticationConverter` to convert the processed response into `Authentication`. You can delegate to the default converter and add account lookup/status/authority mapping, or use the extension point documented for your **exact version**. `OpenSaml4AuthenticationProvider` in some 6.x releases and `OpenSaml5AuthenticationProvider` in newer releases have different APIs; verify your dependencies. Never disable default signature, issuer, audience, recipient, conditions, `InResponseTo`, or replay validators to simplify local account checks.

### 7.3. `SecurityFilterChain` config and least privilege

File `src/main/java/example/security/FederationSecurityConfig.java` in a Spring Boot project with valid SAML registrations:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class FederationSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/help", "/access-pending", "/error")
                    .permitAll()
                .requestMatchers("/admin/**")
                    .hasAuthority("app:admin")
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This configuration only **enables SAML login and URL/method security rules**. It **does not yet implement the admission gate**, lacks IdP metadata, does not map approved entitlements, and cannot compile standalone via `javac` with the JDK alone. Deploying this example verbatim to production without the admission component leaves locked accounts unaddressed.

`@EnableMethodSecurity` enables `@PreAuthorize` on services. Example:

~~~java
package example.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports:read')")
    public String readSummary() {
        return "Report summary";
    }
}
~~~

This illustrates a **service in a Spring project**, without controllers or per-report-ID ownership checks. Multi-tenant systems must also enforce logic such as:

~~~text
authentication is present?
localAccount is currently ACTIVE?
approvedPermissions contains "reports:read"?
localAccount belongs to request.tenantId?
requestedReport.tenantId == request.tenantId?
requestedReport is visible to this principal?
=> all true, otherwise deny
~~~

Do not rely merely on hidden UI buttons, `tenantId` query parameters, or a default `ROLE_USER`. Authority mapping must derive from approved application entitlements; SAML groups may be used only under a trusted mapping contract and **must never bypass a local lock**.

### 7.4. Extension points and invariants to preserve

| Need | Suitable extension point | What must be preserved |
| --- | --- | --- |
| Look up local user after SAML validation | Response authentication conversion/provider extension, or admission component wired into the SAML authentication manager. | Keep all default SAML validators and block session creation when the account is locked. |
| Map IdP subject → local user | Identity-binding repository with unique constraint. | Stable issuer/subject; block merging via unguaranteed emails. |
| Map permissions | Approved entitlement service and authority mapper. | Deny precedence, map only allowlisted groups, check tenant. |
| URL-level access checks | `authorizeHttpRequests`. | Authenticated alone is insufficient for sensitive resources. |
| Method/resource access checks | `@EnableMethodSecurity`, `@PreAuthorize`, business policy. | Tenant ownership/resource authorization. |
| Account errors/redirects | Authentication failure handler, access denied handler. | Avoid login loops and never leak SAMLResponse. |
| Locking an account with an active session | Spring Session/session registry, policy status/version, revocation service. | Revoke across all nodes and API tokens within SLA. |

## 8. When an account is locked after already logging in

This is a common lifecycle gap: a user logs in via SAML at 09:00, establishing an SP session valid until 17:00; at 09:10 an admin locks the local account, yet the SP checked status only during the 09:00 callback. If `SecurityContext` in the session stores `Authentication` with old rights, the user can keep calling APIs until session expiry.

Mitigations:

- **Session revocation:** look up all sessions for `localUserId` and invalidate them in a shared session store (e.g., Spring Session) or custom revocation registry. Plan for multi-node/multi-region setups.
- **Account security version:** store `securityVersion` or `revokedAfter` on the account; critical requests compare against the current session/token.
- **Re-check at business boundaries:** read current account status and entitlements before sensitive actions; keep caches short with explicit invalidation if revocation SLAs are tight.
- **JWT/stateless APIs:** issued JWTs are not automatically revoked when the DB flips to `LOCKED`. Use short TTLs, introspection/revocation, or live account policy checks at the Resource Server.
- **Event-driven offboarding:** when HR/SCIM/IAM disables an account, emit session/token/role revocation events with retries, auditing, and delayed-event handling.
- **Cross-SP behavior:** locking at one SP does not automatically log out the IdP or other SPs. For organization-wide security locks, coordinate with IAM/IdP and sibling SPs.

**Never promise "instant lock"** if status/entitlement caches actually stay stale for 15 minutes or revocation waits until the next login. Test SLAs across all replicas, failovers, and datastore outages.

## 9. Distinguishing HTTP outcomes and user experience

| State | Usually appropriate handling | Notes |
| --- | --- | --- |
| Unauthenticated API call | **401 Unauthorized**, or redirect to IdP for web apps. | Controlled by `AuthenticationEntryPoint`. |
| Invalid SAML response | Authentication failure. | Never disguise signature errors behind a fake "account locked" message. |
| Valid SAML yet local `LOCKED/DISABLED` | Authentication failure, no SP session created. | ACS endpoint can redirect to an error page instead of raw HTTP 401. |
| Local `PENDING_APPROVAL` | Deny product usage; display pending-approval notice. | If a pending page exists, grant strictly limited access. |
| Authenticated/admitted yet lacking resource rights | **403 Forbidden** or access-denied page. | Handled by `AccessDeniedHandler`. |
| Status DB unavailable | **Fail closed** with retryable error. | May return 503 for APIs; never grant default access. |

**Avoid login loops:** if the user still has an IdP SSO session, redirecting immediately from "local account locked" back to the IdP returns another valid SAML assertion and blocks again in an infinite loop. Show an explanation page instructing them to contact admin/approval instead, without requiring denied permissions. Also prevent user enumeration: public notices must not leak sensitive internal states before identity is established.

### 9.1. Minimal audit log

~~~text
event=FEDERATED_LOGIN_DENIED
time_utc=2026-11-07T03:00:00Z
idp_registration=corporate
trusted_issuer=urn:example:idp:corporate
local_account_id=user-42
reason=ACCOUNT_LOCKED
correlation_id=trace-024b
outcome=AUTHENTICATION_FAILURE
~~~

Log trace/correlation ID, policy version, verified issuer, and reason code for governance. Never log full SAMLResponse XML, PII-bearing NameIDs, cookies, private keys, or security investigation details in public responses. Distinguish `not found` vs. `database unavailable` inside internal logs; user-facing messages may look identical while operations must tell them apart.

## 10. Testing critical scenarios

| Test case | Safe outcome |
| --- | --- |
| Valid IdP SAML, local ACTIVE, authorized for SP. | Login succeeds; authorities mapped from approved entitlements. |
| Valid SAML, local account LOCKED. | No new Authentication/session created. |
| Valid SAML, local account DISABLED. | Rejected, and prior sessions/tokens revoked within SLA. |
| Valid SAML, account PENDING_APPROVAL. | Business features inaccessible; pending view does not escalate rights. |
| Valid SAML, no local account, JIT disabled. | Denied; no silent account creation. |
| Valid SAML, JIT enabled yet missing approval/tenant/license. | Grants no privileges; may create PENDING if policy permits. |
| Valid SAML, IdP group contains admin yet locally locked. | Local deny wins. |
| ACTIVE yet missing `reports:read`. | Login may succeed; resource returns 403. |
| Authorized for tenant A yet calls tenant B API. | 403; zero cross-tenant data leakage. |
| Email reassigned to a new federated identity. | Never attaches to old privileges; uses verified stable subject. |
| Concurrent JIT logins on two nodes. | Unique binding prevents duplicates or bypassing locks. |
| DB/status store failure during login. | Fail closed; never defaults to ACTIVE. |
| Account locked mid-session. | Session cannot continue past revocation SLA. |
| Role revoked mid-session. | Authorization sees new status or session/token is revoked. |
| SAML response bad signature or `InResponseTo` mismatch. | Rejected before considering JIT account creation. |
| IdP still holds SSO session after local lock. | No login loop; displays safe error page. |

Integration tests should run with signed SAMLResponses from a test IdP and standard federation metadata to prove the **exact order: SAML validation → local admission → session**. Java policy unit tests cannot replace Spring Security filter/provider tests. Also test multi-node setups, stale caches, JIT races, tenant boundaries, and revoked sessions.

## 11. Common mistakes and fixes

1. **"If the IdP authenticated them, the app must let them in."** Wrong: admission and resource authorization belong to the SP.
2. **"Local lock is overridden if the IdP group is admin."** Wrong: local locks must take higher precedence.
3. **"Just hide forbidden buttons in the frontend."** Wrong: enforce on APIs/methods.
4. **"Having a `UserDetailsService` bean makes SAML login check `isEnabled` automatically."** Wrong: wire it explicitly into the SAML flow.
5. **"Email is the sole safe key."** Wrong: emails change/get reused; use issuer + stable subject.
6. **"No ACTIVE record found, so run JIT to create a new account."** Wrong: may miss LOCKED/DEPROVISIONED accounts.
7. **"Map every IdP group into an app role."** Wrong: require an allowlist and approval policy.
8. **"Checking status once at login is enough."** Wrong: accounts can be locked while sessions remain open.
9. **"Return 401 for every missing-permission error."** Wrong: authenticated users lacking resource rights usually get 403.
10. **"When the local DB fails, grant temporary access to preserve uptime."** Wrong: fail closed on mandatory authorization checks.
11. **"SAML succeeded, so skip tenant checks on the backend."** Wrong: invites BOLA/IDOR.
12. **"Redirecting repeatedly to the IdP fixes local locked."** Wrong: causes an infinite loop while the IdP session is valid.
13. **"Local lock means every other SSO system logged out."** Wrong: coordinate lifecycle/revocation with IAM.
14. **"`ROLE_USER` implies all permissions."** Wrong: never grant default business privileges outside policy.

## 12. Implementation checklist

1. Does identity binding pin **trusted issuer + stable subject + tenant scope**, blocking email-based merges?
2. Does the local account track `ACTIVE/LOCKED/DISABLED/PENDING` with explicit deny precedence?
3. Does the **admission check** run after SAML validation and before creating `Authentication`?
4. Does `NO_LOCAL_ACCOUNT` deny by default, or JIT-provision strictly with eligibility, unique constraints, auditing, and least privilege?
5. Are LOCKED/DISABLED accounts checked before JIT to prevent re-creation?
6. Are permissions/roles derived from **approved application entitlements**, rather than blindly trusting SAML groups?
7. Does every API/service enforce tenant, ownership, and resource-level checks independently of login?
8. Are existing sessions/JWTs revoked when an account is locked mid-session?
9. Is the revocation SLA tested across multi-node clusters, stale caches, and database outages?
10. Do error handlers avoid login loops, user enumeration, and PII/SAMLResponse leaks?
11. Have local LOCKED, DISABLED, PENDING, NO_ACCOUNT, and ACTIVE-without-permissions states been tested with a test IdP?
12. Are reason code, trusted issuer, local account ID, and policy version audited on every denial?

## References

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses, response authentication converter](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Method Security and @PreAuthorize](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — HTTP Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security API — UserDetails.isEnabled and isAccountNonLocked](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security API — AuthenticationManager and account status exceptions](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
