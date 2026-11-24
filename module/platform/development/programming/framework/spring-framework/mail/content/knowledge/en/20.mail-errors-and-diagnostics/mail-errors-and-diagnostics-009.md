# Determining Whether a Message Reached the Server in Spring Framework Mail

When a Spring application calls `JavaMailSender.send(...)`, a timeout or exception can make developers ask: **did the SMTP server receive the email, or did the email never leave the application?** This is not just a logging issue. Retrying when the server already received the message can cause users to receive duplicate emails; marking success when the server did not receive it can cause the system to lose notifications.

To diagnose accurately, distinguish **created the message in the application**, **sent bytes over the SMTP connection**, **SMTP relay accepted responsibility for processing the message**, and **final recipient received the email**. These four states are not equivalent. In Spring Framework Mail, `JavaMailSender` helps send emails, yet does not by itself prove every recipient saw the email in their Inbox.

This lesson focuses on evidence at each SMTP step, the meaning of reply codes, uncertainty windows when connections drop, reading JavaMail/Spring Mail errors, provider correlation strategies, safe retries, and operational diagnostic workflows.

## 1. "Sent" Has Multiple Meanings

In email systems, the same word "sent" is sometimes used for very different milestones:

| Status | What actually happened | Proves SMTP relay received the message? |
| --- | --- | --- |
| `CREATED` | Created `SimpleMailMessage` or `MimeMessage` | No |
| `ENQUEUED` | Mail-sending job sits in executor/queue/outbox | No |
| `CONNECTED` | Client opened TCP connection to SMTP server | No |
| `AUTHENTICATED` | Server accepted SMTP authentication | No |
| `ENVELOPE_ACCEPTED` | Server accepted `MAIL FROM`/`RCPT TO` | Not yet |
| `DATA_STARTED` | Server returned `354` and permitted content transfer | Not yet |
| `DATA_SENT` | Client finished transmitting message and DATA terminator | Insufficient without final reply |
| `SUBMITTED`/`ACCEPTED` | Server returned success reply for **end of DATA** | Yes, for that SMTP hop |
| `DELIVERED` | Delivery signal from receiving system/provider | Cannot be inferred solely from submission |
| `OPENED` | Open signal, if tracking is enabled and effective | Not reliable proof a real human read it |

An `@Async` call accepted by an executor only means the task entered an in-process queue. A `PENDING` row in a transactional outbox only means the send intent was persisted. Never label these states as `SENT`.

Even `SUBMITTED` should only be understood as **the SMTP server/relay the app connected to accepted the message**, not that the message definitely reached the Inbox.

## 2. How Does an SMTP Session Proceed?

Suppose Spring Mail connects to an SMTP relay using STARTTLS, authenticates, and sends a message to one recipient. An abbreviated session might look like:

~~~text
Client                                   SMTP server
  |                                            |
  |-------- TCP connection ------------------>|
  |<------- 220 Service ready ----------------|
  |-------- EHLO app.example.com ------------>|
  |<------- 250 capabilities -----------------|
  |-------- STARTTLS ------------------------>|
  |<------- 220 Ready for TLS ----------------|
  |====== TLS handshake =====================|
  |-------- EHLO app.example.com ------------>|
  |<------- 250 capabilities -----------------|
  |-------- AUTH ... ------------------------>|
  |<------- 235 Authentication successful ---|
  |-------- MAIL FROM:<bounce@example.com> -->|
  |<------- 250 Sender OK -------------------|
  |-------- RCPT TO:<user@example.net> ------>|
  |<------- 250 Recipient OK ----------------|
  |-------- DATA ---------------------------->|
  |<------- 354 Start mail input ------------|
  |-------- MIME headers and body ---------->|
  |-------- <CRLF>.<CRLF> -------------------->|
  |<------- 250 2.0.0 Queued as A1B2C3 -----|
  |-------- QUIT ---------------------------->|
  |<------- 221 Closing connection ----------|
~~~

This is an illustrative example, not a real transcript from any specific provider. Some systems use implicit TLS or require no AUTH; not every server returns the same phrasing or queue ID.

**The most important milestone for SMTP submission is the success reply after the DATA terminator**. The SMTP client transmits content and ends with a line containing only a dot per SMTP framing. Afterwards the server returns the message acceptance result.

### Why Is `250` Not Guaranteed to Mean "Sent"?

Code `250` can appear at multiple steps:

- After `EHLO`: server returns capabilities.
- After `MAIL FROM`: envelope sender address accepted.
- After `RCPT TO`: recipient accepted for the current transaction.
- After the `DATA` terminator: server confirms acceptance of the entire message.

Merely spotting a log line with `250 OK` without knowing which command it belonged to is insufficient to conclude the message was accepted.

### Why Is `354` Also Not Success?

The `354 Start mail input` reply invites the client to start sending DATA content. If the client fails mid-transfer or the server never returns a final result, message status is unconfirmed. Never mark `SUBMITTED` upon seeing `354`.

## 3. Strongest Evidence: The Final Reply of DATA

When the server returns a final success code after all message DATA, under standard SMTP semantics the server has accepted responsibility for processing the message for the corresponding envelope recipients.

Example:

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: no-reply@example.com
C: To: user@example.net
C: Subject: Confirmed
C:
C: Your order is confirmed.
C: .
S: 250 2.0.0 Ok: queued as A1B2C3
~~~

The line `250 2.0.0 Ok: queued as A1B2C3` appearing **after the DATA terminator** is proof the SMTP server received the submission. If the provider supplies queue ID `A1B2C3`, store that ID to correlate with mail logs, dashboards, or provider support.

Distinguish three conclusions:

1. **The first server received the submission**: provable by a final success reply after DATA.
2. **The message was forwarded to the next receiving system**: may require relay logs/traces.
3. **The message was delivered to the recipient's mailbox**: requires delivery/bounce signals or reliable provider data.

You cannot infer (2) or (3) solely from conclusion (1).

### Not Every SMTP Client API Returns Queue IDs

`JavaMailSender.send(...)` has no standard result field carrying the SMTP server's `queueId`. To capture queue IDs from DATA replies, you need transport-level visibility, SMTP relay logs, provider APIs, or specific instrumentation. Do not assume you can take the queue ID directly from `MimeMessage.getMessageID()`: these two identifiers are different.

## 4. Classifying Milestones to Assess Confidence

You can use the following reasoning table during diagnostics:

| Observed signal | Possible conclusion | Confidence level |
| --- | --- | --- |
| Cannot open TCP to SMTP | That relay could not have received the submission on this attempt | High, if no parallel send path exists |
| TLS handshake failed before `MAIL FROM` | SMTP submission did not complete on this connection | High |
| SMTP AUTH rejected before DATA | Message not submitted on this connection | High |
| `RCPT TO` rejected before DATA | Recipient rejected for current transaction | High for that recipient |
| Server returned `354` | Server permitted client to send DATA | Does not yet prove accepted |
| Client called `writeTo`/transmitted bytes | Data was written toward socket/client | Insufficient to prove server processed it |
| Server returned `4xx/5xx` after DATA | Server reported rejecting that submission | High per available response |
| Server returned `2xx` after DATA | SMTP hop accepted the message | High |
| Client timed out waiting for final reply after DATA | Server may or may not have received it | **Indeterminate** |
| `JavaMailSender.send` returned with no exception | Library considers send completed per contract and recipient mode | Application-level evidence; inspect partial-send |
| Email appeared in Inbox | Mailbox received a copy of the email | High for that email, though correlation to job still needed |
| Email not seen in Inbox | Unknown whether relay received it yet | Inconclusive |

Whenever SMTP traces and server-side logs are absent, accept that some situations cannot be determined with absolute certainty from client-side data alone.

## 5. Understanding `JavaMailSender` Return Behavior

In Spring Framework Mail, the common API is:

~~~java
MimeMessage message = mailSender.createMimeMessage();

// Use MimeMessageHelper to set From/To/Subject/Text.
mailSender.send(message);
~~~

`JavaMailSender.send(...)` is a synchronous call for the submission operation at the JavaMail layer. If the method completes normally, the application can usually record `SUBMITTED` per the library contract: transport finished sending for recipients according to configuration. However, it does not return a delivery receipt proving the message reached the final mailbox.

If the method throws an exception, inspect **the exception type and causes** before concluding no recipients were accepted by the server.

### Do Not Use a Simple `sent` Boolean

This simple pattern conflates too many states:

~~~java
try {
    mailSender.send(message);
    notification.setSent(true);
} catch (Exception exception) {
    notification.setSent(false);
}
~~~

In systems with retries or multiple recipients, a `sent` flag cannot adequately describe failures. Clearer statuses can be used:

~~~java
public enum MailSubmissionStatus {
    PENDING,
    PROCESSING,
    SUBMITTED,
    REJECTED,
    AMBIGUOUS,
    FAILED
}
~~~

Delivery statuses `DELIVERED` and `BOUNCED` should be tracked separately if the provider emits delivery events. Never set `DELIVERED` right after `send(...)` returns cleanly.

## 6. Reading Spring Mail Exceptions

Common exception types include:

| Exception | General meaning | What to check |
| --- | --- | --- |
| `MailAuthenticationException` | Mail server authentication failed | Credentials, auth mechanism, TLS, account policy |
| `MailPreparationException` | Error preparing content/email | Addresses, encoding, MIME resources, attachments |
| `MailSendException` | Error occurred during sending | Failed messages, nested causes, SMTP phase |
| `MailParseException` | Error parsing addresses or mail data | Input data, format |
| `MailException` | Base runtime exception of Spring Mail | Insufficient alone to classify transient/permanent |

Specific failures depend on the JavaMail provider, transport stage, and how Spring wraps Jakarta Mail's `MessagingException`. One `MailSendException` does not guarantee every message in a batch failed.

### Example Handling `MailSendException`

~~~java
import java.util.Map;
import org.springframework.mail.MailSendException;

try {
    mailSender.send(messages);
} catch (MailSendException exception) {

    Map<Object, Exception> failed =
        exception.getFailedMessages();

    for (Map.Entry<Object, Exception> entry : failed.entrySet()) {
        Object failedMessage = entry.getKey();
        Exception cause = entry.getValue();

        // Safely log application ID and error type;
        // avoid printing raw MIME/recipients to logs.
        log.warn("Mail submission failed: type={}",
            cause.getClass().getSimpleName());
    }

    throw exception;
}
~~~

When sending multiple messages in a batch, `getFailedMessages()` can provide a mapping of failed messages to their exceptions. Cross-reference with the application's notification IDs. Do not take a single outer exception and mark the whole batch unsent; other messages may already have been submitted.

At the per-message level, failures can still occur after some recipients were accepted or with unclear outcomes. Therefore, inspect nested exceptions and transport semantics.

## 7. Jakarta Mail `SendFailedException` and Recipient-Level State

Jakarta Mail's `SendFailedException` can supply address groups:

- `getValidSentAddresses()`: addresses recorded by transport as sent successfully under active send behavior.
- `getValidUnsentAddresses()`: valid addresses not yet sent successfully.
- `getInvalidAddresses()`: addresses considered invalid.

Some SMTP implementations offer more specific exceptions for addresses or SMTP commands. Package names vary by library generation: older environments use JavaMail, newer ones use Jakarta Mail/Angus Mail. Do not hard-code logic around a single implementation class if the application supports multiple transports.

The address arrays above represent submission-layer info, **not proof that mailboxes received the email**.

### Partial Success with Multiple Recipients

Suppose a message has `To`/`Cc`/`Bcc` totaling three envelope recipients:

~~~text
MAIL FROM:<no-reply@example.com>       -> 250
RCPT TO:<alice@example.net>            -> 250
RCPT TO:<bob@example.org>              -> 550
RCPT TO:<carol@example.edu>            -> 250
~~~

Subsequent behavior depends on SMTP transport configuration. Some modes abort the entire message if one recipient is invalid; partial-send modes may proceed to send DATA to accepted recipients.

With JavaMail's SMTP provider, properties like `mail.smtp.sendpartial` affect this behavior. Do not enable partial send just to "reduce errors" without reviewing business requirements, as each recipient's send result must then be tracked individually.

When one message has many recipients, the question "was it sent?" can have **different answers per recipient**. When strict reconciliation is required, persist per-recipient status or send independent messages to reduce complexity.

### Do Not Confuse `To`/`Cc`/`Bcc` Headers with the SMTP Envelope

Emails carry two layers of addressing:

- **`To`, `Cc`, `From` headers**: MIME content visible to recipients.
- **SMTP envelope `MAIL FROM` and `RCPT TO`**: addresses used for routing/transport.

`Bcc` normally does not appear in delivered headers, yet `Bcc` recipients are still supplied in the SMTP envelope. When diagnosing, verify which envelope recipients were accepted rather than looking only at the `To` header.

## 8. At Which Timeout Stage Is the Outcome Unclear?

Timeouts can happen at multiple points. Certainty varies by timing.

### Connection Timeout

The application failed to establish a connection to the server. Unless another retry/failover ran, **this attempt sent no data to the SMTP server**.

~~~text
Client ----- connect ----X---- SMTP server
           timeout
~~~

At this point retrying is usually safe if the cause seems transient and within quotas/deadlines.

### Timeout During TLS or AUTH

If the TLS handshake or authentication fails before sending the envelope/DATA, that connection did not complete submission. However, configuration errors should not be hammered with retries. Fix credentials, certificates, STARTTLS mode, or provider policy.

### Timeout During `MAIL FROM` or `RCPT TO`

Since DATA has not completed, there is no evidence the server accepted the full message over that connection. If a server reply rejected a recipient, record it explicitly. Do not infer success from a `250` on `MAIL FROM`.

### Timeout While Transmitting DATA

The server may not have received enough content; or the library may have transmitted almost all or all content while the client does not know how far the server processed it. Depending on the failure point, conclusions may be uncertain.

### Timeout After Sending the DATA Terminator

This is the most critical uncertainty window:

~~~text
Client                              Server
  |                                    |
  |--- MIME bytes and DATA end ------->|
  |                                    | accepted & queued?
  |<--------- response lost --------- X|
  |
  +--> timeout / socket error
~~~

If the server queued the message and the reply was lost, the client sees an error even though the message was actually accepted. Automatic retry can send a second copy.

**There is no reliable way to deduce from a bare timeout that the server definitely did not receive the message.** Confirming requires SMTP relay logs, provider queries, or correlation IDs.

## 9. What Evidence Can SMTP Debug Logs Provide?

Jakarta Mail has a debug mode that records SMTP session progress. In Spring Boot, enable the corresponding JavaMail property in debug environments:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${MAIL_USERNAME}
    password: ${MAIL_PASSWORD}
    properties:
      mail:
        debug: true
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

This example is for controlled diagnostics. Actual log output depends on Jakarta Mail/Angus Mail version, `Session` debug output, and logging configuration. Verify output in a safe environment before use.

### Be Careful with Sensitive Data

**Do not enable SMTP protocol debug permanently in production without risk controls.** Transcripts can contain:

- Recipient and envelope sender emails.
- Hostnames/domains.
- MIME content/metadata.
- AUTH info or sensitive data depending on version/config.
- Message IDs, queue IDs, or reconciliation data.

Enable only briefly, on a test flow or test account, restrict log viewers, and enforce turn-off/retention procedures. Never log passwords/tokens and never paste raw transcripts containing PII into public tickets.

### How to Read an SMTP Transcript

Rather than hunting for any `250` line, verify sequentially:

1. Did it connect to the right host/port?
2. Did STARTTLS/auth succeed?
3. What did the server reply to `MAIL FROM`?
4. What did the server reply to each `RCPT TO`?
5. Was there a `DATA` command and a `354` reply?
6. Did the client send the DATA terminator?
7. Did the server reply `2xx` **after** the DATA terminator?
8. Is there a provider queue ID or transaction ID?
9. After which step did a connection/timeout error occur?
10. Were there multiple recipients, partial send, or multiple messages in a batch?

If the final DATA reply is missing because logs were truncated or the connection dropped, there are insufficient grounds to mark `NOT_SENT` definitively.

## 10. Setting Timeouts to Prevent Indefinite Hangs

SMTP can wait on connect, reading replies, and writing data. In JavaMail's SMTP provider, common properties are:

~~~properties
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
~~~

Values are normally in milliseconds:

| Property | Controls |
| --- | --- |
| `mail.smtp.connectiontimeout` | Time waiting to establish a connection |
| `mail.smtp.timeout` | Time waiting to read data/replies from server |
| `mail.smtp.writetimeout` | Time waiting to write to socket |

If using the `smtps` protocol, the corresponding prefix may be `mail.smtps.*` per provider. Do not confuse network timeouts with "time during which the server definitely has not received the mail".

A read timeout while waiting for the final DATA reply can produce an `AMBIGUOUS` state. Setting timeouts too short can increase failure rates and duplicate sends on retry. Tune timeouts based on actual SMTP latency, message sizes, and SLAs.

## 11. Correlation IDs: Linking Application to SMTP

Without stable IDs, correlating a JavaMail failure with relay logs is very hard, especially when many messages share the same subject and recipient.

Maintain at least:

- **Notification ID**: internal ID of the send request.
- **Attempt ID**: unique ID per attempt.
- **`Message-ID` header**: RFC message identifier, helpful for correlation.
- **Provider queue/message ID**: ID returned by the SMTP relay/ESP if available.
- **Recipient/envelope metadata**: logged only as permitted by security policy.
- **UTC timestamps**: send start, response receipt, and status updates.

These IDs serve different purposes and should not be treated as interchangeable.

### Example Setting a Custom Correlation Header

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendNotification(
        String notificationId,
        String recipient,
        String text) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Notification confirmation");
    helper.setText(text, false);

    message.setHeader(
        "X-App-Notification-ID",
        notificationId
    );

    mailSender.send(message);
}
~~~

Custom headers help correlate raw MIME when receiving systems preserve headers. Providers may modify or strip headers, so do not rely on them as the sole evidence.

### `Message-ID` Is Not Queue ID

The `Message-ID` header is an RFC 5322 email content identifier. Provider queue IDs are internal identifiers at an SMTP hop or ESP. They can be completely different.

`MimeMessage.getMessageID()` reads the `Message-ID` header currently on the message. When calling `saveChanges()` or `JavaMailSender.send(...)`, the library may generate/update management headers, including `Message-ID` depending on implementation. If recording actual values, inspect the prepared/sent message per implementation and cross-check on the relay. Do not assume a `Message-ID` created before calling `send` always remains unchanged.

`Message-ID` **is not an SMTP-guaranteed idempotency key**. Two resent messages with the same `Message-ID` can still be delivered twice.

## 12. Recording Meaningful States in the Application

Never settle for `sent = true/false`. A clearer model:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +--- send() returns normally ---> SUBMITTED
   |
   +--- definitive rejection ------> REJECTED / FAILED
   |
   +--- uncertain result ----------> AMBIGUOUS
   |
   +--- transient before DATA -----> RETRY_WAIT
   |
   +--- permanent preparation -----> FAILED

SUBMITTED
   |
   +--- provider event -----------> DELIVERED / BOUNCED / DEFERRED
~~~

Separate **submission state** from **delivery state** if the application needs to track both. A record can be `SUBMITTED` and later `BOUNCED`; there is no contradiction.

Model example:

~~~java
public record MailSubmissionRecord(
    String notificationId,
    String attemptId,
    SubmissionStatus status,
    Instant attemptedAt,
    Instant acceptedAt,
    String providerMessageId,
    String failureCode
) {}

public enum SubmissionStatus {
    PENDING,
    PROCESSING,
    SUBMITTED,
    REJECTED,
    AMBIGUOUS,
    RETRY_WAIT,
    FAILED
}
~~~

Best-effort emails may not need every field stored, but for transactional mail these states tell operators whether a retry is truly warranted or reconciliation is required.

## 13. Illustrative Logging Around `JavaMailSender`

An adapter can record start, completion, and exception milestones. Example:

~~~java
@Service
public class MailSubmissionService {

    private final JavaMailSender mailSender;
    private final MailAttemptRecorder recorder;

    public MailSubmissionService(
            JavaMailSender mailSender,
            MailAttemptRecorder recorder) {
        this.mailSender = mailSender;
        this.recorder = recorder;
    }

    public void submit(
            String notificationId,
            MimeMessage message) {

        String attemptId = UUID.randomUUID().toString();
        Instant startedAt = Instant.now();

        recorder.markStarted(
            notificationId, attemptId, startedAt);

        try {
            mailSender.send(message);

            recorder.markSubmitted(
                notificationId, attemptId, Instant.now());

        } catch (MailException exception) {
            recorder.recordFailure(
                notificationId,
                attemptId,
                exception.getClass().getSimpleName(),
                Instant.now()
            );

            throw exception;
        }
    }
}
~~~

`MailAttemptRecorder` is an application-defined interface, not a Spring Mail API. The example uses the exception class to record a technical milestone; production needs a classifier to separate definite rejections from ambiguous outcomes.

**Important:** logs from a wrapper only tell whether `send(...)` returned cleanly or threw an exception. They do not themselves prove the SMTP DATA final reply if high-precision failure analysis is needed. When necessary, combine application logs with SMTP transcripts and provider-side traces.

Never write full `MimeMessage`, email bodies, secrets, or attachments into logs just for diagnostics.

## 14. When `@Async` Returns, Has the Email Reached the Server?

Not necessarily. Example:

~~~java
@Async("mailTaskExecutor")
public void sendAsync(OutgoingMail mail) {
    mailDelivery.send(mail);
}
~~~

When the caller invokes `sendAsync`, the task may only have been submitted to an executor. Returning to the caller does not mean `mailDelivery.send(...)` executed or SMTP received the message.

~~~text
HTTP request
    |
    +--> submit async task
    |
    +--> HTTP response 202 Accepted
                 |
                 v
            Thread pool queue
                 |
                 v
            Worker thread
                 |
                 v
            JavaMailSender.send
                 |
                 v
            SMTP DATA response
~~~

If returning HTTP `202 Accepted`, understand that the application accepted the processing request, not that SMTP accepted the message. If tasks sit only in an in-memory queue, process crashes can lose jobs.

For critical emails, persist send requests in a durable outbox/broker and execute with workers. That way `PENDING` states can recover across restarts.

## 15. When Is Retrying Safe?

Before retrying, determine whether evidence shows the message was already accepted by the SMTP hop.

| Scenario | Auto-retry? | Reason |
| --- | --- | --- |
| Unable to connect, no SMTP exchange | Maybe, if error is transient | No submission happened on this attempt |
| Auth failed due to wrong credentials | No, fix configuration | Retrying repeats the exact same error |
| Server returned `4xx` before DATA | Maybe per policy | No accepted message in this transaction |
| Server returned `4xx` after DATA | Maybe per policy/provider | Server reported not accepting that submission |
| Server returned `5xx` after DATA | Usually no, unless fixing content/policy | Permanent or policy rejection |
| Final `250` received after DATA | Do not retry same submission | Server already received it |
| No final DATA reply received | Cannot confirm safe | Risk that message was already received |
| `send` succeeded yet bounced later | Do not blindly retry | Delivery failure needs separate handling |

An application might decide to retry even `AMBIGUOUS` outcomes if the notification is low-sensitivity and duplicates are acceptable. However, that must be an intentional business policy, not a technical assumption that the message was never sent.

### Why Is an Outbox Needed?

An outbox persists send requests in the same business transaction so jobs are not lost. Workers record attempts/statuses and retry transient errors with delays. Yet an outbox does not create exactly-once SMTP delivery:

~~~text
Worker sends successfully
         |
         v
Server returns 250
         |
         v
Worker killed before writing SUBMITTED
         |
         v
Outbox still PROCESSING
         |
         v
Lease expires and worker retries
         |
         v
May send duplicate
~~~

If the provider API supports idempotency keys, reuse the same key across attempts. Traditional SMTP provides no universal idempotency guarantee; `Message-ID` alone does not prevent duplicates.

## 16. Reconciling with the SMTP Server or Provider

When client-side evidence is insufficient, turn to server-side data sources.

### Operations-Managed SMTP Relay

Search mail logs/queues using:

- Approximate send time, synchronized to timezone/UTC.
- Envelope sender.
- Envelope recipient.
- `Message-ID` header if logged by the relay.
- Queue ID if available.
- Application hostname or authenticated sender.
- Custom notification ID/header if retained by the relay.

Locate the **acceptance event** at the first hop, not just a connection-established line. Then follow the queue ID in relay logs to see whether the message was forwarded, deferred, or bounced.

### Email Service Provider

If using an ESP with dashboards, event APIs, or webhooks, cross-check:

- Provider message ID.
- Event types: accepted/processed, delivered, deferred, bounced, dropped, complained.
- Timestamps and recipients.
- Corresponding API/SMTP submission requests.
- Suppression lists, quotas, and policy rejections.

Event names vary across providers. Never equate `processed` or `accepted` with `delivered` unless provider documentation states so.

### Recipient Mailbox

If a user reports not seeing an email, also check spam/junk, quarantine, inbox rules, forwarding, and mailbox policies. A user not finding an email does not prove the initial sending server never received the submission.

## 17. DSN, Bounces, and Delivery Events

SMTP has mechanisms related to Delivery Status Notifications (DSN), while ESPs typically provide event webhooks. These show what happened **after the message was accepted**.

Example:

~~~text
Application
    |
    v
SMTP relay ---- 250 accepted ----> Application: SUBMITTED
    |
    +--> Delivery success event ---> DELIVERED
    |
    +--> Temporary downstream error -> DEFERRED
    |
    +--> Permanent downstream error -> BOUNCED
~~~

A bounce can arrive minutes or hours later. `SUBMITTED` remains accurate for the initial milestone; delivery state transitions to `BOUNCED` when new evidence arrives.

DSN is absent on many mail paths and does not guarantee downstream providers return complete details. Email client opens or tracking pixel downloads are also not reliable proof a human read the email, due to proxies, caches, image blocking, and privacy protections.

## 18. Multiple SMTP Hops Complicate Diagnostics

Emails rarely travel straight from the application to the Inbox:

~~~text
Spring application
       |
       v
SMTP submission relay
       |
       v
Outbound filtering / policy
       |
       v
Destination MX
       |
       v
Mailbox storage
       |
       v
Recipient client
~~~

A final `250` after DATA only confirms the hop the client connected to. The relay may accept and queue the message for further checks. Afterwards the message may be:

- Successfully forwarded.
- Held for scanning/quarantine.
- Deferred and retried downstream.
- Bounced due to nonexistent mailbox/quota.
- Blocked by provider policy/suppression.

Never take the first hop's reply as proof that every hop succeeded. If delivery SLAs matter, monitor provider delivery events and classify downstream states.

## 19. Example Decision Tree When Mail Sending Fails

~~~text
JavaMailSender.send(...) returned?
                |
         +------+------+
         |             |
      Success     Exception/timeout
         |             |
         v             v
   Mark SUBMITTED   Read nested causes,
   (per API)        SMTP phase, logs
         |             |
         |       +-----+----------------------+
         |       |            |               |
         |   Before DATA  Clear server    After DATA with
         |       |        final error     lost response
         |       |            |               |
         |       v            v               v
         |  Not submitted  4xx/5xx classify AMBIGUOUS
         |       |            |               |
         |       v            v               v
         |  Retry/fix     Retry or halt   Provider trace/
         |                                reconciliation
         |
         v
  Track delivery separately
         |
       +---+
       |   |
    Delivered  Bounced/Deferred
~~~

Key takeaway: **when the final reply is missing, the accurate conclusion may be "unknown", not "not sent"**. Embracing `AMBIGUOUS` prevents the system from over-claiming beyond its evidence.

## 20. Diagnostic Walkthroughs for Specific Scenarios

### Scenario 1: Connection Refused

Logs record `Connection refused` when opening a socket to SMTP `host:port`. No SMTP session existed for this attempt. Unless a failover or parallel retry ran, the message was not submitted over that connection.

Handling direction: verify DNS, port, firewall, network, SMTP availability, and TLS config. If transient, retry with backoff; if misconfigured, fix before retrying.

### Scenario 2: Authentication Failed

Server returns an AUTH error. No evidence of reaching `MAIL FROM`/`RCPT`/DATA in that session. This is usually a credential/policy error, unsuitable for rapid continuous retries.

Handling direction: check credentials, app password/OAuth if required by provider, STARTTLS, and account permissions. Never log credentials.

### Scenario 3: Server Accepts Recipient Yet Rejects DATA

~~~text
S: 250 Recipient OK
C: DATA
S: 354 Continue
C: ...message...
C: .
S: 552 Message size exceeds policy
~~~

The server accepted the recipient yet **rejected the entire message**. Shrink the MIME size, replace attachments with links, or adjust valid policies. Retrying the exact same message usually does not help.

### Scenario 4: Final DATA Reply Lost

~~~text
C: DATA
S: 354 Continue
C: ...message...
C: .
[read timeout, no final reply]
~~~

You cannot assert the message was not received. Use queue/provider logs with correlation IDs to reconcile. If reconciliation is impossible, apply duplicate-risk policies and mark `AMBIGUOUS`.

### Scenario 5: Server Returns Final `250` Yet User Does Not See the Email

Submission succeeded at the first relay. Inspect downstream provider events, spam/quarantine, mailbox rules, bounces, or defers. Do not resend the whole message just because the user did not see the email after a few seconds.

### Scenario 6: One Message in a Batch Fails

`JavaMailSender.send(message1, message2, message3)` can report errors for a subset of messages in the batch. Do not mark all three as `NOT_SENT` without evidence; use `MailSendException.getFailedMessages()` and per-notification state to reconcile.

### Scenario 7: One Recipient Rejected, Others Valid

Inspect `mail.smtp.sendpartial`, `SendFailedException`, and SMTP transcripts. Some recipients may have had submissions sent by transport while others did not. Never store one shared flag for the entire group if exact reconciliation is required.

### Scenario 8: `@Async` Caller Reports Success

An `@Async` method returning cleanly may only indicate the executor accepted the task. Track worker results instead of inferring SMTP acceptance from the HTTP response. If reliability matters, use an outbox instead of an in-memory-only queue.

## 21. Testing Submission Outcomes with an SMTP Test Server

To verify how the application reacts, use an SMTP test server such as GreenMail or MailHog/Mailpit in test environments. For happy-path tests, assert the server received the raw message with the right `Message-ID`/headers, recipients, and content.

Scenarios to simulate:

1. TCP connection failure before SMTP handshake.
2. AUTH failure.
3. Recipient rejection at `RCPT TO`.
4. DATA rejection after content transfer.
5. Final `250` after DATA.
6. Disconnect/timeout before and after the DATA terminator.
7. Multi-recipient send with partial-send policies.
8. Batch send mixing successes and failures.
9. Worker crash after relay accepted yet before DB marks `SUBMITTED`.
10. Provider bounce event arriving after submission.

Not every test server supports fault injection at every SMTP phase. For lost responses after DATA, you may need a specialized SMTP stub/proxy capable of closing the connection at the exact boundary.

### Simple Test with a Fake Mail Sender

Unit tests can verify application logic when `send` returns normally or throws an exception:

~~~java
@Test
void normalReturnMarksSubmissionAsSubmitted() {
    JavaMailSender sender = mock(JavaMailSender.class);
    MailAttemptRecorder recorder = mock(MailAttemptRecorder.class);

    // Stub createMimeMessage or use a real sender with a test Session.
    // Call the submit service with a valid MimeMessage.
    // Assert recorder.markSubmitted(...) was called.

    // This is a unit test of application semantics;
    // it does not prove an SMTP server actually received the message.
}
~~~

Mock tests only verify how code handles results from the abstraction. To test SMTP conversations, run integration tests against a real server/proxy or protocol-controlling simulator.

## 22. Production Diagnostic Playbook

When a ticket reports "email not received", follow this sequence:

1. **Identify notification ID** and expected send time.
2. **Check job/outbox**: `PENDING`, `PROCESSING`, `RETRY_WAIT`, `SUBMITTED`, `AMBIGUOUS`, or `FAILED`?
3. **Locate attempt logs** by attempt ID, host/provider, and timestamp; confirm a worker ran.
4. **If an exception occurred**, classify network, TLS/auth, recipient, DATA, timeout, and nested causes.
5. **Verify server acceptance evidence**: final `2xx` after DATA, queue ID, or provider logs.
6. **If outcome is unclear**, do not conclude `NOT_SENT`; mark `AMBIGUOUS` and reconcile.
7. **If `SUBMITTED`**, query provider delivery/bounce/defer/suppression events.
8. **If provider reports `DELIVERED`**, check recipient mailbox, spam, quarantine, and forwarding.
9. **Decide on retry** based on error kind, deadline, and duplicate risk.
10. **Update state and record investigation outcome** by ID without storing unnecessary sensitive content.

Example record structure:

~~~json
{
  "notificationId": "mail-2026-00031",
  "attemptId": "attempt-4",
  "status": "AMBIGUOUS",
  "smtpPhase": "AFTER_DATA",
  "provider": "primary-relay",
  "startedAt": "2026-11-12T10:00:00Z",
  "lastObservedReply": "354",
  "finalDataReplyObserved": false,
  "providerQueueId": null,
  "reason": "socket read timeout after DATA"
}
~~~

These fields are an **illustrative schema**. `JavaMailSender` does not automatically populate `smtpPhase` or `providerQueueId`; appropriate transport/provider data sources are needed. Never fabricate values to fill fields lacking evidence.

## 23. System Observability to Avoid Losing Track

A mail system should separate metrics by layer:

| Metric | What is observed |
| --- | --- |
| Requests accepted | Application accepted send request |
| Jobs queued | Work persisted/enqueued |
| Submission attempts | Actual calls to sender |
| Submission success | Transport reported success |
| Submission rejected | Transport/server reported definite error |
| Submission ambiguous | Outcome unclear |
| Provider delivered | Delivery event with evidence |
| Provider bounced | Bounce event |
| Queue oldest age | Age of unsubmitted notifications |
| Retry exhausted | Jobs exhausting retry policy |

Alert on SMTP authentication failures, post-DATA timeouts, provider throttling, spikes in `AMBIGUOUS` records, or `PENDING` items lingering too long. A high `send` success rate does not guarantee a high delivery rate; track both metric series separately.

Avoid high-cardinality metric labels like recipient addresses or notification IDs. Logs may carry internal IDs for tracing, while metric labels should use bounded dimensions like category, provider, and failure class.

## 24. Common Mistakes

| Mistake | Why it is wrong | Proper approach |
| --- | --- | --- |
| "Saw `250`, so it was sent" | Could be `250` for EHLO/`MAIL FROM`/`RCPT` | Verify final `2xx` after DATA |
| "`354` means server received message" | `354` only permits starting DATA | Wait for reply after DATA terminator |
| "Client wrote bytes, so server received it" | Socket write is not server acceptance | Require final reply or server log |
| "`send()` threw exception, so definitely unsent" | May be partial/ambiguous | Read causes and SMTP phase |
| "`send()` succeeded, so it reached Inbox" | Only confirms submission | Track delivery events |
| "Email not seen means SMTP never got it" | Could be spam, deferred, or bounced | Investigate downstream |
| "`Message-ID` is the queue ID" | Two identifiers serving different roles | Store IDs separately |
| "`Message-ID` prevents duplicates automatically" | SMTP does not guarantee dedup | Use provider idempotency if supported |
| "HTTP `202` means email was sent" | May only mean async job accepted | Track worker/submission state |
| "Retrying any timeout is safe" | Post-DATA timeout may have been accepted | Use `AMBIGUOUS`/reconciliation |
| "One bad recipient means nobody got it" | Partial send may have occurred | Inspect recipient-level diagnostics |
| "Mail debug is always harmless" | Can leak credentials/PII/MIME | Bound, sanitize, and disable debug |
| "Delete outbox right after send succeeds" | Loses reconciliation capability | Use controlled retention |

## 25. Key Takeaways

To determine whether a message reached the server, rely on **evidence at the right SMTP step**:

- Succeeding at `EHLO`, `AUTH`, `MAIL FROM`, and `RCPT TO` does not prove the server accepted the whole message.
- `354` permits transferring DATA, not a submission result.
- **Final `2xx` after the DATA terminator** is the clearest proof that the current SMTP hop accepted the message.
- If the client times out before seeing the final DATA reply, the outcome may be **indeterminate**.
- `JavaMailSender.send(...)` returning normally corresponds to library-level submission success, yet does not prove delivered.
- When `MailSendException` occurs, inspect failed messages, nested causes, SMTP phase, and recipient-level outcomes.
- With multiple recipients or partial send, one message can have different outcomes across recipients.
- The SMTP envelope and MIME headers are distinct layers; `Bcc` also participates in the envelope.
- `Message-ID`, notification ID, attempt ID, and provider queue ID should be stored separately for correlation.
- Debug logs help trace SMTP phases, yet credentials, PII, and message bodies must be protected.
- After submission, delivery/bounce/defer are downstream concerns tracked via provider events.
- Async queues or `PENDING` outbox rows do not mean the message reached the SMTP server.
- For `AMBIGUOUS` timeouts, retries must weigh duplicate risk, provider reconciliation, and idempotency.
- Never log "not sent" if the only evidence is a socket read timeout after DATA.

**The most important rule:** If an SMTP final success reply arrived after DATA, there is solid ground to conclude that server received the submission. If the connection dropped before the final reply, the only accurate conclusion may be "unknown". Designing applications with an `AMBIGUOUS` state, correlation IDs, and reconciliation prevents both lost emails and duplicate sends during network incidents.
