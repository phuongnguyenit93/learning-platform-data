# Registration, Contact Verification, and Account Activation in Spring Security

## 1. The Problem: Completing Registration Does Not Mean Being Logged In

Suppose a system lets users self-create an account using an email address and password. A user enters `lan@example.test` and a sufficiently strong password. At the moment the form is accepted, the system **does not yet know whether the registrant actually controls the `lan@example.test` mailbox**. If it logs them in immediately, someone could register using another person's address, claim the username, or receive permissions meant only for the owner of that contact.

A safe workflow is usually split into distinct steps:

1. **Registration:** validate input, policy, and uniqueness, and create the account in a pending state; store the password using a `PasswordEncoder`, never in plaintext.
2. **Contact verification:** send a code or link containing a random, short-lived, single-use token through the declared contact channel; only when the recipient completes verification do you record control over that channel.
3. **Activation:** update the account status to `ACTIVE` when **all** operational conditions are met (for example, email verified and approved under policy). Only from that point on does the login mechanism allow the account to operate.
4. **Sign-in:** a separate authentication transaction after activation; **do not automatically create a login session just because someone opened a verification link**.

All of these steps relate to the **account lifecycle** in Spring Security, but not all of them are implemented out of the box by the framework. Spring Security handles authentication/authorization, `UserDetails`, `PasswordEncoder`, and the security filter chain; the application must design account persistence, verification tokens, email/SMS delivery, approval, and business state itself.

**Learning outcomes:** understand the registration → verification → activation state machine, generate sufficiently strong tokens, connect account status into Spring Security, handle resend/expiry/race/enumeration/abuse scenarios, and test negative cases as well.

## 2. Distinguishing Four Business Events

| Event | What does it prove? | What does it NOT prove? |
| --- | --- | --- |
| **Valid registration form** | The sender supplied properly formatted data and passed input policy | Does not prove the email/phone number belongs to the sender |
| **Email/SMS successfully dispatched** | The system handed the content to the delivery infrastructure; accepted for processing | Does not prove the recipient read it or was able to use the link/code |
| **Contact verified** | The actor had access to the contact channel at verification time, within the channel's assurance limits | Does not prove government ID, administrative role, or legal identity |
| **Account activated** | The application decided that policy conditions for allowing login are satisfied | Does not mean MFA, business permissions, or session authentication have been completed |

Email verification is **not strong identity proofing** and does not replace MFA. A mailbox can be compromised, forwarded, shared, or recycled. For sensitive applications, additional steps such as administrative approval, organization verification, MFA, and tenant-scoped authorization are required.

An account with `emailVerifiedAt != null` is not necessarily allowed to log in: the account may be `SUSPENDED`, `DISABLED`, `LOCKED`, or awaiting `APPROVAL`. Therefore, **account status** and **contact verification status** should be stored separately.

## 3. Designing an Explicit State Machine

Minimal version:

~~~text
                    POST /register
                          |
                          v
                 PENDING_VERIFICATION
                          |
             confirm valid one-time token
                          |
                          v
                        ACTIVE
                          |
               security policy / admin
                          |
                          v
                     SUSPENDED
                          |
                 authorized recovery
                          |
                          v
                        ACTIVE
~~~

In a system with additional moderation/approval:

~~~text
NEW_REQUEST
    |
    +-- invalid input / blocked rate limit -> REJECTED
    |
    v
PENDING_VERIFICATION
    |
    +-- token expired -> still PENDING, issue new token with controls
    |
    +-- token invalid -> still PENDING, do not modify account
    |
    v
PENDING_APPROVAL (if required by organization)
    |
    +-- denied -> REJECTED/DISABLED
    |
    v
ACTIVE
    |
    +-- policy violation / user deactivated -> SUSPENDED/DISABLED
~~~

**Transitions must have explicit preconditions:**

| Current state | Action | Condition | Next state |
| --- | --- | --- | --- |
| Does not exist | Register | Valid input, no identity conflict under policy | `PENDING_VERIFICATION` |
| `PENDING_VERIFICATION` | Verify contact | Token has matching purpose, is unexpired, unconsumed, and bound to the right account/contact | `ACTIVE` or `PENDING_APPROVAL` |
| `PENDING_VERIFICATION` | Invalid/expired token | Invalid token | **Unchanged**; allow rate-limited resend requests |
| `ACTIVE` | Verify old token | Token already consumed or invalidated | **Unchanged**; do not issue a new session |
| `ACTIVE` | Suspend | Performed by authorized account owner/admin/policy | `SUSPENDED` |
| `SUSPENDED` | Verify old email | Any old registration token | **Must not auto-unlock** |
| `SUSPENDED` | Restore | Approved recovery workflow | `ACTIVE` if policy conditions are met again |

With a lifecycle management service, define states such as `PENDING_VERIFICATION`, `PENDING_APPROVAL`, `ACTIVE`, `DISABLED`, and `SUSPENDED` in an enum; avoid using a single boolean `active` to conflate unverified, unapproved, locked, and banned states.

## 4. Minimal Data Model

A database design can use two tables: account and verification challenge.

~~~sql
-- PostgreSQL example, illustrating schema/structure only.
CREATE TABLE app_account (
    id UUID PRIMARY KEY,
    email_original TEXT NOT NULL,
    email_lookup TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING_VERIFICATION', 'PENDING_APPROVAL',
                   'ACTIVE', 'SUSPENDED', 'DISABLED')),
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE verification_challenge (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES app_account(id),
    contact_snapshot TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (
        purpose IN ('VERIFY_SIGNUP_EMAIL', 'VERIFY_NEW_EMAIL')),
    token_digest TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_verification_account
    ON verification_challenge(account_id, purpose);
~~~

**Field meanings:**
- `id` is an **immutable internal ID**, so email does not have to serve as the primary key. When the email changes, all data still belongs to the same account ID.
- `email_original` is used for display/contact; `email_lookup` is computed under a **consistent canonicalization policy** for lookup/uniqueness.
- `password_hash` is the output of an adaptive `PasswordEncoder` for the password; never store raw passwords and never use plain SHA-256 on its own for user-chosen passwords.
- `status` is the account-level activation decision.
- `email_verified_at` records when the current contact was verified (if the email changes, the status must be reset/adjusted).
- `purpose` prevents a registration token from being used as an email-change or password-reset token.
- `contact_snapshot` prevents race conditions: only accept the token if it still applies to the email address the token was sent to.
- `token_digest` stores the digest of the random token rather than the raw bearer secret; `consumed_at`/`expires_at` enforce single-use and expiration.

**Email note:** per email standards, the domain part is case-insensitive, whereas the local part can be case-sensitive at the protocol level. Some providers have their own dot/alias rules. Do not blindly strip dots, drop `+tag`, or lowercase every local part based on one provider's quirks, as this can merge two different users by mistake. An organization must define its canonicalization and uniqueness policy before implementation.

**Data constraints:** production must ensure accounts and verification tokens are created or consumed inside proper transactions and backed by unique indexes. Doing `SELECT` then `INSERT` without relying on constraints can create duplicate accounts when two registration requests arrive concurrently.

## 5. Secure Registration Flow

### 5.1. Input Validation Is Not Identity Verification

At `POST /account/register`, accept an email and password (and optionally separate terms/policy consent). Validate:
- `email` is non-blank with valid length and syntax; **do not rely solely on a homegrown regex**; account for Unicode/EAI, IDN, and actual mailer policy.
- `password` meets the current password policy; support long passwords/passphrases, do not silently truncate, and check against common/breached passwords when capable.
- Payload size, Content-Type, and auxiliary fields are bounded; protect against abuse/bots and bulk account creation.
- CAPTCHA/abuse challenges are **risk-based supplementary controls**, not replacements for rate limiting, identity proofing, or verification.
- Terms/privacy consent policies if applicable, while avoiding storing excessive PII.

**The server must generate the ID and initial status.** Never trust client-supplied JSON such as `"status":"ACTIVE"`, `"emailVerified":true`, `"role":"ADMIN"`, or `"approvedBy"`. The API should only accept explicitly whitelisted input fields.

### 5.2. Hashing Passwords with the Right Encoder

Spring Security provides `PasswordEncoderFactories.createDelegatingPasswordEncoder()`; it produces strings prefixed like `{bcrypt}...` and supports upgrading algorithms by prefix. For user passwords, use an adaptive hash such as bcrypt/Argon2id/scrypt/PBKDF2 according to policy and deployment capacity; **never store plaintext** or use `{noop}`.

Configuration sample:

~~~java
// Complete bean inside a Spring Boot @Configuration class.
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

In production, monitor cost/latency, memory usage, input length limits, compromised password checking, and hash migration. Choose the encoder according to your security policy and Spring Security version.

### 5.3. Preventing User Enumeration

If you return:
- “Email is not registered” when absent,
- “Email already has an account” when present,

an attacker can probe for registered accounts by calling the endpoint in bulk.

**Public responses should be neutral and consistent**, for example:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"message":"If the request is appropriate, verification instructions will be sent."}
~~~

This does not mean the server must always send an email to every submitted address. Only send appropriate notifications based on policy; you may send nothing for an already active account and avoid letting the public API leak which branch ran. Also pay attention to timing, HTTP status, response size, and side channels; add rate limits by IP, account/email, tenant, and behavior.

Never return the raw token in the registration response. During local debugging, you can use a **test mailbox** accessible only inside the test process; do not expose a public endpoint to read tokens.

## 6. Issuing Contact Verification Tokens

### 6.1. What Security Properties Are Required?

An email verification token should be:
- **Cryptographically random**: generated from `SecureRandom` or an equivalent CSPRNG with high entropy, such as 32 bytes (256 bits).
- **Unpredictable** and not derived from email, user ID, timestamp, or sequential keys.
- **Single-purpose**: `VERIFY_SIGNUP_EMAIL`; never reused as a password-reset token or session ID.
- **Bound to the exact account and email snapshot**, never taking the account ID from the client request during verification.
- **Time-limited**, evaluated using the server's UTC clock/timestamp.
- **Single-use**; consumed atomically so two concurrent requests cannot both activate the account.
- **Revocable** when the email changes, the account is suspended, a resend is requested, or exposure is suspected.
- **Never stored as a raw token** in the database or logs. For a CSPRNG token with sufficient entropy, you can store `SHA-256(token)` and look it up by digest; this differs from user-chosen passwords.

Generating the token:

~~~java
// Java 17 snippet inside a Java service, with SecureRandom/Base64 imports.
byte[] bytes = new byte[32];
SecureRandom random = new SecureRandom();
random.nextBytes(bytes);
String rawToken = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
~~~

Base64URL strings contain no `+`, `/`, or `=` padding. Do not rely on `UUID.randomUUID()` as an invariant for length/entropy, and never generate tokens with `Math.random()` or `Random`.

### 6.2. Storing the Digest, Checking Expiry, and Single Use

A 32-byte random token can be hashed with SHA-256 for storage. During verification, the server hashes the client-submitted token, looks up the record matching that digest, and checks:
1. `purpose` matches the endpoint.
2. Current time is **strictly before** `expires_at`. At the exact expiration timestamp, it is **expired**.
3. `consumed_at` is still null.
4. The account is `PENDING_VERIFICATION`, not disabled or suspended.
5. The current email still matches `contact_snapshot`.
6. Account transition + token consumption happen **atomically**; two verification attempts cannot both succeed.

SQL example with row locking inside a transaction:

~~~sql
BEGIN;

SELECT account_id, contact_snapshot, expires_at, consumed_at
FROM verification_challenge
WHERE token_digest = :digest
  AND purpose = 'VERIFY_SIGNUP_EMAIL'
FOR UPDATE;

-- Application checks that the row exists, expires_at > now,
-- consumed_at IS NULL, contact snapshot, and account status.
-- Within the same transaction, lock the account row / check status.

UPDATE app_account
SET status = 'ACTIVE',
    email_verified_at = now(),
    updated_at = now()
WHERE id = :accountId
  AND status = 'PENDING_VERIFICATION'
  AND email_lookup = :contactSnapshot;

UPDATE verification_challenge
SET consumed_at = now()
WHERE token_digest = :digest
  AND consumed_at IS NULL;

COMMIT;
~~~

This is an **illustrative SQL sketch**, not a copy-paste complete transaction: the application layer must verify **affected row counts**, purpose/expiry, and lock ordering, and roll back if any condition fails. Use challenge/account records with locking or conditional updates that guarantee atomicity. In a multi-server deployment, `synchronized` in a single JVM is insufficient.

**Note on resend:** issuing a new token can invalidate all prior `VERIFY_SIGNUP_EMAIL` tokens for that account within a single transaction, then dispatch the new token via an outbox. Avoid leaving many concurrent tokens valid unless policy specifically requires it.

### 6.3. Delivery and Transactional Outbox

Do not call the email delivery service and **only afterward** persist the account/token without a rollback plan. If the mail provider accepts the send but the DB transaction fails, the user receives a link that cannot verify. If the DB commits but mail delivery fails, the account needs a resend path.

A resilient pattern:
1. A transaction writes the `PENDING_VERIFICATION` account, the challenge digest, and an **outbox event** containing appropriately protected delivery data.
2. Commit the transaction; an email worker reads the event and delivers through the mail provider.
3. When the provider reports success/failure, record delivery status and perform bounded retries while preserving idempotency.
4. Never write the raw token into logs; if the outbox must temporarily hold the token for sending, **encrypt the payload and restrict access and retention**, or use an architecture that issues/wraps the token appropriately at dispatch time.
5. Track delivery/failure/delay metrics and provide a safe resend channel.

Never treat HTTP 202 or “email delivered to provider” as proof that the user has verified their contact.

## 7. Email Verification Links and Automated Click Risks

Emails typically contain a link like:

~~~text
https://accounts.example.org/verify-email?token=<one-time-value>
~~~

A URL in an email is a **short-lived credential**, so extra layers of protection are needed:
- The domain/hostname must be statically configured and owned by the RP; never build `verificationUrl` from untrusted `Host` or `X-Forwarded-Host` headers (host header poisoning).
- Use HTTPS only; keep tokens out of analytics, third-party scripts, click tracking, and access logs.
- On the landing page, set `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; avoid loading third-party assets that could observe the URL.
- Never place tokens in long-lived storage; enforce expiration and single-use.
- **Email security scanners/link previewers may automatically fetch GET links.** Never activate an account on a GET request just because the link was opened! Have GET render a confirmation page where the user actively submits a **POST** carrying the token (or equivalent confirmation mechanism), and only then consume it.
- If redirecting after verification, redirect to a URL **without the token**; never put the token into `Location`.
- Do not automatically log the user in after verification; require normal sign-in under policy.

In the Spring example in Section 10, no real email is sent: a test mailbox holds the code internally, and a client simulates `POST /account/verify` with the token in JSON. This tests the state machine without placing credentials in URLs.

## 8. Email and SMS/Phone Contacts Are Not Equivalent

| Channel | How control is proven | Limitations |
| --- | --- | --- |
| Email | Random token via email confirmed by recipient | Shared mailboxes, forwarding, compromise, recycled addresses |
| SMS | Short OTP via SMS entered by user | SIM swap, number porting, SS7, SMS forwarding, delivery cost |
| Phone call | Voice/IVR code | Call forwarding risks, social engineering |
| Authenticator/strong methods | Passkey, TOTP, organization device | Suitable for authentication/MFA, does not necessarily prove email ownership |

If using **numeric OTPs** (typically lower entropy than a 256-bit token), enforce tighter rate limits on guesses and sends, shorter validity windows, per-challenge attempt caps, and stronger anti-abuse controls. Never store raw codes or expose them in logs. Controlling a phone number at one point in time does not prove permanent ownership; SIM swaps or number reclamation can change the recipient.

**Do not collapse** `email_verified` and `phone_verified` into a single “verified” flag if the product requires channel-specific policies. Each channel should track its own verified timestamp and trust level, especially in systems with multiple recovery channels.

## 9. How Does Spring Security Actually Block Pending Accounts from Logging In?

Spring Security uses `UserDetailsService` to load the user, `PasswordEncoder` to verify the password, and `DaoAuthenticationProvider` in the username/password authentication flow. `UserDetails.isEnabled()` indicates whether an account is permitted to authenticate.

Example of a `UserDetailsService` reading status from a repository:

~~~java
// Illustrative configuration snippet in Spring Security Servlet.
@Bean
UserDetailsService userDetailsService(AccountRepository accounts) {
    return username -> {
        Account account = accounts.findByEmail(username)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Bad credentials"));

        return User.withUsername(account.getEmail())
                .password(account.getPasswordHash())
                .authorities("ROLE_USER")
                .disabled(account.getStatus() != AccountStatus.ACTIVE)
                .build();
    };
}
~~~

This is a **code snippet**, not a standalone class. It illustrates `disabled(...)` as the inverse of `isEnabled()`. When an account is not ACTIVE, it cannot successfully authenticate through providers that check this status, even if the password matches.

**Common pitfalls:**
- `requestMatchers("/account/register").permitAll()` only permits access to the **registration endpoint**; it does **not** grant authorities or turn an account `ACTIVE`.
- `permitAll()` on the verification endpoint allows unauthenticated users to submit a token, but the service itself must validate the token properly; never allow a JSON request to set `status` directly.
- `.disabled(true)` protects login flows that check `UserDetails`. If the system also supports passkeys, OAuth2/OIDC, SAML, or custom authentication providers, the ACTIVE account policy must be enforced consistently **after identity linking** across every mechanism, not just password login.
- `AccountStatus.ACTIVE` does not imply `ROLE_ADMIN`. Authorization still checks roles, tenant, and ownership.
- Sessions created **before an account was suspended** may remain valid unless you have session/cache/refresh revocation policies; checking status at login time alone is not enough for immediate deactivation.

## 10. Runnable Spring Boot 3.3.x Project: Registration, Verification, and Login Gating

This example is a **self-contained lab** using Java 17, Spring Boot 3.3.12, Spring Security 6.3.x, and an in-memory account store. To verify email flow **without emailing real people or logging tokens**, the example includes `DemoMailbox`, called directly only from Java/JUnit tests to read the simulated token. **Never deploy `DemoMailbox` or the `Map` store to production.**

Key behavior: `POST /account/register` creates `PENDING_VERIFICATION`; the token has a SHA-256 digest and expiry; `POST /account/verify` activates exactly once; `GET /account/me` succeeds only when the account is active and the HTTP Basic password is valid. In production, replace HTTP Basic and the demo store with appropriate authentication flows and a real database.

### 10.1. Files

~~~text
account-activation-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/lifecycle/
    │   │   ├── LifecycleApplication.java
    │   │   ├── AccountService.java
    │   │   ├── DemoMailbox.java
    │   │   ├── LifecycleController.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/demo/lifecycle/AccountActivationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-activation-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
spring:
  application:
    name: account-activation-lab
~~~

`src/main/java/demo/lifecycle/LifecycleApplication.java`:

~~~java
package demo.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
~~~

### 10.2. DemoMailbox: Test-Only, No REST Endpoint

`src/main/java/demo/lifecycle/DemoMailbox.java`:

~~~java
package demo.lifecycle;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class DemoMailbox {
    private final ConcurrentHashMap<String, String> latest =
            new ConcurrentHashMap<>();

    // Simulates delivering the token to the mail system, without logging to console.
    public void deliver(String normalizedEmail, String rawToken) {
        latest.put(normalizedEmail, rawToken);
    }

    // Test code in the JVM uses this method; do not expose over HTTP.
    public String readForTest(String normalizedEmail) {
        return latest.get(normalizedEmail);
    }
}
~~~

**Do not use in production:** this mailbox keeps raw tokens in memory and does not actually send email. In production, replace it with a controlled email delivery interface, transactional outbox, encryption/retention for delivery payloads, and a sender domain authenticated with SPF/DKIM/DMARC per policy.

### 10.3. AccountService: Random Token, Digest, Status

`src/main/java/demo/lifecycle/AccountService.java`:

~~~java
package demo.lifecycle;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AccountService {
    public enum Status { PENDING_VERIFICATION, ACTIVE, SUSPENDED }

    public record Account(
            String email,
            String encodedPassword,
            Status status,
            Instant verifiedAt) {}

    private record Challenge(String email, Instant expiresAt) {}

    private final Map<String, Account> accounts = new ConcurrentHashMap<>();
    private final Map<String, Challenge> pending = new ConcurrentHashMap<>();
    private final SecureRandom secureRandom = new SecureRandom();
    private final PasswordEncoder encoder;
    private final DemoMailbox mailbox;

    public AccountService(PasswordEncoder encoder, DemoMailbox mailbox) {
        this.encoder = encoder;
        this.mailbox = mailbox;
    }

    // Email policy used only in this lab, not globally applicable
    // to all email providers: the local part may be case-sensitive.
    static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    public synchronized void register(String rawEmail, String password) {
        String email = normalize(rawEmail);

        // Do not return "already exists" to the client.
        if (accounts.containsKey(email)) {
            return;
        }

        String encoded = encoder.encode(password);
        accounts.put(email, new Account(
                email, encoded, Status.PENDING_VERIFICATION, null));

        byte[] secret = new byte[32];
        secureRandom.nextBytes(secret);
        String rawToken = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);
        String digest = sha256Hex(rawToken);
        pending.put(digest, new Challenge(
                email, Instant.now().plus(Duration.ofMinutes(20))));

        // Lab only. Production uses outbox/sender after DB commit.
        mailbox.deliver(email, rawToken);
    }

    public synchronized boolean verify(String rawToken) {
        if (rawToken == null || rawToken.isBlank()
                || rawToken.length() > 128) {
            return false;
        }

        String digest = sha256Hex(rawToken);
        Challenge challenge = pending.get(digest);
        if (challenge == null) {
            return false;
        }

        // expiresAt == now is also considered expired.
        if (!Instant.now().isBefore(challenge.expiresAt())) {
            pending.remove(digest);
            return false;
        }

        Account account = accounts.get(challenge.email());
        if (account == null
                || account.status() != Status.PENDING_VERIFICATION) {
            return false;
        }

        pending.remove(digest); // consume only once in the lab JVM
        accounts.put(account.email(), new Account(
                account.email(), account.encodedPassword(),
                Status.ACTIVE, Instant.now()));
        return true;
    }

    public Account findByEmail(String rawEmail) {
        if (rawEmail == null) {
            return null;
        }
        return accounts.get(normalize(rawEmail));
    }

    private static String sha256Hex(String input) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException impossibleOnJava17) {
            throw new IllegalStateException(impossibleOnJava17);
        }
    }
}
~~~

**Code analysis:**
1. A new account starts as `PENDING_VERIFICATION`; there is no public method allowing the client to write `ACTIVE`.
2. A 32-byte secret from `SecureRandom` is Base64URL-encoded, and its token digest is stored in `pending`; the raw token goes only to the test mailbox.
3. `verify` checks existence, expiry, and status, and consumes the digest before transitioning the account to ACTIVE. With `synchronized` in **a single JVM**, concurrent verification attempts serialize so a token cannot be reused.
4. A `SUSPENDED` account cannot be unlocked by an old registration token, because transitions are allowed only from `PENDING_VERIFICATION`.
5. `findByEmail` only supplies data for `UserDetailsService`; turning it into a Spring Security `Authentication` happens in the filter chain.
6. **The lab omits several production requirements**: Map state is lost on restart, `synchronized` is unsafe across multiple nodes, there is no resend flow, `purpose` and `contactSnapshot` are not yet modeled on the record, and there is no mail provider, DB transaction, anti-enumeration timing equalization, rate limiting/audit, or session revocation mechanism. Sections 4–6 and Section 13 explain what to add; do not use this service directly in production.

**Email normalization:** calling `toLowerCase(Locale.ROOT)` across the entire email is a simplified policy for `example.test` addresses. Before production deployment, standardize how domain/local parts, IDN/Unicode, and account uniqueness are canonicalized to prevent identity confusion.

### 10.4. SecurityConfig: PENDING Cannot Authenticate

`src/main/java/demo/lifecycle/SecurityConfig.java`:

~~~java
package demo.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(AccountService accounts) {
        return username -> {
            AccountService.Account acc = accounts.findByEmail(username);
            if (acc == null) {
                throw new UsernameNotFoundException("Bad credentials");
            }

            return User.withUsername(acc.email())
                    .password(acc.encodedPassword())
                    .authorities("ROLE_USER")
                    .disabled(acc.status() != AccountService.Status.ACTIVE)
                    .build();
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .csrf(csrf -> csrf.ignoringRequestMatchers(
                        "/account/register", "/account/verify"))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/account/register",
                                "/account/verify").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Key security points:**
- `.disabled(true)` makes `UserDetails.isEnabled()` return false; Spring Security's `DaoAuthenticationProvider` will not authenticate a PENDING account via HTTP Basic even if the password is correct.
- Both registration and verification endpoints are `permitAll` because the user cannot log in yet, but authority to change status **resides solely in `AccountService.verify`**.
- The CSRF configuration here **exempts only the two public POST endpoints of this lab**; other browser POSTs still retain default CSRF protection. Production must evaluate session cookies, abuse rate limiting, and CSRF across the entire flow; never disable CSRF globally just for a verification token.
- `httpBasic()` is used here solely to keep MockMvc authentication simple. For real browsers, prefer form login/sessions and appropriate CSRF protection; never send plaintext passwords over HTTP—always use HTTPS.

### 10.5. Strongly Typed REST Controller, Never Accepting Status from the Client

`src/main/java/demo/lifecycle/LifecycleController.java`:

~~~java
package demo.lifecycle;

import java.security.Principal;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LifecycleController {
    private final AccountService service;

    public LifecycleController(AccountService service) {
        this.service = service;
    }

    public record RegisterRequest(
            @NotBlank @Email String email,
            @NotBlank @Size(min = 12, max = 100) String password) {}

    public record VerifyRequest(@NotBlank String token) {}

    @PostMapping("/account/register")
    public ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegisterRequest body) {
        service.register(body.email(), body.password());

        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(Map.of("message",
                        "If the request is valid, instructions will be sent."));
    }

    @PostMapping("/account/verify")
    public ResponseEntity<Map<String, String>> verify(
            @Valid @RequestBody VerifyRequest body) {
        if (!service.verify(body.token())) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "INVALID_OR_EXPIRED"));
        }
        // Verification does not create a login session.
        return ResponseEntity.ok(Map.of("status", "VERIFIED"));
    }

    @GetMapping("/account/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

The public controller only accepts `email`, `password`, and `token`. There are no `role`, `verified`, or `status` fields, so a client cannot request activation via mass assignment. Production must add request size limits, abuse controls, safe telemetry, and error handling that does not leak account information.

**Note:** the verify endpoint returns `"INVALID_OR_EXPIRED"` for unusable tokens without revealing which email the token belonged to. A real-world response may link to a resend support page without disclosing extra details.

### 10.6. Integration Test Verifying the Lifecycle and One-Time Token

`src/test/java/demo/lifecycle/AccountActivationTest.java`:

~~~java
package demo.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AccountActivationTest {
    @Autowired MockMvc mvc;
    @Autowired DemoMailbox mailbox;

    @Test
    void pendingCannotLoginAndVerificationActivatesOnce() throws Exception {
        String email = "learner@example.test";
        String password = "lab-password-long-123";

        mvc.perform(post("/account/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"learner@example.test",
                                 "password":"lab-password-long-123"}
                                """))
                .andExpect(status().isAccepted());

        mvc.perform(get("/account/me").with(httpBasic(email, password)))
                .andExpect(status().isUnauthorized());

        String rawToken = mailbox.readForTest(email);
        org.junit.jupiter.api.Assertions.assertNotNull(rawToken);

        mvc.perform(post("/account/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"" + rawToken + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("VERIFIED"));

        mvc.perform(get("/account/me").with(httpBasic(email, password)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value(email));

        mvc.perform(post("/account/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"" + rawToken + "\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongTokenDoesNotActivate() throws Exception {
        mvc.perform(post("/account/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"reader@example.test",
                                 "password":"reader-password-long-123"}
                                """))
                .andExpect(status().isAccepted());

        mvc.perform(post("/account/verify")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"token\":\"invalid-token\"}"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/account/me")
                        .with(httpBasic("reader@example.test",
                                "reader-password-long-123")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void duplicateRegistrationHasSamePublicResponse() throws Exception {
        String body = """
                {"email":"repeat@example.test",
                 "password":"another-password-123"}
                """;

        for (int attempt = 0; attempt < 2; attempt++) {
            mvc.perform(post("/account/register")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body))
                    .andExpect(status().isAccepted())
                    .andExpect(jsonPath("$.message")
                            .value("If the request is valid, instructions will be sent."));
        }
    }
}
~~~

Run the tests using an installed Gradle or a generated wrapper:

~~~bash
gradle test
# If the project has a Gradle Wrapper:
./gradlew test
# Windows:
# gradlew.bat test
~~~

Expected result: **3 tests pass**:
- A PENDING account is blocked even with the right password; the right token activates it; login then succeeds; the old token cannot be used a second time.
- An invalid token does not activate.
- Registering an existing email still returns the same public HTTP status and message.

Exact Gradle stdout is not guaranteed verbatim because console formatting, caching, and versions may vary; the assertions are the actual proof. This is a **single-JVM in-memory lab** with no real email delivery. To test a real workflow with a mail provider, replace `DemoMailbox` with a test integration and never expose `readForTest` in deployed environments.

## 11. Testing Token Expiry/Resend, Concurrency, and Abuse

The tests in Section 10 cover core behavior. Before production, also test:

| Case | Condition | Expected outcome |
| --- | --- | --- |
| Expired token | `now >= expiresAt` | Does not activate; allows resend per policy |
| Invalid token | Digest not in DB | Does not activate; does not leak account |
| Reused token | `consumed_at` already set | Does not activate a second time |
| Another account's token | Challenge bound to A, client tries to bind to B | Does not transition B to ACTIVE |
| Account already `SUSPENDED` | Submit old registration token | Does not reopen account |
| Email changed | Token sent to old email | Does not verify new email |
| Two concurrent verifications | Same raw token | Only **one** request wins; atomic transition/consume |
| Two concurrent registrations | Same normalized contact | Unique constraint creates at most one account |
| Repeated resends | Many requests to same email/IP | Rate limit and cooldown; no mail flooding |
| Token from another flow | Password reset token submitted to email verify | Rejected by `purpose` |
| Right password, PENDING account | HTTP login | Rejected because `isEnabled() == false` |
| Right password, ACTIVE account | HTTP login | Can authenticate; still subject to business authorization |
| OTP brute-force | Repeated code guesses | Throttling/lockout/abuse mitigation |
| Email spoof/mismatch | Mail link uses foreign host or different contact | Not accepted or granted access |
| GET link by scanner | Bot opens email before user | Does not consume token and does not auto-login |
| Timezone/clock skew | Exactly on expiration boundary | Consistent policy; use UTC/`Clock` injection in tests |
| Restart/node failover | Distributed challenge/session | Does not lose tokens or allow double-use |

**Clock testing:** replace `Instant.now()` with an injected `Clock` in the real service to test exact expiry boundaries without `Thread.sleep()`. Tests should not depend on arbitrary wait times or execution order.

**Race testing:** use a real database or multi-instance integration environment to verify row locks and conditional updates. `synchronized` in the demo only protects the current process; it has no effect across multiple pods.

**User enumeration testing:** do not compare only the response message. Also check HTTP status codes, response bodies, processing times, quotas, resend behavior, and side channels; noticeable differences can reveal whether an account exists.

## 12. Why Must an Account Be Activated Before Login?

A common mistake is creating new accounts with `enabled=true` and sending verification email afterward. Email verification then degrades into a mere “reminder”; the account can already log in or call APIs before verification.

In Spring Security, login handlers can read from `UserDetailsService`; `DaoAuthenticationProvider` checks the password and account flags such as enabled/locked/expired. **Read status from a trusted data source** so `isEnabled()` accurately reflects `ACTIVE`. If using custom JWT authentication:
- Do not merely verify the token signature and ignore account status when policy requires fast revocation.
- Consider short token TTLs, session revocation, token versions, or introspection; authorize against current account state.
- When an account becomes active, do not automatically grant elevated roles just because its email was verified.
- When an account is suspended, revoke access according to business requirements, including previously issued sessions/tokens.

Distinctions:
- **Authentication**: valid credentials and an account eligible for use.
- **Authorization**: what the account is allowed to do and on which data.
- **Contact verification**: whether control over a contact channel was proven at a point in time.
- **Activation**: a business state transition, not automatic Authentication.

With SSO/OIDC/SAML, the `email_verified` claim from an IdP may be used **only when** the issuer and claims have been verified and the trust contract and user linking are correct. Never accept a frontend-submitted `email_verified=true` field as independent proof.

## 13. Verification Resend, Contact Changes, and Reactivation

### 13.1. Resend

The `POST /account/verification/resend` endpoint should:
- Return the same generic message whether the email exists, does not exist, or is already active, without revealing account state.
- Enforce cooldowns per account/contact/IP, limits within a time window, and anti-bot checks when needed.
- If the account is PENDING, generate a **new token** and invalidate previous tokens; send only to the contact awaiting verification.
- Never reset passwords/roles/status or create a second account on resend.
- Never include the token in responses or logs; use a mail provider with retries and separate delivery status tracking.
- Monitor email bounces and addresses that could be abused to spam others.

If a user did not receive the email, instruct them to check spam/quarantine, verify the entered address, and request a resend after the cooldown. Do not publicly reveal “that address already has an account.”

### 13.2. Changing Email While the Account Is ACTIVE

Changing an email address is a **change to a recovery/identity channel** and carries account takeover risk. A common workflow:
1. Require the authenticated user to **reauthenticate** for sensitive changes.
2. Store `pending_new_email` separately; do not overwrite the current verified email yet.
3. Send an alert to the old email and a verification code to the new email; sensitive systems may require confirmation from both.
4. Verify a token with purpose `VERIFY_NEW_EMAIL`, bound to the account and pending email, single-use and time-limited.
5. Inside a transaction, promote the new email to verified, update uniqueness, revoke old challenges, and write an audit entry.
6. Send a confirmation notice and provide a way to revoke/report unauthorized changes.

**Never** accept a `VERIFY_SIGNUP_EMAIL` token sent to the old email to activate a new email. Contact snapshots and purpose binding prevent races and cross-flow confusion.

### 13.3. Re-enabling a Suspended Account

An account suspended due to a security event or policy violation **must not automatically return to ACTIVE** via an old email verification link. It requires a dedicated policy: review, approved self-service recovery, MFA/re-authentication, credential reset, staff approval, and session revocation if needed.

If someone is deleted and later registers again with the old email, the system must decide whether that represents the same identity or a brand-new identity. Email addresses can be recycled; **never automatically restore old account data based solely on ability to read email**.

## 14. Common Security Pitfalls

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Account created `ACTIVE` before verification | Someone registering with another's email can log in | Start `PENDING`, consider activation only after verification |
| Predictable token like `userId+timestamp` | Attacker guesses or bypasses verification | 256-bit CSPRNG, digest, expiry/single-use |
| Storing raw tokens in DB/logs | Token leakage from DB or observability | Store digest only; protect mail payload/outbox |
| GET link auto-activates | Email scanners/prefetchers consume the token | GET renders page only; POST confirms |
| Token not bound to purpose/account/email | Cross-flow misuse or account takeover | Purpose + contact snapshot + state checks |
| Resend leaves all old tokens valid | Larger attack surface and race conditions | Invalidate prior tokens according to policy |
| `SELECT` then `UPDATE` without transaction/lock | Verification race, double-use | Atomic update, row lock, unique constraint |
| Public “email already registered” response | User enumeration | Generic response, rate limiting, timing controls |
| Arbitrary email normalization | Accidental account merging, identity confusion | Explicit canonicalization policy and consistent uniqueness |
| Building links from request `Host` header | Host header poisoning redirects links to attacker domain | Fixed public URL from trusted configuration |
| URL token sent to analytics/referrer | Bearer verifier exposure | HTTPS, no-referrer/no-store, no third-party scripts; clean redirect |
| Auto-creating an ADMIN session after verify | Privilege escalation | Verification is not login and does not grant roles |
| Checking `enabled` only on password login | SSO/token flows bypass suspension | Central status policy across all auth flows |
| Unbounded email sending | Email bombing/spam/cost | Rate limits, cooldowns, abuse monitoring |
| Ignoring mail delivery failures | Users get stuck in PENDING | Outbox, retries, resend, and help paths |
| Trusting frontend-supplied `email_verified` | Verification bypass | Accept proof only from server or verified IdP |
| Unthrottled 6-digit SMS activation | OTP brute-force | Throttling, strict attempt/TTL caps, hashed OTP |
| Not revoking sessions after disable | Locked/disabled account retains access | Session/token lifecycle and revocation within SLA |

## 15. Observability, Data Security, and Operations

**Recommended logs:** request ID/correlation ID, event type (`REGISTER_REQUESTED`, `VERIFICATION_SENT`, `VERIFICATION_FAILED`, `ACTIVATED`, `SUSPENDED`), authorized actor/tenant, categorized internal failure reason, delivery queue status, and UTC timestamp.

**Do not log:** passwords, raw verification tokens, full verification URLs, OTPs, session cookies, or full email/contact addresses without a valid basis. You may mask or HMAC identifiers for abuse analysis within allowed retention windows; never put secrets into analytics or traces.

**Useful metrics:** registration count, verification rate within TTL, undeliverable mail count, daily resends, expired/invalid token rate, time from registration to activation, suspected abuse attempts, and mail provider incidents. Protect telemetry data as it can reveal account state.

**Retention policy:** unverified PENDING accounts after a defined period should be cleaned up or processed per legal/retention policy; do not retain indefinitely. Expired or consumed verification tokens should be purged per retention rules. On account closure, handle data, sessions, and contact emails per legal requirements.

**Deploying behind a proxy:** always use a public HTTPS URL, trust `Forwarded`/`X-Forwarded-*` headers only from controlled reverse proxies, and never let attackers inject arbitrary hosts into verification links. Restrict URL logging and apply appropriate CSP/cookie policies to activation pages.

## 16. Exercises and Answers

**Q1.** Registration succeeds, but the recipient has not verified the email yet. What should `UserDetails.isEnabled()` return?  
**False** if policy requires verification before activation. Never allow login to succeed merely because the password matches.

**Q2.** A verification link has the right token, but it expires at the exact current timestamp. Should it be accepted?  
**No.** Under the condition `now < expiresAt`, when `now == expiresAt` the token is expired.

**Q3.** A user receives a verification URL via email, and anti-spam software opens the URL first. What should be done to avoid automatic consumption?  
**Do not activate on GET alone**; serve a confirmation page and require a POST when the user actively completes the action.

**Q4.** The account is already ACTIVE and the old token is submitted again. Should a session be created or `verifiedAt` updated?  
**No.** A used token is invalid; it grants no automatic sign-in capability.

**Q5.** A user changes their email in their profile without verifying the new email. Can the old `emailVerifiedAt` be kept as-is for the new address?  
**It must not be treated as verification of the new email.** Use a pending contact, a new challenge, and appropriate reauthentication/notification steps.

**Q6.** The server stores only `SHA-256(token)`, and also stores user passwords with plain SHA-256. Is that secure?  
**No.** High-entropy random tokens and human-chosen passwords have very different entropy. Passwords require adaptive password hashing via `PasswordEncoder`.

**Q7.** Someone registers with another person's email address; can they guess the verification URL?  
With a long CSPRNG token, guessing probability is negligible; you still need rate limiting and zero token leakage. However, you **must handle** mailbox compromise, forwarding, or address recycling; email verification does not prove legal identity.

**Q8.** An account was suspended for fraud, and the user still has an old verification link. Should it unlock the account?  
**No.** The `SUSPENDED → ACTIVE` transition must go through a dedicated policy, not initial verification.

### Release Checklist

- [ ] New accounts start in a pending state; the server never trusts status or roles from the client.
- [ ] Passwords are stored using an adaptive `PasswordEncoder`.
- [ ] Email canonicalization and unique constraints are designed consistently.
- [ ] Tokens come from a CSPRNG with sufficient entropy, are bound to purpose/account/contact, have finite TTL, are single-use, and are stored as digests.
- [ ] Token consumption + account activation are atomic in the DB and safe under concurrent requests.
- [ ] Delivery uses an outbox/retry flow; raw tokens are never leaked in logs, APIs, or analytics.
- [ ] Links use HTTPS, a trusted public domain, and are not consumed by GET scanners.
- [ ] Registration/resend endpoints have generic responses, rate limits, cooldowns, and anti-enumeration controls.
- [ ] `UserDetails.isEnabled()` or a shared policy blocks all authentication methods for inactive accounts.
- [ ] Email change, reactivation, account recovery, and password reset are separate workflows.
- [ ] Tests cover negative cases, expiry, replay, concurrent verification, wrong account/contact, and disabled accounts.
- [ ] Sessions/tokens issued prior to disabling are handled within SLA.
- [ ] PENDING accounts, expired tokens, and PII have clear retention policies.

## 17. References

- [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html): canonicalization, email ownership, single-use tokens, anti-enumeration, and email change flows.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): user identifiers, password/authentication, anti-enumeration.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): principles for random tokens, TTL, single use, and neutral responses; apply similar principles, but **never share tokens between reset and verification**.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): DelegatingPasswordEncoder and adaptive hashing.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): UserDetailsService + PasswordEncoder during authentication.
- [Spring Security 6.5 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): enabled, account non-locked/expired, and credential checks.
- [Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/): configuring and testing Spring Boot 3.3.x projects.

**Takeaway:** Registration creates an **account request**, contact verification confirms **access to a contact channel**, and activation is a **business state decision**. Allow sign-in only when the account is eligible, keep verification tokens random, time-limited, and single-use, perform state transitions atomically, and verify with negative tests.