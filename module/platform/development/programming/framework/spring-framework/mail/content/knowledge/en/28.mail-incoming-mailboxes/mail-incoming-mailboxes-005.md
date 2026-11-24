# Inbound Channel Adapters and Polling

In Spring Framework Mail, most programs begin by **sending emails** via `JavaMailSender` and SMTP. However, a system managing tickets, invoices, customer feedback, or partner integrations may also need to **receive emails** from a mailbox: checking the mailbox periodically, reading new emails, converting content into a business task, storing attachments, and updating state.

To implement this problem in a Spring-idiomatic way, you can use **Spring Integration Mail** with an **inbound channel adapter** and a **poller**. The mail receiver connects over IMAP or POP3; `MailReceivingMessageSource` supplies data to the integration flow; the poller periodically invokes the receiving source; and the channel forwards messages to handlers. This decouples mailbox reading from ticket processing, file storage, or business responses.

~~~mermaid
flowchart LR
    A["IMAP/POP3 mailbox"] --> B["Mail receiver"]
    C["Poller"] --> D["MailReceivingMessageSource"]
    B --> D
    D --> E["Inbound channel adapter"]
    E --> F["Message channel"]
    F --> G["Ingestion handler"]
    G --> H["Database / job queue"]
~~~

However, configuring a poller to run every 30 seconds **does not guarantee** that emails are processed exactly once, never lost on server errors, or that attachments are always safe. An inbound mail system must proactively manage **UIDs, UIDVALIDITY, read flags, idempotency, acknowledgments, MIME parsing, retries, and backpressure**.

This lesson explains the inbound channel adapter model, Java DSL configuration, polling vs. IMAP IDLE comparisons, identifying new mail, common errors, and operational architecture, along with JUnit/integration test examples tailored for Spring Integration Mail.

## 1. Receiving Mail and Sending Mail Are Two Different Flows

| Aspect | Sending Mail | Receiving Mail |
| --- | --- | --- |
| Typical component | `JavaMailSender` | Spring Integration Mail receiver |
| Protocol | SMTP | IMAP/IMAPS, POP3/POP3S |
| Trigger source | Business events, APIs, outbox | Poller or IMAP IDLE notifications |
| Action | Submit MIME message to SMTP relay | Search messages, fetch metadata and content |
| Initial outcome | Relay accepts or rejects submission | A message enters the integration flow |
| State to manage | Send retries, submission outcome | Mailbox UID, processing state, acknowledgment |
| Risks | Duplicate sends, quotas, throttling | Duplicate receipts, missed mail, unsafe parsing |

`JavaMailSender` has no inbox polling capability. An IMAP receiver does not turn a received email into an SMTP send. If an application handles both inbound and outbound flows, design separate credentials, endpoints, queues, and business policies for the two directions.

In particular, **having downloaded an email from the mailbox** does not mean **the request inside the email has been processed**. Reading, durable persistence, business processing, and marking on the mail server can each fail independently.

## 2. What Is an Inbound Channel Adapter?

In Spring Integration, an inbound channel adapter is an endpoint that brings data from an external system into a `MessageChannel`. On the mail-receiving side, the components include:

- **Mail receiver:** reads messages from a mailbox over an appropriate protocol.
- **Message source:** an object callable to retrieve messages, such as `MailReceivingMessageSource`.
- **Poller:** a schedule that invokes the source periodically.
- **Integration channel:** forwards received messages.
- **Service activator/handler:** processes payloads, stores data, or creates jobs.
- **Error handling:** records and routes errors from the source or handlers.

Example of a single poll:

~~~text
Poller triggers
  -> MailReceivingMessageSource.receive()
  -> ImapMailReceiver finds eligible messages
  -> Message converted to integration Message
  -> Channel dispatches to MailIntakeService
  -> Intake persists metadata + files
  -> Creates business job
~~~

**Inbound channel adapters are typically one-way.** They do not automatically generate reply emails or require an SMTP response. If business logic requires sending an acknowledgment email, that is a separate use case using an outbound gateway/sender after the request has been validated and processed.

## 3. Spring Integration Mail and Dependencies

With Gradle in a Spring Boot application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

If the same application also needs to send email:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Spring Integration Mail and the outbound mail starter have distinct responsibilities. Use compatible dependency versions managed by Spring Boot BOM/dependency management. In modern Spring Framework, Jakarta Mail uses the `jakarta.mail` namespace; arbitrarily mixing older `javax.mail` and newer `jakarta.mail` versions can cause classpath errors.

An application that only receives email does not have to use `JavaMailSender`. It only needs an outbound sender if the workflow actually sends replies or notifications.

## 4. Where Do IMAP and POP3 Differ?

| Criterion | IMAP/IMAPS | POP3/POP3S |
| --- | --- | --- |
| Folders | Supports multiple folders | Typically accesses mailbox with a simple model |
| Flags | Has `\Seen`, `\Deleted`, and other flags | Lacks an equivalent IMAP flag system |
| UID | UID tied to folder and UIDVALIDITY | UIDL per POP3 server semantics |
| Server-side search | Has IMAP SEARCH | More limited |
| Mark as read | Has IMAP flags | No direct equivalent |
| Delete messages | Flags/expunge depending on commands | POP3 deletion semantics |
| IMAP IDLE | May be supported | Does not support IMAP IDLE |

**IMAPS** is IMAP protected directly by TLS, typically on port 993. **POP3S** is the equivalent for POP3, typically on port 995. Exact protocols and ports must follow the provider.

For workflows needing to retain messages, flag, archive, and track state across multiple workers, IMAP is usually more convenient. POP3 can suffice for simple download flows when supported by the provider. Do not assume IMAP IDLE, OAuth2, or every IMAP extension is available on all servers.

## 5. What Exactly Is Polling?

Polling means the application periodically asks the mailbox whether any messages match the search criteria.

~~~text
00:00  poll -> message A
00:30  poll -> no messages
01:00  poll -> messages B, C
01:30  poll -> no messages
02:00  poll -> message D
~~~

Each poll does **not** mean one new email. A single poll can return 0, 1, or many messages depending on the source, batch size, and configuration.

There are two independent questions:

1. **When to run?** Decided by the poller.
2. **Which messages to receive?** Decided by the mail receiver, search strategy, and mailbox state.

If the poller runs on schedule but the receiver only searches unread messages, an email opened by another user may be missed. If the receiver does not mark messages and lacks idempotency, the same email may repeat on every poll.

## 6. Fixed Delay, Fixed Rate, and Processing Latency

**Fixed delay:** a new poll is scheduled after a wait interval measured from when the previous run finished.

**Fixed rate:** targets a cadence measured from start times, depending on the scheduler and how long-running tasks are handled.

Example:

~~~text
Fixed delay: 30 seconds
  poll #1 starts t=0, finishes t=8
  poll #2 starts around t=38

Fixed rate: 30 seconds
  targets starting near t=0, t=30, t=60...
~~~

Do not assume every fixed-rate configuration runs multiple threads overlapping each other; concurrent execution also depends on the scheduler/task executor.

For mailboxes receiving large attachments and heavy handlers, fixed delay is usually easier to predict. However, if a very low SLA is required, separate intake from business processors instead of merely shrinking the poll interval to tiny values.

## 7. Spring Boot Configuration for Inbound Mail

`spring.mail.*` normally describes outbound SMTP. For inbound, an application can define its own namespace:

~~~yaml
app:
  mail:
    inbound:
      enabled: true
      protocol: imaps
      host: ${MAILBOX_IMAP_HOST}
      port: 993
      username: ${MAILBOX_IMAP_USER}
      folder: INBOX
      poll-delay: 30s
      max-messages-per-poll: 10
      delete-after-ingest: false
~~~

This is **custom configuration**, not built-in defaults Spring Boot understands automatically. You must bind it using `@ConfigurationProperties` or an equivalent configuration mechanism.

Real credentials belong in a secret manager or protected configuration source. Never hardcode passwords/app tokens, never log passwords, and never print full mail URLs.

### Separating the SMTP Host from the IMAP Host

For example, the same provider may have two endpoints:

~~~text
SMTP submission: smtp.provider.example:587
IMAPS inbox:     imap.provider.example:993
~~~

They have different protocols and access permissions. An SMTP account that sends mail does not automatically have permission to open an IMAP folder.

## 8. Java DSL with ImapMailReceiver

Example configuring the core components in Spring Integration Mail:

~~~java
import java.time.Duration;
import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
public class InboundMailConfiguration {

    @Bean
    ImapMailReceiver imapReceiver(
            @Value("${app.mail.inbound.url}")
            String mailUrl) {

        ImapMailReceiver receiver =
                new ImapMailReceiver(mailUrl);

        receiver.setShouldDeleteMessages(false);
        receiver.setShouldMarkMessagesAsRead(false);

        Properties props = new Properties();

        props.put(
                "mail.imaps.connectiontimeout", "5000"
        );
        props.put(
                "mail.imaps.timeout", "10000"
        );
        props.put(
                "mail.imaps.ssl.checkserveridentity",
                "true"
        );

        receiver.setJavaMailProperties(props);
        return receiver;
    }

    @Bean
    IntegrationFlow inboundMailFlow(
            ImapMailReceiver receiver,
            MailIntakeService intake) {

        MailReceivingMessageSource source =
                new MailReceivingMessageSource(receiver);

        return IntegrationFlow
                .from(
                    source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(
                                    Duration.ofSeconds(30)
                            ).maxMessagesPerPoll(10)
                    )
                )
                .handle(intake, "accept")
                .get();
    }
}
~~~

This snippet illustrates the receiver → source → polling endpoint → service activator structure. Java DSL overloads/API names must match the Spring Integration version used by the project.

`app.mail.inbound.url` can be a receiver URL like `imaps://user:credential@host:993/INBOX` constructed from a trusted config source. If the URI contains secrets, handle URL encoding properly and never log the full URI. Providers using OAuth2 may require different auth/token configuration than standard password URLs.

The two options in the example are intentional:

- `setShouldDeleteMessages(false)`: do not auto-delete emails after fetching.
- `setShouldMarkMessagesAsRead(false)`: do not treat fetching as a "processed" acknowledgment.

This **does not prevent duplicates**. Because messages can still be seen again by the receiver, the application must have an idempotency store or an explicit search/ack policy.

## 9. What Part Does MailIntakeService Handle?

A handler should not perform all heavy work while the IMAP session remains open. A sound approach:

~~~java
public final class MailIntakeService {

    private final InboundMailIngestor ingestor;

    public MailIntakeService(
            InboundMailIngestor ingestor) {
        this.ingestor = ingestor;
    }

    public void accept(MimeMessage message)
            throws MessagingException {

        InboundEnvelope normalized =
                extractEnvelope(message);

        ingestor.persistIfNew(normalized);
    }

    private InboundEnvelope extractEnvelope(
            MimeMessage message)
            throws MessagingException {

        // Read required metadata and content.
        // Enforce MIME/attachment limits.
        // Application-defined API.
        throw new UnsupportedOperationException(
                "Implement extractor per project"
        );
    }
}
~~~

The `InboundEnvelope` and `InboundMailIngestor` types are application abstractions, not built-in Spring APIs. The example intentionally leaves extraction as a skeleton, because MIME parsing and UID retrieval must match folder lifecycle in the actual implementation.

Key points:

- Intake must know the mailbox/account source.
- Generate a stable key for the email.
- Parse minimal data within limits.
- Persist metadata/content and jobs durably.
- Never create multiple tickets just because an email is re-polled.
- Never push a live `MimeMessage` into a queue that survives restarts.

## 10. maxMessagesPerPoll Is Not a Size Limit

Example:

~~~java
Pollers.fixedDelay(
        Duration.ofSeconds(30)
).maxMessagesPerPoll(10)
~~~

Normally, `maxMessagesPerPoll` controls how many receive calls/messages the poller processes from the source per pass. However, a mail receiver may fetch metadata or content in batches, and depending on the implementation it may retrieve many candidates from the server before the poller finishes.

It does not mean:

- Each poll uses at most 10 MiB of heap.
- The server only sends at most 10 MIME parts.
- Attachments have been safely checked.
- No more than 10 emails exist in the system.
- Business handlers run only 10 jobs cluster-wide.

You must enforce **message size, attachment count, batch fetch, handler concurrency, and queue capacity** through separate mechanisms.

## 11. How Should the Poll Interval Be Chosen?

Factors:

- Mailbox volume.
- Acceptable detection latency.
- Provider connection/query quotas.
- MIME/attachment fetch duration.
- CPU/heap/network capacity.
- Processing backlog.
- Availability of IMAP IDLE.
- Email priority.

A ticket system not needing real-time updates might poll every few dozen seconds; a system receiving daily reports might poll every few minutes. These are examples only—there is no universal threshold.

Shrinking the interval to one second when the mailbox/server is slow can increase throttling and reset connections. Measure **mailbox arrival → durable ingest → business processed** instead of merely counting polls per minute.

## 12. Polling vs. IMAP IDLE

IMAP IDLE is an extension allowing clients to maintain a connection and receive mailbox change signals. Spring Integration Mail offers an **IMAP IDLE channel adapter** approach when supported by the provider.

| Factor | Polling | IMAP IDLE |
| --- | --- | --- |
| Detection | Scheduled | Server notification over IDLE connection |
| Latency | Tied to poll interval | Potentially lower |
| Connection | Per connect/fetch strategy | Usually keeps an IDLE session open |
| Protocol support | Works with IMAP or POP3 | Requires server IDLE support |
| Reconnect | Next poll and retry | Must reconnect/restart IDLE |
| Duplicates | Still possible | Still possible |
| Missed events on network drop | Requires rescan | Requires backfill/reconciliation |

**IMAP IDLE is not an HTTP webhook** and does not replace fetching content. When connections drop, the application still needs re-scanning, duplicate handling, and state management.

For simple needs or servers without stable IDLE support, polling is a clear, easy-to-observe, and controllable choice.

## 13. Search Strategy: What Counts as a New Message?

An IMAP receiver can filter by:

- Configured folder.
- `\Seen` or other flags.
- Server-side search terms.
- Received date/time.
- Application-specific user flags.
- Custom policy conditions.

Example:

~~~text
Poll receiver INBOX
  -> search UNSEEN
  -> fetch A and B
  -> send A, B to channel
~~~

If staff open A in webmail before the poller runs, `\Seen` may be set even though the application has not ingested A yet. Conversely, if the receiver never marks read and always searches `UNSEEN`, A may be re-emitted on subsequent polls.

**Unseen is not unprocessed.** Mailbox flags represent protocol state, not proof that business processing completed.

### Relying Solely on Timestamps Also Risks Missing Mail

A mechanism that "fetches messages with `receivedAt` greater than the last run" can miss late-arriving mail, identical timestamps, or records whose metadata changed on the server. If using timestamps to narrow search scope, combine overlap/reconciliation with idempotency.

## 14. Read, Deleted, and Processed Messages

| State | Where Stored | Meaning |
| --- | --- | --- |
| `\Seen` | IMAP mailbox | Server marks as read |
| `\Deleted` | IMAP mailbox | Message marked for deletion per IMAP |
| `INGESTED` | Application database | Needed metadata/content saved |
| `PROCESSING` | Database/job queue | Worker is executing business logic |
| `PROCESSED` | Database | Business processing completed |
| `RETRY` | Job store | Temporary processing failure |
| `QUARANTINED` | Separate database/storage | Message cannot be processed normally |

Dangerous failure mode:

~~~text
1. Receiver fetches email.
2. Marks Seen or deletes.
3. Database insert fails.
4. Poller searches only unseen.
5. Email is never ingested again.
~~~

Therefore, without another recovery mechanism, **never delete or exclude a message from search before data is durably persisted**.

A sound ordering:

~~~text
Fetch candidate
  -> Extract key/content
  -> Persist unique inbox record
  -> Commit
  -> Ack / mark / move per policy
  -> Process business job
~~~

If acknowledgment fails after commit, the next poll may detect the message again. The unique key prevents creating a duplicate job.

## 15. IMAP Sequence Number, UID, and UIDVALIDITY

Do not use message numbers as durable identifiers.

**Sequence number** is the message's position in a folder at a point in time. It can shift when messages are expunged or folders change.

**UID** is a stable identifier per IMAP folder semantics, but must be placed within a **UIDVALIDITY** namespace.

**UIDVALIDITY** distinguishes moments when the server resets the UID namespace. If it changes, old and new UIDs cannot be treated as equivalent just because the numbers match.

An appropriate key:

~~~text
mailboxAccountId
  + folderId
  + uidValidity
  + uid
~~~

~~~java
public record ImapMessageKey(
        String mailboxAccountId,
        String folderId,
        long uidValidity,
        long uid) {
}
~~~

Example key:

~~~text
(account-support, INBOX, 982341, 1077)
~~~

If the same email is copied to another folder, it may receive a different UID. This identifies **one occurrence in a mailbox**, not a global hash of the email's content.

## 16. Retrieving UIDs via Jakarta Mail

Jakarta Mail provides `UIDFolder` when supported by the folder:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.UIDFolder;

public ImapMessageKey toKey(
        String accountId,
        String folderId,
        Message message) throws MessagingException {

    Folder folder = message.getFolder();

    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "UIDFolder not available"
        );
    }

    long uidValidity =
            uidFolder.getUIDValidity();

    long uid =
            uidFolder.getUID(message);

    return new ImapMessageKey(
            accountId,
            folderId,
            uidValidity,
            uid
    );
}
~~~

This illustrates calling while the message/folder **is still valid and open**. If the receiver has already closed the folder or the message is handed off to a handler after the connection closes, reading the UID or lazy attachments may fail.

A good design captures the UID and needed metadata **during the mailbox access phase** within the receiver-supported lifecycle. Never keep an IMAP session open for hours simply because a business handler is slow.

## 17. Is Message-ID Enough to Deduplicate?

The `Message-ID` header is often helpful for threading/tracing, but:

- It can be missing.
- It can be duplicated.
- Senders can spoof it.
- The same message copied to another folder gets a different UID.
- A resent email may reuse an old Message-ID or generate a new one.

Therefore, do not use `Message-ID` alone as an absolute ingestion key. For IMAP, the tuple account/folder/UIDVALIDITY/UID protects against ingesting the same mailbox message twice.

Additionally, business logic may need its own idempotency key from a valid request ID or token inside the email. These two layers are distinct:

1. **Ingestion idempotency:** one IMAP occurrence is persisted once.
2. **Business idempotency:** one business action is not unintentionally executed twice.

## 18. Idempotency Store in the Database

An illustrative table:

~~~text
inbound_mail
------------
id
mailbox_account_id
folder_id
uid_validity
uid
message_id_header
sender_address
received_at
raw_object_key
ingestion_status
processing_status
first_seen_at
last_seen_at
~~~

A unique constraint:

~~~sql
UNIQUE (
    mailbox_account_id,
    folder_id,
    uid_validity,
    uid
)
~~~

When another poller or the same poller runs again, duplicate-key inserts must follow this contract:

~~~text
Insert succeeds:
  -> new mail, create business job.

Unique key already exists:
  -> mail already ingested; do not create a new job.
  -> may retry acknowledgment if needed.
~~~

Never implement a "SELECT not found then INSERT" flow without a unique constraint when multiple workers run; two threads can both observe absence and both insert.

If storing raw MIME or attachments, manage storage references and transaction boundaries so no orphan objects are created and nothing is acknowledged as succeeded before data is durable.

## 19. At-Least-Once and Failures Between Steps

| Crash/Failure Point | Situation | Recovery |
| --- | --- | --- |
| Before fetch | Message not yet seen | Re-poll |
| Fetched, not persisted | Content exists only transiently | Re-poll while message remains on server |
| Persisted, not marked Seen | Server may return message again | Deduplicate via unique key |
| Marked Seen, DB fails | Risk of losing message | Avoid this ordering |
| Business worker fails | Inbound record still exists | Retry job |
| IMAP ack/move fails | Inbound already saved | Retry acknowledgment |
| Server changes UIDVALIDITY | New key namespace | Reconcile per policy |

The database and IMAP server do not share an ACID transaction. Therefore systems are normally designed for **at-least-once detection/ingestion with idempotent processing**, rather than claiming exactly-once just because a poller runs on one thread.

If the mailbox has an automatic deletion policy, ensure the retention window is long enough to recover if the application is down for hours or days.

## 20. Separating Intake from Long-Running Business Processing

An email might require:

- Parsing MIME.
- Scanning attachments.
- PDF OCR.
- Extracting invoice data.
- Creating a ticket.
- Calling third-party APIs.
- Sending a reply email.

Do not hold the poller loop and mailbox connection waiting for all of this work when throughput or reliability matters.

~~~mermaid
flowchart TD
    A["IMAP/POP3 poll"] --> B["Fetch + metadata"]
    B --> C["Validate MIME/size"]
    C --> D["Persist unique inbound record"]
    D --> E["Persist raw content/attachment"]
    E --> F["Business queue"]
    F --> G["Worker"]
    G --> H{"Result"}
    H -->|"Success"| I["PROCESSED"]
    H -->|"Transient error"| J["RETRY"]
    H -->|"Permanent error"| K["QUARANTINED"]
~~~

Once durably captured, business workers read data from the database/object storage rather than from a `MimeMessage` still attached to a folder/session.

### Why Not Put a Live MimeMessage into a Queue?

A `MimeMessage` may rely on lazy content or streams from the folder/server. When a handler runs later, the folder may already be closed, causing errors reading bodies/attachments. A durable queue should also avoid serializing whole Jakarta Mail objects.

Convert it into a DTO with lightweight metadata, object storage keys, validated content, or bounded stored raw MIME.

## 21. Inbound MIME Email Is Untrusted Data

An email can contain:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
├── image/png (inline)
└── invoice.pdf (attachment)
~~~

Risks:

- Spoofed `From` sender.
- `Subject` containing tokens/unusual characters.
- HTML containing malicious markup or remote tracking.
- Attachments containing malware.
- Filenames containing path traversal.
- Deeply nested or malformed MIME parts.
- ZIP bombs.
- Extremely large content exhausting the heap.
- Emails containing sensitive data subject to retention and access policies.

Never use `message.getFrom()` to decide who is authorized to modify a ticket. Email sender identity is spoofable data and must be verified at the business layer via tokens, identity binding, or approved policies.

### Email HTML Should Never Be Rendered Directly in Admin UIs

An email viewing screen must sanitize content, restrict remote image loading, and apply appropriate sandboxing/CSP. `MimeMessage.getContent()` is not an HTML sanitizer.

## 22. Bounded Multipart Extraction

An illustrative helper:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public void inspectPart(
        Part part,
        int depth) throws Exception {

    if (depth > 12) {
        throw new IllegalArgumentException(
                "MIME nesting too deep"
        );
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart =
                (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            inspectPart(
                    multipart.getBodyPart(i),
                    depth + 1
            );
        }

        return;
    }

    if (part.isMimeType("text/plain")) {
        // Limit bytes/chars before persisting.
        return;
    }

    if (part.isMimeType("text/html")) {
        // Store/sanitize per policy; never render directly.
        return;
    }

    // Other parts: attachments, inline files,
    // nested messages, or unsupported content.
}
~~~

This is an **outline**, not a production MIME parser. You must handle nested `message/rfc822`, charsets, filename encoding, and proper stream lifecycles. `multipart/alternative` usually represents the same content in plain text and HTML, not two separate business requests.

Do not trust sender-provided `Content-Type` or filenames to determine whether a file is safe. For sensitive file types, apply byte inspection, scanning, and appropriate size caps.

## 23. Size Policy and Attachment Streaming

Some limits you can configure:

| Limit | Purpose |
| --- | --- |
| Max total MIME bytes | Block oversized emails |
| Max attachment bytes | Block a single large file |
| Max total attachment bytes | Cap total resource usage |
| Max part count | Prevent thousands of MIME parts |
| Max nesting depth | Prevent deeply nested content |
| Max HTML/plain bytes | Prevent abnormal body sizes |
| Max processing time | Protect workers |
| Max concurrent fetches | Limit mailbox pressure |
| Quarantine TTL | Retention and data protection |

For large attachments, stream into managed storage with a byte counter and cap; never unconditionally call `readAllBytes()` or store whole files as `byte[]` in a queue. For malformed multipart emails or messages exceeding policy sizes, quarantine them and continue processing other emails.

## 24. IMAPS, POP3S, and Credential Management

In production:

1. Use provider-appropriate TLS.
2. Enable hostname/certificate verification.
3. Never disable TLS validation to fix connection errors.
4. Configure connection/read timeouts.
5. Use a secret manager for credentials.
6. Support OAuth2/token refresh if required by the provider.
7. Never log URIs containing usernames/passwords.
8. Restrict egress hosts/ports to approved provider endpoints.
9. Monitor authentication failures and lockouts.
10. Never grant production mailbox read permissions to automated tests.

A URL-based receiver sometimes uses the structure:

~~~text
imaps://user:secret@imap.example.org:993/INBOX
~~~

This is a syntax example, not a place to put passwords in source code. Special characters in credentials must be encoded according to how the receiver parses URLs; secrets must never be printed in exceptions.

### A Sending Domain Does Not Necessarily Have an IMAP Mailbox

An application may have permission to send via an SMTP subaccount without having a corresponding inbox. To receive replies/bounces, configure a dedicated mailbox or provider webhook. Never infer from a `From` address that IMAP credentials must exist.

## 25. Multi-Tenant or Multi-Mailbox Setups

A platform may receive mail for:

~~~text
support@tenant-a.example
invoices@tenant-b.example
reply@platform.example
~~~

Each mailbox needs configuration for:

- Account ID/tenant scope.
- Endpoint and folder.
- Credential reference.
- Poll interval and connection limit.
- Search strategy.
- Idempotency namespace.
- Storage/retention policy.
- Business destination.

If a centralized mailbox holds emails for multiple tenants via aliases, you must have reliable mapping rules. `To` or `From` headers are not always sufficient to verify the tenant, especially with forwarding/Bcc. You can use recipient alias tokens issued to a tenant/workflow and validate them before performing actions.

Background pollers have no HTTP actor request. Do not rely on a `ThreadLocal` tenant context left over from an earlier request.

## 26. Multiple Workers Polling the Same Inbox

Suppose:

~~~text
Pod A -> poll INBOX
Pod B -> poll INBOX
~~~

Both pods may see the same UID. IMAP does not automatically distribute each message to a single worker like a Kafka consumer group.

Options:

- One active poller per mailbox.
- Leader election/distributed leases.
- Partitioning mailboxes/accounts across instances.
- DB unique keys guarding against duplicate ingestion.
- Combining leases and idempotency for greater efficiency.

**The IMAP Seen flag is not a distributed lock.** Two clients can find the same message before one flags it, or server semantics may differ from DB transactions.

A lease needs an owner, expiration, and fencing against stale workers after the lease transfers. Otherwise, a dead process can stall inbox polling indefinitely.

## 27. Transactions Between Inbox and Database

`@Transactional` on a service manages database transactions, but does not make IMAP mark/move/delete operations part of an atomic commit.

A recommended order:

~~~text
Fetch mail
  -> Extract UID + content
  -> Begin DB transaction
  -> Insert inbox unique key
  -> Persist business job
  -> Commit DB
  -> Mark/move mail per policy
~~~

If mark/move fails after commit, re-polling can deduplicate. If the DB fails before commit, the message remains in the mailbox and can be ingested again.

Avoid letting a mailbox error keep a DB transaction open for dozens of seconds while holding locks. Keep transactions short around persistence, decoupling network operations where appropriate.

## 28. Error Handling and Retries

| Error | Handling |
| --- | --- |
| IMAP connection timeout | Reconnect/backoff |
| AUTH failure | Refresh credentials/alert; avoid tight-loop retries |
| TLS/certificate error | Fix trust/config; never bypass validation |
| Folder renamed or deleted | Configuration failure, alert |
| Server throttling | Lower poll rate, backoff |
| Malformed MIME | Quarantine and continue |
| Oversized attachment | Quarantine/reject with reason |
| Duplicate UID | Skip duplicate side effects |
| Database unavailable | Do not ack/drop mail |
| Business API error | Retry job separately |
| Ack/move error | Retry acknowledgment, preserve dedupe |
| Unknown mailbox state | Reconcile by key and server metadata |

Spring Integration provides error channels/error handling for flows, but receiving an error event **does not automatically resolve** the email's state on the server. The error handler must decide: retry the poll, retry the business job, or quarantine the message?

A malformed poison message can appear on every poll and block subsequent messages. Record the error state/UID, apply retry limits, and allow valid messages to proceed.

## 29. Polling and Backpressure

Suppose a mailbox receives 500 emails/minute while processors can only handle 100/minute. Lowering the poll delay from 30 seconds to 1 second does not increase business throughput; the backlog will simply grow faster.

An architecture needs:

- Bounded poller/worker concurrency.
- Queue/job persistence.
- Limits on MIME size.
- Max in-flight data/attachments.
- Rate limits per mailbox/provider.
- Scheduled retries, never busy loops.
- Prioritizing important mail.
- Monitoring oldest pending message age.
- Mechanisms to throttle intake when storage nears capacity.

If using an in-memory queue and acknowledging the mailbox before the job is persisted, a restart can lose work. For critical business logic, durable intake must precede acknowledgment.

## 30. Monitoring and Alerting

| Metric | Meaning |
| --- | --- |
| `mail_inbound_poll_total` | Poll count |
| `mail_inbound_poll_duration_seconds` | Poll latency |
| `mail_inbound_poll_failure_total` | Mailbox failures |
| `mail_inbound_candidate_total` | Candidate count |
| `mail_inbound_ingested_total` | Newly ingested emails |
| `mail_inbound_duplicate_total` | Repeated UID encounters |
| `mail_inbound_quarantined_total` | Quarantined messages |
| `mail_inbound_processing_failure_total` | Business failures |
| `mail_inbound_backlog_count` | Unfinished work items |
| `mail_inbound_oldest_pending_age_seconds` | Maximum delay |
| `mail_inbound_reconnect_total` | Reconnect count |
| `mail_inbound_lease_conflict_total` | Lease contention |

Labels should use internal mailbox IDs, protocol, and error categories. Never attach sender email, subject, or attachment filenames to every metric, as that can leak sensitive info and cause high cardinality.

Useful alerts when:

- No successful poll occurs within the SLA.
- Credential/TLS failures repeat.
- Backlog and oldest pending age grow.
- Quarantines spike abnormally.
- Duplicate ingestion surges sharply.
- `UIDVALIDITY` changes, requiring resync.
- Mailbox storage nears quota exhaustion.
- A tenant has messages waiting too long.

## 31. What to Unit Test?

Tests that do not require a real mailbox:

**Key idempotency:**

~~~java
@Test
void sameUidWithinSameNamespaceIsSameMessage() {
    ImapMessageKey first =
            new ImapMessageKey(
                    "account-a",
                    "INBOX",
                    100L,
                    200L
            );

    ImapMessageKey second =
            new ImapMessageKey(
                    "account-a",
                    "INBOX",
                    100L,
                    200L
            );

    assertEquals(first, second);
}
~~~

**Business ingestion:** mock the mailbox adapter while using real repository/transaction tests to verify the unique constraint blocks duplicates.

**MIME extractor:** build MIME fixtures with `text/plain`, `text/html`, nested multipart, Unicode filenames, and small attachments; verify size/depth limits.

**Security:** spoofed `From` emails or subjects containing a ticket ID must not trigger side effects without a valid authorization token/identity.

**Retry state machine:** permanent parse errors move to quarantine, transient DB errors must not ack and lose mail, and business errors set `nextAttemptAt`.

## 32. Integration Testing with an IMAP Test Server

An integration test can use GreenMail or an equivalent IMAP test tool:

~~~text
Test IMAP server
  -> Test mailbox + seeded MIME message
  -> ImapMailReceiver
  -> Polling adapter
  -> MailIntakeService
  -> Inbound repository
  -> Assertions by correlation/UID
~~~

Steps:

1. Initialize an isolated test mailbox with its own port/credentials.
2. Seed an email with a correlation ID.
3. Run the poller or trigger controlled polling.
4. Wait for the ingestion record to appear.
5. Verify persisted metadata/content.
6. Poll again and verify no duplicate occurs.
7. Simulate a DB failure and retry.
8. Clean up test resources.

Never use a production inbox or a CI-wide shared mailbox. Parallel tests must isolate servers/recipients/UID namespaces and never invoke delete-all on another test's resources.

### Wait on Conditions Instead of Thread.sleep

Example with the Awaitility library if used by the project:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            assertTrue(
                inboundRepository.existsByCorrelationId(
                        correlationId
                )
            );
        });
~~~

`existsByCorrelationId` is an illustrative test helper/repository method. The goal is observing data belonging specifically to the current test, not checking a global "newest message" in the mailbox.

## 33. Error Testing Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Empty inbox | Poll creates no job |
| New mail present | Ingests one record |
| Same UID polled twice | Creates no duplicate business side effects |
| Two JVMs polling together | Unique constraint/lease protects |
| `UIDVALIDITY` changes | Does not blindly reuse old UID offset |
| Already-Seen message | Handled per intentional search policy |
| IMAP disconnects | Reconnect/backoff |
| Credentials locked | Alert, no hot login loop |
| Corrupt MIME | Quarantine and continue |
| Oversized attachment | Does not exhaust heap |
| DB fails before commit | Does not ack and lose mail |
| Ack fails after commit | Re-poll deduplicates |
| Worker crashes after ingest | Durable job remains |
| Folder closes before reading attachment | Needed data already captured |
| Poison message at head of queue | Does not block other emails |
| Restart mid-poll | Resyncs without data loss |

Not every test requires a real provider. A fake receiver/transport can emit structured errors in unit/component tests; an IMAP test server should verify real interaction and lifecycles.

## 34. Common Implementation Mistakes

### 34.1. Using JavaMailSender to Query a Mailbox

`JavaMailSender` uses SMTP. Receiving mail requires an IMAP/POP3 mail receiver or an appropriate adapter.

### 34.2. Believing the Poller Guarantees Exactly-Once Automatically

The poller only triggers the source; there is no shared transaction between the mailbox and the DB.

### 34.3. Treating \Seen Alone as Processed

Another client can mark a message as read. Flags do not reflect business state.

### 34.4. Marking Seen/Deleting Before Persisting

A DB failure can cause the email to never be seen again when searching unseen messages.

### 34.5. Using Message Number as UID

Sequence numbers can change when the folder is expunged.

### 34.6. Ignoring UIDVALIDITY

UIDs cannot be interpreted safely if the UID namespace has changed.

### 34.7. Deduplicating Solely by Message-ID

The header can be missing, duplicated, or spoofed. Mailbox keys and business policies are required.

### 34.8. Two Pods Polling Without Coordination

Can double-ingest; use leases/leader election and DB unique constraints.

### 34.9. Assuming maxMessagesPerPoll Is a RAM Limit

A single 100 MiB email can still blow up the heap. A MIME size policy is needed.

### 34.10. Running Slow OCR Directly Inside the Polling Handler

Holds threads/connections too long. Separate durable intake from processors.

### 34.11. Letting Live MimeMessages Survive Across Queues/Restarts

Folders/sessions can close; persist needed content durably.

### 34.12. Assuming IMAP IDLE Needs No Rescanning

Connections can drop and require backfill/reconnects.

### 34.13. Retrying Corrupt Messages Infinitely

Poison messages cause backlogs; use quarantine and reason codes.

### 34.14. Trusting From Sender as an Authenticated Identity

Headers can be spoofed. Never update sensitive data based solely on `From`/subject.

### 34.15. Rendering HTML Directly in a Dashboard

Risks malicious content and tracking. Sanitize/sandbox.

### 34.16. Trusting Attachment Content-Type/Filenames

Metadata does not prove a file is safe; validation/scanning is required.

### 34.17. Logging Full Raw MIME

Can expose PII, tokens, and attached files.

### 34.18. Using Production Mailboxes in Tests

Risks marking/deleting real mail or leaking credentials.

### 34.19. Using Thread.sleep to Test Async Flows

Prone to flakiness; wait on correlation IDs with timeouts.

### 34.20. Merging Tenants in a Shared Inbox Without Reliable Mapping

Can process mail for the wrong tenant; require trusted alias/token/ownership validation.

## 35. Practice Questions

**Q1.** Does `JavaMailSender` poll IMAP automatically?

No. It is an outbound SMTP abstraction.

**Q2.** Does a 30-second poller guarantee a message is processed only once?

No. Search/ack policies and idempotency are required.

**Q3.** The receiver does not mark Seen and has no dedupe store. What happens?

The same message may be fetched repeatedly.

**Q4.** Is UID 100 in two different folders necessarily the same message?

No. UIDs belong to a folder's namespace and `UIDVALIDITY`.

**Q5.** Is `Message-ID` sufficient to prevent all duplicates?

No. It can be missing, duplicated, or spoofed.

**Q6.** DB commit succeeds but `Seen` is not marked yet, and the app crashes. What happens?

Re-polling runs, the unique key recognizes it is already saved, and acknowledgment can proceed.

**Q7.** What is the risk of marking `Seen` before committing to the DB?

If the DB fails and search only fetches unseen, the email can be missed.

**Q8.** Does IMAP IDLE create a durable queue on its own?

No. It only assists change detection; persistence and recovery are still required.

**Q9.** When multiple pods poll one mailbox, does IMAP partition messages like Kafka?

Not by default. Coordination/idempotency is required.

**Q10.** Is `maxMessagesPerPoll` equal to 1 safe against a 200 MiB email?

No. Size limits and streaming are required.

**Q11.** Does a subject containing a ticket ID mean the sender is authorized to edit the ticket?

No. Authentication/authorization must be enforced by business rules.

**Q12.** Should a `MimeMessage` be placed into a job queue to be processed a day later?

Do not rely on live objects. Persist controlled DTOs/raw content.

**Q13.** A malformed email is fetched repeatedly. How should it be handled?

Use quarantine/reason codes/retry limits so it does not block the entire mailbox.

**Q14.** Two emails have the same `Message-ID` but different UIDs—what should the app do?

Ingest by mailbox key and then apply an appropriate business dedupe policy rather than making automatic assumptions.

**Q15.** Where should you test to verify IMAP transport works?

Integration tests with an isolated mailbox/test server, without needing a production provider.

## 36. Mental Model

~~~mermaid
flowchart TD
    A["IMAP / POP3 mailbox"] --> B["Poller"]
    B --> C["MailReceivingMessageSource"]
    C --> D["Inbound channel adapter"]
    D --> E["Extract UID + metadata"]
    E --> F["Validate MIME / size / security"]
    F --> G{"Already ingested?"}
    G -->|"Yes"| H["Dedupe / ack per policy"]
    G -->|"No"| I["Persist unique record"]
    I --> J["Commit data + job"]
    J --> K["Ack/move mailbox"]
    J --> L["Business worker"]
    L --> M{"Process"}
    M -->|"Success"| N["PROCESSED"]
    M -->|"Temporary"| O["RETRY"]
    M -->|"Permanent"| P["QUARANTINED"]
~~~

Key takeaways:

1. **Inbound channel adapters bring emails from a mailbox into a Spring Integration channel**, rather than sending over SMTP.
2. **The poller decides the schedule**, while the receiver/search strategy decides candidates.
3. **IMAP/POP3 differ** in folders, UIDs, flags, and deletion semantics.
4. **IMAP IDLE reduces latency when supported**, yet still requires reconnect/backfill/idempotency.
5. **Unread, ingested, and processed are three distinct concepts.**
6. **Never mark/delete before durable persistence** if there is a risk of losing messages.
7. **IMAP keys should include account, folder, `UIDVALIDITY`, and UID**, not just message number.
8. **Repeated polling is normal**; unique constraints and business idempotency are essential.
9. **Multiple instances need leases/coordination**; never treat IMAP flags as distributed locks.
10. **Inbound MIME is untrusted input**; enforce size/depth caps, scanning, and business authorization.
11. **Never keep live `MimeMessage` instances across long-running workers**; persist needed content/metadata durably.
12. **`maxMessagesPerPoll` is not a memory size cap**; bounded resources are required.
13. **Monitoring must track poll failures, backlog, duplicates, quarantine, and latency.**
14. **Test with isolated mailboxes** covering crash recovery, `UIDVALIDITY`, duplicates, and malformed MIME.

In Spring Framework Mail, reliable mail receiving is not just "reading INBOX every 30 seconds". **Inbound channel adapters and polling provide a structured entry point for emails**, while the application must decide which messages are new, when they are considered durably saved, how duplicates are handled, and how to recover from failures. Separating the receiver, poller, idempotency store, durable intake, business processing, and monitoring turns a mailbox into a controlled data source rather than a fragile loop that drops messages or executes the same business action repeatedly.
