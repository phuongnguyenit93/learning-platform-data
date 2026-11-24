# Mail Receiver in Spring Integration

When talking about email in Spring Framework, developers immediately think of `JavaMailSender` and `MimeMessageHelper` for **sending emails outbound**. However, many systems also need to **receive emails from a mailbox**: reading customer replies, ingesting partner reports, processing emails with attachments, or importing support requests from a shared address.

**Spring Integration Mail** provides components that integrate with JavaMail/Jakarta Mail to turn emails received over **IMAP or POP3** into messages inside a **Spring Integration message flow**. Instead of writing your own loop to connect to a mailbox, search for unread emails, and hand off content to business logic, the application can use mail receivers, inbound endpoints, channels, and message handlers.

Architecture example:

~~~text
Mailbox support@example.com
          |
          | IMAP / IMAPS
          v
Spring Integration Mail receiver
          |
          | Spring Message<?> containing email data
          v
Message channel / integration flow
          |
          +-- classify email type
          +-- read subject, From, MIME, attachments
          +-- run security checks
          +-- persist inbound job durably
          |
          v
Application creates ticket or updates business state
~~~

This is **receiving mail from an existing mailbox**, not writing an SMTP server to receive email directly from the Internet. Spring Integration Mail usually acts as an **email client** connecting to a provider's mailbox service.

This lesson explains the role of a mail receiver, how to configure polling and IMAP IDLE, Spring Java DSL examples, safe MIME handling, message state, idempotency, concurrency, operations, and integration testing.

## 1. Distinguishing Mail Sending and Mail Receiving in Spring

| Aspect | Sending Email | Receiving Email |
| --- | --- | --- |
| Familiar components | `JavaMailSender`, `MimeMessageHelper` | Spring Integration Mail receiver / inbound adapter |
| Common protocols | SMTP submission | IMAP, IMAPS, POP3, POP3S |
| Primary action | Submit email to a mail server | Read emails already in a mailbox |
| State to manage | Outbox, retries, submitted, bounced | New/read messages, UID, processed, duplicate |
| Business input | Internal events, mail-sending jobs | External data provided by senders |
| Specific risks | Quotas, SMTP rejections, duplicate sends | Malicious MIME, duplicate processing, missed mail |

An email may be **sent via SMTP** to `support@example.com`. Then the application **reads it via IMAP**, with the two protocols serving two different stages:

~~~text
External sender --SMTP--> Mail server / mailbox
                                   |
                                   | IMAP/POP3
                                   v
                            Spring Integration
                                   |
                                   v
                            Business processing
~~~

### 1.1. When to Use a Mail Receiver?

Suitable use cases:

- Reading emails arriving at `support@...` to create tickets.
- Receiving invoices/reports from partners and extracting attachments.
- Reading a mailbox used for approval or data-ingestion workflows.
- Receiving replies to a sent notification, matched via correlation IDs.
- Triggering workflows when emails arrive from a controlled set of addresses.

### 1.2. When Should You Use a Webhook or Inbound Email API?

If the email service provider offers an **inbound parse webhook**, the application can receive HTTP events instead of polling IMAP itself. Webhooks can reduce mailbox connection management, though you must handle webhook signatures, retries, idempotency, payload formats, and provider limits.

If you only need to know whether an outgoing email bounced or received a complaint, **provider event webhooks** are usually more appropriate than inferring it from a reply mailbox. A mail receiver is useful when the business requirement is genuinely **reading incoming email content from a mailbox**.

## 2. Overview of IMAP, POP3, and IMAP IDLE

### 2.1. IMAP

IMAP fits when the application needs to:

- read a mailbox while keeping emails on the server;
- use folders such as `INBOX`;
- search messages by `SEEN`, `DELETED` flags, or search criteria;
- manage message UIDs within a folder;
- coordinate with other clients or an email archiving process.

Example:

~~~text
imaps://mail-reader:<credential>@mail.example.test:993/INBOX
~~~

This string only illustrates the URL structure; **never put real credentials in documentation, logs, or repositories**. Protocol names, hosts, ports, folders, and special-character escaping must match the library/provider version.

IMAPS typically uses TLS from the start on port **993**. IMAP with STARTTLS typically uses port **143**, if permitted by the provider. Always choose a mode officially published by the provider.

### 2.2. POP3

POP3 is usually simpler, focused on downloading messages in a mailbox, with more limited folder/flag management than IMAP.

~~~text
pop3s://mail-reader:<credential>@mail.example.test:995/INBOX
~~~

POP3S typically uses implicit TLS on port 995. For systems requiring folder searches, reading/marking messages by state, and multi-client handling, **IMAP is usually better suited**.

### 2.3. IMAP IDLE

IMAP IDLE lets a client maintain an IMAP connection so the server notifies it when the mailbox changes, enabling lower-latency processing of new mail than periodic polling.

~~~text
Polling:
  every 15 seconds -> connect/search messages -> process

IMAP IDLE:
  hold an IMAP IDLE session
  -> server notifies of change
  -> receiver searches/receives messages
  -> forwards to integration channel
~~~

**IDLE is not a queue with absolute delivery guarantees.** Servers can drop connections, networks can interrupt, or notifications can be missed. Production applications still need a reconnect and mailbox re-sync strategy, rather than relying solely on a live IDLE connection.

### 2.4. Quick Comparison

| Criterion | IMAP polling | IMAP IDLE | POP3 polling |
| --- | --- | --- | --- |
| Detection method | Scheduled | Server pushes change notice over IDLE connection | Scheduled |
| Folders | Yes | Yes | Limited |
| Flags/read state | Yes | Yes | Limited |
| UID per folder | IMAP UID/UIDVALIDITY | IMAP UID/UIDVALIDITY | UIDL if supported by server |
| Latency | Depends on poll interval | Usually lower when IDLE is stable | Depends on poll interval |
| Long-lived connection | Not necessarily | Yes | Not necessarily |
| Best suited for | Batches, reconciliation, moderate load | Near real-time response | Simple mailboxes |

## 3. Building Blocks of Spring Integration Mail

Spring Integration separates **fetching messages** from **processing messages**:

| Component | Role |
| --- | --- |
| `ImapMailReceiver` | Accesses emails from an IMAP mailbox |
| `Pop3MailReceiver` | Accesses emails from a POP3 mailbox |
| `MailReceivingMessageSource` | Exposes received messages as a source for polling endpoints |
| `SourcePollingChannelAdapter` | Endpoint that periodically polls a message source |
| `ImapIdleChannelAdapter` | Inbound endpoint using IMAP IDLE instead of regular polling |
| `MessageChannel` | Passes Spring Integration messages between steps |
| `IntegrationFlow` | Describes a pipeline using the Java DSL |
| `MessageHandler` / `@ServiceActivator` | Processes messages in a flow |
| `jakarta.mail.Message` / `MimeMessage` | Actual email and MIME objects |

**Distinguish the two `Message` classes:**

- `org.springframework.messaging.Message<?>` is the Spring Messaging message, consisting of a payload and integration flow headers.
- `jakarta.mail.Message` is the mail-protocol message; `MimeMessage` is the common implementation for MIME content.

In an inbound flow, the Spring message's **payload** may be a Jakarta Mail object, or content already transformed by the receiver/transformer, depending on configuration. Do not assume every handler always receives a `String`.

### 3.1. A Mail Receiver Is Not a Mail Sender

`JavaMailSender` has no API to poll an inbox. Adding the `spring-boot-starter-mail` dependency for sending email **does not automatically create an inbox receiver**. The inbound side requires **Spring Integration Mail** components and explicit flow configuration.

### 3.2. Pollable Message Source and Message-Driven Adapter

With polling:

~~~text
Poller
  -> MailReceivingMessageSource.receive()
      -> ImapMailReceiver
          -> Spring Message payload
              -> channel/handler
~~~

With IDLE:

~~~text
ImapIdleChannelAdapter
  -> ImapMailReceiver / IDLE connection
      -> channel
          -> handler
~~~

The two approaches differ in **how reception is triggered**, while downstream business processing after the channel can be reused.

## 4. Dependencies and Versions

With Spring Boot/Spring Integration using Jakarta Mail:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

If using Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mail</artifactId>
</dependency>
~~~

Typically, **Spring Boot dependency management** is used to align Spring Integration, Spring Framework, and Jakarta Mail/Angus Mail versions. For projects not using Boot, declare compatible dependency management and mail implementations explicitly.

**Namespace distinction:**

- Spring Framework 6 / Spring Boot 3 and corresponding Spring Integration versions use `jakarta.mail.*`.
- Older Spring/JavaMail projects may use `javax.mail.*`.

Never mix `javax.mail` and `jakarta.mail` arbitrarily in the same application; that can cause class/method errors and incompatible dependencies.

**Version note:** Builder or method names in the Java DSL may vary across Spring Integration generations. When applying the code below, use the API of your exact library version and verify against its reference documentation.

## 5. IMAPS Polling Example in Spring Boot

The following example chooses **IMAPS polling**, an easy-to-understand model for building a first receiver.

### 5.1. Application Configuration

~~~yaml
app:
  mail:
    inbound:
      imap-url: ${INBOUND_IMAP_URL}
      poll-delay-ms: 15000
~~~

The `INBOUND_IMAP_URL` environment variable holds a test mailbox endpoint matching the Spring Integration Mail URL format. If the URL contains a username/password, it is a **secret** and must be managed as a secret; do not print it in logs or commit it to a repository. For passwords containing characters such as `@`, `/`, `:`, or `%`, encode them in the URL format required by the library rather than naively concatenating strings.

Illustrative example with credentials redacted:

~~~text
imaps://reader:<redacted>@mail.example.test:993/INBOX
~~~

This is not a real connection address.

### 5.2. Creating the Receiver and Flow

~~~java
package com.example.mail.inbound;

import java.time.Duration;
import java.util.Properties;

import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
@EnableIntegration
public class ImapInboundConfiguration {

    @Bean
    ImapMailReceiver imapMailReceiver(
            @Value("${app.mail.inbound.imap-url}") String imapUrl) {

        ImapMailReceiver receiver = new ImapMailReceiver(imapUrl);

        Properties properties = new Properties();
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "15000");
        properties.put("mail.imaps.ssl.checkserveridentity", "true");

        receiver.setJavaMailProperties(properties);

        // Illustrative config: read messages will be marked SEEN.
        // Production must define a durable ingest strategy first.
        receiver.setShouldMarkMessagesAsRead(true);
        receiver.setShouldDeleteMessages(false);

        return receiver;
    }

    @Bean
    IntegrationFlow imapInboundFlow(
            ImapMailReceiver receiver,
            InboundMailInspector inspector,
            @Value("${app.mail.inbound.poll-delay-ms:15000}")
                    long pollDelayMs) {

        MailReceivingMessageSource source =
                new MailReceivingMessageSource(receiver);

        return IntegrationFlow
                .from(source, endpoint -> endpoint.poller(
                        Pollers.fixedDelay(
                                Duration.ofMillis(pollDelayMs))
                                .maxMessagesPerPoll(10)))
                .handle((payload, headers) -> {
                    inspector.inspect((MimeMessage) payload);
                    return null; // Terminal handler: produces no new output.
                })
                .get();
    }
}
~~~

### 5.3. Handler Reading Only Metadata Safely

~~~java
package com.example.mail.inbound;

import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.stereotype.Component;

@Component
public class InboundMailInspector {

    public void inspect(MimeMessage mimeMessage) {
        try {
            String subject = mimeMessage.getSubject();
            Address[] from = mimeMessage.getFrom();
            String messageId = mimeMessage.getMessageID();

            // In practice: create an inbound job and persist minimal metadata.
            // Example only illustrates reading; avoid logging body/PII.
            String safeType = subject == null
                    ? "no-subject" : "has-subject";

            System.out.println(
                    "Received mail: type=" + safeType
                    + ", hasFrom=" + (from != null && from.length > 0)
                    + ", hasMessageId=" + (messageId != null));

        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot inspect inbound mail", ex);
        }
    }
}
~~~

**This is a starter example, not a production pipeline with exactly-once guarantees.** The example marks messages as read to avoid repeatedly polling them; if the handler fails after a message has already been marked `SEEN`, the message may no longer appear in the next unread search. Production needs a **persist durably before acknowledging receipt** strategy and proper scanning/recovery mechanisms.

### 5.4. Step-by-Step Explanation

1. `ImapMailReceiver` manages mailbox access.
2. `setJavaMailProperties` configures timeouts and TLS server identity verification.
3. `MailReceivingMessageSource` serves as the source polled to fetch messages.
4. `Pollers.fixedDelay(...)` determines the interval between polling runs.
5. `maxMessagesPerPoll(10)` caps the number of messages polled in one cycle per endpoint semantics; it does not replace overall mailbox or attachment size limits.
6. The handler receives a `MimeMessage` payload in this illustrative setup.
7. `return null` marks a terminal processing step, emitting no further output message.

Do not use an excessively short poll interval when unnecessary: mailbox providers enforce connection/rate limits, and excessive polling increases load.

### 5.5. Points to Verify Against Your Version and Provider

- Mail URLs can contain credentials; Spring Integration offers authenticator/connection configuration options depending on the API/version. When using rotating credentials or OAuth, prefer configuration that avoids exposing credentials in URLs.
- MIME payloads may be lazy-loaded from the folder. If the handler needs to traverse body content/attachments, ensure **the folder remains open while reading**, or materialize the content into a DTO/byte storage during reception.
- Settings like `shouldMarkMessagesAsRead` and `shouldDeleteMessages` control receiver side effects; do not treat them as business transaction commits.
- When multiple receiver beans exist, use `@Qualifier` or explicit bean names to avoid wiring the wrong one.

## 6. Polling Interval, Batch Size, and Backpressure

Polling must balance latency against load:

~~~text
Polling every 1 second:
  + fast response
  - many requests, sockets, and CPU usage

Polling every 60 seconds:
  + lower connection frequency
  - mail may wait longer
~~~

### 6.1. Operational Parameters

| Parameter | Impact |
| --- | --- |
| `fixedDelay` / `fixedRate` | When the next poll runs |
| `maxMessagesPerPoll` | Number of receives per poll cycle |
| Worker concurrency | Number of messages processed in parallel |
| IMAP connection/read timeout | Network wait limits |
| Search criteria | Number of messages to inspect |
| Attachment limits | RAM, disk, and I/O limits |
| Queue capacity | Cap on pending work items |
| Retry policy | How transient failures are retried |

**Do not confuse `maxMessagesPerPoll` with payload size limits.** A single message with hundreds of MB of attachments can still overwhelm processing even when polling one message at a time.

### 6.2. Decouple Mail Reception from Expensive Processing

Do not let an IMAP poller synchronously wait for OCR, slow API calls, or large PDF processing before ingesting the next email.

A generally better architecture:

~~~text
IMAP receiver
  |
  v
Validate + extract metadata/content within limits
  |
  v
Durable inbox store / queue
  |
  +-- publish accepted inbound job
  |
  v
Background business workers
  |
  v
Ticket / invoice / workflow
~~~

The receiver focuses on **safe and durable ingestion**, while business workers process asynchronously. If the queue/storage becomes overloaded, apply backpressure or slow down polling to avoid exhausting memory/disk.

## 7. IMAP IDLE with an Inbound Channel Adapter

When the mailbox server supports IDLE and near real-time processing is required, Spring Integration provides `ImapIdleChannelAdapter`.

Model:

~~~text
IMAP server
   |
   | IDLE notification
   v
ImapIdleChannelAdapter
   |
   v
MessageChannel
   |
   v
@ServiceActivator / message handler
~~~

### 7.1. Java Configuration

One way to organize with the component API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.ImapIdleChannelAdapter;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.messaging.MessageChannel;

@Configuration
public class ImapIdleConfiguration {

    @Bean
    MessageChannel inboundMailChannel() {
        return new DirectChannel();
    }

    @Bean
    ImapIdleChannelAdapter imapIdleAdapter(
            ImapMailReceiver receiver,
            MessageChannel inboundMailChannel) {
        ImapIdleChannelAdapter adapter =
                new ImapIdleChannelAdapter(receiver);
        adapter.setOutputChannel(inboundMailChannel);
        return adapter;
    }
}
~~~

Handler:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import jakarta.mail.internet.MimeMessage;

@Component
public class IdleInboundHandler {

    private final InboundMailInspector inspector;

    public IdleInboundHandler(InboundMailInspector inspector) {
        this.inspector = inspector;
    }

    @ServiceActivator(inputChannel = "inboundMailChannel")
    public void handle(Message<?> springMessage) {
        inspector.inspect((MimeMessage) springMessage.getPayload());
    }
}
~~~

This is **an alternative configuration to a polling flow**, not something to run in parallel with a poller on the same `ImapMailReceiver`. If the application chooses IDLE, activate only the appropriate IDLE endpoint to prevent two consumers from competing over the same mailbox state.

### 7.2. IDLE Does Not Replace Rescanning

Servers may:

- drop IDLE when the allowed duration expires;
- close connections during maintenance;
- send notifications while the client loses network connectivity;
- enforce quotas or connection count limits;
- alter folder state unexpectedly.

The application needs reconnect capability and **periodic reconciliation**: re-scanning from a checkpoint/UID or appropriate state window to find potentially missed mail, while relying on idempotency to avoid creating duplicate tickets.

Never expect IDLE to guarantee "exactly-once, zero missed mail".

## 8. IMAP Flags: SEEN, DELETED, and Processing Acknowledgment

IMAP manages flags on individual messages. Common flags:

| Flag | Common Meaning | Notes |
| --- | --- | --- |
| `\Seen` | Message has been read/marked read | Does not mean business processing finished |
| `\Deleted` | Message marked for deletion | May require expunge depending on server behavior |
| `\Flagged` | Message flagged | Meaning depends on workflow |
| User-defined flag | Custom flags allowed if server supports them | Not supported by all servers |

Receiver options such as `shouldMarkMessagesAsRead` and `shouldDeleteMessages` mutate messages in the mailbox. **They are not transactional ACKs tied to the application database.**

### 8.1. The "Marked Read = Processed" Trap

~~~text
T1 Receiver downloads email M1
T2 Receiver marks M1 as SEEN
T3 Handler creates ticket, but database fails
T4 Application crashes
T5 Next poller searches only UNSEEN
T6 M1 is never processed again
~~~

If messages are searched only by unread status, the system can **drop** M1. Conversely, if `SEEN` is never set, the poller may re-read M1 on every cycle and create duplicate tickets.

No single flag configuration solves every scenario; combine **durable inbox + idempotency + flag/checkpoint rules**.

### 8.2. A More Reliable Strategy

~~~text
1. Receive email M1
2. Determine stable identifying key within mailbox scope
3. Persist inbound record + required content durably
4. Commit inbound store transaction
5. Update mailbox flag/checkpoint per policy
6. Worker processes inbound record idempotently
7. Record status PROCESSED or FAILED
~~~

If a crash occurs after step 4 and before step 5, the next scan may pick up M1 again. A **unique constraint/upsert** in the inbound store prevents creating a duplicate record. This is usually far preferable to assuming a `SEEN` flag means processing completed.

### 8.3. Deleting Messages from the Mailbox?

Do not automatically enable `shouldDeleteMessages=true` for important emails without a retention and recovery strategy. With IMAP, `\Deleted` may require an expunge for physical deletion; exact behavior also depends on the receiver, folder mode, and server. With POP3, deletion semantics differ from IMAP and are typically applied at the protocol session level.

A generally safer approach:

- retain messages in the mailbox for a retention window;
- flag/move them after successful ingestion;
- purge messages via a separate audited retention job;
- never delete before essential data/attachments are durably stored.

If policy mandates early deletion due to sensitive data, you still must define the commit point and error recovery plan.

## 9. Idempotency and Message Identification

An email may be read more than once due to:

- application restarts;
- IMAP connection drops and reconnects;
- `SEEN` flags changed by a human or another client;
- receivers running across multiple replicas;
- reconciliation jobs re-scanning;
- DB commit succeeding while flag update fails.

**Idempotency** is a core requirement for a production inbox processor.

### 9.1. Message-ID Is Not an Absolute Unique Key

An example `Message-ID` header looks like:

~~~text
Message-ID: <opaque-id@sender.example>
~~~

It is useful for correlation and threading, but:

- some emails lack a `Message-ID`;
- senders can generate invalid/non-unique IDs;
- the same message can appear in multiple mailboxes;
- the header can be spoofed;
- forwarded/imported content may retain an old ID.

Therefore, do not rely solely on `Message-ID` as a system-wide unique key without understanding its scope and edge cases.

### 9.2. IMAP UID and UIDVALIDITY

IMAP assigns a UID to each message in a folder. A UID is meaningful together with the folder's **UIDVALIDITY**: if `UIDVALIDITY` changes, an old numeric UID may no longer refer to the same message.

A typical technical key includes:

~~~text
mailbox_account_id
folder_identifier
uid_validity
message_uid
~~~

When using Jakarta Mail, IMAP folders may support `UIDFolder`:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public record ImapIdentity(
        long uidValidity,
        long uid) {
}

static ImapIdentity identityOf(Message message)
        throws Exception {
    Folder folder = message.getFolder();
    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Folder does not support IMAP UID");
    }

    return new ImapIdentity(
            uidFolder.getUIDValidity(),
            uidFolder.getUID(message));
}
~~~

**Important:** this example must be called **while the folder/connection is still open and the message is still valid**. A `MimeMessage` detached from a closed IMAP folder may not allow querying the UID. Thus, UID extraction should happen inside the ingestion/receiver stage that has folder access, not arbitrarily inside an async worker running minutes later.

UIDs are scoped **per mailbox/folder**; when moving a message to another folder, account for the new UID. In production, use a composite key including account and folder, not just a bare integer UID.

### 9.3. POP3 UIDL

Some POP3 servers support UIDL to identify messages across sessions. Availability and stability characteristics depend on the provider/implementation. Without a reliable UIDL, use an alternative such as controlled message metadata/hashing, while accepting that deduplication may not be perfect.

Do not use **message sequence numbers** inside a folder as durable identifiers across polls and mailbox changes.

### 9.4. Inbound Deduplication Table

PostgreSQL design example:

~~~sql
CREATE TABLE inbound_mail (
    inbound_id        UUID PRIMARY KEY,
    mailbox_account   VARCHAR(120) NOT NULL,
    folder_id         VARCHAR(250) NOT NULL,
    uid_validity      BIGINT NOT NULL,
    message_uid       BIGINT NOT NULL,
    rfc_message_id    VARCHAR(1000),
    subject_summary   VARCHAR(300),
    state             VARCHAR(40) NOT NULL,
    received_at       TIMESTAMPTZ NOT NULL,
    ingested_at       TIMESTAMPTZ NOT NULL,
    processed_at      TIMESTAMPTZ,
    UNIQUE (
        mailbox_account,
        folder_id,
        uid_validity,
        message_uid
    )
);
~~~

This model is **for IMAP sources with valid UIDs**, not a schema to apply verbatim to POP3. You can add storage key fields for MIME/attachments and retention settings. `subject_summary` can contain PII, so it requires appropriate access control and retention limits.

One ingestion pattern:

~~~sql
INSERT INTO inbound_mail (
    inbound_id,
    mailbox_account,
    folder_id,
    uid_validity,
    message_uid,
    state,
    received_at,
    ingested_at
)
VALUES (
    :id,
    :account,
    :folder,
    :uid_validity,
    :uid,
    'INGESTED',
    :received_at,
    CURRENT_TIMESTAMP
)
ON CONFLICT (
    mailbox_account,
    folder_id,
    uid_validity,
    message_uid
) DO NOTHING;
~~~

If the insert creates no new row, the message was already ingested under the same UID scope. Do not unconditionally create a new ticket. Emitting business events should be tied to the inbound record's transaction/outbox to prevent creating two tickets.

### 9.5. Two Consumers Reading the Same Mailbox

If multiple replicas poll a mailbox, both may receive the same email:

~~~text
Pod A: finds M1
Pod B: finds M1
Pod A: INSERT inbound record -> success
Pod B: INSERT same unique key -> conflict / no-op
~~~

The unique constraint prevents duplicate processing at the data layer. However, two pods still generate extra traffic and can contend on IMAP flags/connections. For critical mailboxes, it is usually better to have a **leader/lease or a single active consumer** at any given time, combined with durable deduplication.

Do not rely on `@Scheduled` or `@EnableIntegration` automatically creating a distributed lock across instances.

## 10. Managing Folders and the MimeMessage Lifecycle

A `MimeMessage` read from IMAP may remain backed by data on the server. Some content/attachment parts may be loaded **lazily** when `getContent()` or `getInputStream()` is called.

Example:

~~~text
IMAP receiver reads metadata
   |
   v
Passes MimeMessage to async worker
   |
   v
Receiver closes IMAP Folder
   |
   v
Worker calls getInputStream() on attachment
   |
   v
FolderClosedException / I/O error
~~~

### 10.1. Do Not Pass Raw MimeMessage Across a Durable Queue

A queue/database typically needs a **materialized** payload:

~~~text
InboundMailRecord {
  mailboxId,
  sourceMessageKey,
  fromAddress,
  subject,
  receivedAt,
  textBodyStorageRef,
  attachmentStorageRefs,
  state
}
~~~

While the receiver still has folder access:

1. Read MIME within size limits.
2. Convert needed data into DTOs/bytes/storage objects.
3. Close streams and persist data durably.
4. Commit the inbound record.
5. Only afterward let async workers use the storage references.

Never retain a `MimeMessage` bound to a closed folder inside a long-lived queue.

### 10.2. The autoCloseFolder Option

Some Spring Integration Mail versions provide a configuration option for automatically closing the folder after the receiver receives a message. You may need to adjust folder lifecycle handling when reading MIME content downstream of the adapter.

**Do not simply disable auto-closing the folder to "fix errors" and forget cleanup.** Holding a folder open too long can exhaust connections or fail when the server times out. Choose a design that reads/materializes content at the right stage, and verify the semantics of your Spring Integration version.

### 10.3. Closing InputStreams

When reading attachments:

~~~java
try (var input = bodyPart.getInputStream()) {
    // Stream bytes into size-bounded storage.
}
~~~

Always use size-bounded streaming; never call `readAllBytes()` unconditionally on emails from the Internet without knowing the size beforehand.

## 11. Reading MIME Structure Safely

An email may contain:

~~~text
MimeMessage
  |
  +-- multipart/mixed
        |
        +-- multipart/alternative
        |     +-- text/plain
        |     +-- text/html
        |
        +-- application/pdf; attachment
        +-- image/png; inline; Content-ID
~~~

Never assume every email is a `String`. `MimeMessage.getContent()` can return a `String`, `Multipart`, or another object depending on the MIME part and implementation.

### 11.1. Traversing Content Parts

Illustrative utility:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeWalker {
    private MimeWalker() {}

    public static void walk(Part part, int depth)
            throws Exception {
        if (depth > 12) {
            throw new IllegalArgumentException(
                    "MIME nesting limit exceeded");
        }

        if (part.isMimeType("multipart/*")) {
            Multipart parts = (Multipart) part.getContent();
            if (parts.getCount() > 100) {
                throw new IllegalArgumentException(
                        "Too many MIME parts");
            }
            for (int i = 0; i < parts.getCount(); i++) {
                walk(parts.getBodyPart(i), depth + 1);
            }
            return;
        }

        if (part.isMimeType("text/plain")) {
            // Read text with size limits and proper charset.
            return;
        }
        if (part.isMimeType("text/html")) {
            // Never render untrusted HTML in an admin page.
            return;
        }

        // Attachment/inline/other content: check MIME type,
        // size, disposition, filename, then stream to storage.
    }
}
~~~

This utility only demonstrates **depth and part-count control**. It does not yet enforce total byte limits, decompression ratios, character decoding, nested `message/rfc822`, signed/encrypted email handling, or malware scanning. For untrusted inputs, add the corresponding protections.

### 11.2. Untrusted HTML Email

HTML emails may contain:

- scripts or markup causing XSS if rendered directly;
- remote images/tracking URLs;
- deceptive links;
- unusual CSS/HTML;
- attachments with spoofed content types.

If displaying received content in a support dashboard, sanitize HTML, isolate the rendering environment, control remote resources, and normalize links. Never assume email from a trusted mailbox is browser-safe.

### 11.3. Filenames and Attachment Path Traversal

Never write:

~~~java
Path target = uploadDir.resolve(part.getFileName());
Files.copy(part.getInputStream(), target);
~~~

without validating the filename. An attachment may declare:

~~~text
../../config/application.yml
C:\Windows\...
invoice.pdf/../secret.txt
~~~

Instead, generate a **server-assigned storage key**, such as a UUID, and keep the original filename only as sanitized metadata:

~~~java
Path target = uploadDir.resolve(
        UUID.randomUUID().toString() + ".bin");
~~~

Then verify that the normalized path stays inside the designated directory, enforce size limits, set file permissions, and handle symlinks per your environment. Never use a sender-supplied filename directly as a write path.

### 11.4. Attachments Can Contain Malware

When receiving PDFs, Office documents, ZIPs, or other files:

- enforce per-file and total message size limits;
- limit attachment count and multipart depth;
- verify the actual file format instead of trusting `Content-Type`;
- scan for malware if the application stores or distributes files;
- avoid auto-execution or unbounded auto-extraction;
- cap decompressed size to defend against zip bombs;
- store files in a non-executable location;
- never expose files publicly before passing inspection policy.

The receiver is a **trust boundary**: every `From`, `Subject`, MIME header, and attachment is external input.

## 12. Sender Authentication and Preventing Spoofed Emails

A sender can set:

~~~text
From: invoices@trusted-partner.example
~~~

but the `From` value **is not cryptographic proof of identity**. When using email to trigger sensitive business logic:

- check SPF/DKIM/DMARC results from a trusted receiving mail system;
- understand that `Authentication-Results` can be inserted at multiple hops; trust only headers generated by your trusted receiving infrastructure;
- treat sender/domain allowlist matching as one layer of defense, not the sole guarantee;
- use document signatures/S/MIME/PGP or out-of-band verification when required by the workflow;
- avoid automatically approving payments or changing permissions based solely on the `From` address;
- verify business correlation IDs securely.

Unsafe example:

~~~text
Email From: finance@partner.example
Subject: Approve payment
Body: Please transfer money to new account.
~~~

If the application automatically updates payment details based solely on `From` and `Subject`, an attacker can spoof the email. Require independent approval/verification rules for high-risk actions.

## 13. Authentication, TLS, and OAuth2 for IMAP

The receiver must authenticate with the mail server and protect content in transit.

### 13.1. IMAPS/POP3S

Example parameters:

~~~text
IMAPS: protocol=imaps, implicit TLS, usually port 993
POP3S: protocol=pop3s, implicit TLS, usually port 995
IMAP STARTTLS: usually port 143, if supported by provider
~~~

Properties for IMAPS use the `mail.imaps.` prefix:

~~~properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=15000
mail.imaps.ssl.checkserveridentity=true
~~~

For IMAP using STARTTLS instead of implicit TLS, properties belong to the `imap` protocol and must configure required STARTTLS/hostname verification per provider documentation. Do not copy `mail.imaps.*` verbatim onto an `imap` connection assuming it applies.

### 13.2. Never Disable Certificate Verification

Never install a trust-all socket factory to "make tests or production work". The right approach is:

- use the correct hostname and port;
- verify the certificate chain;
- configure an appropriate truststore;
- investigate any TLS inspection/proxy;
- update CA certificates if needed.

Received emails and mailbox credentials can contain sensitive data; invalid TLS can allow server impersonation.

### 13.3. OAuth2/XOAUTH2

Many providers restrict Basic Authentication for IMAP/POP3. They may require OAuth 2.0 with SASL XOAUTH2 or another mechanism.

Conceptual flow:

~~~text
Identity provider
   |
   | token with mailbox scope/audience
   v
AccessTokenProvider
   |
   v
Jakarta Mail IMAP authentication (XOAUTH2)
   |
   v
Spring Integration IMAP receiver
~~~

You must verify:

- the provider genuinely supports IMAP OAuth for that account/tenant type;
- scopes, token audience, and mailbox identity;
- whether delegated or app-only flow is allowed;
- token expiry, refresh, and revocation;
- updating credentials when connections reconnect;
- which SASL/auth mechanisms the mail provider version supports.

**Never use a token from another API as an IMAP password** when the audience/scope does not match. Never write access tokens to logs, exception text, or mail headers. If the provider only supports an HTTP API with proper permissions, consider using the API instead of IMAP.

### 13.4. Secrets Must Not Live in Source Code

Never hardcode:

~~~java
new ImapMailReceiver(
    "imaps://real-user:real-password@mail.example.com:993/INBOX");
~~~

This is an example of **what not to do**. In production, use a secret manager, managed identity if supported by the provider, or framework credential mechanisms. If URLs are constructed from secrets, avoid logging full URLs and watch out for special characters/encoding.

## 14. Error Classification and Retry Strategies

Not all mail-receiving errors should be handled the same way.

| Error | Examples | Handling Direction |
| --- | --- | --- |
| Authentication | Expired credentials, revoked OAuth permissions | Alert, refresh/rotate validly; do not hot-loop retry |
| TLS/certificate | Hostname mismatch, untrusted chain | Stop connecting, fix trust/config |
| Network | Timeouts, connection resets | Retry with backoff and jitter |
| Folder unavailable | INBOX/folder renamed or lacking permissions | Verify config/permissions |
| MIME parse error | Corrupt multipart, invalid charset | Quarantine or mark processing failed |
| Attachment limit | Oversized file, too many parts | Quarantine/reject per policy |
| Business validation | Insufficient data to create a ticket | Route to dead-letter/manual review |
| Database failure | Unable to persist inbound record | Retry ingestion; do not ack/delete mail |
| Duplicate message | UID already has a record | No-op or check record status |

### 14.1. Receiver Errors Differ from Handler Errors

~~~text
Receiver connect/search/read failure
  -> no message received
  -> reconnect/backoff, alert mailbox health

Handler parsing/business failure
  -> message already entered the flow
  -> record error + quarantine/retry
~~~

If a received message was already marked `SEEN` before the handler failed, retrying solely by waiting for the next IMAP unread poll may not work.

### 14.2. Bounded Retries

Do not retry a corrupt MIME message, malicious attachment, or invalid business request indefinitely. You can use:

~~~text
INGESTED -> PROCESSING
           |
           +-- PROCESSED
           +-- RETRY_WAIT -> PROCESSING
           +-- QUARANTINED / FAILED_FINAL
~~~

Store attempt count, next retry time, error class, and correlation ID. Quarantine should retain minimal data sufficient for investigation while complying with access control and retention policies.

### 14.3. Error Channels in Spring Integration

Spring Integration provides error messages/error channels for certain endpoints and flows. When using them, clarify:

- are synchronous errors thrown back to the poller or routed to the error channel?
- are the original message and exception persisted durably?
- does the error handler perform retries or merely log?
- does one exception halt the entire flow or only one message?

**An error channel does not automatically create a transaction across IMAP flags and the database.** It is an error-handling mechanism for the messaging pipeline; idempotency and durable state still must be designed.

## 15. Account and Tenant Isolation Across Multiple Mailboxes

A SaaS application may read mailboxes such as:

~~~text
tenant-a -> support-a@...
tenant-b -> invoices-b@...
tenant-c -> claims-c@...
~~~

Each mailbox has its own:

- provider/host/port;
- credentials/tokens;
- folder/search policy;
- cursor/UIDVALIDITY/checkpoint;
- quotas, rate limits, and retention.

Never take the email's `From` header as the tenant ID: senders can spoof it. Tenant identity should be determined from the **preconfigured mailbox account** or verified routing.

### 15.1. One Receiver per Mailbox?

Creating a separate receiver/flow per mailbox works when the count is small. With thousands of tenants, holding one IDLE connection per mailbox can exceed provider limits and consume excessive memory, threads, and sockets.

Alternative strategies:

- schedulers grouping mailboxes and polling with bounded concurrency;
- balancing mailboxes across worker shards;
- managed dynamic receiver lifecycles;
- provider inbound webhooks/APIs where suitable;
- a shared mailbox with routing based on verified destination addresses when the business model allows.

### 15.2. Never Share Sessions/Credentials Across the Wrong Tenant

You must isolate:

- credentials and OAuth tokens;
- mailbox UIDs/checkpoints;
- inbound deduplication keys;
- attachment storage;
- event logs;
- content viewing permissions.

If tenant A's receiver routes a message to tenant B's handler due to misconfiguration, the result can be a data leak. Testing mailbox-to-tenant mapping is a critical part of integration tests.

## 16. Avoiding Auto-Reply Loops and Email Storms

A receiver might create a ticket and automatically send a reply:

~~~text
Customer email -> inbound receiver
   -> ticket created -> automatic reply
   -> customer auto-responder
   -> inbound receiver
   -> new reply ...
~~~

To reduce the risk:

- detect automated notices via `Auto-Submitted`, `Precedence` headers, and provider characteristics, without treating a single header as a perfect signal;
- use correlation IDs / threading such as `In-Reply-To` and `References`;
- never reply to every bounce or delivery status notification with a new email;
- cap auto-replies per conversation/recipient/time window;
- recognize the system's own sending addresses;
- enforce sender policies and rate limits;
- include a kill switch for inbound-triggered outgoing mail.

Do not use a subject containing "Re:" as sole proof that an email belongs to an existing ticket; threading headers may be missing or forged.

## 17. Observability and Operating the Receiver

Useful metrics:

| Metric/Signal | Meaning |
| --- | --- |
| `inbound_mail_poll_total` | Number of polling runs |
| `inbound_mail_poll_error_total` | Polling/connection errors |
| `inbound_mail_received_total` | Messages read by the receiver |
| `inbound_mail_ingested_total` | Messages persisted as inbound records |
| `inbound_mail_duplicate_total` | Deduplicated messages |
| `inbound_mail_processing_failed_total` | Business processing failures |
| `inbound_mail_quarantined_total` | Quarantined messages |
| `inbound_mail_processing_duration_seconds` | Processing duration |
| `inbound_mail_oldest_pending_age_seconds` | Age of the oldest pending inbound job |
| `inbound_mail_attachment_bytes` | Received size, using an appropriate histogram/summary |
| `inbound_mail_last_success_timestamp_seconds` | Timestamp of the most recent successful receive/ingest |

These names are **suggested application-instrumented metric names**, not all built-in metrics automatically provided by Spring Integration.

### 17.1. Bounded Metric Tags

Recommended:

~~~text
mailbox_profile=support_primary
protocol=imaps
stage=poll|ingest|process
result=ok|error|duplicate
error_class=auth|tls|network|mime|storage|unknown
~~~

Do not use raw `From`, `Subject`, `Message-ID`, recipient emails, UIDs, or every dynamic tenant ID as metric labels. Detailed data belongs in access-controlled logs/DBs.

### 17.2. Health Dashboard

~~~text
Mailbox receiver health
------------------------------------------------
Receiver connected: YES
Last successful poll: 15 seconds ago
Last successful ingest: 40 seconds ago
Inbox messages observed: 320
New inbound jobs: 12 in last 5 minutes
Processing retry backlog: 8
Quarantined: 2 today
Connection errors: 0 in last 1 hour
------------------------------------------------
~~~

Numbers are illustrative only. For low-traffic mailboxes, "no new emails received in an hour" **is not automatically an incident**. Combine polling health, connection status, and expected traffic.

### 17.3. Alerts

- Receiver suffering repeated authentication failures.
- IMAP IDLE unable to reconnect or polling stalled for a long time.
- Mailbox nearing full/rising quota, if exposed by provider.
- Inbound jobs pending unusually long.
- Sudden spikes in MIME parse errors/quarantines.
- Attachment/storage persistence errors.
- One tenant/mailbox receiving abnormal traffic spikes.
- Processing workers backed up, causing backpressure on ingestion.

Never output raw emails, attachments, tokens, or personal data in alerts.

## 18. Integration Testing with a Mock SMTP + IMAP Server

Unit tests for handlers can construct an in-memory `MimeMessage`. However, to test that **the receiver actually connects over IMAP and reads a mailbox**, use integration tests with a test mail server supporting IMAP, such as GreenMail.

Model:

~~~text
JUnit test
   |
   +-- start GreenMail SMTP + IMAP
   |
   +-- send fixture email to SMTP test server
   |
   +-- Spring Integration ImapMailReceiver polls inbox
   |
   +-- handler writes inbound record / test sink
   |
   +-- assert metadata, MIME, state, dedupe
   |
   +-- stop flow/server + cleanup DB/files
~~~

### 18.1. Test Layers

| Test Type | Target |
| --- | --- |
| Unit test MIME parser | `String`/`Multipart`, attachments, charset, MIME errors |
| Unit test classification | `From`, subject, correlation, validation rules |
| Unit test deduplication | Unique key/`UIDVALIDITY`, duplicate no-op |
| Integration test IMAP | Connect, poll, flags, folder lifecycle |
| Integration test IDLE | Notification/reconnect and rescan behavior |
| Integration test DB/outbox | Commit, retry, crash between ingest/ack |
| Provider sandbox test | Actual TLS/auth/OAuth, quotas, folder behavior |

### 18.2. Important Test Cases

1. Empty mailbox: receiver creates no inbound job.
2. One new email: accurately reads `From`, `Subject`, and body.
3. Email with HTML and plain text: parser extracts both properly.
4. Email with multiple attachments: handles within limits and stores properly.
5. Email missing `Message-ID`: does not crash repeatedly.
6. Email with Unicode/various charsets: decodes appropriately.
7. Mailbox containing already-read messages: search/flag behavior matches policy.
8. Database fails after receiving: email is not lost.
9. Same email read twice: does not create duplicate tickets.
10. Two receivers running concurrently: dedupe/lease works.
11. IMAP folder closed before reading attachment: detects and handles lifecycle.
12. IDLE connection dropped: reconnects and reconciles.
13. Expired credentials/token: auth error classified, no tight-loop retries.
14. Malicious attachment filename or oversized file: quarantined, no path traversal.
15. Spoofed `From` email: does not automatically trigger sensitive actions.

### 18.3. Test with Conditions Instead of Fixed Sleeps

Avoid:

~~~java
Thread.sleep(3000);
assertEquals(1, inboundRepository.count());
~~~

Timing depends on the machine and CI. If using Awaitility in tests:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals(
            1,
            inboundRepository.countByMailboxProfile(
                    "support_primary")));
~~~

`await()` is an example of the Awaitility API when the project has the corresponding dependency. Conditions should check records for the **current test**, not count the entire mailbox/DB if fixtures are shared.

### 18.4. Cleanup

Integration tests must clean up:

- IMAP/SMTP test servers or containers per their owner;
- mailbox messages and flags;
- inbound DB records / queue jobs;
- background schedulers/async workers;
- attachments/temp files/streams;
- Spring contexts bound to dynamic ports if contexts are cached.

Do not purge the entire mailbox in `@AfterEach` if other tests share the same server and run in parallel. Prefer per-test fixtures, separate accounts/recipients, or test correlation IDs.

## 19. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `JavaMailSender` to read inbox | Wrong API/protocol | Use Spring Integration Mail receiver |
| Adding only mail starter and expecting auto-receive | No inbound flow | Configure receiver and endpoint |
| Confusing `org.springframework.messaging.Message` with Jakarta `Message` | Cast/type errors | Distinguish wrapper and payload |
| Marking `SEEN` before durable ingest and treating as ack | Can lose processing on crash | Durable inbox + reconciliation |
| Not marking or checkpointing anything | Re-polling creates duplicate tickets | Idempotency and read/flag policy |
| Using IMAP sequence number as permanent ID | Wrong after folder changes | UID + `UIDVALIDITY` + folder + account |
| Using only `Message-ID` as unique key | Missing/duplicate/spoofed | Key based on mailbox and UID |
| Passing `MimeMessage` tied to closed folder to async worker | `FolderClosedException` | Materialize content during reception |
| Using IDLE assuming zero lost notifications | Can miss emails | Reconnect and periodic rescan |
| Multiple pods polling without dedupe | Duplicate processing | Lease/leader + unique constraint |
| Loading all attachments into RAM | `OutOfMemoryError` | Streaming + size limits |
| Using original filename as filesystem path | Path traversal/overwrite | Safe storage key |
| Rendering HTML email directly | XSS/tracking | Sanitize and isolate rendering |
| Trusting `From` header for approvals | Email spoofing | Additional business identity verification |
| Disabling TLS hostname verification to fix errors | Credentials/data can be exposed | Fix CA/truststore/endpoint |
| Polling too fast without backpressure | Quotas, high load | Rate limiting, queue capacity |
| Retrying malformed MIME infinitely | Poison message stalls flow | Quarantine/`FAILED_FINAL` |
| Not closing server/folder/streams in tests | Leaks/socket conflicts | Lifecycle management per owner |
| Logging raw emails and tokens | Sensitive data exposure | Minimal metadata, access control |

## 20. End-to-End Scenario: Support Mailbox Creating Tickets

Suppose an application has a `support@example.com` mailbox. Each customer email is processed into a support request.

### 20.1. Architecture

~~~mermaid
flowchart TD
    A["Customer sends email"] --> B["Support mailbox"]
    B --> C["IMAP receiver"]
    C --> D["Extract UID + bounded MIME"]
    D --> E{"Already ingested?"}
    E -->|Yes| F["No-op / reconcile state"]
    E -->|No| G["Durable inbound_mail + content storage"]
    G --> H["Ticket processing queue"]
    H --> I{"Validation / processing"}
    I -->|Success| J["Ticket created"]
    I -->|Transient error| K["Retry wait"]
    I -->|Invalid/unsafe| L["Quarantine"]
    K --> H
~~~

### 20.2. A Normal Email

~~~text
Mailbox: support-primary
Folder: INBOX
UIDVALIDITY: 1008
UID: 5521
Message-ID: <opaque-id@customer.example>
From: customer@example.net
Subject: I cannot log in
Attachment: screenshot.png
~~~

Receiver:

1. Connects via IMAPS over TLS, authenticating with permitted credentials.
2. Searches for new messages per search policy.
3. While the folder is still open, extracts mailbox/folder/UIDVALIDITY/UID.
4. Reads and validates MIME within limits; stores attachment under a separate storage key.
5. Inserts the `inbound_mail` record with the corresponding unique key.
6. Commits the record and emits the ticket-creation job.
7. Updates mailbox flags/checkpoint per policy.
8. Worker creates the ticket, linking it to the inbound ID.

If the receiver crashes after step 6 and before step 7, the next scan may re-read the message. The unique key prevents creating a second ticket.

### 20.3. An Invalid Email

The email has:

~~~text
From: unknown@example.net
Attachment: ../../app-config.yml
Size: exceeds allowed limit
~~~

The application does not write the original filename to an arbitrary path, does not try to load everything into RAM, and does not create a ticket containing the dangerous file. It logs controlled metadata/quarantine events while avoiding an infinite loop on the same poison message.

### 20.4. IMAP Provider Error

When the server closes the connection:

1. The receiver classifies the network/folder error.
2. Applies backoff and reconnect instead of tight-looping immediately.
3. After recovery, reconciliation scans the mailbox by checkpoint.
4. Deduplication prevents creating duplicate tickets for previously ingested mail.
5. Dashboard reports the last successful poll timestamp, error counts, and backlog.

## 21. Pre-Production Checklist

### Protocol and Connectivity

- [ ] Choose IMAP polling, IMAP IDLE, or POP3 based on requirements.
- [ ] Host, port, folder, and URL verified with the provider.
- [ ] TLS/hostname verification enabled per the right protocol.
- [ ] Credentials/tokens reside in a secret store; rotation/refresh supported.
- [ ] Connection/read timeouts and reconnect/backoff configured.

### Ingestion and State

- [ ] Clear understanding of `SEEN`, `DELETED`, and the receiver's search mechanism.
- [ ] Read flag is not treated as proof of completed business processing.
- [ ] Durable inbound store exists before ack/checkpoint.
- [ ] Deduplication key includes mailbox/folder/UIDVALIDITY/UID for IMAP.
- [ ] Reconciliation strategy exists for crashes/IDLE disconnects.
- [ ] Guaranteed that two consumers do not corrupt the same mailbox.

### MIME and Security

- [ ] Content is read while folder is open or materialized into storage.
- [ ] Limits enforced on message bytes, MIME part count, and nesting depth.
- [ ] Attachments use server-generated storage names, never sender paths.
- [ ] Malware scanning/quarantine present as required.
- [ ] HTML from emails is never rendered directly without sanitization.
- [ ] `From`/`Subject` headers are not trusted for sensitive actions.
- [ ] Email bodies, tokens, or unnecessary PII are never logged.

### Business Processing

- [ ] State machine INGESTED/PROCESSING/PROCESSED/RETRY/QUARANTINED in place.
- [ ] Bounded retries distinguishing transient vs. permanent errors.
- [ ] Business worker is idempotent, preventing duplicate tickets/invoices.
- [ ] Backpressure exists if mailbox traffic or attachment sizes spike.
- [ ] Mechanisms exist to prevent auto-reply loops.
- [ ] Tenant identity is derived from verified mailbox/routing.

### Observability and Testing

- [ ] Poll errors, ingest success, duplicates, and pending age are measured.
- [ ] Alerts trigger when the receiver stops or authentication fails.
- [ ] Integration tests cover IMAP flags, UIDs, crash/retry, and IDLE reconnect.
- [ ] Tests cover malicious MIME, Unicode, oversized files, and duplicates.
- [ ] Test fixtures clean up mailboxes, DB, queues, and attachment files.

## 22. Key Takeaways

- **Spring Integration Mail** provides components for **receiving emails** over IMAP/POP3, distinct from `JavaMailSender` used for sending via SMTP.
- For polling, `MailReceivingMessageSource` and `ImapMailReceiver` work with a poller to feed emails into an integration flow.
- For IMAP IDLE, `ImapIdleChannelAdapter` receives change signals from the server, yet still requires reconnects and reconciliation.
- In Spring Integration, `Message<?>` wraps a payload; the payload can be a Jakarta `MimeMessage` or a converted form depending on configuration.
- `\Seen` and `\Deleted` are mailbox states, **not business processing transaction ACKs**.
- Production requires a **durable inbox, idempotency, and checkpoints**; IMAP UIDs must be paired with `UIDVALIDITY`, folder, and account.
- Never keep a `MimeMessage` tied to a closed folder in an async job; materialize needed data during the reception stage.
- Email content is untrusted input: limit sizes, sanitize HTML, validate attachments, and never trust `From` headers for risky operations.
- TLS, credential management, and OAuth configuration are part of receiver security.
- Distinguish connection/reception errors, MIME parse errors, and business errors so retries behave properly.

A mail receiver can start simply with a few Spring Integration beans, but a reliable email-receiving system must clearly define **when a message is persisted, how duplicate processing is prevented, when mailbox state is updated, and what happens when connections or handlers fail**. Designing these boundaries makes incoming email a stable input for tickets, invoices, and many other Spring application workflows.

### References

- **Spring Integration Reference — Mail Support:** inbound channel adapters, polling, IMAP IDLE, mail receivers, and search strategies.
- **Spring Integration API:** `ImapMailReceiver`, `Pop3MailReceiver`, `MailReceivingMessageSource`, `ImapIdleChannelAdapter`.
- **Spring Integration Reference — Java DSL / Polling Consumers:** `IntegrationFlow`, `Pollers`, message channels, and error handling.
- **Spring Framework Reference — Integration / Messaging:** `Message<?>`, message headers, and channel semantics.
- **Jakarta Mail API:** `Message`, `MimeMessage`, `Folder`, `UIDFolder`, `Multipart`, `Part`.
- **RFC 3501 — Internet Message Access Protocol Version 4rev1:** IMAP folders, flags, UIDs, and UIDVALIDITY (check protocol updates applicable to your provider).
- **RFC 9051 — Internet Message Access Protocol Version 4rev2:** IMAP4rev2.
- **RFC 2177 — IMAP4 IDLE command:** mailbox notifications via IDLE.
- **RFC 1939 — Post Office Protocol Version 3:** POP3 and UIDL.
- **RFC 5322 — Internet Message Format:** From, Subject, Message-ID, References, and headers.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** MIME multipart, content types, charsets, and attachments.
- **IMAP/OAuth documentation of your mailbox provider:** permissions, rate limits, connection policies, TLS, and token lifecycles.
