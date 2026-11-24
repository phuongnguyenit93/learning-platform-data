# Session and Connections for Reading Mailboxes

In **Spring Framework Mail**, many examples focus on `JavaMailSender` for **sending emails**. However, an application may also need to **read incoming emails** from a mailbox: receiving customer replies, collecting error report emails, processing requests sent to `support@...`, or ingesting data from a shared mailbox. On the reading side, the central component is not `JavaMailSender`, but **Jakarta Mail** APIs such as `Session`, `Store`, `Folder`, `Message`, and **IMAP/POP3** protocol providers.

A common design mistake is treating `Session` as an already-open TCP connection. In reality, `Session` is **Jakarta Mail's configuration context**; `Store` represents the connection to the mail store, `Folder` represents a folder in the mailbox, and `Message` represents an email retrieved through a folder. Understanding this boundary properly helps manage resources, authenticate securely, read MIME accurately, avoid accidentally marking messages as read or deleting them, and handle disconnects during synchronization.

This lesson walks through the full lifecycle of **creating a Session → connecting a Store → opening a Folder → retrieving Messages → processing → closing Folder/Store**, compares IMAP and POP3, configures IMAPS/STARTTLS, manages UIDs/flags, implements polling or IDLE, builds testable Spring services, and designs a production-safe mailbox-reading workflow.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `Session`, `Store`, `Folder`, `Message`, `UIDFolder`, and `Transport`.
- Explain why `JavaMailSender` is generally intended for **outbound SMTP**, not as a mailbox-reading API.
- Choose IMAP or POP3 based on application requirements, not merely on connection ports.
- Create a Jakarta Mail `Session` with protocol-specific properties for reading mail.
- Connect via IMAPS (implicit TLS) or mandatory IMAP + STARTTLS, verifying certificates and hostnames.
- Open folders in `READ_ONLY` or `READ_WRITE` mode and understand the impact on mail flags.
- Read message lists using `getMessageCount()`, `getMessages()`, and `FetchProfile`.
- Understand the limitations of message sequence numbers and the role of IMAP UID/UIDVALIDITY.
- Read plain-text/HTML parts and metadata of a `MimeMessage` following the MIME tree.
- Design polling, cursors, idempotency, and handling for dropped connections.
- Close resources properly and avoid holding `Message` references after the folder is closed.
- Test using sandbox mailboxes rather than relying on real personal accounts.

## 2. How Does Reading a Mailbox Differ from Sending via SMTP?

```text
                     SPRING APPLICATION
                            |
           +----------------+----------------+
           |                                 |
           v                                 v
   SEND EMAIL (OUTBOUND)              READ EMAIL (INBOUND)
           |                                 |
    JavaMailSender                       Jakarta Mail
           |                                 |
    MimeMessageHelper                       Session
           |                                 |
    SMTP Transport                          Store
           |                                 |
    SMTP relay/provider                      Folder
           |                                 |
   Recipient mail server                    Message
```

| Need | Commonly Used Interface | Protocol |
|---|---|---|
| Send order confirmations | `JavaMailSender` / `JavaMailSenderImpl` | SMTP submission |
| Send HTML email, attachments | `MimeMessageHelper` and `JavaMailSender` | SMTP |
| List messages in Inbox | `Store` + `Folder` | IMAP, sometimes POP3 |
| Inspect unread/seen status | `Folder` + `Flags` | Primarily IMAP |
| Sync new messages with durable IDs | `UIDFolder` when supported by server | IMAP |
| Fetch new mail via change notifications | IMAP IDLE or polling | IMAP |
| Simple mail download from one mailbox | POP3 `Store`/`Folder` | POP3 |
| Hosted mailbox services like Gmail/Graph API | Provider-specific API | HTTPS; not standard Jakarta Mail protocol |

**`JavaMailSender` does not provide a `readInbox()` method by default.** Although `JavaMailSenderImpl` also uses a Jakarta Mail `Session` for sending, a mailbox-reading application should have separate configuration and services to avoid mixing outbound SMTP credentials with inbound IMAP credentials.

### 2.1. Do Not Confuse SMTP, IMAP, and POP3

- **SMTP:** relays or submits outgoing emails.
- **IMAP:** retrieves and synchronizes messages on the server, supporting folders and flags; usually suited for applications needing mailbox state.
- **POP3:** primarily downloads messages from a mailbox, with fewer synchronization and folder features than IMAP.

One mailbox provider may support SMTP, IMAP, and POP3 simultaneously, but the **host, port, TLS mode, authentication mechanism, and access permissions** may differ.

## 3. Jakarta Mail Model: Session → Store → Folder → Message

```text
Session (configuration and provider registry)
   |
   +--> Properties: host, TLS, timeout, auth mechanism
   |
   v
Store (IMAP/POP3 provider + connection)
   |
   +--> connect(host, port, user, credential)
   |
   v
Folder ("INBOX", "Sent", or another folder)
   |
   +--> open(READ_ONLY / READ_WRITE)
   |
   +--> getMessageCount()
   +--> getMessages(start, end)
   +--> search(SearchTerm)
   |
   v
Message / MimeMessage
   |
   +--> From / To / Subject / Date
   +--> Flags / UID
   +--> Content-Type / Multipart / BodyPart
   +--> Attachment / inline resources
```

### 3.1. What Is Session?

`jakarta.mail.Session` holds properties, authenticators, and the environment for creating a `Store` or `Transport`. It **does not automatically open a TCP socket** simply because you call:

```java
Session session = Session.getInstance(properties);
```

A `Session` can be created and reused across multiple synchronization cycles when configuration does not change. Avoid mutating `Properties` after the session has been shared across threads; it is better to treat the initialized configuration as an immutable snapshot.

### 3.2. What Is Store?

`Store` is the abstraction of a **message store**. A `Store` is bound to a protocol provider, such as `imap`, `imaps`, `pop3`, or `pop3s`. When `connect(...)` is called, the provider establishes the network connection and authenticates per protocol.

A `Store` manages network resources and connection state, so `store.close()` must be called when finished.

### 3.3. What Is Folder?

`Folder` represents a mailbox directory. On IMAP there is typically `INBOX` and other folders; some providers use specific namespaces/hierarchies. A folder must be opened before reading content or manipulating messages via APIs that require an open folder.

### 3.4. What Is Message?

`Message` represents an email read from a folder: headers, body, flags, and metadata. Many providers **lazy-load** content when the application accesses `getContent()`, so the `Message` object may still depend on the open `Store`/`Folder`.

Do not place a live `Message` from an IMAP session into a queue or return it from a controller and then close the connection. Always **extract required data into a DTO/snapshot** while the folder is still open.

### 3.5. Where Does Transport Fit?

`Transport` is for sending via SMTP or another transport provider, **not for reading an Inbox**. The fact that both `Store` and `Transport` are created from `Session` does not mean the two protocols share a connection or credentials.

## 4. Choosing IMAP vs. POP3

| Criterion | IMAP | POP3 |
|---|---|---|
| Multiple folders | Yes, provider-dependent | Usually no; mainly INBOX |
| Syncing read/unread and flags | Standard IMAP support | Very limited, lacks equivalent model |
| UID for tracking across polls | IMAP UID with UIDVALIDITY | POP3 UIDL if server supports it |
| Server-side search | Has commands and matching SearchTerm | Limited |
| Concurrent multi-client access | Better suited | Less suitable when state sync is needed |
| Near real-time change awareness | IMAP IDLE on supporting servers | Usually polling |
| Simple mail download | Yes | Yes |
| Deleting mail | Via flags/EXPUNGE semantics | Via POP3 DELE/QUIT semantics |
| Multi-agent support mailbox apps | Usually preferred | Usually suboptimal |

**Practical recommendation:** If you need to synchronize an Inbox with state and avoid duplicate processing, **IMAP** is generally the better choice. If you only download mail from a simple single mailbox and the provider only offers POP3, add dedicated UIDL or fingerprint tracking, retention, and idempotency mechanisms.

Neither protocol replaces safe business data processing after downloading emails.

## 5. Common Ports and TLS Modes

| Protocol | Common Port | TLS Mode | JavaMail Store Name |
|---|---|---|---|
| IMAP | 143 | Plain IMAP + STARTTLS if server supports it | `imap` |
| IMAPS | 993 | Implicit TLS, starts immediately after TCP connect | `imaps` |
| POP3 | 110 | Plain POP3 + STLS/STARTTLS if server supports it | `pop3` |
| POP3S | 995 | Implicit TLS | `pop3s` |

These are common ports, **not a guarantee that every provider uses those exact ports**. Always check the mailbox service's official configuration documentation.

### 5.1. IMAPS vs. IMAP STARTTLS

Implicit TLS:

```text
Application                   IMAPS server :993
     |------ TCP connect ---------->|
     |====== TLS handshake ========|
     |      cert/hostname check     |
     |------ IMAP LOGIN/AUTH ------>|
     |------ SELECT INBOX --------->|
     |------ FETCH ---------------->|
```

STARTTLS:

```text
Application                    IMAP server :143
     |------ TCP connect ---------->|
     |<----- server greeting -------|
     |------ CAPABILITY ----------->|
     |------ STARTTLS ------------->|
     |====== TLS handshake ========|
     |      cert/hostname check     |
     |------ LOGIN/AUTH (TLS) ----->|
     |------ SELECT INBOX --------->|
```

In environments requiring mandatory encryption, never fall back to a non-TLS mailbox-reading session just to bypass handshake errors.

### 5.2. Reading Mailboxes Still Requires Verifying Server Identity

TLS is only useful if the application verifies:
- the certificate chain up to a trusted CA;
- that the connected hostname matches the certificate's SAN;
- that the certificate is not expired;
- appropriate protocol/ciphers;
- that the server is genuinely the intended trusted mailbox endpoint.

Never disable certificate validation such as `mail.imaps.ssl.trust=*` in production.

## 6. Configuring IMAPS via Jakarta Mail

Example using **IMAPS port 993** with username/password:

```java
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.Properties;

public class ImapsConnectionExample {

    public static void connect(
            String host,
            int port,
            String username,
            String credential) throws Exception {

        Properties props = new Properties();

        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.writetimeout", "10000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(host, port, username, credential);
            System.out.println("IMAPS connection established");
        } finally {
            if (store.isConnected()) {
                store.close();
            }
        }
    }
}
```

In this example:
- `Session.getInstance` only creates the context.
- `session.getStore("imaps")` selects the Store provider.
- `store.connect` initiates network/TLS/AUTH.
- `isConnected()` gives a current status signal, though the network can drop at any time.
- `close()` releases the connection when done.

**Never hardcode real usernames/passwords in source code.** In production, credentials must come from a secret manager or protected configuration.

### 6.1. Property Prefixes Must Match the Protocol

For `imaps`, socket timeouts are typically:

```properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=10000
mail.imaps.writetimeout=10000
mail.imaps.ssl.checkserveridentity=true
```

For `imap`, use `mail.imap.*`. For `pop3s`, use `mail.pop3s.*`.

If you write `mail.smtp.timeout` in an IMAP-reading service, that is an SMTP transport property and **does not control the IMAP socket**.

### 6.2. Timeouts and Resource Limits

- `connectiontimeout`: wait time for establishing the connection.
- `timeout`: socket read timeout limit.
- `writetimeout`: socket write timeout limit.
- They use **milliseconds** per the corresponding Jakarta Mail properties.

These timeouts **do not equal a total deadline for a single sync cycle**, because DNS, multiple FETCH commands, MIME parsing, attachments, and database operations also take time.

When a mailbox holds tens of thousands of messages, limit **the number of messages and bytes processed per batch**, rather than only increasing read timeouts.

### 6.3. Configuring TLS Protocols

When infrastructure has specific requirements, you can set:

```properties
mail.imaps.ssl.protocols=TLSv1.2 TLSv1.3
```

Version names depend on the Java runtime and server. Never enable TLS 1.0/1.1 or weak ciphers just to bypass errors; upgrade the server/provider instead when possible.

## 7. Configuring IMAP STARTTLS on Port 143

If the provider requires plain IMAP followed by TLS upgrade:

```java
Properties props = new Properties();

props.put("mail.store.protocol", "imap");
props.put("mail.imap.starttls.enable", "true");
props.put("mail.imap.starttls.required", "true");
props.put("mail.imap.ssl.checkserveridentity", "true");
props.put("mail.imap.connectiontimeout", "5000");
props.put("mail.imap.timeout", "10000");
props.put("mail.imap.writetimeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("imap");

try {
    store.connect(
        "imap.example.com",
        143,
        "reader@example.com",
        mailboxCredential
    );

    // Process mailbox only after connection and TLS are valid.
} finally {
    if (store.isConnected()) {
        store.close();
    }
}
```

`mailboxCredential` is a variable holding the credential supplied by the secure configuration layer, not a built-in Java placeholder literal.

Differences from IMAPS:
- The protocol is `imap`, not `imaps`.
- TLS begins **after the STARTTLS command**.
- `starttls.required=true` prevents continuing if the server does not enforce upgrading.
- `ssl.checkserveridentity=true` is still required.

Do not arbitrarily set `mail.imap.ssl.enable=true` on an endpoint that only supports STARTTLS; choose the TLS mode matching the server.

## 8. Connecting via POP3/POP3S

To download emails over POP3S port 995:

```java
Properties props = new Properties();

props.put("mail.store.protocol", "pop3s");
props.put("mail.pop3s.ssl.enable", "true");
props.put("mail.pop3s.ssl.checkserveridentity", "true");
props.put("mail.pop3s.connectiontimeout", "5000");
props.put("mail.pop3s.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("pop3s");

try {
    store.connect(
        "pop.example.com",
        995,
        "reader@example.com",
        mailboxCredential
    );

    Folder inbox = store.getFolder("INBOX");
    inbox.open(Folder.READ_ONLY);

    try {
        System.out.println(
            "Messages: " + inbox.getMessageCount()
        );
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
```

Requires importing `jakarta.mail.Folder`.

With POP3:
- Usually only `INBOX` exists.
- There is no folder/flag/UID model equivalent to IMAP.
- Message deletion has different semantics; avoid automatically marking `DELETED`.
- UIDL support varies by server; if tracking messages across polls is needed, verify the provider's exact capabilities.
- Do not choose POP3 if the problem requires folder synchronization and multi-client state.

## 9. Spring Boot Does Not Automatically Turn JavaMailSender into a Mailbox Reader

Common properties:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
```

are primarily used for **mail-sending auto-configuration**. To read an Inbox, design separate configuration:

```yaml
app:
  mailbox:
    host: imap.example.com
    port: 993
    protocol: imaps
    username: ${MAILBOX_USERNAME}
    password: ${MAILBOX_PASSWORD}
    folder: INBOX
    batch-size: 100
    poll-interval: 30s
```

This helps:
- avoid confusing the SMTP host with the IMAP host;
- separate mailbox-reading credentials from SMTP-sending credentials;
- separate timeouts, TLS mode, folder, and polling;
- toggle the mailbox consumer independently;
- control permissions per component.

`app.mailbox.*` is an **application-defined** namespace, not built-in Spring Boot properties that automatically create an IMAP reader.

### 9.1. ConfigurationProperties

Example configuration as a record:

```java
package com.example.mailbox;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mailbox")
public record MailboxProperties(
    String host,
    int port,
    String protocol,
    String username,
    String password,
    String folder,
    int batchSize,
    Duration pollInterval
) {}
```

From the metadata above, the application should validate:
- `protocol` is in the allowed set;
- `host` belongs to an administrator-approved endpoint;
- `port` is valid;
- `batchSize` is positive and bounded;
- `folder` is permitted for access;
- credentials are present or OAuth2 is configured per policy;
- `pollInterval` is not too small and causing excessive load;
- TLS and certificate validation are not disabled.

Never log the entire configuration record if it contains a password.

## 10. Basic Service to Open and Read an Inbox

The example below illustrates one polling cycle using an **IMAPS connection and a READ_ONLY Folder**. The goal is to understand the proper lifecycle and avoid holding resources after completion.

```java
package com.example.mailbox;

import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

public final class SimpleImapReader {

    private final String host;
    private final int port;
    private final String username;
    private final String password;

    public SimpleImapReader(
            String host,
            int port,
            String username,
            String password) {
        this.host = host;
        this.port = port;
        this.username = username;
        this.password = password;
    }

    public List<MailSummary> readLatest(int limit)
            throws Exception {

        if (limit < 1) {
            throw new IllegalArgumentException(
                "limit must be positive"
            );
        }

        Properties props = new Properties();
        props.put("mail.imaps.ssl.enable", "true");
        props.put("mail.imaps.ssl.checkserveridentity", "true");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");
        Folder inbox = null;

        try {
            store.connect(host, port, username, password);

            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_ONLY);

            int count = inbox.getMessageCount();
            if (count == 0) {
                return List.of();
            }

            int first = Math.max(1, count - limit + 1);
            Message[] messages =
                inbox.getMessages(first, count);

            List<MailSummary> result = new ArrayList<>();

            for (Message message : messages) {
                result.add(new MailSummary(
                    message.getMessageNumber(),
                    message.getSubject(),
                    message.getReceivedDate(),
                    message.getContentType()
                ));
            }

            return List.copyOf(result);
        } finally {
            try {
                if (inbox != null && inbox.isOpen()) {
                    inbox.close(false);
                }
            } finally {
                if (store.isConnected()) {
                    store.close();
                }
            }
        }
    }

    public record MailSummary(
        int messageNumber,
        String subject,
        java.util.Date receivedDate,
        String contentType
    ) {}
}
```

Key points:

1. `Session` makes no network calls when created.
2. `Store.connect` opens the connection and authenticates.
3. `Folder.open(READ_ONLY)` obtains read access to the folder.
4. `getMessageCount` provides the current message count.
5. `getMessages(first,count)` returns messages in a valid sequence number range.
6. Convert each message into a **snapshot DTO** while the folder is still open.
7. `close(false)` does not request expunging messages marked deleted.
8. `Store.close` releases network resources.

This is a **partial Inbox reading example**, not durable synchronization: `messageNumber` is only a sequence number while the folder is open and **should not be used as a long-term database key**.

### 10.1. What If Folder or Store.close Also Throws an Exception?

The nested `finally` ensures `Store` still attempts to close if closing `Folder` fails. In production, have a policy to record cleanup errors without masking the primary exception; you can use resource-management helpers with suppressed exceptions or controlled logging.

Never omit `close` just to keep code shorter.

## 11. How Do READ_ONLY and READ_WRITE Affect Behavior?

When opening a folder:

```java
folder.open(Folder.READ_ONLY);
```

the application requests read-only access. This is usually the right choice for an **ingestion worker** when processing and state are tracked in a separate database.

When updating flags is needed:

```java
folder.open(Folder.READ_WRITE);
```

Server/provider-supported actions such as marking `SEEN` or `DELETED` become available. `READ_WRITE` must be used cautiously because its effects can be observed by users and other clients.

### 11.1. Do Not Mark as Read Just to "Fetch Email"

Some body-reading methods can affect `SEEN` depending on the protocol, provider, and FETCH mode. Do not assume every `getContent()` call is completely non-mutating in every configuration.

For ingestion:
- open folders `READ_ONLY` when only reading is needed;
- track processing in a dedicated DB;
- verify `SEEN` behavior in integration tests against the actual provider;
- if `READ_WRITE` is required, enforce an explicit policy and update flags only after business data is durably persisted.

### 11.2. Common Flags

```java
import jakarta.mail.Flags;
import jakarta.mail.Message;

boolean seen = message.isSet(Flags.Flag.SEEN);
boolean deleted = message.isSet(Flags.Flag.DELETED);
boolean answered = message.isSet(Flags.Flag.ANSWERED);
```

Some IMAP servers also support user-defined flags/keywords. Do not assume all flags can be read/written identically across every provider.

### 11.3. Marking as Processed Does Not Mean Setting SEEN

`\Seen` is a mailbox display state for mail clients, **not a durable transactional ACK** confirming the application parsed the content, saved it to the database, and finished the business process.

If `SEEN` is used as the processed signal:
- a user may open the email before the worker reads it;
- another client may change the flag;
- the worker may set `SEEN` and crash before saving to the DB;
- mailbox state may be reset or messages moved.

It is much better to use **IMAP UID + idempotency data in the DB**, and only set `SEEN` for UX purposes after reliable processing.

## 12. Message Sequence Numbers Are Not Durable IDs

IMAP `messageNumber` is the message's position in the folder at access time.

Example:

```text
INBOX:
  sequence #1 -> Mail A
  sequence #2 -> Mail B
  sequence #3 -> Mail C
```

If Mail B is expunged, sequence numbers may be renumbered:

```text
INBOX:
  sequence #1 -> Mail A
  sequence #2 -> Mail C
```

If the application stores `lastMessageNumber=2` and treats any message with a higher number as new, it may miss or misprocess messages when messages are deleted or moved across folders.

**Do not use message sequence numbers as a durable sync cursor across connections.**

### 12.1. UID in IMAP

IMAP provides **UID** to identify messages more durably **within a single folder and a single UIDVALIDITY**. Jakarta Mail exposes this via `UIDFolder`:

```java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

if (folder instanceof UIDFolder uidFolder) {
    long uidValidity = uidFolder.getUIDValidity();

    Message[] messages =
        uidFolder.getMessagesByUID(1L, UIDFolder.LASTUID);

    for (Message message : messages) {
        long uid = uidFolder.getUID(message);

        System.out.println(
            "UIDVALIDITY=" + uidValidity + ", UID=" + uid
        );
    }
}
```

This snippet demonstrates the UID API, but fetching from UID 1 to the last UID on a large mailbox can return far too many messages. In production, **read in ranges and batches** based on a saved cursor, combined with size and count limits.

### 12.2. Durable Processing Key

A suitable identity for an email at an IMAP location:

```text
(mailbox_account_id, folder_id, uid_validity, uid)
```

Do not use UID alone because:
- a UID is only unique within one folder for a given UIDVALIDITY value;
- another mailbox account may use the same UID;
- UIDVALIDITY can change when the server rebuilds the folder;
- moving or copying a message to another folder can assign a different UID.

### 12.3. What If UIDVALIDITY Changes?

If the server returns a new `UIDVALIDITY`, the application must not continue using the old UID cursor as if it belonged to the same message set. It must switch to a policy-driven **resynchronization** process:
- detect that UIDVALIDITY changed;
- store a new folder generation;
- re-scan in batches;
- deduplicate at the business layer to minimize duplicate events;
- retain audit history.

Do not assume UIDs across two generations have the same meaning.

## 13. Message-ID Can Help, but Does Not Replace UID

The `Message-ID` header can help correlate a logical email:

```text
Message-ID: <example-123@mail.example>
```

However:
- some messages lack a Message-ID;
- some messages have duplicate Message-IDs due to misconfiguration or copying;
- the same message can be moved/copied between folders;
- Message-ID is not a unique key guaranteed by every mailbox server.

An ingestion pipeline can store all of:
- mailbox/folder/UIDVALIDITY/UID for synchronization;
- normalized Message-ID at a reasonable level;
- hashes or business correlation IDs when needed;
- processing status and source.

**Do not deduplicate all emails solely by Message-ID** if the goal requires handling messages sent separately to different accounts or separate copies.

## 14. FetchProfile Reduces Round Trips, but Does Not Download All Bodies

When listing many emails, accessing each property individually can cause many network requests depending on the provider. `FetchProfile` lets the provider know which fields to prefetch.

Example:

```java
import jakarta.mail.FetchProfile;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

Message[] page = folder.getMessages(first, last);

FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);
profile.add(FetchProfile.Item.CONTENT_INFO);
profile.add(UIDFolder.FetchProfileItem.UID);

folder.fetch(page, profile);
```

Prefetched fields can include:
- From/Subject/Date metadata;
- flags;
- content information;
- UID if supported by the provider.

**`FetchProfile` does not guarantee that the entire MIME body/attachments have been downloaded**, nor does it limit byte counts on its own. Read bodies only when needed and with a clear resource budget.

### 14.1. Avoid Scanning the Entire Mailbox Every Cycle

An unsuitable approach for a mailbox with hundreds of thousands of messages:

```java
Message[] all = folder.getMessages();
for (Message m : all) {
    process(m);
}
```

It can allocate a huge array, perform heavy network I/O, take a long time to read, and create memory pressure.

The proper approach:
- use a UID cursor;
- fetch a small batch by UID range;
- fetch only necessary headers first;
- enforce attachment/MIME body limits;
- cap the number of messages per poll;
- persist the checkpoint after each successfully processed record or batch.

### 14.2. SearchTerm Does Not Replace Durable IDs

You can filter on the server:

```java
import jakarta.mail.Flags;
import jakarta.mail.search.FlagTerm;

Message[] unseen = folder.search(
    new FlagTerm(
        new Flags(Flags.Flag.SEEN),
        false
    )
);
```

This is an example of finding messages **not marked SEEN**, not "not yet processed by the application". In multi-client mailboxes, SEEN changes independently of ingestion. Searching can be useful to narrow the message set, but cursors/idempotency still need a more durable mechanism.

## 15. Reading MIME Bodies: Plain Text, HTML, and Attachments

A received email is not necessarily a `String`:

```text
MimeMessage
   |
   +-- multipart/mixed
       |
       +-- multipart/alternative
       |    |
       |    +-- text/plain
       |    +-- text/html
       |
       +-- application/pdf (attachment)
```

`Message.getContent()` may return:
- `String` for a text body;
- `Multipart` for multipart content;
- `InputStream` or another object depending on MIME type/provider;
- sometimes a nested `Message` for `message/rfc822`.

Do not cast blindly:

```java
String body = (String) message.getContent();
```

because multipart emails will fail.

### 15.1. Basic MIME Content Extractor

```java
package com.example.mailbox;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.util.ArrayList;
import java.util.List;

public final class TextPartExtractor {

    private TextPartExtractor() {}

    public static List<String> collect(
            Part root,
            String mimeType) throws Exception {

        List<String> output = new ArrayList<>();
        visit(root, mimeType, output);
        return List.copyOf(output);
    }

    private static void visit(
            Part part,
            String mimeType,
            List<String> output) throws Exception {

        // Do not treat text attachments as the email body.
        String disposition = part.getDisposition();
        if (Part.ATTACHMENT.equalsIgnoreCase(disposition)) {
            return;
        }

        if (part.isMimeType(mimeType)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                output.add(text);
            }
            return;
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                visit(
                    multipart.getBodyPart(i),
                    mimeType,
                    output
                );
            }
        }
    }
}
```

Usage:

```java
List<String> plainTexts =
    TextPartExtractor.collect(message, "text/plain");

List<String> htmlTexts =
    TextPartExtractor.collect(message, "text/html");
```

This is an **illustrative MIME traversal example**, not a production parser for untrusted emails. Real systems must account for:
- deeply nested MIME and `message/rfc822`;
- `multipart/alternative`: choosing an appropriate representation instead of concatenating all;
- text attachments with missing or non-standard disposition;
- broken charsets or unusual content transfer encodings;
- limits on total bytes, part count, and depth;
- malicious HTML content and tracking URLs;
- stream lifecycles and zip bombs.

### 15.2. Prefer Plain Text When Business Logic Only Needs Text

If extracting ticket content:
1. Locate the appropriate `text/plain` body part.
2. If absent, convert HTML to plain text using a controlled parser.
3. Do not render HTML directly into an admin dashboard without sanitizing.
4. Be careful with quoted history, signatures, and forwarded messages.

Email HTML is **untrusted data**, even when arriving from an internal mailbox. Never treat `getContent()` as browser-safe output.

### 15.3. Do Not Trigger Network Calls When Parsing HTML

During parsing:
- do not automatically download images or stylesheets from URLs in the email;
- do not arbitrarily resolve `file:`, `http:`, or external entities;
- do not execute JavaScript;
- do not automatically open URLs containing tokens;
- do not embed raw HTML into web templates.

The goal is data extraction, not emulating a mail client with full active content.

## 16. Attachments Must Be Treated as Untrusted Data

A mailbox reader can receive PDFs, ZIPs, images, or files of unknown format. Apply:
- attachment count limits;
- per-attachment and whole-message size limits;
- file-type allowlists based on business needs;
- verification of MIME type and actual file contents;
- malware scanning/CDR according to policy;
- protection against path traversal and malicious filenames;
- storing files in a quarantine location before use;
- never executing or auto-opening attachments;
- encryption, retention, and access control.

`Part.getFileName()` comes from the email and is unsafe to concatenate directly into a filesystem path.

### 16.1. Bounded Stream Reading

Do not call `readAllBytes()` unconditionally on a very large attachment. When saving files:
- stream in chunks;
- count bytes;
- reject if limits are exceeded;
- assign a server-generated filename;
- store only metadata/scan results for downstream steps;
- ensure resources are closed.

For MIME containing nested attachments or compressed data, limits must also check decompressed size if archives are processed.

### 16.2. Do Not Keep Live MimeMessage Objects in a Queue

Once the folder/Store closes, lazy-loaded MIME parts may no longer be readable. If attachments need asynchronous processing, persist a snapshot or object-storage reference before closing the connection, with appropriate quotas and encryption.

## 17. Designing IMAP Sync with a UID Cursor

A resilient pipeline can look like this:

```text
Scheduled poll
    |
    v
Connect Store
    |
    v
Open INBOX READ_ONLY
    |
    v
Read UIDVALIDITY
    |
    +--> changed? -> resync strategy
    |
    v
Find UID > last committed UID
    |
    v
Fetch batch headers
    |
    v
Extract & validate content
    |
    v
DB transaction:
  - save mailbox message identity
  - enqueue business processing event
  - update cursor/checkpoint safely
    |
    v
Close Folder and Store
```

### 17.1. Illustrative Database Schema

```sql
CREATE TABLE mailbox_message (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mailbox_account VARCHAR(120) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    uid BIGINT NOT NULL,
    message_id VARCHAR(998),
    received_at TIMESTAMP,
    subject TEXT,
    processing_status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_mailbox_uid
      UNIQUE (
          mailbox_account,
          folder_name,
          uid_validity,
          uid
      )
);

CREATE TABLE mailbox_cursor (
    mailbox_account VARCHAR(120) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    last_committed_uid BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (mailbox_account, folder_name)
);
```

This schema is illustrative only:
- In multi-tenant setups, account identity must be controlled and must not contain credentials.
- `message_id` is optional metadata, not a mandatory unique key.
- The cursor is updated only after the processing plan has been safely persisted.
- If a UID fails while the cursor keeps advancing, messages risk being skipped. Implement retries/dead-lettering and batch checkpoint rules.
- When UIDVALIDITY changes, handle the new generation rather than continuing with the stale cursor.

### 17.2. Persist Data First, Acknowledge Later

A workflow can:
1. Read metadata/message.
2. Validate and persist the record with a unique key.
3. Enqueue internal work in the same transaction.
4. Commit.
5. Afterward, optionally mark `SEEN` or move the folder according to policy.

If a crash occurs after step 4 and before step 5, the next poll may encounter the message again, but the unique key prevents creating a **duplicate business event**.

Doing the reverse (marking processed on the mailbox before committing to the DB) risks losing work on a crash.

### 17.3. No Atomic Transaction Across IMAP and Database

IMAP flag updates/moves and database commits belong to two independent systems. No simple transaction guarantees both commit together or both roll back together.

Therefore, design for **at-least-once observation + idempotent processing**, rather than claiming exactly-once across the network. Business-level exactly-once must be built using unique keys, internal transactions, and side-effect controls.

## 18. Periodic Mailbox Polling

Polling is straightforward and widely used.

Spring scheduler example:

```java
package com.example.mailbox;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailboxPollScheduler {

    private final MailboxSyncService syncService;

    public MailboxPollScheduler(
            MailboxSyncService syncService) {
        this.syncService = syncService;
    }

    @Scheduled(
        fixedDelayString = "${app.mailbox.poll-delay-ms:30000}"
    )
    public void poll() {
        syncService.synchronizeOneBatch();
    }
}
```

`MailboxSyncService` is an application-defined service handling connections, folders, cursors, and persistence. To use `@Scheduled`, the application must enable scheduling properly, e.g., `@EnableScheduling`, and manage exceptions so operational signals are not silently lost.

Here `fixedDelayString` means the delay is measured **after the previous poll finishes** under the corresponding scheduling mode. With multiple application instances, `@Scheduled` alone does not guarantee each mailbox has only one consumer.

### 18.1. Choosing the Polling Interval

If polling every 2 seconds:
- detection latency for new mail may be low;
- but connect/login frequency and IMAP server load increase;
- provider rate limits are easily hit.

If polling every 5 minutes:
- lower load;
- but tickets/alerts arrive slowly.

Tune based on:
- SLA;
- mailbox arrival rate;
- provider connection quota;
- number of accounts/folders;
- processing duration per batch;
- polling overlap;
- number of consumer instances.

There is no single universal optimal interval.

### 18.2. Prevent Overlapping Polls

When one poll runs longer than the interval:
- do not allow two threads to process the same folder concurrently;
- use scheduler configuration, locks, or distributed leases;
- with multiple pods, use a single-owner lease per mailbox/folder;
- save the cursor after commit with optimistic/concurrency controls.

Do not assume that having one scheduler thread per JVM means only one consumer exists across the whole cluster.

### 18.3. Backpressure

If 50,000 messages are pending, a single poll must not load them all onto the heap. Instead:
- cap batch size;
- cap bytes per batch;
- enqueue into a durable queue;
- pause/throttle when downstream backlog is high;
- prioritize new or old messages per an explicit policy;
- monitor lag and age of oldest unprocessed message.

## 19. IMAP IDLE and Change Notifications

IMAP supports the **IDLE** extension on capable servers, allowing clients to wait for mailbox change notifications without repeatedly querying the whole Inbox.

Concept:

```text
Client                        IMAP server
  |---- SELECT INBOX ---------->|
  |---- IDLE ------------------>|
  |                             |
  |<--- EXISTS / change notice--|
  |---- DONE ------------------>|
  |---- FETCH new UIDs -------->|
  |---- IDLE again ------------>|
```

However:
- IDLE **is not a durable notification queue**;
- servers/proxies can drop idle connections;
- clients still need to reconnect and resync by UID;
- changes can occur while the client is offline;
- IDLE may need to be periodically terminated and re-established;
- IDLE support and exact APIs depend on the provider/implementation.

Some Jakarta Mail provider libraries expose an `IMAPFolder` class/extension supporting `idle()`, though that API is not standard behavior across all `Folder` protocols. When needed, pick the right implementation and library version and test against the mailbox provider.

### 19.1. IDLE Does Not Replace Checkpoints

After receiving a notification, you still must:
1. Verify the folder connection is still valid.
2. Find new UIDs from the cursor.
3. Fetch in batches.
4. Persist idempotently.
5. Commit.
6. Return to IDLE.

If the process restarts, it must be able to resync even if no notifications were received while offline.

### 19.2. Choosing Polling or IDLE?

| Criterion | Polling | IDLE |
|---|---|---|
| Ease of implementation | High | Medium, extra lifecycle |
| Near real-time | Depends on interval | Usually faster when server supports it |
| Long-lived connections | Fewer if connecting per poll | Potentially high |
| Resilience to proxies/drops | Short connections easier to manage | Requires continuous reconnect/refresh |
| Recovery after restart | Based on cursor | Still must use cursor |
| Server support | Ubiquitous | Capability must be verified |
| Suitable for few mailboxes | Yes | Yes if low latency is needed |
| Suitable for many mailboxes | Needs query throttling | Needs managing many sockets/lifecycles |

If a mailbox does not require real-time delivery, polling can be simpler and more reliable. If low latency is needed and the provider supports IDLE reliably, implement IDLE **together with resync**, never replacing durable synchronization completely.

## 20. Connection Management: Per Poll or Long-Lived Connections?

Two strategies:

**A. Per-batch connection**
- Create or reuse a configured `Session`.
- Call `Store.connect`.
- Open Folder.
- Process one batch.
- Close Folder/Store.

Pros: clear lifecycle, fewer stale connections, suits infrequent polling. Cons: added TCP/TLS/AUTH overhead.

**B. Long-lived connection**
- Keep Store/Folder open in a dedicated consumer.
- Use IDLE or fetch multiple batches.
- Monitor disconnects and reconnect.
- Close resources on shutdown.

Pros: reduces connection overhead, can lower latency. Cons: requires ownership, heartbeats, timeouts, reconnects, thread-safety, and recovery.

### 20.1. Session Reuse Is Not Store Reuse

`Session` can be reused as configuration. `Store`/`Folder` hold live connection/selection state and must be managed separately.

Do not reuse one static `Store` across multiple mailbox accounts by swapping username/password. Also do not share an open `Folder` across multiple workers concurrently calling FETCH/close/expunge.

### 20.2. Considering IMAP Provider Connection Pools

Some Jakarta Mail IMAP providers offer connection caching/pooling mechanisms for `Store`/`Folder` operations. However, details like pool size, timeouts, and reuse rules depend on implementation and version.

Do not assume a `Session` or `Store` is a thread-safe general connection pool. If optimizing pooling:
- check the documentation for the implementation in use;
- cap connections per mailbox/provider quota;
- measure actual socket counts;
- test server-side disconnects;
- ensure multiple consumers never process the same UID.

### 20.3. Disconnecting Mid-Fetch

Cases:
- server closes an idle socket;
- network reset;
- TLS session failure;
- expired token;
- folder renamed/deleted;
- mailbox account disabled.

On error:
1. Do not assume you still hold a healthy `Store` merely because `isConnected()` was previously true.
2. Close stale resources.
3. Reconnect with jittered backoff and bounded attempts.
4. Reopen the folder.
5. Check `UIDVALIDITY`.
6. Resume from the durable checkpoint, not from an old message number.
7. Never duplicate business events.

## 21. Password, App Password, and OAuth2 Authentication

Many mailbox providers no longer permit plain username/password over IMAP or require:
- a dedicated app password;
- OAuth2/XOAUTH2;
- mailbox access permissions granted to the application;
- security policies/conditional access;
- account/folder scopes;
- admin consent.

Verify against the actual provider. An app with SMTP sending permission **does not automatically have permission to read the Inbox**.

### 21.1. Example XOAUTH2 Configuration for IMAPS

With a Jakarta Mail implementation supporting the XOAUTH2 mechanism:

```java
Properties props = new Properties();

props.put("mail.imaps.ssl.enable", "true");
props.put("mail.imaps.ssl.checkserveridentity", "true");
props.put("mail.imaps.auth.mechanisms", "XOAUTH2");
props.put("mail.imaps.connectiontimeout", "5000");
props.put("mail.imaps.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");

try {
    store.connect(
        imapHost,
        993,
        mailboxUsername,
        accessToken
    );
} finally {
    if (store.isConnected()) {
        store.close();
    }
}
```

Here `accessToken` is passed in the credential position of `Store.connect` per the provider's XOAUTH2 mechanism. **Not every mailbox provider automatically accepts this pattern.** Ensure:
- the provider supports IMAP + OAuth2;
- the token has the right audience/scope/permissions;
- the token is still valid;
- the auth mechanism does not unexpectedly fall back to password auth;
- the provider/API/library are compatible;
- the token is never logged.

### 21.2. Token Refresh

Do not keep reusing an expired access token forever in a `Store`. Long-lived connections can be dropped by the server; on reconnect, fetch a fresh token from the token provider per policy.

Never hardcode refresh tokens in source code or write them in plaintext to logs. Secret/token storage, scopes, and rotation belong to the application's security boundary.

### 21.3. Least Privilege

If the application only reads the Inbox, do not grant delete or send-as-user permissions when the provider allows separating scopes. Separate service accounts by responsibility and restrict accessible mailboxes/folders.

## 22. Configuring Multiple Mailbox Accounts or Tenants

A SaaS application may need to read:
- `support@tenant-a.example`;
- `support@tenant-b.example`;
- an internal mailbox;
- a delegated shared mailbox.

Never use a single singleton `Store` reconfigured sequentially with each tenant's credentials.

Safe model:

```text
MailboxAccountRegistry
  |
  +--> Account A config -> Session/Store A -> Folder A
  |
  +--> Account B config -> Session/Store B -> Folder B
  |
  +--> Internal config -> Session/Store C -> Folder C
          |
          v
Per-mailbox cursor + access policy
```

Parameters to isolate:
- credentials/tokens;
- mailbox account identity;
- allowed folders;
- cursor and `UIDVALIDITY`;
- rate limits;
- downstream tenant ID;
- file attachment storage;
- access auditing.

**Tenant identity must come from an authenticated backend**, not from a header in a received email or an arbitrary request used to pick a secret.

### 22.1. Do Not Rely on From to Identify the Tenant

`From: customer@...` is easy to spoof. If content enters tenant A's system, the tenant must be determined by the configured mailbox account/route, not solely by the `From` address in the message.

SPF/DKIM/DMARC can provide authentication signals about the sending domain, but they are not proof that the sender is authorized to act on a tenant's data.

### 22.2. Do Not Open Arbitrary IMAP Endpoints from User Input

If an API allows callers to supply `host` and `port` for the server to connect to directly, the application can be abused for SSRF or accessing internal services. Only use admin-approved account profiles with appropriate DNS/IP/egress policies.

## 23. Mailbox Reading Performance

Possible bottlenecks include:
- number of TCP/TLS logins;
- server-side FETCH round trips;
- number of messages/folder;
- size of MIME and attachments;
- charset decoding/HTML parsing;
- database writes;
- downstream enrichment;
- mailbox provider throttling;
- running polling across multiple replicas.

### 23.1. Do Not Download Bodies Before Knowing Processing Is Needed

Efficient flow:

```text
UID range
   |
   v
FETCH UID + headers + flags
   |
   v
Already processed?
   |
   +-- Yes -> skip
   |
   v
Download necessary body parts
   |
   v
Validate / persist / enqueue
```

For emails where only the subject is needed to create an initial ticket, downloading attachments in the first pass may not be necessary. However, if the business flow requires saving full content as a snapshot, explicitly define a `CONTENT_PENDING` state and retry body downloads rather than marking completion prematurely.

### 23.2. Paginating by UID

With IMAP, a strategy can store `lastCommittedUid`, query UIDs higher than the cursor in windows (accounting for gaps), and call `getMessagesByUID(...)` or `getMessageByUID(...)` per the provider's APIs.

Do not assume contiguous UIDs: IMAP UIDs **do not have to be sequential**. Gaps do not by themselves indicate errors. Advance the cursor to the UID actually processed according to durable rules.

### 23.3. Size Limits

You can enforce:
- maximum messages/poll;
- maximum MIME parts;
- maximum header/body bytes;
- maximum attachment bytes;
- maximum nested MIME depth;
- maximum parsing duration;
- per-mailbox concurrency;
- total in-flight memory budget.

A malicious or malformed email should never cause a worker to consume the entire heap or block progress for all other mailboxes.

### 23.4. Timing Each Stage

| Metric | Question |
|---|---|
| `mailbox_connect_duration_seconds` | Which provider has slow TCP/TLS/AUTH? |
| `mailbox_open_folder_duration_seconds` | Is SELECT folder slow? |
| `mailbox_fetch_headers_seconds` | How long does metadata fetching take? |
| `mailbox_fetch_body_seconds` | Are messages/attachments causing load? |
| `mailbox_processed_total` | How many messages were ingested successfully? |
| `mailbox_skipped_duplicate_total` | How many UIDs were already recorded? |
| `mailbox_sync_lag_seconds` | How far behind mailbox arrival is sync? |
| `mailbox_reconnect_total` | How many dropped connections occurred? |
| `mailbox_uidvalidity_changed_total` | Did a mailbox reset its generation? |
| `mailbox_parse_failures_total` | How many messages had MIME/charset errors? |
| `mailbox_processing_backlog` | Is downstream keeping up? |

Never include email bodies, access tokens, or attachment bytes in metric labels/logs.

## 24. Logging and Safe Error Handling

An error can occur at:
1. account configuration/lookup;
2. DNS/TCP;
3. TLS and hostname verification;
4. AUTH;
5. opening the folder;
6. FETCH headers;
7. downloading/parsing MIME;
8. persisting/acking in the database;
9. updating flags/moving folders;
10. closing/reconnecting.

Do not lump everything into "IMAP connection failed" when you need to determine the proper remediation.

### 24.1. Error Categories

| Category | Examples | Action |
|---|---|---|
| Network transient | timeout, connection reset | Close/reconnect with backoff |
| TLS/certificate | PKIX, hostname mismatch | Stop aggressive retries; fix endpoint/CA |
| Authentication | wrong token, expired token, missing scope | Refresh token or fix permissions/config |
| Folder | folder missing or forbidden | Verify configuration; do not retry blindly |
| Message missing | message expunged between list and fetch | Skip/reconcile by UID; do not fail whole pipeline |
| MIME parse | malformed content, broken charset | Record per-message retry/quarantine |
| Resource limit | oversized attachment, deep nested MIME | Isolate message per policy |
| DB outage | unable to persist checkpoint | Keep old cursor; safely retry after DB recovers |
| UIDVALIDITY changed | folder generation changed | Resync per policy |

### 24.2. Structured Logging

Example:

```json
{
  "event": "mailbox.sync_batch",
  "mailboxKey": "support-a",
  "folder": "INBOX",
  "uidValidity": 4567,
  "fromUid": 12001,
  "toUid": 12100,
  "processed": 72,
  "duplicates": 28,
  "durationMs": 1830,
  "outcome": "SUCCESS"
}
```

This information helps investigation without logging:
- usernames/passwords;
- OAuth2 tokens;
- full headers/bodies;
- recipients/From when unnecessary;
- URLs containing reset/verification tokens;
- attachment bytes.

### 24.3. Avoid Debug Logging in Production

Jakarta Mail supports enabling debug on `Session` for diagnostics:

```java
Session session = Session.getInstance(props);
session.setDebug(true);
```

Debug mode can output protocol details, account/server metadata, and in some configurations expose sensitive data. Enable it only temporarily in controlled environments; avoid logging credentials or raw emails.

## 25. Testing Session and Mailbox Readers

### 25.1. Unit Tests Without Real IMAP

Components that can be unit-tested independently:
- mailbox account profile selection;
- configuration validation;
- MIME traversal with in-memory `MimeMessage`;
- charset/Unicode handling;
- mapping headers to DTOs;
- cursor/resync policy;
- idempotency and retry classifiers;
- attachment size/filename rules.

In-memory MIME example:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

message.setSubject("Yêu cầu hỗ trợ từ Nguyễn Thị Ánh", "UTF-8");
message.setText(
    "Xin chào,\nTôi cần hỗ trợ đơn hàng 123.",
    "UTF-8"
);

message.saveChanges();
```

You can test that `TextPartExtractor.collect(message,"text/plain")` returns the properly decoded content. This test verifies MIME parser logic, **not** `Store`/`Folder` IMAP connectivity.

### 25.2. Integration Tests Need an IMAP Test Server

Use a controlled mailbox server as an IMAP/POP3 sandbox supporting the APIs under test. For example, some projects use **GreenMail** for JavaMail tests; choose a version compatible with the application's `jakarta.mail.*`.

Checks:
1. Create a mailbox/test user.
2. Inject a test email into the server.
3. Create a real `Session` and `Store` pointing to the test endpoint.
4. Connect and open INBOX `READ_ONLY`.
5. Fetch the message and read Subject and body.
6. Verify closing folder/store.
7. Test accounts with bad credentials, missing folders, and disconnects.
8. Test UID/UIDVALIDITY when appropriately supported by the server.

Never use real personal mailboxes or production SMTP credentials in a test suite.

### 25.3. Test TLS Separately

A local IMAP test server without TLS proves API reading, but does not prove production IMAPS security configuration.

Separate tests are needed for:
- IMAPS or STARTTLS in the right mode;
- valid certificate chains;
- hostname matching SAN;
- untrusted certificates being rejected;
- timeouts/reconnects;
- OAuth2 if supported by the provider;
- TLS inspection/proxies if present in the infrastructure.

Never use `ssl.trust=*` in tests and assume production will verify certificates properly.

### 25.4. Test That Reading Does Not Unintentionally Mutate Flags

An important test:
1. Create an unread email in the test server.
2. Open the folder `READ_ONLY`.
3. Fetch headers/body using the ingestion code.
4. Close folder/store.
5. Reconnect and verify `SEEN` matches expectations.

This is an integration test because flag behavior depends on the server/protocol.

### 25.5. Test Idempotency Across Reconnects

- Poll the first time and store the UID in the DB.
- Poll the same folder/UIDVALIDITY again.
- Assert no extra business item is created.
- Simulate a crash after DB commit but before flag update.
- Poll again: the unique constraint prevents duplicates.
- Simulate a `UIDVALIDITY` change: the system resyncs without confusing old-generation UIDs.

### 25.6. Test Concurrent Workers

Run two consumers against the same mailbox/folder. Verify that DB leases/claims prevent duplicate side-effect execution. Do not rely on the same IMAP server returning different message counts as a locking mechanism.

## 26. Common Real-World Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `JavaMailSender` has no `getInbox()` | Confused sending API with receiving API | Use Jakarta Mail `Store`/`Folder` |
| `Session` created, but cannot read mail | Forgot to get or connect `Store` | Call `getStore` and `connect` |
| `AuthenticationFailedException` | Bad credentials, expired token, IMAP disabled, missing scope | Check provider auth policy |
| `SSLHandshakeException` or `PKIX` | Mismatched CA/chain/hostname/TLS mode | Verify cert/endpoint; keep validation enabled |
| `Connection refused` | Wrong host/port, firewall, IMAP blocked | Check network/provider |
| `FolderClosedException` | Server closed folder or app closed too early | Reconnect/reopen; do not retain lazy `Message` |
| `IllegalStateException` folder not open | Calling API requiring open folder before `open` | Manage lifecycle explicitly |
| `getContent()` is not a `String` | MIME multipart | Traverse MIME tree |
| Messages unexpectedly marked read | `READ_WRITE` or fetch behavior | Use `READ_ONLY`/peek; test flags |
| Cursor misses messages | Stored `messageNumber` instead of UID | Use UID + UIDVALIDITY |
| Duplicate tickets after restart | Missing unique key/checkpoint | Persist idempotently |
| Old UID points to wrong message | `UIDVALIDITY` changed | Resync by folder generation |
| Slow polling, high memory | Fetching all messages and attachments | Batch by UID/size limits |
| POP3 lacks folders like IMAP | Different protocol semantics | Choose IMAP if folders/flags are needed |
| New mail missed by `UNSEEN` query | User opened it or another client set `SEEN` | Use UID cursor instead of `SEEN` alone |
| Consumer hangs after a long time | Stale `Store`, network/proxy disconnect | Timeouts, reconnect, health monitoring |
| Reads fail only in production | Different JDK/truststore/proxy than tests | Diagnose from actual runtime environment |
| Attachment saved to wrong path | Trusted sender's filename | Server-generated filename and validation |
| HTML email causes XSS in dashboard | Rendering raw HTML from received mail | Sanitize/escape; block active content |
| Gmail/hosted provider rejects password | Requires OAuth2/app password | Follow provider policy |
| Multiple pods process same message | No ownership lease | Distributed lock + DB idempotency |

## 27. Checklist for Production Mailbox Reader Deployment

### 27.1. Configuration and Security

- [ ] Correct IMAP/POP3 protocol per provider.
- [ ] Correct host/port/TLS mode; use IMAPS or mandatory STARTTLS.
- [ ] Hostname verification and CA trust configured properly.
- [ ] Auth credentials/OAuth2 scopes have least privilege.
- [ ] Secret rotation and token refresh planned.
- [ ] No passwords/tokens/raw bodies logged.
- [ ] Egress allowlist and tenant account registry if needed.
- [ ] No real email accounts used in tests.

### 27.2. Resource Lifecycle

- [ ] `Session` is not mistaken for a TCP connection.
- [ ] `Store.connect` is invoked in a controlled manner.
- [ ] `Folder.open` uses the right mode.
- [ ] `Folder.close(false)` and `Store.close()` inside `finally`.
- [ ] No lazy `Message` retained past the folder lifecycle.
- [ ] Timeouts and reconnect with backoff implemented.
- [ ] `Store`/`Folder` not arbitrarily shared across threads.
- [ ] Server-side connection quotas monitored.

### 27.3. Synchronization and Data

- [ ] Unique key on mailbox/folder/UIDVALIDITY/UID.
- [ ] `messageNumber` is not used as a durable cursor.
- [ ] `UIDVALIDITY` changes have a resync policy.
- [ ] Persist before marking processed on the server.
- [ ] MIME/attachment parsing enforces byte/depth limits.
- [ ] HTML and URLs treated as untrusted data.
- [ ] Polling/IDLE has backpressure and distributed ownership.
- [ ] Per-message retry/quarantine on parse failures.
- [ ] Metrics for lag, errors, and duplicates.

### 27.4. Testing

- [ ] Unit tests for MIME/Unicode/cursor policies.
- [ ] Integration tests against an IMAP mailbox sandbox.
- [ ] Tests for authentication failure/TLS mismatch.
- [ ] Tests confirming `READ_ONLY` does not alter `SEEN` unexpectedly.
- [ ] Tests for UID cursors, duplicates, and `UIDVALIDITY` resets.
- [ ] Tests for closed folders, connection resets, and recovery.
- [ ] Tests for large attachments and malformed messages.
- [ ] Tests with two consumers on the same folder.
- [ ] Tests for IDLE reconnect and poll fallback if using IDLE.

## 28. Practice Exercises

### Exercise 1 — Session and Store

Write two snippets: one that only creates a `Session`, and a second that calls `Store.connect`. Explain exactly when the network connection is initialized.

### Exercise 2 — IMAPS

Configure IMAPS on port 993 with TLS hostname verification and three timeouts. Open `INBOX` in `READ_ONLY`, retrieve the message count, and close Folder/Store properly.

### Exercise 3 — IMAP STARTTLS

Convert the example to IMAP port 143 using `starttls.enable=true` and `starttls.required=true`. Explain why you must not fall back to plaintext if the server refuses STARTTLS.

### Exercise 4 — POP3S

Create a POP3S `Store` and read the message count from INBOX. Compare what is missing compared to IMAP regarding folders, flags, and UIDs.

### Exercise 5 — MIME Multipart

Build a multipart `MimeMessage` with `text/plain`, `text/html`, and an attachment. Write a MIME traversal function to extract the plain body while skipping text attachments.

### Exercise 6 — Flags

Create an unread test email. Fetch it using `READ_ONLY` then reopen to check `SEEN`. Propose how to track business processing without relying solely on mail flags.

### Exercise 7 — Message Number and UID

In a mailbox with three messages A, B, and C, delete/expunge B and observe the sequence number of C. Explain why UID/UIDVALIDITY is required for cursors.

### Exercise 8 — UIDVALIDITY Reset

Simulate a rebuilt folder where `UIDVALIDITY` changes while the app already stored a last UID. Design a resync that neither mixes the two UID generations nor emits duplicate events.

### Exercise 9 — Cursor Database

Design a table containing `mailboxAccount`, `folder`, `uidValidity`, `uid`, and processing status. Add a unique constraint and test that re-polling the same message does not insert a second row.

### Exercise 10 — Polling Batch

A mailbox has 100,000 messages, and the app may process at most 100 per poll. Design `getMessagesByUID` or a UID window so all messages are never loaded onto the heap.

### Exercise 11 — FetchProfile

Before downloading bodies, fetch envelope/flags/UID for a batch. Measure round trips/duration against a test server and explain the benefits of prefetching.

### Exercise 12 — Disconnection

Simulate the server closing the IMAP connection mid-fetch. Test that the app closes the stale Store, reconnects, opens the folder, checks `UIDVALIDITY`, and resumes from the checkpoint.

### Exercise 13 — OAuth2

The provider only permits IMAP XOAUTH2. Design a token provider, verify scopes, and refresh tokens on reconnect. Never write access tokens to logs.

### Exercise 14 — Polling vs. IDLE

Compare a support ticket mailbox needing 2-minute latency against an alerting mailbox needing near real-time detection. Recommend polling or IDLE and always include a resync cursor.

### Exercise 15 — Multi-Tenant Mailboxes

Two tenants have separate mailbox credentials and folders. Write a routing/account registry ensuring each worker can only read its designated mailbox, without relying on the `From` header to identify the tenant.

### Exercise 16 — Unsafe Attachments

A received email contains a large ZIP, filename `../../invoice.pdf`, and HTML containing an external image URL. Describe how to quarantine, limit bytes, and avoid automatically fetching external resources.

### Exercise 17 — Crash After DB Commit

The worker persisted a ticket but crashed before updating `SEEN`. Re-poll the same UID. Demonstrate that the DB unique key prevents creating a duplicate ticket.

### Exercise 18 — Monitoring

Design a dashboard including connect latency, poll lag, parse failures, `UIDVALIDITY` changes, duplicate rate, backlog, and reconnect attempts. Never place bodies or tokens into metric labels.

## 29. Summary

**Session and mailbox-reading connections** in Spring Framework Mail rely primarily on **Jakarta Mail inbound APIs**, not outbound `JavaMailSender`.

Principles to remember:

1. **`Session` is configuration**, `Store` represents the message-store connection, `Folder` must be opened in the right mode, and `Message` may lazy-load data over the connection.
2. **IMAP** suits workflows needing folder, flag, and UID synchronization; **POP3** mainly serves simple message downloads with fewer state features.
3. Use **IMAPS/STARTTLS with certificate and hostname verification**, timeouts, and provider-appropriate credentials/OAuth2; never fall back to plaintext.
4. Manage the full lifecycle **connect → open → fetch → convert to DTO → close**, without retaining `Message` after the Folder closes.
5. `READ_ONLY` is usually suitable for ingestion; **SEEN is not a business ACK**.
6. **Message sequence numbers are not durable**; IMAP sync should use **mailbox + folder + UIDVALIDITY + UID** and a safely persisted cursor.
7. Traverse MIME as a tree; limit attachments, and never render untrusted HTML or auto-fetch external resources.
8. Both polling and IDLE require **reconnect/resync, idempotency, backpressure, and distributed ownership** when running multiple workers/pods.
9. Persist DB progress before changing server flags, because IMAP and the database do not share an atomic transaction.
10. Test against an IMAP sandbox, covering TLS/auth/UID/flags/reconnects; separate parser and cursor-policy unit tests from network integration tests.

By understanding the true boundaries between `Session`, `Store`, `Folder`, and `Message`, you can build a stable, secure, and resilient mailbox reader while integrating received email data into your Spring application without dropping messages or accidentally processing duplicates.
