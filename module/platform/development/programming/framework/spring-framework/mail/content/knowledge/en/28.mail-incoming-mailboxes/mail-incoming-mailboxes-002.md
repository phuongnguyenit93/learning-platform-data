# IMAP and POP3 in Mail-Receiving Problems

## 1. Receiving Email Is a Different Problem from Sending Email

In the **Spring Framework Mail** ecosystem, the most familiar parts are **JavaMailSender**, **JavaMailSenderImpl**, **MimeMessage**, and **MimeMessageHelper** for building and sending emails to an SMTP server. However, many Java applications also need to **receive and process emails from a mailbox**: fetching customer replies, reading partner invoices, accepting orders sent via email, classifying documents, or handling an operational mailbox.

Sending and receiving use different protocols:

- **SMTP**: the application sends messages to a mail server, or mail servers relay messages to one another.
- **IMAP (Internet Message Access Protocol)**: the application accesses, searches, and manages messages stored on a mail server; it supports folders, status flags, and rich synchronization capabilities.
- **POP3 (Post Office Protocol version 3)**: the application retrieves messages from a mailbox using a simpler model, usually to download content for local processing.

Key point: **Spring Framework Mail primarily provides mail-sending abstractions**, without a **JavaMailReceiver** object completely symmetric to **JavaMailSender** to automatically handle every receiving workflow. To receive email, applications typically use the **Jakarta Mail API** directly or **Spring Integration Mail** to build inbound adapters, polling, and processing flows.

This lesson explains when to use IMAP or POP3, how to read mail in a Spring application, how to design a reliable mail-receiving pipeline, and practical issues around state, duplicates, security, attachments, retries, and performance.

## 2. Business Problems That Commonly Use Inbound Email

| Problem | Email Source | Key Requirements |
|---|---|---|
| Receiving support requests | support@... | Read content, sender, thread, attachments, and create tickets |
| Processing invoices/documents | invoices@... | Validate files, deduplicate, store in object storage, and route to accounting |
| Syncing employee mailboxes | Personal or group mailboxes | Preserve read/unread state, folders, UIDs, and multi-device sync |
| Receiving campaign replies | replies@... | Match In-Reply-To/References with the original notification |
| Processing bounces/DSNs | bounces@... | Parse delivery status and correlate by recipient/notification |
| Automating order intake | orders@... | Verify source, parse content, and process idempotently |
| Archiving emails to a data store | Integrated mailbox | Traceable snapshots and appropriate retention |
| Migrating mailboxes | Old server to new system | High-volume scanning, checkpoints, and preserving metadata |

**IMAP** usually fits problems that require folders, UIDs, flags, and long-term synchronization. **POP3** is more suitable for simpler flows such as downloading messages from a standalone receiving mailbox into a separate processing system when server-side folder state is not needed.

Do not choose a protocol just because IMAP has more features. Consider requirements around **state, concurrency, mailbox ownership, volume, latency, deletion behavior, and provider policies**.

## 3. High-Level Architecture: From Mailbox to Business Logic

~~~text
Sender or external system
                 |
                 | SMTP
                 v
          Receiving mail server
                 |
           INBOX / folders
                 |
          IMAP or POP3
                 |
                 v
      Spring inbound mail component
        |           |
        |        Parse MIME
        |           |
        v           v
       Validation + Security checks
                 |
                 v
       Dedup / Inbox persistence
                 |
                 v
         Queue / Event pipeline
                 |
                 v
          Business processors
        |         |          |
      Ticket    Invoice     Bounce
                 |
                 v
        State / attachment storage
~~~

A good pipeline separates **fetching messages** from **executing business logic**. If every IMAP read runs OCR, calls external APIs, writes to the database, and sends a reply before reading the next message, a downstream error can hold the mailbox connection open for a long time or cause the worker to miss notifications.

Useful concepts:

- **Poller/listener**: accesses the mail server to detect new messages.
- **Mail identity/checkpoint**: records which messages have been seen or fetched successfully.
- **MIME parser**: interprets headers, body content, and attachments.
- **Inbox store**: durably persists email reception events.
- **Worker**: executes business processing outside the mailbox access loop.
- **Dead-letter/quarantine**: holds unprocessable messages for investigation without blocking the entire mailbox.

## 4. What Is IMAP?

**IMAP** allows a client to access and manage emails that remain on the server. Key concepts:

- **Mailbox/folder**: e.g., INBOX, Sent, Archive, Support/Processed.
- **Message sequence number**: the relative position of a message in a folder at a point in time.
- **UID (Unique Identifier)**: a more stable identifier than sequence numbers within the same mailbox, used together with **UIDVALIDITY**.
- **Flags**: states such as **\\Seen**, **\\Answered**, **\\Flagged**, **\\Deleted**.
- **Server-side search**: can search by flags, date, and criteria supported by the server.
- **FETCH**: retrieves headers, bodies, flags, or MIME parts.
- **IDLE**: an extension allowing the server to push change notifications in near real time when supported by server and client.

Example:

~~~text
IMAP server
  |
  +-- INBOX
  |    +-- UID 101: unseen
  |    +-- UID 102: seen
  |    +-- UID 105: flagged
  |
  +-- Archive
  |    +-- UID 203
  |
  +-- Support/Processed
       +-- UID 45
~~~

IMAP follows a **server-stored mailbox** model. One client can read and flag a message, and another client can observe those changes. This is a strength when multiple applications or staff share a mailbox, but it also creates **state-interaction risks** if automation treats flags as the sole checkpoint.

## 5. What Is POP3?

**POP3** focuses on accessing a maildrop to retrieve messages using a relatively simple protocol. A typical POP3 session has these phases:

1. Connect and authenticate.
2. List available messages.
3. Read listing/sizes and retrieve messages.
4. Optionally mark messages for deletion.
5. Quit the session so the server applies deletions according to the protocol.

POP3 generally does not provide a multi-folder model, Seen/Answered/Flagged states, or rich thread synchronization like IMAP.

Example flow:

~~~text
POP3 server: single maildrop
  |
  +-- message A
  +-- message B
  +-- message C
         |
         v
POP3 client downloads A/B/C
         |
         v
Local archive / processing queue
~~~

**Do not assume POP3 always deletes messages after downloading.** Whether messages are deleted or kept on the server depends on the client, protocol commands, and configuration. The application must explicitly decide on retention and deduplication policies.

## 6. How Do IMAP and POP3 Differ?

| Criterion | IMAP | POP3 |
|---|---|---|
| Primary model | Manage mailbox on server | Download messages from maildrop |
| Folders | Supports mailboxes/folders | Usually single maildrop only |
| Seen/Answered flags | Yes | No full equivalent model |
| UID | Per-mailbox UID + UIDVALIDITY | UIDL may be supported by server |
| Multi-client sync | Suitable | Limited |
| Server-side search | Has SEARCH command | More limited |
| Partial data download | Possible, server/API dependent | Usually focused on whole messages |
| Near real-time mechanism | IMAP IDLE if supported | Usually polling |
| Moving messages across folders | Yes | Not a standard POP3 feature |
| Simple flow implementation | Requires richer state management | Often easier to understand initially |
| Checkpoint | Folder + UIDVALIDITY + UID | UIDL if available, or controlled fingerprint |
| Server-side deletion | Flag + EXPUNGE or equivalent method | Mark DELE then apply on QUIT |

Do not think of IMAP as "always push, POP3 always pull." IMAP can be **polled periodically**; IDLE is a change-notification mechanism, not a durable event queue.

## 7. Ports and TLS for Inbound Mail

| Protocol | Common Port | Protection Mode |
|---|---:|---|
| IMAP | 143 | Plaintext initially, upgradable via STARTTLS |
| IMAPS / IMAP implicit TLS | 993 | TLS immediately upon connection |
| POP3 | 110 | Plaintext initially, upgradable to TLS via STLS |
| POP3S / POP3 implicit TLS | 995 | TLS immediately upon connection |

In production applications, require **TLS** and verify the certificate chain and hostname. Ports are common conventions only; actual endpoints must follow the provider's guidance.

**IMAP STARTTLS** and **POP3 STLS** are connection-upgrade mechanisms specific to each protocol. They are not the SMTP STARTTLS command, even though both activate TLS.

Example:

~~~text
IMAP on 143:
  TCP -> IMAP greeting -> CAPABILITY -> STARTTLS -> TLS

IMAPS on 993:
  TCP -> TLS handshake -> IMAP greeting

POP3 on 110:
  TCP -> POP3 greeting -> STLS -> TLS

POP3S on 995:
  TCP -> TLS handshake -> POP3 greeting
~~~

Do not send usernames/passwords over an unprotected connection when the provider requires TLS. Do not use **trust all certificates** to "fix" hostname, CA, or truststore errors.

## 8. How Does Spring Framework Mail Support Receiving Mail?

Functional layers in the Spring ecosystem:

| Component | Purpose |
|---|---|
| **spring-context-support / JavaMailSender** | Build and send emails via SMTP |
| **Jakarta Mail Session, Store, Folder, Message** | Access IMAP/POP3 and read MIME |
| **Spring Integration Mail** | Inbound adapters, polling/IMAP IDLE, and turning emails into messages in integration flows |
| **Spring Scheduling / TaskExecutor** | Schedule mailbox queries and execute workers |
| **Spring Data / JDBC** | Store checkpoints, state, idempotency, and metadata |
| **Spring Security** | Protect processing endpoints, tenant context, and secrets |

Common choices:

**A. Direct Jakarta Mail** when fine-grained control over folders, UIDVALIDITY, search, flags, and checkpoints is needed.

**B. Spring Integration Mail** when the mail-receiving workflow fits the **message channel** model, inbound adapters, pollers, filters, transformers, and integration endpoints.

The two options are not mutually exclusive. Spring Integration Mail is typically built on Jakarta Mail, and an application can use Jakarta Mail inside a dedicated technical component and then publish results into a Spring channel/queue.

## 9. Dependencies for the Examples

In a modern Spring Boot project, you can use:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    // If you want inbound adapters / integration flows:
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The direct Java examples below use the **jakarta.mail** package and assume the Jakarta Mail implementation dependency is present via the starter or corresponding dependency. **Spring Boot 3 / Spring Framework 6** uses the Jakarta Mail namespace, unlike **javax.mail** in older generations.

**You do not need to add Spring Integration Mail** if you only want to call the Jakarta Mail API directly. Conversely, simply adding starter-mail does not create an inbound worker for IMAP or POP3 automatically.

When choosing dependencies and DSL examples, you must use **Spring Boot, Spring Integration, Jakarta Mail, and JDK** versions that are mutually compatible with your project's build system.

## 10. Core Jakarta Mail Objects for Reading Mail

| API | Role |
|---|---|
| **Session** | Holds Jakarta Mail configuration properties and providers |
| **Store** | Connects to an IMAP or POP3 mail store |
| **Folder** | Opens and accesses a mailbox/maildrop |
| **Message** | A received message |
| **MimeMessage** | Message with MIME headers and multipart body |
| **Multipart** | Container of multiple body parts |
| **Part / BodyPart** | Access Content-Type, content, filename, disposition |
| **FetchProfile** | Hint to prefetch a set of metadata across multiple messages |
| **Flags** | Seen/Deleted/Answered states and other flags when supported by protocol |
| **UIDFolder** | Common API for accessing UID and UIDVALIDITY in UID-supporting folders |

Simple access flow:

~~~text
Session.getInstance(properties)
          |
          v
session.getStore("imaps")
          |
          v
store.connect(...)
          |
          v
store.getFolder("INBOX")
          |
          v
folder.open(READ_ONLY / READ_WRITE)
          |
          v
folder.getMessages(...) / search(...)
          |
          v
read headers, MIME, attachments
          |
          v
folder.close(...) -> store.close()
~~~

**Store, Folder, and Message are usually tied to connection/session resources**; do not push these objects onto a queue expecting a worker in another process to use them. Convert the email into a durably stored record or data object before closing the session.

## 11. Example of Reading INBOX over IMAPS Using Jakarta Mail

The example below opens **IMAP implicit TLS on port 993**, fetches up to the last 20 messages by sequence number, and reads basic metadata. The goal is to illustrate connection and resource lifecycle; it is **not yet a checkpointed consumer**.

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.internet.InternetAddress;
import java.util.Properties;

public final class ImapsMailboxReader {

    public void readRecent(
            String host,
            String username,
            String password
    ) throws Exception {

        Properties props = new Properties();
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.writetimeout", "10000");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(host, 993, username, password);
            Folder inbox = store.getFolder("INBOX");

            try {
                inbox.open(Folder.READ_ONLY);

                int count = inbox.getMessageCount();
                if (count == 0) {
                    return;
                }

                int first = Math.max(1, count - 19);
                Message[] messages = inbox.getMessages(first, count);

                for (Message message : messages) {
                    System.out.println("Subject: "
                            + message.getSubject());

                    InternetAddress[] from =
                            (InternetAddress[]) message.getFrom();

                    if (from != null && from.length > 0) {
                        System.out.println(
                                "From: " + from[0].getAddress()
                        );
                    }
                }
            } finally {
                if (inbox.isOpen()) {
                    inbox.close(false);
                }
            }
        } finally {
            store.close();
        }
    }
}
~~~

The example uses **host, username, and password** values from the application's secure configuration. Never put real credentials in source code or logs.

### Limitations of This Example

- Only reads the **last 20 messages by sequence number**; messages can be missed if the mailbox receives more than 20 messages between runs.
- Has no checkpoint, so each run can re-read the same emails.
- Reading metadata does not mean the email has been business-processed.
- Printing sender addresses to stdout is only suitable for demonstration in a test environment; production must control logging and PII.
- Casting to **InternetAddress[]** works for typical Internet mail mailboxes, but an implementation may return an **Address[]** array that is not that concrete array type; in broader implementations, check each element with **instanceof InternetAddress** instead of casting the entire array.

In a production pipeline, read by **UID/checkpoint**, not just the last N emails. The next sections explain why.

## 12. Reading via IMAP STARTTLS Instead of Implicit TLS

If the server requires using IMAP port 143 and upgrading to TLS, a Jakarta Mail configuration can be:

~~~java
Properties props = new Properties();

props.put("mail.imap.starttls.enable", "true");
props.put("mail.imap.starttls.required", "true");
props.put("mail.imap.ssl.checkserveridentity", "true");
props.put("mail.imap.connectiontimeout", "5000");
props.put("mail.imap.timeout", "10000");
props.put("mail.imap.writetimeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("imap");

try {
    store.connect(host, 143, username, password);
    // Access Folder after STARTTLS has been established.
} finally {
    store.close();
}
~~~

Differences to remember:

~~~text
session.getStore("imaps")
  -> mail.imaps.* properties
  -> implicit TLS, usually port 993

session.getStore("imap")
  -> mail.imap.* properties
  -> STARTTLS if enable/required, usually port 143
~~~

**The property prefix must match the protocol/provider in use.** If you configure **mail.imaps.timeout** but obtain **Store("imap")**, the timeout may not be applied as expected.

When security is required, **starttls.required=true** prevents continuing an unencrypted session if the server does not support upgrading. Never fix TLS errors by skipping hostname verification or trusting all certificates.

## 13. IMAP Message Sequence Numbers Are Not Durable Checkpoints

In IMAP, a **sequence number** indicates a message's current position in the selected folder. It can change when messages are deleted/expunged.

Example:

~~~text
At 09:00:
  seq 1 -> message A
  seq 2 -> message B
  seq 3 -> message C

After message A is EXPUNGED:
  seq 1 -> message B
  seq 2 -> message C
~~~

If the application saves **lastSequenceNumber = 3**, and next time reads "sequence > 3", it may miss new messages because the numbering has shifted.

Therefore:

- **Sequence numbers** are for temporary positional access within a session/folder.
- **UID** is a more suitable identifier for checkpointing within the same mailbox when combined with **UIDVALIDITY**.
- **Message-ID** is a header generated by the sending system, not an absolutely reliable folder identifier key.

**Do not use message.getMessageNumber() as a long-term idempotency key**.

## 14. IMAP UID and UIDVALIDITY

Each message in an IMAP mailbox can have a server-assigned **UID**. The UID is meaningful within the mailbox scope and is tied to **UIDVALIDITY**.

A checkpoint may look like:

~~~text
account_id      = mailbox-support-A
folder          = INBOX
uid_validity    = 1836720
last_uid        = 184930
~~~

Meaning:

- If **UIDVALIDITY remains the same**, UIDs can be treated as stable identifiers within the same folder.
- If **UIDVALIDITY changes**, previously stored UIDs may no longer map to the same messages. A controlled re-sync procedure must be executed.
- A UID is not a global identifier across two folders, two accounts, or two servers.
- When copying/moving between folders, the copy in the new folder may receive a different UID.

### Jakarta Mail API

~~~java
import jakarta.mail.Folder;
import jakarta.mail.UIDFolder;
import jakarta.mail.Message;

Folder inbox = store.getFolder("INBOX");
inbox.open(Folder.READ_ONLY);

if (!(inbox instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "IMAP folder does not implement UIDFolder API"
    );
}

long uidValidity = uidFolder.getUIDValidity();
long messageUid = uidFolder.getUID(message);
~~~

The snippet assumes **store** is already connected and **message** comes from that open **inbox** folder. With standard Jakarta Mail IMAP providers, `UIDFolder` is the appropriate API.

### What to Do When UIDVALIDITY Changes?

Do not continue using the **old last_uid** as usual. One strategy:

1. Mark the old checkpoint as invalid.
2. Schedule a bounded mailbox re-scan with deduplication.
3. Reconcile against already-stored messages using an appropriate business key.
4. Create a new checkpoint under the new UIDVALIDITY after processing.
5. Monitor changes to detect mailbox migrations/rebuilds or server-side incidents.

There is no simple, reliable transformation from old UIDs to new UIDs once UIDVALIDITY has changed.

## 15. Fetching IMAP Messages by UID Instead of Loading the Entire INBOX

With **UIDFolder**, you can request messages within a UID range:

~~~java
UIDFolder uidFolder = (UIDFolder) inbox;

long fromUid = lastProcessedUid + 1;
Message[] candidates = uidFolder.getMessagesByUID(
        fromUid,
        UIDFolder.LASTUID
);

for (Message message : candidates) {
    long uid = uidFolder.getUID(message);
    // Prepare data and process/checkpoint according to policy.
}
~~~

This API illustrates UID-based retrieval, **not yet enough to guarantee correctness in production**:

- If the mailbox has a large volume of messages, a wide UID query can return too many messages into memory.
- UIDs are not necessarily contiguous; gaps can exist due to expunges.
- Checkpoints must be stored per **UIDVALIDITY** and account/folder.
- You must cap the number of messages per batch or design proper pagination.
- Update the checkpoint only after durably persisting the email, not immediately upon seeing the UID.
- If a message is deleted between listing and fetching, the server may return incomplete data or an error; handle this explicitly.

### Why Can lastProcessedUid Be Dangerous?

Suppose:

~~~text
UID 100 -> processed successfully
UID 101 -> temporary parse error
UID 102 -> processed successfully
~~~

If checkpoint **102** is written immediately, the worker will only read UIDs greater than 102 next time and skip **101** forever.

There are two options:

1. **Contiguous checkpoint:** only advance the high-water mark to the highest UID where every previously seen UID has been processed or durably persisted; errors go to a retry queue before advancing.
2. **Per-message state storage:** record an entry per UID, allowing 101 to stay in FAILED/RETRY while the discovery checkpoint can still advance.

For systems needing high throughput and per-message retries, an **inbox table with a unique key on mailbox + UIDVALIDITY + UID** is usually more reliable than keeping only a single last UID variable.

## 16. Distinguishing the Seen Flag from Business Processing State

IMAP has the **\\Seen** flag indicating a message has been marked read. However, "read" does not mean:

- MIME has been parsed successfully.
- Attachments have been saved.
- A ticket/invoice has been created.
- An event has been published to a queue.
- A database transaction has committed.

Failure example:

~~~text
Worker FETCHes message
      |
      v
Set \\Seen
      |
      v
Process crashes before creating ticket

Next run searches only UNSEEN
      |
      v
Message is skipped permanently
~~~

If the mailbox is also read manually by staff or accessed by multiple clients, they can change the Seen flag unintentionally. Therefore **do not use Seen as the sole source of truth for exactly-once processing**.

### Practical Policy

- You can open the folder **READ_ONLY** during discovery/fetch to avoid mutating server state.
- Store **UID/checkpoints** and processing records in the application's database.
- Only set Seen or move to a Processed folder after business logic commits according to policy.
- When multiple consumers exist, use database/queue claim/lease mechanisms so the same UID is not processed concurrently.
- Avoid automatically turning all unread messages into Seen without verifying the mailbox users' expectations.

A shared mailbox system may need to keep the Seen flag under human control and rely solely on an **application-specific checkpoint** for automation.

## 17. What Does IMAP IDLE Help With?

**IMAP IDLE** allows the server to notify the client of changes in a folder while the client waits, instead of sending polling commands continuously at every interval.

~~~text
Client                        IMAP server
  | SELECT INBOX                   |
  |------------------------------->|
  | IDLE                           |
  |------------------------------->|
  |                                |
  |<----------- EXISTS update -----|
  | DONE / end IDLE                |
  |------------------------------->|
  | FETCH/SEARCH new messages      |
  |------------------------------->|
  | IDLE again                     |
~~~

Potential benefits:

- Reduces latency in detecting new emails.
- Reduces constant polling when a mailbox receives low traffic.
- Fits ticket inboxes, customer replies, or mailboxes requiring low latency.

However, IDLE **is not a broker guaranteeing event persistence**:

- TCP connections can drop.
- Servers can proactively terminate IDLE after some time.
- Firewalls/NATs can close idle connections.
- During reconnection, the client can miss EXISTS notifications.
- Servers may send multiple events, while actual content still needs to be fetched.

**After reconnecting, you still must reconcile UID/checkpoints**, not merely process the IDLE events just received.

## 18. When to Use Polling vs. IMAP IDLE?

| Criterion | IMAP Polling | IMAP IDLE |
|---|---|---|
| Detection mechanism | Scheduled queries | Server notifies of changes |
| Implementation complexity | Easy to control via scheduler | Requires managing persistent connections |
| Latency | Poll interval plus processing | Usually shorter if server supports it |
| Load when mailbox has low traffic | Empty polls occur | Fewer queries, but holds a connection open |
| Disconnection | Next poll runs automatically | Requires reconnect and catch-up sync |
| UID/checkpoint required | Yes | Still required |
| Suitable scenarios | Periodic batch, low load, minute-level SLA | Tickets/live replies, near real-time SLA |

A resilient architecture can combine both:

~~~text
IMAP IDLE -> signals change -> triggers incremental UID sync

Periodic reconciliation -> catches missing UIDs

Connection broken -> reconnect -> incremental UID sync
~~~

Core takeaway: **IDLE is a wakeup signal**, while **UID reconciliation and inbox persistence** are the foundation that prevents data loss. Do not record a checkpoint merely upon receiving an EXISTS notification before fetching and persisting the message.

For applications with many mailboxes, one IDLE connection per folder can consume sockets, threads, and server resources. Check the provider's concurrent connection quota and plan partitioning/scheduling strategies rather than opening thousands of permanent connections.

## 19. Spring Integration Mail: Inbound Adapters

**Spring Integration** uses a message-driven model:

~~~text
IMAP/POP3 server
         |
         v
Mail inbound component
         |
         v
Spring Integration MessageChannel
         |
         v
Filter / Transformer / Service Activator
         |
         v
Business service / Queue / Database
~~~

In the Spring Integration Mail ecosystem, key concepts include:

- **ImapMailReceiver**: receives messages via IMAP.
- **Pop3MailReceiver**: receives messages via POP3.
- **MailReceivingMessageSource**: bridges a mail receiver into a pollable message source.
- **IMAP IDLE adapter**: an inbound component using the IDLE mechanism when configured and supported by the server.
- **Poller**: schedules calls to the message source, using fixed delay or other triggers.
- **MessageChannel**: decouples message retrieval from downstream processing steps.
- **Service activator / handler**: invokes business logic after receiving a message.

Architecture example:

~~~text
ImapMailReceiver
       |
       v
MailReceivingMessageSource
       |
       v
Poller (every 30 seconds)
       |
       v
Channel
       |
       v
Validate + Persist inbox
       |
       v
Async processing
~~~

In systems using Spring Integration DSL, inbound flows can be configured with the factories corresponding to the version in use. **Depending on the Spring Integration version, adapter initialization, DSL method names, and return types may vary.** Always check the API against your project's actual dependency; do not copy an old XML/namespace example and assume it works on newer Spring Integration.

### Does Spring Integration Guarantee Exactly-Once Automatically?

No. Inbound adapters can re-receive messages after a reconnect, restart, or when server state has not been marked yet. **Idempotency, transactions, durable persistence, and per-mailbox checkpoints** remain the application's design responsibility.

In many projects, Spring Integration is used for orchestration and filtering, while still writing a **mail_inbox** record with a unique key before executing any operations with side effects.

## 20. What Needs to Be Configured When Using Spring Integration Mail

A real-world inbound adapter must clarify:

| Configuration Group | Questions |
|---|---|
| Protocol | IMAP, IMAPS, POP3, or POP3S? |
| Mailbox | Which host, port, folder/maildrop? |
| Authentication | Password/app password/OAuth2 permitted by provider? |
| TLS | Implicit TLS or mandatory STARTTLS/STLS? |
| Polling | What poll interval, batch size, and concurrency? |
| Search | Select only unread messages or use a dedicated UID/checkpoint? |
| Mark-as-read | When to set Seen, if at all? |
| Delete/expunge | Is deleting messages on the server permitted? |
| MIME output | Keep raw MimeMessage or convert to a normalized payload? |
| Transaction | When to record the inbox entry and confirm receipt? |
| Error channel | Where do emails failing parse/validation go? |
| Reconnect | How to recover after timeout, disconnect, or credential rotation? |

Avoid embedding username/password directly in a **receiver configuration URL** and then logging the full URL. Some APIs accept a mail URL, but credentials should come from a secret manager and be masked when inspecting configuration.

### Things to Check with Adapters

A default configuration may alter message state with flags, filter by **UNSEEN**, or apply a fetch limit. These behaviors affect retries and already-processed data, so you must inspect the characteristics of the actual **receiver/adapter + library version**.

Do not rely on default behavior as a business guarantee. If the mailbox is shared with humans, mark-as-read and delete settings must be chosen deliberately.

## 21. Example Service Reading POP3S via Jakarta Mail

With POP3 implicit TLS, **protocol "pop3s"** on port 995 is commonly used. A simple example:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public final class Pop3sMailboxReader {

    public void readMessages(
            String host,
            String username,
            String password
    ) throws Exception {

        Properties props = new Properties();
        props.put("mail.pop3s.connectiontimeout", "5000");
        props.put("mail.pop3s.timeout", "10000");
        props.put("mail.pop3s.writetimeout", "10000");
        props.put("mail.pop3s.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("pop3s");

        try {
            store.connect(host, 995, username, password);
            Folder inbox = store.getFolder("INBOX");

            try {
                inbox.open(Folder.READ_ONLY);

                int count = inbox.getMessageCount();
                for (int i = 1; i <= count; i++) {
                    Message message = inbox.getMessage(i);
                    String subject = message.getSubject();

                    // In practice, store fingerprint/UIDL to prevent duplicates.
                    processMetadata(subject);
                }
            } finally {
                if (inbox.isOpen()) {
                    inbox.close(false);
                }
            }
        } finally {
            store.close();
        }
    }

    private void processMetadata(String subject) {
        // Placeholder example for the processing step.
    }
}
~~~

Caveats:

- This is a **reading demonstration**, without UIDL, inbox persistence, retries, quotas, or deduplication.
- Each run may re-read the entire maildrop.
- Do not load tens of thousands of messages into memory without batching/limits.
- A POP3 server may impose concurrency limits and deletion/retention policies.
- **READ_ONLY** avoids deletion intent in this example; it does not mean POP3 offers a full set of flags and folders like IMAP.

If the mailbox is large, prefer a server/API with pagination capabilities or adjust the architecture. POP3 was not designed to perform all the metadata querying/synchronization operations of IMAP.

## 22. POP3 STLS on Port 110

A provider may require plain POP3 followed by TLS upgrade using **STLS**:

~~~java
Properties props = new Properties();

props.put("mail.pop3.starttls.enable", "true");
props.put("mail.pop3.starttls.required", "true");
props.put("mail.pop3.ssl.checkserveridentity", "true");
props.put("mail.pop3.connectiontimeout", "5000");
props.put("mail.pop3.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("pop3");

try {
    store.connect(host, 110, username, password);
    // Retrieve maildrop from Store after a secure connection is established.
} finally {
    store.close();
}
~~~

The property keys here belong to the **compatible Jakarta Mail POP3 provider**. Just like IMAP, the **mail.pop3** and **mail.pop3s** prefixes cannot be swapped arbitrarily.

**Do not enable a TLS mode just because the port looks familiar.** The endpoint address, STLS capability, and authentication method must match the provider's documentation.

## 23. POP3 UIDL: How to Identify Already-Downloaded Messages

POP3 has a **UIDL (Unique-ID Listing)** extension supported by many servers, allowing clients to identify previously downloaded messages instead of relying on their ordinal number in the maildrop.

Example:

~~~text
POP3 session A:
  1 -> UIDL abc-100
  2 -> UIDL abc-101
  3 -> UIDL abc-102

After one message is deleted:
POP3 session B:
  1 -> UIDL abc-101
  2 -> UIDL abc-102
~~~

Here the message ordinal numbers shift, while the UIDLs of remaining messages are preserved by the server according to the extension contract.

Points to note:

- **Standard Jakarta Mail Folder does not define a common portable UIDL API** like IMAP's `UIDFolder`.
- POP3 implementations may provide provider-specific APIs to fetch UIDL (for example, a provider's `POP3Folder` class).
- Do not cast a folder to a concrete implementation without verifying the actual library/version in use.
- UIDL scope and behavior depend on the POP3 server; store it alongside the account/maildrop identity.
- If the server does not support UIDL or UIDL is unstable, a fallback deduplication strategy is needed.

A checkpoint store may persist:

~~~text
pop3_account_id
uidl_value
first_seen_at
processing_status
ingested_message_ref
~~~

Do not use POP3 message sequence numbers as long-term immutable keys. For a mailbox with multiple workers, pay special attention to the fact that a message can be retrieved by more than one session.

## 24. POP3: Delete Messages or Keep Them on the Server?

POP3 generally allows a client to mark messages for deletion during a session. Server-side deletion is executed per protocol behavior when the session closes properly.

Two strategies:

**Keep messages on the server**

- Easier to reconcile or re-download while the pipeline is still stabilizing.
- Requires UIDL/deduplication to avoid repeated processing.
- The maildrop can grow in size and storage quota.

**Delete after receiving**

- Keeps the maildrop small.
- Requires proof that data was durably persisted before marking for deletion.
- If deleted before the application transaction commits, data can be lost.
- POP3 is not a transactional queue with exact post-commit ACK semantics.

A safer workflow example:

~~~text
POP3 RETR message
       |
       v
Validate size and parser boundaries
       |
       v
Persist raw message + dedup record
       |
       v
Commit inbox transaction
       |
       v
Optional mark for deletion
       |
       v
Close session according to delete policy
       |
       v
Business worker handles persisted inbox item
~~~

Even when following the right order, crashes can still occur between the database commit and message deletion, leaving the message on the server to reappear. **Deduplication/idempotency** must handle this.

Do not blindly apply **folder.close(true)** or the `DELETED` flag to every mail server or every type of inbox. IMAP and POP3 deletion policies differ, and a shared mailbox usually must not have automatic deletion enabled.

## 25. When IMAP Is Better Suited Than POP3

Choose IMAP if the application needs:

- Mailbox synchronization across INBOX/Processed/Archive folders.
- Marking messages as read, answered, or processed as server-side state.
- Concurrent access by multiple clients or human mailbox management.
- Searching by headers, dates, flags, and folders.
- Stable per-mailbox UID/checkpoints.
- Near real-time change notifications via IDLE.
- Fetching headers first and downloading bodies/attachments later per policy.
- Long-term server-side storage and classification of messages.

Example **support ticket inbox**:

~~~text
support@company.example
       |
       v
IMAP INBOX
       |
       +-- New mail -> create ticket
       +-- Human reads mailbox -> Seen may change
       +-- Automation stores own UID checkpoint
       +-- After durable processing -> optional move to Processed
~~~

In this model, IMAP is advantageous because it has folders and state, yet the application still must not use the Seen flag in place of a business checkpoint.

## 26. When POP3 Can Be Suitable

Choose POP3 when:

- The system only needs to **download messages**, without managing multiple folders.
- The mailbox is dedicated exclusively to a single integration process.
- Messages are moved into the application's **inbox database/object store** immediately after reading.
- Read-status synchronization across multiple clients is not needed.
- Traffic and client count are low, minimizing contention.
- The provider offers POP3 but not IMAP for that specific account.

Example document-collection mailbox:

~~~text
receipts@partner.example
        |
        v
POP3 retrieve
        |
        v
Durable inbox + attachment archive
        |
        v
Document processing queue
        |
        v
Accounting workflow
~~~

With this design, POP3 is purely a **data ingestion gateway**. Processing state, retries, and auditing are managed inside the application.

Do not use POP3 if folder synchronization, rich flag manipulation, or coordination across multiple clients on the same mailbox is required without an additional coordination layer.

## 27. The Inbox Pattern Architecture to Prevent Losing Emails

There is **no shared ACID transaction** between a mail server and an application database. When processing mail, you can encounter:

~~~text
Case A:
  Fetch mail OK
  Mark Seen / delete on server
  DB transaction fails
  -> Opportunity to process is lost if searching only unread/non-deleted

Case B:
  Fetch mail OK
  DB commit OK
  Process crashes before mark Seen/delete
  -> Next run reads the same email again
~~~

This is why inbound email should be designed around **at-least-once ingestion + idempotent processing**, rather than promising exactly-once based solely on IMAP or POP3.

A pipeline:

~~~text
IMAP / POP3 fetch
       |
       v
Derive stable identity
       |
       v
BEGIN DB TRANSACTION
  INSERT mail_inbox (unique mail identity)
  INSERT processing_outbox / work item
COMMIT
       |
       v
Advance discovery checkpoint
       |
       v
Optional mark Seen / move / delete on mail server
       |
       v
Business worker processes persisted item
~~~

If the process crashes before commit, the email is read again. If it crashes after commit but before checkpointing or mutating the server, the email is read again **but the unique key prevents creating the same inbox item a second time**.

### When Is the Checkpoint Allowed to Advance?

Only after messages have been **durably persisted or assigned a durable error/quarantine state**, so that no UID is skipped without a trace in the inbox database.

If the business worker also needs to call external services, do not hold the IMAP Folder open waiting until the entire workflow finishes; let the worker process from the persisted data.

## 28. Message Identifiers: IMAP UID, POP3 UIDL, and Message-ID

An email can have multiple identifiers:

| Identifier | Source | Reliability and Scope |
|---|---|---|
| **IMAP UID** | IMAP server | Used with mailbox/folder and UIDVALIDITY |
| **IMAP UIDVALIDITY** | IMAP server | Identifies the UID generation of a folder |
| **POP3 UIDL** | POP3 server if supported | Scoped to maildrop/provider; do not substitute sequence numbers |
| **Message-ID header** | Message creator | Not guaranteed globally unique; can be missing/spoofed |
| **Raw MIME SHA-256** | Computed by app on fetched bytes | Identifies exact byte content; can change on relay/re-serialization |
| **Provider message ID** | ESP/mail server if available | Meaningful per provider/account |
| **Business correlation ID** | Assigned/mapped by app | Used to link with business tickets/notifications |

For IMAP, the unique key is typically:

~~~text
(mail_account_id, folder_id, uid_validity, uid)
~~~

For POP3:

~~~text
(mail_account_id, uidl)
~~~

When UIDL is unavailable or unreliable, a combination of headers/size/hash can be used **with an explicit deduplication policy**. Do not rely solely on **Message-ID** as an absolute key because two different emails can share a duplicate Message-ID, lack one, or have it altered by a provider.

### Two Mailboxes Receiving the Same Message Is Not Necessarily a Duplicate Error

A message forwarded from mailbox A to mailbox B may need to be processed in two separate pipelines. Ingestion identity **must include the mailbox/account scope** or tenant scope according to business rules.

Conversely, the same email fetched again from the same mailbox after a restart must not create two tickets or import an invoice twice.

## 29. Designing the mail_inbox Table

An example business data model may include:

~~~sql
CREATE TABLE mail_inbox (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id        VARCHAR(120) NOT NULL,
    folder_name       VARCHAR(300),
    uid_validity      BIGINT,
    imap_uid          BIGINT,
    pop3_uidl         VARCHAR(600),
    message_id_header VARCHAR(1000),
    raw_object_key    VARCHAR(1200),
    sender_address    VARCHAR(600),
    subject_preview   VARCHAR(500),
    received_at       TIMESTAMP WITH TIME ZONE,
    ingested_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    status            VARCHAR(40) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0
);
~~~

Example constraint for IMAP:

~~~sql
CREATE UNIQUE INDEX uq_imap_mail_identity
ON mail_inbox (
    account_id,
    folder_name,
    uid_validity,
    imap_uid
)
WHERE imap_uid IS NOT NULL;
~~~

Example for POP3:

~~~sql
CREATE UNIQUE INDEX uq_pop3_mail_identity
ON mail_inbox (account_id, pop3_uidl)
WHERE pop3_uidl IS NOT NULL;
~~~

This is illustrative DDL for a SQL engine supporting **partial indexes** such as PostgreSQL; a production schema may need tenantId, a stable mailbox ID, checksums, state transitions, and retention fields.

### Why Store Raw MIME Outside the Database?

If emails have large attachments, stuffing entire EMLs/blobs into a hot transactional table can bloat database size and degrade queries. You can store **raw EML** in access-controlled object storage while keeping **object key, checksum, size, and metadata** in the database.

Important: you need a **staging/commit/reconciliation** process between object storage and the DB because the two systems lack a shared atomic transaction. Never mark an inbox entry `PERSISTED` before the EML is safely stored in storage.

### Do Not Store Unnecessary PII

Sender, Subject, attachment names, and certain MIME headers can contain personal data. Only store information needed for business logic and debugging for an appropriate retention period. If only Message-ID and UID are needed, there is no need to retain the entire body indefinitely.

## 30. Persisting Clear Mail-Receiving States

A state machine might look like:

~~~text
DISCOVERED
    |
    v
FETCHING
    |
    +-- transient network error -> FETCH_RETRY
    |
    +-- MIME too large / disallowed -> QUARANTINED
    |
    v
PERSISTED
    |
    v
PROCESSING
    |
    +-- transient business error -> PROCESS_RETRY
    |
    +-- invalid/malicious content -> QUARANTINED
    |
    v
PROCESSED
~~~

These states are application-defined; IMAP or POP3 **does not provide a business state machine out of the box**.

If a message fails parsing, do not let the poller continuously retry it immediately and block every email behind it. You can store the raw content in quarantine, record a reason code, and let the discovery checkpoint advance according to policy.

### Discovery and Processing Are Two Distinct Processes

**Discovery** identifies messages not yet persisted to the inbox database. **Processing** reads persisted inbox items and performs business work.

Separating these two steps helps:

- Close IMAP connections faster.
- Bound CPU/attachment parsing independently of mail server connection counts.
- Retry business logic without re-downloading emails from the server.
- Handle errors/quarantine without losing track of the original mail.
- Throttle throughput per tenant, mailbox type, or task type.

## 31. Reading MIME: An Email Is Not Just a String

A received email may contain:

~~~text
MimeMessage
  |
  +-- multipart/mixed
       |
       +-- multipart/related
       |    |
       |    +-- multipart/alternative
       |    |    +-- text/plain
       |    |    +-- text/html
       |    |
       |    +-- image/png (inline, Content-ID)
       |
       +-- application/pdf (attachment)
~~~

Scenarios:

- **text/plain** is the plain-text version for reading or simple extraction.
- **text/html** is the HTML version, which may include links and inline resources.
- **multipart/alternative** contains alternative representations, not fragments to concatenate directly.
- **multipart/related** groups HTML with CID images/inline resources.
- **multipart/mixed** typically combines body content and attached files.

Therefore, code like:

~~~java
String body = (String) message.getContent();
~~~

is **unsafe as a general-purpose parser**. If the message is multipart, **getContent()** can return a **Multipart** rather than a String, causing a `ClassCastException`.

Design a **MIME walker** based on **Part**, inspecting Content-Type/Content-Disposition and classifying leaf parts.

## 32. Traversing Multipart Messages with Jakarta Mail

An example depth-limited helper:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public final class MimePartCollector {

    public record PartRef(
            Part part,
            String mimeType,
            String disposition
    ) {
    }

    public static List<PartRef> collect(Part root)
            throws Exception {
        List<PartRef> found = new ArrayList<>();
        walk(root, 0, found);
        return List.copyOf(found);
    }

    private static void walk(
            Part part,
            int depth,
            List<PartRef> found
    ) throws Exception {
        if (depth > 24 || found.size() > 200) {
            throw new IllegalStateException(
                    "MIME nesting/part count exceeds policy"
            );
        }

        found.add(new PartRef(
                part,
                part.getContentType(),
                part.getDisposition()
        ));

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();

            if (!(content instanceof Multipart multipart)) {
                throw new IllegalStateException(
                        "Expected Multipart content"
                );
            }

            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                walk(child, depth + 1, found);
            }
        }
    }
}
~~~

This is an **illustrative helper for common MIME multipart structures**, not yet a production security parser:

- It does not yet handle nested **message/rfc822** attachments separately.
- Limiting **part count and depth** does not replace limiting **total decoded bytes**.
- It does not distinguish main body text from text attachments.
- It does not check antivirus, actual file type, or dangerous HTML.
- Calling **part.getContent()** can trigger I/O and exceptions.

In a pipeline receiving mail from external sources, apply pre/post-decode size limits, timeouts, and resource budgets to the parser.

## 33. How to Choose Between text/plain and text/html?

When **multipart/alternative** is present, the two parts are usually different representations of the same content:

~~~text
multipart/alternative
  |
  +-- text/plain: "Order ORD-100 has been delivered"
  |
  +-- text/html: "<p>Order ORD-100 has been delivered</p>"
~~~

Do not concatenate both versions into:

~~~text
Order ORD-100 has been delivered
Order ORD-100 has been delivered
~~~

because that produces duplicated content.

Policies can be:

- **Prefer plain text** if only simple classification/extraction is needed and the text is clear enough.
- **Read sanitized HTML** when plain text is absent or table/link structure is required.
- Store both forms if needed for user display or auditing.
- Avoid using naive regexes to "strip HTML tags" on complex inputs; use a safely configured HTML parser if truly needed.

When extracting text from MIME, inspect **Content-Disposition**: a **text/plain** attachment is not necessarily the main body of the email.

### Charset

Emails may use UTF-8 or other charsets. Jakarta Mail typically decodes text content based on MIME headers. If a header is missing or wrong, apply a controlled error-handling policy; never silently reinterpret arbitrary bytes as UTF-8 and corrupt Vietnamese text.

Retaining raw MIME or checksums according to policy helps with reconciliation when a parser mis-decodes a charset.

## 34. Handling Attachments and Inline Resources

An attachment can be identified through:

- **Content-Disposition: attachment**.
- **Filename** in Content-Disposition/Content-Type parameters.
- MIME types such as **application/pdf**, **image/png**, **application/vnd...**.
- Context of the part within the multipart tree.

Inline resources typically have a **Content-ID** and are referenced from HTML via **cid:**, though Content-Disposition can vary by producer.

Do not merely check:

~~~java
if (part.getFileName() != null) {
    // attachment
}
~~~

because an inline resource can also have a filename, and an attachment sometimes lacks one.

### Reading Data Using InputStream

~~~java
import jakarta.mail.Part;
import java.io.InputStream;

public void copyAttachment(
        Part part,
        AttachmentObjectStorage storage,
        String tenantId
) throws Exception {

    try (InputStream input = part.getInputStream()) {
        storage.saveBounded(
                tenantId,
                input,
                part.getFileName(),
                part.getContentType()
        );
    }
}
~~~

**AttachmentObjectStorage** is an illustrative application-designed interface. The **saveBounded** method must cap bytes, sanitize the filename, avoid trusting the sender-declared Content-Type, and write data into a storage location with proper tenant permissions.

Store attachments only after malware scanning and file-type policy checks, or place them in **quarantine storage** before exposing them downstream. Never automatically execute files, macros, or scripts, or use filenames as filesystem paths.

## 35. Do Not Trust MIME Headers and the From Address

Email is data arriving from an external network. The following fields **are not absolute proof of identity**:

- **From**: can be spoofed.
- **Reply-To**: can point to an address on a different domain.
- **Subject**: can contain misleading data, personal information, or unusual characters.
- **Message-ID**: can be missing or intentionally duplicated.
- **Content-Type**: declared by the sender, and may not match actual bytes.
- **Filename**: can contain path traversal, control characters, or deceptive extensions.
- **Date**: generated by the sending client, not necessarily when the mail server received it.
- **X-... headers**: can be self-crafted and are not inherently trustworthy.

For example, an email sent with:

~~~text
From: accounting@trusted-company.example
Reply-To: attacker@outside.example
Subject: Urgent wire transfer
~~~

Must not be assumed to come from the accounting department merely because the From display looks familiar.

### Supplementary Authentication Information

Mail servers may add **Authentication-Results** covering SPF, DKIM, and DMARC. These fields are useful in processing policies, but the application must understand the **trust boundary**: headers added by the sender itself must not be treated as verification results from trusted mail infrastructure.

For sensitive workflows such as approving payments, modifying accounts, or granting permissions, **inbound email should only serve as an initiation signal**; the action itself requires an independent authentication/authorization step.

## 36. HTML and Attachments Are Untrusted Data

Common risks:

- HTML containing phishing links or remote images causing tracking.
- Scripts, forms, or interactive content stored and rendered unsanitized in an admin UI.
- ZIP archives with massive decompressed sizes.
- PDF/Office files containing malicious payloads.
- Attachment filenames containing **../** or characters causing unintended filesystem operations.
- Deep MIME trees and high part counts exhausting CPU/RAM.
- Extremely long text stalling parsers or search indexes.
- **cid:** paths or remote URLs improperly formatted or normalized.

An inbound service should:

1. Cap message size before downloading when supported by the protocol/API.
2. Limit part count, MIME depth, and total decoded bytes.
3. Verify file types using multiple signals, not just extension/Content-Type.
4. Scan for malware or quarantine files according to policy.
5. Never automatically fetch remote URLs while parsing HTML.
6. Sanitize HTML before rendering in a web UI.
7. Store files under system-generated object keys, never using raw filenames as paths.
8. Record checksums, source, and tenant scope to support auditing.
9. Never log raw emails or attachments in standard error logs.

**Reading email over IMAP/POP3 does not make its content trustworthy.** TLS only protects the connection to the mailbox server; it does not prove that every message in the mailbox is safe or legitimate.

## 37. Handling Bounces/DSNs Received via IMAP or POP3

A Spring Mail application can send email over SMTP and receive **Delivery Status Notifications (DSNs)** in a dedicated bounce mailbox.

Example:

~~~text
Outbound:
  Spring -> SMTP provider
  MAIL FROM:<bounces@bounces.example.com>
  RCPT TO:<customer@recipient.example>

Later:
  Receiving server cannot deliver
       |
       v
  DSN -> bounces@bounces.example.com
       |
       v
  IMAP/POP3 inbound consumer
       |
       v
  DSN parser -> notification outcome
~~~

A DSN may have the structure:

~~~text
multipart/report; report-type=delivery-status
  |
  +-- text/plain
  +-- message/delivery-status
  +-- message/rfc822-headers (optional)
~~~

Inside the **message/delivery-status** part, fields may appear such as:

~~~text
Final-Recipient: rfc822; customer@recipient.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Not every DSN includes all fields, and not every delivery failure generates a DSN. Providers may send **webhooks** instead of bounce emails to a mailbox.

### Principles for Handling Inbound Bounces

- Correlate to the **notification/recipient** using a provider ID, VERP token, or reliable metadata.
- Do not suppress a recipient merely because the text body contains "User unknown".
- Classify hard/soft/policy rejections by enhanced status code and event source.
- Protect against backscatter and forged bounces.
- Treat DSN reports as external inputs; validate plausibility before updating status.
- Maintain idempotency because mail servers or pollers may re-deliver the same event.

If the ESP provides a reliable and comprehensive webhook, you may not need a separate IMAP/POP3 inbox to collect bounces. The choice depends on provider capabilities and storage/reconciliation requirements.

## 38. Handling Replies: In-Reply-To and References

A common mail-receiving problem is matching a recipient's reply with a previously sent email.

Example original message:

~~~text
Message-ID: <ticket-123@support.example.com>
From: support@example.com
To: customer@example.net
Subject: [TICKET-123] We have received your request
~~~

The reply email may contain:

~~~text
From: customer@example.net
To: support@example.com
In-Reply-To: <ticket-123@support.example.com>
References: <ticket-123@support.example.com>
Subject: Re: [TICKET-123] We have received your request
~~~

The application can use **In-Reply-To** and **References** to support threading/correlation, but:

- These headers can be missing or altered by email clients.
- The Subject can be edited or forwarded.
- Message-ID is not proof of authenticated identity.
- A conversation may involve multiple recipients, aliases, or forwarders.

Use a **ticket ID/opaque correlation token** and verify that the sender is authorized to update the ticket before accepting content. Never trust a string in the Subject alone as sufficient to write information into someone else's record.

### Do Not Use Message-ID as a System-Wide Unique Key

If two mailboxes receive a message with the same Message-ID, they may represent two distinct inbound events by tenant or workflow. Ingestion identity should remain mailbox-scoped; business correlation happens in a downstream step.

## 39. IMAP Flags, Move, and Expunge

IMAP can support actions such as:

~~~text
INBOX / UID 400
   |
   +-- Set \\Seen
   |
   +-- Add keyword/flag (if supported by server)
   |
   +-- Copy/move to Processed
   |
   +-- Mark \\Deleted
   |
   +-- Expunge
~~~

These operations **mutate the mailbox server**, potentially affecting other users or clients. Therefore:

- By default, inbound automation should use `READ_ONLY` if it only needs to fetch content.
- If marking/moving is required, ensure appropriate account/permissions are used.
- Only change server state after the message has been durably recorded according to policy.
- Moving a message to a new folder can change its UID/folder identity.
- Expunge can affect multiple messages already marked Deleted in the same folder.
- Avoid expunging an entire folder in a routine that does not understand other clients' states.

### Do Not Turn the Mailbox into the Sole State Database

IMAP flags are helpful for client-level coordination, but insufficient for complex business states like "invoice verified", "ticket assigned to team", or "document awaiting retry". Manage those states in your application database.

## 40. One Mailbox, Multiple Workers: Handling Contention

Suppose two pods poll the same IMAP INBOX simultaneously:

~~~text
Pod A: discovers UID 200
Pod B: discovers UID 200

Pod A: creates ticket #101
Pod B: creates ticket #102
~~~

Without a unique key/claim, one email can trigger two side effects.

Strategies:

**A. Single active mailbox poller**

- Only one worker reads a mailbox at a time.
- Uses a distributed lease/leader election when running multiple instances.
- Easier to preserve ordering/checkpoints.
- Needs failover if the worker dies.

**B. Multiple pollers with a deduplication database**

- Multiple workers may see the same UID.
- Uses a unique key on the inbox table so only one worker is allowed to ingest.
- Business workers read from the deduplicated queue/outbox.
- Must avoid opening too many mailbox connections.

**C. Sharding by mailbox/tenant**

- Mailbox A is handled by partition 1, mailbox B by partition 2.
- Scales with the number of mailboxes without contention on a single folder.
- Needs rebalancing management when instances scale.

When using a **lease**, implement TTL, heartbeats, and an ownership/fencing token so a stale worker cannot overwrite the checkpoint after the lease has moved to a new worker.

**Do not use the Seen flag as a distributed lock**; two clients can fetch simultaneously before the flag is updated, and humans can also alter message state.

## 41. Multi-Tenant Mailbox Isolation

In SaaS, each tenant may own its own integrated mailbox:

~~~text
Tenant A -> support-a@tenant-a.example -> IMAPS account A
Tenant B -> support-b@tenant-b.example -> IMAPS account B
Tenant C -> invoices@tenant-c.example  -> POP3S account C
~~~

What needs to be isolated:

| Component | Rule |
|---|---|
| Tenant identity | Authenticated and stored alongside mailbox configuration |
| Mailbox credentials | Never mix up accounts/secrets across tenants |
| Checkpoint | Keyed by tenant + mailbox + folder + UIDVALIDITY/UID |
| Inbox records | Accessible only by the owning tenant |
| Attachment storage | Object keys and access permissions scoped per tenant |
| Parser policy | Byte/file-type limits per tenant policy |
| Worker quota | One tenant cannot exhaust all connections/poll slots |
| Delivery/bounce events | Correlated to the right tenant and original notification |
| Logs/metrics | Never expose another tenant's addresses/Subject/Message-ID |

When multiple mailboxes share a provider, check **connections per account**, **request rate**, **API quota**, and any access policies imposed by the provider.

Do not open one IMAP IDLE connection per folder for tens of thousands of tenants if the infrastructure/provider cannot support that connection count. You can group mailboxes, cap concurrency, use polling for low-traffic mailboxes, or use the provider's official webhook/API when available.

## 42. Authentication Policies: Passwords, App Passwords, and OAuth2

Not every mail provider permits traditional username/password authentication.

Options:

- **App passwords** issued for the application when supported by the provider.
- **OAuth2 access tokens** with the appropriate SASL mechanism, commonly called **XOAUTH2** in many mail systems.
- **Internal credentials** for an organization's own mail server, with TLS and least privilege.
- **Provider APIs** instead of IMAP/POP3 if the provider favors API-based integration.

Do not equate **"Spring has a password property"** with **"the provider allows basic auth"**. Actual authentication depends on the server and tenant policy.

### OAuth2 Requires More Than Just a Token String

When using access tokens:

1. Obtain the appropriate scope/permissions for reading mailboxes.
2. Have a mechanism to issue and refresh tokens before expiration.
3. Store tokens/refresh tokens in protected secret storage.
4. Pass tokens via the SASL mechanism supported by the provider/Jakarta Mail implementation.
5. Handle revoked tokens, disconnected tenants, or administrator permission changes.
6. Avoid logging SASL exchanges and tokens.

Do not embed an access token in a mailbox URL or exception logs. When the server returns authentication failed, do not retry in a tight loop with an expired token without refreshing or verifying permissions.

## 43. TLS and Inbound Server Verification

TLS protects the connection from the application to the IMAP/POP3 server, including credentials and downloaded email content. Configuration items to care about:

- Official provider hostname.
- Correct port and TLS mode.
- Certificate chain signed by a trusted CA.
- Hostname verification against the server certificate.
- Protocol versions/ciphers permitted by the organization.
- Finite connect/read/write timeouts.
- JDK/container truststore.

IMAPS example:

~~~properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=10000
mail.imaps.writetimeout=10000
mail.imaps.ssl.checkserveridentity=true
~~~

POP3S example:

~~~properties
mail.pop3s.connectiontimeout=5000
mail.pop3s.timeout=10000
mail.pop3s.writetimeout=10000
mail.pop3s.ssl.checkserveridentity=true
~~~

Timeouts are in milliseconds and illustrative only. When using **getStore("imap")** with STARTTLS or **getStore("pop3")** with STLS, the prefixes are **mail.imap** and **mail.pop3** respectively.

### Common Errors

| Symptom | Possible Cause |
|---|---|
| Connection refused | Wrong host/port, listener not running, firewall |
| Connect timeout | Routing/egress/network/provider outage |
| SSLHandshakeException | Wrong TLS mode, CA, hostname, or protocol |
| PKIX path building failed | Truststore does not trust the server's chain |
| AuthenticationFailedException | Credentials/token/scope/account policy |
| Read timeout | Slow server or network, stalled connection |
| Folder not found | Wrong folder name or access permissions |
| Folder closed | Session dropped or object used after closing |

Do not disable TLS to get past `AuthenticationFailedException`. If a certificate error occurs, fix the trust chain/hostname or endpoint—never configure trusting all certificates.

## 44. Polling Limits and Efficient Data Reading

A multi-year mailbox can contain millions of messages. If every run does:

~~~java
Message[] all = inbox.getMessages();

for (Message message : all) {
    // Read full body and attachments...
}
~~~

the application can suffer:

- High memory consumption holding message lists/objects.
- Excessive IMAP round-trips fetching headers.
- High bandwidth downloading unnecessary attachments.
- Long folder-open durations.
- Provider rate/quota throttling.
- Workers falling behind on new mail while re-scanning old messages.

Efficient design:

1. Use UID/UIDL checkpoints to avoid scanning the entire mailbox.
2. Define a **batch size** by message count or total bytes.
3. Fetch **metadata/headers** first and download full MIME only when needed.
4. Use an appropriate **FetchProfile** to reduce round-trips when supported by the provider.
5. Limit the number of mailboxes/folders polled concurrently.
6. Never hold a database transaction open while waiting on IMAP/POP3.
7. Configure timeouts and a reconnect policy.
8. Measure queue latency and mailbox scan duration to pinpoint bottlenecks.

### FetchProfile Example

~~~java
import jakarta.mail.FetchProfile;
import jakarta.mail.Folder;
import jakarta.mail.Message;

FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);

Message[] batch = inbox.getMessages(start, end);
inbox.fetch(batch, profile);

for (Message message : batch) {
    // Read appropriate metadata without necessarily downloading attachments.
}
~~~

The snippet assumes **inbox** is open and **start/end** have been validated to lie within the valid message sequence range. This optimizes metadata fetching; it does not solve checkpointing or exactly-once on its own.

With IMAP, UID ranges and `FetchProfile` can be used appropriately, though optimization depends on the server/provider; measure in practice before assuming a batch FETCH is always faster.

## 45. Retries, Dead-Lettering, and Quarantine

Not every error should be retried the same way:

| Error | Typically Appropriate Handling |
|---|---|
| Temporary DNS/network timeout | Retry connection with backoff |
| IMAP/POP3 server closes session | Reconnect and re-sync from checkpoint |
| Expired credentials/token | Refresh/re-authorize; avoid hot-loop retries |
| Folder does not exist | Alert on configuration; pause polling that folder |
| Malformed MIME | Quarantine and store diagnostic metadata |
| Email exceeds size policy | Quarantine/reject according to policy |
| Malicious attachment | Quarantine; do not pass to business worker |
| Database temporarily unavailable | Do not mark/delete; retry inbox persistence |
| Downstream business API error | Retry from inbox database; no need to re-fetch email |
| Untrusted sender identity | Route to review/quarantine instead of executing commands |

### Why Must You Have Dead-Letter/Quarantine?

If a malformed email always causes the poller to throw an exception, the entire mailbox can get stuck on the same message and never reach subsequent emails.

One approach:

~~~text
Fetch UID 100 -> OK -> PERSISTED
Fetch UID 101 -> MIME malformed
    |
    +-- Save identity and error to quarantine record
    +-- Save raw MIME if permitted and within limits
    +-- Flag for investigation
    |
Fetch UID 102 -> OK -> PERSISTED
~~~

With this design, **skipping UID 101 on the next poll** is safe only because the application durably preserved the processing/quarantine record. Never simply catch the exception and advance `lastUID` past 101 without leaving a trace.

### Retrying Does Not Mean Re-Downloading from the Server

Once the raw EML is persisted, business retries should process from the stored copy. This reduces load on the mail server and avoids issues if the message is deleted from the mailbox between attempts.

## 46. Observability and Alerting for Inbound Mail

An email-receiving pipeline needs different metrics from a sending pipeline:

| Logical Metric | Meaning |
|---|---|
| **mail_inbound_poll_total** | Poll attempts by account/protocol/result |
| **mail_inbound_poll_duration** | Duration of a single poll |
| **mail_inbound_discovered_total** | Number of message identities discovered |
| **mail_inbound_persisted_total** | Number of unique inbox items persisted successfully |
| **mail_inbound_duplicate_total** | Number of messages already present in the inbox store |
| **mail_inbound_parse_failed_total** | Number of messages that failed parsing |
| **mail_inbound_quarantined_total** | Number of messages moved to quarantine |
| **mail_inbound_processing_failed_total** | Business processing failures |
| **mail_inbound_checkpoint_lag** | Lag/UID lag as defined by the system |
| **mail_inbound_queue_oldest_age_seconds** | Age of the oldest unprocessed item |
| **mail_inbound_connection_failures_total** | DNS/TCP/TLS/AUTH errors |

Some metrics should be split by **protocol=imap|pop3**, **result**, and **error_category**.

**Do not put email addresses, Subjects, raw Message-IDs, or individual message UIDs into Prometheus labels** if they create high cardinality or expose PII. For large tenant/account counts, consider using only a bounded **mailbox group/tier** in metrics, keeping lookup details in access-controlled databases/logs.

### Three Useful Alert Categories

**A. No new emails received when traffic is expected.**

Do not rely solely on "0 mails in 10 minutes", because the mailbox may genuinely have no mail. Maintain heartbeat/poll liveness and correlate with upstream signals when available.

**B. Rising inbox backlog/oldest age.**

Messages are persisted, but business workers cannot keep up, or the poller is still connecting without successfully persisting.

**C. Spikes in AUTH/TLS/parse errors.**

Separate account configuration errors, mail server errors, and invalid email payloads.

If IMAP IDLE disconnects repeatedly, monitor reconnect counts and time since last successful sync, not merely notification counts.

## 47. Runbook When the Application Does Not Receive Mail

A diagnostic sequence can follow this order:

1. **Are there actually emails in the mailbox?** Verify via an authorized client/admin console.
2. **Is it the right account/folder?** INBOX may differ from a folder into which messages are auto-filtered.
3. **Do DNS and TCP to host:port** work from the exact container/VM running the application?
4. **Is the TLS mode right?** IMAPS 993/POP3S 995 or STARTTLS/STLS per provider.
5. **Are credentials/tokens and scopes** still valid?
6. **Have provider quotas/rates/concurrent connections** been exceeded?
7. **Is the poller/IDLE listener** running, connected, and able to reconnect?
8. **Is the UIDVALIDITY/UIDL checkpoint** valid or stale?
9. **Are search filters/Seen logic** accidentally excluding messages?
10. **Is inbox persistence** succeeding, or are the DB/object storage failing?
11. **Are processing workers** backed up in a queue or dead-lettered?
12. **Do logs/metrics** show the message was received but placed in `QUARANTINED`?

If the server returns "folder not found", increasing network timeouts will not help. If the mailbox has messages but the UID checkpoint exceeds current UIDs because UIDVALIDITY changed, re-sync rather than randomly deleting data.

### Runbook for Duplicate Receipts

Check:

- Is the same email being re-fetched after restarts/reconnects?
- Are multiple active pollers sharing the same mailbox?
- Does the inbox unique key properly include account/folder/UIDVALIDITY?
- Is POP3 UIDL stable?
- Was a message copied/moved to a new folder and processed again?
- Do events/attachments/business actions have their own idempotency keys?
- Are the messages genuinely two identical emails sent twice by the sender?

Do not "fix" duplicate receipts by deleting all read emails if the business still needs retention or reconciliation.

## 48. Testing IMAP/POP3 with a Test Mail Server

In Spring, one integration-testing approach is starting an **SMTP + IMAP/POP3 test server** (for example, a Jakarta Mail-compatible GreenMail version) and then:

~~~text
JUnit / Testcontainers
        |
        +-- Start test SMTP + IMAP/POP3 server
        |
        +-- Submit test email to mailbox
        |
        +-- Call inbound poller/receiver
        |
        +-- Assert inbox DB / captured payload
        |
        +-- Assert attachment/text extraction
        |
        +-- Simulate reconnect/restart and poll again
        |
        +-- Assert no duplicate business action
        |
        +-- Stop test server and clean resources
~~~

Recommended test cases:

| Case | Expected Outcome |
|---|---|
| Empty INBOX | Poll succeeds without error and creates no inbox item |
| Single text/plain mail | Reads subject/from/body accurately |
| Multipart alternative | Chooses plain text/HTML per policy |
| HTML + CID image + PDF | Classifies inline/attachment properly |
| Two consecutive polls on same mailbox | Creates no duplicate inbox/business record |
| Process crash after DB commit | Re-polls but deduplication succeeds |
| Process crash before DB commit | Message is re-discovered and persisted |
| UIDVALIDITY changes | Does not misuse the old UID checkpoint |
| POP3 UIDL present | Identifies messages across sessions |
| Server disconnects mid-fetch | Retry/reconnect does not mis-mark |
| Malformed MIME | Quarantined; does not block subsequent messages |
| Attachment exceeds size limit | Blocked/quarantined per policy |
| Spoofed From email | Does not run sensitive operations based solely on header |
| Two different tenant mailboxes | Does not mix content/checkpoints |
| IMAP Seen changed by another client | App still relies on its own checkpoint |
| Wrong Auth/TLS | Does not fall back to plaintext or log secrets |

Never send test emails to real users. Use test accounts and domains; configure local servers, dynamic ports, or container isolation so parallel tests do not collide.

### Why Are Unit Tests with Mocks Insufficient?

Unit tests can prove a service calls a receiver or parser, but cannot prove:

- The IMAP/POP3 server returns messages as expected.
- UID/UIDVALIDITY/UIDL are read properly from the server.
- Flags and deletion semantics behave correctly.
- Reconnect/timeout and session lifecycles are handled properly.
- MIME serialized over transport is parsed properly.

Use **unit tests for policy** and **integration tests for protocol/storage behavior**. There is no need to run the entire suite against an external Internet mail server.

## 49. Three Reference Architectures by Problem

### A. Support Mailbox: IMAP and Ticket Processing

~~~text
Customer replies
       |
       v
support@company.example
       |
       v
IMAP (IDLE + periodic UID reconciliation)
       |
       v
Inbox DB / raw EML archive
       |
       v
Ticket correlation & authorization
       |
       v
Ticket event + attachment scan
       |
       v
Agent UI
~~~

Why choose IMAP:

- Multiple agents may need to view the mailbox on the server.
- Folders and flags are available for mail organization.
- IDLE reduces latency, while periodic UID reconciliation guards against disconnects.
- UID+UIDVALIDITY handle ingestion deduplication.

Watch out: **do not use Seen as ticket-completed status**, do not trust `From` to let anyone edit a ticket, and do not render unsanitized HTML in the agent UI.

### B. Document-Collection Mailbox: POP3 and Document Archive

~~~text
Partner sends invoices
        |
        v
inbound-invoices@company.example
        |
        v
POP3S scheduled retrieval
        |
        v
UIDL dedup + durable EML storage
        |
        v
Attachment quarantine / antivirus
        |
        v
Document recognition
        |
        v
Review + accounting system
~~~

Why POP3 may suffice:

- Only a single integration consumer.
- No need for multiple folders or Seen status.
- After downloading, the application maintains its own data store as the source of truth.

Watch out: without stable UIDL, use an appropriate fingerprint/deduplication mechanism; never delete messages from the server before durable persistence.

### C. Bounce Mailbox: IMAP or POP3 Purely as an Ingestion Gateway

~~~text
SMTP MAIL FROM -> bounce mailbox
              |
              v
       IMAP/POP3 fetch
              |
              v
       DSN MIME parser
              |
              v
  Validate + correlate notification
              |
              v
      Delivery state / suppression
~~~

Why avoid forcing a more complex protocol:

- The main value lies in **parsing DSNs accurately, verifying the source, and correlating**, not in folder operations.
- If the provider offers authenticated webhooks, choose webhooks instead of building a receiver for a bounce mailbox.

## 50. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "Spring Mail has a default JavaMailReceiver like JavaMailSender" | Receiving mail usually uses Jakarta Mail or Spring Integration Mail |
| "SMTP is also an Inbox-reading protocol" | SMTP is for sending/relaying; IMAP/POP3 are for accessing mailboxes |
| "IMAP always pushes, POP3 always polls" | IMAP can also poll; IDLE is only a change-notification mechanism |
| "IMAP IDLE guarantees zero missed mail" | Reconnection and UID reconciliation are still needed after interruptions |
| "Sequence numbers are durable message IDs" | They can shift after expunge; use UID+UIDVALIDITY |
| "A standalone UID is globally unique" | UID is scoped by folder/mailbox and UIDVALIDITY |
| "A Seen message means business processing succeeded" | Seen is a mailbox flag, not a DB transaction |
| "POP3 always deletes emails on download" | Deletion depends on commands, client, and session policy |
| "POP3 message number is a stable key" | Ordering can shift; use UIDL when supported |
| "The Message-ID header cannot be spoofed or duplicated" | It can be missing, forged, or non-unique |
| "Storing UID guarantees exactly-once" | Crashes, duplicate workers, and business side effects still happen |
| "An email only has a single String body" | It can be nested multipart/alternative/related/mixed |
| "MIME Content-Type always reflects actual bytes" | Header is sender-declared and can be inaccurate |
| "Plain text and HTML parts should be concatenated" | In alternative, they are alternate representations |
| "From proves a trustworthy sender" | From can be spoofed; an independent verification policy is needed |
| "TLS guarantees the email content inside is safe" | TLS protects transport, not malware/phishing checks |
| "Once fetched, mark Seen/delete immediately" | Only mutate server state after persisting per policy |
| "Multiple pods on one mailbox automatically share work" | They can read duplicates; use leases/dedup/sharding |
| "Increasing polling rate always improves throughput" | It can increase provider throttling and cost |
| "Mock receivers suffice for integration tests" | They do not test real protocol, UID, session, flags, and parser behavior |
| "No new mail means the poller is healthy" | The poller may have stopped; monitor heartbeats and liveness |

## 51. Checklist for Implementing Inbound Email in Spring

**Protocol and provider selection**

1. Does the mailbox need folders, flags, search, and multiple clients?
2. Is near real-time latency needed, or is polling every few minutes enough?
3. Does the provider support IMAP/POP3, IDLE, or webhooks/APIs?
4. What connection limits, quotas, and authentication policies exist?
5. Are TLS mode, hostname verification, and credential rotation defined?

**Identification and persistence**

6. Are mailbox/account and tenant identities reliable?
7. For IMAP, does the checkpoint include **folder + UIDVALIDITY + UID**?
8. For POP3, is UIDL supported and verified to be stable?
9. Is there a unique key preventing duplicate ingestion?
10. Are messages or raw EMLs persisted durably before marking/deleting?
11. Is discovery/persistence separated from business processing?
12. Are per-message retries, quarantine, and dead-lettering implemented?

**MIME and security**

13. Does the parser handle multipart, charsets, text alternatives, and attachments?
14. Are limits enforced on size, depth, part count, and decoded bytes?
15. Is HTML sanitized before rendering?
16. Are attachments checked for file type and malware per policy?
17. Are From, Reply-To, and Message-ID prevented from being mistaken for identity proof?
18. Is tenant-level authorization enforced on mailboxes, storage, and business events?
19. Are credentials/raw MIME/PII kept out of logs and metric labels?

**Performance and recovery**

20. Are batch limits and an appropriate FetchProfile configured?
21. Are server disconnects/reconnects and UID reconciliation handled?
22. Are concurrent polling/IDLE connections capped?
23. Are duplicates prevented when running multiple instances?
24. Are mailbox lag, inbox backlog, and poll failures measured?
25. If a worker/DB crashes between fetch and persist, is the message safely re-processed?
26. When server-side flags/folders change, do checkpoints remain valid?
27. Has mailbox migration causing UIDVALIDITY changes been tested?

**Operations**

28. Are there dedicated runbooks for auth/TLS, missing folders, malformed MIME, and server outages?
29. Is there an approved message retention/deletion policy?
30. Are integration tests run against a test mail server rather than production mailboxes?

This checklist is not a mandate to build every feature into a small application. It helps establish **safety boundaries** before operating a mail-receiving pipeline that affects business data.

## 52. Takeaways

**IMAP and POP3** both allow an application to access emails stored on a mail server, but they serve different models.

- **IMAP** fits when server-side mailbox management, folders, flags, UIDs, and optional near real-time notifications via IDLE are needed. Checkpoints must be tied to **UIDVALIDITY**, and reading the Seen flag does not replace business processing state.
- **POP3** fits simple download flows from a maildrop for the application to store and process separately. Use **UIDL** when supported by the server/provider; never use message ordinal numbers as durable identifiers. Server deletion requires an explicit policy.
- In **Spring Framework Mail**, **JavaMailSender** handles SMTP sending. For receiving mail, use **Jakarta Mail Session/Store/Folder/Message** directly or **Spring Integration Mail** with inbound adapters and polling/IDLE flows.
- **Both IMAP IDLE and polling require catch-up synchronization** after network failures or restarts. Do not rely on a single event or flag to assert that a message was processed.
- A reliable architecture should **ingest at-least-once, persist the inbox durably, deduplicate with proper identity, and process business logic idempotently**.
- **MIME, HTML, and attachments are untrusted data**. Enforce size and depth limits, sanitize, scan files, and maintain tenant authorization.
- Monitor **poll liveness, UID/checkpoint lag, duplicate counts, parse failures, quarantine, and processing backlog**, not merely message counts received.

**The essence of mail receiving is not simply "reading a Message from INBOX", but bringing data from the mail server into the Spring system with accurate state, zero lost messages, controlled deduplication, and without letting external content cross security boundaries.**






