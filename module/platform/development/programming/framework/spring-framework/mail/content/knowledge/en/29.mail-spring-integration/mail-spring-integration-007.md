# Inbound Mail Adapters and Message Sources

In an application using **Spring Framework Mail**, sending mail typically starts with `JavaMailSender` and the SMTP protocol. The reverse direction—**reading emails that have arrived in a mailbox and feeding them into application processing workflows**—can be built using **Spring Integration Mail**.

Spring Integration provides two key concepts:

- **Mail message source:** a component that actively fetches emails from a mailbox (e.g., IMAP or POP3) and returns an `org.springframework.messaging.Message<?>`.
- **Inbound mail adapter:** an endpoint connecting the mail source into Spring Integration, deciding *when* to fetch mail and *where* to send the results. With polling, the endpoint invokes the message source via a `Poller`; with IMAP IDLE, the adapter can react to server change notifications.

As a result, mailbox-reading logic is decoupled from business logic such as creating tickets, ingesting invoices, or updating a support request.

~~~text
Internet sender
    |
    | SMTP
    v
Mailbox on mail server (INBOX)
    |
    | IMAP/POP3
    v
Mail Receiver
    |
    v
MailReceivingMessageSource
    |
    | Poller triggers mail fetching
    v
Polling Inbound Channel Adapter
    |
    v
Spring Integration MessageChannel
    |
    v
Validation / MIME parser / durable inbox / business handler
~~~

This diagram illustrates a **polling adapter**. In an IMAP IDLE configuration, `ImapIdleChannelAdapter` handles event-driven receipt and does not need a poller calling `MailReceivingMessageSource` on a regular schedule.

**Boundary to remember:** this is an application *connecting to a mailbox*, **not an SMTP server receiving emails directly from the Internet**. The mail server/provider remains responsible for receiving and storing mail before the application reads it.

## 1. Why Do We Need an Inbound Mail Adapter?

Suppose a business has a mailbox `support@example.com`. When customers send emails, the system wants to automatically create tickets:

~~~text
Customer sends email
       |
       v
support@example.com
       |
       v
IMAP receiver
       |
       v
Normalize + validate MIME
       |
       v
Inbound-mail record
       |
       v
Ticket-processing worker
       |
       v
Ticket created
~~~

If writing a manual loop with Jakarta Mail, the application has to manage:

1. Connecting and authenticating to the mailbox.
2. Searching for matching emails.
3. Keeping/closing folders and network sessions.
4. Downloading and decoding emails.
5. Running the polling loop or IMAP IDLE loop.
6. Passing messages to handlers.
7. Classifying errors and retrying.
8. Managing `SEEN`, `DELETED` flags, or checkpoints.

Spring Integration Mail wraps the common integration boilerplate and connects into Spring Integration's **channels, message handlers, filters, transformers, and routers**. However, the framework does not automatically know which business transactions completed, so **idempotency, durable persistence, and content safety** remain the application's responsibility.

### 1.1. Use Cases

| Scenario | How Inbound Flow Is Used |
| --- | --- |
| Support mailbox | Create tickets from customer emails |
| Receiving quotes or invoices | Extract data and attachments into reconciliation workflows |
| Reply mailbox | Match reply emails to a conversation via correlation info |
| Receiving scheduled reports | Save partner files into a processing store |
| Receiving manual confirmations | Create records requesting staff review |
| Dedicated import mailbox | Feed emails into controlled data-import workflows |

Never use a `From` header alone to automatically approve money transfers, grant privileges, or execute dangerous actions; email is untrusted input.

## 2. Three-Layer Architecture: Receiver, Message Source, Endpoint

Three objects have distinct roles:

### 2.1. Mail Receiver: Mailbox Access

The receiver specializes in protocol and state:

- `ImapMailReceiver` works with IMAP/IMAPS.
- `Pop3MailReceiver` works with POP3/POP3S.

The receiver needs host, account, folder, protocol, credentials, and JavaMail/Jakarta Mail properties such as timeouts or TLS. It also defines policies for how messages are searched, flagged, or deleted.

### 2.2. Message Source: Supplying Spring Messages

`MailReceivingMessageSource` bridges a mail receiver and Spring Integration's **pollable message source** model.

Conceptually:

~~~java
Message<?> springMessage = mailMessageSource.receive();
~~~

`receive()` fetches a Spring Messaging message—or `null` if no message is available per the source's contract. **This is an API illustration, not a production loop to invoke manually inside a business service.** Normally, a polling endpoint calls it on a configured schedule.

### 2.3. Inbound Channel Adapter: Flow Entry Point

A polling inbound adapter is a **message-producing endpoint**:

~~~text
Scheduler / Poller
       |
       v
MessageSource.receive()
       |
       v
Spring Message<?>
       |
       v
Output MessageChannel
       |
       v
Handler / Flow
~~~

The endpoint is responsible for pulling messages from the source and emitting them onto the channel. It does not automatically know whether the business operation finished or was persisted to a database.

### 2.4. Comparison Table

| Component | Question It Answers | Example |
| --- | --- | --- |
| Receiver | *Which protocol and policy read the mailbox?* | `ImapMailReceiver` |
| Message source | *How is the next message fetched?* | `MailReceivingMessageSource` |
| Poller | *How often to call the source, how many per poll?* | `Pollers.fixedDelay(...)` |
| Inbound endpoint | *How is the source wired to a channel?* | `SourcePollingChannelAdapter` |
| Channel | *Which handler receives the message?* | `DirectChannel`, `QueueChannel` |
| Handler | *What operation is performed on the email?* | MIME parser, durable ingest, ticket service |
| Error channel | *Where do certain flow errors go?* | Application-configured error flow |

Do not replace these concepts with a single `MailService` class that connects to IMAP, parses PDFs, creates tickets, commits DB transactions, and sends auto-replies all at once. Layered design makes testing, extension, and isolated error handling much easier.

## 3. Polling Inbound Adapter vs. IMAP IDLE Adapter

Spring Integration Mail has two common trigger modes.

### 3.1. Polling

The poller checks the mailbox on a schedule:

~~~text
00:00 -> poll IMAP -> 0 mail
00:15 -> poll IMAP -> 2 mails
00:30 -> poll IMAP -> 1 mail
00:45 -> poll IMAP -> 0 mail
~~~

Advantages:

- Easy to reason about, pace, and bound load.
- Does not require maintaining a long-lived IMAP IDLE session.
- Fits batch processing or moderate-traffic mailboxes.
- Easy to combine with checkpoints and periodic reconciliation scans.

Limitations:

- Receipt latency depends on the poll interval.
- Polling too aggressively can hit provider connection/search quotas.
- Requires managing duplicate jobs and mailbox state.

### 3.2. IMAP IDLE

`ImapIdleChannelAdapter` leverages the IMAP IDLE protocol to receive notifications when a folder changes:

~~~text
IMAP server -- notification --> IMAP IDLE adapter
                                      |
                                      v
                                MessageChannel
                                      |
                                      v
                                 Mail handler
~~~

Advantages:

- Typically lowers latency when new emails arrive.
- Avoids executing fixed polls every few seconds just to check.

Limitations:

- Depends on server IDLE support and timeout policies.
- Must handle reconnects, dropped sessions, and delayed notifications.
- Does not guarantee "zero lost notifications" or "exactly once".

### 3.3. Comparison

| Criterion | Polling Source + Adapter | IMAP IDLE Adapter |
| --- | --- | --- |
| Mechanism | Poller calls `receive()` | Adapter reacts over IDLE connection |
| Common protocols | IMAP or POP3 | IMAP |
| Latency | Driven by poll interval | Usually near real-time |
| Connection management | Per receiver/poller behavior | Long-lived IDLE connection |
| Rate limiting | Tune poll cadence and throughput | Tune processing/connection flow |
| Reconnect | Needed on failure | Especially critical |
| Risk of misses/duplicates | Still present without checkpoints/dedup | Still present without reconciliation/dedup |
| Best fit | Batches, imports, controlled polling | Mailboxes needing fast response |

**Never run both polling and IDLE on the same receiver/folder just to be "faster and safer".** Two consumers can fight over flags, folders, and state. If periodic reconciliation is needed alongside IDLE, design a separate process with locks/cursors and idempotency.

## 4. IMAP and POP3 as Message Sources

### 4.1. IMAP

IMAP lets you work with folders, flags, and UIDs in a mailbox:

~~~text
Mail account: support@example.com
Folder: INBOX
Protocol: imaps
Port: typically 993
~~~

It fits when you need to:

- read a mailbox without deleting messages immediately;
- search for new/unprocessed messages;
- organize by folder or status;
- track `UID`/`UIDVALIDITY` inside a folder;
- recover from errors by rescanning received messages.

### 4.2. POP3

POP3 is simpler and generally used to download messages. Folder and flag capabilities are more limited than IMAP.

~~~text
Mail account: import@example.com
Protocol: pop3s
Port: typically 995
~~~

POP3 works for some simple mailbox workflows, yet makes multi-worker state management or flag-based reconciliation difficult. POP3 offers UIDL when supported by the server; never use sequence numbers as durable IDs.

### 4.3. Mailbox URL Is Only Part of Configuration

Illustrative URLs:

~~~text
imaps://reader:<secret>@mail.example.test:993/INBOX
pop3s://reader:<secret>@mail.example.test:995/INBOX
~~~

**Never copy these URLs verbatim into production.** Domain `example.test` is an example; `<secret>` is a placeholder. Use the URL format matching your Spring Integration version, escape special characters per URL syntax, and never expose secrets in source code, logs, or exceptions.

If the provider supports OAuth2/XOAUTH2 or requires tokens, configure a compatible authenticator/token provider; do not assume every mailbox still permits basic passwords.

## 5. Dependencies for Spring Boot

A Spring Boot application using Spring Integration Mail typically needs:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

Maven:

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

There is no mandatory reason to include `JavaMailSender` if the application *only receives* mail. If the application also sends emails, add `spring-boot-starter-mail` and configure SMTP appropriately.

When using Spring Boot dependency management, Spring Integration, Spring Framework, and Jakarta Mail versions must match. Modern projects use the `jakarta.mail.*` namespace; legacy Spring 5/JavaMail projects may use `javax.mail.*`. Never mix namespaces arbitrarily.

## 6. Example: Building an IMAP Message Source and Polling Inbound Flow

Building a small flow:

~~~text
ImapMailReceiver
  -> MailReceivingMessageSource
  -> Poller, up to 5 messages/poll
  -> InboundMailHandler
~~~

### 6.1. Application Configuration

~~~yaml
app:
  inbound-mail:
    url: ${INBOUND_MAIL_URL}
    poll-delay-ms: 15000
~~~

`app.inbound-mail.*` is an **application-defined** namespace, not Spring Boot properties that automatically configure inbound IMAP.

### 6.2. Creating Receiver, Message Source, and IntegrationFlow

Spring Integration Java DSL example on Jakarta Mail:

~~~java
package com.example.mail.inbound;

import java.time.Duration;
import java.util.Properties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
@EnableIntegration
public class InboundMailConfiguration {

    @Bean
    ImapMailReceiver supportMailReceiver(
            @Value("${app.inbound-mail.url}") String mailboxUrl) {

        ImapMailReceiver receiver =
                new ImapMailReceiver(mailboxUrl);

        Properties properties = new Properties();
        properties.put("mail.imaps.connectiontimeout", "5000");
        properties.put("mail.imaps.timeout", "15000");
        properties.put("mail.imaps.ssl.checkserveridentity", "true");
        receiver.setJavaMailProperties(properties);

        // Illustrates mailbox policy; not a business ACK.
        receiver.setShouldMarkMessagesAsRead(false);
        receiver.setShouldDeleteMessages(false);
        return receiver;
    }

    @Bean
    MailReceivingMessageSource supportMailSource(
            ImapMailReceiver supportMailReceiver) {
        return new MailReceivingMessageSource(supportMailReceiver);
    }

    @Bean
    IntegrationFlow supportMailFlow(
            MailReceivingMessageSource supportMailSource,
            InboundMailHandler inboundMailHandler,
            @Value("${app.inbound-mail.poll-delay-ms:15000}")
                    long pollDelayMs) {

        return IntegrationFlow
                .from(
                        supportMailSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                        Duration.ofMillis(pollDelayMs))
                                        .maxMessagesPerPoll(5)))
                .handle(message ->
                        inboundMailHandler.accept(
                                message.getPayload()))
                .get();
    }
}
~~~

Here, the **message source** is a separate bean, while DSL `IntegrationFlow.from(source, endpoint -> endpoint.poller(...))` builds the polling endpoint wiring the source into the flow.

There is no need to write a manual `while(true)` loop or `Thread.sleep(...)` to call `receive()`.

### 6.3. Handler Receiving Emails

~~~java
package com.example.mail.inbound;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.stereotype.Component;

@Component
public class InboundMailHandler {

    private final InboundMailStore store;

    public InboundMailHandler(InboundMailStore store) {
        this.store = store;
    }

    public void accept(Object payload) {
        if (!(payload instanceof MimeMessage mail)) {
            throw new IllegalArgumentException(
                    "Expected a MimeMessage payload");
        }

        try {
            String subject = mail.getSubject();
            String messageId = mail.getMessageID();

            // Illustration: safely and idempotently persist metadata/content.
            // Do not treat Message-ID as a reliable unique key.
            store.ingest(mail, subject, messageId);
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot read inbound mail metadata", ex);
        }
    }
}
~~~

`InboundMailStore` is an **application-defined interface/service**, not a built-in Spring class. A production implementation will need to:

1. Extract source identity at the mailbox/folder/UID level.
2. Read MIME within size limits.
3. Persist required metadata and attachments to storage.
4. Write a durable inbound record and deduplicate.
5. Only after committing, update mailbox state according to policy.

**This example flow does not yet solve full durable persistence or acks.** In particular, if `setShouldMarkMessagesAsRead(false)` is set, the application needs a filtering/state-transition strategy so it does not re-read the same messages forever; conversely, marking read too early risks missing mail if the handler fails.

### 6.4. Choosing the Payload Type for Your Version

In a typical receive configuration, the payload may be `jakarta.mail.internet.MimeMessage`. However, Spring Integration Mail has options for simple content and content conversion; flows may also insert transformers before the handler.

Therefore, business handlers must not assume every flow always delivers `String` or always delivers `MimeMessage`. Define the **payload contract** right after the inbound adapter and verify it in integration tests.

## 7. InboundChannelAdapter Annotation and Java DSL

Spring Integration supports multiple ways to configure endpoints:

- **Java DSL** such as `IntegrationFlow.from(source, spec -> spec.poller(...))`.
- Spring Integration annotations such as `@InboundChannelAdapter` combined with `@Poller`.
- XML namespace configuration in older projects.

An annotation example, as an alternative to the DSL polling flow above:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Bean
@InboundChannelAdapter(
        channel = "inboundRawMailChannel",
        poller = @Poller(fixedDelay = "15000"))
public MessageSource<?> inboundMailSource(
        ImapMailReceiver receiver) {
    return new MailReceivingMessageSource(receiver);
}
~~~

With this organization, declare the matching channel and handler, e.g., `@ServiceActivator(inputChannel = "inboundRawMailChannel")`.

**Choose one way to create the endpoint.** If the same source is used simultaneously by both an annotation endpoint and a DSL endpoint, two pollers can race for messages or corrupt receiver state.

### 7.1. Do Not Confuse Adapter with Transformer

The adapter brings data from **outside** into the Spring message flow. The transformer alters the **internal message representation**:

~~~text
MailReceivingMessageSource
         |
         v
Inbound Adapter
         |
         v
Spring Message<MimeMessage>
         |
         v
MIME Transformer / Normalizer
         |
         v
Spring Message<InboundMailCommand>
         |
         v
Business Handler
~~~

This is a clean boundary for converting data from a Jakarta Mail object into a validated, durably persisted DTO.

## 8. Channels and Choosing Synchronous vs. Asynchronous

After the inbound adapter, Spring Integration uses a `MessageChannel` to deliver messages to handlers. The channel directly shapes processing semantics.

### 8.1. DirectChannel: Synchronous Processing

~~~text
Poller thread
  -> receive MimeMessage
  -> DirectChannel
  -> Handler reads MIME/persists inbound record
  -> Handler returns
  -> Poller continues
~~~

Advantages:

- Handler runs on the standard dispatch thread.
- Easy to tell when the handler invocation finishes.
- Reduces the risk of passing raw MIME across thread boundaries right as the folder closes.

Disadvantages:

- Slow handlers slow down the poller.
- Expensive parsing/attachment work lowers ingestion throughput.

**Common pattern:** execute **short, durable ingestion** on the synchronous path, then let separate workers process business tasks from the DB/queue.

### 8.2. ExecutorChannel / Async Handoff

When a channel hands messages off to another thread:

~~~text
Poller receives MimeMessage
    -> executor queue
       -> worker reads MIME later
~~~

There are two risks:

1. The mail receiver may have closed the IMAP folder before the worker calls `getContent()` or `getInputStream()`.
2. A queue living only in memory is not a durable store. A crash can lose messages already fetched from the mailbox before they are durably persisted.

Therefore, **materialize required data and write an inbound record** before the async boundary. When long-running processing is needed, pass an `inboundId` or `storageRef` to workers rather than passing a raw `MimeMessage` tied to an IMAP connection.

### 8.3. Is QueueChannel a Durable Queue?

An in-memory `QueueChannel` does not automatically become a durable queue just because it has "queue" in its name. Spring Integration has several message stores/queue adapters, each with a different contract.

Distinguish among:

- in-memory queue;
- persistent message store/DB;
- external broker (RabbitMQ/Kafka/...);
- application-managed outbox or inbox table.

Only claim "message saved" once a durable storage transaction has actually succeeded.

### 8.4. Lower-Risk Organization

~~~mermaid
flowchart TD
    A["IMAP Receiver"] --> B["Polling Inbound Adapter"]
    B --> C["DirectChannel"]
    C --> D["Bounded MIME parsing"]
    D --> E["Durable inbound store"]
    E --> F["Inbound job queue"]
    F --> G["Business workers"]
    G --> H["Ticket / Invoice / Workflow"]
~~~

If ingestion can fail, never mark a message as fully processed before saving succeeds; retries and reconciliation must bridge any gap between mailbox state and DB state.

## 9. Poller: Cadence, Batch Size, and Resource Limits

The polling endpoint can be tuned:

~~~java
return IntegrationFlow
        .from(source, spec -> spec.poller(
                Pollers.fixedDelay(Duration.ofSeconds(20))
                        .maxMessagesPerPoll(10)))
        .handle(message -> inboundHandler.accept(
                message.getPayload()))
        .get();
~~~

### 9.1. Fixed Delay vs. Fixed Rate

| Schedule | General Meaning | When to Use |
| --- | --- | --- |
| Fixed delay | Wait an interval after the previous poll completes | Want to prevent overlapping poll cycles |
| Fixed rate | Attempt to poll on a fixed clock cadence | Need steady schedule, must evaluate processing time |
| Cron | Poll on a calendar schedule | Receive batches at specific hours or times |

Do not configure polling too aggressively when the mailbox provider limits connections or search requests. Polling every few seconds does not necessarily make the application process more mail if the parser/storage is slow.

### 9.2. maxMessagesPerPoll Is Not a MIME Size Limit

`maxMessagesPerPoll(10)` limits the number of receive attempts in a single poll cycle per endpoint semantics. It does **not** limit:

- individual message size;
- MIME part count;
- total attachment bytes;
- processing duration;
- total emails sitting in the mailbox.

Apply size/timeout/part-count limits separately in the parser and infrastructure.

### 9.3. Competing with the Scheduler

When running multiple pollers, thread pools, or multiple application replicas:

- bound concurrency per mailbox/provider;
- prevent two consumers from altering the same flags concurrently;
- use leases/leaders or mailbox partitioning if needed;
- persist durable idempotency keys;
- never assume a JVM-local Spring scheduler acts as a distributed lock.

### 9.4. Backpressure

If 2,000 emails arrive per minute while workers only process 300:

~~~text
Incoming rate: 2000/min
Processing rate: 300/min
Backlog growth: 1700/min
~~~

Mitigations can include:

- capping messages fetched per poll;
- pausing the adapter when storage exceeds thresholds;
- scaling workers processing persisted jobs;
- optimizing parsers and file storage;
- enforcing per-mailbox/tenant quotas/rates;
- alerting on backlog age and disk usage.

**Pausing polling to protect the system** is usually better than loading every attachment into RAM and crashing. However, evaluate mailbox retention/quotas: if left unread too long, the mailbox may fill up and stop accepting new mail.

## 10. IMAP IDLE Adapter and Message-Driven Flows

When choosing IMAP IDLE, configuration typically uses `ImapIdleChannelAdapter`. This is an **inbound channel adapter**, yet **not a polling adapter requiring `MailReceivingMessageSource`**.

Component API example:

~~~java
package com.example.mail.inbound;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.ImapIdleChannelAdapter;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.messaging.MessageChannel;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
public class IdleMailConfiguration {

    @Bean("inboundIdleChannel")
    MessageChannel inboundIdleChannel() {
        return new DirectChannel();
    }

    @Bean
    ImapIdleChannelAdapter inboundIdleAdapter(
            ImapMailReceiver idleReceiver,
            @Qualifier("inboundIdleChannel")
                    MessageChannel outputChannel) {

        ImapIdleChannelAdapter adapter =
                new ImapIdleChannelAdapter(idleReceiver);
        adapter.setOutputChannel(outputChannel);
        return adapter;
    }
}
~~~

A handler can use:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class IdleMailHandler {

    private final InboundMailHandler inbound;

    public IdleMailHandler(InboundMailHandler inbound) {
        this.inbound = inbound;
    }

    @ServiceActivator(inputChannel = "inboundIdleChannel")
    public void onMessage(Message<?> message) {
        inbound.accept(message.getPayload());
    }
}
~~~

**Note:** this example is a standalone IDLE configuration; do not run both a polling source and an IDLE adapter on the same `ImapMailReceiver`. Create a dedicated `idleReceiver` and corresponding URL/properties, similar to the polling receiver above.

### 10.1. Do Not Confuse IDLE with Exactly-Once

IDLE can drop connections, hit server timeouts, or miss notifications. Production applications need:

- reconnect/backoff;
- connection/last-success timestamp checks;
- periodic reconciliation (rescanning by checkpoint);
- idempotency if an email arrives twice;
- handling changes in IMAP `UIDVALIDITY`.

Never design assuming "if an IDLE event arrives once, the email is processed only once".

## 11. Payload, Headers, and Differences Between Spring Message and Email MIME

This is a major source of confusion.

### 11.1. Spring Messaging Message

~~~java
org.springframework.messaging.Message<?> integrationMessage;
Object payload = integrationMessage.getPayload();
var headers = integrationMessage.getHeaders();
~~~

It consists of:

- `payload`: the data object;
- `headers`: **Spring Integration flow** metadata, not necessarily Internet mail headers.

### 11.2. Jakarta Mail Message

~~~java
jakarta.mail.internet.MimeMessage mimeMessage;
String subject = mimeMessage.getSubject();
var from = mimeMessage.getFrom();
String[] values = mimeMessage.getHeader("Message-ID");
~~~

`MimeMessage` holds email content and standard email headers such as From, To, Subject, Message-ID, and Content-Type.

Do not write:

~~~java
integrationMessage.getHeaders().get("Subject");
~~~

and assume that is the real email subject. Spring Integration may map certain metadata into Spring headers, yet **the contract does not guarantee every email header is copied into Spring `MessageHeaders`**.

### 11.3. Defining the Flow Contract

A clear flow should have two boundaries:

~~~text
Adapter output:
  Message<MimeMessage>          (example)

After normalization:
  Message<InboundMailCommand>
~~~

`InboundMailCommand` can hold:

~~~java
public record InboundMailCommand(
        String mailboxProfile,
        String sourceKey,
        String normalizedFrom,
        String subject,
        String plainBodyStorageRef,
        String htmlBodyStorageRef,
        java.util.List<String> attachmentStorageRefs) {
}
~~~

This is an illustrative application-defined DTO, not a Spring Integration class. Never place a folder-bound raw `MimeMessage` object onto a long-lived queue.

## 12. Mailbox State Is Not Business Acknowledgment

IMAP supports flags, commonly:

- `\Seen`: read;
- `\Deleted`: marked for deletion, may require expunge;
- `\Flagged`: flagged;
- custom flags if supported by the provider.

Spring Integration Mail receivers can configure settings such as:

~~~java
receiver.setShouldMarkMessagesAsRead(false);
receiver.setShouldDeleteMessages(false);
~~~

**The `SEEN` flag does not mean a ticket was created successfully.**

### 12.1. Missing Email Scenario

~~~text
T1 Poller fetches email M1
T2 Receiver marks SEEN
T3 Handler begins DB write
T4 DB fails, handler throws exception
T5 Next poll searches UNSEEN -> M1 is skipped
~~~

If the application treats `SEEN` as a business acknowledgment, M1 can be silently missed.

### 12.2. Duplicate Processing Scenario

~~~text
T1 Receiver reads M1 without marking SEEN
T2 Handler creates ticket
T3 Application crashes before updating mailbox
T4 Reconnects and re-reads M1
T5 Handler creates a second ticket
~~~

If relying solely on flags, the application can create duplicate data.

### 12.3. Durable Inbox Strategy

A more reliable approach:

~~~text
1. Receiver reads M1
2. Extract mailbox + folder + UIDVALIDITY + UID
3. Stream required MIME into bounded storage
4. INSERT inbound record with unique key
5. COMMIT database + durable content
6. Update mailbox flags/checkpoints per policy
7. Worker processes inbound record idempotently
8. Record PROCESSED / RETRY_WAIT / QUARANTINED
~~~

If a crash occurs after step 5 but before step 6, step 4 on the next scan hits a unique conflict and avoids creating a second business record.

**There is no automatic distributed transaction between an IMAP server and a database simply from using Spring Integration.** You must design at-least-once ingestion, deduplication, and reconciliation.

## 13. Searching, Filtering, and Marking Read

A receiver may use a search strategy based on flags or search criteria. Default policies and customization options depend on the protocol, Spring Integration version, and mail server.

Questions to settle:

1. Does the receiver only fetch `UNSEEN`, `RECENT`, or another criterion?
2. Should emails already read by another client still be processed?
3. Should system/auto-responder emails be skipped?
4. On parse failure, is an email retried or quarantined?
5. When the server changes `UIDVALIDITY`, how is the checkpoint handled?
6. After successful processing, is the email kept, flagged, or moved to another folder?

### 13.1. Spring Integration Filters Differ from Server-Side Search

A **mail search strategy** limits which messages are downloaded from the server:

~~~text
IMAP search criteria
  -> only a subset of messages fetched
~~~

A Spring Integration **message filter** operates after the message has already entered the flow:

~~~text
Inbound adapter
  -> filter message
  -> handler
~~~

Filtering after the adapter does not necessarily reduce network traffic. Worse, if a message is filtered out after already being marked `SEEN`, it may never reappear in future polls.

For messages rejected as invalid, specify explicitly whether they are audited, quarantined, retained, or tagged with a status.

### 13.2. Flags and Criteria Are Shared State

A mailbox may be accessed concurrently by:

- humans via email clients;
- other automation bots;
- an application running across multiple pods;
- mail server auto-rules.

Another client can change flags, breaking an unread-only strategy. Never treat inbox flags as the sole store of business state for an important workflow.

## 14. Preventing Duplicate Processing: IMAP UID, UIDVALIDITY, and Message-ID

### 14.1. Message-ID Is Not Enough

The email header:

~~~text
Message-ID: <sample-123@sender.example>
~~~

is useful for correlation, yet can be missing, duplicated, forged, or reappear inside forwarded messages.

Never use `Message-ID` alone as a system-wide unique key without defining source and scope.

### 14.2. IMAP UID Is a Folder-Scoped Identifier

To identify a message in IMAP:

~~~text
mailbox_account
folder_identifier
UIDVALIDITY
UID
~~~

A UID is normally unique only **within one folder under one specific `UIDVALIDITY`**. When `UIDVALIDITY` changes, never assume an old numeric UID still points to the same message.

### 14.3. Jakarta Mail UIDFolder Example

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.UIDFolder;

public record SourceIdentity(
        long uidValidity,
        long uid) {
}

public static SourceIdentity readSourceIdentity(
        Message sourceMessage) throws Exception {

    Folder folder = sourceMessage.getFolder();
    if (!(folder instanceof UIDFolder uidFolder)) {
        throw new IllegalStateException(
                "UID is unavailable for this folder");
    }

    return new SourceIdentity(
            uidFolder.getUIDValidity(),
            uidFolder.getUID(sourceMessage));
}
~~~

**The example must run while the folder is still open.** If the payload has already been detached from its folder or the folder closed before the handler runs, reading the UID may fail.

### 14.4. Unique Constraints Stop Duplicates

PostgreSQL example:

~~~sql
CREATE TABLE inbound_mail (
    inbound_id      UUID PRIMARY KEY,
    mailbox_profile VARCHAR(100) NOT NULL,
    folder_name     VARCHAR(250) NOT NULL,
    uid_validity    BIGINT NOT NULL,
    message_uid     BIGINT NOT NULL,
    rfc_message_id  VARCHAR(1000),
    storage_ref     VARCHAR(500),
    status          VARCHAR(40) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    processed_at    TIMESTAMPTZ,
    UNIQUE (
        mailbox_profile,
        folder_name,
        uid_validity,
        message_uid
    )
);
~~~

An upsert:

~~~sql
INSERT INTO inbound_mail (
    inbound_id, mailbox_profile, folder_name,
    uid_validity, message_uid, status, created_at
)
VALUES (
    :id, :profile, :folder,
    :uid_validity, :uid, 'INGESTED', CURRENT_TIMESTAMP
)
ON CONFLICT (
    mailbox_profile, folder_name, uid_validity, message_uid
) DO NOTHING;
~~~

This is an illustrative model for IMAP, not a complete production migration. A real system needs atomic content storage or orphan-object cleanup, tenant scoping, indexes, retention, and handling messages without a UID in the handler.

### 14.5. Multiple Application Instances Reading the Same Mailbox

If two pods read M1 concurrently:

~~~text
Pod A receives M1 -> INSERT -> success
Pod B receives M1 -> INSERT -> unique conflict
~~~

The unique constraint prevents two inbound records, yet does not replace concurrency control around folder/flag contention. For critical mailboxes, consider a **single active consumer/lease/leader** and keep deduplication as a second line of defense.

## 15. MIME Parsing and Folder Lifecycle

Real-world emails can have nested MIME structures:

~~~text
MimeMessage
  └── multipart/mixed
        ├── multipart/alternative
        │     ├── text/plain; charset=UTF-8
        │     └── text/html; charset=UTF-8
        ├── application/pdf; attachment
        └── image/png; inline; Content-ID
~~~

A `MimeMessage` read from IMAP may **lazy-load** parts of its content. If the folder closes before code calls `getContent()` or `getInputStream()`, a `FolderClosedException` or I/O error can occur.

### 15.1. Materialize Before Crossing Threads

~~~text
Avoid:
  Receiver -> ExecutorChannel -> Queue<MimeMessage>
  -> receiver closes folder -> worker reads attachment

Prefer:
  Receiver -> synchronous ingest
  -> parse + stream attachment -> durable storage
  -> inbound record committed
  -> Queue<InboundMailId> -> async business worker
~~~

Spring Integration Mail offers options for folder-close behavior depending on version, yet merely keeping folders open longer does not solve durable ingestion and can exhaust connections. Design to bound the lifetime of server-dependent mail objects.

### 15.2. Traverse MIME by Type, Not Fixed Indices

Utility example:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static void visit(Part part, int depth)
        throws Exception {
    if (depth > 12) {
        throw new IllegalArgumentException(
                "MIME nesting is too deep");
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        if (multipart.getCount() > 100) {
            throw new IllegalArgumentException(
                    "Too many MIME parts");
        }
        for (int i = 0; i < multipart.getCount(); i++) {
            visit(multipart.getBodyPart(i), depth + 1);
        }
        return;
    }

    if (part.isMimeType("text/plain")) {
        // Read and enforce text size limit.
    } else if (part.isMimeType("text/html")) {
        // Sanitize/normalize; do not render directly.
    } else {
        // Attachment/inline/other: enforce size and storage controls.
    }
}
~~~

This snippet illustrates traversal; it does **not** yet include total byte caps, nested `message/rfc822` handling, malformed headers, malware scanning, ZIP bombs, or encrypted content. Production requires stricter policies.

### 15.3. Attachments Are Untrusted

A message can declare:

~~~text
Content-Disposition: attachment; filename="../../config.yml"
Content-Type: application/pdf
~~~

Never use the original filename directly as a filesystem path. Instead:

- generate a server-controlled storage ID/filename;
- retain the sanitized original name only as metadata;
- bound attachment count and total size;
- stream bytes under a quota (never unbounded `readAllBytes()`);
- validate file signatures when appropriate;
- scan for malware before distribution;
- guard against path traversal, zip bombs, and symlink misuse.

With `Part.getInputStream()`, close streams via `try-with-resources`. Never store files in directories with arbitrary execute permissions.

### 15.4. HTML Email Is Not Trusted HTML

HTML emails can contain remote images, tracking links, and unsafe markup. Never embed email HTML directly into an admin UI without sanitization. Validate URLs, block scripts/unsafe attributes, and consider render isolation.

## 16. Spring Integration Error Handling

Errors can occur at different points:

~~~text
Poller
  |
  +-- IMAP connect/auth error
  +-- mailbox folder/search error
  |
  v
Message source
  |
  +-- MIME read/parse error
  |
  v
Channel / handler
  |
  +-- validation/storage error
  +-- business processing error
~~~

### 16.1. Error Channel and Exceptions

Spring Integration provides error channel mechanisms to route certain failures from endpoints/flows. However, you must understand **whether the error is emitted synchronously or asynchronously**, whether it is wrapped in an `ErrorMessage`, which endpoint is responsible, and how the error handler processes it.

Do not assume:

- every exception automatically retries;
- failed emails always stay untouched and get re-read;
- receiving an `ErrorMessage` means the database rolled back;
- an error channel is a durable dead-letter queue;
- IMAP flags are automatically restored when a handler fails.

### 16.2. Classifying Errors

| Error Group | Example | Appropriate Response |
| --- | --- | --- |
| Authentication | Wrong credentials, expired token | Alert and refresh/rotate, avoid tight retries |
| TLS | Certificate/hostname mismatch | Fix trust/endpoint, never disable verification |
| Network | Timeout, connection reset | Backoff + jitter + reconnect |
| Folder | Renamed folder, missing permissions | Investigate config/permissions |
| Message parse | Corrupted MIME, invalid charset | Quarantine/review, avoid poison loops |
| Size/security | File too large or dangerous | Reject/quarantine per policy |
| Database | Failed to persist inbound record | Retry ingest, avoid early ack |
| Business | Cannot create ticket/invoice | Retry persisted job or mark `FAILED_FINAL` |
| Duplicate | Unique source identity already exists | No-op or reconcile status |

### 16.3. Poison Messages

If the receiver repeatedly polls the same corrupted MIME:

~~~text
M1 -> parse error
M1 -> parse error
M1 -> parse error
...
~~~

the system can stall indefinitely. Enforce attempt limits, quarantine records, and explicit mailbox handling (e.g., moving to an error folder or recording status per policy). Avoid **deleting failing emails** before persisting enough diagnostic data or fulfilling retention rules.

## 17. Credential and Connection Security

Inbound adapters require mailbox access—a sensitive privilege since they can read emails and attachments.

### 17.1. TLS Matching the Protocol

Typical ports:

| Protocol | Common Port | TLS |
| --- | --- | --- |
| IMAPS | 993 | Implicit TLS |
| IMAP | 143 | Supports STARTTLS if enabled by provider |
| POP3S | 995 | Implicit TLS |
| POP3 | 110 | Supports STARTTLS if enabled by provider |

Set properties using the matching prefix:

~~~properties
mail.imaps.connectiontimeout=5000
mail.imaps.timeout=15000
mail.imaps.ssl.checkserveridentity=true
~~~

For IMAP STARTTLS, use `mail.imap.*` properties, enabling and requiring STARTTLS per provider rules. Do not blindly set `mail.imaps.*` expecting them to apply to `imap`.

### 17.2. OAuth2/XOAUTH2

Some providers no longer allow Basic Authentication for IMAP. With OAuth2/XOAUTH2, the application may need:

- a token provider using the right OAuth scope/audience for IMAP;
- permissions on the corresponding mailbox;
- refreshing/re-acquiring tokens upon expiry;
- reconnecting when credentials rotate;
- SASL auth mechanisms supported by the Jakarta Mail implementation;
- compliance with provider rate limits and account access policies.

Never put an expiring access token into a static IMAP URL assuming it refreshes itself. Check authenticator/token callback support in your library version and provider.

### 17.3. Never Log Secrets

Avoid:

~~~java
logger.info("Mailbox URL: {}", mailboxUrl);
~~~

when the URL contains username/password/tokens. Log a non-sensitive mailbox profile such as `support_primary`, protocol, and sanitized host instead. Load secrets from a secret manager or environment, never committed to source.

### 17.4. Never Disable Certificate Verification

TLS failures can stem from host mismatches, proxies, truststores, or certificate chains. The proper fix is correcting configuration and certificate trust, **never enabling trust-all** to bypass errors in production.

## 18. Multi-Tenant and Multiple Mailboxes

A platform may receive emails for:

~~~text
tenant-a -> support-a@example.com
tenant-b -> invoices-b@example.com
tenant-c -> claims-c@example.com
~~~

Receiver architecture options:

- one inbound flow per mailbox when counts are small;
- a scheduler coordinating multiple mailboxes with bounded concurrency;
- sharding mailboxes across workers;
- provider inbound webhooks/APIs at large scale;
- a shared mailbox with verified routing if business rules permit.

### 18.1. Tenant Boundary Is Determined by Mailbox

**Never derive tenant ID from the email's `From` header.** Senders can spoof it:

~~~text
From: finance@tenant-a.example
~~~

Tenant identity should bind to a **pre-configured mailbox account/receiver profile** or a verified routing rule.

### 18.2. Many IDLE Connections Have a Cost

With thousands of mailboxes, one IDLE connection per tenant can exceed provider limits or strain sockets/threads/memory. Grouped polling with bounded concurrency or provider inbound APIs may fit better.

### 18.3. Deduplication Keys Are Mailbox-Scoped

Even if two mailboxes receive the same email with the same `Message-ID`, those may be two separate items to process. Identifiers must include mailbox/folder scope by design.

## 19. Observing Inbound Flows

Useful metrics:

| Suggested Metric | Purpose |
| --- | --- |
| `inbound_mail_poll_total` | Poll count |
| `inbound_mail_poll_errors_total` | Connect/fetch failures |
| `inbound_mail_messages_received_total` | Messages emitted by the source |
| `inbound_mail_ingested_total` | Messages durably persisted |
| `inbound_mail_duplicates_total` | Duplicates blocked |
| `inbound_mail_processing_failed_total` | Business processing failures |
| `inbound_mail_quarantined_total` | Quarantined emails |
| `inbound_mail_ingest_duration_seconds` | Parse/save duration |
| `inbound_mail_pending_jobs` | Downstream backlog |
| `inbound_mail_oldest_pending_age_seconds` | Age of oldest unprocessed job |
| `inbound_mail_last_success_timestamp_seconds` | Most recent successful fetch/persist |

These names are **application-defined instrumentation examples**; Spring Integration does not emit all of them out of the box.

### 19.1. Measure Each Stage

~~~text
mailbox checked
  -> message fetched
  -> message persisted
  -> business job processed
~~~

"Fetched" and "Ingested" differ. An email may be downloaded yet fail DB persistence; if you only measure `received_total`, dashboards can report healthy status while data is being lost.

### 19.2. Safe Metric Labels

Use a bounded label set:

~~~text
mailbox_profile=support_primary
protocol=imaps
stage=receive|ingest|process
result=ok|error|duplicate
error_class=auth|tls|network|mime|storage|unknown
~~~

Avoid labels built from raw email addresses, From, Subject, Message-ID, UID, filenames, tokens, or every dynamic tenant ID. They cause high cardinality and can leak PII.

### 19.3. Alerts

- Polling stopped for too long.
- IMAP IDLE disconnected and failed to reconnect.
- Repeated authentication/TLS failures.
- Mailbox quota nearly full.
- Fetched message count rises while ingested stalls.
- Pending inbound jobs exceed threshold.
- Sudden spike in quarantined emails or attachment errors.

Do not treat "no new mail in 30 minutes" as an error on low-traffic mailboxes. Combine last poll success, connection health, and expected traffic.

## 20. Unit Testing and Integration Testing

### 20.1. Unit Testing Handlers

Reading emails as `MimeMessage` can be tested entirely in memory:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import static org.junit.jupiter.api.Assertions.*;

@Test
void parsesSubject() throws Exception {
    MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties()));
    mime.setFrom("customer@example.net");
    mime.setRecipients(
            jakarta.mail.Message.RecipientType.TO,
            "support@example.test");
    mime.setSubject("Support request", "UTF-8");
    mime.setText("I need assistance.", "UTF-8");
    mime.saveChanges();

    assertEquals("Support request", mime.getSubject());
}
~~~

This test verifies Jakarta Mail object behavior; it does **not** prove the receiver can connect to IMAP.

### 20.2. Integration Testing with a Mock Mailbox Server

You can use **GreenMail** or a test mail server supporting IMAP/SMTP:

~~~text
JUnit
  |
  +-- start GreenMail SMTP + IMAP
  |
  +-- send fixture email via local SMTP
  |
  +-- Spring Integration poller / IDLE adapter reads IMAP
  |
  +-- handler saves inbound record
  |
  +-- assert: subject, source identity, dedupe, status
  |
  +-- cleanup server, inbox, DB, queue, files
~~~

With polling:

1. Start the test server on a dynamic port, create the mailbox, and log in.
2. Point the IMAP receiver to the exact test host/port.
3. Send a fixture message.
4. Wait for the inbound record condition with a bounded timeout.
5. Verify exactly one record and its contents.
6. Let the receiver re-read/intentionally restart and verify no duplicate record is created.
7. Stop the inbound endpoint and server, and clean up all fixtures.

### 20.3. Do Not Use Hardcoded Sleeps

Avoid:

~~~java
Thread.sleep(3000);
assertEquals(1, repository.count());
~~~

If using Awaitility in tests:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertEquals(
            1,
            repository.countByMailboxProfile(
                    "support_primary")));
~~~

`await()` is an Awaitility API when tests include that dependency; this illustrates conditional waiting rather than requiring every project to add the library.

### 20.4. Important Test Cases

| Scenario | Outcome to Verify |
| --- | --- |
| Empty inbox | Adapter emits no phantom mail |
| One email present | Received and inbound record created |
| HTML + plain | MIME parsed accurately |
| PDF attachment | Streamed and stored safely |
| Unicode email | Subject/body decoded accurately |
| Email without Message-ID | Does not crash or build bad keys |
| Re-reading same email | Does not create duplicate job/ticket |
| Crash after DB commit before marking SEEN | Reconciliation/dedup behaves cleanly |
| DB failure before durable ingest | Does not acknowledge as processed |
| Early folder close | No raw `MimeMessage` passed to late workers |
| `UIDVALIDITY` change | Old UID not treated as same message |
| IDLE disconnect | Reconnects and rescans |
| Two pods reading same mailbox | Unique constraint/lease protects |
| Expired OAuth/token | Classified as auth error, valid refresh |
| Dangerous attachment filename | No path traversal |
| Oversized message | Quarantined/rejected per policy |
| Spoofed `From` header | Does not trigger sensitive operations |

### 20.5. Cleaning Up State Between Tests

To keep tests order-independent, clean up:

- SMTP/IMAP test server or container;
- mailbox messages/flags;
- inbound DB rows;
- durable queues and delayed jobs;
- running workers/executors;
- attachments/temp files/streams;
- Spring contexts bound to dynamic test server ports.

Never purge a shared mailbox if tests run in parallel. Use per-test fixtures or test-scoped correlation/namespaces.

## 21. End-to-End Scenario: Support Mailbox to Ticket

An application receives email at `support@example.com` using IMAP polling:

~~~mermaid
flowchart TD
    A["Email arrives at support mailbox"] --> B["ImapMailReceiver"]
    B --> C["MailReceivingMessageSource"]
    C --> D["Polling inbound adapter"]
    D --> E["DirectChannel"]
    E --> F["MIME normalizer + limits"]
    F --> G{"Inbound key exists?"}
    G -->|Yes| H["Duplicate: no-op"]
    G -->|No| I["Durable inbound record"]
    I --> J["Business job"]
    J --> K["Ticket created"]
~~~

### 21.1. Valid Email

~~~text
Mailbox: support_primary
Folder: INBOX
UIDVALIDITY: 1008
UID: 5521
From: customer@example.net
Subject: Cannot log in
Attachment: screenshot.png
~~~

Workflow:

1. Poller calls message source.
2. Receiver connects via IMAP and finds messages per search strategy.
3. Adapter emits `Message<MimeMessage>` onto channel.
4. Handler extracts source identity while folder is open.
5. Handler reads MIME within bounds and saves attachment under a server-generated storage key.
6. Persist inbound record with unique key and commit.
7. Once data is safe, update mailbox flags/checkpoints per policy.
8. Business worker picks up inbound ID and creates ticket idempotently.

### 21.2. Re-Reading After Crash

If the application crashes after step 6 but before step 7, the message may be re-emitted by the receiver on reconnect. Instead of creating a second ticket, the unique-constrained `INSERT` detects it was already ingested, then reconciles mailbox state.

### 21.3. Malicious Email

If an attachment claims filename `../../application.yml` or the mail contains suspicious HTML, the parser never uses that filename as a path and never renders raw HTML. When limits are exceeded or validation fails, the message is quarantined per policy.

### 21.4. Mailbox Provider Disruption

When IMAP connections fail:

1. Endpoint reports error appropriately.
2. Reconnects with backoff instead of hammering in a tight loop.
3. Upon recovery, runs mailbox/checkpoint reconciliation.
4. Deduplication prevents duplicate tickets.
5. Dashboard shows poll errors, last successful ingest, and backlog.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `JavaMailSender` to read inbox | Wrong API role | Use mail receivers in Spring Integration |
| Adding only `spring-boot-starter-mail` | No inbound adapter included | Add `spring-integration-mail` and configure flow |
| Confusing receiver with message source | Unclear who polls vs. connects | Separate protocol, source, and endpoint |
| Letting two pollers share one source | Message/flag race conditions | Single endpoint owns source or explicit locking |
| Running polling and IDLE on same receiver | Folder contention | Pick one mode, reconcile separately |
| Polling too fast | Load/quota spikes | Tune intervals and backpressure |
| Treating `maxMessagesPerPoll` as a size limit | OOM on large attachments | Enforce byte/MIME limits |
| Putting raw `MimeMessage` in async queue | `FolderClosedException`, non-durable data | Materialize/save and pass inbound ID |
| Treating `\Seen` as business ACK | Emails missed on DB errors | Durable inbox + reconciliation |
| Skipping deduplication | Duplicate tickets after crash | `UID`/`UIDVALIDITY` + unique constraint |
| Using `Message-ID` alone as unique key | Can be missing or duplicated | Mailbox-scoped keys |
| Using sequence numbers as permanent cursors | Shift when messages are deleted | Use proper IMAP UIDs |
| Auto-deleting emails right after fetch | Data loss on handler failure | Explicit retention/ack policy |
| Not validating MIME input | XSS, path traversal, malware risk | Sanitization, size caps, scanning |
| Trusting `From` for sensitive approvals | Easily spoofed | Out-of-band identity verification when needed |
| Hardcoding credentials in URLs/logs | Mailbox compromise | Secret manager, metadata-only logs |
| Disabling TLS hostname verification | MITM exposure | Fix certificates/trust |
| Infinitely retrying poison messages | Flow stalls | Quarantine and attempt limits |
| Not comparing fetched vs. ingested | Hard to detect silent data loss | Instrument every stage |
| Only testing parsers, skipping IMAP flows | Misses connection/flag bugs | Integration tests with mock mail server |

## 23. Implementation Checklist

### Architecture

- [ ] Choose IMAP polling, IMAP IDLE, or POP3 based on requirements.
- [ ] Separate receiver, message source, poller, inbound endpoint, and handler.
- [ ] Ensure one primary endpoint owns a receiver/mailbox at a time, or define explicit concurrency control.
- [ ] Define the payload contract between adapter and transformer.
- [ ] Never push folder-bound raw `MimeMessage` objects onto a durable async queue.

### Connectivity

- [ ] Host, port, folder, and URL match provider settings.
- [ ] TLS/hostname verification matches the protocol.
- [ ] Secrets/tokens are provisioned and refreshed securely.
- [ ] Timeouts and reconnect/backoff are configured.
- [ ] Poll rate and connection quotas are monitored.

### Data and State

- [ ] Search criteria and `SEEN`/`DELETED` policies are defined.
- [ ] Durable inbound store exists before treating messages as ingested.
- [ ] Deduplication by account/folder/`UIDVALIDITY`/UID for IMAP.
- [ ] Reconciliation exists for crashes or IDLE disconnects.
- [ ] `Message-ID` is not relied upon as an absolute unique key.
- [ ] Business handlers are idempotent with retry/quarantine paths.

### Security

- [ ] MIME size/depth/part counts are bounded.
- [ ] Attachments use safe storage keys, never paths from original filenames.
- [ ] HTML is never rendered directly without sanitization.
- [ ] `From` headers are never trusted for sensitive operations.
- [ ] Email bodies, secrets, tokens, or PII are kept out of metrics/logs.
- [ ] Retention/quarantine and access controls exist.

### Operations and Testing

- [ ] Metrics exist for polls, receives, ingests, duplicates, errors, and backlog.
- [ ] Alerts fire on IMAP auth/TLS failures or stalled polls.
- [ ] Tests use an isolated IMAP/SMTP test server and dynamic ports/fixtures.
- [ ] Tests cover duplicates, crashes, `UIDVALIDITY`, IDLE reconnects, and malformed MIME.
- [ ] Mailbox, DB, queue, workers, and attachments are cleaned up after tests.

## 24. Key Takeaways

- **`ImapMailReceiver`/`Pop3MailReceiver`** handle protocol-level mailbox reading.
- **`MailReceivingMessageSource`** is the message source a polling endpoint draws emails from.
- **Polling inbound adapters** pair a source with a `Poller` and emit messages to a `MessageChannel`.
- **`ImapIdleChannelAdapter`** uses IDLE push notifications; no normal polling message source is needed.
- Spring `Message<?>` is the wrapper; Jakarta `MimeMessage` is the email content inside the payload when configured accordingly.
- **`SEEN`/`DELETED` are not business ACKs.** Preventing misses and duplicates requires a durable inbox, source identity, and reconciliation.
- A short synchronous path to parse/persist durably and pass an **inbound ID** to workers is generally safer than passing raw MIME across async boundaries.
- Email from the Internet is untrusted data; enforce controls over HTML, attachments, size, permissions, and sender identity.
- Polling intervals, IDLE connections, quotas, retries, logs, and metrics must be operated intentionally.
- Integration tests must exercise a real test mailbox, not just invoke a handler with an in-memory `MimeMessage`.

**Inbound mail adapters and message sources form the boundary between external email systems and Spring Integration flows.** Understanding the responsibilities of receivers, message sources, endpoints, and channels helps build mail-ingestion flows that are testable, operable, and recoverable on failure. For production use, pair these components with **durable ingestion, idempotency, MIME security, and mailbox sync strategies** rather than treating every fetch as a completed business transaction.

### References

- **Spring Integration Reference — Mail Support:** inbound mail adapters, IMAP/POP3, IMAP IDLE, receiver/search strategies.
- **Spring Integration Reference — Java DSL and Polling Consumer:** `IntegrationFlow`, `Pollers`, polling endpoints, message channels.
- **Spring Integration API:** `MailReceivingMessageSource`, `ImapMailReceiver`, `Pop3MailReceiver`, `ImapIdleChannelAdapter`.
- **Spring Framework Reference — Messaging:** `Message<?>`, `MessageChannel`, `MessageHandler`.
- **Jakarta Mail API:** `Session`, `Message`, `MimeMessage`, `Folder`, `UIDFolder`, `Multipart`, and `Part`.
- **RFC 3501 — Internet Message Access Protocol Version 4rev1:** folders, flags, UID/`UIDVALIDITY`; check updates in IMAP4rev2.
- **RFC 9051 — Internet Message Access Protocol Version 4rev2:** IMAP protocol updates.
- **RFC 2177 — IMAP4 IDLE:** notification mechanism over an IDLE connection.
- **RFC 1939 — Post Office Protocol Version 3:** POP3, message retrieval, and UIDL.
- **RFC 5322 — Internet Message Format:** From, Subject, Message-ID, and headers.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** multipart, charsets, transfer encoding, and attachments.
- **Your mailbox provider's documentation:** IMAP/POP3 authorization, OAuth2/XOAUTH2, folder behavior, TLS, quotas, and connection limits.
