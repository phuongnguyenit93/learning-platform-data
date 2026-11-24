# Storing Internal Users and Linking External Accounts with Stable Identifiers

## 1. The Problem: Sign In with Google Today, Change Email Tomorrow, Same Account

A Spring Security reactive/WebFlux application can let users sign in with Google or another OpenID Provider (OP) via OAuth2/OIDC. After the provider authenticates the user, the application still needs an **internal user** to store profiles, orders, tenant permissions, history, and owned resources. Never use an external email address as the primary key of business tables.

Example:
- First time, Alice signs in with Google using `alice@old.example`. The application creates local user `u-100`.
- Later Alice changes her email at the provider to `alice@new.example`, while her **subject remains the same**.
- Alice signs in again: it must resolve to **the exact same `u-100`**, without creating a new user or transferring data ownership.
- Bob owns a different Google account and later acquires Alice's old email address. Bob **must never** be logged into `u-100` via email collision.
- Alice wants to link an additional Identity Provider so she can sign in two ways into one account. That must originate from an **authenticated local session + explicit link intent + authenticating the new provider**, never by entering a matching email and treating it as linked.

**The most important OIDC rule:** once the ID Token has been verified, the **`(iss, sub)` pair** is the stable external identifier to bind to a local user. Claims like `email`, `preferred_username`, `name`, and phone numbers can all change, be recycled, or collide; even `email_verified=true` **does not** turn an email into a safe linking key between two accounts. OIDC Core Section 5.7 designates the issuer + subject pair as the identifier a relying party can rely on for an external user.

### Learning Outcomes

After this lesson you will be able to:
1. Distinguish local user ID, OAuth2 client registration ID, OIDC `iss`/`sub`, email, ID Token, and access token.
2. Design `local_users` and `external_identities` tables with proper unique constraints, independent of email.
3. Implement flows for first login, subsequent logins, email changes, explicit account linking, unlinking, conflicts, and account recovery.
4. Understand **pairwise subjects**, multi-issuer scenarios, and account-takeover risks from auto-linking by email.
5. Use Spring Security WebFlux `oauth2Login`, `OidcUser`, and `ServerAuthenticationSuccessHandler` to synchronize local users at login time.
6. Write safe reactive services with idempotency strategies to prevent creating duplicate users on concurrent logins; understand the limits of in-memory stores compared to DB transactions/unique constraints.
7. Run a Java 17+ Spring Boot 3.3.13 project and test suite with `WebTestClient`, `mockOidcLogin()`, and `StepVerifier`.
8. Separate **recognizing an external identity** from **approving account linking**, authorization, session management, and OAuth2 token storage.

## 2. From OAuth2 to OIDC: What Does the Application Actually Trust?

### 2.1. OAuth2 Authorization vs. OIDC Authentication

OAuth2 provides an authorization framework where an access token is used to call a resource server. **An access token is not by default an end-user identity credential for arbitrary clients.** OpenID Connect adds an authentication layer on top of OAuth2, notably the **ID Token** containing claims identifying the end-user within an issuer context.

Typical flow:

~~~text
Browser                     WebFlux app                   OIDC Provider
   │                            │                              │
   │ GET /oauth2/authorization/google                          │
   ├───────────────────────────►│                              │
   │                            │ Authorization Request        │
   │◄───────302 to OP───────────┼─────────────────────────────►│
   │                            │                              │
   │          User logs in / consents at provider              │
   │                            │                              │
   │ GET /login/oauth2/code/google?code=...&state=...          │
   ├───────────────────────────►│                              │
   │                            │ exchange code for tokens     │
   │                            ├─────────────────────────────►│
   │                            │◄── ID Token/access token ────┤
   │                            │                              │
   │                            │ Validate ID Token: sig, iss, │
   │                            │ aud, exp, nonce/state...     │
   │                            │                              │
   │                            │ (verified iss, sub)          │
   │                            ▼                              │
   │                     external_identities                    │
   │                      ├─ exists → existing local user      │
   │                      └─ missing → create local user+link  │
   │                            │                              │
   │◄──── redirect /me ─────────┤                              │
   │                            │                              │
~~~

Spring Security WebFlux handles the complex OAuth2/OIDC protocol steps (authorization code, `state`, token exchange, ID Token validation, callback) when `oauth2Login` is properly configured. **Only after authentication through that mechanism succeeds** should the application use the external identity to look up or create a local user.

Never accept a public API request with body `{"iss":"...","sub":"..."}` and treat it as authenticated. That data can be forged. Nor should you Base64-decode a JWT without verifying signature/audience/issuer and use `sub` for linking.

### 2.2. Three Types of IDs Not to Confuse

| Value | Example | Issued By? | Purpose |
| --- | --- | --- | --- |
| Local user ID | UUID `73ab...` | Application database | Primary key across orders, profiles, permissions, and audit logs |
| OIDC issuer `iss` | `https://accounts.google.com` | Verified OIDC Provider | Namespace issuing subjects |
| OIDC subject `sub` | Provider's opaque string | Provider within issuer's namespace | OP's user identifier for the relying party |
| Client registration ID | `google`, `corp-oidc` | Spring client configuration | Selects provider/client to initiate OAuth2 flow |
| Email | `alice@example.org` | Profile claim from OP | Contact/display; never a security linking key |
| `email_verified` | `true` or `false` | Claim from OP | Signal that provider verified email per its process; not local account ownership |
| Access token | Opaque/JWT string | Authorization Server | Calls protected resources per scopes |
| ID Token | OIDC JWT | OP | Authentication assertion verified by the client |

**`registrationId` is not itself the issuer.** Two different registrations can point to the same issuer, or a registration can be renamed in config; conversely, the same subject string under two different issuers represents two distinct identities.

For standard OIDC, use the **verified canonical issuer + verbatim subject** pair to identify an external account. Never rely on `sub` alone, and never tie users solely to `registrationId`.

### 2.3. OIDC Guarantees Only the Issuer + Subject Pair

Example:

~~~text
(iss="https://idp-a.example", sub="123") → external user A
(iss="https://idp-b.example", sub="123") → external user B
~~~

These two users **must not** be merged just because both `sub` values are `123`.

`sub` values can be opaque, case-sensitive, and contain characters meaningless to the application. Never `toLowerCase()`, parse as numbers, strip prefixes, hash uncontrolledly, or arbitrarily normalize `sub`. For `iss`, compare strictly against the configured/trusted issuer; apply alias mapping only when officially documented and security-reviewed.

For example, Google has documented issuer representations; if a migration must canonicalize an alias, **verify the token from Google first** and then map the alias under an approved rule. Never apply “strip scheme and take hostname” across all issuers, as that could merge distinct OPs.

## 3. Why Must Email Never Be Used to Auto-Link Accounts?

### 3.1. Account Takeover via Matching Email

Suppose a legacy app stores:

~~~text
users:
  id = u-100
  email = employee@company.example
~~~

On first OAuth2 login, broken code does:

~~~java
// ANTI-EXAMPLE: DO NOT look up a local account by email to auto-login/link.
return userRepository.findByEmail(oidcUser.getEmail())
    .switchIfEmpty(userRepository.createFromEmail(...));
~~~

What can go wrong:
- An email is changed/reclaimed and reassigned to another person.
- Provider A has different email-verification rules from Provider B.
- An unverified email still appears in UserInfo.
- Two identities share a valid email across different contexts.
- `email_verified=true` only attests to a provider-side event; it **does not prove the person logging in is authorized to inherit an existing local user**.

If a matching email automatically grants access to `u-100`, the new user can take over all historical data. This is an **account takeover** vulnerability.

### 3.2. Email Changes While Local ID Stays Constant

~~~text
Login 1:
  (iss=Google, sub=opaque-A, email=old@example.org)
     → external link L1 → local user u-100

Login 2:
  (iss=Google, sub=opaque-A, email=new@example.org)
     → external link L1 → local user u-100
~~~

The application may update profile email metadata (subject to email verification policies and reconfirmation), but it **never updates owner IDs in orders/documents tables** and never creates a new local account.

Email is merely metadata. The immutable local user ID is what domain entities reference:
- `orders.user_id`.
- `documents.owner_id`.
- `memberships.user_id`.
- `audit_events.actor_user_id`.
- `permissions.user_id`.

Do not repeat `iss`/`sub` across every business table when the goal is login linking. Keep an external identity → local user mapping table so multiple providers can be supported cleanly.

### 3.3. What Can `email_verified` Be Used For?

A verified-email signal can inform contact preferences, prompt for extra verification, or gate email notifications depending on policy and issuer trustworthiness. However:
- Never use it by itself as proof of “same person as an existing local account”.
- Never grant internal `ADMIN` roles by email domain without verifying organization, tenant, and provisioning policies.
- If an email changes at the provider, updating the internal contact email must follow security policy—never silently redirect recovery codes without confirmation.
- Do not treat `email_verified=false` as “provider failed to authenticate identity”: it is a claim about the email, not the entire OIDC authentication.

## 4. Data Model Design: Separating Local Users from External Identities

Logical diagram:

~~~text
local_users
┌─────────────────────────────────────────┐
│ id (UUID PK)                            │
│ status                                  │
│ display_name / contact_email            │
│ created_at / updated_at                 │
└───────────────┬─────────────────────────┘
                │ 1
                │
                │ n
external_identities
┌─────────────────────────────────────────┐
│ id (PK)                                 │
│ local_user_id (FK → local_users.id)     │
│ issuer  (normalized trusted issuer)     │
│ subject (opaque, case-sensitive)        │
│ registration_id (metadata)              │
│ linked_at / last_login_at               │
│ provider_email (metadata only)          │
│ provider_email_verified                 │
│ UNIQUE(issuer, subject)                 │
└─────────────────────────────────────────┘
~~~

PostgreSQL example:

~~~sql
CREATE TABLE local_users (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    display_name VARCHAR(200),
    contact_email VARCHAR(320),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'LOCKED', 'DELETED'))
);

CREATE TABLE external_identities (
    id BIGSERIAL PRIMARY KEY,
    local_user_id UUID NOT NULL
        REFERENCES local_users(id),
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    provider_email VARCHAR(320),
    provider_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    UNIQUE (issuer, subject),
    CHECK (length(issuer) > 0 AND length(subject) > 0)
);

CREATE INDEX ix_external_identities_local_user
    ON external_identities(local_user_id);

-- If the business allows only one account per issuer per local user:
-- CREATE UNIQUE INDEX ux_local_user_issuer
--     ON external_identities(local_user_id, issuer);
~~~

**Key constraints:**
1. `local_users.id` is issued by the app/DB and persists independently of provider changes.
2. `external_identities(issuer, subject)` must be **UNIQUE** so one external identity can never point to two local users.
3. `external_identities.local_user_id` is a foreign key, allowing multiple external identities to link to one local user (e.g., Google + corporate IdP).
4. `registration_id` is useful for auditing/routing, **never** replacing the OIDC identity's unique key.
5. `provider_email` and its verified flag are metadata. **Never put `UNIQUE` on email to force auto-merging.**
6. If multiple external subjects from the same issuer are allowed to link to one local user (multiple orgs/sectors), carefully decide whether to add `UNIQUE(local_user_id,issuer)`; secondary constraints must match business rules.
7. The data type for `subject` must preserve case. Database collation/case-folding must match; never use `citext` or a case-insensitive collation for `sub`.
8. Production needs plans for deletion/deactivation, audit retention, length limits, and handling extreme claim values rather than blindly trusting arbitrary long strings.

### 4.1. Example Data After Multiple Logins

~~~text
local_users:
  u-100 | Alice | ACTIVE
  u-200 | Bob   | ACTIVE

external_identities:
  https://accounts.google.com | google-sub-A | u-100 | alice-new@...
  https://login.corp.example  | corp-sub-77  | u-100 | alice@corp...
  https://accounts.google.com | google-sub-B | u-200 | bob@...
~~~

Alice can sign in from two identity sources while retaining **one `local_user_id` `u-100`**. Bob might share the same display email as Alice at some point, yet his external key is distinct and his local user remains separate.

## 5. First Login, Subsequent Logins, and Email Changes

### 5.1. First OIDC Login

1. Browser starts `/oauth2/authorization/{registrationId}` via Spring Security.
2. Spring Security handles `state`, callback, authorization code, token exchange, and ID Token verification (signature, issuer, audience, expiration, and applicable conditions like `nonce`).
3. Only after authentication **genuinely succeeds**, read `iss` and `sub` from the validated `OidcUser.getIdToken()`.
4. Normalize issuer **only** per verified policy (if an alias is recognized); keep `subject` verbatim.
5. Query `external_identities` by the unique key:
   - If a link exists: load the exact local user and check status (`ACTIVE`/`LOCKED`).
   - If not found: per product policy, create a new local user or route to onboarding/pending approval; **never auto-link by email**.
6. Update `last_login_at` and permitted metadata; never turn metadata into access privileges.
7. Only after the local account is accepted, finalize the login session and redirect to a safe internal route.

### 5.2. Subsequent Logins

Look up by the same `(iss, sub)` and get back the same local user ID. Name/email/avatar changes do not alter the link. If the local user is `LOCKED`, block login even though the OP authenticated OIDC successfully; a valid ID Token verifies only the external account, **never bypassing internal account status**.

### 5.3. Two Near-Simultaneous Logins

If two tabs log in with the same external identity not yet in the DB:

~~~text
Request A                         Request B
  Lookup(iss, sub) → not found      Lookup(iss, sub) → not found
  Insert local user u-101           Insert local user u-102
  Insert external link              Insert external link
           └── Only one INSERT is allowed to win UNIQUE(iss, sub).
~~~

Doing only `findByKey().switchIfEmpty(create())` without transactions/unique constraints can create two local users and split data.

**Production requirement:** the database enforces `UNIQUE(issuer, subject)`, creating the user + external link happens inside a **transaction**, and the losing race branch rolls back the temporary user and **re-reads the winner** in a fresh transaction or retries the whole transaction from an appropriate boundary. Never simply catch `DuplicateKeyException` mid-way through an aborted PostgreSQL transaction and continue querying inside that same transaction.

### 5.4. Distinguishing “Auto-Create a New Account” from “Auto-Link to an Existing Account”

These two actions carry very different security implications:
- **Auto-provision:** if the external identity does not exist yet, create **a brand-new local user** with a fresh ID—never match an existing account by email.
- **Explicit link:** an existing local user actively proves control over **both the local session and the new external account**, and the system attaches the new external identity to that local user.

First-time auto-provisioning can never be treated as proof of ownership over an existing internal account sharing the same email.

## 6. Linking an Additional Provider: Requires a Dedicated Protocol

Suppose a user is logged in locally as `u-100` via Google and wants to link a corporate IdP.

Safe flow:

~~~text
Authenticated local user u-100
            │
            ▼
Selects "Link corporate account"
            │
            ▼
POST /account/links/start
  Valid CSRF, re-authenticate if needed
            │
            ▼
Server creates link intent in session/trusted store:
  localUserId=u-100
  targetRegistrationId=corp
  intentId=random
  expiresAt=...
  state/correlation bound to OIDC flow
            │
            ▼
Redirect to corporate OIDC provider
            │
            ▼
OIDC callback after validating code/state/id_token
            │
            ▼
Retrieve (trusted iss, sub) of corporate account
            │
            ▼
Single transaction:
  Read valid, single-use link intent,
  bound to the requesting user+session+provider;
  if (iss,sub) already linked to another user → CONFLICT;
  if not yet linked → INSERT external link to u-100;
  if already linked to u-100 → idempotent success.
            │
            ▼
Delete intent, audit event, notify success
~~~

**The hard part is not the SQL INSERT, but proving both sides of the linking action.** Safeguards:
- The local session must be authenticated; consider requiring recent login/MFA before linking.
- The link initiation button uses **POST and CSRF**; never link via GET or email links alone.
- OAuth2 authorization `state`/nonce and link intent must bind session, user ID, `registrationId`, expiry, purpose, and single-use semantics to prevent login CSRF and mix-up attacks.
- The callback must authenticate the **new provider account**, never accepting an arbitrary client-submitted `sub` form field.
- Never mix “sign in” with “link account” using email or a `?linkUser=u-100` query parameter.
- On conflict, never silently move a link away from another user; return a clear error without leaking that other user's data.
- If callbacks open across multiple tabs, manage races via state/intent; never attach to a session that just switched users.
- Enforce unique constraints/transactions and audit logging before announcing the link succeeded.
- Linking **does not automatically** elevate roles or tenant memberships; internal policies still govern privileges.

### 6.1. What If the External Identity Is Already Linked to Another Local User?

For example, corporate `(iss=corp, sub=77)` is currently attached to `u-200`, and user `u-100` tries to link it. You must reject (`409 Conflict` or equivalent error policy), never delete the old link and reassign it to `u-100`.

If the product genuinely wants to merge two local accounts, build a **dedicated account-merge workflow** verifying both accounts, checking data, permissions, tenants, and audit trails—never merge simply on matching email.

### 6.2. Safe Unlinking

Removing an external link can lock a user out of their account:
- Require reauthentication/MFA for sensitive unlinking operations.
- Verify the account retains at least one verified login/recovery method, or apply the appropriate account-deactivation policy.
- Confirm user intent and log before/after audit records.
- Revoke sessions/tokens if policy requires; unlinking in the DB **does not automatically revoke tokens already issued at the OP**.
- Prevent another user from claiming the link during a race window; use transactions, unique constraints, and conflict handling.
- Never let a user unlink another account's external identity via a client-supplied ID.

## 7. Pairwise Subjects, Changing Client IDs, and Multi-Tenant Setups

OIDC defines two common subject types: **public** and **pairwise**. With pairwise subjects, the same end-user at a provider can receive **different `sub` values for different relying parties/sector identifiers**. Therefore:
- Never assume same OP + same email = same external identity.
- Changing an OAuth2/OIDC client registration or sector identifier can change `sub` depending on provider policy.
- If migration is needed, use provider-supported migration flows, user re-verification, and explicit re-linking; never auto-merge by email.
- Two `registrationId` entries in Spring Boot pointing to the same issuer are not guaranteed to yield identical identities in all circumstances; OIDC rules still rely on the actually received and verified `issuer + subject`.

In multi-tenant systems, consider also:
- Local users may be global identities while memberships/roles live in a separate `tenant_memberships` table.
- If local users are tenant-scoped, unique constraints and link policies must specify whether one external identity can span multiple tenants; never let login in tenant A automatically grant roles in tenant B.
- `groups` or `roles` claims from an IdP do not grant internal `ROLE_ADMIN` unless the issuer, tenant scope, and mapping are approved.
- If provider access is revoked, local account status or enterprise offboarding may require disabling sessions and revoking memberships.

## 8. SQL/Transaction Examples for Real R2DBC Applications

### 8.1. Looking Up an External Identity

~~~sql
SELECT u.id, u.status, u.display_name, u.contact_email
FROM external_identities e
JOIN local_users u ON u.id = e.local_user_id
WHERE e.issuer = :trustedIssuer
  AND e.subject = :trustedSubject;
~~~

`trustedIssuer` and `trustedSubject` must be extracted from a **validated identity**; never accept them freely via a JSON body on an unprotected API.

Outcomes:
- `ACTIVE` row found → use the local ID.
- `LOCKED` row found → block login; never auto-unlock just because OP login succeeded.
- No row → follow auto-provision or onboarding policy; never run `SELECT WHERE email = ...` to claim an existing account.

### 8.2. Creating Local User and Link in a Transaction

~~~sql
BEGIN;

INSERT INTO local_users (id, status, display_name)
VALUES (:newLocalUserUuid, 'ACTIVE', :displayName);

INSERT INTO external_identities
    (local_user_id, issuer, subject, registration_id,
     provider_email, provider_email_verified)
VALUES
    (:newLocalUserUuid, :trustedIssuer, :trustedSubject,
     :trustedRegistrationId, :emailMetadata, :emailVerified);

COMMIT;
~~~

On a unique conflict on `(issuer, subject)`, roll back the **entire transaction** and then fetch the local user created by the winning request. In PostgreSQL, never assume you can keep running arbitrary queries after a duplicate-key error **inside the same aborted transaction**. With R2DBC, use `TransactionalOperator` or `@Transactional` with proper reactive transaction context and retry outside the transaction boundary.

### 8.3. Linking an Additional Identity to an Existing Local User

~~~sql
BEGIN;

-- Read/lock valid link intent belonging to this exact current session/account
-- after completing OIDC callback for the right provider; single-use consume.

INSERT INTO external_identities
    (local_user_id, issuer, subject, registration_id)
VALUES
    (:authenticatedLocalUserId,
     :verifiedIssuer,
     :verifiedSubject,
     :verifiedRegistrationId);

-- UNIQUE(issuer,subject) catches race/link-hijacking conflicts.
-- Cases where the identity is already attached to the same user can be handled idempotently
-- via a SELECT/check branch inside an appropriate transaction.

COMMIT;
~~~

**Never** execute `UPDATE external_identities SET local_user_id=:newId WHERE issuer=:iss AND subject=:sub` without an approved account-merge workflow. That statement can “hijack” an external identity already linked to another user.

### 8.4. Reactive Transaction Boundary Example

**Architectural pseudo-code, not a standalone Java file**:

~~~java
Mono<LocalUser> provisionAfterVerifiedLogin(VerifiedOidcIdentity identity) {
    return lookupExisting(identity.key())
        .switchIfEmpty(
            transactionalOperator.transactional(
                createLocalUserAndLink(identity) // both INSERTs in 1 TX
            )
        );
}
~~~

This illustrates **transactional intent** without race-retry handling. `lookupExisting` and `createLocalUserAndLink` are app-defined APIs. Production must catch unique conflicts and retry the **entire transaction** or re-read after rollback, while also handling locked accounts, cancellations, replica lag, and operation idempotency.

## 9. Runnable Project: WebFlux + OIDC Login + Local Identity Store

This learning example uses **Java 17+**, **Spring Boot 3.3.13**, Gradle 8.x, and Spring Security reactive OAuth2 Client. Versions are pinned for clear API cross-checking; production should use a currently supported Spring Boot/Security release.

Goals:
- Spring Security configures OAuth2/OIDC login with the Google provider.
- Once **Spring Security verifies an actual OIDC login**, the success handler uses `iss + sub` to look up/create the local user.
- `GET /me` reads the already-provisioned local user from the external identity; it **does not** create users on GET.
- Local users and links are simulated with two maps + a synchronized critical section **for JVM demo purposes only** to enforce internal uniqueness.
- Includes a `linkAfterConfirmedFlow(...)` service API for explicit linking, without **exposing an HTTP endpoint** because the demo does not implement a full session-bound OAuth2 linking intent. Tests invoke the service after simulating a verified flow.
- Tests can run **offline** using mocked OIDC principals/Spring Security Test. Completing real Google login requires real registered client ID/secret and redirect URI.

### 9.1. Structure

~~~text
webflux-oidc-local-identity/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── OidcLocalIdentityApplication.java
    │   │   ├── ExternalIdentity.java
    │   │   ├── LocalIdentityStore.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── LocalIdentityTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-oidc-local-identity'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
# Uses Spring Boot's built-in Google provider configuration.
# The two demo values only allow the app to start/run offline tests;
# REAL GOOGLE LOGIN REQUIRES replacing with credentials registered at Google.
spring.security.oauth2.client.registration.google.client-id=offline-demo-client
spring.security.oauth2.client.registration.google.client-secret=offline-demo-secret
spring.security.oauth2.client.registration.google.scope=openid,profile,email
~~~

`offline-demo-client` and `offline-demo-secret` are **not real credentials**, so the browser cannot complete Google login with them. Tests in section 10 use Spring Security Test to mock a verified identity. To run real Google login, provision credentials via a secure secrets mechanism and register a public redirect URI like `{baseUrl}/login/oauth2/code/google` with accurate proxy/TLS/hostname settings.

Never commit production client secrets. Never take `OIDC client id` from user input to dynamically choose a trusted audience.

### 9.2. Main Class

`src/main/java/demo/OidcLocalIdentityApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLocalIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcLocalIdentityApplication.class, args);
    }
}
~~~

### 9.3. ExternalIdentity: Constructed Only from Validated OIDC Principals in Real Apps

`src/main/java/demo/ExternalIdentity.java`:

~~~java
package demo;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Package-private: service data object, not an API request body.
record ExternalIdentity(
    String issuer,
    String subject,
    String email,
    boolean emailVerified
) {
    record Key(String issuer, String subject) {}

    Key key() {
        // Email intentionally NOT part of the identity key.
        return new Key(issuer, subject);
    }

    static ExternalIdentity fromVerifiedGoogleOidc(OidcUser user) {
        if (user == null || user.getIdToken() == null) {
            throw new IllegalArgumentException("Missing verified ID Token");
        }

        var token = user.getIdToken();
        String iss = token.getClaimAsString("iss");
        String sub = token.getSubject();

        if (sub == null || sub.isBlank() || sub.length() > 500) {
            throw new IllegalArgumentException("Invalid OIDC subject");
        }

        // Accept only the two issuer aliases documented by Google.
        // IMPORTANT: must be called after Spring Security has validated
        // the Google ID Token (signature, aud, iss, exp, nonce...).
        if ("accounts.google.com".equals(iss)) {
            iss = "https://accounts.google.com";
        }

        if (!"https://accounts.google.com".equals(iss)) {
            throw new IllegalArgumentException("Unexpected OIDC issuer");
        }

        String email = token.getClaimAsString("email");
        boolean verified = Boolean.TRUE.equals(
            token.getClaimAsBoolean("email_verified"));

        return new ExternalIdentity(iss, sub, email, verified);
    }
}
~~~

**Explanation and warnings:**
- `fromVerifiedGoogleOidc` **does not verify the ID Token signature**. It only extracts claims from an `OidcUser` previously authenticated/verified by Spring Security. A test-built `OidcUser` does not prove a signature.
- The `iss` string is checked against Google's allowlist; the `accounts.google.com` alias is canonicalized **only after** passing real provider verification. Never arbitrarily normalize other OPs this way.
- `sub` preserves exact casing and its opaque value. Never trim or lowercase it.
- `email` and `emailVerified` are metadata only, excluded from `Key`.
- Other providers need separate adapters + issuer allowlists; never pass arbitrary JWTs or OAuth2 UserInfo into `fromVerifiedGoogleOidc`.

### 9.4. LocalIdentityStore: Unique Identity and Explicit Linking

`src/main/java/demo/LocalIdentityStore.java`:

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
class LocalIdentityStore {

    record LocalUser(
        UUID id,
        String lastSeenEmail,
        boolean emailVerified,
        boolean enabled
    ) {}

    static final class LinkConflictException extends RuntimeException {
        LinkConflictException() {
            super("External identity is already linked");
        }
    }

    private final Map<UUID, LocalUser> users = new HashMap<>();
    private final Map<ExternalIdentity.Key, UUID> links =
        new HashMap<>();

    // SIMULATION: short critical section within a single JVM.
    // Production must replace with a reactive database + UNIQUE + TX.
    Mono<LocalUser> signIn(ExternalIdentity identity) {
        return Mono.fromSupplier(() -> {
            synchronized (this) {
                UUID existing = links.get(identity.key());

                if (existing != null) {
                    LocalUser oldUser = users.get(existing);
                    if (oldUser == null) {
                        throw new IllegalStateException("Dangling link");
                    }
                    if (!oldUser.enabled()) {
                        throw new IllegalStateException("Account disabled");
                    }

                    // Email is metadata only; ID does not change.
                    LocalUser updated = new LocalUser(
                        oldUser.id(),
                        identity.email(),
                        identity.emailVerified(),
                        true
                    );

                    users.put(existing, updated);
                    return updated;
                }

                UUID localId = UUID.randomUUID();
                LocalUser created = new LocalUser(
                    localId,
                    identity.email(),
                    identity.emailVerified(),
                    true
                );

                users.put(localId, created);
                links.put(identity.key(), localId);
                return created;
            }
        });
    }

    Mono<LocalUser> find(ExternalIdentity.Key key) {
        return Mono.fromSupplier(() -> {
            synchronized (this) {
                UUID id = links.get(key);
                return id == null ? null : users.get(id);
            }
        });
    }

    // ONLY CALL AFTER a link flow has verified BOTH:
    //  (1) authenticated local user + CSRF/re-auth
    //  (2) new OIDC callback + state/session-bound link intent
    // Project DOES NOT expose this method via an HTTP request.
    Mono<LocalUser> linkAfterConfirmedFlow(
            UUID authenticatedLocalUserId,
            ExternalIdentity verifiedNewIdentity) {

        return Mono.fromSupplier(() -> {
            synchronized (this) {
                LocalUser local = users.get(authenticatedLocalUserId);
                if (local == null || !local.enabled()) {
                    throw new IllegalArgumentException(
                        "Local account unavailable");
                }

                UUID owner = links.get(verifiedNewIdentity.key());

                if (owner != null
                    && !owner.equals(authenticatedLocalUserId)) {

                    throw new LinkConflictException();
                }

                // If already linked to this same user: idempotent.
                links.putIfAbsent(
                    verifiedNewIdentity.key(),
                    authenticatedLocalUserId
                );
                return local;
            }
        });
    }
}
~~~

**Why doesn't the code use email?**
- `signIn` looks up by `identity.key() = (issuer, subject)`.
- For a new key, it always allocates a fresh local ID. It never calls `findByEmail`.
- For an existing key, the local ID stays unchanged even when the email changes.
- `linkAfterConfirmedFlow` accepts only the local ID of an account already authenticated by a separate flow; it is **not** an API accepting client-submitted local IDs or external subjects.
- If the external identity is already linked to another user, it throws `LinkConflictException` rather than transferring link ownership.
- If already linked to the same user, it behaves idempotently.
- `enabled` demonstrates checking local status so a successful OP login cannot unlock a disabled account.

**Major limitation:** `synchronized` guards a single JVM and in-memory `HashMap` in the demo—it is not a database, not durable, not multi-instance capable, and not a reactive I/O strategy. The critical section in the example is tiny and does no network/DB/blocking I/O; production uses `R2dbcEntityTemplate`/`DatabaseClient`, unique keys, and transactions. Never put blocking JDBC/file/network calls inside `synchronized` or on the Netty event loop.

### 9.5. SecurityConfig: Recording Links After Successful OIDC Login

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    ServerAuthenticationSuccessHandler provisionOnOidcLogin(
            LocalIdentityStore store) {

        var redirect =
            new RedirectServerAuthenticationSuccessHandler("/me");

        return (filterExchange, authentication) -> {
            if (!(authentication instanceof OAuth2AuthenticationToken oauth)
                || !"google".equals(
                    oauth.getAuthorizedClientRegistrationId())
                || !(oauth.getPrincipal() instanceof OidcUser oidc)) {

                return Mono.error(new BadCredentialsException(
                    "Expected verified Google OIDC login"));
            }

            final ExternalIdentity identity;
            try {
                identity = ExternalIdentity.fromVerifiedGoogleOidc(oidc);
            }
            catch (IllegalArgumentException malformedClaims) {
                return Mono.error(new BadCredentialsException(
                    "Untrusted OIDC identity", malformedClaims));
            }

            // Must complete local-user provisioning BEFORE
            // considering login successful at the application level.
            return store.signIn(identity)
                .then(redirect.onAuthenticationSuccess(
                    filterExchange, authentication));
        };
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ServerAuthenticationSuccessHandler provisionOnOidcLogin) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(provisionOnOidcLogin))
            // Keep default CSRF enabled for session-based actions.
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Explanation:
1. Spring Security OAuth2 Client configures `registrationId=google`. The OIDC flow uses `scope=openid`, producing an ID Token rather than just an email profile.
2. The handler processes only an `OAuth2AuthenticationToken` whose principal is `OidcUser` and whose registration is `google`. Other authentication types are not treated as verified Google identities.
3. `fromVerifiedGoogleOidc` extracts the key only after Spring Security has processed OIDC login. Never accept raw `iss`/`sub` from requests.
4. `store.signIn(identity)` is a publisher; `.then(redirect.onAuthenticationSuccess(...))` awaits its completion before redirecting. No `block()`, no detached `subscribe()`.
5. After sign-in, the session `SecurityContext` is managed by Spring Security. **The local user does not automatically replace the framework's `Authentication.getPrincipal()`**; if services need the local UUID, resolve it from the verified identity or configure a consistent custom principal/mapping.
6. `RedirectServerAuthenticationSuccessHandler` uses a saved request if present, otherwise `/me`; in production, validate redirect targets to prevent open redirects and avoid blindly replaying unsafe POSTs.
7. If provisioning fails or the local user is locked, do not redirect to success; production needs proper failure UX/auditing and must ensure no usable internal authentication persists when provisioning fails.
8. `csrf(Customizer.withDefaults())` preserves CSRF; never disable it for linking convenience.
9. The demo auto-provisions **brand-new accounts only**. It does not invoke `linkAfterConfirmedFlow` from the success handler because logging in does not mean the user requested linking to an existing local account.

### 9.6. Controller: Reading Only Already-Provisioned Local Users

`src/main/java/demo/ProfileController.java`:

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class ProfileController {

    public record MeView(
        String localUserId,
        String lastSeenEmail,
        boolean emailVerified
    ) {}

    private final LocalIdentityStore store;

    ProfileController(LocalIdentityStore store) {
        this.store = store;
    }

    @GetMapping("/")
    Mono<String> home() {
        return Mono.just("Start OIDC login at /oauth2/authorization/google");
    }

    @GetMapping("/me")
    Mono<MeView> me(@AuthenticationPrincipal OidcUser principal) {
        if (principal == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED));
        }

        final ExternalIdentity identity;
        try {
            identity = ExternalIdentity.fromVerifiedGoogleOidc(principal);
        }
        catch (IllegalArgumentException invalid) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED, "Invalid OIDC principal"));
        }

        return store.find(identity.key())
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Local account has not been provisioned")))
            .map(user -> new MeView(
                user.id().toString(),
                user.lastSeenEmail(),
                user.emailVerified()
            ));
    }
}
~~~

**Why doesn't `GET /me` auto-create a local user?** GET must be a read operation. Creating users inside GET lets crawlers, prefetching, tests/middleware, or profile-reading code paths cause unintended side effects. The project puts provisioning in the OIDC login success handler; the controller only performs a lookup.

Never return raw ID Tokens, access tokens, refresh tokens, client secrets, all `OidcUser.getClaims()`, or session IDs. Local UUIDs are generally not secrets, yet resource authorization must still enforce access checks by local user/tenant on the backend.

## 10. Testing with JUnit, StepVerifier, and WebTestClient

The test suite below **does not connect to real Google**. It intentionally builds `ExternalIdentity` fixtures mocked as “verified” to test mapping logic, uses `mockOidcLogin()` to test WebFlux `SecurityContext`, and unit-tests the success handler. Mocking does not prove cryptographic ID Token validation; add integration/E2E tests with a real OIDC Provider or trusted test provider in an integration environment.

`src/test/java/demo/LocalIdentityTests.java`:

~~~java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class LocalIdentityTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    LocalIdentityStore store;

    @Autowired
    ServerAuthenticationSuccessHandler provisionOnOidcLogin;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private ExternalIdentity external(
            String issuer, String subject, String email) {

        // Test fixture: assumes the key was verified by an OP.
        return new ExternalIdentity(
            issuer, subject, email, true);
    }

    private OidcUser fakeGoogleOidc(
            String subject, String email) {

        OidcIdToken token = OidcIdToken.withTokenValue("test-only")
            .claim("iss", "https://accounts.google.com")
            .claim("sub", subject)
            .claim("email", email)
            .claim("email_verified", true)
            .build();

        return new DefaultOidcUser(
            List.of(new SimpleGrantedAuthority("OIDC_USER")),
            token
        );
    }

    @Test
    void sameIssuerAndSubjectKeepLocalIdAfterEmailChange() {
        var before = external(
            "https://accounts.google.com",
            "stable-sub-01", "old@demo.test");

        var after = external(
            "https://accounts.google.com",
            "stable-sub-01", "new@demo.test");

        StepVerifier.create(
            store.signIn(before).flatMap(first ->
                store.signIn(after).map(second ->
                    new String[] {
                        first.id().toString(),
                        second.id().toString(),
                        second.lastSeenEmail()
                    })))
            .assertNext(result -> {
                assertThat(result[0]).isEqualTo(result[1]);
                assertThat(result[2]).isEqualTo("new@demo.test");
            })
            .verifyComplete();
    }

    @Test
    void sameEmailWithDifferentSubjectsMustNotMerge() {
        var alice = external(
            "https://accounts.google.com",
            "stable-sub-alice-02", "shared@demo.test");
        var bob = external(
            "https://accounts.google.com",
            "stable-sub-bob-02", "shared@demo.test");

        StepVerifier.create(Mono.zip(
            store.signIn(alice), store.signIn(bob)))
            .assertNext(pair ->
                assertThat(pair.getT1().id())
                    .isNotEqualTo(pair.getT2().id()))
            .verifyComplete();
    }

    @Test
    void sameSubjectButDifferentTrustedIssuerIsDifferentIdentity() {
        var first = external(
            "https://idp-a.example", "subject-03", "a@demo.test");
        var second = external(
            "https://idp-b.example", "subject-03", "a@demo.test");

        // Store test: assumes both issuers are verified.
        // Production adapter must validate each issuer before calling.
        StepVerifier.create(Mono.zip(
            store.signIn(first), store.signIn(second)))
            .assertNext(pair ->
                assertThat(pair.getT1().id())
                    .isNotEqualTo(pair.getT2().id()))
            .verifyComplete();
    }

    @Test
    void subjectComparisonIsCaseSensitive() {
        var upper = external(
            "https://idp-a.example", "CaseSensitive", "a@demo.test");
        var lower = external(
            "https://idp-a.example", "casesensitive", "a@demo.test");

        StepVerifier.create(Mono.zip(
            store.signIn(upper), store.signIn(lower)))
            .assertNext(pair ->
                assertThat(pair.getT1().id())
                    .isNotEqualTo(pair.getT2().id()))
            .verifyComplete();
    }

    @Test
    void explicitLinkAllowsTwoProvidersForOneLocalUser() {
        var google = external(
            "https://accounts.google.com",
            "link-google-05", "a@demo.test");
        var corporate = external(
            "https://corp.example",
            "link-corp-05", "new@corp.test");

        StepVerifier.create(
            store.signIn(google)
                .flatMap(user ->
                    store.linkAfterConfirmedFlow(
                        user.id(), corporate)
                      .then(store.signIn(corporate))
                      .map(alsoSignedIn ->
                          new boolean[] {
                              user.id().equals(alsoSignedIn.id())
                          })))
            .assertNext(result -> assertThat(result[0]).isTrue())
            .verifyComplete();
    }

    @Test
    void identityAlreadyLinkedToAnotherLocalUserIsConflict() {
        var googleA = external(
            "https://accounts.google.com",
            "first-account-06", "a@demo.test");
        var googleB = external(
            "https://accounts.google.com",
            "second-account-06", "a@demo.test");

        StepVerifier.create(
            store.signIn(googleA)
                .flatMap(userA -> store.signIn(googleB)
                    .flatMap(userB ->
                        store.linkAfterConfirmedFlow(
                            userA.id(), googleB))))
            .expectError(
                LocalIdentityStore.LinkConflictException.class)
            .verify();
    }

    @Test
    void missingOrUntrustedIssuerIsRejectedAtOidcBoundary() {
        OidcIdToken token = OidcIdToken.withTokenValue("untrusted")
            .claim("iss", "https://attacker.example")
            .claim("sub", "unknown-sub-07")
            .build();

        OidcUser user = new DefaultOidcUser(
            List.of(new SimpleGrantedAuthority("OIDC_USER")), token);

        assertThatThrownBy(() ->
            ExternalIdentity.fromVerifiedGoogleOidc(user))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void mockOidcLoginCanReadAlreadyProvisionedLocalUser() {
        var verified = external(
            "https://accounts.google.com",
            "web-profile-08", "reader@demo.test");

        AtomicReference<String> id = new AtomicReference<>();

        StepVerifier.create(store.signIn(verified))
            .assertNext(user -> id.set(user.id().toString()))
            .verifyComplete();

        client.mutateWith(mockOidcLogin()
                .idToken(token -> token
                    .claim("iss", "https://accounts.google.com")
                    .claim("sub", "web-profile-08")
                    .claim("email", "reader@demo.test")
                    .claim("email_verified", true)))
            .get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.localUserId").isEqualTo(id.get())
            .jsonPath("$.lastSeenEmail")
                .isEqualTo("reader@demo.test");
    }

    @Test
    void mockOidcLoginDoesNotAutoProvisionOnGet() {
        client.mutateWith(mockOidcLogin()
                .idToken(token -> token
                    .claim("iss", "https://accounts.google.com")
                    .claim("sub", "never-provisioned-09")))
            .get().uri("/me")
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.CONFLICT);
    }

    @Test
    void anonymousProfileIsRedirectedToLogin() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void oidcAuthenticationSuccessProvisionsBeforeRedirect() {
        String subject = "success-sub-11";
        OidcUser oidc = fakeGoogleOidc(
            subject, "success@demo.test");

        var authentication = new OAuth2AuthenticationToken(
            oidc, oidc.getAuthorities(), "google");

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get(
                "/login/oauth2/code/google"));

        var filterExchange = new WebFilterExchange(
            exchange, e -> Mono.empty());

        StepVerifier.create(
            provisionOnOidcLogin.onAuthenticationSuccess(
                filterExchange, authentication))
            .verifyComplete();

        assertThat(exchange.getResponse().getStatusCode())
            .isEqualTo(HttpStatus.FOUND);

        var key = new ExternalIdentity.Key(
            "https://accounts.google.com", subject);

        StepVerifier.create(store.find(key))
            .assertNext(local ->
                assertThat(local.lastSeenEmail())
                    .isEqualTo("success@demo.test"))
            .verifyComplete();
    }

    @Test
    void repeatSameLinkForSameLocalUserIsIdempotent() {
        var google = external(
            "https://accounts.google.com",
            "link-main-12", "a@demo.test");
        var corporate = external(
            "https://corp.example",
            "link-secondary-12", "a@corp.test");

        StepVerifier.create(store.signIn(google).flatMap(user ->
            store.linkAfterConfirmedFlow(user.id(), corporate)
                .then(store.linkAfterConfirmedFlow(
                    user.id(), corporate))
                .map(linked -> user.id().equals(linked.id()))))
            .expectNext(true)
            .verifyComplete();
    }
}
~~~

**Interpreting the tests accurately:**
- Two logins with the same `(iss, sub)` and different emails → **one local ID**.
- Two different subjects even with the same email → **two local IDs**.
- Two different issuers even with the same subject → **two identities**.
- Subject comparison is case-sensitive.
- Explicit linking **after verifying both sides** attaches a second provider to the existing user; the demo method is not exposed over HTTP.
- Linking an identity already belonging to another account → conflict, never “hijacking” the link.
- Issuers outside Google's allowlist are rejected at the adapter.
- Spring Security Test's `mockOidcLogin()` places a mock principal in WebFlux `SecurityContext` to test profile-reading endpoints.
- `GET /me` does not auto-create users; mock login bypasses the success handler, so an unprovisioned user returns 409 per the demo contract.
- The success handler test invokes the handler directly with an OIDC fixture and verifies the local account is created **before** redirecting; this tests handler orchestration, **not that the fixture ID token has a real signature**.
- Linking the same external key to the same local user again is idempotent.

### 10.1. What Have These Tests Not Proven Yet?

Mock `OidcIdToken` objects created in Java code have no signature verification. These tests do not replace real OAuth2/OIDC integration tests with a provider or a properly configured test IdP. Never extrapolate from `mockOidcLogin` that signatures, audiences, issuers, nonces, PKCE, `state`, HTTPS redirect URIs, and JWKS are protected in production.

Also test these production cases:
- Provider omits `email` or returns `email_verified=false`.
- Pairwise subject changes when switching client/sector.
- Concurrent logins for a new client → unique constraint/transaction creates only one local user.
- `LOCKED`/`DELETED` local users remain blocked even with a valid ID Token.
- Two accounts sharing an email across different `iss`/`sub` are not merged.
- Explicit linking is rejected when the external identity already belongs to another user.
- Link callbacks with invalid/expired `state` or a changed local session are rejected.
- Unlinking the user's last login method is blocked or routed to a verified recovery flow.
- Never reuse a `registrationId` to point to a different issuer after migration without approved migration data.
- OIDC access/refresh tokens are protected and never logged.

### 10.2. Running the Project and Viewing Results

Requires JDK 17+, Gradle 8.x, and network access for initial dependency resolution. From the project directory:

~~~bash
gradle test
~~~

If using the Gradle Wrapper, run `./gradlew test` on Linux/macOS or `gradlew.bat test` on Windows. The project is designed to run tests **offline without calling Google**, once dependencies are cached. All 12 test methods are expected to pass with matching APIs/dependencies; **compilation and execution must be confirmed by running them yourself**, never treating the guide text as Gradle output.

You can run:

~~~bash
gradle bootRun
~~~

Open `http://localhost:8080/` to see route instructions and `/oauth2/authorization/google` to initiate the OAuth2 flow. With the demo client ID/secret, Google will not accept an actual login. To test real login, configure real credentials and a registered redirect URI with the exact host/scheme/port; use HTTPS on the public Internet, never HTTP Basic or a `?sub=...` query hack instead of OAuth2 callbacks.

## 11. Why Doesn't `OAuth2AuthorizedClient` Replace the External Identity Table?

Spring Security provides `OAuth2AuthorizedClient`/`ReactiveOAuth2AuthorizedClientService` or repositories to hold client registrations, access tokens, and refresh tokens for an authorization grant. That structure is for **managing OAuth2 tokens**, not for local account mapping.

| Structure | Purpose |
| --- | --- |
| `ClientRegistration` / `ReactiveClientRegistrationRepository` | Provider endpoints, client ID, scopes, redirect URI, and OAuth2 config |
| `OAuth2AuthenticationToken` | Current authentication result, principal/authorities/registration ID |
| `OidcUser` and `OidcIdToken` | Identity verified by the OIDC login pipeline |
| `OAuth2AuthorizedClient` | Tokens issued to the client to call provider resources |
| `local_users` | Durable internal identity, primary key for business tables |
| `external_identities` | Unique link `(trusted iss, sub) → localUserId` |
| `tenant_memberships` | Roles/permissions per tenant and enterprise policy |

Never use a refresh token as a user's “identifying key”. Tokens rotate, expire, and get revoked, whereas the local user ID must endure independently.

Production token persistence must protect secrets, encrypt at rest, enforce access control, and manage rotation/revocation; never expose token values in `/me` JSON responses or application logs.

## 12. Common Difficult Migration Scenarios

### 12.1. Legacy System Has Only Email

If legacy local users were stored by email, **never migrate by automatically linking all Google identities with matching emails**. Safe path:
1. Have the user sign into the **legacy local account** via the existing mechanism or trusted account recovery.
2. From the authenticated local session, initiate the explicit link flow.
3. Authenticate the provider and attach the exact `iss`/`sub` to the local ID inside a transaction.
4. Audit and notify the user.
5. Deprecate the legacy mechanism only once the user has valid login/recovery options and policy allows it.

If the old account cannot be verified, route to an independent identity-verification support workflow; never use `email_verified` alone to skip steps.

### 12.2. Provider Changes Issuer URL

`iss` is a security namespace, not just a technical string. If an IdP changes its issuer:
- Confirm the change through official documentation/trusted administrative channels.
- Re-verify JWKS, redirects, audience/client IDs, discovery metadata, and validation.
- Confirm whether the provider **guarantees subject mapping stability**.
- Migrate identity links using a reviewed migration with a rollback plan and audit trail.
- Never drop the issuer check or normalize arbitrarily just to “let login pass”.

### 12.3. Changing OIDC Client/Sector Changes Pairwise Subjects

With pairwise `sub`, changing RP/sector can yield a new subject. The account has not lost its identity, yet the app cannot automatically deduce the two subjects are the same person via email. Use provider-assisted migration or explicit re-linking proving both identities.

### 12.4. Merging Two Local Users That Have Separate Orders

Two existing local IDs may each own independent orders, invoices, permissions, tenant memberships, and audit records. Account merging is not just updating a link table. You must verify control over both accounts, assess data impact, handle ownership references, use proper transactions/migrations, and audit. Never run `UPDATE external_identities SET local_user_id=...` as an ad-hoc merge.

## 13. Account Linking and Spring Security Sessions/Authorization

After OIDC login:
- Spring Security holds the external provider's authentication.
- Internal services need the local user ID to look up tenant permissions and owned resources.
- Never assume `Authentication.getName()` is the local UUID; it may be the provider's `sub`/username.
- Never assume `OidcUser.getAuthorities()` reflects internal roles. `SCOPE_profile` represents an OAuth2 scope, **not** `ROLE_ADMIN`.
- If you want a custom principal carrying the local user ID, apply it in an authentication mapping/service synchronized with `SecurityContext`, handling session refreshes and permission changes.
- In the demo project, `/me` looks up from the verified external identity; production can cache the mapping per session/short TTL, invalidating on disable/link/unlink/role changes.
- API resources must enforce owner/tenant checks using the resolved local ID, never checking access by email.
- Logging out of the app session does not automatically unlink accounts or revoke all tokens/SSO sessions; configure OIDC logout/revocation policies separately.
- Cookie sessions, CSRF, OAuth2 `state`/`nonce`, PKCE, and browser redirects are distinct security layers that must all be tested together.

### 13.1. Which Operations Require CSRF?

Initiating linking, confirming a link, unlinking, or changing default login methods are usually sensitive **POST/DELETE** operations when authenticated via cookie sessions. Require CSRF tokens and fresh authentication proportional to risk. Spring Security's OAuth2 callback has its own `state`/correlation protocol; never replace it with a public POST endpoint accepting an arbitrary subject.

**Never** disable CSRF app-wide to make “Google linking easier”. On 403 errors, identify which request the CSRF filter rejected and fix the flow properly without disabling protection.

## 14. Troubleshooting

| Symptom | Common Cause | How to Diagnose |
| --- | --- | --- |
| Re-login creates a new local user | App looks up by email/`registrationId` or didn't persist the link | Query by unique `(iss, sub)` inside a transaction |
| Changing email loses orders | User ID derived from email or local account recreated | Move ownership to immutable local UUID |
| Two people log into the same local account | Auto-linking by email/shared username | Stop auto-merging; audit affected accounts |
| Callback has Google `sub` but adapter misses key | Issuer alias, case normalization, changed client/sector | Check verified issuer, controlled canonical mapping, and exact subject |
| Login succeeds at OP but app errors | Local user `LOCKED`, DB link conflict, or provisioning error | Check local status, unique violations, and error UX |
| Two tabs create two accounts | Check-then-insert race, missing unique/transaction | Unique `(iss, sub)` + retry outside transaction boundary |
| External account gets linked to another user | Direct link-owner UPDATE or race condition | `UNIQUE` + reject conflicts; never transfer ownership |
| Unverified email receives ADMIN role | Granting privileges by email domain without verification | Derive internal roles from trusted tenant/SCIM/membership sources |
| Local user has two providers, only one works | Link flow didn't persist `issuer`/`sub`, stale session/cache | Inspect persisted links and ID Token validation |
| Callback `redirect_uri_mismatch` | Public URL/proxy/scheme differs from registered URI | Configure HTTPS, trusted forwarded headers, and client registration |
| `/me` returns 409 in mock tests | `mockOidcLogin` skips the success handler so user wasn't provisioned | Provision a fixture or test the success handler directly |
| Deleted account can still log in | OP authenticates successfully while app ignores local status | Block local `LOCKED`/`DELETED` before granting internal access |
| Unauthorized after link/unlink | Stale session `SecurityContext`/cache | Review reauth, cache invalidation, and logout policies |
| Access token used as user ID | Tokens rotate, vary in scope, not stable identities | Use verified `iss`/`sub` |
| Spring MVC `OAuth2Login` API mismatch | Using `HttpSecurity`/Servlet instead of `ServerHttpSecurity` | Use reactive stack and `ReactiveClientRegistrationRepository` |

## 15. Self-Check Questions

1. **What is the stable key of an OIDC identity?** The `(verified issuer, subject)` pair, not `sub` alone.
2. **Why isn't `registrationId=google` enough?** It is a Spring client config name, not a user discriminator, and it can be renamed.
3. **Why shouldn't email be the primary key?** Emails can change, be recycled, collide, or be unverified.
4. **Does `email_verified=true` allow auto-linking to a local user with the same email?** No; it does not prove ownership of the existing local user.
5. **Alice changes her email while `iss`/`sub` stay the same—what happens to her local ID?** It stays unchanged; only metadata may be updated.
6. **What if two issuers emit the same `sub`?** They are two distinct external identities.
7. **What is a pairwise subject?** A subject that can differ across RPs/sectors, preventing identity correlation by email.
8. **What should happen when a brand-new external identity appears for the first time?** Create a new local account/onboarding per policy; never merge by email.
9. **What risk do two concurrent logins for the same identity create?** Duplicate users, orphan rows, or race conditions; handle with unique constraints/transactions/retries.
10. **Why is `UNIQUE(issuer, subject)` important?** One external identity must never map to two local users, even under race conditions.
11. **Why retry duplicate-key errors outside the transaction?** A PostgreSQL transaction after an error may be aborted; roll back first, then re-read/retry.
12. **What must be proven to link a new provider?** Both the authenticated local session/consent and new provider authentication, with a state-bound single-use intent.
13. **What if the external identity is already linked to another user?** Return a conflict; never transfer it to the current user.
14. **Is unlinking all login methods safe?** It can lock the user out; require recovery/reauth checks.
15. **Does a test-created `OidcUser.getIdToken()` prove the signature?** No; mocks are fixtures, requiring tests against a real OIDC provider.
16. **Why not let `GET /me` auto-create users?** GET should stay read-only to avoid state mutations from prefetch/crawlers/monitoring.
17. **Is an OAuth2 access token a stable user ID?** No; it authorizes resource access and can expire/rotate.
18. **Does provider `SCOPE_profile` become `ROLE_USER`/`ADMIN` automatically in the app?** No; internal roles/memberships require separate policy.
19. **Can one user have two external identities?** Yes, when secure explicit linking creates multiple records pointing to the same local ID.
20. **Should changing issuer or OIDC client auto-merge by email?** No; use provider-supported migration or identity re-verification.

## 16. Production Deployment Checklist

- [ ] Use a local UUID as the primary key for business data.
- [ ] Accept OIDC `iss`/`sub` only after signature, issuer, audience, expiry, and `state`/`nonce`/PKCE are verified by the framework/provider.
- [ ] Enforce reviewed per-provider issuer allowlists/canonicalization while preserving exact `subject` casing.
- [ ] Maintain a separate `external_identities` table with `UNIQUE(issuer, subject)` and FK to `local_users`.
- [ ] Never auto-link or auto-merge by email, even with `email_verified=true`.
- [ ] Auto-provision first-time logins (if permitted) inside a transaction; check local account status.
- [ ] Existing-account linking requires local session, CSRF, fresh auth, state-bound link intent, verified callback, and replay protection.
- [ ] Return conflict when an identity is already attached to another user; never silently reassign `local_user_id`.
- [ ] Handle concurrent login races with unique constraints, transactions, and post-rollback retries.
- [ ] Never grant roles or tenant memberships from unapproved emails/scopes.
- [ ] Treat provider email/name metadata as mutable; enforce validation and permissions when changing contact email.
- [ ] Enforce auditing, reauth, notifications, and account recovery for linking/unlinking.
- [ ] Store refresh/access tokens separately, protect secrets, and never log/serialize them to APIs.
- [ ] Give local mapping caches an invalidation policy when users are disabled/unlinked or roles change.
- [ ] Test same `iss`/`sub` with email change, same email with different `sub`, same `sub` with different `iss`, and pairwise migration.
- [ ] Test duplicate-link conflicts, concurrent logins, transaction rollbacks, and zero orphan users.
- [ ] Test callback `state`/`nonce` failures, provider mismatches, issuer mismatches, locked users, and consent flows.
- [ ] Verify HTTPS, trusted forwarded headers, redirect URIs, cookies/sessions, and OAuth2 logout/revocation.
- [ ] In multi-node production, use a real reactive repository instead of in-memory maps.
- [ ] Never expose a public endpoint accepting `issuer`/`subject` as proof of login.

## 17. Official Documentation

- OpenID Connect Core 1.0 — `sub`, `iss`, Claim Stability and Uniqueness, Section 5.7: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security — OAuth2 WebFlux: https://docs.spring.io/spring-security/reference/reactive/oauth2/
- Spring Security — Reactive OAuth2 Login Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
- Spring Security — Reactive OAuth2 Login Advanced, OIDC User Service and ID Token Verification: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
- Spring Security — Testing OAuth2/OIDC Login with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security 6.3 API — `ServerHttpSecurity.OAuth2LoginSpec.authenticationSuccessHandler`: https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html
- Spring Security 6.3 API — `RedirectServerAuthenticationSuccessHandler`: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html
- Spring Boot 3.3 — OAuth2 Client Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Google — OpenID Connect ID Token claims (`iss` and `sub`): https://developers.google.com/identity/openid-connect/openid-connect
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Remember:** In WebFlux OAuth2/OIDC login, the **verified external identity = issuer + subject**, while the **durable business identity = local user ID**. Email is profile metadata, not proof for merging accounts. Store links in a separate table with unique constraints and transactions, auto-provision new users only when appropriate, and to link into an existing user, run a flow verifying **both the local account and the new provider** with state/CSRF/reauth. Spring Security verifies OIDC login, while the database and application remain responsible for uniqueness, internal permissions, and conflict policies.
