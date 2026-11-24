# Contact Verification Tokens: Purpose, Expiration, and Single Use

## 1. Goal and Account Lifecycle Context

When someone registers an account or requests an email/phone change, the application must distinguish **declared contact information** from **contact information proven accessible**. Entering `alice@example.org` into a form does not prove the submitter controls that mailbox. A standard workflow is to issue a **contact verification token** and send it over the channel being verified; the recipient presents the token back so the system can record control over that channel.

A secure contact verification token must satisfy **three simultaneous constraints**:

1. **Purpose-bound:** a token issued for `VERIFY_EMAIL` must never be accepted for `RESET_PASSWORD`, `CHANGE_EMAIL`, adding MFA, signing in, or any administrative action.
2. **Time-limited:** the token is valid only before `expires_at`. After that point, even if the token string is intact, the request must be rejected.
3. **Single-use:** after a **successful verification**, the same token cannot trigger the action a second time, even if two requests hit multiple instances concurrently.

In addition, the token must have enough randomness to be unguessable, bind to the right **account + target contact**, be delivered over the right channel, never leak into logs, and be checked atomically alongside the account state transition.

**This is not a login access token.** Verifying access to an email address or phone number does not automatically prove legal identity, is not equivalent to multi-factor authentication, and must never implicitly grant a login session or admin privileges.

### Learning Outcomes

After this lesson, you will be able to:
- Distinguish email/phone verification from password reset, login tokens, and sessions.
- Design a token schema with `purpose`, `subject`, `target_contact`, `expires_at`, and `consumed_at`.
- Generate high-entropy tokens with `SecureRandom` and store only the token digest.
- Verify expiry, account state, and target contact, and consume the token **inside a transaction**.
- Integrate `email_verified` / `enabled` state with Spring Security in a controlled way.
- Handle resends, contact changes, email link scanners, enumeration, race conditions, revocation, and security testing.

## 2. Distinguishing Contact State from Account Authentication State

An account can have an email address that has not yet been verified:

~~~text
New account
    |
    v
PENDING_EMAIL_VERIFICATION
    |  send link to email being verified
    |  accept only valid token
    v
EMAIL_VERIFIED
    |  per product policy
    v
ACTIVE

Email change:
ACTIVE(oldEmail verified)
    |
    v
PENDING_EMAIL_CHANGE(newEmail unverified)
    |
    +-- token sent to newEmail, current email kept
    |
    v
NEW_EMAIL_VERIFIED
    |
    v
ACTIVE(new email applied per policy)
~~~

There are two common options:
- **Block all sign-in** until the email is verified: `enabled=false` or `status=PENDING` in the `UserDetailsService` source.
- **Allow limited access while unverified:** open only safe operations and block sensitive actions; authorization must check the verification flag at the right level.

Both options require an explicit policy. Never treat `email_verified_at` as equivalent to `isAuthenticated()` on a request. `isAuthenticated()` describes the principal/session making the request; `email_verified_at` describes **proof of a contact channel** at the time it was verified.

**Changing email differs from new signup:** for an active account, the old email should remain the primary address until the new email verification completes; change requests usually require reauthentication/step-up and a notification to the old email.

## 3. "Purpose" Must Be Enforced on the Server

### 3.1. A Token Is a Scoped Capability

Examples of distinct purposes to separate:

| Purpose | Action after token is accepted | Interchangeable? |
|---|---|---|
| `VERIFY_SIGNUP_EMAIL` | Verify email for an account awaiting activation | No |
| `VERIFY_NEW_EMAIL` | Verify a new email for an existing account | No |
| `VERIFY_PHONE` | Record control over a phone number | No |
| `RESET_PASSWORD` | Permit the new-password reset flow | No |
| `CONFIRM_SENSITIVE_ACTION` | Permit a specifically bound action | No |
| `MAGIC_LOGIN` | Authenticate a session if the product intentionally designs magic links | No |

**A token grants only the exact capability designed at issuance.** An email verification link must never carry password-reset privilege just because both links travel via email.

### 3.2. The Server Never Trusts a Client-Modified Purpose

Suppose the token stored in the DB looks like:

~~~json
{
  "accountId": 42,
  "purpose": "VERIFY_SIGNUP_EMAIL",
  "targetEmail": "alice@example.org",
  "expiresAt": "2030-01-01T10:15:00Z",
  "consumedAt": null
}
~~~

A client tampering with `purpose=RESET_PASSWORD` in query parameters or the request body cannot alter what the token is good for. The password-reset handler must query **server-side records with purpose `RESET_PASSWORD`**, not just any token with a matching string.

A token record should bind at least:
- **Subject:** immutable account ID, not only email;
- **Destination:** the contact address being proven;
- **Purpose:** the sole permitted action;
- **Lifecycle:** issued, expiry, consumed/revoked;
- **Context:** tenant/app/channel or contact-change session if needed.

In multi-tenant applications, the same email may appear in different tenants. Therefore keys must also bind `tenant_id` or an account namespace when applicable.

## 4. Random Tokens, Format, and Storage

### 4.1. Generating Unpredictable Tokens

For an **email verification link**, you can use 32 bytes from `SecureRandom` (256 bits), Base64URL-encoded without padding into 43 characters:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

SecureRandom rng = new SecureRandom();
byte[] bytes = new byte[32];
rng.nextBytes(bytes);
String rawToken = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(bytes);
~~~

This is an **illustrative snippet** meant to sit inside a Java class/method, not a standalone file because it lacks a class declaration. Generate fresh bytes on every call; never construct tokens from timestamps, emails, truncated UUIDs, `Math.random()`, or sequential IDs.

32 random bytes from a CSPRNG provide a massive search space. The rule of “sufficient entropy” matters far more than making a string look long and complex. Do not embed the account ID or email inside the raw token; keep metadata on the server.

### 4.2. Store Only the Digest, Never the Raw Token

Sound workflow:

~~~text
Issue:
    rawToken = SecureRandom(32 bytes) → Base64URL
    tokenDigest = SHA-256(rawToken)
    DB stores only tokenDigest + purpose + account + target + expiry
    send rawToken to target email

Redeem:
    receive rawToken
    tokenDigest = SHA-256(rawToken)
    lookup digest in DB
    verify purpose/account/target/expiry/unused
    transition state in transaction
~~~

For instance, store `token_digest_hex` as 64 hex characters. Because the raw token has **256 bits of random entropy**, plain SHA-256 for lookup in this example is appropriate. If you send a **short 6-digit OTP**, entropy is drastically lower: bare SHA-256 cannot resist offline guessing if the DB leaks. OTPs require strict rate limiting, attempt caps, very short TTLs, and storage via HMAC with a server-side key/pepper or dedicated OTP mechanisms suited to the risk model.

**Do not confuse token hashing with password hashing.** Human-chosen passwords have low entropy and need work-factor password hashing like Argon2id/bcrypt/PBKDF2. A 256-bit random token does not need password-style slow hashing when the goal is avoiding plaintext storage.

### 4.3. Should Token ID Be Split Out?

You can use a `tokenId.secret` format indexed in the DB by `tokenId` and verify only the secret digest on that row, or use the digest of the entire random token as the lookup key. Both approaches are valid if cleanly defined:
- `tokenId` is a lookup identifier, **not a credential**;
- `secret`/raw token is the secret to protect;
- the token is verified against the stored purpose, destination, and account;
- responses never reveal whether a token exists.

The example at the end of this lesson chooses **lookup by SHA-256 of the 43-character raw token** to avoid splitting two parts.

## 5. Expiration: How Long Is a Token Valid?

### 5.1. Exact Rule

With `issued_at = T0` and `expires_at = T0 + TTL`, at time `now`:

~~~text
Valid if:
    now < expires_at
    AND consumed_at IS NULL
    AND revoked_at IS NULL (if present)
    AND purpose/account/target match

Invalid if:
    now >= expires_at
    OR token already consumed/revoked
    OR account/target state no longer valid
~~~

**At the exact instant `expires_at`, the token must be rejected.** Some distributed systems allow a small clock skew, but any allowance must be an explicit policy rather than uncontrolled TTL extension.

### 5.2. How Should TTL Be Chosen?

No single TTL fits every product. Illustrative *reference* policies (not mandatory standards):

| Verification type | Illustrative TTL | Rationale |
|---|---:|---|
| Signup email verification link | 15–60 minutes | Balances time to open email against link exposure window |
| New email verification link | 10–30 minutes | Higher risk of identity/contact modification |
| 6-digit SMS OTP code | 3–10 minutes | Short codes need tighter guessing windows |
| Sensitive action confirmation | 5–15 minutes | Reduces stale-link exposure |

Organizations must choose lifetimes based on risk, email/SMS latency, UX, internal rules, and rate-limit controls. A longer TTL is never automatically safer because even high-entropy tokens are vulnerable if leaked: an attacker uses the **real token** rather than brute-forcing it.

### 5.3. Use Trusted Server/DB Time

- In Java, prefer `Instant` and an injectable `Clock` rather than browser timezones.
- Across multiple instances, synchronize clocks with NTP; in SQL statements, use consistent `CURRENT_TIMESTAMP`/DB clock.
- Never accept `expiresAt` from a client-supplied request.
- Never reset or extend TTL whenever the user refreshes the verification page.
- Resend issues a **new token**, with rules to invalidate or expire old tokens.

If email delivery is delayed, do not “extend” an already-issued raw token via client parameters; provide a rate-limited resend flow with a fresh timestamp.

## 6. "Single-Use" Must Be Guaranteed Atomically

### 6.1. Why `find` Followed by `save` Is Not Enough

Two nearly simultaneous requests can arrive:

~~~text
Instance A                         Instance B
  SELECT token unused                SELECT token unused
  → sees unused                      → sees unused

  UPDATE user verified               UPDATE user verified
  UPDATE token consumed              UPDATE token consumed

  → both A and B believe they consumed the token successfully
~~~

If a token authorizes a higher-stakes action (changing email, granting access, or confirming a transaction), double processing causes duplicate side effects or security breaches.

**Single-use** does not mean “delete the token on the client after clicking” or “set a flag after finishing.” It means **on the server, at most one request is allowed to complete the state transition**.

### 6.2. Safe Database Mechanisms

Two common patterns:
- **Transaction + `SELECT ... FOR UPDATE`:** lock the token row until commit; verify unused and unexpired, then update both account and token inside the same transaction.
- **Compare-and-set (`UPDATE ... WHERE consumed_at IS NULL ... RETURNING`):** only one request wins the claim to consume. Account updates and token consumption must occur in the **same transaction** to avoid consuming the token without updating the account.

For email verification, the transaction should uphold these invariants:

~~~text
BEGIN TRANSACTION
    lookup/lock valid token
    confirm matching purpose, account, destination
    confirm account still pending for matching contact
    update account.email_verified_at/status
    update token.consumed_at
    invalidate related pending verification tokens if required
COMMIT

If any step fails:
    ROLLBACK
    no half-finished state
~~~

**Wrong ordering or broken transaction boundaries cause business bugs.** For instance, marking a token used, committing, and then calling another service to update the account can leave the token spent while the account stays unverified. Distributed systems require dedicated outbox/saga/idempotency designs.

### 6.3. Replay After Success

The first valid redemption updates the account and token; subsequent attempts receive a generic message such as “Link is invalid or has expired.” Never disclose whether the token was already used or which account it belonged to. If UX needs an idempotent “already verified” response, do so only after checking the current account state **without leaking information**, and never re-run sensitive side effects.

## 7. Target Binding to the Destination Contact

Many vulnerabilities stem not from guessing tokens, but from **binding tokens to the wrong data**.

### 7.1. Account ID Differs from Email String

Tokens should bind to a stable account (`account_id`) and the **address awaiting verification**. Never identify an account by email string alone because:
- the email can be changed after the token was issued;
- the email may collide across tenants, or be recycled by the mail provider;
- email strings require a consistent canonicalization policy;
- an attacker could change the email between issuance and redemption to verify a new address improperly.

Example:

~~~text
T0: account 42 pendingEmail = alice@example.org
T1: issue token X for account 42 + alice@example.org
T2: account 42 changes pendingEmail = mallory@example.org
T3: click old token X

CORRECT: reject X because token target differs from pending contact.
WRONG: mark account 42 emailVerified=true regardless of current email.
~~~

### 7.2. New Email Verification Cannot Reuse Old Tokens

When changing email:
1. Require the signed-in user to reauthenticate/step-up based on risk.
2. Store `pending_email` **without promoting it to the login/primary email yet**.
3. Issue a `VERIFY_NEW_EMAIL` token bound to **`pending_email`** and the current account.
4. Notify the old email address; consider requiring confirmation from the old email in high-risk systems.
5. When a valid token is redeemed, inside a transaction verify `pending_email` still matches, then update the email and verified status per policy.
6. Invalidate tokens from prior change requests, update login identifiers/sessions if needed, and send a confirmation notice.

Never accept `VERIFY_SIGNUP_EMAIL` as `VERIFY_NEW_EMAIL` just because both relate to `purpose=email`. Action scopes must be granular enough to prevent cross-flow reuse.

### 7.3. Canonicalize Emails Carefully

OWASP recommends defining a consistent canonicalization policy. Domains are generally case-insensitive; local parts have more complex rules. Do not automatically strip dots or `+tag` suffixes as in Gmail for every provider, and do not blindly lowercase the local part if doing so could conflate distinct accounts. Store both the original value for display and the policy-canonicalized value for comparison, ensuring the exact same rules apply across signup, login, recovery, and contact verification.

## 8. What Should a Verification Token Record Store?

PostgreSQL example:

~~~sql
CREATE TABLE app_accounts (
    id                 BIGINT PRIMARY KEY,
    email_canonical    VARCHAR(320) NOT NULL,
    email_verified_at  TIMESTAMPTZ,
    status             VARCHAR(24) NOT NULL
                       CHECK (status IN ('PENDING', 'ACTIVE', 'DISABLED'))
);

CREATE TABLE contact_verification_tokens (
    id                 BIGSERIAL PRIMARY KEY,
    token_digest_hex   CHAR(64) NOT NULL UNIQUE,
    account_id         BIGINT NOT NULL
                       REFERENCES app_accounts(id),
    purpose            VARCHAR(40) NOT NULL,
    target_contact     VARCHAR(320) NOT NULL,
    issued_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at         TIMESTAMPTZ NOT NULL,
    consumed_at        TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    CONSTRAINT chk_contact_token_expires
        CHECK (expires_at > issued_at)
);

CREATE INDEX idx_contact_tokens_account_purpose
    ON contact_verification_tokens(account_id, purpose);
~~~

This is an **illustrative** schema, not tables auto-created by Spring Security. Production needs migrations, proper transactions/indexes, ownership/tenant columns, personal-data deletion policies, current contact status, email uniqueness constraints if required by business rules, and scheduled cleanup of stale rows.

Key fields:
- `token_digest_hex`: digest of the random raw token, not the raw token;
- `purpose`: exact permitted action, never self-escalating;
- `account_id`: specific account, avoiding email-only binding;
- `target_contact`: the contact value being proven;
- `issued_at`/`expires_at`: time bounds;
- `consumed_at`: proof the token was processed once;
- `revoked_at`: invalidation on contact change, resend, anomaly detection, or account deletion.

**SQL queries must check all validity conditions**; a token with `consumed_at IS NULL` must still be rejected if `revoked_at` is non-null, it is expired, or the account is no longer in the expected state.

## 9. Standalone Java 17 Demo: Purpose, TTL, and Single Use

The following example runs **without Spring**, focusing on in-memory logic to illustrate boundaries. It generates a 256-bit raw token, stores only the SHA-256 digest, binds the token to account/target/purpose/expiry, and uses `ConcurrentHashMap.computeIfPresent` to prevent consuming the same key twice within **one JVM**.

**Limitations:** single-JVM memory is not a database transaction. The demo **does not send real email**, does not mutate users in a DB, and does not guarantee cross-instance safety or atomic account updates. Section 10 shows how to implement this in Spring/JDBC production code.

File `ContactVerificationDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class ContactVerificationDemo {

    enum Purpose {
        VERIFY_SIGNUP_EMAIL,
        VERIFY_NEW_EMAIL
    }

    record Entry(
            long accountId,
            String targetEmail,
            Purpose purpose,
            Instant expiresAt) {
    }

    static final class MutableClock extends Clock {
        private final AtomicReference<Instant> current;

        MutableClock(Instant start) {
            current = new AtomicReference<>(start);
        }

        void advance(Duration duration) {
            current.updateAndGet(t -> t.plus(duration));
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) {
                throw new IllegalArgumentException("UTC only");
            }
            return this;
        }

        @Override
        public Instant instant() {
            return current.get();
        }
    }

    static final class TokenService {
        private final SecureRandom random = new SecureRandom();
        private final Clock clock;
        private final ConcurrentHashMap<String, Entry> rows =
                new ConcurrentHashMap<>();

        TokenService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        String issue(
                long accountId,
                String targetEmail,
                Purpose purpose,
                Duration ttl) {

            if (accountId <= 0 || targetEmail == null
                    || targetEmail.isBlank()
                    || purpose == null || ttl == null
                    || ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("Invalid issuance");
            }

            byte[] bytes = new byte[32];
            random.nextBytes(bytes);

            String rawToken = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(bytes);

            String digest = sha256Hex(rawToken);

            Entry entry = new Entry(
                    accountId,
                    targetEmail,
                    purpose,
                    clock.instant().plus(ttl));

            if (rows.putIfAbsent(digest, entry) != null) {
                throw new IllegalStateException("Duplicate token digest");
            }
            return rawToken;
        }

        boolean consume(
                String rawToken,
                long accountId,
                String targetEmail,
                Purpose purpose) {

            if (rawToken == null || rawToken.length() != 43
                    || !rawToken.matches("[A-Za-z0-9_-]{43}")) {
                return false;
            }

            String digest = sha256Hex(rawToken);
            AtomicBoolean accepted = new AtomicBoolean(false);

            rows.computeIfPresent(digest, (key, entry) -> {
                boolean matches = entry.accountId() == accountId
                        && entry.targetEmail().equals(targetEmail)
                        && entry.purpose() == purpose
                        && clock.instant().isBefore(entry.expiresAt());

                if (matches) {
                    accepted.set(true);
                    return null; // Remove atomically for this map key.
                }
                return entry;
            });
            return accepted.get();
        }

        private static String sha256Hex(String input) {
            try {
                byte[] bytes = input.getBytes(StandardCharsets.US_ASCII);
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(bytes);
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException("SHA-256 unavailable", e);
            }
        }
    }

    public static void main(String[] args) {
        MutableClock clock = new MutableClock(
                Instant.parse("2030-01-01T10:00:00Z"));
        TokenService service = new TokenService(clock);

        String token = service.issue(
                42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL,
                Duration.ofMinutes(15));

        System.out.println("wrong-purpose=" + service.consume(
                token, 42, "alice@example.org",
                Purpose.VERIFY_NEW_EMAIL));
        System.out.println("wrong-target=" + service.consume(
                token, 42, "mallory@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));
        System.out.println("first=" + service.consume(
                token, 42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));
        System.out.println("replay=" + service.consume(
                token, 42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));

        String expiring = service.issue(
                42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL,
                Duration.ofSeconds(5));
        clock.advance(Duration.ofSeconds(5));

        System.out.println("expired=" + service.consume(
                expiring, 42, "alice@example.org",
                Purpose.VERIFY_SIGNUP_EMAIL));
    }
}
~~~

Compile and run:

~~~bash
javac ContactVerificationDemo.java
java ContactVerificationDemo
~~~

**Exact stdout:**

~~~text
wrong-purpose=false
wrong-target=false
first=true
replay=false
expired=false
~~~

Explanation:
- Wrong purpose or target **does not consume** the valid token; the goal is to reject cross-flow/cross-contact misuse.
- The first qualifying call returns `true` and removes the map entry; the second returns `false`.
- Exactly at `expiresAt`, the token is rejected because `Instant.isBefore` returns `false`.
- `MutableClock` is used only in the demo to test expiry without `sleep`; in a real app inject `Clock.systemUTC()` or read the DB clock.
- Never print raw tokens, avoiding leaking secrets to stdout.
- Map logic provides **single-use only within one process**. Do not treat it as proof of transactional safety across multiple servers/DBs.

## 10. Spring Boot 3.x + Spring Security 6.x: Transactional Verification

In real Java/Spring applications, tokens are stored in a database, and `@Transactional` ensures updating the account and marking the token consumed **commit or roll back together**. Below is a concrete repository/service example using **Spring JDBC + PostgreSQL** with the schema from Section 8.

### 10.1. Dependencies

In a `pom.xml` with a Spring Boot 3.x parent or BOM, using Java 17+:

~~~xml
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
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

This is a **dependency snippet for a Spring Boot project**, not a standalone complete POM. You need a configured PostgreSQL datasource, migrations creating the tables in Section 8, and separate token-issuance/email-sending flows.

### 10.2. Service Consuming Email Verification Tokens

File `src/main/java/com/example/account/EmailVerificationService.java`:

~~~java
package com.example.account;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmailVerificationService {

    private final JdbcTemplate jdbc;

    public EmailVerificationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    record TokenRow(
            long id,
            long accountId,
            String targetEmail) {
    }

    @Transactional
    public boolean verifySignupEmail(String rawToken) {
        if (rawToken == null ||
                !rawToken.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        String digest = sha256Hex(rawToken);

        // FOR UPDATE serializes use of this token row.
        List<TokenRow> rows = jdbc.query("""
                SELECT id, account_id, target_contact
                  FROM contact_verification_tokens
                 WHERE token_digest_hex = ?
                   AND purpose = 'VERIFY_SIGNUP_EMAIL'
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                   AND expires_at > CURRENT_TIMESTAMP
                 FOR UPDATE
                """, (rs, rowNum) -> new TokenRow(
                    rs.getLong("id"),
                    rs.getLong("account_id"),
                    rs.getString("target_contact")),
                digest);

        if (rows.size() != 1) {
            return false;
        }

        TokenRow token = rows.get(0);

        // Bind confirmation to the SAME account + pending email.
        int updated = jdbc.update("""
                UPDATE app_accounts
                   SET email_verified_at = CURRENT_TIMESTAMP,
                       status = 'ACTIVE'
                 WHERE id = ?
                   AND email_canonical = ?
                   AND status = 'PENDING'
                   AND email_verified_at IS NULL
                """, token.accountId(), token.targetEmail());

        if (updated != 1) {
            throw new IllegalStateException(
                    "Account state no longer permits verification");
        }

        int consumed = jdbc.update("""
                UPDATE contact_verification_tokens
                   SET consumed_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                   AND expires_at > CURRENT_TIMESTAMP
                """, token.id());

        if (consumed != 1) {
            throw new IllegalStateException(
                    "Verification token could not be consumed");
        }

        // Once verified, older signup verification links should not work.
        jdbc.update("""
                UPDATE contact_verification_tokens
                   SET revoked_at = CURRENT_TIMESTAMP
                 WHERE account_id = ?
                   AND purpose = 'VERIFY_SIGNUP_EMAIL'
                   AND id <> ?
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                """, token.accountId(), token.id());

        return true;
    }

    private static String sha256Hex(String input) {
        try {
            byte[] bytes =
                    input.getBytes(StandardCharsets.US_ASCII);
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(bytes);
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                    "SHA-256 is required", e);
        }
    }
}
~~~

**Why is this genuinely single-use inside a DB transaction?**

- `SELECT ... FOR UPDATE` holds a row lock on the token row in PostgreSQL. Under standard `READ COMMITTED` isolation, two requests presenting the **same token** cannot both pass the unused check and commit as two independent redemptions.
- `UPDATE app_accounts` checks that the account is still `PENDING`, its current email matches the token's target, and it is not yet verified. An old token cannot verify a changed address.
- `UPDATE contact_verification_tokens` marks the token consumed only if it is still unconsumed, unrevoked, and unexpired at update time.
- Both updates run inside one transaction via `@Transactional`. If the account update succeeds and the token update fails, `IllegalStateException` is a runtime exception and **Spring rolls back the entire transaction**.
- Upon success, the server revokes remaining pending signup verification links for that account. In a race between **two different tokens for the same account**, only one transaction is allowed to move `PENDING → ACTIVE`; the other fails and rolls back.
- `@Transactional` takes effect when the method is invoked through a Spring proxy from another bean; self-invocation inside the same instance can bypass the transaction proxy. Production must configure the transaction manager for the right datasource.
- Outer handlers should map state errors and expired tokens to a generic public message **that does not disclose whether the account exists**. Server logs should aid investigation without logging raw tokens.

This example implements only `VERIFY_SIGNUP_EMAIL`. For `VERIFY_NEW_EMAIL`, the update logic must differ: match `pending_email`, keep the old email until completion, and possibly require step-up auth before issuance. Do not copy the `status='PENDING'` predicate for already-active users.

### 10.3. Spring Security Access Control and Unverified Accounts

A verification endpoint must be reachable by **unauthenticated** users (for example, a pending account has no session yet), but that does not mean opening every API route.

Example `SecurityFilterChain` in a Servlet project:

~~~java
package com.example.account;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/verify-email",
                                "/verification-result", "/error")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Keep default CSRF protection** for form POSTs; the GET link only opens the verification page. In an app using `UserDetailsService`, you can map `account.status == ACTIVE` and `email_verified_at != null` to `UserDetails.isEnabled()` to block login before verification (if policy requires). However, `permitAll()` only waives login requirements for the endpoint—it **does not make the internal token validation secure on its own**.

When account state changes in the DB, existing sessions may still hold an earlier `Authentication`. On contact revocation/change or account disabling, evaluate session invalidation or revalidation on sensitive endpoints; do not expect a DB flag to take immediate effect in every active session automatically.

### 10.4. Email Links, GET, and POST Must Have Distinct Responsibilities

The link sent via email might look like:

~~~text
https://app.example.org/verify-email?token=<random-token>
~~~

In a real link, `<random-token>` is replaced by the newly issued raw token. **Never build URLs from untrusted `Host` or `X-Forwarded-Host` headers**; use a fixed `publicBaseUrl` from configuration or a hostname allowlist.

Design the flow as:

~~~text
GET /verify-email?token=...
    └─ Render the "Confirm email" page
       Do not consume token.
       Referrer-Policy: no-referrer
       Cache-Control: no-store
       No third-party scripts/tracking pixels.
       Hidden token form field + CSRF token.

User clicks confirm button:
POST /verify-email (token + CSRF)
    └─ EmailVerificationService.verifySignupEmail(...)
       Transaction updates account and consumed_at
       Redirect to a URL WITHOUT the token
~~~

**Why not activate immediately on GET?** Anti-spam gateways, email security scanners, link previewers, and browser prefetchers can open links automatically. If GET has side effects, the token may be consumed before the user intentionally clicks confirm.

**Why must email links still be protected against URL leakage?** A token in a query string can appear in access logs, browser history, analytics, and `Referer` headers. Enforce redaction in proxies/apps/monitoring, `Referrer-Policy: no-referrer`, an appropriate CSP, zero third-party assets on pages holding the token, and short TTLs. Some systems put tokens in URL fragments and let browser scripts move them into a POST; that prevents the token from hitting server logs on the initial GET, but does not by itself prevent XSS, so full defenses remain necessary.

### 10.5. Issuing Tokens and Sending Email Over a Side Channel

A proper issuance flow must:
1. Issue only for accounts in an eligible state; validate the canonical target email on the server.
2. Rate-limit by account, email/IP/device, and resend count.
3. Generate a new raw token via CSPRNG and store **digest + metadata**.
4. Build the notification email to the **exact stored target**, using an HTTPS URL from trusted configuration.
5. Keep raw tokens out of HTTP responses, app logs, traces, and DB rows.
6. If sending asynchronously, use a **transactional outbox**/queue with clear expiry and retry/idempotency rules. Never send the email before DB commit and dispatch a link whose token does not yet exist.
7. For resend rules: you may revoke prior tokens, issue a new one, and update notifications; avoid email storms or an unbounded number of concurrently valid tokens.

Email notifications should clarify **that this is contact verification**, not a password, and that the user need not act if they did not initiate the request. For SMS, short OTP codes require strict TTLs, rate limits, failed-attempt caps, anti-guessing defenses, and secure code storage.

## 11. Resend and Contact-Change Flows

### 11.1. Resend Should Never "Resend the Raw Token" from the DB

If you store only digests, you **cannot recover the raw token**. A resend flow generates a new raw token, stores a new digest, and sends a new link.

There are two clear strategies:
- **Only latest valid:** revoke all older verification tokens for the same account/purpose/target before issuing the new token.
- **Several pending valid:** allow a bounded number of links to remain valid until the first one succeeds, at which point the remaining ones are revoked.

Only-latest is easier to reason about securely, though out-of-order email delivery can cause a user to click a recently superseded link. Choose the UX based on email/SMS latency and risk; **never accidentally leave unlimited concurrent links valid**.

### 11.2. Changing Email While an Old Link Is Still in Flight

When `pending_email` changes:
- invalidate tokens bound to the old email;
- create a new token with the new `target_contact`;
- at redemption, verify the token's target matches the account's current pending contact;
- if already active, apply the new address **only after verification**, never overwriting the previously verified email prematurely.

Separate verifying the new address from alerting the old address of the change. For high-risk actions, consider requiring confirmation from both the old and new emails or adding MFA/step-up.

### 11.3. "Single-Use" Differs from "Idempotent"

An endpoint may return a friendly message if the user clicks an already-used link again, **without re-executing side effects**. For example:
- First click: the account becomes verified and an audit entry is recorded.
- Second click: the server does not re-run the verification transaction; it can display “This link is no longer valid.”
- If business needs dictate an idempotent presentation, check account state separately without leaking information to unauthenticated clients.

**At-most-once action execution** differs from **at-most-once HTTP 200**. In practice, the HTTP response of a successful request can be lost and the browser may retry; the server must handle retries safely.

## 12. Preventing Token Exposure and Abuse

### 12.1. Where Tokens Can Leak

| Leak vector | Risk | Control |
|---|---|---|
| URLs in access logs/proxies/APM | Anyone with log access can steal the raw token | Redact query parameters/headers containing tokens |
| Browser history | Link remains in history on shared machines | Short TTL; keep tokens out of URLs after POST |
| Referer to third-party sites | URL can leak to analytics or external images | `Referrer-Policy: no-referrer`, no third-party assets |
| Compromised inbox | Attacker can click links for the mailbox owner | Strengthen email account security; short-lived links |
| Mail send logs or support tickets | Staff see links containing raw tokens | Log notification IDs, never full URLs |
| Unencrypted HTTP | Token sniffed in transit | HTTPS + certificate validation |
| XSS on verification page | Scripts on the real origin can read the token | Output escaping, CSP, XSS defenses, JS protection |
| Client shares link in chat | Another recipient can redeem the token | Explain links are secrets; enforce TTL and single-use |

Never place raw tokens in analytics events, monitoring spans, or error messages. Nor does `tokenDigest` belong in client responses; internally log an opaque `verificationRequestId` that cannot serve as a credential.

### 12.2. User Enumeration

A resend endpoint must not return:
- “This email is not in our system” in one case;
- “Verification link sent to Alice's account” in another.

Instead, return a generic response such as **“If the address is eligible, we will send instructions”**, apply consistent response timing behavior, and enforce rate limiting and abuse monitoring. During signup, duplicate-email UX policies may vary by product, but account-existence leakage must be evaluated explicitly.

### 12.3. Spam and Brute-Force Defense

- Limit issuances, resends, and redemptions per account/email/IP/device and time window.
- For short OTPs, enforce failed-attempt caps/locks; do not rely solely on TTL.
- Never let a request send email to an address other than the server-held pending `target_contact`.
- Use CAPTCHA/risk-based checks under abuse, but never as a substitute for token entropy or authorization.
- Write sanitized audit logs for issue, resend, successful/failed consume, revoke, and account changes.

### 12.4. A Verified Contact Does Not Stay With the Same Person Forever

Email addresses can change owners, be hijacked, or be reclaimed by providers. Phone numbers can be recycled or SIM-swapped. Thus `verified` proves control **at verification time**, not permanent identity. For high-risk operations, use MFA/step-up, change alerts, and stronger recovery mechanisms.

## 13. Are JWTs Suitable for Contact Verification Tokens?

You can encode purpose, account, target, and expiration inside a **signed JWT**. However:

- A JWT signature prevents tampering with claims, not **copying the whole token**.
- `exp` bounds lifetime, but **does not automatically make a JWT single-use**.
- Enforcing single-use requires storing `jti`/nonce server-side, checking unused/unrevoked state, and transitioning state atomically.
- You must validate issuer, audience, signing algorithm, and exact purpose/target; never trust claims merely because the payload decodes.
- JWTs easily leak email/PII into URLs or logs inside a decodable payload.

For the simple use case of **email link verification**, a 256-bit opaque token storing a digest + metadata is usually **simpler to manage for expiry, revocation, and single-use**. Do not pick JWT merely to avoid a DB while still expecting single-use guarantees.

## 14. Common Mistakes

1. **Using the same token for email verification and password reset.** Breaks token scoping; always separate `purpose` explicitly.
2. **Looking up the account solely by client-supplied `email`.** Leads to misbinding, especially across email changes or multi-tenancy.
3. **Using timestamps or truncated UUIDs as secrets.** More predictable than necessary; use a CSPRNG.
4. **Storing raw tokens in the DB.** Turns a DB leak into a credential leak; store digests of random tokens.
5. **Treating SHA-256 alone as enough for a 6-digit OTP.** Short codes can be brute-forced offline; use low-entropy protections.
6. **Allowing tokens to work at or after `expires_at`.** The exact rule is `now < expires_at`, not `now <= expires_at`.
7. **Marking consumed outside the account update transaction.** Can burn the token while leaving the account unverified, or apply twice.
8. **`SELECT` then `UPDATE` without locks or conditions.** Two instances can execute the same action concurrently.
9. **Checking token validity without checking the current target.** Old links can mistakenly verify a newly entered contact.
10. **Auto-activating on HTTP GET.** Email scanners and link previewers can open links before the user.
11. **Logging verification URLs in logs/analytics or loading third-party images on the page.** Leaks tokens via URLs or `Referer`.
12. **Building links from arbitrary `Host` headers.** Host-header poisoning can point links at an attacker's domain.
13. **Allowing resend to keep hundreds of active links valid.** Expands attack surface, confuses UX, and invites spam.
14. **Returning different errors for existing vs non-existing emails.** Enables account enumeration.
15. **Treating `email_verified` as an authenticated principal.** Proof of contact does not create a session or satisfy MFA.
16. **Switching primary email before the new email is verified.** Can break recovery or enable account takeover.
17. **Assuming JVM `synchronized`/`ConcurrentHashMap` works across a cluster.** Use DB transactions and atomic compare-and-set across instances.
18. **Assuming account status inside a session never becomes stale.** Disabled/revoked accounts after login need a revalidation policy.
19. **Ignoring that emails/phones can change owners.** Verification status is a point-in-time claim.
20. **Handling idempotent retries by re-running side effects.** Browser/network retries must never execute the action twice.

## 15. Test Matrix

| Case | Secure outcome |
|---|---|
| Token issued and sent to right email, within TTL | Verifies successfully **once**, updates contact |
| Replay same token after success | Rejected; does not change state again |
| Two concurrent POSTs with same token (2 replicas) | Only one transaction completes; the other makes no change |
| Valid token with wrong purpose | Rejected; does not reset password or change email |
| Valid token with mismatched account ID | Rejected |
| Valid token after pending contact changed | Rejected; does not verify the new contact |
| Expired token, `now == expires_at` | Rejected |
| Token revoked due to resend/change | Rejected |
| Fake 43-char token matching format | Rejected; does not reveal account existence |
| Token with extra characters or wrong format | Rejected before querying DB |
| Account already active or disabled, no longer pending | No state transition performed |
| Account verification SQL update fails after row lock | Rolls back; token is not consumed alone |
| Token update fails after account update | Rolls back both account and token |
| Two valid tokens for same account used concurrently | One account transition; sibling token triggers no second action |
| GET on link by email security scanner | Does not consume token |
| Verification POST missing CSRF in session-based form | Rejected by CSRF policy |
| Request logs containing token URL | Redaction protects raw token |
| Rapid repeated resends | Rate-limited; no unbounded spam |
| Query for non-existent email | Anti-enumeration response |
| Link generation under forged `Host` header | Issued URL still uses trusted base URL |
| Email verification token submitted as login token | Does not create a login session |
| Repeated guesses on 6-digit OTP | Strict attempt cap/rate limiting |
| Email changed while old link is in flight | Old token invalidated; only new target can verify |
| Login after verification | Account policy permits; session created **by separate auth flow** |

**Concurrency testing is critical:** single-threaded unit tests never catch “two requests both saw unused.” With PostgreSQL, write a real integration test using at least two connections/transactions and a barrier to force contention, then assert that **one** account update succeeded with no duplicate side effects.

In Spring Security, testing `permitAll` proves only that unauthenticated callers can reach the route—it **does not prove the token verification logic is secure**. Test domain services and DB transactions directly, plus end-to-end tests covering links, CSRF, and browser flows.

## 16. Implementation Checklist

- [ ] Define token purposes using explicit enums/constants; never use tokens as login/session credentials.
- [ ] Bind tokens to the exact account ID + current contact + tenant/context + purpose.
- [ ] Generate raw tokens from a high-entropy CSPRNG; never print/log them, store only digests in DB.
- [ ] Enforce explicit TTL with `now < expires_at` and check revoked/consumed flags.
- [ ] Enforce unique digests in DB with transactions/row locks or conditional `UPDATE`.
- [ ] Commit account state updates and token consumption together; handle rollback cleanly.
- [ ] Resend, contact change, and account deletion invalidate obsolete tokens.
- [ ] Unverified accounts are restricted appropriately by login and authorization policies.
- [ ] Email changes require reauthentication/step-up, notify the old email, and verify the new email.
- [ ] Public GET renders only the confirmation page; POST performs mutations with CSRF per browser architecture.
- [ ] HTTPS links use a trusted base URL, `no-referrer`, `no-store`, and no third-party assets.
- [ ] Rate-limit issuance/resend/redemption; errors and responses prevent enumeration.
- [ ] Never return raw tokens in HTTP responses of resend API requests.
- [ ] Email/SMS delivery has retries, outbox/idempotency, and latency monitoring.
- [ ] Short OTP codes enforce attempt caps and dedicated storage protections.
- [ ] Tests cover expiry, replay, wrong purpose, wrong target, concurrent requests, rollback, and multi-instance runs.
- [ ] Audit logs exclude full emails/tokens/verification URLs; retention and access controls are in place.

## 17. Key Takeaways

A secure contact verification token can be summarized concisely:

~~~text
ValidContactVerification =
    matching secret
    + matching purpose
    + matching account and pending target
    + matching tenant/context
    + not expired
    + not revoked / not consumed

Successful execution =
    contact state change
    AND consumed token
    IN ONE transaction
~~~

**Purpose limits what can be done, TTL limits how long it lasts, and single-use limits how many times it works.** All three must be enforced server-side alongside token secrecy and accurate contact binding. Email/phone verification is one step in the account lifecycle, not a blanket mechanism for granting login access.

## 18. References

1. [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html): single-use, expiry, email ownership, canonicalization, anti-enumeration, and email changes.
2. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): secure token generation/storage, purpose-limited flows, URL leakage, Host headers, and rate limiting. Similar token-protection principles apply to contact verification, though the two purposes remain distinct.
3. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): identity, reauthentication, responses, and account security.
4. [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): limiting credential exposure and managing secrets.
5. [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction boundaries and rollback rules.
6. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `permitAll`, `authenticated`, security chains.
7. [Spring Security 6.5 API — UserDetails](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/userdetails/UserDetails.html): `isEnabled` and account state during login.
8. [Oracle Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): strong random bytes for tokens.
9. [Oracle Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 digests.
