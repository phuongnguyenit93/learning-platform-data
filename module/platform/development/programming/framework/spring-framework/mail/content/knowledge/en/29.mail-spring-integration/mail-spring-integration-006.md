# Pollers, Queue Channels, and Send Schedules

In **Spring Framework Mail**, `JavaMailSender` handles creating and sending emails to an SMTP server. When an application needs to poll for incoming mail periodically, buffer messages in a queue, rate-limit sending, or send notifications only at a specific time, an additional orchestration layer is needed. **Spring Integration Mail** provides *Enterprise Integration Patterns* (EIP) components—including **inbound/outbound channel adapters**, **message channels**, **pollers**, and **service activators**—to compose mail tasks into an explicit flow.

A common design is:

```text
IMAP mailbox                      Business application
    |                                     |
    v                                     v
Inbound Mail Adapter               Scheduled Mail Job
    |                                     |
 Poller A                              Due-job poller
    |                                     |
    v                                     v
Inbound QueueChannel               Outbound QueueChannel
    |                                     |
 Poller B                              Poller C
    |                                     |
    v                                     v
Mail processing handler             SMTP outbound adapter
                                          |
                                          v
                                     JavaMailSender
                                          |
                                          v
                                      SMTP relay
```

Three concepts are very easy to confuse:

- **Poller**: the mechanism that wakes an endpoint periodically to read from a source or pull messages off a `PollableChannel`.
- **`QueueChannel`**: a buffer for messages between producer and consumer; by default this is an **in-memory queue**, not a durable send-schedule store.
- **Send schedule**: the business rule deciding **which email is permitted to be sent at which time**, whether as a one-off future send or a recurring schedule. This schedule usually must be persisted in a database/outbox if it needs to survive restarts.

This lesson walks through each layer using Spring Boot, Spring Integration Java DSL, and Spring Mail, while explaining backpressure, timeouts, SMTP failures, retries, transactions, multi-instance deployments, and testing strategies.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish a mailbox-reading poller, a queue-reading poller, and a scheduler deciding send timing.
2. Understand `MessageSource`, `SourcePollingChannelAdapter`, `PollableChannel`, `QueueChannel`, `PollingConsumer`, and `MailSendingMessageHandler`.
3. Configure a simple outbound flow using `QueueChannel` and `@ServiceActivator` with a poller.
4. Configure an IMAP inbound polling adapter using Java DSL.
5. Choose appropriately among `fixedDelay`, `fixedRate`, and `cron`.
6. Use `maxMessagesPerPoll` and `receiveTimeout` accurately.
7. Set queue capacity for backpressure instead of unbounded memory usage.
8. Explain why successful enqueueing differs from SMTP accepted and delivered.
9. Design send schedules with `sendAt`, timezones, cancellation, rescheduling, and idempotency.
10. Combine a transactional outbox when schedules must survive restarts.
11. Handle transient/permanent/unknown outcomes without blind retries after SMTP timeouts.
12. Test flows using Mockito, in-memory queues, and an SMTP sandbox.

## 2. Components of Spring Integration Mail

Spring Integration uses a message-centric structure:

```text
Message<?>
    = payload + headers
          |
          v
MessageChannel
          |
          v
MessageHandler
```

| Component | Function | Example in Mail Workflows |
|---|---|---|
| `Message<?>` | Wraps payload and metadata | Email command, `SimpleMailMessage`, mail received from IMAP |
| `MessageChannel` | Connects endpoints | Channel for send requests |
| `DirectChannel` | Delivers messages synchronously to subscriber | Validate/transform immediately when producer sends |
| `QueueChannel` | Buffers messages for active consumer pulling | Queue between app and SMTP sender |
| `MessageSource` | Supplies messages when polled | `MailReceivingMessageSource` |
| `SourcePollingChannelAdapter` | Polls source and forwards to channel | Checks for new mail via IMAP |
| `PollingConsumer` | Polls a `PollableChannel` and processes | Pulls pending emails from queue to send |
| `ServiceActivator` | Triggers message-processing logic | `MailSendingMessageHandler` or worker |
| `MailSendingMessageHandler` | Delegates outbound mail to Spring `MailSender` | Sends `MailMessage` over SMTP |
| `TaskScheduler`/trigger | Determines when a poller runs | fixed delay, fixed rate, cron |

**Which component does what?** A poller does not send emails itself, `QueueChannel` does not call SMTP itself, and `JavaMailSender` does not provide durable scheduling itself. They cooperate through endpoints and configuration.

### 2.1. Spring Integration Mail Is an Add-On Module

Add `spring-integration-mail` for mail-specific adapters. `spring-boot-starter-mail` supports Spring Mail/Jakarta Mail sending; `spring-integration-core` provides message flow infrastructure.

A single application can use both `JavaMailSender` in traditional code and Spring Integration outbound adapters. You do not have to rewrite every service into an Integration Flow simply because one flow needs a poller.

### 2.2. Two Meanings of "Message"

In this chapter:

- **Spring Integration Message:** `org.springframework.messaging.Message<?>`, consisting of pipeline payload + headers.
- **Email/MIME message:** `jakarta.mail.Message` or `MimeMessage`, consisting of email headers/body per email standards.

An Integration Message can carry a `SimpleMailMessage`, `MimeMessage`, or a `MailJob` DTO payload. Never confuse Spring Integration headers with SMTP/MIME headers without explicit mapping.

## 3. What Does a Poller Actually Do?

A poller has a timed **trigger** and a **receive action**.

```text
Trigger fires
     |
     v
Poller invokes receive()
     |
     +--> MessageSource (IMAP inbox, JDBC source, ...)
     |
     +--> PollableChannel (QueueChannel, ...)
     |
     v
Message received?
     |
     +--> No  -> end this poll cycle
     |
     +--> Yes -> invoke downstream handler/flow
     |
     v
Repeat up to maxMessagesPerPoll, then wait for next trigger
```

Key point: a poller runs on a **wake-up schedule**; it does not understand business fields like `sendAt` or `dueDate` inside the payload.

For example:
- The poller fires every 5 seconds.
- The queue holds a message scheduled for next week.
- If the message was already pushed into `QueueChannel` and the consumer has no time check, the message may be sent **on the very next poll**, not next week.

Therefore, **business send schedules must be enforced before enqueueing or right before submission**.

### 3.1. Source Polling and Channel Polling Are Two Different Endpoints

**Inbound adapter**:

```text
IMAP server
    |
    v
MailReceivingMessageSource.receive()
    ^
    | Poller every 10 seconds
    |
    +----> Spring Integration Message
                    |
                    v
               inboundChannel
```

**Outbound consumer**:

```text
outboundQueue
    |
    v
PollingConsumer.receive()
    ^
    | Poller every 1 second
    |
    +----> MailSendingMessageHandler
                    |
                    v
               JavaMailSender
```

A system may need both pollers, with different configurations.

## 4. How Does QueueChannel Differ from DirectChannel?

| Criterion | DirectChannel | QueueChannel |
|---|---|---|
| Delivery mode | Pushes directly to subscriber, usually on caller thread | Producer puts into queue, consumer pulls later |
| Buffers messages? | No | Yes |
| Needs consumer poller? | Usually no | Yes for polling service activators/handlers |
| Producer waits for SMTP send? | Possibly, if handler sends synchronously | Usually only waits for enqueue |
| Memory usage | Holds no default queue | Holds queued messages, up to capacity |
| Durability | Not a durable queue | Default is **in-memory**, still not durable |
| Best fit | Simple processing needing synchronous feedback | Decoupling producer/consumer pace, backpressure |

### 4.1. DirectChannel Example

```text
HTTP request
   |
   v
DirectChannel
   |
   v
MailSendingMessageHandler
   |
   v
SMTP
   |
   v
HTTP response (may have to wait for SMTP)
```

An SMTP timeout can hold the request thread for a long time and make high-traffic handling difficult.

### 4.2. QueueChannel Example

```text
HTTP request
   |
   v
QueueChannel(capacity=100)
   |
   +--> producer receives enqueue result
   |
Poller
   |
   v
MailSendingMessageHandler
   |
   v
SMTP
```

The producer does not necessarily wait for the email to be sent. However, if the application restarts while messages remain in the in-memory queue, those messages can disappear.

**Being enqueued into QueueChannel does not equal "durably scheduled".**

## 5. Dependencies and Example Versions

With Spring Boot and Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.integration:spring-integration-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Select compatible dependency versions via your project's BOM/dependency management. Examples use:
- Java 17+;
- Spring Framework 6+/Spring Boot 3+;
- Spring Integration Java DSL;
- Jakarta Mail (`jakarta.mail`), not the legacy `javax.mail` namespace.

Java DSL APIs may vary across Spring Integration branches. When using a different version, cross-check builder/poller signatures against that version's reference docs. This lesson describes general contracts and common configuration patterns.

## 6. Configuring SMTP Before Putting It into an Integration Flow

A Spring Boot application can use `spring.mail.*` to configure `JavaMailSender`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
```

This configuration illustrates SMTP STARTTLS on port 587. Replace parameters with real endpoints provided by your provider; never commit secrets.

The Spring Integration layer **does not replace**:
- TLS certificate/hostname verification;
- SMTP AUTH;
- SPF/DKIM/DMARC and verified From;
- quota/provider rate limits;
- SMTP connect/read/write timeouts.

The queue/poller orchestrates **when and how many messages are passed to the sender**. `JavaMailSender` itself is responsible for submitting MIME over SMTP.

## 7. Minimal Outbound Example: QueueChannel + Poller + JavaMailSender

This is a complete example of an **in-memory queue** for simple text emails. It is suitable for demos or flows not requiring durability.

### 7.1. Declaring the Queue and Service Activator

```java
package com.example.mailflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class OutboundMailFlowConfig {

    @Bean("outboundMailQueue")
    public PollableChannel outboundMailQueue() {
        // Buffer bounded to 100 messages inside one JVM.
        return new QueueChannel(100);
    }

    @Bean
    @ServiceActivator(
        inputChannel = "outboundMailQueue",
        poller = @Poller(
            fixedDelay = "1000",
            maxMessagesPerPoll = "5"
        )
    )
    public MessageHandler outboundMailHandler(
            JavaMailSender javaMailSender) {

        return new MailSendingMessageHandler(
            javaMailSender
        );
    }
}
```

Meaning:

- `@EnableIntegration` enables required Spring Integration infrastructure.
- The `outboundMailQueue` bean is a `PollableChannel` with capacity 100.
- `MailSendingMessageHandler` uses the configured sender.
- The poller triggers on a fixed interval per `fixedDelay`, attempting to process up to 5 messages in one poll cycle.
- If the queue is empty, the consumer has nothing to send.
- One poll does not mean only one message is sent; the count depends on `maxMessagesPerPoll` and processing duration.

Do not set `maxMessagesPerPoll` too high when SMTP sends are slow, as one poll cycle can drag on and occupy scheduler/worker resources.

### 7.2. Producer Creating SimpleMailMessage and Enqueueing

```java
package com.example.mailflow;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class SimpleMailQueuePublisher {

    private final MessageChannel outboundQueue;

    public SimpleMailQueuePublisher(
        @Qualifier("outboundMailQueue")
        MessageChannel outboundQueue) {

        this.outboundQueue = outboundQueue;
    }

    public void enqueue(String recipient, String subject,
                        String plainBody) {

        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("no-reply@example.com");
        mail.setTo(recipient);
        mail.setSubject(subject);
        mail.setText(plainBody);

        boolean queued = outboundQueue.send(
            MessageBuilder.withPayload(mail).build(),
            1000L
        );

        if (!queued) {
            throw new IllegalStateException(
                "Outbound mail queue is full"
            );
        }
    }
}
```

`SimpleMailMessage` is Spring Mail's message abstraction; `MailSendingMessageHandler` can process it and pass it to `MailSender`. For HTML/multipart/attachments, construct a `MimeMessage` via the sender or a dedicated transformer/service instead of stuffing raw HTML into `SimpleMailMessage`.

### 7.3. What Is Actually Guaranteed?

If `enqueue()` returns without error:
- `QueueChannel` has accepted the Spring Integration Message per its contract.
- SMTP **has not necessarily been called**.
- SMTP **has not necessarily accepted**.
- The email **has not necessarily been delivered**.
- The job **does not survive restarts** if the queue remains in-memory.

Thus, an API can return "queued", not "sent successfully" or "reached recipient".

### 7.4. One Singleton Sender, Many Mail Messages

`JavaMailSender` is typically managed by Spring as a shared bean. Each email still needs its own content/recipient; never hold a mutable `SimpleMailMessage` and mutate it concurrently across requests.

## 8. Inbound Example: IMAP Adapter with Poller

Spring Integration Mail provides `ImapMailReceiver` and `MailReceivingMessageSource`; Java DSL provides the `Mail.imapInboundAdapter(...)` builder.

Configuration example targeting an authorized mailbox with TLS:

```java
package com.example.mailflow;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.dsl.Mail;
import org.springframework.messaging.PollableChannel;

@Configuration
public class InboundMailFlowConfig {

    @Bean("inboundMailQueue")
    public PollableChannel inboundMailQueue() {
        return new QueueChannel(200);
    }

    @Bean
    public IntegrationFlow inboxPollingFlow(
            MailboxEndpointProperties endpoint) {

        Properties javaMailProperties = new Properties();

        javaMailProperties.put(
            "mail.imaps.ssl.checkserveridentity", "true"
        );
        javaMailProperties.put(
            "mail.imaps.connectiontimeout", "5000"
        );
        javaMailProperties.put(
            "mail.imaps.timeout", "10000"
        );

        return IntegrationFlow
            .from(
                Mail.imapInboundAdapter(
                        endpoint.storeUri()
                    )
                    .javaMailProperties(javaMailProperties)
                    .shouldDeleteMessages(false)
                    .shouldMarkMessagesAsRead(false)
                    .maxFetchSize(10),
                e -> e.poller(
                    Pollers.fixedDelay(10000)
                        .maxMessagesPerPoll(10)
                )
            )
            .channel("inboundMailQueue")
            .get();
    }
}
```

`MailboxEndpointProperties` is an application-defined configuration class returning an IMAPS store URI loaded from a secure store, **not a Spring API**. A structurally illustrative URL is `imaps://user:credential@host:993/INBOX`; never hardcode real credentials into URLs in source code or log them.

Cross-check method and builder names against your Spring Integration version. Never copy configuration URLs containing passwords from documentation examples into a real repository.

### 8.1. Two Configuration Levels Not to Confuse

In the inbound example:

- `maxFetchSize(10)` controls how many messages the receiver attempts to fetch according to the receiver's capability/implementation.
- `maxMessagesPerPoll(10)` controls how many times `MessageSource.receive()` is called by the poller in **one cycle**.

These two parameters are not a single unified quota and **do not guarantee that exactly 10 email payloads are fetched every 10 seconds**. Check the actual receiver, payload, and downstream flow semantics.

### 8.2. Do Not Delete or Mark SEEN Before Processing

`shouldDeleteMessages(false)` and `shouldMarkMessagesAsRead(false)` are cautious choices for ingestion. Marking `SEEN`, moving folders, or deleting messages should follow an explicit policy only after required data is safely persisted.

With IMAP, track `UID`/`UIDVALIDITY` and storage idempotency rather than relying solely on the unread flag. If polling fetches the same message multiple times, downstream must deduplicate.

### 8.3. IMAP IDLE Differs from Polling

If the server supports IDLE, `ImapIdleChannelAdapter` can emit messages when new mail arrives **without using a poller the way a polling inbound adapter does**. Even so, reconnects and UID resynchronization after restarts/disconnects are still required.

Do not deploy two adapters onto the same mailbox via two paths without ownership/idempotency, or the same email may be processed twice.

## 9. Using QueueChannel Between Inbound and Processor

You can wire:

```text
IMAP polling adapter
      |
      v
inboundMailQueue(capacity=200)
      |
      v
Poller every 500 ms
      |
      v
TicketIngestionHandler
      |
      v
Database / durable work
```

Consumer example:

```java
package com.example.mailflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class InboundMailConsumerConfig {

    @Bean
    @ServiceActivator(
        inputChannel = "inboundMailQueue",
        poller = @Poller(
            fixedDelay = "500",
            maxMessagesPerPoll = "10"
        )
    )
    public MessageHandler inboundMailHandler(
            TicketIngestionService ingestion) {

        return message -> ingestion.accept(
            message.getPayload()
        );
    }
}
```

`TicketIngestionService` is an application-defined service. The inbound payload can be a Jakarta Mail message or a converted content form depending on the adapter and configuration; the ingestion layer should have an explicit contract/type conversion.

### 9.1. Why Not Process the Database Directly Inside the Source Poller?

You can, if processing is very short. However, a slow API call or attachment scan can tie up the source poller. `QueueChannel` decouples producer/consumer pace in-process, enabling backpressure.

However, the default queue is in-memory: if the application crashes between receiving mail and saving to the database, messages in the queue can be lost. If the mailbox retains the email and the cursor/flag has not been confirmed yet, it can be re-scanned; however, that must be designed and tested, not assumed automatically.

### 9.2. Do Not Treat "Dequeued" as "Finished Processing"

A `PollingConsumer` usually pulls the message from the queue before invoking the handler. If the handler throws an exception:
- the message has already been dequeued at the channel layer;
- whether the message is returned depends on transaction/advice and the message store;
- an in-memory `QueueChannel` by default is not a broker with visibility timeouts, ack/nack, and DLQ like RabbitMQ.

To achieve durable at-least-once processing, you need durable storage, idempotent consumers, and proper error recovery.

## 10. fixedDelay, fixedRate, and cron

Pollers support different timing modes.

| Mode | Meaning | When to Use |
|---|---|---|
| `fixedDelay` | Pause after the previous poll cycle ends | Want to avoid piling up runs when a cycle is slow |
| `fixedRate` | Trigger schedule at fixed intervals from scheduler tick | Want steady cadence with controlled concurrency |
| `cron` | Matches specific calendar times | Want to poll at specific times/days of the week |
| Custom trigger | Determines schedule via custom logic | Complex scheduling requirements |

### 10.1. fixedDelay

Example:

```java
e -> e.poller(
    Pollers.fixedDelay(5000)
        .maxMessagesPerPoll(5)
)
```

Intuitive timeline:

```text
00:00 poll starts
00:03 poll ends
      wait 5 seconds
00:08 next poll starts
```

Fits when you want a guaranteed rest period after a processing batch, avoiding hammering the mailbox/provider back-to-back.

### 10.2. fixedRate

```java
e -> e.poller(
    Pollers.fixedRate(5000)
        .maxMessagesPerPoll(5)
)
```

Timeline:

```text
00:00 planned
00:05 planned
00:10 planned
00:15 planned
```

Do not interpret `fixedRate` as the framework unconditionally spawning unlimited concurrent runs when processing is slow. Actual behavior depends on `TaskScheduler`, executor, thread counts, and execution duration. If a poll cycle runs long, ticks may be delayed or handled per scheduler trigger semantics.

### 10.3. Cron

Illustrative idea: pull data from a source at 9:00 AM on weekdays. Spring-style cron typically includes a seconds field:

```text
0 0 9 * * MON-FRI
```

Cron is useful for "when to wake the endpoint". However, a cron poller reading a `QueueChannel` **does not inspect per-message deadlines**. If 100 emails have different `sendAt` timestamps, do not use a shared cron poller and assume each will automatically be sent at its exact time.

### 10.4. Timezones

If using a "9:00 AM" schedule, specify whether it is:
- UTC time;
- data center time;
- tenant time;
- or recipient local time.

Timezone-aware schedules must be resolved using `ZoneId`/cron triggers appropriately, avoiding reliance on the JVM default timezone. In regions with DST, 9:00 AM shifts its UTC offset seasonally; some local times do not exist or occur twice.

## 11. maxMessagesPerPoll: Bounding Reads in One Cycle

`maxMessagesPerPoll` is an important parameter that is easy to misunderstand.

Suppose `QueueChannel` holds 100 messages and the consumer has:

```java
@Poller(
    fixedDelay = "1000",
    maxMessagesPerPoll = "10"
)
```

One poll cycle can read and process at most 10 messages (or fewer if the queue empties or errors occur). Remaining messages wait for subsequent cycles per the scheduler.

For example, if each message takes 200 ms on average:
- processing 10 messages takes about 2 seconds;
- `fixedDelay=1s` adds roughly 1 second of pause afterward;
- actual throughput is lower than 10 messages/second.

Do not calculate throughput merely as `maxMessagesPerPoll / fixedDelay` when the handler has non-trivial latency.

### 11.1. Source and Consumer Defaults May Differ

In Spring Integration, `SourcePollingChannelAdapter` and `PollingConsumer` have different default values for `maxMessagesPerPoll`. Therefore **specify it explicitly**, rather than assuming both fetch the same number of messages per cycle.

### 11.2. Do Not Use Negative Values Carelessly

Some configurations allow polling until the source returns `null` when a negative limit is set. If `receive()` always has messages or blocks long, the cycle may never finish as expected, harming lifecycle management and endpoint shutdown.

Do not use "infinite poll" just to boost throughput when producers can continuously refill the queue.

### 11.3. Zero Does Not Mean "Wait for Message"

In some Spring Integration versions, `maxMessagesPerPoll=0` pauses polling on a `MessageSource`. Never treat zero as "unlimited"; verify behavior for your exact version and endpoint type.

## 12. receiveTimeout: Waiting on the Queue or Adding Latency?

`receiveTimeout` affects how long a consumer waits when calling `receive()` on a source that supports blocking.

Example:

```text
Poller every 5 seconds
receiveTimeout = 50 ms
```

If a message arrives right after a poll returned empty, it may have to wait nearly 5 seconds until the next poll runs.

Conversely:

```text
Poller frequently
receiveTimeout = 5 seconds
```

A consumer can wait longer for messages, shrinking detection gaps while holding a waiting thread. This is the idea behind long polling.

### 12.1. receiveTimeout Is Not an SMTP Timeout

Distinct parameters:

| Parameter | Applies To | Controls |
|---|---|---|
| Poller `receiveTimeout` | `PollableChannel.receive()` | Waiting for a message to become available |
| `mail.smtp.connectiontimeout` | SMTP transport | TCP connect |
| `mail.smtp.timeout` | SMTP transport | Socket read |
| `mail.smtp.writetimeout` | SMTP transport | Socket write |

Adjusting `receiveTimeout` does not fix SMTP timeouts. If an SMTP submission hangs, check SMTP properties, worker deadlines/leases, and provider behavior.

### 12.2. Do Not Let Many Long-Poll Consumers Exhaust Scheduler Threads

Many pollers with long `receiveTimeout` values can tie up scheduler/executor threads waiting on queues. When designing systems with many consumers, check task scheduler pool sizing and concurrency policies; never let every endpoint occupy a thread indefinitely.

## 13. QueueChannel Capacity and Backpressure

Example:

```java
@Bean
public PollableChannel outboundMailQueue() {
    return new QueueChannel(100);
}
```

With this setting, the queue holds at most 100 messages in memory. When full, the producer can:
- block waiting for space until timeout;
- fail to enqueue once timeout expires;
- trigger a retry/backpressure policy.

Example:

```java
boolean accepted = queue.send(
    MessageBuilder.withPayload(mail).build(),
    250L
);

if (!accepted) {
    // Must not be treated as successfully enqueued.
    throw new IllegalStateException("MAIL_QUEUE_FULL");
}
```

### 13.1. Why Are Unbounded Queues Dangerous?

When an SMTP provider slows down or suffers an outage:
- producers keep enqueueing thousands of messages;
- heap grows with message and attachment counts;
- GC pauses spike;
- `OutOfMemoryError` can crash the application;
- the entire in-memory queue is lost when the process crashes.

Bounded queues expose problems early, yet **do not replace a durable outbox**.

### 13.2. Backpressure at the Business API Layer

If an HTTP request only needs to request sending:
1. Validate and persist a durable outbox row.
2. Return `202 Accepted` after commit if that is the contract.
3. Let the downstream queue/poller process at a sustainable pace.
4. Throttle enqueueing when downstream is overloaded.

If you only enqueue into memory and return `202`, the contract must explicitly acknowledge non-durability, or the architecture must change so jobs cannot be lost.

### 13.3. A QueueChannel Is Not a Cross-Host Broker

An in-memory `QueueChannel` belongs to one JVM. If the application runs three replicas:
- each replica has its own queue;
- messages are not automatically shared;
- one pod crashing loses its unprocessed messages;
- there is no distributed ack, replication, or durable consumer group.

Use a JDBC-backed channel store/broker or database outbox when crash recovery and multi-instance load distribution are required.

## 14. Persistent QueueChannel and Message Store Limitations

Spring Integration can use persistent `MessageStore`/`MessageGroupStore` implementations to back a `QueueChannel`; one example is `JdbcChannelMessageStore`.

```text
Producer
   |
   v
QueueChannel
   |
   v
JdbcChannelMessageStore
   |
   v
Database
   |
   v
Poller -> handler
```

This reduces the risk of losing queued messages on process restart, though it still depends on:
- payload serialization/converters;
- transaction boundaries on enqueue/dequeue;
- concurrent consumers;
- schema/indexes and database availability;
- handling messages dequeued before SMTP submission completes;
- idempotency of downstream business operations.

**A persistent queue does not make SMTP send "exactly once".** An SMTP submission cannot automatically roll back if a database transaction rolls back after the relay already accepted the email.

### 14.1. When Should You Use a Persistent QueueChannel?

Useful when an application already uses Spring Integration message stores and wants pipeline recovery. For future-scheduled emails with rich business states (cancel, reschedule, expire, retry, suppression), a **transactional outbox with a dedicated schema** is usually easier to query and audit than storing serialized Spring Messages.

### 14.2. Do Not Put Mutable MimeMessage into a Persistent Store Uncontrolled

A `MimeMessage` may hold state/streams/attachments that are hard to serialize durably and depend on session lifecycles or existing files.

Instead, store:
- job ID;
- template ID/version or protected content snapshot;
- validated recipient;
- `sendAt`;
- timezone/business metadata;
- status/attempt count;
- lifecycle-managed file/object references.

Only when the consumer processes the job does it construct a fresh `MimeMessage`.

## 15. Send Schedule Is a Business Condition, Not a Polling Interval

There are three distinct requirement patterns:

| Requirement | Approach |
|---|---|
| Send email right after a business event | Persist/enqueue and process promptly |
| Send an email at a future `sendAt` | Persist job with due time and claim only when due |
| Send a report every Monday at 9:00 | Recurring schedule generates a new job per business key |

Example:

```text
Notification A: sendAt = 2026-11-13T09:00+07:00
Notification B: sendAt = 2026-11-15T14:30+07:00
Notification C: sendAt = 2026-12-01T08:00+07:00
```

A consumer polling `QueueChannel` every second **does not know** when A/B/C should be sent unless enqueue logic holds them in storage until due.

### 15.1. Correct Model for Future Sends

```text
Create scheduled mail
       |
       v
Database outbox:
   messageKey
   sendAt
   status=PENDING
       |
       v
Due-job scheduler/poller
   WHERE sendAt <= now
       |
       v
Claim job atomically
       |
       v
Mail worker / outbound adapter
       |
       v
SMTP relay
```

The scheduler checks time, the channel/worker executes processing, and the SMTP adapter sends externally.

### 15.2. A "Send Schedule" Is Not a Millisecond Guarantee

If a poller runs every 10 seconds, a job becoming due between two ticks can be picked up nearly one cycle late even in a healthy system. In production there are also:
- backlogs;
- provider latency;
- rate limits;
- clock skew;
- retries;
- application restarts;
- transaction contention.

Therefore define the SLA as: "never sent before the chosen time, and normally within X minutes after that time" instead of promising 09:00:00 sharp.

## 16. Outbox Schema for Scheduled Email

PostgreSQL example:

```sql
CREATE TABLE scheduled_email (
    message_key UUID PRIMARY KEY,
    business_event_key VARCHAR(160) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    from_identity VARCHAR(320) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    template_version VARCHAR(60) NOT NULL,
    payload_ref VARCHAR(512),
    send_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_error_code VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT scheduled_email_attempt_nonnegative
        CHECK (attempt_count >= 0),
    CONSTRAINT scheduled_email_status_valid
        CHECK (status IN (
            'PENDING',
            'SENDING',
            'RETRY_WAIT',
            'SMTP_ACCEPTED',
            'CANCELLED',
            'EXPIRED',
            'UNKNOWN',
            'DEAD_LETTER'
        ))
);

CREATE INDEX idx_scheduled_email_due
    ON scheduled_email(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE UNIQUE INDEX uq_scheduled_email_business
    ON scheduled_email(business_event_key);
```

A product may need the business event key scoped by tenant and notification type rather than globally unique on `business_event_key`. Choose uniqueness according to real business rules.

### 16.1. Distinguishing sendAt and nextAttemptAt

- `send_at`: the **earliest** timestamp the email is permitted to send per business rules.
- `next_attempt_at`: the timestamp when the next send attempt is allowed per retry/backoff.
- A job is eligible when both time conditions are met and status permits.

Example:
- `send_at` = 09:00.
- First attempt at 09:00 returns a transient error.
- `next_attempt_at` = 09:05.
- At 09:03 it must not be retried, even though `send_at` has passed.

### 16.2. Cancellation and Rescheduling

When a user cancels:
- allow cancellation only if the job has not yet started submission or per policy;
- use a conditional DB update to avoid racing with a worker claim;
- once `SMTP_ACCEPTED`, you cannot "recall SMTP" by deleting the outbox row.

When changing `sendAt`:
- update with proper row lock/versioning;
- record audit actor/time/reason;
- do not create a second logical message when merely rescheduling;
- if a worker already claimed it, concurrency rules must define whether rescheduling is allowed.

## 17. Atomically Claiming Due Jobs

With multiple workers/pods, do not use:

```text
SELECT due jobs
FOR each job:
   UPDATE status
   send
```

without locks/transactions, because two workers can select the same row and send duplicates.

A PostgreSQL example using `FOR UPDATE SKIP LOCKED`:

```sql
WITH due AS (
    SELECT message_key
    FROM scheduled_email
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at, send_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE scheduled_email e
SET status = 'SENDING',
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    attempt_count = e.attempt_count + 1,
    updated_at = :now
FROM due
WHERE e.message_key = due.message_key
RETURNING e.message_key, e.attempt_count,
          e.lease_token, e.recipient;
```

This is a skeleton for a short claim transaction. When claiming multiple rows, use distinct lease/attempt IDs or design a batch token with clear ownership. Create an attempt history row inside the same claim transaction.

### 17.1. Do Not Hold Database Locks While Calling SMTP

Appropriate workflow:

```text
Transaction 1: claim due rows + commit
        |
        v
SMTP network call (outside DB transaction)
        |
        v
Transaction 2: persist outcome + release lease
```

SMTP can take tens of seconds. Holding DB row locks across network calls increases contention and disrupts other business transactions.

### 17.2. Fencing When Persisting Outcomes

```sql
UPDATE scheduled_email
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

If the affected row count is 0, the worker no longer owns a valid lease; do not overwrite another worker's state.

Fencing protects **database state**, though it does not recall an email the SMTP relay already accepted. When a lease expires during a network call with an unknown outcome, reconciliation is needed.

## 18. Job-Creating Scheduler vs. Job-Dispatching Scheduler Are Two Separate Things

**Scheduler creating recurring jobs**:

```text
Every weekday 09:00
    |
    v
Create a new digest job
    |
    v
Persist messageKey + sendAt
```

**Dispatcher finding due jobs**:

```text
Every 1 second
    |
    v
SELECT/CLAIM due jobs
    |
    v
Submit through mail worker
```

Do not mix the two concepts. A weekly report job creates **a new logical email each period**, while the dispatcher processes jobs already created.

### 18.1. Daily Digest Cron

```java
package com.example.mailflow;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MorningDigestSchedule {

    private final ScheduledMailService scheduledMailService;

    public MorningDigestSchedule(
            ScheduledMailService scheduledMailService) {
        this.scheduledMailService = scheduledMailService;
    }

    @Scheduled(
        cron = "0 0 9 * * MON-FRI",
        zone = "Asia/Ho_Chi_Minh"
    )
    public void createDailyDigestJobs() {
        scheduledMailService.createDigestForBusinessDate();
    }
}
```

`ScheduledMailService` is a project-defined application service that must:
- determine the business date/timezone;
- generate an idempotency key per date and digest type;
- persist email jobs in the DB;
- avoid sending immediately inside a long transaction unless deliberate;
- support catching up if the scheduler was down during a scheduled run.

Enable scheduling with `@EnableScheduling` in the appropriate configuration. A cron method across multiple replicas can fire **on every replica**, so unique keys/distributed locks remain essential.

### 18.2. Catch-Up and Missed Ticks

When the application is down right at 09:00:
- do not assume `@Scheduled` automatically catches up all missed periods;
- implement a "create jobs for ungenerated business dates" policy if needed;
- use unique constraints to avoid duplicates;
- cap catch-up periods to avoid sending bursts of stale, obsolete emails.

### 18.3. User Schedules in Different Timezones

Store:
- user-intended local date/time;
- the schedule's `ZoneId`;
- the resolved `Instant`/UTC timestamp for a specific send;
- DST ambiguous/nonexistent time policy;
- audit logs on timezone changes or rescheduling.

Never compute "the user's 9:00 AM" by adding a fixed 7 hours for all tenants across regions.

## 19. Periodic Dispatcher for Due Jobs

A periodic component can invoke the dispatch service:

```java
package com.example.mailflow;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueMailDispatcher {

    private final DueMailDispatchService dispatchService;

    public DueMailDispatcher(
            DueMailDispatchService dispatchService) {
        this.dispatchService = dispatchService;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.dispatch.fixed-delay-ms:1000}"
    )
    public void dispatch() {
        dispatchService.dispatchDueBatch();
    }
}
```

This is one way to use Spring's scheduler to **wake up a use case**. To stay strictly within Spring Integration, you can build a `MessageSource` backed by a due-job repository and attach a `SourcePollingChannelAdapter` with a poller. Both approaches need proper transaction/cursor/lease semantics.

### 19.1. A Scheduler Does Not Replace a Durable Queue

If the dispatcher:
1. Claims the job as `SENDING`.
2. Enqueues the job reference into an **in-memory** `QueueChannel`.
3. Crashes before the consumer sends.

The job can get stuck in `SENDING`. Recovery must inspect leases, determine whether SMTP side effects occurred, and only retry once outcomes are safely classified.

If in-memory buffering is unnecessary, the dispatcher can claim a job and call the sending worker directly. Simpler architectures often make atomicity and duplicate prevention easier to control.

### 19.2. Recommended Architecture for Critical Emails

```text
Database scheduled_email (source of truth)
               |
               v
Due-job poller + atomic claim
               |
               v
Bounded processing worker
               |
               v
JavaMailSender / SMTP
               |
               v
Persist attempt outcome
               |
               +--> ACCEPTED
               +--> RETRY_WAIT
               +--> DEAD_LETTER
               +--> UNKNOWN
```

`QueueChannel` can serve as a **buffer/wakeup hint** when needed, but should not be the sole store holding jobs scheduled hours or days ahead.

## 20. A Complete Flow: Producer -> Queue -> Poller -> SMTP

Consider a scheduled notification use case using a message reference:

```text
POST /notifications/schedule
      |
      v
Validate recipient + template + sendAt
      |
      v
DB transaction: insert scheduled_email(PENDING)
      |
      v
HTTP 202 + messageKey
      |
      |  eligible time reached
      v
Due-job poller
      |
      v
Claim job (SENDING + lease)
      |
      v
QueueChannel (optional, bounded)
      |
      v
PollingConsumer
      |
      v
Mail renderer -> JavaMailSender
      |
      v
SMTP relay
      |
      v
Persist submission outcome
```

### 20.1. Critical Boundaries

- HTTP returns `202` after **DB commit**, not after `QueueChannel.send(...)` when the contract requires durability.
- The queue holds a job reference/command, not the sole source of state.
- Workers must verify the job has not been cancelled/expired and still holds a valid lease before submission.
- SMTP accepted does not equal delivered; providers may defer or bounce.
- SMTP errors should not be retried blindly inside every catch block.
- Side effects and state transitions need attempt IDs for auditing.

### 20.2. Using Channels for Route Separation

A system can have:

```text
scheduled_email
    |
    v
Router
    |
    +--> transactionalMailQueue -> provider A sender
    |
    +--> marketingMailQueue     -> provider B sender
    |
    +--> internalAlertQueue     -> internal relay
```

Separating queues enables applying:
- isolated concurrency/rate limits;
- policy-specific retry/backoff;
- proper TLS/credentials/verified sender identities;
- monitoring by business category;
- suppression checks for marketing.

Do not send all tenants and categories through a single queue/sender if doing so breaks isolation or violates provider quotas.

## 21. Errors, Retries, and errorChannel

Spring Integration supports error handling for message flows, yet an error channel **does not automatically turn SMTP errors into safe retries**.

Scenarios:

| Outcome | Example | Appropriate Decision |
|---|---|---|
| Failure before submission starts | Validation/template error | Stop or dead-letter per policy |
| Verified transient SMTP failure | Relay returns 421/451 before acceptance | Backoff and retry within budget |
| Permanent SMTP rejection | Invalid recipient/permission | Do not retry indefinitely |
| Timeout after DATA, no response | Relay may have accepted | `UNKNOWN`, reconciliation |
| SMTP accepted, delivery deferred | Provider is already retrying | Do not create a new submission immediately |
| Message queued but processor crashes | In-memory queue may lose it | Use designed outbox/recovery |

### 21.1. What Is an Error Channel For?

An integration endpoint can emit an `ErrorMessage` to an error channel as configured in Spring Integration. An error handler can:
- log safely;
- map error classes to domain outcomes;
- emit metrics/alerts;
- trigger retry/dead-letter workflows;
- avoid letting the scheduler stop silently.

Never write an error handler that only runs `log.error(...)` and assume the email will be retried or never lost.

### 21.2. Retry Advice

`RequestHandlerRetryAdvice` or an equivalent Spring Integration retry policy can be attached to a handler. It suits errors **confirmed safe to retry** with a bounded retry budget.

However:
- in-memory retry advice loses context on process restart;
- ambiguous-outcome errors can create duplicates;
- retrying without delay/backoff can cause SMTP storms;
- successful SMTP submissions cannot be rolled back;
- messages with expired links/tokens should not be retried.

For critical emails, maintain durable attempt history and a `RETRY_WAIT`/`UNKNOWN`/`DEAD_LETTER` state machine in the outbox; advice is only a well-defined supplementary layer.

## 22. Poller Transactions Cannot Roll Back SMTP

Spring Integration can apply transaction advice to polling endpoints, providing atomicity for certain message store/database reads and writes.

However:

```text
BEGIN DB TRANSACTION
  dequeue job
  send SMTP -> relay accepted
  UPDATE DB -> error
ROLLBACK DB
```

A DB rollback **does not recall an email** already accepted by the relay. If rolling back the queue transaction makes the job reappear, the next poll can send a duplicate.

### 22.1. Guarantees You Can Achieve

- Atomic insert of business record + outbox job in one DB transaction.
- Atomic claim + creation of attempt record.
- Atomic outcome persistence + job state update.
- Unique idempotency key preventing two logical emails from one business event.
- Fencing tokens preventing stale workers from overwriting results.

These guarantees do not equal **exactly-once SMTP delivery**.

### 22.2. When the Outcome Is Unknown

After SMTP DATA, if the network drops before a response, the application does not know whether upstream accepted it. A new worker must not blindly resend simply because a poller popped the message or a lease expired.

Instead:
- record `UNKNOWN`;
- reconcile via provider logs/APIs/events if supported;
- use provider-side idempotency if the contract truly supports it;
- or apply a documented decision accepting duplicate risk.

## 23. Concurrency and Rate Limits

A `QueueChannel` poller can read multiple messages per cycle, yet concurrent SMTP connections also depend on:
- `TaskScheduler`/`TaskExecutor`;
- number of service activators/consumers;
- number of application instances;
- SMTP send duration;
- provider quotas/rate limits.

**`maxMessagesPerPoll` is not a global concurrency limiter or token bucket.**

### 23.1. Concurrent Workers Need Explicit Limits

Example:
- Provider allows 5 concurrent SMTP connections.
- 3 application pods.
- Each pod has a 5-thread executor.

Total can reach 15 concurrent sends, exceeding the provider limit. Coordinate account-wide quotas or partition limits across pods.

### 23.2. Rate Limit vs. Concurrency

- **Concurrency:** at most N in-flight submissions at once.
- **Rate:** at most M submissions per second/minute.
- **Queue capacity:** at most K buffered messages.
- **Retry budget:** at most R attempts per logical email.

Do not try to replace all four with a single poller parameter.

### 23.3. Backoff and Jitter During Provider Outages

If 10,000 emails are pending during a 5-minute provider outage:
- polling too aggressively triggers continuous retries;
- queue memory grows;
- SMTP 4xx counts spike;
- when the provider recovers, a retry storm can hit.

Needed:
- exponential backoff + jitter;
- circuit breakers when appropriate;
- provider health/routing policies;
- throughput caps;
- backlog dashboards;
- dead-lettering for permanent/budget-exhausted failures.

## 24. Mailbox Polling: UIDs and Idempotency

When a flow uses IMAP inbox polling, note that a Jakarta Mail `Message` differs from outbound email.

An email in an IMAP folder has:
- a message sequence number, which can shift when messages are expunged;
- a more stable UID scoped by `folder + UIDVALIDITY`;
- flags like `SEEN`, `DELETED`;
- potentially untrusted headers and MIME parts.

Never use `messageNumber` as a long-term sync key. In ingestion storage, a useful identity is:

```text
(mailboxAccount, folder, uidValidity, uid)
```

### 24.1. Pollers Can Receive the Same Email Again

Even if the IMAP adapter caps `maxFetchSize` and does not mark `SEEN`, re-polling after restarts/errors can emit the same email. This is normal in an at-least-once design.

Downstream should:
1. Extract identifiable UID/metadata.
2. Check the unique key in the database.
3. Persist snapshot/processing event in a transaction.
4. Update cursor/flags per policy only after commit.
5. Skip idempotently if seen again.

### 24.2. Do Not Pass Lazy-Loading Messages Through Long-Lived Queues

A Jakarta Mail `Message` may depend on an open `Store`/`Folder` connection when reading body content. Pushing it directly onto a queue and closing the mailbox connection can cause downstream worker failures.

Instead, convert the message into:
- a DTO with already-loaded headers and required body data;
- a durable mailbox message ID/UID reference where workers know how to reconnect;
- stored and scanned attachment references.

Choose the approach matching your retention, resource limits, and privacy policies.

## 25. Recurring Schedules, Catch-Up, and DST

"Every Monday at 9:00 in the customer's time" differs from "in 10 minutes":

| Requirement | Representation |
|---|---|
| In 10 minutes | `Instant.now().plus(Duration.ofMinutes(10))` |
| Specific date in a timezone | `LocalDateTime` + `ZoneId` -> `Instant` |
| Every Monday at 9:00 | Recurrence rule/cron with timezone |
| Every 24 hours since last run | Interval/Duration per scheduler policy |

### 25.1. Do Not Use Cron to Create Duplicates Across Multiple Pods

A `@Scheduled(cron=...)` runs on every application instance unless coordinated. With 4 pods, you can generate 4 duplicate digest emails.

Solutions:
- unique key such as `tenantId + notificationType + businessDate`;
- claim/distributed lock;
- single-owner scheduler;
- idempotent job creation.

### 25.2. Do Not Send Expired Schedules

For instance, an account verification email whose token expires after 15 minutes. If the SMTP provider is down for an hour, retrying the job after the token expired is pointless.

Track:
- `expiresAt` or business deadline;
- suppression/cancel status;
- max attempts;
- policy transitioning to `EXPIRED` when no longer valid.

At dispatch time, check the deadline right before attempting, not only at enqueue time.

### 25.3. Local Time Shifts with DST

A day can:
- lack 02:30 when clocks jump forward to 03:00;
- have 01:30 twice when clocks fall back.

The system must define a policy: which offset to pick, skip, or shift the time. For global schedules, store standard IANA timezones such as `Europe/Berlin` instead of hardcoding current offsets.

## 26. Security in Pollers, Channels, and Outbound Adapters

Message flows easily become uncontrolled email relays if any service can push arbitrary recipients onto a shared channel.

### 26.1. Verify Before Enqueueing

- Is the caller authorized to send this email type?
- Is the recipient eligible per business rules?
- Has a marketing recipient opted in and not unsubscribed?
- Is the sender domain verified?
- Are the email template and URLs safe?
- Are attachments authorized and within size limits?
- Have all message fields been validated/escaped for their context?

Never let an arbitrary Integration Message header overwrite controlled `From` or `To` values.

### 26.2. Separate Channels Along Trust Boundaries

Inbound email is **untrusted** data. Never wire directly:

```text
IMAP incoming payload -> outbound SMTP channel
```

without validation/authorization, or attackers can turn the application into a mail forwarder or spam relay.

Insert a verification/translation service checking:
- mailbox account/tenant;
- sender identity;
- business rules;
- approved recipients;
- content sanitization;
- rate limits.

### 26.3. Secrets and TLS

- SMTP: STARTTLS required or implicit TLS on the proper port, with hostname verification.
- IMAP: IMAPS/STARTTLS required, CA and hostname validation.
- Fetch credentials from a secret store.
- Never log raw MIME or OAuth tokens.
- Never use `ssl.trust=*` in production.
- Restrict network egress to permitted endpoints only.

### 26.4. Email Headers Are Not Authorization

`X-Application-Message-Key` or `correlationId` aids tracing; it does not prove the caller is authorized to send. All routing and tenant identities must derive from authenticated server-side context.

## 27. Operational Observability

Do not rely solely on a "mail sent" log.

| Metric | Meaning |
|---|---|
| `mail_queue_depth` | Number of Spring Messages waiting in `QueueChannel` |
| `mail_queue_capacity` | Current capacity |
| `mail_enqueue_rejected_total` | Count of full-queue/timeout rejections |
| `mail_poller_cycle_seconds` | Duration of each poll cycle |
| `mail_poller_received_total` | Messages pulled from source |
| `mail_outbox_due_count` | Scheduled emails currently due |
| `mail_schedule_lag_seconds` | Delay from `sendAt` to claim/submission |
| `mail_active_submissions` | Active in-flight SMTP attempts |
| `mail_smtp_submit_seconds` | Submission latency |
| `mail_smtp_outcomes_total` | Accepted/transient/permanent/unknown |
| `mail_retry_wait_count` | Jobs awaiting retry |
| `mail_dead_letter_count` | Jobs stopped automatically |
| `mail_imap_fetch_errors_total` | Mailbox read errors |
| `mail_provider_rate_limited_total` | Rate-limit errors per provider |

### 27.1. Structured Logs

```json
{
  "event": "mail.submission_attempt",
  "messageKey": "msg-1001",
  "attemptId": "att-3",
  "provider": "transactional",
  "dueAt": "2026-11-13T02:00:00Z",
  "claimedAt": "2026-11-13T02:00:02Z",
  "outcome": "SMTP_ACCEPTED",
  "durationMs": 843
}
```

Never log passwords, tokens, full email bodies, or attachment bytes. `messageKey` and `attemptId` are server-generated identifiers for support and reconciliation.

### 27.2. Tracking True Delay

Distinguish:

```text
scheduledAt -> dueAt -> claimedAt -> smtpAcceptedAt
```

If `dueAt -> claimedAt` is high, investigate scheduler/queue/backlog. If `claimedAt -> smtpAcceptedAt` is high, investigate SMTP/network/rendering. If `smtpAcceptedAt -> deliveredAt` is high, inspect the provider/destination mail system.

Do not treat a steadily running poller as proof that emails are delivered on time.

## 28. Unit Testing QueueChannel Without Calling SMTP

You can test the producer enqueueing a `SimpleMailMessage` without any server.

```java
package com.example.mailflow;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.messaging.Message;

class MailQueuePublisherTest {

    @Test
    void enqueuesOneMailWithCorrectContent() {
        QueueChannel queue = new QueueChannel(10);
        SimpleMailQueuePublisher publisher =
            new SimpleMailQueuePublisher(queue);

        publisher.enqueue(
            "customer@example.net",
            "Order confirmation",
            "Hello Anh Nguyen."
        );

        Message<?> pending = queue.receive(0);

        assertThat(pending).isNotNull();
        assertThat(pending.getPayload())
            .isInstanceOf(SimpleMailMessage.class);

        SimpleMailMessage mail =
            (SimpleMailMessage) pending.getPayload();

        assertThat(mail.getTo())
            .containsExactly("customer@example.net");

        assertThat(mail.getSubject())
            .isEqualTo("Order confirmation");

        assertThat(mail.getText())
            .contains("Anh Nguyen");
    }
}
```

This test verifies content and enqueueing; it does **not** test poller scheduling or SMTP delivery. `queue.receive(0)` pulls the message directly in the test without waiting for an automatic endpoint.

### 28.1. Testing Queue Capacity

```java
@Test
void rejectsWhenBoundedQueueIsFull() {
    QueueChannel queue = new QueueChannel(1);

    SimpleMailMessage first = new SimpleMailMessage();
    first.setText("A");

    SimpleMailMessage second = new SimpleMailMessage();
    second.setText("B");

    assertThat(queue.send(
        MessageBuilder.withPayload(first).build(), 0
    )).isTrue();

    assertThat(queue.send(
        MessageBuilder.withPayload(second).build(), 0
    )).isFalse();
}
```

Import `org.springframework.messaging.support.MessageBuilder`. Capacity tests help ensure producer logic never treats `send(false)` as success.

### 28.2. Testing Poller Scheduling Differs from Testing QueueChannel

To verify an endpoint automatically polls and sends the expected number of messages per cycle, test a Spring Integration context with a test poller/scheduler. A unit test reading `QueueChannel` directly does not prove `@Poller` is active.

## 29. Integration Testing with an SMTP Test Server

Use an SMTP sandbox such as GreenMail/Mailpit or an appropriate SMTP test server to test the Spring Integration outbound flow.

Cases:
1. Push a `SimpleMailMessage` into `QueueChannel`.
2. Poller runs and `MailSendingMessageHandler` submits.
3. Test SMTP server receives exactly one email.
4. Verify recipients, subject, and body.
5. Queue is empty after successful processing.
6. Inject an SMTP error before DATA and verify error handling/retries.
7. Test rate limits and timeouts using a fault-injecting server.
8. Test application restarts with a durable outbox, not just an in-memory queue.

### 29.1. Do Not Use Arbitrary Thread.sleep

An asynchronous test needs:
- a controllable trigger/poller when possible;
- latches/barriers or bounded-timeout condition assertions;
- a test clock for `sendAt` and `nextAttemptAt`;
- bounded waits instead of scattered `Thread.sleep` calls;
- per-test isolation and cleanup.

A test that "waits 10 seconds hoping mail arrives" is flaky and slows down CI. Assert real conditions rather than relying on scheduler luck.

### 29.2. Testing Message Deadlines with Clock.fixed

Suppose a job has `sendAt` at T+10 minutes:
- T: not yet eligible, dispatch returns 0.
- T+9m59s: still not eligible.
- T+10m: claimable.
- SMTP accepted: status updated.
- Re-running dispatch: no duplicate sent.

Unit tests can verify the pure due predicate; integration tests use PostgreSQL/Testcontainers to verify SQL comparisons and atomic claims.

### 29.3. Testing Restarts

With a durable outbox:
1. Persist a future-dated job.
2. Restart the application or spin up a fresh worker context against the same DB.
3. Advance the test clock until due.
4. Run due-job polling.
5. Verify the job is still present and processed.

If only an in-memory `QueueChannel` were used, the test would show jobs lost when the queue is recreated. That is why in-memory queues must not serve as scheduling storage for critical notifications.

## 30. Failure Matrix and Remedies

| Symptom | Common Cause | Remedy |
|---|---|---|
| Sent immediately despite next-week schedule | Pushed into `QueueChannel` upfront, consumer poll does not check due time | Store `sendAt` in durable outbox, claim only when due |
| Poller does not run | Endpoint not started, integration/scheduling disabled, or missing poller on pollable channel | Check endpoint lifecycle and wiring |
| Queue full, producer stalls | Low capacity, high send timeout, slow SMTP | Backpressure, bounded wait, durable storage |
| Memory grows continuously | Unbounded queue, large attachments | Bounded queue, cap bytes/attachments |
| Emails lost after restart | In-memory `QueueChannel` | Persistent store/outbox and recovery |
| Same email sent twice across multiple pods | No atomic claim/idempotency | Unique business key, leases, fencing |
| `maxMessagesPerPoll=5` yet processing is very slow | Slow SMTP calls stretch poll cycles | Measure duration, bound work, rate/concurrency |
| Polling runs but receives no new mail | Wrong IMAP credentials/folder/search policy | Check IMAP adapter and auth/TLS |
| IMAP mail processed twice | Relying on `SEEN`/message number | `UID + UIDVALIDITY`, DB unique key |
| SMTP exception makes message vanish | Dequeued from memory without durable recovery | Persist job before submission, error/retry |
| SMTP timeout immediately resends | Not distinguishing `UNKNOWN` outcome | Reconciliation, no blind retries |
| Cron runs 3 times | 3 application replicas all trigger | Distributed ownership/idempotency |
| Yesterday's report sent 2 weeks late | No expiration/catch-up policy | Deadlines/expiry and missed-run rules |
| Wrong send time | Using host timezone or fixed offset | Store `ZoneId` and resolve DST |
| Provider reports accepted but not in inbox | Confusing SMTP submit with delivery | Track provider delivery events |
| Long poller starves other endpoints | Long `receiveTimeout` on a small pool | Pool sizing, bounded waits |
| Mail placed in `QueueChannel` never reaches handler | Wrong channel name or consumer lacks poller | Declare bean and endpoint properly |
| Integration Message carries dangerous headers | Trusting untrusted headers for recipient/From | Authorize/validate at boundary |
| Error channel only logs without updating job | Missing durable failure state | Outbox retry/dead-letter/reconciliation |
| Tests pass but production TLS fails | Test server lacked strict TLS mode | Add integration tests for certs/hostnames |
| `CANCELLED` job still gets sent | Race between cancel and worker claim | Conditional update, re-check before send |

## 31. Implementation Checklist

### 31.1. Poller

- [ ] Clarify whether the poller reads a source or reads a `QueueChannel`.
- [ ] Choose `fixedDelay`, `fixedRate`, or `cron` intentionally.
- [ ] Configure `maxMessagesPerPoll` explicitly based on throughput.
- [ ] Configure `receiveTimeout` within resource/thread budgets.
- [ ] Measure poll cycle duration and error rates.
- [ ] Avoid non-terminating poll cycles caused by unbounded receives.
- [ ] Manage startup/shutdown and error channels.
- [ ] Prevent multiple pods from polling the same mailbox/job without ownership.

### 31.2. QueueChannel

- [ ] Bounded capacity if in-memory.
- [ ] Producers handle full queue/timeouts.
- [ ] Never use in-memory queues as the sole store for future mail.
- [ ] Never share mutable MIME across threads.
- [ ] If using a persistent channel store, test serialization/transactions/recovery.
- [ ] Monitor depth/backlog/oldest age.
- [ ] Distinguish dequeue from business processing success.

### 31.3. Send Schedule

- [ ] Persist `sendAt` and exact timezone.
- [ ] Add unique business/idempotency keys.
- [ ] Claim jobs atomically using due predicates.
- [ ] Implement cancellation/reschedule/expiration rules.
- [ ] Configure max attempts/backoff/jitter and dead-lettering.
- [ ] Reconcile `UNKNOWN` rather than resending automatically.
- [ ] Do not promise millisecond precision given polling/backlog/provider latency.
- [ ] Control catch-up after downtime.
- [ ] Ensure cron across multiple replicas does not create duplicate jobs.

### 31.4. Mail Security

- [ ] SMTP TLS/hostname verification and secure credentials.
- [ ] IMAP TLS/permissions per provider if inbound is used.
- [ ] From domain and recipients are authorized.
- [ ] Marketing suppression enforced before routing.
- [ ] Never let inbound email open an arbitrary outbound relay.
- [ ] Never log raw MIME/secrets.
- [ ] Attachment/MIME parsers enforce data bounds and treat input as untrusted.

### 31.5. Tests

- [ ] Unit test producer/queue capacity.
- [ ] Unit test due-time/recurrence/timezones.
- [ ] Integration test poller/handler with SMTP sandbox.
- [ ] Integration test PostgreSQL outbox claims/concurrency/restarts.
- [ ] Test transient/permanent/`UNKNOWN` outcomes.
- [ ] Test queue full, cancellation races, and missed schedules.
- [ ] Test IMAP UID/idempotency if inbound is used.
- [ ] Test multi-replica deployments under ownership policies.

## 32. Practice Exercises

### Exercise 1 — Diagram the Flow

Distinguish three activities in a diagram: IMAP source polling, `QueueChannel` polling consumer, and scheduled email due-job dispatch. Mark where an email is considered `QUEUED` and where upstream SMTP accepted occurs.

### Exercise 2 — Outbound QueueChannel

Create `QueueChannel(20)` and a `@ServiceActivator` using `MailSendingMessageHandler` with a 1-second poller and at most 5 messages/poll. Use an SMTP sandbox; never send to the public Internet.

### Exercise 3 — Backpressure

Use `QueueChannel(1)` and have the producer send two messages with timeout 0. Verify the second returns false and the API does not report enqueue success.

### Exercise 4 — fixedDelay vs. fixedRate

A handler takes 2 seconds and the poller interval is 1 second. Analyze the actual cadence of `fixedDelay` and `fixedRate`, including `TaskScheduler` limits.

### Exercise 5 — maxMessagesPerPoll

A queue holds 25 messages. The consumer processes at most 5/poll with `fixedDelay` of 2 seconds. Determine the minimum number of poll cycles without errors and why total elapsed time also depends on handler latency.

### Exercise 6 — receiveTimeout

Compare a 5-second poller with `receiveTimeout` 50 ms against a more frequent poller with a long `receiveTimeout`. Analyze latency when a message arrives right after an empty poll.

### Exercise 7 — IMAP Inbound Adapter

Build a `Mail.imapInboundAdapter(...)` flow with `shouldDeleteMessages(false)` and `shouldMarkMessagesAsRead(false)`. Push onto a `QueueChannel` and test against an IMAP sandbox.

### Exercise 8 — Do Not Use SEEN as ACK

Trigger two polls of the same IMAP message; use unique `(mailbox,folder,uidValidity,uid)` to prove only one ticket is created.

### Exercise 9 — Sending Future Email

Accept `sendAt` as an `Instant`. Persist `scheduled_email`, poll `WHERE sendAt<=now`, and never enqueue ahead of schedule.

### Exercise 10 — Timezone

A user in `Europe/Berlin` wants email every Monday at 09:00. Design how to store `ZoneId` and handle DST so the schedule never drifts by an hour seasonally.

### Exercise 11 — Daily Digest

Use cron to create a job every weekday, unique on `(tenant,date,notificationType)`. Run two replicas and prove no duplicate logical emails are created.

### Exercise 12 — Missed Runs

The application was down for 3 days, then restarts. Design a catch-up policy: which periods should be backfilled and which are too stale and should be skipped.

### Exercise 13 — Atomic Claim

Two workers scan for due jobs in PostgreSQL simultaneously. Use `FOR UPDATE SKIP LOCKED`, a lease token, and unique attempts so only one worker claims each job.

### Exercise 14 — Error Channel

Have the outbound handler throw a simulated SMTP exception. Define how to translate the exception into durable state rather than merely logging it.

### Exercise 15 — Unknown Outcome

Simulate a connection drop after DATA. Test that the job enters `UNKNOWN` and is not automatically re-enqueued via another provider.

### Exercise 16 — Retry Backoff

Design `maxAttempts=3`, exponential backoff, and a deadline. Test with `Clock.fixed`/mutable clock without using `Thread.sleep`.

### Exercise 17 — Persistent Queue

Compare an in-memory `QueueChannel` against a JDBC-backed channel store and a dedicated outbox schema. List failures that can still happen after SMTP accepted.

### Exercise 18 — Cancellation Race

A user cancels an email at the exact moment a worker claims it. Design a conditional transaction determining whether cancellation succeeded so a job is never marked `CANCELLED` while SMTP still submits unchecked.

### Exercise 19 — SMTP Sandbox Integration

Push an email from `QueueChannel` through a poller to `MailSendingMessageHandler` and an SMTP test server. Verify recipient/subject/body; do not treat this as proof of Internet delivery.

### Exercise 20 — Monitoring

Design a dashboard for queue depth, poll duration, scheduling lag, SMTP submission latency, retries, dead letters, and `UNKNOWN`. Propose alerts when backlog breaches SLA.

## 33. References

To cross-check settings against your deployed version, consult Spring's official documentation:

- Spring Integration — Mail Support: https://docs.spring.io/spring-integration/reference/mail.html
- Spring Integration — Message Endpoints and Pollers: https://docs.spring.io/spring-integration/reference/endpoint.html
- Spring Integration — Message Channels: https://docs.spring.io/spring-integration/reference/channel/configuration.html
- Spring Integration — Java DSL Message Channels: https://docs.spring.io/spring-integration/reference/dsl/java-channels.html

Patterns in this lesson are reference designs; in real projects use compatible API and dependency versions, approved SMTP/IMAP endpoints, and state persistence matched to business requirements.

## 34. Summary

**Pollers, QueueChannel, and send schedules** solve three distinct problems in Spring Integration Mail:

1. **Pollers** schedule calls to `MessageSource.receive()` or `PollableChannel.receive()`; they do not understand a business email's send time on their own.
2. **`QueueChannel`** decouples producers from consumers and provides backpressure, yet defaults to an **in-memory** queue that does not guarantee emails survive restarts.
3. **`MailSendingMessageHandler`** is an outbound adapter using Spring's `JavaMailSender`; enqueueing onto a channel is not SMTP accepted, and SMTP accepted is not delivered.
4. `fixedDelay`, `fixedRate`, `cron`, `maxMessagesPerPoll`, and `receiveTimeout` govern cadence and receive counts; **they do not replace global rate limits or concurrency control**.
5. For **future-scheduled emails**, persist `sendAt` with state in a database/outbox and atomically claim only when due; use polling as a wake-up mechanism.
6. For **recurring schedules**, a scheduler creates email jobs with business idempotency keys; a separate dispatcher finds and processes due jobs.
7. **Backpressure** requires queue capacity, worker concurrency/rate limits, retry/backoff, and observability; never let an SMTP outage grow an in-memory queue unboundedly.
8. For critical emails, persist **outbox, attempt history, leases, retries, dead letters, and `UNKNOWN` state** to handle restarts, timeouts, ambiguous outcomes, and duplicate risks.
9. For **IMAP inbound**, combine pollers, `UID`/`UIDVALIDITY`, and idempotency; never use `SEEN` or queue dequeue as a business ACK.
10. Unit tests verify queue/time logic; integration tests verify pollers against an SMTP sandbox and durable persistence in a real database.

By clearly separating **wake-up schedules, buffering queues, and when an email is permitted to send**, you can build Spring Integration Mail flows that are observable, overload-safe, duplicate-resistant, and recoverable after failures without confusing queueing with successful mail delivery.
