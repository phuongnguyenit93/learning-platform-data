# 25.6. Linking Multiple Identities to One Internal Account

## 1. The Problem: One Person, Multiple Identity Providers

In a **Spring Security OAuth 2.0/OIDC Client** application, a user may log in through multiple Identity Providers (IdPs), such as a corporate OpenID Provider, a Google account, or another OAuth2 provider. Even so, the application may want the user to see **a single internal account**: the same profile, orders, history, and business permissions.

Example:

```text
                  INTERNAL ACCOUNT
                 user_id = 7b6f...
                 displayName = Alice
                 tenant_id = tenant-a
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
   Google OIDC     Corporate OIDC   GitHub OAuth2
   iss+sub = G1    iss+sub = C9     providerUserId=4421
          |             |             |
          +-------------+-------------+
                        |
                        v
                 Alice logs in
          -> same internal user_id
          -> app data/authorization
```

**Identity linking (account linking)** is when an application creates a controlled relationship:

```text
External Identity  --->  Internal Account
```

This is not merely "comparing two matching emails." It is a **security decision**: anyone who authenticates with a linked external identity gains the ability to log in or act under the permissions of that internal account.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **internal account**, **external identity**, **OAuth2/OIDC login session**, and **`OAuth2AuthorizedClient`**.
2. Use a stable OIDC identifier via the **`(iss, sub)`** pair.
3. Determine the identifier key for non-OIDC OAuth2 providers.
4. Explain why **auto-linking by email must not be done**, even for verified emails, without explicit policy and additional proof.
5. Design a flow for **logging in with a linked identity** separately from a flow for **linking a new identity**.
6. Require proof of control over both the internal account and the new identity; prevent account takeover.
7. Use `state`, PKCE, OIDC `nonce`, CSRF, and recent authentication checks.
8. Design SQL schemas, unique constraints, and transactions to handle concurrent linking races.
9. Understand Spring Security extension points such as `OidcUserService`, `DefaultOAuth2UserService`, success handlers, and repositories/services.
10. Map external identities to a consistent **local principal**.
11. Distinguish identity linking from storing access/refresh tokens to call provider APIs.
12. Design unlinking, logout, revocation, account recovery, multi-tenancy, and auditing.
13. Test collision and attack scenarios.

> Scope: multiple providers in **Spring Security OAuth 2.0/OIDC Client**. Examples use Spring Boot/Spring Security on Servlet MVC; WebFlux is contrasted separately. Illustrative provider names, domains, and identities do not represent actual production configurations.

---

## 2. Distinguishing Four Identity and Authorization Layers

### 2.1. Internal account

An application account typically has an ID managed by the system itself:

```text
internal_user_id = 7b6f51dc-...
status = ACTIVE
tenant_id = tenant-a
profile = ...
```

This ID governs ownership of business data and is the entity to which the application grants permissions.

**One internal account is not necessarily equivalent to one external identity.**

### 2.2. External identity

An identity authenticated by a provider, for example:

```text
OIDC issuer = https://login.corporate.example
OIDC sub    = 00u3abc...

Google issuer = https://accounts.google.com
Google sub    = 109101...
```

In OIDC, `sub` is only fully meaningful within the namespace of `iss`. Two issuers can both issue `sub="123"` for two different people.

### 2.3. Spring Security's `Authentication`

After login, Spring Security can create:

```java
OAuth2AuthenticationToken
```

with a principal of:

```java
OidcUser  // OIDC provider
OAuth2User // non-OIDC OAuth2 login
```

`Authentication.getName()` typically reflects the principal's name, but **never assume it is the internal account ID** unless a mapping step is configured.

### 2.4. `OAuth2AuthorizedClient`

`OAuth2AuthorizedClient` holds the client registration, principal name, access token, and possibly refresh token.

It serves **calling APIs at the provider/Resource Server**, not recording ownership of an internal account.

| Component | Contains what? | Used for what? |
|---|---|---|
| `InternalAccount` | Immutable local ID, status, business roles | Application data and permissions |
| `ExternalIdentity` | Provider namespace, stable subject, link to account | Identifies account when user logs in via provider |
| `Authentication` | Current principal, authorities, auth details | Spring Security authentication/authorization |
| `OAuth2AuthorizedClient` | Registration, access/refresh tokens, expiry | Calling downstream APIs via OAuth2 |

**Do not equate `OAuth2AuthorizedClient.getPrincipalName()` with the external identities table**, unless the system intentionally designs a consistent mapping and verifies its security properties.

---

## 3. Reliable OIDC Identifier: `(iss, sub)`

In OpenID Connect, the ID Token contains:

```json
{
  "iss": "https://login.corporate.example",
  "sub": "alice-00u3",
  "aud": "portal-client",
  "exp": 1980000000,
  "iat": 1979996400
}
```

For an **identity verified via OIDC login**, use:

```text
identity_key = (validated_issuer, validated_subject)
```

### 3.1. Why is `issuer` required?

Example:

```text
Provider A: iss=https://id-a.example, sub=123
Provider B: iss=https://id-b.example, sub=123
```

These two identities **are not the same person** merely because `sub` is equal.

### 3.2. Why not use email?

Emails can:

- Change when users change names or companies.
- Be omitted by a provider.
- Be unverified.
- Be reassigned to another employee after the former employee leaves.
- Collide across multiple provider accounts.
- Lack equivalence to ownership of an internal account.

Even if `email_verified=true`, that is usually just a claim by the provider under its own mechanism at a point in time. It is **not proof that the application should attach a new identity to an existing account sharing that email**.

### 3.3. Pairwise subjects

An OpenID Provider may issue **pairwise subject identifiers**: the same user receives different `sub` values across different OAuth2 clients/sector identifiers.

Therefore:

```text
sub from client A != sub from client B
```

does not necessarily mean two different people.

Do not auto-link them by email without a verified linking flow. Check the issuer and subject policy per client/sector in the provider contract.

### 3.4. Issuer must be verified, not supplied by the browser

Only trust `(iss, sub)` after Spring Security/the OIDC client validates the ID Token as required: signature/JWK, issuer, audience, expiry, `state`/`nonce`/corresponding checks.

Never accept:

```text
POST /api/link
{"issuer": "...", "subject": "..."}
```

and write it straight to the DB. A caller could supply someone else's `sub`.

---

## 4. Non-OIDC OAuth2 Providers: Use a Stable Provider User ID

Some providers support OAuth2 Login without providing an OIDC ID Token. `DefaultOAuth2UserService` can call a UserInfo/user endpoint to retrieve attributes.

For example, a provider returns:

```json
{
  "id": 44217820,
  "login": "alice-dev",
  "email": "alice@example.com",
  "name": "Alice"
}
```

If the provider documents `id` as a stable account identifier, you can build:

```text
namespace = oauth2:github
subject   = "44217820"
```

However, you must understand the provider's contract:

- Is the User ID stable when the username changes?
- Are IDs ever reused?
- Are there multiple enterprise instances/hosts?
- Was the user endpoint genuinely called using the provider-issued access token?
- Was the response verified over HTTPS with proper TLS?
- Do organization/tenant mechanisms alter the identity namespace?

### 4.1. Do not use display name or username if a stable ID exists

An account might change:

```text
login = alice-dev
```

to:

```text
login = alice-platform
```

while the numeric user ID stays the same. Keying by `login` causes the system to treat them as two identities, or leads to mis-mapping if the old username is claimed by someone else.

### 4.2. One "provider" can have multiple instances

For example, GitHub.com and a private GitHub Enterprise Server:

```text
oauth2:github.com
oauth2:github.enterprise.example
```

Never merge user IDs from two instances into the same namespace. For OIDC, the issuer URI normally provides this namespace.

### 4.3. Do not trust claims from an unverified provider

If `OAuth2User` is constructed from frontend-submitted data or an unauthenticated userinfo endpoint, never use it to link accounts.

Provider identity must come from a completed OAuth2/OIDC flow and a trustworthy source of claims/attributes per the provider's contract.

---

## 5. Two Flows Must Stay Separate: Login vs. Linking

### 5.1. Flow A: Logging in with an already-linked identity

```text
User selects "Sign in with Google"
    |
    v
OAuth2/OIDC login succeeds
    |
    v
IdentityKey = (iss, sub)
    |
    v
Lookup external_identity
    |
    +-- Linked to internalUserId U
    |      -> Create local Authentication for U
    |      -> Use U's business roles/tenant
    |
    +-- Not linked
           -> New account creation workflow,
              or ask user to log into existing account
              and perform explicit linking
```

**Never do "identity not found, so search for matching email and log into that account."** That is a very common source of account takeover.

### 5.2. Flow B: Linking an additional identity to a logged-in account

```text
User already logged into internal account U
    |
    v
Clicks "Link Google"
    |
    v
BFF checks U, CSRF, recent auth/step-up
    |
    v
Starts OAuth2/OIDC authorization for Google
    |
    v
Google authenticates identity G
    |
    v
BFF validates state, PKCE, nonce, callback
    |
    v
Is external identity G already attached to another account?
    |
    +-- Yes: reject, do not hijack link
    |
    +-- No: record (G -> U) atomically
            audit + notify
```

This combines **the intentional decision of account U's owner** with **proof the user controls external identity G**.

### 5.3. Why not use a callback that "auto-links if email matches"?

If account U holds sensitive data and provider X issues an email matching U due to misconfiguration or email recycling, an attacker can log into identity X and get auto-linked to U.

Once linked, the attacker can keep logging in as U later, even after U logs out.

**Safe default rule:** only auto-login with an external identity **that was already linked beforehand**; a new identity creates a new account or goes through an explicit account-linking flow with permission checks.

---

## 6. Threat Model for Account Linking

Risks to consider before writing controllers:

| Threat | Example | Mitigation |
|---|---|---|
| Email-based account takeover | Attacker has provider account with U's email | Never auto-link by email |
| Login CSRF / account confusion | Attacker's identity callback enters victim's session | OAuth2 `state` + session binding + intent |
| Link CSRF | Malicious site tricks victim into linking an identity | CSRF protection on link initiation |
| Stolen session | Attacker holds U's session cookie, adds own identity | Step-up/re-authenticate account U |
| IdP mix-up | Response from provider B handled as provider A | Registration/issuer/callback binding and validation |
| Subject collision | Two issuers share `sub=123` | `(iss, sub)` key |
| Stale provider email | Recycled old email | Never use email as ownership key |
| Two-account race | Two requests attach identity G to U and V concurrently | Unique constraint + transaction |
| Overly broad session rights | New login callback replaces old user mid-link | Pending intent holds server-side account U |
| Token theft | Link callback/tokens logged or sent to browser | Backend-only tokens, redaction |
| Unlink self-lockout | User deletes their last login method | Block or require a recovery method |
| Token persistence mismatch | Link succeeds, yet token saved under old principal | Align authorized client store/mapping |
| Cross-tenant linking | Tenant A's identity attached to Tenant B's account | Tenant policy and namespace |
| Malicious provider metadata | User-chosen dynamic issuer | Allowlist and discovery trust |
| Email-based recovery abuse | Transferring links via insufficiently verified email | Recovery with step-up and independent policy |

There is **no single check** that mitigates all these risks. Account linking requires defense in depth: authentication, session/CSRF, provider validation, database constraints, business policies, and auditing.

---

## 7. Proof of Control on Both Sides

A valid link requires **two conditions simultaneously**.

### 7.1. Internal account side

The application must know the person initiating the link is authorized to manage account U.

Typically:

- A valid `Authentication` exists in the Spring Security session.
- Internal account U is active.
- The user logged in recently or completed **step-up** via MFA/password/passkey based on risk.
- Valid CSRF token on link initiation.
- User/tenant policy permits adding that provider.
- The session was not revoked between initiation and completion.

### 7.2. External identity side

The application must have proof that external identity G was authenticated by the provider:

- Redirected to the configured authorization endpoint.
- Callback `state` matches the authorization request.
- PKCE code challenge/verifier per policy.
- Valid OIDC ID Token with `iss`, `aud`, expiry, and `nonce` verified where applicable.
- For non-OIDC OAuth2, a trustworthy provider user endpoint/stable ID.
- If recent authentication is required, verify `auth_time`, `max_age`, and `acr`/`amr` per provider.

**Email confirmation does not replace external identity authentication.**

### 7.3. "Prompt login" is not absolute

OIDC may support:

```text
prompt=login
max_age=0
```

yet enforcement and `auth_time`/`acr` depend on the IdP. Never assume simply adding a query parameter proves fresh MFA login.

For sensitive account linking, verify authentication freshness and assurance per the IdP contract or require additional app-local step-up.

---

## 8. Backend-Stateful Linking Flow

In a browser, a common design is:

```mermaid
sequenceDiagram
    autonumber
    actor U as Browser / User
    participant App as Spring Boot BFF
    participant Sess as Session / Pending Link Store
    participant IdP as External IdP
    participant DB as Identity DB

    U->>App: POST /api/account/links/start {provider}
    Note over App: Session U authenticated, CSRF, step-up
    App->>Sess: Create pending link for internalUserId U
    App-->>U: Allowlisted login navigation URL
    U->>App: GET /oauth2/authorization/{registrationId}
    App->>Sess: OAuth2 authorization request; state + PKCE
    App-->>U: 302 to provider authorize
    U->>IdP: Login/consent at provider
    IdP-->>U: 302 callback code + state
    U->>App: GET /login/oauth2/code/{registrationId}
    App->>Sess: Validate OAuth2 state, session binding, PKCE
    App->>IdP: Back-channel token request
    IdP-->>App: Token / verified OIDC identity
    App->>Sess: Resolve pending link, U, state, expiry
    App->>DB: INSERT external identity -> U (unique)
    DB-->>App: Link created
    App->>Sess: Consume pending link, preserve local login U
    App-->>U: Redirect /settings/connections?linked=1
```

### 8.1. What data does a pending link intent need?

A server-side record might contain:

```text
pending_link_id = random opaque value
internal_user_id = U
session_binding = current authenticated session binding
registration_id = google
oauth_state_binding = expected OAuth2 authorization state
created_at = ...
expires_at = ...
consumed = false
required_assurance = recent_login_with_mfa
```

Never store refresh tokens or client secrets in the pending record.

**Correlation with OAuth2 `state` must be verified.** If the app only remembers "this session wants to link Google" without knowing which authorization request a callback corresponds to, it can link the wrong identity across multiple tabs or competing login flows.

### 8.2. Do not replace framework-generated `state`

Spring Security already manages OAuth2 authorization requests and `state`. To attach business intent, you can:

- Use a server-side pending record referencing the authorization request's **`state`** via a custom `OAuth2AuthorizationRequestResolver`/`Repository`.
- Or design a dedicated flow with strong transaction binding and an explicit callback route.
- Always let Spring Security validate OAuth2 `state` per protocol before processing the identity.

Never create a static `state` or use a user ID/email as `state` and bypass framework validation.

### 8.3. Session IDs may change after authentication

Spring Security commonly applies session fixation protection when OAuth2 login completes. If a pending link is bound strictly to the old session ID string and ignores session migration/ID changes, the callback may fail to find the pending intent.

Use a server-side record/session mechanism compatible with the session lifecycle, while verifying the intent still belongs to the same user/account. Never skip checking intent because of a session migration bug.

---

## 9. Callback May Change the Current `Authentication`

A subtle detail: a successful OAuth2 Login endpoint typically sets **the new provider's `Authentication`**.

Inside the success handler:

```text
Before redirect:
    Browser session is authenticated as InternalAccount U

After OAuth2 provider callback:
    Authentication in the filter chain may be OAuth2AuthenticationToken(G)
```

Therefore **never assume**:

```java
SecurityContextHolder.getContext().getAuthentication().getName()
```

in the success handler will always return the internal user U who initiated the link. It may return **external principal G** after the provider login succeeds.

### 9.1. Where to get the original internal account?

From the **server-side pending link intent** created before redirect and bound to U's session/state/authentication.

The callback must:

1. Validate the OAuth2 callback successfully.
2. Determine the verified registration/identity G.
3. Resolve the exact pending record by state/session.
4. Confirm the pending record is valid, unconsumed, and unexpired.
5. Verify account U is still active and session binding matches.
6. Execute the link atomically.
7. Finish the flow with **U's local `Authentication`**, without accidentally switching the browser to another internal account.
8. Consume the intent and clear temporary state on both success and failure.

### 9.2. Do not guess U from email or provider principal

Wrong:

```text
Callback G has email alice@example.com
    -> find internal account by email
    -> link G to result
```

Right:

```text
Verified PendingLinkIntent: internalUserId U
Verified external identity: G
DB transaction: link G -> U if policy and uniqueness allow
```

### 9.3. Normal login callback and linking callback are not identical

A callback without a valid pending link should be processed as a **normal login** (if that is the intended flow) or rejected per routing policy—**never auto-linked**.

Some systems use a separate route/authorization request marker for account linking to avoid ambiguity. When sharing a callback, logic must cleanly separate the two intents and never let a browser query parameter like `link=true` turn a login callback into a linking operation.

---

## 10. `state`, PKCE, OIDC `nonce`, and CSRF Play Different Roles

| Mechanism | Protects |
|---|---|
| OAuth2 `state` | Binds authorization response to authorization request; prevents login CSRF when properly designed |
| PKCE | Binds authorization code to client-held code verifier |
| OIDC `nonce` | Binds ID Token to OIDC authentication request, prevents replay per OIDC |
| BFF session cookie | Authenticates browser-to-backend session; must be protected against session hijacking |
| CSRF token | Protects state-changing POST link/unlink requests under cookie auth |
| Step-up/recent auth | Mitigates session theft adding a persistent login method |
| Database uniqueness | Prevents one external identity from linking to two accounts simultaneously |
| Authorization check | Ensures U is permitted to manage that account and registration |

**Never disable CSRF protection** for account settings on the grounds that "OAuth2 already has `state`." `state` only protects the OAuth2 flow, not every state-mutating API.

### 10.1. Link initiation should be a CSRF-protected POST

An illustrative endpoint:

```http
POST /api/account/links/start HTTP/1.1
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Content-Type: application/json

{"registrationId":"google"}
```

The controller checks:

- Authenticated account.
- Provider is in the server-side allowlist.
- CSRF validated by Spring Security.
- Reauthentication/step-up is sufficiently recent.
- Account is not locked/disabled.
- Limits/rate limiting.

Then the backend creates a pending intent and returns the OAuth2 authorization initiation URL (never returning OAuth2 tokens).

### 10.2. OAuth2 redirect remains a top-level browser navigation

The frontend uses:

```javascript
window.location.assign(startUrl);
```

to execute the Authorization Code Flow, rather than starting OAuth2 login via a `fetch()` expecting JSON and having `XMLHttpRequest` follow redirects to the IdP.

---

## 11. Data Architecture: Accounts and External Identities

An illustrative SQL schema:

```sql
CREATE TABLE internal_account (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    namespace VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    provider_display_name VARCHAR(200),
    provider_email VARCHAR(320),
    email_verified BOOLEAN,
    linked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_login_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_external_identity_account
        FOREIGN KEY (account_id)
        REFERENCES internal_account(id),
    CONSTRAINT uq_external_identity_namespace_subject
        UNIQUE (namespace, subject)
);

CREATE INDEX idx_external_identity_account
    ON external_identity(account_id);
```

**This is an illustrative custom schema**, not default tables created by Spring Security or `JdbcOAuth2AuthorizedClientService`.

### 11.1. How is `namespace` constructed?

For OIDC:

```text
namespace = validated ID Token iss
subject = validated ID Token sub
```

For non-OIDC OAuth2:

```text
namespace = canonical provider instance identifier
subject = stable provider user ID from trusted provider API
```

Example:

```text
namespace = oauth2:github.com
subject = 44217820
```

Never use a constant `provider="oauth2"` across all providers.

### 11.2. Why is `UNIQUE(namespace, subject)` a core constraint?

An external identity must point to **at most one internal account** at a time. If two accounts both store the same external identity, the next login will lack a single unambiguous account to determine permissions.

The database constraint is the last line of defense complementing Java checks. A check like:

```java
if (!repository.existsByNamespaceAndSubject(...)) {
    repository.save(...);
}
```

is **not atomic** across concurrent transactions.

### 11.3. Should `(account_id, registration_id)` be unique?

Depends on business rules:

- If each account may link only **one Google identity** for registration `google`, add the corresponding unique constraint.
- If the product allows **two different Google accounts** under the same internal account, omit that constraint and design how identities/tokens are selected when calling APIs.
- If one registration can point to multiple issuer/provider instances, keying by registration does not replace `namespace`.

Do not assume Spring's `OAuth2AuthorizedClientService` can store **multiple provider identities under the same registration and same principal name**; default lookups key by `(registrationId, principalName)`.

### 11.4. Do not treat `provider_email` as a unique identity

Email can be stored as a **display attribute or UX hint**, but never as a unique external identity key. If an email changes, have a policy to update it rather than transferring the identity link to someone else.

### 11.5. Separate secret storage

Never add raw refresh tokens to the `external_identity` table just for query convenience. If downstream provider API access is needed, store tokens via `OAuth2AuthorizedClientRepository/Service` or a protected token vault. Identity mapping schemas and token storage have distinct lifecycles.

---

## 12. Transactions and Race Conditions When Multiple Accounts Link One Identity

Suppose Alice (U1) and Bob (U2) complete OAuth2 login for the same external identity G nearly simultaneously:

```text
Request A:
    SELECT G -> not found
Request B:
    SELECT G -> not found

Request A:
    INSERT G -> U1

Request B:
    INSERT G -> U2
```

Without uniqueness, G could become attached to both accounts.

With the constraint:

```sql
UNIQUE(namespace, subject)
```

only one insert can succeed.

### 12.1. Transaction pseudocode

```text
@Transactional linkVerifiedIdentity(
    expectedInternalAccountId,
    verifiedExternalIdentity
):
    1. Load internal account U; require ACTIVE.
    2. Confirm current policy allows this provider/tenant.
    3. Check existing identity by (namespace, subject).
    4. If linked to U:
           -> treat as already linked, if flow proof still valid.
    5. If linked to another account:
           -> reject, never reassign silently.
    6. Otherwise INSERT G -> U.
    7. Flush/commit; unique constraint enforces exclusivity.
    8. Emit audit/domain event after successful commit.
```

In production, handle database unique constraint violations caused by races and return a business error **without revealing which account holds the link** to an unauthorized caller.

### 12.2. Illustrative Java service

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdentityLinkingService {

    private final InternalAccountRepository accounts;
    private final ExternalIdentityRepository identities;

    public IdentityLinkingService(
            InternalAccountRepository accounts,
            ExternalIdentityRepository identities) {
        this.accounts = accounts;
        this.identities = identities;
    }

    @Transactional
    public void linkVerified(
            UUID expectedAccountId,
            VerifiedExternalIdentity verified) {

        InternalAccount account = accounts
            .findById(expectedAccountId)
            .orElseThrow(() ->
                new IllegalStateException("Account not available"));

        if (!account.isActive()) {
            throw new IllegalStateException("Account is inactive");
        }

        var existing = identities.findByNamespaceAndSubject(
            verified.namespace(),
            verified.subject()
        );

        if (existing.isPresent()) {
            if (existing.get().getAccountId()
                    .equals(expectedAccountId)) {
                return; // Idempotent if caller is properly authenticated.
            }
            throw new IdentityAlreadyLinkedException();
        }

        ExternalIdentity identity = new ExternalIdentity(
            UUID.randomUUID(),
            account.getId(),
            verified.namespace(),
            verified.subject(),
            verified.registrationId(),
            Instant.now()
        );

        identities.saveAndFlush(identity);
    }
}
```

`InternalAccount`, `ExternalIdentity`, repositories, exceptions, and `VerifiedExternalIdentity` are application-defined types. This is a **transaction logic skeleton**, not a standalone runnable JPA application.

In a real flow, callers may only invoke `linkVerified` **after** checking pending intent, CSRF/step-up, and external identity validation. `VerifiedExternalIdentity` must be constructed by trusted authentication infrastructure, never deserialized directly from frontend JSON.

### 12.3. Handling unique conflicts at transaction boundaries

If `saveAndFlush` hits a unique violation, the transaction may be marked rollback-only. Never catch the exception and continue performing further DB writes inside the **same broken transaction**.

You can:

- Let the transaction roll back and map `DataIntegrityViolationException` at an outer API/service boundary.
- Re-read the identity in a fresh transaction if you need to distinguish idempotency from conflict.
- Never automatically reassign the link to the requesting account.

### 12.4. Idempotency is not re-linking

If a link request `G -> U` is retried after the DB commits yet the HTTP response was lost, you can return "already linked" when **G still belongs to U** and proof/session policy holds.

If G currently belongs to V, U's retry **must never delete `G -> V`**. Transferring ownership is a separate workflow requiring stronger proof.

---

## 13. Designing `VerifiedExternalIdentity` as a Data Boundary

An internal type could be:

```java
public record VerifiedExternalIdentity(
    String namespace,
    String subject,
    String registrationId,
    String displayName,
    String email,
    boolean emailVerified
) {
    public VerifiedExternalIdentity {
        if (namespace == null || namespace.isBlank()
                || subject == null || subject.isBlank()
                || registrationId == null || registrationId.isBlank()) {
            throw new IllegalArgumentException(
                "External identity key is required"
            );
        }
    }
}
```

**Important:** the record constructor only checks **non-emptiness**; it does not prove tokens or providers were verified.

A record should only be treated as `Verified` if constructed from a completed trust boundary:

- An OIDC principal whose ID Token was validated by Spring Security per issuer/client.
- An `OAuth2User` returned from a trusted provider user endpoint over an authenticated flow.
- A registration ID belonging to the configured and permitted list.
- A subject extracted from a stable claim/attribute guaranteed by the provider.

### 13.1. Converting `OidcUser` into an identity key

Pure code logic example after OAuth2 Login completes:

```java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public VerifiedExternalIdentity fromOidc(
        String registrationId,
        OidcUser user) {

    String issuer = user.getIdToken()
        .getIssuer()
        .toString();

    String subject = user.getSubject();

    String email = user.getEmail();

    return new VerifiedExternalIdentity(
        issuer,
        subject,
        registrationId,
        user.getFullName(),
        email,
        Boolean.TRUE.equals(
            user.getClaimAsBoolean("email_verified")
        )
    );
}
```

This snippet assumes `OidcUser` was created by Spring Security **after OIDC token validation**. Never accept a raw ID Token string from the browser and parse claims yourself while skipping signature/issuer/audience checks.

### 13.2. Provider-specific user attributes

For a non-OIDC OAuth2 provider, a dedicated mapper per registration is required:

```text
github:
    namespace = oauth2:github.com
    subject = stable numeric id from verified OAuth2User

enterprise-gitlab:
    namespace = oauth2:gitlab.enterprise.example
    subject = stable id per instance
```

Never assume every provider has `sub`. `OAuth2User.getName()` depends on `user-name-attribute` configuration, and some providers use unstable nicknames or handles.

---

## 14. Multiple ClientRegistrations in Spring Boot

Example `application.yml` on Spring Boot 3.x:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email

          workforce:
            provider: workforce-oidc
            client-id: ${WORKFORCE_CLIENT_ID}
            client-secret: ${WORKFORCE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

        provider:
          workforce-oidc:
            issuer-uri: https://login.corporate.example
```

Values are placeholders; never commit secrets to the repository.

`google` can use provider defaults supported by Spring Boot. A custom-configured OIDC provider uses `issuer-uri` for discovery and validating the expected issuer, depending on provider metadata/version.

### 14.1. Registration ID does not replace the identity key

`registrationId="workforce"` is an application-chosen name to look up an OAuth2 `ClientRegistration`. It is **neither an issuer** nor a user ID.

Example:

```text
registrationId = workforce
issuer = https://login.corporate.example
sub = 123
```

If the registration is later renamed to `workforce-v2` while `issuer` + `sub` remain unchanged, do not create a new identity for the same user just because a config key changed, unless migration policy specifies otherwise.

### 14.2. Do not let the frontend supply an arbitrary issuer URI

Never implement dynamic registration like:

```text
GET /login?issuer=https://attacker.example
```

and automatically trust the discovery endpoint passed by the browser. This can cause issuer mix-up, metadata injection, token leakage, and SSRF.

For enterprise multi-tenant dynamic IdPs, enforce tenant allowlists, provider onboarding, and strict validation.

### 14.3. Which providers have `email_verified`?

OIDC defines the standard `email_verified` claim if the provider issues it. With non-OIDC OAuth2 UserInfo, a similar field may have different semantics or not exist.

Never assume:

```java
user.getAttribute("email_verified")
```

is a trustworthy boolean across every OAuth2 provider.

---

## 15. `SecurityFilterChain` and OAuth2 Login

A minimal Servlet configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/assets/**").permitAll()
                .requestMatchers("/api/account/links/**").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        // Keep CSRF protection for state-changing endpoints.
        return http.build();
    }
}
```

This enables OAuth2/OIDC Login for multiple declared registrations. **It does not implement account linking yet**; you must build the mapping, pending intent, success handling, and local `Authentication` per the following sections.

### 15.1. OAuth2 login success does not mean linking is permitted

Spring Security proves the OAuth2 callback is valid. Whether `G -> U` may be created still depends on:

- Internal account U of the user initiating the link.
- Selected provider.
- Reauthentication freshness.
- Tenant policy.
- Whether external identity G already belongs to another account.
- Linking consent and audit.

Never auto-link inside `OAuth2UserService.loadUser()` merely because an `OAuth2User` has a matching email.

---

## 16. Spring Security Extension Points for Identity Mapping

### 16.1. `OAuth2UserService`

For non-OIDC OAuth2 providers:

```java
org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService
```

It retrieves user attributes from the provider using the access token and appropriate UserInfo endpoint.

### 16.2. `OidcUserService`

For OIDC login:

```java
org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService
```

It builds/populates the OIDC principal from the ID Token and UserInfo per protocol/configuration.

### 16.3. What is a custom user service used for?

A wrapper/delegate can be used to:

1. Obtain the authenticated `OidcUser`/`OAuth2User` from the framework.
2. Construct a stable external identity key.
3. Look up the linked internal account.
4. Map domain-specific profiles or authorities per local policy.
5. Return an application-specific principal carrying the internal account ID.

Conceptual sketch:

```java
OidcUserService delegate = new OidcUserService();

OAuth2UserService<OidcUserRequest, OidcUser> customService =
    userRequest -> {
        OidcUser oidc = delegate.loadUser(userRequest);

        String issuer = oidc.getIdToken()
            .getIssuer()
            .toString();
        String subject = oidc.getSubject();

        // Look up identity map; account linking needs its own flow.
        // Return the appropriate local principal if a mapping already exists.
        return oidc;
    };
```

**This snippet illustrates the extension point, not a complete account-mapping implementation.** In a linking flow without an existing external identity mapping, never silently assign by email.

### 16.4. Authentication success and linking success are two different events

An OAuth2 login success handler can branch:

```text
if validated pending link intent:
    -> link external identity to pre-existing internal account
    -> preserve/restore intended local principal session
else:
    -> normal external identity login
    -> mapped internal account or onboarding
```

However, the success handler runs **after certain security authentication and authorized client persistence steps**. Understand the filter chain order of your version and avoid accidentally saving tokens under the wrong principal or overwriting the user's session.

### 16.5. Do not write "half-login, half-link" code in a controller

A controller should not accept raw `code`/`state` and call the Token Endpoint itself when Spring Security already provides OAuth2 Login infrastructure. Doing so easily omits PKCE, nonce, redirect URI, and state validation.

Prefer standard OAuth2 Login and customizations at documented extension points, with clear separation between authentication and business linking.

---

## 17. Consistent Local Principal After Logging In with Multiple IdPs

Goal:

```text
Google identity G -> internal account U
Corporate identity C -> internal account U

On both logins:
    Authentication.getName() -> stable internal account key U
```

Yet **you must not just override `getName()` and consider it finished**.

### 17.1. Two identity layers inside one principal

A custom principal can hold:

```text
internalUserId = U
externalIdentityKey = (iss, sub)
registrationId = google
displayName = Alice
authorities = computed from local policy
```

External identity data serves auditing and provider API access; `internalUserId` serves business authorization.

### 17.2. Application permissions should not blindly trust provider claims

For example, a provider returns:

```text
email = alice@company.example
groups = ["engineering"]
```

That does not automatically mean Alice holds `ROLE_ADMIN` in the application.

Local authorities can come from the database and tenant policies, with IdP claims serving as **signals trusted per mapping rules**.

A provider identity attached to account U should not automatically merge all permissions across different tenants.

### 17.3. Disabled local accounts must apply across all linked identities

If `InternalAccount(U).status=DISABLED`, logging in via either Google or Workforce must be rejected or restricted per policy.

Do not only disable username/password login while forgetting OAuth2 login paths.

### 17.4. Post-linking session must still belong to U

After callback for a new identity G, never let the browser switch to user V just because a success handler loaded a different mapping for G or ran auto-onboarding. If G is already linked to V, **reject the link** and keep U's session (or require reauthentication per policy)—never silently switch.

---

## 18. `OAuth2AuthorizedClientService` and Default Key Limitations

Spring Security OAuth2 Client typically loads an authorized client by:

```java
loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
)
```

Meaning the logical key is normally:

```text
(registrationId, principalName)
```

With local principal U:

```text
("google", "U") -> Google token for U
("workforce", "U") -> Workforce token for U
```

This works **if each registration attaches at most one external identity** to U.

### 18.1. What if one internal account links two Google identities?

```text
U -> Google G1
U -> Google G2

Both use registrationId = google
PrincipalName = U
```

The default service keyed by `(google,U)` **cannot simultaneously represent two authorized clients** under the same key.

Options:

1. **Limit to one external identity per registration/provider** by business policy.
2. Separate registrations if distinct managed OAuth client configurations exist.
3. Design a custom authorized client store keyed by external identity ID if multiple accounts on the same provider must be supported.
4. Make the UI explicit about which identity is used when calling provider APIs and avoid token overwrites.

Never use `(registrationId, internalUserId)` casually if the product genuinely supports multiple identities on the same provider.

### 18.2. Identity linking differs from granting API access

Linking Google for **sign-in** may only request basic OIDC scopes:

```text
openid profile email
```

If reading the Google Drive API is desired later, separate API permissions and consent are needed. Never assume a linked identity carries an access token with scopes for all Google services.

### 18.3. Authorized client principal keys can drift with custom mapping

In default OAuth2 Login, the authorized client may be stored under the principal name from the external identity.

If authentication later uses a local account ID, a service querying by the local ID might **miss tokens saved under the external subject**.

Establish a consistent convention across:

- `OAuth2AuthenticationToken` principal.
- User service/success handler.
- `OAuth2AuthorizedClientRepository`/`Service`.
- Backend API clients and token refresh.
- Session/tenant mappings.

Never patch around mismatches by copying refresh tokens uncontrollably across stores or setting a global "current authorized client."

---

## 19. Logging In with a Linked Identity: Safe Algorithm

Pseudocode:

```text
onOidcLoginSuccess(validatedOidcPrincipal, registrationId):
    key = identityKey(
        iss = validatedOidcPrincipal.idToken.issuer,
        sub = validatedOidcPrincipal.idToken.subject
    )

    identity = identityRepository.findByKey(key)

    if identity == null:
        return beginExplicitOnboardingOrLinkFlow()

    account = accountRepository.findById(identity.accountId)

    if account == null or account.disabled:
        rejectLogin()

    if tenantPolicyRejectsIdentity(account, registrationId, key):
        rejectLogin()

    localAuthorities = authorizationService.loadAuthorities(account)

    authentication = createTrustedLocalAuthentication(
        internalUserId = account.id,
        linkedIdentity = key,
        authorities = localAuthorities
    )

    persistAuthenticationAndAuthorizedClientConsistently()
    issueSession()
```

### 19.1. Do not auto-create duplicate accounts on each login

If a provider previously issued `sub=123` for user U and their email changes, looking up `(iss,sub)` must still find U.

### 19.2. Do not auto-merge accounts by email

If the external identity has no mapping yet:

```text
Email same -> do not auto-join
```

You can show UX like:

> "Already have an account? Sign in with your existing method and choose Link Account."

Avoid publicly revealing details of existing accounts from an email alone if user enumeration is a risk.

### 19.3. New signups also need policy

If auto-creating an internal account is allowed when an identity is unlinked, distinguish:

- Is the provider issuer accepted?
- Is email domain an onboarding condition or display-only?
- Is an invitation/tenant membership required?
- Does the provider account belong to a trusted organization/enterprise instance?
- Is a verified email or other claims required by business policy?

Even when auto-signup is enabled, **never attach the identity to an existing account U just because of a matching email**.

---

## 20. Linking a Provider When a Session Might Be Hijacked

An attacker who steals a BFF session cookie might attempt:

```text
Alice's Session -> Settings -> Link attacker's OAuth2 identity
```

Without step-up, the attacker creates a persistent login method for Alice. Later, even after the old session expires, the attacker can still log in via their own identity.

### 20.1. Recent authentication/step-up

Sensitive actions should enforce a policy such as:

```text
last_strong_auth_at <= N minutes
```

or require:

- Password/passkey verification.
- Policy-compliant MFA.
- OIDC reauthentication with `max_age`/`acr`.
- Trusted device/transaction confirmation.
- Administrator approval in enterprise contexts if required.

`N` is not a universal constant; choose it based on your threat model.

### 20.2. Do not treat session age as authentication freshness

A session whose idle timeout was recently refreshed does not prove the user recently authenticated with MFA.

Reliable last-authentication or assurance info is required. In OIDC, `auth_time` and `acr`/`amr` carry semantics governed by the issuer and negotiated requirements.

### 20.3. Post-link notifications

Send a notification via the registered account channel or audit UI:

```text
A new sign-in method was linked:
Provider: Workforce OIDC
Time: ...
```

Notifications **do not replace verifying the link**, yet help detect account compromise.

Avoid sending raw subjects, access tokens, or sensitive provider attributes in notifications.

---

## 21. Unlinking: Removing a Link Without Locking Users Out of Their Accounts

When a user wants to remove a provider:

```http
DELETE /api/account/links/{identityId}
Cookie: SESSION=...
X-CSRF-TOKEN: ...
```

The backend must:

1. Verify the user manages account U.
2. Require recent authentication/step-up if dictated by policy.
3. Ensure `identityId` actually belongs to U.
4. Disallow removing **the last login method** unless a valid recovery method exists.
5. Transactionally unlink or mark inactive.
6. Remove/revoke the corresponding identity's authorized client per policy.
7. Invalidate sessions or require reauthentication if the security change is significant.
8. Record audit logs and send notifications.

### 21.1. Do not simply delete the row and stop

There may still be:

- `OAuth2AuthorizedClient` in Redis/JDBC.
- Unrevoked refresh tokens at the provider.
- Sessions on other devices.
- Background jobs calling provider APIs.
- Scheduled sync integrations.
- Cached local authorities.
- Associated recovery methods.

Identity unlinking and **OAuth2 authorization revocation** are distinct actions, yet often need coordination.

### 21.2. Last login method and recovery

Suppose U has:

```text
Google identity G
Workforce identity C
Password login disabled
```

G can be unlinked if C still works. However, if Workforce access is revoked when an employee leaves, an independent policy-compliant recovery strategy is needed.

Never promise email-only recovery if the email identity is not a trustworthy proof of ownership.

### 21.3. Transferring an identity from account U to V

Never silently execute:

```sql
UPDATE external_identity
SET account_id = :new_account_id
WHERE namespace = ... AND subject = ...;
```

because this **transfers login capability**. If the business truly supports transfer/merge, enforce proof-of-control for both accounts, step-up, auditing, rollback/notifications, and data/tenant boundary handling.

---

## 22. Account Recovery and Account Merge Are Not Account Linking

### 22.1. Linking

An authenticated account U adds an external identity G **not yet belonging to any other account**.

### 22.2. Recovery

A user loses access to all login methods and must prove ownership of account U using registered recovery factors.

### 22.3. Merge

Two internal accounts U and V each hold distinct data/authorizations and must be consolidated.

**Merging is far more complex than linking**:

- Order ownership, billing, sensitive data.
- Memberships and tenant roles.
- Linked identities and active sessions.
- OAuth2 authorized clients and refresh tokens.
- Audit trails, legal obligations.
- Conflicting resource IDs, data retention.
- User consent and reversibility.

Never auto-merge due to matching emails.

### 22.4. If the identity is already linked to account V

The message shown to user U should avoid leaking specific details:

```text
This identity cannot be linked right now.
Please use the support or account recovery process.
```

Backoffice logs can record reason code `IDENTITY_ALREADY_LINKED` and audit details, without disclosing account V's email/name to an unauthorized user U.

---

## 23. Multi-Tenancy and Multi-Organization

In SaaS, one external identity may be used to access multiple organizations. There are at least two architectures:

**Architecture A: global person account**

```text
External Identity G -> Global Internal User U
U -> Membership tenant-a (role Member)
U -> Membership tenant-b (role Admin)
```

**Architecture B: tenant-scoped account**

```text
External Identity G -> Local User UA in tenant-a
External Identity G -> Local User UB in tenant-b
```

Architecture B may intentionally allow one identity to map to multiple user records **in different tenants**. In that case, the unique key must accurately reflect policy—such as `(tenant_id, namespace, subject)` rather than global uniqueness.

### 23.1. Choose the policy before choosing the unique constraint

If a global identity may link to at most one global account, `UNIQUE(namespace,subject)` makes sense.

If the same external identity is allowed across multiple tenant-local accounts, enforce tenant-aware constraints and clear business logic. Never drop uniqueness altogether and leave accounts vulnerable to uncontrolled duplicate linking.

### 23.2. Tenant from URL is not automatically a trusted tenant

A request:

```text
POST /tenants/tenant-b/link
```

does not prove the principal has permission to manage an account in tenant B.

Verify membership, roles, and identity provider restrictions. The `tenant_id` stored in a pending link intent must come from a trusted server-side authorization context.

### 23.3. Enterprise OIDC and home tenant

An OIDC provider may issue a tenant-specific issuer or claims such as a tenant ID. Follow the provider's issuer/tenant validation contract rather than merely inspecting the user's email domain.

If tenant policy requires managed corporate identities, linking a consumer identity with the same email does not satisfy the requirement.

---

## 24. Preventing Mis-Linking Across Multiple Tabs and Devices

A browser may have two tabs open:

```text
Tab A: linking Google
Tab B: linking Workforce
```

If the app stores a single session variable:

```text
pending_registration = google
```

and Tab B overwrites it with `workforce`, Tab A's callback may bind to the wrong business intent.

### 24.1. Key pending records by authorization transaction

Recommended:

- Generate a random pending link ID.
- Bind to the expected internal account U.
- Bind to the exact OAuth2 `state`/authorization request.
- Bind to registration ID with a short TTL.
- Single-use / consume atomically.
- Define policy when sessions change, log out, or switch logins.
- Prevent a pending record from an old tab from automatically linking an identity to a new account.

### 24.2. Multi-device

If a user starts linking on a laptop and finishes authenticating on a phone, the OAuth2 callback normally returns to the laptop's browser session. If a product offers a cross-device linking flow, enforce dedicated transaction proof and anti-session-swapping controls.

Never treat an OAuth2 `code` passed via chat/QR as sufficient on its own to attach to another account.

### 24.3. Provider account chooser

Users may be signed into multiple Google accounts. UX should help them confirm **which provider account** will be linked, such as displaying email/avatar after verifying identity.

However, database persistence must still rely on the **stable subject key**, not on the email shown on the confirmation screen.

---

## 25. Race Between Unlink and Login/Link

One request may delete link `G -> U` while an OAuth callback request for G is being processed.

Example:

```text
Thread A: Logs in with G, reads G->U
Thread B: User unlinks G, deletes mapping
Thread A: Creates session for U from stale snapshot
```

If policy requires unlinking to take effect immediately, consider synchronization mechanisms:

- Versioning/state on the external identity.
- Session revocation or short-lived authentication caches.
- Transaction boundaries.
- Re-checking link status before committing authentication.
- Conditional writes with tombstones for late-arriving callbacks.
- Auditing and eventual consistency guarantees.

Avoid checking the link once and caching it indefinitely in a global cache.

### 25.1. Tombstones

Instead of deleting the row immediately, you can retain:

```text
identity_state = ACTIVE / UNLINKED
version = 12
```

so an old callback cannot accidentally recreate `G -> U` right after U unlinked it. This is a custom application model, not a built-in Spring Security field.

### 25.2. Re-linking must re-prove external identity

If G was unlinked yesterday and the user wants to link it again today, do not rely on an old snapshot `id` or browser-supplied email. Execute the full provider flow and pending intent again.

---

## 26. `SecurityContext` and OAuth2 Token Storage After Linking

Suppose Alice has:

```text
Local account: U
Google identity: G
Workforce identity: C
```

After Google login:

```text
Authentication local principal = U
Authorized client for registration google = Token_G
```

After Workforce login:

```text
Authentication local principal = U
Authorized client for registration workforce = Token_C
```

### 26.1. Never return `OAuth2AuthorizedClient` to the frontend

An `OAuth2AuthorizedClient` object can contain `accessToken` and `refreshToken`. It is not a DTO for `/api/account/links`.

The response should be:

```json
{
  "connections": [
    {
      "id": "opaque-link-id-1",
      "provider": "Google",
      "displayName": "alice@example.com",
      "linkedAt": "2026-10-01T12:00:00Z"
    },
    {
      "id": "opaque-link-id-2",
      "provider": "Workforce",
      "displayName": "Alice (Corporate)",
      "linkedAt": "2026-10-10T07:00:00Z"
    }
  ]
}
```

Do not return raw `iss+sub` unnecessarily, especially for identifiers that could correlate users across services.

### 26.2. Login identity does not equal API access

A user can **link a Google identity** for login without granting scopes to read Google Calendar.

If the app needs the Calendar API, a separate OAuth2 authorization with proper consent, scopes, and token persistence is required. Never expand permissions silently during linking.

### 26.3. Token revocation and unlinking

When a user unlinks a provider:

- Remove/invalidate the mapping used for login.
- If API tokens are no longer needed, remove the authorized client and call the revocation endpoint if supported/required by the AS contract.
- Across multiple sessions, it may be necessary to invalidate sessions authenticated via that identity.
- Do not assume provider logout revokes all tokens.
- Refresh token rotation and concurrent jobs need a consistent policy.

---

## 27. Backend-Browser Boundary in the Link Flow

In a BFF/server-side OAuth2 Login model:

```text
Browser:
    Session cookie + OAuth authorization redirect
Backend:
    OAuth2 client credentials, access token, refresh token
```

The link flow must never expose raw provider tokens in:

```text
localStorage
sessionStorage
window.__TOKEN__
HTML inline scripts
frontend JSON responses
URL query or fragment
browser-readable cookies
```

The authorization code appears in the callback URL per protocol, yet the backend must exchange it over the back-channel and never return the token response to JavaScript.

### 27.1. Session cookies remain credentials

`HttpOnly`, `Secure`, `SameSite`, and session fixation protection protect the session. `SameSite` does not replace CSRF tokens. Linking logins returning from cross-site IdP redirects requires cookie policies compatible with callback GET/form POST.

### 27.2. XSS can trigger the link flow

Even with an `HttpOnly` session cookie, same-origin XSS can submit POSTs and read CSRF tokens depending on frontend design. Step-up and reauthentication before linking limit the blast radius of a compromised session or script, though they do not replace CSP/output encoding.

### 27.3. Never expose tokens in logs

Never log raw:

```text
Authorization: Bearer ...
access_token
refresh_token
id_token
code_verifier
client_secret
authorization_code
session_cookie
```

You can audit:

```text
event=EXTERNAL_IDENTITY_LINKED
internalAccountRef=<pseudonymized>
provider=google
externalIdentityRef=<opaque link ID>
result=success
requestId=...
```

---

## 28. Login Flow After Linking: Avoiding Provider Confusion

For example, Alice links Google and Workforce and then logs in via Workforce:

```text
Workforce callback:
    iss = https://login.corporate.example
    sub = corporate-991

Identity map:
    (workforce issuer, corporate-991) -> U

Authentication:
    localUserId U
    currentAuthenticationProvider workforce
    businessAuthorities from trusted local policy
```

A mapping step should verify:

- Account U is still active.
- Provider/issuer is permitted in the tenant.
- Identity link is still active.
- Sign-in risk/step-up policy applies.
- If the Workforce source is disabled or group membership changes, local policy is re-evaluated.
- Never elevate privileges simply because another identity linked to U holds an `admin` claim.

### 28.1. Same internal account, different session provenance

The application can record:

```text
session 1:
    authenticated_via = google
    assurance = low

session 2:
    authenticated_via = workforce
    assurance = high
```

Sensitive actions can require a specific authentication provider or assurance level. Linking multiple identities does not mean **every login method carries equal trust**.

### 28.2. Do not arbitrarily combine claims from older logins

For example, `employee=true` from Workforce while Alice currently logs in via a personal Google account. Policy may require recent Workforce authentication before accessing HR data.

Never retain `employee=true` indefinitely merely because local account U once linked a Workforce identity.

---

## 29. Administration, Deprovisioning, and SCIM/JIT Onboarding

In enterprise setups, internal accounts can be created by:

- JIT provisioning after login from a trusted provider.
- Invitation flows.
- SCIM provisioning.
- Admin consoles.
- HR/account directory sync.

Linking a new external identity **is not** a way to bypass provisioning.

### 29.1. Disabled IdP accounts

If corporate identity C is disabled at the IdP:

- Subsequent logins via C should fail.
- Existing sessions may remain alive until expiration/revocation without back-channel deprovisioning integration.
- Internal account U might still have Google login; whether Google remains usable after an employee leaves is a **business policy**.

If the internal account itself is disabled due to deprovisioning, all linked identity logins to U must be rejected.

### 29.2. Switching tenants

Never automatically move external identity C from tenant A to tenant B just because the user selected a tenant in the UI. Authorization, policy, and usually explicit migration/approval are required.

### 29.3. A verified domain is not sufficient on its own

A provider returning an email with a corporate domain does not prove the organization authorized the user for a specific tenant. You may need to check organization membership, tenant claims, invitations, or managed account policies.

---

## 30. Testing Linking: Happy Path Is Not Enough

### 30.1. Service-level tests

| Test | Expectation |
|---|---|
| Link unowned G to authenticated U | Creates `G -> U` |
| Re-link `G -> U` with valid proof | Idempotent per policy |
| Link G (already owned by V) to U | Rejected, no transfer |
| Two threads link G to U/V | Unique constraint allows only one |
| Disabled account U | Link not created |
| Tenant policy forbids provider | Link not created |
| Missing external identity proof | Link not created |
| Provider email matches U, different subject | No auto-link |
| Provider email changes, subject stays same | Still logs into U |
| Different OIDC `iss`, same `sub` | Not treated as same identity |
| Missing email claim | Can still match stable identity per policy |
| Stale callback for UNLINKED identity | Does not reactivate without new flow |
| Unlink last login method | Rejected or triggers proper recovery flow |
| Logout after link | Session/token behavior matches policy |

### 30.2. OAuth2/OIDC protocol tests

Test:

- Wrong or replayed `state`.
- Reused Authorization Code.
- Wrong PKCE verifier.
- Wrong OIDC ID Token issuer/audience/expiry.
- Mismatched `nonce` where applicable.
- Provider registration differing from expected pending link.
- Callback lacking pending intent entering the link branch.
- Expired or already-consumed pending intent.
- Two tabs starting links to different providers simultaneously.
- U's session logging out or switching users mid-redirect.
- IdP mix-up or dynamic issuer outside the allowlist.

**Never bypass Spring Security protocol validations** in tests. When using mock OAuth2 Login, understand that mocks may bypass real network/token validation.

### 30.3. MockMvc and Spring Security Test

Spring Security Test provides post-processors:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Conceptual test example:

```java
mockMvc.perform(
        post("/api/account/links/start")
            .with(oidcLogin())
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"registrationId\":\"google\"}")
    )
    .andExpect(status().is2xxSuccessful());
```

This is an illustrative JUnit/MockMvc snippet requiring full MVC security, account session mapping, mocks, and imports.

`oidcLogin()` simulates an already-authenticated user; it **does not prove full OIDC redirect/token exchange/nonce verification**. For account linking, write integration/contract tests covering the callback and pending intent.

### 30.4. Testing CSRF

A `POST /api/account/links/start` with a valid session yet **no CSRF token** must be rejected per Servlet Spring Security CSRF policy.

Never put `.with(csrf())` in every test and forget that the real frontend must send the CSRF header/token.

### 30.5. Testing uniqueness under concurrency

You can use a `CountDownLatch` so two workers attempt to link `G -> U` and `G -> V` concurrently.

The test must verify:

```text
COUNT(external_identity WHERE namespace=N AND subject=S) = 1
```

and the final link points to **one** account. Do not merely assert "one Java thread saw `exists=true`"; the DB unique constraint is what enforces safety under races.

### 30.6. Testing OAuth2 authorized client permissions

If U has Google and Workforce identities:

- Google tokens must never be sent to Workforce APIs.
- Bob's tokens must never be usable by U.
- Linking/unlinking must not accidentally alter the `principalName` storage key of other authorized clients.
- When an identity is unlinked, API access tokens are removed/revoked per policy.
- If the same registration has multiple identities, the custom store selects the right external identity.

---

## 31. Common Implementation Mistakes

### Mistake 1 — Using email to auto-link

```text
if (externalEmail == internalEmail) {
    link();
}
```

**Consequence:** account takeover risk from changed/recycled emails or weak provider assurance.

**Right approach:** explicit linking flow with proof-of-control over both the internal account and external identity.

### Mistake 2 — Storing only `sub`

Two issuers can share the same `sub`. Use `(iss,sub)` after OIDC validation or provider namespace + stable ID for OAuth2.

### Mistake 3 — Using `registrationId` as issuer

`registrationId` is an application config alias, not an issuer/trust namespace.

### Mistake 4 — Treating `email_verified` as ownership of an internal account

`email_verified` is only a claim per the provider's semantics. It does not authorize changing account mappings.

### Mistake 5 — Linking immediately upon OAuth2 callback success

The callback proves external identity, but does not prove the user is authorized to link to a specific internal account without a server-side pending intent.

### Mistake 6 — Success handler reading current `Authentication` as account U

After callback, the current `Authentication` may already be the new external user. Retrieve U from the protected pending intent.

### Mistake 7 — Skipping CSRF for link/unlink APIs

`state` does not replace CSRF tokens for application settings.

### Mistake 8 — Lacking a DB unique constraint

Two concurrent callbacks can attach the same identity to two accounts.

### Mistake 9 — Automatically reassigning external identity on conflict

Never run `UPDATE account_id` at a caller's whim. That transfers login access and requires a separate recovery/transfer workflow.

### Mistake 10 — Blocking an identity in the DB without invalidating sessions

Users can keep using sessions created before unlink/deprovision. Define a session revocation policy.

### Mistake 11 — Treating identity linking as granting OAuth2 scopes

Linking for login does not mean the provider granted Calendar/Drive/Graph API permissions.

### Mistake 12 — Assuming the authorized client store supports multiple identities per registration

The default `(registrationId,principalName)` key has limits; enforce a business limit or custom storage if multiple identity tokens exist for one provider.

### Mistake 13 — Storing raw ID Tokens/refresh tokens in the identity mapping table

Not needed for user identification; increases leak, retention, and privilege risks.

### Mistake 14 — Letting users pick arbitrary issuer URLs

Dynamic provider discovery without an allowlist creates mix-up/SSRF and token leakage risks.

### Mistake 15 — Caching local users by email indefinitely

Email is not a stable key; email changes or deprovisioning can break mappings.

### Mistake 16 — Unlinking the last login method without recovery

Users can permanently lock themselves out. Require another verified login/recovery method.

### Mistake 17 — Inheriting the highest role from all linked providers

Linking identities must not allow arbitrary privilege escalation. Roles must be governed by application/trusted provider policies with freshness/tenant controls.

### Mistake 18 — Logging in via a weak provider and using permissions requiring a strong provider's MFA

Authentication assurance/provenance and step-up checks may be required based on resource sensitivity.

---

## 32. Symptom-Based Troubleshooting

| Symptom | Possible cause | How to isolate |
|---|---|---|
| Google login creates a new account despite prior link | Different issuer/sub key or mapping not persisted | Compare validated issuer + stable subject, DB transaction |
| Workforce login enters another account | Auto-link by email or wrong registration alias | Check lookup and account ownership |
| Link callback returns `invalid_state` | Lost session/pending OAuth2 request or wrong callback | Check state repo, `SameSite` cookies, multi-tabs |
| Link succeeds yet browser switches to external user | Success handler replaced local `Authentication` | Separate login/link and restore local session U |
| Provider email missing | Scope/claim policy or provider omits it | Rely on stable subject; don't require email if policy allows |
| User changes email and cannot log in | Using email as identity key | Migrate mapping to `(iss,sub)` |
| DB unique collision | Identity already linked or concurrent link | Roll back; map conflict safely without reassigning |
| Link disappears after restart | Stored only in session/in-memory map | Use persistent identity DB |
| API tokens lost after custom `getName` | Authorized client principal key changed | Align user mapping and service keys |
| Same Google registration overwrites tokens | Two linked identities on one key | Enforce one-per-registration policy or custom store |
| API still callable after unlink | Refresh token/session still alive | Remove/revoke tokens, invalidate sessions per policy |
| User keeps admin role after deprovision | Cached authorities or wrong policy | Revalidate account status/roles/tenant |
| Corporate identity shares email with personal identity | Two different providers/trust levels | Never auto-merge; use explicit linking |
| Login callback fails CSRF or loses session | Incompatible cookie flags/response mode | Check GET redirect/form POST and state repository |
| Fails only when two tabs are open | Pending link intent overwritten | Bind intent to OAuth state/transaction |
| Account hijacked after new link | Missing step-up, stolen session | Enable step-up/notifications/audit/revocation |
| User cannot unlink last method | Proper recovery protection policy | Provide flow to add a recovery method first |

### 32.1. Do not debug by logging ID Tokens

You can log:

```text
registrationId=workforce
issuerNamespace=<approved provider>
identityRef=<opaque ID>
linkIntentId=<opaque short correlation>
result=LINKED|ALREADY_LINKED|DENIED
```

Never log:

```text
id_token
access_token
refresh_token
client_secret
authorization_code
session_cookie
```

`iss` and `sub` fields can be personal identifiers; limit logging/raw metric labels according to data policies.

---

## 33. Practical Scenarios

### Scenario A — Alice has Google and Workforce with the same email

Both providers return `alice@example.com`.

**Handling:** treat as **two distinct external identities**; Alice must log into internal account U and explicitly link the new identity. After linking, both can log into U.

### Scenario B — Attacker registers a recycled email

A new provider issues an email matching an older account.

**Handling:** never auto-link by email. Use a trusted stable identity key and proof-of-control of the internal account.

### Scenario C — Two issuers issue `sub=123`

**Handling:** the OIDC key must be `(iss,sub)`, not just `sub`.

### Scenario D — Alice links Google in tab A, Workforce in tab B

**Handling:** pending link transactions are bound to OAuth2 `state` and registration; never use a single last-write-wins session variable.

### Scenario E — Success handler receives Google principal, misses local user U

**Handling:** retrieve U from the server-side pending link intent, not from the newly authenticated `OAuth2AuthenticationToken`.

### Scenario F — Google identity already belongs to account V

**Handling:** reject linking into U; never delete or transfer from V. If merge/recovery is truly needed, use a dedicated workflow.

### Scenario G — Alice changes her email at the provider

**Handling:** update display attributes if needed, keeping the link via the stable OIDC subject/provider user ID.

### Scenario H — Alice wants to link two Google accounts

**Handling:** enforce a one-per-registration policy or design custom storage keys for two authorized clients; avoid token overwrites.

### Scenario I — Corporate IdP revokes an employee's identity

**Handling:** future logins via that provider must fail; whether internal account U may continue via Google is governed by business deprovisioning policy.

### Scenario J — Active user deletes their last identity

**Handling:** require adding another recovery/login method before unlinking; never let users lock themselves out unknowingly.

### Scenario K — User has only OIDC Login, no password

**Handling:** step-up can use reauthentication at a trusted IdP/MFA, rather than demanding a nonexistent application password.

### Scenario L — OAuth2 provider has no `sub`

**Handling:** use the stable ID from the trusted provider user endpoint and the namespace of that exact provider instance.

### Scenario M — OAuth2 provider returns `email_verified` with unclear semantics

**Handling:** never use the claim as proof for linking; validate the stable provider ID and provider-specific policy.

### Scenario N — Browser holds access tokens after linking

**Handling:** in a BFF design, tokens stay on the backend; never return `OAuth2AuthorizedClient`/raw tokens to JavaScript.

### Scenario O — Linked identity holds admin rights at another IdP

**Handling:** apply only local business roles permitted by policy/tenant mapping; linking an identity never grants admin automatically.

### Scenario P — Two requests link the same external identity concurrently

**Handling:** DB unique constraint + transaction; one request wins, the other receives a safe conflict error.

### Scenario Q — Normal OAuth2 Login mistaken for linking

**Handling:** callbacks must have a valid pending link intent bound to `state`/session. Otherwise, handle normal login/onboarding separately.

### Scenario R — User unlinks, yet background sync still holds a refresh token

**Handling:** clean up/revoke the authorized client and job access per policy, coordinating with concurrent refreshes.

---

## 34. Self-Check Questions

**1. Can one internal account have multiple external identities?**  
Yes, under a linking data model. However, identities must be verified and attached via explicit policy.

**2. Which identity key should be used for OIDC?**  
The `(validated iss, validated sub)` pair.

**3. Do two providers returning the same `sub` mean the same user?**  
No. `sub` only has meaning within its corresponding issuer namespace.

**4. Should two providers returning the same email be auto-linked?**  
Not by default. Email is not sufficient proof of ownership of an internal account.

**5. Why is `email_verified=true` not enough?**  
It is a claim under the provider's policy, not authorization to attach an external identity to an existing internal account.

**6. Is a successful OAuth2 Login callback enough to permit linking?**  
No. Pending intent, account ownership/step-up, tenant policy, and DB uniqueness are also required.

**7. Why shouldn't the success handler read account U from the current `Authentication`?**  
After the callback, `Authentication` may be the newly logged-in external identity, not the original local account of the linking flow.

**8. Do `state`, PKCE, and CSRF protect the same thing?**  
No. They handle authorization-response correlation, code binding, and state-changing BFF requests respectively.

**9. What is the most important DB constraint for the identity key?**  
Uniqueness on the provider identity key, such as `(namespace,subject)` under a global-account policy.

**10. Is `existsBy...` followed by `save` enough to prevent races?**  
No. Two concurrent transactions can both observe absence; a DB unique constraint and transaction are still required.

**11. Is `ClientRegistration.registrationId` an OIDC issuer?**  
No. Registration ID is a local config alias, not an issuer identity namespace.

**12. What must be done for an OAuth2 provider without an OIDC ID Token?**  
Obtain the stable provider user ID via a trusted OAuth2 user endpoint and explicit namespace.

**13. Does linking an identity automatically grant Google Drive scopes?**  
No. API access requires OAuth2 authorization/consent for that specific resource.

**14. What is `OAuth2AuthorizedClientService` normally keyed by?**  
`(clientRegistrationId,principalName)`.

**15. What happens if one local principal has two Google identities under the same registration?**  
The default authorized client service can only represent one record per key; a business limit or custom storage is needed.

**16. When a provider identity already belongs to account V, what should U do?**  
Reject linking; use a separate recovery/merge workflow if permitted.

**17. Should unlinking the last login method be allowed?**  
Normally it must be blocked or require a verified recovery method beforehand.

**18. Does linking give all authentication methods the same assurance?**  
No. Provider provenance/MFA/`auth_time` can affect permission for sensitive actions.

**19. When internal account U is disabled, can a linked Google identity log into U?**  
No under account-disable policies; all external login mappings must check U's status.

**20. Why audit link/unlink events?**  
They alter login capabilities and carry account takeover risk, requiring traceability and alerting.

---

## 35. Key Glossary

| Concept | Takeaway |
|---|---|
| Internal account | Application's own business account with a stable local ID |
| External identity | Identity authenticated by a provider |
| OIDC identity key | `(iss,sub)` after ID Token validation |
| OAuth2 provider user ID | Stable ID from trusted user endpoint, namespaced per instance |
| `registrationId` | OAuth2 client config alias; not synonymous with issuer |
| Account linking | Attaching a verified identity to an internal account via proof-of-control |
| Account login | Looking up a linked identity to resolve the local account |
| Account merge | Consolidating two internal accounts; much more complex than linking |
| Pending link intent | Server-side transaction binding account U, provider, state, and TTL |
| OAuth2 `state` | Binds authorization request and callback |
| PKCE | Binds authorization code and verifier |
| OIDC `nonce` | Binds ID Token and authentication request |
| Step-up | Proving fresh/stronger authentication before sensitive changes |
| Unique constraint | Prevents an identity key from linking to two accounts against policy |
| Transaction | Commits linking atomically, rolling back on conflict |
| `OidcUserService` | Loads/builds OIDC principal, customizable for mapping |
| `DefaultOAuth2UserService` | Handles OAuth2 UserInfo for non-OIDC providers |
| `OAuth2AuthenticationToken` | `Authentication` produced by OAuth2/OIDC login |
| Local principal | Application principal carrying a stable internal user ID |
| `OAuth2AuthorizedClient` | Access/refresh tokens for a registration/principal |
| Identity unlink | Removing a login method; must handle sessions/tokens/recovery |
| Identity provenance | Provider, issuer, and authentication assurance of a login |
| Tenant isolation | Preventing unauthorized cross-namespace linking or login |
| JIT onboarding | Creating an account when a new identity authenticates per policy |
| Deprovision | Disabling accounts/permissions per organization lifecycle |
| Audit | Recording link/unlink changes with minimal metadata |

### Conclusion

In a **Spring Security OAuth 2.0/OIDC Client system integrating multiple providers**, the goal of account linking is to let **multiple verified external identities** resolve to **one stable internal account**. This gives users multiple ways to sign in while keeping business data and permissions consistent.

However, connecting two identities **modifies account access capabilities**, not just email matching. A secure architecture must:

1. Use **`(iss,sub)`** for OIDC or provider namespace + stable user ID for non-OIDC OAuth2.
2. Distinguish **normal login** from an **explicit linking flow**.
3. Prove the user controls both account U and external identity G, with appropriate `state`, PKCE, nonce, CSRF, and step-up.
4. Bind the linking transaction to a **server-side pending intent** so callbacks never confuse accounts.
5. Use unique constraints and transactions to prevent duplicate/conflicting mappings.
6. Separate identity mapping from OAuth2 token storage while keeping principal/registration keys consistent.
7. Handle unlinking, logout, revocation, account recovery, deprovisioning, and tenant policies across the full lifecycle.
8. Never self-elevate privileges, never auto-merge by email, and never expose raw OAuth2 tokens.

**The right design has multiple authentication methods leading to one internal account—not arbitrary claim sources able to hijack that account.**

## References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — issuer, subject, ID Token, nonce, `auth_time`, pairwise subject.
- [Spring Security — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) — login, authorized principals, and customization.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html) — user service, authorization request resolver, success/failure handlers.
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html) — client registration, authorized clients, managers/repositories.
- [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html) — OIDC principal loading.
- [Spring Security API — DefaultOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html) — OAuth2 UserInfo support.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — protecting state-changing endpoints.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — session fixation, authentication lifecycle.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749) — OAuth2 authentication/authorization grants.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — Authorization Code protection.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 security considerations, CSRF, issuer/redirect and token protections.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) — authentication/re-authentication controls.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — session security controls.
