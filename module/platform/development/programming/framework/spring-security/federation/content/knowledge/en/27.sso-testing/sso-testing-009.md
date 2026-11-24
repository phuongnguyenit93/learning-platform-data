# Testing Account Linking, Missing Local Roles, and Locked Users in SSO

> **Module:** Spring Security – federation · **Group:** SSO Testing. This Knowledge article focuses on three business/security flaws that typically surface only **after SSO verification succeeds**: (1) binding an IdP identity to the **wrong local account**, (2) a user holding a valid SAML Assertion/OIDC ID Token who **lacks local permissions** to access features, and (3) an account marked **locked/disabled/suspended** at the RP still being allowed to log in because developers trusted IdP status alone. It covers identity modeling, policies, testing layers, standalone Java 17 code, Spring Security examples, and negative test matrices. All identifiers, emails, URIs, and accounts are synthetic test data.

## 1. The Problem: SSO Success Does Not Mean Account or Permission Grant

Suppose an enterprise has IdP `https://idp.example.org` and reporting app `https://reports.example.org`. The app already verified the signature and SSO token:

```text
SAML IdP / OIDC Provider
          |
          | signed assertion / validated ID Token
          v
Spring Security federation login
          |
          v
External identity:
  issuer  = https://idp.example.org
  subject = opaque-sub-92df
  email   = an@example.org
          |
          v
Local account resolver / link registry
          |
          +--> Local user ID: user-17
          +--> Local status: LOCKED
          +--> Local roles: []
          |
          v
Policy gate: reject even though IdP authentication succeeded
```

Common anti-patterns:

- **Auto-linking by email:** seeing `email=an@example.org` in a token and immediately linking it to a local account with the same email. An attacker at another provider or a recycled email can hijack the local account.
- **Granting default permissions:** an SSO user lacking a `LocalRole` record gets auto-assigned `ROLE_USER` or `ROLE_ADMIN` “to avoid 403s.”
- **Ignoring local locks:** the IdP says the user authenticated, and the app skips checking `isAccountNonLocked`/`enabled` in the local store, or stale sessions continue accessing resources.
- **JIT creating duplicate accounts:** link not found ⇒ creates a new local account even though a disabled/locked account or different subject mapping already exists.
- **Using email as a key:** emails change, go unverified, use aliases, or get reassigned, causing duplicates/mislinks.
- **Using OIDC mocks and treating full SSO as tested:** `oidcLogin()` creates a fake principal and can bypass the link service if the real login path was never exercised.

**Goal:** verify **whom the IdP asserted**, link the **right local identity**, check **local account status**, and then grant exact **local authorities**. Whenever linking/permission/status evidence is missing, enforce **deny by default**.

### 1.1. Learning Outcomes

After this lesson, you will:

1. Distinguish external identity, local account, account linking, JIT provisioning, authentication, and authorization.
2. Design proper link keys for OIDC `(iss, sub)` and SAML `(assertingPartyEntityId, persistent NameID and required qualifiers)`.
3. Understand why `email_verified`, names, phone numbers, or matching emails are insufficient to link an existing account.
4. Describe **link/unlink flows with reauthentication**, session binding, state/nonce/CSRF, ownership checks, and uniqueness constraints.
5. Reject login—or at minimum deny protected actions—when **local roles/entitlements** are missing, depending on feature policy.
6. Reject `LOCKED`, `DISABLED`, and `SUSPENDED`/`DELETED` accounts despite valid SAML/OIDC signatures.
7. Avoid assuming `UserDetailsService` and `DaoAuthenticationProvider` automatically enforce local account status on federated logins.
8. Write unit, repository/transaction, MockMvc Security, and full SSO callback tests, including active sessions after locks.
9. Run standalone Java 17 modeling login/link/role/status rules with deterministic stdout.
10. Build telemetry, runbooks, and checklists that never leak PII or account existence through error responses.

## 2. Distinguishing 5 Commonly Confused Concepts

| Concept | Meaning | Who Decides? |
| --- | --- | --- |
| **External authentication** | IdP verifies identity and sends signed assertion/ID Token | IdP; SP/RP must validate |
| **External subject** | `sub` in OIDC or `NameID` in SAML with issuer/context | Supplied by IdP; RP verifies before use |
| **Local account linking** | Binds an external subject to a local account ID | **RP**, based on policy and ownership proof |
| **Local account status** | `ACTIVE`, `LOCKED`, `DISABLED`, `CLOSED`, `PENDING` | RP/user directory/HR with administrative authority |
| **Local authorization** | `REPORT_VIEWER`, `REPORT_ADMIN`, project/tenant permissions | App policy and trusted entitlement sources |

**Authentication ≠ Account linking ≠ Authorization.** The IdP can prove the user is `opaque-sub-92df`, yet it has no authority to declare that ID corresponds to local `finance-admin`, let alone grant access to all reports.

### 2.1. Four Sequential Decisions

```text
1. VERIFY FEDERATED ASSERTION
   Is token/assertion from trusted issuer for our RP?
          |
          +-- no --> reject, no local account mutation
          v
2. RESOLVE LOCAL ACCOUNT
   Is (issuer, subject) linked to a local account?
          |
          +-- no --> controlled JIT onboarding or reject
          v
3. CHECK LOCAL ACCOUNT STATE
   Is local account ACTIVE, not locked/disabled/expired?
          |
          +-- no --> reject and revoke/avoid authenticated session
          v
4. CHECK LOCAL ROLE / RESOURCE PERMISSION
   Does the account have verified RP-specific rights?
          |
          +-- no --> deny protected action, optionally deny login
          v
ALLOW only the authorized function
```

At every rejection step, **create no new local authenticated session**, write no unauthorized account links, and auto-grant no roles; protect CSRF/session cookies and log sanitized reason codes.

### 2.2. Check Before or After Auth Session Creation?

In strict applications, `LOCKED` status can **reject the federated login callback** before writing `Authentication` to `SecurityContext`. For “missing role,” an application may adopt:

- **Strict login policy:** lacking any valid app role ⇒ reject login / create no authenticated app session.
- **Login allowed, feature denied:** create a session with **no protected authorities**, allowing non-sensitive onboarding pages while protected routes still return 403.

Both are valid when documented clearly. **Never promote a roleless user to admin or allow protected data access**. The Java demo later uses the strict policy on `REPORT_VIEW` for testing clarity.

## 3. Link Identifiers Must Be Stable and Issuer-Scoped

### 3.1. OIDC: Use `issuer + subject`

Per OIDC Core, `sub` is a subject identifier scoped to its issuer; a `sub` string from OP A does not mean the same string from OP B is the same person.

Standard key:

```text
OIDC external identity key:
  protocol = OIDC
  issuer   = https://idp.example.org
  subject  = opaque-7f89c2

NOT:
  email = an@example.org
```

The issuer must be the **issuer inside the verified ID Token**, never pulled arbitrarily from a query string or browser cookie. Validate `aud`, `exp`, `nbf`, `nonce`/`state`, and signatures per OIDC flow. For multi-tenant apps, include trusted tenant/provider registrations in the link as needed so subjects from another tenant cannot map onto the same account.

### 3.2. Pairwise Subjects and Account Recovery

An OP may issue different pairwise `sub` values per sector identifier. If an app changes client registrations or sectors, `sub` may change per provider policy. Never pair by email during migrations; require admin/IdP-verified migration or protected user re-linking.

`email_verified=true` states the OP asserts the email was verified under its own process—it **does not** prove the user owns the RP's historical local account carrying that email. Emails get reassigned inside companies, change on name/domain changes, serve as shared mailboxes, or carry provider-specific semantics.

### 3.3. SAML: IdP `entityID` + `NameID` Context

SAML Assertion contains:

```xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.example.org/saml"
      SPNameQualifier="https://reports.example.org/sp">
    opaque-saml-sub-77
  </saml:NameID>
</saml:Subject>
```

This XML is an **illustrative fragment** lacking `Response`, signature, and bearer confirmation; never use it for real login. SAML link keys should bind the trusted asserting party `entityID`, `NameID` format, and qualifiers per the IdP contract. `NameID` may be transient, persistent, `emailAddress`, or custom; **transient `NameID` is unsuitable as a durable local account key** if its value changes every login.

A practical rule:

```text
account_link(
  protocol,
  trusted_idp_entity_id,
  name_id_format,
  name_qualifier,
  sp_name_qualifier,
  stable_name_id_value
) -> immutable local_account_id
```

Never assume any `NameID` formatted as `emailAddress` may auto-link to a local account with that email. External identity must come from an **assertion verified for signature/issuer/audience/recipient/time/InResponseTo/replay**.

### 3.4. Never Link by Username / Full Name

Display names, `preferred_username`, email aliases, `upn`, or `sAMAccountName` need not be unique across realms. “LDAP DN path contains the same username” does not prove ownership. When a user is renamed, the linked account should retain its immutable local ID rather than spawning a second account.

### 3.5. Mapping Table with Constraints

Illustrative schema:

```sql
CREATE TABLE local_account (
  id               VARCHAR(64) PRIMARY KEY,
  status           VARCHAR(20) NOT NULL,
  version          BIGINT NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE external_identity_link (
  id               BIGINT PRIMARY KEY,
  local_account_id VARCHAR(64) NOT NULL,
  protocol         VARCHAR(10) NOT NULL,
  issuer_key       VARCHAR(512) NOT NULL,
  subject_value    VARCHAR(1024) NOT NULL,
  subject_format   VARCHAR(256),
  linked_at        TIMESTAMP NOT NULL,
  UNIQUE (protocol, issuer_key, subject_value),
  FOREIGN KEY (local_account_id) REFERENCES local_account(id)
);

CREATE TABLE local_grant (
  local_account_id VARCHAR(64) NOT NULL,
  role_code        VARCHAR(128) NOT NULL,
  tenant_id        VARCHAR(64) NOT NULL,
  PRIMARY KEY (local_account_id, role_code, tenant_id)
);
```

**This is a design schema**, not production DDL: DB-specific types, collations, case sensitivity, indexes, encryption/retention, nullable subject qualifiers, and multi-tenant uniqueness must be finalized. In particular, **never include nullable columns inside a composite unique key** without understanding DB semantics; normalize SAML qualifiers via normalized keys or appropriate constraints.

**Why enforce `UNIQUE` in the DB:** two concurrent login/linking callbacks must never bind the same external identity to **two local accounts**. Checking `exists()` then `insert()` is insufficient without transaction isolation and unique constraints.

## 4. Secure Account-Linking Model

### 4.1. Linking Is Not Login

A user already holds local account `user-17` and wants to add an OIDC account from IdP B:

1. User logs into their **existing local account** via a currently trusted method.
2. RP requires **recent reauthentication**/step-up for the sensitive operation.
3. RP creates a server-side linking transaction holding `state`, nonce, expiry, initiating local account, tenant, provider, and CSRF/session binding.
4. Browser redirects to the **approved IdP** and completes the protocol-compliant SSO flow.
5. RP validates the ID Token/SAML Assertion via the trusted IdP registration, `state/nonce/InResponseTo`, and replay controls.
6. Extract the stable external identity from the **verified** assertion/token.
7. Verify the target local account is still `ACTIVE`; never locked/disabled, preventing account takeover.
8. Transactionally insert the external link enforcing uniqueness; if already linked to another account, **reject** and require recovery/incident handling.
9. Rotate/invalidate sensitive session state if policy requires, audit the event, and notify the user via a trusted channel.
10. Grant no additional local roles merely from a new link; authorization stays under RP control.

**Never** create a link just because the browser passed `?email=an@example.org` or an email claim matched a local account.

### 4.2. Why Are “Two Proofs” Required?

To link **X (external identity)** to **A (local account)**, the RP must have proof **the user currently controls A** and **the user just authenticated X**. One proof alone is insufficient:

- Logged in as X without verifying A ⇒ must not take over A by email.
- Logged in as A without verifying X ⇒ attacker could attach a self-asserted external ID.
- Both present, yet the response is unbound to pending link state ⇒ **login CSRF/account-linking CSRF** can bind the attacker's identity into the victim's session.

Reauthentication must be fresh relative to risk: typically verifying a recent local session, MFA/step-up when sensitive, and single-use code challenges/state.

### 4.3. Link-Initiated vs. Login-Initiated

In OIDC, a callback after authorization code exchange must distinguish intent:

```text
pending_flow = LOGIN
  -> resolve external identity to existing local account
  -> if unlinked, JIT/provision/reject by policy

pending_flow = LINK_EXISTING_ACCOUNT
  -> must have authenticated local account + recent reauth
  -> verify external identity + session-bound state
  -> link only to that same local account

NEVER:
  OIDC callback has any email => attach to first local account
```

Sharing one callback endpoint is fine, provided **server-side state** distinguishes the flow. Never treat browser-supplied `state` alone as authorizing link creation—validate it against the RP's stored transaction.

### 4.4. Unlinking and Last-Factor Lockout

When unlinking:

- Require an authenticated local account, recent reauthentication, and CSRF protection.
- Verify the link belongs to this account; never delete someone else's link by ID.
- If it is the **last remaining login method**, warn and require an approved recovery method first, or deny unlinking per policy.
- Revoke sessions/tokens/federated access tied to the removed link as needed.
- Audit/notify; never write raw ID Tokens/SAML Assertions into audits.
- After unlinking, **the removed external identity must no longer log into A**.

### 4.5. Account Migration and Merging

Merging two local accounts carrying business data is a **security-sensitive merge**, not an “update foreign key by email.” Verify ownership of both accounts, resolve privilege conflicts, preserve historical logs, execute transactional migration, and require review. When an untrusted external subject suddenly appears with a matching email, **never auto-merge**.

## 5. JIT Provisioning — When May a New Account Be Created?

### 5.1. Missing Link Does Not Always Mean Create

Just-In-Time (JIT) provisioning can fit an employee portal backed by a verified enterprise IdP and invitation policy. Yet if an RP holds financial or customer-care data, account creation may require invitations, group eligibility, or administrator approval.

When an SSO identity is unlinked:

| Condition | Action |
| --- | --- |
| RP forbids JIT | Reject / onboarding pending; create no account |
| JIT allowed with expected issuer + tenant + validated entitlement | May create local account with **minimum roles** per policy |
| Email matches existing local account while subject is unlinked | No auto-link; require explicit verified link/recovery |
| Existing `LOCKED` local account has similar email | Never create a bypass account around the lock |
| User deprovisioned while IdP still issues valid tokens | Deny per authoritative RP/HR status and policy |
| Subject belongs to un-onboarded external IdP | Reject; never auto-add issuers |
| Invitation expired or already redeemed | Reject; create no account |
| Concurrent JIT callbacks | Transaction/unique constraint prevents duplicates |

### 5.2. JIT and Idempotency

Two callbacks for the same external identity arrive concurrently:

```text
Callback A: external key K has no link yet
Callback B: external key K has no link yet

Unsafe:
  both create new account
  both try link K
  one fails, orphan account remains

Safer:
  transaction + unique external key
  upsert/retrieve canonical local account
  handle unique-conflict deterministically
  clean any orphan artifacts
```

Never run “if no row then insert” without a DB guard. Test concurrency with 10–100 requests against a test DB and assert exactly one mapping and zero orphans. Never auto-unlock an old account when a callback arrives with the same email.

### 5.3. Invitation-Based Onboarding

If permitting automatic provisioning, bind invitations to the **expected email/identity** per IdP assurance, single-use, expiry, tenant, purpose, and reauthentication. Email matching can serve as an **additional verification signal**, never sole proof to link a privileged account. Critical apps require admin approval and verified ownership flows.

## 6. Local Permissions Do Not Come from SSO Tokens by Default

### 6.1. IdP Authenticates; RP Authorizes

OIDC `scope=openid profile email` is an OIDC claim request, not the app's `ROLE_REPORT_ADMIN`. SAML `AttributeStatement` may carry groups or roles, yet the RP is **not obligated** to promote all of them into privileged authorities. Trusted roles must derive from app policy, tenant, resource entity, and trusted entitlement sources.

Example:

```text
IdP authenticated:
  issuer = https://idp.example.org
  subject = employee-tenant-scoped-id

Local account:
  id = user-17
  status = ACTIVE
  grants = []

Protected endpoint:
  GET /reports/financial
  requires REPORT_VIEW

Decision:
  access DENIED (no local grant)
```

Never grant privileges simply because a token includes `email_verified=true`, group `Employees`, or profile claim `department=Finance`. When an official authorization contract uses IdP entitlements, map explicitly: **trusted issuer + audience + entitled value + tenant + freshness**.

### 6.2. Role Names in Spring Security

Spring Security commonly uses `GrantedAuthority` strings like `ROLE_REPORT_VIEWER`. `hasRole("REPORT_VIEWER")` checks authority `ROLE_REPORT_VIEWER` with the default prefix; `hasAuthority("REPORT_VIEW")` checks the exact string. **Never mix naming conventions** causing false passes/failures in tests.

A user holding only `OIDC_USER` or `SCOPE_openid` does not automatically hold `ROLE_REPORT_VIEWER`. `@WithMockUser(roles="ADMIN")` in unit tests injects authorities onto a mock; it does not prove whether production mapping grants them accurately.

### 6.3. “Missing Role” Differs from “No Local Account”

| State | Expected Decision |
| --- | --- |
| Unlinked subject | Deny or controlled onboarding |
| Linked `ACTIVE` account with empty grant set | Deny protected routes; may allow onboarding page per policy |
| `ACTIVE` with `ROLE_VIEWER` hitting endpoint needing `ROLE_ADMIN` | Authenticated, **403** on admin feature |
| `ACTIVE` with right role, yet grant belongs to another tenant | Deny access to current tenant's resources |
| Expired/revoked role | Deny/refresh; never reuse stale session indefinitely |
| IdP token claims “admin” without local policy approval | Never auto-grant |
| IdP omits optional `groups` claim | Never default to full access; fail closed |
| Role sync service times out | Never create temporary admin roles; deny or use approved least-privilege grace policy |

### 6.4. Reject Login or Return 403?

Separate two acceptance criteria:

1. **SSO Login Policy:** if the RP requires at least one application entitlement, the callback must reject roleless users.
2. **Resource Authorization Policy:** the callback may create a minimal session, while `/reports/**` must still deny without `REPORT_VIEWER`.

Document which policy is tested. Do not call login success a bug if the app intentionally permits onboarding, and do not call a 403 on a protected endpoint an SSO signature failure.

### 6.5. Freshness / Role Revocation

Roles can change between SSO login and a later request. A cached `SecurityContext` holding stale granted authorities may linger in the session. For high-risk actions, design:

- Re-reading authoritative grants or short authorization TTLs.
- Revocation event cache invalidation.
- Session/token invalidation when a user is revoked.
- Method-level and object-level authorization, not just URL paths.
- Never passing raw LDAP groups to browsers/tokens when the RP only needs an entitlement.

**Never sync IdP permissions on every request by disabling caching blindly** if availability forbids it; document consistency risks and test windows explicitly.

## 7. Locked Accounts: Local Status Must Override SSO Success

### 7.1. Different Statuses

| Local Status | Example Meaning | Login/Access Policy |
| --- | --- | --- |
| `ACTIVE` | Allowed to use app if grants permit | Evaluate roles/tenant |
| `LOCKED` | Locked by admin/risk/abuse | Reject login and protected access |
| `DISABLED` | Account turned off by HR/IT | Reject |
| `SUSPENDED` | Temporarily suspended or under review | Reject or restrict per approved policy |
| `PENDING` | Unapproved / incomplete onboarding | Restricted onboarding only |
| `CLOSED/DELETED` | No longer permitted | Reject; never auto-recreate via JIT |

**Local locks differ from IdP locks.** The IdP may still let the user log into other systems; the RP must still obey local status. Conversely, if the IdP account is locked while the user holds an existing RP session, access may continue until revoked; maintain a cross-system logout/deprovisioning policy.

### 7.2. Does `UserDetailsService` Automatically Protect SAML/OIDC?

**Not automatically.** Spring Security's `UserDetailsService` is used primarily by `DaoAuthenticationProvider` for username/password auth. Methods `UserDetails.isEnabled()`, `isAccountNonLocked()`, and `isAccountNonExpired()` run only **in flows/providers that invoke them**.

A `Saml2Authentication` or `OAuth2AuthenticationToken` can be created successfully **without ever calling a local `UserDetailsService`** unless the application explicitly performs local lookup/checks. Therefore:

- Never register `@Bean UserDetailsService` alone and assume SAML/OIDC callbacks check `locked`.
- Never treat `Authentication.isAuthenticated()` as meaning “local account active.”
- Place a **local account policy gate** at the right boundary before issuing full authenticated app sessions/authorities.
- When using a custom `AuthenticationProvider` or OIDC `OidcUserService`, preserve the framework's signature/issuer/audience/state/nonce validators.
- For SAML, process the principal **only after OpenSAML validation**; never parse raw XML/`NameID` yourself.

### 7.3. SSO Lockout Differs from Password Brute-Force Lockout

An SSO user uses no local password, so “5 wrong local passwords” may not apply. Yet locks triggered by security incidents, HR termination, or admin rules **remain fully binding** at the RP. Tests must never unlock accounts upon receiving a valid SSO token. Unlocking must go through an authorized, audited local workflow with revalidation.

### 7.4. Users Holding an Active Session Before Being Locked

Suppose a user logs in via SSO at 09:00. An admin locks the account at 09:15. If `HttpSession` already holds `ROLE_REPORT_VIEWER` and a 09:16 request skips re-checking local status, the user can still read data.

Design per risk level:
- Upon lock: invalidate active sessions or publish revocation events across nodes/regions.
- For stateless/JWT APIs: token revocation, short TTLs, introspection, or a backend status gate.
- Re-check account status on sensitive endpoints or cache status with a tight TTL.
- Separate **login-time denial** from **active-session revocation** in tests; one does not replace the other.
- Never promise `session.invalidate()` on one node instantly revokes distributed sessions unless architecture supports it.

### 7.5. `SecurityContext` and Session Fixation

A successful SSO callback must never reuse an attacker-controlled session after link state changes. Configure Spring Security session fixation protection explicitly; test new session creation per policy and cookie protections. When login is rejected due to locking, store no `Authentication` and render no protected data on follow-up requests with the same cookie; clear any stale context.

## 8. Order of Decisions in the Local Gate

An illustrative policy for the reporting app:

```text
external auth verified?                  NO -> DENY_UNTRUSTED_SSO
trusted issuer + subject present?        NO -> DENY_BAD_SUBJECT
link exists?                             NO -> DENY_UNLINKED
linked local account exists?             NO -> DENY_ORPHAN_LINK
status ACTIVE?                           NO -> DENY_LOCKED/DISABLED
role REPORT_VIEWER for current tenant?   NO -> DENY_MISSING_ROLE
resource-level access permitted?         NO -> DENY_RESOURCE
all checks pass?                        YES -> ALLOW
```

**Never** let a JIT branch execute after `DENY_LOCKED` to spawn another account bypassing the lock. An IdP identity already linked to a locked user must never create a new local account simply because “login failed.”

### 8.1. Internal-Only Error Codes

Example reason codes:

```text
SSO_INVALID_ASSERTION
SSO_UNLINKED_EXTERNAL_SUBJECT
LOCAL_ACCOUNT_LOCKED
LOCAL_ACCOUNT_DISABLED
LOCAL_GRANT_MISSING
LOCAL_TENANT_MISMATCH
LINKING_PROOF_MISSING
LINKING_ALREADY_BOUND
SESSION_REVOKED
```

Externally, return a generic message like “Unable to log in or access. Contact your administrator if needed,” revealing neither whether an email exists, whether the account is locked, nor which roles the user holds. OWASP Authentication Cheat Sheet recommends **generic authentication errors** to limit account enumeration. Internal logs may keep reason codes/correlation IDs, never raw JWTs/SAMLResponses/emails.

### 8.2. Check Status Before Roles

A `LOCKED` account may still hold roles in the DB. If code checks only roles and grants access when `ROLE_REPORT_ADMIN` is present, it bypasses the lock. Therefore, enforce logical ordering so the **status gate** governs every allowed action; at the authorization layer, revalidate status as needed and never treat a role as proof the account is active.

## 9. Spring Security OIDC: Controlled Hook Points for Local Policy

### 9.1. Spring OIDC Login Component

Spring Security OIDC login uses `OidcUserService` to load/interpret user claims after framework token validation. Spring Security docs allow delegating `OidcUserService` and mapping granted authorities. You can compose a custom `LocalIdentityGate` service, **never replacing ID Token verification with a handwritten parser**.

Fragment:

```java
import org.springframework.security.oauth2.client.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

// Fragment: localIdentityGate is an RP bean/adapter.
// This code must be wired into the application's SecurityFilterChain.
OAuth2UserService<OidcUserRequest, OidcUser> gatedOidcService(
        LocalIdentityGate localIdentityGate) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser verifiedUser = delegate.loadUser(userRequest);
        String issuer =
            verifiedUser.getIdToken().getIssuer().toString();
        String subject = verifiedUser.getIdToken().getSubject();

        boolean allowed = localIdentityGate.isActiveAndEntitled(
            issuer, subject, "REPORT_VIEWER");

        if (!allowed) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error("access_denied",
                    "Local account policy denied login", null));
        }
        return verifiedUser;
    };
}
```

**This is an illustrative fragment**, not a runnable standalone program: you must define `LocalIdentityGate`, repositories, entity/tenant policies, and wiring. On the real login path, token validation covers issuer, audience, nonce/state, signing key, expiry, and OIDC provider/client controls. Never treat `isActiveAndEntitled` as part of JWT signature verification.

### 9.2. Wiring the Service into `SecurityFilterChain`

Example wiring in a Spring Boot application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        LocalIdentityGate localIdentityGate) throws Exception {

    return http
        .authorizeHttpRequests(a -> a
            .requestMatchers("/reports/**").hasRole("REPORT_VIEWER")
            .anyRequest().authenticated())
        .oauth2Login(o -> o
            .userInfoEndpoint(u -> u
                .oidcUserService(
                    gatedOidcService(localIdentityGate))))
        .build();
}
```

**Real local authority mapping must be added**: the fragment above rejects users lacking local entitlement, yet returns `verifiedUser` carrying default IdP/Spring authorities—which usually lack `ROLE_REPORT_VIEWER`. For `hasRole("REPORT_VIEWER")` on protected endpoints to succeed, your implementation must map **verified local grants** to `GrantedAuthority("ROLE_REPORT_VIEWER")` on the final `Authentication` (via custom `OidcUser`/`GrantedAuthoritiesMapper`), never blindly trusting scopes or IdP roles. Otherwise tests will see login pass while endpoints return 403—a configuration bug to test for, never “fixed” by opening `permitAll`.

### 9.3. Is a Custom `OidcUser` Needed?

You can use `GrantedAuthoritiesMapper` to map OIDC authorities, or a delegating `OAuth2UserService` to load local grants and construct a `DefaultOidcUser` with the right authorities. Depending on Spring version, `DefaultOidcUser` requires the ID Token and UserInfo. Preserve trusted protocol claims/subject and grant local authorities strictly from status/tenant-verified lookups. Never copy raw `groups=admin` to local `ROLE_ADMIN` without contract approval.

### 9.4. Check Local Lock Before Returning the Principal

If `localIdentityGate` detects a locked/disabled account, throw an appropriate `OAuth2AuthenticationException` into the flow so the failure handler runs and avoids creating an authenticated session. Merely rendering “locked” in a post-login controller while leaving `SecurityContext` authenticated lets other endpoints grant access.

### 9.5. `UserDetailsService` Does Not Automatically Apply to OIDC

Declaring a local `UserDetailsService` does not guarantee `OAuth2LoginAuthenticationProvider` calls it. That is why real callback tests are mandatory: verify `OidcUserService`/custom mapping or the local auth gate executes and propagates failures **before session establishment**.

## 10. Spring Security SAML2: Check Local Accounts Even After Validation

### 10.1. Do Not Read Raw `NameID`

In Spring Security Servlet SAML2, `OpenSaml5AuthenticationProvider` (or equivalent in your release) verifies the Response/Assertion against a trusted `RelyingPartyRegistration`. Post-validation, the principal is `Saml2AuthenticatedPrincipal`.

Example **controller fragment reading information only after authentication**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;

public String viewName(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
    // Only after SAML authentication provider has validated assertion.
    return user.getName();
}
```

`getName()` does not prove it is a **persistent stable account key**. Bind it with the trusted asserting party `entityID` and `NameID` format/qualifiers per registration. Another person at a different issuer may present an identical `NameID` string.

### 10.2. Choosing Where to Enforce

Depending on Spring Security release, use a **validated response authentication converter**, a wrapper provider after OpenSAML validation, or service mapping prior to publishing the final `Authentication`. Preserve all signature, issuer, audience, `Conditions`, `SubjectConfirmation`, `InResponseTo`, and replay checks. Under strict login policy, the local status/role gate must reject **before the authenticated session is saved**.

If an architecture checks status only in `AuthenticationSuccessHandler` after the provider built `Authentication`, ensure the failure path **clears `SecurityContext`/invalidates the session** and exposes no protected resources during the callback; enforcing at the conversion/provider boundary is preferable and easier to test.

### 10.3. Multi-Tenant SAML

If an RP accepts IdP A and IdP B, a `NameID` string `employee-123` from both IdPs must never map to the same local account automatically. Key mappings by approved `registrationId`/`entityID` + stable subject. Test a signed IdP B assertion carrying the same email/`NameID` as local admin A and confirm it **cannot** log in as A.

### 10.4. SAML Test Code Needs Signed Fixtures

A full SAML callback test needs:

- Trusted signing certificate for the test IdP.
- Exact `RelyingPartyRegistration` `entityID`/ACS/`Recipient`.
- Valid signed Response/Assertion with unexpired `Conditions` and `SubjectConfirmationData`.
- `InResponseTo` matching the pending `AuthnRequest` in SP-initiated flows.
- Unique Assertion/Response IDs, no replay, exact audience.
- Synthetic local account data with statuses/roles matching the test case.
- Verification that the callback creates or avoids creating `SecurityContext` per policy.

**Never** edit a signed fixture's XML to alter email/`NameID`/status without re-signing. Failures then come from invalid signatures rather than proving the account-linking gate works.

## 11. Spring Security Test Helpers: Right Purpose, Right Limits

### 11.1. MockMvc `oidcLogin()` Is Only a Mock Principal

Spring Security Test provides:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;

// Fragment inside a Spring MVC Test with MockMvc.
mvc.perform(get("/reports/home").with(oidcLogin()));
```

`oidcLogin()` injects an OIDC principal/test authentication into the request. It is great for testing **controllers/methods/authorization**, yet usually **skips the full OAuth2 authorization code callback, token signature, user service linking, and account gate**. A passing test using `oidcLogin()` and `hasRole` does not prove disabled local users are rejected at real login.

### 11.2. Explicit MockMvc Authorities

Example:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Fragment; not a standalone JUnit test class.
mvc.perform(get("/reports/private")
    .with(oidcLogin()
        .authorities(new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"))))
    .andExpect(status().isOk());

mvc.perform(get("/reports/private")
    .with(oidcLogin().authorities(
        new SimpleGrantedAuthority("OIDC_USER"))))
    .andExpect(status().isForbidden());
```

Expecting `403` depends on the authentication entry point, filter chain, and route policy; an already-authenticated user lacking a role typically gets 403. **Never** hardcode that outcome across all apps if failure handlers redirect/prompt login. Proper imports, JUnit/test config, and test setup are required.

### 11.3. Testing Custom Linking Services Separately

Mocking a principal + calling a real `LocalIdentityGate` can test policy if controllers invoke it per request. Still, full callbacks need integration tests because the **linking service itself might have been bypassed** by a login success handler, OAuth2 user service path, or SAML converter.

### 11.4. `@WithMockUser` Is Even Further from SSO

`@WithMockUser(roles="REPORT_VIEWER")` directly creates an authenticated user with test-declared roles. Useful for route authorization, it verifies no issuer, SAML `NameID`, OIDC `sub`, local linking, account locks, or IdP signatures. Never cite it as proof of full federation security.

### 11.5. Full Stack vs. Simulated Tests

| Test Level | What Is Verified | What Is Not Proved |
| --- | --- | --- |
| Unit local gate | `ExternalKey` lookup, status, grants, link policy | SAML/OIDC token verification |
| DB transaction test | Unique constraints, races, rollback/consistency | ACS redirects/nonces |
| MockMvc `oidcLogin()` | Protected MVC routes & method authorities | OAuth2 code flow, token parser, linking callback |
| Test with mocked `OidcUserService` | Local exception flow/mapping wiring | Real ID Token signature |
| Real OIDC test OP/auth server | State/nonce/code exchange, validated subject, link | SAML-specific signature validation |
| Real SAML test IdP signed fixtures | XML signature, issuer, `InResponseTo`, link/status gate | OIDC path |
| Multi-node session integration | Revocation after lock, distributed state | All IdP operational guarantees |
| Security/abuse tests | Enumeration, CSRF/link hijacking, stale roles | Business approval outside the app |

**A complete test suite** need not run a full browser for every role permutation; exhaustive unit tests plus critical E2E cases strike a fast, realistic balance.

## 12. Standalone Java 17: Testing Linking, Missing Roles, and Locked Accounts

The example below simulates **already-verified external logins** and a local account registry. It runs no real IdP/SAML/OIDC and **must never serve as a production authentication provider**. Its purpose is a simple JDK 17 runnable test oracle showing:

- Links are created only with **local reauthentication + validated external proof + state binding**.
- External identity keys consist of **issuer and subject**; email collisions never auto-link.
- One external identity cannot link to two local accounts.
- Roles come from the **local account**, never external claims.
- `LOCKED` and `DISABLED` are always denied despite an existing link.
- Empty roles ⇒ deny protected access.
- Locking an account **after linking** causes the next login to be rejected.
- Unlinking blocks further access by that external identity.

Save `SsoAccountLinkPolicyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class SsoAccountLinkPolicyDemo {

    enum Status {
        ACTIVE, LOCKED, DISABLED
    }

    enum LoginDecision {
        ALLOW,
        DENY_UNLINKED,
        DENY_LOCKED,
        DENY_DISABLED,
        DENY_MISSING_ROLE
    }

    enum LinkDecision {
        LINKED,
        DENY_UNKNOWN_ACCOUNT,
        DENY_LOCAL_ACCOUNT_BLOCKED,
        DENY_NOT_VERIFIED,
        DENY_ALREADY_LINKED
    }

    record ExternalKey(String issuer, String subject) {
        ExternalKey {
            Objects.requireNonNull(issuer, "issuer");
            Objects.requireNonNull(subject, "subject");
            if (issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException(
                    "issuer and subject must be nonempty");
            }
        }
    }

    record LocalAccount(
            String localId, Status status, Set<String> roles) {
        LocalAccount {
            Objects.requireNonNull(localId, "localId");
            Objects.requireNonNull(status, "status");
            roles = Set.copyOf(roles);
        }

        LocalAccount withStatus(Status next) {
            return new LocalAccount(localId, next, roles);
        }
    }

    static final class AccountGate {
        private final Map<String, LocalAccount> accounts =
                new HashMap<>();
        private final Map<ExternalKey, String> links =
                new HashMap<>();

        void register(LocalAccount account) {
            accounts.put(account.localId(), account);
        }

        void changeStatus(String localId, Status next) {
            LocalAccount account = accounts.get(localId);
            if (account == null) {
                throw new IllegalArgumentException(
                    "Unknown local account");
            }
            accounts.put(localId, account.withStatus(next));
        }

        LinkDecision link(
                String targetLocalId,
                ExternalKey external,
                boolean recentLocalReauth,
                boolean verifiedExternalProof,
                boolean stateBoundToSession) {

            LocalAccount account = accounts.get(targetLocalId);
            if (account == null) {
                return LinkDecision.DENY_UNKNOWN_ACCOUNT;
            }
            if (account.status() != Status.ACTIVE) {
                return LinkDecision.DENY_LOCAL_ACCOUNT_BLOCKED;
            }
            if (!recentLocalReauth || !verifiedExternalProof
                    || !stateBoundToSession) {
                return LinkDecision.DENY_NOT_VERIFIED;
            }

            // Demonstrates policy, NOT a safe concurrent DB transaction.
            if (links.containsKey(external)) {
                return LinkDecision.DENY_ALREADY_LINKED;
            }
            links.put(external, targetLocalId);
            return LinkDecision.LINKED;
        }

        LoginDecision login(
                ExternalKey external, String requiredLocalRole) {
            String localId = links.get(external);
            if (localId == null) {
                return LoginDecision.DENY_UNLINKED;
            }

            LocalAccount account = accounts.get(localId);
            if (account == null) {
                return LoginDecision.DENY_UNLINKED;
            }
            if (account.status() == Status.LOCKED) {
                return LoginDecision.DENY_LOCKED;
            }
            if (account.status() == Status.DISABLED) {
                return LoginDecision.DENY_DISABLED;
            }
            if (!account.roles().contains(requiredLocalRole)) {
                return LoginDecision.DENY_MISSING_ROLE;
            }
            return LoginDecision.ALLOW;
        }

        boolean unlink(
                String localId, ExternalKey external,
                boolean verifiedLocalReauth) {
            return verifiedLocalReauth &&
                    links.remove(external, localId);
        }
    }

    public static void main(String[] args) {
        AccountGate gate = new AccountGate();
        gate.register(new LocalAccount(
            "account-A", Status.ACTIVE, Set.of("REPORT_VIEWER")));
        gate.register(new LocalAccount(
            "account-B", Status.ACTIVE, Set.of()));
        gate.register(new LocalAccount(
            "account-C", Status.ACTIVE, Set.of("REPORT_VIEWER")));
        gate.register(new LocalAccount(
            "account-D", Status.ACTIVE, Set.of("REPORT_VIEWER")));

        ExternalKey a = new ExternalKey(
            "https://idp.example.org", "sub-A");
        ExternalKey b = new ExternalKey(
            "https://idp.example.org", "sub-B");
        ExternalKey c = new ExternalKey(
            "https://idp.example.org", "sub-C");
        ExternalKey d = new ExternalKey(
            "https://idp.example.org", "sub-D");

        // Setup is allowed while accounts are ACTIVE.
        gate.link("account-A", a, true, true, true);
        gate.link("account-B", b, true, true, true);
        gate.link("account-C", c, true, true, true);
        gate.link("account-D", d, true, true, true);
        gate.changeStatus("account-C", Status.LOCKED);
        gate.changeStatus("account-D", Status.DISABLED);

        System.out.println("Linked active account: " +
            gate.login(a, "REPORT_VIEWER"));
        System.out.println("Missing local role: " +
            gate.login(b, "REPORT_VIEWER"));
        System.out.println("Locked local account: " +
            gate.login(c, "REPORT_VIEWER"));
        System.out.println("Disabled local account: " +
            gate.login(d, "REPORT_VIEWER"));

        ExternalKey unknown = new ExternalKey(
            "https://idp.example.org", "sub-unknown");
        System.out.println("Unknown external subject: " +
            gate.login(unknown, "REPORT_VIEWER"));

        ExternalKey wrongIssuer = new ExternalKey(
            "https://other-idp.example.org", "sub-A");
        System.out.println("Same sub from wrong issuer: " +
            gate.login(wrongIssuer, "REPORT_VIEWER"));

        // Even if an email field happened to match account-A,
        // email is intentionally absent from ExternalKey.
        ExternalKey sameEmailDifferentSubject = new ExternalKey(
            "https://idp.example.org", "new-sub-same-email");
        System.out.println("Matching email never auto-links: " +
            gate.login(
                sameEmailDifferentSubject, "REPORT_VIEWER"));

        ExternalKey newIdentity = new ExternalKey(
            "https://second-idp.example.org", "new-sub-5");

        System.out.println("Link without local reauth: " +
            gate.link("account-A", newIdentity,
                false, true, true));
        System.out.println("Link without IdP proof: " +
            gate.link("account-A", newIdentity,
                true, false, true));
        System.out.println("Link without state binding: " +
            gate.link("account-A", newIdentity,
                true, true, false));

        System.out.println("Explicit verified link: " +
            gate.link("account-A", newIdentity,
                true, true, true));
        System.out.println("Duplicate link to other account: " +
            gate.link("account-B", newIdentity,
                true, true, true));
        System.out.println("New link gets only local role: " +
            gate.login(newIdentity, "REPORT_VIEWER"));

        gate.changeStatus("account-A", Status.LOCKED);
        System.out.println("Previously linked, now locked: " +
            gate.login(newIdentity, "REPORT_VIEWER"));

        gate.changeStatus("account-A", Status.ACTIVE);
        System.out.println("Unlink with local proof: " +
            gate.unlink("account-A", newIdentity, true));
        System.out.println("Unlinked identity denied: " +
            gate.login(newIdentity, "REPORT_VIEWER"));
    }
}
```

Compile and run:

```bash
javac SsoAccountLinkPolicyDemo.java
java SsoAccountLinkPolicyDemo
```

**Exact** stdout:

```text
Linked active account: ALLOW
Missing local role: DENY_MISSING_ROLE
Locked local account: DENY_LOCKED
Disabled local account: DENY_DISABLED
Unknown external subject: DENY_UNLINKED
Same sub from wrong issuer: DENY_UNLINKED
Matching email never auto-links: DENY_UNLINKED
Link without local reauth: DENY_NOT_VERIFIED
Link without IdP proof: DENY_NOT_VERIFIED
Link without state binding: DENY_NOT_VERIFIED
Explicit verified link: LINKED
Duplicate link to other account: DENY_ALREADY_LINKED
New link gets only local role: ALLOW
Previously linked, now locked: DENY_LOCKED
Unlink with local proof: true
Unlinked identity denied: DENY_UNLINKED
```

### 12.1. Why Does the Example Produce These Results?

- `account-A` is `ACTIVE` with `REPORT_VIEWER` and a valid link ⇒ `ALLOW`.
- `account-B` is linked yet has an empty roles set ⇒ `DENY_MISSING_ROLE`, no auto-added roles.
- `account-C` and `account-D` were linked while `ACTIVE`, then switched to `LOCKED`/`DISABLED` ⇒ logins denied even though links remain stored.
- `sub-unknown` does not exist ⇒ `DENY_UNLINKED`, no automatic JIT creation.
- `sub-A` from another issuer does not match A's `(issuer,subject)` key ⇒ `DENY_UNLINKED`.
- “Matching email” is a modeled case: a different external subject is still denied; the program **does not read email** to link.
- Missing local reauth, external proof, or state binding ⇒ `DENY_NOT_VERIFIED`.
- All three proofs satisfied and `ACTIVE` account ⇒ `LINKED`. Attempting to link the same identity to B ⇒ `DENY_ALREADY_LINKED`.
- The new external link to A inherits only A's **local role** via lookup, ignoring external groups.
- Once A is locked, another linked identity is also denied right at the status check.
- Unlinking with local proof deletes the mapping; logging in via that identity is no longer allowed.

### 12.2. Mandatory Limitations Before Production

This program is a policy demo, **not a real login service**. Specifically:

1. `verifiedExternalProof`, `recentLocalReauth`, and `stateBoundToSession` are test-supplied booleans. Production **never** accepts booleans from request bodies/browsers; outcomes must originate from trusted provider/session/transaction logic.
2. `HashMap` is not concurrency-safe, lacks transactions, and provides no DB uniqueness; real links require **unique indexes, transactions, and conflict recovery**.
3. No SAML XML Signature/OIDC JWT verification, token expiry, nonce, state, `InResponseTo`, CSRF, replay protection, or TLS.
4. No tenant keys/qualifiers/sector migrations; production requires issuer/tenant isolation.
5. No account-link notifications, freshness timestamps, risk-based step-up, or device assurance.
6. No active-session revocation post-lock, even though fresh logins are denied.
7. `login` checks a caller-passed role; in production `requiredRole` must come from **server-owned authorization policy**, never a client-chosen query parameter.
8. Local roles are plain strings here. Production needs authorities with tenant/resource scope, expiration, and auditing.
9. Reason enums are for internal tests; production external errors must be generic without revealing account state.
10. No account recovery/last-factor unlink policies, compliance retention, or distributed cache invalidation.

## 13. Account-Linking Test Matrix

| ID | Scenario | Required Result |
| --- | --- | --- |
| LINK-01 | OIDC `(iss, sub)` linked to A, local account `ACTIVE` | Resolves cleanly to A |
| LINK-02 | Matching `sub` yet different issuer | Do not link A; deny/onboarding |
| LINK-03 | Matching `iss` yet different `sub`, matching email | Do not auto-link A |
| LINK-04 | SAML `NameID` differs in format/qualifier, same value | Do not treat as same identity |
| LINK-05 | SAML transient `NameID` changing every login | Do not create fake persistent link |
| LINK-06 | Account A proves local reauth + verified external token + bound state | Links cleanly if unique |
| LINK-07 | Only external subject verified, no local session proof | Reject |
| LINK-08 | Only local login A, external subject unverified | Reject |
| LINK-09 | Invalid or expired `state`/nonce/correlation | Reject; write no mapping |
| LINK-10 | Link callback hits a different browser/session | Reject login CSRF/link hijack |
| LINK-11 | External subject X already linked to A, attempt link to B | Reject; preserve link A |
| LINK-12 | Two concurrent link callbacks for same X | Exactly one mapping; DB unique |
| LINK-13 | Existing local account `LOCKED` during link | Reject; never auto-unlock |
| LINK-14 | Old email reassigned to another employee | Does not hijack account A |
| LINK-15 | User legitimately changes email | Preserve stable link A; update optional profile |
| LINK-16 | IdP lacks `email_verified` | Never trust email ownership; stable subject still needs verification |
| LINK-17 | Pairwise subject changes after sector migration | Controlled account migration; no auto-merge |
| LINK-18 | Un-onboarded provider/tenant | Reject; never auto-add issuer |
| LINK-19 | Unlink missing recent local reauth | Reject |
| LINK-20 | Unlink link belonging to another account | Reject; never delete others' links |
| LINK-21 | Unlink last login method without recovery method | Per policy: reject/step-up |
| LINK-22 | Unlink succeeds, removed external identity logs in again | Deny unless re-linked via verified flow |
| LINK-23 | Two local accounts sharing display name | Never merge |
| LINK-24 | SAML assertion signed by IdP B claims NameID A | Uses only B's key; no cross-IdP linking |
| LINK-25 | Terminated user receives JIT callback | Never create bypass account by email |
| LINK-26 | JIT allowed + invited + right tenant + proof | Creates at most one account with minimal grants |
| LINK-27 | Invalid SAML signature with valid `NameID` | Reject before link lookup/mutation |
| LINK-28 | OIDC ID Token wrong `aud`/`iss` with matching email | Reject before linking |
| LINK-29 | Replay same link callback | Reject duplicate state/nonce/replay |
| LINK-30 | Audit link events | Minimal metadata only; no raw tokens/PII |

### 13.1. “Correct Link” Assertions Must Check Three Dimensions

Do not assert only `login success`. Tests must verify:

1. Table `external_identity_link` has **exactly one** entry for that external identity.
2. `local_account_id` matches the account that reauthenticated.
3. Zero duplicate or orphan rows exist.
4. Local roles **did not change** due to linking unless policy provisions them.
5. Post-link sessions hold only that local account's authorities.
6. Upon unlinking or locking, associated sessions/refresh tokens are handled per policy.

## 14. Missing Local Role Test Matrix

| ID | SSO State | Local Grants | Effect |
| --- | --- | --- | --- |
| ROLE-01 | Valid, linked, `ACTIVE` | `REPORT_VIEWER` | Protected viewer endpoint allows |
| ROLE-02 | Valid, linked, `ACTIVE` | Empty | Deny protected report; no auto-role |
| ROLE-03 | Valid, linked, `ACTIVE` | `REPORT_VIEWER` | Admin endpoint denies |
| ROLE-04 | Valid, linked, `ACTIVE` | `REPORT_ADMIN` matching tenant | Allow admin if resource policy permits |
| ROLE-05 | Valid, linked, `ACTIVE` | `REPORT_ADMIN` other tenant | Deny in current tenant |
| ROLE-06 | Valid SAML assertion with `groups=Admins` | Local role absent | Never auto-grant admin |
| ROLE-07 | Valid OIDC token with `scope=openid` | Role absent | Never treat scope as local role |
| ROLE-08 | IdP `groups` claim missing | Local policy requires group mapping | Deny/least-privilege per policy |
| ROLE-09 | Local roles service timeout | Unknown | Fail closed on protected actions |
| ROLE-10 | Local role expired | Stale cached session | Revoke/refresh; deny after TTL/event |
| ROLE-11 | User granted role post-login | Stale cache | Refresh/re-auth per approved consistency |
| ROLE-12 | Role revoked while session active | Old granted authority | Sensitive endpoint denies per revocation policy |
| ROLE-13 | `hasRole("REPORT_VIEWER")`, authority is `REPORT_VIEWER` | Prefix mismatch | Test catches mapping bug |
| ROLE-14 | `hasAuthority("REPORT_VIEW")`, authority is `ROLE_REPORT_VIEWER` | Name mismatch | Deny and fix policy; never `permitAll` |
| ROLE-15 | Authenticated user lacking role calls REST API | Active yet unauthorized | Typically 403, not 500/200 |
| ROLE-16 | Anonymous calls protected route | No auth | Challenge/redirect; never treat as authenticated |
| ROLE-17 | Same user across multiple providers | One approved local account link | Roles from local ID; never combine provider roles blindly |
| ROLE-18 | Unknown/unfamiliar role claim | Local mapper unknown value | Ignore/reject; never elevate |
| ROLE-19 | Role differs only in case (`admin` vs `ADMIN`) | Case mismatch | Never auto-normalize to privileged role |
| ROLE-20 | Role list from client query | Untrusted | Never use as authority |

**PASS criteria:** zero data leakage, zero privilege escalation, clearly documented login policy. A passing MockMvc test faking `ROLE_ADMIN` **does not** prove real IdP claims map properly; include at least one integration test backed by real local grants.

## 15. Locked / Disabled Account Test Matrix

| ID | IdP Authentication | Local Status | Outcome |
| --- | --- | --- | --- |
| STATUS-01 | Valid SAML/OIDC | `ACTIVE` | Evaluate roles normally |
| STATUS-02 | Valid | `LOCKED` | Reject new login and protected access |
| STATUS-03 | Valid | `DISABLED` | Reject |
| STATUS-04 | Valid | `SUSPENDED` | Reject/restrict per policy |
| STATUS-05 | Valid | `CLOSED/DELETED` | Reject; no silent JIT recreation |
| STATUS-06 | Valid | `ACTIVE` yet account expired | Reject per local lifecycle |
| STATUS-07 | Valid with MFA | `LOCKED` | Still reject; MFA never overrides lock |
| STATUS-08 | Valid, local role `ADMIN` | `LOCKED` | Reject; role never overrides lock |
| STATUS-09 | IdP disabled, existing RP session valid | RP `ACTIVE` | Deprovision event/session revocation test |
| STATUS-10 | Locked locally after login | Old `HttpSession` | Revoke or backend status gate denies |
| STATUS-11 | Locked locally on Pod A | Session used on Pod B | Distributed revocation works |
| STATUS-12 | Unlocked locally by authorized admin | Valid link, role | New login permitted after policy checks |
| STATUS-13 | SSO callback during admin lock | Race | Atomic status decision; no newly active session |
| STATUS-14 | Stale cached local account shows `ACTIVE` | DB shows `LOCKED` | Cache invalidation/TTL test |
| STATUS-15 | Lock event arrives after local authz cache populated | Stale grants | Deny within approved revocation SLA |
| STATUS-16 | Browser keeps IdP cookies after lock | Fresh IdP SSO succeeds | RP still rejects |
| STATUS-17 | Multiple external identities linked to locked local A | All identities | All must be denied |
| STATUS-18 | JIT attempts creating new local B after A locked with same email | Valid IdP token | No bypass/silent new account |
| STATUS-19 | Failure response reveals “account locked for an@example.org” | Any | Security QA fail (enumeration) |
| STATUS-20 | Audit record stores full `SAMLResponse`/ID Token | Any | Security QA fail |
| STATUS-21 | User switches tenant in session | Scoped status policy | Validate local account + tenant grants |
| STATUS-22 | Lock + return to earlier browser tab | Existing cookie | Zero access to protected resources |
| STATUS-23 | Lock during ongoing background export | Work authorization | Cancel/limit per high-risk policy |
| STATUS-24 | Local DB fails to resolve account state | Unknown | Fail closed; never assume `ACTIVE` |

### 15.1. “Account Locked” Has Multiple Sources

- **IdP/Directory lock:** user cannot authenticate freshly at the IdP, yet existing RP sessions may need revocation.
- **Local RP lock:** SSO token remains valid, yet RP rejects the linked account.
- **Tenant-level suspension:** user can be active in tenant A while suspended in tenant B.
- **Risk/abuse flag:** not necessarily stored in `UserDetails.isAccountNonLocked`; the policy gate must read the right source.
- **Legal/HR termination:** account deprovisioning / SCIM `active=false` and separate token/session invalidation.

Each source needs **precedence rules**. Normally, if any authoritative deny flag is active for that RP/resource, access must be denied even if another source reports `ACTIVE`.

## 16. Testing OIDC and SAML2 End-to-End Along the Real Path

### 16.1. OIDC Full Callback Checklist

1. Use a **test OIDC Provider** with discovery/JWKS, issuer, client registration, and trusted signing keys.
2. Browser initiates login; RP generates `state`, `nonce`/PKCE per flow.
3. IdP returns authorization code; Spring Security exchanges tokens and validates the ID Token.
4. Test principal carries fixed `(iss,sub)`; local repository holds account/link/grants/status.
5. Test active linked user: callback creates authenticated session with proper authorities.
6. Test linked account missing role: protected routes deny or strict login fails per policy.
7. Test linked locked account: callback rejects with no authenticated session.
8. Test same email from another subject/issuer: cannot log into the existing local account.
9. Test explicit linking flow: user has active local session + recent reauth and verified external proof.
10. Test replayed state, reused code, cross-session state, and wrong nonce/issuer/aud.
11. Test locking account **after** successful login and session revocation.
12. Audit logs never contain raw tokens, codes, userinfo, or link proofs.

### 16.2. SAML2 Full ACS Checklist

1. Test IdP issues a **signed SAML Response/Assertion** with a registered key.
2. `RelyingPartyRegistration` holds trusted IdP verification credentials, expected issuer/`entityID`, ACS, and SP `entityID`.
3. Valid `Conditions`, bearer `SubjectConfirmationData`, `Recipient`, `InResponseTo`, `AudienceRestriction`, unique IDs.
4. Test stable persistent `NameID`/qualifiers mapping to the right local account.
5. Identical `NameID` string from another IdP must never map to the wrong local account.
6. With local locked/disabled, a verified assertion still fails application login.
7. With no local role, protected routes deny or strict login rejects.
8. Expired/replayed/wrong-audience assertions are rejected **before** local link mutations.
9. XML Signature Wrapping cannot trick the app into reading an unverified `NameID`.
10. Re-sign every negative fixture **validly after modifying claims** when testing link/status; editing signed XML without re-signing tests only signature rejection.
11. Revoke sessions when locking after login; test across pods.
12. Never write raw Assertion XML/`NameID`/PII to logs.

### 16.3. Watch Out for Inter-Test Dependencies

If an identity was linked in an earlier case, a subsequent “unlinked” test may pass/fail falsely unless the DB fixture resets. Each test needs transaction rollback, isolated test schemas, or fresh identifiers:

```text
test-001 -> issuer A, sub unique-test-001
test-002 -> issuer A, sub unique-test-002
test-003 -> issuer B, sub unique-test-003
```

Never use production emails or person IDs. Clean up test external links and active sessions after every test. This matters especially for JIT/concurrency tests where auxiliary rows may commit outside the test transaction.

### 16.4. Do Not Hand-Craft `RequestPostProcessor` for SAML from Raw XML

Spring Security Test supports various `SecurityContext` mocks, yet **not every `oidcLogin` API has an exact SAML counterpart in every release**. To test full SAML ACS, stand up a trusted test IdP and send signed fixtures through the real SAML2 filter. Controller unit tests may use a test-harness verified principal, clearly noting **XML Signature is not tested**.

## 17. Testing Session Protection and Active Account Locks

### 17.1. Two Independent Phases

**Phase A — login-time:** RP rejects callbacks when the account is `LOCKED`. **Phase B — after-login:** user already holds an app session, then the account is locked; RP must block continued sensitive access per revocation SLA.

Example scenario:

```text
09:00:00  OIDC login of account-A succeeds.
09:00:10  Browser can GET /reports/summary.
09:01:00  Admin locks account-A in local DB.
09:01:01  RP publishes user-session revocation.
09:01:02  Browser reuses old JSESSIONID cookie.
EXPECTED: no confidential report data.
```

Do not merely assert no new session cookie is minted; actively send a request to a protected route **using the old cookie**. With Spring Session Redis, verify session deletion/event propagation across nodes. If self-contained JWTs remain valid, the app needs introspection/status checks or bounded expiry—clearing an in-node `HttpSession` alone is insufficient.

### 17.2. Role Revoked After SSO

Similarly: user role `REPORT_VIEWER` is revoked at 09:01 while the session retains `ROLE_REPORT_VIEWER`. If the app requires near-real-time revocation, re-check local roles per request or invalidate the session. Post-revocation tests must confirm zero leakage. Never substitute “opening a new login page fails” for “old session was revoked.”

### 17.3. Cache Consistency

Services may cache local statuses/entitlements. Define a **max stale window**: 0s for ultra-sensitive operations or a bounded TTL fitting business needs. Test:

- Warm `ACTIVE` cache while DB changes to `LOCKED`.
- Revocation event received promptly vs. dropped event.
- TTL expiry still enforces denial.
- Multi-region cache invalidation.
- Behavior when cache backend is down: never assume `ACTIVE`.
- Stale session behavior after load-balancer stickiness shifts.

## 18. Security Boundaries of Account Linking

### 18.1. Account Takeover via Email Collision

Threat model:

```text
Victim has local account:
  localId = user-17
  email = a@example.org
  role = REPORT_ADMIN

Attacker authenticates at another permitted IdP:
  iss = https://other-op.example.org
  sub = attacker-unique
  email = a@example.org

Vulnerable RP:
  find local account by email -> user-17
  auto-link -> attacker becomes REPORT_ADMIN

Hardened RP:
  no existing (iss,sub) link
  email only a profile hint
  explicit link requires victim's local reauth
  otherwise deny/onboarding -> NO takeover
```

This is why linking requires stable issuer/subject and **never** auto-merging by email, even when email looks “verified.”

### 18.2. Login CSRF and Forced Account Linking

An attacker can initiate OAuth/OIDC login with their own account and trick a victim into submitting the callback/authorization response inside the victim's session. If the RP fails to bind `state`/nonce/callback to the session/pending link transaction, the attacker's external identity attaches to the victim's local account. The attacker then signs into the victim's account using their own identity.

Controls: server-side `state` bound to session, nonce where required, CSRF protection, reauth, single-use linking transactions, expiration, and server-side fixed link target local account. Test cross-browser/cross-session callbacks, replayed states, and races.

### 18.3. SAML IdP-Initiated Login

IdP-initiated SSO can lack `InResponseTo` per profile. Never assume missing request correlation suffices as proof for **linking onto an existing local account**; linking is sensitive and should normally use SP-initiated flows with pending context. If business requires IdP-initiated login, apply strict hardening: trusted issuer, audience, recipient, replay, controlled onboarding, and explicit account linking.

### 18.4. Local Password Recovery After SSO Linking

An account may hold multiple methods: local password, passkey, SAML, OIDC. Never bypass a lock because the user switches login methods. Locks/suspensions on the **local account ID** must block every linked method. Test locking a user via OIDC A and attempting login via SAML B: still denied. Recovery/unlocking must follow an audited authorized workflow, never a simple new link.

## 19. Race Conditions and Transaction Tests

### 19.1. Unique Link Concurrency

Suppose two actors concurrently attempt to link the same external identity X to A and B:

```text
T1: see X absent
T2: see X absent
T1: insert X -> A, commit
T2: insert X -> B, attempt commit
EXPECTED: DB unique constraint rejects T2.
         A remains linked; B receives generic failure.
```

Run DB integration tests against real SQL storage with concurrent transactions and uniqueness assertions. Never rely only on the Java `HashMap` demo; `HashMap` is not thread-safe and does not replace a DB unique constraint.

### 19.2. Link vs. Lock Race

```text
T1: begin link A<-X
T2: admin locks A
T1: commit link and issue authenticated session?
```

A strong policy checks **account status at commit/session-creation time** using locking/optimistic versioning/transactions. If A is already locked when the callback finishes, issue no session. If the lock occurs right after login, revoke the active session. Test both orderings; checking only “T1 saw ACTIVE at the start” is insufficient.

### 19.3. IdP Subject Reassignment and Account Merging

Some legacy IdPs use mutable usernames/emails that can be reassigned. Every RP should contractually confirm identifiers are stable/non-reassignable within the issuer, or use IdP-guaranteed opaque internal UUIDs. During IdP migrations, never reuse matching subject strings as proof of the same person if the trust contract changed.

### 19.4. Partial Transaction Failures

Test:

- Local account created yet link insert fails ⇒ roll back account creation or clean up deterministically.
- Link insert succeeds yet audit notification fails ⇒ do not roll back identity security if auditing has separate durability; ensure event recovery.
- Link insert succeeds yet session creation fails ⇒ retries must not create duplicate links.
- Unlink succeeds yet old refresh token still works ⇒ invalidate/revoke per policy.
- Partial role-map update leaves privileged role lingering ⇒ transactional update or deny until sync recovers.

## 20. Observability, Error Codes, and Avoiding PII Leaks

A safe log entry might look like:

```json
{
  "event": "federated_login_denied",
  "protocol": "oidc",
  "provider_registration": "corporate",
  "reason_code": "LOCAL_ACCOUNT_LOCKED",
  "local_account_ref": "pseudonymous-event-ref",
  "policy_version": "local-gate-v3",
  "correlation_id": "opaque-request-id",
  "result": "rejected"
}
```

Never put raw `id_token`, `access_token`, `SAMLResponse`, `NameID`, real emails, passwords, session IDs, or full group lists into app logs/metrics. Restrict access and retention on internal event reasons. External user-facing messages must be generic to avoid enumeration:

```text
Unable to complete login or access.
Please contact support through the published channel.
Request ID: <opaque-correlation-id>
```

Never tell anonymous users “this email belongs to a locked admin” or “account exists but is not linked.” For authenticated users inside reauth flows, UI feedback can align with policy without exposing account ownership to attackers.

### 20.1. Useful Metrics

- `federation_login_denied_total` by **`reason_code`/registration**, never by email/`NameID`.
- `account_link_conflict_total` by provider/tenant; alert on spikes.
- `local_status_denied_total` by service/region.
- `local_role_missing_total` by resource group, never by user.
- `session_revocation_lag_ms`/cache staleness percentiles.
- `unexpected_jit_creation_total` or reconciliation counts.

### 20.2. Alerts and Response

A spike in `LINKING_ALREADY_BOUND` may signal a legitimate migration or attempted takeover; never auto-merge. A spike in `LOCKED` after an SSO provider rollout may indicate stale status or duplicate provisioning. Distinguish protocol auth errors before the local gate from authorization errors after subject verification; never loosen trust or role policies to “turn dashboards green.”

## 21. Runbook When IdP SSO Succeeds Yet the App Denies Access

1. Determine **whether federation validation passed or failed**: invalid signature/issuer/audience/nonce is one group; linked local status/roles is another.
2. Collect approved registration/issuer, **pseudonymous** subject reference, and local account link key. Never paste real JWTs/Assertions into chat or logs.
3. Verify whether the user has an **existing link** for the exact issuer+subject rather than merely a matching email.
4. Check target local account status in the authoritative store: `ACTIVE`/`LOCKED`/`DISABLED`, reason, and audit approval.
5. Check the protected route's required role, actual granted authorities, and tenant/resource scope.
6. If the role is absent, have the owner provision access through workflow; **never self-grant `ROLE_ADMIN`** or bypass routes.
7. If the account is locked, verify the security/HR cause; **never unlock via a login callback**.
8. On link conflicts, never merge by email; use secure link/recovery flows requiring both local and IdP proof.
9. If occurring on only one node, check session caches/status drift and version mismatches.
10. If the user held a session before lock/revocation, verify whether the old session still works and revoke per policy.
11. Audit safe logs, audit events, retry/transaction races, JIT duplicates, and deprovisioning.
12. After remediation, re-run positive/negative tests and monitor spikes; do not stop at verifying the user can log in.

## 22. Pre-Release Review Checklist

- [ ] IdP/OP registrations are governed, with trusted issuers/`entityID`s and exact tenants.
- [ ] OIDC `(iss, sub)` or SAML stable `NameID` + issuer/qualifiers serve as the external link key.
- [ ] No auto-linking by email, username, display name, or group.
- [ ] Account linking enforces local session proof, recent reauth, verified external proof, and state/CSRF binding.
- [ ] Linking succeeds only when target local account is `ACTIVE`; never link to locked/disabled accounts.
- [ ] External identity uniqueness is enforced **in the database** and tested under concurrency.
- [ ] JIT provisioning runs only when allowed by policy/invitation, is idempotent, and never bypasses locked old accounts.
- [ ] Unlinking/relinking enforces ownership/reauth controls, last-login-factor safety, and revocation.
- [ ] Local status gate sits on the real SAML/OIDC login path prior to final `Authentication`/session creation.
- [ ] Never assume `UserDetailsService` runs automatically for SAML/OIDC.
- [ ] Missing local roles are never auto-granted; protected routes return 403 or strict login rejects.
- [ ] Role mapping uses solely trusted claims/local policies with tenant/resource scope.
- [ ] Active-session revocation after `LOCKED`/role revocation is tested across multiple nodes.
- [ ] MockMvc `oidcLogin()` is used only for route/mapping tests; full callbacks have dedicated integration tests.
- [ ] SAML fixtures are validly re-signed after altering `NameID`/attributes for link tests.
- [ ] Cross-issuer same `sub`, cross-`sub` same email, and transient SAML `NameID` all have negative tests.
- [ ] Cross-session state/nonce, expired link intents, and replayed callbacks are rejected.
- [ ] Zero raw tokens, Assertions, `NameID`s, emails, or PII in errors/logs/metrics.
- [ ] User-facing errors never reveal account existence or locked status.
- [ ] Lock/unlock/role changes are audited and never triggered automatically by SSO callbacks.
- [ ] Session fixation, CSRF, login flow isolation, deprovisioning, and recovery policies are tested.
- [ ] Code uses version-appropriate Spring Security APIs without disabling token/signature validators.
- [ ] Positive controls prove linked `ACTIVE` + role grants genuine access.
- [ ] Negative controls prove missing links, missing roles, and locked/disabled accounts all fail closed.

## 23. Review Questions

**1. Why isn't a signed ID Token enough to access a local account?**  
Because the token only authenticates an external subject; the RP must still map the right local ID and check local status/roles and resource policy.

**2. Should you auto-link when an email claim matches an email in the DB?**  
No. Emails can change, be reused, or alias, and do not prove ownership of the local account. Use verified issuer+subject and explicit secure linking.

**3. Does an identical `sub` from two OIDC issuers mean the same person?**  
No. Link keys must include the trusted issuer, plus tenant/sector when required by architecture.

**4. Does a transient SAML `NameID` make a good persistent account key?**  
No if the IdP rotates values per login. You need a stable identity contract or verified account-linking flow.

**5. Does a user holding only `SCOPE_openid` automatically become `REPORT_VIEWER`?**  
No. An OIDC scope is not a local application role.

**6. Must a missing role always fail login?**  
Depends on policy: strict apps may fail login; onboarding-enabled apps may keep a minimal session while denying protected resources.

**7. If `UserDetailsService` is defined, does SAML2/OIDC login automatically check `isAccountNonLocked`?**  
No. Password-based `DaoAuthenticationProvider` uses `UserDetails`; federated flows must integrate a local status gate explicitly.

**8. Why can an account be locked at the RP while the IdP still issues tokens?**  
Because the IdP and RP manage state separately. The RP must reject or revoke sessions per its own policy.

**9. When a user is locked after login, is blocking the next callback enough?**  
No. Existing authenticated sessions/tokens may still hold access; enforce revocation/status gates and test old cookies.

**10. Why doesn't MockMvc `oidcLogin()` prove SSO callbacks are secure?**  
It injects a mock principal/authorities without executing real authorization-code exchange, token signatures, or link services.

**11. How do you test a SAML `NameID` mismatch without hitting signature errors?**  
Re-sign a fresh fixture using the test IdP key after setting `NameID`, keeping other protocol fields valid.

**12. Why must external link uniqueness live in the database?**  
Two concurrent requests can pass an `exists()` check simultaneously. DB constraints/transactions prevent linking X to two accounts.

**13. Can local `ADMIN` be granted immediately when a SAML Attribute says “admin”?**  
Not automatically. Only when the RP has an allowlisted mapping, trusted issuer/tenant/entitlement contract, and authorization policy.

**14. Should a local account unlock happen upon a successful SSO login?**  
No. Unlocking must follow an approved workflow, not merely a valid IdP token.

**15. What happens if a user unlinks an external identity and logs in with it again?**  
They must be denied access to the old local account unless re-linked via an approved linking flow.

**16. Account A is locked and the user tries IdP B already linked to A—what happens?**  
Still rejected. Locks apply to the local account regardless of login method.

**17. What if the local roles service is unreachable?**  
Never fail open as admin. Depending on risk policy, deny protected operations or use an approved bounded cache with revocation safeguards.

**18. What is the risk of returning “Account a@example.org locked”?**  
It exposes account existence/status, aiding enumeration. Return generic messages externally and keep detailed reason codes in internal audits.

**19. Should JIT always create an account when a subject is unlinked?**  
No. JIT applies only per approved issuer/tenant/invite/entitlement policy; unlinked subjects may need to be rejected.

**20. What proves a user holding local roles cannot bypass a lock?**  
A negative integration test where a linked `LOCKED` account holding `REPORT_ADMIN` is still rejected on both new logins and protected requests.

## 24. Official Documentation and References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer, subject, pairwise identifiers, ID Token validation, nonce/state semantics.
- [NIST SP 800-63C-4 — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): secure account linking, RP/IdP trust agreements, and federation security.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic failures, account enumeration, secure federated linking, and reauthentication.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth state/PKCE, login CSRF, and token handling.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, invalidation, logout, and revocation.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService` delegation, authority mapping, and userInfo endpoint configuration.
- [Spring Security — Testing OAuth2/OIDC Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oidcLogin()`, `oauth2Login()`, and test authorities/claims.
- [Spring Security — SAML2 Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2AuthenticatedPrincipal`, validated assertions, and provider customization.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): trusted `RelyingPartyRegistration`, SAML Response/Assertion checks, and ACS flow.
- [Spring Security — `UserDetailsService`](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): role of `UserDetailsService` in `DaoAuthenticationProvider`.
- [Spring Security — `UserDetails` API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UserDetails.html): `isEnabled`, `isAccountNonLocked`, `isAccountNonExpired`, and authorities.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContext`, `Authentication`, authorities, session establishment.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `Subject`/`NameID`, Assertion signature/trust, and SAML identity semantics.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): secure SAML response validation, trust, and replay protection.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoiding sensitive authentication data in logs.

**Takeaway:** SAML/OIDC SSO verifies an **external subject**; it does not prove that external subject owns a **local account** merely because emails match. Secure linking requires immutable issuer+subject/`NameID`-context keys, local reauthentication, verified external proof, state/CSRF binding, and DB uniqueness. Reporting/admin permissions are **local authorization**, and missing roles must never be auto-granted. `LOCKED`/`DISABLED` accounts must be denied even with valid SSO tokens, and when locking happens **after login**, existing sessions/tokens must be handled. To verify thoroughly, combine unit policy tests, DB concurrency, MockMvc route tests, **and** full SAML/OIDC callbacks against real local state—never let mocked `oidcLogin()` fool you into thinking all of federation has been tested.