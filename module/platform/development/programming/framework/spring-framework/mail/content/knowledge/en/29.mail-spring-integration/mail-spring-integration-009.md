# Converting a Mail Message into a Domain Event

When building an application with **Spring Framework Mail** and **Spring Integration Mail**, you can receive emails from an IMAP/POP3 mailbox and feed them into automated workflows: creating customer support tickets, recording service requests, detecting replies, or syncing conversations with a CRM. However, **a received email is not automatically a trustworthy business event**. An email is external data in MIME format, whereas a domain event is structured, meaningful information validated by the system.

For example, a customer sends an email with Subject "Support request" and a body describing an error. At the mail-receiving layer, it is a **jakarta.mail.Message**. Through Spring Integration, it may appear as an **org.springframework.messaging.Message<?>** on a channel. Only after being parsed, normalized, validated, and linked to a domain aggregate can the system emit an event such as **SupportRequestReceived** or **CustomerReplyRecorded**.

This document progresses from email message structure, Spring Integration inbound adapters, MIME parsing, mapping, and validation to safely publishing domain events in the presence of multiple workers, retries, or network failures. Examples focus on **Spring Integration Mail with Jakarta Mail**; business classes like `SupportRequestReceived`, `InboundMailKey`, and repositories are **illustrative self-built models**, not built-in Spring Mail APIs.

> **Core principle:** Receiving an email is an event at the **integration boundary**. Only publish a **domain event** after a valid business decision has been made and the required outcome has been durably persisted. Separate **sender-controlled email headers** from **trusted sources of truth**, and never treat the `SEEN` flag or `Message-ID` as an exactly-once guarantee.

## 1. Distinguishing Mail Messages, Spring Messages, and Domain Events

Three types of "message" often appear together:

| Concept | Library/Class | Content | Role |
| --- | --- | --- | --- |
| **Mail message** | **jakarta.mail.Message** / `MimeMessage` | RFC 5322 headers, MIME parts, flags, addresses, body | Email data fetched from a mailbox |
| **Integration message** | **org.springframework.messaging.Message<T>** | Spring Integration channel payload and headers | Carries data between steps in a flow |
| **Domain event** | Application-defined class/record | Event ID, aggregate, business facts, time, correlation | Records a meaningful fact accepted by the domain |

Example:

~~~text
IMAP INBOX
   |
   v
jakarta.mail.internet.MimeMessage
   |
   v
Spring Integration inbound mail adapter
   |
   v
org.springframework.messaging.Message<?>
   |
   v
MIME parser / Normalizer
   |
   v
InboundMailCandidate (untrusted data)
   |
   v
Validation + Domain Application Service
   |
   +--> Reject / Quarantine / Needs review
   |
   '--> Persist domain state
               |
               v
          Domain Event
               |
               v
       Outbox / Event Publisher
~~~

### Do Not Confuse Classes Named Message in Java

These two classes are **different**:

~~~java
jakarta.mail.Message rawEmail;
org.springframework.messaging.Message<?> channelMessage;
~~~

When code needs both, import one and use the fully qualified name for the other to avoid collisions. Spring Message headers are managed by the message channel; they are not directly equivalent to email headers like **From**, **Subject**, **Message-ID**, and **Content-Type**.

### Domain Events Differ from "Commands" and "Raw Input Data"

**InboundMailReceived** may be an integration event stating "the mailbox received a message". **CreateSupportTicket** is a command asking the system to do something. **SupportTicketOpened** is a domain event describing what happened after the ticket was created.

Do not call every DTO produced after parsing an email a domain event. A domain event must represent **what the domain recognizes as having happened**, not what an email sender claims.

## 2. Business Example: Email Opens a Support Ticket

Suppose a company operates a mailbox:

~~~text
support@example.test
~~~

An email arrives:

~~~text
From: customer@example.test
To: support@example.test
Subject: Cannot log in
Message-ID: <example-123@sender.test>
Date: ...

I have not been able to log in since this morning.
~~~

The application needs to:

1. Receive the email from the configured mailbox.
2. Record the technical source identity: mailbox, folder, `UIDVALIDITY`, `UID`.
3. Parse MIME, extracting text and attachment references if present.
4. Validate data, enforce size limits, and resolve the eligible requester.
5. Apply domain rules to open a ticket or append to an existing ticket.
6. Save the ticket and the email's processed marker.
7. Create the **SupportTicketOpened** event only when the ticket was actually created.
8. Publish the event through a crash/retry-resilient mechanism.
9. Per policy, mark the email read or move folders after processing.

### The Same Email Can Lead to Different Outcomes

~~~text
Email A -> valid, opens a new ticket
           -> SupportTicketOpened

Email B -> reply to an existing ticket
           -> SupportReplyAdded

Email C -> auto-reply or spam
           -> No ticket domain event

Email D -> missing info, cannot authenticate
           -> NeedsManualReview / RejectedInboundMail
~~~

This is why mapping cannot simply do **new SupportTicketOpened(subject, body)** the moment an email is read.

## 3. Role of Spring Integration Mail

**Spring Integration** follows Enterprise Integration Patterns: inbound adapters, message channels, transformers, filters, routers, service activators, error channels, and outbound adapters. The Mail module provides receiving/sending capabilities over supported protocols.

### Inbound Mail Adapter

The adapter reads a mailbox periodically or receives change notifications when the implementation supports them (e.g., IMAP IDLE). It creates Spring messages to feed into the flow.

Common components:

- **ImapMailReceiver**: receiver reading from IMAP.
- **Pop3MailReceiver**: receiver reading from POP3.
- **MailReceivingMessageSource**: polling source backed by a receiver.
- **ImapIdleChannelAdapter**: event-driven adapter for IMAP IDLE.
- **IntegrationFlow**: DSL defining the processing pipeline.
- **MessageChannel**: channel transferring messages between endpoints.

These class/API names belong to Spring Integration Mail, not **org.springframework.mail.javamail.JavaMailSender**. `JavaMailSender` is primarily for SMTP sending.

### Technical Context and Versions

With modern Spring Integration versions on Jakarta EE, emails typically use **jakarta.mail.***. Older Spring Framework/Spring Integration projects may use **javax.mail.***. Never mix both namespaces in the same pipeline if dependencies are incompatible.

Payload behavior, auto-mark-as-read, delete-after-receive, multipart loading, and DSL methods can differ by **receiver configuration** and version. Always confirm the adapter's actual payload contract before writing transformers.

### Basic Flow Structure

~~~text
IMAP
  |
  v
Inbound Channel Adapter
  |
  v
mailInboundChannel
  |
  v
Envelope/Source-Key Extractor
  |
  v
MIME Normalizer
  |
  v
Validation + Classification
  |
  v
Domain Application Service
  |
  v
Event Outbox
  |
  v
Kafka / AMQP / internal subscribers
~~~

Capabilities outside the flow (database, broker, attachment storage) are implemented by the application; Spring Integration connects the steps without defining the system's domain events itself.

## 4. Configuring a Secure Mail-Receiving Connection

An application typically uses IMAPS:

~~~properties
app.mail.inbound.protocol=imaps
app.mail.inbound.host=imap.example.test
app.mail.inbound.port=993
app.mail.inbound.folder=INBOX
~~~

These are illustrative application properties, **not Spring Boot properties that auto-create an inbound mail adapter**. You must configure your own receiver/flow and supply host, credentials, folder, timeouts, and security policies.

With Jakarta Mail:

~~~java
import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.Store;

Properties props = new Properties();
props.put("mail.store.protocol", "imaps");
props.put("mail.imaps.connectiontimeout", "5000");
props.put("mail.imaps.timeout", "10000");
props.put("mail.imaps.writetimeout", "10000");
props.put("mail.imaps.ssl.checkserveridentity", "true");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
~~~

If using plain IMAP with STARTTLS, properties live under the **mail.imap.** prefix, such as:

~~~properties
mail.imap.starttls.enable=true
mail.imap.starttls.required=true
mail.imap.ssl.checkserveridentity=true
~~~

Authentication methods may be application credentials, OAuth 2.0, or another provider mechanism. Never put passwords/tokens into URLs or logs. Receiver URL examples containing credentials are convenient for demos, but production requires proper secret handling and URL escaping.

### SMTP and Inbound Are Separate Concerns

A system can simultaneously have:

~~~text
JavaMailSender  -> SMTP provider -> Send reply
Mail Receiver   <- IMAP mailbox  <- Receive request
~~~

Using `spring-boot-starter-mail` does not mean an **inbound IntegrationFlow** already exists. You must add compatible Spring Integration Mail dependencies and configuration.

## 5. Inbound Adapter Payload Contract

A Spring Integration **Message<?>** has two parts:

~~~java
Object payload = message.getPayload();
var headers = message.getHeaders();
~~~

The exact payload depends on receiver configuration:

- It may be a **jakarta.mail.Message** or **MimeMessage** object.
- Some configurations/versions may convert the payload to simple content, an array of messages, or another type.
- If an upstream transformer already ran, the payload may be an application DTO.
- Flow-created/enriched headers may hold metadata; never assume a header is present and trustworthy without verifying its source.

Therefore, **the domain mapper must accept an explicit contract**, such as **RawInboundMail** containing a `MimeMessage` and source metadata, or **ParsedInboundMail** after parsing. Never cast blindly:

~~~java
// Error-prone if adapter is configured to simplify payload:
jakarta.mail.internet.MimeMessage mime =
        (jakarta.mail.internet.MimeMessage) message.getPayload();
~~~

In a flow explicitly configured for raw `MimeMessage` payloads, the cast may be valid. Still, place a validation/normalization step at the boundary instead of coupling business services to receiver configuration.

### Spring Message Headers Are Not Verified Facts

When a transformer copies From/Subject from MIME into Spring headers, those values are still **email sender-supplied data**. Sitting inside **MessageHeaders** does not turn them into trusted identity.

Avoid:

~~~java
// Not safe enough for authorization:
if ("admin@example.test".equals(mailFrom)) {
    approvePayment();
}
~~~

To execute sensitive business actions, enforce authentication/authorization at a trusted layer—such as login confirmation links, one-time tokens, verified user mappings, or evidence from a trusted inbound provider paired with domain policy.

## 6. Two-Stage Transformation Architecture

Separate **technical normalization** from **domain interpretation**:

~~~text
MimeMessage
    |
    v
[Technical Mapper]
    |
    v
InboundMailCandidate
  - source key
  - sender/display name (untrusted)
  - recipients (untrusted)
  - headers
  - text/plain
  - sanitized HTML reference (if any)
  - attachment metadata/references
    |
    v
[Business Validator / Application Service]
    |
    v
Domain Model / Business Action
    |
    v
Domain Event
~~~

Benefits:

1. MIME parser can be unit-tested independently from business rules.
2. Switching IMAP for an ESP inbound webhook affects only the adapter.
3. Keeps **jakarta.mail.Message** out of the domain model.
4. Domain events keep stable schemas, independent of raw MIME boundaries/encodings.
5. Provides a place to record parse errors and quarantine without triggering business side effects.
6. Enables adding trust verification, size limits, and deduplication before domain processing.

### InboundMailCandidate Is Not Yet a Domain Event

The **InboundMailCandidate** record only represents extracted data; it does not confirm the sender is authorized to open a ticket or approve an order. It belongs in an **integration layer** or **anti-corruption layer**, not directly on the domain event stream.

### Events Are Created Only When the Domain Accepts

A reply email may map to:

~~~text
Mail candidate
   |
   v
TicketApplicationService.recordReply(...)
   |
   +--> TicketReplyRejected (if defined by the system's model)
   |
   '--> TicketReplyAdded (when the reply is persisted)
~~~

Not every application needs a `Rejected` event; some cases only need logs, quarantine, or operational alerts. However, **TicketReplyAdded** must never be emitted unless adding the reply succeeded.

## 7. Data Models at the Inbound Boundary

Example record declarations:

~~~java
import java.time.Instant;
import java.util.List;

public record InboundMailSource(
        String tenantId,
        String mailboxId,
        String folderName,
        long uidValidity,
        long uid
) {
}

public record InboundAttachment(
        String storageKey,
        String suppliedFileName,
        String detectedMediaType,
        long sizeBytes
) {
}

public record InboundMailCandidate(
        InboundMailSource source,
        String providerMessageId,
        String rawFrom,
        List<String> rawRecipients,
        String subject,
        String plainText,
        String htmlText,
        List<InboundAttachment> attachments,
        Instant emailSentAt,
        Instant observedAt
) {
}
~~~

These records are examples. Systems that reject HTML can retain only plain text. For attachments, store an **application-generated storageKey** rather than carrying raw bytes in every domain event.

### Field Naming Discipline

- **rawFrom**: value from the email header, not yet a verified identity.
- **providerMessageId**: typically taken from `Message-ID`; may be null/duplicate/forged.
- **emailSentAt**: taken from `Date`/`SentDate`, which senders can manipulate.
- **observedAt**: timestamp when the application observed the email; not necessarily exact server receipt time.
- **uid + uidValidity**: technical identifier within a specific folder; not a global key.
- **attachments**: metadata and references stored safely.

Such naming discourages developers from treating `rawFrom` or `Message-ID` as authorization proof.

## 8. Mail Source Identity and Preventing Duplicate Processing

An IMAP message has a **message sequence number** representing only its relative position in a folder at that instant. When messages are deleted/expunged, sequence numbers shift. To re-identify messages across polls, IMAP provides **UID** and **UIDVALIDITY**.

An illustrative source key:

~~~text
tenantId
  +
mailboxId
  +
folderId / folderName
  +
UIDVALIDITY
  +
UID
  =
InboundMailSourceKey
~~~

### Why Is UIDVALIDITY Necessary?

Two messages from two different mailbox recreations can share the same numeric UID. `UIDVALIDITY` distinguishes mailbox "epochs". If the server changes `UIDVALIDITY`, old UID checkpoints lose their previous meaning; the app needs a controlled resynchronization process.

### Why Is Message-ID Not Enough?

The **Message-ID** header can be missing, duplicated by senders, or changed during forwarding/copying. Two copies of an email in two folders can also share a `Message-ID` while having different UIDs. `Message-ID` is useful for correlation/reply threading, **not as a guarantee of a single unique business event**.

### A Copy's UID Can Differ from the Source UID

If an app reads a message from `INBOX` and copies/moves it to `Processed`, the message in the new folder can receive a different UID. The original source key must be preserved in an application table or mapping so moving a copy does not open a duplicate ticket.

### Do Not Assume Every Inbound Source Has an IMAP UID

With **POP3**, the flag/UID model differs; POP3 has `UIDL` when supported by the server and has no IMAP-style `UIDVALIDITY`. With **HTTP inbound webhooks**, providers may supply event IDs or request IDs. Define a **source identity abstraction** per transport, for example:

~~~java
public sealed interface MailSourceIdentity
        permits ImapSourceIdentity, ProviderEventIdentity {
}

public record ImapSourceIdentity(
        String mailboxId,
        String folder,
        long uidValidity,
        long uid
) implements MailSourceIdentity {
}

public record ProviderEventIdentity(
        String provider,
        String accountId,
        String eventId
) implements MailSourceIdentity {
}
~~~

This is an illustrative extensible model: using sealed interfaces requires a compatible Java version. For POP3 you can add `Pop3SourceIdentity` with account/mailbox and `UIDL` plus retention policy.

### UID Must Be Extracted Within the Proper Folder Lifecycle

Jakarta Mail API:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public static InboundMailSource identify(
        Message message,
        String tenantId,
        String mailboxId
) throws Exception {
    Folder folder = message.getFolder();
    if (folder == null || !folder.isOpen()) {
        throw new IllegalStateException(
                "IMAP folder must remain open when reading UID"
        );
    }
    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Folder does not support UIDFolder"
        );
    }

    return new InboundMailSource(
            tenantId,
            mailboxId,
            folder.getFullName(),
            uidFolder.getUIDValidity(),
            uidFolder.getUID(message)
    );
}
~~~

In Spring Integration, **never assume every Message payload still holds an open Folder when downstream handlers run**. The receiver may fetch/close the folder beforehand depending on configuration and implementation. If UIDs are needed for deduplication, the right fix is **extracting source metadata into the message while the receiver still has access**, using a receiver/transformer or header/metadata mechanism verified against your version before handing off to other workers. Never rely on calling **message.getFolder()** arbitrarily after the adapter closes the connection.

## 9. Setting Up Inbound Adapter and Channel in Spring Integration

A polling configuration can start from an **ImapMailReceiver**. Example using Spring Integration DSL:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
public class InboundMailFlowConfiguration {

    @Bean
    public ImapMailReceiver mailReceiver() {
        ImapMailReceiver receiver = new ImapMailReceiver(
                "imaps://mail-reader:example-password@imap.example.test:993/INBOX"
        );
        receiver.setShouldMarkMessagesAsRead(false);
        receiver.setShouldDeleteMessages(false);
        return receiver;
    }

    @Bean
    public IntegrationFlow inboundMailFlow(
            ImapMailReceiver receiver,
            InboundMailHandler handler
    ) {
        MailReceivingMessageSource source =
                new MailReceivingMessageSource(receiver);

        return IntegrationFlow
                .from(
                        source,
                        e -> e.poller(
                                Pollers.fixedDelay(
                                        Duration.ofSeconds(30)
                                )
                        )
                )
                .handle(handler)
                .get();
    }
}
~~~

**This is a structural example** that must be adapted to your Spring Integration version. Convenience DSL factories and some overloads may vary across versions. The URL/credentials shown are placeholders to demonstrate structure—**never put real passwords in source code**. In practice, load settings from a secret manager, handle percent-encoding for mail store URIs, and never print URIs containing credentials in logs.

### Why Disable Auto-Mark-Read and Auto-Delete?

If the receiver marks `SEEN` or deletes a message right after pulling it from the mailbox, the business handler might fail before creating a ticket, yet the next poll will no longer see those candidates. For durable pipelines, explicitly decide:

- Does the receiver automatically mark `SEEN`?
- Does it automatically delete/expunge messages?
- Is discovery based on unread messages or UID checkpoints?
- If the flow crashes, can source messages be safely rediscovered?

**setShouldMarkMessagesAsRead(false)** gives explicit control over when marking happens if the receiver/provider honors those semantics. However, **reading a body over IMAP without PEEK can still flip SEEN**; verify actual fetch settings and provider behavior. Never treat a single property as an absolute guarantee.

### Polling Requires Concurrency Control

One poller instance can fetch multiple messages; multiple replicas can also read `INBOX` concurrently. Turning off auto-mark-read alone does not stop two workers from processing the same message. You need durable source keys and database claim/deduplication.

### Spring Integration Does Not Replace Spring Mail Senders

The inbound adapter delivers mail as messages on a channel; to send replies via SMTP, use an outbound mail adapter or `JavaMailSender` per your design. Do not embed reply-sending logic inside the MIME parser where side effects are hard to control.

## 10. Creating a Handler That Accepts Only Raw Mail

The goal is a clean code boundary: the handler receives a **Spring Message<?>**, checks the payload shape, and delegates to an inbound mail service. Never pass raw `MimeMessage` straight into the domain.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.stereotype.Component;

@Component
public class InboundMailHandler implements MessageHandler {

    private final InboundMailProcessingService service;

    public InboundMailHandler(InboundMailProcessingService service) {
        this.service = service;
    }

    @Override
    public void handleMessage(Message<?> message) {
        Object payload = message.getPayload();
        if (!(payload instanceof MimeMessage mime)) {
            throw new IllegalArgumentException(
                    "Expected raw MimeMessage; check receiver configuration"
            );
        }

        service.process(mime, message.getHeaders());
    }
}
~~~

**InboundMailProcessingService** is an application component. This example holds when the inbound adapter is configured to emit individual **MimeMessage** payloads that remain accessible. If the receiver returns another payload (e.g., simplified content, a non-MimeMessage `Message`, or a batch), add a type-matching normalization adapter instead of casting.

### Do Not Pull SourceKey from an Arbitrary Header

If UID/`UIDVALIDITY` were enriched into Spring `MessageHeaders` upstream, the handler can read application-defined headers such as **mailboxId**, **folder**, **uidValidity**, and **uid**. Trust them only when populated by an **internal adapter** from a verified source; never accept identically named external email headers as technical source metadata.

### Header Extraction Should Happen Before Resources Close

To process asynchronously on an `ExecutorChannel` or queue, **never hand an open-Folder-bound `MimeMessage` across threads/hosts**. Instead:

1. Within the receive boundary, extract UID/source identity.
2. Read/stream required content within bounds.
3. Persist a durable **inbound snapshot** or normalized DTO.
4. Pass the **snapshot ID** or self-contained DTO over the channel.
5. Close `Folder`/`Store` once transport work completes.

This prevents downstream **FolderClosedException** errors when reading bodies and decouples domain state from IMAP connection lifecycles.

## 11. MIME Normalization: More Than Just Subject and Body

A MIME email can contain:

- **text/plain**: plain-text content.
- **text/html**: HTML content.
- **multipart/alternative**: multiple content representations.
- **multipart/mixed**: body plus attachments.
- **multipart/related**: HTML and CID-referenced inline resources.
- **message/rfc822**: nested email.
- Different **transfer encodings** and **charsets**.

Example:

~~~text
MimeMessage
  |
  '-- multipart/mixed
        |
        +-- multipart/alternative
        |      |
        |      +-- text/plain
        |      '-- text/html
        |
        +-- application/pdf (attachment)
        '-- image/png (attachment)
~~~

Never use a rigid cast:

~~~java
// May throw ClassCastException when message is Multipart.
String body = (String) mime.getContent();
~~~

The library can return **String**, **Multipart**, **InputStream**, or another type depending on MIME type and implementation.

### Step-by-Step Parsing

A safe parser typically:

1. Reads header metadata within limits.
2. Checks message size and MIME part counts.
3. Selects `text/plain` or converts HTML to text per policy.
4. Normalizes Unicode/newlines while preserving meaningful content.
5. Extracts attachments into isolated storage and scans/validates them.
6. Returns an immutable **InboundMailCandidate** to the domain layer.

### Note on Selecting Plain Text in multipart/alternative

An email may carry both plain text and HTML with differing content. If the application only parses plain text automatically, recognize that a sender can craft plain text different from HTML. For sensitive business actions, never base permissions or monetary amounts purely on unverified email content.

## 12. A Resource-Bounded MIME Parser

The following snippet illustrates **traversing text parts**, not a full attachment parser. Bounding depth, part count, and text length reduces the risk of oversized inputs:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.BodyPart;
import java.util.concurrent.atomic.AtomicInteger;

public final class PlainTextExtractor {

    private final int maxDepth = 8;
    private final int maxParts = 80;
    private final int maxTextChars = 200_000;

    public String extract(Part root) throws Exception {
        StringBuilder text = new StringBuilder();
        AtomicInteger parts = new AtomicInteger();
        visit(root, text, parts, 0);
        return text.toString();
    }

    private void visit(
            Part part,
            StringBuilder text,
            AtomicInteger parts,
            int depth
    ) throws Exception {
        if (depth > maxDepth || parts.incrementAndGet() > maxParts) {
            throw new IllegalArgumentException(
                    "MIME structure limit exceeded"
            );
        }

        String disposition = part.getDisposition();
        if (Part.ATTACHMENT.equalsIgnoreCase(disposition)) {
            return; // Handle attachments in a separate pipeline.
        }

        if (part.isMimeType("text/plain")) {
            Object content = part.getContent();
            if (content instanceof String value) {
                if ((long) text.length() + value.length()
                        > maxTextChars) {
                    throw new IllegalArgumentException(
                            "Text body too large"
                    );
                }
                if (!text.isEmpty()) {
                    text.append('\n');
                }
                text.append(value);
            }
            return;
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                visit(child, text, parts, depth + 1);
            }
        }
    }
}
~~~

This snippet demonstrates traversal; for **Java StringBuilder** in your JDK, check `isEmpty()` availability by Java version (if unsupported, use **text.length() > 0**). It also does not bound raw MIME bytes **before** the library decodes the body: a compressed/encoded part can expand before forming a `String`. Production code must cap **source size, actual bytes read, element count, processing time, and attachment size**, while handling charsets and malformed MIME.

### Never Save Attachments by Trusting the File Name

**part.getFileName()** is sender-supplied data and may contain control characters, path separators, or extensions that misrepresent actual content. To store files, generate a server-side storage key and keep the supplied filename only as normalized metadata—never use it directly as a filesystem path.

### HTML Must Be Treated as Untrusted Data

If HTML needs to be displayed in an internal UI, apply proper **sanitization** and block scripts, tracking, and external references per policy. Never embed email HTML directly into a dashboard as trusted HTML.

## 13. Inspecting Headers for Classification, Not Authorization

Useful headers include:

| Header/Property | Meaning | Limitation |
| --- | --- | --- |
| **From** | Declared sender address | Can be spoofed |
| **Reply-To** | Desired address for replies | Does not prove ownership |
| **To / Cc** | Presented recipients | May differ from envelope recipients; Bcc hidden |
| **Subject** | Email subject | May be missing or modified |
| **Message-ID** | Threading trace | Can be missing, forged, or duplicated |
| **In-Reply-To** | Parent message reference | Insufficient to grant ticket write access |
| **References** | Thread reference chain | Can be forged by senders |
| **Date** | Sender-claimed timestamp | Untrusted for event `occurredAt` |
| **Auto-Submitted** | May indicate automated response | Not an absolute anti-loop signal |
| **Content-Type** | Declared MIME type | Must verify when handling attachments |
| **Authentication-Results** | Email auth results added by receiving system | Trust only from a defined inbound/trust boundary |

### Reading Header Information with Jakarta Mail

~~~java
import jakarta.mail.Message;
import jakarta.mail.Address;
import java.util.Date;

public static void inspect(Message message) throws Exception {
    Address[] from = message.getFrom();
    String subject = message.getSubject();
    Date sent = message.getSentDate();
    String[] messageIds = message.getHeader("Message-ID");
    String[] replies = message.getHeader("In-Reply-To");

    // Normalize, bound length, and transfer to candidate.
    // Never use raw From or In-Reply-To to approve transactions.
}
~~~

### Authentication-Results Header Must Come from a Trusted Source

An email passing through a mail gateway may have SPF/DKIM/DMARC results appended. However, an attacker can also inject a fake **Authentication-Results** header into the raw message. To rely on authentication results for sender mapping, obtain them from a **trusted inbound provider** that strips/overwrites externally supplied headers at a well-defined trust boundary.

### Handling Reply Threading

An email containing:

~~~text
In-Reply-To: <original-ticket-notice@example.test>
References: <original-ticket-notice@example.test>
~~~

may be a reply to an existing ticket. Yet you must verify:

1. Does the original `Message-ID` map to a ticket in the database?
2. Does the receiving mailbox belong to the active tenant?
3. Is the sender permitted to add content to that ticket?
4. Has the ticket been closed or restricted?
5. Are there signs of automated mail/loops/spoofing?

Only after business conditions pass should **SupportReplyAdded** be emitted. Simply finding a `Message-ID` in `References` is not enough.

## 14. Normalization and Validation Before Entering the Domain

An input boundary can divide validation into four layers:

1. **Transport validation**: configured connection and mailbox, email exists, valid source identity.
2. **MIME validation**: parses cleanly, permitted size/charset/attachment types.
3. **Application validation**: tenant, recipient route, required fields, mail command schema.
4. **Domain authorization**: sender is permitted to request the action; current ticket/order allows mutation.

### Examples of Different Errors

| Scenario | Suggested Outcome | Should a Domain Event Be Emitted? |
| --- | --- | --- |
| Failed to fetch MIME due to IMAP timeout | `RETRY_WAIT` | No |
| Corrupted MIME, unparseable | `QUARANTINE` / `PERMANENT_FAILED` | Never emit a success domain event |
| Empty body when policy requires content | `REJECTED` / `REVIEW` | No |
| Unauthenticated sender for sensitive action | `REVIEW` / `REJECTED` | No |
| Reply points to nonexistent ticket | `REJECTED` or unmatched queue | Never emit `SupportReplyAdded` |
| Ticket opened and persisted | `PROCESSED` | Emit `SupportTicketOpened` |
| Same UID already `PROCESSED` | `DUPLICATE` | Do not emit again |
| Ticket service timeout after external side effect | `UNKNOWN` | Reconcile before retrying |

Do not funnel everything into one generic exception that retries forever. A malformed-MIME parser failure would spin endlessly if every error were treated as transient. Conversely, a transient network timeout must not drop an email permanently right away.

### Separating Retryable and Permanent Errors

An application model:

~~~java
public enum InboundFailureKind {
    TRANSIENT_TRANSPORT,
    TRANSIENT_DEPENDENCY,
    INVALID_MIME,
    UNSUPPORTED_ATTACHMENT,
    UNAUTHORIZED_SENDER,
    UNMATCHED_THREAD,
    AMBIGUOUS_BUSINESS_OUTCOME
}
~~~

These enums are project-defined. **AMBIGUOUS_BUSINESS_OUTCOME** differs from ordinary retryable errors: the side effect may already have happened, requiring reconciliation to avoid creating two tickets or sending two replies.

## 15. Mapping into a Structured Domain Event

For opening a new ticket, a domain event should carry **business facts**:

~~~java
import java.time.Instant;
import java.util.UUID;

public record SupportTicketOpened(
        UUID eventId,
        int schemaVersion,
        UUID ticketId,
        String tenantId,
        String customerId,
        String sourceMailboxId,
        String sourceReference,
        Instant occurredAt,
        String correlationId
) {
}
~~~

Here:

- **eventId** is generated once when the domain event is durably persisted, never changing across publish retries.
- **schemaVersion** enables handling format evolution.
- **ticketId** is the business aggregate ID, distinct from the source UID.
- **tenantId/customerId** are mapped via domain policy; never use raw `From` as `customerId`.
- **sourceMailboxId/sourceReference** support tracing without embedding raw MIME in the event.
- **occurredAt** is when the domain recorded the action, not defaulted to the `Date` header.
- **correlationId** links mail poll, processing record, ticket, and event outbox.

### Minimal or Rich Event?

Two common designs:

**Identifier-only event:**

~~~text
SupportTicketOpened {
  eventId,
  ticketId,
  occurredAt,
  ...
}
~~~

Consumers query ticket details under a separate contract when needed. Advantage: avoids spreading PII and keeps schemas compact; disadvantage: consumers depend on lookups.

**Selective snapshot event:**

~~~text
SupportTicketOpened {
  eventId,
  ticketId,
  category,
  priority,
  summary,
  ...
}
~~~

Advantage: consumers receive minimal required context upfront. However, privacy policies, encryption/retention, and schema evolution are needed when potentially sensitive fields are included.

Never embed full MIME, access tokens, password reset links, or attachment bytes onto a public event bus merely to "preserve full info".

### Avoid Misleading Event Names

Do not name **EmailReceived** as **OrderApproved** simply because an email had Subject "Approve order". To emit **OrderApproved**, the domain must verify the requester's authority, confirm the order's state allows approval, and persist the change.

## 16. From Candidate to Business Decision

An application service flow:

~~~text
InboundMailCandidate
       |
       v
Identify tenant + classify purpose
       |
       v
Resolve customer identity safely
       |
       v
Dedup / claim source key
       |
       v
Validate ticket request/reply
       |
       v
Apply domain rules
       |
       +-- Reject / Needs review
       |
       '--> Persist Ticket and TicketEvent
                   |
                   v
          Commit business transaction
                   |
                   v
              Publish event
~~~

### An Explicit Result Type

~~~java
public enum InboundDecisionType {
    PROCESSED,
    DUPLICATE,
    REJECTED,
    RETRY_WAIT,
    NEEDS_REVIEW
}

public record InboundDecision(
        InboundDecisionType type,
        String eventId,
        String reasonCode
) {
}
~~~

For `PROCESSED`, `eventId` can hold the persisted domain event ID. For `DUPLICATE`, it can return the previously recorded event ID. For `REJECTED`, do not necessarily emit a domain event sharing the success action's name; the system can record an audit entry at the integration layer.

### Never Let the Parser Perform Business Actions

The parser only extracts/normalizes and reports data errors:

~~~java
InboundMailCandidate candidate =
        normalizer.normalize(rawMail, source);

InboundDecision decision =
        applicationService.handle(candidate);
~~~

Separating these two steps ensures swapping the MIME parser, receiver, or message channel never alters ticket-opening rules.

## 17. Domain Services and Transaction Boundaries

Suppose ticket creation and event persistence share the same database. A safe design is:

~~~text
BEGIN DB TRANSACTION
    |
    +-- Lock/claim source key
    |
    +-- Validate customer and ticket
    |
    +-- Insert ticket / reply
    |
    +-- Mark inbound processing PROCESSED
    |
    '-- Insert domain event into outbox
    |
COMMIT
    |
    v
Separate publisher reads event outbox
    |
    v
Publish to broker, retry safely
~~~

With changes in the **same database** under the same transaction manager, the ticket, inbound processing state, and event outbox commit or roll back together. Calls to an IMAP server, object storage, or a broker **do not automatically** participate in that database transaction.

### Illustrative Application Service Example

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SupportMailApplicationService {

    private final InboundProcessingRepository inbound;
    private final CustomerResolver customers;
    private final SupportTicketRepository tickets;
    private final DomainEventOutbox events;
    private final Clock clock;

    public SupportMailApplicationService(
            InboundProcessingRepository inbound,
            CustomerResolver customers,
            SupportTicketRepository tickets,
            DomainEventOutbox events,
            Clock clock
    ) {
        this.inbound = inbound;
        this.customers = customers;
        this.tickets = tickets;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public InboundDecision handle(InboundMailCandidate candidate) {
        String sourceKey = sourceKeyOf(candidate.source());

        if (!inbound.tryRegisterOnce(sourceKey)) {
            return new InboundDecision(
                    InboundDecisionType.DUPLICATE,
                    inbound.eventIdOf(sourceKey),
                    "ALREADY_PROCESSED"
            );
        }

        String customerId = customers.resolveAuthorizedCustomer(
                candidate
        );

        UUID ticketId = tickets.openTicket(
                candidate.source().tenantId(),
                customerId,
                candidate.subject(),
                candidate.plainText()
        );

        SupportTicketOpened event = new SupportTicketOpened(
                UUID.randomUUID(),
                1,
                ticketId,
                candidate.source().tenantId(),
                customerId,
                candidate.source().mailboxId(),
                sourceKey,
                Instant.now(clock),
                sourceKey
        );

        events.save(event);
        inbound.markProcessed(sourceKey, event.eventId().toString());
        return new InboundDecision(
                InboundDecisionType.PROCESSED,
                event.eventId().toString(),
                "TICKET_OPENED"
        );
    }

    private String sourceKeyOf(InboundMailSource source) {
        return source.tenantId() + ":"
                + source.mailboxId() + ":"
                + source.folderName() + ":"
                + source.uidValidity() + ":"
                + source.uid();
    }
}
~~~

**InboundProcessingRepository**, **CustomerResolver**, **SupportTicketRepository**, and **DomainEventOutbox** are application-implemented interfaces. `tryRegisterOnce` must be genuinely atomic, e.g., backed by a unique constraint/row lock; the snippet assumes a shared database where failures roll back the transaction. `sourceKeyOf` only demos the identifier structure; production should use structured length-prefixed encoding or hash a canonical representation to avoid ambiguity from colons inside components.

### Transactional Subtleties

Avoid running full IMAP downloads, virus scans, or external API calls **inside the transaction** whenever possible, as their latencies are unpredictable and hold DB locks too long. Split into:

1. Fetch + normalize + save snapshot under bounds.
2. Claim source/processing record.
3. Short transaction: domain mutation + event outbox + processing state.
4. Post-commit: sync IMAP `SEEN`/move and publish outbox.

If steps 2 and 3 span separate transactions, use leases/versions so multiple workers cannot process concurrently. If a side effect hits an external API, enforce an idempotency key or separate reconciliation.

## 18. Guaranteeing a Stable eventId Across Retries

A common bug:

~~~text
Poll #1:
  UID 108 -> creates SupportTicketOpened(eventId=A)
  Send to broker -> timeout

Poll #2:
  UID 108 -> creates SupportTicketOpened(eventId=B)
  Send to broker -> accepted
~~~

If a fresh `eventId` is generated on each attempt, consumers cannot easily tell that A and B represent the same logical event. Persist a **durable eventId** in the transaction, then let publisher retries reuse that `eventId`.

~~~text
Inbound source key -> unique processing row
                  -> one domain mutation
                  -> one event outbox row
                  -> stable eventId
                  -> many delivery attempts (if necessary)
~~~

### Illustrative Database Unique Constraints

~~~sql
CREATE TABLE inbound_mail_processed (
    source_key VARCHAR(512) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    event_id UUID,
    processed_at TIMESTAMPTZ
);

CREATE TABLE domain_event_outbox (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    publish_attempts INTEGER NOT NULL DEFAULT 0
);
~~~

These tables are PostgreSQL examples, not Spring Integration auto-generated schemas. If the outbox publisher crashes after the broker **accepted** the event yet before updating `published_at`, it may republish. Consumers still need idempotent processing by **eventId** or aggregate version.

### Domain Events Do Not Have System-Wide Exactly-Once Guarantees

Unique keys ensure each source creates one business mutation; transactional outboxes prevent losing events between business commit and enqueueing. Still, external brokers/APIs and consumers can receive events multiple times on retries. Thus the practical goal is **at-least-once delivery + idempotent consumers**, never claiming end-to-end exactly-once solely because an outbox is used.

## 19. Spring Integration Transformer, Filter, and Service Activator

A clean pipeline can compose Spring Integration steps:

~~~text
Inbound Adapter
     |
     v
Raw Mail Channel
     |
     v
Transformer: MimeMessage -> InboundMailCandidate
     |
     v
Filter: basic eligibility (size/type/auto-reply)
     |
     v
Service Activator: domain application service
     |
     v
Domain Decision Channel
     |
     +--> PROCESSED -> Event outbox publisher
     +--> RETRY_WAIT -> Retry management
     '--> REJECTED / QUARANTINE -> Review
~~~

### Transformers Only Normalize; They Never Create Domain Events

Method example:

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.Message;

public class MailNormalizationComponent {

    private final InboundMailNormalizer normalizer;

    public MailNormalizationComponent(InboundMailNormalizer normalizer) {
        this.normalizer = normalizer;
    }

    @Transformer(inputChannel = "rawMailChannel",
                 outputChannel = "normalizedMailChannel")
    public InboundMailCandidate transform(Message<?> springMessage) {
        return normalizer.normalize(springMessage);
    }
}
~~~

**InboundMailNormalizer** is an application-defined service responsible for validating payloads and source metadata. `@Transformer` belongs to Spring Integration. In Java DSL configurations instead of annotations, the equivalent can be **.transform(normalizer, "normalize")** when the method signature matches framework expectations.

### Filters Should Only Enforce Basic Technical Criteria

~~~java
public boolean allowForProcessing(InboundMailCandidate mail) {
    return mail.plainText() != null
            && mail.plainText().length() <= 200_000
            && mail.source() != null;
}
~~~

Filters often simplify pipelines, yet for **rejected** emails you need an audit/quarantine path and reason code so work never disappears silently. Sender domain authorization still belongs in the application service, not a simplistic Subject-based filter.

### Service Activator Is the Business Boundary

~~~java
import org.springframework.integration.annotation.ServiceActivator;

public class InboundDomainHandler {

    private final SupportMailApplicationService service;

    public InboundDomainHandler(
            SupportMailApplicationService service
    ) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "normalizedMailChannel")
    public InboundDecision handle(InboundMailCandidate mail) {
        return service.handle(mail);
    }
}
~~~

These are structural options; do not apply both `@Transformer` and an equivalent DSL step twice for the same flow. When an annotated method returns a value, output channel/reply handling must be explicit; a handler with nowhere to send its reply can raise warnings or errors depending on the endpoint contract.

### Avoid Calling publishEvent Directly Inside a Transformer

A transformer may be re-invoked if a message is retried. If it parses, creates a ticket, and publishes an event all at once, idempotency becomes very hard to maintain. Domain mutations and event creation belong in a single explicit transaction/service.

## 20. Acks, the SEEN Flag, Mail Deletion, and Domain State

An inbound mail adapter can be configured to mark messages read, delete them, or leave them untouched. However, the **IMAP `SEEN` flag** is neither a database transaction ACK nor confirmation that an event reached consumers.

### Three Separate States

| State | Where Stored | Meaning |
| --- | --- | --- |
| **Mailbox read state** | IMAP server, `SEEN` flag | Mailbox UI shows read/unread |
| **Processing state** | Application database | Whether the email was processed by business logic |
| **Event publish state** | Event outbox/broker | Whether the domain event was published/acked |

A failure scenario:

~~~text
1. Mail receiver reads email and auto-marks SEEN.
2. MIME parse succeeds.
3. Ticket repository fails.
4. Flow throws exception.
5. Next poll searches only UNSEEN.

Result: Email is missed unless separate recovery exists.
~~~

Therefore, for pipelines that cannot miss emails, mark `SEEN` **only after business state is safely persisted**, and track state via a processing/UID table rather than relying solely on `UNSEEN`.

### What If Setting SEEN Fails After Commit?

~~~text
Domain ticket = committed
Event outbox = committed
IMAP flag-sync = failed
~~~

The system **must not create a duplicate ticket** because flag-sync failed. Instead, a dedicated **mail_flag_sync** job can retry setting `SEEN` by source UID/`UIDVALIDITY`. If the message was moved/expunged, record the outcome and stop retrying endlessly.

### What If Business Rules Require Keeping Emails Unread?

Not every workflow needs marking. For instance, an app that only indexes support mail might leave `SEEN` to webmail staff; in that case `SEEN` is UI state while **PROCESSED** is automation state.

### Deleting/Expunging Is Not a Default Ack

Never use **setShouldDeleteMessages(true)** or `close(expunge=true)` as a way of "marking processed" without formal retention storage. One email deletion can erase audit evidence and disrupt shared mailboxes.

## 21. Error Channels and Error Routing

Spring Integration provides an **error channel** mechanism using error messages to route exceptions from flow components depending on endpoint, thread, and message channel settings.

~~~text
inboundMailFlow
      |
      +--> NORMALIZE SUCCESS -> domain service
      |
      +--> MIME PARSE FAILURE -----------+
      |                                 |
      +--> DB TEMPORARY FAILURE --------+--> Error handling
      |                                 |      |
      +--> UNKNOWN BUSINESS OUTCOME ----+      +--> Retry
                                             +--> Quarantine
                                             '--> Reconciliation
~~~

### Classifying Errors

| Error Type | Handling Direction |
| --- | --- |
| IMAP connection reset / timeout before fetch | Retry with backoff, use source checkpoint |
| Corrupted, unparseable MIME | Quarantine or manual review, never infinite retry |
| Oversized/unsafe attachment | Reject/quarantine, audit per policy |
| Unable to resolve tenant/customer | Needs review, never auto-emit privileged events |
| DB temporarily unavailable | Retry with backoff, keep source key |
| Unique key already `PROCESSED` | Duplicate no-op |
| Broker publish failure | Retry event outbox, do not reprocess email |
| Ambiguous external ticket API timeout | `UNKNOWN`, reconcile to avoid duplicate tickets |

### Message-Handling Errors May Be ErrorMessage

An error handler can inspect the payload:

~~~java
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.Message;

public void onError(Message<?> message) {
    if (message instanceof ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        // Classify root cause, log redacted metadata.
        // Do not print full failed mail payload.
    }
}
~~~

This snippet shows how to inspect an `ErrorMessage`; routing it onto a specific error channel requires configuring the corresponding channel/endpoint. With synchronous polling flows, exceptions may be thrown on the poller thread and follow different error handling than `ExecutorChannel`/async flows; do not assume every error automatically appears on a channel without configuration.

### Do Not Treat an Error Channel as a "Trash Can"

If a parse error goes to an error channel that only logs one line and drops it, the email can vanish from processing. Define concrete decisions: retry, quarantine, audited rejection, or manual review. Source identity must be preserved to reprocess the right email.

## 22. Retries, Idempotency, and Avoiding Duplicate Events

You cannot wrap the entire flow in a `RetryTemplate` and assume it will never produce duplicate domain events. Distinguish:

~~~text
Retry IMAP fetch:
  re-reads the same email, no business mutation yet

Retry MIME parse:
  same input, usually repeatable if parser has no side effects

Retry domain operation:
  safe only if idempotent/transaction-aware

Retry event publishing:
  reuses same eventId from outbox, consumer deduplicates

Retry IMAP flag sync:
  only updates SEEN, does not rerun business operations
~~~

### Different Retries Carry Different Risks

| Stage | Side Effects? | Approach |
| --- | --- | --- |
| Fetch metadata | Usually minimal, depends on flags/fetch | `READ_ONLY`/peek, reconnect |
| Parse raw MIME | Mostly CPU, can consume resources | Limits and quarantine |
| Save business state | Mutates DB | Unique keys and transactions |
| Call external ticket API | Side effects outside DB | Idempotency keys or reconciliation |
| Publish domain event | Broker side effects | Transactional outbox + consumer dedup |
| Set IMAP `SEEN` | Mailbox side effects | Separate sync, retry by UID |

### Never Change Event IDs Between Deliveries

A broker redelivers twice:

~~~text
Event id = 123
Delivery #1 -> consumer processes -> response lost
Delivery #2 -> consumer sees id 123 already processed -> skip
~~~

This is an **idempotent consumer**. If the publisher generates a fresh event ID on each retry, consumers cannot easily tell two deliveries belong to one logical event.

### Do Not Confuse HTTP Request Idempotency with UID Deduplication

UID identifies the source email. If a business service creates multiple records from one email per requirements (e.g., an email listing multiple order lines), it may need an idempotency key scoped to **mail source + operation**, rather than a single global "email processed" boolean.

## 23. Managing Attachments in Events

An email may carry error screenshots, logs, invoices, or malicious files. Domain events **should not embed full attachment bytes by default**:

~~~text
MimeMessage
  |
  v
Attachment processor
  |
  +-- Validate size/content type
  +-- Scan/quarantine according to policy
  +-- Store in protected object storage
  '-- Return opaque storage reference
                 |
                 v
       InboundMailCandidate
                 |
                 v
         Domain decision
                 |
                 v
      SupportTicketOpened
        + attachment IDs
~~~

### Why Not Embed Base64 into Events?

- Event sizes balloon; one 20 MiB attachment can exceed broker record limits.
- Multiplies PII exposure across many consumers.
- Cannot easily revoke permissions or delete content later.
- Malware/retention policies become hard to enforce uniformly.
- Domain event schemas get tightly coupled to MIME storage.

Instead, events can carry access-controlled **attachment reference IDs**. A consumer receiving a reference does not automatically gain file read rights: the storage service must enforce tenant/role, TTL, and purpose checks.

### MIME Content-Type Is Not Proof of Real File Type

An email may declare:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

while the actual bytes are not a PDF. Never open or serve files to users based solely on sender-supplied filenames or content types. Apply validation, magic-byte/content inspection, size limits, and malware policies.

### Handling Inline Images and CIDs

Inline images in **multipart/related** carry a `Content-ID` and may be referenced in HTML bodies as `cid:image-001`. If the domain needs to display the email, handle CID references under policy and block remote-content tracking; if only opening a ticket from text, you do not have to import every inline image as a domain attachment.

### Protecting Against Filename Path Traversal

Never write files via:

~~~java
// Unsafe when filename is sender-controlled.
var destination = uploadDir.resolve(part.getFileName());
~~~

Use server-generated storage IDs and keep the original filename as normalized metadata with bounded length and characters. When writing to a filesystem, enforce path canonicalization and permissions.

## 24. Designing Schema Evolution for Domain Events

An integration event might stay inside one service; a domain event published to Kafka/AMQP may have many independent consumers. When evolving schemas, avoid breaking older consumers.

Version 1 example:

~~~json
{
  "eventId": "8c75f2c1-0000-4000-8000-000000000001",
  "eventType": "SupportTicketOpened",
  "schemaVersion": 1,
  "ticketId": "9f1a00a0-0000-4000-8000-000000000002",
  "tenantId": "tenant-7",
  "occurredAt": "2026-01-01T10:00:00Z"
}
~~~

Version 2 might add **category** as an optional field; older consumers can ignore unknown fields if deserializers/configs permit. If changing the semantics of an existing field, enforce explicit versioning and migration contracts rather than merely renaming a Java record field.

### Events Should Describe What Happened

~~~text
SupportTicketOpened
SupportReplyAdded
CustomerContactVerified
~~~

are past-tense domain event names. **ParseInboundMail** or **CreateTicketFromEmail** are commands/steps, not domain facts.

### Storing Metadata in an Event Envelope

An event envelope:

~~~java
public record DomainEventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateType,
        String aggregateId,
        String tenantId,
        String correlationId,
        String causationId,
        java.time.Instant occurredAt,
        T payload
) {
}
~~~

**correlationId** tracks the entire inbound email flow, while **causationId** can link directly to the triggering source event; define explicit semantics so untrusted email `Message-ID`s are never confused with internal causation IDs.

### Ordering by Aggregate

If a ticket receives 3 consecutive emails, **SupportReplyAdded** events may require ordering by ticket ID/aggregate version. Mailbox ordering and broker publish ordering are not guaranteed to match due to retries, multiple workers, or provider delays.

One design persists an incrementing **aggregateVersion** inside the transaction, partitions broker messages by ticket ID, and lets consumers discard stale/duplicate messages by version. Never rely on email `Date` headers or sequence numbers as strict business ordering.

### Domain Events Are Not Data Dumps

An event can carry `ticketId`, `category`, and `createdAt`; sensitive email content can stay in a separately authorized domain repository. Choose payloads based on legitimate consumer needs, not everything available on `MimeMessage`.

## 25. Preventing Auto-Reply Loops

Systems that read mailboxes and send automated emails can accidentally reply to another system's **auto-reply**:

~~~text
System A receives mail -> auto reply
System B receives reply -> auto reply
System A receives reply -> ...
~~~

Consequences include mail loops, exhausted quotas, spam complaints, and processing backlogs.

### Reference Signals

- **Auto-Submitted** typically indicates an auto-generated email.
- Some bounce/DSN notices use `multipart/report`.
- Subjects starting with "Automatic reply" or "Out of office" are weak signals.
- Some ESP/gateway headers help identify bounces/complaints.
- A null envelope sender (`MAIL FROM:<>`) can appear on DSNs; not from the `From` header.

No single header is safe across every provider. These fields can be spoofed, so combine policies, provider characteristics, and rate limits.

### Do Not Create Infinite Tickets from DSNs

If the system sends replies and the mailbox receives bounces for those replies, never treat every DSN as a new support request unless the use case is specifically bounce processing. Automated messages and failure notices should route to **integration events or dedicated workflows**.

### Classify Without Immediately Deleting Data

When an auto-reply is detected, mark status **IGNORED_AUTO_REPLY**, storing the source key and reason to avoid reprocessing. Deleting it from the mailbox is unnecessary; retention and permissions must follow operational policies.

## 26. Never Trust Email for High-Privilege Actions

An email with Subject:

~~~text
Subject: APPROVE TRANSFER 1000000
From: ceo@example.test
~~~

is no basis for emitting **TransferApproved**. Email headers are easily forged, content can be altered/forwarded, and a support mailbox can receive email from anywhere.

### Security Boundaries

Fields to separate:

~~~text
Raw From address        -> user-supplied claim
Inbound mailbox ID      -> integration-configured source
Provider auth metadata  -> only trusted if verified at boundary
Customer identity       -> resolved by application
Business permission     -> checked against domain policy
Domain event            -> emitted after authorized mutation
~~~

Some cases require signed payloads, portal authentication, one-time confirmation links, or requiring the user to sign in to confirm. Never assume SPF/DKIM pass automatically grants a sender authority to approve a business action.

### A Reply Containing a Ticket ID Is Also Insufficient

If someone guesses a ticket ID and sends "Reply to TICKET-123", never let them read or modify arbitrary tickets. Beyond thread checks, verify that the sender is linked to the ticket/tenant under trusted rules.

### Limiting Email as a Command Bus

Low-risk commands like "open a support request" may accept inbound email after validation. Sensitive operations like changing permissions, transferring funds, resetting MFA, or exporting sensitive data need a stronger confirmation channel. That directly governs which domain events may originate from an inbox.

## 27. Protecting Personal Data in the Event Pipeline

An email can contain:

- Names, phone numbers, physical addresses.
- Login tokens/OTPs.
- Invoices, account numbers, or contract text.
- Attachments containing health/HR records.
- Email signatures and quoted conversation history.

Turning the entire email into a JSON event on a broker subscribed to by many services expands data exposure dramatically.

### Design Principles

1. **Data minimization:** events include only fields consumers genuinely need.
2. **Access control:** only authorized services can read payloads/attachments.
3. **Encryption:** protect transport and data at rest in DBs, object storage, and brokers.
4. **Retention:** define separate retention periods for raw MIME, normalized candidates, events, and logs.
5. **Redaction:** never log credentials, tokens, bodies, or attachment bytes.
6. **Tenant isolation:** derive `tenantId` from mailbox/internal authorization, never directly from sender headers.
7. **Audit:** allow tracing who processed an email and which events were emitted via internal IDs.
8. **Deletion lifecycle:** when PII must be erased per policy, track which stores/consumers received copies.

### Opaque sourceReference

A domain event can carry:

~~~text
sourceReference = "inbound-mail:7f23..."
~~~

pointing to an access-controlled record. Event consumers should not automatically gain access to raw mailbox credentials or full MIME just by knowing that reference.

### Logs Are Data That Needs Protection Too

Logging:

~~~text
event=inbound_mail_processed
mailbox_id=support-1
source_key_hash=sha256:...
decision=PROCESSED
event_id=...
duration_ms=190
~~~

is far more useful than dumping full `From`, `Subject`, and 10,000 characters of body. When deep debugging is needed, store details in an access-controlled, TTL-bounded store rather than enabling raw protocol traces by default.

## 28. Choosing Synchronous vs. Asynchronous Channels

Spring Integration offers multiple message channel types. Channel choice affects threads, transaction contexts, error handling, and retry semantics.

### DirectChannel

A synchronous flow normally handles messages on the caller/poller thread:

~~~text
IMAP poller thread
     |
     v
DirectChannel
     |
     v
Transformer -> Domain Handler
~~~

Advantages: easy to observe exceptions and transaction boundaries, minimal thread hopping. Disadvantages: slow parser/domain logic ties up the poller and increases mail pickup latency. If raw payloads still depend on an open folder, verify adapter lifecycle before running synchronously.

### ExecutorChannel

An asynchronous flow can look like:

~~~text
IMAP poller
     |
     v
Snapshot/normalize + persist source data
     |
     v
ExecutorChannel
     |
     v
Business handler in another thread
~~~

`ExecutorChannel` decouples threads yet **does not turn messages into a durable queue**. On a JVM crash, messages sitting only in an in-memory executor can be lost. To avoid dropping work between transport and processing, persist a snapshot/processing record first or use a queue/message store with proper guarantees.

### QueueChannel and Persistent MessageStore

An in-memory `QueueChannel` decouples producer/consumer in-process without durability. Spring Integration supports backing channels with `MessageStore`/JDBC depending on configuration. Still, evaluate:

- Is the payload serializable?
- Are you holding raw `MimeMessage` objects tied to `Store`/`Folder`?
- What are the transaction/ack/retry and ordering semantics?
- Is the `MessageStore` genuinely durable and schema-compatible?

In many applications, an **inbound processing table + domain outbox** remains easier to control than serializing `MimeMessage` directly into a persistent channel.

### When Should IntegrationFlow Emit Events?

`IntegrationFlow` works well for orchestrating steps. However, if domain events must commit atomically with business data, the decision point should be a **domain application service** writing to an event outbox inside the transaction, while the integration flow only triggers the service/observes outcomes. Never treat a Spring channel handler receiving an event as equivalent to durable event publishing.

## 29. Observing the Entire Chain from Inbound Mail to Domain Event

If a dashboard only reports **IMAP connection healthy**, the application may still emit zero events because the MIME parser fails, the database is down, or the inbox contains messages rejected by the domain.

Separate milestones:

~~~text
IMAP mail observed
     |
     v
Source key recorded
     |
     v
MIME normalized
     |
     v
Candidate classified
     |
     v
Domain state persisted
     |
     v
Event outbox committed
     |
     v
Event published / acked
     |
     v
Consumer processed
~~~

### Suggested Metrics

| Metric | Type | Meaning |
| --- | --- | --- |
| **inbound_mail_poll_total** | Counter | Poll count by outcome |
| **inbound_mail_discovered_total** | Counter | Source messages discovered |
| **inbound_mail_normalized_total** | Counter | Parse successes/failures |
| **inbound_mail_candidate_rejected_total** | Counter | Technical rejection reasons |
| **inbound_mail_domain_processed_total** | Counter | Source messages processed by outcome |
| **inbound_mail_duplicate_total** | Counter | Same source key already processed |
| **inbound_mail_pending_jobs** | Gauge | Source records awaiting business processing |
| **inbound_mail_oldest_pending_age_seconds** | Gauge | Age of oldest pending source record |
| **domain_event_outbox_pending** | Gauge | Committed events not yet published |
| **domain_event_publish_total** | Counter | Publish attempts by result |
| **domain_event_publish_duration_seconds** | Timer | Publish latency |
| **inbound_mail_flag_sync_failures_total** | Counter | Failures marking `SEEN`/moving |
| **inbound_mail_uidvalidity_changes_total** | Counter | Mailbox epoch changes |

These are **application-defined** metrics, not default metrics emitted out of the box by Spring Integration Mail. Exported Prometheus names may be normalized with `_total` suffixes per registry conventions.

### Low-Cardinality Labels

Use:

~~~text
purpose=support_reply|support_new|other
result=processed|duplicate|rejected|retry|review
reason=invalid_mime|too_large|unmatched_thread|...
source=imap|pop3|provider_webhook
~~~

Never attach **email addresses**, Subjects, UIDs, Message-IDs, `ticketId`s, or raw exception text to metric labels; doing so causes cardinality explosions and leaks data.

### Tracing Across Boundaries

~~~text
trace=inbound-mail-opaque-correlation
  span=mail.poll
  span=mail.source.identify
  span=mail.mime.normalize
  span=mail.domain.apply
  span=mail.outbox.commit
  span=mail.event.publish
~~~

When a Spring message crosses an asynchronous boundary, propagate correlation/trace context explicitly. Never place raw MIME into tracing attributes.

### Dashboards Separating Parse and Publish Lag

Example:

~~~text
Last successful IMAP poll:     2 sec ago
New source messages:          250 / hour
MIME parse failed:              3 / hour
Domain processed:             240 / hour
Pending inbound records:       18
Domain events not published:   120
Oldest event outbox age:       11 min
Flag sync failed:               4
~~~

If inbound counts keep rising while domain event outbox pending also grows, the fault likely lies in the **event publisher/broker**, not the IMAP receiver. If MIME parse failures spike, adding publisher workers will not fix the root cause.

## 30. Unit Testing Pure Mapping Logic

Functions mapping candidates to business decisions should be **easy to test without a mail server**. Use normalized inputs to test rules:

- Missing/blank Subject.
- Email body with HTML only, no `text/plain`.
- Sender does not match a customer.
- Mailbox tenant mismatch.
- Attachment exceeds limit.
- Automated email/DSN.
- Reply without a ticket mapping.
- Same source key already processed.

### Small Classifier Example

~~~java
public enum MailIntent {
    NEW_SUPPORT_REQUEST,
    SUPPORT_REPLY,
    AUTOMATED_MESSAGE,
    NEEDS_REVIEW
}

public record MailIntentDecision(
        MailIntent intent,
        String reason
) {
}

public final class SupportMailClassifier {

    public MailIntentDecision classify(
            InboundMailCandidate mail,
            boolean automaticMessage,
            boolean trustedReplyMappingExists
    ) {
        if (automaticMessage) {
            return new MailIntentDecision(
                    MailIntent.AUTOMATED_MESSAGE,
                    "AUTO_SUBMITTED"
            );
        }

        if (mail.subject() == null
                || mail.subject().isBlank()) {
            return new MailIntentDecision(
                    MailIntent.NEEDS_REVIEW,
                    "SUBJECT_MISSING"
            );
        }

        if (trustedReplyMappingExists) {
            return new MailIntentDecision(
                    MailIntent.SUPPORT_REPLY,
                    "KNOWN_THREAD"
            );
        }

        return new MailIntentDecision(
                MailIntent.NEW_SUPPORT_REQUEST,
                "NEW_REQUEST"
        );
    }
}
~~~

This is an illustrative classifier, not a complete algorithm for detecting automated emails or authenticating replies. In practice, both booleans must come from meaningful checks; in particular, **trustedReplyMappingExists** must not rely solely on matching a raw `In-Reply-To` string.

### JUnit Example

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;

class SupportMailClassifierTest {

    private final SupportMailClassifier classifier =
            new SupportMailClassifier();

    private InboundMailCandidate candidate(String subject) {
        return new InboundMailCandidate(
                new InboundMailSource(
                        "tenant-7", "mailbox-1", "INBOX", 42, 108
                ),
                "untrusted-message-id",
                "customer@example.test",
                List.of("support@example.test"),
                subject,
                "Problem description",
                null,
                List.of(),
                Instant.parse("2026-01-01T09:00:00Z"),
                Instant.parse("2026-01-01T09:01:00Z")
        );
    }

    @Test
    void rejectsEmptySubjectForReview() {
        MailIntentDecision decision = classifier.classify(
                candidate(""),
                false,
                false
        );
        assertEquals(MailIntent.NEEDS_REVIEW, decision.intent());
    }

    @Test
    void doesNotCreateTicketForAutoReply() {
        MailIntentDecision decision = classifier.classify(
                candidate("Automatic reply"),
                true,
                false
        );
        assertEquals(
                MailIntent.AUTOMATED_MESSAGE,
                decision.intent()
        );
    }

    @Test
    void knownAuthorizedThreadBecomesReply() {
        MailIntentDecision decision = classifier.classify(
                candidate("Re: Support request"),
                false,
                true
        );
        assertEquals(MailIntent.SUPPORT_REPLY, decision.intent());
    }
}
~~~

These unit tests do not verify MIME decoding, IMAP flags, or transactions. That is why boundary integration tests are also needed.

## 31. Integration Testing with an Isolated Mailbox

An integration test can run **GreenMail** (SMTP + IMAP) or a containerized test IMAP server:

~~~text
Test JVM
  |
  +-- JavaMailSender -> local SMTP fixture
  |                        |
  |                        v
  |                     Test INBOX
  |                        |
  '-- Spring Integration Mail inbound adapter
                           |
                           v
                    Candidate normalizer
                           |
                           v
                    Fake domain repository
                           |
                           v
                       Event outbox
~~~

### Fixture Assumptions

- The SMTP fixture delivers messages into a test mailbox without **relaying to the Internet**.
- The IMAP fixture supports reading and UID/flags when needed by tests.
- Usernames/passwords are test-only, never real accounts.
- Dynamic ports prevent collisions across tests.
- Tests never share mailbox state unintentionally.
- Timeouts are set on SMTP/IMAP operations.
- When testing TLS/auth, the fixture must genuinely enforce TLS/certificates/credentials, not merely capture mail.

### Example Sending a Test Email into the Mailbox

~~~java
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

public static void seedMailbox(
        String smtpHost,
        int smtpPort
) throws Exception {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost(smtpHost);
    sender.setPort(smtpPort);

    var message = sender.createMimeMessage();
    var helper = new MimeMessageHelper(
            message, false, "UTF-8"
    );
    helper.setFrom("customer@example.test");
    helper.setTo("support@example.test");
    helper.setSubject("Cannot log in");
    helper.setText("I cannot log in.");

    sender.send(message);
}
~~~

The fixture must provision the corresponding recipient and SMTP routing. The snippet only creates the test email—it **does not start Spring Integration**; the integration test itself starts the IMAP-receiving flow and asserts processing.

### Happy Path Test

~~~text
Given:
  Fixture INBOX has one valid email
  Domain customer mapping permits opening a ticket

When:
  Spring Integration polls/receives one message

Then:
  Candidate normalizes subject/body accurately
  Source key is recorded
  One support ticket is committed
  One SupportTicketOpened event is persisted
  Event carries valid eventId/schemaVersion/ticketId
~~~

### Same-Source Retry Test

~~~text
Given:
  UIDVALIDITY=42, UID=108 is already PROCESSED

When:
  Mail adapter receives the same source message again

Then:
  No new ticket is created
  No new domain event is created
  Flag sync may retry if the previous attempt failed
~~~

### Domain Transaction Rollback Test

~~~text
Given:
  Valid email
  Ticket repository throws an error before commit

When:
  Handler executes

Then:
  Ticket is not persisted
  Event outbox has no new SupportTicketOpened
  Processing record does not report PROCESSED
  Retry is allowed per policy
~~~

### Broker Unavailable Test

~~~text
Given:
  Business transaction committed ticket and event outbox
  Event broker is temporarily down

When:
  Publisher attempts to send event

Then:
  Event remains in outbox
  No second ticket is created
  When broker recovers, publisher reuses the same eventId
~~~

### Testing Read/Seen Behavior

If the system must keep messages `UNSEEN` until business commit, simulate:

1. Read the body with the real receiver/fetch configuration.
2. Parse/validate.
3. Inject a DB error.
4. Open a fresh IMAP session and verify the `SEEN` flag per policy.

Never use a mocked **MimeMessage** and conclude there are no side effects on the IMAP server.

## 32. Difficult Failure Scenarios Requiring Fault Injection

### Worker Crashes After Writing Ticket but Before Publishing Event

If the ticket and outbox share a transaction, the publisher can continue after restart. If code only calls **ApplicationEventPublisher** after saving and dies between the two steps without an outbox, the event can be lost.

### Worker Crashes After Publishing but Before Marking Published

The broker may have already received the event. The publisher retries with the same `eventId`; consumers must deduplicate. Never mint a new domain event merely to "resend", as that breaks idempotency.

### IMAP Reconnects with a New UIDVALIDITY

Old source checkpoints may be invalid. Tests must verify old UIDs are not conflated with new UIDs and previously emitted event states are not wiped.

### Two Replicas Poll the Same Mailbox

Both may receive the same source UID. Concurrency tests with database unique keys and atomic claims prove only one business mutation commits, even when two Spring messages are created.

### Reading Body Flips the Message to SEEN Automatically

Test with an IMAP fixture and the chosen receiver configuration. If messages must stay unread, MIME parsing must not mark mail as read before the business transaction succeeds.

### External API Times Out After Creating a Ticket

An external ticket API may have created the ticket before the response was lost. Retrying without an idempotency key creates two tickets. Tests should simulate **server accepted / client timeout**, then verify the system records **UNKNOWN** and reconciles or retries with a provider-enforced idempotency key.

### Message with Many Multipart Levels and Oversized Attachments

A syntactically valid MIME tree with too many parts or huge files can exhaust worker memory. Parser tests must enforce input/resource limits aligned with operational requirements.

### Spoofed Header Attempting to Access Someone Else's Ticket

A sender sets `In-Reply-To` matching a ticket ID they are unauthorized to touch. The domain must reject or route to review; no `SupportReplyAdded` event is emitted.

### Continuous Automated Emails

Fixtures seed DSNs/auto-replies into `INBOX`. The system must classify and cap responses without entering an auto-reply loop.

## 33. Runbook When Email Arrives Without a Domain Event

When a user reports "I sent an email and no ticket appeared", never immediately replay the whole mailbox. Walk through pipeline milestones to find where processing stopped.

### Step 1 — Verify Email Source

- Are the right mailbox and folder being monitored by the app?
- Are IMAP/POP3 credentials still valid?
- Are TLS, hostname, and port correct?
- Is the adapter polling/IDLEing and recording recent successes?
- Was the email moved, expunged, or marked `SEEN` before the adapter searched?
- Are multiple replicas/consumers contending over the mailbox?

Do not assume every email sent to an address shown in `To` lands in the configured `INBOX`. Providers apply routing, aliases, and spam folders.

### Step 2 — Check Discovery and Source Key

Search by source identity:

~~~text
tenant
mailbox
folder
UIDVALIDITY
UID
~~~

If no source record exists, the fault likely sits in the inbound adapter/filter/UID checkpoint. If a **PROCESSED** record exists, do not replay blindly; inspect the recorded business record/event ID.

### Step 3 — Check Normalization and Validation

- Did the MIME parser reject due to unsupported charset/content type?
- Was the email body inside `multipart/alternative` or an embedded attachment?
- Did it exceed size/part/depth limits?
- Was it classified as automated mail, spam, or a DSN?
- Is tenant/customer mapping valid?
- Does it need manual review due to an unverified source?

When investigating, inspect metadata and error categories rather than dumping raw MIME containing PII into logs.

### Step 4 — Check Domain Persistence

Does a corresponding ticket/reply exist? If the service logged a duplicate, that may be expected behavior when the message was already processed earlier. If a DB error occurred, check whether the transaction committed or rolled back.

If an external ticket API timed out, the side effect may already have occurred; check idempotency keys or reconcile before retrying.

### Step 5 — Check Event Outbox

~~~text
Business state committed?
         |
         +-- No  -> Review domain processing
         |
         '-- Yes
              |
              v
       Event outbox exists?
             |           |
             No          Yes
             |           |
             v           v
         Transaction/   Published?
         persistence       |           |
         design issue      No          Yes
                          |           |
                          v           v
                     Publisher/      Consumer
                     broker issue    processing
~~~

If the event outbox already has the record un-published, the bug is no longer in IMAP or the parser. Fix the publisher/broker instead of re-running the domain service.

### Step 6 — Safe Recovery

- **IMAP fetch error:** re-poll using source checkpoint/UID.
- **Permanent MIME error:** quarantine/review, never infinite retry.
- **DB transaction rollback:** retry processing idempotently.
- **Business side effect `UNKNOWN`:** reconcile; never recreate unconditionally.
- **Event outbox pending:** retry publishing with the same event ID.
- **Flag sync failed:** retry setting `SEEN`/moving only; never recreate the ticket.

### Step 7 — Confirm Recovery

After incident remediation, verify:

1. The source UID is recorded once in the identity table.
2. The appropriate business mutation committed.
3. The event outbox holds the right event ID.
4. Broker/consumers received the event per contract.
5. No duplicate events or tickets exist.
6. Mailbox flags are synced per policy.
7. Failures in one mailbox did not impact others.

## 34. Common Design Mistakes

### Mistake 1 — Treating Every Read Email as a Domain Event

An auto-reply, spam, or unauthenticated message may carry no valid business event. Only emit domain events after validation and domain mutation.

### Mistake 2 — Mixing Jakarta Mail Message and Spring Message

Two classes share the same name at different layers. One is a MIME/mailbox object; the other is an envelope passed between Spring Integration components. Define clear payload contracts and imports.

### Mistake 3 — Casting Every Payload to MimeMessage

Receivers may return simplified/transformed payloads or multiple messages depending on settings. Validate the payload contract at the boundary instead of casting inside domain services.

### Mistake 4 — Using From as a Trusted User ID

`From` can be spoofed. Use customer identity resolution, permission checks, and appropriate trusted authentication evidence.

### Mistake 5 — Using Message-ID as the Sole Unique Key

Sender-supplied headers can be missing or duplicated; use an appropriate source identity such as `mailbox + folder + UIDVALIDITY + UID`, and persist separate idempotency records.

### Mistake 6 — Reading UID After the Folder Closed

Downstream `MimeMessage` objects may no longer hold IMAP context. Extract UID/source metadata at the receiver boundary while still available, then save/enrich before async handoff.

### Mistake 7 — Marking SEEN Immediately When the Adapter Receives

The business handler may fail, and the next poll misses `UNSEEN`. Separate read state from processing state, use UID deduplication, and sync flags after commit.

### Mistake 8 — Treating SEEN as a Lock

Two consumers can observe `UNSEEN` concurrently. Use atomic DB claims and unique constraints; never rely on `SEEN` for deduplication.

### Mistake 9 — Publishing Events Before Business Commit

Consumers may see an event while the ticket does not exist or the transaction rolls back. Persist domain events into an outbox in the same transaction and publish after commit.

### Mistake 10 — Relying Only on @TransactionalEventListener for Delivery

An `AFTER_COMMIT` callback defers handlers until after the transaction, yet if the JVM dies right after commit or the broker rejects it, the event can be lost unless persisted durably. Use a transactional outbox when crash reliability is needed.

### Mistake 11 — Minting a New Event ID on Publisher Retries

Consumers struggle to deduplicate the same event. Event IDs must be stored once in the outbox and reused by the publisher.

### Mistake 12 — Retrying the Entire Flow When Flag-Sync Fails

The ticket committed yet setting `SEEN` failed; retrying the entire flow can create duplicate tickets. Retry only the flag-sync step.

### Mistake 13 — Serializing Raw MIME onto the Event Bus

Payloads become huge, carry sensitive data, and couple to protocol implementations. Emit minimal domain facts and attachment references.

### Mistake 14 — Trusting Content-Type or Filename on Attachments

Senders can forge metadata. Verify bytes, scan, cap sizes, and use server-generated storage keys.

### Mistake 15 — Treating HTML as Safe Content

Email HTML can contain malicious markup, remote trackers, and fake links. Sanitization/escaping and content policies are mandatory when rendering.

### Mistake 16 — Treating an In-Memory ExecutorChannel as a Durable Queue

On a process crash, unprocessed messages can be lost. Persist source snapshots/processing state or use a real persistent store before going asynchronous.

### Mistake 17 — Confusing Broker ACK with Business Success

Broker acceptance does not prove downstream consumers processed the event. Monitor consumers, idempotency, and error/DLQ policies separately.

### Mistake 18 — Ignoring UIDVALIDITY Changes

Old UIDs can point to different messages after a mailbox reset. Compare `UIDVALIDITY` and resynchronize rather than ignoring epoch changes.

### Mistake 19 — Using Email Date as Domain Event occurredAt

The `Date` header can be wrong or forged. Event `occurredAt` should reflect when the domain action actually committed/was recorded on the system's trusted clock.

### Mistake 20 — Auto-Replying to Every Email

DSNs and auto-responses can trigger loops. Classify `Auto-Submitted` and bounces, rate-limit, and govern automated replies by policy.

### Mistake 21 — Using Raw In-Reply-To to Access Tickets

Threading headers do not replace authorization. Match parent messages and verify tenant/customer permissions.

### Mistake 22 — Logging Full Raw MIME on Exceptions

MIME can hold OTPs, reset tokens, PII, and attachments. Log reason codes/correlation IDs; store detailed diagnostics in an access-controlled location.

### Mistake 23 — Not Separating Permanent Failures from Transient Ones

Malformed MIME gets retried forever, or transient network timeouts get dropped permanently. Classify properly and route to quarantine/review.

### Mistake 24 — Deleting Emails from the Mailbox as a Default ACK

Deletion/expunge can erase unprocessed data and disrupt shared mailboxes. Only use destructive operations with formal policies, retention, and recovery paths.

### Mistake 25 — Counting Received Emails as Domain Events

Not every email produces a ticket/event. Dashboards must distinguish discovered, normalized, rejected, processed, outbox published, and consumer handled.

## 35. Practice Scenarios

### Scenario A — One Email Creates Two Tickets

Two pods poll the same IMAP `INBOX` and both receive UID 108.

**Question:** Is using `SEEN` enough to prevent duplicates?

**Answer:** No. You need a source key by `UID`/`UIDVALIDITY` and atomic DB claim/unique constraints. Domain operations must also be idempotent when external side effects exist.

### Scenario B — MIME Parser Succeeds but No Ticket Exists

The parser returned `InboundMailCandidate`, yet the customer resolver finds the sender lacks authorization.

**Question:** Should `SupportTicketOpened` be emitted?

**Answer:** No. A candidate is only technical data; a domain event requires a valid, persisted business state change.

### Scenario C — Email with Subject "APPROVE INVOICE"

`From` displays a manager's name, without sender/permission verification.

**Question:** Emit an `InvoiceApproved` event?

**Answer:** No. Never use raw `From`/Subject as authorization. Route to a stronger confirmation workflow.

### Scenario D — Publisher Encounters a Broker Outage

The ticket committed and `SupportTicketOpened` sits in the event outbox.

**Question:** Do we need to re-poll the email to emit the event?

**Answer:** No. Retry the publisher on the outbox record using the same event ID. Never create the ticket again.

### Scenario E — IMAP SEEN Flag Fails to Update

The ticket was created, yet the message remains `UNSEEN` due to a network error.

**Question:** Should the next poll create a new event?

**Answer:** No. The source key is already `PROCESSED`; only retry flag-sync if policy wants messages marked read.

### Scenario F — Encoded Vietnamese Subject

Raw headers contain MIME encoded-words instead of readable text.

**Question:** Should the raw header be copied as-is into the domain event?

**Answer:** Use appropriate Jakarta Mail APIs/decoders to normalize strings, bound length, and handle malformed encodings. Never log sensitive raw bodies/headers.

### Scenario G — 30 MiB Attachment

The event broker caps payloads at a few MiB while a sender attaches a huge file.

**Question:** Should the file be Base64-encoded inside the event?

**Answer:** No. Validate/scan and store in appropriate storage, carrying a controlled reference ID in the event, or reject per policy.

### Scenario H — UIDVALIDITY Changes

The mailbox is restored; UID 108 in the new epoch is not the old message.

**Question:** Should the source key change?

**Answer:** Yes, because `UIDVALIDITY` is part of the identifier. Rescan/reconcile instead of reusing the old UID directly.

### Scenario I — ExecutorChannel Loses Work on JVM Crash

The adapter pushed a `MimeMessage` to an in-memory executor and the process died.

**Question:** Can you guarantee the email will still create a ticket?

**Answer:** Not from `ExecutorChannel` alone. Persist source/snapshot durably or guarantee rescan and deduplication; a raw `MimeMessage` may depend on a closed connection.

### Scenario J — Auto-Reply Email

A sender receives an automated response from the system; the mailbox keeps receiving "Out of office".

**Question:** Should it keep opening tickets and replying?

**Answer:** Depending on policy, usually classify auto-replies/DSNs and prevent reply loops; never emit `SupportTicketOpened` unconditionally.

### Scenario K — HTML-Only Body

The parser only reads `text/plain` and returns an empty body.

**Question:** Is the email definitely empty?

**Answer:** Not necessarily. Support multipart/HTML per policy, extract text safely, or send to manual review if unprocessable.

### Scenario L — Same Message-ID on Two Messages

Two emails sent to a mailbox carry the same `Message-ID` header.

**Question:** Should the second email be skipped as a duplicate?

**Answer:** Never rely on `Message-ID` alone. Use mailbox source keys and appropriate business deduplication rules.

### Scenario M — Reply Email to Another Tenant's Ticket

`In-Reply-To` matches an outbound message, yet sender/tenant do not match.

**Question:** Should `SupportReplyAdded` be created?

**Answer:** No if authorization fails. Threading headers are hints, not permission to mutate an aggregate.

### Scenario N — Domain Event Delivered Twice by Broker

The publisher timed out after the first send and retried the same record.

**Question:** What should the consumer do?

**Answer:** Deduplicate by stable `eventId`/aggregate version and skip executing side effects a second time if already handled.

### Scenario O — Should Events Be Emitted Before Commit?

A developer calls `publisher.publishEvent` directly inside the transformer for faster response.

**Question:** What is the risk?

**Answer:** Events can be published even though the domain transaction has not committed or rolls back, and transformer retries can emit duplicates. Persist to an event outbox in the transaction and publish after commit.

### Scenario P — setFlag Failure Makes HTTP Return Error

The application created the ticket successfully yet could not mark `SEEN`.

**Question:** Should the user see "ticket creation failed"?

**Answer:** Not necessarily. Business success and mailbox flag-sync are separate outcomes. Report the ticket created and enqueue a retryable flag-sync job.

### Scenario Q — Support Email Contains a Password Reset Link

The body may contain a one-time token.

**Question:** Should the event carry the raw content?

**Answer:** Only if genuinely needed and permitted; normally the event carries `ticketId`/source reference while sensitive content stays in domain storage with separate permissions and retention.

### Scenario R — Unversioned Domain Event

Older consumers break when the producer adds a new required field.

**Question:** How should this be organized?

**Answer:** Use `schemaVersion`/schema registries/compatibility contracts, evolve schemas by rule, and test consumer contracts before release.

## 36. Implementation Workflow from Inbox to Domain Event

An implementation plan can follow clear phases:

~~~text
IDENTIFY BUSINESS RULES
      |
      +-- Which email types trigger actions?
      +-- Which domain invariants must hold?
      +-- Which sender sources are trustworthy?
      '-- Which events represent what happened?
      |
      v
DESIGN MAIL INGESTION
      |
      +-- IMAP/IMAPS or provider webhook?
      +-- Mailbox/account/folder mapping?
      +-- TLS/auth and secret management?
      +-- Polling / IMAP IDLE / backoff?
      '-- Spring Integration payload contract?
      |
      v
NORMALIZE MIME
      |
      +-- Header/text/HTML/attachment parser
      +-- Size/parts/depth/charset limits
      +-- Source identity UID + UIDVALIDITY
      +-- Security/privacy controls
      '-- InboundMailCandidate
      |
      v
VALIDATE + CLASSIFY
      |
      +-- Tenant/mailbox authorization
      +-- Sender trust/identity resolution
      +-- Anti-loop / auto-reply detection
      +-- Ticket/order threading
      '-- Domain invariants
      |
      v
DURABLE PROCESSING
      |
      +-- Atomic dedup/claim source
      +-- Transactional domain mutation
      +-- Mark inbound PROCESSED
      '-- Save domain event into outbox
      |
      v
EVENT DISPATCH
      |
      +-- Publish stable eventId
      +-- Retry with backoff
      +-- Consumer idempotency
      '-- DLQ/reconciliation if necessary
      |
      v
MAILBOX STATE SYNCHRONIZATION
      |
      +-- Optional mark SEEN
      +-- Optional move/label
      '-- Retry flag-sync separately
      |
      v
OBSERVABILITY + TESTING
      |
      +-- Source discovery and lag
      +-- MIME/domain error categories
      +-- Event outbox health
      +-- Duplicate prevention
      '-- Fault injection and incident runbook
~~~

### A Sensible Package Structure

~~~text
com.example.inboundmail
  |
  +-- adapter
  |     +-- ImapInboundFlowConfiguration
  |     +-- MailSourceIdentityExtractor
  |     '-- MailReceiverHandler
  |
  +-- parsing
  |     +-- MimeNormalizer
  |     +-- SafeAttachmentExtractor
  |     '-- InboundMailCandidate
  |
  +-- application
  |     +-- InboundMailProcessingService
  |     +-- MailIntentClassifier
  |     +-- SenderAuthorizationPolicy
  |     '-- InboundProcessingRepository
  |
  +-- domain
  |     +-- SupportTicket
  |     +-- SupportTicketOpened
  |     '-- SupportReplyAdded
  |
  +-- persistence
  |     +-- ProcessedMailEntity
  |     +-- DomainEventOutboxEntity
  |     '-- AttachmentStorageAdapter
  |
  +-- publishing
  |     +-- OutboxPublisher
  |     '-- EventSerializer
  |
  '-- operations
        +-- MailMetrics
        +-- MailErrorClassifier
        '-- MailboxFlagSyncWorker
~~~

This partitioning is illustrative; not every class needs its own package. The key is that **domain** never needs to import Jakarta Mail or Spring Integration APIs, keeping the business model clean and able to accept events from other channels.

### Separate "Receive and Persist" from "Process and Publish"

One pattern persists an **InboundMailSnapshot** immediately upon receiving MIME, then lets background workers read snapshots to process. Advantage: reduces IMAP connection dependency and eases retries; trade-off: raw email data must be protected in storage with clear retention. For small workloads with fast business handlers, you can start with a synchronous flow while still keeping idempotency and an event outbox at the domain boundary.

### Never Work Asynchronously Before Data Is Durable

If a worker receives a `MimeMessage` and pushes it onto an in-memory queue, a process crash can lose work. When zero misses are required, persist source identity/snapshots or ensure **IMAP UID rediscovery** with uncorrupted flags. Never let the receiver delete messages before durable persistence finishes.

## 37. Implementation and Testing Checklist

### Inbound Transport

- **Protocol:** identified IMAP/POP3/webhook and flag/UID differences?
- **Connection:** TLS/hostname verification, timeouts, and secure credentials/OAuth?
- **Mailbox:** accurate tenant, account, folder; handles renames/resets/`UIDVALIDITY`?
- **Receiver:** payload shape, auto-`SEEN`, and auto-delete behavior verified?
- **Lifecycle:** source identity extracted before folders/connections close?
- **Concurrency:** multiple pollers/workers protected by atomic dedup/claims?

### MIME and Security

- **Parser:** supports plain/HTML/multipart per use case?
- **Limits:** bounded raw bytes, MIME depth, part count, attachment size, and processing time?
- **Charsets:** controlled handling of Unicode and malformed inputs?
- **Attachments:** scanned, content-type validated, server-generated storage keys?
- **HTML:** unsanitized content never rendered directly?
- **Trust:** `From`/Subject/`Message-ID` never treated as sender authority?
- **Auto-reply:** DSN/auto-response loops prevented?
- **Privacy:** raw bodies, OTPs, passwords, access tokens, or attachments never logged?

### Domain Mapping

- **Boundary:** `MimeMessage`, Spring `Message`, and domain events clearly separated?
- **Candidate:** raw sender, tenant/mailbox identity, timestamps, and source keys normalized?
- **Classification:** each email type has an explicit accept/reject/review decision?
- **Authorization:** sender and ticket/order relationship verified?
- **Domain event:** named as a past-tense fact, not a command?
- **Schema:** stable `eventId`, `schemaVersion`, `aggregateId`, and correlation?
- **Payload:** minimal necessary data, never blindly copying raw MIME?

### Durability and Recovery

- **Source key:** `tenant + mailbox + folder + UIDVALIDITY + UID` clearly defined?
- **Claim:** unique constraints/leases/versions block concurrent processing?
- **Commit:** domain mutation, processed record, and event outbox share a transaction where appropriate?
- **Publish:** broker outages never lose committed domain events?
- **Consumer:** deduplication by `eventId` and redelivery handling?
- **Retry:** distinguishes transient parse, permanent, and `UNKNOWN` business outcomes?
- **SEEN:** optional post-commit flag-sync, retried independently on failure?
- **Recovery:** runbook exists if `UIDVALIDITY` changes or source messages are expunged?

### Tests and Operations

- **Unit tests:** normalization, classification, unauthorized replies, auto-responses?
- **Integration tests:** SMTP/IMAP fixtures, UID persistence, and receiver flags?
- **Failure injection:** crash between commit/publish, broker unavailable, duplicate polls?
- **Monitoring:** metrics for poll, normalize, domain processed, outbox pending, flag sync?
- **Alerts:** detects event publish lag, mailbox connection failures, and pending backlogs?
- **Data governance:** clear raw email retention, storage access control, and audits?

This checklist is an implementation guide. A simple system may not need every piece, yet **risks around identity, idempotency, event consistency, and sensitive data** must be designed explicitly rather than left to mail adapter defaults.

## 38. Summary of Core Principles

~~~text
jakarta.mail.Message
    = email/MIME data from mailbox

org.springframework.messaging.Message<?>
    = message flowing through Spring Integration channels

InboundMailCandidate
    = normalized email not yet accepted by the domain

Domain event
    = business fact after validation and successful mutation

From / Subject / Message-ID
    != authorization proof

IMAP UID + UIDVALIDITY + folder + mailbox
    = better source identity than message number

SEEN
    != PROCESSED
    != a lock
    != event published

Transformer
    -> normalizes data, causes no domain side effects itself

Application Service
    -> validates + enforces invariants + persists business state

Transactional Outbox
    -> persists domain events atomically with business commit

Stable Event ID
    -> enables publish retries and consumer deduplication

Attachment reference
    -> better than embedding raw MIME/bytes in events

UNKNOWN external outcome
    -> reconcile, never retry blindly

Flag-sync failure
    -> retry read flag separately, never recreate ticket
~~~

**Converting a mail message into a domain event** in Spring Integration Mail is not merely grabbing Subject/Body from `MimeMessage` and emitting a Java object onto a message channel. It is a critical boundary between **external email data that can be forged and repeated** and **system-verified business events**. Spring Integration helps receive mail and organize the pipeline; Jakarta Mail provides MIME/Store/Folder access; and the application must own source identity, content normalization, authorization checks, deduplication, transactions, and durable publishing. By separating **mail transport**, **integration candidates**, and **domain facts**, and using proper source keys, transactional outboxes, and independent IMAP flag sync, systems can open tickets or record replies from email without losing events, creating duplicate side effects, or turning untrusted email content into business privileges.
