# Distinguishing Sending Mail from Reading, Synchronizing, and Managing Mailboxes

In a Spring application, an "email integration" requirement might simply be sending order notifications, or it might involve reading incoming customer emails, keeping mailbox data consistent with the server, or moving messages between folders. These four needs use different operations and protocols. Understanding the boundaries right from the start helps you choose the right components and avoid designing a mail-sending system as if it were also an inbox-management system.

At an introductory level, distinguish them by the **action the application wants to perform**:

- **Sending:** the application constructs a message and asks a server to deliver it to recipients.
- **Reading:** the application retrieves messages already sitting in a mailbox to inspect metadata, content, or attachments.
- **Synchronization:** the application tracks changes over time to keep a local copy of data aligned with the mailbox on the server.
- **Mailbox management:** the application changes the state or structure of a mailbox, such as marking as read, flagging, moving messages, or deleting messages.

Core point: **Spring Framework Mail focuses on sending emails.** Reading, synchronizing, and managing mailboxes require other APIs or components, typically based on IMAP, POP3, or an email service provider's dedicated API.

## 1. The Big Picture: Emails Are Sent and Read at Opposite Ends

An email is not "pushed directly" from a Java method into the message list of the recipient's application. In the common model, the application hands the message off to a sending server; email infrastructure transports it; and later the recipient retrieves the message from their mailbox.

~~~text
Sender's Spring application
        |
        | Create content + send via SMTP (submission)
        v
Mail-sending server / email service
        |
        | Routing and delivery
        v
Mail-receiving server + mailbox storage
        |
        +---- IMAP / POP3 / provider API --------> Mail-reading application
        |
        +---- IMAP / provider API ---------------> Application that syncs,
                                                   flags, moves, deletes mail
~~~

The diagram depicts logical roles. A provider may run several roles together on the same system, and an application may both send and read, yet **each direction of interaction remains a distinct problem**.

| Use case | Key question | Common protocol/API | States to care about | Real-world example |
| --- | --- | --- | --- | --- |
| Sending mail | How do we get a message out? | SMTP submission or HTTP mail-sending API | Send request, acceptance result, errors, send history | Sending OTPs, invoices, notifications |
| Reading mail | Which messages exist now and what is inside? | IMAP, POP3, mail-reading API | Messages existing at read time | Viewing customer support emails |
| Synchronization | What is new, changed, or deleted since last time? | IMAP with change tracking, polling, IDLE, or delta/webhook API | Checkpoint, identifiers, flags, deletion state | Syncing an inbox into a database |
| Mailbox management | How do we update message state or organization? | IMAP or mail-management API | Write permissions, folders/labels, flags, deletion policy | Marking as processed, moving messages |

A **one-time read** operation is not yet **synchronization**. A **successful SMTP send** also does not prove the recipient opened the message.

## 2. Sending Mail: Creating Messages and Handing Them to the Sending Server

### 2.1. What Role Does SMTP Play?

**SMTP (Simple Mail Transfer Protocol)** is the foundational protocol for sending and transferring emails. An application typically connects to a provider's message submission endpoint over authenticated SMTP, such as port 587 with STARTTLS or port 465 with implicit TLS, depending on service configuration.

Minimal workflow:

1. The application creates a message with recipients, subject, and body.
2. The application connects to the SMTP server using appropriate settings and authenticates if required by the service.
3. The SMTP server accepts or rejects the send request.
4. Email infrastructure continues routing and attempting delivery to the receiving server; the message may be delayed, bounced, or filtered.

SMTP also distinguishes the **transport envelope** (envelope sender/recipients used in the protocol session) from **email headers** such as From, To, and Subject. The two data layers usually correspond but are not strictly identical. When diagnosing mail sending, you need to know whether you are looking at an envelope address or a display address inside the message.

**Important limitation:** a send call does not produce an API to list an inbox, re-read messages, mark a message as read, or move a message to a folder. Those are functions on the mailbox-storage side.

### 2.2. How Does Spring Framework Mail Support Sending Mail?

In Spring Framework, the basic concepts include:

- **MailSender:** interface for sending simple plain-text messages via **SimpleMailMessage**.
- **JavaMailSender:** extended interface supporting MIME emails, i.e., HTML content, multipart bodies, attachments, and other required features.
- **JavaMailSenderImpl:** common mail-sending implementation built on the Jakarta Mail library.
- **MimeMessageHelper:** utility that makes building MIME messages more convenient.
- **MailException** and related exception types: represent errors detected by Spring during sending.

Spring Boot can auto-configure a **JavaMailSender** when the application declares the mail starter and provides appropriate properties. This is the typical integration pattern in a Spring Boot application; it still serves only the **sending** direction.

Gradle dependency example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

SMTP configuration example in **application.yml** (addresses are illustrative only):

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Username and credentials can be supplied via environment variables **SPRING_MAIL_USERNAME** and **SPRING_MAIL_PASSWORD** or a secret management system. Do not put real passwords into source code or documentation. Authentication, TLS, and port settings must follow the documentation of the SMTP service in use.

A simple plain-text mail-sending service:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("noreply@example.org");
        message.setTo(recipient);
        message.setSubject("Welcome");
        message.setText("Thank you for registering an account.");

        mailSender.send(message);
    }
}
~~~

**What happens:** the method constructs a message and uses **JavaMailSender** to send it to the configured SMTP server. **What does not happen:** the method does not connect to the recipient's inbox to check whether the message is there or has been read.

When HTML or attachments are needed, the application creates a **MimeMessage** and uses **MimeMessageHelper**. Although the representation is richer, this is still a sending operation.

### 2.3. What Exactly Does "Sent Successfully" Mean?

Different milestones must be distinguished:

| Milestone | What can be concluded | What cannot yet be concluded |
| --- | --- | --- |
| Email object created | Message data has been constructed | That the SMTP server accepted it |
| Send call completes without error | The sending component completed the required exchange per the received response | That the message definitely reached the recipient's inbox |
| Sending service confirms acceptance | The sending system took responsibility for processing under its service contract | That the recipient saw or read the message |
| System reports successful delivery | The service recorded delivery according to its own semantics | That the message was unfiltered or read by the recipient |
| Open/read event received | A tracking signal or receipt occurred | That a human reliably read it in all cases |

A message can be held in a queue, bounced, filtered as spam, or blocked due to sending domain configuration. SPF, DKIM, and DMARC help authenticate domains and email policies; they do not replace mailbox-reading mechanisms. "Opened" signals in email marketing tools are also not absolute proof because clients can block or preload remote content automatically.

Another common pitfall: **sending via SMTP does not automatically create a copy in any account's Sent folder**. Saving to Sent depends on the service, client, or a separate message-saving operation.

## 3. Reading Mail: Retrieving Emails Already in a Mailbox

Reading mail shifts the problem from "pushing a message outward" to "accessing a mail store held by a server". Typically, the application needs access credentials for an account/mailbox and a mechanism to list messages, fetch headers, and fetch bodies.

### 3.1. Three Common Access Approaches

| Access method | Characteristics | Suitable when |
| --- | --- | --- |
| **IMAP** | Works with messages on the server; supports folders and multiple status flags; capable of querying/updating messages | You need to read and maintain a consistent view across multiple clients |
| **POP3** | Focuses on fetching messages from the inbox; status and folder sync capabilities are more limited than IMAP | Simple cases or legacy systems that only need to download messages |
| **Provider API** | HTTP API with the provider's own message, label, event, and permission model | Tight integration with Gmail, Microsoft 365, or platforms with dedicated APIs |

Common ports for IMAP are 143 (upgradeable to TLS) or 993 (TLS from start); POP3 commonly uses 110 or 995. This is general guidance, not a substitute for official server configuration.

**IMAP is not SMTP running in reverse.** SMTP transfers messages between sending and receiving sides; IMAP lets you access and operate on a mailbox.

### 3.2. Reading Mail with Jakarta Mail in a Spring Application

The Jakarta Mail library has the concepts **Session**, **Store**, **Folder**, and **Message**:

- **Session:** configures the working environment for the email protocol.
- **Store:** connects to an account's mail repository.
- **Folder:** a box/folder on the server, such as INBOX.
- **Message:** an individual message accessed through that folder.

A plain Java example using Jakarta Mail, illustrating reading up to the last 10 message subjects over IMAPS:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.Properties;

public class InboxReader {

    public void printRecentSubjects(
            String host, String username, String credential
    ) throws MessagingException {
        Properties properties = new Properties();
        properties.put("mail.store.protocol", "imaps");
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "5000");

        Session session = Session.getInstance(properties);
        Store store = session.getStore("imaps");
        Folder inbox = null;

        try {
            store.connect(host, 993, username, credential);
            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_ONLY);

            int count = inbox.getMessageCount();
            if (count > 0) {
                int first = Math.max(1, count - 9);
                Message[] messages = inbox.getMessages(first, count);

                for (Message message : messages) {
                    System.out.println(message.getSubject());
                }
            }
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

The example intentionally opens in **READ_ONLY** mode and fetches only subjects. It requires a provider that supports IMAPS, appropriate security configuration, and an authentication method accepted by the server. In a real application, do not print sensitive email subjects or bodies to logs; pass the data into an access-controlled processing layer. Some services require OAuth 2.0 or another authentication mechanism instead of an account password.

In the example, **getMessages(first, count)** uses the message sequence numbers in the folder at that moment. These sequence numbers can change when the mailbox changes, so **do not use them as a long-term synchronization checkpoint**.

When reading the message body, **Message.getContent()** may return text, a multipart object, or nested structures. An HTML email can come with a plain-text version, inline images, and attachments. You must handle MIME properly, enforce size limits, respect character encodings, and validate file types; do not assume every email is just a plain string.

### 3.3. Does Reading Once Necessarily Mark a Message as Read?

You cannot answer "yes" for every situation. Read status is normally stored as a mailbox flag, yet the side effect of fetching content also depends on the protocol, folder open mode, and client/provider behavior.

When an application only wants to inspect messages without modifying the mailbox, use a non-mutating read mechanism and define an explicit policy for the **Seen** flag. When the application intends to mark a message as read, treat that as **a separate state-management operation**.

## 4. Mail Synchronization: Maintaining State Over Time

Suppose a customer support system reads the inbox at 09:00 and saves 20 messages to a database. By 09:05, two new messages arrive, one message is moved to another folder, and one message is marked as read. If the application merely re-runs "fetch the last 20 messages" and inserts everything, data will be duplicated and status changes will not be reflected.

**Synchronization** is the process of detecting and applying changes between two systems, typically between a server-side mailbox and the application's data store. It requires **state across multiple runs**, not just a single read command.

### 4.1. Facts That Must Be Tracked

A synchronizer may need to store:

- Account identifier and source folder.
- A stable identifier for each message within the scope guaranteed by the provider.
- The most recent processing checkpoint or API delta token.
- Message state: read/unread, answered, starred, deleted flags; folder or labels.
- Timestamp and processing outcome for safe re-execution after failures.

With **IMAP**, each message can be referenced by **UID**, which is an identifier scoped per folder. When using UIDs as a checkpoint, they must be paired with the folder's **UIDVALIDITY**. If UIDVALIDITY changes, previously stored UIDs can no longer be interpreted in the same scope; the synchronizer must rebuild an appropriate mapping. A UID is not a globally unique identifier across all accounts and folders.

Do not use the **Message-ID** email header as an absolute unique key: that header may be missing or duplicated. Do not use the message sequence number as a long-term key, because sequence numbers can shift after deletions or mailbox updates.

### 4.2. How Do Polling, IMAP IDLE, and Webhooks Differ?

| Mechanism | How it works | Things to note |
| --- | --- | --- |
| **Polling** | Periodically asks the server for new messages and changes | Easy to implement; incurs latency and query cost; requires a checkpoint |
| **IMAP IDLE** | Keeps a connection open to receive a server signal when the mailbox changes | Still must query to determine what changed; must handle disconnects and reconnects |
| **Provider webhook/push** | Provider pushes an event or notification when changes occur | Must verify notifications, deduplicate deliveries, and backfill missed events |
| **Delta/change tracking API** | Queries changes since a previous token/state | Tokens can expire; must have a full re-sync fallback |

**Receiving a new notification does not mean you have received all new data.** IDLE or webhooks are usually signals to "check for changes"; the system still needs to fetch the data and handle dropped connections, duplicate notifications, or out-of-order events.

IMAP has extensions such as CONDSTORE/QRESYNC on some servers to track state changes more efficiently. Do not assume every server supports these extensions; the design must check actual capabilities and provide a fallback.

### 4.3. Minimal Synchronization Flow

~~~text
First run:
  Connect and identify mailbox
    -> read messages to import
    -> write data + source identifiers
    -> save checkpoint after processing succeeds

Subsequent runs:
  Load checkpoint
    -> query changes from server
    -> add new messages / update flags / handle missing or moved messages
    -> write results idempotently
    -> update checkpoint once data is safely persisted

When checkpoint is lost or source identifiers are invalidated:
  Rescan or reconcile according to system rules
~~~

For example, with an IMAP folder, a synchronizer might read UIDVALIDITY, fetch UIDs greater than the last processed UID, retrieve needed content, and persist records plus the checkpoint. However, **scanning only UIDs higher than last time is not enough to detect flag changes or deleted messages**; a corresponding reconciliation or change-query mechanism is required. If a message is moved to another folder, it may appear with a new identifier in the destination folder.

A record might use a logical key such as:

~~~text
(accountId, folderId, uidValidity, uid)
~~~

This illustrates the IMAP case, not a universal key across all providers. A provider API may supply a message ID or thread ID with a different stability scope.

### 4.4. What Must Safe Synchronization Handle?

**Re-runs and dropped connections.** If a message is saved successfully before the checkpoint is updated, the next run may encounter the same message again. Use upserts or unique constraints on the source key and ensure checkpoint updates remain consistent with processed data.

**Concurrent processes.** Two workers could import the same message or update the checkpoint out of order. Locking, partitioning by account/folder, or proper coordination is required.

**Two-way state.** If a user in the application marks a message as "read" and that action is pushed back to the server, the system must decide which side is the source of truth, how to resolve conflicts, and how to react if the server rejects the change.

**Deletions and moves.** Disappearing from the current listing does not necessarily mean a message was permanently deleted: it may have been moved to another folder, hidden by a filter, or lost access permissions. Local retention and deletion policies must be defined clearly.

**Resource limits.** Large mailboxes require batched queries, reasonable pagination, attachment size limits, bounded retries, and monitoring for provider rate limiting.

Because of these factors, a job that "reads the inbox every minute" only becomes true synchronization when it handles **changes, checkpoints, and re-runs**.

## 5. Mailbox Management: Changing State on the Server

Reading and managing may share an IMAP connection, but **their permissions and consequences differ**. Management includes write operations on the mailbox.

Some examples:

| Operation | Effect on the mailbox | Notes |
| --- | --- | --- |
| Mark as read | Sets the Seen flag or equivalent state | Affects how other clients display the message |
| Flag/star | Sets the Flagged state or corresponding label | Providers may use custom labels |
| Mark as answered | Sets the Answered state if the system uses this flag | Does not itself prove a reply email was actually sent |
| Move or copy message | Places the message into another folder/label or copies it | UID in the destination folder may differ |
| Delete message | Marks for deletion, moves to Trash, or deletes directly depending on API and system | May require an expunge/permanent-delete step |
| Create/rename folder | Changes mailbox organization | Not all providers model folders the same way |

With Jakarta Mail, modifying state requires opening **Folder.READ_WRITE** and having appropriate permissions. For example, an API may toggle **Flags.Flag.SEEN**; message deletion operations must be handled very carefully because they can affect multiple clients and message recoverability.

Traditional IMAP uses folders and flags, whereas some major services use a **label** model, allowing one message to appear in multiple "groups" without being separate copies. Do not force every provider into an identical folder model when designing management features.

### Boundary Between Synchronization and Management

The two use cases often sit side by side, yet are not identical:

- When **synchronizing**, the application observes that a message was marked as read elsewhere and updates its database.
- When **managing**, the application proactively marks a message as read on the server based on a user action.
- When doing **two-way synchronization**, the application both observes changes from the server and pushes local changes to the server, so conflict-resolution rules are needed.

For example: an agent clicks "Resolved" in customer support software. If only the ticket's **status** field in the database changes, that is managing the application's business data. If the system also applies a label or moves the email itself into a "Processed" folder on the server, that is **mailbox management**. If the application then reflects that change accurately across all screens and devices, maintaining consistency is **synchronization**.

## 6. Where Does Spring Mail Sit in the Architecture?

A complete application may combine multiple components:

~~~text
                         SPRING APPLICATION
                                |
         +----------------------+----------------------+
         |                      |                      |
   Outbound Mail          Inbound Reader         Mailbox Sync /
   Service                Service                Management Service
         |                      |                      |
  JavaMailSender          Jakarta Mail Store      IMAP / provider API
         |                or provider API        + checkpoint in DB
    SMTP / send API             |                      |
         v                      v                      v
  Sending infra         Server mailbox <--------> Application database
~~~

**Spring Framework Mail** handles the sending side. If receiving mail is needed in the Spring ecosystem, consider **Spring Integration Mail**, with scheduled mail-receiving components or IMAP IDLE, depending on version and server capabilities. Spring Integration provides integration building blocks, while the application still decides persistence, checkpoints, deduplication, access permissions, and management logic.

Alternatively, you can use **Jakarta Mail** directly to access IMAP/POP3 or use a provider's client SDK/API. The choice depends on the specific need:

- Only sending verification codes or notifications: usually just **JavaMailSender** or an HTTP mail-sending service.
- Occasionally fetching email content from an account: needs an **IMAP/POP3/API reader**.
- Receiving many emails and processing continuously: needs a **receiver + synchronization mechanism + persistent state**.
- Building an inbox UI where users mark, categorize, move, or delete messages: needs a **mailbox management API** along with permissions and state synchronization.

Do not create a single generic service named "EmailService" and assume every operation can be invoked through **JavaMailSender**. Class names and boundaries should reflect the role of each communication direction.

## 7. Three Scenarios That Often Cause Confusion

### Scenario A: "I Sent a Confirmation Email, Now I Need to Know If the Customer Read It"

These are two distinct requirements. **Sending** via JavaMailSender only lets the application request message transmission. To verify reading, you need a tracking/receipt solution with its own consent and limitations; many clients do not provide reliable signals. **Reading the application's own inbox** also cannot answer whether the customer opened the message in their mailbox.

A more reliable solution for business confirmation is providing an explicit action such as a **Confirm email** button or a tokenized link. When the user clicks and the server verifies the token, the application knows they completed verification; this is still different from measuring "email read".

### Scenario B: "The System Needs to Read Customer Reply Emails"

This is a use case of **receiving/reading messages from the company's mailbox**, such as support@example.org. JavaMailSender has no operation to list incoming messages. The system needs inbox access via IMAP or a provider API, decodes the required content, and links the message to the appropriate support request.

If only sampling messages manually, a one-off fetch may suffice. If continuous operation is needed, a synchronization mechanism must be added so messages are neither processed twice nor missed.

### Scenario C: "Automatically Move Processed Emails to the Archive Folder"

The system **reads** to identify the message, **manages the mailbox** to change its state, and usually needs to **synchronize** to remember that the message has been processed. If a message is moved to another folder, the synchronizer must understand the semantics of the new identifier in the destination folder and avoid treating it as an entirely new support request.

This is not a natural extension of an SMTP send command; it requires a mailbox connection with write permissions or the corresponding provider API.

## 8. Constraints to Clarify Before Choosing a Solution

When specifying an email feature, clearly answer the following questions:

1. **Is the application the sender or accessing a mailbox?** Sending accounts and permissions may differ from reading accounts and permissions.
2. **Is a point-in-time result needed or continuous tracking?** "Fetch the 10 latest emails" is completely different from "never miss an email over several months".
3. **Read-only observation or modifying messages on the server?** Read and write permissions must be separated according to need.
4. **Which protocols does the provider support?** Not every mailbox permits IMAP/POP3; provider APIs may require scopes, OAuth, and specific quotas.
5. **Which data store is the source of truth?** If there is a local database, define how new messages, flag changes, deleted messages, errors, and two-way sync are handled.
6. **How are security and operations handled?** Protect credentials/tokens, use TLS, control access to email data, limit attachments, avoid logging private content, manage retries/rate limits, and monitor errors.

Some common mistakes:

- Trying to use SMTP to "read incoming mail" or using JavaMailSender to search an inbox.
- Treating **no exception thrown by send()** as proof that the recipient received or opened the message.
- Using IMAP message sequence numbers as long-term IDs; ignoring UIDVALIDITY or flag/deletion changes.
- Re-reading the entire inbox and inserting every message as new on each scheduled run.
- Automatically modifying/deleting messages when the original requirement only called for reading, without explicit permissions and policies.
- Equating IMAP folders with labels or message identifiers across all providers.

## 9. Choosing the Right Solution for the Requirement

| If the requirement is… | Primary operation | Implementation direction |
| --- | --- | --- |
| "Send an OTP on login" | Sending | Spring Mail / JavaMailSender or sending API |
| "Send an invoice with a PDF attachment" | Sending | JavaMailSender with MIME and attachment |
| "Display the 10 latest emails from a shared inbox" | Reading | IMAP or mail-reading API |
| "Create a ticket on each new email, without duplicates on re-runs" | Reading + synchronization | Receiver with checkpoint, source identifier, and durable storage |
| "Display read/unread changes across multiple devices" | Synchronization | Track flags/labels, update data from server changes |
| "Mark as processed and move message to Archive" | Management + synchronization | Writable mailbox API, then reconcile state |
| "Know whether the recipient verified their email address" | Business verification | Verification link/token in the app; sending mail is only delivery |

## 10. Takeaways When Learning Spring Framework Mail

**Sending** asks a server to transmit a message outward; **reading** retrieves stored messages; **synchronization** maintains consistency as a mailbox changes over time; **management** actively modifies mailbox state or structure. They all involve the word "email", yet they differ in protocols, access permissions, state data, and success conditions.

When working with **Spring Framework Mail**, keep **MailSender/JavaMailSender** in its sending role. If the problem grows into reading an inbox, continuously processing messages, flagging, moving, or deleting emails, design the corresponding mailbox-access and synchronization components separately. Choosing the right boundaries from the start clarifies what the application actually guarantees, especially under network failures, duplicate messages, or differing states across multiple clients.
