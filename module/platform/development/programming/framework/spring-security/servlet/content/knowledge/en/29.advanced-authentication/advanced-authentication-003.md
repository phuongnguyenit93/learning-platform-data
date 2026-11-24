# One-Time Token Lifecycle: Issuance, Delivery, Expiration, and Replay Protection in Spring Security Servlet

## 1. The Problem: Why Is a Token That “Expires After 10 Minutes” Still Not Enough?

A Spring Boot application provides **forgot password**, **email verification**, **one-time login link (magic link)**, or **sensitive action confirmation**. The system issues a token to the user, delivers it over a designated channel, and lets the recipient use that token to complete an action.

A common mistake is checking only `expiresAt > now`. If the token remains valid for 10 minutes and the server does not record usage, **anyone holding a copy of the token can keep calling it for 10 minutes**. Time-to-live (**TTL**) and single-use (**one-time use**) are two independent properties.

In Spring Security Servlet, the full lifecycle must be designed:

1. **Issuance:** generate a token with sufficient entropy using a cryptographic random generator, bound to one user, one purpose, one expiration, and required context.
2. **Storage:** store only a non-recoverable representation of the original token (digest/HMAC) along with metadata; limit the number of active tokens and manage revocation.
3. **Delivery:** transport the token through an out-of-band channel or controlled UI; do not place it in logs, analytics, or unintended public responses.
4. **Verification and consumption:** verify that the token exists, matches the purpose, matches the user/context when required, is unexpired, and is unconsumed; **mark it as used with an atomic operation** so only one request wins.
5. **Expiration, revocation, cleanup:** reject expired tokens, invalidate tokens after use or after security events, and purge expired records per retention policy.
6. **Observability and testing:** verify replay, double-click, race conditions, forged tokens, expiration boundaries, delivery failures, and service failures.

This lesson uses **password reset** as the primary example because it clearly illustrates the difference between proving control of a contact channel and updating account state. The principles also apply to email verification, invitations, magic links, and step-up challenges, though the **post-consumption action** and authorization policy of each type must be designed separately.

## 2. Token Types That Are Easily Confused

| Type | Purpose | One-Time or Reusable? | Security Requirements |
| --- | --- | --- | --- |
| **Password reset token** | Confirms the recipient is allowed to reset the associated account’s password | **One-time**, short-lived | Correct purpose, expiration and atomic consumption, anti-guessing |
| **Email verification token** | Verifies access to an email address | Typically **one-time** | Bound to user/email version; invalidated when email changes |
| **Magic-link login token** | Logs in via a delivered link channel | **One-time** | Verify, consume, then create a secure session; prevent URL leaks |
| **6-digit one-time password (OTP)** | Short-lived challenge, usable for MFA if properly designed | One-time per challenge/time step | Attempt limits, rate limiting, anti-replay; low entropy |
| **CSRF token** | Confirms state-changing requests within a browser session context | **Not one-time by default** | Bound to Spring Security session/handler |
| **OAuth2 access token** | Calls resource APIs within granted scopes | Usually reusable until expiry/revocation | Verify signature/issuer/audience/scope or introspection |
| **JWT containing `exp` and `jti`** | Self-describing token with expiration and ID | **Not inherently one-time** | Single-use requires server state tracking `jti` for consumption |

**Do not use an access token or a JWT that only has `exp` as a one-time token without server-side state.** Validating the signature and `exp` only states that the token is valid at that point in time; it does not prove the token has never been used. For a one-time JWT, you still must store/check `jti` (or an equivalent mechanism) and apply an atomic update.

MFA TOTP differs from a password reset link: TOTP relies on a short code changing per time step, so anti-replay, clock windows, and attempt limits require separate design. Do not replace an MFA system by emailing a password-reset token and assuming email is a strong authentication factor.

## 3. State Machine of a One-Time Token

A token can have the following logical states:

~~~text
                     request issue
                          |
                          v
                       ISSUED
                          |
               +----------+----------+
               |                     |
               v                     v
            DELIVERED           DELIVERY_FAILED
               |                 (retry rules needed)
               |
          Presented for use
               |
         Validate atomically
               |
       +-------+-------+----------------+
       |               |                |
       v               v                v
    CONSUMED         EXPIRED          REVOKED
       |               |                |
       +---------------+----------------+
                       |
                 REJECT all reuse
~~~

`DELIVERED` is a separate transport status; it does **not** mean the token has been used by the user. With email/SMS, successfully handing off to a provider only means the send request was accepted, not that the recipient read it. You can design the data model with a separate `deliveryStatus` instead of stuffing everything into one status column.

Security **invariants** of the verification step:

- The token must not be guessable from the account, time, sequence ID, email, or `Math.random()`.
- The token is valid only for the exact **purpose** and account recorded at issuance.
- `now < expiresAt`; **at exactly `expiresAt`, it is expired**.
- `consumedAt IS NULL` and `revokedAt IS NULL` are mandatory conditions for use.
- For the same token, **at most one request may change state**.
- When a token fails or expires, responses and logs must not expose the raw token.

Multiple tokens may be issued for one user if the design allows it. If policy permits **only one active token per user + purpose**, a new issuance must revoke the prior one **within a transaction** or use a generation/version to invalidate older tokens. Never assume a `ConcurrentHashMap` on one server represents the state across all instances in a distributed system.

## 4. Issuance: SecureRandom, Entropy, and Token Format

For **long link tokens**, a straightforward choice in Java 17 is 32 bytes (256 bits) from `java.security.SecureRandom`, encoded in **URL-safe Base64** without padding. 32 bytes typically produce a 43-character string containing only letters, digits, `-`, and `_`, suitable for URLs or forms.

~~~java
import java.security.SecureRandom;
import java.util.Base64;

SecureRandom random = new SecureRandom();
byte[] bytes = new byte[32];
random.nextBytes(bytes);

String rawToken = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);

// Do not log or store rawToken long-term.
~~~

This is a **Java snippet** for use in a service, not a standalone file. A specific output cannot be predicted, so there is no fixed stdout the documentation can list. Do not generate tokens with `UUID.randomUUID().toString()` when conventions require 256-bit entropy, and never use `System.currentTimeMillis()`, usernames, or predictable values.

**Hash before storing:** when a token has 256-bit high entropy, storing `SHA-256(rawToken)` instead of the raw token is a useful practice. If the database is leaked, an attacker does not obtain raw tokens to use directly. Example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

static String sha256(String rawToken) {
    try {
        byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(rawToken.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(hash);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException("SHA-256 unavailable", e);
    }
}
~~~

Use `token_digest` as the lookup key; compare against the same digest computed by the application from input. For **6-digit OTPs**, SHA-256 is insufficient against offline brute force if the database leaks because the search space is too small; a different design is needed (e.g., HMAC with a separately protected secret key, attempt counters, rate limiting, and challenge locking). Do not use slow password hashes like BCrypt for 256-bit tokens purely out of habit; the goals and entropy differ.

## 5. Binding Tokens to Purpose and Target Entity

A token should be managed using a logical record:

~~~text
one_time_token
    id              UUID or internal DB key
    token_digest    SHA-256 of raw token, UNIQUE
    account_id      Account bound at issuance time
    purpose         PASSWORD_RESET | VERIFY_EMAIL | INVITE | ...
    created_at      Issuance timestamp
    expires_at      Expiration deadline (UTC/Instant)
    consumed_at     null or timestamp when used
    revoked_at      null or timestamp when revoked
    delivery_status Separate delivery status if needed
~~~

When completing a password reset, **do not accept `accountId` or `email` from the client and use the token to change that account’s password**. You must look up the **`accountId` pre-bound in the token record**. If the backend receives `token=aliceToken` and `email=bob@example.org`, the operation must not be allowed to change Bob’s password.

Similarly, an email verification token must bind to the **specific email address being verified** (and email version if changeable), rather than binding only `userId` and accepting a different email. A workspace invitation token must bind the workspace, approved role, and invitee; a transfer confirmation token must bind the approved transaction/amount or require a stronger authentication step.

**Tokens must be restricted in usage scope.** Never share one raw token across email verification, password reset, and login, as doing so creates a purpose-switching privilege escalation path.

## 6. Delivering Tokens: Channel Security and Leak Prevention

Delivery channels may be email, SMS, push notifications, or authenticator apps. Each has distinct reliability and risks. For password reset via email:

1. The user calls the password reset request endpoint. The server **always returns a generic message** such as “If the account exists, instructions will be sent,” never returning `404` for unknown emails and `200` only for real ones.
2. The server generates a token **only for eligible accounts**, stores the digest + TTL, and passes the raw token to the email service over an internal interface.
3. The email contains a link to a **fixed configured HTTPS origin** (never derived from an arbitrary `Host` header), e.g., `https://app.example.org/reset?token=...`.
4. The GET reset page only **renders the form** without consuming the token; completion uses POST. This is critical because email security scanners, link-preview bots, or browser prefetching may open GET links before the user does.
5. Upon completion, the form submits the token + new password over HTTPS. The server verifies and consumes the token **once** before applying the change.

**Minimizing token leakage in URLs:** URL query strings can appear in browser history, access logs, reverse proxy logs, analytics, Referer headers, or screenshots. The landing page should set `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, and avoid loading unnecessary third-party scripts; after extracting the token into the form, `history.replaceState` can strip the query from the address bar. Never place raw tokens into other links’ URLs or send them to analytics. URLs in emails must use a fixed allowed host to prevent **Host Header Poisoning**.

An email channel is not a license to skip other checks. Before allowing a password reset on a high-privilege account, consider MFA/recovery policies, security alerts, and invalidating sessions/cookies/remember-me tokens according to risk. For magic-link login, creating a new session also requires **session fixation protection**, cookie flags, CSRF/session policies, and a proper authentication workflow.

**Never include raw tokens in the response of the request endpoint** in production. The runnable example later uses a dummy `TokenSender` to avoid requiring SMTP; unit tests use a sender that captures the token **only in test memory**. Thus the demo app proves the logic without sending real emails.

## 7. Consumption Must Be Atomic: Preventing Double-Clicks and Race Conditions

An anti-pattern:

~~~java
// WRONG: Two requests can both read "unused" before the update.
TokenRow row = repository.findByDigest(digest);
if (row != null && !row.isUsed() && row.getExpiresAt().isAfter(now)) {
    resetPassword(row.getAccountId(), newPassword);
    repository.markUsed(digest);
}
~~~

Between `findByDigest` and `markUsed`, two parallel requests can both observe the token as unused and both execute the business logic. A mutex in the current JVM is insufficient when **multiple instances** exist.

In a database supporting conditional updates, use **one atomic UPDATE** and check the affected row count. Example with **PostgreSQL** (using bind parameters; `RETURNING` is PostgreSQL syntax):

~~~sql
BEGIN;

UPDATE one_time_token
   SET consumed_at = CURRENT_TIMESTAMP
 WHERE token_digest = :digest
   AND purpose = 'PASSWORD_RESET'
   AND consumed_at IS NULL
   AND revoked_at IS NULL
   AND expires_at > CURRENT_TIMESTAMP
RETURNING account_id;

-- Continue only if UPDATE RETURNING returns exactly 1 account_id.
-- UPDATE this account's password in the same transaction if supported by the system.
-- If no row: roll back or terminate with a generic failure.

COMMIT;
~~~

If two requests use the same digest, only **one request** updates `consumed_at` from NULL to a timestamp. After waiting for the lock, the second request no longer satisfies the condition. For operations that can share a transaction (token and password in the same database), place **consume + change password in one transaction** so you never end up in a “token consumed but password not changed” state due to a mid-flight error. If side effects happen in an external system, use a clearly designed state machine/outbox/idempotency strategy to avoid triggering side effects twice.

In a **single-JVM demo**, atomicity *within the same process* can be achieved with `ConcurrentHashMap.compute(key, ...)`; the full example below uses this to focus on the concept while noting that it must be replaced with a DB transaction in multi-instance deployments.

**Consume before or after the side effect?** There is no universal formula for every side effect; the critical requirement is that both steps share **consistent transactional semantics**. For password reset stored in the same database, a transaction is the natural choice. For sending notification emails or calling downstream services, define idempotency and recovery when failing mid-way.

## 8. Complete Sample: Java 17, Spring Boot 3.3.5, Spring Security Servlet

We build a password reset example consisting of:

- `POST /password-reset/request`: accepts an email and **always returns 202** with a generic message; if the demo account matches, generates a 256-bit token and calls `TokenSender`.
- `POST /password-reset/complete`: accepts a raw token and new password; verifies TTL, purpose, and unused state via atomic consumption; updates the BCrypt password hash; returns **204** on success, **400** on invalid/expired/used token.
- `GET /csrf`: provides a CSRF token so browser clients or HTTP test commands can send it in a header. POST requests **still go through CsrfFilter**, even when the endpoint is `permitAll()`.
- `MemoryTokenStore`: stores **digests**, preventing replay via `ConcurrentHashMap.compute`; **not** for production storage.
- Default `TokenSender` is a **no-op** so the code runs without a mail server and never leaks raw tokens in logs. Tests substitute a capturing sender.

File structure:

~~~text
one-time-reset-demo/
  pom.xml
  src/main/java/example/onetime/OneTimeResetApplication.java
  src/test/java/example/onetime/ResetServiceTests.java
  src/test/java/example/onetime/ResetHttpTests.java
~~~

### 8.1. Maven Dependencies

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>one-time-reset-demo</artifactId>
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
~~~

### 8.2. Application and Token Logic

**src/main/java/example/onetime/OneTimeResetApplication.java:**

~~~java
package example.onetime;

import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OneTimeResetApplication {

    public static void main(String[] args) {
        SpringApplication.run(OneTimeResetApplication.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoAccounts demoAccounts(PasswordEncoder encoder) {
        return new DemoAccounts(encoder);
    }

    @Bean
    MemoryTokenStore memoryTokenStore() {
        return new MemoryTokenStore();
    }

    @Bean
    TokenSender tokenSender() {
        // Demo does not transport tokens externally; unit tests use
        // CapturingSender. Production replaces this with a real mail sender.
        return (email, rawToken) -> { };
    }

    @Bean
    ResetService resetService(
            DemoAccounts accounts,
            MemoryTokenStore tokens,
            TokenSender sender,
            PasswordEncoder encoder,
            Clock clock) {
        return new ResetService(accounts, tokens, sender, encoder, clock);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/csrf", "/password-reset/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class CsrfController {
        @GetMapping("/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                    CsrfToken.class.getName());
            return Map.of(
                    "headerName", token.getHeaderName(),
                    "token", token.getToken());
        }
    }

    @RestController
    @RequestMapping("/password-reset")
    static class ResetController {
        private final ResetService service;

        ResetController(ResetService service) {
            this.service = service;
        }

        record ResetRequest(String email) {}
        record CompleteRequest(String token, String newPassword) {}

        @PostMapping("/request")
        ResponseEntity<Map<String, String>> request(
                @RequestBody ResetRequest input) {

            service.requestReset(input.email());
            return ResponseEntity.accepted().body(Map.of(
                    "message",
                    "If the account exists, instructions will be sent"));
        }

        @PostMapping("/complete")
        ResponseEntity<Void> complete(
                @RequestBody CompleteRequest input) {
            boolean success = service.complete(
                    input.token(), input.newPassword());
            return success
                    ? ResponseEntity.noContent().build()
                    : ResponseEntity.badRequest().build();
        }
    }

    @FunctionalInterface
    interface TokenSender {
        void send(String destination, String rawToken);
    }

    // Mock directory for one account; not suitable for multiple instances.
    static final class DemoAccounts {
        private final Account account;

        DemoAccounts(PasswordEncoder encoder) {
            account = new Account(
                    "account-1",
                    "alice@example.test",
                    new AtomicReference<>(
                            encoder.encode("initial-password-123")));
        }

        Optional<Account> findByEmail(String email) {
            if (email == null || email.length() > 254) {
                return Optional.empty();
            }
            return email.strip().equalsIgnoreCase(account.email())
                    ? Optional.of(account)
                    : Optional.empty();
        }

        void changePassword(String accountId, String newEncodedPassword) {
            if (!account.id().equals(accountId)) {
                throw new IllegalStateException("Account missing");
            }
            account.passwordHash().set(newEncodedPassword);
        }

        boolean passwordMatches(String rawPassword, PasswordEncoder encoder) {
            return encoder.matches(rawPassword, account.passwordHash().get());
        }
    }

    record Account(
            String id,
            String email,
            AtomicReference<String> passwordHash) {}

    record StoredGrant(
            String accountId,
            String purpose,
            Instant expiresAt,
            boolean consumed) {}

    static final class MemoryTokenStore {
        private final ConcurrentHashMap<String, StoredGrant> byDigest =
                new ConcurrentHashMap<>();

        void save(String digest, StoredGrant grant) {
            byDigest.put(digest, grant);
        }

        Optional<String> consume(
                String digest, String requiredPurpose, Instant now) {
            AtomicReference<String> acceptedAccount = new AtomicReference<>();

            // compute() is atomic per key within the same JVM.
            byDigest.compute(digest, (key, grant) -> {
                if (grant == null || grant.consumed()
                        || !requiredPurpose.equals(grant.purpose())
                        || !now.isBefore(grant.expiresAt())) {
                    return grant; // leave unchanged, do not accept
                }
                acceptedAccount.set(grant.accountId());
                return new StoredGrant(
                        grant.accountId(),
                        grant.purpose(),
                        grant.expiresAt(),
                        true);
            });

            return Optional.ofNullable(acceptedAccount.get());
        }

        void removeExpired(Instant now) {
            byDigest.entrySet().removeIf(entry ->
                    !now.isBefore(entry.getValue().expiresAt()));
        }
    }

    static final class ResetService {
        static final Duration TTL = Duration.ofMinutes(10);
        private static final String PURPOSE = "PASSWORD_RESET";

        private final DemoAccounts accounts;
        private final MemoryTokenStore tokens;
        private final TokenSender sender;
        private final PasswordEncoder encoder;
        private final Clock clock;
        private final SecureRandom secureRandom = new SecureRandom();

        ResetService(
                DemoAccounts accounts,
                MemoryTokenStore tokens,
                TokenSender sender,
                PasswordEncoder encoder,
                Clock clock) {
            this.accounts = accounts;
            this.tokens = tokens;
            this.sender = sender;
            this.encoder = encoder;
            this.clock = clock;
        }

        void requestReset(String email) {
            Optional<Account> account = accounts.findByEmail(email);
            if (account.isEmpty()) {
                return; // Controller still returns generic response
            }

            byte[] bytes = new byte[32];
            secureRandom.nextBytes(bytes);
            String rawToken = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(bytes);

            String digest = sha256(rawToken);
            tokens.save(digest, new StoredGrant(
                    account.get().id(),
                    PURPOSE,
                    clock.instant().plus(TTL),
                    false));

            // Only TokenSender receives rawToken.
            sender.send(account.get().email(), rawToken);
        }

        boolean complete(String rawToken, String newPassword) {
            if (rawToken == null
                    || !rawToken.matches("[A-Za-z0-9_-]{43}")
                    || newPassword == null
                    || newPassword.length() < 12
                    || newPassword.length() > 128) {
                return false;
            }

            String digest = sha256(rawToken);

            Optional<String> accountId = tokens.consume(
                    digest, PURPOSE, clock.instant());
            if (accountId.isEmpty()) {
                return false;
            }

            // If this step fails, the demo has still consumed the token:
            // request a new token. Production should place consume and
            // password change in the same DB transaction.
            accounts.changePassword(
                    accountId.get(), encoder.encode(newPassword));

            return true;
        }

        private static String sha256(String rawToken) {
            try {
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(rawToken.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException(
                        "SHA-256 unavailable", e);
            }
        }
    }
}
~~~

**Reading the code in context:**

- `SecureRandom` generates 32 bytes per token; Base64URL produces 43 characters. Only the **digest** is stored in `MemoryTokenStore`.
- `StoredGrant` binds `accountId`, `purpose`, `expiresAt`, and `consumed`; the client cannot change the target account by sending a different email.
- `MemoryTokenStore.consume` checks the condition and flips `consumed` inside one `ConcurrentHashMap.compute`, so **within one JVM** only one request can use the token. `removeExpired` illustrates cleanup; a scheduled job or TTL persistence is needed in real deployments.
- `Clock` is injected so expiration boundary tests do not rely on `Thread.sleep`.
- `PasswordEncoder` uses BCrypt; plaintext passwords are never stored. The single demo account has an initial password solely to illustrate testing.
- Default `TokenSender` is a no-op: the server runs without **sending emails**. To test the full cycle, unit tests swap in a fake sender recording the raw token in test RAM. Production must replace it with SMTP/email API using secrets, queues/outbox, and delivery observability.
- `permitAll()` only skips the login requirement for reset endpoints. **CSRF still applies to POSTs** due to `csrf(Customizer.withDefaults())`; `spring-security-test` allows testing with `with(csrf())`.

**Intentional demo limitations:** the map, password state, and tokens live only in memory, so restarts lose data and multiple instances are not synchronized. There is no rate limiter, real email, persistent transaction, or session revocation after password reset. This is a **teaching sample for the mechanism**, not a production-ready password reset system.

### 8.3. Running HTTP and Observing CSRF

In the project directory:

~~~bash
mvn spring-boot:run
~~~

With `/csrf`, a browser-simulating client can obtain a CSRF token and session cookie. The commands below use Bash/Git Bash, `curl`, and Python 3:

~~~bash
# Fetch CSRF token bound to the cookie jar.
CSRF=$(curl -fsS -c demo-cookies.txt http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# POST without CSRF token: Spring Security typically returns 403.
curl -i -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.test"}' \
  http://localhost:8080/password-reset/request

# POST with cookie and CSRF token: returns 202 with generic message.
curl -i -b demo-cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.test"}' \
  http://localhost:8080/password-reset/request
~~~

A request with a non-existent email also produces the **same response body/status as above** when valid JSON and valid CSRF are sent. Because the application’s `TokenSender` is a no-op, you cannot retrieve the raw token from the demo HTTP response to call `/complete` manually; run the unit tests below. Never add a public `GET /last-token` endpoint for testing convenience, as it would expose every active token.

Returning a generic 202 is one step against **account enumeration**, but production also needs timing-difference analysis, rate limiting, delivery policies, and behavior for disabled accounts. When a user is already authenticated, re-authentication/step-up can be used instead of email reset for especially sensitive operations.

## 9. Unit Tests: Issuance, Single-Use, Boundary, Expiration, and Race Prevention

Test the service directly without depending on SMTP or LDAP/IdP. `CapturingSender` exists only in tests and holds the raw token to perform verification.

**src/test/java/example/onetime/ResetServiceTests.java:**

~~~java
package example.onetime;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

class ResetServiceTests {

    private static final Instant START =
            Instant.parse("2026-01-01T00:00:00Z");
    private static final String EMAIL = "alice@example.test";

    static final class CapturingSender
            implements OneTimeResetApplication.TokenSender {
        String latest;

        @Override
        public void send(String destination, String rawToken) {
            latest = rawToken;
        }
    }

    record Fixture(
            OneTimeResetApplication.DemoAccounts accounts,
            OneTimeResetApplication.MemoryTokenStore tokens,
            CapturingSender sender,
            PasswordEncoder encoder,
            OneTimeResetApplication.ResetService service) {}

    private static Fixture fixture(Instant now) {
        PasswordEncoder encoder = new BCryptPasswordEncoder(4);
        var accounts =
                new OneTimeResetApplication.DemoAccounts(encoder);
        var tokens =
                new OneTimeResetApplication.MemoryTokenStore();
        var sender = new CapturingSender();
        var service = new OneTimeResetApplication.ResetService(
                accounts, tokens, sender, encoder,
                Clock.fixed(now, ZoneOffset.UTC));
        return new Fixture(accounts, tokens, sender, encoder, service);
    }

    @Test
    void newTokenCanResetExactlyOnce() {
        Fixture f = fixture(START);
        f.service().requestReset(EMAIL);

        String token = f.sender().latest;
        assertThat(token).matches("[A-Za-z0-9_-]{43}");

        assertThat(f.service().complete(
                token, "a-new-password-123")).isTrue();
        assertThat(f.accounts().passwordMatches(
                "a-new-password-123", f.encoder())).isTrue();

        // The same token cannot reset the password a second time.
        assertThat(f.service().complete(
                token, "another-password-456")).isFalse();
        assertThat(f.accounts().passwordMatches(
                "a-new-password-123", f.encoder())).isTrue();
    }

    @Test
    void expiresExactlyAtDeadline() {
        Fixture f = fixture(START);
        f.service().requestReset(EMAIL);

        var serviceAtDeadline =
                new OneTimeResetApplication.ResetService(
                        f.accounts(), f.tokens(), f.sender(), f.encoder(),
                        Clock.fixed(
                                START.plus(Duration.ofMinutes(10)),
                                ZoneOffset.UTC));

        assertThat(serviceAtDeadline.complete(
                f.sender().latest, "a-new-password-123")).isFalse();
    }

    @Test
    void unknownAddressDoesNotDeliverAnyToken() {
        Fixture f = fixture(START);
        f.service().requestReset("unknown@example.test");
        assertThat(f.sender().latest).isNull();
    }

    @Test
    void onlyOneConcurrentRequestCanConsumeTheToken()
            throws Exception {
        Fixture f = fixture(START);
        f.service().requestReset(EMAIL);
        String token = f.sender().latest;

        var executor = Executors.newFixedThreadPool(2);
        var start = new CountDownLatch(1);

        try {
            Future<Boolean> a = executor.submit(() -> {
                start.await();
                return f.service().complete(token, "new-password-111");
            });
            Future<Boolean> b = executor.submit(() -> {
                start.await();
                return f.service().complete(token, "new-password-222");
            });

            start.countDown();
            int successes = (a.get(5, TimeUnit.SECONDS) ? 1 : 0)
                    + (b.get(5, TimeUnit.SECONDS) ? 1 : 0);

            assertThat(successes).isEqualTo(1);
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Notably, the concurrency test does not just call `complete` twice sequentially: two threads wait on the same `CountDownLatch`, then race on the same digest. `ConcurrentHashMap.compute` ensures only one receives the account; the test asserts **exactly one** `true` result. For multi-instance systems, the test must become an integration test against a real database and conditional-transaction token claiming.

### 9.1. HTTP Tests: permitAll Still Passes Through CsrfFilter

**src/test/java/example/onetime/ResetHttpTests.java:**

~~~java
package example.onetime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResetHttpTests {

    @Autowired
    MockMvc mvc;

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/password-reset/request")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"alice@example.test\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void existingAndUnknownEmailsHaveSameResponse()
            throws Exception {
        String existing = mvc.perform(
                post("/password-reset/request").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"alice@example.test\"}"))
                .andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();

        String unknown = mvc.perform(
                post("/password-reset/request").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"unknown@example.test\"}"))
                .andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();

        assertThat(existing).isEqualTo(unknown);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Test expectations**, when the code and dependencies above are used intact: service tests verify a 43-character raw token, single-use reset success, replay failure, invalidity at the exact expiration boundary, no token issued for unknown emails, and only one success for two concurrent requests. MVC tests verify POST without CSRF is blocked and both email addresses produce identical responses. Tests do not verify real email transport, HTTPS certificates, or PostgreSQL transactions; those layers must be verified separately.

## 10. From In-Memory Demo to Reliable Database Deployment

In production, the following parts usually need to change:

### 10.1. Database and Transactions

Create a unique index on `token_digest`, binding `account_id`, `purpose`, `expires_at`, `consumed_at`, and `revoked_at`. Check the expiration condition and `consumed_at IS NULL` **inside an atomic UPDATE**, check the affected row count, and update the password in the same transaction. Use a consistent clock source (e.g., database timestamp for the expiration condition in SQL). Keep verified operations together to prevent time-of-check/time-of-use gaps.

If the password update lives in another system not sharing the transaction, implement a compensation process or reliable state transition; never just mark consumed and ignore downstream failures. Always design idempotency for side effects like sending notifications or calling payment/invitation services.

### 10.2. Issuance Limits and Anti-Guessing

- Rate-limit by IP, canonicalized account/email, tenant, and suitable device signals; feed abuse signals into detection systems. Never rely solely on IP rate limiting due to shared IPs/proxies.
- Prevent email/SMS spam and repeated sending; consider cooldowns, quotas, and active token limits. Never lock a victim’s account just because someone repeatedly clicks “forgot password.”
- With random 256-bit tokens, online guessing is impractical when entropy is sound, yet **the endpoint still needs rate limiting and DoS protection**. With short OTPs, limit attempts per challenge and prevent reuse within the time window.
- Never disclose account existence via status/body; pay attention to processing time, email contents, and delivery-system responses.
- Never return tokens from the request endpoint, or write tokens to logs, raw database columns, telemetry, or crash reports.

### 10.3. Invalidation on State Changes

After a successful password reset, consider invalidating other reset tokens for the same account, removing remembered devices/tokens, rotating session identifiers, or revoking open sessions as required by security policy. Do not assume old sessions automatically become invalid just because the BCrypt hash changed: **active HTTP sessions may remain valid** unless explicitly invalidated.

For email verification, when the email changes, tokens for verifying the old email must become invalid. For invitations, when an invite is canceled or roles/workspaces change, prior tokens must not retain old permissions. Dependent preconditions must be recorded or re-verified at consumption time.

### 10.4. Retention and Data Access Control

Digests are also operationally sensitive data; restrict who can read the token table, protect backups, schedule cleanup of expired/consumed rows, and audit issuance/consumption using request IDs rather than raw tokens. Separate event logs (“issue requested,” “token consumed,” “expired/replayed”) from secret values. During incident handling, never share password reset tokens in tickets/chat.

### 10.5. Delivery Channel Availability

A token stored but not delivered to the user needs a retry/timeout strategy and a safe way to re-issue **notifications**; never log raw tokens to help support. With mail queues/outboxes, keep raw tokens short-lived and avoid long-lived raw payloads in queues when alternatives exist. Account for SMTP bounces and delayed email delivery: TTL starts at **issuance**, not when the recipient opens the email. If TTL is 10 minutes and the email arrives after 15 minutes, the token must be rejected and the user must request a new one.

## 11. Additional Cases to Test

| Scenario | Correct Result |
| --- | --- |
| Valid, unexpired, unused token | Succeeds once |
| Reusing the same token a second time, even immediately | Rejected |
| Two parallel requests with the same token | At most one succeeds |
| `now == expiresAt` or later | Rejected |
| Token modified by one character | Rejected |
| Valid token but wrong purpose | Rejected |
| Valid token of user A with client sending `email=userB` | Does not update user B; always uses `accountId` from the grant |
| Revoked token | Rejected |
| Password changed, then trying another old reset token | Per policy, related tokens are revoked/invalidated |
| Non-existent email | Generic HTTP response; no token sent |
| Reset completion POST missing/invalid CSRF in session web app | Handled by CsrfFilter per configuration; verify with MockMvc |
| New password fails policy | Rejected **before** consuming the token so the user can fix it, or clearly define another policy |
| DB/queue error between consume and update | No duplicate action occurs; rollback/recovery per transaction design |
| Multi-instance server deployment | Requires shared persistence/atomic claim, never trust per-JVM locks |
| GET reset link opened early by email scanner/prefetcher | Does not consume token solely from GET |
| Token in URL leaked via Referer/logs | Mitigations reduce leakage, short TTL, revoked on use |

Tests should cover failure paths, not just happy paths. Bugs like “expired yet still accepted” or “double-click reset updates twice” are **lifecycle logic bugs** that cannot be fixed merely by increasing token entropy.

## 12. Analysis of Common Mistakes

**Mistake 1 — Checking TTL without storing used state.** `expiresAt` does not protect against replay. Add a token/state record and atomic consumption.

**Mistake 2 — Using a JWT with `exp` and assuming `jti` prevents replay by itself.** `jti` is just an identifier; the server must store/claim it atomically if single-use is truly needed.

**Mistake 3 — Writing `find unused` then `mark used`.** Two competing requests can both pass. Use a conditional UPDATE/transaction, or `ConcurrentHashMap.compute` **only in a single-JVM demo**.

**Mistake 4 — Returning the raw token to the frontend at the “request token” step.** Anyone knowing a victim’s email could grab the reset token directly. Deliver via a verified owned channel and return a generic response.

**Mistake 5 — Hashing a 6-digit OTP with SHA-256 and calling it secure.** A 1-million-value space is easily brute-forced offline if the database leaks; use a dedicated mechanism with secrets/attempt limits and suitable expiration.

**Mistake 6 — Building email token URLs from an untrusted `Host` header.** Attackers can trick the backend into sending links with domains they control. Use a **fixed configured base URL**.

**Mistake 7 — User clicks an email link and GET already marks the token used.** Security scanners open the link first, preventing the user from completing the flow. GET displays a form/confirmation; only a valid POST consumes.

**Mistake 8 — Logging tokens or sending them to analytics.** Tokens in query strings are especially prone to leaking via request logs, Referer headers, and browser history. Minimize token exposure, set referrer/cache policies, and avoid logging secret query parameters.

**Mistake 9 — Forgetting account binding.** Alice’s token is sent with Bob’s email to change Bob’s password. Derive the account from the server-side grant; never trust client-submitted targets.

**Mistake 10 — Not checking purpose.** A `VERIFY_EMAIL` token could pass a `PASSWORD_RESET` endpoint. Every consumption must verify the exact `purpose`.

**Mistake 11 — Changing the password without revoking old sessions.** Authenticated sessions/cookies may remain active. Design session revocation explicitly per security requirements.

**Mistake 12 — Assuming `permitAll()` disables CSRF.** Authorization and CSRF are independent. In Spring Security Servlet, anonymous POSTs may still require a CSRF token; do not disable CSRF app-wide just because `curl` gets 403.

**Mistake 13 — No cleanup.** Expired and used records grow unbounded; configure retention, TTL indexes, or cleanup jobs. Cleanup must never make a used token valid again.

**Mistake 14 — Returning detailed “expired,” “already used,” or “unknown token” errors for every request.** Overly specific responses can give attackers signals. Return generic messages to clients and record detailed categories in internal logs without raw tokens.

**Mistake 15 — Token spans multiple application instances while locking only one instance.** Requests hitting another instance can still reuse it. Atomic claiming must live in a shared store, DB transaction, or consistent state service.

## 13. Self-Check Questions

**Question 1.** A token has 5 minutes left and was used successfully. Can the same token be submitted again?  
**No.** Single-use and TTL are independent; once consumed, it must be rejected immediately.

**Question 2.** Is using `Math.random()` plus a timestamp to generate reset tokens acceptable?  
**No.** Use `SecureRandom` with sufficient entropy, e.g., 32 bytes.

**Question 3.** Can `SHA-256(rawToken)` be stored instead of the original token?  
**Yes**, when the raw token is a high-entropy random string; the server hashes the client-supplied token and looks up/claims the digest.

**Question 4.** Should two concurrent requests be able to complete using the same `token_digest`?  
**No.** Atomic consumption / conditional UPDATE is required, verifying a single success.

**Question 5.** At `now == expiresAt`, is the token still valid?  
**No**, when the validity rule is `now.isBefore(expiresAt)`.

**Question 6.** After resetting a password, do all old sessions automatically expire?  
**Not by default.** Changing the password hash does not directly invalidate all stored `SecurityContext`s; a separate session/remember-me/token revocation policy is needed.

**Question 7.** A reset token is sent via email, and a mail scanner opens the URL with GET first. Should the token be consumed immediately on GET?  
**No.** Consume only when the user submits the proper completion request (usually POST), preventing link previews from invalidating the token.

**Question 8.** Are a CSRF token and a password reset token the same thing?  
**No.** A CSRF token protects requests in a browser/session context; a reset token is a one-time credential bound to account/purpose/TTL that must be consumed atomically.

**Question 9.** A JSON Web Token has `exp` and `jti`; is single-use guaranteed?  
**Not yet.** Server-side consumed/revoked state bound to `jti` or an equivalent mechanism is required.

**Question 10.** With a multi-instance system and PostgreSQL, which layer enforces single-use?  
**Conditional database claiming/transactions**, not `synchronized` on individual Java instances.

## 14. Pre-Deployment Checklist

- **Issue:** `SecureRandom` with sufficient entropy; issue only when policy allows; purpose, account, TTL, and relevant metadata properly stored.
- **Store:** hash/HMAC matching entropy/threat model; unique digest; restricted DB access; expiry/consumed/revoked state and cleanup.
- **Deliver:** appropriate channel, TLS, no raw token leaks via response/logs/analytics/`Host` header; GET links perform no side effects.
- **Verify:** check format, purpose, account binding, expiry boundary, revoked status, and attempted/used state; rate-limit and avoid detailed error leaks.
- **Consume:** atomic operation in shared store; update side effects in the same transaction or design recovery/idempotency.
- **After:** revoke related tokens, consider invalidating old sessions, notify users of security changes, keep token-free audit logs.
- **Test:** success, expired, replay, double-submit, concurrent requests, delivery failure, multi-instance, and CSRF; ensure reports do not claim unit tests prove real email/DB/TLS operation.

**Key takeaway:** a secure one-time token needs not only to be **unpredictable** and **time-limited**, but also to have **explicit permission scope, an appropriate delivery channel, atomic consumption, and controlled revocation**. In Spring Security Servlet, authentication/authorization mechanisms and `CsrfFilter` continue protecting actual requests; issuing and consuming reset tokens is application business logic that must cover the full lifecycle.
