# Error Channels and Dead-Letter Flows

## 1. Why Do Email Receiving/Sending Flows Need a Dedicated Error Path?

In **Spring Integration Mail**, an application may connect to IMAP/POP3 to receive mail, pass messages across channels, parse MIME, create tickets, ingest documents, update bounce statuses, or send emails over SMTP. Any of those steps can fail at different times:

- The IMAP server is unreachable or credentials expired.
- An email has malformed MIME, an oversized attachment, or prohibited content.
- A handler fails while mapping email data into business objects.
- The database is temporarily unable to persist results.
- The ticket-creation service times out even though it may have created the ticket.
- The SMTP relay temporarily rejects sending or returns an authentication error.
- A worker stops after causing a side effect before updating state.

Merely wrapping a handler in `try/catch` and logging can **lose track of emails**, endlessly reprocess a failing message, or create duplicate actions on retries.

An **error channel** in Spring Integration is a mechanism that routes exception details into a message flow for centralized or per-flow handling. A **dead-letter flow** is the process that ends automatic retries by persisting a failed message/job into a durable store with metadata for investigation and controlled redrive.

~~~text
Mailbox / inbound gateway / mail task
                 |
                 v
          Integration flow
          parse -> validate
                 |
                 v
          business handler
                 |
         +-------+--------+
         |                |
         v                v
      SUCCESS          EXCEPTION
         |                |
         v                v
  Commit processing   ErrorMessage
  state / outcome          |
                          v
                     Error channel
                          |
                          v
                 Failure classification
                          |
           +--------------+---------------+
           |              |               |
           v              v               v
        RETRY          DEAD LETTER       UNKNOWN
       scheduled       / quarantine     / reconcile
           |              |               |
           v              v               v
      Next attempt     Operator review   Avoid blind retry
~~~

> **Important:** Spring Integration provides `errorChannel` and `ErrorMessage` mechanisms, yet **does not automatically turn every failure into a durable dead-letter record**. To avoid losing emails across restarts, the application must configure durable queues/brokers/databases and explicit state transitions.

## 2. What Is an Error Channel?

Spring Integration models systems as **message -> channel -> endpoint/handler**. When an error is turned into a message, its payload is typically a `Throwable` (often a `MessagingException`), wrapped in a Spring Messaging `ErrorMessage`.

An ordinary message:

~~~text
Message<?>:
  payload: MimeMessage / application command
  headers:
    id
    timestamp
    correlationId (if supplied)
    ...
~~~

When an error is published:

~~~text
ErrorMessage:
  payload: Throwable
    possibly MessagingException
       cause: original failure
       failedMessage: Message<?> (if available)
  headers: error context
  originalMessage: optional
~~~

### 2.1. Key Classes to Know

| Component | Role |
| --- | --- |
| `org.springframework.messaging.Message<?>` | Application message passed between components |
| `org.springframework.messaging.support.ErrorMessage` | Message carrying an exception as its payload |
| `org.springframework.messaging.MessagingException` | Exception optionally carrying `failedMessage`, linking failures to messages |
| `org.springframework.messaging.MessageChannel` | Channel interface for sending messages |
| `org.springframework.integration.channel.DirectChannel` | Channel processing synchronously on the sender thread |
| `org.springframework.integration.channel.ExecutorChannel` | Asynchronous dispatch via an executor |
| `org.springframework.integration.channel.QueueChannel` | Pollable channel (in-memory queue by default unless backed by a durable message store) |
| `org.springframework.integration.channel.PublishSubscribeChannel` | Broadcasts to multiple subscribers |
| `org.springframework.integration.core.MessagingTemplate` | Sends/receives messages and routes errors per context |

The name `errorChannel` is the **standard channel name** used by Spring Integration where applicable. Applications can define dedicated channels such as `mailErrorChannel` to isolate mail failures from other integration flows.

### 2.2. ErrorMessage Is Not a Copy of the Original Email

Suppose:

~~~java
throw new IllegalArgumentException(
        "Missing required order reference");
~~~

The error flow may receive an `ErrorMessage` whose exception is wrapped in a `MessagingException`. Original email context may reside in:

- `MessagingException.getFailedMessage()` if the exception carried a failed message.
- `ErrorMessage.getOriginalMessage()` if supplied by the error emitter.
- Previously propagated correlation/internal delivery ID headers.
- The inbox/outbox/database record linked to the attempt.

**Never assume every `ErrorMessage` carries `failedMessage` or `originalMessage`.** An IMAP connection failure before fetching mail is a prime example: there is no application message yet to attach.

### 2.3. Error Channels Differ from Business Dead-Letter Stores

~~~text
Error channel:
  "An exception occurred that needs handling right now in the integration runtime."

Dead-letter store:
  "An unprocessable unit of work has been persisted
   into a terminal state with enough metadata to investigate."
~~~

Standard `DirectChannel` and `PublishSubscribeChannel` are **not durable message stores**. A default `QueueChannel` does not guarantee recovery across JVM restarts either. For a genuinely durable DLQ, use:

- A `FAILED`/`DEAD_LETTER` database table with transactions and audits.
- A broker queue configured with durability, publisher confirms, and consumer acks.
- A Kafka dead-letter topic with appropriate retention, ACLs, and consumer policies.
- A persistent message store backing a pollable channel if your architecture uses one.

These options have distinct semantics. Never call a `DirectChannel` named `deadLetterChannel` a "safely persisted dead letter" when it merely hands exceptions to an in-JVM handler.

## 3. Where Do Synchronous and Asynchronous Errors Go?

Understanding thread boundaries is the most critical factor when designing `errorChannel`.

### 3.1. Synchronous Flows with DirectChannel

~~~text
Caller
  |
  v
DirectChannel
  |
  v
Handler
  |
  +-- throws exception
  |
  v
Caller receives exception
~~~

A handler on `DirectChannel` normally runs on the same thread calling `send`. When it throws an exception, that exception can propagate back to the caller up the call stack. **Not every synchronous failure automatically turns into an `ErrorMessage` on the global `errorChannel`.**

If the caller wants centralized handling, it can catch and publish an `ErrorMessage` (or use an Integration component with error handling), while keeping retry/transaction boundaries explicit.

### 3.2. Asynchronous Flows with ExecutorChannel

~~~text
Caller --send--> ExecutorChannel
                      |
                      v
                 Worker thread
                      |
                      v
                    Handler
                      |
                      v
                   Exception
                      |
                      v
                ErrorMessage path
~~~

When an endpoint runs on another thread, the exception **cannot be thrown back to the original caller like a synchronous call**. Spring Integration can publish the failure to an error channel when the messaging context and error handler are configured.

The error destination may come from the message's `errorChannel` header, endpoint/poller configuration, or a default channel per component capability. **Do not assume an `ExecutorChannel` design always behaves identically to a poller or gateway**, because producers, handlers, and error infrastructure each have their own contracts.

### 3.3. Pollers Are a Key Error-Handling Boundary

A polling inbound mail adapter typically executes:

~~~text
Scheduler
   |
   v
Poller task
   |
   v
Read IMAP/POP3 message
   |
   v
Send to downstream flow
   |
   +--> exception
             |
             v
        Poller error handler
             |
             v
       Configured error channel
~~~

This is a convenient place to **specify a dedicated error channel on the poller**. If the error is handled and logged, the scheduler can keep polling on the next cycle. If the error keeps recurring on the same email, maintain retry/quarantine/dead-letter state to prevent an infinite failure loop.

### 3.4. Comparison Table

| Error Source | Can Exception Throw to Caller? | When Does the Error Channel Receive It? |
| --- | --- | --- |
| Handler via `DirectChannel` | Usually yes | If caller/endpoint explicitly routes or handles errors accordingly |
| Handler via `ExecutorChannel` | Not on original caller's call stack | When async error handler publishes `ErrorMessage` |
| Mail polling inbound adapter | No HTTP caller waiting for result | Poller error handling can publish it |
| Synchronous gateway with reply/timeout | Usually returns exception to caller | Per reply/error channel/gateway configuration |
| Scheduled service calling `JavaMailSender.send` directly | Yes on that service thread | **Does not enter Spring Integration `errorChannel` automatically** just because the app uses Spring Integration |
| HTTP webhook controller | Exception may become HTTP response | Only enters error flow if controller/service sends a message or routes errors deliberately |

What decides is not the framework name alone, but the **boundary where exceptions are caught, converted to messages, and sent onto channels**.

## 4. Global Error Channel vs. Dedicated Mail Error Channel

In Spring Integration, `errorChannel` is the default channel used by the runtime in error-publication scenarios. In an application spanning mail, file polling, Kafka, HTTP, and other flows, consider dedicated channels per domain so each has the right retry policy and owners.

Example:

~~~text
Global errorChannel
   |
   +--> generic logging/alerting

mailErrorChannel
   |
   +--> mail-specific classifier
   +--> retry/dead-letter state transitions

fileErrorChannel
   |
   +--> file import recovery flow
~~~

### 4.1. Why Not Send Everything to the Global errorChannel?

An IMAP `FolderClosedException`, a CSV parser error, and an SMTP `MailAuthenticationException` require different remedies. If everything flows into one generic handler:

- Source identity is insufficient to tell which message needs retrying.
- Permanent errors may get retried.
- Dead letters mix inbox failures with outbound delivery failures.
- A batch parser bug can flood logs/alerts.
- Admins struggle to identify the owner/tenant/region of failed work.

A global error channel helps for **fallback visibility**, yet should not replace per-flow error policies.

### 4.2. Separating Errors Along Business Boundaries

An application with two mail flows:

~~~text
Inbound:
  IMAP -> parse -> create support ticket
                 |
                 +--> inboundMailErrorChannel

Outbound:
  Outbox -> render -> SMTP send
                    |
                    +--> outboundMailErrorChannel
~~~

On the **inbound** side, retrying means re-reading/reprocessing an already received email. On the **outbound** side, retrying may send the same email over SMTP again and **carries duplicate risk when outcomes are ambiguous**. Sharing a single generic `RETRY` hides which kind of side effect is involved.

## 5. Example Configuring mailErrorChannel in Spring Integration

A simple architecture has three components:

1. An inbound message source reading emails from IMAP.
2. An `IntegrationFlow` routing emails to a processing service.
3. A `mailErrorChannel` receiving `ErrorMessage` published by the poller/endpoint.

The snippets below use Spring Boot 3.x, Java 17+, and Spring Integration 6.x style **to illustrate structure**, not a standalone runnable project from copying a single class. Align dependency versions and API overloads with your Spring Boot/Spring Integration versions.

### 5.1. Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

`spring-integration-mail` supplies mail adapters/receivers; `spring-boot-starter-jdbc` is only needed when the example persists state/DLQ in a database. If your application already uses Spring Data JPA, you do not need a separate JDBC starter. Let the Spring Boot BOM manage dependency versions where supported.

### 5.2. Defining the Channel and Error Flow

~~~java
package com.example.mail.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
public class MailErrorIntegrationConfiguration {

    @Bean("mailErrorChannel")
    public MessageChannel mailErrorChannel() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mailErrorFlow(
            MailFailureRouter failureRouter) {

        return IntegrationFlow.from("mailErrorChannel")
                .handle(message -> {
                    if (message instanceof ErrorMessage error) {
                        failureRouter.accept(error);
                    } else {
                        failureRouter.recordUnexpectedPayload(
                                message.getClass().getName());
                    }
                })
                .get();
    }
}
~~~

`MailFailureRouter` is an **application-built service**, not a Spring Integration class. In production, validate types and record minimal diagnostics when receiving unexpected messages rather than throwing endlessly inside the error handler.

In this example, `DirectChannel` has **one subscriber receiving errors synchronously**, so it does not persist errors across restarts itself. `failureRouter.accept(...)` must classify and persist durable failure state or route to an appropriate store. If an error flow itself throws, the exception can propagate back to the poller/producer or trigger secondary failures; plan for secondary incident handling.

### 5.3. Wiring the Poller to the Error Channel

Suppose the application has declared a `MessageSource<?>` reading IMAP via the mail adapter:

~~~java
package com.example.mail.integration;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
public class InboundMailFlowConfiguration {

    @Bean
    public IntegrationFlow inboundMailFlow(
            MessageSource<?> imapMailSource,
            InboundMailHandler handler) {

        return IntegrationFlow.from(
                        imapMailSource,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                                Duration.ofSeconds(10))
                                        .maxMessagesPerPoll(10)
                                        .errorChannel("mailErrorChannel")))
                .handle(message -> handler.accept(message))
                .get();
    }
}
~~~

`InboundMailHandler` is the application's business handler. `imapMailSource` must be properly configured with IMAP server, credentials, TLS, and retention/read policies. The poller is only **one** place where errors originate; handlers may need dedicated error channels or transactional exception routing if the pipeline has additional async branches.

Setting `.errorChannel("mailErrorChannel")` on the poller means exceptions caught by the poller's error handler during polling can be sent to this channel. **Do not assume it automatically catches every exception from downstream threads outside the poller context.**

### 5.4. IMAP Source via MailReceivingMessageSource

Spring Integration Mail provides `ImapMailReceiver` and `MailReceivingMessageSource`. Source setup outline:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.mail.ImapMailReceiver;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Bean("imapMailSource")
MessageSource<?> imapMailSource(
        ImapMailReceiver receiver) {
    return new MailReceivingMessageSource(receiver);
}
~~~

`ImapMailReceiver` is constructed from validated IMAP config, e.g., URL or Jakarta Mail properties/Authenticator per your library version. Credentials/secrets must come from a **secret manager/runtime**, never committed in source code. TLS, timeouts, folder, and `shouldDeleteMessages`/`shouldMarkMessagesAsRead` must align with your application's retry strategy.

Special point for inbound mail: if the receiver marks a message `SEEN`, moves it, or deletes it before business outcomes commit, the error flow might record `RETRY` yet **no longer find the original email**. Persist durable identities/snapshots and separate IMAP flag/move actions from committing business state.

### 5.5. When an Endpoint Uses No Poller

A mail flow may use an event-driven receiving adapter or gateway with different settings. In those cases, error handling belongs on the endpoint/message headers/adapter itself—**there is no poller on which to set `errorChannel`**.

Clarify explicitly:

- Which thread invokes the business handler?
- Who catches exceptions?
- Are errors wrapped into `ErrorMessage`?
- Which error channel is selected?
- If there is no subscriber or the error handler fails, where does the exception go?
- Once the error handler finishes, does the source consider the message successfully received?

Answer all six questions in your design rather than adding a `mailErrorChannel` bean and assuming the whole system is protected.

## 6. Reading ErrorMessage Safely

An error handler can receive many exception shapes. Therefore, the first step is normalizing info without depending on a single rigid nested exception chain.

### 6.1. Accessing Payload and failedMessage

~~~java
package com.example.mail.integration;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public final class ErrorMessageInspector {

    public static Message<?> failedMessageOf(
            ErrorMessage error) {

        Throwable failure = error.getPayload();
        if (failure instanceof MessagingException messaging) {
            Message<?> failed = messaging.getFailedMessage();
            if (failed != null) {
                return failed;
            }
        }
        return error.getOriginalMessage();
    }

    public static Throwable rootCauseOf(
            ErrorMessage error) {

        Throwable cause = error.getPayload();
        int depth = 0;
        while (cause.getCause() != null
                && cause.getCause() != cause
                && depth++ < 20) {
            cause = cause.getCause();
        }
        return cause;
    }
}
~~~

`getOriginalMessage()` can return `null`. The root-cause loop bounds depth to guard against pathological exception chains; applications should **classify by error type and actual stage**, not solely by matching `getMessage()` strings.

### 6.2. Do Not Keep Raw Message Payloads in the DLQ by Default

With inbound MIME, `failedMessage.getPayload()` can be a `MimeMessage` holding:

- Sender-supplied email addresses and headers.
- HTML bodies containing sensitive data.
- Large attachments, malware, or confidential files.
- Streams/resources tied to an already-closed IMAP connection.

Never serialize raw `Message<?>`/`Throwable` into the database via Java serialization. Store instead:

~~~text
internalMessageId
sourceIdentity
attemptNumber
failureStage
safeErrorCode
payloadReference (if durable and authorized)
occurredAt
correlationId
~~~

Without a durable MIME copy, an in-JVM `ErrorMessage` cannot serve as **proof that the email was safely persisted for replay**.

### 6.3. When Errors Occur Before Any failedMessage Exists

For example, IMAP authentication fails during `Store.connect`:

~~~text
ErrorMessage.payload:
  AuthenticationFailedException

failedMessage = null
originalMessage = null
~~~

This is a **source/connection-level failure**, not a failure on one specific email. The system should:

- Increment connection error counters for that mailbox.
- Log internal provider/mailbox ID and safe error code.
- Alert owners about credentials/provider status.
- Retry **connecting** with backoff/circuit breaker.
- Never mint a fake dead-letter record for an "unknown email" when no email was fetched.

Conversely, only when a handler fails after fetching an email and assigning an internal message ID is there a basis to transition a specific delivery to `RETRY` or `FAILED`.

## 7. The errorChannel Header and Correlation Context

Spring Messaging provides the `errorChannel` header (constant `MessageHeaders.ERROR_CHANNEL`). Components supporting error routing can read this header to determine where to send errors.

Example building a message with an explicit error channel:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<MailWorkItem> request = MessageBuilder
        .withPayload(workItem)
        .setHeader(
                MessageHeaders.ERROR_CHANNEL,
                mailErrorChannel)
        .setHeader(
                "mailInternalId",
                workItem.inboundId().toString())
        .build();
~~~

The header can be a `MessageChannel` or channel name depending on participant contracts. Merely setting the header on a message **does not guarantee every plain Java method call underneath automatically routes exceptions**; error publication must be supported or implemented explicitly.

### 7.1. Preserving Context Across Asynchrony

When emails cross executors, channels, brokers, or task schedulers, never rely entirely on `ThreadLocal`/MDC from the IMAP-reading thread. Carry minimal context explicitly via:

~~~text
inboundId / outboundDeliveryId
mailboxId / providerId
tenantId (with access controls)
attemptId
correlationId
workflowType
sourceIdentity
~~~

These fields tie an `ErrorMessage` back to its state record. Never put passwords, raw MIME bodies, recipient emails, or attachment bytes into headers just for debugging convenience.

### 7.2. Correlation ID Is Not a Default Idempotency Key

A trace/correlation ID helps search logs, yet is not necessarily stable across all retries. An idempotency key must identify **the same business operation**, for example:

~~~text
inboundId = D1
operation = CREATE_SUPPORT_TICKET
idempotencyKey = "ticket-from-inbound:D1"
~~~

Never mint a fresh idempotency key per attempt if the goal is preventing duplicate tickets. Likewise, never use sender-supplied RFC `Message-ID` as an authorization key or sole idempotency key, as it can be spoofed or duplicated.

## 8. Classifying Errors Before Deciding Retry vs. Dead Letter

An `ErrorMessage` only tells you **an error occurred**. Whether to retry or dead-letter must depend on **error kind, stage, and side-effect state**, not solely on the outer exception class.

| Group | Scenario | Typical Appropriate Action |
| --- | --- | --- |
| Source infrastructure | IMAP server unavailable, network timeout before receiving mail | Retry connection with backoff, alert on mailbox |
| Source authentication | IMAP OAuth token expired or invalid credentials | Pause rapid retries, fix secret/auth |
| Transient processing | DB deadlock, downstream temporarily unavailable | Controlled message retry |
| Permanent validation | Email missing required data, invalid business format | `FAILED`/quarantine, keep reason |
| Malicious content | Dangerous attachment, MIME abuse, virus | `QUARANTINED` per security policy |
| Data/snapshot missing | IMAP email deleted/moved, `UIDVALIDITY` changed | Reconcile or `SOURCE_UNAVAILABLE`; never fetch wrong UID |
| Unknown external outcome | Timeout after remote ticket API may have created record | `UNKNOWN`/reconcile or retry with idempotency key |
| SMTP temporary failure | Relay temporarily unavailable or throttling | Retry outbound with backoff if outcome is clear |
| SMTP permanent failure | Recipient definitively rejected, message exceeds `SIZE` | `FAILED`, never infinite retries |
| Error flow infrastructure | Failed to persist retry/DLQ row, broker publish failure | Alert on secondary error; avoid ACKing source before saving state |

### 8.1. Separating Failure Kind and Failure Stage

~~~java
public enum FailureKind {
    TRANSIENT,
    PERMANENT,
    SECURITY,
    UNKNOWN
}

public enum FailureStage {
    IMAP_CONNECT,
    IMAP_FETCH,
    MIME_PARSE,
    ATTACHMENT_SCAN,
    BUSINESS_VALIDATE,
    BUSINESS_DATABASE,
    EXTERNAL_SIDE_EFFECT,
    SMTP_SEND,
    STATE_PERSIST,
    ERROR_FLOW
}

public record FailureDecision(
        FailureKind kind,
        FailureStage stage,
        String safeErrorCode,
        boolean retryAllowed) {
}
~~~

These enums/records are **application-defined models**, not Spring Integration built-ins. In Java, place each top-level `public` type in its own matching file.

`retryAllowed` is not a boolean supplied by an external caller. It is the policy output after evaluating error kind, attempt count, deadline, suppression, source readability, and side-effect state.

### 8.2. Illustrative Classifier

~~~java
package com.example.mail.integration;

import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailSendException;

public final class MailFailureClassifier {

    public FailureDecision classify(
            Throwable rootCause,
            FailureStage stage) {

        if (stage == FailureStage.MIME_PARSE
                || stage == FailureStage.BUSINESS_VALIDATE) {
            return new FailureDecision(
                    FailureKind.PERMANENT,
                    stage,
                    "INVALID_INBOUND_CONTENT",
                    false);
        }

        if (rootCause instanceof MailAuthenticationException) {
            return new FailureDecision(
                    FailureKind.PERMANENT,
                    stage,
                    "SMTP_AUTH_CONFIGURATION",
                    false);
        }

        if (rootCause instanceof MailSendException) {
            return new FailureDecision(
                    FailureKind.UNKNOWN,
                    stage,
                    "SMTP_SEND_UNCLASSIFIED",
                    false);
        }

        return new FailureDecision(
                FailureKind.UNKNOWN,
                stage,
                "UNCLASSIFIED",
                false);
    }
}
~~~

This is only a **default fail-closed classifier**, not a complete production retry policy. In practice, `MailSendException` often carries nested exceptions and per-recipient details; inspect the SMTP cause, status code, and **whether execution passed the DATA stage**. Never treat every `MailSendException` as transient to retry immediately.

Similarly, a `MessagingException` can wrap an `IOException`, conversion error, database error, or custom exception. The outer wrapper class name **is insufficient** to decide behavior.

### 8.3. Not Every Error Is Tied to a Message

The model distinguishes two incident types:

~~~text
SOURCE FAILURE
  mailboxId=MB1
  stage=IMAP_CONNECT
  no inboundMessageId
  action=BACKOFF_SOURCE

MESSAGE FAILURE
  inboundMessageId=D1
  stage=MIME_PARSE
  errorCode=INVALID_MULTIPART
  action=QUARANTINE
~~~

Do not generate thousands of dead-letter rows from one bad mailbox credential. Source-level errors belong on **mailbox/connect attempts**, whereas message-level failures attach to `inboundMessageId` and processing state.

## 9. Dead-Letter Flow: From ErrorMessage to Durable Record

A dead-letter flow requires **a durable record or acknowledged broker message**, not merely sending exceptions to a logging consumer.

~~~text
mailErrorChannel
      |
      v
Failure router
      |
      +-- No source message ID?
      |      |
      |      v
      |  Source incident / reconnect policy
      |
      +-- Has durable message ID
             |
             v
       Lookup current processing state
             |
             v
      Classify failure + attempt
             |
       +-----+-----------+--------------+
       |                 |              |
       v                 v              v
     RETRY             FAILED        QUARANTINED
       |                 |              |
       v                 v              v
   next_attempt_at    Dead-letter     Security queue
                     record/store     / restricted access
       |                 |              |
       +-----------------+--------------+
                         |
                         v
                  Audit + monitoring
~~~

### 9.1. Illustrative Dead-Letter Schema

With PostgreSQL, you can use an inbound status table plus a dead-letter event table:

~~~sql
CREATE TABLE inbound_mail_work (
    id UUID PRIMARY KEY,
    mailbox_id UUID NOT NULL,
    source_key VARCHAR(450) NOT NULL,
    payload_ref VARCHAR(500),
    workflow_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    terminal_reason VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(mailbox_id, source_key, workflow_type)
);

CREATE INDEX ix_mail_work_due
    ON inbound_mail_work(status, next_attempt_at);

CREATE TABLE inbound_dead_letter (
    id UUID PRIMARY KEY,
    inbound_work_id UUID NOT NULL
        REFERENCES inbound_mail_work(id),
    attempt_no INT NOT NULL,
    failure_kind VARCHAR(30) NOT NULL,
    failure_stage VARCHAR(50) NOT NULL,
    error_code VARCHAR(100) NOT NULL,
    terminal_reason VARCHAR(100) NOT NULL,
    payload_ref VARCHAR(500),
    dead_lettered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution VARCHAR(100),
    UNIQUE(inbound_work_id, attempt_no)
);
~~~

`source_key` in this example is a canonicalized, mailbox-scoped string; for IMAP, store folder, `UIDVALIDITY`, and `UID` **separately** with matching data types and unique constraints. Never use RFC `Message-ID` directly as an absolute source key. This schema highlights the **durable state + DLQ event** boundary, not a full production migration.

### 9.2. Writing FAILED and the Dead-Letter Record in One Transaction

~~~sql
-- Inside transaction after verifying claim ownership.
UPDATE inbound_mail_work
SET status = 'FAILED',
    last_error_code = :error_code,
    terminal_reason = :terminal_reason,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :work_id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token;

-- INSERT only if UPDATE actually modified exactly one row.
INSERT INTO inbound_dead_letter(
    id, inbound_work_id, attempt_no, failure_kind,
    failure_stage, error_code, terminal_reason, payload_ref
)
VALUES (
    :dlq_id, :work_id, :attempt_no, :failure_kind,
    :failure_stage, :error_code, :terminal_reason, :payload_ref
);
~~~

**Never execute two separate statements with auto-commit** if business rules demand consistency: the row could become `FAILED` without a DLQ record. The service should start a transaction, assert update count equals 1, insert the event, and commit atomically.

If the error flow receives the same failure again, the unique key on `(inbound_work_id, attempt_no)` prevents emitting duplicate terminal events for one attempt. If multiple terminal states/events are supported for the same attempt, use a more suitable event ID/transition ID model.

### 9.3. When the Dead Letter Lives on a Broker

A RabbitMQ architecture:

~~~text
inbound.work.queue
      |
      v
Consumer
      |
      +-- success -> ack after durable business result
      |
      +-- transient -> retry policy / delayed queue
      |
      +-- permanent -> reject/nack without requeue
                           |
                           v
                     Dead-letter exchange
                           |
                           v
                     inbound.mail.dlq
~~~

The broker must have proper DLX/queue bindings, durability, and acknowledge/publish policies. **Sending to a `MessageChannel` named `mailDeadLetterChannel` does not configure a RabbitMQ DLX automatically.**

With Kafka, a dead letter is usually a **separate topic** published by error handling/retry policies after processing fails; manage publish confirmations, consumer offsets, headers, ACLs, and retention. These mechanics belong to the broker adapter layer and are not automatic features of `spring-integration-mail`.

### 9.4. What Should Be Kept When Moving an ErrorMessage to the DLQ?

A minimal dead-letter payload:

~~~json
{
  "deadLetterId": "dlq-opaque-id",
  "inboundWorkId": "work-opaque-id",
  "sourceType": "IMAP",
  "mailboxId": "mailbox-opaque-id",
  "workflowType": "CREATE_SUPPORT_TICKET",
  "attempt": 5,
  "failureStage": "MIME_PARSE",
  "failureKind": "PERMANENT",
  "safeErrorCode": "INVALID_MULTIPART",
  "terminalReason": "NON_RETRYABLE_FAILURE",
  "payloadReference": "restricted-storage-reference"
}
~~~

Never place credentials, attachment bytes, raw HTML, full MIME headers, or stack traces that may expose user data into the DLQ by default. If replay is needed, `payloadReference` must point to genuinely durable, authorized, and still-retained data.

### 9.5. Quarantine Differs from Operational Dead Letters

For suspicious emails:

- `FAILED`: handler failed to process; can be investigated and fixed.
- `QUARANTINED`: content restricted by security policy; regular operators cannot retry or download attachments.

Quarantine needs dedicated access controls, retention, malware scanning, and release procedures. Never build a single "Retry all" button spanning both malware emails and DB-timeout emails.

## 10. Retrying Before Moving to the DLQ

Not every error should go straight to the dead-letter queue. For temporarily unavailable databases or flaky IMAP servers, bounded retries make sense.

An illustrative retry policy:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

If `d_0 = 30 seconds`, `d_max = 15 minutes`, `max_attempts = 5`:

| Attempt That Just Failed | Base Delay for Next Try | State |
| --- | --- | --- |
| 1 | 30 seconds | `RETRY` |
| 2 | 60 seconds | `RETRY` |
| 3 | 120 seconds | `RETRY` |
| 4 | 240 seconds | `RETRY` |
| 5 | No more automatic attempts | `FAILED`/`DLQ` |

Jitter can spread retry timestamps so workers do not hit IMAP/SMTP/database in a single burst. No single retry schedule fits every use case; consider SLAs, source content retention, and side-effect types.

### 10.1. Retrying at Which Layer?

There are multiple distinct layers:

~~~text
IMAP reconnect attempt
      |
      v
Inbound message fetch attempt
      |
      v
Message processing attempt
      |
      v
External API side-effect attempt
~~~

A reconnect attempt does not equal reprocessing an email. Never increment `inbound_message.attempt_count` before fetching/claiming an inbound work item; use separate counters/metrics for mailbox connection failures.

### 10.2. Retry Advice vs. Durable Retry Queue?

Spring Integration provides advice/interceptors to retry a handler on failure; `RequestHandlerRetryAdvice` is commonly attached around endpoint handlers with version-appropriate policy, backoff, and recovery settings.

**In-process retries** suit brief transient errors, with clear limits:

- Worker threads stay occupied across attempts.
- Retry state is lost on JVM restarts.
- If the handler caused partial side effects, retries can create duplicates.
- Does not persist durable DLQ records automatically.

For emails that must survive crashes or worker restarts, maintain **durable retry state** in a database/broker with independent attempts. You can combine *very few* in-process retries for safe errors with durable retries for longer outages, provided "attempt" is clearly defined so `max_attempts` is never exceeded.

### 10.3. Never Let Retry Advice Hide Business Errors

If a handler catches all exceptions and returns success:

~~~java
try {
    ticketService.createTicket(mail);
} catch (Exception ex) {
    log.warn("Cannot process inbound mail", ex);
    // returning normally
}
~~~

Spring Integration may treat the endpoint as having succeeded; retry advice and the error channel will never see the failure. Instead:

- Catch only errors the handler can completely resolve.
- When retries are needed, throw a properly categorized exception or persist `RETRY` state explicitly.
- Once `FAILED`/DLQ is explicitly recorded, avoid letting the same exception emit a second un-deduplicated DLQ event.

### 10.4. Never Let DLQ Failures Lose the Original Error

Suppose the business handler fails, and then the DLQ persistence service also fails:

~~~text
Original error: INVALID_MULTIPART
                  |
                  v
Dead-letter database unavailable
                  |
                  v
Secondary error: DEAD_LETTER_PERSIST_FAILED
~~~

If the source message was acked/moved/deleted before durable error persistence, it can be lost. Policy must enforce:

- Never ack the source before achieving durable receipt per contract.
- Retain or recover the work record to retry DLQ persistence.
- Emit metrics/alerts for **error flow failures**.
- Maintain a minimal fallback store for investigation if the primary store cannot write.
- Preserve both the original and secondary error details rather than logging only the final exception.

## 11. Inbound IMAP: Never Let Error Channels Lose Emails

When receiving mail over IMAP, a critical issue is that **mailbox flags and business processing state do not share a transaction**.

Unsafe flow example:

~~~text
IMAP adapter reads message
         |
         v
Mail marked SEEN / moved
         |
         v
Ticket handler throws
         |
         v
ErrorMessage logged
         |
         v
Next poll reads UNSEEN only
         |
         v
Mail never processed again
~~~

A log event or `ErrorMessage` alone does not ensure reprocessing. Persist the **received message identity** and business status in a durable store.

### 11.1. Proper Source IDs for IMAP

Common IDs:

| ID | Meaning |
| --- | --- |
| RFC `Message-ID` | Sender-supplied header; may be missing, duplicated, or forged |
| IMAP UID | Server-assigned, scoped to one folder |
| IMAP `UIDVALIDITY` | Folder UID epoch |
| IMAP message sequence number | Ephemeral position, shifts on expunge |
| Internal inbound ID | Application-assigned UUID |

A sound source identity key:

~~~text
(mailbox_id, folder_key, uid_validity, imap_uid)
~~~

Never use RFC `Message-ID` or `getMessageNumber()` as a global unique key for inbound mail. Two emails can share an RFC `Message-ID`; a numeric UID can be reused after `UIDVALIDITY` changes.

### 11.2. Mail Receipt State Schema

~~~sql
CREATE TABLE inbound_mail_message (
    id UUID PRIMARY KEY,
    mailbox_id UUID NOT NULL,
    folder_key VARCHAR(250) NOT NULL,
    uid_validity BIGINT NOT NULL,
    imap_uid BIGINT NOT NULL,
    rfc_message_id VARCHAR(512),
    payload_ref VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'DISCOVERED',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(mailbox_id, folder_key, uid_validity, imap_uid)
);
~~~

This is a **separate illustrative schema** for inbound identity. In real implementations, merge it with `inbound_mail_work` above instead of creating two tables modeling the same workflow. The goal is explicit source identity and processing state independent of IMAP flags.

### 11.3. Inbound Email Lifecycle

~~~text
IMAP UID discovered
        |
        v
Insert inbound row (idempotent)
        |
        v
Optional snapshot MIME to durable storage
        |
        v
Worker atomic claim (PROCESSING)
        |
        v
Business handler
        |
      /   \
     v     v
  Success  ErrorMessage
     |     |
     v     +--> RETRY / FAILED / QUARANTINED
  Commit
  PROCESSED
     |
     v
  Optional IMAP mark/move
~~~

If the application keeps only the UID without snapshotting MIME, a user may delete or move the email before retry. The error handler needs a `SOURCE_UNAVAILABLE`/reconciliation state instead of blindly trying to fetch that UID in a different folder or `UIDVALIDITY`.

### 11.4. Discovery Checkpoints Must Be Independent of Processing

Suppose:

~~~text
UID 1001 -> PROCESSED
UID 1002 -> RETRY
UID 1003 -> PROCESSED
UID 1004 -> DISCOVERED
last_discovered_uid = 1004
~~~

The cursor indicates the poller discovered and persisted IDs up to UID 1004—**it does not claim UID 1002 was processed**. Maintain per-UID work records/statuses. If a batch insert fails, never advance the cursor before all source identities in the batch are durably persisted.

### 11.5. UIDVALIDITY Changes

If the server returns a `UIDVALIDITY` differing from the stored value, stop using the old cursor, initialize a new generation, and reconcile reappearing emails. Never resume from the old generation's `last_discovered_uid` or equate numeric UIDs across two generations.

A `FAILED`/`RETRY` record from an older generation can only be retried if a valid snapshot remains or a verified matching source exists. Never fetch the same numeric UID in the new generation and treat it as the old email.

### 11.6. What Does the Poller Do Once the Error Flow Receives an Error?

If the error handler catches the exception, persists `RETRY` durably, and returns normally, the poller can proceed with future scans. That **does not mean the email retries automatically**: a worker must pick up due `RETRY` records.

If the error handler only logs and returns, the failure can vanish from the flow's perspective. Keep the contract crystal clear:

~~~text
ErrorMessage handled successfully
    == failure disposition has been recorded durably
    != business operation has succeeded
~~~

Never mark `PROCESSED` or move the email simply because the error flow finished handling the exception.

## 12. Outbound SMTP: Error Flows Differ from Inbound Retries

An email-sending flow can traverse:

~~~text
Business transaction
      |
      v
Mail outbox PENDING
      |
      v
IntegrationFlow / mail worker
      |
      v
Render MIME + JavaMailSender.send
      |
      +--> success: SMTP_ACCEPTED
      |
      +--> error: ErrorMessage / retry state / failed state
~~~

If a Spring Integration mail **outbound adapter** or service handler using `JavaMailSender` throws an exception, error routing depends on configured channels, endpoints, and error handlers. `JavaMailSender` itself does not publish an `ErrorMessage` just because the app has an `errorChannel` bean.

### 12.1. Send Outcomes to Distinguish

| Outcome | What Is Known | Action |
| --- | --- | --- |
| MIME preparation failure | Email not yet submitted to SMTP | Fix data/template; may mark `FAILED` |
| Connection failure before submission | SMTP did not receive content if evidenced | Retry with backoff |
| SMTP temporary rejection | Relay temporarily refused at known stage | Retry per code, quota, deadline |
| SMTP permanent rejection | Message/recipient definitively rejected | `FAILED` or suppress per policy |
| `send(...)` succeeds | Relay accepted email per app observation | Record `SMTP_ACCEPTED`/`SENT` |
| Timeout after DATA | Relay may have accepted despite missing response | `UNKNOWN`/reconciliation |
| DB `markSent` fails after SMTP accepted | SMTP may have accepted yet outbox unchanged | Never retry blindly; record duplicate risk |

**SMTP accepted does not equal inbox delivery.** The provider can emit a bounce/DSN later. Provider-side retries after acceptance also differ from application retries; never submit a fresh email merely upon receiving `DEFERRED` feedback.

### 12.2. How a Failure Can Cause Duplicate Sends

~~~text
Worker sends message
      |
      v
SMTP server accepts DATA
      |
      v
JavaMailSender.send returns successfully
      |
      v
Database markSENT fails
      |
      v
Outbox remains PROCESSING
      |
      v
Lease expires, new worker retries
      |
      v
Second email can be sent
~~~

Even a transactional outbox does not create an atomic transaction across a database and an SMTP relay. Integration error flows need states/metrics for `UNKNOWN` or state-write failures, along with reconciliation/duplicate-tolerance policies.

### 12.3. Never Retry Based Solely on MailSendException

`org.springframework.mail.MailSendException` can wrap diverse JavaMail/Jakarta Mail errors, including transport and recipient details. Never write:

~~~java
catch (MailSendException ex) {
    // Wrong: always resend immediately.
    mailSender.send(message);
}
~~~

An exception alone does not tell whether the provider already accepted. In the error flow, persist:

~~~text
attemptId
outboundDeliveryId
failureStage
smtpCommandStage (if known)
safeSmtpCode
result = DEFINITE_FAILURE | UNKNOWN
~~~

Do not guess "not sent" from a timeout alone, especially when the failure happens after transmitting SMTP `DATA`.

### 12.4. Using Spring Integration with Outbound Work Items

Illustrative strategy:

~~~java
@Bean
public IntegrationFlow outboundMailFlow(
        OutboundMailSenderHandler senderHandler) {

    return IntegrationFlow.from("mailOutboundWorkChannel")
            .handle(message -> senderHandler.submit(message))
            .get();
}
~~~

`OutboundMailSenderHandler` is an application component managing routing, sending via `JavaMailSender`, and updating status. In a synchronous channel flow, handler exceptions can propagate back to the caller. If you want a message-based error flow, configure/open an explicit catch/publish boundary; creating an `outboundMailErrorChannel` alone will not make synchronous exceptions land there automatically.

## 13. Bridging Service Errors to ErrorMessage When Needed

Sometimes a business handler is not invoked by an endpoint with automatic error publication, yet the application still wants to route failures into a centralized error flow.

Example of a service processing `Message<MailWorkItem>`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

public final class MailWorkExecutor {

    private final MessageChannel mailErrorChannel;
    private final MailBusinessProcessor processor;

    public MailWorkExecutor(
            MessageChannel mailErrorChannel,
            MailBusinessProcessor processor) {
        this.mailErrorChannel = mailErrorChannel;
        this.processor = processor;
    }

    public void execute(Message<MailWorkItem> message) {
        try {
            processor.process(message.getPayload());
        } catch (Exception ex) {
            MessagingException failure =
                    new MessagingException(message, ex);
            boolean published = mailErrorChannel.send(
                    new ErrorMessage(failure));

            if (!published) {
                throw failure;
            }
        }
    }
}
~~~

`MailWorkItem` and `MailBusinessProcessor` are illustrative abstractions. When an error channel acts as a **path to record durable failure dispositions**, also handle `send(...)` throwing an exception instead of returning `false`, and verify the handler truly commits `RETRY`/`FAILED` state. `send` returning `true` **does not prove** a DLQ persisted anything if the consumer only logs.

**Never publish the same error twice.** If the same exception is also rethrown to a poller error handler while the service publishes an `ErrorMessage`, one attempt can generate two retry/dead-letter records. Establish single error ownership and deduplicate via unique transition/attempt IDs.

### 13.1. Separating Business Exceptions from Error-Flow Exceptions

~~~text
Business handler throws E1
       |
       v
Error publishing succeeds?
       |
   +---+---+
   |       |
  Yes      No
   |       |
   v       v
Durable disposition?   E2 = Error flow failure
   |       |
   v       v
Ack according          Keep source unacked / retry
to source contract     or invoke fallback incident path
~~~

If `failureRouter.accept(...)` writes to the DB and commits, the error can be treated as dispositioned. If it only increments a counter or logs, never ack and delete the source email merely because error handling "did not throw".

### 13.2. Secondary Errors Can Hide Source Context

An `ErrorMessage` throwing again while serializing its payload to the DLQ can mask the root cause. Preserve `safeErrorCode` and `attemptId` from the initial failure; `DLQ_PUBLISH_FAILED` is **a separate incident**. Log and alert on both without creating an infinite publish chain on the same error channel.

## 14. Choosing the Right Channel for Error Flows

Not every channel named "error" behaves the same. Channel type affects synchronicity, ordering, backpressure, secondary failures, and persistence.

| Channel | Mechanism | When to Use | Caveats |
| --- | --- | --- | --- |
| `DirectChannel` | Handler invoked synchronously on sender thread | Short error handler; state/audit write must finish before caller proceeds | DB errors can propagate back to publisher |
| `ExecutorChannel` | Dispatches to an executor | Want to decouple error work from poller thread | Needs bounded queue; crashes can lose in-memory work |
| `PublishSubscribeChannel` | Multiple subscribers can receive events | Fan-out logging, monitoring, state recording | One failing/async subscriber complicates semantics; does not replace durable commit |
| `QueueChannel` | Sender enqueues, separate poller consumes | Load smoothing/sequencing next step | Non-durable by default; configure capacity/message store |
| Broker-backed channel | Messages traverse external broker | Durable retry/DLQ if fully configured | Requires acks, publisher confirms, and retention |

### 14.1. Why DirectChannel Is Often Easy to Start With

For an inbound handler, you may require:

~~~text
Error published to mailErrorChannel
           |
           v
Failure handler commits RETRY/FAILED state
           |
           v
Error handler returns
           |
           v
Poller can proceed
~~~

This is easier to reason about than fire-and-forget error processing. Its downside: during a database outage, the error handler can block or throw, slowing or halting poller cycles. Set timeouts and explicit policies instead of blocking threads indefinitely.

### 14.2. Separating Observation from Durable Disposition

A clean pattern:

~~~text
             ErrorMessage
                  |
                  v
           Durable disposition
              RETRY/FAILED
                  |
               COMMIT
                  |
                  v
           Publish safe event
              |
        +-----+-----+
        |           |
        v           v
      Metrics      Logging/alert
~~~

Treat **state persistence as the success criterion**, while metrics/logs emit after commit. If the metrics service is temporarily down, never trigger a business retry or send an email twice just because a metric failed to record.

### 14.3. Avoiding "Error of Error" Loops

If an `ErrorMessage` goes to a channel whose handler throws and republishes back to the same error channel, you hit a loop:

~~~text
mailErrorChannel -> error handler fails
     ^                    |
     |                    |
     +---- republish -----+
~~~

A strategy:

- Bound DLQ writes in the error handler with timeouts.
- If persistence fails, log a **sanitized secondary incident** and let the error follow caller/source error semantics.
- Alert on `ERROR_FLOW_PERSIST_FAILURE`.
- Never republish the same error message back onto the same channel indefinitely.
- Deduplicate by `attemptId + errorDispositionType` if publications can repeat.

## 15. Redriving from the Dead Letter Back to Processing

A dead-letter store is not only a graveyard for failed messages. Once a bug is fixed, operators may want to **redrive** (return work to the processing queue).

However, not every email is still eligible:

- Inbound emails with malicious files must never be casually released from quarantine.
- A ticket may already exist while DB status failed to commit; blind redrive can create a duplicate ticket.
- Password reset emails may have expired; resending stale emails causes confusion.
- An inbound source message may have been deleted with no MIME snapshot left to replay.
- An outbound email may already be SMTP-accepted while in `UNKNOWN`; resending risks duplicates.

### 15.1. Redrive Workflow

~~~text
Operator requests redrive
            |
            v
Authenticate + authorize
            |
            v
Inspect DLQ reason + attempt history
            |
            v
Check payload still exists / integrity
            |
            v
Check tenant, deadline, suppression, security policy
            |
            v
Check prior side effect / SMTP outcome
            |
            v
Reserve capacity and create audit record
            |
            v
Requeue existing work or create linked attempt
            |
            v
Observe new outcome
~~~

### 15.2. Two Redrive Models

**Continuing the same work item:**

~~~text
workId = W1
attempts = 1, 2, 3
status = FAILED

Operator approves retry cycle 2
workId = W1
attempts = 4, 5...
~~~

Advantage: keeps full history on one record. Clarify whether `max_attempts` is per cycle or total across attempts, and never silently reset attempt counts.

**Creating a new linked work item:**

~~~text
oldWorkId = W1 (FAILED)
newWorkId = W2 (DISCOVERED/PENDING)
redriveOf = W1
redriveReason = "downstream ticket service restored"
~~~

Advantage: keeps W1 immutable for audit. Trade-off: enforce business idempotency across W1/W2 so one email cannot trigger duplicate side effects when disallowed.

### 15.3. Illustrative Single-Row Redrive SQL

~~~sql
UPDATE inbound_mail_work
SET status = 'RETRY',
    next_attempt_at = now(),
    claim_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :work_id
  AND status = 'FAILED';
~~~

**Never expose this SQL directly as a public redrive API.** The service must perform authentication/authorization, verify source/snapshots, check duplicate side effects and retry-cycle policies, write an audit record in the same transaction, and check the update count. A bulk "reset every `FAILED` to `RETRY`" action can repeat failures and overload the system.

### 15.4. Redrive with a Broker DLQ

With RabbitMQ/Kafka:

1. Read the DLQ item along with source metadata.
2. Resolve the internal work/delivery ID and business state.
3. Validate the redrive policy.
4. Republish using a broker mechanism with durable confirms.
5. Ack/commit the source offset per contract only after publish/redrive is confirmed.
6. Write an audit record and monitor the new attempt.

During a crash window, succeeding at republishing before ACKing the DLQ can repeat the redrive. Thus consumers must remain **idempotent**, never assuming "move DLQ -> work" is atomic on every broker.

### 15.5. Auditing Redrive Operations

~~~sql
CREATE TABLE inbound_redrive_audit (
    id UUID PRIMARY KEY,
    work_id UUID NOT NULL,
    actor_id VARCHAR(120) NOT NULL,
    reason VARCHAR(300) NOT NULL,
    action VARCHAR(40) NOT NULL,
    previous_status VARCHAR(30) NOT NULL,
    new_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Never store tokens, passwords, email bodies, or raw stack traces in `reason`. Store a ticket/incident ID and reason category rather than pasting email content.

## 16. Integrating Spring Retry/Advice with errorChannel

Spring Integration can apply an **advice chain** to message handlers for retries or recovery. Understand **where retry sits in the flow** and whether exceptions still reach the error channel or are consumed by a recoverer.

~~~text
Inbound message
     |
     v
Handler with retry advice
     |
     +--> attempt 1 fails
     +--> attempt 2 fails
     +--> attempt 3 fails
     |
     v
Recovery callback (if configured)
     |
     +--> publish ErrorMessage?
     +--> record RETRY/FAILED?
     +--> throw?
~~~

### 16.1. ErrorMessageSendingRecoverer

Spring Integration provides `ErrorMessageSendingRecoverer`, which can act as a recovery callback in certain retry-advice setups. Its role is converting a failure into an error message sent to a designated channel.

**Be especially careful with attempt counts:** if retry advice invokes a handler three times in one poll cycle and emits only one final `ErrorMessage`, the database `attempt_count` may count "one worker claim", not three **handler attempts**. Define clearly what counts as an attempt and bound total retries across all layers.

### 16.2. Do Not Use Retry Advice for Every Side Effect

A handler that creates a ticket and fails while updating status may have already created the ticket on the first attempt. Retry advice immediately re-invoking the handler in the same process can create a second ticket.

Use direct local retries only when:

- The operation is idempotent; **or**
- The failure is guaranteed to occur before side effects; **and**
- Retry counts/timeouts are explicit; **and**
- It will not breach SLAs or block worker threads too long.

Without those guarantees, persisting durable `UNKNOWN`/`RETRY` state and letting a worker process with idempotency keys/reconciliation is far easier to control.

### 16.3. Recovery Does Not Mean Processing Succeeded

A recoverer forwarding an exception to an error channel and returning normally can make the upstream endpoint treat the failure as consumed. Therefore, the error handler must persist a durable disposition. Never log "retry exhausted" and let the framework proceed as if the business workflow succeeded.

### 16.4. Never Mix Source Retries with Message Retries

For example, an IMAP connection fails during a poll:

~~~text
IMAP connection failure
  -> retry IMAP connection with bounded backoff
  -> no inboundMessageId yet
~~~

Whereas an already-received message fails during import:

~~~text
inboundMessageId=D1
  -> processing attempt fails
  -> record retry_count / next_attempt_at
~~~

Both retry types need distinct metrics, SLOs, and dead-letter policies. Never fabricate a phantom D1 record just to store a connection failure.

## 17. Observing Error Channels and DLQ with Micrometer/Actuator

An error flow cannot be operated well with stack traces alone. You need **error counts, error types, backlog age, and DLQ status**.

### 17.1. Metrics to Distinguish

| Logical Metric | Type | Question |
| --- | --- | --- |
| `mail_error_messages_total` | Counter | How many `ErrorMessage` instances reached the router? |
| `mail_error_disposition_total` | Counter | How many errors were dispositioned `RETRY`/`FAILED`/`QUARANTINED`/`UNKNOWN`? |
| `mail_error_flow_failures_total` | Counter | Did the error-recording flow itself fail? |
| `mail_mailbox_connect_failures_total` | Counter | Which mailbox groups hit connect/auth failures? |
| `mail_inbound_processing_attempts_total` | Counter | How many handler executions ran? |
| `mail_inbound_completed_total` | Counter | How many work items completed? |
| `mail_inbound_retry_due` | Gauge | How many messages are due for retry? |
| `mail_inbound_processing_inflight` | Gauge | How many messages are currently claimed? |
| `mail_dead_letter_current` | Gauge | How many messages await triage? |
| `mail_dead_letter_arrivals_total` | Counter | How many new messages entered the DLQ? |
| `mail_dead_letter_oldest_age_seconds` | Gauge | How old is the oldest unresolved dead letter? |
| `mail_redrive_attempts_total` | Counter | How many operator-approved redrives ran? |
| `mail_inbound_oldest_due_age_seconds` | Gauge | How old is the oldest due unprocessed work item? |
| `mail_source_last_successful_poll_age_seconds` | Gauge | How long since the last successful poll? |

Not every app needs every metric on day one. Still, **total `ErrorMessage` count** alone cannot tell whether emails are still progressing; combine **ready/failed/oldest age/throughput**.

### 17.2. Choosing Low-Cardinality Labels

Standardized label examples:

~~~text
workflow = inbound_ticket | inbound_bounce | outbound_transactional
source = imap | pop3 | webhook | smtp
stage = mime_parse | database | external_api | smtp_send
outcome = retry | failed | quarantined | unknown
error_code = imap_timeout | invalid_mime | db_unavailable | none
~~~

Never attach raw recipient emails, RFC `Message-ID`s, subjects, attachment filenames, stack traces, or internal UUIDs to metric series. In multi-tenant setups, use approved group/plan/region tags if label cardinality stays bounded and visibility is authorized.

### 17.3. Micrometer Counter Example

~~~java
package com.example.mail.ops;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public final class MailErrorMeters {

    private final MeterRegistry registry;

    public MailErrorMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    public void disposition(
            String workflow,
            String stage,
            String outcome,
            String errorCode) {

        Counter.builder("mail.error.disposition")
                .tag("workflow", workflow)
                .tag("stage", stage)
                .tag("outcome", outcome)
                .tag("error_code", errorCode)
                .register(registry)
                .increment();
    }
}
~~~

In production, validate labels against an enum/allowlist instead of passing raw `Throwable.getMessage()` or strings from inbound data. An attacker could generate thousands of distinct error codes/subjects if tags came straight from input.

**Note:** Counters are process-local observations; they reset on restarts and can lag behind DB commits. Databases/outboxes/DLQs are the durable audit source; Micrometer drives alerting and trend analysis rather than replacing state history.

### 17.4. Prometheus and Grafana

With Spring Boot Actuator and the Prometheus registry:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: when-authorized
~~~

The endpoint is typically `/actuator/prometheus` when dependencies and security config allow. Never expose management endpoints to the public Internet or without authorization. Exported Prometheus metric names follow registry conventions; verify real output before writing PromQL.

Illustrative PromQL if these series are exported:

~~~promql
# Dispositioned error rate by group over 5 minutes
sum by (workflow, outcome) (
  rate(mail_error_disposition_total[5m])
)

# Count of FAILED jobs still in DLQ, if gauge is a global snapshot
max(mail_dead_letter_current)

# Oldest due email currently waiting
max(mail_inbound_oldest_due_age_seconds)
~~~

**Watch out for global gauges:** if every replica queries the same DB to export `mail_dead_letter_current`, `sum` will double-count. Choose an authoritative collector or proper aggregation scope; never blindly sum across instances.

### 17.5. Actionable Alerts

| Alert | Signal | Action |
| --- | --- | --- |
| Mailbox polling stalled | Last successful poll age breaches SLO | Check IMAP credentials/network/TLS |
| Rapid DLQ growth | DLQ arrivals spike by error code | Inspect recent deploys, parser, and source data |
| Error flow itself failing | `error_flow_failures_total` rises | Inspect DB/broker used for DLQ writes |
| Processing backlog too old | Oldest due age grows while completion rate drops | Inspect workers, capacity, downstream |
| Retry storm | Scheduled/started retry rate spikes suddenly | Check backoff, jitter, provider outage |
| Quarantine spike | MIME/security errors rise | Investigate malicious email campaign or parser |
| SMTP `UNKNOWN` outcomes | Unclear if relay accepted | Reconcile before resending |
| High expired leases | Workers crashing or hanging | Inspect timeouts, heartbeats, and concurrency |

Alert thresholds must reflect real SLOs. One rejected invalid attachment is not an incident; hundreds of authentication failures in minutes can be severe.

### 17.6. Logging/Tracing by Work ID

A structured event:

~~~json
{
  "event": "mail.failure.disposition",
  "workId": "opaque-work-id",
  "attemptId": "opaque-attempt-id",
  "workflow": "INBOUND_TICKET",
  "source": "IMAP",
  "stage": "BUSINESS_DATABASE",
  "safeErrorCode": "DB_TIMEOUT",
  "decision": "RETRY",
  "nextAttemptAt": "2026-11-12T13:25:00Z"
}
~~~

Never log `MimeMessage.toString()`, full exception chains containing PII, raw headers, authentication details, or attachment bytes in error handling. To trace source identity, look up the internal work ID inside an authorized UI.

## 18. Testing ErrorMessage and Dead-Letter Flows

A test suite should cover both **error routing** and **durable state transitions**, not merely verify that a handler was invoked.

### 18.1. Unit Testing Error Classification

A test matrix:

| Input | Failure Stage | Expectation |
| --- | --- | --- |
| Missing required field | `BUSINESS_VALIDATE` | Permanent/`FAILED` |
| IMAP temporary timeout | `IMAP_CONNECT` | Source reconnect/backoff |
| DB temporarily unavailable | `BUSINESS_DATABASE` | Retry if message has an ID |
| Malware detected | `ATTACHMENT_SCAN` | `QUARANTINED` |
| External API timeout after request sent | `EXTERNAL_SIDE_EFFECT` | `UNKNOWN`/reconcile |
| SMTP accepted then DB commit fails | `STATE_PERSIST` | `UNKNOWN` risk, no blind resend |
| Invalid recipient | `SMTP_SEND` | Permanent failure per verified SMTP code |

Do not mock a `MailSendException` and conclude all SMTP 4xx/5xx cases are tested. Mocks test application policy, not which error codes real transports emit.

### 18.2. Testing That the Error Channel Receives ErrorMessage

An example using Spring `ErrorMessage`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class ErrorMessageContextTest {

    @Test
    void preservesFailedMessageContext() {
        Message<String> source = MessageBuilder
                .withPayload("test-work")
                .setHeader("workId", UUID.randomUUID().toString())
                .build();

        MessagingException failure = new MessagingException(
                source, new IllegalStateException("fake processing error"));
        ErrorMessage error = new ErrorMessage(failure);

        assertThat(error.getPayload())
                .isInstanceOf(MessagingException.class);
        assertThat(((MessagingException) error.getPayload())
                .getFailedMessage())
                .isSameAs(source);
    }
}
~~~

This test verifies how `failedMessage` is extracted when an error is explicitly constructed. It **does not prove** all IMAP/SMTP errors automatically attach `failedMessage` or traverse a channel; write integration tests for real sources/endpoints.

### 18.3. End-to-End Poller Error Channel Test

A scenario:

~~~text
Mock/fake MessageSource returns a mail work message
              |
              v
IntegrationFlow poller invokes business handler
              |
              v
Handler throws controlled exception
              |
              v
mailErrorChannel receives ErrorMessage
              |
              v
failureRouter persists RETRY/FAILED
              |
              v
Assert database state + attempt history
~~~

For polling endpoints, use bounded-timeout waits (e.g., Awaitility) instead of fixed `Thread.sleep`. Each test needs unique work IDs, database isolation, and must not clear shared message queues if tests run in parallel.

Also test **errors before any `Message<?>` exists**, e.g., a fake IMAP source throwing on connect. Expect a source-level incident, never fabricating a fake work item for the DLQ.

### 18.4. Testing DLQ Persistence Failure

This is a critical test:

1. The business handler throws.
2. `mailErrorChannel` receives the `ErrorMessage`.
3. The repository writing `FAILED`/DLQ is configured to throw.
4. The error flow **does not report fake durable success**.
5. Per the source contract, the message is not deleted/acked before a valid recovery path exists.
6. A `DLQ_PERSIST_FAILED` metric/alert is emitted.
7. Once the DB recovers, retries/reconciliation create no duplicate side effects.

If a test merely asserts a log contains "failed" and passes, it misses email-loss risks.

### 18.5. Testing Permanent Errors Do Not Retry Infinitely

An email with broken multipart is stored under `payload_ref`:

~~~text
Attempt 1: MIME_PARSE throws INVALID_MULTIPART
        |
        v
Failure classifier: PERMANENT
        |
        v
Status: FAILED / QUARANTINED
        |
        v
No automatic attempt 2, 3, 4...
~~~

Assert terminal reasons/attempt history and that no eligible work item gets re-polled. If operators want to redrive after fixing the parser, enforce an audited workflow.

### 18.6. Testing Retries with Bounded Attempts

With `max_attempts=3`:

~~~text
Claim #1 -> transient error -> RETRY after backoff
Claim #2 -> transient error -> RETRY after backoff
Claim #3 -> transient error -> FAILED/DLQ
~~~

Assert:

- `attempt_count=3`.
- No automatic claim #4.
- Dead-letter record is written exactly once.
- `last_error_code` preserves the actual error code.
- `terminal_reason=MAX_ATTEMPTS_EXHAUSTED` is stored separately.
- Retry schedule does not invoke the handler before `next_attempt_at`.

### 18.7. Testing the Crash Window and Idempotency

Suppose the handler creates a ticket:

~~~text
Create ticket T1
       |
       v
Process crashes before marking PROCESSED
       |
       v
Retry same inbound work ID
       |
       v
Must not create ticket T2
~~~

If the ticket and state reside in the same database, save them in the same transaction. If the ticket is in an external service, use a stable idempotency key and reconciliation. Tests must verify the **business outcome**, not just the `ErrorMessage` count.

### 18.8. Testing Real Inbound with an SMTP/IMAP Test Server

You can use **GreenMail** configured with IMAP support to:

1. Create a test mailbox and send a sample email to it.
2. Poll with Spring Integration Mail/Jakarta Mail.
3. Trigger a controlled processing failure.
4. Verify the error flow and database status.
5. Fix the error / reach the retry schedule, and verify only one business side effect occurs.
6. Run another poll and verify the source identity does not create a duplicate work item.

Mailpit or an SMTP sink with only SMTP/API message reception **does not necessarily provide an IMAP mailbox**. Testing IMAP sources must choose a tool that supports the right protocol.

### 18.9. Testing Outbound Separately with a Fake SMTP Server

For SMTP integration:

- Success: test relay receives the message; outbox `SENT`.
- Permanent rejection: `FAILED`, no blind retry.
- Temporary rejection: `RETRY` with backoff.
- Timeout after DATA: outcome `UNKNOWN` if there is no conclusive evidence.
- SMTP accepted + DB update fail: do not automatically resubmit immediately.

A fake SMTP server with programmable responses is more suitable than a default SMTP sink when detailed protocol error simulation is needed.

## 19. Runbook: Error Channel Receiving Continuous Errors

An error channel receiving many messages may reflect an issue at the source, handler, downstream, or a configuration change. You should not start by "increasing the retry count".

### 19.1. Step 1: Identify the Scope

Check:

- Do the errors come from `INBOUND_IMAP`, `INBOUND_WEBHOOK`, or `OUTBOUND_SMTP`?
- Is there an `inboundMessageId`/`outboundDeliveryId`, or is the error at the connection layer?
- What are `failureStage` and `safeErrorCode`?
- When did it start—after a deploy/secret rotation or a provider outage?
- How many messages are actually affected, and how many have newly entered the DLQ?
- Are queue ready age and last successful processing increasing/stalling?

Example:

~~~text
mailbox source MB1:
  errorCode = IMAP_AUTH_FAILURE
  failedMessage = null
  no inbound work ID

=> Resolve mailbox credential / provider access.
=> Do not create fake message DLQ items.
~~~

Another example:

~~~text
inbound work D1:
  errorCode = INVALID_MULTIPART
  attemptCount = 1
  payloadRef = stored safely

=> Mark FAILED / QUARANTINED.
=> Do not reconnect IMAP repeatedly to fix MIME bytes.
~~~

### 19.2. Step 2: Check Durability

Do not just look at error logs. Ask:

1. Is the original email or snapshot still accessible?
2. Was the inbound/outbound record created before the error occurred?
3. Did the error flow commit `RETRY`/`FAILED`, or only publish to an in-memory channel?
4. With a broker, was the message acked, offset-committed, or moved to the DLQ successfully?
5. Was there a secondary error when saving to the DLQ?

If a message was already acked/moved/deleted without a durable record, trigger recovery procedures from mailbox/provider logs/backups if permitted; do not assume the error channel can recover it on its own.

### 19.3. Step 3: Decide Actions by Error Type

| Situation | Action |
| --- | --- |
| IMAP authentication failed | Check credentials/OAuth/TLS, reduce reconnect storm |
| IMAP network unavailable | Backoff, health check, and wait for recovery |
| Handler database timeout | Check DB pool/locks/outage, bounded retry |
| Mass invalid MIME after deploy | Check parser regression and quarantine records |
| Malicious attachment | Do not auto-redrive; handle via security workflow |
| External ticket API timeout | Reconcile/use idempotency key before calling again |
| SMTP rate limit | Reduce concurrency, backoff/jitter |
| SMTP auth fail | Fix credentials, do not keep retrying the same wrong secret |
| SMTP result unknown | Reconcile before resending |
| Dead-letter DB/broker unavailable | Alert error flow, keep source unacked if policy allows |

### 19.4. Step 4: Verify Recovery

Monitor:

- New errors decrease and last successful poll/process updates.
- Queue ready age decreases.
- Retry-due jobs are processed without creating a retry storm.
- DLQ arrivals return to normal levels.
- Old terminal items are triaged or redriven according to policy.
- No duplicate tickets/emails are sent after recovery.
- No data is lost due to premature ack/marking SEEN.

## 20. Runbook: Dead-Letter Spike

A DLQ spike does not automatically mean a Spring Integration bug. Find the **root-cause group** and the **change timestamp**.

~~~text
Alert: inbound_dead_letter_arrivals spikes
           |
           v
Group by safeErrorCode / workflow / source
           |
           v
Check release, schema, auth, upstream changes
           |
    +------+----------------+
    |                       |
    v                       v
Transient but exhausted    Permanent/unsafe
    |                       |
    v                       v
Fix service/backoff         Fix validation/security
    |                       |
    v                       v
Approved redrive           Quarantine/review
           |
           v
Audit + monitor success
~~~

### 20.1. When Not to "Retry All"

- Message rejected due to malware/invalid payload.
- Original payload past retention or checksum mismatch.
- Business operation already completed, only app state was not updated.
- An inbound reply was already manually attached to a ticket and no longer needs processing.
- Outbound email was already SMTP accepted, only status retry occurred due to a DB error.
- Source identity belongs to a mailbox/tenant no longer permitted for processing.

The redrive feature needs **dry-run, bounded scope, operator permissions, audit, and rate limiting**. Otherwise, incident response actions can become the cause of higher error rates or duplicate data.

### 20.2. Do Not Delete the DLQ Just to Zero the Dashboard

A DLQ containing 500 failed messages can hold crucial information for investigation. Deleting records loses:

- Source identity and metadata about the failed work.
- Attempt history.
- Terminal reason.
- Ability to link to a ticket or outbound delivery.
- Audit trail of when the error occurred.

Apply retention/archiving by policy—do not keep data indefinitely, but do not delete data merely because a dashboard is alerting.

## 21. Dedicated Security for Error Channels and Dead Letters

Error flows potentially access more information than normal handlers because they contain exceptions, headers, and sometimes the failing payload. That makes them a security boundary.

### 21.1. Data Leakage Risk Through Exceptions

Exception messages/stack traces can contain:

- SMTP/IMAP host and username.
- Recipient/sender email addresses.
- MIME headers or subject.
- Raw body fragments reported by the parser.
- Internal URLs or object storage keys.
- External service responses containing tokens.

Do not serialize the entire `Throwable` into a dead-letter table or message broker without necessity and data controls. Store **safeErrorCode**, stage, attemptId, correlation ID, and a controlled source reference. Detailed logs require masking, restricted read access, and retention.

### 21.2. Defending Against MIME/Attachment Abuse

Incoming external emails may contain:

- Deeply nested multiparts to overload the parser.
- Extremely long headers or an abnormal number of parts.
- Attachments with spoofed content types.
- Archive bombs or files containing malware.
- HTML with phishing links or deceptive content.

Inbound flows must limit **message size, MIME depth, part count, attachment bytes, parse time, and concurrency**. For suspicious content, move to `QUARANTINED` before the business handler creates a visible ticket or imports files.

### 21.3. Authorization for DLQ and Redrive

Not everyone with permission to view a dashboard should be allowed to:

- Download raw MIME or attachments.
- See customer email addresses.
- Change status from `FAILED` to `RETRY`.
- Resend outbound emails.
- Delete audit events.

Enforce RBAC/tenant scopes, audit actor/reason/time, encrypt at rest where needed, and control retention. Do not send a DLQ containing sensitive emails to a public topic/bucket just for debugging convenience.

### 21.4. Do Not Use Message-ID to Bypass Authorization

RFC `Message-ID`, `In-Reply-To`, and `References` can be forged by a mail client/sender. They are useful for finding candidate conversations, **not proof that the sender has permission to modify another ticket, account, or record**.

An `ErrorMessage` containing an attacker's original mail is also untrusted data. Do not let header values arbitrarily determine buckets, file paths, SQL queries, or routing targets.

### 21.5. Rate-Limiting Errors and Logs

A malformed email can be polled and fail every second. If raw MIME/stack traces are stored each time, an attacker can cause:

- Disk/log exhaustion.
- High-cardinality metrics.
- Alert fatigue.
- Many unhelpful attempts in the DB.

Use source identity dedupe, retry backoff, bounded DLQ, bounded metric labels, and rate-limited logs. However, **do not swallow errors** if doing so drops an un-dispositioned work item.

## 22. Error-Handling Decision Diagram

~~~text
An error occurs in Spring Integration Mail
                    |
                    v
        Is error in an Integration endpoint?
               |                  |
              Yes                No
               |                  |
               v                  v
   Configure publisher /     Explicit try/catch,
   error channel/poller      publish error or persist state
               |                  |
               +--------+---------+
                        |
                        v
                 Have work/delivery ID?
                    |           |
                   No          Yes
                    |           |
                    v           v
             Source incident   Lookup durable state
             reconnect policy       |
                                      v
                              Classify error
                                      |
                          +-----------+-----------+
                          |           |           |
                          v           v           v
                       Transient    Permanent    Unknown
                          |           |           |
                          v           v           v
                    Retry schedule  Failed/DLQ   Reconcile
                          |           |           |
                          +-----------+-----------+
                                      |
                                      v
                              Commit durable outcome
                                      |
                                      v
                               Safe metrics/audit
                                      |
                                      v
                        Optional source ack/move/cleanup
~~~

### 22.1. The "Error Handled" Rule Must Be Defined

Avoid confusion:

~~~text
ErrorMessage consumed != business success
ErrorMessage logged   != durable dead letter
SMTP send exception   != definitely not accepted
IMAP SEEN flag         != business PROCESSED
DLQ published          != safe to lose audit/source state
~~~

For a flow to be reliable, each step must have clearly defined states and commit/ack boundaries. If an error has no source message ID, handle it as an infrastructure incident rather than fabricating a fake email to put into the DLQ.

## 23. Frequently Asked Questions

**"Is an error channel a dead-letter queue?"**  
No. An error channel is a channel that receives `ErrorMessage`. It can help route errors to a handler, but it does not store messages durably by default, nor does it provide automatic retry/audit/redrive. A DLQ is where terminal or non-auto-recoverable errors are persisted according to policy.

**"If I add a bean named errorChannel, will every Java exception go there?"**  
No. Spring Integration only publishes errors to an error channel when the component/endpoint is configured or supports error publication. A normal Java service call or direct `JavaMailSender.send` call does not automatically send every exception to the channel.

**"Why are errors on a DirectChannel thrown back to the caller?"**  
`DirectChannel` typically invokes the handler on the same thread that sent the message. Therefore, the exception can propagate up the call stack; it does not go through an error channel by default unless a corresponding catch/publish boundary exists.

**"Why don't errors on an ExecutorChannel appear on the thread calling send?"**  
The handler runs on a different executor thread. The exception cannot be thrown back up a call stack that has already returned. Error handling must be configured appropriately, and a state store is needed so information is not lost if a worker dies.

**"Should I create a dedicated mailErrorChannel instead of using the global errorChannel?"**  
Usually yes—it is helpful when mail flows need separate taxonomy, retries, owners, and DLQ. The global channel can still serve unclassified/general observability errors, but mail policies should not be conflated with every other integration flow.

**"Will a poller's errorChannel catch every error in the system?"**  
No. It is bound to the poller task and downstream calls within that processing context. Errors from executors, gateways, or services outside the poller may require separate mechanisms.

**"What is the ErrorMessage payload?"**  
It is a `Throwable`, often wrapped in a `MessagingException` in many Spring Messaging/Integration paths. It is not the original email payload.

**"How do I get the original email from an ErrorMessage?"**  
Check `MessagingException.getFailedMessage()` or `ErrorMessage.getOriginalMessage()` when available, and use the internal work ID to retrieve the durable copy. Both APIs can return `null`, especially when the error occurs before fetching the email.

**"If failedMessage is null, should it go into the DLQ?"**  
Do not automatically create a fake inbound mail item. If the error belongs to IMAP connect/auth before any message is read, handle it as a source-level incident with reconnect/backoff and alerting. A message-level DLQ entry needs an actual source identity/work ID.

**"If an error handler receives an error and returns, does that mean the message was processed successfully?"**  
No. It only means the exception was consumed at the error-flow layer. Business state must be explicitly recorded as `PROCESSED`/`RETRY`/`FAILED`; never mark success just because the error handler did not throw.

**"Does QueueChannel persist data across a JVM restart?"**  
Not by default. You need a persistent message store or a broker configured with appropriate durability/ack semantics. A channel name or using an in-memory queue does not guarantee durable delivery.

**"Can I name a channel deadLetterChannel and consider it a DLQ?"**  
No. If the channel only delivers to an in-JVM handler, there is no durable storage yet. You must prove that the message/metadata was committed to a database, broker, or message store.

**"Can RequestHandlerRetryAdvice replace database retry state?"**  
It can work for short, safe, idempotent in-process retries. However, the advice does not itself guarantee recovery after a JVM crash or persist full attempt history. For durable at-least-once requirements, database/broker state is needed.

**"What is ErrorMessageSendingRecoverer used for?"**  
It is a recovery mechanism that can send the exception to an error message/channel when the advice exhausts its configured retries. It does not automatically solve durable DLQ storage, business idempotency, or ack semantics.

**"If retry advice tries three times, is attempt_count three?"**  
It depends on the application's convention. If `attempt_count` increments once per worker claim, three internal retries may still belong to a single work claim. Separate `handler_attempts` and `durable_work_attempts`, or define one consistent frame of reference.

**"Why can MIME parsing errors happen again on every poll?"**  
Because the mail source still exists, the poller may pick it up again if there is no terminal state or if it still only scans UNSEEN. Persist the source identity, classify the error as permanent, mark `FAILED`/`QUARANTINED`, and avoid a hot loop.

**"Isn't marking IMAP SEEN after reading enough?"**  
No. The SEEN flag is not part of the transaction that creates tickets or imports data. Another mail client can alter SEEN, and a crash between the flag update and the business commit can cause messages to be missed.

**"If UIDVALIDITY changes, how do you retry old emails?"**  
Do not fetch the same UID number in the new generation assuming it is the same message. Use the durable MIME copy if available, or reconcile the source with appropriate evidence; preserve the old UIDVALIDITY history.

**"Should the entire MimeMessage be stored in the DLQ?"**  
Not by default. It may contain PII/attachments/malware, is hard to serialize safely, and may depend on streams or an IMAP connection. Use a payload reference to a permission-controlled durable snapshot along with essential metadata.

**"When should QUARANTINED be used instead of FAILED?"**  
When content needs isolation due to security policy, malware, MIME abuse, or failing safety checks. Redriving from quarantine requires separate permissions and workflows, unlike fixing a database error.

**"Does an SMTP MailSendException definitely mean the email was not sent?"**  
No. There are cases such as a timeout after DATA where the client does not know whether the relay accepted it. Distinguish definite failure from UNKNOWN; resending can create duplicates.

**"Does a successful SMTP send mean the recipient has the mail in their inbox?"**  
Not yet. It usually only proves that the SMTP relay accepted the message from the application's perspective. Bounces/DSNs and delivery feedback are a separate stage.

**"Why do DLQ write errors need a separate alert?"**  
Because they occur **right when the system is trying to save evidence of another failure**. If you continue acking the source without a durable disposition, the message can be lost permanently. Clear alerts and fallbacks are required.

**"What happens if an error handler publishes an ErrorMessage and then throws an exception?"**  
There is a risk that the same attempt gets processed again by another error handler, creating duplicate retries/dead letters. Choose a single error-ownership path and use a unique transition/attempt ID for deduplication.

**"Should IMAP/SMTP auth errors be retried continuously?"**  
No. Wrong credentials or provider policies will not resolve themselves via rapid retries and may even lock the account. Fix the secret/provider config, apply backoff, and alert.

**"Is dead letter a permanent final state?"**  
It is the state where **automatic retries** stop. Operators can redrive if the root cause is fixed and policy permits. States should not be reset without an audit trail.

**"Should a redrive create a new work ID?"**  
It depends on the architecture. Keeping the same ID allows linking attempt history; creating a new ID linked to the old ID keeps the terminal record immutable. Either way, business idempotency must prevent unintended duplicate side effects.

**"Why do DLQ metrics and the database sometimes disagree?"**  
Due to snapshot timing, metric counter resets, multiple replicas exporting global gauges, or collector errors. Define the source of truth, metric freshness, and scope-accurate aggregation.

**"Should subject/email address be attached to metrics for easy lookup?"**  
No. Those are PII and high-cardinality labels. Use error/workflow/source-type enums for metrics, and use internal work IDs in access-controlled logs to investigate individual records.

## 24. Checklist for Implementing Error Channels and Dead-Letter Flows

### Error routing boundaries

1. Identify all error sources: IMAP, POP3, inbound webhooks, MIME parser, business handlers, SMTP sender, database.
2. Know whether each handler runs synchronously or asynchronously, and who catches exceptions.
3. Configure a dedicated `mailErrorChannel` when mail-specific policies are needed.
4. Attach the error channel properly to pollers/endpoints, or explicitly publish when services sit outside the integration error mechanism.
5. Do not assume synchronous exceptions automatically route to the global `errorChannel`.
6. When handling an `ErrorMessage`, read `Throwable` and failed/original message **if present**, never assuming non-null.
7. Propagate internal work ID/attempt ID across all boundaries.

### Retries and state

8. Distinguish source-level errors from message-level errors.
9. Create a durable source identity before business processing.
10. For IMAP, use mailbox/folder/UIDVALIDITY/UID—not just the SEEN flag or RFC Message-ID.
11. Support `DISCOVERED`, `PROCESSING`, `RETRY`, `PROCESSED`, `FAILED`, and `QUARANTINED` where needed.
12. Claim work items atomically with lease/fencing.
13. Store attempt history and normalized error codes.
14. Retry with backoff/jitter, deadlines, and max attempts.
15. Do not retry permanent validation or malicious content indefinitely.
16. For external side effects, maintain idempotency keys and reconciliation when outcomes are unclear.

### Durable dead letter

17. The error flow must persist a durable disposition, not merely log.
18. Write `FAILED` and the DLQ event in the same transaction when using a database.
19. With a broker, configure durability, routing, publish confirmations, and proper ack/offset handling.
20. Never ack/delete the source before achieving durable receipt per contract.
21. If DLQ storage itself fails, trigger a secondary alert and a mechanism to avoid losing the work item.
22. Do not arbitrarily serialize raw MIME/Throwables/passwords into the DLQ.
23. Enforce appropriate access control/retention/quarantine for payloads.
24. Never let an `ErrorMessage` republish itself into the same channel infinitely.

### Operations and redrive

25. Have metrics for source errors, processing, retries, DLQ arrivals/current count, and backlog age.
26. Have alerts for error-flow persistence failures.
27. Separate dashboards for inbox processing, outbound SMTP, and provider delivery feedback.
28. Maintain runbooks for auth failures, missing IMAP sources, invalid MIME, SMTP UNKNOWN, and DB outages.
29. Redrive requires authorization, payload validation, side-effect checks, audit, and rate limiting.
30. Never use a single `Retry all` button for malware/quarantine/SMTP UNKNOWN alike.

### Testing

31. Test that `ErrorMessage` is routed from the appropriate poller/endpoint.
32. Test that errors without a `failedMessage` become source incidents rather than fabricated DLQ items.
33. Test that permanent errors move to `FAILED`/`QUARANTINED` exactly once.
34. Test retries up to max attempts with no attempts exceeding the cap.
35. Test the crash window between a side effect and status commit.
36. Test secondary failures when persisting to the DLQ.
37. Test IMAP UIDVALIDITY, duplicate source identity, and the SEEN flag.
38. Test SMTP temporary/permanent/unknown responses using a suitable fake server.
39. Test that redrive preserves audit trails and idempotency.
40. Test that metrics/logs do not contain credentials, MIME bodies, PII, or high-cardinality labels.

## 25. Architecture Summary

~~~text
                  Spring Integration Mail
                            |
        +-------------------+----------------------+
        |                   |                      |
        v                   v                      v
   Inbound IMAP        Inbound webhook        Outbound mail job
        |                   |                      |
        v                   v                      v
    Discover UID       Verify event ID          Outbox claim
        |                   |                      |
        +-------------------+----------------------+
                            |
                            v
                   Durable work identity
                            |
                            v
                    Integration endpoint
                            |
                +-----------+-----------+
                |                       |
                v                       v
             SUCCESS                  EXCEPTION
                |                       |
                v                       v
         Business state commit      ErrorMessage
                |                       |
                |                       v
                |                 mailErrorChannel
                |                       |
                |                       v
                |                Error classifier
                |                       |
                |           +-----------+-----------+
                |           |           |           |
                |           v           v           v
                |         RETRY      FAILED/DLQ   UNKNOWN
                |           |           |           |
                |           v           v           v
                |        Due work    Redrive     Reconcile
                |           |           |           |
                +-----------+-----------+-----------+
                            |
                            v
                 Audit, metrics, runbooks
~~~

### Principles to Remember

- `errorChannel` is an **ErrorMessage delivery route**, not automatically a dead-letter store.
- Synchronous, asynchronous, and poller errors have different **error publication semantics**.
- `ErrorMessage` carries a `Throwable` payload; the failed/original message **may be absent**.
- **Mailbox connection errors** need source-level retry/alerting; **specific email errors** need a work ID and processing state.
- **Safe retries** must consider whether a side effect may have already occurred as well as business deadlines.
- **DLQs must be durable**, with dedupe and audit; logging and dropping is not a dead letter.
- **Quarantine must not auto-redrive** and requires permissions and retention matching sensitivity.
- **SMTP UNKNOWN must not be blindly resent**, because the relay may have already accepted the message.
- **Mail ingestion must have durable source identity/cursor**, without relying on the SEEN flag to prove processing.

## Conclusion

**Error channels and dead-letter flows** in Spring Integration Mail separate exception handling from the business flow, but they are only trustworthy when paired with **durable state, error classification, bounded retries, idempotency, and controlled redrive mechanisms**. An `ErrorMessage` appearing on a channel is a signal that needs handling—not a guarantee that the original email was saved or that the business operation definitively failed.

When designing for production, clearly define **who catches the error**, **which message is affected**, **whether the error occurred before or after side effects**, **when the source may be acked**, and **what conditions prove `RETRY`/`FAILED` state is committed**. These boundaries turn a simple error handler into an observable, crash-recoverable, auditable mail operations system without dropping or uncontrollably duplicating emails.
