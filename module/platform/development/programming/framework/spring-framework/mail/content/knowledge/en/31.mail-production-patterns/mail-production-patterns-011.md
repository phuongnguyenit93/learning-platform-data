# Encrypting or Removing Sensitive Content After Sending

In a Spring Framework Mail application, sending email is not just building a `MimeMessage` and calling `JavaMailSender.send(...)`. A notification can contain names, phone numbers, shipping addresses, password-reset codes, tokenized links, invoices, HR documents, or financial data. This data can be retained across many locations: outbox tables, queues, object storage, temporary files, logs, APM traces, exceptions, backups, and the email provider's infrastructure.

A production design pattern must answer two **distinct yet complementary** questions:

1. **Encrypting sensitive content while it must be retained:** limit damage if the database, disk, object storage, or backups are accessed without authorization.
2. **Removing sensitive content once its purpose ends:** do not keep plaintext, ciphertext, attachments, or tokens longer than genuinely required.

"Sent" should not be treated as the moment all data can be wiped immediately, because SMTP submission can return transient errors, ambiguous outcomes, or require retries. Conversely, you also should not keep bodies, HTML, attachments, and full raw emails indefinitely just to make debugging easy.

**Important limitation:** once an email has been handed off to a provider or recipient mail server, the application normally **cannot recall or delete all external copies**. Deleting a copy from the application's database does not delete the email in the Inbox, forwarded messages, provider backups, or the recipient's devices. This lesson focuses on **the copies the application controls**, protections during the sending process, and accurately stating the boundaries of protection.

## 1. Learning objectives

After this lesson, you will be able to:

1. Identify which types of data should be kept out of emails from the start.
2. Enumerate where sensitive data can be created, copied, or persisted inside a Spring Mail pipeline.
3. Distinguish **TLS in transit**, **encryption at rest**, **application-level encryption**, and **end-to-end encryption**.
4. Design an email outbox storing only the minimum data needed for rendering, retries, auditing, and delivery tracking.
5. Apply authenticated encryption such as AES-GCM properly when sensitive payloads must be stored in the application.
6. Understand the roles of KMS/HSM, data encryption keys, key versions, and key rotation workflows.
7. Manage the lifecycle of attachments, temporary files, HTML, signed URLs, and serialized MIME content.
8. Set retention/TTLs according to `PENDING`, `PROCESSING`, `RETRY_WAIT`, `SUBMITTED`, `FAILED`, and `UNKNOWN` states.
9. Implement retryable, verifiable cleanup/purge without breaking active notifications.
10. Design logs, metrics, traces, tests, and runbooks without accidentally persisting sensitive data.

## 2. Start with a threat model, not an algorithm

Before adding AES to code, answer: **what data**, **who can read it**, **where it is held**, **for how long**, and **the purpose** of each copy.

Example of a password-reset email:

```text
User requests password reset
         |
         v
Create short-lived one-time reset token
         |
         v
Render reset email
         |
         v
Queue / Outbox
         |
         v
JavaMailSender / SMTP
         |
         v
Mail provider / Recipient mailbox
```

Threats can vary:

- Operations staff accidentally reading raw payloads from a database or logs.
- SQL injection or leaked backups exposing outbox contents.
- Object storage misconfigured as public for attachments.
- SMTP debug logs printing both recipients and message contents.
- Worker crashes leaving temporary files containing invoices on disk for months.
- Raw MIME sent to a third-party monitoring system.
- An expired secret/token remaining usable because the system failed to revoke it.
- A user requesting data deletion while copies persist in archives and scheduled backups.

### Classify data first

| Data category | Examples | Suggested policy |
| --- | --- | --- |
| Authentication secrets | OTP, reset token, magic-link token | Avoid plaintext storage; very short TTL; one-time use |
| Identifying information | Email, full name, phone number, address | Minimize, restrict permissions and retention |
| Financial data | Invoices, account numbers, statements | Access controls/encryption matched to sensitivity |
| HR/medical data | Recruiting content, lab results | Evaluate whether email is an appropriate channel; strict protection |
| Operational metadata | Notification ID, route, status | Often kept longer than payload, still protected |
| Non-sensitive data | Generic notification templates | May store template/version instead of full render |

Not every email needs the same policy. A financial report with sensitive attachments differs from a "Your order has been received" email containing no private details beyond the recipient address.

## 3. Attacks at each layer: storage, transit, and end-to-end

A simple model:

```text
Application DB / disk / object storage
       |     encryption at rest
       v
Spring Mail worker (data visible to permitted process)
       |     SMTP over TLS when properly configured
       v
Sending mail provider
       |     inter-server transport policies vary
       v
Receiving mail provider
       |
       v
Recipient mail client / mailbox
```

**Encryption at rest** helps when a storage medium is accessed without authorization, yet an application granted decryption permission still sees plaintext.

**STARTTLS/TLS** protects the connection between client and SMTP server to the extent it is properly established and verified; it does not mean every inter-server hop and mailbox is end-to-end encrypted.

**S/MIME or OpenPGP** can protect message content end-to-end when properly deployed and recipients hold suitable keys; however, certificate/key administration, header metadata, and recipient UX are significantly more complex.

**Data deletion** shrinks the volume of copies needing protection, yet cannot guarantee immediate removal from backups or providers outside application control.

## 4. Distinguish three states: submitted, accepted, and delivered

`JavaMailSender.send(...)` returning without throwing an exception usually only indicates **SMTP submission completed based on transport evidence**. It does not prove the email reached the Inbox.

```text
PENDING -> PROCESSING -> SUBMITTED
                 |
                 +-- known transient error -> RETRY_WAIT
                 +-- terminal error --------> FAILED
                 +-- ambiguous outcome -----> UNKNOWN

SUBMITTED -> provider may later report:
             DELIVERED_REMOTE / BOUNCED / DEFERRED
```

Do not treat the `SUBMITTED` event alone as a signal that "everything can be deleted" if the application needs the payload for retries/reconciliation or business retention requirements. Conversely, do not retain plaintext reset tokens forever just because `DELIVERED_REMOTE` has not arrived, if the token has expired or a cancellation policy applies.

**Retention must depend on purpose and state**, not a single `sent` boolean.

## 5. Data minimization: the safest data is data never stored

Before encrypting, reduce what the email pipeline actually needs.

For example, **do not** push an entire customer object into the queue:

```java
record MailJobUnsafe(
        CustomerEntity entireCustomer,
        OrderEntity entireOrder,
        byte[] pdfInvoice,
        String resetToken,
        String htmlBody
) {}
```

Such objects carry excess fields, may hold entities not detached from transactions, and leak PII into serialization/logs.

Replace it with a compact job:

```java
record MailJobRef(
        UUID notificationId,
        UUID recipientId,
        String templateKey,
        String templateVersion,
        String encryptedPayloadRef,
        String attachmentObjectVersion
) {}
```

Benefits:

- The queue does not carry raw attachments or lengthy HTML.
- Sensitive fields are easier to exclude from logs.
- Payloads can live in a dedicated encrypted store with TTLs.
- Versions/immutability can be managed for retries.
- Unnecessary business data never traverses the mail worker.

Still, **storing only a reference** is not automatically safe. If the reference is a public URL or mutable object, workers might fetch wrong data or expose secrets. References must carry proper access controls, versioning, deletion policies, and auditing.

## 6. Lifecycle of an email containing sensitive data

```text
Business event
      |
      v
Validate recipient + eligibility
      |
      v
Create encrypted payload reference / version
      |
      v
Outbox notification PENDING
      |
      v
Claim + PROCESSING
      |
      v
Decrypt only fields needed
      |
      v
Render + create MimeMessage
      |
      v
SMTP submission
      |
      +--> SUBMITTED
      +--> RETRY_WAIT
      +--> FAILED
      +--> UNKNOWN
      |
      v
Apply retention decision
      |
      +--> keep encrypted payload briefly
      +--> remove rendered/plaintext artifacts
      +--> delete encrypted payload at due time
      +--> keep minimal outcome/audit
```

What must be avoided is creating **untracked raw copies** at each step. Every data store must have an owner and a retention policy.

## 7. Table: which data to keep, which data to delete?

| Data | While pending send | After submission | Explanation |
| --- | --- | --- | --- |
| Notification ID | Keep | May keep per audit policy | Not email content, though still linkable to individuals |
| Recipient ID | Keep | May keep with limits | Used for correlation, suppression, and auditing |
| Plaintext recipient email | Only when truly needed; restrict access | Restrict or replace with reference | Protect PII |
| Template key/version | Keep | May keep | Supports auditing and authorized content reconstruction |
| Sensitive template model | Encrypt if persisted | Delete once retry need ends | Can data be reconstructed from another source? |
| Rendered HTML/plaintext | Prefer generating close to send time | Remove persistent copies when unneeded | Avoid holding identical content in many places |
| Raw MIME | Do not store by default | Do not store by default | May contain tokens, Bcc, attachments |
| Attachment temp file | Keep long enough for worker read | Clean up per lifecycle | Do not delete before serialization |
| Encrypted attachment blob | When needed for retry/audit | Delete per TTL/retention | May involve object versions/backups |
| SMTP provider ID | Keep when available | Keep for bounded reconciliation | Not guaranteed supported by every provider |
| Delivery/bounce events | Purpose-bound, minimal fields | Retain minimally | May contain diagnostic PII |
| One-time token | Avoid plaintext storage | Revoke/expire | Hash tokens or use specialized store |

Exact retention policies must be decided based on business needs, contracts, regulations, and investigative requirements—**there is no universal TTL right for every system**.

## 8. Deleting content immediately after send can break retries

An unsafe pattern for reliability:

```java
try {
    mailSender.send(message);
} finally {
    payloadRepository.delete(notificationId);
}
```

If `send(...)` fails transiently, loses the connection, or yields `UNKNOWN`, the payload may already be deleted even though policy still requires retrying or reconciling.

A sounder model:

1. Classify the attempt outcome.
2. Persist the result durably.
3. Determine whether the payload is still needed for a subsequent attempt.
4. Schedule purging only when retention policy allows.
5. Clean up **plaintext artifacts** as soon as the processing scope ends.
6. When purging fails, trigger retries/alerts.

**Early plaintext cleanup** and **deleting all encrypted sources** are two distinct decisions. You can avoid persisting plaintext from the outset while keeping the encrypted payload long enough for reliable retries.

## 9. Send only what the recipient truly needs

Instead of sending an Excel file packed with full customer records:

```text
Subject: Q4 Customer Report
Attachment: customers-all-fields.xlsx
```

design content containing only authorized fields:

```text
Subject: Q4 Summary Report
Body: 235 orders completed
Attachment: Not required
Link: Authenticated portal for detailed data
```

If the product requires users to download a sensitive document, an authenticated portal with authorization, auditing, TTLs, and revocation capability is often safer than an attachment that cannot be recalled once forwarded. However, links also carry leakage risks; do not replace attachments with indefinite public/bearer URLs lacking controls.

## 10. Spring Mail does not automatically encrypt email content before sending

Example:

```java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, true, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("recipient@example.net");
helper.setSubject("Notification");
helper.setText(
        "Notification content",
        "<p>Notification content</p>"
);

sender.send(mime);
```

This code constructs a MIME email; it does not apply end-to-end encryption. `MimeMessageHelper` helps assemble content and MIME parts; it neither replaces a key management system nor turns content into S/MIME/PGP.

If the application saves `MimeMessage`, serializes it to a file, prints it via `writeTo(System.out)`, or logs exceptions with payloads, information can appear in readable form in those places.

## 11. What does STARTTLS help with, and what does it not?

A common Spring Boot configuration:

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
      "[mail.smtp.timeout]": 15000
      "[mail.smtp.writetimeout]": 15000
```

This is an **illustrative configuration** for an SMTP relay supporting STARTTLS and username/password authentication. Ports, TLS modes, and properties must match your specific provider. Implicit TLS differs and typically uses a dedicated port.

`mail.smtp.starttls.required=true` requires upgrading to STARTTLS rather than silently falling back to plaintext on a connection configured this way. Verifying server identity with appropriate certificate/hostname policies reduces the risk of connecting to the wrong endpoint.

**Limits of STARTTLS:** when configured correctly, it protects the connection **from the application to this SMTP relay**. It does not guarantee the relay will not read/store the email, does not guarantee every inter-server hop uses TLS, and does not guarantee emails are encrypted in the recipient's mailbox.

## 12. Encryption at rest: protecting copies stored by the application

Multiple protection layers exist:

| Layer | Example | Prevents | Does not prevent |
| --- | --- | --- | --- |
| Disk encryption | Volume encryption | Physical disk/device theft | Processes permitted to read filesystem |
| Database transparent encryption | DB-engine TDE | Certain lost backup/disk files | DB users permitted to query plaintext |
| Object storage server-side encryption | KMS-managed bucket encryption | Unauthorized storage-media access per policy | Apps/services with GetObject+Decrypt permissions |
| Application-level field encryption | AES-GCM before row insert | Reading DB dumps without keys | App/KMS principals granted decrypt |
| Client-side E2E mail encryption | S/MIME/OpenPGP | Providers ordinarily cannot read protected content | Header/metadata exposure and endpoint compromise |

Layers can be combined. **No single layer eliminates every risk**. For instance, application-level encryption reduces the impact of a leaked DB dump, yet if an attacker also obtains KMS credentials, protection drops substantially.

## 13. Choosing authenticated encryption: AES-GCM

When a small payload must be encrypted before storing in the outbox, **AES-GCM** can be used. It provides:

- Content confidentiality.
- Integrity/authenticity verification via an authentication tag.
- Support for **Additional Authenticated Data (AAD)** to bind ciphertext to context.

Rules:

1. Use an AES key of appropriate strength (e.g., 256-bit per policy).
2. Use a nonce/IV **never reused with the same key**; 96 bits is the standard size for GCM.
3. Generate a fresh IV with high-quality `SecureRandom` for every encryption operation.
4. Store version/algorithm, IV, ciphertext+tag, and key reference.
5. Never invent custom AES modes or Base64-encode data and call it "encryption."
6. Never use ECB or unauthenticated modes for new payloads.
7. When tag verification fails during decryption, **never return partial plaintext** or ignore the error.
8. Keep secrets out of source code/public configs; manage them via KMS/HSM/secret manager.

### What is AAD used for?

For example, AAD can include:

```text
tenantId | notificationId | payloadType | schemaVersion
```

That way, ciphertext copied onto another notification with different AAD will fail decryption. AAD **is not encrypted**, so never put sensitive information into AAD expecting it to be hidden.

## 14. Java example: encrypting and decrypting payloads with AES-GCM

This is an **illustrative component for application-level encryption**, not a built-in `JavaMailSender` API. In production, keys must come from a KMS/secret management mechanism, and payload metadata needs explicit versions/schemas.

```java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;

public final class PayloadAesGcm {

    private static final int IV_LENGTH = 12;      // 96-bit GCM nonce
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    public record SealedPayload(
            int formatVersion,
            byte[] iv,
            byte[] ciphertextAndTag
    ) {
        public SealedPayload {
            iv = iv.clone();
            ciphertextAndTag = ciphertextAndTag.clone();
        }

        @Override
        public byte[] iv() {
            return iv.clone();
        }

        @Override
        public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    public static SealedPayload encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad
    ) throws GeneralSecurityException {

        byte[] iv = new byte[IV_LENGTH];
        RANDOM.nextBytes(iv);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, iv)
        );
        cipher.updateAAD(aad);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return new SealedPayload(
                1,
                iv,
                ciphertextAndTag
        );
    }

    public static byte[] decrypt(
            SecretKey key,
            SealedPayload sealed,
            byte[] aad
    ) throws GeneralSecurityException {

        if (sealed.formatVersion() != 1
                || sealed.iv().length != IV_LENGTH) {
            throw new GeneralSecurityException(
                    "Unsupported encrypted payload format"
            );
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, sealed.iv())
        );
        cipher.updateAAD(aad);

        // Throws AEADBadTagException if ciphertext/AAD/key
        // was modified or does not match.
        return cipher.doFinal(sealed.ciphertextAndTag());
    }
}
```

Usage:

```java
byte[] aad = buildAad(
        tenantId, notificationId, "mail-template-data", 1
);

byte[] plaintext = serializeApprovedTemplateModel(model);
PayloadAesGcm.SealedPayload sealed =
        PayloadAesGcm.encrypt(dataKey, plaintext, aad);

// Persist sealed.iv(), sealed.ciphertextAndTag(),
// formatVersion, and the dataKey reference.
```

`buildAad(...)` and `serializeApprovedTemplateModel(...)` are application-provided functions. **Construct AAD in a canonical, unambiguous format**, such as length-prefixed/typed serialization rather than concatenating strings with delimiters that might appear in inputs.

### What is still missing from this example?

- No code provisioning/fetching keys from KMS.
- No schema versioning for business data.
- No authorization checks on the caller requesting decryption.
- No key rotation/revocation management.
- No policy for handling KMS errors, rate limits, or unavailable keys.
- No cleanup/retention or database access controls.
- No logging/redaction policy for exceptions.

Never copy this example into production with a hardcoded AES key in source code.

## 15. Nonce reuse is a critical risk in GCM

Under the same GCM key, **reusing an IV/nonce** across two messages can compromise both confidentiality and integrity. Therefore:

```java
// Do not do this:
byte[] iv = new byte[12]; // all zeros for every payload
```

In the Java example, `SecureRandom` generates a random IV for every encryption call. For extremely high-volume systems or many instances sharing a key over long durations, enforce encryption limits per key and nonce management aligned with cryptographic safety standards for the chosen scheme.

**Do not increment an IV using a static variable in the JVM if multiple nodes share a key**; nodes can produce duplicate values. If using counter-based nonces, the counter requires a distributed/recoverable design guaranteeing strict uniqueness.

When an audited, maintained crypto library/provider offers an envelope encryption API, prefer that abstraction over building custom cryptographic formats.

## 16. Encrypt the JSON payload or encrypt individual fields?

Two common approaches exist:

**Encrypt the entire payload object**:

```json
{
  "encryptedPayloadRef": "opaque-ref-123",
  "schemaVersion": 2
}
```

The payload lives in a dedicated store as ciphertext; the template model is decrypted only when rendering.

**Encrypt individual fields**:

```text
notification_id         UUID (clear metadata)
template_key            string
recipient_email_enc     ciphertext
display_name_enc        ciphertext
invoice_data_ref        opaque reference
```

| Strategy | Pros | Cons |
| --- | --- | --- |
| Whole-object encryption | Lower risk of missing a field; easier to restrict decrypt permissions | Hard to query/filter on one field |
| Field-level encryption | Can separate permissions per field | Complex schema/key/rotation management |
| Storage encryption only | Simple, usually minimal app code change | App/DB principals can read plaintext |
| Data minimization + references | Reduces content held in mail DB | Must manage source data and source lifecycle |

If you must query by email address when the column is randomly encrypted with AES-GCM, direct equality queries on ciphertext fail because each encryption uses a fresh nonce. You can design a **blind index/HMAC** over normalized values per policy, though it introduces frequency-analysis risks and also requires a separate key and rotation.

Never apply unkeyed SHA-256 over a small, guessable set like emails/OTPs and assume it provides strong anonymization.

## 17. KMS and envelope encryption

A production pattern commonly uses **envelope encryption**:

```text
Key Management Service (KMS)
           |
           | generate/wrap data key
           v
Encrypted Data Key (EDK) ----> store with ciphertext
           |
           | plaintext data key available briefly
           v
Application encrypts payload with AES-GCM
           |
           v
DB/Object Storage:
  - ciphertext
  - IV/nonce
  - auth tag
  - encrypted data key / key reference
  - algorithm + schema version
  - AAD context identifiers
```

At decryption time:

1. Verify caller/tenant/notification authorization.
2. Fetch ciphertext, IV, and wrapped data key.
3. Call KMS to unwrap the data key under proper permissions and context.
4. Decrypt AES-GCM with the exact AAD.
5. Retain plaintext only long enough to render/send.
6. Never log the data key or plaintext.

KMS may encrypt small payloads directly or manage master keys wrapping data keys. The choice depends on API limits, payload size, latency, cost, rotation, and security requirements.

### What does KMS protect?

KMS manages key lifecycles, access controls, and auditing; it **cannot stop application code authorized to decrypt from logging plaintext**. Separation of privileges and least privilege remain essential.

## 18. Designing metadata for encrypted payloads

A record can contain:

```text
payload_id
notification_id
tenant_id
format_version
data_schema_version
algorithm_id = AES-256-GCM
kms_key_ref
encrypted_data_key
iv
ciphertext_and_tag
created_at
expires_at
encryption_context_version
```

Setting `expires_at` **does not make data vanish automatically**. You need a worker or storage TTL/lifecycle capable of actual deletion and a way to prove cleanup state.

### Do not "store a key ID" in place of key management

A `kms_key_ref` column only identifies the key; you must design:

- Which tenant/region/data class owns the key?
- Which principals may decrypt?
- Are permissions separated across mail workers, web APIs, and admins?
- How does key rotation affect older data?
- If a key is revoked, what happens to pending/retrying notifications?
- Do KMS logs/audits contain sensitive identifying information?

If the email pipeline serves multiple tenants with strict isolation, consider appropriate key scopes and IAM conditions.

## 19. Rotation, re-encryption, and cryptographic erasure

**Key rotation** can mean several things:

- Creating a new master/wrapping key version for new data.
- Rewrapping old encrypted data keys under the new key version.
- Re-encrypting payloads with fresh data keys.
- Revoking a compromised key.
- Destroying a key so associated ciphertexts can no longer be decrypted.

Never assume "enabling auto-rotation on KMS" automatically re-encrypts all existing ciphertexts or removes the ability to decrypt older versions. Behavior depends on the key management system and envelope encryption pattern.

### Cryptographic erasure

When content is no longer needed, you can delete ciphertexts and/or destroy the keys needed to decrypt them. Key destruction can render encrypted copies left in backups undecryptable, **but only if no copies of the key, data key, or plaintext remain elsewhere**.

For example, if 1,000 records share one data key and 999 must still be kept, you cannot destroy that key to erase only the first record without losing the other 999. Design key granularity upfront if selective erasure is required.

**Never claim absolute deletion by deleting a KMS alias.** An alias is a name/routing pointer, not necessarily the key material; follow proper key lifecycles and account for irreversible impacts.

## 20. Searchability and its relationship to privacy

Operations teams often want to look up notifications by email. If you store raw emails for searching, body encryption only protects part of the data.

Options:

- Store an internal `recipientId` and look up emails through an authorized service.
- Use an HMAC index following defined canonicalization.
- Store prefixes/domains or statistical buckets when sufficient for analytics.
- Separate PII tables with restricted roles/permissions.

HMAC index:

```text
index = HMAC(searchKey, canonicalRecipientEmail)
```

cannot be reversed directly without the key, yet still leaks equality and value distribution. For low-entropy data, assess guessing risks, key compromise, search permissions, and rotation. The HMAC search key should not be shared with encryption keys.

Never put blind indexes into public logs or metrics and assume they are no longer personal data; they can still serve as linking identifiers.

## 21. Immutable payloads for retries without storing plaintext

Suppose an invoice email must be resent if the provider temporarily loses connectivity. One option:

```text
Invoice issued
   |
   v
Create versioned immutable invoice PDF
   |
   v
Encrypt object or store with controlled KMS encryption
   |
   v
Outbox:
  notificationId
  recipientId
  templateVersion
  invoiceObjectVersion
  encryptedModelRef
   |
   v
Worker loads/decrypts and sends
```

There is no need to store a serialized raw `MimeMessage` in the database if it can be rebuilt from an immutable snapshot. However, if business or legal rules require **retaining the exact issued bytes**, maintain a dedicated compliant archive with its own retention and encryption, rather than repurposing logs or temp folders as storage.

### Why are versioned objects needed?

If an object key points to a file that changes over time, a subsequent retry could send a different invoice than the first attempt. Data minimization must never trade away content correctness. Use object versions or immutable content addressing where appropriate without leaking information.

## 22. Email body and template model: where to store them?

An HTML email can be produced from:

```text
templateKey = payment-receipt
templateVersion = 4
model = {
  customerDisplayName,
  orderCode,
  totalAmount,
  receiptLink
}
```

Strategies you can apply:

| Strategy | When appropriate | Caveats |
| --- | --- | --- |
| Render near send time from business data | Content must reflect latest state | Data may mutate; clear policy needed |
| Encrypted model snapshot | Need consistent content across retries | Manage keys, schemas, TTLs |
| Store encrypted rendered MIME | Byte-for-byte archive requirement | High storage cost, risk of multiple copies |
| Store only ID and portal link | No need to attach sensitive content | Access controls and token expiry |

There is no single right strategy. For a "Current order status" email, rendering fresh data may make sense; for an issued invoice, an immutable snapshot is usually needed to prevent content drift on retries.

## 23. Do not put plaintext reset tokens in the outbox

A common mistake:

```java
record ResetPasswordMail(
        String email,
        String resetToken,
        String html
) {}

// Push a record holding the raw token into queue/log/database.
```

If the token is stored in plaintext, anyone able to read the queue/outbox can use it to hijack the account while the token remains valid.

An alternative design depending on architecture:

1. Generate high-entropy tokens with a CSPRNG.
2. Store only a suitable **token verifier/digest** in the reset-password system (protected), with TTL and single-use state.
3. In the email-sending step, either generate the token close to send time or hold the token awaiting delivery in an **encrypted store with an ultra-short retention window**, keeping raw tokens out of logs.
4. Restrict the mail worker's decryption privileges.
5. Revoke tokens on use, expiration, or successful password reset.
6. If the email needs retrying after the token expires, **do not resend the expired link**; enforce policy to issue a new request.

Storing a one-way token hash supports verifying the token later, **but cannot reconstruct the token to send the email**. Thus, the "create token then send asynchronously" problem requires choosing an appropriate strategy: temporarily encrypting the token, generating the token in the worker, or a dedicated token-issuance workflow. Never describe hash storage as if the original token could be recovered from the hash.

### Considerations for tokens in URLs

Magic links/reset links can appear in browser history, proxy logs, email security scanners, or link previews. Use TTLs, one-time use, official domains, HTTPS, and mechanisms preventing prefetchers from accidentally redeeming tokens. Replacing a raw OTP with a bearer-token URL **does not by itself eliminate secret exposure risks**.

## 24. Encryption at rest does not replace TLS and recipient validation

A well-encrypted outbox record can still go to the wrong recipient if:

```java
helper.setTo(untrustedRecipient);
sender.send(message);
```

The `To` value might come from unvalidated input or stale business data. In that case, the secret is properly decrypted yet delivered to the wrong person.

Before submission:

- Verify the recipient is authorized to receive this notification type.
- Check consent/suppression per regulations and business rules.
- Verify tenant ownership.
- Never take `Bcc` and `Reply-To` arbitrarily from untrusted headers.
- Confirm templates and attachments belong to the right notification.
- Never render raw HTML directly from user data without escaping.

**Data encryption is a defense layer, not a substitute for authorization and recipient correctness.**

## 25. Data in the Java heap: limits of "erasure"

When decrypting payloads, the application may create:

```java
byte[] plaintext = decrypt(...);
String html = renderer.render(...);
MimeMessage message = sender.createMimeMessage();
```

A `byte[]` can be overwritten after use:

```java
try {
    processPlaintext(plaintext);
} finally {
    Arrays.fill(plaintext, (byte) 0);
}
```

Yet this **does not guarantee every plaintext copy vanishes from the heap**:

- Immutable `String` instances have no reliable wipe mechanism.
- Renderers/template engines may create intermediate strings and buffers.
- Jakarta Mail may hold data inside MIME parts.
- Java/JIT/GC can copy or relocate objects in memory.
- Crash dumps/core dumps/heap dumps may capture rendered content.

Therefore, the realistic goal is **minimizing lifetime and copy count**, controlling heap dumps and swap/disk, avoiding long object retention, and never promising absolute zeroization on a managed JVM runtime.

## 26. Temp files are data copies even outside the database

When generating PDF/CSV attachments:

```java
Path file = Files.createTempFile(
        "mail-invoice-", ".pdf");
invoiceRenderer.writeTo(file, invoiceData);
```

This file may reside on:

- Local container/VM disk.
- Mounted shared filesystems.
- Volumes shared with other processes.
- Disks with snapshots or backups.
- Ephemeral storage persisting across the node lifecycle.

**Never assume a "temp" directory means files disappear automatically after mail is sent**. Nor should sensitive data go into directories with broad read permissions.

### Rules for temp files

1. Create inside a dedicated directory with restricted permissions.
2. Never embed email addresses, full names, or secrets in filenames.
3. Use random/opaque names to avoid collisions.
4. Keep only long enough for MIME serialization and the defined retry policy.
5. Delete when no longer needed; log failures if deletion fails.
6. Run a periodic sweeper for files orphaned after crashes.
7. Enforce disk quotas and capacity alerts.
8. Consider volume encryption or dedicated file encryption for highly sensitive content.
9. Never let workers load files from user-supplied paths without validating permissions and paths.
10. Avoid enabling backups/snapshots on temp directories by habit if incompatible with retention.

## 27. FileSystemResource may be read during send, not during addAttachment

Example:

```java
Path invoicePath = createTemporaryInvoice();

MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, true, "UTF-8");
helper.setTo("recipient@example.net");
helper.setFrom("billing@example.org");
helper.setSubject("Invoice");
helper.setText("See the attached invoice.");
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath)
);

Files.delete(invoicePath);  // May delete too early!
sender.send(mime);
```

`addAttachment(...)` binds a content source to a MIME part; the file may only be read when Jakarta Mail serializes the message or the transport transmits `DATA`. Deleting the file before `send(...)` can cause sending to fail or leave the attachment unreadable.

A safer lifecycle example for **synchronous sending**:

```java
Path invoicePath = createTemporaryInvoice();

try {
    MimeMessage mime = composeWithAttachment(invoicePath);
    sender.send(mime);
} finally {
    Files.deleteIfExists(invoicePath);
}
```

**Condition:** this example only fits when the file can be discarded right after the attempt and the application either holds a durable source for retries or has an explicit failure policy. For asynchronous sending, deleting in the caller's `finally` block right after enqueueing is **far too early**. For crash recovery retries, an ephemeral temp file is insufficient.

## 28. Do not arbitrarily use single-use InputStreamResource

An `InputStreamResource` typically wraps an already open stream that can be read only once. Jakarta Mail may request data from a MIME part across multiple phases.

```java
InputStream stream = storage.openStream(key);
InputStreamSource risky = new InputStreamResource(stream);
helper.addAttachment(
        "document.pdf",
        risky,
        "application/pdf"
);
```

To support re-reading per contract, you can use:

```java
InputStreamSource source = () ->
        storage.openStream(versionedObjectKey);
```

Each call to `getInputStream()` opens a fresh stream. Still, ensure:

- The object/version remains present until the attempt finishes.
- Storage access enforces authentication/authorization and timeouts.
- Long-lived signed URLs are not written into logs or unprotected databases.
- Plaintext is not spilled onto unmanaged local disk.
- Streams are closed per library lifecycle contracts.
- Never assume streaming guarantees zero plaintext in the heap.

For encrypted objects from object storage, decryption streams must enforce size bounds and verify content authenticity; when using authenticated encryption, **never serve unauthenticated bytes as a valid attachment**. Choose streaming authenticated-encryption libraries/formats with clear contracts for large files rather than splitting a GCM ciphertext arbitrarily and sending unverified chunks.

## 29. Attachments in object storage: lifecycle and versioning

An architecture:

```text
Encrypted object:
  tenant/invoice/opaque-id/version
             |
             v
Outbox holds:
  notificationId + objectVersionId
             |
             v
Worker decrypts/streams content
             |
             v
JavaMailSender SMTP submission
             |
             v
Retention worker deletes object/version
```

When object storage enables versioning:

- Deleting the current key may create only a delete marker.
- Older versions remain stored.
- Replication may maintain extra copies in another region.
- Lifecycle expiration may act per version under separate rules.
- Incomplete multipart uploads may require cleanup routines.
- Backups or object lock/retention policies may block immediate deletion.

**Do not report "payload completely deleted" simply because a delete-object call returned success** if storage retains independently managed versions/replicas.

### What should a cleanup job know?

```text
payloadReference
objectVersion
encryptionKeyReference
expiryPolicy
retentionHold
deletionRequestedAt
deletionConfirmedAt
lastErrorCategory
```

Objects targeted for deletion must come from verified internal metadata, never by assembling paths from user-supplied email strings.

## 30. Retention varies by state

An illustrative policy, **not a fixed duration recommendation**:

| State | Keep content? | Decision rule |
| --- | --- | --- |
| `PENDING` | May retain encrypted payload/reference | Not yet dispatched |
| `PROCESSING` | Keep until attempt completes or lease reconciles | Worker actively using source |
| `RETRY_WAIT` | Keep source long enough for next attempt | Check TTL and validity |
| `SUBMITTED` | May delete source per policy | Is retention needed for audit/recipient resend? |
| `FAILED` | May delete early after investigation window | No need to keep full bodies forever |
| `UNKNOWN` | Consider short-term retention of encrypted source | Unknown whether already sent |
| `CANCELED` | Remove payload when no other purpose remains | Do not disturb externally submitted records |
| `EXPIRED` | Delete tokens/attachments per policy | Content no longer valid |

Some systems retain encrypted payloads briefly after `SUBMITTED` to support **manual resends**. If required, enforce resend permissions, auditing, and duplicate-risk controls; never cite "might resend" as grounds for indefinite storage.

### Delete payload only, keep minimal metadata

Post-purge, you may keep:

```text
notificationId
messageClass
templateVersion
createdAt
submittedAt
status
payloadPurgedAt
providerRoute
errorCategory (not raw body)
```

Even metadata can constitute personal data when linkable to a recipient/tenant. Metadata retention must also be reviewed; "contains no body" does not justify keeping it forever.

## 31. Designing retention policies around purpose

Do not apply a number like "30 days" across all notifications without justification:

- **Sending purpose:** minutes for OTPs, years for invoices, campaign lifespan for marketing.
- **Retention basis:** are there valid record/audit requirements?
- **Retry window:** what is the maximum allowed submission window?
- **Provider feedback window:** do bounces/deliveries need reconciliation?
- **Attachment source:** is it already officially stored in another business system?
- **Revoked data:** request cancelled, consent changed, user deleted account?
- **Storage locations:** primary DB, object versions, caches, backups, third-party logs.
- **Legal hold:** must a specific record be preserved?

A policy can be expressed as:

```text
DataClass: MAIL_TEMPLATE_MODEL
Purpose: render and retry transactional notification
Storage: application encrypted payload store
EligibleForPurge: terminal or retry expired
RetentionAfterTerminal: configured duration
LegalHoldSupport: yes
DeletionMethod: delete payload ref + wrapped DEK
Audit: status and timestamp only
```

Exact timeframes must be determined by business, security, and legal teams under applicable regulations. Never infer a uniform deletion deadline for all email types from Spring Mail.

## 32. Never couple purging directly to the SMTP callback

An anti-pattern:

```java
sender.send(message);
payloadStorage.delete(payloadId);
```

If the process crashes after SMTP acceptance and before deletion, the payload stays behind. If deletion fails, the code needs a cleanup retry mechanism. If wrapped inside a long DB transaction, SMTP I/O holds locks unnecessarily.

A better design:

```text
Mail worker
   |
   +-- submit SMTP
   +-- record outcome
   +-- schedule payload retention deadline
   |
   v
Background cleanup worker
   |
   +-- selects eligible payloads
   +-- checks active leases/legal holds
   +-- deletes exact storage version
   +-- records minimal tombstone/result
   +-- retries cleanup failures safely
```

Cleanup should be **a stateful workflow** rather than an unobservable statement. That ensures object storage or KMS failures do not leave data sitting indefinitely unnoticed.

## 33. Data model: separating outbox from encrypted payloads

Pedagogical PostgreSQL example:

```sql
CREATE TABLE mail_notification (
    notification_id UUID PRIMARY KEY,
    recipient_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    encrypted_payload_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mail_encrypted_payload (
    payload_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    format_version INTEGER NOT NULL,
    kms_key_ref VARCHAR(250) NOT NULL,
    encrypted_data_key BYTEA NOT NULL,
    iv BYTEA NOT NULL,
    ciphertext_and_tag BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE',
    deletion_requested_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_mail_payload_expiry
    ON mail_encrypted_payload(expires_at, payload_id)
    WHERE state = 'AVAILABLE';

CREATE TABLE mail_submission_attempt (
    attempt_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_notification(notification_id),
    status VARCHAR(32) NOT NULL,
    provider_key VARCHAR(80),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);
```

In production, systems typically add recipient policies, tenant isolation, foreign key constraints, storage object versions, indexes, and concurrency controls. Do not treat this schema example as a drop-in migration.

### Why not put the payload bytea directly on the notification row?

Separating tables helps:

- Restrict `SELECT` privileges to components needing decryption.
- Apply independent retention/indexes and lifecycles.
- Delete bodies/attachment sources while keeping audit metadata.
- Reduce how many people/workers read sensitive data.

However, table separation does not prevent leaks on its own if every service shares database credentials with access to both tables.

## 34. Purging must avoid racing active send workers

Scenario:

```text
10:00 Worker A claims mail, starts reading encrypted payload
10:01 Cleanup worker sees expires_at passed
10:01 Cleanup deletes payload
10:02 Worker A needs to read attachment a second time
10:02 SMTP submission fails because source is gone
```

A resolution approach:

- Send workers hold sufficiently long claims/leases renewed during long processing.
- Cleanup deletes only when the notification is inactive and the payload is no longer referenced by valid attempts.
- If a shared payload serves multiple notifications, use reference counting or policies spanning all consumers.
- Never equate TTL expiration with certainty that the file is no longer in active use.
- When expiration mandates deletion under security policy, the worker must halt/cancel and record an appropriate status rather than continuing to send expired data.

The "wait for worker completion" rule and "delete expired data" rule need an explicit precedence policy, not just a single timestamp comparison.

## 35. Example cleanup states

```text
AVAILABLE
   |
   v
ELIGIBLE_FOR_PURGE
   |
   v
DELETE_IN_PROGRESS
   |
   +-- storage temporarily fails --> DELETE_RETRY
   |                                      |
   |                                      v
   |                              DELETE_IN_PROGRESS
   |
   +-- deletion confirmed -------> PURGED
   |
   +-- legal hold ---------------> HELD
```

**`PURGED` must be defined concretely:** removed from primary database? object version deleted? wrapped key deleted? or no longer reachable via the application? Avoid generic state names without specifying the scope of the guarantee.

If system-wide deletion compliance is required, maintain a manifest of storage targets and per-target results rather than a single boolean.

## 36. Conditional SQL purging

One step to identify due payloads:

```sql
SELECT p.payload_id
FROM mail_encrypted_payload p
WHERE p.state = 'AVAILABLE'
  AND p.expires_at <= now()
  AND NOT EXISTS (
      SELECT 1
      FROM mail_notification n
      JOIN mail_submission_attempt a
        ON a.notification_id = n.notification_id
      WHERE n.encrypted_payload_id = p.payload_id
        AND a.status IN (
            'PROCESSING', 'RETRY_WAIT', 'UNKNOWN'
        )
  )
ORDER BY p.expires_at, p.payload_id
FOR UPDATE OF p SKIP LOCKED
LIMIT 100;
```

This is an **illustrative query**, not a complete purge policy. In practice you must:

- Check legal holds, retention exceptions, shared references, and active leases.
- Claim payloads / mark `DELETE_IN_PROGRESS` inside a short transaction.
- Commit before calling object storage/KMS for operations outside the database.
- Retry when deletion fails on one of multiple storage targets.
- Remove sensitive bytes reliably once preconditions pass.
- Avoid wrapping network calls and complex cleanup inside a single database transaction.

**Never simply run `DELETE FROM mail_encrypted_payload WHERE expires_at < now()` in production** if workers might still use the data or a legal hold applies.

## 37. Delete idempotency and tombstones

A cleanup worker can crash after deleting an object and before updating the database. Upon restart, the object delete call may return "not found."

If the object version was verified as the intended deletion target, `not found` can be treated as cleanup complete within that specific scope. However, **never confuse "not found" caused by missing permissions or wrong keys with successful deletion**.

Tombstone metadata:

```text
payloadId
deletionRequestId
targetClass
deletionPolicyVersion
requestedAt
completedAt
resultCategory
```

Do not retain raw recipients or content just to prove content deletion. Store only minimal metadata per audit policy; tombstones also have their own retention period.

## 38. Backups and snapshots: primary deletion does not erase all copies immediately

When a database has backups:

```text
Primary DB: payload deleted at T1
Daily backup created at T0 (< T1)
Backup retained until T2 (> T1)
```

Backups may still contain older encrypted payloads. Answer:

- Are backups encrypted and who has restore rights?
- What is the backup retention period?
- Can an individual record be removed from an immutable backup?
- If a backup is restored, are recent deletion requests reapplied?
- If keys were destroyed/revoked, can backups still be decrypted?
- Do legal holds require keeping certain records?

**Expiration on backup rotation** can be an acceptable policy approach, provided timelines and limits are clearly documented. Never promise "immediate deletion from all backups" if infrastructure does not support it.

## 39. Restoring backups can bring deleted data back

A scenario:

```text
Day 1: user requests deletion
Day 2: primary payload purged
Day 3: incident -> restore backup from Day 0
Day 3: deleted payload appears again in restored DB
```

To prevent this:

1. Store deletion requests/tombstones or event logs in a source durable across restores.
2. When restoring, **replay deletion decisions** before returning data to active service.
3. Verify restored backups do not feed expired payloads back into mail workers to resend.
4. Distinguish technical recovery from restored authority to use data.
5. Maintain runbooks and exercises combining restores with retention.

If relying on cryptographic erasure via key destruction, make sure key material is not restored from another backup making old data readable again. Encrypted backups do not automatically satisfy deletion policies if keys are mismanaged.

## 40. Logs can be the biggest leak source

A log line:

```java
log.error("Failed to send mail: {}", mimeMessage, exception);
```

or:

```java
mimeMessage.writeTo(System.out);
```

can capture bodies, headers, To/Cc/Bcc, tokens, filenames, and attachments in policy-violating form. Logs may flow to multiple APM/SIEM systems retained longer than the outbox database.

### Logging principles

- Never log raw `MimeMessage`, `SimpleMailMessage`, or full Integration Messages.
- Never log template model payloads or `Map.toString()` containing PII.
- Never log `JavaMailSenderImpl` production debug sessions without explicit controls.
- Never place unsanitized raw exception messages into metric labels.
- Never log HTTP/webhook error bodies if they may contain recipients/content.
- Never ship attachments via tracing or crash reports.
- Use opaque IDs and normalized error categories.

Example metadata log:

```text
event=mail_submission_failed
notificationId=6b7f-opaque
attemptId=23e1-opaque
providerRoute=transactional-primary
failureCategory=SMTP_TEMPORARY
smtpReplyClass=4xx
containsAttachment=true
payloadRetentionState=ENCRYPTED
```

Even IDs require access restrictions if they can map back to a user.

## 41. JavaMail debug and SMTP protocol logging

Jakarta Mail supports enabling session debugging to inspect SMTP connections/exchanges. This helps in test environments but creates risk in production.

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
Properties props = sender.getJavaMailProperties();

// Do not enable in production without strict controls:
props.put("mail.debug", "true");
```

Depending on implementation and debug level, logs may include SMTP commands, recipient addresses, credentials masked or unmasked differently than expected, and other metadata. Never assume every library version redacts all credentials and PII automatically.

**A safer approach**:

1. Enable debugging only against SMTP test servers with synthetic data.
2. During production investigations, favor reply-code statistics, timings, and correlation IDs.
3. If protocol traces are unavoidable, restrict viewers, duration, environment, and collection methods.
4. Disable debugging right after investigation; check whether centralized log systems kept copies.
5. Never enable debug logging globally across all production traffic for days.

## 42. Exceptions and stack traces can also carry PII

`MailSendException` or nested `MessagingException` instances can contain:

- Failed recipient addresses.
- SMTP reply messages from the server.
- Host, route, or account metadata.
- Descriptions of payloads/attachments if embedded by custom code.

An interceptor logging full exceptions by default can ship PII straight to SIEM.

### Change how errors are classified

```java
public enum MailFailureCategory {
    PREPARATION,
    AUTHENTICATION,
    CONNECTION,
    RECIPIENT_REJECTED,
    MESSAGE_REJECTED,
    TIMEOUT_UNKNOWN,
    PROVIDER_RATE_LIMIT,
    STORAGE_UNAVAILABLE,
    UNCLASSIFIED
}
```

Persist the enum, protocol phase, and correlation ID; for detailed diagnostics, use a secured channel with its own TTL. There is no need to retain raw `ex.getMessage()` on notification records just for support dashboards.

### Avoid storing exception objects in queues

Never serialize full `Throwable`, `MimeMessage`, or `ErrorMessage` objects into dead-letter queues if they can contain sensitive payloads. A DLQ record should carry an ID, error category, and reference to managed state under proper ACLs and retention.

## 43. Tracing and APM: keep sensitive data out of spans

What not to do:

```java
span.setAttribute("mail.recipient", customerEmail);
span.setAttribute("mail.body", html);
span.setAttribute("mail.reset_token", token);
```

Better:

```java
span.setAttribute("mail.type", "transactional");
span.setAttribute("mail.provider_route", approvedRoute);
span.setAttribute("mail.has_attachment", true);
span.setAttribute("mail.outcome", "SUBMITTED");
```

Values such as `approvedRoute` should come from an allowlist rather than arbitrary user input.

Never use subjects, filenames, recipient emails, or unassessed email hashes as span names/metric labels. Tracing data is commonly exported to external backends under different retention policies than business databases.

## 44. Metrics should count states, not retain content

Example operational metrics:

| Metric | Purpose |
| --- | --- |
| `mail.payload.encrypted_total` | Count of encrypted payloads stored |
| `mail.payload.decrypt_failures_total` | Decryption/KMS/tag mismatch failures |
| `mail.payload.purge_eligible` | Payloads eligible for cleanup |
| `mail.payload.purge_attempt_total` | Cleanup attempts |
| `mail.payload.purge_failure_total` | Cleanup failures by type |
| `mail.payload.oldest_expired_age_seconds` | Age of oldest expired payload still retained |
| `mail.temp_files_bytes` | Bytes of undeleted temporary files |
| `mail.outbox.pending` | Jobs still requiring data to send |
| `mail.smtp.unknown_total` | Attempts with ambiguous outcomes |
| `mail.raw_mime_logging_incidents_total` | Info-control incidents if tracked |

Metric names are application-defined examples. Never place raw payload IDs, emails, tokens, attachment filenames, or ciphertexts into metric labels. To investigate a single notification, use authorized logs rather than high-cardinality time series.

## 45. Audit logs are not full-body archives

A sufficiently useful audit record:

```text
notificationId
createdAt
messageClass
templateVersion
recipientRef
submissionAttemptId
status
providerRoute
payloadPurgedAt
deletionPolicyVersion
```

Do not store by default:

```text
htmlBody
plainText
rawMime
attachmentBytes
resetToken
smtpPassword
```

If legal/business rules demand exact sent-email archival, build a **compliant archive** separately: encrypted, access-audited, with explicit retention, legal holds, backups, and deletion policies. Never rely on application logs as an evidence archive.

### Auditing decryption access

Some systems need to audit:

- Who/which service called decrypt?
- Business purpose/notification ID?
- When and in which environment?
- Which KMS key scope?
- Success/failure outcome?

Audits must not record plaintext or data keys. Auditing access helps detect a service reading encrypted payloads in anomalous bulk volumes.

## 46. The SMTP provider is an independent data processor

When sending:

```text
Spring app -> SMTP relay -> recipient provider
```

the relay/provider may retain messages, routing metadata, bounce logs, or copies under its own policies. Even if the application deletes the outbox immediately after `SUBMITTED`, the provider may still retain data.

Verify from provider contracts and documentation:

- Does the provider store full bodies/attachments?
- Do logs contain recipients/content?
- What are default and configurable retention periods?
- Do sandbox/test modes retain data differently from production?
- What are the data residency and subprocessor details?
- Does the provider offer message-log deletion or data requests?
- How long can the provider restore from backups?
- Who can access message events/history?

**Never claim the application can delete an email from the provider post-submission unless supported by provider contract/API.**

### Provider message IDs may still require protection

A `providerMessageId` usually does not contain plaintext email, yet it can link to a recipient/transaction inside the provider dashboard. Protect lookup access and keep it out of unnecessary public URLs.

## 47. Delivery webhooks do not need raw email content

Provider feedback often contains:

```text
provider
providerMessageId
eventType = delivered / bounced / deferred
eventTime
recipient metadata
diagnostic text (may be sensitive)
```

The application should normalize this into:

```text
notificationId
attemptId
recipientId
canonicalEventType
occurredAt
failureCategory
eventDedupeKey
```

If raw webhook bodies must be kept briefly to debug signatures or mappings, give them separate retention and access controls. Raw diagnostics may carry recipient addresses, mailbox responses, and other sensitive details; never keep them indefinitely by default.

### Do not use missing feedback as an excuse to retain bodies

If SMTP submitted and the provider emitted no delivered event, holding raw email bodies for another year **will not conjure missing feedback**. You can keep provider correlation IDs and reconcile via provider APIs/logs within a support window, then mark `UNOBSERVED` instead of extending full-body retention.

## 48. End-to-end encryption: S/MIME and OpenPGP

If the application genuinely needs to protect email content from intermediary mail providers, consider standards such as:

- **S/MIME:** encrypts/signs emails with certificates and public/private keys.
- **OpenPGP (PGP/MIME):** encrypts/signs payloads for recipient keys.

Conceptual model:

```text
Spring app
   |
   +-- Build MIME content
   +-- Encrypt for recipient public key
   |
   v
Encrypted MIME body
   |
   v
SMTP providers cannot ordinarily read protected body
   |
   v
Recipient client decrypts with private key
```

**This is E2E content encryption**, distinct from database outbox encryption or STARTTLS. However, it carries major limitations:

- Requires trusted public keys/certificates for recipients.
- Must manage key rotation, revocation, and opening older messages.
- Some mail clients have incomplete support or complex UX.
- Email headers such as `To`, `From`, and `Subject` may still be exposed or need separate protections depending on standards and implementation.
- Sender/recipient endpoints still see plaintext.
- If private keys are lost, recipients may be unable to decrypt.
- Malware, phishing, or forwarding decrypted content is not prevented by E2E alone.

Never encode HTML in Base64 and label it "encrypted." If adopting S/MIME/PGP, use audited/maintained libraries, manage keys properly, and test client compatibility.

## 49. Encrypting the outbox does not prevent providers from seeing content

Suppose:

```text
Encrypted outbox
      |
      v
Worker decrypts
      |
      v
MimeMessageHelper.setText(plaintext)
      |
      v
SMTP provider receives ordinary email
```

At send time, the provider can inspect content unless the email is end-to-end encrypted. Outbox encryption reduces risk **before and after submission inside the application**, rather than turning ordinary MIME email into E2E-encrypted mail.

This security boundary must be stated clearly during compliance reviews or user privacy notices.

## 50. A document download link can be easier to revoke than an attachment

A sensitive email can say only:

```text
You have a new document.
Sign in at https://portal.example.org/documents
to view your document.
```

Pros:

- The email does not carry the full document.
- Access can be revoked at the portal.
- MFA/re-authentication can be required.
- Auditing tracks who downloaded the document.
- TTLs, quotas, and DLP policies apply.

Cons:

- Recipients must sign in and have connectivity.
- Links/portals can be targeted by phishing spoofing.
- Metadata in the email can still be sensitive.
- Documents already downloaded to recipient devices still cannot be fully recalled.

A **signed URL** is a bearer capability; anyone holding a valid URL can use it without further authentication layers. Never send multi-month signed URLs via email expecting the same security as an authenticated portal with sessions/MFA.

## 51. Avoid "password-encrypted ZIP with the password in the same email"

A common workaround:

```text
Email body: "The ZIP password is ABC123"
Attachment: secret.zip
```

If password and attachment travel in the same email, anyone accessing the email typically gets both. This adds negligible protection against unauthorized mailbox access.

Even when passwords travel via another channel, examine:

- ZIP encryption algorithms and client tool support.
- Password entropy and policy.
- Independent password delivery channel.
- Risk of passwords being persisted/logged.
- Retention durations for ciphertexts and keys.
- Recipient UX.

For high-sensitivity data, authenticated/authorized portals or supported E2E standards are generally preferable to ad-hoc attachment encryption schemes.

## 52. Never send secrets the application has no reason to disclose

Fields to exclude from template models unless genuinely required:

```text
password hash
API key
JWT refresh token
database credential
complete payment card data
internal session cookie
long-lived signed URL
unredacted identity document
```

In password-reset emails, send only a **one-time link** governed by safe policies—never send current passwords or attach session secrets.

For payment card numbers or highly sensitive identity records, evaluate whether email is an appropriate channel under business goals and regulations before even asking "where to encrypt."

## 53. Email headers can disclose data too

Even if the body is encrypted or unstored, a message still carries:

```text
From
To / Cc
Subject
Reply-To
Message-ID
Date
Received
Content-Type
```

Specifically:

- Subjects may appear on lock-screen notifications.
- `To`/`Cc` expose the recipient list by email semantics.
- `Bcc` must be handled carefully across envelopes and headers.
- Custom headers can accidentally leak sensitive IDs.
- `Message-ID` and `Received` headers expose tracing metadata.

Never put sensitive identifiers, OTPs, or medical visit details directly into the Subject. If internal correlation is needed, use opaque IDs with proper TTLs/permissions, never values allowing outsiders to fetch data.

## 54. Misdelivery cannot be fixed by purging alone

Sending an email with sensitive documents to the wrong recipient is an **authorization and data-disclosure incident**, not merely a database cleanup issue.

Preventive controls:

1. Validate recipient eligibility at send time, not only when scheduling.
2. Bind tenant, notification, and attachment ownership.
3. Verify template/model data belongs to the intended recipient.
4. Avoid reusing mutable `MimeMessage` objects across users.
5. For `Bcc`, test both SMTP envelopes and MIME headers.
6. Use provider test/sandbox modes rather than real addresses in QA.
7. Consider portal access instead of attachments for ultra-sensitive data.
8. Maintain an incident-response procedure for misdelivery.

Once an email reaches another person's mailbox, the application normally cannot force them to delete all copies. That makes **pre-send authorization** even more critical than post-send record cleanup.

## 55. Differences among encryption, redaction, pseudonymization, and deletion

| Measure | Example | Recoverable? | Purpose |
| --- | --- | --- | --- |
| Encryption | AES-GCM ciphertext + KMS key | Yes, with key and permission | Protect confidentiality at rest/in transit by layer |
| Redaction | Mask email to `j***@example.net` in logs | No from redacted copy, though source may exist | Reduce exposure in observability |
| Pseudonymization | Replace email with recipient ID | Linkable via mapping | Reduce direct identifiers |
| Irreversible deletion | Delete plaintext/ciphertext and decrypt capability | No, once all copies/keys handled | Reduce/eliminate stored data |
| Retention expiry | Mark as due for cleanup | Data may still remain | Signal triggering deletion |

**Pseudonymization is not anonymization** while the system retains mappings or enough attributes to re-identify users. Log redaction likewise does not remove sensitive sources from databases or backups.

## 56. Access control: only the mail worker should decrypt when needed

An application consists of components:

```text
Web/API service
Outbox dispatcher
Mail renderer + sender
Reporting dashboard
Cleanup worker
Security audit service
```

Not every component needs permission to decrypt full email models. One design:

| Component | Required permissions |
| --- | --- |
| Notification API | Write encrypted payload reference, create request |
| Outbox dispatcher | Read status/IDs, claim and enqueue |
| Mail renderer/sender | Decrypt exact payload of claimed notification |
| Reporting dashboard | Read aggregate metrics/statuses, not bodies |
| Cleanup worker | Delete scoped payloads/objects/keys; need not decrypt |
| Audit service | Read event metadata, not raw content |

Permissions must be enforced via IAM/KMS/DB grants/network access rather than relying solely on code conventions.

### Separate workers from dashboards

If the dashboard API shares database credentials or KMS permissions with the mail sender, a vulnerability in the dashboard could expose all payloads. Separating service identities and decryption permissions limits the blast radius.

When multiple tenants share a worker pool, authorization must also bind `tenantId` to notifications/outboxes and KMS encryption contexts. Never accept IDs from untrusted HTTP requests to arbitrarily decrypt another tenant's payloads.

## 57. Separating encryption context by tenant and notification

A key context might include:

```text
tenant_id
notification_id
payload_type
format_version
```

If KMS supports encryption context in envelope flows, bind that context to wrapped/unwrapped keys. Simultaneously, AES-GCM AAD can bind ciphertext to the logical record.

**Never rely on encryption context as sole authentication.** The application must still verify record read authorization, tenant ownership, and business role before calling KMS.

If context fields change during tenant migration or notification ID updates, older data may fail decryption without a re-encrypt/rewrap procedure. Storing context versions and exact metadata prevents logical "key loss" during migrations.

## 58. A mail-sending service with short-lived plaintext scope

Skeleton example:

```java
import java.util.Arrays;
import java.util.UUID;

public final class ProtectedMailWorker {

    private final EncryptedPayloadReader payloadReader;
    private final MailTemplateRenderer renderer;
    private final MailSubmitter submitter;

    public ProtectedMailWorker(
            EncryptedPayloadReader payloadReader,
            MailTemplateRenderer renderer,
            MailSubmitter submitter
    ) {
        this.payloadReader = payloadReader;
        this.renderer = renderer;
        this.submitter = submitter;
    }

    public void process(UUID notificationId) throws Exception {
        byte[] plaintextModel =
                payloadReader.decryptForClaimedNotification(
                        notificationId);

        try {
            RenderedMail mail =
                    renderer.render(plaintextModel);

            // submitter owns a distinct attempt record and
            // classifies SMTP result: SUBMITTED/FAILED/UNKNOWN.
            submitter.submit(notificationId, mail);
        } finally {
            Arrays.fill(plaintextModel, (byte) 0);
        }
    }
}
```

`EncryptedPayloadReader`, `MailTemplateRenderer`, `MailSubmitter`, and `RenderedMail` are application-designed abstractions. This snippet shows how to limit the scope of the decrypted `byte[]`; it **does not guarantee full-heap zeroization**, since the renderer may allocate `String`/MIME copies. Avoid caching `RenderedMail` or passing it through logging interceptors.

In a real system, persist a durable submission attempt prior to SMTP I/O and record the outcome afterward in a separate transaction. This snippet alone does not guarantee retries or exactly-once semantics.

## 59. Never hold a DB transaction open across decrypt, render, and send

Anti-pattern:

```java
@Transactional
public void send(UUID id) {
    Notification n = repository.lockById(id);
    byte[] model = crypto.decrypt(n.payload());
    MimeMessage message = compose(model);
    sender.send(message);  // SMTP I/O inside DB transaction.
    n.markSubmitted();
}
```

Problems:

- SMTP submission can take seconds or time out.
- Transactions/locks/connections are held open needlessly.
- Database rollback cannot "recall" an email already accepted by the provider.
- Crashing after SMTP acceptance and before DB commit can cause duplicate sending.
- Plaintext remains in memory longer while the method blocks on I/O.

Split it into:

```text
Transaction 1: claim notification + create attempt
              |
              v
Outside DB transaction:
  authorize decrypt -> render -> SMTP submit
              |
              v
Transaction 2: record attempt outcome
              |
              v
Cleanup worker: evaluate retention separately
```

When sending to multiple recipients in a single `MimeMessage`, also evaluate partial SMTP successes before retrying to avoid accidentally resending to recipients already accepted.

## 60. Do not use email attachments to transfer entire personal datasets

A report may need only:

```text
Total revenue this period: ...
Order count: ...
Link to authenticated admin portal
```

rather than:

```text
List of every customer + phone numbers +
addresses + payment histories as PDF/CSV
```

This reduces:

- Sensitivity of outbound emails.
- Volumes requiring encryption/storage/backup.
- Attachment copies across SMTP relays/mailboxes.
- Cost and complexity of retention/deletion.

If recipients genuinely need detailed records, grant audited downloads via a portal or API. **Do not strip fields legitimately required for lawful tasks**; determine minimum fields jointly with product/security stakeholders.

## 61. DLP and pre-send content checks

A pre-SMTP inspection layer can evaluate:

- Were secrets/credentials accidentally injected into the body?
- Do attachments contain data exceeding the recipient's permissions?
- Did the template render customer data from another tenant?
- Do files match allowed MIME types and size policies?
- Is the recipient domain permitted for this class of information?
- Is content classified as "portal only" being sent as raw email?

A flow:

```text
Render candidate message
      |
      v
Policy/DLP check
      |
      +-- Allowed --> SMTP send
      |
      +-- Blocked --> FAIL_CLOSED + safe audit
```

**Never log raw DLP-blocked content** just because it "needs investigation." You can store a reason code/category, a security fingerprint with separate retention, or a sample inside an authorized, controlled system if policy truly requires it.

A DLP scanner can miss leaks or produce false positives. It is a supplementary safeguard, not a substitute for bounding data at the business/template model level.

## 62. A data deletion request must have clear scope

Suppose a user requests deletion of email-related data. Determine:

1. Which notifications belong to that person?
2. Are any scheduled/pending outbox jobs still able to regenerate content?
3. Which encrypted payloads and attachment/object versions exist?
4. Which events/webhooks/projections contain PII?
5. Do raw MIME records/logs/traces or support tickets hold copies?
6. What retention rules govern backups/replicas?
7. Do legal holds or valid preservation duties apply?
8. Do external providers still retain emails/logs?

Do not claim "user data deleted" simply because one `mail_notification` row was removed while attachments and storage copies remain.

### Build a data inventory upfront

An internal inventory table might include:

| Store | Data class | Owner | Retention | Deletion mechanism |
| --- | --- | --- | --- | --- |
| Outbox DB | Encrypted template model | Mail platform | Per policy | Purge worker |
| Object storage | Encrypted attachment version | Document service | Per policy | Lifecycle + explicit delete |
| Redis/cache | Render/temp metadata | Mail worker | Short-term | TTL + eviction |
| Logs | Status/diagnostic metadata | Platform ops | Per policy | Log retention |
| APM traces | Technical spans | Observability | Per policy | Export retention |
| Backup | Encrypted DB/object snapshots | Infrastructure | Per backup policy | Expire/restore re-delete |
| External provider | Recipient/message feedback | Vendor account | Per contract | Vendor controls/request |

An inventory is a prerequisite for evaluating real deletion, without needing to embed this list inside every notification record.

## 63. Legal holds and mandatory retention requirements

Certain documents or notifications must be retained due to accounting obligations, contracts, internal investigations, or specific legal requirements. This can conflict with immediate deletion requests.

A retention engine should evaluate:

```text
Is content eligible for purge?
          |
          +-- No: still needed for processing/retry
          |
          +-- No: authorized legal hold / required retention
          |
          +-- Yes: schedule controlled deletion
```

**Never use a legal hold as an arbitrary flag to keep data forever.** Require an owner, legal/policy basis, scope, review deadline, and governance. Once a hold ends, re-evaluate retention and delete if no preservation grounds remain.

Specific rules vary by jurisdiction and data class; coordinate with legal/compliance owners rather than deriving a uniform TTL from Spring Mail.

## 64. Deleting data before sending: cancelling pending notifications

If a user withdraws a request or an OTP expires while a notification is still `PENDING`:

1. Update `status=CANCELED/EXPIRED` inside a transaction.
2. Prevent new workers from claiming the notification.
3. Determine whether an in-flight worker must abort per policy.
4. Delete or invalidate any generated token.
5. Purge the encrypted payload once no active lease/retention hold remains.
6. Write minimal audit metadata.

If a job was already claimed and started SMTP I/O, database cancellation cannot guarantee the email did not leave the system. Enforce business-state checks right before sending and clear rules for in-flight attempts.

## 65. Deleting after sending: avoid promising beyond your control

An API `deleteNotificationContent(notificationId)` can:

```text
Delete encrypted outbox payload
Delete local temp files
Delete object versions under app control
Prune archived MIME if retention allows
Scrub/cache eviction as supported
Schedule backup expiration/replay deletion
Keep minimal audit tombstone
```

It **cannot automatically**:

```text
Delete message from recipient mailbox
Delete forwarded copies
Delete screenshots/downloads
Delete a provider's backups without its cooperation
Guarantee zero RAM remanence on every JVM component
```

When reporting outcomes to callers/users, distinguish:

- `PURGED_FROM_APP_PRIMARY_STORES`.
- `ADDITIONAL_STORES_PENDING_RETENTION`.
- `EXTERNAL_EMAIL_ALREADY_SUBMITTED`.
- `BLOCKED_BY_AUTHORIZED_HOLD`.

These names are illustrative, not Spring Mail statuses. The goal is **accuracy about scope and progress**.

## 66. Encryption and deletion across environments

Development, staging, and production differ:

| Environment | Recommendation |
| --- | --- |
| Local development | Synthetic recipients/payloads, SMTP capture server |
| CI | No production secrets, fake KMS/test keys |
| Staging | Isolated KMS/test resources, never copy raw production PII |
| Production | Least privilege, encryption, retention, auditing, and monitoring |
| Disaster recovery | Restore tests covering key management + deletion replay |

A common mistake is copying the production database into staging "to test mail sending," causing staging to submit old notifications to real users or hold raw payloads in a less-protected environment.

If representative data is needed for benchmarks, use synthetic or properly sanitized datasets and disable real outbound mail delivery. When restoring databases, default to **disabling mail submission** until flags and deletion records are reconciled.

## 67. Test 1: encrypted storage contains no plaintext

A baseline test:

1. Create a synthetic payload containing a clear marker, e.g., `"TEST-SECRET-436"`.
2. Encrypt and persist via the test repository.
3. Read raw row/object bytes directly from the store.
4. Confirm the plaintext marker does not appear directly.
5. Decrypt with an authorized key and exact AAD.
6. Confirm the output matches the original fixture.

JUnit example using AES-GCM:

```java
import org.junit.jupiter.api.Test;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import static org.junit.jupiter.api.Assertions.*;

@Test
void encryptThenDecryptWithCorrectContext() throws Exception {
    KeyGenerator generator = KeyGenerator.getInstance("AES");
    generator.init(256);
    SecretKey key = generator.generateKey();

    byte[] plaintext =
            "TEST-SECRET-436".getBytes(StandardCharsets.UTF_8);
    byte[] aad =
            "tenant-1/notification-1/model-v1"
                    .getBytes(StandardCharsets.UTF_8);

    var sealed = PayloadAesGcm.encrypt(
            key, plaintext, aad
    );

    assertFalse(
            java.util.Arrays.equals(
                    plaintext,
                    sealed.ciphertextAndTag()
            )
    );

    byte[] restored = PayloadAesGcm.decrypt(
            key, sealed, aad
    );

    assertArrayEquals(plaintext, restored);
}
```

Testing `ciphertext != plaintext` is only a baseline assertion, **insufficient by itself to prove storage encryption is secure**. You still need vetted algorithms, secret handling, key management, and security testing at the relevant layers.

## 68. Test 2: modified ciphertext or AAD must be rejected

The GCM authentication tag must detect tampered data:

```java
@Test
void rejectsTamperedCiphertext() throws Exception {
    SecretKey key = newAesKeyForTest();
    byte[] aad = "notification-1".getBytes(UTF_8);

    var sealed = PayloadAesGcm.encrypt(
            key, "synthetic".getBytes(UTF_8), aad
    );

    byte[] corrupted = sealed.ciphertextAndTag();
    corrupted[0] ^= 0x01;

    var tampered = new PayloadAesGcm.SealedPayload(
            sealed.formatVersion(),
            sealed.iv(),
            corrupted
    );

    assertThrows(
            javax.crypto.AEADBadTagException.class,
            () -> PayloadAesGcm.decrypt(key, tampered, aad)
    );
}
```

`newAesKeyForTest()` and `UTF_8` are helpers/imports in the test class; the example highlights behavior rather than serving as a complete standalone test class.

A similar test modifying `aad` (e.g., a different notification ID) must also fail. The application **must never fall back to returning ciphertext as plaintext** or ignore tag validation failures.

## 69. Test 3: KMS permissions and tenant isolation

In integration tests using a KMS sandbox or policy-enforcing mock:

1. A mail worker belonging to tenant A is allowed to decrypt payload A.
2. Workers or APIs not belonging to tenant A **cannot** decrypt payload A.
3. A dashboard principal has status-read permissions only, no KMS decrypt rights.
4. A cleanup principal can delete targeted objects/versions without needing body decryption rights.
5. A modified encryption context is rejected per contract.
6. After key rotation, older payloads remain readable if policy requires.
7. When a key is revoked, workers handle the error via status updates instead of sending emails missing content.

Never conclude security is complete solely because a mocked unit test returns `AccessDenied`. Test actual IAM/KMS policies in staging or authorized environments, especially across multiple service accounts and cross-account boundaries.

## 70. Test 4: deletion does not break notifications still needing retries

Scenario:

```text
N1: PENDING      -> encrypted payload present
N2: RETRY_WAIT   -> encrypted payload present
N3: SUBMITTED    -> retention deadline expired
N4: UNKNOWN      -> reconciliation policy active
N5: FAILED       -> retention deadline expired
```

Run the cleanup worker with a fixed `Clock`:

- N1 is not purged because it is still pending.
- N2 is kept until the retry policy expires.
- N3 is purged if no legal holds, active references, or archive requirements apply.
- N4 is retained/flagged per `UNKNOWN` policy, never deleted automatically merely because the SMTP call threw an exception.
- N5 is purged if no purpose or hold remains.

**Retention tests must assert against the actual storage target**, not just a `deleted=true` flag on an entity. If the file/object remains readable, cleanup failed its goal.

## 71. Test 5: cleanup idempotency after crashes

A cleanup flow can crash at several points:

```text
A: claim deletion
B: delete object version
C: delete encrypted data key/reference
D: delete database ciphertext
E: mark completion/audit
```

Test simulating a crash after B followed by restart:

1. Cleanup knows the target version was already queued for deletion.
2. "Object not found" is classified accurately based on API/cause.
3. Steps C/D/E resume or reconcile safely.
4. Newer objects/versions are never deleted by mistake.
5. Unconfirmed steps are never recorded as completed.
6. Metrics/alerts fire if cleanup gets stuck past deadlines.

This is an **idempotent workflow pattern**, not an ACID transaction spanning database, object storage, and KMS.

## 72. Test 6: concurrent cleanup and active SMTP processing

A concurrency test:

```text
Mail worker A: starts reading attachment
Cleanup worker B: sees expires_at reached
Mail worker A: needs resource for MIME serialization
```

Verify:

- If policy allows active attempts to finish, cleanup respects active leases/references and avoids premature deletion.
- If policy mandates immediate cancellation upon expiry, the worker receives cancellation and withholds expired content within controllable bounds.
- If the email already passed SMTP acceptance, cancellation applies only to unsubmitted items and controllable retention targets.
- After work finishes, cleanup can be re-triggered.

Use `CountDownLatch`, transaction barriers, or deterministic test helpers to control timing instead of arbitrary `Thread.sleep(...)` calls. The key is verifying **state ordering** and storage availability under race conditions.

## 73. Test 7: no plaintext logged on happy or failure paths

Fixtures should include a synthetic marker:

```text
TEST-ONLY-SECRET-DO-NOT-LOG-436
```

Test flow:

1. Encrypt and store the synthetic payload.
2. Render and submit to an SMTP test server.
3. Force the sender to throw connection/auth/RCPT errors per scenario.
4. Capture logs/traces emitted by application components in the test environment.
5. Verify the marker never appears in application logs or serialized exceptions.
6. Verify structured events contain only permitted IDs/categories.

Do not use this marker test alone to claim **all** production logging is safe. Also review library configs, APM agents, SMTP debug flags, framework exception handlers, and log routing.

**Never capture real users' raw MIME** in tests; SMTP test servers should receive only synthetic fixture data.

## 74. Test 8: backup restore and deletion replay

An integration/disaster-recovery exercise:

```text
T0 Backup DB contains encrypted payload P
T1 Delete request for P recorded
T2 Primary DB purges P
T3 Restore backup from T0 into isolated DR test
T4 Replay authoritative deletion ledger
T5 Confirm P inaccessible before mail workers enabled
```

Verify:

- The deletion ledger was not lost along with the restored snapshot.
- All storage targets are updated properly.
- Mail submission stays **disabled** during DR restore until reconciliation completes.
- If ciphertexts remain in snapshots, appropriate encryption/ACLs and key policies exist.
- Audits do not disclose bodies/tokens.

Never test restoring production backups containing PII into unauthorized or less-secured environments.

## 75. Test 9: providers do not auto-delete after app purge

In integration tests using an SMTP sandbox:

1. The application submits a synthetic email containing a marker.
2. The application purges encrypted payloads and temp files.
3. The SMTP sandbox still holds the received message copy.
4. Tests verify this boundary is accurately documented in policies.

This prevents teams from mistakenly assuming "deleted in the app" means the email no longer exists externally.

If a provider exposes APIs to delete logs or suppress messages, test against the exact contract and distinguish **deleting provider logs** from **recalling emails delivered to recipient mailboxes**.

## 76. Test 10: retention by email type

A table-driven policy test:

| Content type | State | Expected outcome |
| --- | --- | --- |
| Expired OTP | `PENDING` | Do not send, revoke token, purge per policy |
| Invoice awaiting retry | `RETRY_WAIT` | Keep encrypted source until retry expiry |
| Marketing email opted out before send | `PENDING` | Cancel, do not send, purge source appropriately |
| Submitted email | `SUBMITTED` | Delete renders/temp files, retain minimal audit |
| Uncertain attempt | `UNKNOWN` | Reconcile or keep source briefly per policy |
| Record under legal hold | Terminal | Never purge against hold; review expiry |

Do not hardcode durations directly inside tests without policy versions/configs. Use `Clock.fixed(...)` and fixture expiry timestamps for deterministic tests.

## 77. Test 11: payload copied to another notification

Encrypt ciphertext for notification A with AAD:

```text
tenant-A | notification-A | templateModel | v1
```

Then attempt to decrypt those exact bytes using notification B's context. Under proper AES-GCM AAD, authentication must fail.

This test catches correlation errors or ciphertext swaps between records. However, it **does not replace authorization checks**; the application must still verify the caller may access A or B before attempting decryption.

## 78. Test 12: never send stale emails when payloads expire

Scenario:

```text
Reset token expires at 10:05
Mail worker delayed until 10:08
```

Expected behavior:

- Worker checks whether token/notification remain eligible.
- If the link expired, do not submit an email carrying a useless token.
- Mark the notification `EXPIRED/CANCELED` per policy.
- Purge temporarily stored token data.
- A new reset request must issue a fresh token with fresh state.

Never "extend tokens" automatically by altering `expiresAt` in the database without evaluating the security protocol; token issuance and reset verification require a unified security model.

## 79. Test 13: attachments are gone after cleanup

A test using synthetic files/objects:

1. Worker uses an immutable attachment object to send.
2. SMTP test server confirms exact attachment bytes were delivered.
3. Mark the notification past its retention deadline.
4. Cleanup deletes the exact object version and metadata key.
5. Verify storage APIs no longer return the attachment under relevant permissions.
6. Verify newer versions of an object sharing a name (if any) are not accidentally deleted.

Never treat `Files.exists(path)==false` as proof that all backups/snapshots and storage replicas are gone as well. Verification applies strictly to **the storage target under test**.

## 80. A security and reliability test matrix

| ID | Scenario | Protection layer | Observed outcome |
| --- | --- | --- | --- |
| S01 | Encrypted payload store | At rest | No direct plaintext in row/blob |
| S02 | Ciphertext tamper | Integrity | Decryption fails closed |
| S03 | AAD swapped notification | Context binding | Authentication tag failure |
| S04 | Unauthorized KMS principal | Access control | Decryption denied |
| S05 | Retryable SMTP failure | Lifecycle | Encrypted source kept long enough to retry |
| S06 | SMTP outcome UNKNOWN | Reliability | No blind purging or blind retrying |
| S07 | Submitted + TTL expired | Retention | Cleanup triggered accurately |
| S08 | Cleanup crash midway | Idempotency | Resumes without mis-deleting |
| S09 | Active worker vs cleanup | Concurrency | Never deletes sources violating policy |
| S10 | Application logs | Observability | Synthetic secrets never appear |
| S11 | Backup restore | Recovery | Deletion replay runs before workers open |
| S12 | Provider SMTP acceptance | External boundary | App purge never labeled as mailbox deletion |
| S13 | Object versions | Storage semantics | No targeted versions remain |
| S14 | Legal hold | Retention exception | Never deleted while valid hold applies |
| S15 | Expired reset token | Security | Never sends expired tokens |
| S16 | Bcc recipient | Privacy | Envelope accurate; no header logging/leak |

A suite includes unit, integration, and DR tests; not every test must run on every commit. Yet changes to crypto formats, retention workers, and mail routing require targeted testing prior to deployment.

## 81. Runbook: raw email discovered in logs

Suppose the team discovers a log line containing a reset link with a token:

```text
ERROR mail send failed:
  subject=Reset password
  body=https://example.org/reset?token=...
```

Response steps:

**Step 1 — Stop generating new copies.**

- Identify the offending logger/interceptor/debug property.
- Halt printing raw MIME or payload-bearing exceptions.
- Avoid emitting new log lines containing the same token during investigation.

**Step 2 — Triage scope.**

- Which services/instances wrote it?
- Are logs on local disk, stdout, APM, SIEM, or support tickets?
- Who had read access?
- What is the retention window and copy count?

**Step 3 — Mitigate active secret exposure.**

- Revoke/reset exposed tokens or credentials if permitted and protocol-safe.
- Avoid needlessly locking accounts without an incident workflow.
- For non-revocable data, apply incident response/compliance procedures.

**Step 4 — Clean up per platform capabilities.**

- Use platform log-deletion/redaction features if supported.
- Check retention/backups and exported copies.
- Record audit outcomes; never promise instant removal across all copies.

**Step 5 — Prevent recurrence.**

- Enforce structured safe logging.
- Add unit/integration tests using synthetic markers.
- Review code review checklists and default logging configurations.

Never paste raw logs containing tokens into chat channels or emails when asking for help.

## 82. Runbook: payloads overdue but not deleted

If `mail.payload.oldest_expired_age_seconds` rises:

1. Confirm whether the cleanup worker is running.
2. Check storage/KMS API errors, permissions, and rate limits.
3. Check whether active leases or notification states block purging.
4. Check for valid legal holds.
5. Check object version/delete marker/replication behavior.
6. Inspect deletion retry states and pending target counts.
7. Consider controlled increases to batch size/concurrency.
8. Prioritize high-sensitivity and longest-overdue records.
9. Record result categories and audit each batch.
10. Never force-delete payloads belonging to valid in-flight attempts without a formal cancellation policy decision.

If the cause was a cleanup job turned off for weeks, drain the purge backlog in bounded batches instead of deleting everything in one massive transaction.

## 83. Runbook: suspected encryption key compromise

Any incident involving a key/KMS principal must be treated with dedicated scope:

- Identify affected key versions, aliases, decrypt permissions, and payloads.
- Revoke compromised credentials/roles per procedure.
- Inspect KMS audit logs and access timestamps.
- Create new keys/versions for new data.
- Decide on rewrapping/re-encrypting retained data.
- Never delete a key still required to decrypt valid notifications without a recovery plan.
- Assess whether backups or caches holding data remain accessible.
- Check whether plaintext was exported externally.
- Monitor decryption errors/queue backlogs post-rotation.

**Rotation does not retroactively revoke data already read by an attacker.** Impact must be evaluated from access evidence and data scope.

## 84. Runbook: restore brings deleted data back

During a DR restore:

1. Place the system in **no-outbound-email** mode.
2. Restore databases/storage per approved plan.
3. Retrieve the deletion ledger/authoritative state from an appropriate source.
4. Replay deletions/cancellations committed after the backup snapshot.
5. Check expired/held records and active references.
6. Verify KMS key references and decryption permissions.
7. Reconcile notification statuses; never blindly resend an old outbox.
8. Run integrity/cleanup verification before enabling mail workers.
9. Document the scope of restored and reprocessed data.

If the deletion ledger resided inside the same old snapshot with no external source, replay capability may be lost. DR designs must therefore account for deleted data upfront.

## 85. Runbook: sensitive document sent to wrong recipient

An incident is not resolved by a lone `payloadStorage.delete(...)` call.

Assessment steps:

- Identify notification, recipient, attachments, and send timestamp.
- Determine whether root cause was upstream data, header mapping, mutable message reuse, or tenant authorization.
- Block similar sends immediately if necessary.
- Check whether the mail provider accepted it and whether delivery feedback arrived.
- Trigger appropriate security/legal/compliance workflows per sensitivity level.
- If the provider offers relevant controls, use them strictly per contract; never promise mailbox recall.
- Avoid creating extra copies in logs/tickets.
- Fix validation, ownership checks, tests, and monitoring.

Never send an "apology" email re-attaching all the sensitive data as part of incident handling.

## 86. Checklist: before placing payloads in the outbox

- [ ] Sensitive fields and sending purpose identified.
- [ ] Unnecessary fields stripped from template model.
- [ ] Recipient/tenant ownership and eligibility verified.
- [ ] Tokens enforce TTLs, one-time use, and revocation rules.
- [ ] Template/key/version recorded explicitly if reconstruction is needed.
- [ ] Persisted payloads encrypted at the appropriate layer.
- [ ] Data keys never stored in source code/DB in plaintext.
- [ ] AAD/context binding designed properly.
- [ ] Only designated services permitted to decrypt.
- [ ] No `MimeMessage`, raw HTML, or large `byte[]` pushed onto uncontrolled queues.
- [ ] Attachment references point to secure, non-public objects/versions.
- [ ] `expires_at` and retention policy version recorded.

## 87. Checklist: when workers build and send mail

- [ ] Decryption occurs only after claim/authorization is confirmed.
- [ ] Plaintext never kept in long-lived caches or debug logs.
- [ ] HTML rendered safely without cross-tenant/cross-recipient mixups.
- [ ] MIME subjects/headers omit unnecessary secrets.
- [ ] Bcc handled in accordance with privacy policies.
- [ ] SMTP TLS/certificate policy matches provider requirements.
- [ ] SMTP raw `DATA` never logged.
- [ ] Attachment files/streams live long enough for serialization.
- [ ] SMTP attempts durably recorded and outcomes classified.
- [ ] `UNKNOWN` outcomes never retried blindly without policy.
- [ ] DB transactions never held open across SMTP I/O.
- [ ] Post-attempt, plaintext artifacts cleaned up and encrypted source retention scheduled.

## 88. Checklist: cleanup and deletion

- [ ] Data inventory covers DB, object storage, caches, logs, backups, and providers.
- [ ] Retention defined per data category and purpose.
- [ ] Clear policies handle `PENDING`/`RETRY_WAIT`/`SUBMITTED`/`UNKNOWN`.
- [ ] Cleanup checks leases, active references, and legal holds.
- [ ] Unique/idempotent deletion request IDs or equivalent states exist.
- [ ] Storage deletes target exact object versions.
- [ ] Versioning/replication/backup TTLs accounted for.
- [ ] Retries and alerts exist for cleanup failures.
- [ ] Minimal body-free tombstones/audits maintained.
- [ ] Restore runbook includes deletion replay.
- [ ] "Purged" state defined accurately by scope.
- [ ] Never claim mailbox recall merely because the app deleted data.

## 89. Checklist: key management and environments

- [ ] Modern algorithms/modes with integrity verification used.
- [ ] GCM nonces unique per key; never static/fixed IVs.
- [ ] Algorithm/key/schema versions tracked.
- [ ] KMS/HSM/secret manager configured and protected.
- [ ] Least-privilege IAM for mail workers and cleanup workers.
- [ ] Rotation/rewrap/re-encryption/revocation policies established.
- [ ] Monitoring tracks decryption failures and KMS access anomalies.
- [ ] Secrets omitted from logs/config dumps.
- [ ] CI/staging use separate keys and synthetic payloads.
- [ ] Backup and DR plans cover key availability/deletion considerations.
- [ ] Incident runbook exists for key compromise.

## 90. Checklist: testing and observability

- [ ] AES-GCM roundtrip and tag-tampering fail-closed tested.
- [ ] AAD mismatch/cross-tenant access rejected.
- [ ] Encrypted storage verified free of direct synthetic plaintext.
- [ ] Retention policies tested with `Clock.fixed(...)`.
- [ ] Cleanup idempotency after crashes tested.
- [ ] Races between purge and active SMTP workers tested.
- [ ] No synthetic secrets leaked into logs/traces on failure paths.
- [ ] Expired tokens/links withheld from sending.
- [ ] Backup restore reapplies deletion states.
- [ ] Metrics track expired backlogs, purge failures, and key errors.
- [ ] Recipient addresses/tokens omitted from metric labels.
- [ ] SMTP sandbox and test keys isolated from production data.

## 91. Common mistakes

| Mistake | Why it is dangerous | Replacement |
| --- | --- | --- |
| "TLS is on so DB needs no protection" | TLS does not protect DB dumps | Encryption at rest + access controls |
| "DB is encrypted so provider cannot read it" | Worker decrypts before SMTP submit | E2E content encryption if genuinely required |
| Storing key alongside ciphertext in unprotected table | DB leak exposes both data and key | KMS/envelope encryption/least privilege |
| Fixed GCM IV across messages | Can break confidentiality and integrity | Unique random nonce/key policy |
| Using Base64 to "encrypt" | Base64 is publicly reversible | Standard encryption and key management |
| Persisting entire unnecessary template models | Expands PII exposure | Data minimization |
| Logging raw `MimeMessage` for easy debugging | Bodies/Bcc/tokens/attachments enter logs | Structured safe diagnostics |
| Deleting payload in `finally` even on send error | Loses data needed for retry/reconcile | Outcome-based lifecycle policy |
| Waiting for `DELIVERED` forever before deleting bodies | Provider may omit events | Separate feedback coverage and retention |
| Deleting file right after `addAttachment` | Resource may not have been read yet | Retain until serialization/attempt completes |
| Temp files without a sweeper | Files survive crashes | Cleanup jobs + quotas |
| Deleting object key while ignoring versions | Older versions remain | Version-aware deletion/lifecycle |
| Deleting primary DB then claiming all backups deleted | Snapshots retain older copies | Backup policy + restore replay |
| Storing OTP hashes then trying to send hash in mail | Hashes cannot be reversed | Token issuance and encrypted transient delivery |
| Sending ZIP password in the same email | Anyone accessing email gets both | Separate channel/E2E/portal |
| Deleting app record then promising Inbox recall | Provider/mailbox outside control | State scope accurately |
| Sharing KMS permissions between dashboard and mail worker | Broadens blast radius | Separate service identities |
| Using email addresses as metric labels | PII + high cardinality | Opaque IDs/authorized logs |
| Ignoring legal holds | Deletes mandatorily preserved data | Audited hold workflow with expiry |
| Skipping deletion replay after backup restore | Deleted data reappears | Restore runbook with deletion ledger |

## 92. Practice scenario 1 — Password-reset email

A service generates a reset token, stores it in plaintext in the outbox payload, and schedules delivery 30 minutes later. The token expires in 15 minutes.

**Question:** What bugs exist?

**Hint:** the raw token is persisted too long, the email sends after token expiry, the queue may leak it, and retries could deliver dead links. Design proper token issuance/TTLs, avoid persistent unencrypted plaintext, check eligibility prior to sending, and delete/revoke on expiry.

## 93. Practice scenario 2 — Invoices retained indefinitely

SMTP submitted the email, yet the PDF attachment and rendered MIME sit in object storage for six months "in case of resend."

**Hint:** define official purpose and retention. If invoices must be retained, store them in an encrypted, access-controlled document/archive system rather than treating mail worker temp copies as infinite archives. Enforce explicit manual resend policies and auditing.

## 94. Practice scenario 3 — SMTP timeout after DATA

The worker transmitted all MIME bytes and timed out (`UNKNOWN`). Cleanup saw `send(...)` threw an exception and deleted the payload.

**Hint:** unknown status requires reconciliation/policy—never equate exceptions with guaranteed non-submission; cleanup must not destroy processing capability still valid under configured retention.

## 95. Practice scenario 4 — AES key stored straight in config

The application encrypts its outbox well, except for:

```yaml
app:
  mail:
    encryption-key: "hardcoded-key-example"
```

**Hint:** secrets can leak via repositories, CI, deployment logs, and broad config access. Use KMS/secret managers, minimal decryption permissions, rotation, and auditing; never put keys in source.

## 96. Practice scenario 5 — Deleted, yet versioning keeps old copies

Cleanup calls DeleteObject successfully and the dashboard reports `PURGED`. The bucket has versioning enabled with three prior versions.

**Hint:** inspect delete-marker semantics, delete exact versions or configure lifecycles properly, and report status scoped accurately; never equate one API call with wiping every copy.

## 97. Practice scenario 6 — Incident with token in logs

SMTP authentication fails. The error handler prints the entire `MimeMessage` for debugging; the reset token ends up in SIEM.

**Hint:** disable raw logging, triage exposure scope, revoke active tokens per incident procedures, clean up controllable storage locations, and switch to structured error codes.

## 98. Practice scenario 7 — Worker and cleanup racing

The worker uses `FileSystemResource` to read a PDF during send. Cleanup deletes the file the instant TTL expires while SMTP is streaming.

**Hint:** active leases/references vs. retention precedence; synchronize deletion with lifecycle state. If expiry mandates cancellation, block submission via policy rather than silently yanking files mid-serialization.

## 99. Practice scenario 8 — Sensitive document sent as ordinary email

A team proposes encryption at rest for the outbox and concludes mail providers cannot read the content.

**Hint:** workers decrypt before SMTP. Determine whether E2E is truly needed; if so, evaluate S/MIME/OpenPGP or authenticated portals alongside key policies and client support.

## 100. Practice scenario 9 — Backup restore

A user requests data deletion on Monday; on Wednesday the system restores Sunday's backup and old emails reappear in the queue.

**Hint:** halt outbound delivery during DR, replay the deletion/cancellation ledger, verify outbox states and key policies, and reopen workers only after reconciliation finishes.

## 101. Practice scenario 10 — Dashboard needs search by email

A team wants to store plaintext recipient emails in every `mail_notification` row for easy filtering.

**Hint:** consider recipient IDs, authorized lookup services, and threat-modeled field encryption/blind indexes; do not turn dashboard convenience into justification for every worker reading PII.

## 102. Key principles to remember

1. **Not storing data is the strongest protection when data is unnecessary.**
2. **Encryption at rest, SMTP TLS, and E2E encryption protect different boundaries.**
3. **JavaMailSender does not automatically end-to-end encrypt email content.**
4. **Outboxes should hold metadata/references and encrypted models when needed**, avoiding raw MIME by default.
5. **AES-GCM requires unique nonces, tag validation, AAD/context, and key management.**
6. **KMS does not automatically prevent authorized code from logging plaintext.**
7. **Retention must account for SMTP states and business purposes**, especially retry/`UNKNOWN`.
8. **Cleanup is a durable workflow** with retries, idempotency, and monitoring.
9. **Temp files, object versions, logs, APM, backups, and providers are copies requiring inventory.**
10. **Copies already delivered to providers/recipients generally cannot be fully recalled by the app.**
11. **Data key destruction requires evaluating granularity and other copies**, not just deleting an alias.
12. **Restores can resurrect deleted data**, requiring deletion replay.
13. **Expiring/one-time tokens must have an independent lifecycle**, not relying solely on send status.
14. **Decryption privileges must be minimal and separated from dashboard access.**
15. **Pre-send authorization and recipient accuracy matter as much as encryption.**

## 103. References

To implement against your exact versions, consult:

- Spring Framework — Email Integration: https://docs.spring.io/spring-framework/reference/integration/email.html
- Spring Boot — Sending Email: https://docs.spring.io/spring-boot/reference/io/email.html
- Java Cryptography Architecture / Cipher (JDK documentation): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html
- OWASP — Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- NIST SP 800-38D — Galois/Counter Mode (GCM): https://csrc.nist.gov/pubs/sp/800/38/d/final

These documents serve as reference points for APIs and security principles; KMS features, object versioning, backups, and deletion controls must be checked against your platform's documentation, contracts, and policies. The repository/KMS/service examples here are application-designed abstractions, not APIs automatically provided upon adding `spring-boot-starter-mail`.

## 104. Conclusion

**Encrypting or removing sensitive content after sending** is a production pattern spanning **the entire data lifecycle**, not calling `JavaMailSender.send(...)` successfully and running `DELETE`. Applications must minimize sensitive fields upfront, hold models/attachments in encrypted stores while needed for retries, restrict decryption rights, keep raw MIME out of logs, manage temp files and object versions, and define clear retention by email type, notification state, and business requirements.

When encrypting, distinguish encryption at rest from SMTP TLS and S/MIME/PGP. For application-stored payloads, use supported authenticated encryption and proper key management; AES-GCM demands unique nonces, authentication tags, and accurate context binding. When deleting, cleanup must be stateful and idempotent, handle worker races, honor retention/legal holds, and account for backups/restores. **Never promise that purging payloads inside the application removes email copies stored by providers or recipients.**

The architectural goal is **store as little as possible, tightly protect what must be stored, delete verifiably when purpose ends, and communicate control boundaries honestly**. Combining encrypted outboxes, secure mail workers, retention services, deletion ledgers, and synthetic-data testing dramatically reduces leakage risks while preserving reliable retries, auditing, and operations.
