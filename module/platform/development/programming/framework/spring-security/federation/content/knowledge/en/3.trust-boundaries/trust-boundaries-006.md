# Stable User Identification Scoped to Each Provider

## 1. Goal and Context

In **Spring Security – federation**, an application can receive login results from multiple Identity Providers (abbreviated **IdP**). A critical design question is: **do today's login and next month's login truly belong to the same user?** If two people from two IdPs share the name `alex` or the same short ID value `123`, how do you avoid accidentally merging accounts?

This lesson belongs to the **trust boundaries** group: an application must only equate identities when authentication credentials originate from a trusted provider and the identifier has an **explicit scope**.

Core principle of OpenID Connect (OIDC):

> The stable linking identifier a Relying Party can rely on is the **`(iss, sub)` pair from a valid ID token**, within the issuer's scope and subject-issuance policy.

- **`iss` (issuer):** logical identity of the issuer, e.g., `https://login.example.test/realms/staff`. One host can have multiple distinct issuers due to path/realm/tenant differences.
- **`sub` (subject):** user identifier issued by the issuer. Under OIDC, it is unique within the issuer and must not be reassigned to another user; this string is case-sensitive.
- **Local user ID:** account key owned by the business system, e.g., `user_9001`. It is not synonymous with `sub` and can have multiple external identities linked to it.
- **Email, username, display name:** profile attributes that may change or collide; they are not stable linking keys under OIDC guarantees.

For OIDC, keep three layers in mind: **the IdP authenticates and issues an identifier**, **Spring Security verifies the authentication result and supplies a trusted principal**, and **the application links the principal to an internal account**. Spring Security does not automatically guarantee that all IdPs assign user IDs the same way.

## 2. Why Must Identifiers Be Provider-Scoped?

Consider the following two logins:

| Login | Issuer | Subject | Email |
| --- | --- | --- | --- |
| Alice via company A's IdP | `https://idp-a.example.test` | `123` | `alice@a.example.test` |
| Bob via company B's IdP | `https://idp-b.example.test` | `123` | `bob@b.example.test` |

Two `sub=123` values **do not prove** the two records are the same person. They were created in two different identity spaces. The exact key is:

```text
(https://idp-a.example.test, 123) -> local_user_Alice
(https://idp-b.example.test, 123) -> local_user_Bob
```

If the database only stores `sub`, Bob's login could be mapped to Alice's account. That is an **account collision/account takeover** bug at the federation boundary. Avoid this bug with a composite `issuer + subject` key, combined with verifying the issuer before lookup.

The same commercial vendor can also host multiple **logical issuers**:

```text
https://sso.example.test/realms/sales   + subject=123
https://sso.example.test/realms/hr      + subject=123
```

The two identities remain distinct. Do not replace `iss` with hostname, vendor name, `registrationId`, an inferred `realm`, or email domain. OIDC specifies that the issuer value must match metadata and token exactly; **the path is part of the issuer**. Never strip paths, change casing, normalize URLs arbitrarily, or merge two different issuers into one.

## 3. What Counts as "Stable"?

A key for linking accounts needs these properties:

1. **Same subject over time:** future logins still find the old link even if name/email changes.
2. **Never reassigned to someone else:** if a subject is deleted, the old identifier does not transfer to a new person.
3. **Explicit uniqueness scope:** a `sub` value is unique only within its **issuer**; do not assume global Internet-wide uniqueness.
4. **Originates from a verified source:** never trust `iss`/`sub` inside client-supplied JSON/headers/query parameters.
5. **Lifecycle agreement:** when an IdP changes tenants, changes issuers, migrates systems, or alters `sub` policy, the application needs a controlled migration process.

Per OIDC Core, `sub` is a **locally unique and never reassigned identifier within the issuer**. However, "stable" does not mean one human receives **one shared `sub` across every application**: OIDC supports **pairwise subject identifiers** that vary per sector/client. That protects privacy and does not violate uniqueness within the issuer.

In addition, a real-world system might migrate from issuer A to issuer B or restructure data despite initial agreements. The application must not infer the new identity from an old email address; it needs **verified linking/migration**.

## 4. Claim Categories: Identity Keys vs. Profile Data

| Value | Meaning | Use as Account Linking Key? |
| --- | --- | --- |
| Verified `iss` + `sub` | Identity established by an OIDC issuer for the Relying Party | **Yes**, per committed issuer/subject policy |
| `sub` alone | Subject without issuer namespace | **No** in a multi-IdP system |
| `email` | Contact address | **No**: can change, be deleted, reassigned, duplicated/spoofed |
| `email_verified` | Signal that IdP verified the email by its own mechanism | **No**: does not prove the old internal account owner is the current person |
| `preferred_username`, `name` | Login/display name | **No**: can change/collide, different scopes |
| `groups`, `roles`, `scope` | Groups, roles, permission scopes | **No**: used for authorization, not identification |
| `aud` | Intended recipient of the token | Not a user ID; used to verify the token is for the app/API |
| `jti` | JWT token ID if present | **No**: identifies a token, not a user across tokens |
| `sid` | Session ID when issued | **No**: identifies a session, can change |

Example of a user changing email:

```json
{
  "iss": "https://login.example.test/realms/staff",
  "sub": "7b1f93",
  "email": "mai.old@example.test"
}
```

After a domain change:

```json
{
  "iss": "https://login.example.test/realms/staff",
  "sub": "7b1f93",
  "email": "mai.new@example.test"
}
```

Both illustrations are **abbreviated claim payloads for explanation**, not complete JWTs or signed credentials. If the **ID token has been validly verified by the OIDC client** and has the same `(iss, sub)` pair, the application can locate the same internal link even if the email changed. Never use two unverified JSON snippets to conclude the caller is the same previous person.

## 5. OIDC Public Subjects and Pairwise Subjects

OIDC supports two subject types:

- **Public subject:** an issuer may issue the same `sub` for the same user across eligible clients. A client should not assume another provider's subjects behave the same way.
- **Pairwise subject:** an issuer generates a different `sub` per **sector identifier** so applications in different scopes cannot easily cross-track the same person. The same person at the same issuer in different sectors can have two different subjects.

Illustrative example:

| Login | Issuer | Sector | Subject |
| --- | --- | --- | --- |
| Employee Mai to portal A | `https://idp.example.test` | `portal-a.example.test` | `pair-A-8f2` |
| Mai to portal B | `https://idp.example.test` | `portal-b.example.test` | `pair-B-5d1` |

You cannot automatically confirm `pair-A-8f2` and `pair-B-5d1` belong to the same person just because the email matches. With pairwise subjects, the sector is computed per OIDC rules, typically involving the redirect URI host or `sector_identifier_uri`; changes to sector configuration can affect the subject a client receives.

**Proper design:** treat each `(iss, sub)` pair as a distinct **external identity**. If an enterprise wants portal A/B to share one internal account, joining the two identities must follow a linking mechanism approved by the IdP and application (e.g., authenticating both accounts in the same session, a broker flow with an explicit contract, or verified migration). Do not try to recompute pairwise `sub` values, and do not use email as a key to defeat this privacy protection.

If multiple redirect URIs/clients need consistent pairwise identities, the IdP operations team must design the sector identifier **before going to production**, test URL/client changes, and maintain a plan to preserve legacy mappings.

## 6. Trust Boundary: "Who Says Who This User Is?"

What matters is not only the claim contents, but also **who issued the claim and how the application verifies it**.

```text
User / Browser
   │ login redirect
   ▼
Trusted IdP (registered issuer)
   │ authenticates user, issues authorization code / ID token
   ▼
Spring Security OIDC Client
   │ verifies flow and ID token per configuration
   │ reads iss, sub from trusted principal
   ▼
External Identity Resolver
   │ looks up (iss, sub) in link table
   ▼
Local User + Membership + Business Permissions
```

The application only accepts a **verified identity** after standard OIDC processing: verifying signature/trusted keys, `iss`, `aud` (client ID), expiration, and `state`/`nonce` constraints where applicable. Spring Security performs the OIDC client steps per configuration; custom validations must **add** security requirements rather than bypassing default verification steps.

Never take `iss` from a `?issuer=...` query parameter, never take `sub` from a client-controlled HTTP header, and never decode a JWT and treat its payload as trusted. An unverified subject is merely **untrusted data**.

In a multi-IdP system, each issuer must be in the allowed configuration set. Even if two IdPs share a vendor name or email domain, IdP A's tokens **have no authority** to impersonate IdP B.

**Do not mix token roles:** an OIDC **ID token** proves login to the specific OIDC client; a bearer API should verify an **access token intended for that API**. A `client_credentials` flow may represent an **application** rather than an end user; never blindly take `sub` from any access token and map it to an employee account.

## 7. Choosing Storage Keys and Data Design

Use two layers: an immutable internal key and an external identity link table.

```text
local_user
  id = user-9001       (issued by application)
  status = ACTIVE

external_identity
  issuer = https://idp-a.example.test
  subject = abcd-001
  user_id = user-9001

external_identity
  issuer = https://idp-b.example.test
  subject = pp-981
  user_id = user-9001  (only after verified linking)
```

Key point: **one local user may have multiple external identities**, and each issuer/subject pair may be bound to **at most one** active local user. Never force an external subject to become the primary key of all business data. Relationship tables using the local user ID remain intact when an IdP changes.

PostgreSQL schema example (illustrative for an application you control):

```sql
CREATE TABLE local_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE external_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_user_id BIGINT NOT NULL REFERENCES local_user(id),
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT external_identity_iss_sub_unique
        UNIQUE (issuer, subject),
    CONSTRAINT external_identity_nonempty
        CHECK (length(issuer) > 0 AND length(subject) > 0)
);

CREATE INDEX external_identity_local_user_idx
    ON external_identity(local_user_id);
```

Additional production design considerations:

- Store `issuer` as its **exact verified value**; since OIDC issuers and subjects are case-sensitive, avoid `LOWER(issuer)`, `LOWER(subject)`, or case-insensitive collations.
- Define policies for disabling an external identity, locking a user, and revoking sessions; never cascade-delete relationships/orders just because an IdP account changed.
- For multi-organization systems, use a `membership(local_user_id, tenant_id, ...)` table to represent permissions. **Business tenant does not replace issuer**. When one issuer houses multiple logical tenants, understand how the provider issues `sub` and scope accounts by contract rather than merging tenants by inference.
- Create/update links inside a **transaction** and rely on the unique constraint to prevent race conditions: two concurrent JIT provisioning requests must not create two users for one `(iss,sub)`.
- Restrict read permissions on the mapping table and audit link/unlink operations. `iss`+`sub` can constitute personally identifiable data in the system and must be protected accordingly.

**Upsert rule:** if `(iss,sub)` already exists, look up the corresponding local user and check `status`; if it does not exist, create a new user only when policy allows JIT provisioning or initiate a **verified linking workflow**. Never auto-link to a local user with a matching email.

## 8. Where Does Spring Security Retrieve the OIDC Identity?

With Spring Security OAuth 2.0 Login and the `openid` scope, the principal is typically `OidcUser`. It holds the **ID token** and related claims. `OidcUser` provides `getIdToken()`, `getIssuer()`, and `getSubject()`.

A minimal OIDC Client configuration (illustrative only; operation requires registering the client and redirect URI at the IdP):

File `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: staff
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope: [openid, profile, email]
        provider:
          staff:
            issuer-uri: https://login.example.test/realms/staff
```

Required libraries for the Servlet example: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`; the redirect URI configured at the IdP must match the application's redirect endpoint, usually `{baseUrl}/login/oauth2/code/{registrationId}`. Protect secrets using environment variables/a secret manager; HTTPS is a requirement in real environments.

A class extracting the principal from Spring Security **after OIDC login succeeds**:

File `VerifiedIdentity.java` in an application package, e.g., `com.example.federation`:

```java
package com.example.federation;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component
public class VerifiedIdentity {

    public IdentityKey from(OidcUser principal) {
        // Call only when principal comes from an authenticated OIDC flow.
        String issuer = principal.getIdToken().getIssuer().toString();
        String subject = principal.getIdToken().getSubject();
        return new IdentityKey(issuer, subject);
    }

    public record IdentityKey(String issuer, String subject) {}
}
```

The class above is an **integration fragment inside a Spring Boot project with dependencies**, not a standalone runnable JDK program. It illustrates extracting the two claims from the **ID token**, then passing them to a mapping lookup service. The example does not query a DB itself, does not implement account linking, and does not replace configuring `SecurityFilterChain` with `oauth2Login()` or equivalent Spring Boot configuration.

**Why not just read `principal.getName()`?** Principal name is a framework display representation and can change via `user-name-attribute`/custom configuration. Although by default OIDC often displays the subject, it should not be used alone as a linking key because the issuer is also required. Similarly, the registration name `staff` is a local config label, not the issuer inside the token.

When using SAML, the principal is not `OidcUser`: you must read the SAML NameID with appropriate persistence policies and IdP/SP context. When using an OAuth 2.0 Resource Server, API requests usually carry a `JwtAuthenticationToken` or equivalent principal; **do not force everything into an OIDC login principal type**. An API's identity contract must be verified separately by token/issuer and grant type.

## 9. Standalone Java 17 Example: Three Identification and Separation Cases

The following program simulates lookup after token verification. There are no real tokens, signatures, IdP, or Spring Security in the program; the goal is to verify **keying rules**.

File `ProviderScopedIdentityDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class ProviderScopedIdentityDemo {

    record IdentityKey(String issuer, String subject) {
        IdentityKey {
            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new IllegalArgumentException("Missing identity key");
            }
        }
    }

    public static void main(String[] args) {
        Map<IdentityKey, String> localUsers = new HashMap<>();

        IdentityKey companyA = new IdentityKey(
            "https://idp-a.example.test", "123"
        );
        IdentityKey companyB = new IdentityKey(
            "https://idp-b.example.test", "123"
        );

        localUsers.put(companyA, "user-A");
        localUsers.put(companyB, "user-B");

        // Same subject, different issuer -> two separate accounts.
        System.out.println("A=" + localUsers.get(companyA));
        System.out.println("B=" + localUsers.get(companyB));
        System.out.println("sameExternalIdentity="
            + companyA.equals(companyB));

        // Same issuer+subject, email changes -> still looks up the same account.
        String oldEmail = "mai.old@example.test";
        String newEmail = "mai.new@example.test";
        System.out.println("emailChanged="
            + !oldEmail.equals(newEmail));
        System.out.println("sameLocalUserAfterEmailChange="
            + "user-A".equals(localUsers.get(companyA)));

        // Different pairwise subject -> do not auto-link based on email.
        IdentityKey otherSector = new IdentityKey(
            "https://idp-a.example.test", "pairwise-999"
        );
        System.out.println("otherSectorMapped="
            + localUsers.containsKey(otherSector));
    }
}
```

Run with JDK 17+:

```bash
javac ProviderScopedIdentityDemo.java
java ProviderScopedIdentityDemo
```

Exact stdout:

```text
A=user-A
B=user-B
sameExternalIdentity=false
emailChanged=true
sameLocalUserAfterEmailChange=true
otherSectorMapped=false
```

Explanation:

- `record` generates `equals()`/`hashCode()` from both **issuer and subject**, so two companies both issuing subject `123` still produce two distinct keys.
- Email does not participate in `IdentityKey`, so changing email preserves the mapping as long as the issuer/subject pair remains the same.
- An unmapped new pairwise subject returns `false`. A real system must perform evidence-backed linking rather than assuming two subjects are the same person.
- Never use an in-memory `Map` as a production account store; persistence, unique constraints, transactions, and auditing belong in the service + database.

## 10. SAML 2.0: Same Concept, Different Identifier Mechanism

In **SAML 2.0** federation, the application acts as a Service Provider (SP) receiving assertions from an IdP. The identifier is typically carried in `<NameID>`; however, **not every NameID is stable**.

| SAML NameID Format | Characteristics | Suitability for Long-Term Linking |
| --- | --- | --- |
| `persistent` | Opaque, long-lived identifier, typically scoped to an IdP–SP relationship | Suitable once stability contract and qualifiers are confirmed |
| `transient` | Short-lived identifier, not for long-term recognition | No |
| `emailAddress` | Uses email address as identifier | Risk of change/reassignment; not stable by default |
| `unspecified` | No general guarantee on format/persistence | Must be explicitly agreed with IdP before storing |

With a SAML persistent NameID, besides the string value you must consider **IdP entityID, NameQualifier/SPNameQualifier (if present), NameID Format**, and the per-SP contract. Do not simply take the text of NameID and compare it system-wide. A persistent NameID can **differ between two SPs even when the actual user is the same person**. This situation is analogous to OIDC pairwise subjects.

Spring Security `saml2Login()` processes SAML credentials per configuration, yet the **policy for choosing which ID to use for account linking** remains an integration decision of the application/IdP. When an IdP does not guarantee a persistent NameID, require another immutable attribute with a trusted scope and contract, or design a secure linking workflow.

## 11. SCIM, LDAP, and Employee IDs Do Not Automatically Replace OIDC Keys

Organizations may use LDAP/Active Directory, HR systems, or **SCIM** to provision accounts. These are complementary sources/flows that do not automatically turn every code into a trustworthy federation identifier.

- **SCIM `id`** is issued by the SCIM service provider; it is stable and never reassigned **within the SCIM service provider's namespace**.
- **SCIM `externalId`** is supplied by the provisioning client; it is scoped to the provisioning domain and serves as mapping data for the provisioning flow, not a default OIDC `sub`.
- **Employee ID / LDAP DN / username** can migrate across systems, change organizations, be renamed, reused, or have separate scopes; never assume immutability.
- When onboarding via SCIM and logging in via OIDC, define an official mapping: which SCIM resource corresponds to which `(iss,sub)`, established via a verified join during provisioning/login rather than email matching alone.

Safe pattern: SCIM creates the local user and records an **administratively verified link**; OIDC login looks up `(iss,sub)` to open that exact account. If no mapping exists yet, apply pending status or user verification instead of guessing.

## 12. Linking Multiple IdPs to the Same User

There are two distinct operations:

1. **Recognizing a known external identity:** valid token with `(iss,sub)` already in the table ⇒ look up local user.
2. **Attaching a new external identity to an existing local user:** this is a **sensitive action** that can transfer data access privileges and must be separately authorized and verified.

Example of a user who already has an account via IdP A wanting to link IdP B:

```text
1. Signed into the internal account via IdP A with a sufficiently strong current session.
2. User requests "Link IdP B".
3. Application initiates a separate login flow to B with CSRF/state protection.
4. Spring Security receives the verified authentication result from B.
5. Verify key (iss_B, sub_B) does not already belong to another local user.
6. Perform linking inside a transaction + audit log.
7. Only on subsequent logins allow B to access the linked local user.
```

Depending on risk level, MFA/step-up, administrative approval, or organizational workflows may be required. If B is already bound to another user, **reject the conflict and open a resolution workflow** rather than silently reassigning the link. Merely seeing the same `email` or `email_verified=true` must never trigger an automatic merge.

Unlinking workflows must also be controlled: avoid removing the last login method and locking the user out, and handle active sessions/tokens/permissions after unlinking.

## 13. Issuer Changes, IdP Migrations, and Organizational Mergers

Scenarios that break links:

- Changing URL/realm/tenant alters `iss`.
- Migrating from IdP A to B: the new `sub` belongs to a different identifier space.
- Switching from public subjects to pairwise (or changing sector ID/redirect domain) yields a new `sub`.
- Moving tenants/restoring data at a provider causes identifiers to be exported/imported differently.
- Merging two organizations that have overlapping usernames/emails.

Do not "auto-fix" by finding users with matching emails. A safe migration process:

1. Inventory **old/new issuers** and subject types; check whether the IdP provides an official mapping table.
2. Choose a trustworthy proof source for the link: signed export/controlled admin evidence, authenticating both accounts, or an IdP consolidation mechanism.
3. Create `old (iss,sub) -> local_user` and `new (iss,sub) -> same local_user` mappings inside a transaction, checking uniqueness and conflicts.
4. Dry-run on a small audited subset; resolve conflicts via review rather than bulk auto-merging.
5. Preserve history and link rollback capability; never lose business data owner IDs.
6. Retire the old issuer only with a cutoff policy, handling issued sessions/tokens and fallback login paths.

Using `issuer` as the identity namespace means **an issuer change is a link-key change event**. Never simply change an `issuer-uri` config value and expect all users to be recognized as before.

If the application trusts an **identity broker** (e.g., intermediary IdP A authenticates upstream at IdP B), the application receives the identity **issued by A**; A is responsible for mapping B's user to A's subject. Do not store B's `sub` from an uncontracted claim while ignoring the `iss` of the token the application actually trusts.

## 14. Relationship Between Identification and Authorization

The `(iss,sub)` key answers **"which account is this?"**, not **"what are they allowed to do?"**.

Once the local user is resolved, the application must evaluate:

- Account status: ACTIVE, SUSPENDED, DEPROVISIONED.
- Current tenant/organization membership.
- Roles, specific resource permissions, and business conditions.
- Guarantees that another tenant's data is never read merely due to matching `sub` or group names.
- Policy upon IdP change: are existing permissions retained or must they be re-approved?

An IdP might issue `groups=["finance"]`, yet the application must still decide which authority/role that group maps to and which records it may access. Durable identification is a **prerequisite** for accurate authorization, not a license to access all data.

## 15. Essential Test Matrix

| Test Case | Input | Expected Outcome |
| --- | --- | --- |
| Same person logs in again | Same `iss`, same `sub`, unchanged email | Resolves to the exact previous local user |
| Email changed | Same `iss`, same `sub`, new email | Resolves to the exact previous local user; updates email per policy |
| Username changed | Same `iss`, same `sub`, new username | Resolves to the exact previous local user |
| Two IdPs share subject | `iss_A`, `iss_B`, both `sub=123` | Two distinct external identities |
| Issuer differs by path | `/realms/a` and `/realms/b` on same host | Never merged automatically |
| Forged token / unknown issuer | Payload has `sub` matching an existing user | Rejected before lookup if token is invalid/issuer untrusted |
| ID token with wrong audience | Valid issuer and subject, but token issued for another client | OIDC client must reject |
| New pairwise subject | Same IdP, different `sub` due to sector | Never merged automatically; requires linking |
| Concurrent linking attempts | Same external identity into two accounts | Unique constraint prevents double-binding |
| Recycled email | New person has old person's email but different `sub` | Never grants access to old account |
| IdP A migrated to B | `iss` and possibly `sub` change | Never auto-matched; requires verified migration |
| Locally disabled user | Valid token, known `(iss,sub)` | Application denies based on local user status |
| API client credentials | Token represents an app, no end user | Never blindly mapped to a local user |
| SAML transient NameID | NameID changes per session | Never used as a permanent user key |
| Overlapping SCIM externalId from another provisioning domain | Same `externalId` string | Distinguished by domain and mapping policy |

During integration, run end-to-end tests with **two different issuers**; mocking only one issuer easily misses collisions. Include interruption tests during migration/linking to catch race conditions, and inspect audit logs before/after.

## 16. Common Mistakes and How to Avoid Them

1. **Keying the table solely by `sub`:** two IdPs can issue the same subject ⇒ include `issuer` in the key/unique constraint.
2. **Auto-joining users by email:** emails change or get recycled; even `email_verified` does not guarantee equivalence with a prior internal account ⇒ verify links separately.
3. **Trusting `preferred_username`, `name`, or `registrationId` as permanent IDs:** these are not the issuer/subject pair ⇒ extract identity claims from the verified ID token.
4. **Reading `iss`/`sub` from an unverified JWT or HTTP header:** client-supplied data ⇒ process only after trusted validator success.
5. **Normalizing subjects with lowercase/trim:** subjects are case-sensitive strings; altering them can cause collisions ⇒ keep the exact issued value.
6. **Dropping paths or tenants from the issuer:** multiple realms have distinct issuers ⇒ store the full verified issuer.
7. **Assuming one person always has one shared subject across all clients:** pairwise subjects differ by sector ⇒ design account linking by contract.
8. **Using `jti` or session ID as a user ID:** tokens and sessions change over lifecycles ⇒ use issuer/subject.
9. **Using the ID token's subject as a substitute for data authorization:** right identification still does not prove access to an invoice/project ⇒ enforce business authorization.
10. **Merging accounts during an IdP change via an email-matching script:** risks exposing someone else's data ⇒ migration requires proof, auditing, and duplicate/conflict checks.
11. **Skipping DB uniqueness/transaction constraints:** concurrent JIT provisioning easily creates duplicate users ⇒ unique constraint on `(iss,sub)` and conflict handling.
12. **Treating any access token as end-user proof:** tokens for other APIs/clients or client credentials may not represent an end user ⇒ check token type, audience, grant, and contract.

## 17. Deployment Decision Checklist

Before connecting an IdP to the application, verify:

- [ ] What is the exact OIDC issuer? Are realms/tenants/paths distinguished? How are metadata/issuers configured?
- [ ] Are subjects public or pairwise? What is the pairwise/sector identifier scope? What happens if a redirect URI or client changes?
- [ ] Are `iss` and `sub` extracted from a token/principal that already passed signature, audience, issuer, expiration, and flow checks?
- [ ] Does the mapping table have a unique constraint on `(issuer, subject)`, and is the local user ID independent of the IdP?
- [ ] Is auto-linking by matching email—even with `email_verified=true`—prohibited, and is there a secure link/unlink workflow?
- [ ] Is behavior defined and tested for when subject/issuer changes, a user is locked, tenant access is lost, or the IdP changes?
- [ ] If using SAML/SCIM, which attribute has a stability guarantee and what is that attribute's **issuer scope**?
- [ ] Do business services still check account status, membership, and resource permissions after identifying the user?

### Self-Check Questions

**1. Same `sub=42`, one token from `iss=A`, one from `iss=B`. Are they the same user?** No; you cannot draw that conclusion. They are two separate external identities until a link is verified.

**2. Is `email_verified=true` enough to look up an account by email and grant permissions?** No; an email verification signal does not substitute for proof that the current signer-in owns the old local user.

**3. Why do two apps receive two different `sub` values from the same IdP?** The IdP may be using OIDC pairwise subjects for different sectors. A linking contract/workflow is needed if one shared local user is desired.

**4. What happens if a user changes their email while `iss` and `sub` stay the same?** It still resolves to the existing mapping; update the email attribute per governance policy.

**5. When an IdP's issuer changes, should you automatically re-key all users by email?** No. Build verified old/new mappings, handle conflicts, and audit.

**6. Does Spring Security automatically decide which subjects belong to the same business account?** No. Spring Security handles protocol authentication and constructs the principal; the application manages the linking table and makes access decisions.

## Standards References

- OpenID Connect Core 1.0, sections **2, 5.7 Claim Stability and Uniqueness, 8 Subject Identifier Types**: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security, OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security, Advanced OAuth 2.0 Login / OIDC User Service: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security, `OidcUser` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- OASIS SAML 2.0 Core, sections **2.2 Name Identifiers, 8.3.7 Persistent Identifier**: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- IETF RFC 7643 (SCIM Core Schema), `id` and `externalId` sections: https://datatracker.ietf.org/doc/html/rfc7643

**Takeaway:** a subject only has meaning within its issuer's namespace and that issuer's subject policy. In OIDC, **verified `(iss,sub)`** is the durable linking key; **local user** is the identity managed by the application; any merging, transferring, or granting of permissions across identities requires explicit evidence and policy.