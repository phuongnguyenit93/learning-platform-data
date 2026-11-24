# Least Privilege and Content Inspection for Incoming Mail in Spring Framework Mail

When building an application that processes incoming emails—such as receiving customer support emails, collecting invoices from an accounting mailbox, or reading partner replies—the problem goes beyond **logging into IMAP and fetching email content**. An email arriving from outside is **untrusted data** that can contain spoofed headers, malicious HTML, phishing links, dangerous attachments, complex MIME structures, or sizes exceeding system limits. At the same time, mailbox login credentials may allow reading vast amounts of private mail, or even deleting, forwarding, or sending mail if granted overly broad permissions.

Therefore, this lesson establishes two parallel lines of defense:

1. **Least privilege:** the mail-reading process holds only the minimum permissions necessary for the exact permitted account, folder, and operations.
2. **Content inspection:** every incoming email passes through a pipeline with resource limits, source verification, MIME parsing, attachment quarantine, and safety checks before executing any business impact.

The goal is not to build an "absolutely safe email filter", but to design a system that can **receive mail reliably, minimize blast radius if an account is compromised or an email carries dangerous payloads, and prevent both dropped mail and duplicate processing**.

> Key principle: **being able to read an email does not mean the email's content is allowed to command the application**. `From` addresses, `Subject`, HTML, filenames, and information inside the message must all be treated as untrusted input until checked against explicit policies.

## 1. Scope of Mail Receiving in the Spring Ecosystem

The name "Spring Framework Mail" often evokes `JavaMailSender`, `JavaMailSenderImpl`, and `MimeMessageHelper`, yet those abstractions primarily serve **composing and sending mail**. To **receive mail**, applications typically use:

- **Jakarta Mail API:** connecting `Store`, opening `Folder`, reading `Message`, `Part`, `Multipart` over IMAP/IMAPS or POP3/POP3S.
- **Spring Integration Mail** (if the project includes the module): supporting polling or IMAP IDLE and integrating messages into Spring Integration flows.
- **Mail provider APIs/webhooks:** receiving metadata or raw messages per provider contract, requiring dedicated webhook/API authentication.

Do not assume `JavaMailSender.receive()` exists. This lesson uses **Jakarta Mail** to demonstrate mailbox connectivity and outlines the same rules when implementing with Spring Integration Mail or provider APIs.

### Processing Flow Diagram

~~~mermaid
flowchart TD
    A["Mailbox / IMAP or provider event"] --> B["Read-only ingestion identity"]
    B --> C["Bounded retrieval + durable staging"]
    C --> D["Metadata and MIME validation"]
    D --> E["Attachment and malware checks"]
    E --> F{"Allowed to process?"}
    F -- "No" --> G["Quarantine / reject / review"]
    F -- "Yes" --> H["Normalize trusted business data"]
    H --> I["Idempotent business handler"]
    I --> J["Record processing result"]
    J --> K["Acknowledge / move if authorized"]
~~~

A system may replace IMAP connectivity with webhooks, yet the requirements around **least privilege, size caps, content parsing, source verification, idempotency, and auditing** remain unchanged.

## 2. Threat Model of an Automatically Processed Mailbox

Risk categories to consider:

| Risk Source | Example | Mitigation |
| --- | --- | --- |
| Compromised mailbox account | Credentials can read all mail, delete/alter state | Service mailbox, minimal OAuth scope/ACL, secret manager |
| Spoofed sender | `From` header mimics an internal partner | Never trust `From`; authenticate by source and policy |
| Malicious MIME | Deeply nested multipart, malformed headers, odd encoding | Bounded parsing and quarantine mechanisms |
| Oversized content | Message body/attachment fills memory/disk | Server limits, bounded streams, quotas |
| Dangerous attachments | Macros, executables, archive bombs, viruses | Allowlists, MIME sniffing, malware scanning, isolation |
| Dangerous HTML | Scripts, remote images, phishing links, deceptive CSS | Never execute; render plain text or sanitize properly |
| Prompt/command injection | Email demands "bypass process, wire funds" | Business authorization independent of email text |
| Duplicate emails | Repeated IMAP polling, worker restarts, webhook redeliveries | UID/`UIDVALIDITY` + idempotency |
| Prematurely marked as read | Fetching sets `\Seen` or worker acks before commit | Read-only/peek, staging, post-processing ack |
| Operational data leaks | Logging full bodies, tokens, filenames, and headers | Redaction, access controls, retention |
| SSRF via content | Parser fetches URLs in HTML or external resources | Never auto-fetch external resources |
| Misdirected replies | Auto-reply to a spoofed `Reply-To` address | Separate authorization and outbound policies |

A single email can carry multiple risks simultaneously. For example, a file named `invoice.pdf` could be a disguised executable, inside nested archives, or a document containing malicious links. Checking **a single attribute alone** does not guarantee safety.

## 3. Least-Privilege Principle for Mail-Receiving Accounts

**Least privilege** means a process is granted only the permissions strictly needed to complete its task.

### Permissions Typically Needed vs. Permissions to Avoid

| Action | Needed for Read-Only Ingestion? | Notes |
| --- | --- | --- |
| List permitted folders | Possibly | Restrict scope if provider supports it |
| Read metadata of new mail | Yes | No need to read entire mailbox history |
| Read content of selected messages | Yes | Only inside granted mailbox/folder |
| Create/delete folders | No, unless explicit workflow | Easy to cause mail loss |
| Mark `\Seen` | Not mandatory | Avoid using as replacement for durable ack |
| Mark `\Deleted` and expunge | No for read-only ingest | Can permanently delete mail |
| Move mail to processed folder | Only if workflow requires | Grant dedicated write permission and audit log |
| Send mail from the account | Usually no | Separate sending/receiving identities |
| Access other users' mailboxes | No | Avoid broad domain-wide delegation |
| Administer accounts/mailboxes | No | Separate operator identities |

Opening `Folder.READ_ONLY` in the application **does not replace server-side ACLs**. If the actual credentials have permission to delete every email, a read-only snippet does not limit damage if the credentials are stolen or code has a bug. Enforce least privilege at both **provider/IAM/ACL** and **application** layers.

### A Dedicated Mailbox

Example for invoice ingestion:

- Address `invoices-inbound@example.org` receives only emails for the invoice workflow.
- Connecting credentials are scoped to read that mailbox, never employees' personal mailboxes.
- Workers open only the configured folder, never scanning every folder.
- A mailbox for sending replies/rejections uses a separate service identity if needed.
- Mailbox administration and permission changes are audited.

Separating mailboxes not only improves security, but also reduces irrelevant personal data pulled into the system.

### Multi-Tenant Isolation

If the product serves multiple customers/tenants, never use a single token capable of reading all mailboxes unless strictly required and tightly controlled. For every message, correlation must bind `tenantId`, account, folder, and source identity; a routing bug must never send tenant A's email into tenant B's processor.

## 4. Restricting by Folder, Operations, and Time

An account can have many folders: INBOX, Sent, Archive, Spam, Trash, and custom folders. Ingestion should:

1. Open only a configured/allowlisted set of folders.
2. Fetch only messages matching criteria, such as UIDs higher than a checkpoint or recent arrivals.
3. Use **READ_ONLY** when fetching content if flag updates are not needed.
4. Never automatically read Sent, Trash, Spam, or other users' folders.
5. Never automatically move/delete emails when the parser or business handler fails.
6. Record required permissions explicitly if messages must move to a quarantine/processed folder.

### READ_ONLY Is Not Enough to Restrict Reading to One Folder

Folder read permissions can be enforced via IMAP ACLs or provider APIs/IAM, depending on the service. Some providers issue account-level scopes without granular per-folder restrictions; in that case, use dedicated accounts/mailboxes and routing controls rather than assuming `Folder.READ_ONLY` is a security boundary.

### Never Scan Entire History on Every Poll

Each run should process in batches with checkpoints and backpressure. Repeatedly loading all 100,000 messages stalls the system, exceeds quotas, and risks reprocessing old mail. Use IMAP UIDs/checkpoints or provider event cursors where appropriate.

## 5. Credentials and OAuth2: Grant as Little Read Access as Possible

Depending on the provider, a mail-receiving app may authenticate via passwords, app passwords, SASL OAuth2, or provider-specific mechanisms.

### Prefer Dedicated Identities

- Never use employees' personal mailbox passwords in production.
- Avoid domain-wide delegation or broad admin rights when only one mailbox needs reading.
- With OAuth2, request the minimal scope the provider truly supports for reading/metadata.
- Separate the **mail-reading** identity from the **mail-sending** identity when architecture permits.
- Rotate/revoke credentials by procedure, logging versions rather than values.
- Protect refresh tokens and private keys with the same rigor as passwords.

There is no universal OAuth scope list across all IMAP providers. Some providers support narrow read scopes over REST APIs while requiring broader scopes for IMAP. Check documentation for the **exact provider and protocol**; never invent an assumed scope name and call it least privilege.

### Secret Manager and Runtime

Credentials should be injected into workloads via an appropriate secret store/managed identity. Never hardcode them in Java, committed YAML, logs, CI output, tickets, or URI connection strings.

When secrets rotate, active `Store` instances or connection pools may still hold stale credentials/tokens. Design controlled reconnect/refresh logic so hundreds of workers do not retry logins simultaneously and lock the account.

### Expired OAuth Tokens

For short-lived access tokens:

- Track expiry and refresh ahead of a safety margin.
- Do not refresh independently per email at the same instant.
- Distinguish expired tokens from revoked permissions.
- If refresh fails, pause polling or mark degraded; never fall back to weaker password auth.
- Never mark an email as processed merely because the connection dropped.

## 6. Secure IMAPS Connections: TLS and Timeouts

Plain IMAP typically uses port 143 with STARTTLS (if deployed), while IMAPS typically uses port 993 with TLS from the start. Never guess the mode solely from the port and ignore provider documentation.

Example Jakarta Mail IMAPS configuration in Java:

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.Store;

public final class InboundMailConnection {

    public static Store openImaps(
            String host,
            int port,
            String username,
            String secret) throws Exception {

        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "3000");
        props.put("mail.imaps.timeout", "5000");
        props.put("mail.imaps.writetimeout", "5000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");
        store.connect(host, port, username, secret);
        return store;
    }
}
~~~

Timeout values are in milliseconds in standard Jakarta Mail implementations and illustrative only. Ensure a valid truststore/certificate chain and hostname verification enabled per policy. This snippet shows connecting with a runtime secret; it **does not automatically implement OAuth2 token refresh or provider ACL bounds**.

### If Using IMAP + STARTTLS

Configuration differs from IMAPS: use protocol `imap` on the provider-appropriate port/config, requiring STARTTLS via `mail.imap.starttls.enable` and `mail.imap.starttls.required` when supported by the library. Never allow automatic downgrade to plaintext when the provider requires TLS.

### Never Use Trust-All to Fix Certificate Errors

Workarounds like disabling hostname verification, trusting all certificates, or using trust-all in production weaken transport security. On handshake errors, inspect:

- Hostname, SNI, and certificate SANs.
- CA chain and Java truststore.
- TLS mode and port.
- System clock, certificate expiry, and TLS protocols/ciphers.
- DNS/egress proxies or internal relay certificates.

**Timeouts are not authentication guarantees.** Opening a connection and downloading mail does not prove the workload can only read authorized messages; permissions must be enforced at the provider.

## 7. Reading IMAP with READ_ONLY and UIDs Instead of Sequence Numbers

In Jakarta Mail, `Store` represents the mail-server connection and `Folder` represents a folder. Under IMAP, each email has a **message sequence number** that can shift when other messages are deleted or expunged. Thus, never use `folder.getMessage(5)` as a permanent identifier for an email.

IMAP also supports **UIDs** bound to messages in a folder and **UIDVALIDITY** indicating the validity scope of those UIDs. A checkpoint key can consist of:

~~~text
mailbox account ID
+ folder identity
+ UIDVALIDITY
+ UID
~~~

Never store `UID` alone as a system-wide key: UID 42 in folder A does not match UID 42 in folder B; when `UIDVALIDITY` changes, old checkpoints no longer have the same meaning.

### Example Connecting and Scanning a Batch of Messages

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Store;
import jakarta.mail.UIDFolder;

public final class InboundImapPoller {

    private final InboundMessageStager stager;

    public InboundImapPoller(InboundMessageStager stager) {
        this.stager = stager;
    }

    public void poll(
            String host,
            int port,
            String username,
            String secret) throws Exception {

        Store store = InboundMailConnection.openImaps(
                host, port, username, secret);

        try {
            Folder folder = store.getFolder("INBOX");
            if (!folder.exists()) {
                throw new IllegalStateException("INBOX unavailable");
            }

            folder.open(Folder.READ_ONLY);
            try {
                if (!(folder instanceof UIDFolder uids)) {
                    throw new IllegalStateException(
                            "UID support required");
                }

                long uidValidity = uids.getUIDValidity();
                int count = folder.getMessageCount();
                int first = Math.max(1, count - 49);

                for (int number = first; number <= count; number++) {
                    Message message = folder.getMessage(number);
                    long uid = uids.getUID(message);

                    if (uid < 0) {
                        continue; // handle with a provider-specific policy
                    }

                    stager.stage(
                            "inbound-account",
                            folder.getFullName(),
                            uidValidity,
                            uid,
                            message);
                }
            } finally {
                folder.close(false); // do not expunge
            }
        } finally {
            store.close();
        }
    }
}
~~~

`InboundMessageStager` is an application interface to implement yourself. The example fetches **at most the last 50 messages by sequence at runtime** to illustrate resource bounding; this is **not a production algorithm guaranteeing zero missed mail**: if more than 50 new emails arrive between polls, older ones can be missed. In production, store UID checkpoints, query the full unprocessed UID range, and paginate/batch until the backlog clears.

### Safety Points in the Example

- Opens `Folder.READ_ONLY` to avoid mutating server flags.
- Does not delete emails or call expunge.
- Records account/folder/`UIDVALIDITY`/UID into staging.
- Closes `Folder` and `Store` on completion or error.
- Never uses `Subject`, `From`, or RFC `Message-ID` as unique keys.

### Limitations to Understand

- UID and `UIDVALIDITY` are properties of UID-supporting folders; moving an email to another folder can change its UID.
- If `UIDVALIDITY` changes, have a reconciliation or idempotent rescan plan; never trust the old generation's UID checkpoint.
- `getMessageCount()` and fetches can observe mutating results under concurrent server/user activity.
- A message can vanish while a worker is reading it; handle fetch errors and continue safely.
- Providers may enforce request/fetch quotas; enforce concurrency/rate limits.
- `Folder.READ_ONLY` is a client-side folder open mode, **not a substitute for server-side least-privilege read permissions**.

## 8. Never Use the \Seen Flag as a Durable Acknowledgment

In IMAP, `\Seen` is a flag showing a message has been marked read. It was **not designed as a transaction marker** for business applications.

Example failure flow:

~~~text
Worker fetches message
    |
    +--> server marks \Seen
    |
    v
Application crashes before saving message
    |
    v
Next poll filters only UNSEEN
    |
    v
Message silently skipped
~~~

If the application only processes `UNSEEN`, a user reading the email or another client can make the message disappear from processing. Design instead:

1. Scan by UID/cursor or a durable event source.
2. Check whether the inbox ledger already processed it.
3. Save needed content into a safe staging area.
4. Commit `STAGED` status.
5. Process asynchronously and update to `PROCESSED` or `QUARANTINED`.
6. Move/flag only after outcomes are persisted and **only when the account holds proper permissions**.

For IMAP clients needing to minimize `\Seen` changes, `Folder.READ_ONLY` is the baseline choice. Some Jakarta Mail IMAP implementations also support `mail.imaps.peek` to fetch bodies without marking Seen; verify behavior per provider/version and never rely on this flag as an idempotency mechanism.

### Do Not Mark-and-Delete to "Clean Up the Mailbox"

For read-only accounts, avoid `setFlag(Flags.Flag.DELETED, true)` and `expunge()`. If retention or archiving is needed, make it a separate permissioned and audited step after data is safely persisted—never couple deletion into a parser that could fail mid-flight.

## 9. IMAP and POP3 Differ in Permission Scope

IMAP has folders, flags, and UIDs. POP3 generally exposes a simpler mailbox message list with retrieval commands, `UIDL` (if supported by the server), and protocol-defined deletion when the session ends.

| Aspect | IMAP/IMAPS | POP3/POP3S |
| --- | --- | --- |
| Multiple folders | Common | Usually not a goal |
| Flag sync | Supported | Limited |
| Stable identifiers | UID + `UIDVALIDITY` per folder | `UIDL` if supported by server |
| App read-only mode | Open folder `READ_ONLY` | Avoid `DELE`; check server permissions |
| Tracking new mail | Poll/IDLE per server | Polling |
| Multi-client handling | Better suited, still needs sync | Server-dependent, may restrict sessions |
| Permissions and config | Provider-specific ACL/scopes | Provider-specific |

If using POP3:

- Never rely on **message numbers** as long-term keys because numbers can shift.
- Use `UIDL` when supported and verify provider behavior.
- Never trigger `DELE` without a retention workflow.
- Enforce the same mailbox permissions, download limits, and retries as IMAP.
- Do not assume POP3 `UIDL` has the same semantics as IMAP `UIDVALIDITY`.

In many systems, IMAP or provider APIs fit checkpointed processing better, though the choice depends on the mail server and business requirements.

## 10. Two-Phase Mail Receiving: Staging and Processing

To prevent MIME parsing or virus scanning from disrupting fetching and dropping emails, split into two phases:

**Phase 1 — Ingestion/staging:**

1. Derive the message key from account/folder/UID.
2. Check metadata and preliminary size limits.
3. Save a copy of the email or needed parts into bounded isolated storage.
4. Compute hashes and record a ledger entry in `STAGED` state.
5. Acknowledge batch ingestion (not necessarily mutating server flags).

**Phase 2 — Inspection/processing:**

1. Claim the staging record with a lease.
2. Inspect MIME structure, actual sizes, types, and attachments.
3. Scan for malware per policy.
4. If safe and valid, extract business data in a bounded format.
5. Run independent authorization/business validation.
6. Commit processing outcomes idempotently.
7. Mark `PROCESSED`, `REJECTED`, or `QUARANTINED`.

### Why Persist Durably First?

If a worker removes a message from the server or marks it Seen before saving, a crash can leave the application **unable to find** the message again. With durable staging, parsing/scanning can retry during scanner outages without re-reading the mailbox every time.

### Staging Idempotency

A typical unique key:

~~~text
tenantId
+ providerAccountId
+ folderId
+ uidValidity
+ uid
~~~

If a provider API supplies a stable message resource ID, use it per the API contract; do not force IMAP keys onto every provider. Sender-supplied RFC `Message-ID` **is not trustworthy as a sole key** because it can be missing, duplicated, spoofed, or changed on forwarding.

## 11. State Machine for Incoming Mail

~~~mermaid
flowchart TD
    A["DISCOVERED"] --> B["FETCHING"]
    B --> C{"Staging persisted?"}
    C -- "No" --> D["RETRY_FETCH with backoff"]
    C -- "Yes" --> E["STAGED"]
    E --> F["INSPECTING"]
    F --> G{"Validation + scan"}
    G -- "Unsafe" --> H["QUARANTINED"]
    G -- "Invalid" --> I["REJECTED"]
    G -- "Scanner unavailable" --> J["RETRY_INSPECTION"]
    G -- "Allowed" --> K["READY_FOR_PROCESSING"]
    K --> L["Business handler"]
    L --> M{"Committed?"}
    M -- "No" --> N["RETRY_PROCESSING"]
    M -- "Yes" --> O["PROCESSED"]
~~~

These states are an **application-defined model**; Spring Mail does not include built-in `QUARANTINED` or `STAGED` enums.

A record may contain:

| Field | Role |
| --- | --- |
| `accountId`, `tenantId` | Partitioning and access control |
| `folderId`, `uidValidity`, `uid` | IMAP correlation |
| `rfcMessageId` | Reference/tracing info, not a unique key |
| `receivedAt`, `stagedAt` | Operations and retention |
| `rawStorageKey` | Securely stored isolated object |
| `rawSha256` | Tamper detection and audit support |
| `status`, `stopReason` | Next action |
| `attemptCount`, `nextAttemptAt` | Backoff and retry budget |
| `leaseOwner`, `leaseUntil` | Prevents concurrent processing by multiple workers |
| `inspectionVersion` | Version of policy/engine that inspected it |

Do not place full raw MIME or email bodies into a readable log column unnecessarily; store isolated objects with explicit encryption, ACLs, and TTLs.

## 12. Every Incoming Email Must Have Resource Limits

An email may have a short body yet massive MIME parts, multi-encoded base64 attachments, nested multiparts, or huge decompressed archives. Enforce multi-layered limits:

| Limit | Mitigated Risk |
| --- | --- |
| Messages fetched per batch | Prevents one poll from monopolizing workers |
| Concurrent connections/pollers | Prevents IMAP quota breaches/provider lockouts |
| Connect/read/write timeouts | Prevents workers hanging indefinitely |
| Raw RFC 5322 message size | Prevents downloading/storing huge messages |
| Total decoded bytes | Caps content after `Content-Transfer-Encoding` |
| MIME part count | Prevents multiparts with excessive parts |
| `multipart`/`message/rfc822` depth | Prevents overly deep nesting |
| Size per attachment | Caps individual files |
| Total attachment size | Prevents many small files from adding up |
| Parse/scan duration | Prevents stalled parser/AV workers |
| Total decompressed files | Reduces archive bomb risk |
| Maximum compression ratio | Reduces tiny-archive huge-expansion risk |
| URL/link/header counts | Reduces parser load, prevents resource abuse |
| Quarantine retention/duration | Prevents unbounded data accumulation |

**There is no single right default for every application.** For example, a PDF invoice system may permit larger attachments than a customer feedback handler. Base limits on business needs, resources, mail server quotas, and trust levels.

### Declared Size Is Not Final Proof

`Message.getSize()`, `Part.getSize()`, provider-supplied `Content-Length`, or MIME headers can be missing, `-1`, differ from downloaded sizes, or fail to reflect decoded size. Use them as **early filters**, while enforcing actual bytes read/written at the stream/storage layer.

### Limit Input Before Parsing

If the system can enforce message size limits at the ingress/mail gateway or provider, do so. Checking size after loading the entire email into memory **does not prevent OOM during download**. For IMAP mail, Jakarta Mail fetching and MIME parsing may buffer data internally; combine server limits, network/quotas, bounded staging, and process limits.

## 13. Example: Capping Bytes Written to Staging

One way to enforce a size counter is wrapping `OutputStream` and **throwing immediately when the limit is exceeded**, rather than reading all bytes into a `byte[]` first.

~~~java
package com.example.inbound;

import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;

public final class LimitOutputStream extends FilterOutputStream {

    private final long maxBytes;
    private long written;

    public LimitOutputStream(OutputStream out, long maxBytes) {
        super(out);
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Negative size");
        }
        this.maxBytes = maxBytes;
    }

    @Override
    public void write(int value) throws IOException {
        ensureCanWrite(1);
        out.write(value);
        written++;
    }

    @Override
    public void write(byte[] data, int offset, int length)
            throws IOException {
        if (data == null) {
            throw new NullPointerException("data");
        }
        if (offset < 0 || length < 0
                || offset > data.length - length) {
            throw new IndexOutOfBoundsException();
        }
        ensureCanWrite(length);
        out.write(data, offset, length);
        written += length;
    }

    private void ensureCanWrite(long length) throws IOException {
        if (length > maxBytes - written) {
            throw new IOException(
                    "Inbound message exceeds configured limit");
        }
    }

    public long writtenBytes() {
        return written;
    }
}
~~~

This caps **output bytes** at the write destination. It does not by itself control how much data Jakarta Mail already downloaded/buffered before `writeTo` was called. Therefore combine gateway/provider size limits, early metadata checks, worker memory limits, and large-message testing.

### Safe Staging to a Temporary File

~~~java
package com.example.inbound;

import jakarta.mail.Message;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RawMailStaging {

    public static Path writeBounded(
            Message message,
            Path quarantineDirectory,
            long maxRawBytes) throws Exception {

        // Directory configured by the application,
        // never taken from email filename/headers.
        Files.createDirectories(quarantineDirectory);
        Path temporary = Files.createTempFile(
                quarantineDirectory,
                "mail-stage-",
                ".eml.part");

        boolean completed = false;
        try {
            int declaredSize = message.getSize();
            if (declaredSize > maxRawBytes) {
                throw new IOException("Message too large");
            }

            try (OutputStream file = Files.newOutputStream(temporary);
                 LimitOutputStream limited =
                         new LimitOutputStream(file, maxRawBytes)) {
                message.writeTo(limited);
            }

            completed = true;
            return temporary;
        } finally {
            if (!completed) {
                Files.deleteIfExists(temporary);
            }
        }
    }
}
~~~

`message.writeTo(...)` writes the RFC 5322/MIME representation produced by Jakarta Mail from the message object. It **does not necessarily preserve the exact wire bytes bit-for-bit** in every case, and the library may fetch or parse data before writing. If the application needs intact forensic evidence, use a provider raw-fetch mechanism, source hashing, and matching storage handling rather than assuming `writeTo` is an exact wire capture.

### Requirements Beyond the Example

In production, you should:

- Place the folder on a dedicated volume/quarantine with restricted permissions, never served directly by a web server.
- Cap disk/object-store capacity, file counts, and per-tenant quotas.
- Ensure email paths can never escape the staging directory.
- Use atomic commits/renames and an appropriate database ledger.
- Encrypt stored data when required by policy.
- Compute checksums during writes, syncing storage with state records.
- Clean up partial files after process crashes.
- If `writeTo` cannot satisfy memory constraints, switch to a provider raw streaming API/gateway.

The illustrative method only writes a temp file and returns its path. It does **not** implement OS/container isolation, virus scanning, transactions, or retention on its own.

## 14. MIME Parsing: Never Trust Filenames and Content-Type

An email may contain:

~~~text
message/rfc822
 |
 +-- multipart/mixed
      |
      +-- multipart/alternative
      |    +-- text/plain; charset=UTF-8
      |    +-- text/html; charset=UTF-8
      |
      +-- application/pdf
      +-- application/octet-stream
      +-- message/rfc822
           +-- nested message
~~~

MIME allows nested parts, and `Content-Type` or `Content-Disposition` are sender-supplied. A part named `report.pdf` is not guaranteed to contain PDF bytes; `attachment` is not guaranteed safe; `inline` can also carry dangerous payloads.

### Structural Inspection Steps

1. Cap total raw size before parsing.
2. Cap MIME part count and nesting depth.
3. Cap data size after decoding transfer encoding.
4. Identify `text/plain`, `text/html`, attachments, and nested messages.
5. Normalize filenames using Unicode/whitespace rules.
6. Check file extensions against a business allowlist.
7. Verify MIME type **from actual contents** using a proper library, not headers alone.
8. Scan for malware and apply archive/encryption/macro policies.
9. Pass only safe data to the business handler.

### Content-Type Is Not Trustworthy Evidence

For example, an email can declare:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

while leading bytes are not a PDF, or content is a polyglot. A detector like Apache Tika can help identify formats from magic bytes and structure, yet it is **not an antivirus**. A well-formed PDF can still contain malicious links/scripts/embedded objects. Multi-layered policies are needed.

### Handling Charsets and Transfer Encodings

`Content-Transfer-Encoding` may be base64, quoted-printable, or another value. Jakarta Mail's `Part.getInputStream()` usually returns a stream decoded from transfer encoding for body parts; this means **decoded byte size can differ from raw bytes**. Never use an untrusted header's `Content-Length` to allocate huge arrays.

For text:

- Check supported charsets.
- Cap character counts after decoding.
- Define policies for invalid charsets or malformed data.
- Use text for business data only after normalization/validation.
- Never auto-execute HTML/JavaScript in clients or admin dashboards.

## 15. Java Example: Capping Total MIME Parts and Decoded Bytes

Once the raw message passes staging limits, MIME parts can be traversed with guards. Example:

~~~java
package com.example.inbound;

import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.InputStream;

public final class MimeLimits {

    public record Policy(
            int maxDepth,
            int maxParts,
            long maxDecodedBytes) {

        public Policy {
            if (maxDepth < 0
                    || maxParts <= 0
                    || maxDecodedBytes <= 0) {
                throw new IllegalArgumentException("Invalid limits");
            }
        }
    }

    private static final class Budget {
        int parts;
        long decodedBytes;
    }

    public static void inspect(Part root, Policy policy)
            throws Exception {
        walk(root, 0, policy, new Budget());
    }

    private static void walk(
            Part part,
            int depth,
            Policy policy,
            Budget budget) throws Exception {

        if (depth > policy.maxDepth()) {
            throw new IllegalArgumentException(
                    "Nested MIME depth exceeded");
        }

        budget.parts++;
        if (budget.parts > policy.maxParts()) {
            throw new IllegalArgumentException(
                    "Too many MIME parts");
        }

        if (part.isMimeType("multipart/*")) {
            Object value = part.getContent();
            if (!(value instanceof Multipart multipart)) {
                throw new IllegalArgumentException(
                        "Malformed multipart content");
            }
            for (int i = 0; i < multipart.getCount(); i++) {
                walk(multipart.getBodyPart(i),
                        depth + 1, policy, budget);
            }
            return;
        }

        if (part.isMimeType("message/rfc822")) {
            Object value = part.getContent();
            if (!(value instanceof Part nested)) {
                throw new IllegalArgumentException(
                        "Malformed nested message");
            }
            walk(nested, depth + 1, policy, budget);
            return;
        }

        try (InputStream stream = part.getInputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                if (count > policy.maxDecodedBytes()
                        - budget.decodedBytes) {
                    throw new IllegalArgumentException(
                            "Decoded MIME size exceeded");
                }
                budget.decodedBytes += count;
                // In production: pass bounded bytes
                // to quarantine/scanner instead of discarding.
            }
        }
    }
}
~~~

This example demonstrates **how to enforce a budget while traversing MIME**; it is not a complete production MIME filter. In practice:

- `getContent()` may already materialize content before guards inspect all parts, depending on provider/implementation.
- Malformed MIME or content not matching expected types may throw `MessagingException` or `IOException`.
- `message/rfc822` can have content representation variants that must follow policy.
- Traversing and re-reading streams a second time for scanning wastes resources and risks TOCTOU; prefer persisting inspected bytes to an immutable object and scanning that exact object.
- Total decoded byte caps do not replace per-attachment size limits and archive decompression limits.
- A scanner cannot inspect bytes once discarded; production code must stream/persist bounded data into isolation.

### Final Gate Before Handing Off to the Business Handler

Never invoke `businessHandler.handle(message)` directly inside the MIME traversal loop. Construct a **normalized data object** from permitted fields only after the entire message and required attachments pass inspection.

## 16. Filenames: A Sender-Supplied String, Not a Trusted Path

Attachment filenames can contain:

- `../` or `..\\` to escape the storage directory.
- Absolute Windows/Unix paths.
- Control characters, NUL, CRLF.
- Unicode confusables and bidirectional characters hiding the real extension.
- Excessively long names or multiple dots.
- Names like `invoice.pdf.exe` masquerading as PDFs.
- Names colliding with other files in quarantine.

Do not do this:

~~~java
// Dangerous: using filename from email directly as path.
Path target = uploadDir.resolve(part.getFileName());
Files.copy(part.getInputStream(), target);
~~~

Instead:

1. Generate a **random/UUID storage key** unrelated to the filename.
2. Store the original filename as normalized/escaped metadata for display if needed.
3. Check the extension allowlist only after normalization.
4. Sniff the content type from actual bytes.
5. Block dangerous characters/paths.
6. Never place files inside a directory served directly by the web app.
7. Use `CREATE_NEW` or an immutable object store to prevent overwrites.

### Never Infer Trust from a Filename

A file named `document.pdf` can be an invalid or malicious document. Storing under a UUID and running malware scans lowers risk, yet a scanner-clean file does not mean every macro/script behavior or content element is safe.

## 17. Allowlisting Attachment Formats by Business Need

Instead of accepting all files and trying to block every dangerous extension, start from **the formats genuinely needed**.

Example for an invoice-receiving flow:

| Format | Allowed? | Additional Checks |
| --- | --- | --- |
| PDF | Yes, if business needs it | Signature, structure, embedded content, scan, page/size limits on extraction |
| PNG/JPEG | Yes, if document photos needed | Sandboxed image decoding, pixel limits, strip unneeded metadata |
| CSV | Yes, if importing data | Encoding, row/column limits, formula injection protection on Excel export |
| XML | Yes, if schema-controlled | Disable external entities/DTD per parser, schema and depth limits |
| Office documents | Only if explicitly approved | Macros, external links, ZIP structure, CDR if needed |
| ZIP/RAR/7z | Only if truly needed | Nesting, file count, decoded size limits, password-encryption policy |
| HTML/SVG | Usually block or handle specially | Scripts, active content, external resources |
| EXE/JAR/SCRIPT | No in normal invoice flows | Never place on an executable system |
| Password-protected files | May block or quarantine | Scanners cannot inspect contents without decrypting |

This is an example policy, not a universal "safe format list". Every business differs; **allowances must be defined per workflow**.

### Comparing Declarations Against Actual Bytes

An inspection chain can look like:

~~~text
Attachment part
  |
  +-- declared Content-Type: application/pdf
  +-- filename extension: .pdf
  +-- actual bytes / parser-detected type
  |
  v
Policy checks consistency and allowed formats
  |
  v
Malware scan + format-specific inspection
  |
  +-- Pass -> release immutable object
  +-- Fail/uncertain -> quarantine
~~~

Never "fix" a mismatched extension by renaming an executable to `.pdf`. When headers/extensions and detected types conflict, handle as suspicious and keep the original in quarantine for investigation.

## 18. Malware Scanning and Scanner Limits

A mail-receiving pipeline may use:

- ClamAV or an internal scanner.
- An ICAP gateway.
- A managed malware scanning service.
- Content Disarm and Reconstruction (CDR) for specific formats.
- Sandboxes for high-risk documents/formats.

Each has different capabilities and limits. **Never treat a "scan clean" label as an absolute guarantee.** Scanners may lack brand-new signatures, fail to open encrypted archives, or misunderstand unusual file structures.

### Modeling Scanner Results

~~~java
public enum MalwareVerdict {
    CLEAN,
    INFECTED,
    SUSPICIOUS,
    UNSCANNABLE,
    ERROR,
    TIMEOUT
}
~~~

A policy might be:

| Verdict | Action |
| --- | --- |
| `CLEAN` | Allow moving to next check; never auto-execute |
| `INFECTED` | Quarantine and block usage |
| `SUSPICIOUS` | Quarantine/review |
| `UNSCANNABLE` | Quarantine; never assume clean |
| `ERROR` | Bounded scan retries; hold temporarily |
| `TIMEOUT` | Hold temporarily; cap retries and alert on spikes |

### Fail Closed for Attachments

If the scanner fails to respond, never auto-release the attachment "to avoid slowing down business". The right state is `SCAN_PENDING` or `QUARANTINED` until a permitted verdict arrives. For flows handling only `text/plain` without saving attachments, policy can reject attachments upfront without downloading/scanning every file type.

### Bind the Verdict to the Exact Bytes

To prevent **TOCTOU** (time-of-check/time-of-use):

1. Store the file in an immutable object or a quarantine area written only once.
2. Compute SHA-256 and version/object ID metadata.
3. Have the scanner read **that exact object/version**.
4. Record the verdict alongside the hash, scanner engine/version, and timestamp.
5. Business handlers read only objects whose hash/version matches the verdict.
6. If a file is replaced, it must be re-scanned.

Never scan a file at path A and later process a different file sharing the same filename. Use immutable storage keys or verify hashes before use.

## 19. Archive Bombs, Encrypted Documents, and Nested Attachments

A tiny ZIP file can decompress to massive sizes; an archive can hold tens of thousands of files or multiple nested archive layers. Safeguards:

- Cap total uncompressed bytes.
- Cap per-file size and total entry count.
- Cap nesting depth.
- Cap compression ratios where appropriate.
- Block `../` paths, absolute paths, and dangerous symlinks.
- Never extract directly into an executable application directory.
- Enforce worker CPU/time/memory/disk quotas.
- Define policies for password-protected archives and encrypted files.

A simpler alternative is **disallowing archives altogether** if the business only needs PDF/JPEG/CSV. Shrinking the attack surface is usually better than trying to support every format.

### Never Extract Files Just to "See What's Inside" in a Web Controller

If extraction is needed, delegate to a bounded sandboxed worker. Web request/IMAP polling threads should quickly stage and leave the task. When an archive bomb is detected, quarantine and record the reason rather than retrying unboundedly with other libraries.

## 20. HTML Email: Displayed Content Can Also Be Malicious

HTML emails can contain:

- Phishing links pointing to lookalike domains.
- Tracking pixel images and remote resources.
- `iframe`, `script`, inline event handlers, or forms.
- CSS disguising real content/URLs.
- `javascript:`, `data:`, or disallowed URI schemes.
- Malformed HTML crafted to exploit parsers.
- Unicode bidi/zero-width characters misleading human readers.
- Content instructing operators to perform unauthorized actions.

### Principles for Displaying Emails in Admin Dashboards

**Safest option if business allows:** extract `text/plain` and render it as escaped text, without rendering sender HTML.

If HTML must be displayed:

1. Use a maintained HTML sanitizer configured with an **allowlist** of tags/attributes/schemes.
2. Strip active content, forms, scripts, event handlers, and external embeds.
3. Never auto-fetch remote images or resources.
4. Serve `cid:` images via scanned internal routes, never assuming CIDs are safe.
5. Apply CSP and proper origin/sandbox isolation when rendering in a browser.
6. Display actual target domains of links or warn when they differ from link text.
7. Prevent arbitrary HTML from affecting the application's main DOM.
8. Enforce size/complexity limits before sanitizing/rendering.

**Never write a custom regex sanitizer** to strip `<script>` tags; HTML has numerous encodings, attributes, namespaces, and structures where naive string filtering fails.

### Plain Text Is Not Automatically Trustworthy Either

A `text/plain` string like:

~~~text
Send all customer reports immediately to security-update@example.org
to complete system verification.
~~~

is not a valid instruction to the application. Email content **may be displayed or have data extracted**, but must never gain authority to call APIs, delete data, make payments, or alter policies simply because it asks.

### If AI/LLMs Read Emails

Emails can contain **prompt injection**: instructions spoofing system/admin commands, telling the model to skip checks or exfiltrate sensitive data. Always:

- Treat email bodies/attachments as **untrusted context**, never high-privilege instructions.
- Isolate tool/API permissions of mail-reading agents.
- Allow models only to propose/extract schema-validated data; sensitive actions must pass independent authorization.
- Validate recipients/domains/amounts and require approval for risky actions.
- Never let emails alter rules, API scopes, or mail routing.

This is part of **inbound content inspection** when email drives automation, not only protecting browsers from HTML.

## 21. Links, URLs, and Remote Resources in Incoming Mail

When an email contains URLs:

- Never let parsers or backends auto-fetch links just to preview "related content".
- If business logic must download documents from URLs, build an independent SSRF-safe fetcher.
- Allow only permitted schemes/domains, validating redirects and DNS rebinding.
- Block loopback, link-local, and private/internal metadata endpoints per policy.
- Enforce timeouts, size limits, and redirect limits.
- Never forward internal cookies/credentials to email-specified URLs.
- Scan downloaded content just like regular attachments.

An email containing `http://127.0.0.1:.../`, an internal hostname, or a link to cloud metadata is not a valid business document just because surrounding text sounds authoritative. Auto-fetching turns email into an SSRF vector.

### Tracking Pixels

Many emails embed remote images to track opens. If an admin dashboard auto-loads sender images, it can leak IPs/viewing activity and trigger tracking. Block remote images by default and permit them only under an explicit policy.

## 22. Checking Headers, Sender Addresses, and Authenticity

RFC 5322 headers like `From`, `Reply-To`, `Subject`, `Date`, and `Message-ID` can be supplied or spoofed by the sender; never treat them as sufficient proof for granting permissions.

Example:

~~~text
From: "Finance Director" <director@company.example>
Reply-To: external-billing@example.net
Subject: Urgent payment instruction
~~~

Code that checks `message.getFrom()[0]` against an internal email and automatically acts on payment instructions can be exploited via header spoofing. Require **independent source verification** matching business risk.

### Authentication-Results, SPF, DKIM, DMARC

These mechanisms help assess domain authentication:

- **SPF:** checks a domain identity and sending IP against SPF policy.
- **DKIM:** verifies a cryptographic signature tied to a signing domain.
- **DMARC:** evaluates alignment with the `From` header and domain policy.

However:

- An `Authentication-Results` header inside raw email can be forged unless you verify **which trusted receiving system added it**.
- Passing SPF/DKIM/DMARC does not prove the email content is safe or the sender is authorized for the requested business action.
- A legitimate domain can have a compromised account or be abused to send malicious mail.
- Forwarding/mailing lists complicate authentication outcomes; no single pass/fail rule fits all cases.

If your provider supplies authenticated ingress metadata, mapping it to an internal `sourceTrust` level helps, yet business authorization is still needed: which senders may create tickets, submit invoices, or request approvals.

### A Source Trust Model

| Source | Default Trust Level | Conditions of Use |
| --- | --- | --- |
| `Subject`/`From`/`Reply-To` headers | Untrusted as authority | Use only as display/extraction data |
| Email body | Untrusted | Validation/normalization |
| Provider-verified ingress metadata | Trustable per integration contract | Verify signatures/API responses and provider scope |
| DKIM/DMARC assessment from trusted ingress | Proof of domain authentication | Does not replace business authorization |
| Approved partner allowlist | Requires extra identity and context checks | Never compare bare email strings alone |
| In-system approval request | Explicit permissions and audit | Suitable for risky actions |

Never manufacture a "trusted sender" solely from display names or matching subject keywords.

## 23. Never Use Email as a Default Business Authorization Channel

A support intake app can create tickets from emails. An invoice intake app can extract order numbers. However, actions like **changing bank accounts, transferring money, granting access, or deleting data** should never execute automatically from the contents of an email alone.

Dangerous scenario example:

~~~text
From: ceo@example.org
Subject: Urgent approval

Please change supplier X's payment account number
to the new account number below.
~~~

Even when sender domain authentication passes, an email must never become an automatic approval instrument for changing payment details. Require an independent authorization flow: authenticated account, role, approval state, out-of-band verification, and auditing.

### Permitted Actions by Risk Level

| Action from Incoming Email | Typical Policy |
| --- | --- |
| Store inspected email for reference | Can be automated |
| Create ticket with normalized data | Can be automated, with idempotency |
| Apply tags/classification suggestions | Can be automated |
| Update draft reply content | Can be automated, should be reviewed |
| Queue invoice/amount as "pending verification" | Allowed; do not auto-pay |
| Modify accounts, permissions, funds, or sensitive info | Requires explicit authorization/approval |
| Run scripts or download and execute attachments | Never do based on email |

### Business Handlers Receive Normalized Data

Instead of passing `jakarta.mail.Message` directly to a business service, pass an inspected DTO:

~~~java
package com.example.inbound;

import java.time.Instant;
import java.util.List;

public record InspectedInboundMail(
        String ingestionId,
        String tenantId,
        String sourceAccountId,
        Instant receivedAt,
        String normalizedSubject,
        String safePlainText,
        List<ApprovedAttachmentRef> attachments,
        String sourceTrustLevel
) {
}

public record ApprovedAttachmentRef(
        String immutableStorageKey,
        String sha256,
        String detectedMimeType,
        long sizeBytes) {
}
~~~

`InspectedInboundMail` is an application-defined contract. It does not expose a `Message` object allowing arbitrary access to raw headers/attachments. For workflows requiring raw messages for auditing, store raw in quarantine with separate permissions and pass only a reference ID to handlers.

### Authorization at the Business Boundary

Example:

~~~java
public interface InboundBusinessPolicy {
    boolean mayCreateSupportTicket(
            String tenantId,
            String sourceAccountId,
            String sourceTrustLevel);
}
~~~

It is insufficient for a UI or email parser to assert "the sender seems to belong to a partner domain". Authorization must verify the actual account/tenant/workflow, and action handlers must run with least-privilege service identities.

## 24. Extracted Data Must Also Be Validated

An email may contain business fields:

~~~text
Order-ID: 1842
Invoice-Amount: 1000000
Currency: VND
Payment-Account: ...
~~~

Do not:

- Concatenate email values directly into SQL strings.
- Pass them into shell commands or file paths.
- Render them as unescaped HTML.
- Trust amounts or payment destinations without reconciliation.
- Assign a ticket to a tenant based solely on a self-declared ID inside the email.

### A Sound Data Ingestion Pipeline

~~~text
Safe text extraction
    |
    v
Schema validation
    |
    v
Field normalization
    |
    v
Business authorization and ownership checks
    |
    v
Idempotent persistence
    |
    v
Manual approval if risk requires it
~~~

**Schema validation** checks data shape (type, length, format, enums); **business authorization** checks whether that person/source is permitted to make the corresponding change. Neither replaces the other.

### CSV/Excel Formula Injection

If an attached CSV file is parsed and later exported to spreadsheets, values starting with formula characters can be interpreted as executable formulas by spreadsheet software depending on settings. Sanitize or neutralize formulas according to data import/export rules rather than writing untrusted input directly as executable worksheet formulas.

### XML External Entities

If emails carry XML and the app uses an XML parser, configure the parser to disable external entities/DTDs per security best practices to prevent local file reads or SSRF. Never assume an `.xml` file that passed malware scanning is safe for a default XML parser.

### PDF/Office Extraction

Extracting text from PDFs or Office documents should run in a worker with time/memory quotas; document parsers can also encounter malformed files or exploit attempts. Never parse untrusted documents inside a process holding database admin credentials or secret-store access.

## 25. Limiting Headers and Metadata

Email headers go beyond familiar fields. A message can contain huge numbers of header lines, repeated headers, overly long subjects, complex encoded-words, or malformed addresses.

Limits to enforce:

- Total header count and total header bytes, when measurable at ingress/parser.
- Decoded sizes of `Subject`/`From`/`Reply-To`.
- Number of `To`/`Cc`/`Bcc` addresses appropriate to business logic.
- Lengths of `Message-ID` and `References`.
- Reply chain / nested message depth if applicable.
- Number of MIME boundaries and body parts.
- Policy for unparseable or abnormally duplicated headers.

Never write a custom RFC 5322/MIME parser using `split("\\r\\n")` assuming each header occupies one line. Headers have line folding, encodings, and many edge cases. Use Jakarta Mail or an up-to-date specialized library, then enforce application limits.

### Header Injection When Sending Reply Notifications

If the app auto-generates outbound emails using inbound `Subject`/`Reply-To`, prevent header injection and use validating email APIs:

- Never concatenate raw `Subject:` into SMTP transcripts.
- Reject arbitrary CRLF in addresses/header values.
- Validate `Reply-To` against policy before sending.
- Cap recipient counts and never send to attacker-supplied lists.

Using `MimeMessageHelper` properly avoids some manual MIME bugs, yet does not replace validation and authorization.

## 26. Auto-Replies and Email Loops

A mail-receiving flow might auto-send a confirmation "Your request has been received". Prevent loops:

~~~text
System A auto-replies to System B
    |
    v
System B auto-replies to System A
    |
    v
Infinite reply loop
~~~

Before auto-replying:

- Verify the request belongs to an eligible category.
- Never reply to bulk mailings, automated reports, or bounces.
- Check standard signals like `Auto-Submitted` (appropriately), without treating any single header as infallible proof.
- Never reply to bounce/null reverse-path addresses in a way that creates loops.
- Apply rate limits per sender, conversation, and tenant.
- Set `Auto-Submitted` appropriately on automated messages sent by your app if needed.
- Record an idempotency key so an IMAP poller re-processing a message never sends duplicate auto-replies.

Never attach files or quote raw inbound content in replies if doing so could leak sensitive data.

## 27. Distinguishing Support Emails from Control-Command Emails

A `support@example.org` address may accept mail from anyone. An address receiving machine reports should restrict senders/partners and schemas. The two have different trust models:

| Flow | Expected Source | Handling |
| --- | --- | --- |
| Support mailbox | Public, arbitrary senders | Create unprivileged tickets, anti-spam, attachment quarantine |
| Invoice mailbox | Registered partners | Verify partner identity, PO/invoice mapping, approval |
| Automated monitoring inbox | Internal systems | Prefer authenticated APIs/events over email when possible |
| HR/application mailbox | Sensitive PII | Strict mailbox permissions/retention, controlled document handling |
| Security report mailbox | High-risk content | Sandbox, quarantine, never auto-execute instructions |

### Email Is Not a Strongly Authenticated Internal Command Channel

If sensitive jobs must be triggered, prefer authenticated/authorized, audited APIs. Email can act as a **request data source**, not a command execution channel running with service-account privileges capable of mutating every system.

## 28. Data Authorization After Receiving Mail

Once a message lands in staging, access must stay restricted. Otherwise, you protect the mailbox only to copy all emails into an object store readable by every service.

Permission layers:

1. **Mailbox identity:** reads only the designated mailbox/folder.
2. **Ingestion worker:** writes only to that tenant's staging and ledger.
3. **Inspection worker:** reads only isolated objects and writes verdicts.
4. **Business processor:** reads only released data, lacking access to all raw attachments.
5. **Operator:** views sanitized metadata/diagnostics; raw mail requires special privileges.
6. **Retention worker:** deletes per audited policy, separate from business handler permissions.

### Partitioning by Tenant

A `storageKey` must be bound to `tenantId` in the database and checked on every read. Do not rely solely on path prefixes like `tenant-a/` if an endpoint can be called with another tenant's `storageKey`; enforce authorization in API/storage policies.

### Encryption and Data Lifecycle

Raw emails and attachments can contain PII, contracts, account numbers, or other personal data. Require:

- Encryption in transit and at rest per policy.
- Access control and auditing on raw mail access.
- Separate retention for raw staging, quarantine, and extracted business data.
- Deletion or legal-hold mechanisms per applicable regulations.
- Controls over backups, snapshots, and diagnostic dumps.
- Never exposing raw MIME in HTTP errors or APM traces.

### Avoid Storing Attachments in the Database Unnecessarily

An application can store hashes/object keys and metadata in the database while keeping binary blobs in isolated object storage. Storage choice depends on transactional needs, sizes, and architecture. Crucially, never use an unpermissioned store to "temporarily hold" attachments before scanning.

## 29. Processing Idempotency: Incoming Mail Can Be Read Multiple Times

Common duplicate scenarios:

- Worker crashes after staging but before writing `PROCESSED`.
- IMAP poller restarts and re-scans UIDs.
- Provider webhook redelivers.
- `UIDVALIDITY` changes, forcing a folder rescan.
- User moves a message to another folder and back.
- Two instances both receive a "new mail" event.
- A sender genuinely sends two emails with the same `Message-ID`.

Therefore distinguish:

- **Ingestion identity:** source record (account/folder/`UIDVALIDITY`/UID).
- **Raw content hash:** aids verification, not a business unique key.
- **Business idempotency key:** e.g., partner + invoice number + verified account + tenant, or authenticated upstream event ID.

Do not deduplicate all emails solely by body hash: two identical messages can be two valid requests. Conversely, relying solely on RFC `Message-ID` risks spoofing or collisions; design per business semantics.

### Illustrative Database Constraint

~~~sql
CREATE TABLE inbound_mail_ledger (
    id                   VARCHAR(100) PRIMARY KEY,
    tenant_id            VARCHAR(100) NOT NULL,
    account_id           VARCHAR(100) NOT NULL,
    folder_key           VARCHAR(250) NOT NULL,
    uid_validity         BIGINT NOT NULL,
    uid                  BIGINT NOT NULL,
    status               VARCHAR(40) NOT NULL,
    storage_key          VARCHAR(500),
    sha256               VARCHAR(64),
    attempts             INTEGER NOT NULL DEFAULT 0,
    next_attempt_at      TIMESTAMP,
    created_at           TIMESTAMP NOT NULL,
    updated_at           TIMESTAMP NOT NULL,
    UNIQUE (tenant_id, account_id, folder_key,
            uid_validity, uid)
);
~~~

Simplified schema: add leases/versions, indexes, retention, failure classification, auditing, and database-specific constraints. When UID is unavailable or using POP3/APIs, pick a source-compatible key instead of fabricating dummy UIDs.

### Never Use Sequence Numbers as Unique Keys

IMAP `Message.getMessageNumber()` is a shifting position in the folder. If the first message is expunged, messages 2, 3, and 4 can shift to 1, 2, and 3; checkpointing by sequence number will bind the wrong content.

### Atomic Claims and Side Effects

Two workers reading the same staging record must claim transactionally (optimistic CAS/leases/row locking), and business handlers must be idempotent when calling external services. A unique key on the ledger prevents double-ingesting one source, yet **does not automatically create exactly-once side effects** if a worker dies after calling an external API before committing.

## 30. Retry Workflows When Incoming Mail Fails

Not all mail-reading errors should be retried the same way.

| Error Category | Example | Appropriate Action |
| --- | --- | --- |
| Transient connectivity | DNS/IMAP server outage/read timeout | Retry fetch with backoff/jitter |
| Rejected credentials | Revoked OAuth2 token / IMAP AUTH fail | Pause account, alert, avoid login storm |
| UID no longer exists | Message deleted/moved | Reconcile; never bind to another message |
| Oversized raw message | Exceeds hard limit | Reject/quarantine per policy; do not re-download |
| Malformed MIME | Parser cannot understand structure | Quarantine with reason; do not retry infinitely |
| Infected attachment | Scanner detected malware | Quarantine, block release |
| Scanner timeout/outage | Verdict unavailable | Retry inspection; keep object isolated |
| Invalid business input | Missing invoice ID / bad schema | Hold/review or reject per business rules |
| Transient downstream DB error | Transaction failed to commit | Retry business processing idempotently |
| Permission denied | Worker cannot read folder | Fix IAM/ACL; never try admin account |
| Email already processed | Duplicate unique key | Skip or reconcile state |

### Exponential Backoff and Budgets

When IMAP/providers are temporarily unavailable, use jittered backoff and concurrency caps. Never let every message trigger a continuous reconnect/login loop. For scanner outages, retry scanning **against the staged object** without re-fetching from the mailbox.

### Poison Messages

A malformed MIME message can cause the parser to throw on every run. If the worker keeps hitting the same first message and halting, the whole mailbox stalls. Always:

1. Count attempts per ingestion record.
2. Classify permanent vs. transient errors.
3. Quarantine failing records after threshold or once confirmed unparseable.
4. Continue processing other messages in the batch.
5. Alert when quarantine counts rise.

Never "skip" by deleting the original message from the mailbox without proper authorization or when evidence must be preserved for investigation.

## 31. Spring Integration Mail: Convenient, but Does Not Bypass Permissions and Checks

If the system uses **Spring Integration**, inbound mail receivers/pollers or IMAP IDLE adapters can bring messages into an integration flow. These adapters orchestrate connectivity and message delivery, yet **do not automatically make emails trustworthy data**.

When designing the flow:

~~~text
Mail inbound adapter (IMAP/POP3)
        |
        v
Authenticated mailbox/source metadata
        |
        v
Inbound staging handler
        |
        v
Asynchronous inspection + quarantine gate
        |
        v
Validated event channel
        |
        v
Business service
~~~

Verify against your **exact Spring Integration version**:

- Which protocols/URL schemes, connection properties, and TLS settings the receiver supports.
- Whether the adapter uses polling or IMAP IDLE and how it reconnects on network errors.
- Options for auto-closing folders, fetching/marking seen, and message conversion.
- Whether message payloads are raw `MimeMessage`, `Message`, or another wrapper.
- Whether filter/duplicate logic runs before or after fetching the body.
- Backpressure, error channels, and transaction boundaries.
- Behavior if the application crashes while processing an event.

Never assume a message is durably "acked" simply because an adapter placed it onto an in-memory channel. If business handlers require survival across restarts, persist a staging/outbox-style ledger before acknowledging the source per contract.

### IMAP IDLE Is Not Exactly-Once

IDLE can deliver new-mail signals faster than polling, yet connections can drop and notifications can duplicate or vanish during reconnects. You still need UID/cursor reconciliation and an idempotent ledger to catch incomplete messages.

### Error Channels Do Not Replace Quarantine

A MIME parse error can be routed to an error channel, yet without quarantine workflows and durable state, the app may keep hitting the same error or drop messages. Preserve source IDs, reasons, and processing state.

## 32. Receiving Mail via Webhooks/APIs Also Requires Least Privilege

Some providers offer inbound email parsing APIs or webhooks sending raw messages/parsed attachments. Instead of IMAP credentials, the app must protect:

- Webhook endpoints over HTTPS.
- Provider signatures or authentication.
- Raw request bodies per signature verification rules.
- Timestamp/replay defenses when supported by the provider.
- Request body size, attachment counts, and total decoded bytes.
- Provider account/tenant scopes.
- Inbound event IDs and deduplication.
- Object storage URLs/credentials returned by the provider.

**Never trust an HTTP POST with provider-event-like JSON** before verifying the source. An attacker can send a payload pointing an attachment URL at an internal endpoint, causing SSRF or triggering processing under the wrong tenant.

### Acknowledge After Durable Persistence

If the provider redelivers webhooks when not receiving 2xx:

1. Verify signature.
2. Validate envelope/body size.
3. Persist the event or enqueue into a durable queue.
4. Return a success ack only after durable storage succeeds.
5. Process in consumers using an idempotency key.

Never return 200 while holding the payload only in memory if the process could crash before persisting.

### Provider-Supplied Attachment Download URLs

A URL sent by a provider via webhook is not inherently safe if the webhook is unauthenticated or the URL lacks domain restrictions. If downloading from a provider storage API, use a properly configured SDK/API client, verify resource IDs, restrict redirects, and cap bytes. Never treat arbitrary URLs from email bodies as provider attachment URLs.

## 33. Testing Mailbox Security and Access Permissions

A test suite must prove **both functionality and permissions**. Requirements:

| ID | Scenario | Expected Outcome |
| --- | --- | --- |
| P01 | Read-only credential opens INBOX | Reads permitted metadata/messages |
| P02 | Read-only credential attempts delete/expunge | Server rejects or permissions blocked per policy |
| P03 | Credential attempts access to disallowed folder | Blocked at server/API level |
| P04 | Credential reads another tenant's mailbox | Denied |
| P05 | Worker uses account without send permission | Cannot send mail per provider policy |
| P06 | OAuth2 token expires | Refreshes via proper flow or pauses; never logs token |
| P07 | Token is revoked | No infinite login/retry loop |
| P08 | TLS certificate hostname mismatch | Does not connect via trust-all |
| P09 | IMAP server read timeout | Retries with backoff; ledger does not mark `PROCESSED` |
| P10 | `UIDVALIDITY` changes | Old checkpoint not misused |
| P11 | Message sequence shifts due to expunge | Does not misprocess another UID |
| P12 | Two workers poll the same UID | One staging logical record |
| P13 | Worker crashes before staging commit | Can re-fetch without losing message |
| P14 | Worker crashes after business commit | Idempotency prevents double side effects |
| P15 | `Folder.READ_ONLY` | Does not mutate flags unexpectedly |
| P16 | Spoofed `From` header | Does not bypass business authorization |
| P17 | Email with fake `Authentication-Results` | Not treated as trusted ingress |
| P18 | Auto-reply to another auto-reply | Does not create a loop |

**Never test `Folder.READ_ONLY` solely with mocks** and declare server ACLs secure. Write tests against a mail server/provider test identity with genuinely restricted permissions or an equivalent staging environment.

### Testing in an Isolated Environment

Use GreenMail or a test IMAP/SMTP server capable of creating mailboxes/messages to test fetching, MIME, and error handling. However, recognize test servers may not fully emulate OAuth2, provider-specific ACLs, or quotas. For those provider-specific traits, use an authorized staging tenant and synthetic data.

Never access real employees' or customers' mailboxes to intentionally provoke delete/expunge/permission-denied failures.

## 34. Inbound Email Content Test Matrix

| ID | Scenario | Expected Behavior |
| --- | --- | --- |
| C01 | Normal plain-text message | Extracts data, commits once |
| C02 | HTML-only message | Not rendered directly into main DOM |
| C03 | Multipart alternative text + HTML | Picks content per policy; never duplicates side effects |
| C04 | Multipart nested past depth limit | `QUARANTINED`/`REJECTED` |
| C05 | MIME parts exceed limit | Does not parse unboundedly |
| C06 | Message size exceeds raw limit | Rejects staging/inspection without OOM |
| C07 | Declared size small, actual exceeds limit | Bounded stream blocks it |
| C08 | Decoded content exceeds limit | Blocked despite small raw size |
| C09 | Attachment filename has `../` | Never writes outside quarantine |
| C10 | Filename has Unicode bidi/control chars | Normalized/flagged per policy |
| C11 | `.pdf` file with non-PDF bytes | Detected type mismatch, quarantined |
| C12 | EICAR test pattern allowed by scanner | Verdict `INFECTED` and never released |
| C13 | Scanner timeout | Remains in quarantine; bounded retries |
| C14 | Scanner error/unsupported | Never auto-marked `CLEAN` |
| C15 | ZIP with tens of thousands of entries | Entry limit blocks it |
| C16 | ZIP bomb / deep nesting | Resource/expansion limits block it |
| C17 | Encrypted unscannable file | `UNSCANNABLE` per policy |
| C18 | HTML with scripts/event handlers | Sanitizer strips active content or displays text only |
| C19 | HTML with remote images | Does not auto-fetch remote content |
| C20 | Link pointing to localhost/metadata endpoint | No SSRF fetch |
| C21 | Spoofed "admin demands running command" mail | Does not execute unauthorized action |
| C22 | CSV containing formula-like values | Export/import handled as plain data |
| C23 | XML with external entities | Parser accesses no local files/internal URLs |
| C24 | Malformed PDF | Sandboxed/timed-out parser, quarantined if needed |
| C25 | Abnormally long header | Limit blocks or handles safely |
| C26 | Duplicate `Message-ID` | Does not wrongly merge two source records |
| C27 | Same UID, different `UIDVALIDITY` | Ledger distinguishes properly |
| C28 | Message already `\Seen` earlier | Not skipped if not yet `STAGED` |
| C29 | MIME filename/body contains PII | Never leaked in metrics/logs |
| C30 | Business handler fails after inspection | Idempotent retry without re-fetching/re-scanning endlessly |

These scenarios are **tests to execute**, not proof they have already run. Security tests should use safe fixture files and scanner/sandbox test suites; never bring uncontrolled live malware onto developer machines or shared CI.

### Testing the Scanner Without Real Malware

Mock `MalwareScanner` to return `INFECTED`/`ERROR`/`TIMEOUT` for workflow tests. When integrating a real scanner, use the test pattern/signature officially permitted by the tool inside an isolated environment. The goal is verifying quarantine states and fail-closed behavior, not crafting real malware.

## 35. Unit Testing Policy: Unscanned Mail Never Enters Business Logic

A gate class can be defined as:

~~~java
package com.example.inbound;

public enum InspectionState {
    NOT_STARTED,
    SCANNING,
    CLEAN_AND_VALIDATED,
    REJECTED,
    QUARANTINED,
    SCANNER_ERROR
}

public final class ProcessingGate {
    public boolean mayProcess(
            InspectionState state,
            boolean sourceAuthorized,
            boolean limitsSatisfied) {

        return state == InspectionState.CLEAN_AND_VALIDATED
                && sourceAuthorized
                && limitsSatisfied;
    }
}
~~~

JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ProcessingGateTest {

    private final ProcessingGate gate = new ProcessingGate();

    @Test
    void onlyValidatedMessageIsReleased() {
        assertTrue(gate.mayProcess(
                InspectionState.CLEAN_AND_VALIDATED,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.SCANNING,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.SCANNER_ERROR,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.QUARANTINED,
                true, true));

        assertFalse(gate.mayProcess(
                InspectionState.CLEAN_AND_VALIDATED,
                false, true));

        assertFalse(gate.mayProcess(
                InspectionState.CLEAN_AND_VALIDATED,
                true, false));
    }
}
~~~

This test only verifies gate logic. A real system must enforce **verdicts bound to immutable objects/hashes**, transaction states, and races between scanners/processors. Never rely solely on a boolean passed from a controller or client to permit processing.

## 36. Testing Races Between Scanning and Attachment Usage

A TOCTOU bug can occur:

~~~text
Scanner validates object X at version 1
             |
             v
Database says CLEAN
             |
             v
Another process overwrites object X with version 2
             |
             v
Business handler reads version 2 without re-scan
~~~

Tests must prove:

- Staged objects are immutable or versioned.
- Verdicts record the hash/version of the scanned object.
- Handlers require the exact matching hash/version.
- Modified objects or mismatched hashes are never released.
- Quarantine write permissions differ from business handler read permissions.

A post-scan filename extension check cannot replace this invariant.

## 37. Monitoring and Alerting for Mail-Receiving Systems

An application may connect to IMAP successfully yet fail to process any emails—for instance, due to a scanner outage or a poison message at the head of the queue. Thus monitoring must track **connectivity, staging, inspection, and business outcomes**.

| Suggested Metric | Meaning |
| --- | --- |
| `inbound_mail_poll_total` | Poll count by account/folder |
| `inbound_mail_poll_failures_total` | Poll errors by DNS/auth/TLS/timeout |
| `inbound_mail_fetch_total` | Messages fetched |
| `inbound_mail_staged_total` | Messages durably persisted |
| `inbound_mail_stage_failures_total` | Staging failure count |
| `inbound_mail_duplicate_total` | Source messages already in ledger |
| `inbound_mail_oversized_total` | Messages exceeding raw/decoded size limits |
| `inbound_mail_mime_rejected_total` | MIME depth/parts/format failures |
| `inbound_mail_attachment_rejected_total` | Attachments disallowed by policy |
| `inbound_mail_scans_total` | Scan count by verdict |
| `inbound_mail_quarantined_total` | Quarantined messages/files |
| `inbound_mail_processing_success_total` | Business handler commits succeeded |
| `inbound_mail_processing_failures_total` | Business failures by reason |
| `inbound_mail_pending_age_seconds` | Age of pending records |
| `inbound_mail_scanner_latency_seconds` | Scanner latency |
| `inbound_mail_provider_auth_failures_total` | Mailbox authentication errors |
| `inbound_mail_storage_bytes` | Staging/quarantine storage usage |
| `inbound_mail_lease_expirations_total` | Worker lease expirations |

Metric names are **application-implemented examples**, not built-in Spring Mail metrics. Use Micrometer/Spring Boot Actuator or an equivalent observability stack, while bounding label cardinality and access control.

### Reasonable Labels

- Non-sensitive account key.
- Folder type or group, avoiding raw folder names containing PII when unnecessary.
- Tenant group or region per policy.
- Failure category.
- MIME verdict/reason family.
- Processor type.

Avoid using full email addresses, UIDs, `Message-ID`s, subjects, attachment filenames, or object storage keys as Prometheus labels. They can contain personal data and cause unbounded metric cardinality.

### Actionable Alerts

| Signal | Likely Cause | Action |
| --- | --- | --- |
| Rising IMAP authentication failures | Expired token, revoked credentials, policy change | Halt login storm; inspect identity |
| Poll succeeds, staging count stays 0 abnormally | Wrong cursor/UID check, empty folder, filter bug | Check checkpoint and mailbox |
| Rising pending age | Consumer/scanner/DB issue | Investigate bottleneck; scale/tune safely |
| Quarantine spike | Malicious mail wave, parser regression, policy shift | Inspect source, reasons, safe samples |
| Rising scanner timeouts | Scanner overloaded/down | Keep quarantined; scale capacity |
| Raw storage full | Broken retention/cleanup or traffic spike | Throttle ingestion; protect source and disk |
| Rising MIME parse failures | Poison-message campaign or dependency bug | Cap sizes; test isolated fixtures |
| `UIDVALIDITY` changes | Mailbox reset/migration | Reconcile and reset checkpoint safely |
| High duplicate attempts | Poller race, worker restarts | Inspect leases/idempotency |
| Cross-tenant access denied | Authorization bug or attack | Investigate security and metadata |

### Do Not Close an Incident Just Because Error Logs Stopped

If a scanner outage holds every attachment, the IMAP poller may stop throwing exceptions while **the business backlog keeps growing**. Recovery criteria must include declining pending age, restored staging/inspection/processing throughput, intact tenant isolation, and zero dropped records.

## 38. Structured Logging Without Leaking Email Contents

Sample log:

~~~json
{
  "event": "inbound_mail_inspection",
  "ingestionId": "inbound-582",
  "accountKey": "support-mailbox",
  "folderKey": "INBOX",
  "status": "QUARANTINED",
  "reasonFamily": "DISALLOWED_ATTACHMENT_TYPE",
  "attachmentCount": 1,
  "sourceTrust": "UNVERIFIED"
}
~~~

Never log:

- Full `Subject`, body, or raw headers.
- Full recipient/sender addresses unless strictly required.
- OAuth access/refresh tokens, IMAP passwords, or connection URLs containing credentials.
- Attachment contents, sensitive filenames, or raw scanner signatures.
- Verification links, password resets, OTPs, or secrets inside emails.

If raw messages are needed for incident analysis, keep them in permissioned/retention-governed quarantine and log only the reference ID. For forensic access, audit who accessed them and why.

## 39. Runbook: IMAP Cannot Read the Mailbox

When the poller loses connectivity:

1. Identify whether the failure is DNS, TCP, TLS, authentication, folder permissions, or provider throttling.
2. Check account key, host, port, protocol, and TLS mode **without printing credentials**.
3. Check recent secret rotations, OAuth token expiry, and read permissions.
4. Determine whether all pods fail or only one network zone.
5. Never continuously retry logins with invalid credentials.
6. Never fall back to an admin account or personal mailbox to "read instead".
7. Keep ledger/cursors in a safe state; never mark emails processed.
8. Recover with one read-only canary before reopening all pollers.
9. Poll/scan backlog in batches within rate limits.
10. Reconcile UID/`UIDVALIDITY`, process pending messages, and verify lag.

### When the Provider Changes Access Permissions

If an app previously had mailbox read access and hits permission denied after a migration:

- Check provider scopes/grants and resource ACLs.
- Request only the needed permissions, never full tenant/domain privileges.
- Audit access changes.
- Verify send/delete permissions were not accidentally granted.
- Retest with the least-privileged identity before rolling out.

### When the TLS Handshake Fails

Inspect the certificate chain, hostname/SANs, Java truststore, TLS mode, and system clock. Never disable certificate verification to recover.

## 40. Runbook: One Email Causes Repeated MIME Errors

Symptom:

~~~text
mailbox has 200 messages
processor repeatedly fails at UID 8521
pending age keeps increasing
other messages do not progress
~~~

Remediation:

1. Identify `ingestionId` and the failing message's account/folder/UID.
2. Check error category: oversized, malformed MIME, scanner error, or unsupported file.
3. Never open the attachment on the on-call engineer's desktop for a "quick check".
4. Move the message to quarantine/failed state per policy.
5. Keep the object under strict permissions and retention.
6. Let the poller/consumer proceed to other UIDs.
7. Build a sanitized fixture to reproduce the parser bug if needed.
8. After fixing, replay the exact staging object or re-fetch safely without resetting the whole mailbox.

### Never Let a Poison Message Monopolize All Workers

If a parse-failing message retries immediately every time, the queue stalls. Use backoff, dead-letter/quarantine, retry budgets, and fair scheduling so other emails continue moving.

## 41. Runbook: Infected or Suspicious Attachment Detected

When the scanner returns `INFECTED`/`SUSPICIOUS`:

1. Bind the verdict to the scanned hash/object version.
2. Block releasing the attachment to business processors and normal download UIs.
3. Never extract/run the file in an environment with access to production secrets.
4. Record a sanitized reason/code and alert by severity.
5. Inspect source mailbox, related message count, and tenant scope.
6. Check whether an identical hash was released earlier; if so, run incident response per policy.
7. Delete or retain in quarantine per retention; never forward suspicious files via another email.
8. Review detection logic to reduce false positives without bypassing scans.

If the scanner is **unavailable** or returns **unscannable**, that is not a `CLEAN` verdict. Hold temporarily and retry or review according to risk.

### Never Open Files Manually with Office Software

Double-clicking on an engineer's machine can trigger macros, active content, or exploits. When content inspection is required, use a sandboxed/isolated viewer and an approved incident-response workflow.

## 42. Runbook: Suspected Mailbox Access Compromise

An ingestion account may have leaked credentials or tokens. Steps:

1. Trigger the security incident process and document account scope.
2. Identify the mailboxes/folders and actual permissions of the affected credential.
3. Revoke/rotate secrets or tokens according to urgency.
4. Inspect provider audit logs for logins, reads, moves, deletes, forwarding rules, and permission changes if available.
5. Check whether ingestion was disrupted or messages were missed.
6. Re-grant **least privilege**, never broadening permissions just to "get it running again".
7. Roll out the new connection identity and verify read-only behavior.
8. Reconcile checkpoints, ledger entries, and staged messages.
9. Audit logs/CI/tickets to eliminate the credential leak source.
10. Fulfill security/personal-data obligations per organizational policy if applicable.

Even read-only credentials carry **mailbox data-exposure risks**. Never dismiss an incident as harmless merely because the attacker could not send or delete emails.

## 43. Common Mistakes

### 43.1. Using a Personal Account with Full-Mailbox Permissions

Expands data exposure and blast radius if secrets leak. Use a dedicated service mailbox/identity with minimal scope.

### 43.2. Opening READ_ONLY and Assuming Least Privilege Is Achieved

Client mode does not replace provider ACLs. Credentials may still permit deleting or reading other folders.

### 43.3. Using Message-ID as the Sole Unique Key

`Message-ID` is sender-supplied and can be missing/duplicated/spoofed. Use an appropriate source identity such as account/folder/`UIDVALIDITY`/UID for IMAP, paired with business idempotency.

### 43.4. Polling Only UNSEEN

Another client or fetch operation can flip messages to Seen before business processing commits. Use a durable ledger/cursor.

### 43.5. Using Message Sequence Numbers as Checkpoints

Sequences shift when a mailbox expunges or modifies messages. Use UIDs within `UIDVALIDITY` scope.

### 43.6. Trusting Message.getSize() as a Physical Limit

Size can be absent or fail to reflect decoded payloads. Enforce actual byte limits, gateway quotas, and worker resource caps.

### 43.7. Trusting Content-Type and Filenames

Sender declarations are not proof of format. Sniff actual content and scan per policy.

### 43.8. Placing Attachments into a Public Directory Before Scanning

An uninspected file can be downloaded or executed by others. Store in non-public quarantine first and release only after meeting all criteria.

### 43.9. Treating Scanner Failures as Clean

`ERROR`/`TIMEOUT`/`UNSCANNABLE` is not `CLEAN`. Hold in quarantine with bounded retries.

### 43.10. Capping Only Compressed Size

Archive bombs can be small compressed yet massive when extracted. Cap uncompressed bytes, entry counts, nesting, and worker resources.

### 43.11. Rendering Raw HTML in Dashboards

Risks XSS, active content, and tracking. Display plain text or use controlled sanitization + isolation.

### 43.12. Having the Backend Auto-Fetch Every Link in Emails

Risks SSRF or leaking credentials to external servers. Fetch only for approved use cases through a safe fetcher.

### 43.13. Trusting From/Reply-To as Authenticated Users

Headers are easily spoofed; even domain authentication results do not replace business authorization.

### 43.14. Automatically Obeying Instructions Inside Emails

Email content must not authorize modifying data, wiring funds, or running commands. Separate data extraction from action execution.

### 43.15. Running Scanners and Business Handlers Inside the IMAP Poll Thread

Workers can block for long durations, drop connections, or miss new mail. Separate durable staging from asynchronous processing.

### 43.16. Using One Cross-Tenant Token for All Customers

Violates least privilege and enlarges blast radius. Partition identities/accounts wherever possible.

### 43.17. Leaving Raw Storage/Quarantine Unbounded

A spam wave can fill the disk. Enforce quotas, retention, backpressure, and alerts.

### 43.18. Skipping Permission Checks When Reading Scanned Objects

A storage key from tenant A must never be readable by tenant B even if `CLEAN`. Malware scanning and authorization are two independent requirements.

### 43.19. Logging Raw MIME

Emails can hold personal data, tokens, and attachments. Log only necessary metadata with redaction and access controls.

### 43.20. Auto-Deleting Original Emails When Handlers Fail

Can cause unrecoverable data loss. Only move/delete after staging/processing is confirmed and under an explicitly approved permissioned workflow.

## 44. Checklist for Deploying a Secure Mail-Receiving System

### Permissions and Connectivity

- [ ] Use a dedicated service account/mailbox.
- [ ] Grant read access only to required folders/mailboxes when supported by provider.
- [ ] Separate mail-reading credentials from sending/data-mutation credentials.
- [ ] Avoid overly broad domain-wide delegation when unneeded.
- [ ] Store credentials/tokens in a secret manager with rotation and auditing.
- [ ] Enable TLS and hostname verification per protocol.
- [ ] Configure connect/read/write timeouts, connection caps, and retries.
- [ ] Never fall back to weaker authentication when OAuth/tokens fail.
- [ ] Verify permissions via **server ACLs**, not merely client `READ_ONLY`.

### Ingestion and Idempotency

- [ ] Traverse only permitted folders.
- [ ] Use UID/`UIDVALIDITY` or appropriate provider event IDs as source identities.
- [ ] Never use message sequence numbers or RFC `Message-ID` as sole unique keys.
- [ ] Implement checkpoints, batch limits, and reconciliation on `UIDVALIDITY` changes.
- [ ] Never use `\Seen` as the sole durable acknowledgment.
- [ ] Persist staging durably before processing and before moving/deleting.
- [ ] Enforce unique constraints/leases so multiple workers never double-process.
- [ ] Implement retry budgets, backoff, and poison-message quarantine.
- [ ] Ensure one failing message never stalls the whole mailbox for the poller.

### Content Inspection

- [ ] Cap raw message size before/during download when feasible.
- [ ] Cap total decoded size, MIME depth, and part count.
- [ ] Never use filenames or headers directly as paths or authority.
- [ ] Enforce use-case-driven allowlists in attachment policies.
- [ ] Cross-check declared MIME types against actual content bytes.
- [ ] Enforce entry count, nesting, and uncompressed byte limits on archives.
- [ ] Never treat `ERROR`/`TIMEOUT`/`UNSCANNABLE` scan results as `CLEAN`.
- [ ] Bind scanner verdicts to immutable hashes/object versions.
- [ ] Never render raw HTML or auto-fetch external resources.
- [ ] Protect any URL fetching with SSRF defenses.
- [ ] Process text/CSV/XML/PDF with format-specific bounds.
- [ ] Never trust `From` headers or execution instructions inside emails.

### Business Logic, Data, and Operations

- [ ] Business handlers accept only normalized/validated DTOs.
- [ ] Sensitive operations require independent authorization.
- [ ] Business processing enforces idempotency and clear transaction boundaries.
- [ ] Staging/quarantine storage enforces ACLs, encryption, and retention.
- [ ] Raw emails/PII/secrets never appear in logs or metric labels.
- [ ] Dashboards track poll success, staging, scanning, quarantine, and pending age.
- [ ] Runbooks exist for credential/TLS/DNS, parser, scanner, and malware incidents.
- [ ] Tests cover real server permissions, malformed MIME, oversized payloads, and races.
- [ ] Original emails are moved/deleted only via authorized, audited workflows.

These checkboxes are an implementation planning tool, not proof that a given system already complies. Verify through testing and real permission audits before handling sensitive data.

## 45. Example Journey of a Valid Invoice Email

Suppose an email arrives at an invoice-only mailbox:

~~~text
IMAP INBOX:
  account = invoices-inbound
  folder = INBOX
  UIDVALIDITY = 308
  UID = 7281
  one attachment = invoice.pdf
~~~

### Step 1 — Read with Least Privilege

The service identity has read access only to the permitted `INBOX`. The worker opens `Folder.READ_ONLY` and checks by UID key that it is not yet staged. It neither deletes nor moves the original email.

### Step 2 — Persist Staging

The worker checks size metadata, downloads within byte limits, stores an unexposed quarantine object, and records a ledger entry:

~~~text
ingestionId: in-7281
accountId: invoices-inbound
folder: INBOX
uidValidity: 308
uid: 7281
status: STAGED
rawStorageKey: quarantine/random-id
~~~

### Step 3 — Parse MIME

The worker bounds depth/part count, parses subject/text/attachments, verifies `invoice.pdf` matches an allowed format, and confirms decoded bytes stay within limits. The original filename remains metadata only, not a storage path.

### Step 4 — Scan and Release

The attachment is scanned from the exact immutable object/version. If the verdict is `CLEAN` and other checks pass, the system records `ApprovedAttachmentRef`. If the scanner errors, the email stays in quarantine rather than proceeding to the business handler.

### Step 5 — Business Verification

The application extracts invoice number, supplier, and amount, reconciling them against registered suppliers, purchase orders, and approval workflows. It never alters payment accounts just because the email asks.

### Step 6 — Idempotent Commit

The database records the invoice draft/ticket under a business idempotency key. If the worker crashes after commit, retries see the same business work is already complete and never create two invoices.

### Step 7 — Record Outcome

The ledger transitions to `PROCESSED` with timestamp and audit metadata. If the workflow moves the email to a `Processed` folder, that step executes separately with matching credentials/permissions after commit and supports safe retries.

This is the happy path; failure branches such as oversized/virus/invalid supplier stay tracked in state and follow policy rather than silently dropping mail.

## 46. Example Dangerous Email and Blocking Controls

A message impersonating an invoice:

~~~text
From: accounts@trusted-supplier.example
Subject: New invoice
Content-Type: multipart/mixed

Body: Please update bank account immediately.
Attachment: invoice.pdf.exe
HTML: external tracking image and misleading link
~~~

Handling sequence:

1. `From` header is **not** treated as authenticated automatically.
2. HTML is neither rendered nor allowed to fetch remote tracking images.
3. Double-extension filename is flagged by policy and never stored under its original name.
4. Detector identifies actual file type; since executables are not allowlisted, it is blocked.
5. Un-`CLEAN` attachments are never released.
6. Business handler refuses to change bank accounts from a body request.
7. Email is quarantined/reviewed with explicit reason and audit trail.
8. Source or provider event is reconciled if needed, without auto-replying with sensitive content.

The strength of this design is **defense in depth across multiple layers**, never relying on a single filter.

## 47. Self-Check Questions

**1. Is `JavaMailSender` Spring's email-receiving API?**

No. `JavaMailSender` is primarily for sending. Receiving mail uses Jakarta Mail `Store`/`Folder` or Spring Integration Mail / provider APIs.

**2. Why is opening `Folder.READ_ONLY` alone insufficient?**

It is a client-side folder access mode and does not restrict the credential's actual permissions on the mail server. Least-privilege ACLs/scopes are required.

**3. Should ingestion use a personal mailbox or a service mailbox?**

Prefer a dedicated mailbox/identity scoped strictly to needed data; avoid personal accounts or broad admin rights.

**4. Are OAuth2 mail-reading scopes identical across all providers?**

No. Scopes depend on the provider and API/IMAP protocol; read the exact documentation and grant the minimal supported permission.

**5. Why avoid relying on message sequence numbers in IMAP?**

They shift when messages are deleted/expunged. Use UIDs scoped to account/folder/`UIDVALIDITY`.

**6. Are UIDs globally unique and permanent?**

No. UIDs are bound to a folder and `UIDVALIDITY`; moving folders or resetting `UIDVALIDITY` changes UID correspondence.

**7. Why not use `\Seen` as a business-processed marker?**

Flags can be altered before staging/commit by other clients or read operations; it is not a durable transaction marker.

**8. What happens if the scanner loses connectivity?**

Hold the attachment in quarantine/`SCAN_PENDING` with bounded retries or route to review. Never default to `CLEAN`.

**9. Is a file with `.pdf` extension and `Content-Type: application/pdf` already safe?**

No. Both can be forged by the sender. Check actual file type, format-specific risks, and malware policy.

**10. Why is a raw size limit insufficient for ZIPs?**

Archives can decompress massively. Cap decoded/uncompressed bytes, nesting, entry counts, and resource consumption.

**11. Is `Message.getSize()` always accurate?**

No. It can be unavailable or fail to reflect decoded content; enforce actual byte counts during ingestion/storage.

**12. Why must attachment filenames never be used as storage paths?**

Filenames are untrusted input that can contain traversal/absolute paths/control chars; use application-generated storage keys and store filenames as metadata.

**13. Can email HTML be rendered directly inside an admin dashboard?**

No. Use escaped text or a strict sanitizer with isolation, blocking active content and remote resources.

**14. Does a DKIM pass prove the email came from an authorized person?**

No. It is domain/signature authentication evidence in the right context, not business authorization for the requested action.

**15. May the app auto-fetch every link appearing in emails to extract data?**

No. That can cause SSRF or tracking leaks. Use a safe fetcher with allowlists and IP/redirect/size/time limits only when business requires it.

**16. Why distinguish raw message IDs from business idempotency keys?**

One source message can be re-read multiple times, while one business operation can arrive across multiple messages or channels. Enforce deduplication keys at both boundaries.

**17. May an email from a verified partner automatically update payment accounts?**

Not by default. Sensitive actions require independent permission checks and approval workflows.

**18. If an email has malformed MIME, should it retry endlessly hoping to become readable?**

No. Classify as a poison message, quarantine/review after limits, and avoid blocking the whole queue.

**19. When a malicious email is detected, should it be deleted immediately from the server?**

Not by default. Follow retention/forensic policies and separate delete permissions; stage/quarantine before destructive actions.

**20. Should a business handler open `Part.getInputStream()` directly from the mailbox?**

Not when strong security is required. Handlers should receive only inspected DTOs or references to immutable approved objects, never bypassing MIME/scan gates.

**21. Why isolate sandboxed extraction from services holding many secrets?**

Complex document parsers can harbor vulnerabilities or overload; isolation and low privileges limit blast radius when untrusted files misbehave.

**22. Does Spring Integration IMAP IDLE guarantee each message is processed exactly once?**

No. Reconnects, redeliveries, and crashes still require reconciliation/ledgers/idempotency.

**23. What if a record scanned `CLEAN`, yet the underlying object later changes?**

Never apply an old verdict to new bytes. Bind scanner verdicts to hashes/versions; modified objects must be re-scanned or rejected.

**24. Should raw email data be placed into Prometheus labels?**

No. It can expose PII/secrets and create high cardinality. Use bounded labels while keeping details in access-controlled storage with retention.

**25. What conditions must hold before an email enters business processing?**

Valid mailbox permissions; durable staging; valid size/MIME/attachment limits; policy-compliant scan verdict; normalized extracted data; authorized source and action; and designed idempotency/transactions.

## Conclusion

**Least privilege and incoming content inspection are two inseparable layers of defense when using Spring Framework Mail alongside Jakarta Mail or Spring Integration Mail.** Mail-receiving accounts must hold minimal scopes/ACLs, read only necessary mailboxes/folders, protect tokens/secrets, and never implicitly carry send, delete, or admin rights. Fetching must use UID/`UIDVALIDITY` or appropriate source IDs, persist durable staging, maintain checkpoints/idempotency, and avoid treating `\Seen` as the sole acknowledgment.

For content, treat all headers, bodies, HTML, URLs, and attachments as untrusted input. Cap raw/decoded bytes, MIME depth, and part counts; validate filenames, actual content types, archives, and malware; handle scanner failures by isolating rather than releasing; never auto-render active HTML or auto-fetch external resources; and never let emails authorize business mutations. Only inspected DTOs and immutable approved attachments should reach business handlers enforcing independent authorization. **A secure mail-receiving system does not merely "read emails"—it enforces scoped access, keeps dangerous payloads inside quarantine, never loses mail when workers fail, and grounds every business action in verifiable trust and traceability.**
