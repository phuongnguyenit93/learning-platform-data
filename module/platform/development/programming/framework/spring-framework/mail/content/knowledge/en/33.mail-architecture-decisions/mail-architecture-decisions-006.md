# Choosing Full Message Storage vs. Metadata-Only Storage

In **Spring Framework Mail**, an email can be a brief customer notification, or it can be a payment receipt, evidence of a support request, a document sent into a mailbox by a partner, or a message with a very large attachment. When designing a mail sending/receiving system, a key decision is: **store the entire message—headers, body, MIME parts, and attachments—or store only metadata for lookup and operations?**

Storing the full message enables **reviewing, debugging failures, reprocessing, or content auditing**, but increases cost, sensitive-data scope, and security controls. Storing metadata only keeps data small, easy to query, and reduces content exposure risk, yet may **fall short of reconstructing the exact email as sent/received**, especially if templates, business data, or attached files have changed.

In practice, many systems need a **hybrid design**: structured metadata in a database, plus snapshots or raw MIME in access-controlled object storage when business goals require it. Separate decisions must be made for **outbound** (emails built and sent by the app via SMTP) and **inbound** (emails received from IMAP/POP3 mailboxes or providers).

This article explains the options, decision criteria, data structures, integrity, PII risk, cost, attachment storage, transactional outbox, failure recovery, and testing.

## 1. What Constitutes a Full Message?

An email under RFC 5322/MIME can include:

~~~text
Message headers
  From / To / Cc / Reply-To
  Subject / Date / Message-ID
  References / In-Reply-To
  Content-Type / MIME-Version
  Received / DKIM-Signature / custom headers

MIME body
  multipart/mixed
    multipart/alternative
      text/plain
      text/html
    multipart/related
      inline image with Content-ID
    attachment: invoice.pdf
    attachment: report.csv
~~~

Some related data sits **outside** raw MIME:

- SMTP envelope sender and recipients, especially Bcc recipients.
- The actual account/provider used to send.
- SMTP reply codes and send attempt history.
- Provider message IDs and delivered/bounced/deferred webhooks.
- Tenant, business event, and actor responsible for sending.
- Authorization/consent decisions and retry policies.

Therefore, **storing full MIME does not mean storing the complete transport history**. If you need to answer why an email did not reach a recipient, you still need attempt metadata and provider feedback.

### Raw MIME, Byte Copies, and Reconstructibility

Three concepts are often confused:

1. **Raw MIME serialization:** headers + body/attachments serialized into a representation such as an `.eml` file.
2. **Original captured bytes:** the exact byte stream at a defined send/receive boundary; requires capturing at that boundary.
3. **Reconstructible content:** template ID/version, body snapshot, business data, and object references capable of rebuilding an email with equivalent content.

Calling `MimeMessage.writeTo(outputStream)` produces a usable representation, yet if the message was parsed and re-serialized, bytes may differ from the original due to line endings, header folding, boundaries, or encoding. Never claim a reconstructed copy is byte-for-byte identical to the original without capture evidence.

## 2. What Does Metadata-Only Store?

Metadata describes a message without storing full bodies/attachments:

~~~json
{
  "mailJobId": "mail-981",
  "tenantId": "tenant-42",
  "direction": "OUTBOUND",
  "purpose": "PAYMENT_RECEIPT",
  "recipientContactId": "contact-77",
  "templateId": "PAYMENT_RECEIPT",
  "templateVersion": 4,
  "providerId": "relay-a",
  "submissionStatus": "SUBMITTED",
  "attemptCount": 2,
  "providerMessageId": "provider-msg-981",
  "submittedAt": "2026-11-12T12:00:00Z"
}
~~~

Optional additions:

- Business event ID or order/payment reference.
- `From`/sender profile ID.
- Recipient count or hashed identifiers.
- Mailbox account ID, folder, and IMAP UID for inbound.
- MIME type, estimated bytes, attachment count.
- Content checksum, object storage reference if present.
- Retry deadline, error category, and correlation ID.
- Retention, classification, and tenant scope.

**Metadata-only is not automatically anonymous.** Email addresses, subjects, `Message-ID`s, recipient IDs, and some error texts can still be personal data. Protect them according to policy.

## 3. Four Storage Strategies

| Model | What Is Stored? | Pros | Limitations |
| --- | --- | --- | --- |
| **Metadata-only** | IDs, essential headers, statuses, attempts | Lightweight, easy to query, minimal body storage | Cannot replay exact content if source is lost |
| **Structured snapshot** | Metadata + text/HTML/domain snapshots + attachment references | Can rebuild stable content | MIME serialization bytes may differ |
| **Full raw MIME** | Metadata + `.eml` file with headers/body/attachments | Useful for forensics and reparsing | Sensitive data, large size, harder retention |
| **Hybrid/tiered** | Metadata DB + snapshots + raw when needed | Balances audit and performance | Lifecycle and consistency complexity |

A selection diagram:

~~~mermaid
flowchart TD
    A["Mail event / received email"] --> B["Metadata DB record"]
    A --> C{"Retention/content policy"}
    C -->|"Status only"| D["Metadata-only"]
    C -->|"Must reconstruct"| E["Versioned snapshot"]
    C -->|"Need original MIME"| F["Encrypted raw .eml"]
    E --> G["Optional attachment storage"]
    F --> G
    B --> H["Search, attempts, audit"]
~~~

You do not need to store snapshots and raw copies for every message. A tenant sending 1,000,000 marketing emails per day has very different needs from an inbox receiving legal contracts.

## 4. Separate Outbound and Inbound

**Outbound:** the application owns the source data, templates, and send logic.

~~~text
Domain event -> mail outbox -> renderer
  -> MimeMessage -> JavaMailSender -> SMTP
~~~

If the business only needs to know sending was attempted and provider status, metadata may suffice. If the email must preserve exact content as of creation time, a snapshot or versioned data/template/file is needed.

**Inbound:** external content arriving via IMAP, POP3, or a provider inbound API.

~~~text
Mailbox / inbound provider
  -> raw message -> MIME parser
  -> metadata -> validation -> business job
~~~

If the application stores only metadata and the mailbox deletes the message, body/attachments needed for a fixed parser, complaint investigation, or ticket review may be lost. Raw MIME or structured content snapshots are often more critical for inbound.

However, inbound raw data is **untrusted input**: dangerous HTML, malware, malformed MIME, oversized attachments, and personal data must be sanitized and protected.

## 5. Business Goals Determine Storage Level

| Need | Metadata-Only | Snapshot | Raw MIME |
| --- | --- | --- | --- |
| Count enqueued emails | Sufficient | Sufficient | Unnecessary |
| Track SMTP failures | Sufficient with attempts | Sufficient | Raw does not replace attempts |
| Search by job/provider ID | Sufficient | Sufficient | Needs metadata index |
| View email sent to customer | Usually insufficient | Usually sufficient | Sufficient if retained |
| Resend exact receipt details | No if domain data changed | Suitable | Potentially suitable |
| Investigate MIME boundary/charset | Missing | Possibly missing | Suitable |
| Reparse inbound after parser fix | Insufficient | Depends on snapshot | Suitable |
| Verify original attachment | No if source file lost | Yes if file immutable | Yes if raw preserved |
| Minimize PII | Favorable | Needs policy | Broader exposure risk |
| Prove delivery | Not sufficient alone | No | Raw not sufficient either |

This table does not claim every audit requirement demands raw MIME. Define **specific regulations, required proof, retention duration, and access rights** before choosing.

## 6. When Is Metadata-Only Sufficient?

For example, a "report ready" email simply points users to a dashboard where the report data always remains viewable from the business source.

You can store:

~~~text
jobId
businessEventId
tenantId
recipientContactId
purpose
templateId/version
queuedAt
attemptCount
status
providerId
providerMessageId
failureCategory
~~~

Benefits:

- Does not duplicate bodies, PII, and attachments.
- Small data footprint, easy to index and back up.
- Operational access does not grant access to email content.
- Lower exposure if the metadata database leaks compared to full bodies (though still sensitive).
- Less complex retention management.

**Key condition:** if workers must retry hours/days later, ensure content sources remain available and reconstructible per policy. If sources mutated or files were deleted, metadata-only cannot rebuild the old email.

## 7. When Is a Structured Snapshot Useful?

A payment receipt may need to keep:

~~~json
{
  "eventId": "payment-981-confirmed",
  "templateId": "PAYMENT_RECEIPT",
  "templateVersion": 4,
  "locale": "vi-VN",
  "recipientSnapshotId": "recipient-snapshot-981",
  "receiptSnapshotId": "receipt-snapshot-981",
  "attachmentObjectKey": "receipts/tenant-42/981-v1.pdf"
}
~~~

The snapshot reflects values at event time, avoiding reading prices, customer names, or order statuses that changed days later.

Define:

- Template version and rendering locale.
- Immutable business snapshot/data version.
- Attachment version and checksum.
- Recipient semantics: address at enqueue time or send time?
- Send-time eligibility: consent, token expiry, tenant suspension.
- Retention period and deletion workflow.

Snapshots enable **reconstructing content**, though they do not guarantee identical MIME header folding, boundaries, or `Message-ID`.

## 8. When Is Full Raw MIME Needed?

Cases where raw has value:

- Receiving customer support emails and needing to review original content.
- Receiving documents/contracts needing reparsing or investigating broken files.
- Debugging charset issues, inline images, `Content-ID`, multipart nesting.
- Analyzing raw headers for troubleshooting.
- Regulatory/policy requirement to retain a message artifact at a defined capture point.
- Re-running a MIME parser after fixing parsing logic.
- Verifying whether an attachment was actually received.

Still, raw MIME **does not prove by itself**:

- Sender authenticity.
- That a business transaction committed.
- That the SMTP relay accepted it.
- That the email reached the recipient's inbox.
- That the recipient opened the email.
- Full Bcc/envelope recipients.

If raw MIME contains a `DKIM-Signature`, verify the signature independently; the header's mere presence does not prove validity.

## 9. Realistic Capacity and Cost

One MIME message might contain:

~~~text
Plain text: 4 KiB
HTML: 12 KiB
Inline logo: 80 KiB
Invoice.pdf: 8 MiB
Report.zip: 20 MiB
~~~

Binary files base64-encoded in MIME expand substantially compared to raw binaries, plus headers/boundaries and line wrapping.

Raw storage cost is more than object size:

- Replication/backup copies.
- Object versions.
- KMS/encryption operations.
- Network egress when fetched for investigation.
- Antivirus scanning.
- Search indexes or extracted-content caches.
- Retention/legal holds.
- Duplication if storing both raw MIME and extracted attachments separately.

A capacity estimate:

~~~text
estimated_bytes =
    messages_per_day
    × mean_serialized_bytes
    × retention_days
    × replication_factor
    + attachments_copied
    + object_versions
    + indexes
~~~

Base estimates on the actual size distribution and heavy tails, not just averages. A few hundred-MiB messages can dominate costs.

## 10. Full MIME in DB or Object Storage?

| Criterion | Database BLOB | Object Storage |
| --- | --- | --- |
| Atomic transaction with metadata DB | Possible in the same DB | Not by default |
| Suitable for many large files | Usually unfavorable | Usually better |
| Backup/replication | BLOBs bloat the DB | Independent storage policies |
| Searching metadata | Easy via DB columns | Needs separate DB/index |
| Retention | Via schema/jobs | Lifecycle + DB coordination |
| Per-tenant access | DB authorization | IAM + application authorization |
| Consistency | DB transaction | Needs state machine/checksums |
| Cost for large data | Can be high | Usually offers storage tiers |

For small bodies with simple consistency needs, a DB column may suffice. For large raw MIME/attachments, **metadata in DB + encrypted object storage** scales far better.

However, object storage does not share an ACID transaction with the DB. You must handle cases where the object exists yet DB commit fails, or the DB pointer commits yet the object is not ready.

## 11. Security and PII Are Not Optional Afterthoughts

A message can contain:

- Recipient email, name, address, phone number.
- OTP codes or password-reset URLs.
- Payment/invoice data.
- Images, financial files, and personal documents.
- HTML parts with remote tracking URLs.
- Headers containing IP addresses or infrastructure details.
- Malicious attachments.

When retaining full MIME:

1. Use encryption at rest/in transit and KMS management.
2. Restrict read/decrypt permissions by tenant/purpose.
3. Audit every view/download/replay.
4. Sanitize HTML before display and restrict remote resources.
5. Malware-scan and quarantine suspicious attachments.
6. Never write raw MIME to logs, metrics, or traces.
7. Maintain clear retention, deletion, and backup policies.
8. Never allow direct object-storage access merely from a guessable storage key.
9. Never store valid tokens or live reset links indefinitely.
10. Require access approvals for forensics/legal holds.

**Metadata can also be PII**, so never treat metadata-only tables as public data.


## 12. Choose Policy per Mail Purpose

Do not use a single global `storeFullMessage=true` flag for every email.

| Email Type | Typically Sound Choice | Notes |
| --- | --- | --- |
| OTP | Minimal metadata | Do not retain plaintext OTP codes long |
| Password reset | Metadata + protected token reference | Reset URLs are highly sensitive and have TTLs |
| Payment receipt | Versioned snapshot and immutable attachment | Must reflect exact amount/timestamp |
| Operational alert | Metadata, attempts, and failure audits | No need to duplicate production payloads |
| Marketing | Metadata/consent audit, template version | High volume; separate suppression and retention |
| Inbound support | Structured content/attachments, short-TTL raw MIME if needed | Review messages and re-run parsers |
| Inbound contracts | Raw MIME + extracted files per specific requirement | Integrity, provenance, quarantine |
| Bounce/DSN | Normalized metadata + short-lived raw for debugging | Correlate provider IDs and suppression |

These are engineering starting guidelines, not legal retention schedules. Each organization must set retention based on jurisdiction, contracts, data sensitivity, and purpose.

You can express this with custom configuration:

~~~yaml
app:
  mail:
    retention:
      payment-receipt:
        metadata-days: 1095
        snapshot-days: 1095
        raw-mime-days: 0
      inbound-support:
        metadata-days: 365
        snapshot-days: 180
        raw-mime-days: 30
      password-reset:
        metadata-days: 30
        snapshot-days: 0
        raw-mime-days: 0
~~~

This namespace is application-defined; Spring Boot does not automatically delete messages based on these properties. Numbers are illustrative.

## 13. A Central Metadata Schema

PostgreSQL example:

~~~sql
CREATE TABLE mail_record (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    direction VARCHAR(16) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    business_event_id VARCHAR(160),
    recipient_reference VARCHAR(160),
    sender_profile_id VARCHAR(160),
    mailbox_account_id VARCHAR(160),
    mailbox_folder VARCHAR(240),
    imap_uid_validity BIGINT,
    imap_uid BIGINT,
    rfc_message_id VARCHAR(512),
    provider_message_id VARCHAR(512),
    template_id VARCHAR(160),
    template_version INTEGER,
    storage_policy VARCHAR(40) NOT NULL,
    raw_object_key VARCHAR(1024),
    snapshot_object_key VARCHAR(1024),
    content_sha256 VARCHAR(64),
    content_bytes BIGINT,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_or_received_at TIMESTAMP WITH TIME ZONE,
    retention_until TIMESTAMP WITH TIME ZONE
);
~~~

This schema is a reference only; UUID types, timezones, indexes, and constraints must match your real DB. In practice, inbound and outbound can be separated:

- `tenant_id`, `purpose`, and `direction` drive permissions and retention.
- `business_event_id` links domain events/outbox records.
- `mailbox_account_id`, `imap_uid_validity`, and `imap_uid` identify IMAP occurrences.
- `provider_message_id` supports provider feedback correlation.
- `template_version` enables reconstructing content as of send time.
- `raw_object_key`/`snapshot_object_key` point to artifacts if policy stores them.
- `content_sha256`/`content_bytes` verify storage and integrity.
- `retention_until` guides cleanup jobs; it does not enforce TTL on its own.

Never use `Message-ID` as an absolute business unique key since the header can be missing, duplicated, or spoofed.

## 14. Separate Message, Attempt, Artifact, and Attachment

~~~mermaid
flowchart LR
    A["mail_record"] --> B["mail_send_attempt"]
    A --> C["mail_artifact"]
    A --> D["mail_attachment"]
    A --> E["mail_delivery_feedback"]
    C --> F["Encrypted object storage"]
    D --> F
~~~

One way to structure:

~~~text
mail_record
  mailId, tenantId, purpose, status, storagePolicy

mail_artifact
  artifactId, mailId, artifactType
  objectKey, objectVersion, sha256, bytes
  captureMethod, retentionUntil

mail_attachment
  attachmentId, mailId, storageKey
  safeFilename, declaredContentType, detectedContentType
  bytes, sha256, scanStatus

mail_send_attempt
  attemptId, mailId, providerId, accountId
  startedAt, outcome, smtpReplyCategory

mail_delivery_feedback
  eventId, mailId, eventType, sourceVerified
~~~

Separating records lets you query status without loading raw MIME, protect artifact read permissions, retain provider feedback longer than raw content when needed, and manage attachments independently.

Do not assume every `mail_record` has an attachment or raw artifact; for metadata-only, neither may exist.

## 15. When Should Raw MIME Be Stored?

Outbound has stages:

~~~text
Business event
  -> Mail intent/outbox
  -> Template render
  -> MimeMessage headers/body/attachments
  -> MIME serialization
  -> SMTP submission
  -> Provider delivery processing
~~~

**Store at mail intent:** small data, committable inside the business transaction, but lacks full MIME.

**Store after render/preparation:** yields a prepared MIME artifact for debugging or consistent-content retries, though bytes may still differ from what the relay receives if transport alters headers/encoding.

**Store after SMTP submission:** ties the artifact to an attempt, yet does not prove actual wire bytes or delivery; requires provider response/ID separately.

If raw MIME contains OTPs/tokens, policy may forbid storing content even when technically feasible.

### Do Not Forget Inbound Receive Time

For IMAP/provider inbound, if byte-level source is required, capture at the right ingestion point or use the provider's raw-download API. Re-serializing `MimeMessage` after parsing is a **serialized reconstruction** and may differ from the original.

## 16. Java: Writing a MimeMessage to a Stream

~~~java
import java.io.IOException;
import java.io.OutputStream;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

public void writePreparedMime(
        MimeMessage message,
        OutputStream output)
        throws IOException, MessagingException {

    message.saveChanges();
    message.writeTo(output);
}
~~~

This illustrates producing a **prepared MIME representation**. `saveChanges()` can modify headers depending on lifecycle; invoke it per application contract rather than blindly before/after every send.

An anti-pattern for large attachments:

~~~java
ByteArrayOutputStream out =
        new ByteArrayOutputStream();

message.writeTo(out);

byte[] allBytes = out.toByteArray();
~~~

This keeps the entire serialized MIME in RAM and copies buffers. Production should stream through a quota/byte-counting output stream to storage or controlled file staging.

If the system requires raw wire-byte evidence, never equate `writeTo` with SMTP packet capture or provider receipts.

## 17. An Abstraction for Artifact Storage

~~~java
public enum MailArtifactType {
    PREPARED_MIME,
    CAPTURED_RAW_MIME,
    STRUCTURED_SNAPSHOT,
    ATTACHMENT
}
~~~

~~~java
public interface MailArtifactStore {

    StoredArtifact save(
            UUID mailId,
            MailArtifactType type,
            InputStreamSource source,
            long maxBytes);

    InputStream open(
            UUID mailId,
            UUID artifactId,
            AuthenticatedActor actor);

    void scheduleDeletion(
            UUID artifactId,
            Instant retentionUntil);
}
~~~

Types like `StoredArtifact` and `AuthenticatedActor` are application-defined. An implementation must:

- Enforce actual maximum size while streaming.
- Use system-generated object keys, never raw user filenames.
- Enforce tenant authorization even when the caller holds the object key.
- Store object version/size/checksum.
- Log access audits whenever raw content is viewed.
- Clean up per retention/legal holds.
- Avoid issuing long-lived presigned URLs to unauthorized clients.

An object key is not a password, yet it can still be sensitive data and must never act as a capability bypassing authorization.

## 18. DB and Object Storage Transaction Boundaries

Object storage does not participate in database transactions.

~~~text
PUT object
INSERT mail_artifact pointer
COMMIT
~~~

If PUT succeeds and DB commit fails, an **orphan object** remains. If you reverse the order:

~~~text
INSERT pointer
COMMIT
PUT object
~~~

then if PUT fails, the DB holds a **dangling reference**.

A reference lifecycle:

~~~mermaid
flowchart TD
    A["Create content"] --> B["Upload to staging object"]
    B --> C["Verify bytes/checksum"]
    C --> D["DB transaction: artifact READY"]
    D --> E{"Commit success?"}
    E -->|"Yes"| F["Consumer may read"]
    E -->|"No"| G["Orphan cleanup"]
    B --> H["Staging TTL cleanup"]
~~~

Conditions:

1. Never publish an artifact as `READY` before the object is readable.
2. On DB rollback, clean up orphans via TTL/reconciler.
3. On storage upload failure, never mark READY.
4. For retries, control object versions/idempotency keys.
5. If an object is unexpectedly deleted, handle missing references gracefully instead of NPEs.
6. Never delete files while active mail jobs still need them for retries.
7. Never hold DB transactions open while uploading large files.

If artifacts are generated after business outbox commit, use a `WAITING_FOR_ARTIFACT` state, then have workers prepare content/snapshots and transition to `READY_TO_SEND`. Only send SMTP once required data exists.

## 19. Checksums and Artifact Versions

An artifact record might look like:

~~~text
artifactId: artifact-981
mailId: mail-981
artifactType: CAPTURED_RAW_MIME
objectKey: mail/tenant-42/981/raw.eml
objectVersion: v17
sha256: 64-hex-character digest
bytes: 12984321
captureMethod: provider-raw-download
capturedAt: 2026-11-12T12:00:00Z
~~~

Checksums detect whether read bytes differ from recorded bytes or whether an upload was truncated. Versions prevent workers from picking up mutated attachments.

**Checksums do not prove who sent the message or whether SMTP delivered it.** Neither are they digital signatures proving legal authenticity. For nonrepudiation/forensics, use signing or chain-of-custody controls as required.

Never use hashes as the sole unique key of business messages. Two emails can have identical content for different recipients or events. Cross-tenant content-addressable deduplication also risks data inference and complicates tenant deletion.

## 20. Inbound IMAP: Capture Before the Folder Closes

With Spring Integration Mail, receivers can surface Jakarta Mail `Message`/`MimeMessage` objects. Some parts are read lazily through the folder/session.

~~~text
ImapMailReceiver
  -> discover UID + folder
  -> capture metadata/raw/content per policy
  -> durable persist
  -> ack/move/mark mail
  -> business queue
~~~

Never push a live `MimeMessage` into a queue processed hours later assuming the folder stays open. If replay is required, capture raw content or durable components **before the session closes**, within size and security limits.

To prevent inbound duplicates, identify messages by tuple:

~~~text
mailboxAccountId
+ folderId
+ uidValidity
+ uid
~~~

IMAP UIDs must be paired with `UIDVALIDITY`; `Message-ID` can be forged/duplicated/absent. Even with exact identification, **UIDs do not contain bodies/attachments**. If the source email is expunged while the app stored only UID/subject, the original file cannot be recovered.

Never mark/delete mail before durable capture if retries depend on that message.


## 21. Outbox Intent and Raw MIME Are Two Different Decisions

A transactional outbox job is usually a **send intent**:

~~~text
BEGIN DB transaction
  update order/payment
  insert mail_outbox intent
COMMIT

worker
  claim job
  load approved content/attachment
  render MIME
  submit SMTP
  record outcome
~~~

There is no technical requirement for the outbox to store full serialized MIME. A job can reference:

~~~json
{
  "mailJobId": "mail-981",
  "templateId": "ORDER_CONFIRMATION",
  "templateVersion": 3,
  "recipientRef": "contact-77",
  "businessSnapshotRef": "order-snapshot-981",
  "attachmentRefs": []
}
~~~

If template and snapshot versions are pinned, workers can rebuild valid content after restarts. If payloads hold mutable domain references and underlying data changes, semantic drift occurs.

### Does Raw MIME Grant Exactly-Once?

No. A worker can:

~~~text
send MIME -> SMTP accepts -> worker crash
 -> DB status not yet SUBMITTED -> retry same MIME
~~~

The provider may deliver twice. Storing raw keeps content consistent across attempts, yet **creates neither a joint transaction with SMTP** nor a universal idempotency key on the receiving MX.

### Replay Still Depends on Permissions and Deadlines

If a job waits 2 days:

- OTPs may have expired.
- Marketing recipients may have unsubscribed.
- Tenants may be suspended.
- Sender domains may no longer be verified.
- Documents may have deletion requests.
- Attachments may exceed retention.

Therefore separate **content snapshot policy** from **send-time eligibility policy**.

## 22. Choose Metadata for Status and Delivery Feedback

When operations matter, structured data is needed even if raw MIME is stored.

An attempt record:

~~~text
attemptId
mailJobId
providerId
senderAccountId
attemptNumber
startedAt
finishedAt
submissionOutcome
failureCategory
smtpReplyCode
providerMessageId
~~~

A delivery feedback record:

~~~text
providerEventId
providerMessageId
mailJobId
recipientReference
eventType: DELIVERED / BOUNCED / DEFERRED / COMPLAINED
occurredAt
receivedAt
sourceVerified
~~~

`JavaMailSender.send(...)` succeeding only indicates the transport reported no error at submission time; **it proves neither delivery nor read status**.

If a provider uses webhooks, verify signatures/sources, deduplicate events, and map to the exact tenant/account. Never trust an unverified raw tenant ID inside a webhook payload.

Retaining raw MIME does not automatically supply these events. Separating records lets you keep metadata/audits longer than content when needed.

## 23. One Message Sent to Multiple Recipients

A `MimeMessage` can have multiple To/Cc/Bcc recipients. Storage challenges:

- Raw MIME headers do not necessarily preserve the Bcc envelope.
- The same message can be accepted by SMTP for some recipients and rejected for others.
- Retrying the entire message can duplicate sends for already-accepted recipients.
- Recipients who must not see one another should not be exposed in shared To/Cc headers.
- Retention or data-deletion requests can differ across recipients.

For personalized transactional notifications, **one mail job per recipient** usually helps:

- Track individual statuses.
- Apply suppression/consent accurately.
- Deduplicate/retry independently.
- Correlate provider feedback easily.
- Retain recipient snapshots/metadata per exact policy.

If using one MIME message for multiple people, persist per-recipient attempt state; never treat raw To/Cc headers as the full SMTP envelope.

## 24. Content-ID and Inline Images

An HTML email may contain:

~~~html
<img src="cid:logo-123" alt="Logo">
~~~

The MIME message will include a part with the matching `Content-ID`. If you store only the HTML string without keeping inline image bytes/references, a review UI or retry may show broken images.

Options:

- Raw MIME: retains multipart structure and inline assets in the artifact.
- Structured snapshot: stores HTML + `Content-ID` → immutable object key map.
- Metadata-only: no content review; allowed only when re-rendering is unnecessary.

Similarly, `multipart/alternative` carries both `text/plain` and `text/html` representing the same content in two forms. Never reconstruct HTML alone and claim you stored the full message.

A complete replayable content snapshot must specify `text/plain`, HTML, inline assets, attachments, charset, and locale.

## 25. Managing Attachments Separately

Illustrative attachment schema:

~~~sql
CREATE TABLE mail_attachment (
    id UUID PRIMARY KEY,
    mail_id UUID NOT NULL,
    tenant_id VARCHAR(120) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    object_version VARCHAR(160),
    filename_safe VARCHAR(255),
    content_type_declared VARCHAR(200),
    content_type_detected VARCHAR(200),
    sha256 VARCHAR(64) NOT NULL,
    byte_length BIGINT NOT NULL,
    scan_status VARCHAR(40) NOT NULL,
    retention_until TIMESTAMP WITH TIME ZONE
);
~~~

Key points:

- Filenames are untrusted input; sanitize and never use them as storage paths.
- Sender-declared `Content-Type` does not prove actual file format.
- Bound size, part count, and nested MIME depth.
- Malware scanning/quarantine per policy.
- Stream instead of unbounded `readAllBytes()`.
- Raw objects and extracted attachments may duplicate bytes.
- Never delete attachments while outbox jobs still need retries.
- Never let another tenant read objects merely by key.

If deduplicating attachments by content hash, design permissions and deletion policies carefully to prevent cross-tenant information leakage.

## 26. Metadata-Only and Recoverability

Suppose an outbox job is created:

~~~text
jobId: mail-981
templateId: INVOICE
invoiceId: invoice-981
status: PENDING
~~~

Before the worker sends, the invoice is updated and the old PDF object is purged. Storing only the invoice ID is then **insufficient** to send the content approved at enqueue time.

Contract-dependent solutions:

- Pin invoice version and keep an immutable snapshot.
- Generate the durable PDF object before marking the job `READY`.
- Store template/version and required event data.
- Set a TTL or cancel the job if content is no longer valid.
- If business permits reading latest state, document that behavior explicitly.

Distinguish:

**Metadata-only:** describes events and statuses only; lacks sufficient data to rebuild.

**Reconstructible metadata:** references external sources guaranteed to remain intact and versioned.

**Snapshot:** frozen content data.

**Raw MIME:** a serialized/captured message representation.

Calling everything "metadata" misleads developers into thinking replay is possible when it is not.

## 27. Privacy and Field-Level Data Minimization

Even a metadata table can leak sensitive details:

~~~text
recipient = user@example.org
subject = Lab test results ...
messageId = ...
tenantId = ...
providerError = ...
~~~

Instead of storing everything raw, you can:

- Store `recipientContactId` and resolve under authorization.
- Store purpose/subject category instead of literal subject text.
- Store hashed/HMAC addresses when only correlation is needed, with proper key management.
- Separate encrypted contact data from operational status.
- Redact tokens from exception reasons.
- Enforce TTLs on raw headers and provider metadata containing PII.
- Store business event references instead of body excerpts.

**A plain hash of an email address is not always anonymous**, since dictionary attacks can reverse it. Even with HMAC or pseudonymization, protect the key and treat outputs as potential personal data per regulations.

## 28. Encryption and Key Lifecycle

When storing full MIME or snapshots:

1. Data should travel over TLS.
2. Storage has encryption at rest, typically KMS-managed.
3. IAM restricts who can decrypt/download.
4. Data keys/tenant keys and rotation need explicit policies.
5. Logs/backups must never expose raw content.
6. Upon retention expiry, lifecycle rules delete objects and versions appropriately.
7. Legal holds have dedicated, audited permissions.
8. Temporary files/staging must have TTLs and least privilege.

With application-level encryption, ensure retry workers can still decrypt while routine support accounts cannot read raw content. Key rotation must never break decryption of artifacts still within retention.

For multi-tenant data, consider separate encryption keys and access boundaries per tenant or data class depending on required isolation.

## 29. Retention Actually Touches Many Copies

An email can exist across:

~~~text
mail_record metadata
mail_artifact raw .eml
mail_attachment extracted files
search index / extracted text
cache / thumbnail
temporary staging object
backup / replica
provider mailbox
SMTP provider logs
application logs
~~~

When deciding "keep raw for 30 days," specify **which copies the 30 days apply to**. Deleting a `mail_artifact` row does not delete the object/version itself, nor purge text copied into a search index.

A retention engine can:

- Find expired artifacts.
- Check legal holds and active retry references.
- Enqueue audited deletion jobs.
- Delete object versions/derivatives per policy.
- Update state to `DELETED` or tombstone.
- Retry when storage deletion transiently fails.
- Retain minimal metadata if legally/operationally justified.
- Review backup retention separately.

### Deletion on User Request

For data-deletion requests, identify which objects hold private content, which copies are legally required to remain, and which retry jobs still reference that content. Never let an outbox worker keep sending a canceled message merely because raw MIME still sits in storage.

## 30. Legal Holds and Internal Investigations

Some organizations apply legal holds to content linked to active investigations. In those cases:

- Retention policies usually have exceptions governed by authorized teams.
- Do not let arbitrary users place legal holds.
- Record who/which department placed the hold and why.
- Separate artifact-read permissions from mail-sending operations.
- Audit exports/downloads.
- Maintain integrity/versions.
- Provide a workflow to release holds and resume retention.
- Never confuse legal holds with unjustified "keep forever."

This is a data-governance requirement, not a Spring Mail property. The application provides primitives; policy must be approved for the real context.

## 31. Search Indexes and Content Lookup

Raw MIME BLOBs are not directly searchable for support workflows.

You can index:

- Mail job ID, business event ID, tenant.
- Provider message ID.
- Direction, purpose, time range.
- Recipient reference per permissions.
- Normalized subject category.
- Attachment metadata.
- Optional extracted text per policy.

However, a full-text body index creates a **copy of sensitive data**. When raw/snapshots are deleted or permissions revoked, indexes and caches must update accordingly.

Never let a shared search index leak tenant A snippets to a tenant B user because the app checked tenant only when opening details instead of filtering queries.

## 32. How Should Users Review Raw Emails?

A viewer needs:

~~~text
Authorized support agent
  -> check tenant / ticket access
  -> fetch metadata
  -> request normalized body
  -> sanitize HTML / block remote resources
  -> render in isolated viewer
  -> audit access
~~~

When downloading `.eml` files:

- Use server-side streaming or authorized short-lived signed URLs.
- Never issue indefinite public URLs.
- Set safe `Content-Type`/`Content-Disposition`.
- Never auto-open risky attachments in browsers.
- Track scan/quarantine states.
- Rate-limit downloads.
- Log actor, purpose, and artifact ID.

Storing full MIME helps investigations, yet does not mean every employee should read raw content.

## 33. Monitoring Storage Strategies

| Metric | Meaning |
| --- | --- |
| `mail_storage_metadata_count` | Number of metadata records |
| `mail_storage_raw_mime_bytes` | Raw MIME storage size |
| `mail_storage_snapshot_bytes` | Snapshot storage size |
| `mail_storage_attachment_bytes` | Attachment storage size |
| `mail_storage_upload_failure_total` | Failed uploads |
| `mail_storage_checksum_mismatch_total` | Integrity failures |
| `mail_storage_missing_object_total` | Dangling references |
| `mail_storage_orphan_object_total` | Objects lacking DB references |
| `mail_storage_cleanup_failure_total` | Failed deletions |
| `mail_storage_retention_overdue_count` | Expired artifacts still present |
| `mail_storage_quarantine_count` | Quarantined artifacts |
| `mail_storage_artifact_read_total` | Artifact views/downloads |
| `mail_storage_replay_failure_total` | Replays failing to read content |

Metric labels should use purpose, direction, artifact type, storage tier, and error category. Never put raw subjects, recipient emails, or PII-bearing object keys in labels.

Alert when DB records are `READY` yet objects are missing, on checksum mismatches, storage nearing quota, rising orphan staging objects, or stalled retention cleanups.

## 34. A Reference Production Architecture

~~~mermaid
flowchart TD
    A["Business outbox / inbound receiver"] --> B["Policy resolver by purpose"]
    B --> C["Metadata record"]
    B --> D{"Content policy"}
    D -->|"Metadata"| E["Do not store body"]
    D -->|"Snapshot"| F["Immutable snapshot"]
    D -->|"Raw MIME"| G["Bounded MIME capture"]
    F --> H["Encrypted object storage"]
    G --> H
    H --> I["Checksum + version"]
    I --> J["Artifact READY"]
    C --> K["Attempts / provider feedback"]
    J --> L["Authorized replay / viewer"]
    K --> M["Audit / monitoring"]
    L --> M
~~~

Boundaries:

- **Policy:** decides what data must be kept and for how long.
- **Metadata DB:** serves status/attempt queries and authorization.
- **Artifact storage:** holds large content with size caps, checksums, and encryption.
- **Mail transport:** SMTP/IMAP operations; not atomic with DB/object store.
- **Business authorization:** verifies tenant, recipient, consent, and replay rights.
- **Lifecycle:** cleanup, restore, quarantine, legal holds, and reconciliation.
- **Observability:** detects missing objects, lost content, backlogs, and unauthorized access.

This model does not mean a small app must build every component immediately. Yet when deciding between metadata-only and full raw storage, explicitly state what is guaranteed for later retries, audits, and deletions.


## 35. How to Decide at Project Start

Instead of starting with "should we store full MIME?", define **required outcomes**:

| Question | If Answer Is "Yes" | Design Impact |
| --- | --- | --- |
| Need to review the exact content sent by/to a customer? | Yes | Need content snapshot or raw inbound |
| Need to inspect original MIME/headers? | Yes | Consider raw source capture at a defined point |
| Can bodies be rebuilt from immutable snapshots? | Yes | Structured snapshots may suffice |
| Are there attachments unrecoverable from source? | Yes | Must persist attachments/raw in durable storage |
| Do emails contain short-TTL sensitive tokens? | Yes | Prefer minimal metadata |
| Only need to reconcile send success/bounces? | Yes | Metadata/attempts/provider feedback usually suffice |
| Regulatory requirement to retain communications? | Yes | Scope content/retention/access precisely |
| Volume reaches millions of emails/day? | Yes | Model storage/network/backup/retention early |
| Could the inbound mailbox expunge messages? | Yes | Capture required content before acknowledgment |
| Multiple tenants sharing infrastructure? | Yes | Tenant isolation across DB, objects, and search |
| Need replay after template/DB changes? | Yes | Pin template/snapshot/attachment versions |
| Complex deletion/retention obligations? | Yes | Separate metadata, snapshot, raw, and derivative lifecycles |

If the goal is solely reconciling submissions, do not automatically store raw messages that may contain credentials or PII. If the business must prove **exact sent content**, metadata-only is usually insufficient.

### Three Decisive Questions

1. **If we deleted content today, would the system lose the ability to fulfill promised business behavior tomorrow?**
2. **If we keep content, who may view it and for how long?**
3. **If content changes between two attempts, does that violate the email contract?**

Answer these three before optimizing storage bytes.

## 36. Strategy by Maturity Stage

**Small stage:** an app sending a few notification emails with simple content.

- Store outbox metadata and idempotency keys.
- Pin template ID/version and business snapshots when needed.
- Do not store raw MIME without a concrete use case.
- Store attempts/retries so restarts do not lose work.

**Stage with inbound and attachments:**

- Separate object storage for retained raw/content/attachments.
- Enforce MIME size limits and malware scanning.
- Use UID/idempotency for inbound.
- Manage object references and retention.

**Multi-tenant/compliance stage:**

- Per-purpose and per-tenant content policies.
- KMS/IAM/access audits.
- Artifact versions/checksums.
- Cleanup/reconciliation/legal holds.
- Access-controlled search indexes.
- Monitoring for storage, orphan objects, and deletion.

You do not have to discard a simple model just to adopt complex architecture. However, once retention/audit/replay are product commitments, build a sound design from the start.

## 37. Testing Metadata-Only

Tests must check more than inserting a database row. Verify the contract metadata-only promises:

1. When the business transaction commits, metadata/job persists.
2. On rollback, no outbox intent exists.
3. On SMTP failure, attempts and failure categories are saved.
4. On retry, content resolves per the snapshot/reference contract.
5. If source content expired, the job transitions cleanly instead of sending wrong data.
6. When provider webhooks arrive, they map to the right job/tenant.
7. No raw bodies/tokens appear in logs, statuses, or retry metadata.
8. Retention cleanup removes fields no longer permitted.

Test example:

~~~java
@Test
void mailIntentKeepsTemplateVersion() {

    MailIntent intent =
            mailService.planPaymentReceipt(
                    paymentId
            );

    assertEquals(
            4,
            intent.templateVersion()
    );

    assertNotNull(
            intent.businessSnapshotRef()
    );
}
~~~

`MailIntent` and `mailService` are application-defined abstractions. The test verifies a specific design requirement, not a built-in Spring API.

### Testing Missing References

~~~text
Given: outbox job PENDING
And: snapshot object was accidentally deleted
When: worker tries to resolve content
Then: do not send an empty email
And: error/storage incident state is recorded
And: retry or manual action per policy
~~~

If metadata-only stores references, prove those references outlive the retry window and versions cannot mutate.

## 38. Testing Raw MIME and Snapshots

An integration test can build a `MimeMessage` with Jakarta Mail:

~~~java
@Test
void storesPreparedMimeArtifact()
        throws Exception {

    MimeMessage mime =
            new MimeMessage(
                    Session.getInstance(
                            new Properties()
                    )
            );

    mime.setFrom(
            "sender@example.test"
    );
    mime.setRecipients(
            Message.RecipientType.TO,
            "recipient@example.test"
    );
    mime.setSubject(
            "November invoice", "UTF-8"
    );
    mime.setText(
            "Test content", "UTF-8"
    );

    mime.saveChanges();

    StoredArtifact artifact =
            artifactService.storePreparedMime(
                    mailId, mime
            );

    assertTrue(
            artifact.byteLength() > 0L
    );
    assertNotNull(
            artifact.sha256()
    );
}
~~~

`StoredArtifact` and `artifactService` are application-defined. Required imports per test: `jakarta.mail.Session`, `jakarta.mail.Message`, `jakarta.mail.internet.MimeMessage`, and `java.util.Properties`.

This tests **artifact storage/serialization**; it proves neither actual SMTP wire bytes nor delivery. Add readback checks with a strict parser or byte comparison per your capture contract.

### Testing Multipart and Inline Assets

Construct MIME containing:

- Plain-text and HTML alternatives.
- Inline `Content-ID` image.
- Small PDF attachment.
- Unicode filename.
- Nested multipart.
- Special MIME headers.

After store/readback, verify the parts policy requires preserving. If the contract is byte-for-byte capture, compare captured byte streams; if the contract is a semantic snapshot, verify subject/body/attachment contents and meaningful metadata.

## 39. Testing DB/Object Consistency

Key fault injections:

| Scenario | What Must Be Proven |
| --- | --- |
| Storage PUT fails mid-stream | Not marked READY; staging cleaned up |
| PUT succeeds then DB rolls back | Reconciler deletes orphan |
| DB pointer commits yet object unreadable | Clear alert and error state |
| SHA-256 differs on readback | Do not send/replay corrupted artifact |
| Worker crashes mid-upload | Staging TTL cleanup |
| Retry upload with same mail ID | Does not accidentally overwrite version |
| Attachment deleted early | Retry job fails cleanly |
| Legal hold active | Cleanup does not delete against policy |
| Retention reached | Deletes raw, derivatives, and metadata per policy |
| Object referenced by multiple jobs | Not deleted while live references exist |
| Cross-tenant read | Blocked at application and storage boundaries |
| Malware scan unfinished | Unapproved file never served |

Use a test object store and test database in integration tests. Never run automated tests against production buckets or delete real data.

### Do Not Mix Content QA with Storage Tests

Storage integration tests verify object bytes, references, transactional states, and cleanup follow the contract. Reviewing email copy/templates is a separate test layer. Even with a properly stored raw artifact, wrong business rendering still sends wrong content.

## 40. Testing Inbound Retention and Recovery

An inbound test with an IMAP test server (e.g., GreenMail if used by the project) can run:

~~~text
1. Seed a MIME mail into test INBOX.
2. Receiver reads account/folder/UID metadata.
3. Capture content/raw per policy.
4. Commit ingestion record and artifact reference.
5. Simulate mailbox message deleted/expunged.
6. Business reprocessor reads artifact, independent of mailbox.
7. Re-polling same UID namespace creates no duplicate.
~~~

Key details:

- `MimeMessage` folder/session lifecycle.
- UID/`UIDVALIDITY` when supplied by the server.
- MIME parser and file size bounds.
- No mark/delete before durable capture when retries depend on the message.
- Reprocessing produces no duplicate business side effects.
- Isolated test resources—never use personal/production inboxes.

If inbound policy is metadata-only, tests should also document what is **unsupported**, e.g., no raw attachment viewing after mailbox expunge.

## 41. Testing Raw Access Security

Scenarios:

- Tenant A support agent cannot download tenant B raw mail.
- Users without `raw-download` permission can view only allowed metadata.
- Expired signed URLs cannot be reused.
- HTML with remote images does not auto-fetch during preview.
- Unscanned attachments cannot be downloaded publicly.
- Path traversal in object keys cannot control storage paths.
- Audits record actor and download purpose.
- Retry service account can read needed snapshots without admin access to all buckets.
- Raw messages containing reset tokens are masked/short-lived per policy.
- Delete requests purge derived indexes/caches per policy.

These are authorization/data-lifecycle tests; unit testing a single `canRead()` method does not prove full object-store IAM protection.

## 42. Common Architectural Mistakes

### 42.1. Storing Full MimeMessage as a Java Object in the Database

`MimeMessage` is not a stable serialized entity for durable storage. It can bind to folders/sessions and hold streams and internal state. Store a **serialized MIME artifact** or a schema-versioned snapshot DTO.

### 42.2. Storing Only Message-ID Expecting to Recover the Body

The `Message-ID` header is not a durable provider content address and can be duplicated/forged. If the mailbox deletes the message, content can be lost.

### 42.3. Storing Raw MIME Without Storing SMTP Envelope/Attempts

Bcc recipients, provider accounts, retry outcomes, and delivery events may not appear in MIME. Operational metadata is still required.

### 42.4. Treating MimeMessage.writeTo as Original Wire Bytes

Serialization can alter headers/boundaries/encoding. Explicitly record the capture point and artifact type.

### 42.5. Storing Large byte[] Blobs in the Outbox DB

Bloats backups, memory, DB I/O, and PII risk. For large payloads, use policy-governed object storage.

### 42.6. Storing Metadata Only While Templates/Files Are Mutable

Retry workers may render altered content. Pin snapshot/attachment versions when required.

### 42.7. Keeping Every Email Forever "Just in Case"

Accumulates sensitive data and cost; require an approved purpose and retention period.

### 42.8. Deleting Raw Objects While Forgetting Indexes/Thumbnails/Caches

Sensitive data remains in derived copies. Cleanup must cover all derivatives.

### 42.9. Database Pointing to Unfinished Uploads

Workers hit missing/corrupt artifacts. Use staging and mark READY only after storage confirmation.

### 42.10. PUT Succeeds, DB Rolls Back, No Cleanup

Creates costly storage orphans that can outlive retention.

### 42.11. Using Checksums as Proof of Sender Authenticity

Checksums only verify integrity against a reference value; they do not prove identity or delivery.

### 42.12. Rendering Raw HTML Directly

Can trigger tracking or malicious content. Use sanitizers/sandboxes and access controls.

### 42.13. Trusting Attachment Filenames/Content-Types

Sender-supplied metadata is untrusted; validate content and scan.

### 42.14. Treating Object Keys as Authorization Tokens

Knowing a key must not grant read access. Enforce IAM/application authz.

### 42.15. Uncontrolled Cross-Tenant Deduplication of Raw Attachments

Risks inference attacks and deletion-policy conflicts. Protect ownership and lifecycles.

### 42.16. Assuming Raw MIME Prevents Retry Duplicates

SMTP acceptance followed by worker crash can still resend. Outboxes do not grant exactly-once.

### 42.17. Skipping Consent/Token Checks During Replay

Old content may no longer be permitted to send even if bytes are unchanged.

### 42.18. Monitoring Stored Bytes Alone

Also track orphans, checksum mismatches, access audits, and retention compliance.

### 42.19. Not Distinguishing Prepared MIME from Captured Originals

Leads to false claims about evidentiary value. Record capture method/version/time.

### 42.20. Not Defining Recovery Requirements Before Choosing Metadata-Only

Wait until an incident and you discover files are gone or bodies cannot be rebuilt.

## 43. Scenario Questions

**Q1.** We only need to count sent emails and inspect SMTP errors. Do we need full MIME?

Usually no. Job/attempt/provider-feedback metadata suffices when body inspection is not required.

**Q2.** Receipts must reflect exact payment amounts even if orders later change. What should we store?

An immutable transaction snapshot, template version, and matching receipt/attachment version.

**Q3.** Inbound mail has attachments and the provider purges INBOX after 7 days. Are subject and UID enough to reprocess a month later?

No. Capture required content/attachments before purge time.

**Q4.** Does `mime.writeTo(out)` guarantee byte-for-byte identity with what the SMTP server received?

No. Define capture boundaries and account for serialization/transport transformations.

**Q5.** If we have raw MIME but no provider message ID, does that prove the email was delivered?

No. Raw content does not replace submission/delivery feedback.

**Q6.** Are Bcc recipients guaranteed to be inside raw MIME headers?

No. SMTP envelopes and MIME headers differ; Bcc is normally stripped rather than preserved like To.

**Q7.** Object upload succeeded, DB commit failed. What remains?

A potential orphan object; reconciliation/cleanup is needed.

**Q8.** DB points to raw MIME, yet object PUT failed. How do we stop workers from reading broken data?

Never mark an artifact READY until the object exists and is verified; use staging/error states.

**Q9.** What does a SHA-256 digest verify?

It verifies current bytes match the hashed bytes—not origin or authenticity.

**Q10.** Is storing raw MIME of OTP emails for years to debug reasonable?

Usually incompatible with data minimization; enforce TTLs and avoid retaining plaintext tokens.

**Q11.** Does full-text search on email bodies affect retention?

Yes. It creates a derived copy that must be protected and deleted per policy.

**Q12.** Attachment sits in a web pod's local temp folder while outbox workers run on another pod. Is that durable?

No. Use shared, versioned storage that survives across the retry window.

**Q13.** Should we store raw MIME for all marketing emails just because week-one storage looks cheap?

Model long-term volume, retention, privacy, and actual business need first; never default blindly.

**Q14.** An inbound mailbox only creates tickets and never needs body review later. Is metadata-only viable?

Possibly, provided business inputs are persisted elsewhere before mailbox ack/deletion and missing raw copies are accepted.

**Q15.** Can support view emails by rendering raw HTML directly from `MimeMessage`?

Avoid doing so. Inbound HTML is untrusted; sanitize, block remote resources, and enforce permissions.

**Q16.** A template changes between two retries. Could content differ?

Yes, if resolving latest templates only. Use versioned templates/snapshots when content consistency matters.

**Q17.** A tenant asks to delete an email; raw object is deleted, yet attachment thumbnails remain. Is deletion complete?

No; derived copies, indexes, and backups must be handled per policy.

**Q18.** Does storing full MIME prevent SMTP duplicates if a worker crashes after acceptance?

No. Content durability and exactly-once submission are separate problems.

## 44. Mental Model to Remember

~~~mermaid
flowchart TD
    A["Inbound / outbound email"] --> B["Purpose + data classification"]
    B --> C{"Need to retain content?"}
    C -->|"No"| D["Metadata + attempts"]
    C -->|"Yes"| E{"Need verbatim raw MIME?"}
    E -->|"No"| F["Versioned content snapshot"]
    E -->|"Yes"| G["Raw MIME capture"]
    F --> H["Encrypted object storage"]
    G --> H
    H --> I["Artifact checksum + version + READY"]
    D --> J["Retention + authorization"]
    I --> J
    J --> K["Controlled search / replay / audit"]
    K --> L["Cleanup + reconcile"]
~~~

Key principles:

1. **Metadata-only, snapshots, raw MIME, and hybrid are distinct models**; define goals before choosing.
2. **Raw MIME excludes full envelopes, attempts, and delivery feedback**; structured metadata is still required.
3. **Outbound usually owns message sources**, yet if templates/domain data mutate, metadata-only cannot replay old content.
4. **Inbound depends on external mailboxes**, so capture key data before deletion/session closure.
5. **`MimeMessage.writeTo` serializes at a point in time**; it does not prove original wire bytes.
6. **Attachments and inline assets need their own lifecycles**; storing HTML/text alone is incomplete.
7. **Object storage handles large content without sharing DB ACID transactions**; use staging, READY states, and orphan cleanup.
8. **Checksums/versions verify integrity**, not signatures or delivery.
9. **Raw MIME contains sensitive data**, requiring encryption, least privilege, audits, malware scans, and TTLs.
10. **Metadata also holds PII**, requiring minimization and access controls.
11. **Retention must cover copies, indexes, caches, and backups**, not just deleting one DB row.
12. **Outboxes store durable intent**, do not mandate raw MIME, and do not guarantee exactly-once SMTP.
13. **Send-time policies must be rechecked on retry/replay**, especially consent, token expiry, and tenant status.
14. **Multi-tenant systems must isolate storage/search/authz**, never treating object keys as authorization.
15. **Test against the contract**: readback, checksums, DB/object consistency, recovery, retention, and cross-tenant access.
16. **Per-purpose policies matter more than a global flag**, especially for OTPs, payment receipts, and inbound documents.

In Spring Framework Mail, choosing between full message storage and metadata-only storage is a **decision about content recoverability, the scope of sensitive data you take responsibility for protecting, and audit commitments**. When you only need to track jobs, retries, and delivery statuses, structured metadata usually suffices. When you must reconstruct content as of the event time, store versioned snapshots and immutable attachments. When you must inspect headers/MIME or reparse inbound messages, raw MIME may be necessary—backed by clear capture points, encryption, retention, and access controls. The most resilient design retains **the exact data needed, in the right place, for the right duration**, with explicit clarity on what can and cannot be recovered after failures.



