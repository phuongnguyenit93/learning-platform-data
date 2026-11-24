# Linking Multiple External Identities to One Application Account

**Module:** Spring Security – federation → Directories and Accounts.

**Objective:** build a model where **one application account can sign in with multiple external identities** (Google/Entra ID/Keycloak or other OIDC IdPs, SAML2 IdPs, CAS/enterprise directories) without creating duplicate accounts, without email-collision takeovers, without mixing up issuers/tenants, and with safe linking, unlinking, identity-provider migration, and privilege revocation. The content focuses on **trustworthy identity keys, account-linking workflows, database design, Spring Security, concurrent transactions, sessions/CSRF, and testing**.

**Bottom line up front:** **Never automatically merge two identities just because they share the same email or username.** With OIDC, the durable link identifier must be based on the **`(issuer, subject) = (iss, sub)` pair after the ID Token has been verified**. One person may hold two different `(iss, sub)` pairs; connect them to the **same internal account ID** only after a workflow proving control of the existing application account **and** the external identity being added. Email is a profile attribute; `email_verified=true` is **not** proof that two IdPs describe the same human being.

This lesson targets Java 17+ and Spring Security Servlet/OIDC login. All `example.com` URLs and IdP names are illustrative. Spring code is configuration snippets; the pure Java 17 code in the hands-on section runs standalone.

## 1. Real-World Problem: One Account, Many Ways to Sign In

An internal platform holds employee profiles and work data:

- **Application:** `https://work.example.com`.
- **Application account:** `user_id=U-100`, with profile, preferences, document history, memberships, and permissions stored in the application database.
- **IdP A:** OIDC issuer `https://login.corp.example/oidc`, `sub=emp-194` (employee login).
- **IdP B:** OIDC issuer `https://login.partner.example/oidc`, `sub=account-903` (partner login).
- **IdP C:** SAML2 issuer `https://sso.legacy.example/idp` with an approved persistent NameID.

One individual is authorized to control U-100 and wants to sign in via A or B. The application should still see **one U-100**, preserving business records, rather than creating `U-101` and losing history.

```text
              +--------------------------------+
              | Application account U-100      |
              | name, settings, document ACLs  |
              | tenant memberships, lifecycle  |
              +----------------+---------------+
                               |
                +--------------+----------------+
                |              |                |
                v              v                v
       External link A   External link B   External link C
       OIDC iss+sub      OIDC iss+sub      SAML issuer+NameID
                |              |                |
                v              v                v
          Corporate IdP   Partner IdP       Legacy IdP
```

**Entity separation:**
1. **Application account (`app_user_id`):** owned by the application, stable across IdP changes, owner of profiles and data.
2. **External identity (`issuer + subject`):** issued by the IdP; a *method of proving login*, not a business account itself.
3. **Authentication event/session:** the IdP just authenticated the user via OIDC/SAML/CAS; carries its own assurance context, timestamp, and session.
4. **Authorization/membership:** permissions for tenants, departments, reports, or data; requires independent authorities, never inferred merely from successful login.

**Account linking is not the same as data merging:** linking allows multiple credentials/IdPs into **one app account**; *merging* U-100/U-101 is a separate, higher-risk business operation transferring ownership, invoices, permissions, and audits. Never perform silent data merges during login or on matching emails.

## 2. External Identifiers Must Be Namespaced

### 2.1. OIDC: `iss` and `sub` form the identity pair

OpenID Connect Core `5.7` states that `iss` and `sub` combined form the identifier you can rely on to distinguish end-users. For example:

| Verified Issuer | Subject | Display Email | Conclusion |
| --- | --- | --- | --- |
| `https://idp-a.example/oidc` | `42` | `an@example.com` | Identity A |
| `https://idp-b.example/oidc` | `42` | `an@example.com` | **Identity B, distinct from A** |
| `https://idp-a.example/oidc` | `43` | `an@example.com` | **Different identity at A**, despite matching email |
| `https://idp-a.example/oidc` | `42` | `an-new@example.com` | **Same identity A** if `iss+sub` is unchanged |

OIDC `sub` is stable **within the issuer's namespace**, not globally unique across the Internet. `sub` and issuer URLs must be compared with exact casing and semantics defined by the provider; never lowercase `sub` or alter the issuer path. One issuer may issue different **pairwise `sub`** values per sector/client: the same user logging into two RPs may receive two different subjects. If client registration/sector changes, **do not auto-connect via email**; use an approved migration/account-linking workflow.

```json
{
  "iss": "https://idp-a.example/oidc",
  "sub": "employee-194",
  "aud": "work-app-client",
  "exp": 2000000000,
  "iat": 1999999700,
  "email": "an@example.com",
  "email_verified": true
}
```

This is an **illustrative ID Token payload**, not a signed JWT. The application only reads `iss`/`sub` **after** Spring Security/the OIDC client has verified the token for the expected issuer/client ID, signature, and nonce/state/timestamps. `email_verified=true` is a statement by **that issuer** about the email, not an assertion of cross-provider identity equivalence.

### 2.2. Spring's `registrationId` does not replace the issuer

Spring Security distinguishes:
- `registrationId`: a local configuration key such as `corp` or `partner`.
- `issuer-uri`: the real OIDC token source, used for discovery/signatures and validation.
- `OidcIdToken.getIssuer()` / `OidcIdToken.getSubject()`: identity data **after verification**.

Renaming `registrationId` from `corp` to `enterprise` should not alter durable identity keys. Conversely, two registrations pointing to the **same issuer** may receive different pairwise `sub` values; never assume they belong to the same account just because the provider name looks similar.

### 2.3. SAML2, CAS, LDAP, and Kerberos do not share the same key shape

| Protocol/source | External identifier to consider | Warning |
| --- | --- | --- |
| **OIDC** | `(trusted iss, sub)` | Must verify JWT and subject; pairwise `sub` may vary by client/sector |
| **SAML2** | `(trusted IdP entityID/Issuer, persistent NameID, NameID Format/qualifiers/SP scope as needed)` | Transient NameID generally **must not be used as a long-term key** |
| **CAS** | `(trusted CAS server/service namespace, stable principal ID)` | CAS `cas:user` may be a mutable/recycled username; needs contract or directory ID mapping |
| **LDAP/AD** | `(directory authority, immutable entry identity like objectGUID/entryUUID)` | DN, email, and `sAMAccountName` can change/be reused; AD `objectSID` has its own lifecycle |
| **Kerberos** | `(trusted realm/principal and directory ID mapping)` | Kerberos principal names can change/be reassigned per policy; not automatically an immutable app ID |
| **SCIM** | SCIM resource `id` within the providing authority, or namespaced `externalId` per contract | `externalId` is often client-assigned, **not automatically a trusted global user ID** |

**Every identity key must have an explicit authority namespace.** With multi-forest LDAP, use `objectGUID` **paired with directory ID**, never bare GUID/DN/email. With SAML, include `NameQualifier`/`SPNameQualifier`, Format, and assertion context per policy; only treat `NameID` as stable if the IdP guarantees it and the SP verifies the message properly.

In particular, **a compromised IdP must never be able to claim users of another tenant** merely via name/email/claims. The broker/application must separately govern trusted provider registrations, tenant onboarding, mappings, and authorization.

## 3. Identity Linking Differs from Identity Lookup, Provisioning, and Account Merge

| Operation | Goal | Critical conditions |
| --- | --- | --- |
| **Login with linked external identity** | Resolve U-100 from external key, create session | External auth verified, link active, account/tenant permitted |
| **Link identity B to U-100** | Add a second sign-in method | Active strong U-100 session + fresh B auth + session-bound linking intent |
| **Unlink identity B** | Remove B's ability to sign into U-100 | Reauthentication, CSRF, do not lock out account without recovery |
| **Just-In-Time (JIT) create** | Create a new app account on first login | Allowed by provisioning/tenant policy; never auto-merge old accounts by email |
| **SCIM/pre-provision** | Create/update users/attrs from managing authority | Contract and uniqueness; never bypass proof-of-possession for another account |
| **Data account merge** | Merge U-100/U-101 and history | Dedicated business workflow, consent/admin review; never automatic in OAuth callback |
| **IdP rebinding/migration** | Replace old external identity with new one | Proof/migration mapping, session handling, audit, rollback; not just matching email |

What many products call "sign in with Google/Microsoft" is **federated authentication**; it **does not by itself prove the user is the same person** as an existing app account. Linking is a sensitive account-management action, akin to adding a new authenticator. NIST SP 800-63C-4 section `3.8.1` requires linking functions to rely on an authenticated session of the app account and to notify when a linked identifier is added or removed.

## 4. Normal Login Flow Using a Linked Identity

Assume the DB already contains:
- External `(issuer A, sub emp-194) → U-100`.
- External `(issuer B, sub account-903) → U-100`.

```mermaid
sequenceDiagram
    actor User as User
    participant App as Spring App / RP
    participant IdP as OIDC IdP B
    participant Links as Identity Link Store
    User->>App: GET /private
    App-->>User: Redirect /oauth2/authorization/partner
    User->>IdP: Authorization Code + PKCE / login
    IdP-->>User: Authorization code returned to app callback
    User->>App: code + state
    App->>IdP: Redeem code at token endpoint B
    IdP-->>App: Signed ID Token
    App->>App: Verify iss/aud/signature/nonce/exp/state
    App->>Links: Lookup (trusted issuer B, sub account-903)
    Links-->>App: app_user_id U-100
    App->>App: Check ACTIVE/memberships, create app session U-100
    App-->>User: Allow resource access per permissions
```

**Resolving the application account happens only after verifying the external login.** If IdP B returns a matching username/email with a different `sub`, never call `findByEmail` and sign into U-100. If no mapping exists, transition to first-login/onboarding or a safely initiated "Link identity" flow—never accept implicitly.

### 4.1. What should the identity key store?

A minimal link record contains:
- `app_user_id` – internal UUID/ID, foreign key to the account.
- `protocol` and `issuer_or_authority` – OIDC issuer URI, SAML `entityID`, directory authority.
- `subject_type`/`subject_value` – OIDC `sub` or appropriate stable principal/`NameID`.
- `scope/qualifiers` – only when the protocol requires namespace disambiguation.
- `state` – `ACTIVE`/`REVOKED`/`PENDING` per lifecycle.
- `created_at`, `last_verified_at`, `linked_by`, `linked_via`, audit reference.
- Optional `provider_registration_id` for operations, **never used alone as the identity key**.
- Email/display name as **metadata** in a separate profile table; never inside the identity unique constraint.

**There is no need to store raw ID Tokens long-term** to recognize a user once you have issuer/subject; tokens may hold PII and expire. Store only minimal claims/identifiers per privacy policy, and redact tokens and secrets from audits.

## 5. Linking B to U-100 Must Prove Both Sides

### 5.1. Two required proofs

1. **Control of U-100:** the user currently holds an authenticated app session for U-100; sensitive linking may require **reauthentication/MFA/step-up** per policy. An old browser cookie or matching email is **not sufficient** for high-risk linking.
2. **Control of external B:** the app actively initiates a fresh OIDC/SAML authentication with B; receives and verifies the fresh assertion/token, state/nonce/PKCE/request correlation. Never allow the user to type a `sub` or `email` to "attach" B.

Only when both proofs succeed does the app write `(B issuer, B sub) → U-100` in a transaction, enforcing uniqueness and verifying external B is not already bound to another account.

### 5.2. OIDC linking flow

```mermaid
sequenceDiagram
    actor User as User
    participant App as Spring App
    participant Pending as Server-side LinkIntent
    participant IdP as IdP B
    participant DB as Link DB
    User->>App: POST /settings/identities/link/partner (CSRF)
    App->>App: Verify current U-100, fresh auth/MFA
    App->>Pending: Create nonce + one-time intent for U-100/session/provider B
    App-->>User: Redirect to B's OIDC /authorize
    User->>IdP: Authenticate with identity B
    IdP-->>User: Redirect code + state to callback
    User->>App: code + state for link attempt
    App->>App: Verify state/PKCE/nonce/issuer/audience/signature/exp
    App->>Pending: Consume one-time intent, verify session U-100
    App->>DB: Transaction: check (issuer B, sub B) uniqueness
    DB-->>App: Not linked elsewhere; commit B -> U-100
    App->>App: Audit, notify user, rotate/revalidate session if policy
    App-->>User: B linked successfully
```

**A default `OAuth2LoginAuthenticationFilter` may create or replace `Authentication` when the callback returns.** If using it for account linking, never **accidentally switch the principal from U-100 to B** before confirming the original U-100 user. Use a **separate link transaction/handler** or a session-bound broker account-linking API. Store `target_app_user_id` in the server-side intent before redirecting, verify the exact **original authenticated session**, and only link after obtaining the validated OIDC principal from B.

### 5.3. What should a server-side LinkIntent contain?

| Field | Meaning |
| --- | --- |
| Random, unguessable `intent_id` | Dedicated single-use workflow identifier |
| `original_app_user_id` | U-100 of the app session prior to starting |
| `original_session_binding` | Hash/correlation of the current session; never put raw session ID in URL |
| `expected_provider_registration/issuer` | Only B is allowed to complete this intent |
| `state`/`nonce`/PKCE transaction reference | Binds the callback to the authorization request |
| `created_at`/`expires_at` | Short TTL, cleanup |
| `csrf`/`re_auth_evidence` | Proof the request was initiated by the current user and satisfies freshness |
| `status` | `PENDING` → `CONSUMED`/`EXPIRED`/`CANCELLED`, updated atomically |
| `initiating_ip`/device context | Risk-based signal, never sole identity key |

Never let the browser pick the target `app_user_id` via a query parameter like `?linkTo=U-100`. If storing a post-linking return URL, restrict to safe local paths/allowlists to prevent open redirects. IdP B/issuer must come from a preconfigured allowlist; the browser must never supply arbitrary `issuer-uri`/`jwks_uri`/`token_endpoint` values.

### 5.4. Preventing login CSRF, code injection, and mix-up

- `state` must be random, bound to the browser/session, and **single-use**; callbacks with missing/mismatched state must be rejected.
- Use **Authorization Code + PKCE**, exact redirect URIs, and HTTPS.
- OIDC `nonce` where applicable must match the request, alongside token signature/issuer/audience/exp checks.
- When an app is an OAuth client of **multiple authorization servers**, bind the expected issuer to the request. RFC 9700 describes **authorization server mix-up**; RFC 9207 issuer identification in authorization responses helps defend against it when supported by the provider.
- Never redeem codes at a token endpoint suggested by callback/query params; use the **registration/issuer saved** when initiating the transaction.
- Do not automatically treat an **IdP-initiated / unsolicited SAML assertion** as a linking action because it lacks initiation/binding to the authenticated app user; if business requires it, implement a protocol-specific secure proof flow.
- Block session swapping: if someone starts linking while logged in as U-100 but the callback arrives after the browser switched to U-999 → reject, never attach B to the wrong account.

## 6. What Is NOT Sufficient Proof for Linking?

| Signal | What value does it have? | Enough to link? |
| --- | --- | --- |
| Matching `email` | UI/onboarding hint or contact info | **No** |
| `email_verified=true` at both A and B | Each IdP claims email verification under its own policy | **No** |
| Matching `preferred_username` | Display/login hint | **No** |
| Same phone number | Profile; can change/be recycled | **No** |
| Same `sub` but different issuer | Colliding string in two namespaces | **No** |
| Same display name/avatar | UI signal | **No** |
| Active U-100 app session | Proves current app account | **Not enough** without authenticating B |
| Valid B ID Token | Proves external B | **Not enough** without permission to attach to U-100 |
| Fresh U-100 session + fresh B login + bound one-time intent | Enough evidence to **evaluate linking**, if policy permits | **Yes, after collision/authorization checks** |
| Admin importing CSV email mappings | Assists migration review | Not automatic; requires specific authority/proof/audit |

**Account takeover scenario:** Alice owns U-100 and once used `alice@company.example`; that email is later reassigned to Bob at IdP B. If the app auto-links when `email_verified=true`, Bob can sign into Alice's U-100 and access historical data. **Current email ownership does not prove historical ownership of an application account.**

Different IdPs enforce non-equivalent email verification policies. Never enable "Trust Email"/automatic email linking in a broker without a threat model; Keycloak First Broker Login supports multiple linking strategies—choose appropriate reauthentication/verification.

## 7. 1:N Database Design and Unique Keys

### 7.1. Suggested PostgreSQL schema

```sql
CREATE TABLE app_accounts (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_identity_links (
    id UUID PRIMARY KEY,
    app_account_id UUID NOT NULL
        REFERENCES app_accounts(id) ON DELETE CASCADE,
    protocol TEXT NOT NULL,
    issuer_or_authority TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_value TEXT NOT NULL,
    name_qualifier TEXT NOT NULL DEFAULT '',
    sp_name_qualifier TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_verified_at TIMESTAMPTZ,
    UNIQUE (protocol, issuer_or_authority,
            subject_kind, subject_value,
            name_qualifier, sp_name_qualifier)
);

CREATE INDEX idx_links_by_account
    ON external_identity_links(app_account_id);

CREATE TABLE account_tenant_memberships (
    app_account_id UUID NOT NULL
        REFERENCES app_accounts(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (app_account_id, tenant_id, role)
);

CREATE TABLE identity_link_events (
    id UUID PRIMARY KEY,
    app_account_id UUID NOT NULL REFERENCES app_accounts(id),
    action TEXT NOT NULL,
    identity_link_id UUID,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_account_id UUID,
    correlation_id TEXT NOT NULL
);
```

This is an **illustrative design schema**, not a complete migration. You must decide on retention/soft deletes/status history, PII encryption, indexes, audit immutability, customer tenant models, uniqueness for linked/retired identities, and applicable GDPR/data laws. When revoking an identity, a unique constraint on a history-preserving table **prevents key reuse** until a controlled reactivation/relink workflow runs; never delete rows just to bypass uniqueness. You may separate active links and history tables if the lifecycle is complex.

**Strong uniqueness rule:** a verified `(issuer, subject)` must never be simultaneously attached to **two app accounts** within the same trust namespace. If a system has special tenant isolation, explicitly define scoped identity semantics rather than arbitrarily adding `tenant_id` to the unique key to let the same external credential claim multiple accounts across tenants without control.

### 7.2. Separating identity tables from business tables

```text
app_accounts.id = U-100
  |-- document_owners.owner_account_id = U-100
  |-- preferences.account_id = U-100
  |-- memberships.account_id = U-100
  |-- external_identity_links:
          (OIDC, issuer A, sub 194)
          (OIDC, issuer B, sub 903)
          (SAML, issuer C, persistent NameID X)
```

**Never use `external_sub` as the primary key of profiles/invoices/documents**; when an IdP changes or is unlinked, business ownership must remain with U-100. Prefer an immutable internal UUID to avoid forcing users to lose data when changing identity providers.

### 7.3. Normalization and common pitfalls

- **`issuer`:** store the canonical issuer from **trusted configuration** and match token `iss` strictly. Never strip paths, drop `https`, change `www`, or blindly follow discovery redirects just because they look "equivalent".
- **OIDC `sub`:** is a case-sensitive string; never lowercase, trim, or coerce to a number.
- **SAML `NameID`:** identical text can differ by `Format`/`NameQualifier`/`SPNameQualifier` and Issuer. Only use persistent identities per contract; never turn transient IDs into permanent keys.
- **Directory `DN`:** can change on OU move/rename; for a stable external ID, use authority-specific immutable IDs and manage deletion/recreation.
- **`email`:** never place uniqueness on identity links merely because users want email login; profile email uniqueness is a separate concern.
- **`client_id`:** does not replace issuer. With pairwise OIDC `sub`, client/sector context can affect the identifier; manage migrations when changing registrations.
- **`app_account_id`:** use an app-issued UUID; never accept it as unverified input from callbacks.

## 8. Writing Links in a Transaction: Preventing Races and Double-Attaching

When two tabs/requests try to link external B simultaneously:
1. Start a transaction and verify app account U-100 is `ACTIVE`.
2. Confirm the linking intent is **unconsumed** and the current app session/reauth evidence is still valid.
3. Read or `INSERT` the unique identity key, relying on a **database `UNIQUE` constraint** against cross-node races.
4. If the identity key is already bound to U-100, return **already linked** without escalating privileges; depending on policy, this can be treated as idempotent.
5. If already bound to U-999, **never reassign to U-100** just because of email or user request. Return a generic error and open recovery/admin review.
6. If unbound, `INSERT` into `external_identity_links(B→U-100)`.
7. Atomically mark the linking intent `CONSUMED` and commit.
8. Audit/notify via a transactional outbox or reliable mechanism; **never publish "link succeeded" before commit**.

Conceptual pseudo-SQL (not a full migration/transaction):

```sql
BEGIN;
-- Lock current app account to serialize sensitive changes.
SELECT id, status
FROM app_accounts
WHERE id = :current_account_id
FOR UPDATE;

-- Application code has already verified LinkIntent, IdP token, and namespace.
INSERT INTO external_identity_links (
    id, app_account_id, protocol,
    issuer_or_authority, subject_kind, subject_value)
VALUES (
    :link_id, :current_account_id, 'OIDC',
    :trusted_issuer, 'sub', :verified_sub);

-- UNIQUE constraint prevents this link from attaching to another account.
-- Conflicts must be handled intentionally; never "DO UPDATE app_account_id".
COMMIT;
```

**Never use `INSERT ... ON CONFLICT DO UPDATE SET app_account_id = :current_account_id`**: it can silently **transfer an external identity from U-999 to U-100**, creating an account-takeover vector. If using `ON CONFLICT DO NOTHING`, re-read the owner after conflict and distinguish "already linked to U-100" from "already linked to U-999".

**TOCTOU:** application-level `if (!exists) insert` is insufficient because two nodes can both see "not exists". Database uniqueness provides cross-instance protection. The insert and intent consumption must happen in the same transaction (or use full fencing/idempotency in distributed stores).

## 9. Unlinking and Preventing User Lockout

Removing `(issuer B, sub B)` from U-100 is a security operation. Once completed:
- New logins with B **no longer** resolve to U-100.
- Never remove an identity the request does not own (`WHERE app_account_id = currentUserId`).
- Require an authenticated app session, fresh reauthentication/step-up, CSRF protection, and confirmation for the sensitive action.
- When unlinking the last identity while the account has no password/passkey/other IdP/recovery, **enforce an anti-lockout policy**: block unlinking or verify a recovery path first.
- Send notification over a verified channel; investigate events if an unlink was not user-initiated.
- Review **active sessions, refresh tokens, and long-lived authorizations** issued from the removed identity: unlinking does not automatically terminate all existing sessions. Policy may require revoking sessions with provenance from B or all sessions of U-100.
- Removing a link does not delete the business account/data; account deletion is a separate lifecycle.

NIST SP 800-63C-4 specifies that RPs should have a policy when an account has no remaining access/recovery methods; an account with zero federated identifiers must follow the documented account lifecycle rather than leaving ambiguous access behind.

### 9.1. Is "cannot unlink because it is the only login" always true?

Not always: an account that still has a sufficiently strong **passkey/local authenticator/recovery method** still has an access path and may unlink its last external identity. The system should check **actual active and trusted sign-in methods**, not merely count rows in `external_identity_links`. Conversely, having two external identities that both belong to a decommissioned IdP does not guarantee recovery either.

## 10. JIT Provisioning and Controlling Duplicate Accounts

When a new external identity logs in and no link is found:
- **JIT create**: create a **new app account** only when tenant/service policy permits and the user has the required invitation/provisioning proof.
- **Existing-account link**: if the user already has an app account and wants to use a new IdP, they must initiate the **link workflow from the authenticated account** or a verified broker mechanism.
- **Account resolution**: in some enterprise systems, directory/SCIM mappings carry strong enough authority to resolve users; require a trust contract and migration proof—never call email matching authoritative resolution.
- **Deny**: if the user is not onboarded or the IdP is disallowed, return a support message that does not leak "which email already has an account".

**Never create two app accounts U-100/U-101 and auto-"merge" them just because emails match.** If duplicates occur, resolve them through an approved account reconciliation/merge workflow with transactions over business data, authorization checks, and rollback.

### 10.1. Distinguishing email confirmation from external identity proof

An email confirmation link can prove the user **currently receives mail at that address** per the mail system's policy. It does not prove they own an **existing application account** or that the email was never reassigned. Adding IdP B to U-100 requires proving both U-100 and B; if access to U-100 is lost, use a separate **account recovery** flow with stronger evidence, never the shortcut "I know the old email".

## 11. Linking in Multi-Tenant Systems

One person can simultaneously be an employee of A and a partner at B. Both external identities are valid to sign into U-100, yet **permissions across tenants do not automatically merge**.

```text
App user U-100
  external links:
    OIDC corporate A (iss A, sub 194)
    OIDC partner B   (iss B, sub 903)
  memberships:
    tenant CORP    role READER
    tenant PARTNER role EDITOR
  enforcement:
    GET /corp/report  -> check CORP membership + resource
    GET /partner/doc  -> check PARTNER membership + resource
```

Conditions:
1. Linking a B identity does not automatically create `tenant=PARTNER, role=ADMIN`.
2. External `groups` or `roles` are mapped only via an allowlist scoped by **issuer + tenant**, never accepting system-wide "admin".
3. An application may require **step-up** via corporate IdP A for administrative actions, even if the user already holds an app session for U-100 established via B.
4. Distinguish **identity of the person** from **authority of the organization**: being the same person does not mean organizations delegate authority to each other.
5. If IdP B is deprovisioned, review sessions and permissions with provenance B; never retain sensitive privileges just because A remains linked.

**Design fields like `authenticated_via_link_id`/`auth_time` into the app session or audit context** when policies depend on the authentication source. These do not replace `app_user_id`, but help evaluate assurance/step-up and deprovisioning responses.

## 12. SAML2, CAS, and Directories: Special Practical Cases

### 12.1. SAML NameID and qualifiers

A SAML assertion can emit:
- Transient `NameID` for privacy; should not be used as a long-term identity link.
- Persistent `NameID` issued as a stable identifier between IdP/SP, suitable for identity linking if the trust contract permits.
- Email Address `NameID` (not necessarily stable/unique if email changes).

The application must verify the SAML XML Signature of the **exact Response/Assertion**, trusted IdP `entityID`, `AudienceRestriction`, `Recipient`/`Destination`, `InResponseTo`, time conditions, and replay protection. Only after verifying the assertion should you extract `NameID`/qualifiers to look up the link. A SAML Response intended for SP A is not valid for SP B, even when signed by the same IdP.

### 12.2. CAS principal and LDAP backing user

CAS `cas:user=alice` may be a login name rather than an immutable ID. If the directory renames `alice` to `an.nguyen` or reassigns the username to someone else, linking on this text risks misattribution. You need to:
- Identify a directory-backed immutable identity reliably released by CAS (e.g., AD `objectGUID` paired with directory ID).
- Configure CAS service registration to release sufficiently trustworthy/stable attributes.
- Validate the CAS ticket once against the exact `service` before trusting user/attributes.
- Map CAS authority + stable subject to `app_user_id`.
- Handle directory object deletion/recreation or cross-forest migration lifecycles.

### 12.3. LDAP DN, GUID, SID, and SCIM

- **LDAP distinguished name (DN)** can change when a user moves OUs or is renamed; avoid using it as the primary identity link when a stable directory ID is available.
- **AD `objectGUID`** stays with an object, but if deleted and recreated, a new GUID is generated; never auto-map by email.
- **`objectSID`** represents an AD security identity with its own lifecycle/trust/migration semantics; never compare directly across forests.
- **SCIM `id`** is a server-assigned resource ID within the SCIM provider scope; `externalId` may be set by a provisioning client for sync, requiring explicit authority/namespace. Provisioning alone does not prove the browser user controls the account being linked.

## 13. Identity Broker vs. Direct Linking in the Application?

Two common architectures exist:

| Architecture | Where links live | What the app sees | When it fits |
| --- | --- | --- | --- |
| App integrates multiple IdPs directly via `oauth2Login` | App DB holds external links | Tokens from each issuer; app maps to U-100 | Few apps, custom business mapping requirements |
| **Identity broker** like Keycloak/IAM | Broker stores federated links and broker user | App trusts only one broker issuer/sub | Many apps/orgs; centralized federation |
| Directory/SCIM pre-provision + SSO | Directory/IAM manages lifecycle; app maps | Trusted stable user ID and groups from authority | Enterprise provisioning with clear ownership |
| Both app and broker map | Both broker mapping and app mapping | Two identity layers | Requires defining canonical user ID and preventing link divergence |

**A broker must also prove account linking.** A broker may offer First Broker Login, account-linking APIs, and user federation, but enabling "Trust Email"/auto-merge is not safe by default. When the broker issues a **stable broker subject**, downstream apps may only need to map the broker `(iss, sub)` to the app account; do not attempt to extract upstream `sub` from raw claims yourself, as upstream identity sits in a different trust boundary.

A broker may link A/B into the same broker user while the application still maintains its own **business `app_user_id`**. Never confuse the broker user ID with the app data primary key if the app ever needs to migrate brokers/realms.

## 14. Spring Security Integration: Authenticating Two OIDC Providers

### 14.1. Client registrations are only the starting point

Illustrative `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${CORP_OIDC_CLIENT_ID}
            client-secret: ${CORP_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          partner:
            provider: partner
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp:
            issuer-uri: https://login.corp.example/oidc
          partner:
            issuer-uri: https://login.partner.example/oidc

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

This configuration requires **two genuinely registered OIDC clients** with exact redirect URIs, HTTPS, and credentials in a secret manager. `${...}` is a Spring placeholder reading the environment, not a literal secret to hardcode. For local HTTP testing, configure the `Secure` cookie flag per dev profile; **never disable HTTPS in production**.

Standard Spring Security `oauth2Login` provides:
- `GET /oauth2/authorization/corp` and `/partner` to initiate login.
- `/login/oauth2/code/corp` and `/partner` as redirect callbacks.
- OIDC-specific user services when scope includes `openid` and the provider supports OIDC.
- Built-in authorization code state/nonce/token checks per framework behavior, while **app account linking** must be built yourself.

**Two `ClientRegistration` entries do not automatically provide account linking.** The framework verifies external identities; the application needs an `ExternalIdentityLinkRepository`, an app account resolver, a pending-link workflow, and separate authorization.

### 14.2. Minimal Spring SecurityFilterChain

This is a **SecurityFilterChain fragment**, not a full runnable app. A complete app still needs a main class, dependencies, real OIDC issuers, user/tenant repositories, and a linking workflow:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/settings/identities/**")
                    .authenticated()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Never expose the linking endpoint as `GET /link?provider=...&user=...` writing straight to the DB. Link initiation must be a **CSRF-protected POST** requiring fresh app authentication, followed by an OIDC redirect to an allowlisted authorization endpoint. Ensure the framework does not overwrite U-100 on the B login callback while a link is pending.

### 14.3. Extracting the external key after OIDC verification

```java
// EXAMPLE SNIPPET placed after OIDC authentication has been verified.
// Does not run standalone: requires OidcUser and LinkIntent context.
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import java.net.URL;

public record OidcExternalKey(String issuer, String subject) {
    public static OidcExternalKey fromVerified(OidcUser oidcUser) {
        URL issuerUrl = oidcUser.getIdToken().getIssuer();
        String subject = oidcUser.getIdToken().getSubject();
        if (issuerUrl == null || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("Missing OIDC issuer/sub");
        }
        return new OidcExternalKey(issuerUrl.toExternalForm(), subject);
    }
}
```

**Only call `fromVerified` when `OidcUser` comes from an OIDC authentication flow already verified against the expected issuer/client registration.** Never accept an `OidcUser` constructed from unverified browser JSON, never take `iss` from a user-supplied query parameter to select keys, and never fall back to `getEmail()` as a unique identity.

### 14.4. Which components perform the linking in the application?

Depending on design, you can use:
- A custom `AuthenticationSuccessHandler` or `OAuth2UserService<OidcUserRequest,OidcUser>` post-verification to **extract the external key**, map the account, or handle pending intents, **always bound to the original session**.
- An application `IdentityLinkService` handling DB transactions, uniqueness, and auditing.
- A separate link callback flow or broker account-linking API to prevent Spring's default from replacing `Authentication`.
- `SecurityContext` representing **app user U-100** rather than merely an external `sub`, using a custom principal whose mapping has been verified.
- `OidcUserService` to fetch UserInfo when needed; OIDC Core requires UserInfo `sub` to match the ID Token when called. **UserInfo profile data must never replace `iss+sub` from the ID Token as the identity key.**

Warning: an `AuthenticationSuccessHandler` is not a complete solution if it just runs `findByEmailAndAttach`. Linking requires session-bound intent, reauth, external proof, collision checks, and cleanup when callbacks fail/cancel.

### 14.5. Building the app principal and authorities

After looking up `ExternalKey → U-100`:
1. Load account U-100 and ensure it is `ACTIVE` and not suspended/compromised.
2. Map roles/tenant memberships from application authority, never blindly trusting provider claims.
3. Record provenance (`authenticated_via_link_id`, IdP/`auth_time`/assurance) if policy requires it.
4. Build `Authentication` in Spring Security's context with the internal principal and policy-controlled authorities.
5. Rotate/change session ID when transitioning unauthenticated → authenticated per Spring session fixation policy; handle CSRF tokens/sessions properly.
6. On app logout, clear the session/context, and do not promise upstream IdP sessions are logged out unless proper protocol SLO is implemented.

There is no need to store raw IdP access/refresh tokens in account links just for login. If API delegation is needed, use separate authorized-client storage with encryption, scoped access, refresh lifecycle, and revocation.

## 15. Standalone Java 17: One App Account, Multiple External Keys

This program simulates **identity-binding policy** without Spring/Maven/IdP. It demonstrates:
- Two issuers with the same `sub` are **not the same external identity**.
- Once both the account and external identity are proven, two external keys can map to the same U-100.
- An external key **cannot** be stolen from U-100 by U-999.
- Unlinking one key does not delete the app account or other keys.

**Limitations:** the `accountReauthenticated` and `externalProofVerified` flags in the demo are mock inputs confirmed by test setup; **a production application must never accept those two booleans from a client**. Obtain proof from a server-side verified session + OAuth2/OIDC/SAML protocol. The demo's `synchronized` only guards one Java object and **does not replace a multi-node database unique index/transaction**.

File `IdentityLinkDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class IdentityLinkDemo {
    record ExternalKey(String issuer, String subject) {
        ExternalKey {
            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new IllegalArgumentException(
                        "Verified issuer and subject are required");
            }
        }
    }

    static final class Links {
        private final Map<ExternalKey, String> owner = new HashMap<>();

        synchronized boolean link(
                String appAccount,
                ExternalKey verifiedExternal,
                boolean accountReauthenticated,
                boolean externalProofVerified) {
            if (!accountReauthenticated || !externalProofVerified) {
                return false;
            }
            String existing = owner.get(verifiedExternal);
            if (existing != null) {
                return existing.equals(appAccount);
            }
            owner.put(verifiedExternal, appAccount);
            return true;
        }

        synchronized String resolve(ExternalKey key) {
            return owner.get(key);
        }

        synchronized boolean unlink(
                String currentAccount, ExternalKey key,
                boolean reauthenticated) {
            if (!reauthenticated
                    || !currentAccount.equals(owner.get(key))) {
                return false;
            }
            return owner.remove(key, currentAccount);
        }
    }

    public static void main(String[] args) {
        ExternalKey corp =
                new ExternalKey("https://idp-a.example/oidc", "42");
        ExternalKey partner =
                new ExternalKey("https://idp-b.example/oidc", "42");

        Links links = new Links();
        System.out.println("Same sub but different issuer: "
                + !corp.equals(partner));
        System.out.println("Unproven link denied: "
                + !links.link("U-100", corp, false, true));
        System.out.println("First identity linked: "
                + links.link("U-100", corp, true, true));
        System.out.println("Second identity linked: "
                + links.link("U-100", partner, true, true));
        System.out.println("Both resolve to U-100: "
                + "U-100".equals(links.resolve(corp))
                + " / " + "U-100".equals(links.resolve(partner)));
        System.out.println("Takeover by U-999 denied: "
                + !links.link("U-999", corp, true, true));
        System.out.println("Unlink partner succeeded: "
                + links.unlink("U-100", partner, true));
        System.out.println("Partner no longer linked: "
                + (links.resolve(partner) == null));
        System.out.println("Corporate link preserved: "
                + "U-100".equals(links.resolve(corp)));
    }
}
```

Run with JDK 17+:

```bash
javac IdentityLinkDemo.java
java IdentityLinkDemo
```

**Exact stdout:**

```text
Same sub but different issuer: true
Unproven link denied: true
First identity linked: true
Second identity linked: true
Both resolve to U-100: true / true
Takeover by U-999 denied: true
Unlink partner succeeded: true
Partner no longer linked: true
Corporate link preserved: true
```

**Interpretation:** The Java `record` compares both `issuer` + `subject`, never mixing namespaces. `Map<ExternalKey, appAccount>` simulates a `UNIQUE` external key. A link already owned by U-100 cannot have its owner changed by U-999. Unlinking partner preserves corporate login. Do not use this demo as a production credential manager: it lacks OIDC verification, SAML signatures, sessions, PKCE/state/nonce, database locking, auditing, expiry, and recovery—all of which are mandatory in a real system.

## 16. Preventing Account Takeover, Login Swapping, and Linking CSRF

| Attack/mistake | Consequence | Control |
| --- | --- | --- |
| Auto-link on matching email | New holder of old email enters someone else's account | **Never auto-link by email** |
| B only sends unverified `sub` | Attacker attaches arbitrary external identity | Validate issuer/signature/aud/nonce/state and trusted registration |
| Linking endpoint accepts `userId=U-100` from browser | Attacker attaches their IdP to victim | Take app user ID from authenticated server session |
| Linking on an overly stale app session | Session hijack suffices to add auth method | Fresh reauth/step-up, CSRF, risk checks |
| Callback does not match initiating session | Login swapping, links into wrong user | One-time session-bound `LinkIntent` |
| Colliding `sub` across IdPs | Cross-issuer collision | Unique key includes **issuer + sub** |
| Changing IdP registration/sector yields new `sub` | Account duplication | Evidenced migration, never email match |
| Identity key already belongs to another account | Account hijack or silent merge | `UNIQUE` index + deny/recovery/admin approval |
| Two simultaneous callbacks | Double insert/owner overwrite | DB transaction, `UNIQUE` index, consumed intent |
| Issuer mix-up across multiple IdPs | Code/token redeemed at wrong provider | Expected issuer in state, RFC 9207/RFC 9700, exact redirect |
| Attacker supplies custom issuer/JWKS URL | SSRF/key injection | Admin-managed provider allowlist, no dynamic issuer trust |
| `admin` role from partner IdP | App privilege escalation | Separate trust mapping and tenant authorization |
| Unlink last auth method | Lockout | Verify remaining sign-in/recovery method |
| IdP deprovisioned while app session remains | Access persists after revocation | Session provenance, TTL/revocation/signals |
| Key/token/session leaked in logs | Credential theft | Redact logs, HTTPS, vault/KMS |
| Admin migration via email CSV | Wrong user/account | Verified immutable IDs, dual approval, rollback |

**Specific note on OAuth2 access tokens:** an access token issued for some API is not by itself proof that "the user just authenticated to link an app account". For OIDC, use the proper RP authorization code flow and ID Token validation. Never use a token from IdP A with `aud=client-A` to sign into or identify a user at app client B by skipping issuer/audience checks.

## 17. Deprovisioning, Account Recovery, and IdP Migration

### 17.1. When one IdP locks an employee

If the user remains linked to IdP B, they can still sign into U-100 via B. This may be a legitimate business requirement or a **risk**: after offboarding, corporate access should not survive through another external login.

Separate:
- **Auth method revoked**: only external link A is disabled.
- **App account disabled**: U-100 cannot sign in via **any** IdP.
- **Tenant membership revoked**: U-100 still exists, but holds no access to tenant CORP.
- **Sessions/tokens revoked**: clear sessions/refresh access appropriately so changes take effect.
- **Business data retention**: records may be retained for audit per policy without granting user access.

SCIM provisioning, IdP events/webhooks, HR status, and app ACL updates must have an **owner/source of truth**. When an IdP reports a user disabled, company policy must decide whether to lock the entire account, a single link, or only tenant membership. Never assume "link B remains" always grants corporate access.

### 17.2. Account recovery when losing IdP A

If a user loses access to A while U-100 already has B linked, they may use B per policy (potentially requiring appropriate assurance). If **B is not yet linked**, never attach B to U-100 just because someone emails "I am Alice". Require independent recovery with strong identity verification, admin approval, or risk-appropriate identity proofing, with full auditing and notifications.

### 17.3. Enterprise-wide identity provider migration

For example, replacing IdP A with IdP D:
1. Inventory registered clients, realms, old issuer+sub pairs, immutable directory IDs, and tenant memberships.
2. Obtain a signed/approved migration mapping from an existing authority or dual-auth proof while users still have access to both.
3. Test on sandbox users and edge cases: colliding emails, renamed users, pairwise `sub`s, deleted/recreated directory objects.
4. Create the new external link D→U-100 in a transaction; never delete A before verifying D succeeds.
5. Canary by tenant, log link outcomes, and support rollback.
6. After verification, revoke link A per policy; handle existing sessions and stale tokens.
7. Never alter the app user ID in the business database.

**Do not assume changing `issuer-uri` is just a DNS change.** A different OIDC `iss` creates a different identity namespace requiring trust migration. By contrast, issuer key rotation within the same issuer is a JWKS/trust update rather than a new identity.

## 18. Difference Between Account Linking and MFA

Linking Google + Entra accounts does not mean the user has enabled **MFA**. If an app account has two different ways to log in, an attacker only needs to compromise **the weakest one** to reach that account.

Therefore:
- Evaluate the assurance of each IdP/linked identity; never assign `AAL2` just because two identities exist.
- Require MFA/step-up for sensitive linking/unlinking.
- For admin resources, check freshness, `auth_time`, and `acr`/`amr` per OIDC profile and policy; never copy assurance claims from an untrusted IdP.
- If a weaker IdP B is linked to admin account U-100, do not assume a B login is permitted to perform admin operations.
- You can restrict `allowed_idp_for_sensitive_action` or require reauth with the corporate IdP.
- Align session lifetime/revocation with the authentication source, especially when users change tenants or are deprovisioned.

**Linking two identifiers does not equal two factors.** MFA combines multiple factors within a single authentication event/policy; account linking simply adds entry paths to an app account.

## 19. Privacy, Auditing, and User Transparency

The list of linked identities is itself **sensitive data** because it can reveal which organizations an employee belongs to or which IdPs they hold accounts with. Principles:
- Display linked identities only to the account owner or authorized admins; never leak via public APIs.
- Consider showing provider display names rather than full `issuer+sub`; avoid printing raw immutable `sub` values in the UI unnecessarily.
- Notify when link/unlink occurs, with an alert channel if the action was not user-initiated.
- Audit `actor app_user_id`, target link, provider, event type, timestamp, request correlation, assurance, and outcome; **never log ID Tokens/access tokens/refresh tokens**.
- Define retention/history rules for revoked links and security events; restrict access and purge per law/data policy.
- When returning "identity already linked to another account", phrase messages so they never disclose another person's email/ID.
- Do not automatically notify IdP A that the user also holds a link to IdP B via cross-IdP signals without legal basis/agreement. NIST `63C-4` notes that RPs should handle account-linking signals under a privacy risk assessment.

### 19.1. Sample UX for a "Sign-in Methods" page

```text
Linked Sign-in Methods
  [Corporate SSO]    Linked since 2026-10-10    [In Use]
  [Partner SSO]      Linked since 2026-11-01    [Unlink]

[Add Sign-in Method]

Unlink Partner SSO?
- You will no longer be able to sign in to this account using Partner SSO.
- Sessions and access may be revoked per security policy.
[Re-authenticate] [Cancel] [Confirm Unlink]
```

This UI is illustrative only. When the user clicks "Add", the app needs a server-side POST/CSRF step, reauth, and OIDC redirect. There is never a "just enter email and add link" shortcut.

## 20. Pre-Release Test Matrix

| Case | Expected |
| --- | --- |
| OIDC A login with existing link | Maps properly `(iss A, sub A) → U-100` |
| OIDC B login with existing link | Maps properly `(iss B, sub B) → U-100` |
| A and B share `sub=42` | Two distinct external identities |
| A and B share email, unlinked | Accounts are not auto-merged |
| Email at A changes, `iss+sub` unchanged | Does not create a new app account |
| `email_verified=true` from B, unlinked | Cannot access U-100 |
| OIDC ID Token invalid signature | Does not authenticate/link |
| ID Token valid signature but wrong `aud` | Reject; not valid for app |
| OIDC `iss` differs from registered issuer | Reject |
| Wrong `state`/`nonce`/PKCE | Reject; pending `LinkIntent` is not consumed as success |
| Authorization-server mix-up | Callback from B is not processed as A |
| U-100 reauthenticated, valid B auth | Links B → U-100 after DB uniqueness |
| Unauthenticated user opens linking callback | Reject; never pick user from query |
| Session U-100 switches to U-999 before callback | Reject linking attempt |
| Session U-100 too old per sensitive-action policy | Force reauth/step-up |
| Replayed link callback | Intent already `CONSUMED`, reject |
| Link intent TTL expired | Reject, clean up safely |
| B identity already linked to U-999 | Never reassign owner to U-100 |
| Two requests concurrently link B | `UNIQUE` constraint blocks double attach |
| Multiple pods handle linking | Shared DB/session state stays consistent |
| DB connection drops at commit | Never report success without commit |
| Unlink B by U-100 | B can no longer log into U-100 |
| Unlink B via request from U-999 | Reject |
| Unlink last authentication method | Enforce lockout/recovery policy |
| Unlink succeeds while B session still active | Revoke/invalidate per policy |
| IdP B deprovisioned | App revokes link/account/tenant per policy |
| IdP B compromised | Risk response prevents role privilege escalation |
| SAML transient `NameID` | Never stored as durable identity link |
| SAML Assertion wrong recipient/audience | Reject |
| SAML XML signature wrapping/replay | Reject |
| CAS username reassigned | New holder cannot claim U-100 |
| LDAP DN changes due to OU move | Immutable directory ID still maps properly |
| LDAP object deleted/recreated with same email | Does not auto-map to old account |
| Pairwise OIDC `sub` changes on sector change | Requires migration/link proof, no email auto-merge |
| Account U-100 `DISABLED` | None of the linked IdPs can log into U-100 |
| Tenant CORP revoked | B login does not retain CORP permissions |
| IdP B assurance below admin policy | Step-up or deny admin action |
| Raw tokens in audit log | Must never appear |
| Notification on link/unlink | User notified without leaking other identities |
| Restore/backup/migration | Unique links and audits remain intact |

**Recommended test layers:** unit tests for identity keys and collisions; DB integration tests for uniqueness/transactions/outbox; Spring Security integration with OIDC sandbox issuers A/B and session-bound link intents; multi-tab/SameSite/CSRF browser E2E; SAML/CAS/LDAP adapter-specific tests; security negative tests for issuer mix-up, session swapping, account takeover, unlinking the last method, deprovisioning, and multi-tenant authorization.

`@WithMockUser` **does not prove** that an OIDC/SAML identity was verified or that `LinkIntent` is safe: it only creates a mock authenticated context. Tests must exercise the real token/response validation code paths in a sandbox with trusted provider fixtures.

## 21. Safe Deployment Runbook

**Preparation:**
1. Inventory IdPs/realms/client registrations, stable subject claims, trust policies, and per-tenant owners.
2. Choose a stable internal app account ID and key business data by that ID.
3. Design protocol-compliant external keys, unique DB indexes, and link/unlink history.
4. Define who may link: account must be `ACTIVE`, fresh auth, matching tenant/policy.
5. Design server-side pending `LinkIntent` with one-time/short TTL, session binding, expected issuer, and CSRF.
6. Define behavior when an identity is linked elsewhere, an account has zero remaining methods, an IdP is disabled, a user changes email, or duplicate accounts exist.
7. Build the security test suite and audit/notification pipeline.

**During the linking flow:**
1. User logs into U-100 and explicitly POSTs a request to link B.
2. App checks fresh session and reauth policy, then creates `LinkIntent`.
3. Browser redirects to B's OIDC authorize endpoint with state/nonce/PKCE; app records expected issuer B.
4. Callback is fully verified under B's client registration.
5. App consumes the intent against the original U-100 session; checks account is `ACTIVE` and B is not linked elsewhere.
6. Insert into DB within a transaction with the unique key, write audit log, and commit.
7. Notify user and display linked identities, **never auto-merging business accounts**.

**When unlinking or migrating IdPs:**
1. Require fresh auth/CSRF and verify remaining access or recovery paths.
2. Verify the link belongs to U-100 and assess impact on sessions/provenance and tenant permissions.
3. Revoke/disable the link, audit, notify, and review active tokens.
4. Execute an evidenced migration if issuer/subject changes; include rollback and preserve app user IDs.

## 22. Self-Check Questions

**Q1. Why might two ID Tokens with the same `sub=42` not belong to the same person?**  
Because `sub` is only unique **within an issuer**. The `(iss, sub)` pair identifies an external OIDC identity.

**Q2. Can two IdPs returning `email=an@example.com` and `email_verified=true` be auto-linked?**  
No. Emails can change, be recycled, and be verified under different policies. You need proof of ownership of both the app account and the new external login.

**Q3. Where should the application obtain the user's primary ID?**  
Generate a stable internal `app_user_id`; map one or more verified external identities to that ID. Business records/roles reference the app ID.

**Q4. When a user adds IdP B, can we just ask them to sign into B and link to U-100 via a query parameter?**  
No. You need an authenticated U-100 app session, fresh auth, a session-bound `LinkIntent`, a verified B login, and DB uniqueness.

**Q5. If identity B is already linked to U-999, should the app move it to U-100 when emails match?**  
No. That is a conflict requiring denial/recovery/admin-mediated proof and auditing; never overwrite ownership.

**Q6. Does unlinking B automatically terminate all active sessions?**  
No. You need a revocation/session-invalidation policy, especially for sessions created via B.

**Q7. Does an account with two IdPs count as MFA?**  
No. Two login methods do not equal two factors in a single authentication event; assurance/step-up must be evaluated separately.

**Q8. If an application uses an identity broker, must it store upstream `iss+sub` itself?**  
Not necessarily. If the broker manages links and emits a stable broker subject, the app can map `(broker iss, broker sub)` to the app account. Upstream mapping belongs inside the broker's trust boundary.

## 23. Official Documentation and Reference Standards

1. [OpenID Connect Core 1.0 – Claim Stability & Uniqueness `5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability): `iss` + `sub` form the durable identifier pair; email/username carry no such guarantee.
2. [OpenID Connect Core 1.0 – Subject Identifier Types `8](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes): public/pairwise `sub` and sector identifiers.
3. [NIST SP 800-63C-4 – Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): federated identifiers, RP subscriber accounts, account linking `3.8.1`, account resolution, notifications, and privacy signals.
4. [OWASP Authentication Cheat Sheet – Secure Federated Account Linking](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#secure-federated-account-linking): no email auto-linking; require existing session and verified new identity.
5. [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): state, PKCE, CSRF/mix-up, and authorization code security.
6. [RFC 9700 – OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect URI, mix-up defense, and multi-provider flow protection.
7. [RFC 9207 – Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html): issuer identification in authorization responses.
8. [Spring Security – OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth2/OIDC login, authorization/redirect endpoints.
9. [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, custom success/UserInfo processing.
10. [Keycloak – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/#_identity_broker): first broker login, external IdP config, and account linking.
11. [Keycloak – Account Linking](https://github.com/keycloak/keycloak/blob/main/docs/documentation/server_development/topics/identity-brokering/account-linking.adoc): request-bound link initiation and the application's CSRF responsibilities.
12. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, lifecycle, logout, and protection.
13. [SCIM 2.0 Core Schema – RFC 7643](https://www.rfc-editor.org/rfc/rfc7643.html): `id`, `externalId`, and SCIM identifier scope.
14. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `NameID`, `NameQualifier`, assertions, and conditions.

**Final Summary:** **One app account may have multiple external identities**, but only after each identity has been authenticated via its proper protocol and **intentionally, session-bound linked to an authenticated app account** inside a transaction with a unique key. For OIDC, the trustworthy key is `(iss, sub)`; email/username/phone are not durable identity keys. Spring Security authenticates each IdP, while managing the app user ID, linking/unlinking, collisions, revocation, tenant permissions, and account recovery remains the responsibility of the application's **Identity Link Service / IAM policy**.