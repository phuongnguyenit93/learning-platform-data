# Masking or Hashing Recipient Data in Logs

## 1. The problem: monitoring mail sending without putting recipient addresses in logs

In a **Spring Framework Mail** application, operations teams often need to answer: was the order confirmation email sent, which step failed, how many retries ran, is the provider slow, or is an incident affecting a batch of jobs? These questions are usually answered via application logs, distributed tracing, metrics, and database state.

A recipient address can identify a person or organization. Writing raw addresses into every log line replicates that data across many systems:

~~~text
Order / Notification application
           |
           +-- JavaMailSender / SMTP client
           |
           +-- Application logs
                    |
                    +-- Container stdout
                    +-- Log collector / agent
                    +-- Centralized log storage
                    +-- Dashboard / alerts
                    +-- Export to incident ticket
                    +-- Backup / archive
~~~

An email address appearing in logs can be accessed by far more people than business records in a database. Logs also typically have different retention and access controls, so **never treat logs as a safe place to store full recipient emails**.

Avoid doing this:

~~~java
log.info("Sending notification to {}", recipientEmail);
log.warn("Mail to {} failed: {}", recipientEmail, ex.getMessage());
~~~

Even with SLF4J parameterized logging, the real value is still written into the log after formatting. `{}` only defers string interpolation; **it does not hide data**.

Instead, an operationally sufficient log looks like:

~~~text
event=mail_submission_finished
mailJobId=job-7f3a
notificationType=ORDER_RECEIPT
recipientToken=v2:0e8c4f... (truncated HMAC)
attempt=2
result=SMTP_ACCEPTED
durationMs=724
~~~

Here, `mailJobId` is a random job identifier, and `recipientToken` is a policy-governed correlation pseudonym. If you only need to trace a single job, **you do not even need `recipientToken`**.

**Goal of this lesson:** choose when to omit emails, when to partially mask, and when to use keyed HMAC; implement safely with Spring Mail; prevent leaks via exceptions, MIME, SMTP debug, and observability systems; and test that logs contain no real recipient data.

## 2. Distinguishing business data, logs, metrics, and audits

Not every storage layer serves the same role.

| Component | Purpose | Should It Contain Full Email Addresses? |
|---|---|---|
| Customer database | Managing users and contact details | Possibly, under access controls and data policy |
| Mail outbox/job store | Sending to the right recipient and retrying | Possibly, must be protected with retention limits |
| Application log | Debugging errors, tracing execution flow | No by default |
| Metrics | Counting successes, errors, and latency | No; avoid email-based labels |
| Distributed tracing | Tracking requests, dependencies, latency | No by default |
| Security audit | Recording significant actions and actors | Store only what is needed under strict controls |
| Support/admin UI | Authorized incident lookup | May display conditionally; never treat as public log |

With a stable job ID, logs may need nothing more than:

~~~text
jobId=job-7f3a notificationType=ORDER_RECEIPT status=RETRY
errorCode=SMTP_TEMPORARY_FAILURE attempt=3
~~~

Authorized staff can look up the corresponding job in the business system to see the recipient. This is usually a better design than attaching email addresses to every log event.

### Data minimization before masking

Priority order:

1. **Omit** recipient fields whenever unnecessary.
2. Use job/event IDs that do not embed emails or guessable customer IDs.
3. If operators need a small visual hint, consider masking.
4. If correlating the same recipient across multiple jobs is necessary, consider keyed HMAC.
5. Expose real email addresses only in lookup channels with explicit authorization, auditing, and retention.

Never “hash just for the sake of hashing” when metrics or logs have no reason to identify the recipient. Removing data at the source beats sending it and trying to scrub it centrally later.

## 3. Identifying every place that can leak recipients

When an application uses `JavaMailSender`, addresses can surface in many places beyond explicit developer log lines.

| Source | Example Leaked Data | Control Strategy |
|---|---|---|
| Message creation log | `to=user@example.test` | Omit or replace recipient |
| SMTP error/exception | Server echoes rejected address | Log normalized error code |
| Stack trace with exception message | Address, domain, SMTP response | Limit Throwable logging; sanitize |
| JavaMail/Jakarta Mail debug | `RCPT TO:<user@example.test>` | Disable protocol debug in production |
| `MimeMessage.toString()` / raw message | To/Cc/Bcc headers, body | Never dump the entire message |
| Outbox payload dump | Recipient inside JSON | Allowlist logged fields |
| MDC/baggage | `recipient=user@example.test` | Add only safe correlation IDs |
| HTTP request/response logging | Email in body/query | Redact or exclude route/fields |
| Queue/broker client logging | Payload containing recipient | Never log raw payloads |
| Tracing span attributes | `messaging.destination.recipient` | Use non-sensitive attributes |
| Metrics labels | `recipient=...` | Never put emails into labels |
| Log/alert enrichment | Joining email from DB via jobId | Never auto-enrich PII by default |

**`Bcc` is especially sensitive.** Even though `Bcc` normally does not appear as a standard header in the recipient's delivered email, `Bcc` lists can still appear in application inputs, SMTP envelopes, exceptions, or debug traces. Never mask only `To` and overlook `Cc`/`Bcc`.

### Example of an unexpected leak path

~~~java
try {
    mailSender.send(message);
} catch (Exception ex) {
    log.error("Cannot send mail", ex);
}
~~~

No email address is concatenated into that log message, yet the exception or a nested cause from the SMTP server **may contain the recipient address**. Therefore `log.error(..., ex)` is not safe for data privacy by default.

Similarly, logging a request DTO such as `log.debug("Request {}", request)` can cause `record.toString()` or Lombok `@ToString` to print recipient, `Bcc`, or payload data. Never assume the `DEBUG` log level excuses unprotected data.

## 4. How masking, plain hashing, and HMAC differ

Three mechanisms address different needs:

| Approach | Illustrative Example | Benefit | Limitation |
|---|---|---|---|
| Omit | `jobId=job-7f3a` | Exposes no recipient | Cannot group logs by recipient |
| Masking | `a***@example.test` | Human-readable for manual support | Still identifiable; leaks domain and first char |
| Plain SHA-256 | `sha256(email)` | Same input yields same digest | Vulnerable to dictionary guessing over predictable emails |
| Keyed HMAC-SHA-256 | `v2:8d...` | Hard to recompute without key; supports correlation | Still a linkable pseudonym |
| Lookup random token | `recipientRef=7a5c...` | Independent of email structure | Requires access-controlled mapping store |

For production logging:

- **Masking** fits when operators need a controlled visual hint.
- **HMAC** fits when you need a stable correlation key without exposing raw emails in logs.
- **Plain SHA-256 of an email** is usually a poor security choice for preventing address inference.

### Why `SHA-256(email)` does not reliably protect emails

Email addresses are predictable and often appear in public lists or breached datasets. Someone can:

1. Gather a list of candidate emails.
2. Compute SHA-256 for each email using the app's canonicalization rule.
3. Compare digests against values in logs.
4. Determine which people appear in the logs.

No “hash decryption” is needed—only testing candidates. Thus, **never treat an unkeyed hash as strong anonymization** for recipients in logs.

HMAC uses a **secret key**:

\[
\operatorname{recipientToken} =
  \operatorname{HMAC}_{K}(\operatorname{canonicalEmail})
\]

Someone holding the logs without key `K` cannot compute digests for candidate email lists in the same way. However, if the key leaks, dictionary matching becomes possible again. HMAC also does not stop someone with application access from requesting a token for a known address unless invoking the function is controlled.

## 5. Masking: when operators need partial visibility

A support interface might show:

~~~text
minh.anh@example.test -> m***@example.test
admin@small-company.test -> a***@small-company.test
~~~

This reduces full-address exposure for operators, yet **does not eliminate identifiability**:

- Displaying the domain can identify a small organization.
- A one-character local-part or rare name remains easy to guess.
- Combining send timestamp, notification type, and tenant can pinpoint the recipient.
- Consistently masked addresses can still be linked across log entries.

For stronger protection, mask the domain as well (`m***@***`), show only `[redacted-email]`, or omit it entirely.

### Minimal illustrative masking function

~~~java
public final class RecipientMasker {
    private RecipientMasker() {
    }

    public static String mask(String email) {
        if (email == null || email.isBlank()) {
            return "[recipient-unavailable]";
        }

        int at = email.lastIndexOf('@');
        if (at <= 0 || at == email.length() - 1) {
            return "[recipient-invalid]";
        }

        String local = email.substring(0, at);
        String domain = email.substring(at + 1);

        // Illustrates policy for a simple mailbox only.
        String first = local.substring(0, 1);
        return first + "***@" + domain;
    }
}
~~~

This function is **not a full RFC email parser** and still exposes the domain. It is suitable only for illustrating masking on a simple, application-validated mailbox. In real applications, parse mailboxes properly first or default to `[redacted]` when input is untrusted.

Never “mask” a multi-address string by finding the last `@` and assuming every recipient was handled. For `To/Cc/Bcc` lists, process **each structured mailbox individually**.

## 6. When should domains be omitted from logs?

Suppose an email goes to `cfo@very-small-firm.example`. After masking to `c***@very-small-firm.example`, the domain still identifies the exact company, and the timestamp plus email type can reveal business relationships.

Cases where domains should be fully masked or replaced with tokens:

- Healthcare, financial, HR, or security alert emails.
- Systems emailing small businesses with custom domains.
- Subscriptions for sensitive recipient groups.
- Logs shared broadly with vendors, external support, or multiple teams.
- Aggregate domain reports not genuinely needed for operations.

If deliverability metrics by provider/domain are needed, consider **controlled domain buckets** such as `GMAIL`, `OUTLOOK`, `OTHER` from a fixed allowlist, while still evaluating inference risks for rare groups. Never put arbitrary domains into metric labels due to cardinality and data-leak risks.

## 7. Canonicalizing email addresses before computing HMAC

HMAC over identical byte sequences always yields the same output under the same key. Yet strings representing the same apparent address can differ:

~~~text
User@Example.COM
User@example.com
 user@example.com 
"User" <User@example.com>
~~~

To correlate by mailbox, the application must define a **canonicalization rule** before hashing. That rule must stay stable and be applied consistently everywhere tokens are generated.

### Do not arbitrarily lowercase the entire email

Under Internet mail addressing specifications, **domains** are case-insensitive; the **local-part** may theoretically have system-specific matching rules at the receiving server. Many popular providers treat local-parts case-insensitively, but you must not generalize that across every domain.

For example:

~~~text
User@example.com
user@example.com
~~~

If the application blindly converts both to `user@example.com`, their tokens will match even if an organization's or provider's mailbox policy does not treat them as equivalent. A safe default without evidence to the contrary is **preserving the local-part** and normalizing only the domain.

Similarly, do not automatically:

- Strip `+tag` suffixes after a plus sign: plus addressing does not have identical semantics across all providers.
- Remove dots from local-parts because one specific provider ignores dots.
- Strip quotes in quoted local-parts with ad-hoc regexes.
- Transform Unicode local-parts with normalization unaligned with protocol and product definitions.

### Example canonicalization with clear boundaries

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.net.IDN;
import java.util.Locale;

public final class RecipientCanonicalizer {
    private RecipientCanonicalizer() {
    }

    public static String canonicalMailbox(String input)
            throws AddressException {
        if (input == null || input.isBlank()) {
            throw new AddressException("Recipient is required");
        }

        InternetAddress parsed = new InternetAddress(input, true);
        parsed.validate();

        String mailbox = parsed.getAddress();
        if (mailbox == null) {
            throw new AddressException("Mailbox is missing");
        }

        int at = mailbox.lastIndexOf('@');
        if (at <= 0 || at == mailbox.length() - 1) {
            throw new AddressException("Invalid mailbox");
        }

        String localPart = mailbox.substring(0, at);
        String domain = mailbox.substring(at + 1);
        String asciiDomain;

        try {
            asciiDomain = IDN.toASCII(
                    domain, IDN.USE_STD3_ASCII_RULES)
                    .toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException ex) {
            throw new AddressException("Invalid domain");
        }

        return localPart + "@" + asciiDomain;
    }
}
~~~

This example uses Jakarta Mail's `InternetAddress` to extract the mailbox, preserve `localPart`, and normalize the domain to lowercase IDNA ASCII. This is an **illustrative application rule**, not a parser/validator covering every SMTPUTF8 variant, quoted local-part, or internationalized address. For systems accepting full internationalized emails, pick a suitable library and canonicalization policy, test against real data, and preserve backward compatibility.

### Canonicalization is a product decision

If the system already stores recipients under a stable, unique `recipient_id`, correlating by `recipient_id` can be simpler than canonicalizing emails. Still, that ID can itself be pseudonymous personal data and must be protected. Never use an email address as a correlation key simply because it is handy.

Changing canonicalization means **the same mailbox can receive a new token**. Version the policy—for example `v2`—so tokens produced by incompatible algorithms are never compared mistakenly.

## 8. Generating recipient tokens with HMAC-SHA-256 in Java

When you need to recognize that multiple mail jobs target the same recipient without logging the real address, you can use HMAC-SHA-256 with a secret key owned by the observability system.

Basic design:

~~~text
Valid recipient
       |
       v
Canonicalize mailbox
       |
       v
UTF-8 bytes
       |
       v
HMAC-SHA-256(secret key, bytes)
       |
       v
Take first 128 bits if policy permits
       |
       v
recipientToken = v1:<32 hex characters>
~~~

Java 17+ code example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RecipientTokenService {
    private static final String ALGORITHM = "HmacSHA256";
    private static final int TOKEN_BYTES = 16;

    private final SecretKeySpec key;
    private final String keyVersion;

    public RecipientTokenService(
            byte[] secretKey,
            String keyVersion) {
        Objects.requireNonNull(secretKey, "secretKey");
        if (secretKey.length < 32) {
            throw new IllegalArgumentException(
                    "Use at least 32 bytes of key material");
        }
        if (keyVersion == null || keyVersion.isBlank()) {
            throw new IllegalArgumentException(
                    "Key version is required");
        }

        this.key = new SecretKeySpec(
                secretKey.clone(), ALGORITHM);
        this.keyVersion = keyVersion;
    }

    public String token(String recipient)
            throws jakarta.mail.internet.AddressException {
        String canonical =
                RecipientCanonicalizer.canonicalMailbox(recipient);

        try {
            // Do not share a Mac instance across threads.
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            byte[] digest = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));

            byte[] shortDigest =
                    Arrays.copyOf(digest, TOKEN_BYTES);
            return keyVersion + ":"
                    + HexFormat.of().formatHex(shortDigest);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                    "Recipient tokenization unavailable", ex);
        }
    }
}
~~~

Key points:

- `HmacSHA256` is a widely used HMAC algorithm.
- The key comes from a secret source, never hardcoded in source code.
- Each call creates a fresh `Mac` instance; never share a mutable `Mac` across mail executor threads.
- Input is UTF-8 encoded after canonicalization.
- `HexFormat` requires Java 17+.
- `TOKEN_BYTES=16` keeps the first 128 bits of the HMAC output for shorter tokens; if greater collision margin is desired, retain the full 32 bytes.
- `keyVersion` is a public version label; **it must never contain the actual key**.

128 bits of HMAC is ample for typical log-correlation workloads, though any design should evaluate identifier counts and token length. If protocol-level integrity or security guarantees are required, never assume truncation is appropriate without analysis.

### Generate keys with a CSPRNG, not guessable passwords

Example generating 32 bytes:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

byte[] key = new byte[32];
new SecureRandom().nextBytes(key);
String encoded =
        Base64.getEncoder().encodeToString(key);

// Store encoded in secret manager; never log or commit the value.
~~~

This snippet **only illustrates key generation**. Never generate a fresh random key inside an application startup constructor on every deployment, as instances would produce different recipient tokens and break stable correlation. Keys must come from a lifecycle-managed secret store.

### Separate the recipient-logging key from other secrets

Never reuse:

- An SMTP password as the HMAC key.
- A shared JWT signing key.
- A database encryption key.
- Hardcoded test-fixture secrets in production.

If the HMAC key leaks, you must be able to rotate it without disrupting SMTP credentials or other authentication systems. Key separation limits blast radius per incident.

## 9. Supplying the HMAC key to Spring without exposing its value

One option is creating the `RecipientTokenService` bean via Spring configuration reading from a secret store or infrastructure-injected environment. Java configuration example:

~~~java
import java.util.Base64;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class RecipientLoggingConfiguration {

    @Bean
    RecipientTokenService recipientTokenService(
            Environment environment) {
        String encoded = environment.getRequiredProperty(
                "MAIL_LOG_HMAC_KEY_B64");
        String version = environment.getRequiredProperty(
                "MAIL_LOG_HMAC_KEY_VERSION");

        byte[] key = Base64.getDecoder().decode(encoded);
        try {
            return new RecipientTokenService(key, version);
        } finally {
            java.util.Arrays.fill(key, (byte) 0);
        }
    }
}
~~~

`Environment` reads properties provided to the application. Infrastructure must ensure `MAIL_LOG_HMAC_KEY_B64` and `MAIL_LOG_HMAC_KEY_VERSION` exist at runtime, supplied via a secret manager, mounted secret volume, or deployment injection.

Zeroing out the temporary byte array limits residual copies in memory, though it **cannot guarantee all copies of the secret are completely erased**, because the Base64 input is a Java `String` and may already exist in the configuration system. Never put secrets into `toString()`, configuration logs, or exceptions.

### Why not use a shared public salt “instead of HMAC”?

Some code writes:

~~~java
// Not HMAC and offers no defense against dictionary attacks
// if the salt is stored alongside logs or known publicly.
sha256("public-salt:" + email)
~~~

If an attacker knows the salt, they can still test candidate emails. To resist dictionary matching against leaked logs, you need a **secret key** or a controlled pseudonymization service, not merely a public salt.

### Different policies per environment

Use separate keys for development, staging, and production so tokens cannot be compared across environments using logs alone. If tenants require strict isolation, use per-tenant keys or a properly designed key-derivation scheme while accounting for operations and key rotation.

Never write a mapping table between tokens and real addresses into logs; doing so defeats the purpose of HMAC.

## 10. HMAC produces pseudonyms, not absolute anonymization

A stable token can still link multiple events:

~~~text
recipientToken=v1:ab12... notificationType=PASSWORD_RESET
recipientToken=v1:ab12... notificationType=PAYMENT_RECEIPT
recipientToken=v1:ab12... notificationType=SECURITY_ALERT
~~~

Even without seeing the email address, someone reading logs knows these events happened to **the same recipient**. Combining tenant, timestamp, notification type, and job metadata can reveal user behavior.

Therefore:

- Treat HMAC recipient tokens as **pseudonymous data** requiring protection, not fully anonymized data.
- Log tokens only on events that genuinely require correlation.
- Restrict permission to query/search tokens and export results.
- Avoid using tokens as metric labels or publicly visible tracing attributes.
- Shorten retention if long-term correlation is unnecessary.
- Consider scoping tokens per job/campaign instead of system-wide when correlation is needed only locally.

### Scoping tokens by purpose

One global token across all email types lets you find every job for a recipient, yet increases linkability:

~~~text
System-wide scope:
    HMAC(K, canonicalEmail)

Purpose-scoped:
    HMAC(K, "newsletter:" + canonicalEmail)
    HMAC(K, "security:" + canonicalEmail)
~~~

If the system does not need to know that a newsletter subscriber is the same person receiving security alerts, **do not share the same token across both data domains**. Cleaner key-management practice derives a subkey per scope with a proper KDF; if prepending a purpose prefix to the HMAC input, define unambiguous serialization and version the policy.

## 11. Key rotation and correlation windows

A stable HMAC key yields stable tokens. When rotating from `v1` to `v2`:

~~~text
Before rotation:
recipientToken=v1:839a...

After rotation:
recipientToken=v2:af57...
~~~

These two tokens **cannot be compared directly**, even though they derive from the same address. This is both a security property and an operational impact to plan for.

Common rotation strategy:

1. Define rotation cadence per organizational policy.
2. Issue a new key from the secret store with a new `keyVersion`.
3. Roll out the same configuration across all replicas generating correlated tokens.
4. Emit the new token for events after cutover.
5. Keep the old key only if approved transition lookups are needed, inside a tightly restricted key store.
6. Revoke/delete the old key once no longer needed and permitted by policy.

**Never log both `v1` and `v2` tokens for every recipient just to bridge history**, as doing so undermines rotation benefits and increases linkability. When approved cross-window investigations are required, run lookups in an access-controlled tool rather than exposing mappings in general logs.

### Key rotation vs. canonicalization version

`keyVersion` changes when the key changes; `canonicalizationVersion` changes when mailbox normalization rules change. Large systems may document both in design specs or token metadata. Never assume “different tokens mean different recipients” if tokens were generated under incompatible versions.

## 12. Multiple recipients: To, Cc, and Bcc need the same policy

An application may send emails to:

~~~java
helper.setTo(toRecipients);
helper.setCc(ccRecipients);
helper.setBcc(bccRecipients);
~~~

Never log raw `Arrays.toString(toRecipients)` or `MimeMessage` objects during debugging. If recipient volume must be observed, log **counts** and types:

~~~text
event=mail_submission_start
mailJobId=job-7f3a
recipientCount=3
toCount=1
ccCount=1
bccCount=1
notificationType=MONTHLY_REPORT
~~~

If per-recipient tokens are required, process each mailbox explicitly and consider:

- Never log a full list of thousands of tokens for a bulk email; logs bloat and linkability increases.
- `Bcc` must never leak simply because debug mode is enabled.
- Some SMTP exceptions include rejected recipient lists; never call `toString()` on address arrays or exceptions when logging.
- If exact recipient counts are sensitive in small contexts, use buckets (1, 2–5, 6–20, over 20) instead of exact counts.

For personalized notifications, a clean design is **one job per recipient** with its own `jobId`. That is a mail-sending architecture choice, not a requirement to always emit recipient tokens.

## 13. Structured logging: emit only approved fields

A more effective leak-prevention strategy than “find-and-replace every email in strings” is **designing an allowlisted log schema**.

Example event at send start:

~~~text
event=mail_submission_started
jobId=job-7f3a
notificationType=ORDER_RECEIPT
templateVersion=v3
attempt=1
provider=PRIMARY_SMTP
~~~

On completion:

~~~text
event=mail_submission_finished
jobId=job-7f3a
notificationType=ORDER_RECEIPT
result=SMTP_ACCEPTED
attempt=1
durationMs=608
~~~

On failure:

~~~text
event=mail_submission_failed
jobId=job-7f3a
notificationType=ORDER_RECEIPT
errorCode=SMTP_TEMPORARY_FAILURE
attempt=2
retryScheduled=true
~~~

None of these three events contain email addresses, full subjects, raw HTML, sensitive attachment filenames, or access tokens. If correlating jobs by recipient is required, add `recipientToken` per policy—never raw recipients.

### Field selection guidelines

| Field | Usually Log? | Notes |
|---|---|---|
| `event` / `phase` | Yes | Fixed enum/value |
| `mailJobId` | Yes if random ID | Never encode email inside the job ID |
| `notificationType` | Conditionally yes | Highly sensitive types may need generic names |
| `templateId` / `version` | Yes | Never use personalized subjects as template ID |
| `attempt` / `durationMs` | Yes | Useful for retries and latency |
| `providerId` | Yes | Fixed list of providers |
| `smtpStatusClass` / `errorCode` | Yes | Normalized codes only |
| `recipientCount` | Conditionally yes | Can bucket per policy |
| `recipientToken` | When correlation is needed | Keyed HMAC with restricted read access |
| `recipientEmail` | No by default | If strictly needed, keep in protected lookup channel |
| `subject` | No by default | Often contains names, order numbers, content |
| `exception.getMessage()` | No by default | May contain addresses and SMTP replies |
| `MimeMessage` / raw MIME | No | Contains To/Cc/Bcc, body, and attachments |

### Never log entire job DTOs or maps

~~~java
// Easy to leak data if record.toString() includes recipient.
log.info("Mail job {}", mailJob);

// Easy to leak body, headers, Bcc, or tokens.
log.debug("Mail payload {}", payload);
~~~

Replace with explicitly selected fields:

~~~java
log.info(
        "event=mail_job_created jobId={} notificationType={}",
        mailJob.id(),
        mailJob.notificationType());
~~~

`notificationType` should be an enum or validated string; never accept arbitrary client-supplied names that could carry PII.

## 14. Wrapping RecipientTokenService in a dedicated logger

A dedicated mail logging component prevents individual services from logging recipient addresses in inconsistent ways.

~~~java
import jakarta.mail.internet.AddressException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class MailSafeLogger {
    private static final Logger log =
            LoggerFactory.getLogger(MailSafeLogger.class);

    private final RecipientTokenService tokens;

    public MailSafeLogger(RecipientTokenService tokens) {
        this.tokens = tokens;
    }

    public void submissionStarted(
            String jobId,
            String notificationType,
            String recipient,
            int attempt) {

        String recipientToken = safeToken(recipient);
        log.info(
                "event=mail_submission_started "
                    + "jobId={} notificationType={} "
                    + "recipientToken={} attempt={}",
                jobId,
                notificationType,
                recipientToken,
                attempt);
    }

    public void submissionFailed(
            String jobId,
            MailFailureCode code,
            int attempt) {
        log.warn(
                "event=mail_submission_failed "
                    + "jobId={} errorCode={} attempt={}",
                jobId, code, attempt);
    }

    private String safeToken(String recipient) {
        try {
            return tokens.token(recipient);
        } catch (AddressException ex) {
            return "[invalid-recipient]";
        }
    }
}
~~~

Here `MailFailureCode` is an application-defined enum. The logger intentionally **does not** accept a `Throwable` so callers cannot accidentally pass stack traces containing SMTP transcripts or email addresses.

For untrusted inputs, `jobId` and `notificationType` must also be server-generated or validated. An attacker could inject CR/LF into request strings to perform log injection if unhandled. Apply structured logging and validation to **all fields**, not just recipients.

### What if tokenization fails?

In the example, syntactically invalid addresses are replaced with a generic marker without logging the input. If the HMAC key is missing, `IllegalStateException` could halt processing or fall back without a token; define a clear policy:

- **Allow mail sending without logging a token:** log `recipientToken=[unavailable]` safely and emit a configuration-error metric.
- **Fail closed for compliance:** halt the send path if organizational rules require every submission to carry a valid correlation pseudonym.

Never fall back to `recipient.toString()` or `sha256(email)` just because the HMAC service failed. Separate token generation from authorization to send mail according to business requirements.

## 15. Never log JavaMailSender exceptions unconditionally

`JavaMailSender.send(...)` can throw `MailException` subtypes, such as:

- `MailAuthenticationException` when SMTP authentication fails.
- `MailSendException` when sending a message fails.
- `MailPreparationException` when a preparator fails.
- Underlying exceptions such as `MessagingException` or SMTP/address-specific exceptions.

An SMTP server may reply:

~~~text
550 5.1.1 Recipient <person@example.test> does not exist
~~~

If Spring Mail's exception embeds that exact message, logging:

~~~java
log.warn("SMTP failed: {}", ex.getMessage());
log.error("Mail sending error", ex);
~~~

can write the address straight into logs. Even if application code never puts the recipient into log lines, **the provider can echo the address in its error**.

### Classifying errors into controlled codes

~~~java
public enum MailFailureCode {
    AUTHENTICATION_FAILED,
    SMTP_TEMPORARY_FAILURE,
    SMTP_PERMANENT_FAILURE,
    SMTP_SUBMISSION_UNKNOWN,
    MIME_PREPARATION_FAILED,
    RESOURCE_READ_FAILED,
    UNCLASSIFIED_MAIL_FAILURE
}
~~~

A conservative classifier:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;

public final class MailFailureClassifier {
    private MailFailureClassifier() {
    }

    public static MailFailureCode classify(MailException ex) {
        if (ex instanceof MailAuthenticationException) {
            return MailFailureCode.AUTHENTICATION_FAILED;
        }
        if (ex instanceof MailPreparationException) {
            return MailFailureCode.MIME_PREPARATION_FAILED;
        }
        return MailFailureCode.UNCLASSIFIED_MAIL_FAILURE;
    }
}
~~~

This snippet intentionally **does not guess SMTP temporary vs. permanent solely from `MailSendException`**: you must inspect nested causes, SMTP response codes, and protocol phases. Without sufficient evidence, use `UNCLASSIFIED_MAIL_FAILURE` or `SMTP_SUBMISSION_UNKNOWN` per defined semantics.

### Example catch block in a service

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;

public void submit(
        String jobId,
        MimeMessage message,
        int attempt) {
    try {
        mailSender.send(message);
    } catch (MailException ex) {
        MailFailureCode code =
                MailFailureClassifier.classify(ex);

        safeLogger.submissionFailed(jobId, code, attempt);
        // Persist state/retry per policy.
        // Do not log ex.getMessage() or ex here.
        throw ex;
    }
}
~~~

This illustrates a method on a component holding `mailSender` and `safeLogger`; import `jakarta.mail.internet.MimeMessage`. When **rethrowing the exception**, an upper layer or framework might print the stack trace and leak data. Therefore, log protection must span **the entire pipeline**, including schedulers, consumers, HTTP exception handlers, and AOP boundaries—not just one catch block.

Never swallow exceptions merely to “hide addresses”. Retry logic must still observe failures while operational logs emit sanitized codes.

## 16. Controlling exceptions that carry embedded addresses

`MailSendException` can expose details about failed messages and nested exceptions. For instance, its map of failed messages can hold `MimeMessage` keys and exception values. Dumping that map directly:

~~~java
// Unsafe for mail privacy; never log raw.
log.warn("Failed messages: {}", ex.getFailedMessages());
~~~

can expose message contents or SMTP errors depending on how objects serialize.

**Extract only recipient-free metadata**, such as:

- Count of failed messages.
- Normalized general error classification.
- Fixed provider identifier.
- Timing, attempt count, and job ID.

Example:

~~~java
import org.springframework.mail.MailSendException;

if (ex instanceof MailSendException sendException) {
    int failedCount =
            sendException.getFailedMessages().size();
    log.warn(
            "event=mail_submission_failed "
                + "jobId={} failedMessageCount={}",
            jobId, failedCount);
}
~~~

Never print map keys/values or `getMessageExceptions()` directly. If deep inspection is needed to assign an SMTP error code, perform it inside a trusted classifier and **return only an enum/code** to the logging layer.

### SMTP response codes and recipients in the same string

Example:

~~~text
550 5.1.1 user@example.test unknown
421 4.7.0 temporary rate limit for user@example.test
~~~

You can extract codes like `550` or `421` as diagnostic signals if a parser extracts them reliably, but **never log the entire response line**. Even SMTP codes must be interpreted with phase context: a connection drop after sending `DATA` can yield an uncertain outcome, so never infer safe retry from error text alone.

## 17. JavaMail/Jakarta Mail protocol debug: a major address leak source

When Jakarta Mail debug is enabled, the library logs SMTP protocol details:

~~~text
DEBUG SMTP: connecting to host smtp.example.test
MAIL FROM:<noreply@example.test>
RCPT TO:<customer@example.test>
DATA
...
~~~

This can include recipients, sender, SMTP handshake metadata, and depending on mode/implementation can expose authentication data or message bodies. Therefore, **never enable protocol-level debug by default in production**.

Example Spring Boot configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      mail.debug: false
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

`mail.debug=false` disables debugging at the Jakarta Mail session level via the corresponding property, yet you must also audit other places where it might be enabled:

- Code calling `Session.setDebug(true)`.
- Code setting debug output via `Session.setDebugOut(...)`.
- Other mail provider configurations or implementation loggers.
- JVM system properties and environment settings.
- Logger categories at `DEBUG`/`TRACE` logging SMTP transport or mail contents.
- Container stdout/stderr collectors.

**Never assume disabling Spring application loggers stops all SMTP debug output.** Jakarta Mail can use its own debug output stream; verify session/provider configuration and how the runtime captures stdout.

### When protocol debug is unavoidable for investigation

If an emergency requires an SMTP trace:

1. Prefer a test environment, fake recipients, and an SMTP sink.
2. Enable debug only for a short, operationally approved window.
3. Restrict scope to a single instance, job, or test account.
4. Control where output is stored and who can read it.
5. Strip tokens, credentials, recipients, subjects, and bodies before sharing.
6. Disable debug again and verify the configuration is off.
7. Purge or shorten retention of debug artifacts per policy.

Never use `mail.debug.auth=true` or similar settings to expose authentication details for “easier debugging” in production.

## 18. Never dump MimeMessage or raw MIME into logs

A common diagnostic snippet:

~~~java
ByteArrayOutputStream out = new ByteArrayOutputStream();
message.writeTo(out);
log.debug("Raw email: {}", out.toString(StandardCharsets.UTF_8));
~~~

This can push into logs:

- `From`, `To`, `Cc`, and other headers.
- `Subject` containing customer names or order numbers.
- HTML/text bodies.
- Reset links or OTPs.
- Encoded binary attachments.
- `Message-ID` and internal metadata.

**Never dump raw MIME to centralized logs.** For MIME testing, use synthetic fixtures/SMTP sinks and structural assertions instead of logging full bytes. If a real email must be inspected, use an access-controlled diagnostic store with short retention and access auditing; application logs should carry only a reference to the investigation case, never raw bodies.

### Bcc headers must be protected even if absent at the end

Never argue “`Bcc` is not in the delivered email, so there is nothing to worry about”. `Bcc` can still exist at the input layer, in the `MimeMessage` object before sending, in the SMTP recipient list, or in exceptions. Logging policies must apply before data passes through any component, not merely rely on mail clients hiding `Bcc` on display.

## 19. MDC and correlation ID: never pass recipients on the thread

**Mapped Diagnostic Context (MDC)** is commonly used to attach fields automatically to every log line on the same thread:

~~~java
MDC.put("requestId", requestId);
MDC.put("recipient", recipientEmail); // Do not do this.
~~~

When an application places a recipient into MDC, every library and component logging on that thread can inadvertently forward the recipient to centralized logging. If MDC is copied into an executor, the leak radius widens further.

Instead use:

~~~java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
        MDC.putCloseable("mailJobId", jobId)) {

    mailSender.send(message);
} finally {
    // putCloseable removes the key at the end of this scope;
    // if the key had a prior value, manage restoration explicitly.
}
~~~

`mailJobId` should be a stable ID not constructed by concatenating an email or subject. If recipient correlation is needed, emit an HMAC token on specific approved events rather than attaching the token to every log line for convenience.

### `@Async` and context propagation

`@Async("mailTaskExecutor")` moves work onto another thread. The HTTP request thread's MDC **does not propagate automatically** to the worker; if using a `TaskDecorator` to copy MDC, explicitly restrict which fields may be copied.

~~~text
HTTP request thread
  MDC: requestId, userEmail, recipient
                |
                v
        Copy entire MDC?
                |
                +-- Leaks userEmail/recipient to worker logs

Better design:
  Command: jobId, notificationType, allowed metadata
                |
                v
  Mail worker MDC: mailJobId, traceId, phase
~~~

Do not rely solely on `MDC.clear()` for cleanup and forget that sensitive data was already logged before clearing. The best rule is **never putting recipients into MDC in the first place**. In thread pools, restore or clear context in `finally` so a prior task's data never bleeds into the next task.

## 20. Distributed tracing and trace baggage also carry data

OpenTelemetry and tracing backends can receive attributes from application code, HTTP instrumentation, message brokers, or logging bridges. Avoid this:

~~~text
span=mail.smtp.submit
attributes:
  mail.recipient=user@example.test
  mail.subject=Your password reset link
  mail.body=...
~~~

Even when omitted from application logs, tracing backends may store span attributes with different retention, access controls, and export paths. Therefore, PII-exclusion rules must cover:

- Span attributes and span events.
- Trace baggage and context propagation.
- Log-to-trace correlation.
- Message queue/broker attributes.
- Error/exception event details.

Better design:

~~~text
span=mail.smtp.submit
attributes:
  mail.notification_type=ORDER_RECEIPT
  mail.provider=PRIMARY_SMTP
  mail.attempt=2
  mail.result=ACCEPTED
  mail.recipient_count_bucket=1
~~~

`traceId` and `spanId` link operations across services without email addresses. Still, in some systems a trace ID can be joined back to a request/account in a database or observability system, so traces still require appropriate access controls, retention, and export policies.

### Never put recipients into baggage

Baggage is often propagated across service boundaries, sometimes even to external downstream services. Putting `recipientEmail` or a stable pseudonym into baggage can carry data farther than intended. Use random, minimally scoped correlation IDs and only keys necessary for distributed tracing.

## 21. Metrics: never use emails or HMACs as labels

A metric is typically stored as multiple time series keyed by label combinations:

~~~text
mail_submission_total{
  recipient="customer@example.test",
  result="success"
}
~~~

This is an anti-pattern because:

1. Recipients are personal data written into the metrics backend.
2. Each email creates a new label value, causing **high cardinality**.
3. Large time-series counts increase storage cost and can destabilize metrics systems.
4. Anyone with metric read access can discover addresses and sending history.

Instead use:

~~~text
mail_submission_total{
  notification_type="ORDER_RECEIPT",
  provider="PRIMARY_SMTP",
  result="SMTP_ACCEPTED"
}
~~~

If per-recipient analysis is needed, query through an appropriately authorized job/audit system. **HMAC tokens are also unsuitable as metric labels**: they still have high cardinality and still link recipients.

### Micrometer example with bounded tags

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailMetrics {
    private final MeterRegistry registry;

    public MailMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSubmission(
            String notificationType,
            String result) {
        Counter.builder("mail_submission_total")
                .tag("notification_type", notificationType)
                .tag("result", result)
                .register(registry)
                .increment();
    }
}
~~~

`notificationType` and `result` must come from enums or approved value lists, never arbitrary inputs. `mail_submission_total` here is the logical application metric name; Prometheus backends may apply `_total` suffixes according to their conventions. Align naming with your project.

Other useful metrics:

| Metric | Purpose | Recommended Labels |
|---|---|---|
| Submission attempts | Send attempt volume | Provider, notification type, result |
| SMTP latency | Submission latency | Provider, result |
| Outbox backlog | Pending jobs waiting | Status, notification type |
| Retry count | Jobs needing retry | General error category |
| Authentication failures | Detect broken secrets/providers | Provider |
| Invalid recipient count | Track bad input data | Notification type, source |
| Mail task rejection | Executor saturation | Fixed executor name |

Never use `recipientToken`, `mailJobId`, subjects, exception messages, or raw SMTP responses as tags. Certain fields belong only in **controlled logs**, never in metrics.

## 22. Outbox and retries: store real data in the right place, log only metadata

With a **transactional outbox**, the job table may need to store the real recipient so workers can retry after crashes. That does not mean workers may dump the entire row into logs.

Example outbox record:

~~~json
{
  "id": "mail-job-7f3a",
  "notificationType": "ORDER_RECEIPT",
  "recipient": "customer@example.test",
  "status": "RETRY",
  "attemptCount": 3,
  "lastErrorCode": "SMTP_TEMPORARY_FAILURE"
}
~~~

Corresponding log:

~~~text
event=mail_job_retry_scheduled
jobId=mail-job-7f3a
notificationType=ORDER_RECEIPT
attempt=3
errorCode=SMTP_TEMPORARY_FAILURE
nextAttemptBucket=1m_5m
~~~

Outbox payloads are protected by database access policies, encryption, and retention requirements. Logs must omit `recipient`, full payloads, raw MIME, and nested SMTP exceptions.

### Do not store raw exceptions in `last_error` by habit

Some systems write:

~~~java
job.setLastError(ex.toString());
~~~

That value can carry recipient addresses or provider replies. Even inside a database rather than a log, it multiplies copies of sensitive data and leaks easily when admin UIs or logs later dump the row.

Instead store:

~~~text
lastErrorCode=SMTP_TEMPORARY_FAILURE
lastErrorPhase=RCPT_TO
lastErrorAt=...
attemptCount=3
~~~

If raw diagnostics are genuinely needed for a special incident, store them in a restricted-access channel with short retention and access auditing; never use a free-form text column copied across every system.

### One job can have multiple recipients

If an email contains multiple `To`/`Cc`/`Bcc` addresses, one recipient failing can affect part of the message. Logs should record `jobId`, count of rejected recipients, and a general reason code. Specific identities should be looked up via the authorized job store. Never dump the failed address list from `MailSendException` into general logs.

## 23. Structured logging vs. redaction filters: which layer protects best?

There are two strategies:

**Strategy A — Emit only approved fields at the source (preferred)**

~~~text
Mail service
   |
   v
SafeMailEvent(jobId, type, outcome, attempt)
   |
   v
Structured log encoder
   |
   v
Log collector
~~~

No email field exists on the log object. This is the cleanest way to prevent sensitive data from leaving the source.

**Strategy B — Pipeline redaction filters**

~~~text
Application logs
   |
   v
Redaction / processor
   |
   v
Centralized log storage
~~~

A filter in the encoder or collector serves as **defense in depth** for overlooked leak paths. However, it cannot guarantee coverage in every case:

- Addresses can appear inside quoted display names, JSON strings, stack traces, or nested exceptions.
- MIME headers can be folded across multiple lines.
- Data can be Base64 or quoted-printable encoded.
- Internationalized addresses or unusual mailbox syntax can evade simple regexes.
- Data may already have passed through stdout, sidecars, or forwarders **before redaction occurs**.

Therefore, **never rely solely on regex replacement in log lines**. Design to omit PII at the source first, using filters only to catch edge-case slips.

### String-replacement regexes are not email parsers

A simple regex such as:

~~~text
[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+
~~~

catches common addresses, but misses full RFC email syntax, Unicode, quoted local-parts, and multiline/header encodings. It can also falsely match technical identifiers as emails.

A pipeline can combine **structured field-name redaction** (`recipient`, `to`, `cc`, `bcc`) with supplementary unstructured rules. No filter replaces controlling data flow from the start.

## 24. Protecting HTTP logging, message consumers, and admin UIs

Even when the mail sender logs safely, the **entry point** of a mail request may be logged earlier:

~~~http
POST /api/send-notification
Content-Type: application/json

{
  "recipient": "customer@example.test",
  "template": "ORDER_RECEIPT"
}
~~~

If HTTP request-logging middleware records the entire body, the recipient leaks before `JavaMailSender` ever runs. Likewise:

- Spring MVC/WebFlux request logging.
- API gateway access logs with query strings containing emails.
- Kafka/RabbitMQ consumers logging raw messages.
- Admin endpoints serializing outbox records as JSON.
- AOP aspects logging all method arguments.
- Error handlers returning or logging raw requests/exceptions.

Protect the flow from **entry point to egress**, not only inside the mail adapter.

### A clear input/output policy

| Boundary | Approach |
|---|---|
| HTTP/API | Omit body/recipient logging or configure field redaction |
| Application service | Log only `jobId`/type/outcome |
| Outbox DAO | Never dump entities/payloads |
| Broker consumer | Never log raw events containing recipients |
| MIME composer | Never log `MimeMessage` or attachments |
| SMTP adapter | Never log raw exceptions or protocol transcripts |
| Central collector | Add redaction filters, access controls, retention |
| Support UI | Look up by `jobId`, require authorization and auditing |

### Avoid placing emails in URL query parameters when alternatives exist

An endpoint like:

~~~text
GET /mail-status?email=customer@example.test
~~~

readily ends up in access logs, proxies, and browser histories. Use a `jobId` or an authorized lookup endpoint rather than putting emails into query strings for convenience. For unsubscribe URLs carrying tokens, treat those tokens as sensitive data too and keep them out of logs.

## 25. Unit testing stability and scope of recipient HMAC tokens

Before deploying HMAC tokens into observability, verify two properties:

1. Identical canonical mailboxes with the same key/version yield the same token.
2. Tokens contain no raw mailbox parts and are not replaced by plain SHA-256.

JUnit 5 + AssertJ example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;
import org.junit.jupiter.api.Test;

class RecipientTokenServiceTest {

    private RecipientTokenService newService(
            byte keyByte, String version) {
        // Fixed key for testing only; never use in production.
        byte[] key = new byte[32];
        Arrays.fill(key, keyByte);
        return new RecipientTokenService(key, version);
    }

    @Test
    void stableForSameMailboxAndDomainCase()
            throws Exception {
        RecipientTokenService service =
                newService((byte) 0x42, "v1");

        String first =
                service.token("Alice@Example.COM");
        String second =
                service.token("Alice@example.com");

        assertThat(first).isEqualTo(second);
        assertThat(first).startsWith("v1:");
        assertThat(first).doesNotContain("Alice");
        assertThat(first).doesNotContain("example.com");
    }

    @Test
    void changesWhenKeyOrVersionChanges()
            throws Exception {
        String recipient = "Alice@example.com";

        String v1 = newService((byte) 1, "v1")
                .token(recipient);
        String v2 = newService((byte) 2, "v2")
                .token(recipient);

        assertThat(v1).isNotEqualTo(v2);
    }

    @Test
    void doesNotSilentlyLowercaseLocalPart()
            throws Exception {
        RecipientTokenService service =
                newService((byte) 1, "v1");

        assertThat(service.token("Alice@example.com"))
                .isNotEqualTo(
                        service.token("alice@example.com"));
    }
}
~~~

This unit tests the **chosen canonicalization policy** and HMAC mechanism, without claiming that case-differing local-parts are always separate mailboxes on every provider.

### Testing invalid inputs

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.internet.AddressException;
import org.junit.jupiter.api.Test;

class CanonicalizationFailureTest {
    @Test
    void refusesMalformedAddress() {
        assertThatThrownBy(() ->
                RecipientCanonicalizer.canonicalMailbox(
                        "not-an-email"))
                .isInstanceOf(AddressException.class);
    }
}
~~~

Never log the invalid address inside the validator's catch block. If an attacker feeds arbitrary strings into the email field, logging the input can leak tokens or cause log injection even though the parser rejected it.

### Tests alone do not prove key security

A unit test verifying HMAC calculation does not prove secrets are provisioned safely at runtime. You must still govern the secret store, secret rotation, read permissions, and configuration logging. Never record a test key in deployment docs as a production key.

## 26. Unit testing that mail logs contain no real addresses

For projects using **Logback** in tests (common with Spring Boot), you can use `ListAppender` to capture logger output and assert that log messages contain no email addresses:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import java.util.Arrays;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class MailSafeLoggerTest {
    @Test
    void logsRecipientTokenInsteadOfRawEmail() {
        byte[] key = new byte[32];
        Arrays.fill(key, (byte) 7);
        RecipientTokenService tokens =
                new RecipientTokenService(key, "test-v1");
        MailSafeLogger safeLogger =
                new MailSafeLogger(tokens);

        Logger logger = (Logger) LoggerFactory
                .getLogger(MailSafeLogger.class);
        ListAppender<ILoggingEvent> appender =
                new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            safeLogger.submissionStarted(
                    "job-123",
                    "ORDER_RECEIPT",
                    "secret.person@example.test",
                    1);

            String output = appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.joining("\n"));

            assertThat(output)
                    .contains("job-123")
                    .contains("recipientToken=test-v1:")
                    .doesNotContain("secret.person@example.test")
                    .doesNotContain("secret.person")
                    .doesNotContain("example.test");
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

This test only verifies `MailSafeLogger` output under Logback. It does not yet cover the entire system:

- Whether SMTP protocol debug is enabled.
- Whether HTTP middleware, Kafka consumers, or outbox DAOs log recipients.
- Whether a Logback JSON encoder or collector enriches email fields.
- Whether exceptions at framework boundaries print full stack traces.

Therefore, pair logger unit tests with integration tests or configuration checks for major leak paths.

### Tests must remain isolated when multiple classes share a logger

`ListAppender` temporarily attaches to a shared logger. If tests run in parallel or multiple threads log concurrently, captured output can contain lines from other tests. Use test-specific loggers, lock test scope, or configure appropriate isolation. Always detach the appender in `finally` to avoid side effects.

### Negative assertions with sensitive exceptions

A test can craft a simulated error message containing a dummy recipient:

~~~java
String simulatedProviderResponse =
        "550 5.1.1 <secret.person@example.test> unknown";
~~~

Then assert that the classifier returns only a safe `MailFailureCode` and the logging path does not print the raw response. Never write tests that deliberately log full exceptions hoping a filter “always reliably” scrubs every email.

## 27. Testing leak paths outside the logger

A solid test matrix should span multiple boundaries:

| ID | Scenario | Expected Result |
|---|---|---|
| TC-01 | Email sent successfully | Log has only jobId/type/result, no raw recipient |
| TC-02 | SMTP auth failed | Logs `AUTHENTICATION_FAILED`, no password or address |
| TC-03 | SMTP 550 echoes recipient | Exception chain is not printed to routine logs |
| TC-04 | `MailSendException` holds failed message map | Does not dump `failedMessages` or `MimeMessage` |
| TC-05 | To/Cc/Bcc all present | Does not log raw address lists |
| TC-06 | `@Async` mail worker | MDC has only allowed keys, cleaned after task |
| TC-07 | Outbox retry job | Logs metadata/retries, never dumps payload JSON |
| TC-08 | HMAC same mailbox, same key | Consistent token |
| TC-09 | HMAC key changed | Token changes and version is explicit |
| TC-10 | Uppercase domain / IDN | Consistent canonicalization per policy |
| TC-11 | Email with plus tag | Does not strip tag unless policy allows |
| TC-12 | Invalid recipient address | Does not echo input into logs |
| TC-13 | HTTP request contains email | Request logging omits sensitive body/query |
| TC-14 | Broker message contains recipient | Consumer logging never dumps payload |
| TC-15 | Jakarta Mail debug | Production config disables protocol transcript |
| TC-16 | Metrics | Labels contain no email, token, or job ID |
| TC-17 | Distributed trace | Attributes/baggage contain no recipient |
| TC-18 | Log export/alert | Does not auto-enrich raw email from DB |
| TC-19 | Key rotation | New token version, no mapping leaked in logs |
| TC-20 | Incident requires finding recipient | Separate authorized, audited lookup |

This is a **functional/security test matrix for code**, not a substitute for documentation QA. Each environment should pick test techniques suited to its logging framework, mail provider, and observability stack.

### Never run production SMTP in unit tests

Tests for redaction, HMAC, and exception classification can use dummy recipients at `@example.test`, mock senders, and simulated provider responses. You never need to send real emails or enable SMTP protocol debug to verify logging policies.

## 28. Troubleshooting incidents when logs omit email addresses

A common objection is: “If we don't log email addresses, how will support know whether a customer's email was sent?”

Use an authorized lookup workflow:

~~~text
Support agent receives customer inquiry
          |
          v
Verify lookup permission and purpose
          |
          v
Look up mail job by orderId / accountId
in a controlled interface
          |
          v
Obtain jobId and status
          |
          v
Query centralized logs using jobId
          |
          v
Inspect errors and retries without emails in logs
~~~

If multiple jobs for the same recipient must be found when no reliable user ID exists, an internal tool can:

1. Accept the email from an authorized user.
2. Canonicalize using the exact same policy.
3. Compute HMAC with the matching key version.
4. Return the token or bounded lookup results with auditing.
5. Never write the tool's input email into application logs.

**Never expose an unauthenticated or unthrottled “hash any email” API.** Such an endpoint can be abused as an oracle to compute tokens for candidate email lists, eroding HMAC protection.

### Design correlation IDs up front

A random `jobId` or opaque ID is a strong diagnostic tool:

- Persist it in the outbox record.
- Log it on job creation, claim, retry, and submission.
- Attach it to traces to link services.
- Return it in appropriate admin interfaces.
- Never encode raw recipients into the ID.

A job ID is not necessarily absolute anonymous data if internal tools can map it back to a user; access controls are still required. Still, it avoids broadcasting raw addresses across multiple systems simultaneously.

## 29. Access control, retention, and log deletion capability

Masking or HMAC does not replace governance. For data linkable to recipients, define:

- Who can read detailed logs and recipient tokens?
- Who can export logs to external systems?
- How long are logs retained by environment and notification type?
- Must data be deleted/minimized when valid deletion requests arrive?
- Who can access HMAC keys or token-computation tools?
- How long must incident-investigation data be retained and audited?
- Do backups/replicas of logs and secrets share the same retention and access policies?

An illustrative policy:

| Data Type | Storage Location | Controls |
|---|---|---|
| Real recipient | Business DB / outbox | Encryption, RBAC, retention |
| Recipient HMAC token | Logs only when truly needed | Read permissions, expiry, no broad export |
| HMAC key | Secret manager | Workload permissions, rotation, auditing |
| Job ID | Logs / tracing | Never encode emails; role-based access |
| Raw SMTP transcript | Not stored by default | Approved incident investigation only; purge early |
| Normalized error info | Logs / outbox | Fixed enum/code; no raw provider replies |

**Stable HMACs can complicate deleting a person's data from archived logs.** If retention or right-to-erasure requirements are strict, consider omitting tokens altogether or using short-lived/scoped tokens instead of a multi-year pseudonym.

Never assume deleting an HMAC key equals erasing all related data: events may still remain linkable via job IDs, tenants, timestamps, or other metadata.

## 30. Incident response when emails leak into logs

Suppose a code change accidentally logged `recipient` in production. Treat this as a data-governance incident, not just a formatting bug:

1. **Stop the leak at the source:** disable protocol debug, roll back, or fix the log statement.
2. **Determine scope:** which environments, start/end timestamps, and which loggers/collectors/backups received the data.
3. **Restrict access temporarily:** lock down exports and broad dashboards so only authorized responders have access.
4. **Assess severity:** what data appeared—Bcc, tokens, subjects, attachments, or mailboxes only?
5. **Execute deletion/retention remediation:** purge or redact copies in centralized logs, archives, tickets, and backups as supported by policy and tooling.
6. **Investigate root cause:** application log statement, exception formatting, raw DTO, SMTP debug, tracing, or collector enrichment?
7. **Add tests/guardrails:** prevent the exact leak path from recurring.
8. **Monitor and notify appropriately:** fulfill internal or legal reporting obligations without jumping to conclusions from a single log line.

Do not merely hide lines in a dashboard if logs were already copied to multiple sinks. Also never write another log containing emails to “list the leaked emails”.

## 31. Common anti-patterns

### 31.1. Replacing `@` with `[at]` only

~~~text
customer@example.test -> customer[at]example.test
~~~

This is not effective masking. Humans easily reconstruct the address, and many search tools still recognize it.

### 31.2. Plain SHA-256 hashing and calling it anonymous

Emails can be guessed from candidate lists and re-hashed. When you need a correlation token resistant to dictionary testing against leaked logs, use keyed HMAC with restricted invocation.

### 31.3. Using the SMTP password as the HMAC key

When one secret leaks or rotates, both SMTP sending and pseudonymization break. Separate keys by purpose; never share credentials.

### 31.4. Generating a random HMAC key on every service startup

~~~java
byte[] key = new byte[32];
new SecureRandom().nextBytes(key);
// Re-generated per replica/startup: tokens are no longer stable.
~~~

For cross-session correlation, all replicas need the same secret key provisioned from a secret store per policy. Never derive keys from startup timestamps or hostnames.

### 31.5. Lowercasing local-parts and stripping plus-tags unconditionally

`Alice+orders@example.com` is not guaranteed equivalent to `alice@example.com` across all mail providers. Canonicalization must match product data semantics rather than copying one provider's quirk across the entire Internet.

### 31.6. Logging HMAC tokens in every metric label

Tokens still have high cardinality and enable behavioral linking. Metrics should use bounded email types, providers, and statuses; recipient correlation belongs in logs or controlled job stores.

### 31.7. Logging raw exceptions on failures

~~~java
log.error("SMTP error for mail job", ex);
~~~

Providers can echo emails inside messages or nested exceptions. Log controlled error codes and IDs; isolate any detailed diagnostics.

### 31.8. Enabling `mail.debug` to diagnose every issue

SMTP transcripts can contain `RCPT TO`, sender, auth, and data. Never enable it by default in production; when necessary, use a sandbox environment and time-boxed debug procedures.

### 31.9. Logging `toString()` on jobs, MIME messages, or requests

Adding a `bcc` or `recipient` field to a DTO later can silently expose data across logs. Log using an allowlisted schema and audit `@ToString`/Lombok, serialization, and AOP logging.

### 31.10. Masking before logging while keeping raw emails in MDC

One safe log line cannot compensate for MDC carrying the recipient onto every other log line. Control logging context, tracing, and baggage as well.

### 31.11. Redacting only at the central collector

Data may already have traversed stdout, agents, buffers, node logs, and forwarders before redaction. Sink redaction is supplemental defense; omitting data at the source comes first.

### 31.12. Treating `recipientToken` as harmless because it cannot be decrypted directly

A stable token links recipient activity and acts as a pseudonymous identifier. Protect access and retention; never expose tokens or token-generation tools to arbitrary users.

### 31.13. Using the email address as the job ID

~~~text
jobId=customer@example.test:ORDER_RECEIPT:3
~~~

Even after removing other recipient fields, `jobId` still carries the email. Use random/opaque IDs that encode no personal data.

### 31.14. “Investigating” incidents by dumping full mail history into tickets

Exporting logs or job records containing emails and contents into issue trackers or public chats widens the leak. Share `jobId`, `errorCode`, `traceId`, and sanitized metadata; view real recipients only inside authorized tools.

## 32. Implementation roadmap in a Spring Mail application

A phased rollout can follow these steps:

1. **Clarify observability needs:** is job-level lookup enough, or is recipient correlation truly required?
2. **Inventory email touchpoints:** controllers, request logging, outbox, services, SMTP adapters, exceptions, MDC, tracing, metrics, and debug settings.
3. **Design an allowlisted log schema:** `event`, `jobId`, `notificationType`, `outcome`, `attempt`, `duration`, `errorCode`.
4. **Choose a recipient policy:** omit by default; mask in restricted UIs; use HMAC only when correlation is genuinely needed.
5. **Define canonicalization:** domain, local-part, IDN, policy version, and invalid input handling.
6. **Provision a dedicated HMAC key:** secret store, at least 32 random bytes per example, versioned with rotation.
7. **Build `SafeMailLogger`:** dedicated component enforcing schema, accepting no raw exceptions.
8. **Classify exceptions:** emit only approved error codes/phases, never raw provider messages.
9. **Disable protocol debug:** audit Jakarta Mail configuration and related loggers/output streams.
10. **Keep MDC/tracing clean:** carry only IDs, event names, and non-sensitive attributes.
11. **Clean up metrics:** low-cardinality tags only, never emails or HMAC tokens as labels.
12. **Secure outbox/admin lookups:** raw emails reside only in access-controlled, retention-managed stores.
13. **Write tests:** HMAC stability, malformed recipients, Logback capture, simulated SMTP errors containing emails.
14. **Verify deployment:** confirm HTTP/proxy/collectors do not re-enrich logs with emails.
15. **Monitor and review:** catch regressions after changing mail providers, logging frameworks, or middleware.

### Responsibility split pattern

~~~text
Application service
    |
    +-- creates mail job with opaque ID
    +-- stores recipient in protected outbox
    |
    v
Mail worker
    |
    +-- loads recipient for SMTP
    +-- computes optional HMAC token
    +-- emits safe event with jobId
    |
    v
JavaMailSender
    |
    +-- SMTP, protocol debug disabled
    |
    v
Safe outcome mapping
    |
    +-- result/errorCode
    +-- attempt and duration
    |
    v
Log/trace/metrics without raw recipient
~~~

Apply access controls and lifecycle policies to both **real data in the outbox** and **pseudonymous data in observability**. Separating them technically reduces exposure while preserving diagnostic capability.

## 33. Frequently asked questions

**Should partially masked recipients always be logged?** No. If `jobId` and status are enough to diagnose failures, omitting recipients altogether is best. Use masking only when clearly needed.

**Is masking `u***@example.com` anonymous?** No. The domain and partial local-part can still identify the recipient, especially combined with timestamps and email type.

**Can `SHA-256(email)` be reversed?** A digest is not reversible encryption, yet attackers can test candidate email lists and match digests. That is the core risk of unkeyed hashes.

**Does HMAC-SHA-256 guarantee the token contains no PII?** HMAC hides the raw address, yet the token remains a pseudonymous identifier capable of linking activity. Access, retention, and scope still require control.

**Why include `keyVersion` in tokens?** To know which key generated a token during rotation. Never compare tokens from different key versions directly and conclude they belong to different recipients.

**Should the entire email be lowercased before hashing?** Not by default. Domains are case-insensitive, while local-part semantics depend on the receiving system. Define an explicit, consistent canonicalization policy.

**Should `+tag` or dots be stripped for Gmail addresses?** Do not apply provider-specific quirks as a system-wide default. If your product has verified custom normalization, isolate and version that rule explicitly.

**Why not use recipient HMAC tokens as Prometheus labels?** Tokens have high cardinality and still link recipients. Metrics should use small label sets without personal identifiers.

**Is it safe to log full `ex.getMessage()` after masking the recipient beforehand?** Not reliably. Exceptions and SMTP responses themselves can include addresses, domains, or bodies. Log safe error codes and control stack traces.

**If application DEBUG logs are off, can SMTP still leak?** Yes. Jakarta Mail has its own session debug output, provider loggers, or runtime settings. Audit all sources.

**Can SMTP put emails into exceptions even when the app never logs recipients?** Yes. Providers can return errors echoing `RCPT TO` or rejected addresses. Never print raw exceptions to general logs.

**Should `MimeMessage` be logged to debug inline images/attachments?** Not in production. Use MIME unit tests, an SMTP sink, dummy fixtures, or an access-controlled diagnostic store when truly necessary.

**Must `To`, `Cc`, and `Bcc` follow the same policy?** Yes. `Bcc` deserves special care because it can appear in SMTP envelopes or debug logs even though hidden from delivered emails.

**How do we find all send errors for one user?** Use an authorized lookup system from account/order/email to retrieve `jobId`; if strictly necessary, compute HMAC in an audited internal tool and search by token rather than exposing raw addresses in logs.

**Should HMAC be logged for every recipient or only selectively?** Only on events requiring correlation. Logging a stable token too frequently reveals activity history even without exposing the address.

**What if the HMAC key leaks?** Rotate it, assess dictionary-matching exposure on historical logs, restrict access, and follow incident response procedures. Never treat tokens generated with a compromised key as strong protection.

**Can we just add one regex redaction filter in Logback?** Do not rely on it as the sole safeguard. Regexes miss MIME folding, Unicode, multiline strings, encoded content, and pre-filter logs. Eliminate data at the source.

**Is logging SMTP status `550` safe?** Extracting and controlling the numeric code is usually useful; avoid logging the entire raw response since it can contain addresses and provider details.

**Does hiding recipients in logs prevent outbox leaks?** No. The outbox still stores delivery data and requires its own access controls, encryption, retention, and auditing.

**Do HTTP and broker logging also need checking?** Yes. Emails can be logged at ingress before reaching the mail service; policies must cover the entire pipeline.

## 34. Summary

In **Spring Framework Mail**, observing an email-sending system does not require logging recipient addresses by default. Most issues can be diagnosed using **`jobId`, `notificationType`, status, attempt count, duration, provider, and normalized `errorCode`**.

To reduce data exposure:

1. **Omit recipients** whenever there is no genuine correlation requirement.
2. **Masking** only partially hides addresses and can still leak domains or identities.
3. **Keyed HMAC-SHA-256** is safer than plain SHA-256 when stable correlation tokens are needed; manage keys, versions, and canonicalization explicitly.
4. **Never log raw `MailException`, `MimeMessage`, or SMTP debug transcripts**, as they can contain `To`/`Cc`/`Bcc`, rejected addresses, and message contents.
5. **Never use emails or HMACs as metric labels**, and never put recipients into MDC, tracing baggage, or request logs.
6. **Protect data at every layer**: application, outbox, HTTP, broker, SMTP client, collector, dashboards, and lookup tools.

An ideal log entry:

~~~text
event=mail_submission_failed
jobId=job-7f3a
notificationType=ORDER_RECEIPT
provider=PRIMARY_SMTP
errorCode=SMTP_TEMPORARY_FAILURE
attempt=3
retryScheduled=true
~~~

When correlating multiple jobs for the same recipient is necessary, add a recipient HMAC token under strict access and retention policies—never write real email addresses into log strings.

**Core principle:** logs must be rich enough to operate the system, yet never become a distributed replica of the customer database. Minimizing data at the source, using keyed pseudonyms when required, and auditing every potential leak path keeps a mail system both observable and privacy-preserving.
