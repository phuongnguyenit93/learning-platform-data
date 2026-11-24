# Registration, Recovery, and Account Administration Belong to the Application Business Lifecycle

> **Main point:** Spring Security provides building blocks to **authenticate identity** and **authorize access**: `SecurityFilterChain`, `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, sessions, and method security. However, Spring Security **does not itself define full business workflows** for account registration, email verification, access recovery, changing contact addresses, granting or revoking roles, locking accounts, or deleting data on request. These capabilities must be designed as the **application's Account lifecycle**, properly connected to authentication mechanisms and security requirements.

This lesson belongs to the **User Sources** section of **Spring Security – fundamentals**. The focus is on Java 17+, Spring Boot 3.5.16, and Spring Security 6.5.x applications using username/password on Spring MVC/Servlet. The model remains useful with OIDC/SSO, though where the account lifecycle is managed differs if identity is controlled by an Identity Provider (IdP).

## 1. Learning Outcomes

After finishing, you can:

1. Explain how **Account** (the business record) differs from **UserDetails** (how Spring Security reads credentials/permissions for an authentication mechanism).
2. Design account statuses and valid state transitions: `PENDING_VERIFICATION` → `ACTIVE` → `SUSPENDED` or `CLOSED`.
3. Describe complete flows for registration, email verification, forgot password, password reset, changing password while logged in, changing email, locking/unlocking, and closing accounts.
4. Distinguish verification/recovery tokens from **access tokens**, **refresh tokens**, session cookies, and CSRF tokens.
5. Design unpredictable recovery tokens that are **expiring, single-use, stored hashed**, protected against concurrent double consumption, and non-disclosing of account existence.
6. Know where transactions, unique constraints, versioning, email outbox, idempotency, auditing, and rate limiting are needed.
7. Wire `UserDetailsService`/`DaoAuthenticationProvider` to the account store without **putting all registration/recovery logic inside `loadUserByUsername`**.
8. Authorize administration using server-derived roles/authorities; never let public registrants request `ROLE_ADMIN`.
9. Write and test a standalone demo: register → cannot log in yet → verify → log in → request reset → change password → disable account.
10. Identify limitations of the in-memory demo and how to migrate to a database/IdP with real data.

## 2. Responsibility Boundary: Spring Security vs. the Application

### 2.1. Overview diagram

```text
CLIENT / BROWSER
  |
  +-- POST /auth/register --------------------------+
  +-- POST /auth/verify ----------------------------+
  +-- POST /auth/recovery/request ------------------+
  +-- POST /auth/recovery/complete -----------------+--> Account API
  +-- POST /account/change-password ---------------+       |
  +-- POST /admin/accounts/{id}/suspend -----------+       v
  |                                              AccountLifecycleService
  |                                               / policy + transaction
  |                                                |          |
  |                                                v          v
  |                                         AccountRepository  Email/Outbox
  |                                                |
  |                                                v
  |                                           user/status/roles
  |
  +-- GET /me, GET /orders, POST /payments ...
                     |
                     v
              Spring Security Filter Chain
              AuthenticationManager/Provider
                     |
                     v
              UserDetailsService / OIDC / JWT verifier
                     |
                     v
              Account lookup/status/authorities
                     |
                     v
              HTTP authorization
                     |
                     v
              Controller -> service/domain authorization
```

This separation is critical:

- **Spring Security:** verifies credentials, establishes the authenticated principal, enforces filter/method authorization, and protects protocols (such as CSRF, sessions) per configuration.
- **Account domain:** who is allowed to register, required info, whether email is verified, who may lock accounts, recovery policy, auditing, and related data when closing an account.
- **Infrastructure:** databases, transactions, email/SMS queues, IdP, audit stores, anti-spam/rate limiting, and session/token revocation mechanisms.
- **Product/legal policy:** retention rules, identity proofing, underage users, personal data handling, and support procedures; these depend on the product and applicable law.

**Spring Security does not provide an "enableRegistration()" call that generates an entire secure registration and recovery system.** Having `UserDetailsService` does not mean the application has a `POST /auth/register` endpoint. Nor should you put email sending, reset token creation, or account deletion directly inside `loadUserByUsername()`.

### 2.2. Concrete role assignment table

| Component | Should be responsible for | Should not be tasked with |
| --- | --- | --- |
| `Account` / `User` domain entity | Stable ID, email, status, hash, roles, metadata, audit/version | Acting as a Servlet filter or issuing arbitrary JWTs |
| `AccountLifecycleService` | Registration, verification, recovery, status transitions, business rules | Verifying passwords via manual string comparison |
| `AccountRepository` | Retrieval/updates, unique constraints, optimistic locking/transactions | Deciding whether an actor is authorized to perform an operation |
| `VerificationTokenRepository` | Storing token hashes/purposes/expiry/used states | Holding plaintext passwords or access tokens |
| `MailGateway` / outbox worker | Sending notifications and links over verified channels | Returning raw tokens in public HTTP responses |
| `UserDetailsService` | Loading credential hashes, authorities, and account flags for the provider | Sending emails / resetting passwords / registering accounts |
| `DaoAuthenticationProvider` | Checking passwords with `PasswordEncoder` and account status | Automatically activating pending-verification accounts |
| `SecurityFilterChain` | Granting HTTP access for anonymous/member/admin, CSRF/session | Replacing owner/tenant policies in services |
| `AccountAdministrationService` | Letting staff perform permitted admin tasks with auditing | Trusting `role` submitted by the frontend |
| `SecurityContextRepository` / token service | Restoring authentication/sessions per mechanism | Acting as an email verification or password reset token store |

## 3. Modeling Account as a Business Resource

### 3.1. ID, email, and username

An illustrative design:

```text
Account
  id                  UUID or immutable stable ID
  normalizedEmail     unique per product email policy
  emailVerifiedAt     nullable
  passwordHash        one-way hash, with version/algorithm
  status              PENDING_VERIFICATION | ACTIVE | SUSPENDED | CLOSED
  roles               server-managed grants
  credentialVersion   used for policy-based revoke/invalidate
  createdAt
  updatedAt
  version             optimistic locking
  closedAt            nullable

AccountActionToken
  id
  accountId
  purpose             VERIFY_EMAIL | RESET_PASSWORD | VERIFY_NEW_EMAIL
  tokenDigest         hash/HMAC of random string
  expiresAt
  consumedAt          nullable
  createdAt
  requestMetadata     bounded; do not store unnecessary secrets

AuditEvent
  id, actorId, subjectAccountId, action, outcome, occurredAt
  correlationId, minimal and safe metadata
```

Emails can change; **never use email as an immutable foreign key** for orders, payments, ownership, or audits. Use stable `account.id`, while email serves as the contact/login identifier per design. A system may allow logging in via a separate username, phone, SSO subject (`issuer` + `sub`), or multiple methods.

**Normalization:** Email/domains have complex comparison rules; avoid arbitrarily stripping dots, stripping `+tag` suffixes, or transforming local-parts for one specific provider. Demos can use `trim()` and `toLowerCase(Locale.ROOT)` for simplicity, yet production needs product-approved normalization rules, matching unique constraints, IDN handling, and address verification via real email delivery. Never treat a simple email regex as proof the inbox belongs to the registrant.

### 3.2. Proposed statuses

```text
                 register
                     |
                     v
            PENDING_VERIFICATION
                     |
             valid verify token
                     |
                     v
                   ACTIVE
                 /        \
       admin suspends    owner closes
               v          v
           SUSPENDED    CLOSED
               |
        review / reinstate
               |
               v
             ACTIVE
```

A real flow may also have `INVITED`, `LOCKED` from failed logins, `PENDING_REVIEW`, `DELETION_SCHEDULED`, `DELETED`, or `ANONYMIZED`, depending on business logic. You do not have to merge "temporarily locked due to wrong passwords" and "staff suspended due to violation" into one status: reasons, durations, and unlock paths differ.

| Transition | Who decides? | Conditions | Minimum consequences |
| --- | --- | --- | --- |
| Non-existent → PENDING_VERIFICATION | Public signup service | Valid data, unique email, bot/abuse protection | Store hash, issue verification token, send notification |
| PENDING → ACTIVE | Token verifier | Valid token, not expired/consumed, right purpose and account | Mark `emailVerifiedAt`, allow auth |
| ACTIVE → SUSPENDED | Admin/risk service | Authority and business policy | Block new logins, revoke sessions/tokens as required |
| SUSPENDED → ACTIVE | Authorized reviewer | Suspension reason resolved | Audit, send notification; never auto-escalate roles |
| ACTIVE → CLOSED | Account owner via strong auth or authorized admin | Check data/billing/retention obligations | Disable logins, block token issuance, handle data |
| ACTIVE → ACTIVE (reset password) | Owner of recovery channel/strong flow | Valid reset token, new policy, abuse protection | Change password hash, revoke sessions/tokens per policy |

**Invariant:** An unverified or suspended account must not log in via normal username/password. Password reset **must not automatically activate** a suspended account. Roles self-claimed by users in JSON **must never** be placed directly into `GrantedAuthority`.

## 4. Account Registration Flow

### 4.1. Business steps

```text
1. Anonymous POST /auth/register
   { email, password, ...allowed fields }
            |
            v
2. Validate data + password policy + abuse checks
            |
            v
3. Transaction: create Account(PENDING_VERIFICATION)
   - passwordHash = PasswordEncoder.encode(rawPassword)
   - roles = [ROLE_USER] assigned by SERVER
   - normalizedEmail has UNIQUE constraint
            |
            v
4. Create random verification token with purpose + expiry
   - store digest, never store raw token in database
   - outbox event "SEND_VERIFY_EMAIL"
            |
            v
5. Commit transaction
            |
            v
6. Email worker sends link via fixed configured origin
            |
            v
7. User verifies -> atomically consume token -> ACTIVE
            |
            v
8. User can log in via Spring Security provider
```

Do not leave the user ACTIVE immediately upon receiving an unverified email if email ownership is a mandatory product requirement. If the product allows limited usage before verification, define explicit capabilities/permissions and expiration rather than accidentally granting full functionality.

### 4.2. Why must the database have a unique constraint?

Two registration requests for the same email can run concurrently:

```text
Request A: checks email not present
Request B: checks email not present
Request A: insert
Request B: insert
```

If you only check `existsByEmail` and then insert, both can observe "does not exist". You must have a unique index/constraint in the database combined with transactions, catch duplicate errors, and return an appropriate response. When anti-enumeration is needed, public signup responses should be carefully unified so accounts are not disclosed; UX and security must be balanced per product policy.

### 4.3. Users must not request their own roles

**Dangerous anti-pattern:**

```json
{
  "email": "new@example.test",
  "password": "ExamplePassphrase2026",
  "roles": ["ROLE_ADMIN"]
}
```

If the backend maps the request JSON directly into an entity and saves roles, an anonymous user can elevate their own privileges. Public registration DTOs must contain only fields needed for signup; the service creates the account with a server-assigned default role. Staff/admin roles must be handled through audited invitation/provisioning/approval flows.

### 4.4. Email validation and verification are not the same

- **Validation:** String matches system format and length rules; checks empty input, control characters, Unicode, length.
- **Verification:** Someone actually controls the inbox/delivery channel via a single-use token. Checking MX records or regex alone **does not prove** the user receives the email.
- **Identity proofing:** May require stronger evidence than email depending on risk (finance, healthcare, enterprise); email verification does not prove legal identity.
- **Re-verification:** When changing email, verify the new email and notify the old channel; never silently change the login identifier from a single request in a potentially hijacked session.

## 5. Recovery: "Forgot Password" Is a Special Security Transaction

### 5.1. Two endpoints with different responsibilities

```text
POST /auth/recovery/request
   Body: { "email": "alice@example.test" }
   -> return generic notice, e.g. HTTP 202
   -> if an eligible account exists, send token via registered channel

POST /auth/recovery/complete
   Body: { "token": "<opaque token>", "newPassword": "..." }
   -> verify/consume token and update password hash
   -> do not auto-log in
   -> notify password changed via appropriate channel
```

**Never send a new password via email.** The reset email/link is proof of control over the recovery channel at a product-acceptable level, not a password. Only after the user chooses a new password with a valid token is the hash updated.

### 5.2. Required properties of a reset token

- **Generated from CSPRNG:** e.g., 32 bytes via `SecureRandom`, URL-safe Base64 encoded. Never use `Random`, timestamps, userId, or email as a secret.
- **Sufficient entropy:** 256 random bits is strong enough for learning; never compute from public data.
- **Purpose-bound:** a password-reset token must not substitute for an email-verify token, login access token, or refresh token.
- **Expiring:** e.g., 15 minutes in the demo; production chooses TTL by risk/UX and tests it.
- **Single-use:** consume **atomically**; between two racing requests, only one succeeds.
- **Stored safely:** store a SHA-256/HMAC digest of the random token in the DB, never plaintext; fast hashing is appropriate because the token has high entropy (unlike low-entropy human passwords).
- **Rate-limited issuance:** rate limit by account/IP/device/ASN/risk; curb resends, spam, and DoS; return generic notices even for non-existent emails.
- **Never leaked:** keep tokens out of logs, analytics, browser referrers, caches, and off-origin redirects; use HTTPS and `Referrer-Policy: no-referrer` when rendering forms with tokens in URLs.
- **No auto-login after reset:** a recovery token is for changing the password, not a session credential to enter the app immediately.
- **Session policy:** after changing a password, typically revoke old sessions/refresh tokens and require fresh login, depending on the threat model.

### 5.3. Avoiding account enumeration

**Wrong:**

```http
POST /auth/recovery/request
{"email":"not-found@example.test"}

HTTP/1.1 404
{"error":"This email does not exist"}
```

Such a response helps attackers confirm which emails have accounts. A better approach is a generic notice, for example:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"message":"If the account is eligible, instructions will be sent."}
```

Apply the generic notice uniformly across existing/non-existent accounts, suspended status, and eligibility policies. **Timing can also leak:** if a real account generates a token + calls SMTP synchronously while a non-existent email returns immediately, attackers can measure response time. Production should use enqueue/outbox patterns to minimize timing differences, load control, and rate limits; never assume a fixed response alone solves all enumeration.

### 5.4. Why does SHA-256 of a reset token differ from password hashing?

Human passwords are often guessable from dictionaries, so use an appropriate `PasswordEncoder` like bcrypt/Argon2/PBKDF2 with a tuned work factor. A 32-byte random token generated from a CSPRNG has no predictable structure; you can store `SHA-256(token)` or a server-side HMAC digest for comparison. A DB leak reveals only digests that cannot practically be brute-forced back to the raw token.

**Never use plain `SHA-256(password)` instead of proper password hashing.** The two secret types have very different threat models and entropy.

### 5.5. Token links and email scanners

Many email systems run link scanners that automatically fetch URLs. Therefore **a GET link in an email must never change the password or consume the token simply by being opened**. It should render a form/confirmation page, and then the client submits a confirmed POST with the token and new password. If designing email verification via a GET link, account for automatic scanner hits and require a confirmation step suited to product risk.

Links should be built from an **official origin in configuration**, e.g. `https://accounts.example.test/reset?token=...`. Never use client-controlled `Host` or `X-Forwarded-Host` headers directly to assemble reset links sent by email, as this easily causes host-header poisoning/phishing. Tokens in URLs require referrer/cache/history handling and exclusion from reverse-proxy logs.

## 6. Changing Password While Logged In vs. Password Recovery

| Scenario | Required proof | Execution channel | Primary risk |
| --- | --- | --- | --- |
| In-session password change | Valid session + re-checking current password/MFA when needed | `POST /account/change-password` | Session hijacking, CSRF, skipping re-auth |
| Forgot password | Single-use recovery token from verified channel | `POST /auth/recovery/complete` | Token guessing/theft, enumeration |
| Admin-initiated reset | Authorized staff + policy review | Admin API triggers workflow, never sets arbitrary password | Insider abuse, leaked reset link |
| Email change | Session + re-auth + verify new email | Account workflow | Account takeover via swapping recovery channel |
| SSO/OIDC user | Per IdP policy | IdP self-service or administration | Changing wrong credential not owned by app |

A "change password" UI inside a logged-in session typically requires the current password or step-up (MFA, passkey) for sensitive actions. Do not trust a long-lived session cookie alone. For a newly recovered account, notify remaining trusted channels, consider revoking sessions, and require a fresh login.

## 7. Account Administration: Suspend, Reinstate, Assign Roles, Close, and Audit

### 7.1. Administration is a distinct set of permissions

Example APIs:

```text
POST /admin/accounts/{id}/suspend
POST /admin/accounts/{id}/reinstate
POST /admin/accounts/{id}/role-grants
POST /admin/accounts/{id}/revoke-sessions
POST /admin/accounts/{id}/close
```

All are **state-changing** operations. They require at minimum:

- Real staff authentication and minimal corresponding authorities (`ACCOUNT_SUSPEND`, `ROLE_GRANT`, `ACCOUNT_CLOSE`), not necessarily a single `ROLE_ADMIN`.
- Policies covering actor, subject account, tenant, and permission scope. An admin of organization A **does not automatically** have permission to suspend users in organization B.
- Re-auth/step-up or approval workflows for granting admin rights, resetting MFA, or changing sensitive permissions.
- Audit events recording actor, account ID, before/after (redacted), reason, correlation ID, outcome; never logging secrets.
- IDOR/BOLA defenses: verify the subject account falls within the staff member's assigned scope.
- Proper session/token revocation on suspend/close/credential change, not merely flipping a DB column.
- Idempotency/transactions so request retries do not resend emails or duplicate audit records dangerously.

### 7.2. When does UserDetails.isEnabled() take effect?

In password authentication using `DaoAuthenticationProvider`, a custom `UserDetailsService` can map:

```java
boolean allowed = account.status() == AccountStatus.ACTIVE;

return User.withUsername(account.email())
    .password(account.passwordHash())
    .authorities(account.authorities().toArray(String[]::new))
    .disabled(!allowed)
    .build();
```

When an account is unverified/suspended, the provider normally rejects password authentication as disabled. **However:** this does not mean previously logged-in sessions are revoked immediately. If Spring Security restores an `Authentication` from a session, the provider does not necessarily re-query the user store on every request. You must design session invalidation/revocation, denylists, or token versioning/validation per your authentication mechanism.

### 7.3. Closing an account does not mean deleting all data immediately

Closing an account may pass through `DELETION_SCHEDULED`, `CLOSED`, `ANONYMIZED`, and valid retention steps for transaction history or compliance. Exact rules belong to product/legal/data governance; never immediately call `repository.deleteById` ignoring foreign keys, payments, audits, and retention obligations. Once closed, block logins and new token issuance, cancel valid recovery tokens, and manage related data.

### 7.4. Role assignment cannot depend on email or display name

Permissions must be managed by **account ID** or a trusted principal, server-stored roles/permissions, and tenant/organization context. Never write `if (email.endsWith("@company.com")) grant ADMIN`; an email domain does not prove someone is currently an employee with admin rights. With an IdP, mapping roles from claims must verify issuer, audience, signature, expiry, and group/tenant policies.

## 8. Data Architecture and Transactions for Multi-Instance Apps

Below is a conceptual database design. Type names and SQL syntax may need adjustment for PostgreSQL/MySQL and migration tools:

```sql
CREATE TABLE accounts (
    id                UUID PRIMARY KEY,
    normalized_email  VARCHAR(320) NOT NULL UNIQUE,
    password_hash     VARCHAR(255) NOT NULL,
    status            VARCHAR(40) NOT NULL,
    email_verified_at TIMESTAMP NULL,
    credential_version BIGINT NOT NULL DEFAULT 0,
    version           BIGINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE account_roles (
    account_id UUID NOT NULL,
    authority  VARCHAR(120) NOT NULL,
    PRIMARY KEY (account_id, authority)
);

CREATE TABLE account_action_tokens (
    id          UUID PRIMARY KEY,
    account_id  UUID NOT NULL,
    purpose     VARCHAR(40) NOT NULL,
    token_hash  VARCHAR(128) NOT NULL UNIQUE,
    expires_at  TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP NULL,
    created_at  TIMESTAMP NOT NULL
);

CREATE TABLE account_outbox (
    id             UUID PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    account_id     UUID NOT NULL,
    payload_ciphertext TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    delivered_at   TIMESTAMP NULL
);
```

**Note:** This is an illustrative schema rather than a database-agnostic migration script. Production should include appropriate foreign keys, indexes for token/account lookups, status constraints, auditing, TTL cleanup, and protection for outbox payloads. If the outbox holds a raw reset token for an email worker to send after commit, the payload must be encrypted/access-restricted and purged on a very short retention; never leave plaintext tokens sitting indefinitely in the table. Another option is having a worker generate the token and store the digest in a separate controlled transaction.

### 8.1. Registration transaction

```text
BEGIN
  INSERT account(status=PENDING_VERIFICATION, password_hash, default_roles)
  INSERT account_action_token(hash, purpose=VERIFY_EMAIL, expires_at)
  INSERT outbox_message(SEND_EMAIL_VERIFICATION)
COMMIT
Background dispatcher delivers message; retry with idempotency key.
```

Create the account and token/outbox as one logical unit so an account does not get stranded without an email if a transaction rolls back midway. Never send the email directly before committing: if the DB commit fails, the user receives an invalid link.

### 8.2. Reset-token consumption transaction

```text
BEGIN
  Look up token by digest with lock or atomic UPDATE:
    purpose=RESET_PASSWORD
    consumed_at IS NULL
    expires_at > now()
  Allow only one request to mark consumed_at = now().
  Verify account is still ACTIVE and token belongs to that account.
  UPDATE accounts SET password_hash=?, credential_version=version+1, ...
  Invalidate other still-valid tokens of the same type if policy requires.
  INSERT outbox notification / audit event.
COMMIT
After commit:
  Send notification, invalidate sessions/refresh tokens per designed mechanism.
```

If you only do:

```java
if (tokenRepository.find(token).isValid()) {
    account.setPasswordHash(newHash);
    tokenRepository.delete(token);
}
```

then two concurrent requests can both see the token as valid before it is deleted. You need a transaction combined with row locking, optimistic locking, or a conditional atomic consume update. Retrying after the first attempt must fail without changing the password a second time. Never reuse a single token for both email verification and password reset.

### 8.3. Do not auto-issue a session after reset

A reset token is sufficient evidence to set a new password under the risk model; it **is not an access token**. After a successful reset, the response should require the user to log in normally, optionally forcing MFA again per policy. Existing sessions/refresh tokens must be revoked when policy requires; incrementing `credential_version` only works if the authentication/session/token pipeline actually **checks this version** on access.

## 9. Hands-On Demo: Spring Boot 3.5.16 + In-Memory Account Lifecycle

This demo uses **in-memory state** to clarify the flow and run easily with Java 17 and Spring Security 6.5; it **does not implement database persistence/transactions, real email delivery, distributed rate limiting, or production token revocation**. In the demo, a `DemoOutbox` writes tokens to RAM so **JUnit can read them directly**, with no API returning raw tokens to clients. Never package this kind of configuration/token storage into production.

**Versions:** `Spring Boot 3.5.16` (released 2026-06-25, final OSS release of the 3.5.x line) and Security 6.5.x from the Boot BOM; when creating new apps for production deployment, use a still-supported Boot 4.x release and the Spring Security 7 migration guide if applicable.

### 9.1. Structure

```text
account-lifecycle-lab/
├── pom.xml
└── src/
    ├── main/java/demo/lifecycle/AccountLifecycleApplication.java
    └── test/java/demo/lifecycle/
        ├── AccountLifecycleHttpTests.java
        └── AccountLifecycleServiceTests.java
```

These are two test classes using the same application code for different goals: one tests HTTP filters/permissions; the other tests the state machine and single-use tokens at the service level.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>account-lifecycle-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. Complete application code

Create `src/main/java/demo/lifecycle/AccountLifecycleApplication.java`. For lab convenience, package-private classes live in one file; in a real project, split them into `account/api`, `domain`, `repository`, `security`, and `messaging`.

```java
package demo.lifecycle;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class AccountLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountLifecycleApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
class WebSecurityConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AccountLifecycleService accounts) {
        return email -> {
            Account account = accounts.find(email)
                .orElseThrow(() ->
                    new UsernameNotFoundException("User not found"));

            return User.withUsername(account.email())
                .password(account.passwordHash())
                .authorities(account.authorities().toArray(String[]::new))
                .disabled(account.status() != AccountStatus.ACTIVE)
                .build();
        };
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/auth/register",
                    "/auth/verify",
                    "/auth/recovery/request",
                    "/auth/recovery/complete").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.POST,
                    "/admin/accounts/*/suspend").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Keep CSRF: anonymous POSTs can also require a CSRF token.
            .csrf(Customizer.withDefaults())
            .build();
    }
}

enum AccountStatus {
    PENDING_VERIFICATION, ACTIVE, SUSPENDED
}

enum TokenPurpose {
    VERIFY_EMAIL, RESET_PASSWORD
}

record Account(
    String email,
    String passwordHash,
    AccountStatus status,
    Set<String> authorities
) {
    Account {
        authorities = Set.copyOf(authorities);
    }

    Account withStatus(AccountStatus next) {
        return new Account(email, passwordHash, next, authorities);
    }

    Account withPassword(String encoded) {
        return new Account(email, encoded, status, authorities);
    }
}

record ActionToken(
    String email,
    TokenPurpose purpose,
    Instant expiresAt
) {}

/**
 * Fake mailbox solely for demo/test.
 * Raw tokens live in RAM; do not deploy this bean to production.
 */
@Component
class DemoOutbox {
    private final Map<String, EnumMap<TokenPurpose, String>> mailbox =
        new HashMap<>();

    synchronized void deliver(String email, TokenPurpose purpose,
            String rawToken) {
        mailbox.computeIfAbsent(email,
            key -> new EnumMap<>(TokenPurpose.class))
            .put(purpose, rawToken);
    }

    synchronized String lastToken(String email, TokenPurpose purpose) {
        EnumMap<TokenPurpose, String> tokens = mailbox.get(email);
        return tokens == null ? null : tokens.get(purpose);
    }
}

@Service
class AccountLifecycleService {

    private static final Duration TOKEN_TTL = Duration.ofMinutes(15);

    private final Map<String, Account> accounts = new HashMap<>();
    private final Map<String, ActionToken> actionTokens = new HashMap<>();
    private final SecureRandom random = new SecureRandom();

    private final PasswordEncoder encoder;
    private final Clock clock;
    private final DemoOutbox outbox;

    AccountLifecycleService(PasswordEncoder encoder, Clock clock,
            DemoOutbox outbox) {
        this.encoder = encoder;
        this.clock = clock;
        this.outbox = outbox;
    }

    synchronized Optional<Account> find(String email) {
        return Optional.ofNullable(accounts.get(normalize(email)));
    }

    synchronized void register(String rawEmail, String password) {
        String email = validatedEmail(rawEmail);
        validatePassword(password);

        // Public response must stay identical when email already exists.
        if (accounts.containsKey(email)) {
            return;
        }

        // Default role is decided by the server.
        Account account = new Account(
            email,
            encoder.encode(password),
            AccountStatus.PENDING_VERIFICATION,
            Set.of("ROLE_USER")
        );

        accounts.put(email, account);
        issueToken(email, TokenPurpose.VERIFY_EMAIL);
    }

    synchronized boolean verifyEmail(String rawToken) {
        ActionToken action =
            consume(rawToken, TokenPurpose.VERIFY_EMAIL);

        if (action == null) {
            return false;
        }

        Account account = accounts.get(action.email());

        if (account == null ||
                account.status() != AccountStatus.PENDING_VERIFICATION) {
            return false;
        }

        accounts.put(account.email(),
            account.withStatus(AccountStatus.ACTIVE));
        return true;
    }

    synchronized void requestPasswordReset(String rawEmail) {
        // Intentionally do not reveal whether the email exists in HTTP response.
        String email = normalize(rawEmail);
        Account account = accounts.get(email);

        if (account == null || account.status() != AccountStatus.ACTIVE) {
            return;
        }

        issueToken(email, TokenPurpose.RESET_PASSWORD);
    }

    synchronized boolean resetPassword(String rawToken,
            String newPassword) {
        validatePassword(newPassword);

        ActionToken action =
            consume(rawToken, TokenPurpose.RESET_PASSWORD);

        if (action == null) {
            return false;
        }

        Account account = accounts.get(action.email());

        // Reset has no authority to reopen a suspended account.
        if (account == null || account.status() != AccountStatus.ACTIVE) {
            return false;
        }

        accounts.put(account.email(),
            account.withPassword(encoder.encode(newPassword)));

        // Demo: invalidate all remaining action tokens for the account.
        actionTokens.entrySet().removeIf(e ->
            e.getValue().email().equals(account.email()));

        // Production: audit, notification, and session/refresh-token revocation.
        return true;
    }

    synchronized void suspend(String rawEmail) {
        String email = normalize(rawEmail);
        Account account = accounts.get(email);

        if (account == null) {
            throw new IllegalArgumentException("Invalid account");
        }

        accounts.put(email,
            account.withStatus(AccountStatus.SUSPENDED));

        actionTokens.entrySet().removeIf(e ->
            e.getValue().email().equals(email));
    }

    private void issueToken(String email, TokenPurpose purpose) {
        // One unused token / purpose / account at a time.
        actionTokens.entrySet().removeIf(e ->
            e.getValue().email().equals(email)
                && e.getValue().purpose() == purpose);

        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        String raw = Base64.getUrlEncoder()
            .withoutPadding().encodeToString(bytes);

        actionTokens.put(digest(raw),
            new ActionToken(email, purpose,
                clock.instant().plus(TOKEN_TTL)));

        // Production: store digest + outbox atomically in DB,
        // email worker sends raw link via controlled channel.
        outbox.deliver(email, purpose, raw);
    }

    private ActionToken consume(String rawToken, TokenPurpose purpose) {
        String hash = digest(rawToken);

        if (hash == null) {
            return null;
        }

        ActionToken action = actionTokens.get(hash);

        if (action == null || action.purpose() != purpose) {
            return null;
        }

        // Remove token before applying state transition.
        // synchronized guarantees single-use within ONE lab JVM.
        actionTokens.remove(hash);

        if (!clock.instant().isBefore(action.expiresAt())) {
            return null;
        }

        return action;
    }

    private static String digest(String rawToken) {
        if (rawToken == null || rawToken.isBlank()
                || rawToken.length() > 200) {
            return null;
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static String normalize(String rawEmail) {
        return rawEmail == null ? ""
            : rawEmail.trim().toLowerCase(Locale.ROOT);
    }

    private static String validatedEmail(String rawEmail) {
        String email = normalize(rawEmail);

        // Simple validation FOR DEMO ONLY; real email needs dedicated policy.
        if (email.length() > 254
                || !email.matches("[^@\\s]+@[^@\\s]+\\.[^@\\s]+")) {
            throw new IllegalArgumentException("Invalid email");
        }

        return email;
    }

    private static void validatePassword(String password) {
        // Passwords must never be trimmed or silently truncated.
        if (password == null ||
                password.length() < 12 || password.length() > 128) {
            throw new IllegalArgumentException("Invalid password");
        }
    }
}

@Service
class AccountAdministrationService {
    private final AccountLifecycleService accounts;

    AccountAdministrationService(AccountLifecycleService accounts) {
        this.accounts = accounts;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void suspendAccount(String email) {
        // Production: actor/subject/tenant checks, approval, and auditing.
        accounts.suspend(email);
    }
}

record RegistrationRequest(String email, String password) {}
record VerifyRequest(String token) {}
record EmailRequest(String email) {}
record ResetRequest(String token, String newPassword) {}
record Notice(String message) {}

@RestController
class AccountController {

    private static final Notice GENERIC_NOTICE =
        new Notice("If eligible, instructions will be sent.");

    private final AccountLifecycleService accounts;
    private final AccountAdministrationService administration;

    AccountController(AccountLifecycleService accounts,
            AccountAdministrationService administration) {
        this.accounts = accounts;
        this.administration = administration;
    }

    @PostMapping("/auth/register")
    ResponseEntity<Notice> register(@RequestBody RegistrationRequest request) {
        accounts.register(request.email(), request.password());
        return ResponseEntity.accepted().body(GENERIC_NOTICE);
    }

    @PostMapping("/auth/verify")
    ResponseEntity<Void> verify(@RequestBody VerifyRequest request) {
        if (!accounts.verifyEmail(request.token())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid or expired token");
        }
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/auth/recovery/request")
    ResponseEntity<Notice> requestRecovery(@RequestBody EmailRequest request) {
        accounts.requestPasswordReset(request.email());
        return ResponseEntity.accepted().body(GENERIC_NOTICE);
    }

    @PostMapping("/auth/recovery/complete")
    ResponseEntity<Void> completeRecovery(@RequestBody ResetRequest request) {
        if (!accounts.resetPassword(
                request.token(), request.newPassword())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid or expired token");
        }
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/admin/accounts/{email}/suspend")
    ResponseEntity<Void> suspend(@PathVariable String email) {
        administration.suspendAccount(email);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }
}

@RestControllerAdvice
class ValidationErrors {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Notice> invalidInput() {
        return ResponseEntity.badRequest()
            .body(new Notice("Invalid request"));
    }
}
```

### 9.4. Reading the code by responsibility

- `register(...)` creates a `PENDING_VERIFICATION` account with server-fixed `ROLE_USER`; the request DTO contains no role.
- `verifyEmail(...)` accepts only `VERIFY_EMAIL` tokens, checks TTL and state, and transitions to `ACTIVE`. Used tokens are deleted.
- `requestPasswordReset(...)` issues tokens only for ACTIVE accounts, yet **the HTTP response is identical** for non-existent emails.
- `resetPassword(...)` verifies `RESET_PASSWORD` tokens, replaces the password hash using `DelegatingPasswordEncoder`, and never turns `SUSPENDED` into `ACTIVE`.
- `digest(...)` hashes random tokens before storing; `SecureRandom` provides high-entropy tokens and `Base64 URL-safe` makes tokens safe for links.
- Service methods use `synchronized` to prevent two requests from consuming the same token in **one JVM**. They do not solve multi-replica concurrency; moving to a DB requires transactions and atomic updates.
- `DemoOutbox` is intentionally a fake mailbox holding raw tokens for tests to read directly. Real apps must use a secure mail gateway/outbox with no token-reading endpoint.
- `UserDetailsService` is an adapter from the Account store to Spring Security. Non-ACTIVE accounts map to disabled; the provider rejects login.
- `AccountAdministrationService` requires `ROLE_ADMIN` at both HTTP and method levels. The demo provides no self-signup path for admin: this is intentional because administrative rights must be provisioned via trusted channels.
- `SessionCreationPolicy.STATELESS` uses Basic credentials per request. A suspended account is blocked on the next Basic authentication; with sessions/JWTs, explicit revocation must be designed.
- CSRF remains enabled for POSTs. A browser SPA using cookies/Basic can attach credentials automatically; never disable CSRF without evaluating the authentication model.
- `ValidationErrors` returns generic errors for bad inputs. The demo lacks real email delivery, rate limiting, abuse controls, and transactional failure handling. All of those are required before production.

### 9.5. HTTP integration test: from registration to suspend

Create `src/test/java/demo/lifecycle/AccountLifecycleHttpTests.java`:

```java
package demo.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountLifecycleHttpTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoOutbox outbox;

    private static final String EMAIL = "alice107@example.test";
    private static final String ORIGINAL = "FirstPassphrase2026!";
    private static final String CHANGED = "SecondPassphrase2026!";

    @Test
    void completeLifecycleWithAuthenticationAndAuthorization()
            throws Exception {

        // Anonymous POST missing CSRF is rejected.
        mvc.perform(post("/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"alice107@example.test",
                     "password":"FirstPassphrase2026!"}
                    """))
            .andExpect(status().isForbidden());

        // Registration returns 202 and does not return raw token.
        mvc.perform(post("/auth/register")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"email":"alice107@example.test",
                     "password":"FirstPassphrase2026!"}
                    """))
            .andExpect(status().isAccepted());

        // Email not yet verified => provider rejects login.
        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, ORIGINAL)))
            .andExpect(status().isUnauthorized());

        // Test-only: read token from fake outbox, not via HTTP.
        String verify = outbox.lastToken(
            EMAIL, TokenPurpose.VERIFY_EMAIL);

        mvc.perform(post("/auth/verify")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + verify + "\"}"))
            .andExpect(status().isNoContent());

        // Verify token is single-use only.
        mvc.perform(post("/auth/verify")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + verify + "\"}"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, ORIGINAL)))
            .andExpect(status().isOk())
            .andExpect(content().string("me:" + EMAIL));

        // Public reset request does not leak account existence.
        mvc.perform(post("/auth/recovery/request")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"nobody@example.test\"}"))
            .andExpect(status().isAccepted());

        mvc.perform(post("/auth/recovery/request")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"" + EMAIL + "\"}"))
            .andExpect(status().isAccepted());

        String reset = outbox.lastToken(
            EMAIL, TokenPurpose.RESET_PASSWORD);

        mvc.perform(post("/auth/recovery/complete")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + reset + "\"," +
                    "\"newPassword\":\"" + CHANGED + "\"}"))
            .andExpect(status().isNoContent());

        // Reset token can no longer be reused.
        mvc.perform(post("/auth/recovery/complete")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"token\":\"" + reset + "\"," +
                    "\"newPassword\":\"SomeOtherPass2026!\"}"))
            .andExpect(status().isBadRequest());

        // Basic checks new hash: old password is no longer valid.
        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, ORIGINAL)))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, CHANGED)))
            .andExpect(status().isOk());

        // Normal user cannot call admin API.
        mvc.perform(post("/admin/accounts/" + EMAIL + "/suspend")
                .with(httpBasic(EMAIL, CHANGED))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Staff account is a test mock to verify admin policy.
        // Demo provides no public endpoint creating ROLE_ADMIN.
        mvc.perform(post("/admin/accounts/" + EMAIL + "/suspend")
                .with(user("staff").roles("ADMIN"))
                .with(csrf()))
            .andExpect(status().isNoContent());

        mvc.perform(get("/me")
                .with(httpBasic(EMAIL, CHANGED)))
            .andExpect(status().isUnauthorized());
    }
}
```

**Detailed test walkthrough:**

1. The registration request is permitted by **authorization**, yet because CSRF is enabled, a POST without a CSRF token still gets 403. `permitAll` does not mean bypassing `CsrfFilter`.
2. A newly registered but unverified account is rejected at login despite having the right password.
3. The test reads raw verification/reset tokens only via the `DemoOutbox` Java bean, never through a public HTTP endpoint.
4. A valid verify token transitions the account to ACTIVE; reusing the token gets 400.
5. HTTP Basic uses the app's real `UserDetailsService` and `PasswordEncoder`, so the test exercises a real authentication path—unlike `@WithMockUser`.
6. Password reset updates the stored hash; Basic with the old password returns 401, with the new password returns 200; the reset token is consumed once.
7. `user("staff").roles("ADMIN")` is a **mock** authentication to test administrative authorization. It does not verify production admin accounts or real passwords. Regular users remain blocked.
8. After suspension, the account is disabled for subsequent Basic authentications. When using production sessions/OIDC/JWT, you must also verify that the revocation mechanism is implemented.

This test uses a fixed email fixture and a single method walking through the lifecycle because the demo service keeps state in RAM. When adding multiple independent tests, use random per-test emails, factory-created instances, or context isolation; never let later tests depend on ordering or sessions/tokens from earlier tests.

### 9.6. Service test: expired tokens and invalid state transitions

Create `src/test/java/demo/lifecycle/AccountLifecycleServiceTests.java`:

```java
package demo.lifecycle;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AccountLifecycleServiceTests {

    private static final String EMAIL = "student@example.test";
    private static final String ORIGINAL = "LongPassphrase2026!";
    private static final String NEW_PASSWORD = "AnotherPassphrase2026!";

    static final class MutableClock extends Clock {
        private Instant now = Instant.parse("2026-11-04T00:00:00Z");

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        @Override
        public Instant instant() {
            return now;
        }

        void advance(Duration duration) {
            now = now.plus(duration);
        }
    }

    @Test
    void verificationIsSingleUseAndRecoveryExpires() {
        MutableClock clock = new MutableClock();
        DemoOutbox outbox = new DemoOutbox();
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        AccountLifecycleService service =
            new AccountLifecycleService(encoder, clock, outbox);

        service.register(EMAIL, ORIGINAL);

        Account pending = service.find(EMAIL).orElseThrow();
        assertEquals(
            AccountStatus.PENDING_VERIFICATION, pending.status());
        assertEquals(java.util.Set.of("ROLE_USER"),
            pending.authorities());
        assertTrue(encoder.matches(
            ORIGINAL, pending.passwordHash()));

        String verify = outbox.lastToken(
            EMAIL, TokenPurpose.VERIFY_EMAIL);
        assertNotNull(verify);

        // Reset cannot accept a verification token.
        assertFalse(service.resetPassword(
            verify, NEW_PASSWORD));

        assertTrue(service.verifyEmail(verify));
        assertFalse(service.verifyEmail(verify));
        assertEquals(AccountStatus.ACTIVE,
            service.find(EMAIL).orElseThrow().status());

        service.requestPasswordReset(EMAIL);
        String reset = outbox.lastToken(
            EMAIL, TokenPurpose.RESET_PASSWORD);
        assertNotNull(reset);

        // 15-minute token: expires at exact expiry.
        clock.advance(Duration.ofMinutes(16));

        assertFalse(service.resetPassword(reset, NEW_PASSWORD));
        assertTrue(encoder.matches(
            ORIGINAL, service.find(EMAIL).orElseThrow().passwordHash()));

        service.requestPasswordReset(EMAIL);
        String fresh = outbox.lastToken(
            EMAIL, TokenPurpose.RESET_PASSWORD);

        assertTrue(service.resetPassword(fresh, NEW_PASSWORD));
        assertFalse(service.resetPassword(fresh, NEW_PASSWORD));
        assertTrue(encoder.matches(
            NEW_PASSWORD, service.find(EMAIL).orElseThrow().passwordHash()));

        service.suspend(EMAIL);
        assertEquals(AccountStatus.SUSPENDED,
            service.find(EMAIL).orElseThrow().status());

        // Recovery does not automatically reopen a suspended account.
        service.requestPasswordReset(EMAIL);
        assertFalse(service.resetPassword(
            fresh, "ThirdPassphrase2026!"));
    }

    @Test
    void duplicateRegistrationCannotGrantAdminPrivilege() {
        DemoOutbox outbox = new DemoOutbox();
        AccountLifecycleService service = new AccountLifecycleService(
            PasswordEncoderFactories.createDelegatingPasswordEncoder(),
            Clock.fixed(Instant.parse("2026-11-04T00:00:00Z"),
                ZoneOffset.UTC),
            outbox
        );

        service.register(EMAIL, ORIGINAL);
        service.register(EMAIL, "DifferentPassphrase2026!");

        Account unchanged = service.find(EMAIL).orElseThrow();

        assertEquals(java.util.Set.of("ROLE_USER"),
            unchanged.authorities());

        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();
        assertTrue(encoder.matches(
            ORIGINAL, unchanged.passwordHash()));
        assertFalse(encoder.matches(
            "DifferentPassphrase2026!", unchanged.passwordHash()));
    }
}
```

**Unit test limitations:** `MutableClock` reproduces expiration without `Thread.sleep`. `synchronized` protects operations within one service instance; there are no multi-JVM/transaction tests or real SMTP yet. Production tests should add concurrent races of two reset requests, optimistic locking/unique constraints, outbox delivery/retry, rate limiting, CSRF, and session/token revocation.

### 9.7. Running and observing

In the `account-lifecycle-lab` directory:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Once the server runs on localhost, you can test public endpoints with curl and JSON; **POST requires a CSRF token** per configuration. Because the demo provides no browser flow to fetch CSRF tokens or real SMTP, use the **MockMvc tests above** to run the complete verification/recovery flow reproducibly. Never disable CSRF and never expose tokens from the fake outbox on a public endpoint just for curl convenience.

On a real production system, the registration/recovery frontend must have a mechanism to obtain/send CSRF tokens per `CsrfTokenRepository` if using browser credentials at risk of CSRF, or have a distinct policy explicitly configured for pure Bearer APIs per the threat model. Expected outcomes when running with matching dependencies and JDK:

| Request | Expected | Evidence |
| --- | --- | --- |
| POST register missing CSRF | 403 | CSRF filter |
| POST register with CSRF, new email | 202 generic | No raw verification token returned |
| GET /me with newly created email | 401 | Not yet verified, disabled |
| POST verify with valid token | 204 | ACTIVE |
| POST verify reusing token | 400 | Single-use |
| GET /me + valid Basic after verify | 200 | UserDetailsService/PasswordEncoder |
| POST request recovery non-existent email | 202 generic | Reduces enumeration |
| POST complete reset valid token | 204 | Updates hash |
| POST complete reusing token | 400 | Single-use |
| GET /me with old password | 401 | Hash changed |
| GET /me with new password | 200 | Provider uses new hash |
| POST admin suspend with regular user | 403 | Lacks ROLE_ADMIN |
| POST admin suspend with mock staff | 204 | Admin policy |
| GET /me after suspend | 401 | Account disabled |

**What is missing from the demo:** Real email, password-changed notifications, reset UI flow, queue-based anti-enumeration timing control, persistent repository, distributed transactions, session revocation, and abuse monitoring. Do not treat the demo as a production-ready product.

## 10. Moving to a Database: What Should UserDetailsService Mapping Do?

An illustrative adapter showing only how to connect Spring Security to the business store:

```java
@Service
class DatabaseUserDetailsService implements UserDetailsService {
    private final AccountRepository repository;

    DatabaseUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        AccountEntity account = repository
            .findByLoginIdentifier(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.getId().toString())
            .password(account.getPasswordHash())
            .authorities(account.getAuthorities()
                .toArray(String[]::new))
            .disabled(account.getStatus() != AccountStatus.ACTIVE)
            .accountLocked(account.isRiskLocked())
            .build();
    }
}
```

**This is a design snippet, not a standalone compilable file:** `AccountRepository`/`AccountEntity` and mappings vary by project. If `username` in `UserDetails` becomes an ID, clearly define how the login identifier is looked up and what `Authentication.getName()` will return. In systems using email login, you can return email as username like the demo, yet provide a domain principal containing the immutable ID when ownership checks are needed.

`UserDetailsService` only loads users for the username/password mechanism. Never put email sending or reset token creation inside this method. If using OIDC/JWT, info may come from the IdP/verified claims, with internal accounts linked via stable subjects—never trusting unverified emails or omitting `issuer`.

### 10.1. Transactions belong in the service, not the web filter

Account-updating operations should have transactions in the domain service:

```java
@Transactional
public void verifyEmail(String rawToken) {
    // Validate purpose/expiry; lock/atomic consume token.
    // Transition PENDING_VERIFICATION -> ACTIVE.
    // Insert audit + outbox event in the same transaction.
}
```

**The snippet above is directional pseudocode**, lacking complete repository and exception classes to run standalone. With Spring Data JPA, entity mappings, versioning, and repository methods must match transaction isolation. Do not rely on `@Transactional` alone to guarantee single-use if code still reads and updates without locking or conditions. Test concurrency races explicitly.

## 11. Security Rules for Each Workflow

### 11.1. Registration

- Validate input, protect against bots/spam/rate limits, and prevent duplicates.
- Apply an appropriate password policy, support long passphrases, and check compromised passwords when feasible.
- Hash passwords with `PasswordEncoder`; never log raw passwords.
- Assign default roles server-side, preventing mass assignment.
- Verify email/contact channel before granting privileges requiring verified identity.
- Unique constraint + transaction + outbox to prevent half-baked states.
- Protect verification endpoints from token replay and flooding resends.
- Do not auto-log in before completing the product's verification/step-up requirements.

### 11.2. Forgot / reset password

- Generic responses for both existing/non-existent accounts and ineligible accounts.
- Rate limit requests per actor/IP/account/device; detect abuse.
- Long random tokens, dedicated purpose, short TTL, single-use, hash-only storage, atomic consumption.
- HTTPS links with trusted origin from config, host-header poisoning protection, no token leaks via logs/referrer.
- POST completes reset after user confirmation, preventing link scanners from mutating state automatically.
- Never send a new password via email; the user sets their own password.
- After changing: notify, invalidate/revoke sessions and refresh tokens per policy, no auto-login.
- Require re-auth/MFA or verified manual support when recovery carries high risk.

### 11.3. Email change

- An authenticated session is **not necessarily** enough to change identity: require step-up if sensitive.
- Notify the old address; verify the new address before using it for login/recovery.
- Check unique constraints and conflicts with other accounts.
- Store pending new email separately; never immediately delete the active email before verification.
- Block changing another user's email via an `accountId` in the body if the actor lacks authorization.
- Handle IdPs that emit unverified email claims or changing emails.

### 11.4. Permission / administration changes

- Dedicated permissions, tenant/scope verification, and least-privilege principle.
- Roles/authorities never come from the frontend.
- Admin grant/revoke requires auditing, and sometimes two-person approval or step-up.
- Suspension must block new logins and revoke existing access per policy; do not rely solely on a DB boolean if sessions/JWTs do not recheck it.
- On reinstatement, verify subject, reason, evidence, and notifications.
- Closing/deleting accounts must handle data and retention properly, never calling `deleteAll` casually.

### 11.5. Testing and operations

- Include positive and negative tests: valid/invalid tokens, expiration, replay, wrong purpose, suspended account.
- Test concurrency against a real DB for atomic consumption, not just sequential JUnit runs.
- Test that APIs do not leak account existence via responses **or timing** under load.
- Use HTTPS/TLS, secret redaction, appropriate CSP/referrer policies, cookie flags, and CORS/CSRF policies.
- Audits must contain no passwords/hashes/tokens; manage retention and log read permissions.
- Monitor signup/reset rates, deliverability, unusual recovery/suspensions, and failure spikes.
- If using an external IdP, test lifecycles on the IdP instead of building a competing, out-of-sync user store.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Assuming `UserDetailsService` provides registration endpoints | Missing business flow/account store | Separate Account API/service/repository |
| Using only `InMemoryUserDetailsManager` for real users | Data lost on restart, not shared across replicas | Database/IdP, migrations, and operations |
| Signup DTO contains `roles` and copies to entity | Privilege escalation | Server-assigned default role |
| Storing plaintext/MD5/plain SHA-256 passwords | Easy password compromise/cracking | Appropriate `PasswordEncoder`, work factor |
| Unverified email already fully authenticated | Using someone else's address, spam/abuse | Pending state and verification |
| Forgot API returns 404 "email does not exist" | Account enumeration | Generic response, timing/rate limits |
| Reset token is predictable timestamp/userId/UUID | Brute-forceable | 32-byte CSPRNG, TTL, hashed storage |
| Reset token usable multiple times | Replay/second password change | Atomic consume, consumedAt/expiry |
| Verify token usable for password reset | Cross-purpose privilege | Dedicated purpose, server-side check |
| GET link directly changes password | Unintended mail scanner/CSRF hits | Confirmation form and POST |
| Reset token appears in server logs | Recovery credential theft | Redaction, no-referrer, log hygiene |
| Reset turns SUSPENDED account into ACTIVE | Bypasses admin decision | Explicit state transitions and guard checks |
| Auto-login right after reset | Elevates recovery token into session | Require fresh login per policy |
| Changing password without revoking sessions | Hijacked session stays usable | Real session/token revocation |
| Assuming DB role change updates old JWTs | Stale role claims still accepted | TTL, denylist/version/reauth |
| Only `hasRole("ADMIN")`, ignoring tenant | Organization A admin manages B | Service-level object/tenant authorization |
| Sending email before DB commit | Invalid link if transaction rolls back | Transactional outbox |
| `@Transactional` alone without locking token | Two requests both consume | Conditional update/lock + race tests |
| Logging raw request bodies/reset tokens | Secret and PII exposure | Log minimal metadata only |
| Testing only signup happy path | Misses abuse, expiry, replay | State matrix + negative tests |

## 13. Test Matrix by Status and Actor

| Scenario | Actor/account | Expectation |
| --- | --- | --- |
| Valid registration | Anonymous, new email | PENDING account; generic response |
| Duplicate registration | Anonymous, existing email | Does not overwrite password/roles; response does not leak |
| Login before verification | PENDING | Rejected |
| Valid verify | PENDING, unexpired token | Transitions to ACTIVE |
| Repeat verify | Used token | Rejected |
| Verify after TTL | Expired token | Rejected |
| Using RESET token on VERIFY endpoint | Wrong purpose | Rejected |
| Valid login after verify | ACTIVE | Authenticated |
| Recovery request non-existent email | Anonymous | Same generic response as existing email |
| Valid reset | ACTIVE, unused token | New hash, token consumed |
| Reset with old token | Used token | Rejected |
| Expired reset token | ACTIVE | Rejected, password unchanged |
| Login with old password after reset | ACTIVE | Rejected |
| Login with new password after reset | ACTIVE | Succeeds |
| Suspend account | Staff with permission | Transitions to SUSPENDED, audited/revoked |
| Suspend account | Regular user | 403, status unchanged |
| Login after suspend | SUSPENDED | Rejected |
| Reset after suspend | SUSPENDED | Does not auto-unlock |
| Email change | Re-authenticated user, new email token | Updates after verification |
| Accessing another tenant's account | Tenant-scoped admin | Denied in service |
| Close account | Authorized and obligations settled | No login, retention executed |
| Two parallel requests using same reset token | ACTIVE | Only one request commits |
| Token scanned via GET | Not yet confirmed via POST | Password not changed automatically |
| Old session after reset/suspend | Previously logged in | Revoked per policy |
| User from IdP | Authenticated by IdP | Maps subject/tenant properly, never relies on unverified email |

## 14. Self-Assessment Questions

**Question 1.** With `DaoAuthenticationProvider` and `UserDetailsService` already present, why do we still need `AccountLifecycleService`?

**Answer:** The first two load and verify users for authentication requests. Registration, email verification, recovery, locking/unlocking, and auditing are multi-step business workflows involving persistence, transactions, notifications, and dedicated policies.

**Question 2.** A user sends JSON containing `"roles":["ROLE_ADMIN"]` during registration. What should the backend do?

**Answer:** Never trust or accept roles from a signup DTO; assign the server-decided default role. Admin roles may only be granted via authorized, audited flows.

**Question 3.** Why can a reset token be hashed with SHA-256 while passwords must use BCrypt/Argon2/PBKDF2?

**Answer:** CSPRNG-generated tokens have high entropy and resist brute force. Human passwords have low entropy and are guessable, requiring password hashes with a work factor. Never use raw SHA-256 to store passwords.

**Question 4.** A client receives 202 from `/auth/recovery/request`. Does that mean the email definitely exists?

**Answer:** No. The response is intentionally identical whether the account exists or not; the server sends instructions only if the account is eligible.

**Question 5.** An expired reset token was still accepted because the server only checked the hash. What is missing?

**Answer:** You must check purpose, expiry, consumed state, and account status, with atomic consumption in a transaction. A matching digest only proves possession of the token, not that the token is still valid.

**Question 6.** After suspending an account, an already-logged-in browser session can still enter the application. Why?

**Answer:** The session may contain a previously verified authentication; the provider does not automatically rerun on every request. Session/token revocation or account-state checks must be implemented as designed.

**Question 7.** Why must recovery emails not assemble links from arbitrary request `Host` headers?

**Answer:** Headers can be spoofed, causing links to point to an attacker's domain. Use a trusted base origin from configuration and control proxy/forwarded headers.

**Question 8.** Can an email verification token be used to complete a password reset?

**Answer:** No. Tokens must be bound to a purpose and action. Code must reject wrong purposes even when the digest and account exist.

**Question 9.** Does `@Transactional` guarantee single-use tokens if two requests read the same unconsumed row concurrently?

**Answer:** Not necessarily. You need locking or an atomic update conditioned on `consumed_at IS NULL`/`expires_at > now`, checking updated row counts, and testing concurrency.

**Question 10.** An app uses OIDC—does it need to store and reset passwords for all SSO users itself?

**Answer:** Usually no. Passwords/MFA and recovery of federated accounts belong to the IdP. The app still maintains internal accounts/profiles, tenants, roles, and lifecycles, synchronized cleanly via trusted subjects.

## 15. Checklist When Reviewing a Real Implementation

- [ ] Domain account has a stable ID, statuses, and appropriate unique login identifier?
- [ ] Registration/recovery/admin domain is separated from `UserDetailsService`/filters?
- [ ] Signup accepts only allowed fields, server assigns default role, protected against mass assignment?
- [ ] Email verification tokens use CSPRNG, dedicated purpose, TTL, single-use, hash-only storage?
- [ ] Password hashes use a secure `PasswordEncoder`, with password policy and version upgrades?
- [ ] Forgot endpoint returns generic responses with timing control and rate limiting?
- [ ] Reset links use HTTPS/trusted origin and do not leak via logs/referrer/cache?
- [ ] GET links only render forms; POST performs mutations and handles CSRF per threat model?
- [ ] Token consumption is atomic in a transaction, tested for races and retries?
- [ ] Email/outbox/auditing are handled properly before/after commit without losing messages?
- [ ] Reset does not auto-log in and does not bypass SUSPENDED/CLOSED states?
- [ ] After reset/suspend/role changes, sessions and refresh tokens are revoked or updated per policy?
- [ ] Email changes enforce re-auth, new email verification, and old-channel notification?
- [ ] Admin operations check authorities, tenant scope, role escalation, and auditing?
- [ ] Logout/session expiration/token rotation are tested beyond username/password?
- [ ] Closed accounts have clear retention, deletion/anonymization, and data obligation handling?
- [ ] Tests cover happy path, bad password, expired/replayed token, wrong purpose, disabled account, concurrent reset, and owner/tenant?
- [ ] In-memory demo/fake outbox/sample credentials are excluded from production deployment?
- [ ] If using an IdP, credential/recovery management flows reside properly in the IdP instead of drifting duplicates?

## 16. Key Takeaways

1. **The account lifecycle belongs to the application's business domain.** Spring Security supplies authentication/authorization infrastructure; it does not auto-build full signup/recovery/admin workflows.
2. **Account entity differs from UserDetails:** The entity owns status, ID, and business invariants; `UserDetailsService` merely translates trusted data to Spring Security during password authentication.
3. **Registration needs transactions + unique constraints + verification**, with server-assigned default roles and abuse limits.
4. **Recovery is a sensitive security path:** CSPRNG tokens, short-lived, single-use, stored hashed, anti-enumeration, and no auto-login after reset.
5. **Administration is more than `hasRole`:** evaluate actor, tenant, resource, audit, step-up, and session/token revocation.
6. **Changing state in the DB does not auto-revoke already-issued authentications.** Explicitly design session/refresh-token/JWT revocation and test it.
7. **In-memory demos are for learning only.** Production needs persistence, transactions, email/outbox, rate limits, auditing, secret protection, and data policies.

## References

- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Password Storage / DelegatingPasswordEncoder](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Spring Boot 3.5.16 release (25/06/2026)](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
