# Safe Account Linking and Not Trusting Unverified Emails

> **Context:** Spring Security Servlet, logging in with OAuth2/OpenID Connect (OIDC), and linking an Identity Provider (IdP) account to an existing application account. The focus is on preventing **account takeover** and protecting the provenance of identity.

## Learning Objectives

After this lesson, you will be able to distinguish **IdP login**, **external identity linking**, and **granting permissions to an internal account**; identify the OIDC `(iss, sub)` key pair; accurately explain the limits of `email_verified`; design a linking flow that proves ownership of **both accounts**; and properly implement Spring Security, database, session, state, and callback controls.

**Foundational rule:** Sharing an email **does not mean** two accounts share an owner. Never automatically link an unlinked IdP identity to a local user merely because emails match, especially when the email is unverified. Even with a verified email, merging into an existing account still requires an explicit policy and ownership proof.

## 1. Problem: One User, Multiple Login Methods

Your application has a local account:

```text
local_users
  id         = 42
  username   = mai
  email      = mai@example.org
  status     = ACTIVE
  role       = MEMBER
```

The user clicks “Sign in with IdP”. After completing OpenID Connect, the IdP returns an ID Token (an illustrative example of identity claims):

```json
{
  "iss": "https://idp.example.org",
  "sub": "user-abc-123",
  "aud": "my-application-client-id",
  "email": "mai@example.org",
  "email_verified": false
}
```

If the backend takes `email` from the token to run `SELECT * FROM local_users WHERE email=?` and treats user #42 as the person who just signed in, an attacker only needs to create an IdP identity claiming the victim's email. This is **vulnerable account linking**, which can lead to data theft and internal privilege takeover.

**Wrong flow:**

```text
OIDC authentication succeeds for (iss=idp, sub=attacker-01)
   → email = mai@example.org (unverified)
   → looks up local account by email
   → binds session to local user #42        ❌
```

**Right flow:**

```text
OIDC authentication succeeds
   → checks (iss, sub) from verified identity
   → looks up external_account_links(issuer, subject)
        ├─ Already linked to user #42 → loads local user #42, applies account/role policies
        └─ Not yet linked → no local account has been proven;
                            require user to sign into local account to link,
                            or go through a separate NEW registration flow
```

When **linking an additional IdP** to account #42, the user must prove they control local account #42, actively request linking, and then complete authentication with the exact IdP account to be linked. Only after both proofs should the link record be written.

## 2. OAuth2, OIDC, ID Token, and Identity Claims

**OAuth 2.0** focuses on authorization: an application obtains an access token per grant to call resources at another service. An **access token is not automatically an ID Token**, and its unverified payload must not be used as proof of who just signed in. **OpenID Connect** adds user authentication rules and **ID Tokens**.

| Claim / Data | Meaning | Should It Key a Local Account? |
|---|---|---|
| `iss` | Issuer URL of the IdP that issued the ID Token | **Yes, together with `sub`**, once the token is verified |
| `sub` | Subject ID, unique within the issuer and the client's OIDC subject policy | **Yes, together with `iss`** |
| `email` | User's email supplied by the IdP; can change, collide, or be reassigned | **No** |
| `email_verified` | IdP states it performed an email confirmation step at verification time | **No**, metadata about email only |
| `preferred_username`, `name`, `picture` | Display information | **No** |
| `aud` | Client/audience of the ID Token | Must be verified during **token validation**, not a user key |
| OAuth access token | Permission granted to client to call resources | Does not replace OIDC login |
| Spring `registrationId` | OAuth Client config name inside the app (e.g., `corp`) | Does not replace the `iss + sub` pair |

Per **OpenID Connect Core `5.7`**, the pair `iss` and `sub` is the unique/stable identifier a relying party can depend on; `email` may change or be reused. `sub` is a case-sensitive string and may be a **pairwise subject** depending on IdP, client, or sector identifier policy. Migrating clients/providers requires a reconciliation process; never attach a new identity to an existing user just because emails match.

### 2.1. Understanding `email_verified` Properly

- **`true`:** the IdP asserts it verified the end-user controlled the email at the time of verification. This is **not** a permanent guarantee that the email has not changed hands, nor does it prove the person owns a local account with a matching email.
- **`false`:** no email confirmation. Never use this email to log into an existing local account, link accounts, elevate permissions, or mark the app's email as verified.
- **Claim missing:** treat email status as **unverified per that claim**. Never infer `true` because the email belongs to a corporate domain, users share a name, or the IdP is well known.
- **Claim returned in UserInfo:** if reading `email` and `email_verified` from UserInfo, you must ensure `sub` from UserInfo **matches exactly** the ID Token's `sub` and verify the source/provider; never pair one person's verified flag with another person's email.

Important: **Never use `email_verified=true` as the sole basis to merge two accounts that already have data or permissions.** Email is not an immutable OIDC key. Verified emails may be used for profile display, contact, or a dedicated verification flow if IdP/app policy allows.

### 2.2. When `email_verified=false` Yet the User Actively Links

If the owner of local user #42 is already signed in, recently re-authenticated, and completes an OIDC login with an external identity having a valid `(iss,sub)`, the app **may** allow attaching that external identity to #42 under its IdP trust policy, even if the IdP email differs or is unverified. Safe linking comes from **proof of local account control + proof of external account control + linking intent**, not from the IdP email. Even then, the IdP email must **still not be marked verified** or used as a recovery email without independent verification.

### 2.3. OAuth2-Only Providers Without OIDC Support

For OAuth2 providers that do not issue standard ID Tokens, the app must follow provider documentation: use the access token for the right API/audience, obtain a stable provider user ID, and define explicit provider/tenant namespaces. Provider-specific `email` and `verified` fields **do not automatically** carry OIDC semantics. Never assume an OAuth access token is application-level login proof. This lesson prioritizes OIDC because `iss + sub` carries standardized authentication semantics.

## 3. Five Common Account Takeover Scenarios

### 3.1. Email Spoofing at the IdP

An attacker creates an IdP user, sets email `victim@example.org` with `email_verified=false`. The backend looks up the local user by email and grants the attacker access.

**Prevention:** look up local logins exclusively via the formal link table by `(iss,sub)`. Unlinked IdP accounts must follow a separate flow.

### 3.2. Email Verified Yet Reassigned or Transferred

An email once belonged to person A and later transferred to B; the IdP may have verified it at a point in time. Sharing an email does not prove B owns A's internal account. Nor does the OIDC spec guarantee `email` is unique and immutable.

**Prevention:** never auto-merge existing local accounts by email even with `email_verified=true`; require local login/reauth and explicit linking.

### 3.3. Link CSRF, Session Swap, Signing Into the Wrong IdP Account

If the app does not bind the OAuth callback to an explicit action by the local user, an attacker can trick the victim into confirming a callback for the **attacker's IdP account**. Afterward, the attacker signs in with their own IdP and gains access to the victim's local account.

**Prevention:** OAuth `state`, OIDC `nonce`, PKCE per profile, CSRF protection, a server-side single-use **link intent** bound to session/local account/provider, re-authentication, and a confirmation screen. Valid `state` is necessary yet insufficient if logic fails to check **who initiated the link**.

### 3.4. Two Accounts Concurrently Linking One External Subject

Two local accounts both attempt to attach the same `(iss,sub)`. If the app runs “SELECT missing → INSERT” without a unique constraint, concurrent requests can both succeed or leave conflicting records.

**Prevention:** database unique constraint, transactions, idempotency, and conflict policy: if the external account already belongs to another local user, **reject** rather than silently transferring ownership.

### 3.5. Accepting Invalid ID Tokens or Cross-Tenant IdPs

An attacker crafts a JWT with arbitrary `sub` and `email` and sends it to the backend. Successfully Base64-decoding the payload does not mean a trusted IdP signed the token for this application.

**Prevention:** validate signature, algorithm, `iss` against the ClientRegistration allowlist, `aud` matching the client, `exp` lifetime, `nonce/state` flow, and UserInfo consistency. Identities/tenants outside the allowed scope must be rejected.

## 4. Designing a Safe Link Table

Keep an **immutable local ID** independent of external identities. PostgreSQL example, assuming `local_users(id BIGINT PRIMARY KEY, ...)` already exists:

```sql
CREATE TABLE external_account_links (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id BIGINT NOT NULL REFERENCES local_users(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    linked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT external_link_key_unique UNIQUE (issuer, subject),
    CONSTRAINT external_link_key_not_empty CHECK (issuer <> '' AND subject <> '')
);

CREATE INDEX external_links_by_local_user
    ON external_account_links(local_user_id);
```

**Data invariants:**

1. One `(issuer,subject)` has at most **one** local owner, even under concurrent requests.
2. Changing a local or IdP email never changes the link key.
3. Never use `email`, `name`, `preferred_username`, or `registrationId` as a unique key in place of `iss+sub`.
4. Once an external account belongs to user #99, user #42 cannot silently “steal” it with `UPDATE local_user_id=42`. Any ownership transfer requires a separate verified workflow.
5. If the product allows a local user to have multiple external accounts, this table supports it; if only one account per provider is permitted, add an approved unique business rule.
6. If the provider is multi-tenant or issues per-client subjects, store the required tenant/identifier and verify during migrations. Never assume two configurations sharing a username or email are the same user.

Verified OIDC login queries:

```sql
SELECT local_user_id
FROM external_account_links
WHERE issuer = :validated_iss
  AND subject = :validated_sub;
```

Linking after verifying both sides:

```sql
INSERT INTO external_account_links(local_user_id, issuer, subject)
VALUES (:authenticated_local_user_id, :validated_iss, :validated_sub);
```

Wrap this in a transaction alongside consuming the link intent and handling `UNIQUE` conflicts. On insert conflict, load the current owner: same owner may return `ALREADY_LINKED`; different owner returns `CONFLICT`. Resolve races in the database rather than relying solely on `synchronized` within a single JVM.

## 5. Login Flow: Accept Only Pre-Linked Local Owners

```text
Browser
   → Spring Security OAuth2 Login, Authorization Code Flow
   → IdP authenticates external account
   → callback /login/oauth2/code/{registrationId}
   → Spring validates tokens and OIDC ID Token
   → identity = (iss, sub)
   → SELECT owner FROM external_account_links WHERE issuer=? AND subject=?
       ├── owner exists and is active
       │     → establish local Authentication for owner
       │     → permissions / roles loaded from application policy
       └── not yet linked
             → DO NOT look up local_users by email and auto-merge
             → require local login to link or go through NEW user onboarding
```

**Having proven an IdP account** does not mean any local account has been proven. When a login is unlinked, the backend must not assign permissions based on matching username/email. If the product auto-provisions **new** users, that must be a separate workflow ensuring no existing user is taken over while honoring approved invitations, domains/tenants, and policies.

If linked yet the local account is locked, deleted, or has permissions revoked, the app must still enforce that status. A valid IdP token must never re-enable a disabled local user.

## 6. Link Flow: Proving Both Accounts, Binding a Single-Use Intent

1. **Local user is already logged into** the exact account to link; the server reads the local user ID from the verified principal/session, never from a form `userId`.
2. **Recent re-authentication** (step-up) via password/passkey/MFA appropriate to sensitivity. Never accept `reauth=true` from a request parameter as proof.
3. Server creates a **link intent** containing local user ID, session binding, allowed provider/registration, random flow ID, short expiration, and unused flag. Enforce CSRF protection on the initiation endpoint.
4. Start the **OAuth2 Authorization Code Flow** for the exact provider, using `state`, registered redirect URI, OIDC nonce, and PKCE as applicable. Never accept arbitrary issuer/authorization endpoints from the client.
5. IdP authenticates the user of the **external account** and sends the callback; Spring Security validates the protocol, ID Token, and provider match.
6. The app recovers the exact intent by correlating OAuth request/`state` and the bound session; confirms it is unused, unexpired, the local owner is still active, and step-up is still fresh. Never use IdP email, query parameters, or client-supplied IDs to choose the owner.
7. Display details of the IdP account to be linked and require the user to confirm **that exact account**; protect confirmation against CSRF/replay.
8. Transaction: consume the intent once, verify `(iss,sub)` has no owner, and insert into `external_account_links`. If it already belongs to another local user, reject; rely on the unique constraint against races.
9. Preserve/restore the **exact local principal** after callback. Write audit logs and show the added link; do not leave a raw IdP principal holding full internal permissions.

Implementation note: default `oauth2Login` may place an `OAuth2AuthenticationToken` into `SecurityContext` after callback. In a **linking flow**, the app needs a layer managing local session/owner and `SecurityContext` persistence rules; never assume the IdP callback automatically preserves the prior local user. With multiple IdPs, prevent login/link mix-up and confirm the expected issuer for the pending session.

### 6.1. Case-by-Case Decisions

| Case | Expected Result |
|---|---|
| Valid OIDC ID Token, `(iss,sub)` linked to active user #42 | Log in user #42 with internal permissions |
| New external identity shares email with #42, `email_verified=false` | **Do not** auto-link/log in #42 |
| New external identity shares email with #42, `email_verified=true` | **Do not** auto-link/log in #42 solely from email |
| User #42 proved local session, reauth, IdP auth, and confirmed intent | May link that external identity per policy |
| External identity already belongs to user #99 | Reject linking to #42; do not transfer owner |
| Callback with wrong state/session or already-used intent | Reject, do not write to link table |
| ID Token with invalid signature, issuer, audience, or expired | Reject before processing user data |
| UserInfo `sub` does not match ID Token `sub` | Discard UserInfo, reject authentication |
| Missing email or missing `email_verified` | Treat email as unverified; still identifiable via `iss+sub` if token is valid |

## 7. Java 17: Standalone Runnable Safe-Policy Simulation

The example below is a **policy model** demonstrating why lookup must not use email. It assumes the ID Token has already been validated and both step-up/confirm flags are **server-verified**, not client-supplied. It does not perform OIDC, session management, DB transactions, or CSRF protection.

Save `AccountLinkingPolicyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class AccountLinkingPolicyDemo {

    record ExternalKey(String issuer, String subject) {}

    record ExternalIdentity(
        ExternalKey key,
        String email,
        Boolean emailVerified
    ) {}

    static class LinkStore {
        private final Map<ExternalKey, Long> owners = new HashMap<>();

        // Email MUST NOT be used to look up local accounts.
        synchronized String login(ExternalIdentity identity) {
            Long ownerId = owners.get(identity.key());
            return ownerId == null
                ? "REQUIRE_LOCAL_SIGN_IN"
                : "LOCAL_USER_" + ownerId;
        }

        // In a real application, both booleans must be verified by the server.
        synchronized String link(
            long localUserId,
            boolean freshReauthentication,
            boolean confirmedIntent,
            ExternalIdentity identity
        ) {
            if (!freshReauthentication || !confirmedIntent) {
                return "REJECT_PROOF_REQUIRED";
            }
            Long oldOwner = owners.putIfAbsent(
                identity.key(), localUserId);
            if (oldOwner == null) {
                return "LINKED";
            }
            return oldOwner == localUserId
                ? "ALREADY_LINKED"
                : "CONFLICT_OTHER_OWNER";
        }
    }

    public static void main(String[] args) {
        LinkStore store = new LinkStore();

        var unverified = new ExternalIdentity(
            new ExternalKey("https://idp.example.org", "sub-A"),
            "mai@example.org", false);
        var verifiedSameEmail = new ExternalIdentity(
            new ExternalKey("https://idp.example.org", "sub-B"),
            "mai@example.org", true);

        System.out.println("Unverified: " + store.login(unverified));
        System.out.println("Verified: " + store.login(verifiedSameEmail));
        System.out.println("No reauth: " +
            store.link(42, false, true, unverified));
        System.out.println("Explicit link: " +
            store.link(42, true, true, unverified));
        System.out.println("After link: " + store.login(unverified));
        System.out.println("Second owner: " +
            store.link(99, true, true, unverified));
    }
}
```

Compile/run with JDK 17+:

```bash
javac AccountLinkingPolicyDemo.java
java AccountLinkingPolicyDemo
```

Exact stdout:

```text
Unverified: REQUIRE_LOCAL_SIGN_IN
Verified: REQUIRE_LOCAL_SIGN_IN
No reauth: REJECT_PROOF_REQUIRED
Explicit link: LINKED
After link: LOCAL_USER_42
Second owner: CONFLICT_OTHER_OWNER
```

Key takeaway: **a verified email matching the address still does not auto-link**. `verifiedSameEmail`'s `(issuer,subject)` pair differs from `unverified`'s and has no approved link. Explicit linking succeeds after two independent proofs even when the external email is unverified; that **does not promote the external email into a verified application email**.

## 8. Spring Security 6 / Spring Boot 3: Using the Validated ID Token

Example for a **Servlet**, Java 17+, Gradle, and Spring Boot 3.x project.

### 8.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

This is Spring Security OAuth2 Client/Login. `spring-boot-starter-oauth2-resource-server` validates bearer tokens on API requests and **does not replace** the OAuth2 Login client automatically.

### 8.2. Fixed Provider Configuration (OIDC Discovery)

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

`OIDC_ISSUER_URI` must be preconfigured by admins for a trusted IdP/tenant, never chosen by the client. Client secrets live in a secret manager/environment; redirect URIs must match IdP configuration over HTTPS in production. The `openid` scope selects the OIDC flow using ID Tokens for identity authentication.

Spring Security validates the ID Token via OIDC Login when configured properly, including signature, issuer/audience, timestamps, and protocol constraints. Never Base64-decode JWTs and trust claims blindly, and never disable validation when customizing a decoder or adding an OIDC user service.

### 8.3. Extracting the Key After Framework OIDC Validation

This is a Java record used with the dependencies above, **called after OIDC authentication succeeds**, not a JWT signature verifier. Save `src/main/java/com/example/security/ValidatedExternalIdentity.java`:

```java
package com.example.security;

import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ValidatedExternalIdentity(
    String issuer,
    String subject,
    String email,
    boolean emailVerified
) {

    public static ValidatedExternalIdentity from(OidcUser user) {
        OidcIdToken token = user.getIdToken();

        String issuer = token.getClaimAsString("iss");
        String subject = token.getClaimAsString("sub");
        String email = token.getClaimAsString("email");
        boolean verified = Boolean.TRUE.equals(
            token.getClaimAsBoolean("email_verified"));

        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                "Missing OIDC issuer or subject");
        }

        return new ValidatedExternalIdentity(
            issuer, subject, email, verified);
    }
}
```

**Why is this sound within the example's scope?**

- `OidcUser` comes from Spring Security's pipeline already authenticated against a trusted provider; the example **does not** parse raw JSON/JWT from a request.
- Both `email` and `email_verified` are read from the **same ID Token**; if the IdP returns them via UserInfo, verify `sub` matches, check data provenance, and apply policy before reading.
- Only `iss` and `sub` participate in the linking key. Email may be `null`; missing verified flag defaults to `false`.
- The record only shapes identity data; it **does not** search or link local accounts itself. Do not treat `emailVerified` as a permission.
- In multi-tenant environments, the calling layer must also verify issuer/provider/tenant against the config allowlist and the link intent's expected identity.

### 8.4. Integration Points in Spring Security

Spring provides these components:

- `http.oauth2Login(...)`: starts/completes authorization code login; default initiation URL `/oauth2/authorization/{registrationId}` and callback `/login/oauth2/code/{registrationId}`.
- `oauth2Login().userInfoEndpoint().oidcUserService(...)`: customizes user profile handling or authority loading if needed.
- `oauth2Login().successHandler(...)`: integrates login/linking logic after OIDC authentication succeeds.
- `OAuth2AuthenticationToken`: holds the principal and `authorizedClientRegistrationId`, allowing verification against the expected provider.
- `OAuth2AuthorizationRequestRepository`: correlates authorization requests with callbacks; business **link intents** must also bind tightly to the flow/`state`.
- `SecurityContext` and `SecurityContextRepository`: must retain/save the right **local account** principal after login or linking. While a callback temporarily holds an IdP principal, never grant that principal local permissions before mapping.

Example **showing only the hook**, not a complete Spring Boot config:

```java
http.oauth2Login(oauth2 -> oauth2
    .successHandler(accountMappingOrLinkSuccessHandler)
);
```

`accountMappingOrLinkSuccessHandler` is a handler the application **must implement itself** with the local repository, link intent store, transactions, and security context restoration. No built-in class with that name exists in Spring Security. Nor may you configure `oauth2Login(...)` and treat every `OAuth2AuthenticationToken` as an authorized local user: a successful OIDC callback only authenticates the **external account**, without deciding the internal owner yet.

### 8.5. Callback Handling Pseudocode Showing Security Conditions

This is an **illustrative business algorithm**, not a standalone Java class to copy into a project:

```text
onOidcCallback(verifiedOidcUser, authorizationState, currentSession):
    ext = (verifiedOidcUser.idToken.iss, verifiedOidcUser.idToken.sub)
    require ext.iss is expected trusted issuer for this registration

    if linkIntentExistsFor(authorizationState):
        intent = loadAndValidateIntent(
            authorizationState,
            sameBoundSession,
            expectedProvider,
            unexpired,
            unused,
            localOwnerStillEnabled,
            recentLocalReauthentication
        )
        require userConfirmedThisExternalIdentity
        transaction:
            atomicallyConsumeIntentExactlyOnce(intent)
            owner = findLocalOwner(ext.iss, ext.sub)
            if owner exists and owner != intent.localUserId:
                reject conflict
            if owner absent:
                insertLink(intent.localUserId, ext.iss, ext.sub)
                // UNIQUE(issuer,subject) resolves concurrent race
        restoreAuthenticatedLocalPrincipal(intent.localUserId)
        show linked account success
    else:
        owner = findLocalOwner(ext.iss, ext.sub)
        if owner exists and owner is active:
            establishAuthenticatedLocalPrincipal(owner)
        else:
            do not search existing local users by email to auto-link
            show safe sign-in/link or new-account onboarding
```

Intent storage can be a session store/Redis/database with TTL and atomic consumption. Ensure a **standard login** callback cannot spoof a **linking** callback, and vice versa; never rely on client-supplied query strings like `?link=true` or `localUserId=42`.

## 9. Profile Email, Notification Email, and Recovery Channels

Distinguish at least three states:

1. **Local email**: managed by the application, with separate local verification (if any).
2. **IdP email**: merely a profile claim accompanied by issuer, collection time, and whether the IdP marked it verified.
3. **Email trusted enough for password/MFA reset**: follows the application's recovery-channel ownership policy, never inferred from an external profile.

Never overwrite a verified recovery email on a local account with a new IdP email or `email_verified=false`. When the IdP email changes while `(iss,sub)` remains unchanged, the link can stay valid under provider policy; updating contact email must be a separate workflow.

In UI messages, avoid revealing information that helps attackers enumerate registered emails, such as “this email belongs to user #42”. Display a generic message like “If you already have an account, please sign in to link this method” without confirming whether an account exists.

## 10. Unlinking, Revocation, Multi-Tenancy, and Account Lifecycle

- **Unlinking** is sensitive: require local user re-authentication, confirmation, audit logging, transactions, and lockout prevention.
- **Last login method:** disallow removing the sole login link if the account lacks an alternative trusted login/recovery method.
- **Account disabled:** when a local user is locked or disabled, even a validly linked IdP login must not restore access.
- **Issuer/client migration:** never reassign ownership by email when a provider changes tenant, issuer, client ID, or subject strategy; require an approved migration process.
- **Multiple tenants with colliding usernames/emails:** check issuer, tenant, or provider-specific rules; never merge tenant permissions based on email.
- **Compromised/revoked IdP:** implement mechanisms to revoke external links/sessions per risk; never assume old login tokens can reinstate revoked links.
- **Tokens & audit:** never store/log raw OAuth codes, ID/access/refresh tokens, session cookies, or secrets; if storing tokens to call APIs is needed, use a dedicated secure store. Audit logs may store internal IDs, issuer, protected subject references, timestamp, and link outcome.

## 11. Required Test Scenarios

| Test | Input | Expected |
|---|---|---|
| Unverified spoofed email | Local #42 has `mai@example.org`; attacker IdP claims that email, `email_verified=false` | Does not auto-link/log in #42 |
| Matching verified email | New IdP has `email_verified=true` yet `sub` is unlinked, email matches #42 | Does not auto-merge #42 |
| Missing verified claim | Has `email`, lacks `email_verified` | Treat email as unverified; never use as login key |
| Missing email | Valid token with `iss+sub`, no email | Login via link if present; otherwise separate onboarding |
| IdP email changed | Same `iss+sub`, email changed | Link owner unchanged; local email not silently overwritten |
| Two IdPs share `sub` | Different issuers, identical subject string | Two distinct identities |
| Already linked | `iss+sub` maps to active local #42 | Logs in #42 with app roles |
| Active link intent | #42 signed in locally, step-up, valid OIDC callback, confirmed right account | Unique link to #42 |
| No recent reauth | Stale local session, missing step-up | Link rejected |
| Link CSRF | Attacker tries to inject their IdP account callback into victim session | State/session/intent check fails |
| Callback replay | Reused state/intent after consumption | Does not create/modify link |
| Wrong provider | Token issuer differs from intent's provider | Rejected |
| Invalid token | Invalid signature, `aud`, `iss`, exp, or nonce | Rejected before policy |
| Different UserInfo `sub` | UserInfo subject differs from ID Token | Reject UserInfo/authentication |
| Same external identity, two owners | #42 and #99 race to insert | Only one owner via unique constraint; other gets conflict |
| Local disabled | IdP link remains yet local account locked | No permissions granted |
| Last-method unlink | No other login method remains | Requires valid recovery method before unlinking |

**Spring Security and browser session integration tests:**

1. Create a link intent under local principal A, try callback with session B or another provider → must be rejected.
2. After OIDC callback, verify the principal in `SecurityContext` is the mapped local owner, not a temporarily privileged external principal.
3. Try tampering with `state`, reusing consumed codes, swapping issuer, or injecting forged “`email_verified=true`” JSON → cannot bypass validation.
4. Race two link transactions for the same `(iss,sub)` across two nodes → database still holds only one owner.
5. Disable internal user or revoke link; subsequent requests must not regain permissions via matching email.
6. Inspect logs: zero ID Tokens, access tokens, authorization codes, refresh tokens, session secrets, or unnecessary PII.

## 12. Mistakes to Avoid

| Mistake | Right Understanding / Design |
|---|---|
| “OIDC returned the same email, so it's the same person.” | Email is neither stable nor unique; use `iss+sub` and approved links. |
| “`email_verified=true` permits merging existing accounts.” | Verified is an email attribute at verification time, not local account ownership. |
| “Spring OAuth2 Login handles account linking automatically.” | The framework performs protocol authentication; local owner mapping and link intents are application logic. |
| “Decoding the JWT is enough.” | Must verify signature, issuer, audience, timestamps, and protocol conditions. |
| “Checking for an existing link with SELECT prevents race writes.” | Database unique constraints and transactions are required. |
| “A user logging in via IdP automatically gets local ROLE_ADMIN.” | Local permissions must be loaded/evaluated separately; never grant by IdP email or profile. |
| “Disable CSRF because OAuth already has state.” | State protects the OAuth response; link initiation/confirmation endpoints still need intent, session, reauth, and CSRF controls. |
| “When email changes, move the link to the user with the new email.” | Links stay keyed by `iss+sub`; ownership transfer requires an independent verification workflow. |

## 13. Knowledge Self-Check

**Question 1:** If `email_verified=false` and the email matches a local user, may it log into that local user?  
**Answer:** No. An unlinked external identity cannot prove access to a local account via email.

**Question 2:** If `email_verified=true`, should it auto-link to an existing local user registered with that email?  
**Answer:** It should not. OIDC does not guarantee emails cannot collide or change; linking to an existing local account requires proof of ownership of both accounts and explicit intent.

**Question 3:** Why store the pair `iss` and `sub` instead of only `sub`?  
**Answer:** `sub` is unique only within an issuer's scope; two issuers can issue the same subject string to different people.

**Question 4:** Is OAuth `state` alone enough for safe linking?  
**Answer:** No. You also need a link intent binding the local account, session, provider, expiration, re-authentication, confirmation, and atomic processing.

**Question 5:** Why must the database have `UNIQUE(issuer,subject)`?  
**Answer:** It prevents two local users from becoming owners of the same external identity under concurrent requests.

**Question 6:** When a user changes their email at the IdP, how should the link record change?  
**Answer:** Keep the `(iss,sub)` identity; contact/recovery emails have their own update and verification workflow.

## References

- [OpenID Connect Core 1.0 — Standard Claims, UserInfo, and Claim Stability (`5.1, `5.3.2, `5.7)](https://openid.net/specs/openid-connect-core-1_0.html): `iss`, `sub`, `email_verified`, uniqueness/stability, UserInfo `sub` check.
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, issuer URI, redirect callback, and basic configuration.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, ID Token validation, user mapping, and extension points.
- [Spring Security — Servlet OAuth2 Overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): distinguishing OAuth2 Client/Login from Resource Server, role of OIDC ID Token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): securing authorization code flow, redirects, mix-up, and request/response correlation.
