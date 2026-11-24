# Sending Scope of JavaMailSender vs. Reading Mail in Spring Framework Mail

In Spring Framework Mail, `JavaMailSender` is the familiar abstraction for **sending emails**. Developers can create a `SimpleMailMessage` or `MimeMessage`, configure the SMTP host, username, and password, and call `send(...)`. However, when an application needs to **read an Inbox**, find new emails, download received attachments, or process reply messages, `JavaMailSender` alone is not enough.

This is an important architectural boundary: **sending email** and **reading email** are two different types of operations, typically using different protocols, permissions, state, and connection lifecycles. The sending side works with SMTP submission; the reading side typically works with IMAP, POP3, or a mailbox provider's proprietary API.

This lesson explains the exact API scope of Spring Mail, how to use Jakarta Mail to access mailboxes, why you cannot "read sent emails" using only `JavaMailSender`, Java/Spring examples for both directions, MIME and attachment handling, UID management, security, choosing Spring Integration Mail, as well as testing and operational rules.

## 1. Short Answer: What Does JavaMailSender Do and Not Do?

`JavaMailSender` resides in the `org.springframework.mail.javamail` package, extends `MailSender`, and adds the ability to work with MIME messages.

Main capabilities:

- Create a `MimeMessage` using `createMimeMessage()`.
- Send a plain-text `SimpleMailMessage`.
- Send a `MimeMessage` with HTML, attachments, inline resources, and multiple headers.
- Use Jakarta Mail transport to communicate with the configured SMTP server.
- Report preparation, authentication, or submission errors through appropriate exceptions.

Capabilities that are **not part of the JavaMailSender contract**:

- Opening an Inbox mailbox.
- Listing received messages.
- Finding unread messages in a mailbox.
- Reading the content of emails others have sent to the account.
- Managing IMAP folders or `SEEN`, `ANSWERED`, `DELETED` flags.
- Synchronizing a mailbox after reconnecting.
- Searching messages by IMAP UID or POP3 UIDL.
- Providing webhooks for incoming emails out of the box.
- Automatically marking a sent SMTP message as delivered or opened.

**Conclusion:** `JavaMailSender` is a sender, not an all-purpose "JavaMailReceiver" of Spring Framework Mail.

## 2. Sending Flow and Reading Flow Diagram

Both directions can use the same underlying Jakarta Mail library, but not the same protocol.

~~~text
                     SPRING APPLICATION
                            |
              +-------------+-------------+
              |                           |
              v                           v
        SEND EMAIL                   READ EMAIL
              |                           |
       JavaMailSender                Jakarta Mail
              |                      Session + Store
              v                           |
       SMTP transport                     v
              |                      IMAP / POP3
              v                           |
      Submission relay                    v
              |                       Mailbox
              v
      Receiving system
              |
              v
         Recipient mailbox
~~~

On the sending path, the application is an **SMTP client** talking to an SMTP submission server. On the reading path, the application is a **mailbox client** connecting to a mailbox server through `Store` and `Folder`.

The same provider may offer both services, but the endpoints, ports, authentication scopes, and policies are usually different.

## 3. SMTP, IMAP, and POP3 Serve Different Purposes

| Protocol | Primary Purpose | Common Ports | Objects the Application Operates On |
| --- | --- | ---: | --- |
| SMTP submission + STARTTLS | Send email to a relay | 587 | Envelope, DATA, submission response |
| SMTP implicit TLS | Send email over an initially TLS connection | 465 | Similar to SMTP submission |
| SMTP relay | Transfer between mail servers | 25 | Server-to-server forwarding |
| IMAP | Retrieve and manage server-side mailboxes | 143; IMAPS 993 | Folder, message, flags, UID |
| POP3 | Download mail from a mailbox with a simple model | 110; POP3S 995 | Message retrieval, UIDL if supported |

These are common ports; not every provider offers all of those exact ports. Always use endpoints according to the provider's documentation.

**SMTP has no standard command to "list emails in an Inbox".** Conversely, IMAP cannot replace an SMTP transport used to send messages to external recipients.

### Why Is It Necessary to Distinguish Them?

If an application stores `spring.mail.host=smtp.example.com` and then uses that host with `Store.getFolder("INBOX")`, the connection will fail because the SMTP endpoint may not provide IMAP. Similarly, using port 993 for a `JavaMailSenderImpl` configured with the SMTP protocol does not mean it will be able to send mail.

## 4. MailSender and JavaMailSender in Spring

Spring Mail has two abstraction levels:

| API | Supported Objects | Purpose |
| --- | --- | --- |
| `MailSender` | `SimpleMailMessage` | Send plain-text email |
| `JavaMailSender` | `SimpleMailMessage` and `MimeMessage` | Create MIME, send HTML/attachments/inline |
| `JavaMailSenderImpl` | Primary implementation | Configure host, port, protocol, credentials, and JavaMail properties |
| `MimeMessageHelper` | Helper when building a message | Set From/To/Subject, HTML, multipart, attachments |

Common usage example:

~~~java
JavaMailSender mailSender = ...;

MimeMessage message = mailSender.createMimeMessage();

// Use MimeMessageHelper to prepare the content.
mailSender.send(message);
~~~

There is no standard `mailSender.receive()` to fetch emails from an Inbox. A `JavaMailSenderImpl` can expose its internal Jakarta Mail `Session`, but **do not treat the sender as a mailbox reader because of that**. Service boundaries and credentials should be kept separate.

## 5. Spring Boot Configuration for Sending Email

When an application has `spring-boot-starter-mail`, Spring Boot can configure `JavaMailSender` from `spring.mail.*`.

Example `application.yml`:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
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
~~~

These values are examples. `SMTP_USERNAME`/`SMTP_PASSWORD` must be injected from the environment or a secret manager; do not commit real credentials.

Meaning:

- `spring.mail.host/port` points to the SMTP submission server.
- `spring.mail.username/password` provides credentials for the chosen SMTP AUTH mechanism.
- `mail.smtp.auth` enables authentication on the SMTP transport.
- `mail.smtp.starttls.*` configures upgrading the connection to TLS.
- `mail.smtp.ssl.checkserveridentity` helps verify the server certificate's hostname.
- `mail.smtp.*timeout` prevents indefinite network waits.

**These properties do not automatically create an inbound mail listener or an IMAP mailbox reader.** To read mail, separate configuration and an appropriate implementation are required.

## 6. Example of Sending Email with JavaMailSender

Plain-text sending service:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationSender {

    private final JavaMailSender mailSender;

    public NotificationSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String orderCode) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("orders@example.com");
        mail.setTo(recipient);
        mail.setSubject("Order confirmation " + orderCode);
        mail.setText(
            "Order " + orderCode + " has been confirmed."
        );

        mailSender.send(mail);
    }
}
~~~

The service builds the message and sends it over SMTP. It **does not access the Inbox** of `orders@example.com`, does not automatically create a copy in the Sent folder, and does not guarantee that the message appears in the recipient's Inbox.

### With HTML and Attachments

~~~java
MimeMessage mime = mailSender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("New invoice");
helper.setText(
    "Your invoice has been issued.",
    "<html><body><h1>Invoice</h1>"
        + "<p>Please see the attached file.</p>"
        + "</body></html>"
);

helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(pdfFile)
);

mailSender.send(mime);
~~~

`pdfFile` is a valid `java.io.File` prepared by the application. You must ensure the resource exists, is readable, and is permitted to be sent. Spring Mail supports many content types, but still only operates in the **outgoing SMTP submission** direction.

## 7. When send Returns Successfully, What Has Actually Been Confirmed?

You must distinguish these milestones:

~~~text
CREATED
   |
   v
ENQUEUED
   |
   v
SMTP submission attempt
   |
   v
SMTP accepted
   |
   v
Downstream relay/filtering
   |
   v
DELIVERED / DEFERRED / BOUNCED
   |
   v
Recipient reads or interacts (if evidence exists)
~~~

`JavaMailSender.send(...)` completing normally typically corresponds to successful SMTP submission under the transport's contract. That does not mean:

- The recipient has received it in their Inbox.
- The message was not filtered as spam.
- The recipient has opened or read it.
- The provider will not bounce it later.
- The email has appeared in the sending account's Sent folder.

A successful SMTP reply after `DATA` is evidence that the connected relay accepted the message. Downstream delivery is a separate stage, requiring provider events, DSNs, or separate mailbox information when access is permitted.

If the sender throws an exception, you also must not assume no recipient received it: a timeout after `DATA` or a partial send can produce an uncertain outcome.

## 8. Jakarta Mail Uses Store and Folder to Read

For IMAP/POP3, Jakarta Mail provides these key abstractions:

| Type | Role |
| --- | --- |
| `Session` | Configure JavaMail providers and properties |
| `Store` | Connect to a mailbox store over IMAP/POP3 |
| `Folder` | Folders such as INBOX, Sent, Archive |
| `Message` | An email in a folder |
| `MimeMessage` | Representation of a MIME message with headers/body |
| `Multipart` | Container of multiple MIME parts |
| `BodyPart` | A text, HTML, attachment, or inline part |
| `Flags` | Read, flagged, deleted status, etc. |
| `SearchTerm` | Criteria for searching messages |
| `UIDFolder` | Work with UID/UIDVALIDITY on supporting folders |

The sending side typically uses `Transport` underneath `JavaMailSender`; the reading side uses `Store` and `Folder`.

~~~text
Jakarta Mail Session
        |
        +--> Transport (SMTP) --> send
        |
        +--> Store (IMAP) ------> Folder --> Message
        |
        +--> Store (POP3) ------> retrieval
~~~

Do not confuse `MimeMessage` with "reading email": it is a **data type representing email content**, which can appear in both sending and receiving flows. It does not open a connection to a mailbox by itself.

## 9. Separate Inbound Mailbox Configuration

Spring Boot's `spring.mail.*` targets SMTP sending. For a custom inbox reader, you can create a separate configuration namespace, for example:

~~~yaml
app:
  mail:
    incoming:
      protocol: imaps
      host: imap.example.com
      port: 993
      username: ${INBOX_USERNAME}
      password: ${INBOX_PASSWORD}
      folder: INBOX
      poll-batch-size: 20
~~~

The `app.mail.incoming.*` settings are **application-defined properties**, not configuration that automatically enables a Spring Boot inbox reader.

They can be bound with `@ConfigurationProperties`:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail.incoming")
public record IncomingMailProperties(
    String protocol,
    String host,
    int port,
    String username,
    String password,
    String folder,
    int pollBatchSize
) {}
~~~

To have Spring create this bean, you can use `@EnableConfigurationProperties(IncomingMailProperties.class)` or configuration properties scanning according to your project.

You should have separate security configuration, validation, and secret management for inbound mail. Do not assume an SMTP username/password can log in to IMAP; the provider or tenant may issue different credentials and permissions.

## 10. An IMAP Inbox Reading Example Using Jakarta Mail

The following example reads **metadata of a number of the latest messages in folder order**. It does not process the entire mailbox and does not automatically mark messages as read; the goal is to clearly illustrate `Session → Store → Folder → Message`.

~~~java
import jakarta.mail.Address;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.internet.InternetAddress;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Properties;

import org.springframework.stereotype.Service;

@Service
public class ImapInboxReader {

    private final IncomingMailProperties settings;

    public ImapInboxReader(IncomingMailProperties settings) {
        this.settings = settings;
    }

    public List<IncomingMailSummary> readLatest(int requestedLimit)
            throws MessagingException {

        int limit = Math.max(1, Math.min(requestedLimit, 100));

        Properties props = new Properties();
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(
                settings.host(),
                settings.port(),
                settings.username(),
                settings.password()
            );

            Folder inbox = store.getFolder(settings.folder());
            inbox.open(Folder.READ_ONLY);

            try {
                int total = inbox.getMessageCount();
                if (total <= 0) {
                    return List.of();
                }

                int first = Math.max(1, total - limit + 1);
                Message[] messages = inbox.getMessages(first, total);

                List<IncomingMailSummary> result = new ArrayList<>();

                for (Message message : messages) {
                    Address[] from = message.getFrom();
                    String sender = null;

                    if (from != null && from.length > 0) {
                        Address firstFrom = from[0];
                        if (firstFrom instanceof InternetAddress ia) {
                            sender = ia.getAddress();
                        } else {
                            sender = firstFrom.toString();
                        }
                    }

                    Date received = message.getReceivedDate();

                    result.add(new IncomingMailSummary(
                        sender,
                        message.getSubject(),
                        received == null
                            ? null
                            : received.toInstant()
                    ));
                }

                return result;
            } finally {
                if (inbox.isOpen()) {
                    inbox.close(false);
                }
            }
        } finally {
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

DTO:

~~~java
import java.time.Instant;

public record IncomingMailSummary(
    String fromAddress,
    String subject,
    Instant receivedAt
) {}
~~~

The example uses `imaps`/port 993. `session.getStore("imaps")` opens the corresponding protocol provider. `READ_ONLY` prevents the application from modifying flags via the API while reading.

This snippet is a **bounded metadata read**, not a production mailbox synchronization engine: it only fetches up to the last 100 messages in folder order and has no checkpoint, UID deduplication, or content processing. The following sections explain the elements needed to scale it up.

## 11. How to Close Store and Folder Properly

IMAP maintains network connections and server-side state. If resources are not closed:

- Connections can be exhausted.
- Folders can remain in an open state.
- The mail server has to retain sessions for a long time.
- Workers fail to release sockets/threads on time.
- Subsequent tests are affected by stale connections.

The safe order is usually:

1. Create `Session`.
2. Obtain and connect `Store`.
3. Obtain and open `Folder`.
4. Read metadata/body within the permitted scope.
5. Close `Folder` in `finally`.
6. Close `Store` in `finally`.

~~~java
Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

try {
    // Read messages.
} finally {
    if (folder.isOpen()) {
        folder.close(false);
    }
}
~~~

`close(false)` does not request expunging messages marked for deletion. In some protocols or provider behaviors, flag operations still have their own semantics; do not use `READ_WRITE` folders or `expunge` if the use case is read-only.

Do not arbitrarily share an open `Folder` across multiple threads. If high throughput is needed, clearly design worker ownership, connection lifecycle, or provider-supported pooling.

## 12. When Do You Need IMAP Instead of POP3?

IMAP is suitable for use cases such as:

- Reading Inbox and other folders.
- Finding unread messages or messages with specific flags.
- Synchronizing mailboxes across multiple devices/workers.
- Storing UID checkpoints.
- Moving emails to a processed folder if the provider supports it.
- Tracking message status on the server.

POP3 is more suitable for simple scenarios that only need to download messages from a mailbox, with a more limited folder and flag model.

| Characteristic | IMAP | POP3 |
| --- | --- | --- |
| Multiple folders | Yes | Usually no |
| Server-side search/flags | Better | Limited |
| Partial message retrieval | Server/provider dependent | More limited |
| State synchronization | Has UID/flags | UIDL depending on server |
| Push-like notifications | IMAP IDLE if supported | Not the same mechanism |
| Long-running inbox processing workflows | Usually suitable | Suitable for simple downloads |

Do not choose POP3 if the business logic requires folders, flags, and complex mailbox synchronization. However, you are also not required to use IMAP if the provider already offers a standardized inbound mail API or webhook.

## 13. Message Number Is Not a Durable Identifier

In IMAP, a message in a folder has a **message sequence number** and may have a **UID**. You must distinguish:

- `message.getMessageNumber()`: the sequence/order within the currently open folder.
- `UIDFolder.getUID(message)`: the UID of the message in a supporting folder.
- `UIDFolder.getUIDValidity()`: the UID generation of the folder; when it changes, old UID checkpoints no longer have the same meaning.

Message numbers can change when other messages are deleted/expunged. Therefore, using "message number 42" as a long-term idempotency key is unreliable.

Example of retrieving UID when the folder supports it:

~~~java
if (inbox instanceof UIDFolder uidFolder) {
    long uidValidity = uidFolder.getUIDValidity();

    for (Message message : messages) {
        long uid = uidFolder.getUID(message);

        log.debug(
            "IMAP message reference: uidValidity={}, uid={}",
            uidValidity,
            uid
        );
    }
}
~~~

Import `jakarta.mail.UIDFolder`. In production, use a key consisting of mailbox identity, folder identity, UIDVALIDITY, and UID to prevent duplicate processing within the folder scope.

## 14. UID, UIDVALIDITY, and Idempotency

A table recording processed messages can have the following PostgreSQL schema:

~~~sql
CREATE TABLE processed_incoming_mail (
    mailbox_id       VARCHAR(120) NOT NULL,
    folder_name      VARCHAR(255) NOT NULL,
    uid_validity     BIGINT NOT NULL,
    uid              BIGINT NOT NULL,
    processing_state VARCHAR(30) NOT NULL,
    processed_at     TIMESTAMPTZ,
    PRIMARY KEY (
        mailbox_id,
        folder_name,
        uid_validity,
        uid
    )
);
~~~

When a worker reads a UID:

1. Check the processed table.
2. If absent, **claim atomically** and mark as in-progress.
3. Parse content within safe limits.
4. Persist the business result durably.
5. Mark as PROCESSED.
6. Only then modify the folder/flag if the workflow requires it.
7. If a crash occurs, the job can be reclaimed and processed idempotently.

Do not simply mark `SEEN` and treat that as "successfully processed": a worker could mark a message as read before saving to the database and crash, causing the email not to be scanned again.

**A message moved to another folder may receive a different UID.** If you want to prevent duplicate processing across the entire mailbox, you need additional correlation logic based on a business key or reliable metadata, not just the UID of a single folder.

## 15. Does Message-ID Replace UID?

The `Message-ID` header is included in RFC 5322 messages and is useful for correlation, but:

- Some emails lack a Message-ID.
- Some clients generate malformed or non-unique Message-IDs.
- Message-ID may be preserved when an email is moved or copied.
- Senders can spoof Message-ID.
- A mailbox can contain multiple copies with the same Message-ID.

Therefore, do not use Message-ID alone as the key guaranteeing uniqueness of each message in a mailbox. Use UID + UIDVALIDITY within the mailbox/folder scope, and add a business idempotency key if the inbound message triggers a business event.

For POP3, `UIDL` (if supported by the server) has different semantics from IMAP UID; do not reuse a single schema without storing the appropriate protocol source and mailbox/folder.

## 16. Finding Unread Emails with IMAP

Some use cases need to read emails not yet marked SEEN. Jakarta Mail supports `SearchTerm`, for example:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;
import jakarta.mail.search.FlagTerm;

Message[] unread = inbox.search(
    new FlagTerm(
        new Flags(Flags.Flag.SEEN),
        false
    )
);
~~~

This snippet assumes `inbox` is an open `Folder`. `false` requests messages that do not have the SEEN flag.

However, **UNSEEN does not mean UNPROCESSED** in a business processing system:

- A user may open the email using another client.
- Another worker may read it first.
- The server or client may update flags.
- A worker may have processed the email already without setting SEEN yet.
- The message may be moved or expunged.

For workflows requiring reliability, use a durable processing ledger keyed by UID, while flags serve only as a secondary signal or UX operation on the mailbox.

### Avoiding Unbounded Scans

`folder.search(...)` can return many messages. In production, paging/checkpointing or an appropriate volume limit is required. Do not default to loading the entire inbox into memory and filtering in Java if the mailbox has hundreds of thousands of emails.

## 17. Reading MIME Bodies Requires Multipart Handling

The receiving side may encounter:

~~~text
MimeMessage
    |
    +--> text/plain
    |
    +--> text/html
    |
    +--> multipart/alternative
    |       +--> text/plain
    |       +--> text/html
    |
    +--> multipart/mixed
            +--> multipart/alternative
            +--> attachment: invoice.pdf
            +--> multipart/related
                    +--> inline image
~~~

`Message.getContent()` does not always return a String. With multipart messages, the result may be a `Multipart`. Do not write:

~~~java
String body = (String) message.getContent();
~~~

without knowing the MIME type. Casting like that can throw a `ClassCastException`.

When reading received emails, traverse the parts and distinguish:

- `text/plain` body.
- `text/html` body.
- Attachment.
- Inline resource.
- Nested multipart.
- Embedded `message/rfc822`.
- Content-Disposition, filename, and Content-ID.

Not every message has a plain-text alternative; some only have HTML or have unusual structures. The parser must handle errors and enforce resource limits.

## 18. Example of Finding the Text Part in MIME

Helper example for simple messages, intentionally skipping attachments:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static String findTextPart(
        Part part,
        String wantedMimeType) throws Exception {

    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        return null;
    }

    if (part.isMimeType(wantedMimeType)) {
        Object content = part.getContent();
        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            String nested = findTextPart(
                multipart.getBodyPart(i),
                wantedMimeType
            );

            if (nested != null) {
                return nested;
            }
        }
    }

    return null;
}
~~~

Usage:

~~~java
String plain = findTextPart(message, "text/plain");
String html = findTextPart(message, "text/html");
~~~

The helper returns the first matching text part. It is not a safe production parser for all MIME trees: you need limits on nesting depth, number of parts, decoded body bytes, charset handling, and embedded message processing. When a mailbox receives untrusted email from the Internet, you must protect against MIME bombs, excessively deep nested parts, and oversized attachments.

**Do not render raw received HTML email directly in a web application** without sanitizing or sandboxing it. HTML can contain harmful content or tracking resources.

## 19. Reading Received Attachments Differs from Adding Attachments When Sending

When sending, we add an attachment:

~~~java
helper.addAttachment(
    "invoice.pdf",
    new FileSystemResource(pdfFile)
);
~~~

When reading, we must traverse `Part` and extract information:

~~~java
if (Part.ATTACHMENT.equalsIgnoreCase(
        part.getDisposition())) {

    String fileName = part.getFileName();

    try (InputStream input = part.getInputStream()) {
        // Stream to a bounded, quarantined destination.
    }
}
~~~

Use `Part.getInputStream()` to read decoded bytes according to the appropriate transfer encoding, while enforcing limits on size, number of parts, and content types; do not simply call `readAllBytes()` on arbitrary emails from the Internet.

Before storing or allowing attachment downloads:

1. Limit the number of files and total bytes.
2. Check the declared Content-Type, but do not trust it blindly.
3. Sanitize filenames and block path traversal.
4. Store outside the web root or in object storage with appropriate permissions.
5. Scan for malware according to policy.
6. Classify dangerous file types (scripts/executables/archives).
7. Do not automatically open or execute files.
8. Only issue download URLs with access control and appropriate expiration.

An attachment with `filename="../../something"` must never be used as-is as a destination path. Senders have full control over MIME headers, so they are untrusted data.

## 20. Received Emails Are Untrusted Data

Do not assume that just because an email appears in a mailbox, its content comes from a legitimate user. Attackers can spoof From/display names, send malicious HTML, malware attachments, phishing links, or deeply nested MIME structures that exhaust parser resources.

Layers of checks typically needed:

- Authentication/authorization of the workflow using the email.
- Allowlists of permitted senders/domains when appropriate.
- SPF/DKIM/DMARC verdicts from the provider when needed and from a trusted source.
- Verification of tokens or correlation IDs tied to the workflow.
- Size limits, MIME limits, and anti-malware scanning.
- HTML sanitization or text-only rendering.
- Rate limiting per mailbox/source.
- Idempotent processing to prevent replay.
- Audit logging and retention policies.

**The From header is not proof of identity authentication.** If a reply requests changing account information, do not perform sensitive operations based solely on a matching From address.

## 21. Can JavaMailSender Read Emails from the Sent Folder?

Not directly. **Sending via SMTP does not guarantee a copy of the email appears in the sending mailbox's Sent folder.**

Depending on the provider and sending method:

- A webmail client may save a Sent copy when the client itself sends.
- An SMTP provider may automatically save Sent copies according to policy.
- A custom SMTP client application may only submit over SMTP without appending to Sent.
- A provider may use a virtual mailbox or API without providing a corresponding Sent folder.

If the product needs to store sent copies, you must design it explicitly:

1. Store `notificationId`, a rendered content snapshot, and the submission result in the database/storage.
2. Or, if the mailbox provider permits, connect over IMAP and append a `MimeMessage` to the appropriate Sent folder.
3. Understand that folder names vary by provider: `Sent`, `Sent Items`, or localized/special-use names.
4. Avoid creating duplicate Sent copies if the provider already saves them automatically on SMTP submission.
5. Do not treat the existence of a Sent copy as proof that the recipient received the email.

### Example of IMAP Append to a Folder

~~~java
Folder sent = store.getFolder("Sent");
sent.open(Folder.READ_WRITE);

try {
    sent.appendMessages(
        new Message[] { mimeMessage }
    );
} finally {
    sent.close(false);
}
~~~

This example only illustrates the `appendMessages` API; `store` must be a connected IMAP Store and `mimeMessage` must contain valid content. Some providers have special Sent storage mechanisms, folder names, and policies. In production, do not hard-code the `Sent` folder without identifying the mailbox properly.

## 22. Can JavaMailSender Check Whether the Recipient Read the Email?

No. `JavaMailSender` only sends. An email accepted by an SMTP relay may pass through multiple mail servers, then land in Inbox/Spam or bounce.

You cannot arbitrarily access a recipient's Inbox just because the application knows their email address. Reading a mailbox requires valid access permissions and credentials/authorization granted by the mailbox owner or provider.

Even when you have permission to read a mailbox:

- Being able to read a message proves that mailbox contains a copy of the email.
- The `SEEN` flag does not prove a human actually read it carefully.
- Absence of the `SEEN` flag does not prove the email was not opened by some client.
- Email tracking pixels/click events also have inaccuracies due to proxies, bots, and security scanners.
- Delivery/bounces should be tracked using ESP/provider events when available.

Do not use IMAP polling on a test mailbox as proof that all real users receive emails identically.

## 23. Can One Account Be Shared for Both SMTP and IMAP?

Possibly, if the provider and account policy allow it, but that is a **provider decision**, not a guarantee of Spring Mail.

For example:

~~~text
SMTP submit endpoint:
  host = smtp.example.com
  port = 587
  account = service@example.com

IMAP mailbox endpoint:
  host = imap.example.com
  port = 993
  account = service@example.com
~~~

Even with the same username, the two protocols may:

- Use different credentials.
- Have different access permissions.
- Use separate OAuth scopes/audiences.
- Be disabled independently by tenant policy.
- Have different authentication mechanisms.
- Have different quotas/concurrent connection limits.

Do not copy all `spring.mail.properties.mail.smtp.*` settings to IMAP and expect them to work. You must use `mail.imaps.*` for the `imaps` protocol or properties appropriate for the provider.

## 24. Securing IMAP/POP3 Connections

For reading production mailboxes, prefer TLS and server identity verification.

IMAPS example:

~~~java
Properties props = new Properties();
props.put("mail.imaps.connectiontimeout", "5000");
props.put("mail.imaps.timeout", "10000");
props.put("mail.imaps.ssl.checkserveridentity", "true");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
~~~

IMAPS typically establishes TLS immediately from the start on port 993. If using IMAP + STARTTLS on port 143 as specified by the provider, you must configure `mail.imap.starttls.enable`, `mail.imap.starttls.required`, and corresponding trust/hostname validation.

Do not use trust-all settings or disable hostname verification to "fix" certificate errors in production. Fix the hostname, CA/trust store, certificate chain, and TLS mode properly.

For POP3S, the provider/session prefix is typically `mail.pop3s.*`. Do not take IMAP properties and reuse them unchanged for POP3S.

## 25. OAuth and Mailbox Access Permissions

Some providers restrict or disable basic password authentication for IMAP/POP3; users may need to use OAuth2/XOAUTH2 or a provider API.

Permissions should be separated:

- **SMTP send** permission.
- **IMAP read** mailbox permission.
- Permission to read a specific mailbox or an entire tenant.
- Permission to write flags/move/delete.
- Permission to manage settings or subscriptions.

An access token with SMTP permission is not guaranteed to be accepted for IMAP. OAuth access tokens typically have an audience, scopes, and expiry; the reader must request a token intended for the right endpoint and permission type.

In some Jakarta Mail providers, the `XOAUTH2` mechanism can be used for IMAP when supported by the server/client, though configuration and grants depend on the provider. Do not pass a refresh token directly into `Store.connect(...)` as a password. The token provider must obtain a valid access token and refresh it according to policy.

If the application only needs to receive incoming email events via a provider's webhook API, granting full-mailbox IMAP permissions may be unnecessary.

## 26. IMAP Polling and IMAP IDLE

There are two ways to detect new messages:

### Polling

The application periodically connects or reuses an existing session to find new messages.

~~~text
Every N seconds:
   Connect
   Open INBOX
   Find new UID range
   Claim unprocessed messages
   Process
   Save checkpoint
   Close
~~~

Pros: easy to reason about, easy to retry and monitor. Cons: can consume connections, increase latency, and requires checkpoint management.

### IMAP IDLE

Some IMAP servers support the IDLE extension, allowing clients to receive mailbox change notifications while keeping a connection open. It can reduce latency and unnecessary polling, but:

- The server/provider must support it.
- Connections can drop, requiring reconnect/backoff.
- Notifications do not replace durable reconciliation.
- You still must check UIDs and deduplicate.
- You should not spawn unbounded threads/connections per tenant when the provider has connection limits.
- You must check how the client library supports it.

In Jakarta Mail/Angus Mail, some IMAP IDLE functionality may live on a provider-specific IMAP folder implementation. Do not assume `JavaMailSender` provides `idle()`.

## 27. Spring Integration Mail When an Inbound Pipeline Is Needed

If you only need to read a few messages, Jakarta Mail `Store`/`Folder` may be enough. However, for applications with continuous inbound streams, converting emails into messages for processing steps, and needing pollers/adapters, consider **Spring Integration Mail**.

Common concepts:

- `ImapMailReceiver`: receives messages via IMAP.
- `Pop3MailReceiver`: receives messages via POP3.
- `ImapIdleChannelAdapter`: an adapter based on IMAP IDLE when supported by the server.
- Inbound channel adapters and message channels: turn received emails into messages for a processing pipeline.
- Filters, transformers, service activators: steps for processing content and routing.

Diagram:

~~~text
Mailbox provider
       |
       v
Spring Integration Mail inbound adapter
       |
       v
Message channel
       |
       v
Parser / validator / dedup
       |
       v
Business command or inbox event
       |
       v
Durable storage / downstream processing
~~~

**Spring Integration Mail is an additional module/feature**, not a `receive()` method added to `JavaMailSender`. It requires separate dependencies and configuration compatible with your Spring version.

Spring Integration helps organize the messaging flow, but does not automatically solve all concerns: credential security, UID checkpoints, idempotency, mailbox permissions, attachment sanitization, and business transaction semantics still must be designed.

## 28. Architecture When an Application Both Sends and Receives Email

A service can support both outgoing notifications and incoming customer replies, but ports should be separated:

~~~java
public interface OutboundMailPort {
    void send(OutgoingMail mail);
}
~~~

~~~java
public interface InboundMailboxPort {
    List<IncomingMailSummary> poll(
        String mailboxId,
        int limit
    );
}
~~~

The application is organized as:

~~~text
                 Business application
                         |
          +--------------+--------------+
          |                             |
          v                             v
    OutboundMailPort               InboundMailboxPort
          |                             |
          v                             v
   SmtpMailAdapter               ImapMailboxAdapter
          |                             |
          v                             v
    JavaMailSender                  Session + Store
          |                             |
          v                             v
      SMTP server                   Mailbox server
~~~

This avoids a monolithic `MailService` that mixes template/sending logic directly with managing mailbox flags, UID checkpoints, attachment scanning, and inbound routing.

### Separating Outgoing and Incoming DTOs

`OutgoingMail` may include recipient, template, subject, body, and attachment references. `IncomingMail` may include mailbox source, UID, normalized headers, received timestamp, parsed parts, and processing status. Do not share the same DTO to avoid accidentally trusting an external caller's `From` data as a privileged system recipient.

## 29. When Handling Reply Emails: Reply-To and Reply Matching

A mail-sending system that supports replies may set `Reply-To`:

~~~java
helper.setFrom("notifications@example.com");
helper.setReplyTo("support@example.com");
~~~

When a user clicks Reply, the email client typically directs the reply to the `Reply-To` address. However, setting `Reply-To` **does not make the application automatically receive replies**. You still need a configured inbound mailbox, provider inbound routing, or webhook.

To correlate a reply to a notification/ticket, you can use:

- A reply address with a securely managed dedicated routing token.
- `In-Reply-To` and `References` headers when present.
- A ticket/notification ID in a custom header or metadata.
- An explicit business token/verification code.
- Subject as a secondary signal, not an authentication key.

`In-Reply-To`/`References` are useful, but may be missing or altered; subjects can change depending on the email client. Do not perform sensitive actions based solely on a thread header.

If a user sends a reply through an external mailbox, the application needs permission to read that mailbox or a provider inbound gateway that forwards messages to the system.

## 30. Does Receiving Bounces and DSNs Always Require Reading an Inbox?

Not necessarily. Bounces/Delivery Status Notifications (DSNs) can be sent to the envelope return-path mailbox, or an Email Service Provider may offer an event API/webhook.

Options:

| Source | Information Available | Notes |
| --- | --- | --- |
| SMTP relay logs | Submission, queue/defer/reject | Requires server/provider access |
| ESP webhook | Delivered, bounced, deferred, complaint | Provider-specific, requires signature verification |
| Return-path mailbox | DSN/bounce messages | Requires DSN parser and inbound reader |
| Recipient reply | Reply content | Not equivalent to a standard delivery event |
| Sent folder | Copy of sent mail | Does not prove delivery |

If the provider offers a well-structured webhook, processing delivery events via webhooks can be simpler than parsing diverse DSN formats in a mailbox. If the system operates its own SMTP servers, reading a bounce mailbox may be part of operations.

A DSN is also an untrusted email from the parser's perspective: you must correlate, deduplicate, avoid running dangerous actions, and not draw false conclusions from From/subject.

## 31. Sender and Receiver Need Separate State Machines

Outgoing notification:

~~~text
PENDING
   |
   v
SUBMITTING
   |
   +--> SUBMITTED
   +--> RETRY_WAIT
   +--> FAILED
   +--> AMBIGUOUS
~~~

Incoming message:

~~~text
DISCOVERED
   |
   v
CLAIMED
   |
   +--> PARSED
   |      |
   |      v
   |   PROCESSED
   |
   +--> RETRY_WAIT
   +--> REJECTED
   +--> QUARANTINED
~~~

The two state machines have different semantics:

- Outgoing retries carry the risk of duplicate sending if the SMTP outcome is ambiguous.
- Incoming retries carry the risk of processing the same email multiple times if a worker crashes after committing a side effect.
- Outgoing needs provider rate limits and deadlines.
- Incoming needs UID checkpoints, mailbox reconciliation, and safe parsing.
- Outgoing status `SUBMITTED` is not equivalent to incoming status `PROCESSED`.

If an application handles both directions, use separate repositories/metrics or sufficiently distinct models to avoid recording a single `sent` column for every kind of mail.

## 32. A Reliability-Safe Incoming Worker

A practical flow:

~~~text
IMAP poller
   |
   v
Read mailbox UID/UIDVALIDITY
   |
   v
Check durable dedup ledger
   |
   v
Claim unprocessed UID
   |
   v
Load bounded MIME content
   |
   v
Validate sender/routing/token
   |
   v
Store sanitized artifacts
   |
   v
Apply business action idempotently
   |
   v
Mark PROCESSED in DB
   |
   v
Optional mark SEEN / move to processed folder
~~~

If the process crashes **after the business commit but before marking PROCESSED**, the email may be processed again. Therefore, the business handler needs an idempotency key rather than relying solely on the mailbox checkpoint.

If you mark `SEEN` before persisting state, there is a risk of missing messages. If you move the message before completing processing, the UID may change and complicate recovery.

Do not hold a mailbox connection open across an entire long-running database transaction, do not download huge attachments inside a transaction, and do not execute business actions directly from unauthenticated emails.

## 33. Connecting to Multiple Mailboxes or Multi-Tenant Setups

When an application serves multiple mailboxes, distinguish:

- The SMTP account used for sending.
- The IMAP account used for reading.
- Permissions per tenant/mailbox.
- Credential expiration/rotation.
- Concurrency/connection quotas per provider.
- UID checkpoint namespaces per mailbox.
- Storage isolation for content/attachments.
- Retention and privacy policies.

Do not share mutable `Store`/`Folder` instances across tenants A and B without proper control. Do not take arbitrary host/port/mailbox credentials from an HTTP request and connect immediately; you must prevent SSRF, restrict endpoints, and use secret storage.

With many mailboxes, a poller may need capacity scheduling and per-provider circuit breakers so that one tenant's failures do not stall all other users.

## 34. Performance When Reading Large Mailboxes

A mailbox with hundreds of thousands of messages is not suited for calling `getMessages(1, total)` every minute and downloading all content.

Limits typically needed:

- **Batch size:** number of UIDs/messages processed per pass.
- **Paging/checkpointing:** fetch only the unprocessed range.
- **Prefetch headers:** fetch metadata first, avoid downloading bodies prematurely.
- **Body size budget:** reject/quarantine oversized messages.
- **Attachment count/bytes budget:** prevent excessive RAM/disk consumption.
- **Concurrency:** cap the number of IMAP connections.
- **Timeout/reconnect:** do not block forever when the server disconnects.
- **Backpressure:** if downstream processing slows down, throttle reading speed.
- **Retention:** clean up processed artifacts according to policy.
- **Server search/UID APIs:** leverage them appropriately when supported by the provider.

Jakarta Mail APIs such as `FetchProfile` can help request needed fields upfront, depending on the provider implementation:

~~~java
FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);

inbox.fetch(messages, profile);
~~~

This snippet requires importing `jakarta.mail.FetchProfile`, `Message`, and an open folder. It does not guarantee every server executes it with identical efficiency across all providers.

## 35. Common Errors When Reading IMAP/POP3

| Symptom | Likely Cause | Investigation Direction |
| --- | --- | --- |
| Connecting to SMTP host with IMAP | Wrong protocol/endpoint | Use separate IMAP host and port |
| `AuthenticationFailedException` | Credentials, OAuth scope, or policy | Check mailbox permissions, not just SMTP |
| TLS handshake failure | Wrong port mode/certificate | Verify host, trust store, TLS mode |
| `FolderNotFoundException` | Different or nonexistent folder name | List folders, check namespace/special-use |
| `FolderClosedException` | Server closed folder/connection | Reconnect and resume by UID |
| `MessageRemovedException` | Message deleted/expunged while reading | Reconcile UID/checkpoint |
| Unread query returns empty | Flags changed or wrong mailbox | Do not rely solely on UNSEEN |
| Same email processed twice | Missing durable deduplication | UIDVALIDITY + UID and business idempotency |
| Casting body to String fails | Multipart message | Traverse the MIME tree |
| Attachments exhaust RAM | Unbounded stream/size | Bounded streaming + quarantine |
| No Sent copy after SMTP | Provider does not auto-save | Design explicit Sent/archive policy |
| Sender succeeds, reader misses Inbox | Different mailboxes or downstream delay | Distinguish submit/delivery and check provider |
| Slow mailbox polling | Full mailbox scan/connection churn | UID checkpoints, batching/prefetch |

For each error, read the nested exceptions and protocol phase. Do not assume an IMAP failure means `JavaMailSender` is broken when the sender is still submitting via SMTP normally.

## 36. Testing Both Sending and Reading with GreenMail

A simple SMTP integration test can use a GreenMail capture server and call `getReceivedMessages()`. However, that only reads the test server's capture API; it does **not** open an IMAP mailbox.

If you want to genuinely test both protocols, run GreenMail SMTP and IMAP:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.Properties;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

ServerSetup smtpSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
);

ServerSetup imapSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_IMAP
);

GreenMail greenMail = new GreenMail(
    new ServerSetup[] { smtpSetup, imapSetup }
);

greenMail.start();

try {
    greenMail.setUser(
        "reader@example.test",
        "reader",
        "test-secret"
    );

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(greenMail.getSmtp().getPort());

    SimpleMailMessage outgoing = new SimpleMailMessage();
    outgoing.setFrom("sender@example.test");
    outgoing.setTo("reader@example.test");
    outgoing.setSubject("SMTP and IMAP");
    outgoing.setText("Two-way test content.");

    sender.send(outgoing);

    // Confirm test SMTP has captured the submitted message.
    boolean received = greenMail.waitForIncomingEmail(5000, 1);
    if (!received) {
        throw new AssertionError("No message reached test SMTP");
    }

    Session session = Session.getInstance(new Properties());
    Store store = session.getStore("imap");

    try {
        store.connect(
            "127.0.0.1",
            greenMail.getImap().getPort(),
            "reader",
            "test-secret"
        );

        Folder inbox = store.getFolder("INBOX");
        inbox.open(Folder.READ_ONLY);

        try {
            Message[] messages = inbox.getMessages();
            if (messages.length != 1) {
                throw new AssertionError("Unexpected message count");
            }

            if (!"SMTP and IMAP".equals(
                    messages[0].getSubject())) {
                throw new AssertionError("Wrong subject");
            }
        } finally {
            inbox.close(false);
        }
    } finally {
        store.close();
    }
} finally {
    greenMail.stop();
}
~~~

The example requires a GreenMail dependency compatible with Jakarta Mail/Angus Mail and corresponding imports. Because the test server runs on loopback, the example uses the non-TLS `imap` protocol for the local test environment. **Do not copy this plaintext configuration to production.**

The test result proves:

1. `JavaMailSender` submits the message via the SMTP test server.
2. The test mailbox stored the message.
3. Jakarta Mail `Store` connects over IMAP and reads the subject.

It does not prove that an email sent through a production SMTP provider will reach every recipient's Inbox.

## 37. Configuring @SpringBootTest When Both Sending and Reading

For Spring Boot integration tests:

- Start the SMTP/IMAP test server before the Spring context resolves properties.
- Override `spring.mail.host/port` for `JavaMailSender`.
- Override `app.mail.incoming.host/port` for the inbox reader.
- Use test credentials, never production secrets.
- Invoke the application's mail-sending use case.
- Wait for the test server to receive the message with a deadline.
- Invoke the reader bean that uses Jakarta Mail `Store`.
- Assert metadata/body or UID as required.
- Clean up the mailbox/test server and application state after the test.

`@DynamicPropertySource` can supply dynamic ports into the context in a way appropriate for your Spring Test version.

Distinguish three types of assertions:

| Assertion | Evidence |
| --- | --- |
| Mock sender was invoked | The application attempted to send |
| GreenMail `getReceivedMessages()` has mail | The SMTP test server captured the message |
| IMAP `Store` reads the message | The test mailbox can be accessed via IMAP |

If a project only tests `JavaMailSender`, starting IMAP is usually unnecessary. Only extend to IMAP when the test needs to cover actual receiving/reading behavior.

## 38. Testing Data and Edge Cases for Inbound Mail

A test suite for a reader should cover:

1. Empty Inbox.
2. A plain-text message.
3. HTML-only and `multipart/alternative`.
4. Vietnamese subjects and other charsets.
5. Message without `From`/`Message-ID`.
6. Multiple `From`/`To` recipients.
7. Attachment exceeding the size limit.
8. Filename containing path traversal.
9. Excessively deep nested multipart.
10. Duplicate message with the same `Message-ID`.
11. Same UID polled twice.
12. `UIDVALIDITY` change.
13. Message expunged while reading.
14. IMAP connection closed mid-batch.
15. Unread flag changed by another client.
16. Crash after business processing before marking processed.
17. Expired OAuth token or revoked IMAP permission.
18. Multi-tenant account isolation.
19. Backpressure when downstream is slow.
20. Never logging raw bodies or secrets.

For integration tests, you can use GreenMail or a suitable mock server. Specific protocol errors such as mid-stream disconnects or `UIDVALIDITY` resets may require stubs/proxies or dedicated test fixtures.

## 39. Guidelines for Choosing an Approach in Real Applications

Choose a design based on your goal:

| Need | Suitable Solution | Notes |
| --- | --- | --- |
| Only send transactional mail | `JavaMailSender` + SMTP provider | Outbox/retry if critical |
| Send HTML/attachments | `JavaMailSender` + `MimeMessageHelper` | Size limits and repeatable resources |
| Read a few emails in one mailbox | Jakarta Mail `Store`/`Folder` | Resource lifecycle, UID, and TLS |
| Continuously synchronize an Inbox | IMAP worker or Spring Integration Mail | UID checkpoint, reconnect, dedup |
| Only download mail from a simple mailbox | POP3 if supported by provider | Limited folders/flags |
| Receive customer replies | Inbound mailbox or provider inbound webhook | Routing, validation, security |
| Receive bounces/delivery status | Provider events/DSN | Submission differs from delivery |
| View Sent folder | IMAP `Store` + corresponding folder | SMTP does not guarantee a Sent copy |
| Large multi-mailbox system | Dedicated inbound service/workers | Isolation, quota, and backpressure |
| Test sent SMTP mail | GreenMail/Mailpit SMTP capture | No IMAP needed if only testing sender |
| Test both sending and reading | GreenMail SMTP + IMAP | Tests both real protocols |

There is no need to add IMAP if the system only sends. Granting mailbox read permissions merely to verify that the sender "sent successfully" often introduces sensitive access privileges and does not prove delivery to other mailboxes.

## 40. Common Anti-Patterns

| Anti-Pattern | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Calling `JavaMailSender.receive()` | The API has no mail-reading contract | Use `Store`/`Folder` or an inbound adapter |
| Using SMTP host/port 587 to open Inbox | Wrong protocol | Use IMAP/POP3 endpoint |
| Using `spring.mail.*` expecting Spring to poll Inbox | Auto-config is mainly for outbound | Configure inbound separately |
| Treating `MimeMessage` as a mailbox connection | It is a MIME representation object | Distinguish `Message` and `Store` |
| Treating `send()` success as delivered | Relay only confirms submission | Track provider events |
| Treating a copy in Sent as recipient receipt | Sent is a sender-side copy | Distinguish sent copy and delivery |
| Reading others' Inboxes without permission | Security/privacy issue | Only access authorized mailboxes |
| Using `Message-ID` as sole dedup key | Can be duplicated/missing/spoofed | `UIDVALIDITY` + UID + business key |
| Using IMAP message number as checkpoint | Sequence changes on expunge | Use UID |
| Processing only `UNSEEN` | Flag is not a processing status | Durable ledger |
| Marking `SEEN` before saving business result | Can drop messages after crash | Persist before ack/flag |
| Casting every body to `String` | Multipart causes errors | Parse the MIME tree |
| Loading all attachments into RAM | Can cause OOM | Bounded streaming |
| Blindly trusting `From`/filename/HTML | Untrusted external data | Validate and sanitize |
| Sharing one `Store`/`Folder` across all tenants | Isolation/concurrency risks | Scope per account |
| Enabling plaintext IMAP in production | Exposes credentials/content | TLS and hostname validation |
| Failing to close `Store`/`Folder` | Socket/connection leaks | Lifecycle/`finally` |
| Using SMTP test capture as IMAP proof | Two different APIs | Test `Store`/`Folder` separately |
| Treating IMAP IDLE as a durable queue | Connections can drop | Reconcile UIDs and checkpoints |

## 41. An Architecture-Oriented Implementation Checklist

Before building the system, answer:

- Does the application only need to send, or also to read/receive?
- Has the mailbox owner granted valid read permissions?
- Does the provider offer IMAP/POP3, an inbound API, or webhooks?
- If using IMAP, are folders, flags, UIDs, and IDLE needed?
- Is the mailbox large? What are the batch size and checkpoint?
- Will external attachments or HTML be processed?
- Are size/nesting limits and malware scanning in place?
- What business operation does an incoming message trigger, and what is the idempotency key?
- How are `Store`/`Folder` lifecycles, reconnects, retries, and timeouts managed?
- Are there multiple tenants/mailboxes with different secrets and quotas?
- Is outgoing submission state separated from incoming processing state?
- Is there monitoring for poll lag, UID checkpoints, and parse failures?
- Do tests use a local SMTP/IMAP server instead of production mailboxes?

If the need is simply sending order confirmations, keep the architecture simple with `JavaMailSender` and an outbox if required. If you need to handle replies, bounces, or inbound tickets, add a receiving path with clear boundaries and access permissions.

## 42. Key Takeaways

- **`JavaMailSender` is a mail-sending API**, not an Inbox-opening API.
- `MailSender` supports `SimpleMailMessage`; `JavaMailSender` adds MIME support.
- Spring Boot `spring.mail.*` configures the SMTP sender, not an automatic IMAP receiver.
- SMTP is for submission/relay; IMAP/POP3 are for reading mailboxes.
- Jakarta Mail `Session`, `Store`, `Folder`, and `Message` are the core components when reading mail.
- `MimeMessage` represents content; it does not determine the sending or reading protocol on its own.
- Use `imaps`/port 993 or a provider-appropriate TLS mode when reading production mailboxes.
- Always close `Folder` and `Store` to release connections.
- Use UID and `UIDVALIDITY` for IMAP checkpoints, not long-term message sequence numbers.
- `Message-ID` is useful for correlation, but is not an absolute deduplication key.
- `UNSEEN` does not mean "unprocessed"; a durable processing ledger is required.
- Inbound MIME can be multipart, HTML, and attachments; always parse with limits and protect data.
- Received `From` headers, filenames, and bodies are untrusted data.
- SMTP submission success does not prove Inbox delivery or that the recipient read the message.
- Successful SMTP sending does not automatically guarantee a Sent folder copy.
- `Reply-To` only directs reply emails; it does not make the application receive mail by itself.
- Spring Integration Mail can help organize inbound adapters/pollers, but is a separate module.
- GreenMail can test SMTP capture, and when IMAP is enabled, can test real `Store`/`Folder` operations.
- Two-way sending and reading systems should have separate adapters, credentials, states, and metrics.

**Core principle:** In Spring Framework Mail, use **`JavaMailSender` for sending** and use **Jakarta Mail `Store`/`Folder` or a dedicated inbound integration for reading**. Although both directions can operate on `MimeMessage`, they differ in protocols, permissions, durability, and error handling. Separating them cleanly from the start prevents confusing "sent" with "received", keeps mailbox management secure, and produces inbound/outbound workflows that can be tested, operated, and scaled independently.
