# Creating an Endpoint to Request a Confirmation Email

When a user registers an account, changes their email address, or needs to confirm an action, an application often provides an HTTP endpoint to **request sending a confirmation email**. In Spring Framework Mail, the mail-sending part can be implemented using `JavaMailSender` and `MimeMessageHelper`, but a production-ready API also needs input validation, abuse limiting, token management, expiration lifetimes, SMTP error handling, and delivery-state tracking.

This practice project builds a flow for **verifying control of an email address**: the user requests an email to be sent to the address awaiting verification, opens a link containing a single-use token, and then confirms. This is one concrete example of a "confirmation email"; for order, payment, or booking confirmation emails, you still apply the same REST, MIME, security, and reliability principles, but **do not use an email verification token in place of business state**.

We start with an easy-to-understand model in Spring Boot, then upgrade to a production architecture with a **durable command/outbox**, `202 Accepted` response, account enumeration protection, idempotency, retries, and testing with an SMTP sandbox. Each step clearly distinguishes **send requested**, **accepted for processing**, **submitted via SMTP**, and **address verified**.

**Final goal:** have an HTTP endpoint with a clear contract that creates a confirmation email for the right recipient, does not leak accounts or tokens, is testable and observable, and clearly recognizes the limitations of simple synchronous solutions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Design the `POST /api/email-confirmations/requests` endpoint with appropriate request body, validation, and HTTP response.
2. Explain why requesting an email and confirming a token are **two separate actions**.
3. Generate a sufficiently strong, URL-safe random token with a TTL, and store only its digest rather than the plaintext token in the verification table.
4. Build a safe `text/plain` and HTML email using `MimeMessageHelper`.
5. Avoid sending email directly inside a controller or inside a long-running database transaction.
6. Avoid revealing whether an account exists through differing responses, bodies, timing, or errors.
7. Rate-limit requests by user, IP, device, or address with an appropriate policy.
8. Explain transaction boundaries when persisting a token and invoking SMTP.
9. Design an upgrade path to a transactional outbox and safe retries.
10. Organize unit, web, persistence, and SMTP integration tests.

## 2. Defining the Business Workflow

Suppose an account has been created with an **unverified email** status. The user clicks "Send confirmation email". The system needs to:

```text
Web / Mobile client
        |
        v
POST /api/email-confirmations/requests
        |
        v
Validate + authorize/rate limit
        |
        v
Find eligible unverified account
        |
        v
Create single-use token with expiry
        |
        v
Persist token digest + request metadata
        |
        v
Compose and submit email
        |
        v
User opens confirmation link
        |
        v
POST /api/email-confirmations/confirm
        |
        v
Validate token, consume once, mark email verified
```

**Never treat sending the email as having verified the email.** An account is marked `verified` only after a valid confirmation token has been consumed through the designed verification workflow.

### Two Separate Endpoints

| Endpoint | Purpose | Changes verified state? |
| --- | --- | --- |
| `POST /api/email-confirmations/requests` | Request sending an email containing a verification link/code | No |
| `POST /api/email-confirmations/confirm` | Validate the token and confirm the address | Yes, when the token is valid |

For products that use magic links to sign in or change an email address, token policies and permissions differ; **do not reuse verification tokens across all actions** if they have different sensitivity levels.

## 3. Contract of the Request Endpoint

### Example Request

```http
POST /api/email-confirmations/requests HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "email": "student@example.net"
}
```

### Recommended Response

```http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Length: 0
```

**`202 Accepted` means the application has accepted the request under its intake contract**, not that SMTP has submitted it or that the email has been delivered. If an API uses a durable queue, it should only return `202` after the durable request record has been successfully written.

For a public endpoint that could expose account existence, return the same generic response whether the email does not exist, is already verified, or is in cooldown, as long as the request has been handled under the corresponding policy. Do not return `404 Account not found` or `409 Email already verified` only for specific email groups if doing so allows strangers to probe accounts.

### If the Endpoint Requires an Authenticated Session

A safer design for many products:

```http
POST /api/me/email-confirmations/requests HTTP/1.1
Authorization: Bearer <session-token>
```

The backend retrieves the address from the **logged-in account**, rather than trusting an email passed by the client. This is suitable when requesting email confirmation for the current account. For an unauthenticated registration flow, a public request mechanism with abuse protection as shown later is needed.

## 4. Common HTTP Statuses

| Status | Meaning in the API | Notes |
| --- | --- | --- |
| `202 Accepted` | An eligible request has been accepted under the contract | Does not claim "delivered" |
| `204 No Content` | Chosen by some APIs for an idempotent operation already completed | No response body returned |
| `400 Bad Request` | Malformed JSON or values that cannot be parsed per the contract | Does not leak account lookup |
| `401 Unauthorized` | Missing or invalid authentication on an endpoint requiring login | Do not apply mechanically to public endpoints |
| `403 Forbidden` | The principal is not allowed to perform the operation | Avoid leakage on public requests |
| `429 Too Many Requests` | Rate limit exceeded | Return `Retry-After` when appropriate, without revealing account existence |
| `503 Service Unavailable` | Unable to durably accept due to a system dependency | Tells the client it may retry according to policy |

In a public environment, returning `429` selectively based on the specific state of an address can also leak information. Design consistent rate limits and response policies while still blocking abuse.

## 5. What the Endpoint Should Not Do

Do not return the raw token:

```json
{
  "verificationToken": "secret-token",
  "emailExists": true,
  "smtpStatus": "DELIVERED"
}
```

Such data both leaks secrets and misrepresents SMTP outcomes.

Do not accept arbitrary MIME content supplied by a public user:

```json
{
  "to": "victim@example.net",
  "from": "admin@example.org",
  "subject": "Arbitrary",
  "html": "<a href='https://malicious.example'>...</a>"
}
```

If the endpoint's sole purpose is email verification, the backend must **own the template, sender domain, content, TTL, and link target**. Do not turn it into an open mail relay for attackers to send arbitrary messages.

## 6. Spring Boot Architecture for the Practice Project

```text
EmailConfirmationController
         |
         v
ConfirmationRequestService
         |
         +--> Validation / RateLimit / Eligibility
         |
         +--> ConfirmationIssuer (transaction)
         |       |
         |       +--> AccountRepository
         |       +--> VerificationTokenRepository
         |       +--> SecureTokenService
         |
         +--> ConfirmationMailSender
                 |
                 +--> Template renderer
                 +--> JavaMailSender
                 +--> SMTP sandbox/provider

EmailConfirmationController.confirm
         |
         v
ConfirmationVerifier (transaction)
         |
         +--> TokenRepository
         +--> AccountRepository
```

In the initial learning version, the service issues a token inside a transaction and then sends the email **after the transaction completes**. This version is easy to understand, but **does not guarantee against losing the send request if the process crashes or SMTP fails**; the production upgrade section introduces an outbox and durable asynchronous processing.

## 7. Dependencies and Platform

The example uses:

- Java 17+.
- Spring Boot 3.x with `jakarta.mail`/`jakarta.validation`.
- Spring Web for REST.
- Spring Validation for input validation.
- Spring Data JPA and a SQL database.
- Spring Boot Mail for `JavaMailSender`.
- JUnit/Spring Boot Test and an SMTP sandbox for testing.

Gradle dependencies in a project already configured with the Spring Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Do not mix legacy `javax.mail` versions with `jakarta.mail` in the same Spring Boot 3.x project. For production databases, use migrations rather than letting Hibernate drop/recreate critical tables on restart.

## 8. Suggested Package Structure

```text
com.example.mailconfirm
├── MailConfirmationApplication.java
├── api/
│   ├── EmailConfirmationController.java
│   ├── RequestConfirmationBody.java
│   ├── ConfirmEmailBody.java
│   └── ApiExceptionHandler.java
├── domain/
│   ├── UserAccount.java
│   ├── EmailVerificationToken.java
│   └── ConfirmationPolicy.java
├── repository/
│   ├── AccountRepository.java
│   └── EmailVerificationTokenRepository.java
├── service/
│   ├── SecureTokenService.java
│   ├── ConfirmationIssuer.java
│   ├── ConfirmationRequestService.java
│   └── ConfirmationVerifier.java
└── mail/
    └── ConfirmationMailSender.java
```

For production, you can add `outbox/`, `worker/`, `metrics/`, and `security/`. These package names are illustrative, not a mandatory Spring Boot layout.

## 9. Dedicated SMTP Configuration for Development

Never send test emails from a local environment to real users. Use Mailpit, GreenMail, or an approved SMTP sandbox:

```yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000

app:
  confirmation:
    base-url: http://localhost:8080
    token-ttl: PT15M
    sender-address: no-reply@example.org
```

The example assumes an SMTP test server listening on `127.0.0.1:1025` without requiring TLS/auth. **Do not copy `auth=false`/`STARTTLS=false` settings into production.** Real SMTP providers may require STARTTLS, implicit TLS, and proper authentication.

### Production Uses Secrets and Proper TLS Contracts

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000

app:
  confirmation:
    base-url: https://account.example.org
    sender-address: verify@example.org
```

`${...}` represents **Spring property placeholders**; secret values must come from secret management or appropriate environment variables. Never put SMTP passwords into repositories, HTTP responses, or exception logs.

## 10. Database Configuration for the Lesson

Local PostgreSQL example:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://127.0.0.1:5432/mailconfirm
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
```

`ddl-auto: validate` assumes tables have already been created by migrations. In a short demo, you can use an in-memory database with a dedicated test schema. Never use `create-drop` in production on a database holding accounts and verification tokens.

## 11. Logical Database Schema

Two core tables:

```sql
CREATE TABLE user_account (
    id UUID PRIMARY KEY,
    email_canonical VARCHAR(320) NOT NULL UNIQUE,
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE email_verification_token (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES user_account(id),
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);

CREATE INDEX ix_verification_account_expiry
    ON email_verification_token(account_id, expires_at);
```

`token_hash` stores the digest of a high-entropy token, not the raw token. `expires_at` and `used_at` determine whether the token is still valid. Adding a unique constraint supports fast lookups and prevents duplicate digests across the table; with a 256-bit random token, collisions are extraordinarily unlikely, yet the database should still enforce the constraint.

If the application supports changing email addresses, bind the token to the **pending email or email version**. Do not verify a new address using a token issued for an old address.

## 12. Defining REST Request Bodies with Bean Validation

```java
package com.example.mailconfirm.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RequestConfirmationBody(
        @NotBlank
        @Email
        @Size(max = 320)
        String email
) {}
```

Another DTO for the confirmation step:

```java
package com.example.mailconfirm.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ConfirmEmailBody(
        @NotBlank
        @Size(max = 512)
        String token
) {}
```

HTTP validation is only the first layer. `@Email` does not prove that a mailbox exists, that the caller owns the mailbox, or that the address has been normalized properly. Token verification is what proves access to the receiving channel according to the workflow.

## 13. Controller Receiving Requests and Returning 202

```java
package com.example.mailconfirm.api;

import com.example.mailconfirm.service.ConfirmationRequestService;
import com.example.mailconfirm.service.ConfirmationVerifier;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/email-confirmations")
public class EmailConfirmationController {

    private final ConfirmationRequestService requests;
    private final ConfirmationVerifier verifier;

    public EmailConfirmationController(
            ConfirmationRequestService requests,
            ConfirmationVerifier verifier
    ) {
        this.requests = requests;
        this.verifier = verifier;
    }

    @PostMapping("/requests")
    public ResponseEntity<Void> request(
            @Valid @RequestBody RequestConfirmationBody body
    ) {
        requests.request(body.email());
        return ResponseEntity.accepted()
                .cacheControl(CacheControl.noStore())
                .build();
    }

    @PostMapping("/confirm")
    public ResponseEntity<Void> confirm(
            @Valid @RequestBody ConfirmEmailBody body
    ) {
        verifier.confirm(body.token());
        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
```

The controller does not build MIME, generate tokens, query the database directly, or hold SMTP configuration. It simply delegates the request to an application service and enforces the HTTP contract.

**Note:** this is a controller skeleton; for a production API, you must add authentication/authorization, anti-abuse controls, exception mapping, and durable acceptance per policy. Returning `202` does not by itself create background processing capability.

## 14. Distinguishing Public Requests from Authenticated Requests

With a public endpoint accepting an email:

- Anyone can request an email to be sent to any address if there are no guardrails.
- Malicious actors can spam a victim or use the API to enumerate accounts.
- Differences in response time depending on whether an account exists can create a timing side channel.

With a `/api/me/...` endpoint:

- The backend obtains the account ID from the authenticated session/token.
- It only sends to the pending-verification address belonging to that account.
- It usually does not need an `email` field in the request body.
- Rate limits/cooldowns and state checks are still required.

In this lesson, the public controller is kept to demonstrate an easy-to-test contract. **Do not expose this controller as-is to the Internet without implementing the anti-abuse and timing-leakage mitigations** covered in later sections.

## 15. Account Entity Awaiting Verification

We assume the application already has an account creation mechanism. This lesson omits registration and password management to focus on email confirmation.

```java
package com.example.mailconfirm.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "user_account")
public class UserAccount {

    @Id
    private UUID id;

    @Column(
            name = "email_canonical",
            nullable = false,
            unique = true,
            length = 320
    )
    private String emailCanonical;

    @Column(name = "email_verified_at")
    private Instant emailVerifiedAt;

    protected UserAccount() {}

    public UserAccount(UUID id, String emailCanonical) {
        this.id = id;
        this.emailCanonical = emailCanonical;
    }

    public UUID getId() {
        return id;
    }

    public String getEmailCanonical() {
        return emailCanonical;
    }

    public boolean isEmailVerified() {
        return emailVerifiedAt != null;
    }

    public void markEmailVerified(Instant when) {
        if (emailVerifiedAt == null) {
            emailVerifiedAt = when;
        }
    }
}
```

If the system allows changing addresses, the production model should include `pendingEmail` or a separate email version. The token must bind to the **address being verified**, not mistakenly confirm a different address changed after the token was issued.

## 16. Verification Token Entity

```java
package com.example.mailconfirm.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "email_verification_token")
public class EmailVerificationToken {

    @Id
    private UUID id;

    @Column(name = "account_id", nullable = false)
    private UUID accountId;

    @Column(
            name = "token_hash",
            nullable = false,
            unique = true,
            length = 64
    )
    private String tokenHash;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "used_at")
    private Instant usedAt;

    protected EmailVerificationToken() {}

    public EmailVerificationToken(
            UUID id,
            UUID accountId,
            String tokenHash,
            Instant createdAt,
            Instant expiresAt
    ) {
        this.id = id;
        this.accountId = accountId;
        this.tokenHash = tokenHash;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    public UUID getAccountId() {
        return accountId;
    }

    public boolean isUsableAt(Instant now) {
        return usedAt == null && expiresAt.isAfter(now);
    }

    public void consumeAt(Instant now) {
        if (usedAt != null) {
            throw new IllegalStateException(
                    "Token already consumed"
            );
        }
        usedAt = now;
    }
}
```

A token is considered expired when `expiresAt <= now`. Using `Instant` with an injected clock avoids timezone confusion and makes testing straightforward.

### Do Not Store Raw Tokens in the Entity

If the database is compromised while a token is still valid, a `raw_token` column allows an attacker to verify the email on behalf of the recipient. With a high-entropy random token, storing a SHA-256 digest ensures someone with a database dump cannot easily recover the token.

**Note:** a digest does not replace encryption if a raw token still needs to sit in a queue/outbox. In the production section, the token awaiting delivery must be encrypted at rest or issued inside the worker.

## 17. Repositories for Account and Token

```java
package com.example.mailconfirm.repository;

import com.example.mailconfirm.domain.UserAccount;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface AccountRepository
        extends JpaRepository<UserAccount, UUID> {

    Optional<UserAccount> findByEmailCanonical(
            String emailCanonical
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from UserAccount a where a.id = :id")
    Optional<UserAccount> findLockedById(
            @Param("id") UUID id
    );
}
```

And:

```java
package com.example.mailconfirm.repository;

import com.example.mailconfirm.domain.EmailVerificationToken;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.UUID;

public interface EmailVerificationTokenRepository
        extends JpaRepository<EmailVerificationToken, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
           select t from EmailVerificationToken t
           where t.tokenHash = :hash
           """)
    Optional<EmailVerificationToken> findLockedByHash(
            @Param("hash") String hash
    );
}
```

Pessimistic locking on the token reduces the risk of two concurrent requests consuming the same token. Locking the account during state transition prevents races between different tokens belonging to the same account.

In high-traffic production systems, you can also use an atomic conditional UPDATE or optimistic locking with an appropriate contract. Never simply call `findByHash`, check `usedAt`, and save without concurrency control.

## 18. Service for Random Token Generation and Digesting

A token must be **unpredictable** and safe for use in URLs. Avoid sequential tokens or tokens derived from timestamps or account IDs.

```java
package com.example.mailconfirm.service;

import org.springframework.stereotype.Component;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

@Component
public class SecureTokenService {

    private final SecureRandom secureRandom =
            new SecureRandom();

    public String newToken() {
        byte[] bytes = new byte[32]; // 256 random bits
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public String hash(String rawToken) {
        try {
            MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(
                    rawToken.getBytes(StandardCharsets.US_ASCII)
            );
            return HexFormat.of().formatHex(hashed);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable", ex
            );
        }
    }
}
```

### Why 32 Random Bytes?

32 bytes from `SecureRandom` give a token 256 bits of randomness by design; when encoded with unpadded URL-safe Base64, the token is typically 43 characters long. High-entropy tokens can use a SHA-256 digest for lookup, unlike low-entropy user passwords which require slow password hashing algorithms such as Argon2, bcrypt, or scrypt.

Do not substitute `UUID.randomUUID()` plus a timestamp when the product specification calls for a 256-bit secret. And never use `Random` (as opposed to `SecureRandom`) to issue verification tokens.

### Token Hashing Is Not Token Encryption

Hashing is one-way: the token table is used to **verify a token supplied by the user**. To send the email, the application needs the raw token at compose time; if the raw token must be stored for retries, it must be securely encrypted or re-issued inside a worker.

## 19. Clock Injection for Accurate Expiry Testing

```java
package com.example.mailconfirm;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Clock;

@Configuration
public class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

In unit tests you can substitute:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-12T03:00:00Z"),
        ZoneOffset.UTC
);
```

Expiration times should be compared using `Instant`; do not take the server's local time and add "15 minutes" in an unspecified timezone.

## 20. Email Address Normalization Policy

A simple example in a system that has chosen **case-insensitive email matching as an account policy**:

```java
package com.example.mailconfirm.service;

import java.util.Locale;

public final class EmailCanonicalizer {

    private EmailCanonicalizer() {}

    public static String canonicalize(String raw) {
        return raw.trim().toLowerCase(Locale.ROOT);
    }
}
```

**This is a simplified policy for the project**, not a universally safe technical rule for every mailbox: local parts can have case-sensitive semantics, internationalized addresses need dedicated normalization, and provider-specific alias/dot/plus rules must not be applied arbitrarily. For production, align canonicalization from registration/account lookup onward and test Unicode/IDN addresses if the system supports them.

Do not "strip dots in Gmail" or "strip everything after +" across all email domains. Doing so can merge two distinct addresses at other providers.

## 21. Data Passed Between Issuer and Mail Sender

```java
package com.example.mailconfirm.service;

import java.time.Instant;
import java.util.UUID;

public record IssuedConfirmation(
        UUID accountId,
        String recipient,
        String rawToken,
        Instant expiresAt
) {}
```

In the demo version, this record holds the **raw token only in memory between issuance and sending**. Do not log the record via `toString()`, serialize it into an HTTP response, or place it onto an unencrypted queue.

A production worker/outbox needs a different contract to protect unsent data, as shown in the upgrade section.

## 22. Service Issuing the Token in a Dedicated Transaction

```java
package com.example.mailconfirm.service;

import com.example.mailconfirm.domain.EmailVerificationToken;
import com.example.mailconfirm.domain.UserAccount;
import com.example.mailconfirm.repository.AccountRepository;
import com.example.mailconfirm.repository.EmailVerificationTokenRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Service
public class ConfirmationIssuer {

    private final AccountRepository accounts;
    private final EmailVerificationTokenRepository tokens;
    private final SecureTokenService secureTokens;
    private final Clock clock;

    public ConfirmationIssuer(
            AccountRepository accounts,
            EmailVerificationTokenRepository tokens,
            SecureTokenService secureTokens,
            Clock clock
    ) {
        this.accounts = accounts;
        this.tokens = tokens;
        this.secureTokens = secureTokens;
        this.clock = clock;
    }

    @Transactional
    public Optional<IssuedConfirmation> issueIfEligible(
            String rawEmail
    ) {
        String canonical =
                EmailCanonicalizer.canonicalize(rawEmail);

        Optional<UserAccount> found =
                accounts.findByEmailCanonical(canonical);

        if (found.isEmpty() || found.get().isEmailVerified()) {
            return Optional.empty();
        }

        UserAccount account = found.get();
        Instant now = clock.instant();
        Instant expiresAt = now.plus(Duration.ofMinutes(15));

        String rawToken = secureTokens.newToken();
        String hash = secureTokens.hash(rawToken);

        tokens.save(new EmailVerificationToken(
                UUID.randomUUID(),
                account.getId(),
                hash,
                now,
                expiresAt
        ));

        return Optional.of(new IssuedConfirmation(
                account.getId(),
                account.getEmailCanonical(),
                rawToken,
                expiresAt
        ));
    }
}
```

In this lesson, the TTL is hardcoded to 15 minutes for clarity; production should read it from `@ConfigurationProperties` with validation and bounds appropriate for the email type. Do not treat 15 minutes as the right expiration for every product.

### Separating Transactions Is Essential

`@Transactional` on `ConfirmationIssuer` covers only the lookup and token insert. When the facade invokes it **through another Spring bean**, the transaction commits before the facade performs SMTP. This prevents holding a database transaction open during slow network I/O.

However, a window for lost work still exists:

```text
Commit token -> process crashes -> SMTP never called
```

This is an intentional limitation of the demo version; an outbox addresses it.

## 23. Do Not Blindly Revoke All Previous Tokens

A user clicks "Resend email" three times:

```text
Token A issued at 10:00
Token B issued at 10:01
Token C issued at 10:02
```

Two common policies:

**One valid token at a time:**

- Issue token B and revoke A.
- Keeps state simple, but email A may arrive late with a link that is no longer valid.

**Allow several unexpired tokens to coexist:**

- A, B, and C can all verify within the TTL.
- Requires rate limits and ensuring the account transitions to verified only once.
- Once verified, remaining tokens must not be usable for any other action.

The example code follows the second approach: multiple tokens can be created, while the verifier checks whether the account is already verified. Production needs clear resend, cooldown, and max active tokens rules; do not generate unbounded records when an attacker spams the endpoint.

## 24. Building the Confirmation Page and Link

The email contains a link to a frontend page:

```text
https://account.example.org/confirm-email?token=<opaque-token>
```

The frontend displays the confirmation screen and then calls `POST /api/email-confirmations/confirm` with the token. It does not need to verify automatically as soon as HTTP GET opens the link.

### Why Not Auto-Confirm on GET?

Email security gateways and link scanners may fetch URLs before the user does. If GET has the side effect of "consume token and mark account verified", a scanner can accidentally trigger the action. For important operations, use an explanatory page and an appropriately protected confirmation action.

If you choose one-click verification without an extra confirmation step, you must evaluate scanner/prefetch behavior, replay, and product risk rather than assuming a GET URL always represents user intent.

## 25. Managing the Email Base URL

Never use the client-supplied `Host` header to build links:

```java
// Anti-pattern: attacker can control the Host
String link = request.getHeader("Host") + "/confirm-email";
```

Use an application-managed origin instead:

```yaml
app:
  confirmation:
    base-url: https://account.example.org
```

In staging environments:

```yaml
app:
  confirmation:
    base-url: https://staging-account.example.org
```

Avoid using production URLs in test emails, and allow only approved HTTPS origins when serving real users. This reduces the risk of host-header poisoning and links pointing to fake domains.

## 26. Confirmation Configuration as Type-Safe Properties

```java
package com.example.mailconfirm;

import org.springframework.boot.context.properties.ConfigurationProperties;
import java.net.URI;
import java.time.Duration;

@ConfigurationProperties(prefix = "app.confirmation")
public record ConfirmationProperties(
        URI baseUrl,
        String senderAddress,
        Duration tokenTtl
) {}
```

Enabling it:

```java
package com.example.mailconfirm;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ConfirmationProperties.class)
public class MailConfirmationApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                MailConfirmationApplication.class, args
        );
    }
}
```

In production, add property validation: valid sender address, `baseUrl` within allowlisted HTTPS origins, and positive `tokenTtl` within policy bounds. Never let the endpoint caller choose `baseUrl` or the SMTP sender.

## 27. Service Building and Sending the MIME Email

```java
package com.example.mailconfirm.mail;

import com.example.mailconfirm.ConfirmationProperties;
import com.example.mailconfirm.service.IssuedConfirmation;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;
import org.springframework.web.util.HtmlUtils;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

@Component
public class ConfirmationMailSender {

    private final JavaMailSender sender;
    private final ConfirmationProperties properties;

    public ConfirmationMailSender(
            JavaMailSender sender,
            ConfirmationProperties properties
    ) {
        this.sender = sender;
        this.properties = properties;
    }

    public void send(IssuedConfirmation issued)
            throws MessagingException {

        String encoded = URLEncoder.encode(
                issued.rawToken(),
                StandardCharsets.UTF_8
        );
        String url = properties.baseUrl()
                .resolve("/confirm-email?token=" + encoded)
                .toASCIIString();

        String safeUrl = HtmlUtils.htmlEscape(url);
        String plain = """
                Vui lòng xác minh địa chỉ email của bạn.

                Mở đường dẫn:
                """ + url + """

                Nếu bạn không yêu cầu, có thể bỏ qua thư này.
                """;

        String html = """
                <html>
                  <body>
                    <h1>Xác minh địa chỉ email</h1>
                    <p>Vui lòng xác nhận địa chỉ bằng liên kết:</p>
                    <p><a href="%s">Xác minh email</a></p>
                    <p>Nếu bạn không yêu cầu,
                       có thể bỏ qua thư này.</p>
                  </body>
                </html>
                """.formatted(safeUrl);

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom(properties.senderAddress());
        helper.setTo(issued.recipient());
        helper.setSubject("Xác minh địa chỉ email");
        helper.setText(plain, html);

        sender.send(mime);
    }
}
```

**Code block note:** Java text blocks have their own concatenation and newline rules; the example focuses on passing an equivalent `plain` and `html` pair. In a real project, a template engine with explicit HTML escaping and a plain-text renderer are usually easier to maintain. When using code like this in a project, write a clean link-formatting helper instead of overusing string concatenation inside templates.

### Why Use MimeMessageHelper?

- Creates equivalent `text/plain` and `text/html` parts.
- Supports UTF-8 charset for Vietnamese text.
- Can be extended with inline logos or attachments when truly needed.
- Decouples the business service from the MIME/Jakarta Mail APIs.

Never put the email verification token in the `Subject` or custom headers. Subject and headers are often displayed, stored, and logged much more broadly than the body, and the raw token is already inside the link, so additional copies should be minimized.

## 28. Link Token and Privacy Considerations

Links using query parameters may be recorded in:

- Browser history.
- Proxy/server access logs if the request hits the URL.
- Client diagnostics or support screenshots.
- Referrer headers if the page loads third-party resources and is misconfigured.
- Email security scanning/logging.

Therefore, the confirmation page should:

- Use HTTPS and a restrictive `Referrer-Policy`.
- Not load analytics or third-party scripts that receive the full URL containing the token.
- Not print the token in application logs.
- After reading the token, strip it from the displayed URL when appropriate for the frontend design.
- Send the token only to the protected verification endpoint, without passing it through multiple redirects.
- Use short-lived, single-use tokens bound to the right account/action.

You can consider fragment-based links or other patterns to reduce server-side URL logging, but you must evaluate client compatibility, link scanners, and UX; no single URL pattern guarantees absolute safety.

## 29. Facade Coordinating Requests in the Learning Version

`ConfirmationIssuer` saves the token in a transaction. `ConfirmationMailSender` performs SMTP I/O **afterward**, outside that transaction.

```java
package com.example.mailconfirm.service;

import com.example.mailconfirm.mail.ConfirmationMailSender;
import jakarta.mail.MessagingException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.stereotype.Service;

@Service
public class ConfirmationRequestService {

    private static final Logger log =
            LoggerFactory.getLogger(
                    ConfirmationRequestService.class
            );

    private final ConfirmationIssuer issuer;
    private final ConfirmationMailSender mailSender;

    public ConfirmationRequestService(
            ConfirmationIssuer issuer,
            ConfirmationMailSender mailSender
    ) {
        this.issuer = issuer;
        this.mailSender = mailSender;
    }

    public void request(String rawEmail) {
        issuer.issueIfEligible(rawEmail).ifPresent(issued -> {
            try {
                mailSender.send(issued);
            } catch (MailException | MessagingException ex) {
                // Demo: do not leak account/SMTP reason to HTTP.
                // Production: persist failure + retry via outbox.
                log.warn(
                        "Confirmation SMTP submit failed; accountId={}",
                        issued.accountId()
                );
            }
        });
    }
}
```

This code has several pedagogical advantages:

- The controller does not depend directly on SMTP.
- The token hash is persisted before calling `send(...)`.
- No transaction is held open while SMTP experiences network latency.
- The HTTP response does not leak SMTP exception details.

**However, it is not yet a public-production solution**:

1. If the process dies after committing the token but before sending, there is no durable mail work item.
2. If SMTP fails, it only logs without retrying.
3. If the email account does not exist, the code skips SMTP faster; if it exists, it waits for SMTP. **Response time can reveal account existence.**
4. If the client retries the HTTP request, multiple tokens/emails may be generated.
5. There is no rate limiting or abuse protection yet.
6. `202` in the demo only reflects that the endpoint processed the call, not a durable queue.

The production section below solves this with a durable command and outbox, not merely by adding `@Async` to `mailSender.send(...)`.

## 30. Token and Account States Independent of SMTP

Token state model:

```text
ISSUED
  |
  +-- user confirms before expiry -> CONSUMED
  |
  +-- time reaches expiry -------> EXPIRED
  |
  +-- account verified by other token -> NO LONGER ELIGIBLE
```

You do not need to turn every token into a JPA state enum if `expiresAt` and `usedAt` sufficiently represent business state, but remember this state is distinct from the **email sending state**.

A token may be valid even though the email has not yet been sent due to a transport failure; this is why mail notification tracking should be separate from the token.

## 31. Verifying the Token in a Transaction

We use the raw token's digest to look up the row, lock the token row when consuming it, and then lock the account to ensure consistent verification state.

```java
package com.example.mailconfirm.service;

import com.example.mailconfirm.domain.EmailVerificationToken;
import com.example.mailconfirm.domain.UserAccount;
import com.example.mailconfirm.repository.AccountRepository;
import com.example.mailconfirm.repository.EmailVerificationTokenRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;

@Service
public class ConfirmationVerifier {

    private final EmailVerificationTokenRepository tokens;
    private final AccountRepository accounts;
    private final SecureTokenService secureTokens;
    private final Clock clock;

    public ConfirmationVerifier(
            EmailVerificationTokenRepository tokens,
            AccountRepository accounts,
            SecureTokenService secureTokens,
            Clock clock
    ) {
        this.tokens = tokens;
        this.accounts = accounts;
        this.secureTokens = secureTokens;
        this.clock = clock;
    }

    @Transactional
    public void confirm(String rawToken) {
        String hash = secureTokens.hash(rawToken);
        EmailVerificationToken token = tokens
                .findLockedByHash(hash)
                .orElseThrow(InvalidConfirmationToken::new);

        Instant now = clock.instant();
        if (!token.isUsableAt(now)) {
            throw new InvalidConfirmationToken();
        }

        UserAccount account = accounts
                .findLockedById(token.getAccountId())
                .orElseThrow(InvalidConfirmationToken::new);

        if (account.isEmailVerified()) {
            throw new InvalidConfirmationToken();
        }

        // For email change: verify the current address/version
        // still matches the data being verified.
        account.markEmailVerified(now);
        token.consumeAt(now);
    }
}
```

Define a dedicated exception:

```java
package com.example.mailconfirm.service;

public class InvalidConfirmationToken
        extends RuntimeException {
}
```

JPA-managed entities are dirty-checked and flushed when the transaction commits. If the database schema allows multiple active tokens per account, once the account is verified, remaining tokens cannot verify it again due to the account check. You can clean up or invalidate them per policy.

### Be Careful When Changing Email Addresses

In a real project, you must verify that the token confirms the **exact pending email/version**. For example, if a user requests verification for A and then changes to B, token A must not be allowed to mark B as verified. This lesson uses a single fixed email field to focus on the endpoint; an email-change flow needs additional schema columns such as `pending_email`/`target_email_hash`/`email_version`.

## 32. Error Mapping for the Confirm Endpoint

`InvalidConfirmationToken` can return a generic response:

```java
package com.example.mailconfirm.api;

import com.example.mailconfirm.service.InvalidConfirmationToken;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidConfirmationToken.class)
    public ResponseEntity<Void> invalidToken() {
        return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
```

Never return:

```json
{
  "tokenExists": true,
  "accountEmail": "somebody@example.net",
  "expiredAt": "..."
}
```

to an unprivileged caller. You can show user-friendly UX guidance such as "The link is invalid or has expired; please request a new email", but the message and API diagnostics must not help guess tokens or accounts.

## 33. Should a Token Be Single-Use?

Yes. Once a token has been consumed:

```text
First confirmation POST -> success / 204
Second POST with same token -> invalid / generic rejection
```

In a system with idempotent UX, you can show logged-in users an "Email verified" status through a separate account endpoint. You do not need to keep every old raw token valid just so a second POST returns `204`.

### Why Is Locking Necessary?

Without concurrency control:

```text
Thread A: find token used_at = null
Thread B: find token used_at = null
Thread A: set used_at = now
Thread B: set used_at = now
```

If the same token grants additional privileges, this is serious. A JPA pessimistic lock or an atomic UPDATE with `used_at IS NULL AND expires_at > now()` makes the single-use guarantee solid.

## 34. Rate Limiting Is a Mandatory Requirement

A public endpoint can be abused to spam email. Recommended limits:

- At most N requests/IP within a window.
- At most N requests/email/account within a window.
- Cooldown between two emails sent to the same account.
- Limit on the number of active tokens.
- Total traffic limit per tenant/project.
- CAPTCHA or challenge on suspicious behavior.
- Stricter controls when an IP/proxy behaves abnormally.
- Monitor bounces/complaints/suppressions from the provider.

Values of N must be tuned to your usage and abuse profile; there is no single threshold for every application. With multiple application instances, the counter/rate limiter must use a **shared backing store or gateway enforcement**; a static variable in the JVM protects only a single node.

### Preventing Spam Without Leaking Accounts

If the endpoint returns `429` only when an email exists, an attacker can distinguish accounts by the response. Use combined rate limits across IP, identity, and properly normalized/hashed keys while keeping a generic response when dropping ineligible requests. Do not log raw addresses in metric labels.

## 35. Account Enumeration via Response Timing

A dangerous bug:

```java
if (accountNotFound) {
    return 202;          // 2ms
}
mailSender.send(email);   // 700ms
return 202;
```

The body and status are identical, yet the timing differs. Repeated across many attempts, an attacker can infer registered emails.

**Better approach:** decouple HTTP acceptance from account lookup and account-specific SMTP I/O. The endpoint writes a **durable request command** per contract and returns a generic `202`; a separate worker decides whether an eligible account exists and whether to send.

Do not rely on random sleeps or fixed delays as a complete defense; side effects, status/headers, rate limits, and latency distributions must still be designed properly.

## 36. Issuing Requests from a Logged-In Session Reduces the Abuse Surface

If only an authenticated user requests verification for their own email, the endpoint can look like:

```java
@PostMapping("/me/email-verification-request")
public ResponseEntity<Void> requestForCurrentUser(
        Authentication authentication
) {
    UUID accountId = currentAccountId(authentication);
    confirmationCommands.enqueueForAccount(accountId);
    return ResponseEntity.accepted().build();
}
```

`currentAccountId(...)` and `confirmationCommands` are application-defined abstractions; the example assumes a security filter has already authenticated the session/principal.

Do not accept an account ID from the request body if the endpoint is only for the current user, unless explicit authorization checks are in place. For a backend-for-frontend using session cookies, add appropriate CSRF protection for the POST.

## 37. CORS Is Not Authorization

If the frontend is on another origin, the application may need CORS configuration so browsers can submit requests. However:

- CORS is a browser mechanism; it does not stop non-browser HTTP clients from sending requests.
- CORS does not prove the caller has permission to send mail to a mailbox.
- Wildcard origins with credentials are generally inappropriate for authenticated endpoints.
- CSRF and authentication are separate problems.

Do not blindly enable `@CrossOrigin("*")` to fix a frontend error and omit rate limiting or permission checks.

## 38. Idempotency When Users Click Repeatedly

A user might:

- Double-click "Send".
- Refresh the page.
- Lose the HTTP response and retry.
- Use a mobile app with a retry interceptor.
- Open two tabs and submit simultaneously.

If every request creates a token and sends an email:

```text
request-1 -> token A -> email A
request-2 -> token B -> email B
request-3 -> token C -> email C
```

This floods the mailbox and increases the chance of clicking an outdated link.

An API can accept a client-generated `Idempotency-Key` scoped by actor and action, stored durably with a TTL so one user's key cannot affect another user. In addition, a **cooldown** is needed to prevent repeated requests with different idempotency keys.

Do not treat `Idempotency-Key` as an authentication secret; it is solely a key to prevent duplicate execution of a single logical request.

## 39. Generic Response Body for UX

A product might choose a response like:

```json
{
  "message": "If the address is eligible, a confirmation email will be sent."
}
```

On a public endpoint, this phrasing does not confirm whether the account exists. To keep users from getting stuck, the frontend can show:

> If you don't see the email, please check your spam folder or try again in a few minutes.

However, **never say "Email sent successfully" when the API has only enqueued the request**. The wording must match what the backend has actually confirmed.

## 40. Things That Should Never Enter Logs

Do not log:

```text
rawToken
confirmationLink with query token
email body
SMTP password
full MimeMessage
authorization header
unmasked recipient email (unless required)
```

Safer logging example:

```text
event=email_confirmation_requested
requestId=opaque-request-id
flow=signup-email-verification
result=accepted
```

For the worker:

```text
event=email_confirmation_smtp_attempt
notificationId=opaque-notification-id
attemptId=opaque-attempt-id
providerRoute=transactional
status=SUBMITTED
```

Never write the raw token into exceptions or into JSON responses when template/SMTP errors occur.

## 41. Content Configuration for Email: From, Reply-To, Subject

A confirmation email should have:

- A `From` domain authorized by the system.
- A clear `Subject` with no token.
- A `Reply-To` if a support channel exists.
- Equivalent plain text and HTML.
- A notice such as "if you did not request this, you can ignore this email".
- Expiration information matching the actual policy.
- Links pointing to the official domain (HTTPS).

Do not let public requests choose `From` or supply arbitrary HTML, to avoid turning the endpoint into a mail relay.

### SMTP Authentication and Domain Reputation

When moving to production, verify SPF, DKIM, DMARC, and the provider's `From` policies to reduce spoofing and deliverability issues. A successful `JavaMailSender.send(...)` call does not guarantee inbox placement or that the user can open the link.

## 42. Why the Demo Version Is Not Reliable Enough for Production

Consider the flow:

```text
HTTP request
   |
   v
INSERT token_hash  -- database COMMIT
   |
   X  process crashes
   |
   v
JavaMailSender.send(...) never happens
```

The account has a valid token in the database, yet the user never receives an email. Likewise, when the SMTP server rejects temporarily or hits a quota limit, the demo has no retry job.

Another common suggestion is `@Async` or `CompletableFuture.runAsync(...)`. Those can reduce latency, but they do not provide durability: a process restart before the thread executes still loses the work. To recover, **the intent to send must be persisted durably**.

## 43. Production Architecture: Persist the Request Durably First

A public endpoint should decouple acceptance from account lookup and SMTP:

```text
Client
  |
  v
POST /api/email-confirmations/requests
  |
  v
Input validation + rate limit
  |
  v
Persist durable confirmation request command
  |
  v
Commit
  |
  v
HTTP 202 Accepted
                |
                v
        Command worker
          - decrypt/resolve recipient
          - check eligibility/cooldown
          - create token + digest
          - create encrypted mail outbox work
                |
                v
          Mail worker
            - claim notification
            - decrypt token just-in-time
            - render MIME
            - SMTP submit
            - record attempt outcome
```

For an authenticated endpoint, the command may only need `accountId` and action type. For a public endpoint accepting `email`, the email payload must be protected since it is PII; avoid putting raw emails into queue logs or metrics.

**Never return `202` before the durable command is written**, if the API contract states the request has been accepted. If the database or queue is unavailable, return an appropriate service error instead of reporting success and silently dropping the request.

## 44. Illustrative Database Schema for Durable Commands

```sql
CREATE TABLE email_confirmation_request (
    request_id UUID PRIMARY KEY,
    recipient_ciphertext BYTEA,
    recipient_cipher_metadata JSONB,
    actor_account_id UUID,
    action_type VARCHAR(40) NOT NULL,
    state VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    retry_after TIMESTAMPTZ,
    processed_at TIMESTAMPTZ
);

CREATE INDEX ix_confirmation_command_pending
    ON email_confirmation_request(created_at, request_id)
    WHERE state = 'PENDING';
```

This is an **illustrative schema**, lacking full key management, tenancy, and retention constraints. `recipient_ciphertext` is data encrypted by an application-managed encryption system; never "encrypt" with Base64. `actor_account_id` should hold only an authenticated/authorized ID when available.

Some systems store commands in a durable broker rather than a database. In that case, you must understand the broker's publish acknowledgments, persistence, and retry semantics.

### Avoid Storing the Entire SMTP Email in the Request Command

A request command should represent an intent:

```text
action=SEND_EMAIL_VERIFICATION
subject=account
accountId or protected address reference
requestId
createdAt
```

Template, sender address, token, HTML, and routing should be decided by the backend after eligibility checks. This reduces the risk of turning the endpoint into an arbitrary relay.

## 45. Enqueuing Work in a Short Transaction

For an authenticated account:

```java
@Transactional
public UUID enqueueVerificationForCurrentAccount(
        UUID authenticatedAccountId
) {
    UUID requestId = UUID.randomUUID();

    confirmationCommands.insertPending(
            requestId,
            authenticatedAccountId,
            "VERIFY_OWN_EMAIL"
    );

    return requestId;
}
```

`confirmationCommands` is an application-built repository. For public email inputs, an encrypted recipient reference and canonicalization policy are required; never store the raw email in the command for debugging convenience.

The method only writes to the DB; it does not perform SMTP inside the transaction. A worker picks up the command after commit. There is no need to return `requestId` to a public client if that ID could inadvertently allow querying account status.

## 46. Token and Mail Outbox Must Be Created in the Same Transaction

The command worker can do:

```text
Claim request command
      |
      v
Find eligible account
      |
      v
Generate random raw token
      |
      v
SHA-256 digest -> verification_token
      |
      v
Encrypt raw token -> mail_outbox_payload
      |
      v
INSERT notification PENDING
      |
      v
Mark command MATERIALIZED
      |
      v
COMMIT
```

**Important:** if inserting the token digest succeeds but creating the outbox entry fails, the transaction must roll back both together. If the outbox has an email to send while the token hash does not exist, the user will receive a link that can never verify.

Service skeleton example:

```java
@Transactional
public void materializeRequest(UUID requestId) {
    ConfirmationRequest command =
            commands.lockPending(requestId);

    if (!eligible(command)) {
        commands.markSuppressed(requestId);
        return;
    }

    String rawToken = secureTokens.newToken();
    String tokenHash = secureTokens.hash(rawToken);
    Instant expiresAt = clock.instant().plus(tokenTtl);

    tokenRepository.insert(
            command.accountId(),
            tokenHash,
            expiresAt
    );

    EncryptedPayload payload = encryption.encrypt(
            command.accountId(),
            rawToken
    );

    outbox.insertIfAbsent(
            command.logicalRequestKey(),
            payload,
            expiresAt
    );

    commands.markMaterialized(requestId);
}
```

This snippet **assumes** application-defined abstractions: `ConfirmationRequest`, `EncryptedPayload`, repositories, policies, crypto, and duplicate-prevention constraints. It illustrates transaction boundaries, not copy-paste code for a project without those classes defined.

### Critical Rule for Passwords and Tokens

The raw token should appear in memory only at issuance and when the worker builds the email; when it must survive a restart, it must be encrypted and have a TTL. Never use the token digest from the database to render a link: a digest is one-way and cannot recover the raw token.

## 47. Outbox Records and Delivery States

A reference schema:

```sql
CREATE TABLE mail_outbox (
    notification_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    account_id UUID NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    encrypted_token_payload_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    next_attempt_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    submitted_at TIMESTAMPTZ,
    lease_until TIMESTAMPTZ
);

CREATE TABLE mail_submission_attempt (
    attempt_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_outbox(notification_id),
    provider_key VARCHAR(60) NOT NULL,
    status VARCHAR(30) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox(next_attempt_at, notification_id)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
```

`UNIQUE(request_id)` illustrates that one command produces at most one notification. If the product allows one request to send to multiple recipients or use multiple templates, design a different business key.

Never put raw tokens into `mail_submission_attempt` or logs. The mail state and verification token state have separate lifecycles.

## 48. Claiming Work Across Multiple Workers

When running multiple application instances:

```text
Worker A ----+
             +-- shared mail_outbox database
Worker B ----+
             |
             +-- only one valid claim per notification
```

A PostgreSQL pattern:

```sql
SELECT notification_id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
ORDER BY created_at, notification_id
FOR UPDATE SKIP LOCKED
LIMIT 50;
```

**This query alone is not enough if you only SELECT and COMMIT.** You must write `PROCESSING`/owner/lease in the same transaction before committing, and only then perform SMTP outside the transaction.

If a worker crashes, the lease expires and a reconciler decides how to proceed. Never assume an expired lease means SMTP did not submit, especially if the process died after sending `DATA`.

## 49. Why SMTP Retries Must Be Classified

```text
Attempt A
  |
  +-- Connection could not open before DATA
  |       -> known not submitted, retry may be safe
  |
  +-- Temporary 4xx before acceptance
  |       -> retry per provider policy
  |
  +-- Permanent invalid recipient
  |       -> do not retry blindly
  |
  +-- Timeout after SMTP DATA
          -> UNKNOWN: may already be accepted
```

A `MailSendException` does not prove none of the recipients were submitted. Partial acceptance or a timeout after `DATA` can occur. Automatic retries can create two emails containing two tokens, causing confusion.

### Simple Policy for Confirmation Emails

- Failures definitely before submission: safe to retry with limits.
- Permanent failures: record `FAILED`, do not spam the provider.
- `UNKNOWN` outcome: avoid blind retries; reconcile if provider evidence is available.
- Expired token: do not send an old link; require a new request/re-issuance flow per policy.
- Already verified account: suppress pointless confirmation resends.
- Canceled token or account: stop pending work.

## 50. When Should Encrypted Tokens Be Cleaned Up?

Do not retain encrypted raw tokens indefinitely:

```text
PENDING / RETRY_WAIT (valid token)
          |
          +-- still eligible --> retain encrypted payload briefly
          |
          +-- token expired --> cancel pending send

SUBMITTED / FAILED / CANCELED / EXPIRED
          |
          v
Retention decision
          |
          v
Purge encrypted token payload
          |
          v
Keep minimal status/attempt metadata
```

Once SMTP submission finishes, the encrypted raw-token payload can be purged per retention policy, while the token digest remains until consumed or expired and is cleaned up per policy. Do not delete the token digest while the user still needs to verify just because the email was submitted; doing so breaks the link.

## 51. Separating "Sent" from "Verified"

Several distinct states need independent observation:

| Concept | Example States | Meaning |
| --- | --- | --- |
| Request command | ACCEPTED, MATERIALIZED, SUPPRESSED | How the request was handled |
| Outbox notification | PENDING, PROCESSING, SUBMITTED, FAILED, UNKNOWN | Whether the message was submitted |
| Verification token | ISSUED, CONSUMED, EXPIRED | Whether the token can still be used |
| Account email | UNVERIFIED, VERIFIED | Whether control of the email has been confirmed |
| Provider feedback | DELIVERED_REMOTE, BOUNCED, DEFERRED | Transport evidence toward the recipient |

It is completely normal for a notification to be `SUBMITTED` while the account remains `UNVERIFIED`. Even a `DELIVERED_REMOTE` provider event does not prove the recipient clicked verify.

## 52. Do Not Store Send State as a Single Boolean

```java
boolean sent;
```

fails to distinguish:

- Enqueued, not yet picked up by a worker.
- SMTP submission succeeded.
- SMTP timed out with an ambiguous outcome.
- Provider deferred.
- Email bounced.
- User verified.

Use an explicit state/attempt ledger and clear timestamps. The API only needs to expose the appropriate level of detail to the user, without exposing internal transport details.

## 53. Multiple Confirmation Emails in Flight at Once

A user clicks resend while the previous email has not arrived yet:

```text
Email A sent 10:00 (token A)
Email B sent 10:01 (token B)
Inbox receives B first, then A
```

A clear policy is required:

- Allow both unexpired tokens so the account can verify with either one.
- Or allow only the newest token, provided UX accepts that a late-arriving email A will show an expired/invalid link.
- Enforce a cooldown to reduce the number of emails sent.
- You can display "We sent an email recently" without leaking public account existence.

Never let two concurrent requests produce an inconsistent state; use database constraints/locks and explicit validation policies.

## 54. Send Links to the Account's Pending Address, Not an Arbitrary User Email

An endpoint may accept `email`, but the mail sender must not simply use `body.email` without resolving the account and checking eligibility:

```text
Input email
   |
   v
Canonicalize according to account policy
   |
   v
Resolve eligible account
   |
   v
Use verified ownership of target/pendingEmail
   |
   v
Create token scoped to account + address
   |
   v
Send to approved target address
```

In practice, changing an email may require verifying both old and new addresses or re-authentication depending on sensitivity. Never let a client pass another user's `accountId` and an arbitrary `recipient` to make the backend send a verification link for an account they do not own.

## 55. After Verification: State and Permissions

Inside the verifier:

```text
Validate token hash + expiry + unused
      |
      v
Check account and pending email scope
      |
      v
Mark email verified
      |
      v
Consume token
      |
      v
Commit transaction
```

If the application needs to unlock features after verification, publish a domain event/outbox **after the verified state has been durably committed**. Never grant permissions based on requesting the email, and never unlock privileges before the verification transaction commits.

## 56. SMTP Errors Should Not Leak to Public APIs

Example of what not to do:

```json
{
  "error": "Account exists but SMTP provider rejected
            student@example.net due to mailbox policy"
}
```

A public endpoint should return only a generic infrastructure error when acceptance fails. Operational logs can record the error category and opaque request/attempt IDs.

For an authenticated endpoint, the UI can display "Unable to accept the request right now, please try again later" without exposing the raw provider SMTP response.

### Do Not Stay Silent About Lost Work

Hiding SMTP errors from users does not mean ignoring them. Production must record outcomes, metrics, and alerts, and have retry or manual intervention workflows so users actually get a chance to receive the email.

## 57. Steps to Run the Practice Project Locally

A safe sequence:

1. Create a Spring Boot project with the dependencies from earlier.
2. Start a PostgreSQL test database or a compatible test database.
3. Create the schema via migrations (or a dedicated test schema).
4. Start an SMTP capture server on localhost port 1025.
5. Create a **synthetic unverified account** in `user_account`.
6. Configure `app.confirmation.base-url` to point to the local/staging confirmation page.
7. Start the Spring Boot application.
8. Send a POST request to the endpoint.
9. Open the SMTP capture server UI to inspect the email.
10. Extract the test link and confirm via `POST /confirm`.
11. Verify the account's verified state and that the token is consumed.

### Creating a Synthetic Account

Synthetic data example:

```sql
INSERT INTO user_account (
    id, email_canonical, email_verified_at
)
VALUES (
    '5b3a0fd5-a196-4cc0-b9a7-165829479de4',
    'student@example.net',
    NULL
);
```

**Never use real people's addresses when the SMTP client could send to the Internet.** With a local SMTP capture server, messages stay inside the test server; sending test traffic to mailboxes you do not own is strongly discouraged.

## 58. Sending HTTP Requests with curl

Example on a terminal supporting curl:

```bash
curl -i -X POST \
  'http://localhost:8080/api/email-confirmations/requests' \
  -H 'Content-Type: application/json' \
  -d '{"email":"student@example.net"}'
```

Demo response:

```http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Length: 0
```

In PowerShell 5.1, `curl` may be an alias for `Invoke-WebRequest`; use `curl.exe` or `Invoke-RestMethod` with the appropriate JSON body.

### Interpreting the Result

`202` does not guarantee:

- The mailbox has received the email.
- The token is still valid when the user opens it.
- The provider has delivered the message.
- The user has verified.

In the synchronous demo, the service *attempted* to invoke the mail sender when the account was eligible; however, the API contract does not expose those details and still lacks durability.

## 59. Inspecting the Email in the SMTP Sandbox

In an SMTP capture UI:

- Look for Subject "Xác minh địa chỉ email".
- Verify the recipient is the synthetic account.
- Verify `From` matches the test sender.
- Inspect both `text/plain` and `text/html`.
- Confirm the link belongs to the local/staging origin.
- Confirm there is no token in the Subject.
- Confirm there is no malicious user-supplied HTML.

An SMTP capture server lets you view raw MIME and HTML previews, but previews do not replace real testing in Gmail, Outlook, or Apple Mail if the product has client compatibility requirements.

## 60. Calling the Confirmation Endpoint

After grabbing the raw token from the test link in the SMTP sandbox, call:

```bash
curl -i -X POST \
  'http://localhost:8080/api/email-confirmations/confirm' \
  -H 'Content-Type: application/json' \
  -d '{"token":"PASTE_SYNTHETIC_TEST_TOKEN_HERE"}'
```

If the token is valid and unexpired:

```http
HTTP/1.1 204 No Content
Cache-Control: no-store
```

If the token is invalid, already used, or expired, for example:

```http
HTTP/1.1 400 Bad Request
Cache-Control: no-store
```

Never paste real tokens into issue trackers, screen recordings, or command history in production environments. In local practice, use only synthetic test accounts.

## 61. What to Inspect in the Database After Confirmation

Before confirmation:

```text
user_account.email_verified_at = NULL
email_verification_token.used_at = NULL
email_verification_token.expires_at > now
```

After confirmation:

```text
user_account.email_verified_at = timestamp
email_verification_token.used_at = timestamp
```

If the same token is submitted a second time, no further state change may occur and the verifier must reject it per contract. With multiple active tokens per account, the remaining tokens must also be blocked by `account.isEmailVerified()`.

## 62. Unit Test: Random Token and Consistent Hashing

```java
import org.junit.jupiter.api.Test;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import static org.junit.jupiter.api.Assertions.*;

class SecureTokenServiceTest {

    private final SecureTokenService service =
            new SecureTokenService();

    @Test
    void generatesUrlSafeTokensAndStableHashes() {
        String a = service.newToken();
        String b = service.newToken();

        assertNotEquals(a, b);
        assertTrue(a.matches("[A-Za-z0-9_-]+"));
        assertEquals(64, service.hash(a).length());
        assertEquals(service.hash(a), service.hash(a));
        assertNotEquals(service.hash(a), service.hash(b));
    }

    @Test
    void doesNotRepeatInSmallTestSample() {
        Set<String> tokens = IntStream.range(0, 1000)
                .mapToObj(i -> service.newToken())
                .collect(Collectors.toSet());

        assertEquals(1000, tokens.size());
    }
}
```

Testing 1,000 tokens only catches obvious implementation bugs; **it does not prove cryptographic security**. Security relies on `SecureRandom`/entropy and secret management policy, not a random sample test.

## 63. Unit Test: Expiry Boundary

Example testing entity logic with a fixed clock:

```java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class VerificationTokenExpiryTest {

    @Test
    void expiresExactlyAtDeadline() {
        Instant issuedAt =
                Instant.parse("2026-11-12T03:00:00Z");
        Instant expiresAt = issuedAt.plusSeconds(900);

        var token = new EmailVerificationToken(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "a".repeat(64),
                issuedAt,
                expiresAt
        );

        assertTrue(
                token.isUsableAt(expiresAt.minusNanos(1))
        );
        assertFalse(token.isUsableAt(expiresAt));
        assertFalse(token.isUsableAt(expiresAt.plusSeconds(1)));
    }
}
```

Never use `Thread.sleep(900_000)` to test TTL. With `Clock.fixed` and explicit `Instant` values, tests are fast and deterministic.

## 64. Web Test: Controller Returns 202 and Invokes Service

You can use standalone `MockMvc`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class EmailConfirmationControllerTest {

    @Test
    void requestReturnsAcceptedWithoutToken() throws Exception {
        ConfirmationRequestService requests =
                mock(ConfirmationRequestService.class);
        ConfirmationVerifier verifier =
                mock(ConfirmationVerifier.class);

        MockMvc mvc = MockMvcBuilders.standaloneSetup(
                new EmailConfirmationController(
                        requests, verifier
                )
        ).build();

        mvc.perform(post("/api/email-confirmations/requests")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"student@example.net"}
                                """))
                .andExpect(status().isAccepted())
                .andExpect(content().string(""));

        verify(requests).request("student@example.net");
        verifyNoInteractions(verifier);
    }
}
```

This test verifies controller routing and response shape; **it does not test Spring Security filters or rate limiting** unless those filters are registered in standalone setup. For authentication and CSRF, proper integration/web security tests are required.

## 65. Web Test: Validation

Test cases:

| Input | Expected |
| --- | --- |
| Empty JSON or missing email | 400 due to validation |
| `email=""` or whitespace only | 400 |
| Value not matching email format per validator | 400 |
| Exceeds maximum length | 400 |
| Malformed JSON syntax | 400 |
| Valid email but account does not exist | Generic 202 for public API |
| Email already verified | Generic 202 for public API |
| Exceeds rate limit | Per rate-limit policy, without leaking account |

To test that `@Valid` actually runs, use `@WebMvcTest` with a configured validator or supply `LocalValidatorFactoryBean` to standalone `MockMvc`. A test that calls the controller method directly **does not execute** validation annotations.

## 66. Unit Test: Verifier Consumes Token Once

Scenarios to cover:

1. Token hash found, unused, unexpired, account unverified → mark verified and consume.
2. Token does not exist → generic error.
3. Token already used → generic error.
4. Token expired right at the boundary → generic error.
5. Account already verified → do not grant privileges or act again.
6. Token belongs to a deleted account → generic error.
7. Account email/version changed → do not verify the new address with the old token.
8. Two threads consume the token concurrently → only one transaction succeeds.

The last test requires a DB integration test with real locking or an atomic UPDATE; mocking a repository sequentially does not prove concurrency correctness.

## 67. Database Integration Test: Uniqueness and Locks

With a PostgreSQL test database:

- Insert an unverified account.
- Issue a token and confirm the digest is stored, with no raw token appearing in the row.
- Run two concurrent confirm requests with the same token.
- Verify one request marks the account verified and consumes the token, while the other fails generically.
- Verify transaction rollback if updating either the token or the account fails.
- Verify indexes and unique constraints support efficient lookups.

Use transaction barriers/latches with finite timeouts; never rely on `Thread.sleep(...)` to induce a race.

When changing the account's email in another transaction, test that the verifier does not mistakenly verify the new address.

## 68. SMTP Integration Test with GreenMail

An SMTP test server can receive emails sent by `JavaMailSender` without touching the Internet:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import java.time.Instant;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class ConfirmationMailSenderIntegrationTest {

    @Test
    void sendsConfirmationToLocalSmtp() throws Exception {
        GreenMail smtp = new GreenMail(
                new ServerSetup(0, "127.0.0.1", "smtp")
        );
        smtp.start();

        try {
            JavaMailSenderImpl javaMailSender =
                    new JavaMailSenderImpl();
            javaMailSender.setHost("127.0.0.1");
            javaMailSender.setPort(smtp.getSmtp().getPort());

            var props = new ConfirmationProperties(
                    java.net.URI.create(
                            "https://staging-account.example.org"
                    ),
                    "mail-test@example.org",
                    java.time.Duration.ofMinutes(15)
            );
            ConfirmationMailSender mail =
                    new ConfirmationMailSender(
                            javaMailSender, props
                    );

            mail.send(new IssuedConfirmation(
                    UUID.randomUUID(),
                    "student@example.net",
                    "SYNTHETIC_TEST_TOKEN",
                    Instant.now().plusSeconds(900)
            ));

            assertTrue(smtp.waitForIncomingEmail(5000, 1));

            MimeMessage received =
                    smtp.getReceivedMessages()[0];
            assertEquals(
                    "Xác minh địa chỉ email",
                    received.getSubject()
            );
            assertTrue(
                    received.isMimeType("multipart/*")
            );
        } finally {
            smtp.stop();
        }
    }
}
```

The test requires a GreenMail dependency matching the project's Jakarta Mail namespace. This test verifies that local SMTP receives the message and checks basic Subject/MIME; **it does not prove Gmail/Outlook renders it properly** or that a user clicked it.

### Do Not Use Production Credentials in Tests

`JavaMailSenderImpl` in tests must point to localhost/sandbox; never pull host/password from a production profile. Never print raw test tokens in test logs if the suite archives output externally.

## 69. Inspecting MIME Parts and Links with a Parser

In advanced tests:

1. Traverse `MimeMessage` and nested `Multipart`.
2. Verify both `text/plain` and `text/html` parts exist.
3. Read the decoded UTF-8 content.
4. Verify both contain the verification prompt and the link holding the corresponding test token.
5. Check Subject and From.
6. Check that MIME contains no unexpected attachments.
7. Check that the raw token does not appear in Subject or custom headers.
8. Open in at least one real test mail client to confirm the CTA works.

Never compare raw MIME bytes directly because `Content-Transfer-Encoding` may vary and MIME boundaries are random.

## 70. Testing Account Enumeration

For public requests, test:

```text
Account exists, unverified -> generic 202
Account exists, verified   -> generic 202
Account not found         -> generic 202
Account in cooldown       -> generic policy response
```

Beyond status/body/headers, evaluate **timing distribution** and externally observable side effects. A single latency-comparison test does not prove timing-attack resistance; design an async/durable architecture first, then run load/security tests as appropriate.

Never return a `Location` URL that allows querying account state via a public request ID without authorization.

## 71. Testing Rate Limiting and Idempotency

Cases:

- Single double-click with the same idempotency key.
- Retry after HTTP timeout with the same key.
- Two different keys within the cooldown window.
- Same IP targeting multiple addresses.
- Same email targeted from multiple IPs.
- Two application instances receiving requests simultaneously.
- Restarting the rate limiter's backing store.
- Provider 4xx/5xx or quota exceeded.

The goal is not "never send a second email", but rather **preventing spam, avoiding duplicate requests outside policy, and preserving a valid resend path**.

## 72. Testing SMTP Failure and Recovery

A matrix:

| Scenario | Expected Outcome |
| --- | --- |
| SMTP connection refused before submission | Attempt fails, policy may retry |
| Invalid SMTP auth | Alert/config failure, do not retry continuously |
| Temporary SMTP rejection | Retry/backoff within limits |
| Permanent invalid recipient | Do not retry indefinitely |
| Timeout after DATA | `UNKNOWN`, do not blindly resend |
| Process crash after token commit before send (demo) | Acknowledge gap; production outbox must recover |
| Process crash after outbox commit before worker | Work item persists for processing |
| Process crash after SMTP accepted before status update | Avoid duplicates via attempt/reconciliation policy |
| Token expires before retry | Cancel or issue new request per policy |
| Account verified before worker sends | Suppress pending confirmation if policy allows |

Some SMTP providers offer APIs to look up message ID/status, though not every SMTP relay does; the `UNKNOWN` design must remain honest when evidence is lacking.

## 73. Testing Logging and Privacy

Use a fixture token:

```text
TEST-SYNTHETIC-CONFIRMATION-TOKEN
```

In unit/integration tests, capture application logs during:

- Token issuance.
- Successful `MailSender` send.
- SMTP throwing an exception.
- Invalid token submission.
- Rate limit triggered.
- Token/outbox cleanup.

Assert that the token never appears in logs or serialized exceptions; request bodies containing raw tokens on `/confirm` must also not be logged by middleware or tracing.

**Never treat a marker test as absolute security proof**: audit HTTP access logs, reverse proxies, APM, exception reporting, and email provider logs.

## 74. Testing Cleanup of Expired Tokens

The token table grows with requests:

```text
ISSUED -> CONSUMED
ISSUED -> EXPIRED
```

A scheduled cleanup job can delete used/expired token records after an appropriate retention period. If auditing is required, retain minimal non-sensitive metadata rather than keeping token hashes or raw links forever.

For encrypted raw tokens in a production outbox, cleanup must separate:

- Data needed for retries before expiry.
- Data already submitted.
- Data expired or canceled.
- Attempts with `UNKNOWN` outcome requiring reconciliation policy.

Never delete data currently in use by a worker without checking leases and retention.

## 75. Testing in Real Mail Clients

A verification email must work on mobile:

- Vietnamese Subject displays with proper diacritics.
- Link/CTA remains visible when images are disabled.
- `text/plain` contains the full link.
- Dark mode does not blend text into the background.
- Font size is large enough to read comfortably.
- CTA opens the confirmation page on the right domain.
- Confirmation page is not auto-triggered by link previews.
- Token is not truncated or altered during copy/paste.
- No sensitive personal data appears in the preheader.

GreenMail/Mailpit helps test MIME, but does not replace opening the email in Gmail, Outlook, Apple Mail, or clients representative of your users.

## 76. Observability: Metrics for HTTP Acceptance

Do not name a metric `emails_sent_total` in the controller, because at that point the email has not even been submitted.

Suggested metrics:

```text
confirmation.http.requests.total
confirmation.http.accepted.total
confirmation.http.rejected.total
confirmation.requests.rate_limited.total
confirmation.command.pending
confirmation.command.processing.lag
confirmation.token.issued.total
confirmation.token.consumed.total
confirmation.token.expired.total
confirmation.mail.outbox.pending
confirmation.mail.smtp.attempted.total
confirmation.mail.smtp.submitted.total
confirmation.mail.smtp.unknown.total
confirmation.mail.smtp.failed.total
```

These are application-defined metric names, not built-in Spring Mail defaults. You can use Micrometer/Actuator according to your project stack.

**Never put email addresses, raw tokens, full URLs, or high-cardinality account IDs into metric labels.** Specific details belong in appropriately access-controlled logs or audits.

## 77. Timestamps to Track

```text
requestedAt
acceptedAt
materializedAt
firstAttemptAt
submittedAt
tokenExpiresAt
confirmedAt
```

You can measure:

```text
Acceptance latency = acceptedAt - requestedAt
Dispatch lag       = firstAttemptAt - acceptedAt
SMTP latency       = smtp result time - firstAttemptAt
Time to verify     = confirmedAt - submittedAt
```

When `submittedAt` does not yet exist (e.g., SMTP still pending), do not record latency as 0. For public APIs that hide account existence, internal metrics may break down by status but must be protected.

### Illustrative SLO Target

> 99% of eligible requests are durably persisted within a short window; most eligible notifications are attempted via SMTP within a bounded window, barring provider throttling.

Never publish SLA numbers before measuring latency, SMTP quotas, mailbox feedback, and system scaling capacity.

## 78. Auditing Must Distinguish Request, Token Issuance, Send, and Verification

An audit record can include:

```text
event = EMAIL_CONFIRMATION_REQUEST_ACCEPTED
requestId = opaque ID
timestamp = ...

event = VERIFICATION_TOKEN_ISSUED
notificationId = opaque ID
timestamp = ...

event = MAIL_SMTP_SUBMITTED
attemptId = opaque ID
timestamp = ...

event = EMAIL_VERIFIED
accountId = opaque ID
timestamp = ...
```

Never emit `EMAIL_VERIFIED` solely because `MAIL_SMTP_SUBMITTED` was recorded. Likewise, a provider delivered event does not prove the user clicked the link.

Never store full raw SMTP transcripts or tokens in audit logs. If forensic evidence is needed, apply appropriate retention and access controls per data class.

## 79. Runbook: POST Returns 202 but No Email Arrives

Steps:

1. Identify the `requestId`/test actor and call timestamp (without needing a raw token).
2. Check whether the request command was persisted.
3. Check whether a worker claimed the command.
4. Check eligibility: pending account, already verified, or cooldown.
5. Check whether the outbox notification was materialized.
6. Check whether SMTP attempt logs show the mail sender was invoked.
7. Check provider acceptance/rejection, network, TLS, and auth.
8. Check the test mailbox and Spam/Junk/Quarantine folders.
9. Check whether the token expired before the email arrived.
10. Do not resend the same raw token if state or TTL is no longer valid.

For public endpoints, users only see a generic response. Internal investigations should use correlation IDs without exposing an API that lets strangers query account existence.

## 80. Runbook: User Receives Multiple Confirmation Emails

Causes to examine:

- Double-click / HTTP retries.
- Missing cooldown.
- Duplicate worker claim after lease timeout.
- Duplicate queue delivery.
- Retrying SMTP after an `UNKNOWN` outcome.
- Two application instances processing concurrently without a unique constraint.
- One account holding multiple unexpired tokens.

Remediation:

1. Locate the logical request ID and notification IDs.
2. Check whether a single notification had multiple SMTP attempts.
3. Determine which attempts were accepted by the provider.
4. Review idempotency key and cooldown policies.
5. Check worker concurrency and leases.
6. Consider reducing automatic retries on unknown outcomes.

Never delete attempt history to make dashboards look clean; retain enough evidence to see which layer produced the duplicate.

## 81. Runbook: User Clicks Link but Token Is Invalid

Check:

- Is the token actually present in the database digest lookup?
- Has the token expired?
- Was the token already used?
- Was the account already verified by another token?
- Did the user change their email between issuance and confirmation?
- Did the client rewrite or mis-encode the link?
- Did the frontend pass the entire `token` or truncate it at a special character?
- Was the token consumed by a security scanner or link preview hitting an automatic GET endpoint?

With unpadded Base64URL, tokens use URL-safe characters; even so, encode properly and preserve the exact string. Never return sensitive details about why a token is invalid to an unauthenticated caller.

### UX When a Link Expires

Display a clear message:

> This verification link is no longer valid. You can request a new email.

If the user is in a logged-in session, you can direct them to the authenticated resend flow to reduce account enumeration and spam. Never automatically generate a new token just because someone called a confirm endpoint with a random token.

## 82. Runbook: SMTP Authentication Fails

Symptoms:

```text
MailAuthenticationException
SMTP AUTH rejected
```

Investigation:

- Are host, port, and TLS mode right for the provider?
- Were credentials rotated or expired?
- Is the account authorized to send for the `From` domain?
- Was the secret injected into the right environment?
- Does the provider enforce IP, region, or permission restrictions?
- Is the application retrying continuously and causing an account lockout?

Never print passwords or raw AUTH exchanges to logs. On global configuration errors, pause aggressive retries and alert operations.

## 83. Runbook: SMTP Accepts but Nothing Appears in the Inbox

`JavaMailSender.send(...)` throws no error, yet the user says they haven't received it.

Possibilities:

- Provider deferred delivery.
- Mailbox provider bounced/rejected after submission.
- Landed in Spam/Junk/Quarantine.
- Suppression list or sender reputation issues.
- SPF/DKIM/DMARC alignment issues.
- Recipient mailbox rules.
- Link or email intercepted by a security gateway.

Do not assume this means the controller failed to run. Check provider feedback when available and guide the user to check the appropriate mailbox folders.

## 84. Runbook: Token Link Leaked in Logs

If a raw token is recorded in HTTP access logs or exceptions:

1. Stop further logging immediately.
2. Identify the source and storage scope (application, reverse proxy, APM, SIEM).
3. Revoke still-valid tokens per incident policy.
4. Delete or redact records wherever feasible.
5. Check whether the leaked token was used, if evidence exists.
6. Never copy raw tokens into tickets or chats during investigation.
7. Fix logging filters, URL handling, frontend referrer policy, and tests.

Never assume hashing tokens in the database protects you if raw tokens are sitting in access logs.

## 85. Runbook: Token Expires Before Email Is Sent

With an SMTP backlog:

```text
Token issued at 10:00, expires 10:15
SMTP worker executes at 10:20
```

If it still sends the token, the user receives a useless email.

Solution:

- Have the worker check `tokenExpiresAt` before sending.
- If expired, cancel the pending notification and purge the encrypted token payload per policy.
- If resending is needed, issue a new token tied to a new logical request, subject to cooldown/eligibility.
- Never silently extend the expiry of an already issued token without a security review.
- Monitor outbox lag against token TTL.

A 20-minute dispatch SLA makes no sense if tokens live only 15 minutes; TTL and capacity must be compatible.

## 86. Runbook: Duplicate Database Token Hash or Schema Mismatch

A 256-bit token from `SecureRandom` is extremely unlikely to collide naturally. If the `token_hash` unique constraint reports a conflict, investigate:

- Is the service running a deterministic or test token generator in production?
- Is a token being reused due to caching or global state?
- Is there a bug in hashing or encoding?
- Is the database schema truncating the hash string?
- Is a wrong test profile or seed data active?

Never catch the conflict, ignore it, and send the email anyway. If the hash was not persisted, the link sent out can never be verified. Retrying with a freshly generated token may be appropriate after classifying and handling the transaction.

## 87. API Request Checklist

- [ ] Endpoint uses POST; does not mutate state via arbitrary GET requests.
- [ ] DTO has validation and maximum lengths.
- [ ] Does not allow users to supply SMTP From/HTML/Subject.
- [ ] Account ownership/eligibility is clearly established.
- [ ] Public responses do not confirm account existence.
- [ ] Timing/channel side effects do not easily leak accounts.
- [ ] Rate limits, cooldowns, and abuse monitoring are in place.
- [ ] Idempotency policy handles double-clicks and retries.
- [ ] Returns `202` only after durable acceptance if that is the contract.
- [ ] Responses contain no raw tokens or provider details.
- [ ] Safe request IDs/log metadata are included.
- [ ] Sensitive responses/tokens are not cached outside policy.

## 88. Token and Database Checklist

- [ ] Tokens generated from `SecureRandom` with strong entropy.
- [ ] Tokens are URL-safe and contain no predictable data.
- [ ] Only hash/digest is stored in the verification-token table.
- [ ] TTL is validated using `Clock`/`Instant`.
- [ ] Token is bound to the exact account and email/version being verified.
- [ ] Single-use consumption via locking or atomic update.
- [ ] Expired/used/unknown tokens are rejected with a generic response.
- [ ] Unbounded token issuance on repeated resends is prevented.
- [ ] Raw tokens held in a durable outbox are encrypted.
- [ ] Cleanup runs after expiry/retention.
- [ ] Raw tokens, confirmation URLs, and sensitive template models are never logged.

## 89. Spring Mail Checklist

- [ ] `spring-boot-starter-mail` and Jakarta Mail namespace match.
- [ ] SMTP host/port/TLS/auth/timeouts match the provider.
- [ ] `From` domain is authorized to send.
- [ ] MIME includes equivalent `text/plain` and `text/html`.
- [ ] UTF-8 charset is configured for Vietnamese content.
- [ ] Links use the configured domain, never the `Host` header.
- [ ] HTML links are properly escaped and encoded.
- [ ] Email remains readable with images disabled and in dark mode.
- [ ] No OTP/token appears in Subject, filenames, or headers.
- [ ] SMTP test server and test mailbox are used before production.
- [ ] Long database transactions are never held open during SMTP send.

## 90. Outbox/Reliability Checklist

- [ ] Request is persisted before returning `202`.
- [ ] Command worker uses claim/lease and handles duplicates.
- [ ] Token digest and encrypted outbox entry are written atomically.
- [ ] Mail worker tracks attempt IDs and states.
- [ ] Retry/backoff is applied for classified temporary failures.
- [ ] Attempts with `UNKNOWN` outcome are never blindly resent.
- [ ] Pending work is suppressed per policy if the account is verified or the token expired.
- [ ] Retention/purge removes encrypted raw tokens.
- [ ] Metrics cover queue lag, SMTP failures, and token expirations.
- [ ] Worker restarts/failovers do not lose notifications.
- [ ] Exactly-once email delivery is never claimed without a supporting contract.

## 91. Testing Checklist

- [ ] Unit tests for token generation/hashing.
- [ ] Expiry boundary test with a fixed clock.
- [ ] Web MVC tests for `202` and validation.
- [ ] Generic behavior for unknown/verified emails.
- [ ] Concurrency tests for single-use token consumption.
- [ ] SMTP sandbox integration test.
- [ ] MIME plain/HTML/Subject/From tests.
- [ ] Failure tests for SMTP 4xx/5xx/timeouts.
- [ ] Process crash/restart tests for the outbox.
- [ ] Multi-instance rate limit/idempotency tests.
- [ ] Privacy/logging tests with a synthetic token.
- [ ] Real-client tests on representative Gmail/Outlook/mobile clients.
- [ ] Tests for cancellation/resend/expiry and account email changes.

## 92. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sending SMTP directly in controller | Slow requests, hard to retry | Service + durable outbox |
| Sending inside DB transaction | Long locks, rollback cannot unsend email | Short transaction, send after commit |
| Returning `200: Email delivered` after `send(...)` | False guarantee | `202` accepted + accurate layered telemetry |
| Returning 404 for nonexistent email | Account enumeration | Generic public response |
| Identical response with large latency difference | Timing enumeration | Async durable acceptance |
| No rate limiting | Victim spam and exhausted provider quota | Throttling/cooldown/abuse controls |
| Using `Random`/timestamp for tokens | Predictable tokens | High-entropy `SecureRandom` |
| Storing plaintext token in DB | DB leak exposes usable tokens | Hash; encrypt raw token if persisted |
| Missing `expiresAt`/`usedAt` | Links reusable forever | TTL and one-time consumption |
| Check-then-save without locking | Concurrent consumption race | Pessimistic lock/atomic update |
| Old-email token verifies new email | Verifies wrong address | Bind email/version to token |
| Treating `@Async` as durable | Tasks lost on restart | Outbox/durable broker |
| Retrying every SMTP exception | Duplicate emails, confusing links | Outcome/attempt classification |
| Still sending expired tokens | Useless links | Worker pre-send eligibility check |
| Sending HTML with `SimpleMailMessage` | Displays raw HTML | `MimeMessageHelper` |
| Reading base URL from `Host` header | Spoofed/phishing links | Configured allowlisted origin |
| Auto-confirming on GET link | Security scanners can trigger it | Confirmation page + POST/user action |
| Writing token in Subject/access logs | Secret leakage | Redact/avoid sensitive metadata |
| Testing with production SMTP and real emails | Misdirected sends/data leaks | Sandbox/allowlisted seed mailbox |

## 93. Exercise 1 — Create Endpoint Following the Contract

**Requirement:** implement `POST /api/email-confirmations/requests` accepting JSON with `email`, returning `202`, and never returning the raw token.

Criteria:

- Invalid JSON returns 400.
- Nonexistent and already-verified emails receive the generic response per public policy.
- Controller does not invoke `JavaMailSender` directly.
- A service is responsible for accepting the request and deciding the next step.
- Neither raw email nor token is leaked in the HTTP response.

**Hint:** start with the controller and a fake service in unit/web tests before wiring the database.

## 94. Exercise 2 — Generate Token with TTL

**Requirement:** use `SecureRandom` to generate a URL-safe token; persist the SHA-256 digest, `createdAt`, and `expiresAt`.

Criteria:

- Two issuances produce distinct tokens.
- Digest is deterministic for the same raw token.
- Raw token never appears in `email_verification_token`.
- Expires exactly when `now >= expiresAt`.
- Tests do not use `Thread.sleep`.

**Hint:** inject a `Clock` and use fixed test fixtures.

## 95. Exercise 3 — Single-Use Verification

**Requirement:** `POST /api/email-confirmations/confirm` marks the account verified and consumes the token atomically.

Criteria:

- Fresh/valid token verifies successfully.
- Expired/used tokens are rejected generically.
- Calling the token a second time produces no side effects.
- Two concurrent requests cannot both consume the token.
- A token for email A cannot verify email B after the account changes its address.

**Hint:** use optimistic/pessimistic locking or a conditional update with an explicit predicate.

## 96. Exercise 4 — Send Plain Text and HTML

**Requirement:** create a `MimeMessage` with a Vietnamese Subject, `text/plain`, and `text/html` containing the link.

Criteria:

- SMTP sandbox receives exactly one email in the test mailbox.
- Subject and From are correct.
- Both formats contain the same link and business text.
- Raw token does not appear in the Subject.
- Opening the email on a mobile mail client allows clicking the CTA.

**Hint:** use `MimeMessageHelper.setText(plain, html)` with UTF-8, and keep content limited to synthetic tokens.

## 97. Exercise 5 — Prevent Account Enumeration

**Requirement:** make the request API public-safe when an email does not exist or is already verified.

Criteria:

- Identical response shape per policy.
- Timing does not depend directly on SMTP submission.
- SMTP is called only in the worker for eligible accounts.
- No public status endpoint allows probing accounts.
- Rate limits do not inadvertently reveal account existence.

**Hint:** the endpoint only persists a durable request command; account lookup happens behind the async boundary.

## 98. Exercise 6 — Durable Outbox

**Requirement:** after HTTP returns 202, restarting the app still processes unfinished send requests.

Criteria:

- Durable command is committed before the response.
- Worker claims safely across two running instances.
- Token hash and encrypted outbox payload are saved atomically.
- SMTP sending occurs outside database transactions.
- Each attempt has an ID and status.
- Temporary failures are retried with backoff up to max attempts.
- `UNKNOWN` outcomes are never blindly retried.

**Hint:** test process crashes at every boundary: before command commit, after commit, after outbox commit, before SMTP, and after SMTP accepted.

## 99. Exercise 7 — Cooldown and Resend

**Requirement:** prevent sending three emails when a user double-clicks while still allowing valid resends after an interval.

Criteria:

- An idempotency key or logical request deduplication is implemented.
- Cooldown is enforced across multiple instances.
- Max active tokens or an old-token management policy is enforced.
- Public responses do not reveal account existence.
- Metrics count rate-limited/suppressed requests.

**Hint:** a static variable in the JVM is insufficient; use a shared store or coordinate with the API gateway.

## 100. Exercise 8 — Token Expires Before Worker Sends

**Scenario:**

```text
Token expires at 10:15
Outbox worker gets task at 10:20
```

**Requirement:** never send an email containing an already-expired link.

**Hint:** check token TTL immediately before SMTP. Mark the notification `EXPIRED/CANCELED` and purge the encrypted token per policy. If the user still needs verification, require a valid new request flow.

## 101. Exercise 9 — Do Not Verify the Wrong Address

**Scenario:** a user requests verification for `old@example.net`, then changes their pending email to `new@example.net` before clicking the link.

**Requirement:** the old token must not confirm the new email.

**Hint:** bind the token to `accountId + targetEmail/emailVersion`. The verifier checks that context still matches inside the transaction before updating `verifiedAt`.

## 102. Exercise 10 — Safe SMTP Testing

**Requirement:** build a test harness sending to a synthetic mailbox, reading Subject/HTML/plain text, and proving no production Internet access is required.

Criteria:

- `JavaMailSenderImpl` connects only to `127.0.0.1` and the sandbox port.
- No production secrets are used.
- Test data is synthetic.
- A MIME parser test checks the alternatives.
- Failure-path tests never log tokens.
- After tests, stop the SMTP server and clean up fixtures.

**Hint:** use GreenMail or an SMTP capture server compatible with your Jakarta Mail version.

## 103. Exercise 11 — SMTP Timeout After DATA

**Scenario:** the worker finished sending `DATA`, but the connection drops before receiving the final reply.

**Requirement:** distinguish `UNKNOWN` from definite `FAILED`.

**Hint:** use an attempt ledger, provider lookup if available, and a resend policy based on duplicate tolerance and TTL. Never use `catch (MailException) { resend(); }` for all cases.

## 104. Exercise 12 — Confirmation Page and Link Scanners

**Requirement:** the GET link renders a confirmation page without automatically consuming the token.

Criteria:

- GET on the page does not alter the verified state.
- POST confirms upon user action and per security policy.
- Tokens never appear in logs or analytics.
- UI handles expired or already-used links.
- Test with a mailbox/gateway that prefetches links if your product encounters them.

**Hint:** design the confirmation page with a strict referrer policy and avoid loading unnecessary third-party scripts.

## 105. Practice Project Acceptance Criteria

A complete application for this use case can be signed off across these layers:

| Layer | Question to Answer | Evidence |
| --- | --- | --- |
| API | Does POST follow the contract with a generic response? | MockMvc/web tests |
| Validation | Are malformed inputs and size limits rejected? | Validation tests |
| Security | Are tokens and account existence kept secret? | Review + negative tests |
| Token | Random, TTL, hashed, single-use? | Unit + DB integration |
| Data ownership | Is the token bound to the right account/email version? | Domain tests |
| Persistence | Are token and outbox committed atomically? | Transaction tests |
| SMTP | Is the message submitted with proper headers? | SMTP sandbox |
| MIME | Are plain/HTML and UTF-8 correct? | Jakarta Mail parser |
| Retry | Do temporary/unknown outcomes follow policy? | Failure injection |
| Abuse | Multi-instance rate limits and cooldowns? | Load/security tests |
| UX | Do links work on representative clients? | Seed mailbox tests |
| Operations | Are tracing/metrics/audits free of secrets? | Runtime review |

Do not assume every row passes just because two endpoints return 202/204 in Postman.

## 106. Choices That Vary by Project

**A. Sending verification after registration**

- Email comes from the pending registration account.
- Public requests need enumeration and rate-limit protection.
- The account is not yet granted permissions requiring a verified email.

**B. Verifying a new email address for a logged-in user**

- Backend gets the account from the authenticated principal.
- Token must bind to `pendingEmail` and version.
- May require re-authentication or notifying the old email address.

**C. Resending an order confirmation email**

- No email-ownership verification token is needed if it is purely informational.
- Requires authorization and idempotency keyed by `orderId`.
- Do not resend indefinitely on HTTP client retries.
- Use an order snapshot/template version when business rules require it.

**D. Confirming a sensitive transaction**

- An email link is only one factor in the confirmation flow.
- May require step-up authentication, session binding, and replay protection.
- Never allow a GET link prefetch to trigger a high-value side effect automatically.

The same phrase "confirmation email" can refer to very different goals. Throughout this lesson, **account email address verification** serves as the consistent case so every endpoint, token, and test shares unified semantics.

## 107. References

- Spring Framework — Email Integration: https://docs.spring.io/spring-framework/reference/integration/email.html
- Spring Boot — Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Security — Servlet Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP — Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html

These links help verify APIs and design principles for your version. The Spring Boot/JPA model in this article is an illustrative framework, with advanced production services and repositories explicitly noted as abstractions you must build yourself rather than built-in features of `JavaMailSender`.

## 108. Conclusion

To **create an endpoint to request a confirmation email** in Spring Framework Mail, start with an explicit REST contract: `POST /api/email-confirmations/requests` accepts validated input and returns a **generic** response, while `POST /api/email-confirmations/confirm` validates a **random, time-limited, single-use token** and updates the account inside a database transaction.

`JavaMailSender` and `MimeMessageHelper` help build and submit emails with proper `text/plain`, HTML, and UTF-8, yet **they do not replace authentication, authorization, anti-spam controls, token management, database consistency, or delivery guarantees**. The easiest part to write is calling `send(...)`; what determines production quality is knowing **who is allowed to request**, **which address is being verified**, **which tokens remain valid**, **whether the SMTP outcome is certain**, and **how to recover work after a crash**.

For a local demo, you can separate the token issuer transaction from the SMTP sender and test against a sandbox. For a public-production endpoint, advance to a **durable request command + idempotent token/outbox materialization + mail worker** so HTTP never depends on SMTP and never leaks accounts through timing. Track request, notification, attempt, token, and account states separately; retry deliberately, never send expired tokens, never store raw tokens in unprotected places, and never treat SMTP submitted as email verified.

Once you complete the unit, API, DB, SMTP, and security test suites and test the link on representative mail clients, you will have an email confirmation foundation that is **clear, extensible, and operable** in a Spring Boot application—rather than just an endpoint that "calls mailSender and hopes the email arrives".
