# Account Provisioning on First Login and the Just-in-Time Provisioning Model

## 1. The Problem: The IdP Has Authenticated the User, but the App Does Not Have Them Yet

In a **Spring Security - federation** system, organizations typically use OpenID Connect (OIDC), SAML 2.0, or CAS for centralized authentication. After successful authentication, the Spring Security application can receive an identity asserted by a trusted IdP. However, a **federated identity** is not the same as a **local account**: the application still needs an account ID to manage data, status, tenant, access permissions, profile, and audit history.

Suppose employee Lan logs into a reporting application via OIDC for the first time. The IdP returns a valid ID Token with `iss=https://login.corp.example` and `sub=person-742`, but the `local_account` table does not yet contain that user. The application can either deny access until an admin creates the account or **provision it upon first login**, known as **Just-in-Time provisioning (JIT)**.

**JIT provisioning** is the process of **finding or creating a local account and binding it to a verified federated identifier**, per application policy, at the time of the first login event. JIT does not replace verifying the OIDC ID Token/SAML assertion/CAS ticket, does not automatically grant business permissions, and does not automatically handle disabling the account when the user leaves the organization.

> **Safety rule:** only run JIT **after** protocol authentication succeeds; bind the local account to a **stable identity key namespaced by the IdP**; use transactions/unique constraints to prevent duplicates; apply initial status and minimal privileges; never auto-link to an existing account merely because the email matches.

**Learning objectives:** understand when JIT is needed and compare it with SCIM/pre-provisioning; design identity keys for OIDC/SAML/CAS; define eligibility policies; write the data model/atomic upsert; configure Spring Security hooks; handle concurrent logins, account linking, deprovisioning, auditing, and common errors; verify with a self-contained Java 17 program.

## 2. Distinguishing Authentication, Provisioning, Linking, and Authorization

| Stage | Question | Proof / mechanism |
| --- | --- | --- |
| **Authentication** | Did the IdP actually authenticate the user? | Spring OIDC/SAML/CAS validator verifies signature, issuer, audience, lifetime, and protocol conditions. |
| **Identity mapping** | Which account does this federation key correspond to? | Lookup by verified issuer + subject; or SAML IdP-qualified identifier per contract. |
| **Provisioning** | If no account exists yet, may one be created? | JIT policy based on issuer, tenant, cohort, risk, and approval. |
| **Account linking** | May a new identity be attached to an existing account? | Authenticated session of the existing account or identity-proofing/admin-approved workflow; never auto-link by email. |
| **Authorization** | What may the user do in the application? | Local entitlements/authorities, tenant, resource ownership, and method security. |
| **Lifecycle** | What if the user is locked, transferred, or offboarded? | SCIM/HR sync, local status, session and token revocation. |

An OIDC ID Token with a valid signature does not mean the new account may approve invoices; a database account does not prove who currently holds the IdP session. **Authentication, provisioning, and authorization must be evaluated sequentially yet independently.**

### 2.1. Illustrative input and output states

~~~text
Verified OIDC authentication:
  iss = https://login.corp.example
  sub = a7c9b2-pairwise-subject
  email = lan@corp.example
  email_verified = true

Local directory:
  No federated_identity for (iss, sub)

Policy:
  Trusted issuer, tenant=finance-vn, eligible employee
  JIT allowed, manual approval required for business permissions

JIT result:
  local_account id = u-742
  status = PENDING
  federated_identity(iss, sub) -> u-742
  authorities = [app:onboarding]
  business privileges = none
~~~

Even if Lan passed MFA at the IdP, account `u-742` may remain `PENDING` if the application requires approval. On subsequent logins, the resolver must return **that exact `u-742`**; never create a new account keyed by email, cookie, session, or timestamp.

## 3. Comparing Account Provisioning Models

| Mechanism | When is the account created or updated? | Strengths | Limitations |
| --- | --- | --- | --- |
| **Manual pre-provisioning** | Admin creates the account before login. | Tight control, clear approval. | Slow, high manual effort. |
| **HR/batch synchronization** | Periodic job reads directory/HR. | Account exists before user access. | Sync lag, handling inconsistent data. |
| **SCIM 2.0** | IdP/IGA proactively calls the app's Users/Groups API. | Supports create/update/disable per lifecycle and reconciliation. | Requires SCIM service, API protection, mapping, retries. |
| **JIT provisioning** | On first login with a verified identity. | Created right when needed, low manual ops. | Users who haven't logged in have no record; doesn't push disables on offboarding. |
| **Account linking** | When an existing account is connected to a new identity. | Preserves historical data/permissions. | Account takeover if merged solely on matching email. |
| **Login-time profile sync** | Updates permitted claims on every login. | Name/email/department stay fresher. | Does not automatically alter permissions or lifecycle state. |

**JIT + SCIM** is often a strong combination: SCIM/HR proactively disables accounts, while JIT fills in missing accounts when users log in. However, when both write to the database, you must design **precedence, idempotency, and conflict policies**; JIT must never overwrite a `DISABLED` state set by SCIM.

According to NIST SP 800-63C, JIT creates an account at the RP upon receiving an unknown verified federated identifier, or uses policy-driven account resolution; provisioning must complete **before establishing an authenticated session at the RP**. This reminds us never to redirect the user into the app with full business permissions if the account-creation transaction has not committed.

## 4. OIDC: Using the iss + sub Pair as the Identity Key

OpenID Connect Core §5.7 specifies the **`iss` (issuer) and `sub` (subject)** pair in a verified ID Token as the stable key a Relying Party can rely upon; `sub` is unique per issuer, not guaranteed globally unique.

~~~text
IdP A:
  issuer  = https://login.corp.example
  subject = 00123

IdP B:
  issuer  = https://partner-login.example
  subject = 00123

=> Two different federated identities despite the same subject.
~~~

Conversely:

~~~text
Login 1:
  iss=https://login.corp.example, sub=00123
  email=lan.old@corp.example

Login 2:
  iss=https://login.corp.example, sub=00123
  email=lan.new@corp.example

=> Same federated identity; do not create a different account just because email changed.
~~~

**Do not use `email`, `name`, `preferred_username`, or `phone_number` as substitute linked account keys.** They can be absent, changed, duplicated, recycled, or carry different semantics across issuers.

### 4.1. Is email_verified=true enough for auto-linking?

**No.** `email_verified=true` only states that the OP performed a check on control of the email address at the OP's chosen time and method. It does not prove ownership of a **specific local account**, does not prove the email is unique across all IdPs, and does not guarantee the email was never reassigned to someone else.

A takeover scenario:

~~~text
Local admin account #admin-7:
  email = finance.manager@corp.example
  permissions = [payments:approve]

Partner IdP assertion:
  iss = https://partner-id.example
  sub = attacker-sub
  email = finance.manager@corp.example
  email_verified = true

Wrong approach:
  findLocalUserByEmail(email) -> #admin-7
  attach partner identity to #admin-7
  => attacker gains the admin's business permissions.
~~~

**Correct:** the resolver only looks up bindings by **verified issuer + subject**. If no binding exists, create a **new** low-privilege account per policy or require account linking with **independent authentication evidence**. Never merge automatically just because emails match.

### 4.2. Public sub and pairwise sub

OIDC defines **public subject identifiers** and **pairwise subject identifiers**. With pairwise, the same person can receive different `sub` values depending on the application's sector identifier. When changing IdP, client registration, or sector identifier:
- The federation key may change even though it is the same person.
- Do not auto-migrate by email.
- Require an **approved identity linking/migration** step with auditing, rollback, and ownership verification.
- Separate the stable local user ID from the external subject key to preserve data integrity.

If multiple tenants share the same issuer, tenant resolution must follow **verified registration and membership policy**, not accept a `tenant=finance` query parameter as an implicit grant.

### 4.3. ID Token and UserInfo

Classification:
- **ID Token**: source of verified `iss`/`sub`, audience/client ID, and authentication event claims.
- **UserInfo**: can supply email/name/picture; if used, verify its subject matches the ID Token's.
- **Groups/custom claims**: only consider as input to approved role mapping; never auto-convert to `ROLE_ADMIN`.
- **`acr`/`amr`/`auth_time`**: useful when policy requires assurance or recent authentication; never infer "MFA" from `email_verified`.

Never take `sub` from a frontend-submitted JSON body. All JIT must execute inside Spring's trusted authentication flow, after validators.

## 5. SAML 2.0: Identifiers Must Follow the IdP/SP Contract

In Spring SAML2 Login, the OpenSAML provider verifies `SAMLResponse`, after which Spring creates a `Saml2Authentication` with `Saml2AuthenticatedPrincipal`. `principal.getName()` typically comes from `NameID`, **but `NameID` is not always stable**.

| Identifier from SAML | Suitable for long-lived binding? | Notes |
| --- | --- | --- |
| **Persistent NameID** | Usually yes, if the IdP guarantees immutability/non-reuse per SP. | Namespace with IdP `entityID`, format, and `NameID` qualifiers as needed. |
| **Transient NameID** | No. | Changes across sessions; JIT would create an account on every login. |
| **EmailAddress NameID** | Not by default. | Email can change/be recycled; do not auto-link. |
| **Immutable employee/person ID** | Possible, if authoritatively provided and signed/asserted by the IdP. | Ensure uniqueness and tenant/issuer namespace. |
| **Multi-valued attributes** | Depends on field. | Do not assume the first list element is a unique subject without a contract. |

Example identity binding:

~~~text
IdP entityID:
  https://sso.partner.example/idp

NameID format:
  urn:oasis:names:tc:SAML:2.0:nameid-format:persistent

NameID value:
  opaque-persistent-4f21

Local binding:
  (idp_entityID, NameIDFormat, NameIDValue, relevant qualifiers)
       -> local_account u-924
~~~

**Do not rely solely on `RelyingPartyRegistrationId` as an immutable IdP identity**: it is a Spring configuration key that can change across deployments. If the IdP uses a transient `NameID`, negotiate a **persistent identifier** or a contracted immutable attribute—never patch around it with "matching email merges".

JIT must run **after** validating signature, issuer, audience, recipient/destination, `InResponseTo`, `SubjectConfirmation`, `Conditions`/time, and replay. **Never manually parse browser-submitted XML `SAMLResponse` and call `createUser`.**

## 6. CAS, Kerberos, and Proxy Pre-Auth: Different Tokens, Same Principles

- **CAS:** identity comes from `TicketValidator` verifying the service ticket with the CAS Server; assess the stability/namespace of the CAS principal.
- **Kerberos:** principal includes a realm, e.g., `alice@CORP.EXAMPLE`; never strip the realm in multi-realm organizations.
- **Pre-auth HTTP header:** only use for JIT if a trusted gateway has authenticated the user, **strips/overwrites all client-supplied identity headers**, secures gateway→backend via mTLS/network policy, and blocks direct backend access.
- **OIDC/SAML:** use protocol-compliant validators. Never treat raw JWT/SAML XML or a self-asserted header as evidence for JIT.

If the same username is issued by two different realms/issuers, merging them into one local account is **account linking**, not implicit JIT.

## 7. JIT Eligibility: Who Is Allowed to Create an Account?

Before `INSERT`, establish an explicit policy:

1. **Trusted issuer/IdP allowlist**: accept results only from configured IdPs; no dynamic trust from user-supplied URLs.
2. **Valid RP registration**: client/audience/redirect URI or SAML `entityID`/ACS has been verified.
3. **Stable external subject**: non-null/non-blank, properly namespaced, avoiding temporary/inconsistent identifiers.
4. **Server-side tenant**: derived from authoritative registration/membership, not self-asserted query params.
5. **Eligible cohort**: employees/partners/customers entitled to onboarding per contract; IdP self-signup does not imply auto-access.
6. **Assurance/freshness** if needed: check verified `acr`/`amr`/`auth_time` or SAML `AuthnContext` per policy.
7. **Tombstone/deny state**: locked, banned, or offboarded users must not be auto-recreated.
8. **Quotas and anti-abuse**: rate-limit JIT per tenant/issuer, mitigate login storms, monitor account creation spikes.
9. **Minimal default privileges**: new accounts start `PENDING`/onboarding or low-privilege `ACTIVE` if an approval rule applies.
10. **Attribute minimization and auditing**: store only genuinely needed fields, never store entire tokens/assertions.

### 7.1. Account statuses

| Status | Meaning | Permitted behavior |
| --- | --- | --- |
| **PENDING** | Newly created, awaiting profile completion/approval. | Onboarding only (if policy allows), no business access. |
| **ACTIVE** | Approved with application permissions. | Access strictly per approved authorities/tenant/resources. |
| **SUSPENDED** | Temporarily locked due to risk/violation. | No new permissions granted; requires review. |
| **DISABLED** | Offboarded/revoked. | Deny login and never auto-reactivate. |
| **DELETED/TOMBSTONED** | Previously deleted/banned identity, marked against recreation. | Recoverable only through an approved workflow. |

**Creating a `PENDING` local account may allow an onboarding session**, but business endpoints must verify actual entitlements such as `reports:read`, not simply `authenticated()`. Under strict requirements, `PENDING` must not create any application session at all; document the policy clearly.

### 7.2. Decision flow

~~~text
Verified OIDC/SAML/CAS Authentication
                  |
                  v
Trusted issuer/tenant/subject?
      No ----------+-------> DENY, no local account
                  |
                 Yes
                  |
                  v
Find federated_identity by stable key
       |                    |
     Found                Missing
       |                    |
       v                    v
Load local account    JIT allowed for cohort?
       |                 No ---> DENY / invitation
       |                    |
       |                   Yes
       |                    |
       |            Atomic create+bind transaction
       |                    |
       +----------+---------+
                  |
                  v
Check local account status
       Disabled/Suspended -> DENY
       Pending -> onboarding-only (if allowed)
       Active -> approved app authorities
                  |
                  v
Create only allowed Authentication / session
                  |
                  v
Check tenant + ownership + permission on each resource
~~~

**Never jump straight from IdP login success to `ROLE_USER` or `ROLE_ADMIN` before evaluating local admission and permissions.**

## 8. Data Model: Local Account and Federated Identity

Separate the internal key from the IdP key so foreign keys do not break when issuer/client/subject migrate through a verified workflow.

~~~sql
CREATE TABLE local_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL
      CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','DISABLED')),
    email VARCHAR(320),
    display_name VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    disabled_at TIMESTAMPTZ
);

CREATE TABLE federated_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES local_account(id),
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    protocol VARCHAR(20) NOT NULL,
    bound_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ,
    CONSTRAINT uq_fid_issuer_sub UNIQUE (issuer, subject)
);

CREATE INDEX idx_fid_account
    ON federated_identity (account_id);

CREATE TABLE app_entitlement (
    account_id BIGINT NOT NULL REFERENCES local_account(id),
    tenant_id VARCHAR(100) NOT NULL,
    permission VARCHAR(100) NOT NULL,
    source VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, tenant_id, permission)
);
~~~

**This schema is a PostgreSQL example** for applications with one primary tenant per local account and global identity mapping. If an account spans multiple tenants, split out a membership table. If the same external identifier is intentionally mapped to multiple accounts **per tenant**, the unique key and entity model must express that policy transparently; never add `tenant` to the key merely to bypass collision protection.

### 8.1. Why is UNIQUE(issuer, subject) necessary?

Two first-login requests hitting two pods can execute concurrently:

~~~text
Pod A: SELECT (iss, sub) -> NOT_FOUND
Pod B: SELECT (iss, sub) -> NOT_FOUND
Pod A: CREATE local_account #101
Pod B: CREATE local_account #102
Pod A: BIND (iss, sub) -> #101
Pod B: BIND (iss, sub) -> #102
~~~

Without a constraint, one federated identity can get bound to two accounts. **App-level `SELECT` then `INSERT` is not enough** due to races. A database unique constraint (alongside transactions and the right identity key) prevents inconsistent state; a distributed lock is only supplementary and cannot replace DB integrity.

### 8.2. Atomic create + bind

Safe algorithm:

~~~text
resolveOrProvision(verifiedIdentity):
  1. Confirm issuer, subject, tenant and JIT policy.
  2. Look up federated_identity(issuer, subject).
     If exists, load account + check status/tenant, return.
  3. Begin database transaction:
       insert local_account(status=PENDING, tenant)
       insert federated_identity(account_id, issuer, subject)
       commit both records
  4. If UNIQUE conflict:
       rollback WHOLE transaction (including local account insert)
       open a clean transaction/read
       load the winner binding by (issuer, subject)
       check account status and tenant
       return winner
  5. Do not establish business session until binding committed.
~~~

Specifically, when a Spring transaction hits a unique violation, the transaction may already be marked rollback-only or the DB transaction may have failed; **do not catch the exception and attempt to commit within the same transaction**. Place conflict handling in an outer caller outside the transaction, roll back cleanly, and look up the winner in a fresh transaction. If a timeout leaves commit outcome uncertain, reconcile via the natural key once connectivity recovers instead of blindly retrying and flooding records.

Never leave behind a newly created local user without a binding—that is an **orphan account**. If post-commit events must be emitted, use a transactional outbox or reliable event handling; never treat a published event whose DB transaction rolled back as a provisioned account.

## 9. Idempotency and Multi-Node Concurrency

A JIT service must satisfy:

~~~text
Login (issuer-A, sub-1) 1st time -> account #42
Login (issuer-A, sub-1) 2nd time -> same account #42
Login (issuer-A, sub-1) from Pod B concurrently -> same #42
Login (issuer-B, sub-1) -> different identity
Login (issuer-A, sub-2) with same email -> different identity
Login (issuer-A, sub-1) when #42 is DISABLED -> DENY, no new account
~~~

The idempotency key **is not email, timestamp, nonce, session ID, IP, or browser ID**. Use the stable external identity verified by the protocol verifier and namespaced by the issuer/app tenancy contract.

### 9.1. Concurrent SCIM sync and JIT

What can happen:
- SCIM is creating an account for an external identity.
- Simultaneously, the user logs in and JIT finds no account yet.
- One flow wins the transaction; the other hits a unique conflict.

Both must share the **same identity-binding rules**, unique constraints, and status precedence. If SCIM just disabled a user, JIT must never rely on stale state to re-enable them; use transactions/optimistic versioning and deny precedence. Never create a business session solely because the login callback arrived before the disable event finished processing.

### 9.2. Cache eventual consistency

JIT may write to the DB leader while another node reads a stale `NOT_FOUND` from cache and tries to create another account. DB uniqueness still protects you. When status changes to `DISABLED`, a stale cache may allow old logins through; define TTLs and a revocation SLA, and invalidate by account ID/`securityVersion`. For admin/finance privileges, require strong reads or central entitlement checks on critical operations.

## 10. Runnable Java 17: Two Concurrent First Logins

The Java SE program below simulates **the step after successful verified federation**. It uses `ConcurrentHashMap.computeIfAbsent` so two threads requesting the same identity concurrently receive the exact same account within **one JVM**. It also demonstrates not auto-linking by email, not merging two issuers with the same subject, and not reopening a `DISABLED` account.

**This is an algorithmic model**, without OIDC/SAML validation, TLS, DB, HTTP, Spring, or multi-node clustering. Production requires a **database unique constraint + transaction**, never just an in-JVM map.

File **`JitProvisioningDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;

public final class JitProvisioningDemo {

    record Key(String issuer, String subject) {}

    record VerifiedIdentity(
            String issuer, String subject, String email, String tenant) {}

    enum Status { PENDING, ACTIVE, DISABLED }

    static final class Account {
        final long id;
        final String tenant;
        final String emailForDisplay;
        volatile Status status = Status.PENDING;
        volatile Set<String> permissions = Set.of("app:onboarding");

        Account(long id, String tenant, String emailForDisplay) {
            this.id = id;
            this.tenant = tenant;
            this.emailForDisplay = emailForDisplay;
        }
    }

    static final class Directory {
        private final ConcurrentHashMap<Key, Account> accounts =
                new ConcurrentHashMap<>();
        private final AtomicLong nextId = new AtomicLong();

        Account resolveOrProvision(VerifiedIdentity assertion) {
            // Only call after the OIDC/SAML source has been verified.
            if (!Set.of("https://idp-a.example", "https://idp-b.example")
                    .contains(assertion.issuer())) {
                throw new SecurityException("UNTRUSTED_ISSUER");
            }
            if (!"tenant-a".equals(assertion.tenant())) {
                throw new SecurityException("TENANT_NOT_ALLOWED");
            }
            if (assertion.subject() == null ||
                    assertion.subject().isBlank()) {
                throw new SecurityException("BAD_SUBJECT");
            }
            Key key = new Key(assertion.issuer(), assertion.subject());
            Account account = accounts.computeIfAbsent(key,
                    k -> new Account(nextId.incrementAndGet(),
                            assertion.tenant(), assertion.email()));
            if (!account.tenant.equals(assertion.tenant())) {
                throw new SecurityException("TENANT_MISMATCH");
            }
            return account;
        }

        void approve(Key key) {
            Account a = accounts.get(key);
            if (a != null && a.status == Status.PENDING) {
                a.permissions = Set.of("reports:read");
                a.status = Status.ACTIVE;
            }
        }

        void disable(Key key) {
            Account a = accounts.get(key);
            if (a != null) {
                a.permissions = Set.of();
                a.status = Status.DISABLED;
            }
        }

        boolean canReadReports(VerifiedIdentity assertion) {
            Account a = resolveOrProvision(assertion);
            return a.status == Status.ACTIVE
                    && a.permissions.contains("reports:read");
        }

        int size() { return accounts.size(); }
    }

    public static void main(String[] args) throws Exception {
        Directory directory = new Directory();
        VerifiedIdentity alice = new VerifiedIdentity(
                "https://idp-a.example", "subject-001",
                "alice@corp.example", "tenant-a");

        List<Long> ids = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        Runnable login = () -> {
            ready.countDown();
            try {
                start.await();
                ids.add(directory.resolveOrProvision(alice).id);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        };
        Thread t1 = new Thread(login);
        Thread t2 = new Thread(login);
        t1.start();
        t2.start();
        ready.await();
        start.countDown();
        t1.join();
        t2.join();

        System.out.println("SAME_ACCOUNT=" + ids.get(0).equals(ids.get(1)));
        System.out.println("AFTER_RACE=" + directory.size());
        System.out.println("PENDING_READ=" + directory.canReadReports(alice));

        Key key = new Key(alice.issuer(), alice.subject());
        directory.approve(key);
        System.out.println("ACTIVE_READ=" + directory.canReadReports(alice));

        VerifiedIdentity otherIssuer = new VerifiedIdentity(
                "https://idp-b.example", "subject-001",
                "alice@corp.example", "tenant-a");
        Account b = directory.resolveOrProvision(otherIssuer);
        System.out.println("DIFFERENT_ISSUER_ACCOUNT="
                + (b.id != directory.resolveOrProvision(alice).id));

        VerifiedIdentity otherSubSameEmail = new VerifiedIdentity(
                "https://idp-a.example", "subject-002",
                "alice@corp.example", "tenant-a");
        Account c = directory.resolveOrProvision(otherSubSameEmail);
        System.out.println("SAME_EMAIL_NOT_LINKED="
                + (c.id != directory.resolveOrProvision(alice).id));
        System.out.println("TOTAL_ACCOUNTS=" + directory.size());

        directory.disable(key);
        System.out.println("DISABLED_READ=" + directory.canReadReports(alice));
        System.out.println("STILL_DISABLED="
                + (directory.resolveOrProvision(alice).status
                    == Status.DISABLED));

        try {
            directory.resolveOrProvision(new VerifiedIdentity(
                    "https://evil-idp.example", "subject-999",
                    "unknown@corp.example", "tenant-a"));
            System.out.println("UNKNOWN_ISSUER=ALLOWED");
        } catch (SecurityException e) {
            System.out.println("UNKNOWN_ISSUER=DENIED");
        }

        try {
            directory.resolveOrProvision(new VerifiedIdentity(
                    "https://idp-a.example", "subject-001",
                    "alice@corp.example", "tenant-b"));
            System.out.println("WRONG_TENANT=ALLOWED");
        } catch (SecurityException e) {
            System.out.println("WRONG_TENANT=DENIED");
        }
    }
}
~~~

Compile and run:

~~~bash
javac JitProvisioningDemo.java
java JitProvisioningDemo
~~~

**Deterministic stdout** after both threads join:

~~~text
SAME_ACCOUNT=true
AFTER_RACE=1
PENDING_READ=false
ACTIVE_READ=true
DIFFERENT_ISSUER_ACCOUNT=true
SAME_EMAIL_NOT_LINKED=true
TOTAL_ACCOUNTS=3
DISABLED_READ=false
STILL_DISABLED=true
UNKNOWN_ISSUER=DENIED
WRONG_TENANT=DENIED
~~~

Explanation:
1. Same `(issuer, subject)` across two threads → same account, no duplicate.
2. Before approval, `PENDING` lacks `reports:read`; after `approve`, it becomes `ACTIVE`.
3. Same `subject` across two issuers is not merged.
4. Same email with a different `subject` does not auto-link.
5. A `DISABLED` account is not recreated or reactivated on subsequent logins.
6. Unknown issuers and out-of-policy tenants are rejected.

**Never deploy in-memory `computeIfAbsent` as a production JIT store**: multiple pods have separate maps; transactions/unique constraints and persisted state are mandatory. `VerifiedIdentity` fields in the demo **are assumed already trusted** and do not verify OIDC/SAML themselves. `approve`/`disable` here simulate admin actions and do not handle DB locks, auditing, security sessions, or concurrent revocation.

## 11. Integrating OIDC Just-in-Time in Spring Security

In Servlet-based Spring Security, the OIDC Login flow is:

~~~text
Browser -> /oauth2/authorization/corp
       -> OIDC Authorization Code + state/nonce + PKCE policy
       -> Token endpoint / ID Token validation
       -> OidcUserService / UserInfo
       -> JIT service lookup or create local account
       -> local account status & permission mapping
       -> Spring Authentication / SecurityContext
       -> app authorization
~~~

**Only run JIT after the ID Token verification step**: signature, issuer, audience/client, expiry, nonce, and state/correlation per the library. Never manually decode a raw JWT from the browser and create an account just because the token looks valid.

### 11.1. Delegation pattern using OidcUserService

The snippet below illustrates wrapping the default `OidcUserService` to resolve/bind a local account while keeping Spring Security's standard validations intact and without taking authorities from untrusted group claims.

~~~java
package example.security;

import java.util.HashSet;
import java.util.Set;
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
public class OidcJitConfig {

    enum Status { PENDING, ACTIVE, DISABLED }

    record LocalUser(Status status, Set<String> approvedPermissions) {}

    interface LocalIdentityService {
        LocalUser resolveOrProvision(
                String registrationId, String issuer, String subject,
                String email, Boolean emailVerified);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http,
            LocalIdentityService local) throws Exception {

        OidcUserService delegate = new OidcUserService();
        OAuth2UserService<OidcUserRequest, OidcUser> service = request -> {
            OidcUser oidc = delegate.loadUser(request);
            String issuer = oidc.getIdToken().getIssuer().toString();
            String subject = oidc.getSubject();
            String registrationId =
                request.getClientRegistration().getRegistrationId();

            // Application: allowlist issuer, tenant, DB UNIQUE,
            // JIT eligibility, approval and DISABLED precedence.
            LocalUser user = local.resolveOrProvision(
                registrationId, issuer, subject,
                oidc.getEmail(), oidc.getEmailVerified());

            if (user.status() == Status.DISABLED) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("local_account_disabled"),
                    "Local account disabled");
            }

            Set<GrantedAuthority> authorities = new HashSet<>();
            if (user.status() == Status.PENDING) {
                authorities.add(
                    new SimpleGrantedAuthority("app:onboarding"));
            } else {
                for (String permission : user.approvedPermissions()) {
                    authorities.add(new SimpleGrantedAuthority(permission));
                }
            }

            if (oidc.getUserInfo() == null) {
                return new DefaultOidcUser(authorities, oidc.getIdToken());
            }
            return new DefaultOidcUser(
                authorities, oidc.getIdToken(), oidc.getUserInfo());
        };

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/onboarding/**").authenticated()
                .requestMatchers("/reports/**")
                    .hasAuthority("reports:read")
                .anyRequest().authenticated())
            .oauth2Login(oidc -> oidc
                .userInfoEndpoint(info -> info.oidcUserService(service)));
        return http.build();
    }
}
~~~

**This is a configuration fragment inside a Spring Boot application, not standalone Java SE.** It requires a real implementation/bean of `LocalIdentityService`, repositories, transactions, `ClientRegistrationRepository`, TLS, an OIDC OP, callback config, Spring Security dependencies, and compilation/integration tests matching versions 6.x/7.x. Defining an interface inside the snippet does not mean Spring auto-implements it; you must supply the bean.

Key points:
- `OidcUserService` is invoked inside the OIDC-verified pipeline, not in place of the token verifier.
- The application resolver uses verified `issuer`/`sub` and tenant policy.
- `PENDING` only gets `app:onboarding`; business endpoints require specific authorities.
- `DISABLED` is rejected even if the IdP still authenticates the user.
- Authorities come from **local `approvedPermissions`**, never taking `groups=admins` as an admin role.
- Never turn a validated ID Token into a local session if the identity-binding transaction fails.

**Note:** if accounts have other statuses such as `SUSPENDED`, the resolver must reject per policy; the code only illustrates three states and production apps must enforce full controls. Some IdPs do not return `UserInfo` or `email_verified`; the resolver must not require an email to form the identity key, since `issuer`/`sub` suffice for lookup.

### 11.2. Why not let a success handler create the account and redirect regardless?

Some systems use an `AuthenticationSuccessHandler` for JIT. However, a success handler may execute **after** the framework has already partially handled `SecurityContext`/session depending on configuration. If account creation fails yet the handler still redirects, the user may end up in an authenticated session **without a valid local account**.

Solutions:
- Prefer integrating **admission + JIT** at the principal/`Authentication`-creation stage after protocol validation.
- If using a success handler, clear/invalidate state and return a failure when provisioning does not commit.
- Never create accounts inside a protected business controller after the request has already been authorized.
- Never manually set `Authentication` from an unverified URL/header username.

### 11.3. Permissions can go stale while a session remains active

After login, authorities are attached to `OAuth2AuthenticationToken` and may be stored in Spring `HttpSession`. When an admin revokes permissions in the DB, an existing session **does not automatically reload permissions**. To meet SLAs:
- Set appropriate session TTL/absolute expiry.
- Invalidate sessions when roles/statuses change.
- Or recheck entitlements/`securityVersion` on sensitive operations.
- If APIs use standalone JWTs, implement corresponding revocation/introspection/token lifetimes.

JIT handles lifecycle at **login**, not implicitly on every request.

## 12. Integrating SAML2 JIT in the Right Place

After Spring/OpenSAML validates `SAMLResponse`, `Authentication` can contain a `Saml2AuthenticatedPrincipal`. Example of a handler displaying the **authenticated principal**:

~~~java
@GetMapping("/me")
public Map<String, Object> me(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
    return Map.of(
        "subject", principal.getName(),
        "registrationId", principal.getRelyingPartyRegistrationId());
}
~~~

**This snippet does not implement JIT; it is only an example of reading a principal in Spring MVC.** JIT should be implemented inside a **post-validation account resolver / custom response authentication conversion** wrapping or delegating to the standard provider, rather than replacing signature/audience/recipient/time checks with manual XML parsing.

Process:
1. Spring SAML2 verifier confirms the signed assertion and all trust conditions.
2. Extract the IdP `entityID` and stable `NameID`/immutable attribute per the federation contract.
3. Build a natural key namespaced by IdP/SP per policy.
4. Invoke the transactional local identity resolver to look up/create the binding.
5. Check status, tenant, and entitlements; `PENDING` gets onboarding-only or deny.
6. Build `Authentication`/authorities bound to the local account per tested integration.
7. Never create a local business session when JIT fails.

**Caution:** `OpenSaml5AuthenticationProvider` and converter APIs may vary across releases. Never manually construct `Saml2Authentication` after reading unvalidated XML; use the version-appropriate extension point, preserve default validation, and test SAML signature, wrong audience, replay, and transient `NameID`.

### 12.1. Transient NameID risk

~~~text
Login 1: NameID = transient-aa1
Login 2: NameID = transient-bb2
Same real human, but different identifiers.
~~~

If JIT uses `principal.getName()` directly as the key, the app can create a second account on every login. Require the IdP to supply a **persistent NameID** or a contracted stable attribute. **Never solve this via email matching**, as that introduces takeover risk.

## 13. Login-Time Attribute Sync: What Is Allowed to Change?

| Field | Recommended rule |
| --- | --- |
| Display name | Can sync if IdP is authoritative, with consent/retention; never use as identity key. |
| Email | Can sync per policy once verified; **never auto-relink** accounts. |
| Locale / avatar | Store only if needed; validate and prevent SSRF when fetching remote URLs. |
| Department/manager | Use the proper HR/Directory source with timestamps/provenance. |
| Employee ID | Treat as stable ID only if the issuer contract guarantees immutability and non-reuse. |
| Tenant membership | Only from authoritative directory/policy, never from user queries/unchecked groups. |
| Account status | **Never auto-flip `DISABLED`→`ACTIVE`** just because of a login. |
| App role/entitlement | Only from approved local authority sources and scoped mappings. |
| MFA/assurance | Only from verified authentication context, never inferred from `email_verified`. |
| Internal account ID | Immutable, preserving foreign keys and audit trails. |

There is no default "IdP is authoritative for every field". Users might edit their display name in the app while department comes from HR and roles come from an entitlement system. Profile sync must follow **per-field source-of-truth** and avoid unnecessary writes.

### 13.1. Defer noncritical writes

If only avatar/display name needs updating while a secondary profile system is down, login may proceed if **identity binding, status, and permissions** are already verified. Conversely, if active employment/tenant cannot be confirmed, business access must not be granted indefinitely on old roles.

Separate the critical transaction (identity binding + account) from noncritical side effects (welcome email, avatar fetch, analytics) using an outbox/events. Never enqueue "user_created" and report success before the binding commits.

## 14. Account Linking: Distinct from JIT, Requires Evidence

Case where a user already has local account #42 from IdP A and now signs in via IdP B with the same email as #42. The resolver finds no binding for B.

**Wrong:** find the account with the matching email and attach identity B to #42, especially when #42 has admin privileges or sensitive data.

**Right:** perform explicit account linking:
1. The user holds a **sufficiently strong authenticated session for local account #42**, or completes equivalent identity-proofing/admin approval.
2. Initiate a "Link another identity" request with CSRF/state/nonce protections.
3. Perform OIDC/SAML login with IdP B via the proper protocol.
4. Verify issuer/subject B, tenant, consent/risk, and ensure identity B is not bound to another account.
5. In a transaction, add `federated_identity(B, subB) -> account #42` with a unique constraint.
6. Audit the actor, timestamp, and policy, and notify the account owner.
7. When unlinking, block logins from the removed identity; never silently re-JIT it back into the old account.

For bulk IdP migrations, use an approved mapping based on stable HR IDs and admin review; avoid "same email means same person" as a migration path.

## 15. Deprovisioning and the DISABLED State

JIT only triggers at login; it **does not automatically learn about user offboarding** when no new login occurs. You need:
- **SCIM 2.0** or HR/IGA sync to disable accounts and update groups/memberships.
- An account state machine with `DISABLED`/`SUSPENDED`/tombstones.
- Session invalidation, local token revocation, and `securityVersion` checks.
- Short TTLs/revalidation for sensitive permissions.
- Periodic reconciliation for orphan accounts and stale permissions.
- Audited identity-unlinking workflows that do not cause accidental relinking.
- Policy-driven user notifications when an account is disabled.

Invariant:

~~~text
Verified federation authentication SUCCEEDS
AND local_account.status = DISABLED
=> DO NOT grant business access
=> DO NOT reactivate via JIT
~~~

If a user is deleted from the DB while still holding IdP credentials, JIT could inadvertently create a new account. Therefore, maintain a tombstone/revocation marker or deny record per policy while respecting data minimization and retention rules.

### 15.1. Revoking existing sessions

Spring `SecurityContext` may store an old `Authentication` in `HttpSession`. A user disabled after login can retain their session until expiration if the app **does not recheck**. Distinguish:
- **Login-time JIT checks** when building a new `Authentication`.
- **Per-request or critical-action authorization checks** against current status/entitlements.
- **Back-channel logout/session invalidation** when the IdP/IGA reports an event.
- **Bearer token revocation/introspection** if APIs use standalone tokens.

Never promise "disabling at the IdP immediately logs out all apps" unless downstream sessions/tokens actually have a revocation mechanism.

## 16. Fail-Closed Behavior and Safe Operation During Incidents

### 16.1. When the local DB fails

| Condition | Safe behavior |
| --- | --- |
| New external identity, DB cannot write. | **Do not** grant a full session; display an onboarding error with controlled retry. |
| Cannot read status of an existing account. | Cannot confirm `ACTIVE` ⇒ deny or allow only a pre-defined restricted mode. |
| Unique violation due to concurrent first login. | Roll back transaction, load winner, check status/tenant. |
| DB commit outcome unknown due to timeout. | Requery natural key after DB recovery; do not blindly insert another record. |
| Only profile avatar update fails. | May allow login per policy if account/status/rights are verified; audit side effect. |
| IdP/entitlement API unavailable. | Do not grant strong roles from stale caches beyond SLA. |
| Event queue retry. | Idempotent account creation and event handling. |

### 16.2. Preventing unauthorized mass provisioning

If an IdP allows arbitrary email self-signup, an attacker could create thousands of RP accounts even with valid OIDC tokens. JIT requires:
- Real tenant/corporate cohort eligibility.
- Invitation/approval or domain-only rules as supplements, never replacing proofing.
- Rate/quota limits per issuer/client/tenant and alerts on account creation spikes.
- Blocking non-compliant identities and granting no business permissions to `PENDING`.
- Limits on profile attributes, Unicode/length, and XSS/SSRF protection on avatar URLs.
- Orphan/tombstone cleanup per retention rules, without blindly deleting accounts that hold data.

### 16.3. Logs, privacy, and auditing

Never log raw ID Tokens, `SAMLResponse`, access/refresh tokens, browser cookies, full profile claims, or unnecessary emails. You can log references like:

~~~text
event=JIT_PROVISIONING
trace_id=login-20261107-a742
issuer_ref=corporate-oidc
subject_ref=HMAC(issuer|subject)
tenant_ref=finance-vn
local_account_ref=u-742
result=CREATED_PENDING
account_status=PENDING
policy_version=jit-v4
time_utc=2026-11-07T09:00:00Z
~~~

This is an illustrative event schema, not Spring's default log format. Audits must record account created/approved/linked/disabled, role changes, and login denials. Use keyed HMAC references instead of raw subject/email in metric labels; manage keys and retention per privacy policy.

## 17. Testing JIT: Critical Matrix

| Test case | Expected result |
| --- | --- |
| Trusted OIDC token, new issuer/sub, eligible tenant. | One account + federated binding created transactionally. |
| Second login with same issuer/sub. | Same local account ID, no duplicates. |
| Two nodes log in with same issuer/sub concurrently. | Unique constraint ensures 1 account, no orphans. |
| Same sub across different issuers. | No auto-link. |
| Same email but different sub. | No auto-link, no account takeover. |
| Email changed while issuer/sub stayed the same. | Same account, profile updated per policy. |
| `email_verified=true` matching admin email. | **Do not** link into the admin account. |
| Invalid OIDC ID Token signature/issuer/audience/expiry/nonce. | Protocol validator rejects, **no JIT**. |
| SAML transient NameID changes between two logins. | Reject stable mapping or use verified persistent ID. |
| Valid SAML signature from out-of-contract IdP. | Do not create account. |
| IdP changes pairwise subject on migration. | Approved identity linking, no email merge. |
| Local account `PENDING`. | Onboarding only if policy allows; business APIs denied. |
| Local account `DISABLED`/`SUSPENDED`. | No business login, no auto-reactivation. |
| Deleted user with tombstone while IdP still issues token. | No unauthorized JIT recreation. |
| Upstream group "admins". | Do not auto-assign `ROLE_ADMIN`. |
| User has `ACTIVE` account but lacks resource permissions. | 403 per local authorization. |
| Spoofed tenant in query string. | Deny; membership must not be switched. |
| Unique conflict after inserting local account. | Whole transaction rolls back; look up winner. |
| SCIM disable races with user login. | Deny per status/consistency policy and revocation SLA. |
| DB outage on first login. | Fail closed, no full session created. |
| Valid IdP token while HR eligibility service times out. | Fail-safe, do not unconditionally grant strong privileges. |
| Account linking B→A without authenticating A. | Reject. |
| Approved linking with authenticated A + verified B. | Unique binding, audit succeeds. |
| Local account status changes while session is active. | Session/token revocation or per-action check within SLA. |
| Same user across multiple tenants. | Enforce membership/tenant resource boundaries, no leaks. |
| Account creation event retried multiple times. | Idempotent, no duplicate rows created. |
| 10,000 first logins during peak traffic. | Rate/quotas, transaction integrity, no fail-open. |
| UserInfo display name contains HTML/script. | No XSS; account key unaffected. |

**Do not only test happy-path logins.** High-severity flaws include email-based account takeover, race duplicates, disabled account resurrection, cross-tenant grants, and automatic admin role mapping.

## 18. Troubleshooting

| Symptom | Common cause | How to diagnose |
| --- | --- | --- |
| OIDC login succeeds but app returns 403. | Local status `PENDING` or missing entitlements. | Check account status and authz; do not weaken security matchers. |
| Every login creates a new local account. | Using email/session or SAML transient `NameID`. | Inspect identity key for issuer/subject. |
| Two accounts for one user after parallel logins. | Missing DB unique constraint / transaction. | Check unique violation handling and orphan records. |
| Unique violation causes HTTP 500. | Did not roll back/requery in a fresh transaction. | Fix transaction boundary and bounded retry. |
| User changed email and lost data. | Email used as primary external key. | Migrate bindings to issuer/sub, preserving local account ID. |
| User from partner IdP received admin account. | Auto-linking by email. | Stop auto-linking, review access/audit logs and account ownership. |
| `DISABLED` local user flipped back to `ACTIVE` on login. | Upsert overwrote status. | Enforce deny precedence and tombstone checks. |
| `PENDING` user can access `/reports`. | Used `authenticated()` instead of permission check. | Restrict business endpoints by approved authorities. |
| IdP groups auto-generate admin privileges. | Group mapping lacked allowlist/app scope. | Enforce local entitlements. |
| SAML `NameID` changed after IdP update. | Transient/pairwise/qualifier changed. | Define a stable identifier contract and migration plan. |
| JIT creates user without federated binding. | Non-atomic transaction. | Commit local account + identity in one transaction. |
| SCIM disabled user yet session stays valid. | Sessions/tokens not revoked. | Implement session registry, TTLs, per-request checks. |
| Multi-tenant user sees another tenant's data. | Membership/role not scoped to resource. | Enforce tenant checks at resource/service layer. |
| JIT fails during IdP/HR outage. | Synchronous dependency timeout without fail-safe. | Add circuit breakers, explicit-TTL eligibility cache, deny where required. |
| UserInfo email differs from before. | Legitimate profile update or source mismatch. | Never create a new binding from email. |
| Systems store too many raw tokens. | Faulty audit/retention design. | Mask/redact, use HMAC references, apply data minimization. |

## 19. Production Implementation Checklist

1. Is there a clear trust agreement for issuers, client/RP registrations, stable subjects, and tenants?
2. Does JIT run **only after** OIDC/SAML/CAS validation succeeds?
3. Does OIDC use verified `iss+sub` rather than email/username as the account key?
4. Does SAML use a persistent `NameID`/immutable attribute and proper IdP `entityID` namespacing?
5. Are allowed issuers/tenants/eligibility enforced, with no auto-signup from unknown IdPs?
6. Are there unique indexes and atomic transactions creating local account + binding together?
7. Do two concurrent logins create exactly one account?
8. Does a unique conflict roll back completely and load the winner properly?
9. Do new accounts start `PENDING`/least-privilege with no auto-admin?
10. Is there `DENY` precedence for `DISABLED`/`SUSPENDED`/tombstones?
11. Are local authorities and tenant/resource permissions checked separately?
12. Is there an explicit account-linking workflow instead of email auto-matching?
13. Is there an approved migration plan when pairwise `sub` or IdP changes?
14. Does profile sync respect per-field source-of-truth without overwriting statuses/roles?
15. Are SCIM/HR deprovisioning and session/API token revocation in place?
16. Are throttling, quotas, anti-mass-provisioning, and audit events active?
17. Do DB/HR outages fail safely without granting full sessions when state is unknown?
18. Are privacy/PII retention verified and raw assertions/tokens kept out of logs?
19. Are there integration tests for multi-node concurrency, wrong issuer, same-email takeover, and disabled recreation?
20. Is there documentation explaining to users that SSO succeeded while the account is `PENDING` and awaiting business access?

## 20. Knowledge Self-Check

1. **What is JIT?** — Creating/binding a local account on first login upon encountering a new verified federated identity per policy.
2. **Does JIT verify tokens?** — No; protocol validators must run first.
3. **Which stable OIDC key should be used?** — The `iss` and `sub` pair.
4. **Is `email_verified=true` enough to merge into an old account?** — No.
5. **Why is a SAML transient `NameID` unsuitable?** — It can change per session, causing duplicate accounts.
6. **How does JIT differ from SCIM?** — JIT runs at login; SCIM pushes lifecycle updates via API.
7. **Why is a DB unique constraint needed?** — To prevent races across tabs/nodes; app-level checks are insufficient.
8. **What if a unique conflict occurs after creating the local account?** — Roll back the entire transaction and requery the winning identity.
9. **Does a new account automatically get admin?** — No; `PENDING` or minimal privileges per policy.
10. **What if a `DISABLED` user still succeeds at OIDC login?** — Deny local business access and do not reactivate.
11. **What if two IdPs emit the same `sub`?** — They are two distinct identities if the issuers differ.
12. **Can the same email belong to two different `sub`s?** — Yes; do not auto-merge.
13. **What does account linking require?** — An authenticated existing local account/identity proofing and a verified new identity.
14. **Does JIT automatically handle offboarding?** — No; SCIM/HR and session/token revocation are needed.
15. **Which Spring OIDC hook is appropriate?** — Delegate verified `OidcUserService`, then resolve the local account before completing the session.
16. **What if the DB has an outage on first login?** — Do not grant a full session.
17. **Can roles from IdP groups be used directly?** — Only through trusted mapping and local app/tenant entitlements.
18. **What if a pairwise `sub` changes during migration?** — Evidenced account linking/migration, never email merging.
19. **Why test multiple concurrent first requests?** — To verify idempotency and ensure no duplicates/orphans.
20. **Is having an `ACTIVE` account enough to view all data?** — No; app permissions, tenant, and resource ownership also apply.

## References

- [NIST SP 800-63C — Federation and Assertions; Just-in-Time Provisioning and Account Linking](https://pages.nist.gov/800-63-4/sp800-63c.html)
- [OpenID Connect Core 1.0 — Claim Stability, Uniqueness, iss and sub](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth2 Login Advanced Configuration, OidcUserService](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — SAML2 Authentication and Saml2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [SCIM 2.0 RFC 7643 — Core Schema](https://www.rfc-editor.org/rfc/rfc7643.html)
- [SCIM 2.0 RFC 7644 — Protocol](https://www.rfc-editor.org/rfc/rfc7644.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
