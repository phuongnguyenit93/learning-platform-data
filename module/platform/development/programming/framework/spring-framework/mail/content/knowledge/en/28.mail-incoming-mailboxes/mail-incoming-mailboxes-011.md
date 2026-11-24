# Handling Connection Errors When Receiving Mail

## 1. Context: Receiving Email Is Different from Sending Email in Spring

In systems using **Spring Framework Mail**, sending mail usually relies on `JavaMailSender` and SMTP. However, when an application needs to **receive mail** — such as reading a customer support inbox, fetching invoices sent to a dedicated address, processing requests arriving by email, or collecting replies from a mailbox — the problem shifts to protocols such as **IMAP** or **POP3**.

A mail-receiving service does not merely call an API to fetch a message and finish. It must deal with dropped TCP/TLS connections, mailbox server restarts, expired authentication tokens, closed folders, IMAP command timeouts, provider connection limits, and emails that were only partially processed before a worker crashed.

Without recovery design:

- Workers permanently stop receiving mail after a single network outage.
- Schedulers retry in a tight loop, increasing load on the mailbox server.
- Emails are processed twice after reconnecting.
- The application misses emails when tracking only sequential message numbers.
- One malformed email blocks the entire batch from making progress.
- Credentials, recipient addresses, and message contents are printed to debug logs.
- Opening too many IMAP/POP3 connections triggers provider rate or connection limits.

**Goal of this lesson:** accurately classify connection errors when reading a mailbox; configure TLS and timeouts; safely recover `Store`/`Folder`; retry with backoff and jitter; checkpoint by UID and process idempotently; test using a fake/mocked server; and monitor so you know the worker is genuinely receiving mail again.

~~~text
Mailbox provider (IMAP / POP3)
             |
             v
       TLS + AUTH + TCP
             |
             v
   Jakarta Mail Store / Folder
             |
             v
      Poller / Mail Receiver
             |
             +----> Retry/reconnect policy
             |
             v
     Message normalization
             |
             v
     Durable processing state
             |
             v
   Business handler / attachment
~~~

## 2. Which Tools Are Responsible for Receiving Mail?

Clearly distinguish the components:

| Component | Role | Used to receive email? |
|---|---|---|
| Spring Mail `JavaMailSender` | Create and submit email over SMTP | Not an inbound receiver |
| Jakarta Mail `Session` | Holds protocol configuration, creates `Store` | Yes |
| Jakarta Mail `Store` | Authenticates and manages the connection to the mailbox | Yes |
| Jakarta Mail `Folder` | Opens the inbox, retrieves `Message` and flags | Yes |
| Jakarta Mail `UIDFolder` | Reads UID and UIDVALIDITY on servers that support them | Yes, especially useful with IMAP |
| Spring Integration Mail | Polling/receiving adapters and integration flows | Yes, if the project uses Spring Integration |
| Spring `@Scheduled` | Triggers the poller on a schedule | Can be used to organize receiving |
| SMTP server | Accepts outgoing mail for relay/delivery to a destination | Does not replace an IMAP/POP3 mailbox reader |

**There is no direct `JavaMailReceiver` equivalent to `JavaMailSender` in core Spring Framework Mail.** To read a mailbox, you can use **Jakarta Mail** or integrate via **Spring Integration Mail**. Do not try calling `mailSender.send(...)` to "fetch mail".

With Spring Boot 3 / Spring Framework 6+, examples typically use the `jakarta.mail.*` namespace. Legacy projects on Spring Framework 5 may use `javax.mail.*`; choose the matching dependencies and do not mix both package hierarchies.

## 3. Differences Between IMAP and POP3 That Affect Recovery

| Aspect | IMAP | POP3 |
|---|---|---|
| Purpose | Work with server-side mailboxes/folders | Usually downloads mail from a single mailbox |
| Folders | Multiple folders and flags | Does not provide an IMAP-style folder hierarchy |
| Read/unread state | `\\Seen` and server-side flags | No full equivalent model |
| Durable identifier | UID scoped to mailbox and UIDVALIDITY | UIDL if supported by the server |
| Multi-device sync | Better suited | More limited |
| Safe reading approach | Open `READ_ONLY`, checkpoint UID | Download mail, retain UIDL and control deletion |
| Long-lived connection | Can be maintained, but prone to idle timeout | Usually short-lived connection per retrieval session |

In the examples in this lesson, **IMAP** is the primary choice because it supports UIDs and folders. POP3 is discussed separately where it differs in UIDL, message deletion, and recovery behavior.

### Common TLS Ports

| Protocol | Common Port | Mechanism |
|---|---|---|
| IMAPS | 993 | TLS from connection start (implicit TLS) |
| IMAP | 143 | Plain connection upgradable via STARTTLS |
| POP3S | 995 | TLS from connection start |
| POP3 | 110 | Plain connection upgradable via STLS |

These are common standard ports; enterprise services may use custom ports or endpoints. **Do not automatically disable TLS to "fix" timeouts or certificate errors.** Verify the host, port, TLS handshake mode, and server certificate appropriate for your provider.

## 4. A Mail-Receiving Error Can Occur at Many Stages

~~~mermaid
flowchart TD
    A[Start polling] --> B[DNS and TCP connection]
    B --> C{Connection succeeded?}
    C -- No --> D[DNS / firewall / network / connect timeout]
    C -- Yes --> E[TLS handshake]
    E --> F{TLS valid?}
    F -- No --> G[Certificate / hostname / protocol]
    F -- Yes --> H[Authentication]
    H --> I{Login succeeded?}
    I -- No --> J[Credential / OAuth scope / policy]
    I -- Yes --> K[Select/open mailbox folder]
    K --> L{Folder opened?}
    L -- No --> M[Folder permission / state / server BYE]
    L -- Yes --> N[Fetch messages / bodies]
    N --> O{Read succeeded?}
    O -- No --> P[Read timeout / closed folder / malformed MIME]
    O -- Yes --> Q[Process + checkpoint]
~~~

Do not label every exception as "SMTP error" or "wrong password". Each stage has a different handling strategy:

| Stage | Symptom | Handling approach |
|---|---|---|
| DNS | Unable to resolve host | Check hostname, resolver, and network |
| TCP connect | Connection refused/timed out | Check endpoint, port, firewall, egress |
| TLS | `SSLHandshakeException` | Inspect trust chain, hostname, and TLS policy |
| Auth | `AuthenticationFailedException` | Verify credentials/token/account permissions |
| Open folder | `FolderNotFoundException`, permission denied | Verify folder name and grants |
| Fetch | `FolderClosedException`, `StoreClosedException`, timeout | Close the old session and reconnect |
| Parse/process | `MessagingException`, I/O or business error | Distinguish message errors from transport errors |
| Checkpoint | Database/network error | Do not mark as succeeded if not yet durable |

Some errors may only surface as a `MessagingException` wrapping a nested cause. For example, a socket timeout may live inside the cause chain rather than being thrown directly.

## 5. Classifying Errors to Choose the Right Retry Strategy

Errors should be divided into at least four categories:

1. **Transient connectivity:** temporary DNS failures, unstable network, server restarts, connection timeouts. Can be retried with a limit and backoff.
2. **Authentication/authorization:** wrong password, expired token, revoked mailbox access. Do not hammer retries with the same failing credentials; an expired token can trigger a proper refresh flow.
3. **TLS/security/configuration:** mismatched hostname/certificate, incompatible TLS policy, unauthorized folder. Usually requires fixing configuration or permissions; do not "fix" with trust-all.
4. **Data/processing:** malformed email, broken attachment, database down. Do not reconnect to the mail server by default if the root cause is in message processing.

Classification example:

~~~text
TRANSIENT_NETWORK       -> reconnect after backoff
SERVER_THROTTLED        -> provider-specific cooldown
AUTHENTICATION_FAILED   -> refresh once if supported / pause + alert
TLS_OR_TRUST_FAILURE    -> pause + remediation
FOLDER_PERMISSION       -> pause mailbox / review ACL
MESSAGE_PROCESSING      -> quarantine/retry individual message
CHECKPOINT_UNAVAILABLE  -> retain state / retry durable commit
UNKNOWN                 -> limited retry, no tight loop
~~~

Classification must rely on reliable **exception types, cause chains, and protocol statuses**, not solely on `contains("timeout")` in an error string. Providers can change error text, and those messages may also contain sensitive information.

## 6. Timeouts Must Cover Both Connection and Read Operations

Without configured timeouts, a polling job can hang for a long time while connecting, waiting for a response, or performing a write operation. When that happens:

- Scheduler/executor threads are tied up.
- Mailbox claims/leases can expire.
- Subsequent polling runs overlap or fall behind.
- The system cannot easily distinguish "still reading" from "dead".

Important timeouts in Jakarta Mail provider implementations:

| Property | Common meaning |
|---|---|
| `mail.imaps.connectiontimeout` | Time to wait when establishing the TCP connection |
| `mail.imaps.timeout` | Socket read timeout |
| `mail.imaps.writetimeout` | Socket write timeout |
| `mail.imaps.ssl.checkserveridentity` | Enables TLS hostname verification |
| `mail.imaps.ssl.trust` | Custom trust setting; do not use `*` to bypass verification |

Property names are **prefixed by the actual protocol**: `mail.imaps.*` when calling `getStore("imaps")`, `mail.imap.*` when calling `getStore("imap")`; POP3/POP3S use `mail.pop3.*` and `mail.pop3s.*`. A property with the wrong prefix may have no effect.

Example using IMAPS on port 993:

~~~java
import jakarta.mail.Session;
import java.util.Properties;

public final class InboundMailSessionFactory {
    public Session newImapsSession() {
        Properties properties = new Properties();
        properties.put("mail.store.protocol", "imaps");
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "15000");
        properties.put("mail.imaps.writetimeout", "15000");
        properties.put("mail.imaps.ssl.checkserveridentity", "true");
        properties.put("mail.debug", "false");
        return Session.getInstance(properties);
    }
}
~~~

Values in milliseconds are **operational examples**, not universal rules for every server. Choose timeouts based on network latency, message size, provider capability, and SLA; mailboxes with large attachments may require different read timeouts.

## 7. IMAPS and STARTTLS: Configuring the Right Connection Mode

Two common transport-protection models:

**Implicit TLS (IMAPS)**: the client establishes a TLS connection from the very beginning. Example:

~~~java
Session session = Session.getInstance(properties);
Store store = session.getStore("imaps");
store.connect("imap.example.test", 993, username, password);
~~~

**STARTTLS (IMAP)**: the client starts with plain IMAP over TCP and upgrades to TLS according to server capability:

~~~java
Properties properties = new Properties();
properties.put("mail.imap.starttls.enable", "true");
properties.put("mail.imap.starttls.required", "true");
properties.put("mail.imap.ssl.checkserveridentity", "true");

Session session = Session.getInstance(properties);
Store store = session.getStore("imap");
store.connect("imap.example.test", 143, username, password);
~~~

`starttls.required=true` prevents silently continuing an unencrypted session when the server does not support STARTTLS. Do not enable conflicting options simultaneously and assume IMAP will "figure out" the intended mechanism.

For POP3, the equivalent approach uses `pop3s`/995 or `pop3`/110 with `mail.pop3.starttls.*`. The STARTTLS mechanism in POP3 is commonly referred to as STLS at the protocol level.

### TLS Certificate Errors

When encountering `SSLHandshakeException` or hostname verification failures:

1. Check whether the configured domain matches the certificate.
2. Check the certificate chain, trusted CAs, expiration dates, and system clock.
3. Verify you are connecting to the right port and using the right implicit TLS/STARTTLS mode.
4. If an enterprise server uses a private CA, install a valid truststore according to policy.
5. Inspect any proxies/firewalls intercepting the TLS handshake.

Do not resolve it with:

~~~properties
# Do not use in production to bypass verification.
mail.imaps.ssl.trust=*
~~~

Trusting every server increases the risk of connecting to a spoofed server or MITM. Mailbox credentials can be exposed if authentication passes through an untrusted endpoint.

## 8. Login Failures Are Not Network Errors You Can Retry Forever

`AuthenticationFailedException` may indicate:

- Wrong or rotated username/password.
- Revoked app password.
- Provider disabled basic authentication or changed SMTP/IMAP/POP3 policy.
- MFA/conditional access requires another mechanism.
- Expired OAuth2 access token or wrong scope/audience.
- Locked mailbox or disabled user account.
- IMAP/POP3 protocol access disabled specifically on the account.

Retrying the exact same credentials every 100 milliseconds can trigger account lockouts or brute-force protection quotas. Safer behavior:

~~~text
AuthenticationFailedException
          |
          v
Is OAuth token expired and refresh supported?
          |
     +----+-----+
     |          |
    Yes        No
     |          |
     v          v
Refresh token   Pause mailbox receiver
once safely     + alert operator
     |
     v
Retry a bounded authentication attempt
     |
     +-- still unauthorized -> pause + alert
~~~

**Do not try multiple passwords automatically, do not fall back to an admin account, and do not disable MFA.** Obtaining a new OAuth token must be handled by a dedicated authentication component; tokens are typically short-lived and should not be written to logs.

### OAuth2 and IMAP

Some providers support the XOAUTH2 mechanism for IMAP. Jakarta Mail configuration may require:

~~~properties
mail.imaps.auth.mechanisms=XOAUTH2
~~~

Depending on the implementation/provider, the access token is passed in the credential parameter of the connect call, **not a traditional password**. This is not an automatic refresh feature: the application needs a token supplier managing expiry, scope, and refresh lifecycle appropriate to the provider.

Do not assume that `mail.imaps.auth.mechanisms=XOAUTH2` automatically grants the client permission to read the mailbox. The provider also validates consent/grants, account state, mailbox scope, and tenant policies.

## 9. Connecting and Opening INBOX with Jakarta Mail

A minimal example with cleanup to show clearly where connection errors occur:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.Store;

public final class ImapsInboxReader {
    private final Session session;
    private final String host;
    private final String username;
    private final String password;

    public ImapsInboxReader(
            Session session,
            String host,
            String username,
            String password) {
        this.session = session;
        this.host = host;
        this.username = username;
        this.password = password;
    }

    public void readFirstPage() throws MessagingException {
        Store store = null;
        Folder inbox = null;

        try {
            store = session.getStore("imaps");
            store.connect(host, 993, username, password);

            inbox = store.getFolder("INBOX");
            if (!inbox.exists()) {
                throw new MessagingException(
                        "Configured inbox folder not found");
            }

            inbox.open(Folder.READ_ONLY);
            int messageCount = inbox.getMessageCount();
            int first = Math.max(1, messageCount - 19);

            if (messageCount > 0) {
                Message[] recent =
                        inbox.getMessages(first, messageCount);
                for (Message message : recent) {
                    // Illustration only: production uses UID/checkpoint.
                    System.out.println(
                            "Fetched MIME type: "
                                    + message.getContentType());
                }
            }
        } finally {
            if (inbox != null && inbox.isOpen()) {
                inbox.close(false);
            }
            if (store != null && store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

This example opens `READ_ONLY`, without altering flags or expunging. It prints only the MIME type and does not dump subject, sender, recipient, or body. Jakarta Mail objects are created for **a single poll**, without sharing a `Folder` across multiple threads.

**This is an example for learning how to connect, not a production mail-receiving algorithm**: fetching the latest 20 messages by sequence number can miss older messages or reprocess already-read messages. Later sections use UIDs and durable checkpoints.

### Cleanup Notes in the Example

Calls to `Folder.close(false)` or `Store.close()` can also throw `MessagingException`. When the application needs to preserve the original exception and guarantee that `Store` is always closed even if closing `Folder` fails, use a dedicated cleanup helper, catch errors per resource, and attach close failures as **suppressed exceptions** instead of letting a cleanup error mask the root receiving failure.

A cleanup error does not necessarily require retrying every message that was already processed successfully; distinguish **read errors** from **connection-close errors** and track checkpoints.

## 10. Do Not Reuse a Closed Folder/Store After a Connection Error

Several lifecycle-related exceptions:

- `FolderClosedException`: the folder is no longer open, for example because the server closed the connection while reading.
- `StoreClosedException`: the store/session connection is no longer usable.
- `MessageRemovedException`: the message was deleted/expunged while being processed.
- `MessagingException` with nested `SocketTimeoutException`/`SocketException`: network loss or timeout.

Once the session fails, a `Message` object obtained from the old folder may no longer be able to read its body because Jakarta Mail loads content lazily.

Do not do this:

~~~java
try {
    message.getContent();
} catch (MessagingException ex) {
    // Wrong: keep calling on the same broken Folder/Message.
    message.getContent();
}
~~~

Instead:

1. Classify the error; if it is transient connectivity, mark the current session unusable.
2. Clean up the old Store/Folder resource by resource.
3. Wait according to the retry policy; **do not loop endlessly in a hot while loop**.
4. Create a new Store (and new Folder), connect, and reopen.
5. Verify UIDVALIDITY and load the checkpoint.
6. Resume reading unfinished messages based on the saved state.

### Why `store.isConnected()` Is Not Enough

A connection may already have been closed by the server or a network middlebox without the application detecting it yet. `isConnected()` provides a status signal, **not a guarantee that every subsequent operation will succeed**. Always be ready to handle exceptions during `getMessages`, `getContent`, `fetch`, or while reading attachments.

## 11. Limiting Connection Lifetime and Count

An app with 10 mailbox accounts and 5 replicas, where each replica opens 4 Stores per mailbox, can generate **200 connections**. Providers typically enforce connection/session limits or throttling policies.

Plan ahead:

~~~text
Number of mailboxes
  x instances polling same account
  x connections per instance
  = possible concurrent connections
~~~

Reduce risk:

- Allow only one active poller per mailbox when single-consumer semantics are needed.
- Use leader election or a distributed lease if there are multiple replicas.
- Limit the number of open Stores/Folders per account.
- Close unused connections; do not hold them open past idle timeouts.
- Do not open a new Store **for each message** in the same batch when it can be safely reused within a single poll.
- Leave headroom for other applications/mail clients sharing the same mailbox.
- Check the connection limits and polling guidance of your provider.

**More connections do not always speed up mail reading.** They can cause server throttling, trigger BYE responses, or get the account blocked—especially when all replicas poll INBOX simultaneously.

## 12. Polling and IMAP IDLE Have Different Failure Models

**Polling**: opens/reads the mailbox on a schedule. Makes it easy to measure timeouts, retry, and close the Store after each cycle.

**IMAP IDLE**: keeps a connection open so the server pushes mailbox-change notifications when new mail arrives. Reduces latency and poll frequency, but long-lived connections are prone to NAT/firewall/server idle timeouts or closure during maintenance.

| Characteristic | Polling | IMAP IDLE |
|---|---|---|
| Connection | Usually short-lived per cycle or pooled | Usually kept open |
| New mail detection | Based on poll interval | Can be near real-time |
| Recovery after disconnect | Wait for next poll and reconnect | Requires an IDLE restart loop |
| Testability | Fairly straightforward | Must simulate server BYE/IDLE termination |
| Avoiding missed mail | Checkpoint UID on each poll | Still must reconcile UIDs after reconnect |

**IDLE is only a change notification signal, not a durable message queue.** After IDLE is interrupted, you must reconcile the mailbox by UID to find messages that arrived while offline. Do not rely on the count of IDLE events as a checkpoint.

If using **Spring Integration Mail**, you can choose a polling inbound adapter or an IMAP IDLE-driven channel adapter; you still must design exception handling, backoff, duplicate prevention, mailbox state, and observability at the application level.

## 13. Do Not Use Message Sequence Numbers as Durable Checkpoints

In IMAP, each `Message` has a **message sequence number** representing its current ordinal position in the folder. When messages are deleted/expunged or the folder changes, these numbers can shift.

Example:

~~~text
Poll 1:
  Seq 1 -> Email A
  Seq 2 -> Email B
  Seq 3 -> Email C

Email A is expunged

Poll 2:
  Seq 1 -> Email B
  Seq 2 -> Email C

If checkpoint = "processed seq 2":
  app may skip C or process incorrectly.
~~~

Do not store:

~~~text
lastProcessedMessageNumber=2
~~~

and then start reading from 3 on all subsequent connections. Sequence numbers are meaningful only within the current snapshot of folder state.

With IMAP, a better choice is **UID**, combined with **UIDVALIDITY**:

~~~text
Mail account + folder + UIDVALIDITY + UID
                  |
                  v
      Server message identifier
      within one UID validity epoch
~~~

UIDs increase according to mailbox rules within the same UIDVALIDITY, but that does not mean UIDs are contiguous. Do not infer that a UID jump of 100 necessarily means 100 new messages arrived.

## 14. What Does UIDVALIDITY Solve?

An IMAP folder has a `UIDVALIDITY` value that defines the validity context for its UIDs. When a server rebuilds a mailbox or changes how UIDs are assigned, UIDVALIDITY can change.

Example:

~~~text
Before mailbox is rebuilt:
  account=SUPPORT
  folder=INBOX
  UIDVALIDITY=100
  UID=2501 -> Email X

After mailbox is rebuilt:
  account=SUPPORT
  folder=INBOX
  UIDVALIDITY=101
  UID=2501 -> May be Email Y
~~~

If the application only stores UID=2501, it may mistakenly assume Email Y was already processed. Therefore, the identifying key usually includes:

~~~text
(mailboxAccountId, folderName, uidValidity, uid)
~~~

In Jakarta Mail:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.UIDFolder;

Folder folder = store.getFolder("INBOX");
folder.open(Folder.READ_ONLY);

if (!(folder instanceof UIDFolder uidFolder)) {
    throw new IllegalStateException(
            "This mailbox implementation does not expose IMAP UID");
}

long uidValidity = uidFolder.getUIDValidity();
if (uidValidity <= 0) {
    throw new IllegalStateException(
            "Valid UIDVALIDITY is unavailable");
}
~~~

Do not assume every `Store`/`Folder` supports `UIDFolder`. For standard IMAP providers, this is the right mechanism; for POP3, identification works differently.

### What to Do When UIDVALIDITY Changes?

You cannot keep comparing the old `lastUid` as if it were the same mailbox generation:

1. Record a `UIDVALIDITY_CHANGED` event.
2. Initialize a **new checkpoint generation** for the folder.
3. Reconcile existing messages according to policy.
4. Use a deduplication/business idempotency table to reduce duplicate processing of previously handled mail.
5. Do not delete old history before reconciling if the business requires auditing.

**Do not automatically reset the last UID to 0 and process millions of messages without bounds.** You need a plan for initial scan, batch size, cutoff, or rescan aligned with retention and operational capacity.

## 15. Reading IMAP from a Checkpoint After Reconnecting

A high-level code pattern:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.UIDFolder;

public final class ImapBatchProcessor {
    private final MailCheckpointRepository checkpointRepository;
    private final MailBusinessProcessor businessProcessor;

    public ImapBatchProcessor(
            MailCheckpointRepository checkpointRepository,
            MailBusinessProcessor businessProcessor) {
        this.checkpointRepository = checkpointRepository;
        this.businessProcessor = businessProcessor;
    }

    public void processOpenFolder(
            String accountId,
            String folderName,
            Folder folder) throws Exception {

        if (!folder.isOpen()) {
            throw new MessagingException("Folder is not open");
        }
        if (!(folder instanceof UIDFolder uidFolder)) {
            throw new MessagingException(
                    "UID capability required for this processing mode");
        }

        long uidValidity = uidFolder.getUIDValidity();
        if (uidValidity <= 0) {
            throw new MessagingException(
                    "UIDVALIDITY not available");
        }

        MailCheckpoint checkpoint =
                checkpointRepository.loadOrCreate(
                        accountId, folderName, uidValidity);

        if (checkpoint.uidValidity() != uidValidity) {
            // Do not use lastUid from an old generation.
            throw new IllegalStateException(
                    "Mailbox UIDVALIDITY changed; reconciliation required");
        }

        long lastUid = checkpoint.lastCommittedUid();
        if (lastUid == Long.MAX_VALUE) {
            return;
        }

        // Pedagogical example: production should paginate by UID range.
        Message[] candidates = uidFolder.getMessagesByUID(
                lastUid + 1, UIDFolder.LASTUID);

        for (Message message : candidates) {
            if (message == null) {
                continue;
            }

            long uid = uidFolder.getUID(message);
            if (uid <= lastUid) {
                continue;
            }

            // In a real implementation, business side effects and
            // dedup/checkpoint must follow a transaction policy.
            businessProcessor.process(
                    accountId, folderName, uidValidity, uid, message);
            checkpointRepository.commitUid(
                    accountId, folderName, uidValidity, uid);
            lastUid = uid;
        }
    }
}
~~~

`MailCheckpointRepository`, `MailCheckpoint`, and `MailBusinessProcessor` are **application-defined** abstractions, not Spring Mail classes. `processOpenFolder` requires the folder to already be open and the worker to hold permission to poll the corresponding account/folder.

### What This Example Does Not Yet Solve

- `getMessagesByUID` on a large mailbox can return many message references. In production, paginate by UID range/batch.
- `process(...)` and `commitUid(...)` are two separate operations. If processing succeeds and the app crashes before commit, the message can be processed again.
- A failing message in the middle of a batch can delay subsequent messages. That may be the right choice if preserving sequential checkpoint order.
- A folder closing during processing can prevent lazy-fetched messages from being read.
- `loadOrCreate` must recognize an older UIDVALIDITY and **must not silently create a new checkpoint that hides history**.
- Multiple workers processing the same mailbox require a distributed lease and concurrency-safe checkpoint updates.

This example intentionally does not promise **exactly-once processing**. To ensure no duplicate business side effects occur, idempotency and transactions must be added.

## 16. Using a Database to Record Processed Messages

In addition to the latest checkpoint, there should be a message deduplication table:

~~~sql
CREATE TABLE received_mail (
    account_id VARCHAR(100) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    imap_uid BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    processed_at TIMESTAMPTZ,
    business_reference VARCHAR(160),
    PRIMARY KEY (
        account_id, folder_name, uid_validity, imap_uid
    )
);

CREATE TABLE mailbox_checkpoint (
    account_id VARCHAR(100) NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    uid_validity BIGINT NOT NULL,
    last_committed_uid BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, folder_name)
);
~~~

With the `mailbox_checkpoint` table, a policy is needed when UIDVALIDITY changes: update the generation inside a transaction or reconciliation workflow rather than simply using `last_committed_uid` from an older generation.

### Transaction Principles

If processing an email means **writing internal records**:

~~~text
BEGIN TRANSACTION
  Verify message not processed
  Insert/update business data
  Mark received_mail processed
  Advance checkpoint safely
COMMIT
~~~

If all four operations use the same transactional database, strong consistency between business state and checkpoint can be achieved. If processing includes **calling an external API**, sending a reply via SMTP, or publishing an event to another system, a database transaction **does not** cover that side effect; an idempotency key, outbox, or suitable coordination mechanism is required.

### Do Not Mark Success Too Early

Wrong:

~~~text
Fetch UID 500
Advance checkpoint to UID 500
Download attachment / business processing
Crash
~~~

On restart, the checkpoint causes UID 500 to be skipped even though the work was not completed.

Following the right principle:

~~~text
Fetch UID 500
Validate / process idempotently
Persist success and checkpoint
Only then consider UID 500 committed
~~~

For transient errors, keep the message in a retry state and do not advance a sequential checkpoint past an unprocessed gap unless the application has an explicit gap-tracking design.

## 17. Choose At-Least-Once + Idempotency Instead of Promising Exactly-Once

A poll cycle can fail at several crash points:

~~~text
Fetch UID 900
    |
    +-- Crash before processing      -> retry UID 900
    |
    +-- Business DB commit
    |      |
    |      +-- Crash before checkpoint -> may be reprocessed
    |
    +-- Checkpoint commit
    |
    +-- Worker continues to UID 901
~~~

When a mail-receiving pipeline works with a database and an external system such as a CRM, there is **no single atomic transaction** spanning the email server, database, and CRM API. Therefore, design for:

- **At-least-once fetching**: messages may be read again after a reconnect/restart.
- **Idempotent processing**: repeated reads do not create duplicate business records.
- **Transactional inbox**: record the message key in the same transaction as internal business changes.
- **Outbox for external side effects**: write the intent to invoke CRM/HTTP responses into the DB; another worker executes and retries with an idempotency key.
- **Dead-letter/quarantine**: isolate unprocessable messages so they do not block the mailbox permanently.

The `Message-ID` email header is **not guaranteed to be unique or always present**; do not rely on it as the sole deduplication key. An email can be copied to another folder or a provider can regenerate UIDVALIDITY; critical workflows need additional correlation/semantic deduplication rules such as a transaction reference extracted from verified content.

### Checkpoints and Gap State

If message UID 105 fails parsing while UID 106 succeeds, there are two options:

1. **Strict sequential cursor:** stop at UID 105 and do not advance past 105. Simple, though it can stall the batch.
2. **Per-message status + gap tracking:** mark UID 106 completed and UID 105 retry/quarantine, advancing the watermark only after all preceding messages reach an accepted terminal state.

Do not jump the checkpoint straight to 106 just because a newer message finished if the system does not record and track the pending UID 105.

## 18. POP3: UIDL, DELE, and the Risk of Losing Mail

POP3 follows a different model from IMAP:

~~~text
POP3 connect/auth
    |
    v
STAT / LIST / UIDL (if supported)
    |
    v
RETR n
    |
    v
Process + save checkpoint
    |
    v
Optional DELE n
    |
    v
QUIT
~~~

In POP3, some servers provide the **UIDL** command so applications can distinguish messages across connections. However, UIDL and API access support vary by provider. **Do not use POP3 LIST/RETR sequence numbers as durable identifiers**, because they change whenever mail is deleted.

### Be Careful with Deletion

- If you finish reading mail and want to **keep a copy on the server**, do not request deletion.
- If deletion is required by retention policy, mark for deletion only after the payload and processing state have been durably saved.
- In POP3, `DELE` marks are typically executed by the server only on clean session termination (QUIT), so the outcome may be ambiguous if the connection drops before completion.
- Do not assume `Folder.close(true)` has identical semantics in IMAP and POP3 across all implementations; inspect the specific provider/connector before enabling expunge/delete.

For systems that must recover from crashes and handle multiple folders, **IMAP with UIDs is generally easier to checkpoint**. If POP3 is mandatory, implement a UIDL/deduplication strategy and persist message bytes durably before executing operations that remove email from the server.

## 19. Retry with Exponential Backoff and Jitter

When a mailbox experiences an outage, an application must not attempt thousands of reconnects per second. **Exponential backoff** gradually increases wait time across failures:

\[
d_n = \min(d_{\max},\, d_0 \cdot 2^{n-1})
\]

Where `d0` is the base delay, `dmax` is the cap, and `n` is the consecutive failure count.

Add **jitter** so multiple instances do not reconnect all at once:

\[
d_{\text{retry}} \sim U(0,d_n)
\]

This is *full jitter*. If the business requires avoiding overly fast retries, add a minimum retry interval and a limit on total retry attempts/outage age.

Example:

| Failure # | Assumed backoff cap with 2s base | Full jitter range |
|---|---:|---|
| 1 | 2 seconds | 0–2 seconds |
| 2 | 4 seconds | 0–4 seconds |
| 3 | 8 seconds | 0–8 seconds |
| 4 | 16 seconds | 0–16 seconds |
| 5 | 32 seconds | 0–32 seconds |
| 6 onward | Capped, e.g., 60 seconds | 0–60 seconds |

Numbers are illustrative only, not official guidance for any provider. If a provider specifies a minimum interval between IMAP logins or advises waiting longer, respect it.

## 20. Java: Computing Backoff Without Holding a Thread Asleep Indefinitely

A small, easily testable class:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class MailReconnectBackoff {
    private final long baseMillis;
    private final long maxMillis;

    public MailReconnectBackoff(
            Duration base,
            Duration maximum) {
        this.baseMillis = base.toMillis();
        this.maxMillis = maximum.toMillis();
        if (baseMillis <= 0 || maxMillis < baseMillis) {
            throw new IllegalArgumentException(
                    "Invalid reconnect backoff configuration");
        }
    }

    public Duration nextDelay(int consecutiveFailures) {
        if (consecutiveFailures < 1) {
            throw new IllegalArgumentException(
                    "consecutiveFailures must be positive");
        }

        long cap = baseMillis;
        for (int i = 1; i < consecutiveFailures; i++) {
            if (cap >= maxMillis) {
                break;
            }
            cap = cap > maxMillis / 2
                    ? maxMillis
                    : cap * 2;
        }

        long millis = ThreadLocalRandom.current()
                .nextLong(cap + 1);
        return Duration.ofMillis(millis);
    }
}
~~~

Avoid calling `Thread.sleep(...)` inside an IMAP listener or worker holding a DB lease, connection, and executor slot. It is better to **schedule the next poll** via a scheduler or persist `nextAttemptAt` and release the thread.

### Per-Mailbox Retries

If an application receives from 20 mailboxes, a failure on mailbox A should not stop processing for mailboxes B–T. Track the following fields per account:

~~~text
mailboxId
consecutiveFailures
lastSuccessfulPollAt
nextAttemptAt
lastFailureKind
healthStatus
~~~

Do not store raw passwords/tokens in status tables or logs. When A recovers, reset the consecutive failure counter according to policy; do not delete incident history needed for auditing.

## 21. Classifying Jakarta Mail Exceptions

Types to recognize:

| Exception or nested cause | Common meaning | How to respond |
|---|---|---|
| `AuthenticationFailedException` | Auth/token/permission error | Pause and refresh token via approved flow |
| `FolderNotFoundException` | Wrong folder/path or deleted folder | Check configuration, do not hot-retry |
| `FolderClosedException` | Folder closed by server/library | Clean up and open a new folder |
| `StoreClosedException` | Store connection closed | Create a new Store and reconnect |
| `MessageRemovedException` | Message no longer at the read position | Reconcile UID/checkpoint, do not retry old object |
| `SocketTimeoutException` in cause | Slow TCP read/write/connect | Transient retry, check timeouts and server |
| `SocketException`/`ConnectException` | Reset/refused/network error | Check network/endpoint, retry with backoff |
| `UnknownHostException` | DNS host cannot be resolved | May be transient or misconfigured; check DNS |
| `SSLHandshakeException` | TLS trust/hostname/protocol | Verify certificate and endpoint, do not disable TLS |
| Generic `MessagingException` | Insufficient context | Inspect nested cause/type/protocol, classify cautiously |

Some providers report issues through protocol responses before Java throws an exception; specific exception classes depend on the Jakarta Mail implementation. **Do not design policy purely around message strings expecting it to work across every provider.**

### Do Not Confuse IMAP with SMTP Status Codes

- SMTP uses reply codes such as `421`, `450`, `550`.
- IMAP uses tagged `OK`, `NO`, `BAD` along with responses like `BYE` and server informational text.
- POP3 uses `+OK` and `-ERR`.

An SMTP retry policy cannot be applied verbatim to IMAP login/fetch. Classify according to the active protocol.

## 22. Java Example: Classifying Errors into Internal Codes

A classifier helps the poller decide retry behavior without logging raw exceptions containing email addresses or server responses.

~~~java
import jakarta.mail.AuthenticationFailedException;
import jakarta.mail.FolderClosedException;
import jakarta.mail.FolderNotFoundException;
import jakarta.mail.StoreClosedException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import javax.net.ssl.SSLHandshakeException;

public enum ReceiveFailureKind {
    AUTHENTICATION,
    TLS_CONFIGURATION,
    FOLDER_CONFIGURATION,
    CONNECTION_LOST,
    DNS_OR_CONNECTIVITY,
    UNKNOWN
}

public final class MailReceiveFailureClassifier {
    private MailReceiveFailureClassifier() {
    }

    public static ReceiveFailureKind classify(Throwable error) {
        Throwable current = error;
        int depth = 0;

        while (current != null && depth++ < 24) {
            if (current instanceof AuthenticationFailedException) {
                return ReceiveFailureKind.AUTHENTICATION;
            }
            if (current instanceof SSLHandshakeException) {
                return ReceiveFailureKind.TLS_CONFIGURATION;
            }
            if (current instanceof FolderNotFoundException) {
                return ReceiveFailureKind.FOLDER_CONFIGURATION;
            }
            if (current instanceof FolderClosedException
                    || current instanceof StoreClosedException
                    || current instanceof SocketException
                    || current instanceof SocketTimeoutException) {
                return ReceiveFailureKind.CONNECTION_LOST;
            }
            if (current instanceof UnknownHostException
                    || current instanceof ConnectException) {
                return ReceiveFailureKind.DNS_OR_CONNECTIVITY;
            }
            current = current.getCause();
        }
        return ReceiveFailureKind.UNKNOWN;
    }
}
~~~

**Important limitations of this example:**

- This is a basic cause-chain classifier, not a complete handling table for every provider.
- `SocketTimeoutException` is a subclass of `SocketException`, though listed explicitly for clarity.
- A `MessagingException` can hold a nested exception via `getNextException()` in addition to `getCause()`; real systems should traverse both **with a depth limit and cycle protection**, rather than relying solely on `getCause()`.
- Authentication failures caused by an expired token require different handling from a revoked account; use signals from the identity provider.
- `SSLHandshakeException` can reflect several causes, not always just a certificate error.
- Some folder exceptions represent transient mailbox state issues and must be checked against the server response before deciding to stop permanently.

Do not print `error.getMessage()` or `error` directly into centralized logs; responses may contain mailbox names, usernames, email addresses, or account details. Log only the classification code, a non-sensitive mailbox ID, and the job/poll attempt.

## 23. Safe Polling Loop: Do Not Let One Outage Halt the Scheduler

A poller model needs to:

- Start only once `nextAttemptAt` has arrived.
- Confirm only one worker owns the mailbox/folder if serial processing is required.
- Connect the Store and open the Folder.
- Process a bounded batch size.
- Persist successful results and the checkpoint.
- Classify exceptions; schedule retry or pause.
- Close the connection.
- Never retain resources from a previous poll inside a failing loop.

~~~text
Scheduled tick
    |
    v
Is mailbox paused or not due yet?
    |          |
   Yes         No
    |          |
    v          v
  Skip      Acquire lease
                 |
                 v
           Connect / open
                 |
         +-------+-------+
         |               |
       Success          Failure
         |               |
         v               v
    Process batch      Classify
         |               |
         v               v
    Commit state    Backoff or pause
         |               |
         +-------+-------+
                 |
                 v
            Close / release
~~~

### Coordinator Example with Scheduling

~~~java
import java.time.Clock;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class MailboxPollScheduler {
    private final Clock clock;
    private final MailboxPollingCoordinator coordinator;

    public MailboxPollScheduler(
            Clock clock,
            MailboxPollingCoordinator coordinator) {
        this.clock = clock;
        this.coordinator = coordinator;
    }

    @Scheduled(
            fixedDelayString =
                    "${app.mail.receive.poll-delay-ms:30000}")
    public void poll() {
        Instant now = clock.instant();
        coordinator.pollDueMailboxes(now);
    }
}
~~~

`MailboxPollingCoordinator` is an application-built service. It must **catch errors per mailbox** and update `nextAttemptAt`, rather than letting one failing mailbox prevent other mailboxes from being polled. When using `@Scheduled`, enable scheduling via `@EnableScheduling` according to your application configuration.

This only sets up the reminder schedule. With multiple replicas, every replica will run the scheduler; **a lease/leader election is required** before each mailbox is processed. Do not rely on `fixedDelay` assuming only one worker exists cluster-wide.

### Do Not Retry Immediately Within the Same Scheduled Tick

Wrong:

~~~java
while (true) {
    try {
        readMailbox();
    } catch (Exception ignored) {
        // Tight loop: server down -> thousands of connect attempts.
    }
}
~~~

Better is to record a `WAITING_RECONNECT` state with the next attempt timestamp, then exit the tick. A later tick will resume once enough time has elapsed.

## 24. Circuit Breaker for Mailboxes with Prolonged Failures

A mailbox with bad credentials for hours should not occupy the entire system with thousands of login attempts. A **circuit breaker** temporarily blocks new connection attempts.

~~~text
CLOSED: normal, allow polling
    |
    +-- failures exceed threshold
    v
OPEN: pause polling, alert/cooldown
    |
    +-- cooldown expires
    v
HALF_OPEN: try one controlled connection
    |
    +-- success -> CLOSED
    |
    +-- failure -> OPEN
~~~

Distinguish three pause types:

| Type | Meaning | Pause duration |
|---|---|---|
| Retry backoff | Isolated transient failure | Seconds/minutes per policy |
| Circuit breaker | Consecutive failures indicating provider unavailability | Cooldown and limited probe |
| Administrative pause | Bad credential/TLS/config/permission requiring intervention | Until remediated or approved to resume |

Do not keep closing the circuit repeatedly when there is evidence the account was revoked. Conversely, do not turn a 5-second network hiccup into an indefinite pause with no alerting or recovery path.

### Provider-Level Throttling

Some servers limit the rate of opening IMAP sessions or concurrent connections. If multiple mailboxes on the same provider are throttled, reduce **total connections/poll rate**, rather than backing off only a single mailbox. This is a provider/account admission-control problem similar to quota management, applied to inbound connections rather than outbound SMTP.

## 25. Distributed Lease When Multiple Replicas Read the Same Mailbox

If two application instances poll the mailbox concurrently:

~~~text
Instance A        Instance B
    |                 |
    +-- Fetch UID 101 +
                      +-- Fetch UID 101
    |                 |
    +-- Process       +-- Process
    |                 |
         Duplicates!
~~~

You can use a **distributed lease** keyed by:

~~~text
mailbox-receive:{accountId}:{folderName}
~~~

One owner has permission to poll during the lease window; when a worker dies, the lease expires and another worker takes over.

Requirements:

- Atomic acquire/renew/release on a shared store.
- Lease duration longer than a poll segment or properly renewed.
- **Fencing token**/generation so an old worker cannot write checkpoints after losing the lease.
- Checkpoint transaction verifies lease ownership.
- Workers always read the durable checkpoint rather than reusing a stale local cursor after takeover.
- Business handlers must still be idempotent because leases cannot eliminate every race window.

### Why a Single-JVM Lock Is Not Enough

`synchronized` or `ReentrantLock` only coordinates threads inside one JVM. In Kubernetes with 4 pods, there can be 4 separate locks and all 4 pods believe they own the mailbox.

If the application truly runs as a single instance, a local lock may suffice for concurrency. However, that must be a controlled deployment assumption; a rolling deployment can temporarily run two instances simultaneously.

## 26. Do Not Use the Seen Flag as the Sole Checkpoint

A common approach:

~~~text
Search UNSEEN
Process message
Set SEEN
~~~

This looks simple, yet is unreliable:

- A user or another email client can mark a message Seen before the app reads it.
- After a crash, a message may already be marked Seen without business processing completing.
- A client can mark a message Unseen again, causing duplicate processing.
- IMAP flags can change through multi-device synchronization.
- When opened `READ_ONLY`, the app should not expect to modify flags.

**Seen is a mailbox user-experience state, not a business transaction checkpoint.** Combine UID/UIDVALIDITY with a durable processing table.

If the product requires automatically marking Seen after processing, do so per policy with `READ_WRITE` access, setting it **after** saving business results; still, never treat the flag as sole proof. If marking Seen fails, distinguish that from completed business processing so side effects are not duplicated.

## 27. Messages Deleted or Moved to Another Folder While Reading

In a shared mailbox, a user may delete or move an email while the worker is fetching its content:

~~~text
Worker lists UID 888
    |
    +-- User moves message to Archive
    |
Worker fetches body for UID 888
    |
    +-- MessageRemovedException / not found
~~~

Handling depends on business rules:

- If the message is no longer in the folder, record status `MESSAGE_DISAPPEARED` for that UID rather than looping retries infinitely on the old object.
- If the application must still process mail even after it was moved, design a strategy to monitor other folders, use provider APIs, or snapshot early enough.
- Never mark a message "processed successfully" merely because it disappeared.
- When a sequential cursor encounters a UID gap due to a deleted message, verify that the gap is not an unprocessed message being skipped.
- You may record an audit entry for the unreachable UID, while avoiding logging body contents or sender addresses.

**An IMAP UID is an identifier within a folder/UIDVALIDITY**, not a mailbox-wide identifier across move operations. A message copied/moved to a new folder typically receives a different UID.

## 28. Safely Downloading Message Content and Attachments Over Unstable Connections

Calling `Message.getContent()` may fetch data on demand; the entire email is not necessarily resident in memory when `getMessages()` returns. Large attachments raise the probability of read timeouts or connection resets.

Notes:

1. Enforce message/attachment size limits per policy before processing large payloads.
2. Do not call `getContent()` and log the entire payload for debugging.
3. If processing takes a long time, **snapshot the MIME bytes** to protected temporary storage and process after closing the folder.
4. Ensure the snapshot is completely written, with checksum/size and durable state recorded, before advancing the checkpoint.
5. Do not read attachment streams outside the Store/Folder lifecycle if the implementation still depends on the server.
6. Use an appropriate MIME parser and guard against dangerous files, path traversal, zip bombs, and malware.
7. Never render untrusted email content directly into HTML/web output without escaping/sanitizing.

### Example: Snapshotting MIME Content into a Byte Array for Small Fixtures

~~~java
import jakarta.mail.Message;
import java.io.ByteArrayOutputStream;

public byte[] snapshotSmallMessage(Message message)
        throws Exception {
    ByteArrayOutputStream output =
            new ByteArrayOutputStream();
    message.writeTo(output);
    return output.toByteArray();
}
~~~

**Do not use an unbounded `ByteArrayOutputStream` for emails hundreds of MB in size.** For large payloads, stream to bounded/quota-controlled storage, track byte count and checksum, and protect data at rest. Because a snapshot holds real emails, it contains PII and potentially sensitive tokens/links; encryption, RBAC, and retention must be defined.

If `writeTo(...)` fails midway due to a dropped connection, do not mark the message processed simply because partial bytes were received.

## 29. Monitoring: "Zero Poll Errors" Does Not Prove Mail Is Being Received

A worker can connect cleanly and log `poll_completed` steadily while failing to detect new mail because it queries the wrong folder, has a misaligned UID checkpoint, or filters out every message.

Monitor multiple signal groups:

| Metric | Meaning |
|---|---|
| `mail_receive_poll_total` | Number of polls by mailbox/provider and outcome |
| `mail_receive_connection_failure_total` | Count of TCP/TLS/DNS connection failures |
| `mail_receive_auth_failure_total` | Count of authentication failures |
| `mail_receive_reconnect_total` | Count of new connections opened after failures |
| `mail_receive_poll_duration_seconds` | Execution duration of a poll |
| `mail_receive_last_success_timestamp_seconds` | Timestamp of the most recent completed poll |
| `mail_receive_last_message_timestamp_seconds` | Timestamp of the most recent received/completed message |
| `mail_receive_fetched_total` | Number of messages fetched from the server |
| `mail_receive_processed_total` | Number of messages successfully processed by business logic |
| `mail_receive_duplicate_total` | Number of already-known messages whose side effects were skipped |
| `mail_receive_processing_failure_total` | Count of parse/business errors |
| `mail_receive_uidvalidity_change_total` | Count of mailbox generation changes |
| `mail_receive_backoff_seconds` | Currently active cooldown duration |
| `mail_receive_pending_messages` | Number of messages awaiting processing, if measurable |
| `mail_receive_checkpoint_lag` | Lag between newest message and checkpoint; measure only when semantics are clear |

### Label Values Must Be Controlled

Example:

~~~text
provider=PRIMARY_IMAP
mailbox_profile=SUPPORT_INBOX
phase=FETCH
result=TIMEOUT
~~~

Do not use real email addresses, `Message-ID`, subject, or per-message UID as metric labels — that creates high cardinality and can leak sensitive information. `mailbox_profile` should be an internal ID from a bounded list, containing no username/PII.

### Last Successful Poll Differs from Last Message Received

A mailbox may receive no new mail for hours while polling still works properly. Conversely, a successful poll might find no new messages due to misconfiguration.

To stay in control:

- For mailboxes with steady traffic, alert when time since the last successfully processed email exceeds expectations.
- For low-volume mailboxes, use a **synthetic test email** in an authorized environment to verify end-to-end delivery and receipt.
- When diagnosing, inspect checkpoint/UID validity, folder name, and filters rather than looking solely at connection error counts.

A watchdog can detect a worker failing to complete polls for too long or stuck in I/O; a watchdog by itself does not guarantee messages were processed.

## 30. Safe Logging When Handling Mail-Receiving Errors

Received messages may contain:

- From/To/Cc/Bcc addresses.
- Subject and message body.
- Password-reset links, session tokens, or OTPs.
- Sensitive attachments.
- Technical headers and mailbox account details.

Therefore, do not do this:

~~~java
log.error("IMAP failure user={} message={}",
        username, exception.getMessage());

log.debug("Received email: {}", message);
~~~

Instead, log:

~~~text
event=mail_receive_poll_failed
mailboxProfile=SUPPORT_INBOX
provider=PRIMARY_IMAP
phase=FETCH
errorKind=CONNECTION_LOST
consecutiveFailures=3
nextRetryBucket=30s_60s
~~~

If per-message correlation is needed, use an internal ID/UID tuple stored in an appropriately access-controlled audit store. A UID alone is not direct PII, though it can be linked to message content via mailbox access or other logs.

### Jakarta Mail Protocol Debug

`Session.setDebug(true)` and settings like `mail.debug=true` can print IMAP/POP3 protocol traffic. Depending on the implementation and mode, this can expose usernames, mailbox/folder names, and sensitive protocol data.

**Do not enable protocol debug by default in production.** When investigating:

1. Prefer test accounts and simulated mail servers.
2. Restrict duration, target instance, and access to the output.
3. Do not enable options that expose authentication secrets.
4. Sanitize data before pasting into tickets or chat.
5. Turn debug off and purge captured data according to retention policy.

Disabling DEBUG on the application logger does not necessarily stop `Session` from printing its own debug output; control stdout/stderr destinations and library configuration as well.

## 31. Alerts and Runbooks When a Mailbox Stops Receiving Mail

A runbook should be organized by the failure stage:

### A. Unable to Connect to the Server

1. Verify DNS resolution for the configured host from the exact target environment/pod.
2. Verify TCP egress, firewall, NAT, proxy, and port.
3. Check the provider status page and connection limits.
4. Cross-check the implicit TLS/STARTTLS port.
5. Verify whether `connectiontimeout` and `timeout` are reasonable.
6. If the provider is temporarily unavailable, lower reconnect frequency and monitor the backlog.

**Do not disable TLS in production to isolate faults.** If testing is needed, use a controlled sandbox.

### B. TLS Handshake Failures

1. Inspect the certificate chain and hostname.
2. Check the CA/truststore and system date/time.
3. Verify the TLS version and server endpoint.
4. Do not enable `mail.imaps.ssl.trust=*` to bypass verification.
5. Resume only once secure connectivity is properly restored.

### C. Repeated Authentication Failures

1. Identify the auth mechanism: app password, OAuth2, provider-specific.
2. Check secret rotation/expiry and scopes/grants.
3. Verify IMAP/POP3 access is still enabled on the mailbox at the provider.
4. Pause to avoid account lockout.
5. Refresh credentials/tokens from an approved source and perform a bounded retry.
6. Audit the account for unusual sign-in activity.

### D. Connected Successfully, Cannot Read INBOX

1. Check folder name, mailbox hierarchy, and permissions.
2. Verify whether the folder needs `READ_ONLY` or `READ_WRITE`.
3. Check UIDVALIDITY and the checkpoint.
4. Confirm the IMAP folder belongs to the right account INBOX, not another mailbox/alias.
5. Check whether an `UNSEEN` filter is hiding messages already read by another client.
6. Reconcile by UID across a controlled range rather than blindly deleting checkpoints.

### E. Mail Is Read, Business Processing Makes No Progress

1. Distinguish parse/MIME errors from database errors.
2. Identify the blocked UID/message.
3. Check per-message retry/quarantine state.
4. If reprocessing is needed, use idempotency and auditing.
5. Do not mark Seen, delete, or advance the checkpoint before processing succeeds.

### F. Large Volume of Duplicate Messages Appears After an Outage

1. Check whether multiple replicas are polling the same account.
2. Check lease ownership and fencing.
3. Check whether UIDVALIDITY changed.
4. Inspect transactionality between processed state and checkpoint updates.
5. Verify external side effects carry an idempotency key.
6. Stop uncontrolled replays and reconcile data before re-running.

## 32. Unit Testing: Backoff with Deterministic Inputs

Tests relying solely on `Thread.sleep` can be flaky in CI. Backoff logic can be split into a **cap computation** step and a jitter selection step to make testing easier.

Example of a pure cap-calculation policy:

~~~java
import java.time.Duration;

public final class ReconnectBackoffCap {
    private final Duration base;
    private final Duration maximum;

    public ReconnectBackoffCap(
            Duration base, Duration maximum) {
        if (base.isZero() || base.isNegative()
                || maximum.compareTo(base) < 0) {
            throw new IllegalArgumentException(
                    "Invalid durations");
        }
        this.base = base;
        this.maximum = maximum;
    }

    public Duration capFor(int consecutiveFailures) {
        if (consecutiveFailures < 1) {
            throw new IllegalArgumentException();
        }
        Duration current = base;
        for (int i = 1; i < consecutiveFailures; i++) {
            if (current.compareTo(maximum) >= 0) {
                return maximum;
            }
            current = current.compareTo(maximum.dividedBy(2)) > 0
                    ? maximum
                    : current.multipliedBy(2);
        }
        return current.compareTo(maximum) > 0
                ? maximum : current;
    }
}
~~~

JUnit test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class ReconnectBackoffCapTest {
    @Test
    void growsExponentiallyAndStopsAtMaximum() {
        ReconnectBackoffCap policy =
                new ReconnectBackoffCap(
                        Duration.ofSeconds(2),
                        Duration.ofSeconds(30));

        assertThat(policy.capFor(1))
                .isEqualTo(Duration.ofSeconds(2));
        assertThat(policy.capFor(2))
                .isEqualTo(Duration.ofSeconds(4));
        assertThat(policy.capFor(3))
                .isEqualTo(Duration.ofSeconds(8));
        assertThat(policy.capFor(5))
                .isEqualTo(Duration.ofSeconds(30));
        assertThat(policy.capFor(20))
                .isEqualTo(Duration.ofSeconds(30));
    }
}
~~~

When testing jitter, inject a mock random generator or deterministic number supplier, then assert the delay falls within `[minimum, cap]`. **No real network calls or sleeps are needed** to test the formula.

## 33. Unit Testing: Distinguishing Auth, TLS, and Connection Loss

A few scenarios using JUnit + AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import jakarta.mail.AuthenticationFailedException;
import jakarta.mail.FolderClosedException;
import javax.net.ssl.SSLHandshakeException;
import org.junit.jupiter.api.Test;

class MailReceiveFailureClassifierTest {
    @Test
    void authenticationIsNotTreatedAsTransientNetwork() {
        var error = new AuthenticationFailedException(
                "Fake credentials for unit test");

        assertThat(MailReceiveFailureClassifier.classify(error))
                .isEqualTo(ReceiveFailureKind.AUTHENTICATION);
    }

    @Test
    void tlsFailureIsNotSolvedByBlindReconnect() {
        var error = new SSLHandshakeException(
                "Test certificate mismatch");
        assertThat(MailReceiveFailureClassifier.classify(error))
                .isEqualTo(ReceiveFailureKind.TLS_CONFIGURATION);
    }

    @Test
    void closedFolderCausesReconnectClassification() {
        var error = new FolderClosedException(null);
        assertThat(MailReceiveFailureClassifier.classify(error))
                .isEqualTo(ReceiveFailureKind.CONNECTION_LOST);
    }
}
~~~

Exceptions are constructed with fake data. This test verifies the basic classifier, not that it handles every provider-specific exception. Also test nested causes/`MessagingException.getNextException()` and cases where an error lacks sufficient context.

### Tests Must Not Require Real Credentials

Classifier/backoff/state-machine unit tests must run offline. Production SMTP/IMAP credentials must never be placed into tests or CI. When connectivity tests are needed, use a test server or an approved sandbox mailbox.

## 34. Integration Testing with a Simulated IMAP/POP3 Server

Unit tests validate policy logic, whereas **connections closing mid-FETCH** and **UIDVALIDITY changes** are scenarios requiring integration tests.

You can use a test mail server supporting IMAP/POP3 such as GreenMail or a custom test server/double. Scenarios:

| Scenario | Simulation | Expected result |
|---|---|---|
| IT-01 | Normal connection | Message read, checkpoint advances |
| IT-02 | Connect refused | Classified as connectivity, backoff applied |
| IT-03 | TCP connection reset during FETCH | Open new Store/Folder, keep checkpoint intact |
| IT-04 | Read timeout | Worker does not hang indefinitely, safe retry |
| IT-05 | Wrong password | Pause/alert, no login loop |
| IT-06 | Token expired | Refresh per policy, bounded retry |
| IT-07 | Certificate hostname mismatch | Reject TLS, no trust-all |
| IT-08 | Folder closed | Reconnect and reload state |
| IT-09 | UIDVALIDITY changes | Reconcile generation; do not reuse old UIDs |
| IT-10 | Worker crash before checkpoint | Re-fetch, business idempotency prevents duplicate |
| IT-11 | Worker crash after business commit | No duplicate side effects created |
| IT-12 | Message expunged | Do not rely on old sequence numbers |
| IT-13 | POP3 UIDL changes/unsupported | Do not rely on sequence numbers; fallback policy |
| IT-14 | Two replicas on same mailbox | Lease allows one poller and dedup safely |
| IT-15 | IMAP IDLE receives BYE/timeout | IDLE restarts and reconciles UIDs |
| IT-16 | One corrupted attachment | Message quarantined, does not block all mailboxes |

### Connection Failure Tests Must Simulate the Exact Stage

A test server can drop the socket **before** sending FETCH data, **midway** through the MIME stream, and **after** the message has finished downloading. These cases differ in whether direct retry is safe or a temporary snapshot must be discarded, and in no case should the checkpoint be committed before the message is fully processed.

### Boundaries of a Test Server

A local simulated server may not share the exact timeout/connection policies of Gmail, Microsoft 365, or an enterprise mail server. It is valuable for testing reconnect logic, yet integration tests against a **real provider sandbox** remain necessary when rolling out authentication, TLS, or IMAP IDLE-specific behavior.

## 35. Spring Integration Mail: Where Should Retries Live?

If the application uses **Spring Integration Mail**, you may encounter:

- `ImapMailReceiver` for fetching mail over IMAP.
- `Pop3MailReceiver` for fetching mail over POP3.
- Polling inbound adapters using a mail-receiving message source.
- IMAP IDLE-driven channel adapters for near real-time models.
- Message channels, pollers, and error handling inside an integration flow.

Logical design:

~~~text
IMAP / POP3 Provider
        |
        v
Spring Integration Mail receiver
        |
        +-- Polling / IMAP IDLE lifecycle
        |
        v
Spring Integration channel
        |
        v
Message handler / business service
        |
        v
Durable state + checkpoint/dedup
~~~

### Separating Inbound Adapter Errors from Downstream Errors

Errors during `connect/open/fetch` occur **before** a Spring Integration message is emitted onto the channel. Errors during transform/process occur **after** the receiver has already retrieved the message.

Therefore:

1. Configure the mail receiver's timeout/TLS and authentication to match the provider.
2. Verify how the poller or IDLE adapter handles connection loss and restarts in your specific Spring Integration version.
3. Configure the error channel/`ErrorMessage` or error handler in the proper place; **do not assume all fetch errors automatically route to the same channel**.
4. Do not retry the entire mailbox whenever a downstream business handler fails; classify and quarantine failing messages.
5. Check the receiver's default flag handling, auto-delete/expunge, message conversion, and search filters; these behaviors affect re-reading.
6. Implement durable checkpointing/dedup explicitly, especially if the application cannot miss mail after restarts.

**Spring Integration Mail does not automatically turn IMAP/POP3 into a transactional exactly-once message queue.** Adapters assist with connectivity and flow integration; business idempotency, provider auth policy, and recovery semantics still have to be engineered.

### Poller Exceptions Must Not Permanently Halt Receiving Flows

An outage can cause scheduler/logging error loops or stop an adapter depending on configuration. Verify:

- Does the adapter recover/restart after `StoreClosedException`?
- Does the poller back off when auth or network fails?
- Is there a way to mark a mailbox `PAUSED` when credentials are invalid?
- If an IDLE connection closes, does the adapter reconnect and reconcile missed messages?
- If multiple instances read the mailbox, is the business handler idempotent?

Spring Integration APIs change across versions; always check your exact module/version when configuring pollers, advice, retries, or error handling rather than copying older configs unchecked.

## 36. Designing Per-Account Mailbox Polling Configuration

With multiple mailboxes, avoid a config file containing only `mail.host` and an account-agnostic scheduler. A profile should include:

~~~yaml
app:
  mail:
    receive:
      poll-delay-ms: 30000
      accounts:
        support:
          protocol: imaps
          host: imap-support.example.test
          port: 993
          username: ${SUPPORT_IMAP_USERNAME}
          password: ${SUPPORT_IMAP_PASSWORD}
          folder: INBOX
          connect-timeout-ms: 5000
          read-timeout-ms: 15000
          write-timeout-ms: 15000
          batch-size: 50
          reconnect-base-ms: 2000
          reconnect-max-ms: 60000
          require-valid-tls: true
~~~

`app.mail.receive.*` is a **custom application namespace**; Spring Boot does not automatically create an inbound IMAP consumer from this YAML alone. Application code must bind configuration, build the Jakarta Mail Session/receiver, schedule polls, checkpoint, and retry.

All numbers are illustrative and do not represent any specific provider's limits. High-latency servers or mailboxes holding large messages may require different timeouts/batch sizes.

### Configuration Must Never Contain Untrusted Input

Never take `protocol`, `host`, or `port` from arbitrary emails or HTTP requests and let the server connect to them, as that turns the application into an SSRF/network-probing vector. Mailbox profiles must be pre-approved, host/port strictly controlled, and credentials supplied from a secret store.

### Avoid Long-Lived Java Strings Holding Passwords Where Possible

Jakarta Mail commonly accepts credentials via `String` or tokens per auth API. Some secret copies cannot be reliably wiped from the JVM heap. Minimize allocation/logging paths, avoid printing configuration beans, and use a secret manager/workload identity where appropriate.

## 37. Anti-Patterns to Avoid

### 37.1. Immediately Retrying Every Connection Error in a `while(true)` Loop

Network outages produce thousands of connect attempts; bad auth can lock the account. Use backoff, jitter, pauses, and provider-aware limits.

### 37.2. Setting Only Connect Timeout and Omitting Read Timeout

TCP connect may finish quickly while `FETCH` hangs indefinitely due to the server or a large attachment. Configure connect, read, and write timeouts for the right protocol.

### 37.3. Mixing `mail.imap.*` with `getStore("imaps")`

A mismatched property prefix can cause timeout/TLS settings to be ignored. Verify the active session protocol and use the matching prefix.

### 37.4. Solving TLS Failures with Trust-All

~~~properties
mail.imaps.ssl.trust=*
~~~

Disabling certificate verification compromises credentials and message confidentiality. Fix the endpoint, certificate, or truststore instead.

### 37.5. Keeping an Old Store/Folder After a Timeout

A `Message` object may still reference a broken connection. Clean up and create a fresh Store/Folder; reload by UID.

### 37.6. Using Sequence Numbers as Long-Term IDs

Sequence numbers shift after expunge. For IMAP, use UID + UIDVALIDITY + mailbox identity.

### 37.7. Using UID Alone Without UIDVALIDITY

A UID can be reused after the mailbox generation changes. Never read from an old cursor without checking UIDVALIDITY.

### 37.8. Processing Only `UNSEEN` Messages

Users can mark messages Seen before the worker sees them, or messages may get marked Seen prematurely. This is not a reliable transaction checkpoint.

### 37.9. Marking Seen or Deleting Email Before Business Commit

If processing fails, the application can skip or lose the message. Persist results first; update flags/deletions afterward per policy.

### 37.10. Holding a DB Transaction Open Across the Entire IMAP FETCH

Downloading attachments can be slow, holding locks and DB connections open for too long. Separate network fetch/snapshotting from short transactions for business state and checkpoints.

### 37.11. Calling an External API and Assuming Checkpoints Guarantee Exactly-Once

A crash between API success and DB commit can produce duplicate side effects. Use idempotency keys and an outbox when needed.

### 37.12. Two Replicas Polling the Same Mailbox Without a Lease

Both replicas can fetch and process the same UID. Use a distributed lease/fencing or a multi-consumer design with full deduplication.

### 37.13. Reconnecting IMAP IDLE and Waiting Only for New Events

Mail arriving while disconnected may not emit another IDLE event after reconnect. Reconcile UIDs from the checkpoint.

### 37.14. Advancing the Checkpoint Past a Failed Message Without Gap Tracking

An older unprocessed UID will be skipped if the cursor moves forward. Preserve ordering or track per-message status/gaps.

### 37.15. Retrying the Entire Already-Processed Batch on Every Error

If the business handler is not idempotent, all side effects may repeat. Checkpoint per message/transaction and enforce duplicate detection.

### 37.16. Dumping Raw Emails or Exceptions for Investigation

Logs may capture PII, credentials, bodies, links, and attachments. Log mailbox profile, phase, failure kind, and attempt count; keep raw diagnostics on restricted channels only when genuinely required.

### 37.17. Not Monitoring the Timestamp of the Last Successfully Processed Message

The scheduler may keep running while reading the wrong folder or lacking fetch permissions. Track liveness, last success, processed counts, and synthetic end-to-end probes where appropriate.

### 37.18. Treating POP3 UIDL as Identical to IMAP UIDVALIDITY

POP3 UIDL has different semantics and provider-dependent support. Do not apply IMAP `UIDFolder` assumptions to POP3 deletion/migration behavior.

### 37.19. Deleting Every Message After Downloading It Once

If the DB commit fails or the content snapshot is incomplete, the email can be lost. All deletions must respect retention, durable processing, and recoverability.

### 37.20. Testing Only Against an Empty Inbox

An empty test cannot verify attachment handling, mid-FETCH reconnects, UIDVALIDITY changes, or idempotency. Use test fixtures with valid as well as malformed/large messages.

## 38. Implementation Roadmap for Mail-Receiving Recovery

A practical roadmap with Spring + Jakarta Mail/Spring Integration:

1. **Choose the protocol:** IMAP if folders, flags, and UIDs are needed; POP3 if requirements are simple and the server only supports it.
2. **Define mailbox profiles:** account, folder, provider, authentication mode, and data requirements.
3. **Configure proper TLS:** IMAPS or mandatory IMAP STARTTLS; similarly POP3S/STLS; enable hostname verification.
4. **Configure timeouts:** connect, read, write, and connection count limits.
5. **Isolate authentication lifecycle:** password/app password or OAuth2 token supplier, rotation/revocation, and pausing on auth failure.
6. **Design polling/IDLE:** choose acceptable latency and reconnect behavior when the server closes sessions.
7. **Create durable checkpoints:** IMAP by account/folder/UIDVALIDITY/UID; POP3 by UIDL if supported per policy.
8. **Build an idempotent business processor:** message key, transactional inbox, and outbox for external side effects.
9. **Define failed-message handling:** retries, quarantine/dead-letter, and separate backoff for business errors.
10. **Define reconnect error classification:** transient, auth, TLS, folder, and malformed message categories.
11. **Add backoff/jitter and a circuit breaker:** prevent login storms when mailbox servers fail.
12. **Set concurrency/leases:** one poller per mailbox when required by processing, with fencing across replicas.
13. **Control resources:** discard broken Store/Folders, clean up safely, and cap attachment sizes.
14. **Add metrics/logs:** last poll, last processed, auth failures, reconnects, checkpoint health, and backlog.
15. **Write unit/integration tests:** timeouts, disconnects, UIDVALIDITY changes, crashes before/after commit, and malformed mail.
16. **Deploy to sandbox first:** fake mailboxes/test messages, never real customer data for testing.
17. **Write runbooks:** TLS/auth/network diagnostics, UID reconciliation, account lockout, and replay.
18. **Operate periodically:** review permissions, secret rotation, folder retention, connection limits, and mailbox state.

### Recommended Behavior Matrix by Error

| Error | Retry connection? | May advance checkpoint? | Other action needed? |
|---|---|---|---|
| TCP/connect timeout | Yes, after backoff | No if message not committed | Check network |
| Temporary DNS failure | Bounded, with backoff | No | Check DNS/config |
| TLS certificate mismatch | Do not hot-retry | No | Fix trust/certificate |
| Authentication failed | Do not retry indefinitely | No | Refresh legitimately or pause |
| IMAP BYE / Store closed | Yes, fresh reconnect | Keep only prior commits | Reload UIDVALIDITY/checkpoint |
| Folder not found | Do not hot-retry | No | Fix folder/path/permissions |
| Folder closed during FETCH | Yes, reopen | Not for unfinished messages | Refetch by UID |
| Message removed | Reconcile; do not retry old object | Per gap/status policy | Determine move/deletion |
| MIME malformed | Not necessarily reconnect | Only once terminal quarantine is durably saved | Quarantine/test parser |
| Business DB unavailable | Not necessarily reconnect | No | Retry commit, protect state |
| UIDVALIDITY changed | Do not use old cursor | Not before reconciliation | Switch generation/checkpoint |
| Successful poll, no mail | Next scheduled poll | No checkpoint change needed | Track last success |

## 39. Frequently Asked Questions

**Can Spring Mail automatically receive mail from INBOX?** `JavaMailSender` is mainly for sending over SMTP. To receive mail, use Jakarta Mail `Store`/`Folder` or Spring Integration Mail inbound adapters.

**Should I choose IMAP or POP3?** IMAP is a better fit when multiple folders, UID/flags, and synchronization are needed. POP3 may suffice if you only need to download mail from a single mailbox and the provider supports UIDL as required.

**If the network drops for 10 seconds, must I restart the whole Spring Boot app?** No. A properly designed receiver cleans up broken connections, waits through backoff, creates a new Store/Folder, and resumes from the checkpoint.

**If `store.isConnected()` returns true, is a fetch guaranteed to succeed?** No. The connection can drop immediately after the check. Any mailbox operation can still throw an exception.

**Why configure both connect timeout and read timeout?** Connect timeout bounds establishing the TCP connection; read timeout bounds waiting for responses during FETCH and other commands. An established connection can still hang during reads.

**If using `getStore("imaps")`, can I set `mail.imap.timeout`?** No. Provider properties use protocol-specific prefixes, so `imaps` requires `mail.imaps.timeout` and corresponding properties.

**Should certificate checking be turned off when IMAP fails to connect?** No. Check the host, port, truststore, certificate chain, and TLS mode. Trust-all removes protection for both credentials and message contents.

**Does MFA mean an IMAP password will work?** No. Many providers require an app password or OAuth2, may block legacy basic auth, or may disable IMAP on the account.

**How should an expired OAuth2 token be handled?** Obtain a fresh token via a supported mechanism with proper caching, expiry handling, and grants, then perform a bounded retry. Do not keep reusing an expired token in a tight loop.

**Do I need a new Store for every message?** Usually no. One Store/Folder can handle a batch while healthy. After a connection failure, create fresh resources.

**Should one IMAP Store stay connected forever?** It is possible with a properly designed IDLE/long-lived architecture, provided you plan for server/NAT timeouts, reconnects, and UID reconciliation. No connection is guaranteed to stay alive forever.

**Does IMAP IDLE guarantee no missed messages?** No. IDLE is a change-notification mechanism, not a durable checkpoint. After reconnecting, you still must poll/reconcile messages by UID.

**Can I just fetch the latest 20 emails each time and process them?** Only if the business permits dropping messages beyond that threshold. For systems requiring complete processing, use UIDs/checkpoints and controlled batches.

**Why not use message numbers to track processed mail?** Sequence numbers shift whenever messages are expunged. UID combined with UIDVALIDITY is stable within one mailbox generation.

**Does a UIDVALIDITY change mean data corruption?** Not necessarily. A mailbox may have been rebuilt or modified on the server. However, old UIDs no longer carry the same meaning and must be reconciled per policy.

**Can I deduplicate using only the Message-ID header?** Not reliably. Message-ID can be missing, duplicated, changed when forwarded, or decoupled from server message state. Use the mailbox UID key together with proper business idempotency.

**Can I rely on UNSEEN to avoid duplicate processing?** Not reliably. Seen flags can be altered by other clients and are not atomically tied to DB commits.

**On `FolderClosedException`, should I immediately call `message.getContent()` again?** Do not reuse the broken message/folder object. Reconnect, open the folder, and refetch by UID.

**What if a malformed email keeps failing the handler indefinitely?** Quarantine it by message key and record a clear terminal/handled status so it does not block subsequent messages, while keeping controlled investigation/replay capability.

**What if the DB commits but the worker dies before the checkpoint?** The message may be read again. A transactional inbox/idempotent handler ensures duplicate side effects are not created.

**Should checkpoints be stored in RAM?** Only if losing state on restart is acceptable. For important business mail processing, checkpoints must be persisted durably with concurrency protection.

**Is it risky to run two replicas reading the same mailbox?** They can double-process messages or race on checkpoints. Assign clear ownership, use lease/fencing, or ensure strong idempotency.

**Is POP3 UIDL equivalent to IMAP UID?** Not completely. UIDL has its own semantics and server/provider-dependent support; it lacks IMAP's UIDVALIDITY/folder model.

**Should POP3 messages be deleted right after RETR?** Not until the data has been durably stored and processed. Confirm retention policies and the server's DELE/QUIT semantics.

**Should I retry inside the business handler on DB errors?** Yes, as a separate business/state retry. There is no need to close and reopen IMAP over a database failure.

**If `@Scheduled` keeps running without receiving mail, what might be wrong?** It could be reading the wrong folder, have a misaligned checkpoint, filter out messages, swallow auth failures, or have a stuck connection. Monitor last successful poll, fetched/processed counts, and run end-to-end tests.

**Can I log the full raw MIME message for investigation?** Not in production logs. Raw messages contain senders, recipients, subjects, attachments, and tokens/links. Use a strictly restricted diagnostic channel with short retention only when genuinely necessary.

**Do unit tests need a real Gmail/Outlook connection?** No. Unit tests for classifiers, backoff, dedup, and schedulers should use fake data. Connectivity integration tests should use a fake server or an approved sandbox account.

**Should TLS errors be retried with exponential backoff?** Static TLS configuration or certificate errors usually will not resolve through retries. Pause and fix the root cause; backoff can be applied to properly classified transient handshake/network failures.

**How should I handle provider limits on IMAP connections?** Reduce poll concurrency, enforce one owner/lease per mailbox, consider IDLE or a longer poll interval, and monitor account policies.

## 40. Summary

**Handling connection errors when receiving mail** in Spring Framework Mail requires looking well beyond a single `catch (MessagingException)` block and another `connect()` call. A reliable receiver consists of these layers:

~~~text
Configured mailbox profile
        |
        v
TLS / Authentication / Timeout
        |
        v
Jakarta Mail Store + Folder
        |
        v
Poll / IMAP IDLE (with reconnect policy)
        |
        v
UID + UIDVALIDITY / POP3 UIDL
        |
        v
Durable dedup + processing state
        |
        v
Business transaction / outbox
        |
        v
Checkpoint commit
        |
        v
Observability + alert + recovery
~~~

Five most important principles:

1. **Classify before retrying:** network timeouts can recover, whereas bad credentials, TLS errors, and folder permissions usually require different handling.
2. **Never reuse a broken connection after failure:** close and recreate Store/Folder, then resume from a durable checkpoint.
3. **Never use sequence numbers or Seen flags as processing proof:** for IMAP, track UID together with UIDVALIDITY and account/folder; for POP3, handle UIDL according to server capabilities.
4. **Accept re-reads while preventing duplicate side effects:** use a transactional inbox, business idempotency, and commit checkpoints only after durable processing.
5. **Coordinate reconnects and observability:** configure timeouts, backoff/jitter, circuit breakers, multi-replica leases, last-success metrics, and runbooks when a mailbox encounters issues.

When these layers work together consistently, a network outage, server restart, or mailbox disconnect no longer means lost emails or manual worker restarts. The system recovers unfinished work cleanly, protects accounts from retry storms, and lets operators pinpoint root causes accurately without exposing message contents.
