# Separating Responsibilities Between Spring Security and Business Account Services

> **Context:** Spring Security – Authentication, **Account Lifecycle** group. This lesson targets Java 17+, Spring Boot 3.x, and Spring Security 6.x on the Servlet stack. The goal is drawing the right boundary between **authentication/authorization enforcement provided by Spring Security** and **account lifecycle rules owned by business services**. Domain, database, and email components in the examples belong to the application, not features Spring Security provides automatically just by adding a starter.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the exact roles of `SecurityFilterChain`, `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder`, `SecurityContextHolder`, `AuthorizationManager`, and `SecurityContextRepository`.
2. Distinguish **credential verification** from **account registration**, **email verification**, **locking/unlocking**, **role changes**, **password resets**, **account deletion/anonymization**, **session revocation**, and **business auditing**.
3. Model `Account`/`AccountStatus` in the domain, then map them to `UserDetails`—an **adapter/projection** for authentication, not the source of truth for account data.
4. Set proper boundaries for transactions, events, and retries: mutate accounts/credentials in business services while coordinating notifications/email, session invalidation, authorization, and logs.
5. Configure Spring Security 6.x to wire a custom `UserDetailsService` to the application's user store without pushing registration/recovery logic into filters.
6. Recognize when Spring Security **does not automatically update a stored `Authentication`** after an account is locked or roles change, and add live status checks and revocation.
7. Test separation of responsibilities using unit, integration, and security tests, including non-HTTP entry points.

## 2. Short Answer: What Do the Framework and Business Logic Own?

**Spring Security** is a framework for enforcing security policy: intercepting requests, extracting credentials, verifying them through providers, managing principals/security contexts, denying unauthenticated or unauthorized requests/methods, and protecting common web interactions (CSRF, session fixation, logout, etc.).

**Business Account Services (Account Service)** decide how accounts are **created, activated, updated, locked, unlinked, merged, disabled, restored, or deleted** under product rules; define states and events, contact validity, owner/tenant boundaries, and conditions for privilege changes. Account Service collaborates with Security to determine whether an account **is eligible to sign in**.

The two sides intersect but must never swap roles:

- Spring Security does not inherently know which email needs verification, which account needs admin approval, what “pending KYC” means, who can approve a role elevation, or when data must be purged by policy.
- Account Service should not decode JWTs with raw Base64, compare raw passwords inside controllers, forge `SecurityContextHolder` entries, or bypass `AuthorizationManager` just because a DB flag says `active=true`.
- Spring Security defines **interfaces** like `UserDetailsManager` with `createUser`/`updateUser`/`deleteUser`. Having those APIs **does not mean** it implements an enterprise account lifecycle. You may use framework implementations for simple apps, or keep a dedicated domain account service when you need rich states, audits, approvals, multi-tenancy, and compliance.

### Responsibility Split Table

| Action | Primarily handled by Spring Security | Must be decided by Account Service / business logic |
|---|---|---|
| User submits password | Filter/provider extracts credential, `PasswordEncoder.matches`, checks status flags | Which store holds accounts/hashes; which account states allow login |
| After successful login | Creates `Authentication`, persists security context/session, runs security handlers | Which account maps to principal, risk/assurance policies, business audits |
| Account registration | Protects endpoint, CSRF, and request access | Creates account, canonicalizes identifier, enforces uniqueness, anti-abuse, consent |
| Email verification | Secures flows/endpoints per security policy | Issues and consumes `EMAIL_VERIFY` tokens, updates `verified_at`, handles email changes |
| Account lock/unlock | Can deny login via `isAccountNonLocked` / `isEnabled` | Reason, authority, duration, unlock rules, audit, and revocation |
| Password change | Provides `PasswordEncoder`, reauthentication, and request protection | Password policy, credential version, transaction, alerts, reset grants |
| Forgot password | Protects endpoints; may supply some primitives | Dedicated reset tokens, email delivery, TTL/single-use, status checks, credential replacement |
| Role changes | Checks `GrantedAuthority`, `hasRole`, `@PreAuthorize` | Who may grant roles, approvals, tenant scope, effective timing, audit |
| Resource authorization | Request/method authorization and extension points | Ownership, tenant, live data state, product rules |
| Logout / session revocation | Logout handlers, `SecurityContext`/session management | Logout-all-devices policy, revoking tokens/sessions after account events |
| Account deletion or anonymization | Blocks authentication and cleans up sessions as configured | Retention, legal holds, data purge, dependencies, audit, product rules |
| SSO/OIDC | OAuth2/OIDC login and resource-server integration | Linking external identities to local accounts, provisioning, tenants, consent, offboarding |

**Rule of thumb:** the framework provides **“how to verify and enforce”**; the domain provides **“which states are valid, who may change them, and what business consequences follow.”** They collaborate through adapters and service interfaces, not by letting every controller manipulate `Authentication`.

## 3. Recommended Layer Architecture

```text
                    HTTPS Request
                         │
                         ▼
               ┌────────────────────┐
               │ Spring Security    │
               │ SecurityFilterChain│
               │ Authentication /   │
               │ Authorization      │
               └──────────┬─────────┘
                          │
                 UserDetailsService
                 (adapter reading account)
                          │
                          ▼
                 AccountReadRepository
                          │
              stable userId, passwordHash,
              status, roles, tenant...
                          │
         ┌────────────────┴─────────────────────┐
         │                                      │
         ▼                                      ▼
    Authenticated request                Application Controller
    + current principal                      /account/**
         │                                      │
         ▼                                      ▼
    Domain authorization                 AccountService
    (owner, tenant, ACL)                 (use cases)
         │                                      │
         └────────────────┬─────────────────────┘
                          ▼
                    Account Domain
          ┌───────────────────────────────────┐
          │ Account, Credential, Contact,     │
          │ AccountStatus, Membership, Roles  │
          └────────────────┬──────────────────┘
                           ▼
                    Database + Outbox
                      │         │
                 local txn    async worker
                                 │
                      email / notifications /
                      audit / IdP integration
```

These boundaries denote **separation of responsibilities**; they do not force creating separate microservices for Security and Account Service. Inside a monolith, they can be packages or modules with clean dependencies. What matters is that **business invariants are not scattered across filters and controllers**.

### Example Package Structure

```text
com.example.account
  domain/
    Account.java
    AccountStatus.java
    AccountCredential.java
  application/
    RegisterAccountUseCase.java
    VerifyEmailUseCase.java
    ChangePasswordUseCase.java
    DisableAccountUseCase.java
    GrantRoleUseCase.java
  port/
    AccountRepository.java
    OutboxPort.java
    NotificationPort.java
  adapter/
    persistence/...
    email/...

com.example.security
  AccountSecurityConfig.java
  AccountLoginLookup.java
  DatabaseUserDetailsService.java
  CurrentAccountPermission.java
  SessionRevocationPolicy.java

com.example.web
  AccountRegistrationController.java
  AccountSettingsController.java
```

This is an organizational diagram, not a list of built-in Spring classes. A “port” can be backed by Spring Data, JDBC, jOOQ, or an internal API depending on complexity. Do not mechanically create repository/service layers for every getter; the goal is giving **business transitions and security guarantees** clear, testable homes.

## 4. How Spring Security Performs Authentication

In Spring Security Servlet, a request carrying credentials enters security filters (depending on mechanism: form login, HTTP Basic, bearer JWT, OAuth2 login…). A filter builds an **unauthenticated** `Authentication` and passes it to `AuthenticationManager`; a supporting `AuthenticationProvider` verifies the credential. On success, the authenticated result containing principal and authorities is placed into `SecurityContext` and optionally persisted to a session.

```text
Client
  │ POST /login (username, password)
  ▼
UsernamePasswordAuthenticationFilter
  │ UsernamePasswordAuthenticationToken (unauthenticated)
  ▼
AuthenticationManager / ProviderManager
  │
  └── DaoAuthenticationProvider
        ├── UserDetailsService.loadUserByUsername(...)
        │     └── AccountLoginLookup → database
        ├── PasswordEncoder.matches(rawPassword, storedHash)
        └── Account status / authorities checks
                     │
                     ▼
         Authentication (authenticated)
                     │
             SecurityContextHolder
                     │
              HTTP session (if configured)
                     │
           AuthorizationManager / method security
```

**Do not confuse:**

- `UserDetailsService.loadUserByUsername` **only fetches the data** needed by the password provider (username, password hash, flags, authorities). It is not a default “service for registration, email tokens, password changes, and role management.”
- `DaoAuthenticationProvider` verifies a password against a stored hash via `PasswordEncoder`; it does not inherently know whether a customer is old enough, identity-verified, or under a legal hold.
- `Authentication` and `SecurityContextHolder` represent **authentication state for a request/session**, not the authoritative account record, and must not be used as mutable ORM entities.
- `GrantedAuthority` reflects authorities held by the current `Authentication`; it does not automatically refresh from the DB when an admin edits roles after the session was saved.

### 4.1. SecurityContextRepository and HTTP Sessions

In session-based apps, `SecurityContextRepository` controls how security contexts are saved and loaded (typically via HTTP session). With stateless tokens, Spring Security can re-authenticate credentials per request without an HTTP session.

**Version note:** Spring Security 6 emphasizes **explicit saving** of the security context. When writing a custom login controller or provider, calling only `SecurityContextHolder.getContext().setAuthentication(...)` is insufficient to persist across requests; invoke `SecurityContextRepository.saveContext(...)` and coordinate the session authentication strategy. When using built-in `formLogin()`, standard filters and handlers manage the flow automatically without writing a manual login controller.

**Never construct an `Authentication` from browser-supplied claims** or mark `authenticated=true` immediately after registration. Every credential must pass through a trusted verifier.

### 4.2. PasswordEncoder and Where Password Logic Belongs

Spring Security provides the `PasswordEncoder` interface for:

```java
String hashed = passwordEncoder.encode(rawNewPassword);
boolean ok = passwordEncoder.matches(rawPresentedPassword, storedHash);
```

- **During authentication:** `DaoAuthenticationProvider` calls `matches` when verifying login.
- **During business use cases:** `RegisterAccountUseCase` or `ChangePasswordUseCase` calls `encode` before storing a password, alongside password policy checks, account status checks, transactions, and auditing.
- Never let controllers store raw passwords, and never write `encode(password).equals(storedHash)` because bcrypt/Argon2 use random salts so re-encoding yields a different string.
- Never use `NoOpPasswordEncoder` or `User.withDefaultPasswordEncoder()` in production.
- Choose an appropriate algorithm/cost and hash-upgrade strategy; `DelegatingPasswordEncoder` carries `{id}` algorithm prefixes to support smooth migrations.

**Security provides hashing and verification primitives; business logic decides when credentials may be created or changed.**

## 5. Domain-Owned Account Model

A simple model:

```text
Account
 ├── id                       stable local account identifier
 ├── usernameCanonical        unique per policy
 ├── lifecycleStatus          PENDING_EMAIL, ACTIVE, SUSPENDED, DELETED...
 ├── createdAt
 ├── emailVerification        contact value + verifiedAt + version
 ├── passwordCredential       hash + changedAt + credentialVersion
 ├── memberships              tenant, team, role bindings
 ├── sessionVersion           for revocation
 └── audit / data-retention state
```

**Never rely on email as the sole unique key across security boundaries.** Emails can change, remain unverified, or collide across IdPs and tenants. `account.id` is the stable domain key; for SSO identities, link via a verified `(issuer, subject)` pair mapped to the local account.

### 5.1. Distinct Business States

| Illustrative domain state | Business meaning | Typical desired authentication behavior |
|---|---|---|
| `PENDING_EMAIL` | Contact not yet verified | Block full login or allow restricted access per policy |
| `PENDING_APPROVAL` | Awaiting authorized reviewer approval | Do not grant requested access; block approval-gated actions |
| `ACTIVE` | Eligible to log in using supported credentials | Provider may authenticate if credentials pass |
| `TEMPORARILY_LOCKED` | Locked for brute-force/protection | Deny login until unlocked under policy |
| `SUSPENDED` | Proactively suspended for violation or risk | Block new logins and invalidate old sessions/tokens if required |
| `CLOSED` | Account closed, within retention window | No login; handle data per retention policy |
| `DELETED` | Deleted/anonymized per workflow | Never “resurrect” via reset tokens or automatic SSO provisioning |

These are **domain design examples**, not enums provided by Spring Security. An account can simultaneously be `ACTIVE` while carrying flags such as `MFA_REQUIRED`, `EMAIL_CHANGE_PENDING`, or `PASSWORD_RESET_REQUIRED`. Avoid cramming independent dimensions into a single enum.

### 5.2. UserDetails Is a Projection, Not the Account

Spring Security's `UserDetails` exposes `getUsername()`, `getPassword()`, `getAuthorities()`, `isAccountNonExpired()`, `isAccountNonLocked()`, `isCredentialsNonExpired()`, and `isEnabled()`.

**Intentional mapping:**

- `isEnabled=false` can block full login until the account meets activation rules.
- `isAccountNonLocked=false` can express policy-driven locks.
- `isCredentialsNonExpired=false` can force handling expired credentials through a dedicated flow.
- `getAuthorities` loads approved roles/memberships, never trusting a client-submitted `roles=ADMIN` form field.
- A status like `PENDING_KYC` need not map 1-to-1 onto `isEnabled`; many systems permit basic login while blocking KYC-gated transactions. In those cases, business-layer authorization must check KYC on the **specific action**.

Crucially, domain account status can be **richer** than `UserDetails`'s four booleans. **Do not** force complex business rules into `isEnabled()` or an ad-hoc `ROLE_PENDING` string without an explicit operational design.

### 5.3. Durable Persistence and Concurrency

Illustrative PostgreSQL schema:

```sql
CREATE TABLE app_accounts (
    id UUID PRIMARY KEY,
    canonical_username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    lifecycle_status TEXT NOT NULL,
    email_verified_at TIMESTAMPTZ,
    credential_version BIGINT NOT NULL DEFAULT 0,
    session_version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT app_account_status_valid CHECK (
      lifecycle_status IN (
       'PENDING_EMAIL', 'PENDING_APPROVAL', 'ACTIVE',
       'TEMPORARILY_LOCKED', 'SUSPENDED', 'CLOSED', 'DELETED'
      )
    )
);

CREATE TABLE account_role_bindings (
    account_id UUID NOT NULL REFERENCES app_accounts(id),
    tenant_id UUID NOT NULL,
    role_name TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (account_id, tenant_id, role_name)
);

CREATE INDEX account_role_tenant_idx
    ON account_role_bindings(tenant_id, role_name);
```

This schema is illustrative and **omits full migrations**: production needs consistent email normalization/uniqueness policies, consent tracking, soft-delete/retention handling, constraints, optimistic locking/versions, and tenant isolation across queries. `password_hash` is nullable for SSO-only identities; never permit password login when it is null, and never synthesize a local password for an SSO account just because an external email matches.

**Tenant boundaries:** “having `ROLE_ADMIN` in tenant A” does not mean “having `ROLE_ADMIN` system-wide.” A global `ROLE_ADMIN` cannot express tenant-scoped ACLs; use tenant-scoped role bindings and resource ownership. Every role update must specify the tenant scope and an authorized approving actor.

## 6. Lifecycle Workflows Owned by Account Service

### 6.1. Registration and Email Verification

Typical workflow:

```text
POST /signup
  → validate form/rate limit
  → normalize username/email per policy
  → check uniqueness + DB unique constraint
  → hash password via PasswordEncoder
  → transaction creates Account PENDING_EMAIL
  → issue verification grant purpose=EMAIL_VERIFY + TTL
  → write outbox event
  → commit
  → worker sends email to registered contact
  → GET verification landing, POST token confirm
  → atomic consume, update verifiedAt/status per policy
  → redirect to normal login
```

Spring Security can protect `/signup`, `/verify-email`, and CSRF, yet it **knows nothing** about the domain steps above. Never switch an account to `ACTIVE` merely because a request asserts `emailVerified=true`. Verify tokens/callbacks against trusted state, matching owner, purpose, and TTL inside a transaction.

You may use Spring Security's OTP/Magic link features for **one-time sign-in**, but **never reuse a login token** for email verification or password reset when their purposes differ. Keep namespaces, verifiers, and side effects separate.

### 6.2. Email Changes, Password Changes, and Recovery

- **Email change:** require risk-appropriate reauthentication/step-up, save the new email as pending, send verification to the new contact, confirm the exact purpose, protect sessions, and alert the old contact. Account Service decides which contact is trusted.
- **Logged-in password change:** enforce reauthentication, password policy, `PasswordEncoder.encode`, and credential versions. Never update passwords simply because a session exists when `newPassword` arrives.
- **Forgot password:** issue a short-lived CSPRNG recovery token stored as a hash, single-use, bound to the account, with no auto-login. Reset tokens are **not** access tokens or magic login tokens.
- **MFA/device recovery:** use a dedicated policy covering enrollment, backup codes, and helpdesk proofing. Never allow email reset to strip security keys.
- **Registering OAuth/OIDC identities:** Security validates the provider response; Account Service maps `(iss, sub)` to a local account via explicit linking policy rather than auto-linking by unverified emails.

### 6.3. Locking and Unlocking

Two frequently confused scenarios:

1. **Automatic lockout from too many failed logins:** technical anti-abuse mechanisms consume authentication failure events, rate-limit, increment counters, and set an unlock time per policy.
2. **Administrative/legal suspension:** a business decision with an actor, reason, approvals, and audit—unrelated to wrong-password counters.

Account Service owns state transitions, auditing, and deciding whether all sessions/tokens must be revoked. Spring Security reads the updated projection to **reject new logins** and integrates to **block existing sessions**; setting `enabled=false` in a DB does not destroy live sessions by itself.

### 6.4. Role and Membership Changes

A business flow typically requires:

```text
Actor request: "Grant BILLING_APPROVER to user-42 in tenant-A"
  │
  ├─ authenticate actor + MFA freshness
  ├─ check actor may grant this role in tenant-A
  ├─ enforce separation-of-duties (if needed)
  ├─ check target account ACTIVE, matching tenant, limits
  ├─ optional independent approval
  ├─ transaction update account_role_bindings
  ├─ increase authzVersion / revoke stale session rights
  └─ audit + notification
```

Spring's `@PreAuthorize("hasRole('ADMIN')")` checks only one **precondition**; the framework does not know “which ADMIN,” “which tenant,” “which roles they may approve,” “whether self-granting is forbidden,” or “whether two-person approval is required.” Those rules belong in **business policy** and must execute even when invoked from background jobs, event listeners, or internal APIs—not solely the UI.

### 6.5. Account Deletion / Closure

Account deletion workflows typically involve:

- Checking permissions and state: self-service vs admin-initiated, and whether legal holds or retention duties apply.
- Disabling authentication and sessions immediately per policy.
- Invalidating outstanding grants, recovery tokens, and magic links.
- Deleting or anonymizing data according to data classification and retention; never delete legally required accounting records prematurely.
- Revoking external identity links, refresh tokens, and authorized apps per IdP contracts.
- Writing minimal audits, notifying via a trusted channel, and ensuring retries/idempotency.

Spring Security **does not execute account deletion workflows** or know how deletion impacts invoices, orders, and contracts. Domain and downstream services must coordinate.

## 7. Spring Security 6.x Configuration for Form Login

This example uses **Spring Boot 3.x + Spring Security 6.x, Java 17**, and local credentials. Spring snippets are **integration fragments inside a project**, not runnable via a single `javac` command because they rely on starters, an account repository, HTTP runtime, and a database.

### 7.1. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    runtimeOnly 'org.postgresql:postgresql'
}
```

These are common choices; JPA can be swapped for JDBC/jOOQ and Mail for a queue/notification provider. Dependency versions are managed by the project's Spring Boot BOM/plugin.

### 7.2. SecurityFilterChain + PasswordEncoder

File `src/main/java/com/example/security/AccountSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class AccountSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/signup", "/verify-email", "/login").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/signup", "/verify-email").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Keep default CSRF for web/session login POSTs.
        return http.build();
    }
}
```

**Meaning:**

- `formLogin()` enables Security's username/password form login, automatically wiring `UserDetailsService` and `PasswordEncoder` when configured.
- `requestMatchers` declares HTTP route rules; `permitAll()` only allows anonymous requests to reach the route—it **does not** create accounts or verify emails.
- `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority in `Authentication`. It does not enforce tenant authorization or role-grant approvals.
- `@EnableMethodSecurity` activates method-level access control via `@PreAuthorize` etc.; adding `spring-boot-starter-security` does not turn on method security automatically without it.
- With templates such as Thymeleaf, domain controllers must serve matching GET/POST routes with CSRF inputs. Never disable CSRF just to make a signup form submit; pass the token on POST properly.
- Edge paths such as `/admin` (without a trailing slash) or equivalent aliases must be covered by explicit rules; never leave an alternate route calling use cases while bypassing security policies.

### 7.3. Creating a UserDetailsService Adapter for the Account Store

A read-only DTO from the account repository; it is **not** a Spring Security type:

File `src/main/java/com/example/security/AccountLoginSnapshot.java`:

```java
package com.example.security;

import java.util.Set;

public record AccountLoginSnapshot(
        String accountId,
        String canonicalUsername,
        String passwordHash,
        boolean passwordLoginAllowed,
        boolean accountNonLocked,
        Set<String> approvedGlobalRoles) {}
```

File `src/main/java/com/example/security/AccountLoginLookup.java`:

```java
package com.example.security;

import java.util.Optional;

public interface AccountLoginLookup {

    Optional<AccountLoginSnapshot> findForPasswordLogin(
        String canonicalUsername);
}
```

File `src/main/java/com/example/security/DatabaseUserDetailsService.java`:

```java
package com.example.security;

import java.util.List;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final AccountLoginLookup lookup;

    public DatabaseUserDetailsService(AccountLoginLookup lookup) {
        this.lookup = lookup;
    }

    @Override
    public UserDetails loadUserByUsername(String submittedUsername) {
        // Normalize/login-name lookup per DOMAIN POLICY.
        // Database lookup must enforce proper account/tenant boundaries.
        AccountLoginSnapshot a = lookup.findForPasswordLogin(
                submittedUsername)
            .orElseThrow(() ->
                new UsernameNotFoundException("Unknown account"));

        if (a.passwordHash() == null) {
            // SSO-only account: never auto-create a local password.
            throw new UsernameNotFoundException("Password login unavailable");
        }

        List<SimpleGrantedAuthority> authorities =
            a.approvedGlobalRoles().stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .toList();

        return new User(
            a.canonicalUsername(),
            a.passwordHash(),
            a.passwordLoginAllowed(), // enabled
            true,                     // accountNonExpired
            true,                     // credentialsNonExpired
            a.accountNonLocked(),
            authorities
        );
    }
}
```

**Compilation note:** the three files above have complete type references across the shown snippets; a bean **implementing** `AccountLoginLookup` and real database wiring are still needed to run the app. `approvedGlobalRoles` must come from domain-approved, normalized data; never accept client-submitted role strings and prefix `ROLE_` unchecked. Tenant/resource roles belong in policy checks rather than turning everything into global roles.

**How the mapper behaves:**

- `lookup` returns only the **minimal projection** required for password login; do not pull home addresses, transactions, KYC files, or full aggregates into `SecurityContext`/sessions.
- `passwordLoginAllowed` is derived from verified domain status, credential type, and policy—not a client-controlled toggle.
- `accountNonLocked` reflects domain lock status. Apps may similarly map `accountNonExpired` and `credentialsNonExpired` when policies require them.
- Never update `lastLoginAt` inside `UserDetailsService.loadUserByUsername`. That method can run multiple times across auth flows or caches; record last login from an event or handler only after authentication **actually succeeds**.
- Avoid returning distinct “account does not exist” vs “locked” errors to clients when anti-enumeration policy demands neutral responses; keep internal exceptions, logs, and audits separate.
- If usernames can change, carry a **stable account ID** inside the principal/security context so identity never shifts; `getName()` defaults to username and is not guaranteed to be an immutable domain key.

### 7.4. Never Auto-Login Immediately After Account Creation

Wrong:

```java
// WRONG: client just POSTed /signup, account is not yet verified
SecurityContextHolder.getContext().setAuthentication(
    UsernamePasswordAuthenticationToken.authenticated(
        submittedEmail, null, List.of(
            new SimpleGrantedAuthority("ROLE_USER"))));
```

This is an **anti-example**, never for production. Constructing `authenticated(...)` directly from request data before verifier checks can bypass activation rules, MFA, and login policies. Account Service must create `PENDING_EMAIL` and issue a verification token; only proper authentication flows issue `Authentication`.

Even if a product intentionally wants **auto-login after registration** for UX, define the policy explicitly: whether activation rules are satisfied, which verifier is trusted, MFA/session fixation handling, and how `SecurityContextRepository` persists the context. Never guess or shortcut it.

## 8. Business Services: Home of Invariants and Transactions

Example outline of `RegisterAccountUseCase` (pseudocode, not standalone Java source):

```text
register(command):
    validate form + password policy
    normalize username/email using domain rules
    check uniqueness; rely on DB unique constraints for race safety
    encoded = PasswordEncoder.encode(command.rawPassword)

    begin transaction
       account = Account.create(PENDING_EMAIL, encoded, verifiedAt=null)
       AccountRepository.save(account)
       token = EmailVerificationToken.issueRandomFor(account.id)
       VerificationRepository.storeHashAndExpiry(token)
       OutboxPort.save(EmailVerificationRequested(account.id, tokenReference))
       commit
    worker retrieves protected delivery data; sends one-time link
    return generic registration response
```

**Crucial detail on email outbox:** avoid writing **raw tokens** directly into shared event logs with many consumers or long retention. For async mail workers, design an encrypted, access-restricted delivery store purged after send, or issue/wrap tokens at the appropriate step matching transactional guarantees. Consistency between DB writes and email sending is a business architecture decision, not something `SecurityFilterChain` solves.

### 8.1. Account Transitions Must Be Atomic

Example email verification:

```text
verifyEmail(rawToken):
    find verification grant by hash, purpose=EMAIL_VERIFY
    begin transaction
       claim unconsumed grant with expiresAt > now atomically
       lock account and confirm ownership/contact version
       set account.emailVerifiedAt
       if other activation gates satisfied → account.ACTIVE
       save account and event
       commit
    return a neutral success/failure page
```

Handle **concurrent requests with the same token**, **expired tokens**, **contact changes while a token is live**, and **admin-suspended accounts**. “Opening a link” does not equal “logged in”; mail scanners can GET URLs ahead of the user, so avoid consuming tokens on GET when confirmation interaction is appropriate.

### 8.2. Password Changes

In `ChangePasswordUseCase` or `ResetPasswordUseCase`:

- Validate authorization/reauth or a purpose-bound reset token.
- Enforce password policy; call `PasswordEncoder.encode` before saving.
- Inside one transaction: update `passwordHash`, bump `credentialVersion` and/or `sessionVersion`, invalidate reset grants per policy, and record an event.
- Never mint a full login session from a reset token; require proper login/MFA.
- **Actually revoke** stale sessions/tokens per mechanism. With offline self-contained JWTs, changing a DB password does not automatically reject old JWTs.

### 8.3. Approvals and Privilege Controls

`GrantRoleUseCase` should verify actor, tenant, and grant authority before saving. `@PreAuthorize("hasRole('ADMIN')")` is a useful outer guard, yet cannot express “admins cannot promote themselves” or “financial roles require dual approval.” Put those rules in unit-testable domain policy classes independent of HTTP routes.

Example domain policy:

```text
canApproveRoleGrant(actor, target, role, tenant):
    actor authenticated and currently active
    actor has GRANT_ROLE capability for this tenant
    target belongs to same tenant and is ACTIVE
    actor != target if separation-of-duties required
    role is assignable (not immutable/system owner)
    approval workflow state is satisfied
    no conflicting role grants under risk policy
```

Never take `roleName`/`tenantId` from the UI and mutate `user.setAuthorities(...)` on the live principal directly; persist role bindings in the DB and propagate to active sessions properly.

## 9. Business Authorization: Security Enforces, Domain Defines Rules

### 9.1. `hasRole` Does Not Replace Ownership Checks

Suppose an account has `ROLE_USER`. For `GET /orders/815`:

```java
@PreAuthorize("hasRole('USER')")
public OrderView readOrder(long orderId) {
    return orders.load(orderId);
}
```

This code can allow any `ROLE_USER` to read every order unless `orders.load` verifies ownership and tenant. That is **broken object level authorization (BOLA/IDOR)**. Product rules typically require:

```text
user is authenticated
AND user has global ability to read orders
AND order.tenantId == user's active tenant
AND order.ownerId == user's stable account ID
AND order not restricted by business status
```

Enforce this via `@PreAuthorize` invoking a policy bean, or fold ownership predicates directly into controlled queries:

```java
// Domain service snippet; requires OrdersRepository and Policy bean.
public OrderView readOrder(long id, AuthenticatedActor actor) {
    return orders.findVisibleToActor(id, actor.accountId(),
            actor.tenantId())
        .orElseThrow(() -> new OrderNotAccessibleException());
}
```

This snippet uses **application-defined types**, not standalone Java. It expresses tenant-scoped querying; test the repository to ensure no branch falls back to `findById` without ownership checks.

### 9.2. `@PreAuthorize` Must Be Enabled and Applied Properly

Spring Security 6.x supports:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}
```

Once enabled, `@PreAuthorize`, `@PostAuthorize`, and policy interceptors apply to **Spring-managed beans**. Because Spring uses AOP proxies, **self-invocation** from one method to another annotated method in the same instance bypasses the proxy; never rely solely on annotations placed on private or internal methods. Furthermore, scheduler or queue invocations may lack an HTTP security context; require explicit actor/service identity propagation and verification for backend jobs.

**Clean layering:** request security blocks unauthenticated callers, method security enforces functional permissions, and domain services enforce tenant/owner/approval rules and transactional state updates. Not every rule belongs in SpEL; pure Java business policies are far easier to test.

### 9.3. Effects of Post-Login Role Changes

`Authentication` stores a snapshot of `GrantedAuthority`. If an admin revokes `ROLE_ADMIN` in the DB, an existing session may still carry the old authority. Likewise, an issued JWT access token carrying stale `scope`/`roles` may remain unexpired.

Pick mitigations suited to risk:

- Invalidate HTTP sessions when roles or account status change.
- Bump `sessionVersion`/`authzVersion` and verify per request or against a short-TTL/invalidated cache.
- For JWTs, use denylists, opaque introspection, version lookups, or short TTLs; mutating the DB does not immediately revoke offline JWTs.
- Query current permissions inside business services for sensitive actions, minding caching and consistency.
- Emit audits/notifications from Account Service and wire session/security updates via events without **failing open** on critical endpoints.

Never document “account suspended ⇒ all issued JWTs are immediately invalid” unless Resource Servers **actually verify** revocation status.

## 10. Source of Truth, Caching, and Consistency

One of the most common bugs is letting three stores give conflicting answers about the same account:

```text
users table: account.status = SUSPENDED
JWT:         roles = ["ADMIN"]  (issued before suspension)
Session:     Authentication.authorities = ROLE_ADMIN
Cache:       user.enabled = true (not yet invalidated)
```

**Establishing boundaries:**

1. The account database/service is the **source of truth** for business state (unless an IdP contract is authoritative for a specific attribute).
2. `UserDetails`, `Authentication`, and JWT claims are **authentication projections** that can lag as snapshots.
3. Policy engines/business services decide when fresh reads are mandatory, when caches are acceptable, and the maximum allowed staleness SLO.
4. Event-driven propagation works well for notifications, cache invalidation, and analytics; however, if events lag or queues fail, sensitive endpoints must not silently honor stale privileges.
5. Define fail-closed policies whenever live status or permissions cannot be verified.

Never place whole JPA `Account` aggregates into `SecurityContext` across multi-day sessions; JPA entities go stale, fail lazy loading outside transactions, and leak PII. Use a stable principal ID with a minimal, versioned projection.

### 10.1. `UserDetailsService` Caching Can Cause Stale Logins

`CachingUserDetailsService` or custom caches can keep `enabled=true` after an account is locked. Configure explicit TTLs, cache eviction on account events, version checks, or bypass caching for sensitive actions. Password-hash caching also interacts with credential erasure after authentication; test every concrete configuration.

### 10.2. Deleted Accounts and External Identity Provisioning

With `oauth2Login()`, Spring Security verifies the OIDC/OAuth2 flow and supplies principal/claims; business logic decides whether the matching local account **is allowed to exist** or awaits approval. If an account was deleted or banned, never recreate a new user just because an IdP email claim matches. External identity linking relies on verified `(issuer, subject)` plus consent and ownership policy, never email matching alone.

## 11. Standalone Java 17 Example: Separating Login, State, and Permissions

The following program **compiles and runs standalone with JDK 17+** without Spring. It does not simulate cryptographic password verification; `passwordVerified` represents the boolean outcome produced by a trusted verifier (like `DaoAuthenticationProvider`). The goal is showing that **account status and privilege decisions belong to the domain**, while credential checking is only one condition for login.

Save as `AccountResponsibilityDemo.java`:

```java
import java.util.Set;

public class AccountResponsibilityDemo {

    enum State {
        PENDING_EMAIL, ACTIVE, SUSPENDED, DELETED
    }

    record Account(
        String id,
        State state,
        Set<String> approvedRoles,
        long sessionVersion
    ) {}

    record SessionProof(
        String subjectId,
        long issuedSessionVersion
    ) {}

    // Authentication should complete only if domain permits login.
    static boolean canCompleteLogin(
            Account account, boolean passwordVerified) {
        return account != null
            && passwordVerified
            && account.state() == State.ACTIVE;
    }

    // Business policy: only authorized actors may request role grants.
    static boolean canRequestAdminGrant(
            Account actor, Account target) {
        return actor != null
            && target != null
            && actor.state() == State.ACTIVE
            && target.state() == State.ACTIVE
            && actor.approvedRoles().contains("SECURITY_ADMIN")
            && !actor.id().equals(target.id());
    }

    // Security session must respect current status and version.
    static boolean sessionStillAllowed(
            Account account, SessionProof session) {
        return account != null
            && session != null
            && account.state() == State.ACTIVE
            && account.id().equals(session.subjectId())
            && account.sessionVersion()
                == session.issuedSessionVersion();
    }

    public static void main(String[] args) {
        Account pending = new Account(
            "user-42", State.PENDING_EMAIL, Set.of("USER"), 1L);
        Account active = new Account(
            "user-42", State.ACTIVE, Set.of("USER"), 1L);
        Account operator = new Account(
            "operator-9", State.ACTIVE,
            Set.of("SECURITY_ADMIN"), 1L);
        Account suspended = new Account(
            "user-42", State.SUSPENDED, Set.of("USER"), 2L);
        SessionProof oldSession = new SessionProof("user-42", 1L);

        System.out.println("Pending email login: " +
            canCompleteLogin(pending, true));
        System.out.println("Active correct password: " +
            canCompleteLogin(active, true));
        System.out.println("Wrong password: " +
            canCompleteLogin(active, false));
        System.out.println("Self-grant request: " +
            canRequestAdminGrant(active, active));
        System.out.println("Operator grant request: " +
            canRequestAdminGrant(operator, active));
        System.out.println("Suspended login: " +
            canCompleteLogin(suspended, true));
        System.out.println("Old session blocked: " +
            !sessionStillAllowed(suspended, oldSession));
    }
}
```

Run commands:

```bash
javac AccountResponsibilityDemo.java
java AccountResponsibilityDemo
```

Exact stdout:

```text
Pending email login: false
Active correct password: true
Wrong password: false
Self-grant request: false
Operator grant request: true
Suspended login: false
Old session blocked: true
```

**Meaning of each decision:**

- `PENDING_EMAIL` cannot complete full login in the demo policy even with a verified password.
- An `ACTIVE` account with a verified password may complete login.
- An `ACTIVE` account with a wrong password cannot log in; business state never replaces cryptographic verification.
- An actor cannot request admin privileges for themselves under the **illustrative separation-of-duties rule**.
- `operator-9` may submit a role-grant request for an ACTIVE target; this is **not proof that the role was already granted or approved**.
- Suspended accounts are blocked from new logins.
- A session issued at version 1 becomes invalid once the account is suspended and its version increments to 2.

**Demo limitations:** the code simulates state-based decisions only; it does not read a database or include Spring Security, HTTP sessions, password hashing, or domain events. `Set.of` holds static roles to illustrate logic, not a production permission store; tenant checks, approvals, and audits must be added in real systems.

## 12. Overlapping Scenarios: Who Owns Final Responsibility?

### 12.1. Registration Succeeds Yet Login Fails

This is **not necessarily a bug**. Newly created accounts may sit in `PENDING_EMAIL` or `PENDING_APPROVAL`; the account service saved the record properly, while authentication rejects login until activation requirements are satisfied.

Provide clear UX: “Registration received, check your email” instead of “Account logged in.” Avoid returning “email unverified” on public login endpoints if doing so leaks account existence against policy.

### 12.2. Security Verifies the Password Yet the Account Is Locked

`DaoAuthenticationProvider` may match a valid password hash, yet `UserDetails.isEnabled`/`isAccountNonLocked` or a custom provider/policy rejects the outcome. Account Service owns accurate status and lock decisions; Security enforces that decision during authentication.

If an account is locked while the user already holds a session, handle existing sessions too—not just the next login.

### 12.3. Is Email Verification from an IdP Enough to Activate a Local Account?

**Not by default.** Under SSO, `email_verified` is merely a claim governed by the provider's contract. The app must verify issuer, subject, and linking policy rather than letting an external identity claim a matching local account automatically. Account activation may also require invitations, admin approval, tenant membership, and consent.

### 12.4. Does Browser Logout Delete Every OAuth Token?

No. Spring Security logout typically clears `SecurityContext`, sessions, and cookies as configured. If refresh tokens exist at an Authorization Server or unexpired JWT access tokens exist at Resource Servers, app logout does not automatically revoke every credential. Account Service/Security integration must define target revocation scope and call revocation endpoints or check versions accordingly.

### 12.5. Can `UserDetailsManager` Serve as Account Service?

For small demos or simple in-memory/JDBC apps, `UserDetailsManager` supports creating, updating, deleting, checking existence, and changing passwords per implementation. However, it cannot replace a **business account aggregate** when you need email verification, multi-tenant memberships, approvals, legal holds, deletion workflows, audits, and integrations. You can wrap or adapt it into your application architecture if helpful, without coupling core domain business logic directly to Spring Security's user record.

## 13. Anti-Patterns to Avoid

| Anti-pattern | Why it is dangerous | Alternative |
|---|---|---|
| `/signup` controller sets authenticated `Authentication` | Bypasses identity proofing, activation, and MFA | Domain creates account; Security handles login properly |
| `UserDetailsService` sends activation emails or updates `lastLogin` | Lookup may run repeatedly/from cache with uncontrolled side effects | Send email from `AccountUseCase` + outbox; audit logins in success handlers/events |
| Putting all business rules into `SecurityFilterChain` | Bloats security config; prevents isolated domain testing | Domain policies + application services + adapters |
| Reading `ROLE_ADMIN` from signup JSON | Privilege escalation | Fixed/approved default roles and explicit role-grant use cases |
| Using username/email as stable ID | Mutable, collides across tenants/providers, and can be recycled | Stable local account ID + external `(iss,sub)` mapping |
| Account lock updates only DB | Stale sessions/JWTs keep working | Version checks, revocation, session invalidation |
| Uninvalidated `UserDetails` cache | Stale enabled/role flags | TTL/invalidation and live state checks |
| Controller updates `password_hash` directly | Skips password policy, transactions, and audits | `Change/ResetPasswordUseCase` + `PasswordEncoder` |
| Password reset disables MFA | Recovery path weakens login security | Separate MFA recovery and policy-driven step-up |
| Auto-creating local SSO account by email match | Account takeover / identity confusion | Verify issuer+subject and enforce explicit safe linking |
| `hasRole("USER")` suffices to read any resource | IDOR/BOLA | Per-resource/tenant ownership policies |
| `@PreAuthorize` on private/self-invoked methods | Bypasses Spring AOP interceptors | Proxy/service boundaries and domain invariants |
| DB transaction plus direct email send | Email may go out while transaction rolls back | Outbox + protected delivery + retries |
| Treating async event dispatch as instant revocation | Old tokens/sessions remain valid during propagation window | Live version checks or fail-closed revocation |
| Storing JPA `Account` entity in session | Stale data, lazy-loading failures, PII leaks | Minimal principal (stable ID, scoped claims) |
| “The framework handles all security” | Leaves gaps in onboarding, recovery, account states, and resource authz | Explicit threat model and ownership matrix |

## 14. Responsibility and Boundary Test Matrix

### 14.1. Authentication / Authorization

- `ACTIVE` account with valid password hash: `DaoAuthenticationProvider` authenticates; `Authentication` carries policy-aligned principal and authorities.
- Wrong password: rejected; an active account never bypasses `PasswordEncoder.matches`.
- `PENDING_EMAIL` or `SUSPENDED` account: full login rejected per policy even with the right password.
- SSO-only account with `password_hash=null`: cannot log in through password provider.
- New admin grant: existing session does not gain privileges unless policy supports refresh/versioning; test exact expected propagation.
- Admin privilege revocation: sensitive APIs deny within policy latency SLA; stale scopes/roles are never trusted.
- Regular user reads another user's order in same or different tenant: denied despite `ROLE_USER`.
- Blocked HTTP route vs service method called by a job: test policies at service/domain boundaries, not solely URL filters.

### 14.2. Account Lifecycle

- Unverified signup request: creates `PENDING_EMAIL` without creating a login session.
- Email verification token with valid purpose, owner, expiry, and unused state: updates `verifiedAt`/status transactionally.
- Wrong-purpose or replayed email verification token: rejected without mutating account.
- Two concurrent signups with same canonical username/email: at most one transaction commits thanks to DB unique constraint.
- Email change: new address stays pending and does not replace trusted contact before verification; old-email alert sent per policy.
- Admin suspension: records actor/reason, updates status, bumps `sessionVersion` or revokes sessions per policy.
- Account unlock: permitted only for authorized actors or valid recovery flows; password reset does not unlock admin suspensions.
- Account deletion: blocks login and old sessions, honors retention, never resurrects via SSO login or unexpired email reset tokens.
- Role grant via domain use case: checks actor/tenant/approvals and rejects unapproved self-elevation.
- Forged `role=ADMIN` on signup: ignored/rejected; never appears in authorities.

### 14.3. Cross-Component, Caching, and Failures

- Account service commits status change while user cache is not yet invalidated: measure lag until enforcement blocks and keep within SLO.
- Event bus outage when disabling a user: high-risk endpoints fail closed or read authoritative version.
- Password reset completes while remote token invalidation fails: outbox/retries recover, and enforcement blocks stale sessions past policy.
- Auth succeeds on node A while account is suspended on node B: node A rejects subsequent requests per policy.
- `SecurityContext` session created by custom login controller: saved via Spring Security 6 `SecurityContextRepository`, not only `ThreadLocal`.
- Service self-invokes `@PreAuthorize` method in same class: tested to catch proxy bypass.
- Account is admin in tenant A but not tenant B: domain policy denies admin action in tenant B.
- Domain `Account` entity containing PII is never serialized into principals, sessions, or error responses.
- Outbox/email dispatch with tokens: raw tokens never appear in logs, shared queues, or unprotected analytics.

### 14.4. Suggested Test Names

```text
registerCreatesPendingAccountNotAuthentication()
unverifiedEmailDoesNotAutomaticallyActivateAccount()
daoProviderValidatesPasswordHashAndAccountFlags()
suspendedAccountCannotLoginEvenWithValidPassword()
existingSessionDoesNotBypassAccountRevocation()
userDetailsServiceLookupHasNoBusinessSideEffects()
roleApprovalCannotBeBypassedByClientSuppliedRole()
tenantAdminCannotGrantRoleAcrossTenants()
methodSecurityDoesNotReplaceDomainOwnershipCheck()
passwordResetDoesNotLogInOrDisableMfa()
verificationAndResetTokensArePurposeSeparated()
concurrentEmailVerificationIsSingleUse()
deletionBlocksSsoReProvisioningForForbiddenIdentity()
repositoryProjectionExcludesSensitiveAccountData()
```

These are illustrative test case names, not a runnable test suite; implement them against your actual business policies.

## 15. Pre-Release Design Checklist

1. **Draw clear boundaries:** define who owns the Account aggregate/state machine, security integration, event consumption, and revocation.
2. **Stable identity:** use internal account IDs and verified `(iss,sub)` for external providers; treat email as a contact, not an automatic trust anchor.
3. **Separate reads and writes:** `UserDetailsService` reads minimal projections; `AccountUseCase` writes and preserves invariants.
4. **Passwords:** `PasswordEncoder` handles hashing/checking while the app defines policies, migration, and recovery; never store plaintext.
5. **States:** carefully map business states to enabled/locked/credential-expired and authorization without collapsing everything together.
6. **Token lifecycle:** email verification, password reset, magic login, and access/refresh tokens each have distinct purposes, TTLs, and verifiers.
7. **Authorization:** layer request-level, method-level, and domain resource/tenant policies; never treat `hasRole` as complete access control.
8. **Stale sessions/tokens:** implement measurable revocation mechanisms rather than assuming status updates revoke everything automatically.
9. **Database correctness:** enforce unique constraints, row locking/optimistic concurrency, idempotency, transactions, and outbox events.
10. **MFA/recovery:** guard factor changes, roles, email, password, and account closure with appropriate reauthentication/step-up.
11. **Privacy and operations:** enforce retention, audits, alerts, rate limits, anti-enumeration, and secret-free principals/logs.
12. **Testing:** test wrong credentials, account states, ownership, multi-node races, stale caches, role changes, incident revocation, and SSO identity confusion.

## 16. Self-Check Knowledge Questions

**Q1.** Does `UserDetailsService` automatically create accounts, send activation emails, and delete user data on request?  
**Answer:** No. It is a data-retrieval interface for username/password authentication. Account lifecycle workflows belong to Account Service; stuffing extra side effects into a `UserDetailsService` implementation creates tight coupling and hard-to-control behavior.

**Q2.** A user registered successfully and has a password hash in the DB. Why is login still denied?  
**Answer:** The domain account may still be `PENDING_EMAIL` or `PENDING_APPROVAL`; the `UserDetails` projection or authentication policy must block full sessions until activation requirements pass.

**Q3.** Can clients send `roles=["ADMIN"]` to the registration endpoint and get `ROLE_ADMIN` back in `UserDetails`?  
**Answer:** No. Roles are determined by domain approval/grant policies and stored in a trusted source of truth; user input must never elevate privileges.

**Q4.** If an admin locks a user in the DB, do existing `HttpSession` instances automatically expire?  
**Answer:** Not by default. You must explicitly invalidate/revoke sessions or validate account/session versions on subsequent requests.

**Q5.** Does `@PreAuthorize("hasRole('USER')")` prevent a user from reading someone else's invoice?  
**Answer:** No. You must enforce owner/tenant/ACL checks in business policies or appropriately scoped database queries.

**Q6.** Why should `lastLoginAt` not be updated inside `UserDetailsService.loadUserByUsername`?  
**Answer:** Lookups happen even on wrong passwords or repeatedly via caches/providers. Record successful logins only from trusted authentication-success events/handlers with clear semantics.

**Q7.** `PasswordEncoder` belongs to Spring Security. Who owns the rule “new password cannot match the old password”?  
**Answer:** The account/password use case enforces business policy and calls the encoder properly for checking/hashing; Spring does not automatically impose product-specific rules.

**Q8.** A user authenticates via OIDC with an email matching a locked local account. Should a new local account be auto-created?  
**Answer:** Not by default. Link via verified `(iss,sub)` while evaluating lifecycle state, tenant, allowlists, and anti-takeover policies.

**Q9.** Is using `JdbcUserDetailsManager` wrong in a small project?  
**Answer:** No. For simple needs it can fit well. Just avoid mistaking a basic CRUD user store for complete onboarding, approval, recovery, deletion, and audit workflows.

**Q10.** How do we identify the right boundary during an incident?  
**Answer:** Domain logic explains account state and who was permitted to change it; Security explains actual credential, authentication, and authorization checks. Audits, metrics, and traces must connect both sides without exposing secrets or sensitive data.

## References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, `AuthenticationManager`, `AuthenticationProvider`, authorities.
- [Spring Security 6.5 — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): credential lookup interface and implementations.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): combining `UserDetailsService` and `PasswordEncoder`.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): password hashing, `DelegatingPasswordEncoder`.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and Spring AOP.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context persistence, sessions, and concurrent session controls.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): account states, anti-enumeration, reauthentication.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): recovery tokens, expiry/single-use, reset flows.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): per-resource/tenant authorization and least privilege.
