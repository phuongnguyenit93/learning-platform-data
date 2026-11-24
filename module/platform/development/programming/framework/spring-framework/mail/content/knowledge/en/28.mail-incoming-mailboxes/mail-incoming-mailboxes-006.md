# Folders, Messages, and Marking as Read

In applications using **Spring Framework Mail**, we are usually familiar with **sending emails** via **JavaMailSender**. When an application needs to **receive and process emails**—such as reading a customer support mailbox, receiving replies, checking a test mailbox, or automatically classifying incoming mail—the problem shifts to working with mail-receiving protocols and **Jakarta Mail** objects like **Store**, **Folder**, and **Message**.

An email is more than just content, a sender, and a timestamp. On an IMAP server, it also exists inside a **folder/mailbox**, has a relative ordinal position in that folder, and can carry **flags** such as read (**SEEN**), replied (**ANSWERED**), starred (**FLAGGED**), or pending deletion (**DELETED**). Changing the read flag is typically **a server-side state write**, not merely flipping a boolean in Java.

This lesson explains how to open and traverse folders, retrieve messages, read headers/bodies, search for unread mail and mark messages read/unread, as well as boundaries around IMAP/POP3, write permissions, body-reading side effects, UIDs, business transactions, concurrency, and testing. The examples use the **Jakarta Mail API**; Spring Mail primarily serves sending mail and **does not create a full inbox service automatically** just by adding `JavaMailSender` configuration.

> **Important principle:** Do not confuse **"the application successfully processed the email"** with **"the mailbox marked it SEEN"**. These are two states with different purposes. Marking as read too early can cause workers to miss work; marking too late or relying solely on `SEEN` can cause duplicate processing.

## 1. Objects You Need to Know When Reading Email

Jakarta Mail provides core concepts:

| Object | Responsibility | Common Operations |
| --- | --- | --- |
| **Session** | Holds properties and mail connection setup | `Session.getInstance(properties)` |
| **Store** | Represents the connection to the mailbox server | `connect`, `getDefaultFolder`, `getFolder`, `close` |
| **Folder** | Represents a mailbox/directory on the Store | `exists`, `list`, `open`, `getMessages`, `search`, `close` |
| **Message** | Represents an email message inside a folder | `getFrom`, `getSubject`, `getContent`, `getFlags`, `setFlag` |
| **Flags** | Set of message states | `contains`, `add`, `remove` |
| **SearchTerm** | Criteria for searching messages | `FlagTerm`, `FromStringTerm`, `SubjectTerm` |
| **UIDFolder** | API for IMAP UIDs when supported by the provider | `getUID`, `getMessageByUID`, `getUIDValidity` |

A visual model:

~~~text
Application
    |
    v
Jakarta Mail Session
    |
    v
Store (IMAP/IMAPS)
    |
    +-- INBOX ------------------+
    |                          |
    |                         Message #1  [SEEN]
    |                         Message #2  [UNSEEN]
    |                         Message #3  [FLAGGED]
    |
    +-- Sent -------------------+
    |                         Message ...
    |
    '-- Archive ----------------+
                              Message ...
~~~

**Store** is a connection to an account/mail server; **Folder** holds or references messages; **Message** represents a specific email, where much of the data may be **lazy-loaded** from the server when accessed by code.

### Session Is Not a Mailbox

~~~java
Properties properties = new Properties();
Session session = Session.getInstance(properties);
~~~

This snippet only creates a **mail session**; it has not connected over the network or read any emails. To receive mail, obtain a protocol-appropriate **Store** and call **connect(...)**.

### Store Is Not an SMTP Transport

**JavaMailSenderImpl** uses SMTP to send. **Store** over IMAP or POP3 is used to read a mailbox. Do not use **mailSender.send(...)** to read mail, and do not use **Folder** to submit emails to SMTP. An application may need both, but they are two distinct protocol flows.

## 2. Choosing IMAP vs. POP3?

The two common mail-receiving protocols are **IMAP** and **POP3**. They differ significantly in folder and flag models.

| Topic | IMAP | POP3 |
| --- | --- | --- |
| Multiple folders | Has server-side mailbox/folder model | Mainly a flat list mailbox without an equivalent folder model |
| SEEN status | Has server-side **\Seen** flag | No standard equivalent for syncing "read" across clients |
| Server-side search | Has SEARCH command and flag searching | Lacks the same SEARCH/FLAGS suite |
| Long-term IDs | UID tied to folder's UIDVALIDITY | UIDL has different semantics, server-dependent |
| Multi-device sync | Designed for it | More limited |
| Delete/move/copy | Has server-side flag/folder mechanisms | Major differences; typically DELETE per POP3 session |
| Mark read/unread | IMAP STORE flags | Cannot assume IMAP-like support |

**If the requirement is "view unread emails, open folders, and mark read on the server", IMAP/IMAPS usually fits better than POP3.** Do not build an abstraction claiming POP3 has full IMAP-like SEEN/UNSEEN support and leave the backend executing an operation absent from the protocol.

### Use Secure Connections

- **IMAPS**: IMAP over TLS from connection start, usually port **993**.
- **IMAP + STARTTLS**: plain IMAP upgraded to TLS when supported by the server and requested by the client, usually port **143**.
- **POP3S**: POP3 over TLS, usually port **995**.

Ports are conventions only; actual configuration is determined by the server. When security is required, verify certificates, hostnames, authentication mechanisms, and TLS policies rather than only checking port numbers.

## 3. Configuring Jakarta Mail to Connect via IMAPS

Minimal example reading a mailbox over **IMAPS**:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public class MailboxConnectionExample {

    public void connect(
            String username,
            String password
    ) throws Exception {
        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.connectiontimeout", "5000");
        props.put("mail.imaps.timeout", "10000");
        props.put("mail.imaps.writetimeout", "10000");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = session.getStore("imaps");

        try {
            store.connect(
                    "imap.example.test",
                    993,
                    username,
                    password
            );

            Folder inbox = store.getFolder("INBOX");
            System.out.println(inbox.getFullName());
        } finally {
            store.close();
        }
    }
}
~~~

The host and account in the example are placeholders. In a real application, credentials/OAuth tokens must come from an appropriate secret store; never commit passwords to Git or write them to logs.

### Key Properties to Note

| Illustrative Property | Meaning |
| --- | --- |
| **mail.store.protocol=imaps** | Selects the default Store protocol |
| **mail.imaps.connectiontimeout** | Connection establishment timeout |
| **mail.imaps.timeout** | Socket read timeout |
| **mail.imaps.writetimeout** | Socket write timeout |
| **mail.imaps.ssl.checkserveridentity=true** | Verifies hostname in the TLS certificate |
| **mail.imaps.peek=true** | Implementation-dependent; fetches body without auto-setting SEEN |

Do not enable trust-all settings like **mail.imaps.ssl.trust=*** to bypass certificate verification. When a private CA is required, configure an appropriate truststore instead of disabling checks.

### Protocol Determines Property Prefixes

When using **imaps**, many properties start with **mail.imaps.**. With **imap + STARTTLS**, properties usually belong under **mail.imap.**. For example:

~~~properties
mail.imap.starttls.enable=true
mail.imap.starttls.required=true
mail.imap.ssl.checkserveridentity=true
~~~

Do not set **mail.smtp.starttls.required** expecting it to protect an IMAP Store; SMTP and IMAP have separate configuration sets.

### Authentication Is Not Always a Plain Password

Many providers require OAuth 2.0 or a specific authentication mechanism instead of a regular login password. Mechanism selection and token/refresh policies depend on the server, JavaMail implementation, and identity system. The examples in this lesson use username/password to demonstrate the core API, not as a recommendation to use basic passwords for all production mailboxes.

## 4. Store and Folder Lifecycle

Before operating on messages, **Folder** usually must be opened using **open(...)**. Afterward, both folder and store must be closed to release connections/resources.

~~~java
Store store = session.getStore("imaps");
Folder inbox = null;

try {
    store.connect(host, port, user, secret);

    inbox = store.getFolder("INBOX");
    if (!inbox.exists()) {
        throw new IllegalStateException("INBOX does not exist");
    }

    inbox.open(Folder.READ_ONLY);

    int count = inbox.getMessageCount();
    System.out.println("Messages: " + count);
} finally {
    if (inbox != null && inbox.isOpen()) {
        inbox.close(false);
    }
    if (store.isConnected()) {
        store.close();
    }
}
~~~

**close(false)** does not request expunging messages marked DELETED; it does not mean rolling back all flag changes. Flag updates during a READ_WRITE session may already have been persisted by the server before the folder is closed.

### Use READ_ONLY and READ_WRITE Intentionally

~~~java
inbox.open(Folder.READ_ONLY);
~~~

This mode is appropriate for inspecting metadata/messages when the application **does not need to modify flags**. To mark SEEN or clear flags:

~~~java
inbox.open(Folder.READ_WRITE);
~~~

If the server or mailbox permissions disallow writes, opening READ_WRITE or calling setFlag may fail. Never assume every folder is writable merely because the Store authenticated successfully.

### Folder Objects Are Not Necessarily Independent of Store

Do not retrieve a Message from a Folder, close the Store, and expect every call to **getContent()**, **getFlags()**, or **getInputStream()** to keep working. Much of the data is fetched on demand from the server and can throw **FolderClosedException** or **StoreClosedException** after the connection closes.

Maintain this boundary:

~~~text
Connect Store
  -> Open Folder
      -> Fetch needed metadata/body
      -> Persist business results / update flags if permitted
  -> Close Folder
-> Close Store
~~~

### Do Not Arbitrarily Share Folder/Message Across Threads

IMAP Store/Folder instances carry connection state and message sequence numbers that can shift when the server updates. Do not use the same open Folder across multiple worker threads to process and set flags concurrently without synchronization strategies and thorough knowledge of the implementation. Normally, restrict one owner per mailbox/partition or create independent sessions/connections with concurrency control.

## 5. What Is a Folder in IMAP?

A **Folder** is a server-presented container for messages. A Folder can have:

- Short name (**getName**) and full name (**getFullName**).
- Parent folder (**getParent**) and child folders (**list**).
- Attribute allowing messages (**HOLDS_MESSAGES**).
- Attribute allowing subfolders (**HOLDS_FOLDERS**).
- Message count, unread count, open state, and writability.

Hierarchy example:

~~~text
Mailbox account
  |
  +-- INBOX
  +-- INBOX/Support
  +-- INBOX/Billing
  +-- Sent
  +-- Drafts
  '-- Archive
~~~

This structure is illustrative only. Not all servers use **/** as the delimiter, not all folders live under INBOX, and provider folder names may be localized or carry special-use semantics.

### INBOX Is a Special Standard Folder

In IMAP, **INBOX** is a mailbox name treated specially by the protocol and typically present in an account. Names like Sent, Trash, Spam, and Archive vary by server/localization and special-use attributes. Never hardcode that every provider names folders "Sent" or "Spam" identically.

### Inspecting Folder Metadata

~~~java
Folder folder = store.getFolder("INBOX");

if (folder.exists()) {
    System.out.println("Name: " + folder.getName());
    System.out.println("Full name: " + folder.getFullName());
    System.out.println("Type: " + folder.getType());
}
~~~

Some metadata reads do not require an open folder, while methods like `getMessages`/`getMessage`/`getPermanentFlags` require corresponding state and support. Read the specific API contract, handle **MessagingException**, and do not assume every server provides all metadata while a folder is closed.

## 6. Listing Folders and Identifying the Target Folder

Example traversing folders under the default root:

~~~java
import jakarta.mail.Folder;

Folder root = store.getDefaultFolder();
for (Folder folder : root.list()) {
    System.out.printf(
            "Folder=%s, type=%d%n",
            folder.getFullName(),
            folder.getType()
    );
}
~~~

**getDefaultFolder()** is the logical starting point for the folder tree; it is not a message-bearing mailbox that the application can necessarily open and read like INBOX.

### Bounded Traversal

Do not recurse unboundedly through every folder or call `getMessages` on every folder when you only need a work inbox. For enterprise mailboxes with hundreds of folders:

- Use explicit, admin-confirmed folder names/configurations.
- Store mapped folder IDs/names per account/provider.
- Limit traversal depth or folder count.
- Never fetch message bodies when merely listing folders.
- Handle folders deleted or renamed between scans.

### Folder Names and Delimiters

IMAP uses a server-supplied hierarchy delimiter. Do not join folder paths using OS **Path.resolve(...)**, as these are logical names on the IMAP server, not local filesystem paths. To access a subfolder:

~~~java
Folder parent = store.getFolder("INBOX");
Folder child = parent.getFolder("Support");
~~~

Subfolder resolution and actual naming depend on the server. If a folder is renamed while a worker runs, handle **FolderNotFoundException** or the corresponding error rather than accidentally creating a new folder.

## 7. Message Number: Position in a Folder, Not a Long-Term Identifier

When a folder is open, Jakarta Mail allows:

~~~java
int count = inbox.getMessageCount();
Message first = inbox.getMessage(1);
Message last = inbox.getMessage(count);
~~~

This is a 1-based **message sequence number** within the open folder. Never call `getMessage(0)`. On an empty folder, `count=0`, so never call `getMessage(count)` either.

### Why Are Message Numbers Unstable?

In IMAP, when a message is deleted/expunged, the sequence numbers of subsequent messages can shift:

~~~text
Before expunge:
  #1 -> Message A
  #2 -> Message B
  #3 -> Message C

Delete + expunge Message B:
  #1 -> Message A
  #2 -> Message C
~~~

Therefore **number 2 is not a durable database key**. Never store `messageNumber=2` to come back tomorrow and process the same email if the mailbox can change.

### Iterating Within a Short-Lived Snapshot

~~~java
int total = inbox.getMessageCount();
for (int index = 1; index <= total; index++) {
    Message message = inbox.getMessage(index);
    // Operate only while the folder remains open.
}
~~~

This example only illustrates the API; for large mailboxes or concurrent client modifications, use **server-side search, batch fetching, and UIDs** instead of loading all messages or relying on contiguous indices.

## 8. Reading Basic Information from a Message

A **jakarta.mail.Message** object can provide:

| Component | Common API | Notes |
| --- | --- | --- |
| Sender | `getFrom()` | Can have multiple Addresses, be missing, or be spoofed |
| Recipients | `getRecipients(Message.RecipientType.TO)` | Not all recipients appear in To; Bcc may be absent |
| Subject | `getSubject()` | Usually decoded by the library from MIME encoded-words |
| Sent date | `getSentDate()` | Can be null or mis-set by the sender |
| Received date | `getReceivedDate()` | Availability depends on provider |
| Message-ID header | `getHeader("Message-ID")` | Not a trusted/system-wide unique ID |
| MIME type | `isMimeType("text/plain")` | Checks the current content type |
| Content | `getContent()`, `getInputStream()` | Can fetch body over network and alter SEEN |
| Flags | `getFlags()`, `isSet(flag)` | State on the mailbox |
| Folder | `getFolder()` | Link to the current folder |
| Message number | `getMessageNumber()` | Not a stable key |

Example reading **metadata only**:

~~~java
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import java.util.Date;

public record MessageSummary(
        int sequenceNumber,
        String subject,
        String from,
        Date sentDate,
        boolean seen
) {
}

public static MessageSummary toSummary(Message message)
        throws MessagingException {
    Address[] senders = message.getFrom();
    String sender = senders == null || senders.length == 0
            ? "(unknown)"
            : senders[0].toString();

    return new MessageSummary(
            message.getMessageNumber(),
            message.getSubject(),
            sender,
            message.getSentDate(),
            message.isSet(jakarta.mail.Flags.Flag.SEEN)
    );
}
~~~

**Important distinction:** `From` or `Message-ID` fields come from email content/headers and can be controlled or spoofed by the sender. Never use them as proof of sender authentication when processing critical business commands; verify senders using an appropriate policy, potentially combining trusted inbox sourcing, SPF/DKIM/DMARC from receiving infrastructure, and business verification.

### Reading Headers Does Not Always Read the Body

Fetching Subject, From, or flags typically consumes less bandwidth than downloading full bodies/attachments. However, that depends on implementation and server caching/fetching behavior. Never assume a `getSubject()` call makes zero network calls; Jakarta Mail may lazy-fetch data.

### Never Print Full Headers and Bodies to Logs

Emails can contain OTP codes, invoices, tokens, or private data. In logs, prefer folder name, UID, outcome, processing duration, and error codes, without printing full bodies or complete addresses when unnecessary.

## 9. Flags: State Attached to a Message

Jakarta Mail uses **Flags** to represent status. Common system flags:

| Jakarta Mail Flag | Corresponding IMAP Flag | Common Meaning |
| --- | --- | --- |
| **Flags.Flag.SEEN** | `\Seen` | Message has been marked as read |
| **Flags.Flag.ANSWERED** | `\Answered` | Replied to |
| **Flags.Flag.FLAGGED** | `\Flagged` | Marked important/starred depending on client |
| **Flags.Flag.DELETED** | `\Deleted` | Marked for deletion; may not yet be expunged |
| **Flags.Flag.DRAFT** | `\Draft` | Draft |
| **Flags.Flag.RECENT** | `\Recent` | Server-managed recent state, not the same as unread |
| **Flags.Flag.USER** | User-defined flags mechanism | Use/check provider-supported custom flags |

**SEEN** is not a flag invented by Spring Mail; it is part of the Jakarta Mail and IMAP abstractions. Clients treat a message as unread when the `SEEN` flag is absent.

### Checking Flags

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;

boolean read = message.isSet(Flags.Flag.SEEN);
boolean flagged = message.isSet(Flags.Flag.FLAGGED);
boolean deleted = message.isSet(Flags.Flag.DELETED);
~~~

Or:

~~~java
Flags flags = message.getFlags();
boolean read = flags.contains(Flags.Flag.SEEN);
~~~

**Message.isSet(...)** and **getFlags()** may need to query the server if data is not yet cached. For many messages, use batching/fetch profiles or server-side SEARCH.

### Do Not Confuse RECENT with UNSEEN

**RECENT** does not simply mean "the user has not read it". It is a server/session-related state, and not all modern IMAP servers give it identical semantics. When looking for unread messages, check **NOT SEEN**, never substituting RECENT.

### Custom Flags Are Not Always Supported

Some servers support keywords such as label names or custom flags. Before relying on custom flags, inspect **folder.getPermanentFlags()** or provider capabilities, and distinguish flags persisted durably on the server from session-only flags.

## 10. Marking as Read with Flags.Flag.SEEN

To change read/unread status on IMAP, open the folder **READ_WRITE**, then call **setFlag(...)**:

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Store;

Store store = session.getStore("imaps");
Folder inbox = null;

try {
    store.connect(host, port, username, password);
    inbox = store.getFolder("INBOX");
    inbox.open(Folder.READ_WRITE);

    Message message = inbox.getMessage(1);
    message.setFlag(Flags.Flag.SEEN, true);
} finally {
    if (inbox != null && inbox.isOpen()) {
        inbox.close(false);
    }
    if (store.isConnected()) {
        store.close();
    }
}
~~~

**true** means adding the SEEN flag; this makes servers/clients display the email as read if supported by the provider and the operation succeeds.

### Marking as Unread

~~~java
message.setFlag(Flags.Flag.SEEN, false);
~~~

**false** means removing the SEEN flag, returning the message to unread state. This is also a server-side write; you must open READ_WRITE and verify mailbox permissions.

### Setting Flags on Multiple Messages

Jakarta Mail provides a folder-level API to update flags on a batch of messages:

~~~java
Message[] selected = inbox.getMessages(1, 10);
inbox.setFlags(
        selected,
        new Flags(Flags.Flag.SEEN),
        true
);
~~~

The example assumes the folder has at least 10 messages and is open READ_WRITE. Never pass a range exceeding the folder's message count; on active mailboxes, it is safer to search for matching messages and pass that array to **setFlags(...)**.

### Never Mark SEEN Before Processing Completes

A worker reading customer support mail:

~~~text
1. Find UNSEEN messages
2. Mark SEEN immediately
3. Call API to create support ticket
4. API fails
5. Next poll searches only UNSEEN -> message is skipped
~~~

This is a business bug. If mailbox flags are used as an indicator of completed work, **mark them after persisting the business outcome successfully**, and better yet, use a dedicated status table for deduplication. `SEEN` is only a mailbox signal, not a transaction coupled to the business database.

## 11. Reading a Message Body Can Automatically Mark It SEEN

This is one of the easiest details to overlook when building an email-reading application: some IMAP implementations/servers automatically set **\Seen** when a client fetches the body content normally.

Example:

~~~java
Object content = message.getContent();
~~~

With IMAP, performing a body read can add the SEEN flag depending on the provider and fetch/peek settings. Similarly, opening content streams can change state. Thus, an application intending to "preview unread messages" that calls `getContent()` may flip messages to read before business processing happens.

### Configuring Peek When Reading Without Changing SEEN

In Jakarta Mail IMAP implementations supporting the property:

~~~java
Properties props = new Properties();
props.put("mail.store.protocol", "imaps");
props.put("mail.imaps.peek", "true");

Session session = Session.getInstance(props);
Store store = session.getStore("imaps");
~~~

**mail.imaps.peek=true** instructs the IMAP implementation to read content via peek to avoid automatically adding `\Seen` on body fetch. Verify that this property is supported in your actual Jakarta Mail/Angus Mail version and test against the server. For **imap** instead of **imaps**, the prefix is usually **mail.imap.peek**.

### Peek Does Not Replace READ_ONLY

If you only need to observe, opening **Folder.READ_ONLY** is usually appropriate. If you need to process and eventually mark read, you can open READ_WRITE with peek to avoid changing the flag before the intended point:

~~~text
READ_WRITE Folder + peek
       |
       v
Fetch body -> parse / persist business result
       |
       v
Commit business transaction
       |
       v
Set SEEN explicitly
~~~

Even with peek enabled, test against the real server, especially with multipart/attachment messages or copy/move operations. **Never assume every API preserves flags identically across all providers.**

### What If Reading Accidentally Sets SEEN?

Do not try to fix it by always calling **setFlag(SEEN, false)** after reading. If another client intentionally marked the email read while the worker ran, clearing the flag would overwrite the user's action. Instead, configure fetch/peek properly from the start and separate process state from mailbox read state.

## 12. Finding Unread Messages Using FlagTerm

Jakarta Mail provides **SearchTerm**, among which **FlagTerm** searches messages by flags.

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

In **FlagTerm(flags, false)**, the **false** parameter indicates searching for messages **without the specified flags**. With a `SEEN` flag, the result is typically unread messages.

### Combining Multiple Conditions

Example selecting only unread messages whose subject contains a phrase:

~~~java
import jakarta.mail.search.AndTerm;
import jakarta.mail.search.FlagTerm;
import jakarta.mail.search.SearchTerm;
import jakarta.mail.search.SubjectTerm;

SearchTerm unseen = new FlagTerm(
        new Flags(Flags.Flag.SEEN),
        false
);

SearchTerm matchingSubject = new SubjectTerm(
        "Support"
);

Message[] candidates = inbox.search(
        new AndTerm(unseen, matchingSubject)
);
~~~

Searching by subject is merely a convenience filter. Subjects are sender-controlled and must never be treated as proof authenticating payment requests, refunds, or account privilege changes.

### Server-Side Search Still Requires Pre-Processing Verification

Depending on protocol/provider, some SearchTerms execute on the server or partially on the client. Results reflect a moment in time, and the mailbox can change immediately afterward. A message returned as UNSEEN may already have been marked SEEN by another client by the time the worker reads it.

In multi-worker workflows, never treat search results as an **exclusive lock**. You need a business claim/dedup mechanism if the goal is processing each message only once.

### Never Search by Fetching Bodies of the Entire Mailbox

In an inbox with 100,000 messages, iterating all `getContent()` calls to check flags wastes network bandwidth and can alter read state. Prefer **SEARCH UNSEEN** or UID/time-window queries, batch metadata, and fetch bodies only for needed candidates.

## 13. The SEEN Flag Can Be Modified by Multiple Clients

A support mailbox may be open simultaneously on:

- Staff webmail interfaces.
- Mobile apps.
- A Spring worker using IMAP.
- Another automated service.

These clients read/write state concurrently on the server. For example:

~~~text
10:00 Worker finds Message M: UNSEEN
10:01 Staff opens M in webmail -> SEEN
10:02 Worker processes M
10:03 Worker calls setFlag(SEEN, true)
~~~

In this example, there is no major issue with final state, but if the workflow assumes "UNSEEN means unprocessed", the worker can misinterpret staff actions. Conversely, if staff mark M as UNSEEN as a reminder to follow up, the worker might re-run the task.

### SEEN Is Not a Job Lock

There is no guarantee that two workers calling **search(UNSEEN)** concurrently will receive disjoint sets:

~~~text
Worker A: SEARCH UNSEEN -> M
Worker B: SEARCH UNSEEN -> M
Worker A: processes M
Worker B: processes M
~~~

Marking `SEEN` is not an atomic claim/lease mechanism designed for jobs. To prevent duplicate processing, use an **idempotency key** built from mailbox identity + `UIDVALIDITY` + `UID` (or another server-appropriate durable ID), a processed-message table, and atomic claims/unique constraints in the database.

### Distinguishing User Experience from System Progress

**SEEN** belongs to the mailbox state visible to users; **PROCESSED** belongs to the system's business workflow. A message can be:

| SEEN | PROCESSED | Meaning |
| --- | --- | --- |
| false | false | Opened by no one, not yet processed by worker |
| true | false | Read by someone, not yet business-processed |
| false | true | Processed, intentionally kept unread by preference |
| true | true | Read and processed |

Never collapse these two dimensions into a single boolean unless the business accepts the resulting synchronization limitations.

## 14. UID and UIDVALIDITY: More Stable Identifiers Than Message Numbers

When working with IMAP, message sequence numbers can shift after expunge. To know whether a message was already processed in earlier polls, the protocol provides a message **UID** (Unique Identifier) within a mailbox.

However, **UIDs are not globally unique across the entire system**:

- A UID is bound to a specific folder/mailbox.
- A UID is unique within a mailbox sharing the same **UIDVALIDITY**.
- If a mailbox is recreated or changes state such that `UIDVALIDITY` changes, old UIDs no longer carry the same meaning.
- A message copied to another folder may receive a different UID.
- A UID does not replace email sender authentication proof.

A useful logical identifier:

~~~text
Account identity
    +
Folder identity
    +
UIDVALIDITY
    +
UID
    =
Source message key
~~~

In multi-tenant/multi-account systems, use an **application-managed mailbox identifier** (not just the `From` address) to avoid collisions when two accounts share the same folder name and UID.

### Using UIDFolder

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

Folder inbox = store.getFolder("INBOX");
inbox.open(Folder.READ_ONLY);

if (!(inbox instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "Store does not support UIDFolder"
    );
}

long validity = uidFolder.getUIDValidity();
Message candidate = inbox.getMessage(1);
long uid = uidFolder.getUID(candidate);

System.out.println("UIDVALIDITY=" + validity);
System.out.println("UID=" + uid);
~~~

The example assumes the folder has at least one message. **UIDFolder** is a Jakarta Mail interface, but not every provider/folder supports it; check runtime types. UIDs may have special values if a provider does not support identifying a specific Message; production code should verify the implementation's contract.

### Looking Up a Message by UID

~~~java
Message found = uidFolder.getMessageByUID(savedUid);
if (found == null) {
    // Message may have been deleted/moved or UID no longer exists.
}
~~~

This must be called on a folder whose `UIDVALIDITY` matches the earlier record. If `UIDVALIDITY` has changed, **do not use `savedUid` alone** to decide whether a message has been processed.

### Why Not Use the Message-ID Header Instead of UID?

Emails can lack a `Message-ID`, reuse duplicate `Message-ID`s, or have senders intentionally assign the same value to multiple emails. Moreover, forwarded/copied messages can create different `Message-ID` relationships in a mailbox. `Message-ID` is useful for threading/correlation, but **not a reliable key for exactly-once inbox processing**.

### UIDs and Messages Moved Across Folders

If the application processes a message in INBOX and moves it to a Processed folder, the UID in Processed usually differs from the INBOX copy's UID. The database must store the source identity alongside processing state, and if the destination UID is needed, track copy/move results per provider capabilities. Never assume a UID stays identical across folders.

## 15. Fetching Messages by UID or in Batches

In periodic processing, re-reading the entire mailbox from the beginning is usually unnecessary. You can persist **UIDVALIDITY + last observed UID**, then query UIDs newer than the recorded watermark.

Access pattern:

~~~java
long lastUid = checkpoint.lastUid();
long currentValidity = uidFolder.getUIDValidity();

if (currentValidity != checkpoint.uidValidity()) {
    // Mailbox identity epoch changed.
    // Do not continue incremental scan with old UID.
    throw new MailboxCheckpointChangedException();
}

Message[] newer = uidFolder.getMessagesByUID(
        lastUid + 1,
        UIDFolder.LASTUID
);
~~~

**MailboxCheckpointChangedException** and **checkpoint** are application-defined components. **UIDFolder.LASTUID** is a constant used by the API to represent the highest upper bound in certain UID operations.

### Handling UID Gaps Carefully

UIDs do not have to be contiguous. For instance, a server having UIDs 101, 104, and 108 is completely normal. Do not assume every integer from 101 to 108 must have a corresponding message.

### Checkpoints Must Not Advance Ahead of Business Commits

A common worker mistake:

~~~text
1. Find UIDs 104, 108.
2. Save checkpoint=108.
3. Process UID 104 -> succeeds.
4. Process UID 108 -> fails.
5. Next scan starts at UID >108 -> skips UID 108.
~~~

To avoid skipping messages:

- Store processing outcomes per UID using a **unique key**.
- Only advance the checkpoint over UID ranges safely processed or recorded.
- Allow overlapping scans and deduplicate.
- Maintain separate retries for failed UIDs.
- When `UIDVALIDITY` changes, switch to a policy-driven full/incremental resynchronization.

### Checkpoints Are Only an Optimization

Even when the app saves the last UID, older emails may still be flagged UNSEEN again or moved into the folder by another client. If the requirement is processing "all newly arrived mail", UID checkpoints fit; if the requirement is "all currently unread mail", search by SEEN or combine states. The two problems are not identical.

### Reading in Batches Instead of the Whole Mailbox

When a folder contains very many messages:

1. Use SEARCH/UID to select candidates.
2. Cap batch size and concurrency.
3. Prefetch needed metadata.
4. Fetch each candidate's body in a controlled manner.
5. Persist results and checkpoints at the right transaction boundaries.
6. Close Folder/Store or reuse connections according to the designed lifecycle.

Never build an array of hundreds of thousands of `Message` objects and call `getContent` in unbounded parallel: it can exhaust the heap, socket pools, and trigger provider throttling.

## 16. Using FetchProfile to Fetch Metadata Efficiently

Jakarta Mail has **FetchProfile** to prefetch selected information for multiple messages instead of querying each property over many network round trips.

~~~java
import jakarta.mail.FetchProfile;
import jakarta.mail.Message;

Message[] candidates = inbox.search(
        new FlagTerm(
                new Flags(Flags.Flag.SEEN),
                false
        )
);

FetchProfile profile = new FetchProfile();
profile.add(FetchProfile.Item.ENVELOPE);
profile.add(FetchProfile.Item.FLAGS);

inbox.fetch(candidates, profile);

for (Message m : candidates) {
    System.out.println(m.getSubject());
    System.out.println(m.isSet(Flags.Flag.SEEN));
}
~~~

The example assumes imports for **Flags** and **FlagTerm** are present. **ENVELOPE** covers common header metadata and **FLAGS** covers flags; exact optimization depends on the provider. Prefetching does not mean attachments have been downloaded.

### FetchProfile Differs from getContent

Fetching metadata must not be confused with downloading the entire body. For mailboxes acting as queues, prioritize metadata first to inspect:

- UID/UIDVALIDITY.
- Subject/sender/timestamp if routing is needed.
- Flags and fast conditions.
- Size or MIME structure when supported by the provider.

Only after deciding to process, download the body and attachments. This lowers cost and limits unintended side effects on `SEEN`.

### Batching Does Not Turn IMAP into a Transactional Database

Even after `inbox.fetch(candidates, profile)` returns successfully, another client can still delete, move, or change flags. Never treat a batch fetch like strong database snapshot isolation; code must handle **MessageRemovedException**, `FolderClosedException`, and invalidated results.

## 17. Distinguishing Header, text/plain, and Multipart Reading

A message body may be:

- **text/plain** — plain text.
- **text/html** — HTML content.
- **multipart/alternative** — alternative representations (plain/HTML).
- **multipart/mixed** — text with attachments.
- **multipart/related** — HTML and linked resources such as inline images.
- **message/rfc822** — another email attached inside.

Simple code:

~~~java
if (message.isMimeType("text/plain")) {
    String text = (String) message.getContent();
    // Process text after enforcing size limits.
}
~~~

This only works when the message root itself is `text/plain`; many real-world emails are multipart. Never write:

~~~java
String body = (String) message.getContent();
~~~

for arbitrary messages, because `getContent()` can return **Multipart**, **InputStream**, or another type.

### Illustrative Multipart Traversal Example

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static void visitParts(Part part, int depth)
        throws Exception {
    if (depth > 8) {
        throw new IllegalArgumentException(
                "MIME nesting too deep"
        );
    }

    if (part.isMimeType("text/plain")) {
        Object content = part.getContent();
        if (content instanceof String text) {
            System.out.println(
                    "Text length: " + text.length()
            );
        }
    } else if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        for (int index = 0;
             index < multipart.getCount();
             index++) {
            BodyPart child = multipart.getBodyPart(index);
            visitParts(child, depth + 1);
        }
    } else {
        System.out.println(
                "Part type: " + part.getContentType()
        );
    }
}
~~~

The example illustrates MIME structure; it is not a full production parser. In practice you also need:

- Size limits per message and per part.
- Limits on part count and nesting depth.
- Avoiding loading entire attachments into RAM.
- Handling unusual charsets and malformed MIME.
- Malware/security policy checks on attachments.
- Never rendering unsanitized HTML in internal browsers.
- Protection against zip bombs, oversized content, or external tracking image URLs.

**Specifically:** calling **part.getContent()** in examples can pull the body and affect `SEEN` depending on the IMAP implementation. To preserve unread state until after processing, use `READ_ONLY` or peek/fetch behavior verified against your provider.

## 18. Reading and Marking SEEN in the Right Order

A mail-receiving service that creates tickets can be organized as:

~~~text
Poll inbox
    |
    v
Find candidates via IMAP search/UID
    |
    v
Read metadata and UIDVALIDITY
    |
    v
Try atomic claim by application message key
    |
    +-- Already processed/in progress -> Skip
    |
    '-- Claim succeeded
            |
            v
        Fetch body using peek policy
            |
            v
        Validate, parse, store attachment safely
            |
            v
        Persist business result in DB transaction
            |
            v
        Mark application record PROCESSED
            |
            v
        Optionally set SEEN via IMAP
            |
            v
        Record flag-sync status/result
~~~

### Why Set SEEN After the DB Commit?

If `SEEN` is marked before the ticket-creation transaction commits, rolling back the transaction leaves the email read without a corresponding ticket. If setting `SEEN` after the DB commit fails, a later poll may still see the message as `UNSEEN`; the processed-message table and dedup key prevent creating a second ticket.

**This is at-least-once + idempotent processing**, not an atomic transaction spanning IMAP and the database. The two systems do not share a single transaction when using only Jakarta Mail and JDBC.

### What If Users Want Messages to Stay Unread?

An application monitoring a support queue may not want to mutate mailbox state managed by humans. In that case, record **PROCESSED** only in the database and leave `SEEN` untouched. There is no requirement that every automated email must be marked as read.

### Should You Mark Flagged or Move Folders?

Some workflows use **FLAGGED** or move messages to a **Processed** folder instead of `SEEN`. This can aid support workflows, yet still requires durable internal state and dedicated move/copy handling. Never use `SEEN` as the sole mechanism guaranteeing each message is processed once.

## 19. Designing a Processing State Table Separate from SEEN

When an inbox feeds an automated workflow, persist idempotency state in the database. An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE inbound_mail_processing (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    mailbox_id VARCHAR(120) NOT NULL,
    folder_name VARCHAR(500) NOT NULL,
    uid_validity BIGINT NOT NULL,
    message_uid BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    lease_owner VARCHAR(120),
    lease_until TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    received_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    flag_sync_status VARCHAR(40),
    last_error_category VARCHAR(80),
    CONSTRAINT uq_inbound_mail_source
        UNIQUE (
            tenant_id,
            mailbox_id,
            folder_name,
            uid_validity,
            message_uid
        )
);
~~~

This is an application-designed table, not provided out of the box by Spring Framework Mail or Jakarta Mail. Statuses may include:

| Status | Meaning | Action |
| --- | --- | --- |
| **DISCOVERED** | UID has been discovered | Awaiting claim |
| **PROCESSING** | Worker is processing | Held with lease and heartbeat as needed |
| **PROCESSED** | Business outcome persisted | Do not repeat work; optionally sync SEEN |
| **RETRY_WAIT** | Transient failure | Bounded retry |
| **PERMANENT_FAILED** | Unprocessable data | Review or quarantine |
| **NEEDS_REVIEW** | Business outcome unclear | Do not auto-retry ambiguous side effects |

**flag_sync_status** is a separate dimension, such as **NOT_REQUESTED**, **PENDING**, **SYNCED**, **FAILED**, to track marking `SEEN` after business processing completes.

### Why Is a Unique Constraint Needed?

Two workers may discover UID 108 simultaneously. If both try to insert the source record:

~~~text
Worker A INSERT mailbox + UIDVALIDITY + UID
Worker B INSERT mailbox + UIDVALIDITY + UID
~~~

The constraint prevents creating two source records. However, **a single unique insert is not enough** if two workers can still claim an existing record: atomic claim/lease or row-level locking is also needed when executing business side effects.

### Processed Records Do Not Replace Handling UIDVALIDITY Changes

If `INBOX`'s `UIDVALIDITY` changes, the same numeric UID 108 can represent a different message. That is why **uid_validity** is part of the unique key. A mailbox reset/restore may require rescanning; never rely on old UIDs in a new epoch.

### No Need to Store Full MIME in the Tracking Table

Keep only metadata: mailbox, folder, UID, status, timestamps, and error category. Email bodies and attachments can contain sensitive data and should be stored in properly permissioned, encrypted locations with business-driven retention. Never put raw bodies or access tokens into error logs just for debugging convenience.

## 20. Claiming Mail-Receiving Work Using the Database

A safe worker usually splits into two phases:

1. Poll IMAP to discover UIDs and record them in the processing table.
2. Workers claim `DISCOVERED`/`RETRY_WAIT` records in the database to process.

With multiple workers, claiming must be atomic:

~~~sql
WITH next_mail AS (
    SELECT id
    FROM inbound_mail_processing
    WHERE status IN ('DISCOVERED', 'RETRY_WAIT')
      AND (lease_until IS NULL OR lease_until <= CURRENT_TIMESTAMP)
    ORDER BY first_seen_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE inbound_mail_processing AS p
SET
    status = 'PROCESSING',
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = p.attempt_count + 1
FROM next_mail
WHERE p.id = next_mail.id
RETURNING
    p.id,
    p.mailbox_id,
    p.folder_name,
    p.uid_validity,
    p.message_uid;
~~~

This SQL is a PostgreSQL illustration, not a default Spring Mail API. Production may also require a **lease_token/version** so a worker whose lease expired cannot overwrite a newer worker's result. Workers must not hold database row locks while waiting on IMAP or calling ticket-creation APIs.

### A Hard Problem: Worker Dies After the Business Side Effect

~~~text
T1: Worker reads Message UID 108
T2: Worker creates ticket via external API
T3: Ticket creation API succeeds
T4: Worker dies before marking PROCESSED
T5: Job is reclaimed
~~~

If the ticket-creation API lacks an idempotency key, re-running the job can create two tickets. **`SEEN` cannot solve this case.**

Solutions belong at the business layer:

- Create the ticket in the same database transaction as the processed status if possible.
- Or use the target API's idempotency key and send the same key on every retry.
- Or record external requests/outcomes and reconcile when uncertain whether the side effect happened.

An example key:

~~~text
INBOUND_MAIL:
  tenant-7:
  support-mailbox-1:
  INBOX:
  uidValidity=9192:
  uid=108
~~~

Never use **message number**, which can shift on expunge.

## 21. Service Reading a UID and Marking SEEN After Commit

A clean application abstraction:

~~~java
public record InboundMailKey(
        String mailboxId,
        String folderName,
        long uidValidity,
        long uid
) {
}

public record ReceivedMailData(
        InboundMailKey key,
        String from,
        String subject,
        String plainText
) {
}

public interface InboundMailRepository {
    boolean tryClaim(InboundMailKey key);

    void markProcessed(InboundMailKey key, String businessRecordId);

    void markRetryable(InboundMailKey key, String reason);

    boolean isProcessed(InboundMailKey key);
}

public interface TicketCreationService {
    String createTicketIdempotently(ReceivedMailData mail);
}
~~~

These are illustrative application-defined interfaces. **tryClaim** must be atomic in the database and distinguish in-progress, processed, and retryable records. **createTicketIdempotently** must genuinely use the mail identifier as an idempotency key or appropriate transactional mechanism, not merely bear the word "idempotent" in its name.

### Separate Mailbox I/O from Business Transactions

A code structure:

~~~text
open IMAP folder -> get UID -> fetch content
                  |
                  v
        validate and parse message
                  |
                  v
       database transaction / business service
                  |
                  v
             commit success
                  |
                  v
     IMAP setFlag(SEEN, true) if policy requires
~~~

Do not open a **@Transactional** database transaction and hold it across IMAP connection, attachment reading, and external API calls; that keeps connections/locks open too long and increases contention risk.

### Example Handling SEEN Based on UID

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public static boolean markReadByUid(
        Folder folder,
        long expectedValidity,
        long uid
) throws Exception {
    if (!folder.isOpen()
            || folder.getMode() != Folder.READ_WRITE) {
        throw new IllegalStateException(
                "Folder must be open in READ_WRITE mode"
        );
    }

    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "Folder does not support UID"
        );
    }

    if (uidFolder.getUIDValidity() != expectedValidity) {
        return false; // Do not mark the wrong UID epoch.
    }

    Message message = uidFolder.getMessageByUID(uid);
    if (message == null) {
        return false; // Message moved or deleted.
    }

    message.setFlag(Flags.Flag.SEEN, true);
    return true;
}
~~~

**markReadByUid(...)** only confirms the `setFlag` call succeeded, not that the business record committed; call it **after** business logic is safely processed. Depending on requirements, you can re-read **isSet(SEEN)** or sync later to observe server state, as sessions/networks can change.

### What If setFlag Fails?

The application can record:

~~~text
Business state: PROCESSED
Flag sync:      FAILED
Error category: FOLDER_READ_ONLY / NETWORK / MESSAGE_REMOVED
~~~

A dedicated flag-sync worker can retry by `UIDVALIDITY + UID`. Never re-run ticket creation merely because the `SEEN` flag update did not succeed.

## 22. Distinguishing Automatic Flags from Business-Logic-Set Flags

When an IMAP client downloads content, the server may set `\Seen`. When the app calls **setFlag(SEEN, true)**, that is a direct write request. Both mechanisms can affect state:

~~~text
Initial message: UNSEEN
       |
       +-- FETCH BODY (without peek) -> may become SEEN
       |
       '-- Business processed -> setFlag(SEEN, true) -> SEEN
~~~

Therefore clearly define the **intended moment** a message becomes read:

| Scenario | Suitable Organization |
| --- | --- |
| App only displays a list | `READ_ONLY` or metadata fetch, do not alter SEEN |
| Preview body while keeping unread | `READ_ONLY` or verified `PEEK` with tests |
| User clicks "Mark as read" | `READ_WRITE` + `setFlag(SEEN, true)` |
| User clicks "Mark as unread" | `READ_WRITE` + `setFlag(SEEN, false)` |
| Bot creates tickets from email | Separate processed state, optionally sync SEEN after commit |
| Move email after processing | Manage destination UID/folder and copy/move separately |

A webmail design might mark read when **the user opens the email**, whereas a triage bot only reads metadata and never touches `SEEN`. That is a product decision, not a requirement imposed by the JavaMail API.

## 23. READ_ONLY, READ_WRITE, and Permission to Change SEEN

A folder can be opened:

~~~java
folder.open(Folder.READ_ONLY);
~~~

In this mode, the application must not assume it can set flags. When `SEEN` needs to be set, use `READ_WRITE`:

~~~java
folder.open(Folder.READ_WRITE);
~~~

If a folder is already open `READ_ONLY`, do not call `open` a second time on the same folder without closing per lifecycle; close and reopen in the needed mode or use a separate flow with write access.

### Why Separate Read-Only Workers and Flag-Sync Workers?

In a multi-consumer system:

~~~text
Mailbox Poller (READ_ONLY/peek)
          |
          v
Discover UID -> DB job
          |
          v
Business Worker -> persist result
          |
          v
Flag Sync Worker (READ_WRITE)
          |
          v
Set SEEN / FLAGGED / move if policy
~~~

Benefits:

- The poller does not accidentally alter unread counts.
- A `WRITE` folder is not held open across long business transactions.
- Flag-sync retries do not re-execute business side effects.
- Mailbox access permissions can be scoped per role.

The downside is extra steps and eventual consistency, so use it only when the product genuinely needs independent processing and duplicate risk exists.

### Does close(false) Roll Back SEEN?

**No.** In IMAP, setting `SEEN` is usually a server-side operation. **close(false)** only avoids requesting expunge of `DELETED` messages upon closing; it does not roll back flag modifications already performed.

## 24. Marking Multiple Messages and Avoiding Races with Users

Suppose a UI has a **Mark selected as read** button. Multiple selected messages must be identified by UID rather than message numbers across requests.

Request pattern:

~~~text
POST /mailboxes/{mailboxId}/folders/{folderId}/mark-read
{
  "uidValidity": 19220,
  "uids": [104, 108, 110]
}
~~~

The application needs:

1. Authorization for the mailbox/folder.
2. Cap on the number of UIDs per request.
3. Open the folder `READ_WRITE`.
4. Verify `UIDVALIDITY`.
5. Resolve each UID to an existing `Message`.
6. Set flags on authorized `Message`s.
7. Report results for updated UIDs and UIDs already moved/deleted.

Never allow clients to pass arbitrary IMAP hostnames/credentials or folder names if the API should only operate on assigned mailboxes. Mailbox identity and folder scope must be server-controlled.

### Bulk setFlags via Folder

~~~java
import jakarta.mail.Flags;
import jakarta.mail.Message;

Message[] messages = ...; // Resolve from valid UIDs.

if (messages.length > 0) {
    folder.setFlags(
            messages,
            new Flags(Flags.Flag.SEEN),
            true
    );
}
~~~

Never pass an array containing `null` elements when a UID no longer exists. Resolution must filter and bound, especially on mailboxes shared by multiple concurrent clients.

### Race Between Mark Read and Mark Unread

~~~text
T1 Client A: Mark as read
T2 Client B: Mark as unread
T3 Server applies the last operation
~~~

There is no guarantee whether client A or B "wins" on concurrent operations if the app lacks a conflict policy. If the product requires per-user read status, **IMAP `\Seen` on a shared mailbox is insufficient**: maintain a **user_message_read_state** table in the application keyed by user ID rather than relying on one shared flag for everyone.

## 25. Shared Mailbox: Is SEEN Shared or Per-User?

A support mailbox shared by 20 staff members may display `SEEN` once a single staff member reads a message. That does not mean "all 20 staff members have read it".

### Two Experience Models

**Model A — Shared \Seen**:

~~~text
support@example.test / INBOX
Message M: SEEN
~~~

Every client connected to the same mailbox observes the shared status (provider-dependent). Suitable if the team wants to see whether someone opened the message, but does not satisfy per-user requirements.

**Model B — Application Per-User Read State**:

~~~text
Message M:
  Alice -> READ
  Bob   -> UNREAD
  Cara  -> READ
~~~

To support Model B, an example table is needed:

~~~sql
CREATE TABLE user_mail_read_state (
    user_id VARCHAR(120) NOT NULL,
    mailbox_id VARCHAR(120) NOT NULL,
    folder_name VARCHAR(500) NOT NULL,
    uid_validity BIGINT NOT NULL,
    message_uid BIGINT NOT NULL,
    read_at TIMESTAMPTZ,
    PRIMARY KEY (
        user_id,
        mailbox_id,
        folder_name,
        uid_validity,
        message_uid
    )
);
~~~

In this setup, read state inside the app will not completely match `\Seen` on IMAP. That may be intentional behavior. Explain it clearly in the UI so staff are not confused.

### Shared Mailboxes Also Need Work Assignment

**READ/UNREAD** must not replace ticket statuses like **ASSIGNED, IN_PROGRESS, RESOLVED**. A message that has been read but not yet answered must not be considered resolved; ticket states must be managed by dedicated business logic.

## 26. Deleting, Copying, and Moving Folders Differ from Marking as Read

Flags serve distinct purposes. **SEEN** only records read status, whereas **DELETED** signals deletion on IMAP, and move/copy operations change message location.

### Marking DELETED Does Not Necessarily Delete Immediately

~~~java
message.setFlag(Flags.Flag.DELETED, true);
~~~

The message may remain in the folder and stay visible until the server performs an **expunge**, depending on server/client policies. Never substitute `DELETED` for `SEEN`.

### close(true) Can Cause Message Loss

~~~java
folder.close(true);
~~~

The `true` parameter requests expunging messages marked `DELETED` in the folder. It does not merely "close the connection cleanly"; in a shared mailbox, this can also expunge messages marked `DELETED` by other clients.

For workers that only mark as read:

~~~java
folder.close(false);
~~~

and avoid unintended expunges. If actual deletion/moving is needed, require an approved workflow, proper permissions, audit logging, and testing for server-specific impact.

### Copying Messages

Jakarta Mail provides **Folder.copyMessages(...)**:

~~~java
Folder destination = store.getFolder("Processed");
if (!destination.exists()) {
    throw new IllegalStateException(
            "Destination folder does not exist"
    );
}

inbox.copyMessages(
        new Message[] {message},
        destination
);
~~~

The example assumes valid source/destination folders and server copy support. Copying **does not delete the original**; the message can appear in both folders with different UIDs. If implementing "move" via copy followed by `DELETED`/expunge, account for failure windows: copy succeeding while original deletion fails leaves two copies; deleting too early risks data loss.

### Move Extensions Are Not Always Portable

Some IMAP providers support the MOVE extension or proprietary APIs. Core Jakarta Mail `Folder` does not guarantee an atomic move across every backend. If using an implementation-specific IMAP move API, check version and capabilities and provide an appropriate fallback.

### When Moving Messages, UID Data Changes

~~~text
INBOX:
  UIDVALIDITY 100, UID 25
        |
        v
COPY/MOVE
        |
        v
Processed:
  UIDVALIDITY 180, UID 999
~~~

If the app tracks state by source UID, preserve the mapping and avoid reprocessing the moved copy as a new business notification when that is unintended.

## 27. Folder Counts and Unread Count

Folder provides counting methods such as:

~~~java
int total = folder.getMessageCount();
int unread = folder.getUnreadMessageCount();
~~~

With IMAP, the server/provider can report unseen message counts. However:

- Counts can change while other clients receive, delete, or change flags.
- Some servers/implementations return special values when exact counts are unknown or unsupported.
- Counts on open vs. closed folders can behave differently.
- On large mailboxes, frequent count queries can add load.

### Counts Are Not Immutable Snapshots

Example:

~~~text
T0 getUnreadMessageCount() -> 10
T1 Another client marks 3 messages as read
T2 search(UNSEEN) -> 7 messages
~~~

There is no logic bug if the two results differ. If the UI needs strong consistency over a window, design caching/versioning or accept eventual consistency. Never use count alone as proof of processing progress.

### Do Not Infer "Unprocessed" from Unread Count

A support mailbox showing 0 unread does not mean all tickets have been created. Staff may read manually, increasing `SEEN`, before the bot processes them. Conversely, a mailbox showing 30 unread may include emails already processed by the bot while intentionally kept unread.

Dashboards should separate:

~~~text
IMAP unread_count = server-reported inbox status
App pending_count = unprocessed UIDs in DB
App processed_count = business-processed UIDs
Flag_sync_failed_count = processed results whose flags were not updated
~~~

## 28. POP3 and Limitations of Marking as Read

POP3 primarily provides commands to list, download, and delete messages in a mailbox, without an IMAP-equivalent folder and **\Seen** model.

Jakarta Mail example:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

Properties props = new Properties();
props.put("mail.store.protocol", "pop3s");
props.put("mail.pop3s.connectiontimeout", "5000");
props.put("mail.pop3s.timeout", "10000");

Session session = Session.getInstance(props);
Store store = session.getStore("pop3s");
Folder inbox = null;

try {
    store.connect(host, 995, username, password);
    inbox = store.getFolder("INBOX");
    inbox.open(Folder.READ_ONLY);

    for (Message message : inbox.getMessages()) {
        System.out.println(message.getSubject());
    }
} finally {
    if (inbox != null && inbox.isOpen()) {
        inbox.close(false);
    }
    if (store.isConnected()) {
        store.close();
    }
}
~~~

This is an example of reading over POP3S; it does not demonstrate a server-side mark read/unread API because POP3 lacks an IMAP-equivalent flag system.

### If Business Logic Needs Read Status with POP3

You can persist state in the application database keyed by POP3 message identifier (such as **UIDL** if supported by the server and exposed by the implementation), account identity, and retention policy. "Read" status is then an **application-level state**, not an IMAP `SEEN` flag synchronized with webmail.

Never use POP3 message ordinal numbers as stable IDs across downloads if the mailbox can delete/change messages. If syncing read/unread across devices is the goal, consider IMAP instead of trying to emulate full behavior on POP3.

## 29. Polling and Notifications When the Inbox Changes

The application can read the mailbox periodically:

~~~text
Every 30 seconds:
  Connect IMAP
  Open INBOX
  Search new/eligible messages
  Process candidates
  Close folder/store
~~~

Or maintain a connection waiting for change notifications via features like **IMAP IDLE** when supported by server and implementation.

### Scheduled Polling

Pros:

- Easy to understand and broadly compatible with Jakarta Mail.
- Straightforward to manage timeouts, reconnects, and batches.
- No need to hold a long-lived connection open.

Cons:

- Maximum latency roughly equals the polling interval.
- Calling search too frequently can create load.
- Must be careful when multiple replicas poll concurrently.

With Spring Boot, you can use **@Scheduled**:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InboxPollingJob {

    private final InboxPollingService service;

    public InboxPollingJob(InboxPollingService service) {
        this.service = service;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.inbox.poll-delay-ms:30000}"
    )
    public void run() {
        service.pollOnce();
    }
}
~~~

**InboxPollingService** is an application-defined interface/service. Enable scheduling in the Spring context, e.g., **@EnableScheduling**, if not already enabled. Never let each replica independently process the same mailbox without atomic claims/dedup.

### IMAP IDLE and Push Notifications

IMAP has an IDLE mechanism allowing clients to wait for server notifications when the mailbox changes. However:

- The generic Jakarta Mail **Folder** API does not mandate a portable `idle` method across all providers.
- Some implementations offer an `IMAPFolder` class with its own **idle(...)**.
- Connections can be closed by server timeouts or network proxies.
- When notified of changes, you still must fetch/search/check UIDs to identify actual messages.
- Reconnect/backoff and post-disconnect state reconciliation are required.

**IDLE does not turn IMAP into an exactly-once message queue.** If a notification is lost during a network drop, the application must scan UIDs/checkpoints after reconnecting.

### Never Hold a Connection Forever Without Health Checks

A worker running for days needs to handle `StoreClosedException`, timeouts, connection resets, and credential rotation. Use a reconnect loop with backoff/jitter, cap connections per account, and separate application liveness from a specific mailbox's health.

## 30. Security and Resource Limits When Reading Mail

Email comes from an external environment and may contain untrusted data. Even though a message already sits in a corporate mailbox, its body, headers, and attachments may still be attacker-controlled.

### Risks to Mitigate

| Risk | Example | Mitigation |
| --- | --- | --- |
| **Spoofed sender** | `From` spoofing the accounting department | Never authorize business actions solely by `From` |
| **HTML injection** | HTML body containing malicious markup | Never render raw HTML; sanitize/escape per context |
| **Unsafe attachment** | Script or archive containing dangerous payloads | Allowlist, malware scanning, size limits |
| **Path traversal** | Filename containing relative path segments | Server-generated storage keys; filename as metadata only |
| **Decompression bomb** | Compressed attachment expanding massively | Cap resources and file types |
| **Privacy leak** | Logging bodies containing OTPs/tokens | Redact, access control, retention |
| **Credential exposure** | Printing IMAP passwords/OAuth tokens | Secrets manager, disable raw protocol debug |
| **Excessive polling** | Hundreds of replicas connecting every second | Rate limits/concurrency/scheduling |
| **Race/duplicate** | Two workers processing the same UID | DB unique keys, atomic claims, idempotent side effects |
| **Unwanted read flags** | Previewing body auto-sets `SEEN` | `READ_ONLY`/peek, test the specific provider |

### Never Trust Filenames from Message.getFileName()

Attachment filenames are sender-supplied data and may contain unusual encodings, path separators, or control characters. Never use them directly as filesystem paths:

~~~java
String suppliedFileName = bodyPart.getFileName();
// Do not use: uploadDir.resolve(suppliedFileName)
~~~

Instead, use a server-generated storage key, store a normalized/bounded display filename separately, and apply content-type validation matching the actual content.

### Do Not Download All Attachments Just to Mark Read

If you only need to toggle `SEEN`, there is no need to call `getContent` or download the full MIME. Just resolve UID → Message → `setFlag(SEEN, true)`, reducing network, CPU, and exposure to malicious payloads. Separating "mark as read" from "inspect content" keeps the API easier to test and safer.

### Transport Authentication

To protect IMAP credentials and email content over the network, use TLS with certificate/hostname verification, finite timeouts, and appropriate server/auth policies. Never use trust-all in production, and never disable certificate verification as a quick fix for a connection error.

### Least Privilege for Mailboxes

If a service only needs to read and index, prefer read-only permissions if the provider supports granular permissions. A service marking `SEEN` needs flag-write permission, not necessarily permission to delete the whole mailbox. If the server lacks fine-grained permissions, enforce restrictions in the application and audit destructive operations like delete/expunge.

## 31. Testing Folder, Message, and SEEN in an Isolated Environment

A valuable integration test works against a **real IMAP server in a test environment**, rather than merely mocking `Message` methods. It should verify:

1. A new message appears in INBOX.
2. The message initially lacks `SEEN` when supported by the fixture.
3. Searching via `FlagTerm` finds the unread message.
4. Opening `READ_WRITE` and calling `setFlag(SEEN, true)` persists read status on the server.
5. Calling `setFlag(SEEN, false)` clears the flag on the server.
6. Reading the body in peek mode does not unintentionally set `SEEN`.
7. `READ_ONLY` cannot be used to perform flag writes.

### Using GreenMail for Test SMTP Delivery and IMAP Reading

A fixture running both protocols on loopback:

~~~text
JUnit test
   |
   +-- JavaMailSender -> GreenMail's SMTP port
   |                        |
   |                        v
   |                  Test mailbox
   |                        |
   '-- Jakarta Mail Store -> GreenMail's IMAP port
                                 |
                                 v
                         Read / set SEEN / search
~~~

JUnit/Jakarta Mail example using GreenMail (a Jakarta Mail-compatible version):

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.Flags;
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import jakarta.mail.search.FlagTerm;
import java.util.Properties;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class ImapSeenIntegrationTest {

    private GreenMail mailServer;

    @BeforeEach
    void start() {
        mailServer = new GreenMail(
                new ServerSetup[] {
                        new ServerSetup(
                                0, "127.0.0.1",
                                ServerSetup.PROTOCOL_SMTP
                        ),
                        new ServerSetup(
                                0, "127.0.0.1",
                                ServerSetup.PROTOCOL_IMAP
                        )
                }
        );
        mailServer.start();
        mailServer.setUser(
                "reader@local.test",
                "reader",
                "test-secret"
        );
    }

    @AfterEach
    void stop() {
        if (mailServer != null) {
            mailServer.stop();
        }
    }

    private void deliverTestMessage() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(mailServer.getSmtp().getPort());

        var mime = sender.createMimeMessage();
        var helper = new MimeMessageHelper(mime, false, "UTF-8");
        helper.setFrom("sender@local.test");
        helper.setTo("reader@local.test");
        helper.setSubject("SEEN check message");
        helper.setText("Test content.");
        sender.send(mime);

        assertTrue(mailServer.waitForIncomingEmail(5000, 1));
    }

    @Test
    void searchUnreadThenMarkReadAndUnread() throws Exception {
        deliverTestMessage();

        Properties props = new Properties();
        props.put("mail.store.protocol", "imap");
        Session session = Session.getInstance(props);

        Store store = session.getStore("imap");
        Folder inbox = null;
        try {
            store.connect(
                    "127.0.0.1",
                    mailServer.getImap().getPort(),
                    "reader",
                    "test-secret"
            );

            inbox = store.getFolder("INBOX");
            inbox.open(Folder.READ_WRITE);

            Message[] unread = inbox.search(
                    new FlagTerm(
                            new Flags(Flags.Flag.SEEN),
                            false
                    )
            );
            assertEquals(1, unread.length);

            Message message = unread[0];
            assertFalse(message.isSet(Flags.Flag.SEEN));

            message.setFlag(Flags.Flag.SEEN, true);
            assertTrue(message.isSet(Flags.Flag.SEEN));

            message.setFlag(Flags.Flag.SEEN, false);
            assertFalse(message.isSet(Flags.Flag.SEEN));
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

**This is non-TLS IMAP testing on loopback, used only to verify flags and folder lifecycles.** Never use real credentials or send mail over the Internet. To test IMAPS/TLS/hostname verification, use an SSL fixture with its own certificate, a test truststore, and invalid-certificate cases; never treat this plaintext test as proof of secure production connectivity.

### Why Add a Reopen Test?

In the test above, **message.isSet(...)** immediately after `setFlag` might read cached state within the same session. To verify the server actually persisted the flag, an additional integration test should:

1. Capture `UID`/`UIDVALIDITY`.
2. Call `setFlag(SEEN, true)`.
3. Close `Folder` and `Store`.
4. Open a brand-new connection.
5. Fetch the `Message` again by UID and assert `SEEN` persists.

This is a stronger test for **server persistence** and catches mock implementations that only mutate flags locally.

### Testing Body Peek

With an initially `UNSEEN` message:

~~~text
Given:
  IMAP folder READ_WRITE
  mail.imap.peek=true
  message UNSEEN
When:
  getContent() / fetch body
Then:
  server-side SEEN remains false
~~~

The test must reopen on a separate connection to observe the flag independently. Behavior of the `peek` property can vary across Jakarta Mail implementations/versions; test against the real provider/fixture instead of asserting with mocks.

### Testing READ_ONLY

~~~text
Given:
  Folder open READ_ONLY
When:
  setFlag(SEEN, true)
Then:
  write operation is rejected
  server-side SEEN is unchanged
~~~

Depending on the provider, the API may throw **IllegalWriteException** or an appropriate `MessagingException`; the test should confirm server state remains unchanged rather than asserting only a specific exception message.

## 32. Edge-Case Tests You Should Have

A practical test suite can expand along this matrix:

| Test | Setup | Expected |
| --- | --- | --- |
| Nonexistent folder | Wrong folder name | Do not attempt `getMessages`; report meaningful error |
| Empty folder | INBOX `count=0` | Do not call `getMessage(0)` |
| Read-only folder | `READ_ONLY` + mark `SEEN` | Write rejected, flag unchanged |
| Read-write folder | `READ_WRITE` + mark `SEEN` | Persists `SEEN` |
| Mark unread | `SEEN` true then set false | `UNSEEN` |
| Search unread | One `SEEN`, one `UNSEEN` | Returns only `UNSEEN` |
| Body preview | Peek + `READ_WRITE` | Does not auto-set `SEEN` |
| Fetch without peek | Provider with auto-`SEEN` | Verify potential side effect |
| Message deleted/expunged | Message disappears after search | Handle missing message without crashing whole batch |
| `UIDVALIDITY` changed | Mailbox rebuilt | Do not process against old checkpoint |
| Multiple clients | Two workers see same UID | Database dedup creates only one ticket |
| Business commit fails | Read succeeds, save fails | Do not mark processed/`SEEN` per policy |
| Flag-sync fails | Ticket saved, IMAP fails | Do not create duplicate ticket on retry |
| Connection reset | Store/Folder drops abruptly | Safe reconnect/retry |
| Multipart | Plain/HTML/attachments | Bounded parse, no bad casts |
| Shared read state | User A reads, user B unread | Per-user app state if required |
| POP3 | Message downloaded via POP3S | Do not assume server supports `SEEN` |

### Testing Commit Before Marking

A useful failure-injection test:

~~~text
T1 Poll sees UID=108
T2 Body parse succeeds
T3 Ticket service throws exception before commit
T4 Worker aborts attempt
Expected:
  inbound_mail_processing is not PROCESSED
  worker did not set SEEN
~~~

If the goal is preserving unread counts when parsing fails, ensure before T2 that the body is fetched with **peek or READ_ONLY**; if `getContent` already made the server set `SEEN`, deciding at T4 not to call `setFlag` will not restore the original state.

### Testing Replay of the Same UID

~~~text
Given:
  UID 108 processed successfully, ticket #42 exists
When:
  IMAP poll sees UID 108 again
Then:
  no new ticket created
  flag-sync may retry if it failed previously
~~~

If `UIDVALIDITY` changes, the test must confirm the same UID 108 in the new epoch is a distinct source key and is not mistakenly suppressed by the old record.

## 33. Observability and Troubleshooting When Reading Mailboxes

A mail-receiving application needs to monitor both network/IMAP health and business processing progress.

### Suggested Metrics

| Metric | Meaning |
| --- | --- |
| **mail_inbox_poll_total{result}** | Count of successful/failed polls |
| **mail_inbox_poll_duration_seconds** | Poll/fetch duration |
| **mail_inbox_discovered_messages_total** | Count of newly observed UIDs |
| **mail_inbox_processing_total{outcome}** | Processing counts by outcome |
| **mail_inbox_processing_pending** | Count of records not yet `PROCESSED` |
| **mail_inbox_flag_sync_failures_total** | Failures setting `SEEN`/moving messages |
| **mail_inbox_unread_messages** | Server-reported unread count |
| **mail_inbox_checkpoint_age_seconds** | Age of last successful checkpoint/poll |
| **mail_inbox_connection_failures_total** | Connection/auth/TLS errors |
| **mail_inbox_retries_total{reason}** | Business processing retry count |

These are application-designed metrics, **not built into Spring Framework Mail**. Avoid labels keyed by message UID, email address, or ticket ID due to cardinality explosion and privacy risks.

### Structured Logs

~~~text
event=inbound_mail_processing_completed
mailbox_id=support-1
folder=INBOX
uid_validity=19220
uid=108
processing_id=opaque-42
outcome=PROCESSED
flag_sync=SYNCED
duration_ms=281
~~~

This information is enough to correlate source messages and processing records without printing `Subject`, `From`, OTPs, bodies, or attachments.

### Dashboard Separating Mailbox Flags and App State

A clear dashboard might display:

~~~text
IMAP unread:           43
App discovered:        58
App processing:         3
App retry wait:         2
App processed today:  870
Flag sync failed:       5
Last successful poll:   2m ago
UIDVALIDITY changed:    0
~~~

**IMAP unread=43** and **App pending=5** do not necessarily contradict each other: some emails may have been read manually, or the application may have a policy against marking read. Clarify semantics before creating alerts.

### Common Failure Scenarios

| Symptom | Suspected Cause | Remediation |
| --- | --- | --- |
| Authentication failed | Expired password/OAuth token, wrong mechanism | Check secret/refresh; never print credentials |
| Certificate validation failed | Wrong CA/hostname/TLS config | Check truststore; never trust-all |
| `FolderClosedException` | Server closed folder, timeout, disconnect | Reopen folder, retry via UID/dedup |
| `MessageRemovedException` | Message was expunged | Record source no longer exists; handle per policy |
| No unread found | Auto-`SEEN` on body fetch | Verify `READ_ONLY`/peek and other clients |
| Unread count drops, tickets stay flat | UI/another client read or worker marked too early | Decouple processed state and read flag |
| Duplicate tickets created | Relying on `SEEN` as a lock | Unique key + atomic claim + idempotent side effects |
| Last UID advances, mail skipped | Checkpoint advanced before commit | Overlapping scans / per-UID records |
| UID drops to low number | `UIDVALIDITY` changed, folder reset | Controlled resynchronization |
| Too many IMAP connections | Too many replicas / short poll interval | Limit concurrency/pooling and scheduling |
| Parser OOM | Large attachments/decompression | Size limits, streaming, quarantine |

### Short Runbook When "Mail Exists, but the Bot Does Not Process It"

1. Check IMAP/TLS/AUTH connectivity and last successful poll.
2. Verify the exact **mailbox ID + folder name** so you are not reading the wrong account/folder.
3. Check `UIDVALIDITY` and checkpoints.
4. Check whether **SEARCH UNSEEN** still matches your goal or another user/client already set `SEEN`.
5. Inspect the processing table by UID, status, lease, and retry errors.
6. If a business side effect had an ambiguous outcome, reconcile before retrying.
7. Check IMAP flag-sync logs and `Folder READ_ONLY`/permission errors.
8. Ensure recovery neither creates duplicate tickets nor alters flags unintentionally.

Never "quick-fix" by resetting `SEEN` to `false` across the whole mailbox or marking everything `true`; both disrupt user experience and can trigger a wave of duplicate processing.

## 34. Common Pitfalls

### Pitfall 1 — Using JavaMailSender to Read Email

**Problem:** `JavaMailSender` sends over SMTP and provides no `Store`/`Folder` for inbox syncing.

**Fix:** Use **Jakarta Mail `Session` + `Store` + `Folder` + `Message`** with IMAP/POP3 as appropriate, or build an inbound mail service with its own abstraction.

### Pitfall 2 — Calling getMessages() Before Opening the Folder

**Problem:** Certain APIs require an open folder and throw `IllegalStateException`/`MessagingException` per contract.

**Fix:** Connect `Store`, verify `folder.exists()`, open `READ_ONLY`/`READ_WRITE`, process, close.

### Pitfall 3 — Calling getMessage(0) or getMessage(count) When count=0

**Problem:** Message numbers in Jakarta Mail are 1-based.

**Fix:** Verify the folder has messages before indexing, or use `search` which returns an empty array.

### Pitfall 4 — Storing Sequence Numbers as Permanent IDs

**Problem:** Expunges shift message numbers.

**Fix:** Use `mailbox + folder + UIDVALIDITY + UID` and store state in the database.

### Pitfall 5 — Treating the Message-ID Header as an Unforgeable Key

**Problem:** Senders can set `Message-ID`, duplicate it, or omit it.

**Fix:** Use mailbox/UID keys for message sources; use `Message-ID` only to assist correlation.

### Pitfall 6 — Reading the Body Before Considering SEEN Side Effects

**Problem:** `getContent`/`getInputStream` may mark messages as read.

**Fix:** Define policy upfront, use `READ_ONLY`/peek when preserving unread is needed, and test against the real provider.

### Pitfall 7 — Calling setFlag(SEEN, true) Before Persisting Business Results

**Problem:** Worker dies after `setFlag` and before ticket creation; next poll skips the message.

**Fix:** Persist business results successfully first, then sync `SEEN`; maintain deduplication state.

### Pitfall 8 — Relying Only on SEEN to Prevent Duplicate Processing

**Problem:** Two workers can search `UNSEEN` concurrently and both process before either sets the flag.

**Fix:** Unique key + atomic claim + idempotent side effects.

### Pitfall 9 — Assuming READ_ONLY Can Set Flags

**Problem:** Servers reject flag writes in `READ_ONLY` mode.

**Fix:** Open `READ_WRITE` for setting `SEEN`/unseen, and handle permission failures.

### Pitfall 10 — Thinking close(false) Rolls Back Flags

**Problem:** The server may have already persisted `SEEN` before closing the folder.

**Fix:** Understand `close(expunge)` semantics; never treat `close` like a database rollback.

### Pitfall 11 — Calling close(true) as Default Cleanup

**Problem:** It can expunge messages already marked `DELETED`, causing unintended message loss.

**Fix:** Only expunge in explicitly authorized deletion workflows; usually pass `close(false)`.

### Pitfall 12 — Assuming POP3 Has IMAP-Like SEEN

**Problem:** POP3 offers no equivalent server-side read/unread flag system.

**Fix:** Use IMAP, or persist separate app-level state for POP3.

### Pitfall 13 — Relying on RECENT to Find Unread Mail

**Problem:** IMAP `\Recent` is not the same as `\Seen=false`.

**Fix:** Use **`FlagTerm(SEEN, false)`** or `SEARCH UNSEEN`.

### Pitfall 14 — Recreating Business Records When setFlag Fails

**Problem:** Business side effects may already have committed while only flag sync failed.

**Fix:** Separate `processing_status` and `flag_sync_status`; retry flag sync independently.

### Pitfall 15 — Skipping UIDVALIDITY Checks After Reconnect

**Problem:** Old UIDs can point to different messages once the mailbox epoch changes.

**Fix:** Compare `UIDVALIDITY` and run resynchronization when it changes.

### Pitfall 16 — Using Shared \Seen as Per-Staff Read Status

**Problem:** When one person reads a message, others see it as read before opening it.

**Fix:** Add a per-user read-state table if the UI requires individual status.

### Pitfall 17 — Concurrently Scanning Bodies of the Entire Mailbox

**Problem:** Overloads network/heap, pulls huge attachments, and unintentionally alters unread flags.

**Fix:** Server-side search/UIDs, batch metadata fetching, and body/attachment limits.

### Pitfall 18 — Trusting From or Subject to Execute Transactions

**Problem:** Headers are sender-controlled and can be spoofed.

**Fix:** Authenticate senders and business permissions with independent policies; never authorize based on email strings.

### Pitfall 19 — Failing to Close Folder/Store on Exception

**Problem:** Connection leaks, server IMAP session limits hit, and workers stall.

**Fix:** Use `finally` to call `close(false)` and `Store.close()`, with timeouts and backoff/reconnect.

### Pitfall 20 — Assuming One Folder Name Works Across All Providers

**Problem:** Sent/Trash/Spam can be renamed/localized with different delimiters.

**Fix:** Discover/configure folder mappings per account/provider; never join names like filesystem paths.

### Pitfall 21 — Forgetting the Difference Between Reading and Processing

**Problem:** Mailbox shows `unread=0` while business backlog remains huge.

**Fix:** Measure **mailbox unread** and **processing pending** separately; use business state to judge progress.

### Pitfall 22 — Giving a Service Unbounded Expunge Permissions

**Problem:** A logic bug can wipe customer emails.

**Fix:** Least privilege, auditing, and dedicated deletion workflows; never couple deletion with mark-read.

## 35. Practice Scenarios

### Scenario A — Previewing an Email While Keeping It Unread

Staff only want to preview the content of an unprocessed email.

**Question:** Is calling `getContent` on `Folder.READ_WRITE` safe for the unread state?

**Answer:** Not by default. Fetching the body can set `SEEN`; use `READ_ONLY` or provider-supported IMAP peek, and test the server-side flag after reading.

### Scenario B — User Clicks "Mark as read"

The UI wants to change the status of a specific message.

**Question:** Which operation should be used?

**Answer:** Open `Folder.READ_WRITE`, locate the message by `UID`/`UIDVALIDITY`, and call **`message.setFlag(Flags.Flag.SEEN, true)`**. Authorize mailbox/folder access and handle UIDs already moved/deleted.

### Scenario C — Marking a Message as Unread

**Question:** Is calling `setFlag(SEEN, true)` again correct?

**Answer:** No. To clear the read status, use **`setFlag(Flags.Flag.SEEN, false)`** on a writable folder.

### Scenario D — Mailbox Has 0 Messages

Code reads `count=0` and then calls `getMessage(count)`.

**Question:** What is wrong?

**Answer:** Message numbers are 1-based; there is no message 0. Handle empty folders first.

### Scenario E — Worker Set SEEN, Then Ticket Transaction Failed

After the failure, the message no longer appears in `SEARCH UNSEEN` results.

**Question:** How should it be redesigned?

**Answer:** Read with peek/`READ_ONLY` to prevent early `SEEN`, persist business state first and mark read afterward; use an independent processing table for proper retries.

### Scenario F — Two Workers Pick Up the Same Message

Both find UID 100 and call the ticket-creation API.

**Question:** Does `SEEN` act as a lock?

**Answer:** No. You need atomic claims in the database and external API idempotency to avoid creating two tickets.

### Scenario G — Folder Expunged a Message

Initially message #5 was email A; after expunge, #5 is email B.

**Question:** Why must UID be used?

**Answer:** Message numbers shift with folder structure; UID combined with `UIDVALIDITY` provides a more stable identifier within the mailbox.

### Scenario H — UIDVALIDITY Changes

The application has checkpoint `UID=900`; the server changes `UIDVALIDITY` after a restore.

**Question:** Can it continue fetching `UID > 900`?

**Answer:** No. You must handle the new epoch and resynchronize; `UID=900` from the old epoch no longer has the same meaning.

### Scenario I — POP3 Inbox Needs an Unread Button

The application uses POP3S and wants to sync `\Seen` with webmail.

**Question:** Can POP3 call `setFlag(SEEN, false)` like IMAP?

**Answer:** You cannot assume protocol support. Use IMAP if server-side read state is required, or manage separate read state in the application.

### Scenario J — Shared Mailbox with 20 Staff Members

Alice reads a message, while Bob still wants it shown as unread for himself.

**Question:** Does shared `\Seen` satisfy this?

**Answer:** Usually not. You need per-user read state in the application, separated from the IMAP shared flag.

### Scenario K — Marking Many Messages as Read

The UI sends 500 UIDs to the API.

**Question:** How should this be handled?

**Answer:** Cap element count, verify authorization and `UIDVALIDITY`, resolve existing UIDs, batch `setFlags`, and return clear results for deleted or invalid UIDs.

### Scenario L — Message Processed, but Setting SEEN Fails

The ticket was created, and the IMAP connection dropped before `setFlag` succeeded.

**Question:** Will re-polling create a second ticket?

**Answer:** It should not. The processing record marks `PROCESSED` and the idempotency key blocks duplicate ticket creation; only flag-sync retries.

### Scenario M — Two Emails Share the Same Message-ID

Someone sends two emails with identical `Message-ID` headers.

**Question:** Should they be treated as the same message?

**Answer:** Not automatically. Headers are not trusted source keys; mailbox UID and `UIDVALIDITY` distinguish the records.

### Scenario N — Calling getContent() Causes OOM

A huge attachment or anomalous compressed payload fills the heap.

**Question:** Which safeguards are appropriate?

**Answer:** Body/attachment size limits, safe streaming, malware policies, MIME nesting/part caps, and never downloading every message body just to check unread status.

### Scenario O — close(true) Used in finally

A read-only service always calls `folder.close(true)`.

**Question:** What is the issue?

**Answer:** `true` can expunge `DELETED` messages in the folder. Use `close(false)` unless an explicitly authorized workflow requires expunging.

### Scenario P — Poller Misses New Email Because Message Is Already SEEN

A staff member opens the email before the bot runs.

**Question:** Should you search by `UNSEEN` if the requirement is processing all new incoming mail?

**Answer:** Probably not. If the requirement is "all new messages", use UID discovery/checkpoints and processing state rather than relying on other clients' `SEEN` flags.

### Scenario Q — Worker Reconnects After a Day-Long Outage

The mailbox contains many new messages and changed flags.

**Question:** Should it resume from the last saved message number?

**Answer:** No. Use `UIDVALIDITY + UID` checkpoints, overlapping/dedup scans, existence checks, and idempotent per-UID processing.

### Scenario R — An Email Is Moved to Processed

The original UID in INBOX is gone; the destination folder has a new UID.

**Question:** Should the message in the destination folder be treated as a new business event?

**Answer:** Not if the workflow already processed it; maintain mappings/source keys or policies distinguishing the same email appearing in another folder.

### Scenario S — Folder.READ_ONLY Throws Error on setFlag

Code opens the folder `READ_ONLY` and calls `setFlag(SEEN, true)`.

**Question:** Does switching `setFlag` to `getFlags` fix it?

**Answer:** No. `getFlags` only reads. Updating requires opening `READ_WRITE` with server write permission.

### Scenario T — Dashboard Uses RECENT to Count Unread

The dashboard shows `recent=0` despite many unread emails.

**Question:** Which metric should be used?

**Answer:** Use the server unread count or `NOT SEEN` search, while understanding consistency limits. `RECENT` does not directly represent `UNSEEN`.

## 36. Workflow for Implementing an Inbox-Reading Application

~~~text
1. Identify the use case
   |
   +-- Render webmail?
   +-- Ticket-creating bot?
   +-- In-app email sync?
   '-- Mailbox testing?
   |
   v
2. Choose protocol
   |
   +-- IMAP/IMAPS if folders and SEEN are needed
   '-- POP3/POP3S if workflow only downloads mail and app owns state
   |
   v
3. Configure secure transport and auth
   |
   +-- TLS/hostname verification
   +-- Credentials/OAuth secrets
   +-- Connection/read/write timeouts
   '-- Rate limit/concurrency
   |
   v
4. Define folder/account scope
   |
   +-- Store.connect
   +-- Folder.exists
   +-- Folder.READ_ONLY or READ_WRITE
   '-- UIDFolder/UIDVALIDITY if available
   |
   v
5. Find candidates
   |
   +-- FlagTerm(SEEN, false) if use case = unread
   +-- UID scan if use case = new arrivals
   '-- Server-side search + batch metadata
   |
   v
6. Read needed data
   |
   +-- Subject, From, date, flags
   +-- Body with peek/READ_ONLY if keeping unread
   '-- Bounded multipart/attachments
   |
   v
7. Persist business result safely
   |
   +-- Unique mailbox + folder + UIDVALIDITY + UID
   +-- Atomic claim/idempotency
   '-- Commit success/retry status
   |
   v
8. Sync mailbox state if required by policy
   |
   +-- Open READ_WRITE
   +-- Recheck UIDVALIDITY
   +-- setFlag(SEEN, true/false)
   '-- Retry flag sync separately if it fails
   |
   v
9. Close Folder/Store and observe outcomes
   |
   +-- Poll/connection health
   +-- Processing lag
   +-- Flag sync failures
   '-- Errors without logging sensitive content
~~~

### Pre-Implementation Checklist

- **Protocol:** Does the use case truly need IMAP folders/`SEEN`, or only downloading mail with POP3?
- **Session/Store:** Connected to the right mailbox, with timeouts and TLS configured?
- **Folder mode:** `READ_ONLY` for observation, `READ_WRITE` when updating flags?
- **UID:** Source key stores accurate account/folder/`UIDVALIDITY`/UID?
- **Search:** Unread workflows use `NOT SEEN`; new-arrival workflows use UID scans?
- **Body:** Aware that `getContent` may set `SEEN`; peek behavior tested?
- **MIME:** Distinguishes plain, HTML, multipart; enforces size and attachment limits?
- **Business state:** Deduplication via unique keys/atomic claims, not `SEEN` alone?
- **Flag sync:** Updated after commit, and failure does not re-run business side effects?
- **Concurrency:** Bounded workers/connections, never sharing `Folder` arbitrarily?
- **Privacy:** Never logs raw MIME/tokens/passwords?
- **Tests:** GreenMail/IMAP fixtures verify persistence, UIDs, unread state, and failure cases?

## 37. Core Principles Summary

~~~text
JavaMailSender                  -> SMTP sending
Session + Store + Folder       -> mailbox receiving/reading
Folder.READ_ONLY               -> observe without modifying flags
Folder.READ_WRITE              -> can write flags if server allows
Message                        -> email inside a specific folder
Message number                 -> position, not a durable ID
UID + UIDVALIDITY + folder     -> better IMAP source identifier
SEEN=true                      -> read
SEEN=false                     -> unread
RECENT                         != UNSEEN
getContent / body fetch        -> may automatically add SEEN
Peek / READ_ONLY               -> protects read state per policy
search(FlagTerm(SEEN,false))   -> finds unread messages
SEEN                           != PROCESSED
SEEN                           != atomic claim
Database unique + lease        -> reduces duplicate processing
Business commit                -> before optional mark SEEN
close(false)                   != rollback flag writes
close(true)                    -> may expunge DELETED
POP3                           != IMAP flags
IMAP accepted/read             != business action completed
~~~

**Folders, messages, and marking as read** form the foundation for building mail-receiving applications with Jakarta Mail in the context of Spring Framework Mail. **Store** establishes the mailbox connection, **Folder** represents the message container, **Message** exposes metadata/body reading, and **Flags.Flag.SEEN** expresses IMAP read state. However, the unread flag is not a lock against duplicate processing, and reading a body can sometimes have the side effect of changing `SEEN`. When a system must process emails automatically, use **UID together with `UIDVALIDITY`**, persist separate business state, control transactions/retries, and update flags only when intended. Combining IMAP/POP3 in the right context, managing connection resources, testing in isolated mailboxes, and accounting for changes from multiple clients keeps inbox features stable—avoiding both dropped emails and unintended read markings.
