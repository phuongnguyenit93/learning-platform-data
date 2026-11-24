# Preventing Account Takeover When Linking Relies Only on Matching Email

> **Module:** Spring Security – federation · **Parent topic:** Directories and Accounts. This Knowledge article explains why a successful login from an IdP does **not** prove the external user owns an internal account with the same email address; how to prevent account takeover when linking OIDC/SAML/Kerberos/directory/SCIM identities; and how to design linking with proof, atomicity, least privilege, and revocation mechanisms.

## 1. Learning Objectives

After this article, you will be able to:

1. Distinguish three decisions: **the IdP authenticates an external principal**, **the application links an external principal to a local account**, and **the application authorizes access on internal data**.
2. Explain clearly why `email`, `email_verified`, `preferred_username`, `name`, `upn`, `mail`, and SAML email `NameID` are insufficient as linking keys.
3. Use OIDC `(iss, sub)` from a **verified ID Token** and understand the pairwise subject caveat per client/sector identifier.
4. In Microsoft Entra, distinguish `oid + tid` from `iss + sub`; understand why email/UPN can change or be recycled.
5. In SAML2, understand `persistent NameID` with issuer/SP scope and qualifiers, as distinct from `emailAddress` and `transient NameID`.
6. In SCIM, distinguish provider-assigned `id` from provisioning-client-scoped `externalId`; never use `emails.value` as a key to merge into an old account.
7. Analyze pre-hijacking, mailbox recycling, guest accounts, cross-tenant confusion, alias normalization, IdP migration, SCIM races, and concurrent link writes.
8. Build a `local_user_id` model independent of email and an external identity links table with unique keys per source/scope.
9. Design **explicit account linking** with an existing authenticated local session, recent reauthentication/MFA, a fresh IdP authentication flow, CSRF/state/nonce/PKCE, a one-time `LinkIntent`, and a database transaction.
10. Run a Java 17 demo with deterministic stdout showing the email auto-link flaw and safe behavior using `issuer+subject`.
11. Integrate Spring Security `OidcUserService` with no `findByEmail` fallback and load local permissions after an exact match.
12. Handle missing links, email changes, disabled accounts, SCIM deprovisioning, IdP changes, migrations, and account recovery.
13. Apply tests, auditing, and runbooks for mis-linking incidents and revoking tokens/sessions after account takeover.

**Scope:** Account linking in a Java/Spring Security federation application. OIDC examples are the primary focus; SAML2, Kerberos, Entra, and SCIM are compared by identity contract. The Java 17 demo is a simulation; the Spring Boot 3.3.x / Spring Security 6.3.x sample requires a real IdP for interoperability testing. This protection **differs** from merely verifying token signatures.

## 2. The Problem: One Email, Two People, and a Privileged Account

Suppose Orders Portal has an existing account:

~~~text
local_user_id = user-104
tenant_id     = company-A
email         = alice@example.org
authorities   = APP_ORDER_APPROVE
enabled       = true
~~~

A user logs in via OIDC to an approved IdP and receives:

~~~json
{
  "iss": "https://idp.partner.example/realms/workforce",
  "sub": "external-999",
  "email": "alice@example.org",
  "email_verified": true
}
~~~

The ID Token may be completely valid, yet **external-999** has never been linked to `user-104`. If the application executes:

~~~java
// WRONG: matching email treated as inheriting permissions from an old local account.
String email = oidcUser.getEmail();
LocalAccount account = accountRepository.findByEmail(email);
createApplicationSession(account);
~~~

then whoever controls `external-999` can be granted `APP_ORDER_APPROVE` without ever proving they own `user-104`. The IdP signing the token only confirms the **external subject** belongs to that issuer—it does not prove any right to inherit the data history and roles of a local account.

### 2.1. Three trust boundaries

| Question | Who can answer it? | What must not be inferred |
| --- | --- | --- |
| Is the Token/Assertion valid? | OIDC/SAML/Kerberos validator with trust anchors. | Does not prove local account ownership. |
| Which local user is the external principal? | Approved link repository, provisioning crosswalk, and explicit linking proof. | Never infer solely from email or display name. |
| What is the local user allowed to do? | Local account state, tenant/resource policy, and authorization store. | Never derive admin rights from email suffix or untrusted source group names. |

**Authentication success ≠ account linking success ≠ authorization success.**

## 3. OIDC `email_verified` and `(iss,sub)`: How Accurate Are They?

OpenID Connect Core 1.0 `5.7` states that the `iss` and `sub` pair is the durable basis for identification within the issuer's scope. Claims such as `email`, `preferred_username`, `name`, and `phone_number` carry no equivalent guarantee of uniqueness or non-reuse.

### 3.1. `email_verified=true` is not proof of local account ownership

The `email_verified` claim means the IdP took action to verify the user controlled the email **at the time of verification**. Depending on the trust framework, the IdP may have verified via email link/OTP or another organizational mechanism. The claim does not prove:

- That this email belongs to the same person forever.
- That the person holding the mailbox today is the same person who created the internal account years ago.
- That the external subject is entitled to enter the local tenant or inherit local roles.
- That the email in the local database was never transferred to someone else.
- That a new account with the same email was approved by HR/directory admins to attach to the old account.
- That the user completed the MFA/phishing-resistant authentication required for sensitive actions.
- That the email does not exist under multiple aliases/guest objects across realms/tenants.

Therefore:

~~~text
email == local.email                 -> only a hint for display/review
email_verified == true              -> evidence of mailbox verification per contract
(verified_iss, verified_sub) mapped
    to approved local_user_id       -> basis for account lookup
~~~

### 3.2. Email recycling causes mis-linking

~~~text
T0: Alice has sub=A7, email=alice@example.org,
    linked local_user_id=user-104.
T1: Alice leaves the company; email is released.
T2: Bob receives email=alice@example.org, sub=B9.
T3: Bob logs in, email_verified=true.

Auto-link by email: B9 -> user-104 (WRONG)
Lookup by issuer+sub: B9 is not linked (CORRECT)
~~~

No flaw in JWT signatures is needed: **the bug is in the mapping step**. This is especially dangerous if the old local account was not disabled due to a provisioning failure.

### 3.3. Same email, two subjects in one trusted IdP

Even an organization-trusted issuer does not guarantee every subject bearing the same `email` is the same person. Guest accounts, mailbox reuse, directory drift, email aliases, or policies permitting email recycling can exist. If `sub` differs, treat them as distinct external identities until approved linking evidence exists.

### 3.4. Pairwise subjects

OIDC defines `public` and `pairwise` subject types; with `pairwise`, the IdP can issue different `sub` values to different client/sector identifiers. One real person may hold two valid `sub` values across two applications. Never resolve that difference by auto-merging via email; use a trusted migration crosswalk, provisioning anchor, or fresh linking proof.

## 4. Choosing the Right Identifier per System

| Source | Appropriate identity key | Scope/trust to preserve | Attributes not to link on directly |
| --- | --- | --- | --- |
| OIDC | `(iss,sub)` from verified ID Token. | Approved issuer/registration; pairwise scope on migration. | `email`, `name`, `preferred_username`. |
| Microsoft Entra | `iss+sub` per OIDC; or `tid+oid` per Entra-specific contract. | Tenant ID, app registration, and token trust. | `email`, `upn`, `unique_name`. |
| SAML2 | `persistent NameID` with IdP EntityID/SP qualifiers, or contracted signed immutable directory ID. | IdP, SP, NameID format/qualifiers, tenant. | `emailAddress NameID` and `transient NameID` for long-term identity. |
| Kerberos/AD | Approved Kerberos principal+realm; when linking directory, use immutable object ID per contract. | Realm/domain and trust path. | `mail`, UPN, CN, display name. |
| LDAP | `objectGUID`/immutable anchor per directory contract. | Directory/forest/source. | DN across OU moves, `mail`/display name. |
| SCIM | `id` issued by SCIM service provider; `externalId` issued by provisioning client. | Provider/connector/provisioning domain/tenant. | `emails.value`, username for cross-system auto-merging. |
| Local app | Stable, non-recycled `local_user_id`. | Tenant, lifecycle, local permissions. | Email as an authorization key. |

### 4.1. Entra `oid+tid` vs. email/UPN

Microsoft explains that `oid` is the principal's object ID within a tenant and `tid` identifies the tenant. Email/UPN can change or be reused. The same person can have different objects in their home tenant and a resource/guest tenant.

~~~text
(tenant-A, oid-17) = account A
(tenant-B, oid-88) = account B

Same email != same Entra object
Same oid string without tenant scope != approved local user
~~~

If an app uses Entra-specific `(tid,oid)` to correlate multiple services, that must be an explicitly designed contract with issuer/tenant token validation. For standard OIDC providers, prefer `(iss,sub)`.

### 4.2. SAML2 NameID

A `persistent NameID` can be stably issued by the IdP within the SP/qualifier scope when properly configured. A `transient NameID` is unsuitable as a long-term linking key; an `emailAddress NameID` still suffers from email changes/recycling.

A validly signed SAML Assertion still does not prove that a matching `email` NameID and local email belong to the same owner. Signature validation **must happen before** lookup, but it does not replace link proof.

### 4.3. Kerberos and directories

Principal `alice@EXAMPLE.COM` must remain bound to its trusted realm/domain source. UPN, `mail`, or DN can change due to renames/moves. When an immutable directory object ID is issued and governed by an authoritative source, use it in the corresponding crosswalk while understanding its limits across forest migrations, object recreation, or rehires.

### 4.4. SCIM `id` and `externalId`

RFC 7643: `id` is generated by the SCIM service provider and is unique, stable, and non-reassignable within the provider's resource set. `externalId` is assigned by the provisioning client, **scoped to the provisioning domain**; it must never be assumed globally unique.

~~~text
connector-A: externalId=hr-1001  -> local-user-A
connector-B: externalId=hr-1001  -> local-user-B

Never use externalId=hr-1001 -> one shared local user.
~~~

SCIM `userName`/`emails` may be used for contact or searching per policy, **not as a replacement** for an authoritative mapping between the SCIM resource and OIDC `sub`.

## 5. Common Attack Patterns and Operational Mistakes

### 5.1. Pre-hijacking: creating the account before the real person

An attacker can create a local account with a victim's email in a weak signup flow, retaining a password/session/recovery credential. When the real person signs in via SSO for the first time, the app auto-links by email to that existing account. The attacker continues logging in locally and accesses data added later.

**Defense:** never auto-link existing local accounts by email, never inherit credentials/sessions of pre-created accounts, and require evidenced provisioning/reconciliation.

### 5.2. Mailbox recycling

A former employee leaves, a newcomer receives the email address, and signs into the IdP legitimately with `email_verified=true`. If the old local record is still active, email-linking lets the newcomer inherit the predecessor's data and roles.

**Defense:** immutable subject/object IDs, offboarding disable/revocation, and never allowing a new mailbox as sole proof for recovery of historical privileges.

### 5.3. Guest/B2B and multi-tenancy

A guest object from another tenant may carry an employee-looking email. If code only checks `email.endsWith("@company.example")`, an attacker/guest can gain roles. Check trusted issuer/tenant, immutable principal, and local tenant membership; an email domain **does not prove tenant ownership**.

### 5.4. Over-aggressive email normalization

Do not strip dots, `+tag` suffixes, or fold all local-part characters using Gmail rules across every domain. Two distinct addresses at another provider could collapse into one. Domain/canonical email normalization requires explicit rules, and **even properly normalized emails are not account-link proof**.

### 5.5. Two local accounts with the same email

Legacy data may contain duplicate emails across two tenants or from prior migrations. Email auto-linking forces an unproven match, potentially returning the first user or enabling user enumeration. The right response is `LINK_REQUIRED` and review, never silent merging.

### 5.6. IdP changes issuer/sub during migration

Migrating SAML2 → OIDC, changing clients/sectors, or switching tenants can change client-facing immutable identifiers. A script joining on email can mass-mislink accounts. Use a trusted crosswalk via immutable directory anchors, a signed/admin-approved migration manifest, dry-run collision review, and auditing; if proof is missing, require relinking or manual recovery.

### 5.7. SCIM provisioning race

An OIDC login may arrive before SCIM Create, or a SCIM email update may arrive before linking. If "link not found" triggers an email-lookup fallback, account takeover occurs right when distributed systems are out of sync. Return `PROVISIONING_PENDING`/`LINK_REQUIRED`, wait for the authoritative mapping, and never take an email shortcut.

## 6. Safe Login Rules

**Validate the protocol first**, then look up the exact identity link; never fall back automatically to email.

~~~text
Browser -> OIDC authorization code callback
                |
                v
Spring validates state/nonce, code/token,
iss/aud/signature/expiry, registered client
                |
                v
IdentityKey = (validated issuer, validated subject)
                |
                +--> link exists and active?
                |            |
                |            +--> local account enabled + tenant allowed?
                |                       |
                |                       +--> yes -> issue local Authentication
                |                       +--> no  -> DENY
                |
                +--> no link -> LINK_REQUIRED /
                                  approved new-account provisioning
                |
                +--> conflict -> DENY + manual review
~~~

| Case | Handling |
| --- | --- |
| Unverified ID Token / untrusted issuer | REJECT. |
| `iss+sub` has active link to active local account | Login may proceed; check permissions. |
| Link points to disabled user | DENY; do not search for another user by email. |
| Email matches local account but `sub` is unlinked | `LINK_REQUIRED`; do not authenticate as old account. |
| Subject already linked to user A, callback requests user B | CONFLICT; never auto-transfer owner. |
| No local account and onboarding is approved | May create a **new account**, new ID, minimal privileges; completely distinct from linking an old account. |
| Email changed but `iss+sub` unchanged | Keep linked local user; update contact via separate workflow. |
| User deprovisioned | Suspend/revoke local account and sessions per policy. |

**Never call** `findByEmail(oidcUser.getEmail())` inside an OIDC success handler; and never swap in `findByEmail` after checking `email_verified=true`.

## 7. Explicit Account Linking: Two Independent Proofs

To attach a new external identity to an **existing local account**, prove that the actor controls **that local account** and **the external identity being attached**.

### 7.1. State machine

1. The user signs into the existing local account via a sufficiently assured method; the server holds `local_user_id` in the `SecurityContext`/session.
2. The user chooses "Link identity provider". For sensitive changes, require **recent reauthentication/step-up MFA** on the local account, not just an old cookie.
3. The server creates a random, short-lived, single-use `LinkIntent` containing the local ID, session generation, approved provider registration, tenant, anti-CSRF/state, and expiry. Never accept local ID from an HTTP query parameter.
4. Initiate OIDC Authorization Code + PKCE/state/nonce with an allowlisted IdP and fixed HTTPS redirect URI.
5. Spring/IdP completes auth; the application only reads issuer/subject from the **verified** ID Token, never browser-supplied claims.
6. Verify `LinkIntent` is unused, unexpired, and matches provider, local session, tenant, and still-valid recent reauth.
7. Verify external identity `iss+sub` is not linked to another local user and the local account is `ACTIVE`.
8. Insert the link, consume the intent, and write the audit log **atomically** in the database; on race/unique violation, roll back and deny.
9. Notify the local account owner via a verified channel with audit/rollback policies; rotate session ID per policy.
10. Never automatically grant `APP_ADMIN_EXPORT` or change tenant memberships solely because a link was created.

~~~text
Existing local session + recent MFA
              |
              v
   Create one-time LinkIntent
              |
              v
Approved IdP login (state/nonce/PKCE)
              |
              v
Verified (issuer, subject)
              |
              +-- wrong session/expired/used -> DENY
              +-- already linked to another -> CONFLICT
              +-- local account disabled  -> DENY
              |
              v
     Atomic INSERT link + consume intent
              |
              v
  Audit + notify + preserve local authorization
~~~

### 7.2. Why is email OTP not enough?

An email OTP proves control of the **current** mailbox. When a mailbox is recycled, the new holder receives the OTP without owning the former holder's historical account. OTP may assist recovery depending on risk, but **it is never sole proof to merge privileged accounts**. If a user loses local login access, go through a recovery workflow verifying immutable directory/HR identities and approvals.

### 7.3. Replay, CSRF, and account switching

- `LinkIntent` must be random, high-entropy, short-TTL, and single-use.
- Never allow an OIDC login callback for another user to swap the local principal inside an old session while keeping old privileges.
- OIDC `state`/`nonce` and intent binding serve different roles; never omit one just because the other is present.
- When step-up reauthentication finishes, verify the same local user ID, not just email.
- Session fixation protection and CSRF remain mandatory for browsers.
- Unlink/relink operations are also sensitive and require reauth/auditing/revocation.

## 8. Data Model Design and Transaction Constraints

### 8.1. Local user ID independent of email

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email_contact VARCHAR(320),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE external_identity_link (
    id UUID PRIMARY KEY,
    local_user_id UUID NOT NULL REFERENCES app_user(id),
    tenant_id UUID NOT NULL,
    provider_registration VARCHAR(128) NOT NULL,
    source_issuer VARCHAR(512) NOT NULL,
    external_subject VARCHAR(512) NOT NULL,
    proof_kind VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (
        status IN ('ACTIVE','SUSPENDED','REVOKED')
    ),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ,
    UNIQUE (
        tenant_id, provider_registration,
        source_issuer, external_subject
    )
);

CREATE INDEX external_link_by_local_user
    ON external_identity_link(local_user_id);
~~~

This table uses PostgreSQL for illustration. Also ensure:
- Constrain the link's `tenant_id` to match the account's (composite foreign key/trigger or atomic service check); never accept tenant from the client.
- Clarify global vs. tenant-scoped uniqueness when **an external subject must not** attach to multiple accounts in different tenants.
- Never reassign `external_subject` when `status=REVOKED`; relinking after revocation requires separate approval/auditing.
- Never arbitrarily lowercase/canonicalize subjects; subject IDs and issuers must follow exact comparison per provider contract.
- `provider_registration` is a trust configuration ID, not a browser-supplied label.
- Never use email as PK or an authorization key; you may index email for search **without creating linkage**.

### 8.2. Link-creation transaction

~~~sql
BEGIN;

SELECT tenant_id, enabled
FROM app_user
WHERE id = :authenticated_local_user_id
FOR UPDATE;

-- Server must confirm account is active and tenant is right;
-- LinkIntent has proven recent local reauth + OIDC callback.
-- Consume LinkIntent atomically and insert link in the same
-- transaction when both reside in the database.

INSERT INTO external_identity_link (
    id, local_user_id, tenant_id, provider_registration,
    source_issuer, external_subject, proof_kind, status
) VALUES (
    :link_id, :authenticated_local_user_id, :approved_tenant,
    :approved_registration, :validated_issuer, :validated_sub,
    'RECENT_LOCAL_REAUTH_PLUS_OIDC', 'ACTIVE'
);

COMMIT;
~~~

On a `UNIQUE` violation, **never** use `ON CONFLICT DO UPDATE local_user_id=:new_user`. Roll back, log the conflict, and review. If intents live in Redis and links in SQL, design proper atomic consumption/outbox/compensation; a single SQL transaction does not make two stores exactly-once.

### 8.3. Directory and SCIM crosswalk

~~~text
(approved_scim_connector, externalId)
              |
              | administrative verified mapping
              v
         local_user_id
              ^
              | approved identity link
(validated_oidc_issuer, validated_oidc_sub)
~~~

Never infer `externalId == sub`, or `SCIM.email == IDToken.email` as proof. Require an authoritative mapping contract from directory/IdP and verify `active=false`, reassignment, and rehire lifecycles.

## 9. Standalone Java 17: Demonstrating the Vulnerability and the Solution

The code below **runs offline** with one local account Alice and two OIDC subjects sharing the same email. The program intentionally models an **unsafe** function to show takeover, then implements lookup by `issuer+subject` and evidenced linking. The `validated`/`recentReauth` booleans are fixtures inside the program; **never accept them from HTTP requests in production**.

### 9.1. `AccountLinkingSafetyDemo.java`

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class AccountLinkingSafetyDemo {

    record ExternalKey(String issuer, String subject) {}
    record ExternalUser(
        String issuer, String subject, String email,
        boolean emailVerified, boolean tokenValidated) {}
    record Account(String id, String email, boolean active) {}
    record LinkProof(
        String localId, boolean recentReauth,
        boolean secondIdpVerified, boolean sessionAndStateBound,
        long expiresAt, String nonce) {}

    static final class Service {
        private final String approvedIssuer =
            "https://idp.partner.example/realms/workforce";
        private final Map<String, Account> accounts = new HashMap<>();
        private final Map<ExternalKey, String> links = new HashMap<>();
        private final Set<String> usedProofs = new HashSet<>();

        void add(Account a) { accounts.put(a.id(), a); }

        // VULNERABILITY, only used to illustrate why not to do this.
        String unsafeByEmail(ExternalUser x) {
            for (Account a : accounts.values()) {
                if (a.email().equalsIgnoreCase(x.email())) {
                    return "AUTH:" + a.id();
                }
            }
            return "NO_MATCH";
        }

        String safeLogin(ExternalUser x) {
            if (!x.tokenValidated()) return "REJECT_UNVERIFIED";
            if (!approvedIssuer.equals(x.issuer()))
                return "REJECT_UNTRUSTED";
            String localId = links.get(
                new ExternalKey(x.issuer(), x.subject()));
            if (localId == null) return "LINK_REQUIRED";
            Account account = accounts.get(localId);
            if (account == null || !account.active())
                return "DENY_DISABLED";
            return "AUTH:" + account.id();
        }

        String link(ExternalUser x, LinkProof p, long now) {
            if (!x.tokenValidated()
                    || !approvedIssuer.equals(x.issuer()))
                return "REJECT_UNTRUSTED";
            if (!p.recentReauth() || !p.secondIdpVerified()
                    || !p.sessionAndStateBound()
                    || now >= p.expiresAt()
                    || usedProofs.contains(p.nonce()))
                return "PROOF_REQUIRED";
            Account account = accounts.get(p.localId());
            if (account == null || !account.active())
                return "DENY_DISABLED";
            ExternalKey key = new ExternalKey(x.issuer(), x.subject());
            String owner = links.get(key);
            if (owner != null && !owner.equals(p.localId()))
                return "LINK_CONFLICT";

            usedProofs.add(p.nonce());
            if (owner != null) return "ALREADY_LINKED";
            links.put(key, p.localId());
            return "LINKED";
        }
    }

    public static void main(String[] args) {
        Service s = new Service();
        s.add(new Account("u-104", "alice@example.org", true));
        s.add(new Account("u-205", "bob@example.org", true));

        String issuer = "https://idp.partner.example/realms/workforce";
        ExternalUser alice = new ExternalUser(
            issuer, "subject-A7", "alice@example.org", true, true);
        ExternalUser attacker = new ExternalUser(
            issuer, "subject-B9", "alice@example.org", true, true);

        System.out.println("unsafeAttacker=" +
            s.unsafeByEmail(attacker));
        System.out.println("safeAttacker=" +
            s.safeLogin(attacker));

        LinkProof weak = new LinkProof(
            "u-104", false, true, true, 200, "nonce-one");
        System.out.println("weakProof=" +
            s.link(alice, weak, 100));

        LinkProof approved = new LinkProof(
            "u-104", true, true, true, 200, "nonce-two");
        System.out.println("linkAlice=" +
            s.link(alice, approved, 100));
        System.out.println("loginAlice=" +
            s.safeLogin(alice));

        ExternalUser renamed = new ExternalUser(
            issuer, "subject-A7", "alice.new@example.org",
            true, true);
        System.out.println("emailChange=" +
            s.safeLogin(renamed));
        System.out.println("attackerStillUnlinked=" +
            s.safeLogin(attacker));

        LinkProof otherOwner = new LinkProof(
            "u-205", true, true, true, 200, "nonce-three");
        System.out.println("linkOtherOwner=" +
            s.link(alice, otherOwner, 100));
        System.out.println("proofReplay=" +
            s.link(attacker, approved, 100));

        ExternalUser unverified = new ExternalUser(
            issuer, "subject-fake", "alice@example.org",
            true, false);
        System.out.println("invalidToken=" +
            s.safeLogin(unverified));
    }
}
~~~

### 9.2. Run command

~~~bash
javac --release 17 AccountLinkingSafetyDemo.java
java AccountLinkingSafetyDemo
~~~

**Exact expected stdout:**

~~~text
unsafeAttacker=AUTH:u-104
safeAttacker=LINK_REQUIRED
weakProof=PROOF_REQUIRED
linkAlice=LINKED
loginAlice=AUTH:u-104
emailChange=AUTH:u-104
attackerStillUnlinked=LINK_REQUIRED
linkOtherOwner=LINK_CONFLICT
proofReplay=PROOF_REQUIRED
invalidToken=REJECT_UNVERIFIED
~~~

**Explanation:**

- `unsafeAttacker`: an attacker subject with a matching email gains Alice's account permissions if the app auto-links by email.
- `safeAttacker`: no `issuer+sub` link ⇒ cannot log into the old local account.
- `weakProof`: missing recent local reauth ⇒ no link created.
- `linkAlice`: creates link only with proof of both the local account and external subject.
- `emailChange`: address changed while `issuer+subject` remained identical ⇒ local account stays the same.
- `linkOtherOwner`: subject already belonging to Alice cannot be transferred to Bob.
- `proofReplay`: an already-used nonce cannot be reused to link the attacker.
- `invalidToken`: an unverified token is never sufficient for lookup/linking.

**Critical limitations:** This is a simulation, not for production. The code lacks HTTPS, real OIDC token verification, tenants, database transactions, and a distributed nonce store. `HashMap` and `HashSet` do not prevent races across multiple nodes. Proof flags must be determined server-side via validated sessions/callbacks, never asserted by the browser.

## 10. Spring Security OIDC: Rejecting Unlinked Accounts

A Spring Boot sample can configure `OidcUserService` to load the user from a verified IdP and then allow only an exact-match `iss+sub` in a link store. The demo below uses **an admin-configured linked subject** so it does not imply email auto-linking. In production, replace static config with a DB repository storing active local accounts, tenants, approved identity links, and roles.

### 10.1. Project structure

~~~text
safe-oidc-link/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/safelink/
    │   ├── SafeLinkApplication.java
    │   ├── SafeLinkSecurityConfig.java
    │   └── MeController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'safe-oidc-link'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

`src/main/java/com/example/safelink/SafeLinkApplication.java`:

~~~java
package com.example.safelink;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLinkApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLinkApplication.class, args);
    }
}
~~~

### 10.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          workforce:
            issuer-uri: "${OIDC_ISSUER}"

app:
  linked:
    approved-issuer: "${APP_APPROVED_ISSUER:}"
    approved-subject: "${APP_APPROVED_SUBJECT:}"
    local-enabled: "${APP_LOCAL_ENABLED:false}"

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Environment variables must come from **admin-approved configuration**, never from client queries. The demo permits only one admin-configured `issuer+subject` with an active local account; if config is missing, it **denies by default**.

### 10.3. SafeLinkSecurityConfig.java

~~~java
package com.example.safelink;

import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SafeLinkSecurityConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> linkedOidcUserService(
            @Value("${app.linked.approved-issuer}")
            String approvedIssuer,
            @Value("${app.linked.approved-subject}")
            String approvedSubject,
            @Value("${app.linked.local-enabled}")
            boolean localEnabled) {

        OidcUserService delegate = new OidcUserService();

        return userRequest -> {
            // Spring already validated OIDC before delegate returned the user.
            OidcUser external = delegate.loadUser(userRequest);
            String issuer = external.getIdToken()
                .getClaimAsString("iss");
            String subject = external.getSubject();

            // DO NOT call findByEmail(external.getEmail())!
            if (!localEnabled
                    || approvedIssuer.isBlank()
                    || approvedSubject.isBlank()
                    || !approvedIssuer.equals(issuer)
                    || !approvedSubject.equals(subject)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("identity_not_linked")
                );
            }

            // This role represents an approved local role.
            // Never derive from email/UPN/displayName emitted by the IdP.
            Set<GrantedAuthority> localAuthorities = Set.of(
                new SimpleGrantedAuthority("APP_ORDER_READ")
            );

            return new DefaultOidcUser(
                localAuthorities,
                external.getIdToken(),
                external.getUserInfo()
            );
        };
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser>
                linkedOidcUserService) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").hasAuthority("APP_ORDER_READ")
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(info -> info
                    .oidcUserService(linkedOidcUserService)
                )
            )
            .build();
    }
}
~~~

Explanation:
- `OidcUserService` receives a principal that already passed OIDC protocol validation performed by Spring's client, without hand-decoding JWTs.
- `iss` is read from the ID Token and `sub` from `OidcUser`; login proceeds only when **both match exactly** and the local account is active (`localEnabled` in the demo).
- `email` plays no part in lookup. Even with `email_verified=true`, an unlinked external subject fails.
- Authorities come from the approved local profile (hardcoded `APP_ORDER_READ` in the demo for illustration). Production must query the local DB and check real active/tenant/role state; **never** hardcode permissions for all OIDC users.
- `DefaultOidcUser` still carries the OIDC subject; if business logic needs the local user ID as principal name, build a separate audited principal/mapping layer rather than swapping `subject` for email as the local ID.
- If the subject has been revoked, the production repository must deny and terminate sessions/tokens per policy.
- This demo **has no account-linking UI**. Adding a UI must follow the explicit linking flow in section 7, never letting the OIDC callback auto-link.
- CSRF, state, nonce, issuer, audience, signature, session fixation, and PKCE must be tested against a real IdP and chosen version; never disable protections by default when customizing the user service.

### 10.4. MeController.java

~~~java
package com.example.safelink;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "signInUrl", "/oauth2/authorization/workforce",
            "status", "Only preapproved issuer+subject may sign in");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
            "externalSubject", authentication.getName(),
            "permission", "APP_ORDER_READ"
        );
    }
}
~~~

### 10.5. Running and Testing

~~~bash
./gradlew bootRun
~~~

Example test environment variables:

~~~text
OIDC_ISSUER=https://idp.partner.example/realms/workforce
OIDC_CLIENT_ID=approved-client-id
OIDC_CLIENT_SECRET=secret-from-vault
APP_APPROVED_ISSUER=https://idp.partner.example/realms/workforce
APP_APPROVED_SUBJECT=subject-approved-from-real-idp
APP_LOCAL_ENABLED=true
~~~

`.example` values are illustrative; you need a real IdP, OIDC metadata, client registration, HTTPS callback, and an approved subject. The code does not start an IdP. The `/me` output depends on the real IdP's subject/claims.

Test steps:
1. Approved subject logs in and receives `APP_ORDER_READ`.
2. Another subject with the same email hits `identity_not_linked`; never auto-connected to the account.
3. Approved subject changes email without changing `sub`; link remains valid.
4. Disable `APP_LOCAL_ENABLED`; even the approved subject is DENIED.
5. Changed issuer/wrong registration; framework/lookup rejects.
6. Invalid OIDC state/nonce/signature/audience; Spring rejects before local mapping.
7. Unlinked accounts must be directed to onboarding/explicit linking outside the login flow without minting permissions.

**Version note:** These snippets target Spring Security 6.x APIs; upgrading versions or switching OIDC clients requires rebuilding and retesting. Production security also requires persistent DB linking, auditing, role lifecycles, user disabling, tenant isolation, session revocation, key rotation, and security patching.

## 11. Spring SAML/Kerberos/LDAP/SCIM: Applying the Same Principles

### 11.1. SAML2

With Spring `saml2Login`:
- Verify Assertion signature, issuer, audience, recipient, `InResponseTo`, and time conditions.
- Use an approved persistent identifier scoped by IdP/SP; pay attention to `NameID` format and qualifiers.
- If the Identity Provider only sends `mail`/email `NameID`, **do not auto-link to an old local user**; require an immutable directory ID or approved proof flow.
- Never trust user-submitted emails, even when XML formatting looks valid.
- Permissions from SAML attributes require a separate trust contract with local authorization.

### 11.2. Kerberos

Kerberos realm/principal and service ticket validation are one external identity source. When connecting to a local account previously used with OIDC:
- Never auto-merge by UPN/email.
- Use an approved directory object anchor and realm/scope.
- Migration from Kerberos → OIDC requires a crosswalk from an authoritative directory or explicit two-method proof.
- Disabled accounts, group/tenant memberships, and local permissions must still be checked.

### 11.3. SCIM directory provisioning

SCIM can create new local accounts based on an authoritative `externalId` scoped per connector. If an OIDC login arrives before the SCIM link, never search by email to sign into an old account; return a provisioning-pending status or direct to help desk. When SCIM sets `active=false`, revoke local account/sessions per policy—never merely update contact email.

### 11.4. Do not treat an email change as an identity change

An OIDC-linked account may update its contact email after verifying the contact. It still carries the same `(iss,sub)`. A new subject paired with the same old email is not a "minor update"—it is a **change in identity binding** requiring explicit linking/migration proof.

## 12. Revocation, Recovery, and Migration

### 12.1. Unlinking

Require recent reauthentication, CSRF protection, confirmation of local account ownership, and evaluation of whether the user still has another login method. On unlink, revoke related cached sessions/refresh tokens, audit, and notify the account owner. Never let a weak session remove every recovery method.

### 12.2. When a user loses access to their old method

Current email OTP **is not enough** to prove ownership of an old local account if the mailbox could have been recycled. A manual recovery workflow requires:
1. Audited request intake; prevent user enumeration.
2. Verification of authoritative HR/directory immutable IDs and personnel policy.
3. Risk-appropriate identity proofing/step-up/approval.
4. Verifying the new external subject via a trusted IdP.
5. Reviewing old links, disabling stale credentials, and revoking sessions/tokens an attacker might hold.
6. Committing the new link with a unique constraint, audit log, and notification.

### 12.3. IdP migration

~~~text
Old SAML: issuer=old-idp, persistent NameID=p-17
New OIDC: iss=new-idp, sub=s-90
Local: user-104
~~~

Migrate only with a trusted crosswalk (immutable HR/directory object), a double-auth proof process, or verified administrator approval. Never run a migration script joining `old.email=new.email` without proof.

### 12.4. Email reuse and rehires

A new person receiving an old address must receive a **new** local account unless proof confirms it is the same identity being restored by the organization. Rehired employees may need a new account or reactivation per policy; matching email does not decide it automatically. A disabled old local account must never be auto-enabled by an external login.

## 13. Authorization and Sessions After Linking

Even when a link is valid, still evaluate:
- User active/locked/revoked state and credential/session age;
- Local tenant membership and resource tenant isolation;
- `GrantedAuthorities` from approved sources;
- Object-level authorization (owner of the order/report);
- MFA/step-up for sensitive resources;
- Session fixation/CSRF/SameSite cookies and logout;
- Logout/revocation when a link is removed or an account is disabled.

**An attacker's MFA on the attacker's own account does not prove they own the victim's local account.** `email_verified=true` and strong MFA on an external login still cannot substitute for account-link proof.

## 14. Integration Testing

| ID | Scenario | Required outcome |
| --- | --- | --- |
| I01 | Valid linked OIDC `iss+sub`, local active. | Logs into right local user. |
| I02 | Email matches local, different subject. | `LINK_REQUIRED`, no auto-login. |
| I03 | `email_verified=true` but unlinked. | Still `LINK_REQUIRED`. |
| I04 | Email changes while issuer/sub stays constant. | Preserves local identity. |
| I05 | Two subjects in the same issuer share one email. | Do not auto-merge. |
| I06 | Same subject string across two issuers. | Do not map together. |
| I07 | Victim leaves, mailbox recycled. | New holder does not inherit old local account. |
| I08 | Attacker pre-registers local account with victim's email. | Victim's SSO does not auto-attach to attacker's account. |
| I09 | Entra guest shares employee email. | No cross-tenant/guest takeover. |
| I10 | Different Entra `tid`. | Not treated as same oid-scope. |
| I11 | Pairwise sub changes on client/sector migration. | Evidenced migration, no email join. |
| I12 | SAML `persistent NameID` with approved IdP/SP scope. | Resolves per link contract. |
| I13 | SAML `emailAddress NameID`. | Never used as immutable link key. |
| I14 | SAML `transient NameID`. | Never creates persistent link from transient value. |
| I15 | Kerberos UPN/email changes. | Directory immutable ID mapping keeps local account. |
| I16 | LDAP DN changes on OU move. | Does not spawn a new account from the new DN. |
| I17 | Two SCIM connectors share `externalId`. | Do not mix provisioning domains. |
| I18 | OIDC login arrives before SCIM Create. | `PROVISIONING_PENDING`/`LINK_REQUIRED`, no email fallback. |
| I19 | SCIM `active=false`. | Disable/revoke per lifecycle. |
| I20 | Link request lacks local reauth. | `PROOF_REQUIRED`. |
| I21 | Link intent expired TTL. | Reject. |
| I22 | Link callback has different session generation. | Reject, prevent account switching. |
| I23 | Replayed state/nonce or `LinkIntent`. | Reject. |
| I24 | External subject already linked to user A; user B requests link. | `CONFLICT`. |
| I25 | Concurrent linking of same subject. | Unique constraint and atomic guard; no double-link. |
| I26 | Invalid OIDC signature/issuer/audience/nonce. | Framework rejects before lookup. |
| I27 | Browser injects `iss/sub/local_user_id` in query. | Untrusted, reject. |
| I28 | IdP returns user whose local account is disabled. | DENY. |
| I29 | Existing link has local `READ` role while token claims `admin`. | Does not auto-grant `APP_ADMIN_EXPORT`. |
| I30 | Tenant A linked user accesses Tenant B resource. | DENY resource ownership. |
| I31 | Alias/dot/plus normalization makes two emails match. | Never use email normalization for linking. |
| I32 | Two local accounts share the same email. | Never auto-pick the first account. |
| I33 | Attacker uses recycled mailbox email OTP to claim old local account. | Disallow merging solely via OTP. |
| I34 | Link created, then email changes in IdP. | Exact `iss+sub` still logs in properly. |
| I35 | Migration lacks trusted crosswalk despite matching email. | Deny/manual recovery. |
| I36 | Migration has trusted immutable ID crosswalk. | Reviewed/atomic link, audited. |
| I37 | Link revoked while old session remains alive. | Session/token revocation per policy. |
| I38 | Login with non-allowlisted issuer sharing admin email. | Reject issuer, no link. |
| I39 | Logs contain raw ID Token/subject/email in metrics. | QA fail / redaction required. |
| I40 | Provider/client config changes without approved link proof. | Never silently transfer account owner. |

### 14.1. Lab A — running Java 17

1. Run `AccountLinkingSafetyDemo` and observe `unsafeAttacker=AUTH:u-104`.
2. Compare `safeAttacker=LINK_REQUIRED` and `weakProof=PROOF_REQUIRED`.
3. Verify `emailChange=AUTH:u-104` despite the email change.
4. Test conflict when attaching a subject already belonging to another user.
5. Discuss why the demo only illustrates the mechanism and must never be used directly as an auth server.

### 14.2. Lab B — with two OIDC subjects

1. Configure a test IdP with two accounts sharing an email (where the provider allows it) but different `sub` values.
2. Preapprove linking subject A while leaving subject B unlinked.
3. Log in as A successfully; B fails despite matching email.
4. Change A's email and confirm A stays accurately linked.
5. Disable the local account and confirm the production repo denies access.
6. Test replaying the OIDC callback, expired link intent, and concurrent link requests.

### 14.3. Lab C — SCIM, guests, and migration

1. Create SCIM resources from two provisioning clients with colliding `externalId`.
2. Test email reuse, Entra guest tenants, and aliases.
3. Build a migration crosswalk on immutable IDs with auditing/dry-run.
4. Verify no email joins appear in migration SQL.
5. Revoke links and sessions when an incident is detected.

## 15. Monitoring and Alerting

Suggested metrics (not automatically included in Spring):

~~~text
identity_login_total{provider,result}
identity_link_lookup_total{provider,result}
identity_link_approval_total{provider,result}
identity_link_conflict_total{provider}
identity_link_duplicate_email_total{provider}
identity_link_recovery_total{status}
identity_subject_migration_total{provider,status}
identity_deprovision_total{connector,result}
identity_revocation_total{reason}
~~~

Never use email, `sub`, user ID, or raw tokens as metric labels due to PII leakage and high cardinality. Audit records should use only opaque references or hashed subjects per retention policy.

High-priority alerts: same email appearing across multiple issuers/subjects; link owner reassigned; spike in link failures; SCIM `externalId` changed; disabled account still logging in; admin role appearing right after an email update; migration collisions.

## 16. Incident Runbook for Account Takeover via Email Auto-Linking

1. **Disable the email auto-link path** in login/migration/onboarding; where possible, keep logins via existing safe exact links running.
2. **Scope the impact** via audit link events and local user IDs, not merely querying by email.
3. **Revoke** sessions, refresh tokens, API keys, OAuth authorizations, and suspect external links per policy.
4. **Preserve evidence** (audits, immutable IDs, provisioning history, redacted token metadata) for investigation.
5. **Verify legitimate owners** via authoritative HR/directory immutable IDs, not just the current mailbox.
6. **Restore** the proper local user/tenant/roles through a reviewed process, rotate secrets, and force reauthentication.
7. **Notify** account owners and security teams per policy without exposing personal data.
8. **Audit all prior links** created by email and every migration script containing an email join.
9. **Remediate the system** with exact keys, proof flows, database unique constraints, fail-closed responses, and regression tests.
10. **Monitor recovery**: a rise in `LINK_REQUIRED` after removing auto-linking is expected; never re-enable auto-linking just to reduce support tickets.

## 17. Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "OIDC `email_verified` is true so it's enough." | Current mailbox does not prove historical account ownership. | Existing link / explicit proof. |
| "Email is unique in local DB so no collision is possible." | Two owners can hold the same email at different times. | Immutable local ID. |
| "A signed token is all we need." | Signed by issuer does not mean owning the local user. | Separate identity linking. |
| "IdP MFA suffices to link an admin." | Attacker using MFA on attacker's account can still hijack. | Recent local reauth + second IdP proof. |
| "SCIM `externalId` is globally unique." | Collides across provisioning domains. | Scope by connector. |
| "SAML email `NameID` is always stable." | Email changes and gets recycled. | Persistent `NameID`/immutable ID per contract. |
| "Entra email/UPN is the primary key." | Changes/reuse lead to takeover. | Entra `tid+oid` or OIDC `iss+sub` per contract. |
| "If no link is found, call `findByEmail`." | Backdoor takeover. | `LINK_REQUIRED`. |
| "`ON CONFLICT` updates `local_user_id`." | Auto-transfers account owner. | Unique + rollback/review. |
| "Anyone with email OTP gets the old user's history." | Mailbox-recycling takeover. | High-assurance recovery and authoritative sources. |
| "Changing email changes the account." | Data loss, account mix-up. | Keep local ID + external key. |
| "Unlinking is enough." | Attacker may still retain sessions/tokens. | Revoke all related credentials. |
| "Linked account skips role checks." | Privilege escalation. | Local active/tenant/resource authorization. |

## 18. Production Checklist

- [ ] Never use `findByEmail` to connect an OIDC/SAML login to an existing local account.
- [ ] Identity keys include verified issuer/realm/connector source and stable subject/immutable ID.
- [ ] OIDC `iss+sub`, Entra `tid+oid`, SAML `NameID` qualifiers, and SCIM source-scoping are used per contract.
- [ ] `email`/`email_verified` are treated as contact metadata, never account ownership proof.
- [ ] OIDC/SAML protocol validators check issuer/audience/signature/time/state/nonce before linking.
- [ ] Local user IDs are never recycled; changing email does not change local identity.
- [ ] Disabled existing local accounts or wrong tenants DENY without falling back to email.
- [ ] Auto-provisioning new accounts, if enabled, is separated from linking existing accounts and grants minimal privileges.
- [ ] New links require recent local reauthentication, CSRF, external IdP proof, and a short-lived one-time intent.
- [ ] Database unique constraints/transactions prevent races and unauthorized owner transfers.
- [ ] Clients are never allowed to supply arbitrary local IDs/tenants/issuers via query params.
- [ ] Unlink/relink/migration flows include auditing, notifications, approvals, and session/token revocation.
- [ ] SCIM `active=false`, mailbox reuse, guests, aliases, and pairwise `sub` migrations are tested.
- [ ] Legacy account recovery requires authoritative proof, never just a current email OTP.
- [ ] `APP_ADMIN_EXPORT` and high privileges derive solely from local authorization and step-up policies.
- [ ] Never log tokens, subjects, mailboxes, or credentials in shared observability systems.
- [ ] Anomaly monitoring is active for duplicate emails, cross-tenant link attempts, and subject/issuer changes.
- [ ] Tests I01–I40 or equivalent coverage pass in staging.
- [ ] Spring/OIDC dependencies stay on maintained security releases and are rebuilt/retested against the real version.

## Remember

> **A matching email is never proof that two accounts belong to the same person, even with `email_verified=true`.** Federated logins must use a **verified and already-linked external identity key**, typically OIDC `(iss,sub)`. Creating a new link to an existing local account requires **proof from the local account itself + proof from the external IdP + a one-time intent + an atomic transaction**. When emails change, mailboxes are recycled, IdPs migrate, or provisioning lags, **fail closed/review**—never merge by email.

### Official Documentation and Guides

- [OpenID Connect Core 1.0 `5.7 — Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability): `iss+sub` is stable within scope; email is not guaranteed unique or non-recycled; `email_verified` has limited meaning.
- [OpenID Connect Core 1.0 `8 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes): public/pairwise subjects.
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643.html): stable `id`, `externalId` scoped to provisioning domain.
- [Microsoft Entra — ID Token Claims Reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference): `oid`, `tid`, `sub`, and mutable email/UPN fields.
- [Microsoft Entra — Access Token Claims Reference](https://learn.microsoft.com/en-us/azure/active-directory/develop/access-token-claims-reference): identifying users/tenants via immutable IDs, never using email/UPN as authorization keys.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, `DefaultOidcUser`, and identity/authority mapping.
- [Spring Security — OAuth2/OIDC Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): OIDC registration, Authorization Code, and callback.
- [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html): normalization, email changes, account takeover.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): recovery, reauthentication, MFA, and authorization boundaries.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session lifetime, fixation, and revocation.
- [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): SAML `NameID` formats and qualifiers.
