# Password Reset Using Tokens Independent from Login Tokens

> **Context:** Spring Security – Authentication, **Account Lifecycle** group. This lesson guides designing a **forgot/reset password** workflow for accounts with local passwords. Core focus: **a reset token carries only a very narrow privilege — setting a new password after verification — and is strictly never a login or access token**. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet stack), and PostgreSQL; Spring integration snippets must be wired to your real project's repositories, mail delivery, database, and user sessions.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **password reset**, **password change**, **email verification**, **magic login**, **OAuth2 access tokens**, **refresh tokens**, HTTP sessions, and reset tokens.
2. Explain why **reusing login tokens for reset** or letting **reset tokens log users in directly** introduces account takeover vulnerabilities.
3. Design high-entropy random reset tokens with short TTLs, a **dedicated purpose**, hashed storage, single-use enforcement, and transactional verification.
4. Select verified recovery email destinations, return neutral responses to defeat **account enumeration**, prevent spam, and build URLs from configured public origins.
5. Update passwords via Spring Security `PasswordEncoder`, block replays, and ensure **password update and token consumption succeed or roll back together**.
6. Solve edge cases: concurrent reset requests, multiple unused reset tokens, email changes, account locks, stale sessions/tokens, MFA, and account recovery.
7. Write security tests covering **privilege separation**, expiration, race conditions, reauthentication, session revocation, token leakage, and account states.

## 1. Context: Forgot Password Is Not Login

User `lan` forgets their password. The application lets them enter a registered email and sends a link:

```text
https://account.example.org/password/reset?token=BASE64URL_RANDOM_SECRET
```

Whoever holds the link within its validity window can submit the token **to the reset endpoint** to set a new password for the exact account bound to that token. This is an **account control recovery mechanism**, not an ordinary login session.

**Core design principle:** reset tokens must be **independent in semantics, storage, privilege scope, TTL, consumption rules, and revocation state** from tokens used to log in or call APIs.

```text
                 ┌──────────────────────┐
                 │ User forgot password │
                 │ and enters email     │
                 └──────────┬───────────┘
                           │
                           ▼
                  POST /password/forgot
                           │
                 Issue PASSWORD_RESET secret
                           │
                           ▼
                  Email containing reset link
                           │
                GET /password/reset?token=...
                           │
             Render form only, do not log in
                           │
              POST /password/reset + CSRF
                           │
         Verify purpose, subject, TTL, single-use
                           │
            Transaction: update hash + consume token
                           │
                      Commit succeeded
                           │
        Revoke/re-evaluate sessions, send alert
                           │
             Require normal sign-in
```

**Do NOT** do any of the following:

```text
Have reset token  → treat as Bearer access token
Have reset token  → create SecurityContext / ROLE_USER immediately
Have active session → allow password change from "forgot password" without
                      verifying old password or separate reset token
Reset finished    → auto-issue new JWT and sign in without verification
```

Password reset is a sensitive operation because it alters how the account owner authenticates. **Proving access to a verified mailbox** via a reset token **does not automatically** prove other MFA factors; never allow a reset flow to disable MFA or bypass security keys.

## 2. Comparison Table of Token Types and Independence

| Credential / Token | When is it issued? | What is it for? | Must NEVER be used for |
|---|---|---|---|
| **Password reset token** | User requests recovery; server sends to verified contact | Setting a new password **once**, before expiration | Signing in, calling APIs, changing email, disabling MFA, granting roles |
| HTTP session ID | After successful login (or restricted pre-login session) | Identifying a web session with verified authentication | Replacing a reset token in forgot-password flows |
| OAuth2 access token/JWT | After an OAuth2 grant | Calling APIs with granted audience/scopes | Replacing a reset token or acting as a password |
| OAuth2 refresh token | Per grant/IdP | Obtaining new access tokens per policy | Setting a local password without separate recovery proof |
| Magic-login token | When app intentionally issues a one-time token for **sign-in** | Authenticating a login per policy | Automatically acting as a password-reset token |
| Email verification token | When proving control over a specific email address | Verifying **address ownership** | Signing in, resetting passwords, changing other recovery addresses |
| Change-password action | User is logged in and reauthenticated (old password/MFA per policy) | Changing password of the owned account | Bypassing forgot-password policy or using another person's token |

**Purpose separation principle:** the same secret string must never carry both meanings “I am allowed to change the password” and “I am logged in.” You may share underlying DB or queue infrastructure, but records need separate **types/purposes**, endpoints, and verifiers. Safer still is a **dedicated table/namespace** with reset-specific policies.

### 2.1. Why Sharing Tokens Is Dangerous

Consider these mistakes:

- Taking a JWT access token and submitting it to `POST /password/reset` while checking only signature/`sub` and allowing a password change: any client or device with a leaked access token can achieve **long-term account takeover** by changing the password. Login audience/scopes do not prove password-recovery intent.
- Taking an emailed reset token, putting it in `Authorization: Bearer ...`, and having APIs accept it: an emailed recovery token becomes a credential carrying all user permissions without ever completing login or MFA.
- Using one `tokens(token_value,user_id,expires_at)` table for email verification, password reset, and login without checking `purpose`: a token issued for a weaker operation can be redeemed for a privileged one (**cross-purpose token confusion**).
- Using a signed JWT reset token without tracking `jti`/consumed state: while its signature and expiry hold, the token can reset the password repeatedly, violating “single-use.”
- Using an external IdP's access token to set a local password bypassing local policy: blurs account, provider, and tenant boundaries.

**Mitigation:** the reset verifier reads **only** from the reset-token store/structure with purpose `PASSWORD_RESET` and unconsumed state; the login verifier **never** queries the reset-token store. Even if two strings happen to look alike, the system must reject cross-channel use.

### 2.2. Same `userId` Does Not Mean Same Privilege

A reset token typically references `local_user_id=42`, just like a session or JWT `sub=42`. Yet `userId` identifies only the **subject** the credential refers to, not the privilege. Before granting access, verify the **credential type, issuer, purpose, time window, subject, state, and policy**.

Never use `Authentication.isAuthenticated()==true` from an existing session or a decoded JWT to bypass reset-token policy. **Knowing who someone is** and **what an action is authorized to do** are separate concerns.

## 3. Standard Safe Workflow When a User Forgets Their Password

### Step A — Intake Recovery Request

The user opens `GET /password/forgot` and submits `POST /password/forgot` with an email or username. The server **does not** authenticate the caller merely because they typed an existing email.

- Canonicalize the identifier per application rules (e.g., stored email rules), without changing account ownership based on Gmail dots/plus tags or arbitrary Unicode tweaks.
- Look up the account in the **user store** and pick only a **verified recovery contact** per policy. Never send tokens to an arbitrary new email typed in the form if it is not verified and bound to the account.
- Return the exact same message whether the account exists or not: “If the account is eligible for recovery, we will send instructions to the registered channel.”
- Avoid large timing, status, or body differences between the two cases. You can enqueue requests and process them asynchronously behind a neutral response.
- Rate-limit by account/contact, IP, device, ASN/risk signals, and email volume. Avoid letting reset requests immediately lock the victim's account or flood their inbox.
- Never change the password, disable the account, update `last_login`, or create a session upon requesting a link.

The OWASP Forgot Password Cheat Sheet recommends consistent responses, minimizing enumeration, and **changing account state only after valid reset proof is presented**.

### Step B — Issue a Dedicated Recovery Token

If the account satisfies policy, the server generates a secret using a **cryptographically secure pseudorandom number generator (CSPRNG)**, such as 32 bytes (256 bits) from `SecureRandom`, encoded as unpadded Base64URL for URLs.

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class PasswordResetSecret {
    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordResetSecret() {}

    public static String issueRawSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }
}
```

**Note:** the Java class above only creates a random secret; it is **not a complete reset workflow**. You must still store a hash server-side, bind user ID, purpose, TTL, and credential version, and perform atomic consumption.

**Never** use `Math.random()`, timestamps, predictable UUIDs from weak implementations, email/username, the current password hash, or existing session/JWT access tokens as reset tokens. Never place the secret in logs, telemetry, analytics, or exception messages.

### Step C — Store the Narrow-Scoped Token Server-Side

Recommended storage fields:

```text
token_hash           = SHA-256(256-bit raw secret) or HMAC-SHA-256
purpose              = PASSWORD_RESET
local_user_id        = 42
credential_version   = 7
contact_version      = 3 (if checking whether recovery email changed)
created_at           = ...
expires_at           = ...
consumed_at          = null
requested_context    = audit metadata, not raw token
```

- **Hash the secret; never store the raw secret**. With a 256-bit random token, SHA-256 prevents practical reversal from a leaked database; HMAC adds namespace separation and restricts offline analysis under certain threat models. Do not misuse a slow `PasswordEncoder` for directly indexed 256-bit tokens: SHA-256/HMAC risk profiles differ from low-entropy human passwords.
- Pick a **short TTL suited to email delivery** (for instance, 10–30 minutes per policy; not a mandatory framework number). TTL never replaces **one-time use**.
- Each token binds **one stable local user** and **one purpose**, never relying on display email to determine ownership.
- If the account changes its password or recovery contact while a token is live, `credential_version`/`contact_version` can invalidate earlier tokens, protecting against stale links.
- You may enforce that only the latest token works, or allow multiple concurrent tokens while **the first password change invalidates all others** via version/transaction. Pick a clear policy and test concurrency.

### Step D — Deliver the Link to the Verified Contact

The application builds links using a configured **canonical public origin**, for example:

```text
https://account.example.org/password/reset?token=<random-base64url>
```

Never concatenate scheme/host from `HttpServletRequest.getServerName()`, `Host`, `Forwarded`, or `X-Forwarded-Host` influenced by the client, especially behind reverse proxies. **Host Header Injection** can point recovery emails at an attacker's domain and leak the secret.

The recipient address must come from the eligible contact record in the user store, never an arbitrary email from the request. With multiple tenants/custom domains, map **verified tenant → managed HTTPS origin**; never use unverified domain strings from users.

The email should contain the single-use link, explain its expiration, and warn the user if they did not request it; never email a new password.

### Step E — Opening the Link: Never Change Password on GET

`GET /password/reset?token=...` should **only** display the new-password form, perform preliminary format/expiry checks if appropriate, and set safe response headers; it **must not** change the password or auto-login.

Because email gateways prefetch/scan links, consuming tokens on GET breaks UX and enables abuse. The actual change must occur on a properly **CSRF-protected POST** carrying the user-submitted raw secret and new password. On POST, the server verifies and consumes atomically.

Responses for invalid, expired, or used tokens should be uniform and never reveal who owned the link. The UI simply guides the user to request a new link.

### Step F — POST: Verify Token and Set the New Password

On `POST /password/reset`, the backend executes:

1. Validate request size, inputs, and CSRF; enforce attempt rate limits.
2. Hash the raw reset secret using the exact storage mechanism and query the **password reset store**; never ask the login token validator.
3. Verify `purpose=PASSWORD_RESET`, expiration, `consumed_at IS NULL`, valid user/contact/credential versions, and an account state permitting reset.
4. Validate the new password against policy (length, compromised/common passwords, blocklists; avoid arbitrary composition rules); if a confirmation field is present, verify both match.
5. Encode the password via a managed `PasswordEncoder` (Argon2id/bcrypt/PBKDF2/scrypt per policy) and persist the **hash**, never plaintext.
6. Inside **one transaction**: atomically claim the single-use token, lock/check the user, update the password hash, increment credential version, and invalidate prior reset tokens per policy.
7. After commit succeeds, **do not auto-login**. Redirect the user to normal login; if MFA is enabled, enforce MFA as usual.
8. Send a password-change alert to the registered contact without including the raw password. Revoke or re-evaluate existing sessions, refresh tokens, remember-me tokens, and recovery grants per policy, ensuring APIs actually enforce revocation.

If updating the password fails, the transaction must roll back **token consumption as well**. Never mark the token consumed in one transaction and update the password in another, risking a half-completed state.

## 4. Database: Separating Password Reset from Login Credentials

Assume `local_users` has `id`, `password_hash`, `credential_version`, `recovery_contact_version`, and appropriate account status. PostgreSQL example:

```sql
CREATE TABLE password_reset_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_hash BYTEA NOT NULL UNIQUE,
    local_user_id BIGINT NOT NULL REFERENCES local_users(id),
    purpose VARCHAR(32) NOT NULL DEFAULT 'PASSWORD_RESET',
    credential_version BIGINT NOT NULL,
    recovery_contact_version BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT reset_purpose_only CHECK (purpose = 'PASSWORD_RESET'),
    CONSTRAINT reset_expiry_valid CHECK (expires_at > created_at)
);

CREATE INDEX password_reset_user_idx
    ON password_reset_tokens(local_user_id);

CREATE INDEX password_reset_expiry_idx
    ON password_reset_tokens(expires_at);
```

**Schema explanation:**

- `token_hash` is the digest of the **raw reset secret**, not a password hash; `BYTEA` holds 32 bytes for SHA-256.
- `purpose` is fixed to `PASSWORD_RESET`; alongside a dedicated table, this check constraint enforces the invariant and prevents confusion.
- `credential_version` and `recovery_contact_version` capture the account's versions when the token was issued. Incrementing them invalidates earlier reset links without scanning/deleting every row.
- `expires_at`/`consumed_at` are mandatory conditions; an index supports cleaning up expired tokens, though cleanup **never replaces expiry checks at redemption time**.
- `local_user_id` is an internal key; changing a display email does not transfer token ownership.
- Never allow clients to supply `user_id` in the completion request body; the owner **must come from the reset token record**.

Application login tokens and sessions (if used) live in **different** tables:

```text
password_reset_tokens:
  token_hash → local_user_id, purpose=PASSWORD_RESET, expires_at, used_at

http_sessions / access_tokens / refresh_tokens:
  session_id or bearer credential → authenticated principal, permissions,
  expiry, audience, revoked_state per mechanism

No query or validator uses a password_reset_tokens row
to create a login principal directly.
```

### 4.1. Atomic Consumption Against Replay

Never write:

```text
SELECT token WHERE consumed_at IS NULL
if found:
    updatePassword()
    UPDATE token SET consumed_at=now()
```

Two requests can read the same unconsumed token concurrently and overwrite the password twice without locking/transactions. In PostgreSQL, **atomically claiming the token** inside a transaction works cleanly:

```sql
UPDATE password_reset_tokens
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_hash = :digest
  AND purpose = 'PASSWORD_RESET'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
RETURNING local_user_id,
          credential_version,
          recovery_contact_version;
```

If **0 rows** return, the token is invalid, expired, or used. If one row returns, the transaction is **not yet committed**; the backend must still:

- Lock the `local_users` row via `SELECT ... FOR UPDATE` (or equivalent concurrency control).
- Compare `credential_version` and `recovery_contact_version` against current values.
- Check account status and password policy.
- Update `password_hash` and increment `credential_version` so no other token issued at the same version can succeed.
- Commit only when every step passes; any exception rolls back `consumed_at` too.

**Important nuance:** if two different tokens were issued for the same user at the same `credential_version`, two transactions could each claim **two distinct token rows**. Locking and checking the `local_users` version after claiming is decisive: the first transaction bumps the version, and the second sees a version mismatch and rolls back. `UNIQUE(token_hash)` alone cannot prevent two different links from both changing the password.

### 4.2. Stale Sessions/Tokens After a Password Change

Changing `password_hash` does not automatically invalidate:

- Previously logged-in `HttpSession`/remember-me cookies.
- Issued JWT access tokens whose `exp` is still in the future.
- OAuth2 refresh tokens, SSO sessions, or sessions on other devices.
- Other unused password reset tokens, unless versioned or revoked.
- WebSocket connections or application-specific API tokens.

Establish an explicit policy: usually **revoke existing sessions, refresh/remember-me tokens, and related recovery grants** upon successful password reset, or at least offer “sign out of all devices” depending on risk. Under account-takeover risk, broad revocation is generally preferred.

Implement revocation **for real**:

- Spring HTTP sessions: delete sessions from the session repository or track user `session_version` so filters/gates reject stale sessions.
- Stateless JWTs: increment an `authz_version`/`session_version` claim/record and use denylists/introspection/short TTLs so Resource Servers reject old tokens; changing only the DB password hash does not alter issued JWTs.
- Remember-me: delete persistent remember-me series/tokens or bump the corresponding version.
- Refresh tokens/IdP: call revocation APIs when supported, keeping propagation delays in mind.

If calling a remote revocation service over the network, a local DB transaction **is not atomic across systems**. Persist an **outbox event in the same transaction** for reliable retries; for endpoints needing immediate effect, APIs must check shared version state per request rather than waiting for async consumers. Never claim “revoked immediately” if you only enqueued an async message.

## 5. Recovery URLs, Host Header Injection, and Token Leakage

### 5.1. Trusted Canonical Origin

Deployment configuration example:

```yaml
app:
  password-reset:
    public-origin: ${PASSWORD_RESET_PUBLIC_ORIGIN:https://account.example.org}
    token-ttl: PT15M
```

`PASSWORD_RESET_PUBLIC_ORIGIN` comes from administrator/deployment configuration, validated for HTTPS, exact hostname, and no userinfo, query, fragment, or unexpected path. In multi-tenant setups, map origins from verified tenants. **Never** derive emailed links from `request.getRequestURL()`, `Host`, `X-Forwarded-Host`, or any client-supplied header/URL.

Emails must point only to the application's **official domain**. HTTPS protects the link in transit, but cannot save you if the server generates a link to the wrong domain via Host injection.

### 5.2. Raw Tokens in Query Strings Are Secrets

A URL carrying a reset token can leak via browser history, email forwarding, link scanners, proxy access logs, WAF logs, APM, analytics, `Referer` headers, or screenshots. Harden those surfaces:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'
```

This CSP line is an example that **must be tailored to your page, nonces, and actual assets**. On pages displaying a reset token, avoid third-party JS, fonts, images, and analytics that send full URLs externally. Never log query strings or cookies containing raw tokens, and never put tokens in exceptions, trace IDs, or metric labels. After reset, redirect to a clean path with no token.

Watch out for open redirects: never accept `next=https://evil.example` and call `sendRedirect(next)`. When redirecting, use **server-side allowlisted target codes** such as `login → /login`, and never copy the token into `Location`.

### 5.3. GET Requests and Link Scanning

Mail gateways may open links automatically using GET. `GET /password/reset?token=...` should only render the form, **without updating the account**, auto-logging in, or auto-consuming the token. Only a valid POST consumes once and changes the password.

If you want to keep tokens out of the URL bar quickly, the UI can move the secret into a safe POST step and redirect to a clean URL, provided CSRF, XSS, and browser session loss are handled cleanly. **Never** run JavaScript immediately on GET to change a password automatically without user intent.

## 6. Spring Security 6.x: Appropriate Web Endpoint Configuration

Spring Security provides authentication, authorization, CSRF, session security, and password encoding. **Forgot-password token issuance and redemption are typically application-built logic**; do not confuse them with `oneTimeTokenLogin()` for sign-in, `OAuth2 tokens` for APIs, or `remember-me`.

### 6.1. Dependencies (Gradle, Spring Boot 3.x)

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

JPA, mail, database, and template choices are merely implementation options; you can swap in JDBC/jOOQ/Redis or another mail provider per your project's architecture. Spring Security **does not send reset emails automatically** just from adding starters.

### 6.2. Standard PasswordEncoder Bean

`src/main/java/com/example/security/PasswordEncodingConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordEncodingConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }
}
```

`PasswordEncoder.encode(newPassword)` stores new passwords. Spring Security's `DelegatingPasswordEncoder` supports multiple `{id}`-prefixed hash algorithms for clean upgrades and migrations. Never store raw passwords, hash passwords with plain SHA-256, use `NoOpPasswordEncoder`, or let clients submit pre-hashed passwords that bypass policy.

**Distinguishing hashing mechanisms:**

| Data | Characteristics | Appropriate storage |
|---|---|---|
| User-chosen password | Typically low entropy; vulnerable to offline cracking if DB leaks | Adaptive password hashing via `PasswordEncoder` |
| Server-generated 256-bit reset token | High entropy; only needs lookup by submitted token | SHA-256/HMAC digest + TTL + single-use |
| Access/session token | OAuth/session-scoped credential | Independent token/session store with dedicated audience/purpose/expiry |

Never call `PasswordEncoder.matches()` to validate a reset token as if it were a password; the reset verifier must validate **the exact `PASSWORD_RESET` record and one-time state**.

### 6.3. SecurityFilterChain and CSRF

Illustrative configuration for a standard form-login web app; `POST /password/forgot` and `POST /password/reset` are accessible **without a login session**, yet **are not exempt from CSRF**:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/password/forgot", "/password/reset").permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/password/forgot", "/password/reset").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Spring Security CSRF remains enabled for form POSTs.
        return http.build();
    }
}
```

`permitAll()` only lets anonymous clients **reach the HTTP endpoint**; it does not mean the reset request has proven account ownership. Actually changing the password still requires a valid reset token in the service layer. With Spring MVC forms/Thymeleaf, include CSRF tokens on POSTs as supported by the framework. Never call `csrf.disable()` just so forgot-password users can submit a POST.

**Note for pure stateless APIs:** an app can design a reset endpoint without session cookies, but must still evaluate CSRF, origin checks, rate limits, token possession, anti-automation, and the threat model. Never assume “the API uses JSON” automatically makes cross-site requests harmless.

### 6.4. Controller Separating GET and POST

The following is a **Spring MVC skeleton** requiring templates `password-forgot`, `password-reset`, `password-done` and a backing service; it is **not** a standalone app runnable with `javac`:

```java
package com.example.security;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class PasswordResetPages {

    private final PasswordResetUseCase reset;

    public PasswordResetPages(PasswordResetUseCase reset) {
        this.reset = reset;
    }

    @GetMapping("/password/forgot")
    String forgotPage() {
        return "password-forgot";
    }

    @PostMapping("/password/forgot")
    String request(@RequestParam String account) {
        // Service always returns the same UI, even if account does not exist.
        reset.requestReset(account);
        return "password-sent";
    }

    @GetMapping("/password/reset")
    String resetPage(@RequestParam String token, Model model) {
        // DO NOT consume token or change password on GET.
        model.addAttribute("resetToken", token);
        return "password-reset";
    }

    @PostMapping("/password/reset")
    String finish(@RequestParam String token,
                  @RequestParam String newPassword) {
        reset.completeReset(token, newPassword);
        return "password-done";
    }
}
```

Service contract so the controller type-checks within a project:

```java
package com.example.security;

public interface PasswordResetUseCase {
    void requestReset(String account);
    void completeReset(String rawToken, String newPassword);
}
```

**Critical enforcement lives in the service implementation**, not the controller. `requestReset` must generate a CSPRNG token and send email per policy; `completeReset` must execute atomic repository consumption + transactional password update. If rendering a template containing `resetToken`, HTML-escape it properly, add a hidden CSRF input, and keep the token away from scripts and analytics. On its own, the controller above **does not** enforce password policies, anti-enumeration timing, security headers, or auditing unless those layers are added.

### 6.5. Password Reset Transaction (Pseudocode)

Service-side algorithm example, **not copy-paste standalone Java code**:

```text
completeReset(rawToken, newPassword):
    validate request size, password policy and rate limits
    tokenHash = SHA256(rawToken)

    begin database transaction
        grant = claimUnusedResetToken(tokenHash, purpose=PASSWORD_RESET,
                                      unexpired=true)
        require grant exists

        user = SELECT local_users WHERE id=grant.user_id FOR UPDATE
        require user exists and mayResetPassword(user)
        require user.credential_version == grant.credential_version
        require user.recovery_contact_version == grant.contact_version

        passwordHash = PasswordEncoder.encode(newPassword)
        UPDATE local_users
           SET password_hash = passwordHash,
               credential_version = credential_version + 1
         WHERE id = user.id

        invalidate outstanding PASSWORD_RESET grants for this user
        write durable outbox event PASSWORD_RESET_COMPLETED(user.id)
        commit transaction

    keep browser unauthenticated; redirect to normal login
    reliably notify user of change (no password in email)
    revoke/deny old sessions/tokens per security policy
```

**Order may vary** with optimistic locking, JPA, or JDBC as long as all invariants hold. If session revocation must take immediate effect, check a shared credential/session version on Resource Servers rather than relying solely on an async outbox.

**Never call `SecurityContextHolder.getContext().setAuthentication(...)` after a reset**. A reset token has not completed password/MFA login. OWASP likewise recommends returning users to the **normal login flow** after resetting a password.

## 7. Standalone Java 17: A Reset Token Cannot Serve as a Login Token

The following program is a **policy model** runnable with JDK 17+, requiring neither Spring nor a database. It demonstrates:

- Login credentials and reset tokens live in **two separate namespaces**.
- A reset token works once to bump the credential version and never logs the user in.
- A login token cannot be used at the reset endpoint, and vice versa.
- Expired tokens or tokens issued before a completed password change are rejected.

**Warning:** token strings in `main` are fixed demo inputs for deterministic stdout and carry **no real entropy**. Production must use `SecureRandom`; the demo merely assumes tokens were generated by a trusted system. In-memory `HashMap`/`Set` structures do not replace database transactions or multi-node shared token stores.

Save as `ResetVsLoginTokenDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;

public class ResetVsLoginTokenDemo {

    record ResetGrant(
        String tokenDigest,
        String userId,
        Instant expiresAt,
        long issuedVersion,
        boolean consumed
    ) {
        ResetGrant consume() {
            return new ResetGrant(
                tokenDigest, userId, expiresAt, issuedVersion, true);
        }
    }

    static final class Policy {
        private final Map<String, ResetGrant> resetGrants = new HashMap<>();
        private final Map<String, Long> userVersions = new HashMap<>();
        private final Set<String> activeLoginTokens = new HashSet<>();

        void addUser(String userId) {
            userVersions.put(userId, 1L);
        }

        // Login session namespace separated from reset namespace.
        void addLoginToken(String token) {
            activeLoginTokens.add(token);
        }

        String login(String bearer) {
            return activeLoginTokens.contains(bearer)
                ? "LOGIN_ACCEPTED" : "LOGIN_REJECTED";
        }

        void issueForDemo(
                String resetSecret, String userId, Instant expiresAt) {
            long version = userVersions.get(userId);
            resetGrants.put(
                digest(resetSecret),
                new ResetGrant(
                    digest(resetSecret), userId, expiresAt, version, false));
        }

        synchronized String reset(String secret, Instant now) {
            String key = digest(secret);
            ResetGrant grant = resetGrants.get(key);

            if (grant == null
                    || grant.consumed()
                    || !now.isBefore(grant.expiresAt())) {
                return "RESET_REJECTED";
            }

            long currentVersion = userVersions.getOrDefault(
                grant.userId(), -1L);

            if (currentVersion != grant.issuedVersion()) {
                return "RESET_REJECTED";
            }

            resetGrants.put(key, grant.consume());
            userVersions.put(grant.userId(), currentVersion + 1L);
            return "PASSWORD_CHANGED_LOGIN_REQUIRED";
        }
    }

    static String digest(String raw) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                .digest(raw.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");
        Policy policy = new Policy();
        policy.addUser("user-42");

        String resetSecret = "demo-only-reset-secret-A";
        String anotherReset = "demo-only-reset-secret-B";
        String loginToken = "demo-only-login-session";

        policy.addLoginToken(loginToken);
        policy.issueForDemo(resetSecret, "user-42", now.plusSeconds(300));
        policy.issueForDemo(anotherReset, "user-42", now.plusSeconds(300));

        System.out.println("Reset used as login: " +
            policy.login(resetSecret));
        System.out.println("Login used as reset: " +
            policy.reset(loginToken, now));
        System.out.println("Valid reset: " +
            policy.reset(resetSecret, now));
        System.out.println("Replayed reset: " +
            policy.reset(resetSecret, now));
        System.out.println("Older second link: " +
            policy.reset(anotherReset, now));
        System.out.println("After reset login: " +
            policy.login(resetSecret));
        System.out.println("Old session example: " +
            policy.login(loginToken));
    }
}
```

Compile and run:

```bash
javac ResetVsLoginTokenDemo.java
java ResetVsLoginTokenDemo
```

Exact stdout:

```text
Reset used as login: LOGIN_REJECTED
Login used as reset: RESET_REJECTED
Valid reset: PASSWORD_CHANGED_LOGIN_REQUIRED
Replayed reset: RESET_REJECTED
Older second link: RESET_REJECTED
After reset login: LOGIN_REJECTED
Old session example: LOGIN_ACCEPTED
```

**Line-by-line explanation:**

1. `resetSecret` is not in `activeLoginTokens`, so it cannot sign in.
2. `loginToken` is not in `resetGrants`, so it cannot reset the password.
3. A valid reset bumps `user-42` version from 1 to 2, returning only `PASSWORD_CHANGED_LOGIN_REQUIRED` without creating a login.
4. Submitting the same reset token a second time sees `consumed=true` and is rejected.
5. Another reset token issued at version 1 is also invalidated after the password change because current version is now 2.
6. The reset token remains unusable for login afterward.
7. **Old session example: LOGIN_ACCEPTED** is an intentional result highlighting a key limitation: **changing a password does not automatically revoke existing login sessions**. Production requires session revocation or session-version checks per policy.

`synchronized` in the demo only prevents races within **a single JVM**, not across a cluster. Production requires transactions, row locking/version checks, and a shared store. The demo does not store real password hashes, send email, verify account contacts, or enforce Spring Security authorization.

## 8. Two Easily Confused Cases: Logged-In Password Change vs Forgot Password

### 8.1. Password Change

A logged-in user wants to change their own password. Require reauthentication via current password or MFA/reauth appropriate to risk, and defend against CSRF and session theft. The app can log an audit event and revoke other sessions per policy. Never issue a password reset token simply because the user is already signed in.

```text
authenticated session
    → recent reauthentication
    → enter new password
    → hash/store/update credential_version
    → session policy and notification
```

### 8.2. Forgot Password (Forgot/Reset)

The user **does not have their current password**. Proof is a **purpose-bound password reset token** delivered via a verified recovery channel:

```text
anonymous request
    → generic response / rate limit
    → email reset token
    → POST token + new password + CSRF
    → atomic consume + password update
    → require normal login
```

Never call `authenticationManager.authenticate(new UsernamePasswordAuthenticationToken(user, resetToken))` to “verify” a reset token through the password provider. The password provider matches **passwords**, whereas the reset service uses a purpose-bound token store. Mixing the two paths creates authentication bypasses.

### 8.3. SSO/OIDC Users Without a Local Password

If an account signs in **solely through an external IdP**, do not silently create a local password and send a reset link just because you recognize the IdP's email claim. Password recovery belongs to the IdP. If the product intentionally lets users add a local password, treat that as a **sensitive enrollment action** with local/SSO ownership proof and explicit policy—not a default reset.

Never treat `email_verified=true` from an IdP as sole proof for a separate local account with a matching email. Valid external identity pairing and account ownership are governed by a dedicated linking mechanism.

## 9. Passwords, Assurance, and MFA After Reset

### 9.1. New Passwords Must Meet Password Policy

- Support sufficiently long passwords; avoid arbitrary composition rules that drive predictable patterns.
- Check common/breached passwords when an appropriate service is available, without sending raw passwords unprotected to third parties.
- Do not impose an overly short max length; set a practical upper bound to protect against hashing DoS.
- Use an appropriate `PasswordEncoder` tuned for your infrastructure; never log or email passwords.
- If using a pepper, manage it in a secret manager with rotation procedures; never commit keys to source control.
- Never store plaintext password history; if policy blocks reuse, check against protected historical hashes.

### 9.2. Password Reset Does Not Reset MFA

- An emailed reset link must never automatically **remove TOTP/WebAuthn registrations**, backup codes, or security keys, nor grant admin rights.
- If the user also lost their MFA device, enforce a **separate recovery policy**: single-use backup codes, a spare security key, controlled helpdesk verification, alerts, audit logs, and optional time delays on high-risk actions.
- For especially sensitive accounts, password changes or recovery may require additional verification steps per policy.
- After reset, new login sessions must still complete **normal MFA** whenever required by the account.

An overly permissive reset flow becomes a backdoor around strong authentication; therefore evaluate the **entire account lifecycle**, not just the login endpoint.

### 9.3. Disabled, Locked, and Deleted Accounts

Policies must distinguish:

- **Temporarily locked for failed passwords:** may permit password recovery alongside intentional unlock behavior; never auto-unlock an admin-blocked account.
- **Disabled due to violation/security decision:** password reset should not auto-reactivate the account.
- **Deleted or pending deletion:** never recreate the user or let an old token resurrect the account.
- **Recovery email changed:** tokens sent to the old address may need invalidation via `contact_version`.
- **MFA recovery:** a separate workflow that must never “borrow” a password reset token.

This calls for an explicit state-machine policy rather than collapsing every account into a single `enabled=true/false` flag and assuming reset is always valid.

## 10. Preventing Common Attacks

| Threat | Scenario | Defense |
|---|---|---|
| **Account enumeration** | Inferring from response/timing whether email exists | Uniform messages and timing, rate limits, queue |
| Email flooding | Attacker sends thousands of reset requests | Per-account/IP throttling, abuse detection, cooldowns |
| Token guessing | Weak, short, or timestamp-derived token | 256-bit CSPRNG, TTL, brute-force limits |
| Token replay | Redeeming a link a second time | Atomic consume + `consumed_at` |
| Two-token race | Two valid links change password concurrently | User row lock + `credential_version` |
| Login-token confusion | Using access/session token to reset password | Separate purpose namespace and separate verifier |
| Reset-token confusion | Using reset secret for API calls/login | Never create session/`Authentication` from reset tokens |
| Host Header Injection | Reset email points to attacker domain | Fixed public HTTPS origin; gateway validates `Host` |
| Token leakage | Referrer/logs/analytics capture token | `no-referrer`, `no-store`, CSP, log redaction |
| GET consumption | Email scanner opens link and mutates state | GET shows form only; POST consumes |
| CSRF | Attacker forces browser to POST reset/change | CSRF protection and appropriate session/input binding |
| Insecure password hash | Storing plain/MD5/SHA-256 passwords | Spring `PasswordEncoder` adaptive hashing |
| Session persistence | Password changed while old cookie/JWT stays valid | Session/token revocation or version checks |
| Recovery downgrade | Resetting password also turns off MFA | Separate recovery, step-up for factor changes |
| Cross-tenant confusion | Tenant A link resets Tenant B user password | User ID + tenant binding and validation |
| Unverified email | Link sent to attacker-supplied contact | Send only to verified recovery contacts |
| Auto-login after reset | Mailbox link becomes a full session | Require normal sign-in flow afterward |
| OAuth-only account | Creating password for SSO account lacking local credentials | Block reset for incompatible account types; use IdP recovery |

## 11. Test Matrix

### 11.1. Link Issuance and Email Delivery

| Scenario | Expected outcome |
|---|---|
| Existing verified email | Email sent only to stored contact; canonical HTTPS link |
| Non-existent email | Same generic UI/status, no account disclosure |
| Existing unverified email | No reset-capable link sent to untrusted contact; UI leaks nothing |
| SSO-only account | Directs to IdP recovery per policy; no local password added |
| Forged `Host: attacker.example` | Link still uses official domain or gateway rejects |
| Forged `X-Forwarded-Host` | Does not alter reset URL in email |
| Spam requests by IP/user | Rate-limited and audited; no unbounded mail flood |
| Mail send error | Handled via retry/queue policy without leaking account existence |
| Two tenants share same email | Link binds exact local user + tenant, never another owner |

### 11.2. Tokens and Password Updates

- Valid raw reset token past `expires_at`: **rejected**, password unchanged.
- Forged or single-character-modified reset token: **rejected**, no session created.
- `purpose=EMAIL_VERIFY` token submitted to password reset endpoint: **rejected**.
- JWT access token, refresh token, or session cookie submitted as reset token: **rejected**.
- Reset token sent in `Authorization: Bearer ...` to call an API: **unauthenticated**.
- Password reset token works only for the **exact local user ID** bound on the record; client-submitted `userId` ignored.
- Valid token for disabled/admin-blocked account: **rejected** per policy.
- Valid token whose `credential_version` bumped because password changed from another device: **rejected**.
- Valid token whose `recovery_contact_version` changed: **rejected**.
- Two concurrent POSTs with the same reset token: at most **one** transaction commits.
- Two POSTs with two different reset tokens at the same credential version: only **one** password change per version policy.
- Password-update transaction fails: token must not remain marked consumed if the update rolls back.
- New password fails policy: invalid hash not saved, no session created.
- Reusing token after successful reset: **rejected**.
- After reset, old password no longer signs in; new password signs in through normal policy.
- After reset, MFA is still required if the account had MFA enabled.
- No API path allows using a reset token as a cookie or access token.

### 11.3. Sessions, CSRF, and Data Exposure

- GET on reset link by email scanner bot → password unchanged, no login created.
- Form POST missing CSRF token while CSRF is enabled → blocked.
- Reset page loads no external scripts/analytics carrying the full URL/token.
- Responses include `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; post-reset redirect drops the token.
- HTTP logs, traces, exceptions, and mailer debug output omit raw tokens and passwords.
- Sessions or refresh tokens issued before reset are revoked or fail version checks per policy; test across multiple API nodes.
- Post-reset alerts go to trusted channels with no password included; alert if reset was not user-initiated.
- Reset endpoint never grants `ROLE_ADMIN` or inherits privileges from an incidental access token.
- Admin disables account after link issuance but before POST → reset does not resurrect the account.

### 11.4. Purpose-Independence Tests (Most Important)

Name tests after the security invariants you want to guarantee:

```text
passwordResetTokenMustNotAuthenticateApi()
loginAccessTokenMustNotResetPassword()
emailVerificationTokenMustNotResetPassword()
passwordResetTokenMustBeSingleUse()
expiredPasswordResetTokenMustBeRejected()
twoConcurrentResetRequestsMustNotBothCommit()
secondResetTokenIssuedBeforePasswordChangeMustFail()
passwordResetDoesNotBypassMfa()
oldSessionsRevokedOrVersionCheckedAfterReset()
resetLinkHostMustNotComeFromRequestHeaders()
```

Do not test only that “an email was sent” or “`newPassword` was saved.” Security tests must deliberately feed the **wrong token type** to every endpoint to catch confusion and bypasses.

## 12. Production and Incident-Response Checklist

1. **Dedicated purpose-scoped tokens:** separate reset table/namespace and dedicated verifier; login APIs never read the reset store.
2. **Unpredictable tokens:** ≥128 bits of entropy, typically 256-bit CSPRNG; short TTL and single-use.
3. **Verified contacts:** send secrets only to controlled recovery channels; neutral anti-enumeration responses.
4. **Atomic database updates:** consume + password hash update + version increment inside one transaction; prevent replay and two-link races.
5. **Standard password hashing:** use Spring `PasswordEncoder`; enforce password policy; never store or email plaintext.
6. **Trusted public URLs:** fixed HTTPS origin; never read `Host` or forwarding headers from clients; restrict redirects.
7. **No sensitive mutations on GET:** avoid scanner auto-consumption; protect POST with CSRF and rate limits.
8. **Minimize token exposure:** `no-referrer`, `no-store`, CSP, no third-party analytics or query logging, no token in redirects.
9. **No auto-login:** after reset completes, send the user through real login and MFA.
10. **Old sessions:** define and test revocation for `HttpSession`, JWTs, refresh/remember-me tokens, and other sessions.
11. **Independence from MFA/recovery:** password reset never disables WebAuthn/TOTP or grants new roles.
12. **Audit & incident response:** log `PASSWORD_RESET_REQUESTED`, `PASSWORD_RESET_COMPLETED`, `PASSWORD_RESET_REJECTED`, `SESSIONS_REVOKED` with verified user/tenant IDs; avoid logging raw tokens or unnecessary emails.
13. **Multi-node/multi-tenant:** shared-DB transactions/locking, version checks, TTLs, clock sync, and tenant binding; measure revocation propagation lag.
14. **Account-type handling:** distinguish local-password, SSO-only, disabled, locked, email-changing, and deleted accounts; never apply one reset rule blindly.
15. **Operational runbooks:** support safe incident rollback, support-assisted verification, and auditing; never let helpdesk read raw reset tokens or bypass MFA arbitrarily.

## 13. Self-Assessment Questions

**Q1.** Why must an unexpired bearer access token never be accepted as a password reset token?  
**Answer:** An access token has a distinct purpose, audience, and scope; accepting it for reset lets anyone holding a temporary API token gain long-term account access by changing the password. Reset requires dedicated recovery proof and a purpose-bound verifier.

**Q2.** Why must even an unexpired reset token never log the user in automatically?  
**Answer:** It grants only a narrow single-use right to set a new password; login must traverse password/MFA or a mechanism explicitly designed for sign-in. Mixing the two privileges causes token confusion and bypasses assurance checks.

**Q3.** Can two different reset links issued for the same user at the same credential version both be redeemed?  
**Answer:** They should not be if policy requires the first password change to invalidate older links. Locking the user row and checking `credential_version` in a transaction prevents two concurrent password changes.

**Q4.** If token hashes are stored with SHA-256, do we still need TTL and single-use?  
**Answer:** Yes. Hashing protects raw tokens if the database leaks; TTL bounds the exposure window, single-use prevents replay, and user/version binding preserves exact ownership.

**Q5.** Can a reset link be sent to an email address just typed by the user that does not yet exist in the account store?  
**Answer:** Not as a recovery path for an existing account. Use only trusted verified recovery contacts or an explicit separate recovery workflow.

**Q6.** Does a successful reset automatically revoke old JWT access tokens?  
**Answer:** Not automatically. A JWT can remain valid until `exp` if Resource Servers verify offline. You need denylists, introspection, version checks, short TTLs, and revocation per policy.

**Q7.** Why not reset the password on GET when the user clicks the email link?  
**Answer:** Email scanners can automatically fetch GET links; state-changing actions belong on a controlled POST after the user submits the new password.

**Q8.** Does Spring Security automatically provide `PasswordResetToken` just by adding `spring-boot-starter-security`?  
**Answer:** No full forgot-password workflow is enabled automatically by the starter. The application must build issuance, delivery, storage, redemption, and password updates; Spring Security provides password encoders and request/session protection primitives.

**Q9.** After a password change, should the system automatically turn off all MFA authenticators because the user proved email access?  
**Answer:** No. MFA enrollment/recovery is a separate workflow with strong assurance requirements; password reset must never elevate access or strip protective layers.

## References

- [OWASP Cheat Sheet — Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): generic responses and comparable timing, random/one-use/expiring tokens, trusted URL origins, post-reset handling.
- [OWASP Cheat Sheet — Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): anti-enumeration, reauthentication, password recovery, and assurance channels.
- [OWASP Cheat Sheet — Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): hashing user-chosen passwords.
- [OWASP Cheat Sheet — Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session IDs, session lifecycles, and revocation mechanisms.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder`, and managing password updates.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protecting state-changing POST forms.
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): security context/sessions and session-management options.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): access tokens sent to APIs, not reset tokens.
