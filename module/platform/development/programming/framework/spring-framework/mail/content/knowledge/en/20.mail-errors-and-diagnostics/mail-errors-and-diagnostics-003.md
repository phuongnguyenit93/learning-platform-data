# MailSendException and Failed Messages

In a Spring Framework Mail application, a call to `JavaMailSender.send(...)` can throw `MailSendException` when sending email through the mail transport encounters an error. This error is especially notable when the application sends **multiple messages in a single call**: some messages may already have been accepted by the SMTP server while others fail. Therefore, merely seeing the exception and concluding "no emails were sent" can lead to duplicate sends.

Spring provides `MailSendException.getFailedMessages()` to retrieve the messages recorded as having failed along with their corresponding exceptions. However, this map must be interpreted according to **the sending stage, error type, and SMTP server response**; it is neither a list of emails guaranteed not to have reached recipients, nor proof that the remaining messages were delivered to the Inbox.

This lesson focuses on how to read `MailSendException`, analyze failed messages in a batch, trace root causes from Jakarta Mail, distinguish message-level from recipient-level errors, build safe diagnostic logs, and decide on controlled retries.

## 1. Where Does MailSendException Sit in Spring Mail?

Spring Mail has several common exception groups:

| Exception | Typical scenario | Investigation direction |
| --- | --- | --- |
| `MailException` | Parent class of Spring Mail exceptions | Identify the specific subtype |
| `MailAuthenticationException` | SMTP authentication failed | Credentials, SMTP AUTH policy, auth mechanism |
| `MailParseException` | Mail data cannot be validly parsed/converted in the active flow | Addresses, data format |
| `MailPreparationException` | Error preparing MIME message, e.g., inside `MimeMessagePreparator` | Template, attachment resource, Jakarta Mail |
| `MailSendException` | Transport failed to send or one or more messages failed | Connection, SMTP response, failed messages |

Spring Mail exceptions are generally unchecked. Thus, code calling `send(...)` does not need to declare `throws MailSendException`. That does not mean errors can be ignored.

### `MailSendException` vs. `MessagingException`

`MailSendException` belongs to Spring Mail. `jakarta.mail.MessagingException` belongs to Jakarta Mail and typically appears when operating on a MIME message or in the transport layer.

Example:

```java
import jakarta.mail.MessagingException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.MimeMessageHelper;

// When building MIME:
helper.setTo(recipient);      // May throw MessagingException.
helper.setSubject(subject);   // May throw MessagingException.

// When handing off to the sender:
mailSender.send(message);     // May throw MailException,
                              // including MailSendException.
```

If `MimeMessageHelper` fails to build the MIME message, the error can occur **before** SMTP sending. If done through `MimeMessagePreparator`, Spring may wrap some preparation errors in `MailPreparationException`. Do not lump all MIME and SMTP errors together as "flaky network".

## 2. When Does MailSendException Typically Appear?

Several situations:

1. Cannot connect to the SMTP host or port.
2. The mail server closes the connection or a communication error occurs.
3. The SMTP server rejects the sender, recipient, or message content.
4. One message in a batch reports a transport error while other messages may have been processed.
5. Closing/ending the transport fails after a sequence of sends.
6. The connection drops at a point where the send outcome is unclear.

Example of a batch:

```text
JavaMailSender.send(M1, M2, M3, M4)
                 |
                 v
             SMTP transport
                 |
                 +-- M1: server accepted
                 +-- M2: rejected
                 +-- M3: server accepted
                 +-- M4: I/O error
                 |
                 v
       MailSendException
       failedMessages: M2 -> cause2
                       M4 -> cause4
```

This diagram illustrates the possibility of a batch having heterogeneous outcomes. Reality also depends on whether the error occurred at the **shared connection step** or at **individual messages**, and whether the application has sufficient evidence confirming SMTP accepted a message.

## 3. Important Components of MailSendException

Two APIs to know:

```java
Map<Object, Exception> failures = exception.getFailedMessages();
Exception[] causes = exception.getMessageExceptions();
```

In addition, the exception has general information:

```java
String message = exception.getMessage();
Throwable cause = exception.getCause();
```

### `getFailedMessages()`

`getFailedMessages()` returns `Map<Object, Exception>`. Each entry associates a message object with the error Spring recorded when trying to send it:

- **Key:** the corresponding message, usually `MimeMessage` or `SimpleMailMessage` depending on the overload and call site.
- **Value:** the exception associated with sending that message.

This is the most valuable data when analyzing a **batch with multiple messages**.

### `getMessageExceptions()`

`getMessageExceptions()` returns an array of exceptions attached to message failures. It is convenient when you only want to iterate through causes, but it does not preserve the mapping to messages as clearly as the map.

In batch processing, prefer `getFailedMessages()` to know **which message** goes with **which cause**. Use `getMessageExceptions()` when investigating or aggregating causes without full message details.

### `getCause()` and `getMessage()`

`getCause()` can represent a transport-level or outer wrapper error, such as a connection error. `getMessage()` provides a general description, but is insufficient to distinguish:

- Whether the error occurred before sending data or after SMTP may have received data.
- Whether one or multiple messages failed.
- Whether any recipients were accepted by the server.

Do not handle errors merely by checking `exception.getMessage().contains("timeout")` and automatically retrying everything.

## 4. Reading Failed Messages Properly

Basic example:

```java
import org.springframework.mail.MailSendException;

import java.util.Map;

try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    Map<Object, Exception> failedMessages =
            ex.getFailedMessages();

    for (Map.Entry<Object, Exception> entry :
            failedMessages.entrySet()) {
        Object failedMessage = entry.getKey();
        Exception failure = entry.getValue();

        // Identify the message via the application's correlation mapping.
        // Classify the failure before deciding on retry.
    }

    if (failedMessages.isEmpty()) {
        // There was a send/transport error without a per-message map.
        // Do not interpret an empty map as all messages having succeeded.
    }
}
```

An important point is that **the map can be empty** in some cases where the exception is created without per-message failure details. Therefore:

- `failedMessages.isEmpty() == true` does **not** prove the batch succeeded.
- `failedMessages.containsKey(message) == true` only indicates Spring recorded an error for that message.
- A message absent from the map does not mean it was delivered to the Inbox.
- For network errors occurring at an ambiguous moment, a message present in the map also does not always mean the SMTP server definitely did not accept it.

## 5. Keys in `failedMessages` Are Message Objects, Not Email Addresses

Suppose the application does:

```java
MimeMessage first = mailSender.createMimeMessage();
MimeMessage second = mailSender.createMimeMessage();

// Set recipient, subject, and body for each message.
mailSender.send(first, second);
```

When `MailSendException` occurs, keys in `getFailedMessages()` are the message objects attached to the send operation, **not recipient strings by default**.

Do not assume:

```java
// Misconception: the key is not a String email address.
Exception cause = ex.getFailedMessages()
        .get("customer@example.net");
```

Instead, the application must store a mapping from message object to notification ID or business identifier before calling the sender:

```java
Map<Object, String> notificationIds = new IdentityHashMap<>();

MimeMessage first = buildMessage(firstNotification);
MimeMessage second = buildMessage(secondNotification);

notificationIds.put(first, firstNotification.id());
notificationIds.put(second, secondNotification.id());

try {
    mailSender.send(first, second);
} catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        String notificationId =
                notificationIds.get(entry.getKey());
        Exception cause = entry.getValue();

        // Correlate using notificationId
        // instead of logging the entire MimeMessage.
    }
}
```

In the example, `IdentityHashMap` clearly expresses mapping based on **the exact object instance** passed into the batch. This technique should only be used within an active execution flow; do not store object keys in a database or treat object identity as a durable identifier.

If the system uses `SimpleMailMessage`, a similar approach can be used with the original objects. However, when retries across restarts or multiple workers are needed, persist the **notification ID** in a database and rebuild the message from that data.

## 6. SimpleMailMessage and MimeMessage Can Both Appear

Spring Mail has two familiar sending paths:

### Sending Simple Text

```java
SimpleMailMessage simple = new SimpleMailMessage();
simple.setFrom("no-reply@example.org");
simple.setTo("person@example.net");
simple.setSubject("Notification");
simple.setText("Text content.");

mailSender.send(simple);
```

### Sending MIME/HTML

```java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, "UTF-8");

helper.setFrom("no-reply@example.org");
helper.setTo("person@example.net");
helper.setSubject("HTML notification");
helper.setText("<p><strong>HTML</strong> content.</p>", true);

mailSender.send(mime);
```

In `JavaMailSenderImpl`, `SimpleMailMessage` content is converted to MIME to send over transport, yet failed message entries may reference the original simple object. Thus, handling code should not cast every key to `MimeMessage`:

```java
Object key = entry.getKey();

if (key instanceof MimeMessage mime) {
    // MIME message recorded an error.
} else if (key instanceof SimpleMailMessage simple) {
    // Simple mail message recorded an error.
} else {
    // Exact key type unknown:
    // use only correlation metadata stored externally.
}
```

Do not rely on `key.toString()` for logging. Message objects can carry recipient addresses, content, or sensitive headers.

## 7. Distinguishing One Message from Multiple Recipients

A single `MimeMessage` can be sent to **multiple recipients**:

```java
helper.setTo(new String[] {
        "a@example.net",
        "b@example.net",
        "c@example.net"
});
```

When this message encounters an error:

- `getFailedMessages()` speaks about the **message object** that failed.
- It does not necessarily state precisely **which recipient** was rejected.
- Some recipients may be accepted by the server while others are rejected, depending on SMTP commands, transport policy, and partial send configuration.

To find per-address status, inspect the Jakarta Mail cause, especially `jakarta.mail.SendFailedException` and SMTP provider-specific exceptions.

Do not use the entry count of `failedMessages` as the count of failed recipient addresses. A single entry can relate to a message with dozens of recipients.

## 8. Understanding Jakarta Mail's SendFailedException

`SendFailedException` can carry the following address groups:

```java
import jakarta.mail.SendFailedException;
import jakarta.mail.Address;

void inspect(SendFailedException ex) {
    Address[] invalid = ex.getInvalidAddresses();
    Address[] validSent = ex.getValidSentAddresses();
    Address[] validUnsent = ex.getValidUnsentAddresses();
}
```

General meaning:

| API | Transport meaning when reporting error | What must not be assumed |
| --- | --- | --- |
| `getInvalidAddresses()` | Addresses invalid/unaccepted per transport report | Not all recipients of the message |
| `getValidSentAddresses()` | Addresses reported by transport as sent/accepted at the relevant stage | Does not prove delivery to Inbox |
| `getValidUnsentAddresses()` | Valid addresses not yet sent per transport report | Not an email syntax error |

These arrays may be `null` or empty depending on the error and implementation. Do not assume every exception contains complete lists.

### An Analysis Example

Suppose a message has three recipients:

```text
To: a@example.net, b@example.net, c@example.net
```

Transport reports:

```text
invalidAddresses:     b@example.net
validSentAddresses:   a@example.net
validUnsentAddresses: c@example.net
```

In this case, you should not blindly resend the whole message to all three recipients: `a@example.net` could receive a duplicate. Read partial send policies and check what the transport actually performed.

**Note:** recipient group reports reflect transport behavior and evidence at the time of the exception, not the final delivery event.

## 9. The MessagingException Cause Chain

A Jakarta Mail exception can contain:

- A standard cause (`Throwable.getCause()`).
- A "next exception" via `MessagingException.getNextException()` chaining.
- A `SendFailedException` or specific SMTP exception deeper in the chain.

Therefore, calling `getCause()` only once can miss diagnostic data.

Example traversing the cause chain:

```java
static void traceCauses(
        Throwable failure,
        Consumer<Throwable> consumer
) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());

    Throwable current = failure;
    while (current != null && visited.add(current)) {
        consumer.accept(current);
        current = current.getCause();
    }
}
```

The function above only walks the regular cause chain. For `MessagingException`, also inspect `getNextException()`; the next exception can differ from the cause chain. A complete utility should guard against cycles and avoid logging raw exception messages without sanitizing sensitive data.

### Reading `nextException` Carefully

```java
if (failure instanceof MessagingException messaging) {
    Exception next = messaging.getNextException();
    if (next != null) {
        // Analyze next according to its actual exception type.
    }
}
```

With SMTP providers, there may be specialized exceptions containing the SMTP reply code, address, and command. Specific package names depend on the mail implementation/version in use (e.g., Angus Mail or older implementations), so do not hard-code implementation package classes without verifying project dependencies.

## 10. SMTP Reply Codes Are Diagnostic Data, Not the Complete Conclusion

SMTP has reply groups:

| Group | General meaning | Preliminary handling direction |
| --- | --- | --- |
| 2xx | Server accepted the corresponding protocol step | Check which step was accepted |
| 4xx | Transient protocol error | May be retried per policy |
| 5xx | Permanent protocol error | Usually requires fixing config, address, or data |

Examples:

- `421`: server not ready/closing connection.
- `450` or `451`: temporary issue related to mailbox/server.
- `550`: commonly used when mailbox/recipient is rejected.
- `552`: exceeded storage or size limit depending on server context.
- `554`: message rejected by policy or transaction failure.

These are common examples, not absolute rules across all providers. **Reply codes must be tied to the specific SMTP command** and the server's message. The same `550` code can appear for many different reasons.

### `RCPT TO` Reply Differs from Final `DATA` Reply

```text
Client                              SMTP server
  | ---- MAIL FROM ---------------> |
  | <--- 250 ---------------------- |
  | ---- RCPT TO -----------------> |
  | <--- 250 / 4xx / 5xx ---------- |
  | ---- DATA --------------------> |
  | <--- 354 ---------------------- |
  | ---- MIME bytes + "." --------> |
  | <--- 250 / 4xx / 5xx ---------- |
```

If a recipient is rejected at the `RCPT TO` step, transport may clearly know which address was rejected. If the connection drops **after sending DATA but before receiving the final reply**, the application may not know whether the server accepted the message.

Do not classify errors solely by phrases in the exception while ignoring when the error occurred.

## 11. Connection Failure Differs from Per-Message Failure

When sending a batch, errors can occur at two layers:

### Shared Connection Failure

```text
connect SMTP
     |
     X connection failed
     |
     +-- M1 never had a chance to send
     +-- M2 never had a chance to send
     +-- M3 never had a chance to send
```

If no connection was established, multiple messages may share a single root cause. In `JavaMailSenderImpl`, connection setup failures can cause the entire input list to be reported as failed.

### Per-Message Failure

```text
connect SMTP: success
   |
   +-- send M1 -> accepted
   +-- send M2 -> error
   +-- send M3 -> accepted
   |
   +-- close connection
```

In this situation, the failed map helps distinguish failed messages from messages without recorded errors in the loop. However, the actual outcome still depends on SMTP responses and the transport close state.

**Do not retry an entire batch just because a `MailSendException` occurred.** First analyze failed messages and the state already recorded for each notification.

## 12. Complete Example: Sending a Batch and Correlating Notification IDs

Suppose an application has three notifications to send. Each notification has a durable ID.

```java
record MailRequest(
        UUID notificationId,
        String recipient,
        String subject,
        String body
) {}
```

Build the MIME message using helper:

```java
private MimeMessage createMail(MailRequest request)
        throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, "UTF-8");

    helper.setFrom("notification@example.org");
    helper.setTo(request.recipient());
    helper.setSubject(request.subject());
    helper.setText(request.body(), false);

    return message;
}
```

Correlate objects with notifications:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailSendException;

import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public void submitBatch(List<MailRequest> requests)
        throws MessagingException {

    List<MimeMessage> messages = new ArrayList<>();
    Map<Object, UUID> correlation = new IdentityHashMap<>();

    for (MailRequest request : requests) {
        MimeMessage mime = createMail(request);
        messages.add(mime);
        correlation.put(mime, request.notificationId());
    }

    try {
        mailSender.send(messages.toArray(MimeMessage[]::new));
        for (MailRequest request : requests) {
            // Record SMTP submission result using a short DB transaction.
            markSubmitted(request.notificationId());
        }
    } catch (MailSendException ex) {
        for (Map.Entry<Object, Exception> entry :
                ex.getFailedMessages().entrySet()) {

            UUID notificationId =
                    correlation.get(entry.getKey());
            Exception sendFailure = entry.getValue();

            if (notificationId != null) {
                recordFailureForReview(
                        notificationId,
                        sendFailure
                );
            }
        }

        // When a batch throws an exception, entries absent from the failed map
        // and cases where the map lacks details must be verified separately.
        recordBatchExceptionForReconciliation(ex);
    }
}
```

`markSubmitted`, `recordFailureForReview`, and `recordBatchExceptionForReconciliation` are application-implemented extension points. The example shows **how to obtain correlation**, not a complete retry/commit policy; production must persist state atomically, handle empty maps, and classify each failure.

### Why Not Automatically Mark Every Message Absent from `failedMessages` as `DELIVERED`?

Because:

1. "No per-message error recorded" does not equate to delivery.
2. Transport/close errors can occur after several sends.
3. SMTP acceptance differs from mailbox delivery.
4. Without strong per-message evidence, an indeterminate state or reconciliation mechanism is needed.

If optimizing round-trips is unnecessary, sending each notification individually often makes correlation and state tracking simpler:

```java
for (MailRequest request : requests) {
    try {
        mailSender.send(createMail(request));
        markSubmitted(request.notificationId());
    } catch (MailSendException ex) {
        recordFailureForReview(request.notificationId(), ex);
    }
}
```

However, sending individually does not eliminate ambiguous SMTP outcomes, does not automatically guarantee exactly-once delivery, and still needs error policies when preparing messages before `send`.

## 13. How to Read `getMessageExceptions()`

Example:

```java
catch (MailSendException ex) {
    Exception[] messageErrors = ex.getMessageExceptions();

    for (Exception error : messageErrors) {
        // Classify error types or build an aggregate diagnostic summary.
    }
}
```

`getMessageExceptions()` is suitable for viewing a list of causes, but has two limitations for business handling:

- Array elements contain no message keys.
- A single shared error repeated across multiple messages can easily be miscounted as multiple independent incidents.

For example, a connection failure before sending can affect ten messages. If the map has ten entries sharing the same root exception, counting "ten distinct SMTP errors" can be misleading.

Usually you should track separately:

- Number of affected notifications.
- Number of exceptions by class or root cause.
- Number of failed batches.
- Number of network/auth/recipient/content causes.

Do not use `getMessageExceptions().length` as the count of messages guaranteed not to have reached recipients.

## 14. Classifying Causes: Network, Authentication, Recipient, Content

| Error group | Common symptom | Retry? | What to inspect |
| --- | --- | --- | --- |
| DNS/connection | Unresolved host, connection refused, network unavailable | Usually retryable if definitely failed before sending | Host, port, firewall, DNS, timeout |
| TLS/STARTTLS | Handshake/certificate/protocol failure | Usually requires config fix; do not hot-retry | TLS mode, truststore, certificate, server |
| Authentication | Credentials rejected, SMTP AUTH disabled | Do not retry infinitely | Username, auth mechanism, provider policy |
| Recipient | Server rejects some `RCPT TO` | Depends on code and recipient group | Specific address, 4xx/5xx, partial send |
| Sender/domain policy | Sender not allowed, relay denied | Usually requires config/policy fix | `From`, envelope sender, authentication |
| Message content/size | Oversized, content blocked | Usually requires fixing content | MIME size, attachments, provider limit |
| Rate limiting | Server throttling, temporary response | Retry with backoff | Quota, throughput, `Retry-After` if API provides |
| Timeout after DATA | No final response observed | **Ambiguous outcome** | Transport logs, provider events, SMTP stage |
| Transport close failure | Exception while closing connection | Insufficient to claim messages were not sent | Outcomes before close, provider logs |

Do not apply a blanket rule "retry every `MailSendException`". The same exception class can wrap vastly different causes.

## 15. `MailAuthenticationException` Must Not Be Mistaken for a Failed Message

Example SMTP configuration with invalid credentials:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
```

If authentication fails, Spring may throw `MailAuthenticationException`. This is a distinct error type; code with only `catch (MailSendException)` may miss it.

Use explicit branches:

```java
try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Investigate credentials/provider policy; do not flood with retries.
} catch (MailSendException ex) {
    // Read failed messages and classify transport outcome.
} catch (MailException ex) {
    // Other Spring Mail error; record per notification.
}
```

Do not log passwords, SMTP tokens, or full configurations containing secrets. For authentication errors, check the account, SMTP AUTH permissions, and TLS configuration.

## 16. `MailPreparationException` Occurs Before or While Preparing to Send

Complex emails can be built using `MimeMessagePreparator`:

```java
MimeMessagePreparator preparator = message -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");
    helper.setFrom("no-reply@example.org");
    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(plainText, htmlText);
    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );
};

mailSender.send(preparator);
```

If the preparator fails due to template, address, resource, or MIME construction, Spring may throw `MailPreparationException` rather than `MailSendException`.

Therefore:

- Handle **render/compose** errors separately from SMTP errors.
- Do not retry network connections when the actual failure is an unreadable attachment file.
- Do not consider the message to have started sending if the preparator has not successfully built MIME.

Message preparation errors usually require fixing data/templates/resources. Some transient resource source errors can be retried, but must be classified by actual cause.

## 17. Configuring SMTP Timeouts for Diagnostics

Timeout properties prevent threads from hanging indefinitely:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Values are in milliseconds in Jakarta Mail SMTP configuration. These are illustrative values and should be tuned to your network, provider, and message sizes.

| Property | Scope |
| --- | --- |
| `mail.smtp.connectiontimeout` | Timeout when establishing connection |
| `mail.smtp.timeout` | Timeout reading response from socket |
| `mail.smtp.writetimeout` | Timeout writing data to socket |

Timeouts carry different meanings when deciding on retries:

- **Unable to connect:** usually provides evidence that the message was not sent over that connection.
- **Read timeout after DATA:** the server may have already received the message; do not infer it was not sent.
- **Write timeout:** inspect the stage and amount of data transmitted; outcome may be uncertain.

Timeouts keep the system from hanging forever, but do not by themselves provide an exactly-once guarantee.

## 18. Enabling Mail Debug Safely

Jakarta Mail has protocol debug options to help inspect SMTP commands and server replies. In controlled environments, you can enable it with the corresponding configuration:

```yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
```

**Do not leave SMTP debug enabled indefinitely in production.** Protocol logs can contain sender/recipient addresses, metadata, sensitive content, and in some cases authentication details. You must:

- Enable only during a short investigation window.
- Control where logs are written and who can access them.
- Remove/redact addresses, tokens, sensitive headers, and message bodies.
- Do not paste raw debug logs into public tickets.
- Turn it off when finished and follow retention policies.

In many cases, you only need the SMTP reply code, stage, exception class, notification ID, and provider message ID for diagnostics without storing the body.

## 19. How to Log to Find Failed Messages Without Exposing PII?

A structured log:

```text
event=mail_submission_failure
notificationId=N-2026-091
attempt=2
transport=smtp
smtpStage=RCPT_TO
smtpReplyCode=550
exceptionClass=SendFailedException
classification=PERMANENT_RECIPIENT_REJECTION
status=FAILED
```

Avoid:

```java
logger.error(
        "Failed mail: " + failedMessage +
        ", cause=" + exception,
        exception
);
```

Because `failedMessage` and exception messages can carry raw email addresses, server details, internal paths, or message content.

Log standardized fields. If recipient tracing is needed, store an internal `recipientId` or a controlled hash instead of the full address.

### Correlation ID Should Exist Before `send`

A notification ID should be assigned when the application records the send request, for example:

```text
orderEventId=order-123-confirmed
notificationId=N-2026-091
messageType=ORDER_CONFIRMATION
templateVersion=v5
attempt=2
```

When `MailSendException` occurs, the system can link the exception to the notification without searching inside subject/body. This is especially important when the same content is sent to many people.

## 20. When Sending Batches: Do Not Blindly Retry the Whole List

Anti-pattern example:

```java
try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    mailSender.send(messages); // Risk of duplicating the whole batch.
}
```

Because some messages may have already been accepted by the SMTP server on the first attempt, resending everything can create duplicates.

A better flow:

```text
Batch send throws MailSendException
            |
            v
Read failedMessages + root causes
            |
            v
Correlate message with notification ID
            |
            v
Classify per notification
            |
            +-- definite temporary rejection -> RETRY_WAIT
            +-- definite permanent rejection -> FAILED
            +-- ambiguous acceptance --------> UNKNOWN
            +-- confirmed submission --------> SUBMITTED
            |
            v
Individually retry notifications eligible per policy
```

**Important:** the map is only partial evidence. Do not guess `SUBMITTED` for every message absent from the map if the batch encountered a transport close error or the outcome is not sufficiently clear.

### Why Can Sending Notifications Individually Be Easier to Operate?

Sending one message at a time:

- Makes it easy to attach errors to a notification ID.
- Makes it easy to persist attempt counts and status.
- Makes it easy to classify retries individually.
- Reduces the chance of confusing one message with another.

Drawbacks can include connection/transport overhead and lower throughput. If batching is truly required, build detailed correlation and state tracking rather than just catching a single generic exception.

## 21. Retries Must Be Evidence-Based, Not Just Exception-Type-Based

A minimal policy:

| Scenario | Suggested status | Action |
| --- | --- | --- |
| DNS/connect error before sending | `RETRY_WAIT` | Retry with backoff |
| SMTP clearly returns 4xx without accepting message | `RETRY_WAIT` | Retry up to limit |
| SMTP clearly returns 5xx recipient/sender rejected | `FAILED` or await data fix | Do not retry continuously |
| SMTP AUTH error | `FAILED`/configuration incident | Fix config before retrying |
| Template/MIME error before `send` | `FAILED`/quarantine | Fix data/template |
| Final response lost after DATA | `UNKNOWN` | Provider reconciliation or risk-aware policy |
| SMTP clearly accepted | `SUBMITTED` | Track delivery separately |

This is a policy framework; you must account for SMTP provider characteristics, business criticality, recipient count, and the application's duplicate-prevention requirements.

### Backoff and Jitter

For transient errors:

```text
Attempt 1: initial send
Attempt 2: after 30 seconds
Attempt 3: after 2 minutes
Attempt 4: after 10 minutes
Attempt 5: after 30 minutes
```

Cap retry attempts and add jitter to prevent many workers from retrying simultaneously. If the provider returns rate-limit guidance or wait durations, prioritize applying the provider's policy.

For permanent errors or bad data, repeated retries do not help and can cause account lockouts or quota overruns.

## 22. The `UNKNOWN` State and Ambiguous SMTP Outcomes

A typical failure window:

```text
Worker                            SMTP server
  |                                    |
  |--------- DATA + MIME ------------->|
  |                                    | received message
  |<-------- 250 accepted -------------|  (response lost)
  X timeout                           |
  |                                    |
  | MailSendException                  |
  |                                    |
  | Unsure whether server received it or not
```

If automatically resent, the server may receive a second copy. If not resent, in the case where the server did not receive it, the email may be lost.

Separate:

- **Errors definitely before acceptance:** can retry per policy.
- **Errors definitely rejected by the server:** handle by code and cause.
- **Errors lacking sufficient proof of acceptance:** record `UNKNOWN`, query provider if available, and apply reconciliation policy.

### How to Reconcile

- Query provider API/event logs by correlation or provider message ID when available.
- Consume delivery/accepted/bounce webhooks if supported by the provider.
- Retain enough attempt metadata to investigate without storing secrets.
- Define wait windows and authorization rules for manual resends.
- If automatic retry is mandatory, explicitly document the duplicate risk in design and monitoring.

Do not use MIME's `Message-ID` as a default "SMTP deduplication key". Pure SMTP offers no global deduplication guarantee solely via this header.

## 23. `JavaMailSender` Returns `void`: Track State in the Application

Send APIs typically do not return a per-recipient receipt object:

```java
mailSender.send(mimeMessage); // void
```

If no exception is thrown, the application knows the sender call completed per observed transport result; **it does not mean the email was delivered to the Inbox**.

To track lifecycle, the application can store:

| Status | Meaning |
| --- | --- |
| `PENDING` | Send request recorded |
| `PROCESSING` | Worker is processing |
| `SUBMITTED` | SMTP/provider accepted send request per observed result |
| `RETRY_WAIT` | Waiting to retry a recoverable error |
| `FAILED` | Terminal failure per policy |
| `UNKNOWN` | Unclear whether server received the message |
| `DELIVERED` | Delivery proof from provider/events if supported by system |
| `BOUNCED` | Provider reported bounce after submission |

Do not use a single `sent=true/false` flag if you need to distinguish send errors, delivery failures, and ambiguous outcomes.

## 24. Async Sending: Exceptions Appear on the Worker, Not the Caller

Example:

```java
@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<Void> sendAsync(MimeMessage message) {
        mailSender.send(message);
        return CompletableFuture.completedFuture(null);
    }
}
```

A `MailSendException` occurs on the worker and is represented as an exceptional future when Spring properly manages the async method. The caller cannot simply write:

```java
try {
    asyncMailService.sendAsync(message);
} catch (MailSendException ex) {
    // Not how to catch errors from an async worker.
}
```

Instead:

```java
asyncMailService.sendAsync(message)
        .whenComplete((unused, failure) -> {
            if (failure != null) {
                // Correlate by notification ID and record failure.
            }
        });
```

If tasks must survive restarts, a future is still insufficient. Persist notifications/outbox and durable statuses so workers can retry per policy.

### `@Async` Does Not Automatically Turn `MailSendException` into a Retry

Adding `@Async` alone does not make errors disappear and does not classify causes. `@Retryable` also requires care: retrying the whole send method can send duplicates when SMTP accepted the previous attempt but the response was lost.

## 25. Transactional Outbox and `MailSendException`

For business emails, a resilient operational pattern is:

```text
HTTP/business transaction
    |
    +-- UPDATE order
    +-- INSERT mail_notification(PENDING)
    |
    v
COMMIT
    |
    v
Worker claim notification
    |
    v
Compose MIME message
    |
    v
JavaMailSender.send(...)
    |
    +-- success ----------> SUBMITTED
    |
    +-- MailSendException -> classify failed message/cause
                                |
                                +-- RETRY_WAIT
                                +-- FAILED
                                +-- UNKNOWN
```

Benefits:

- Send requests survive commits and restarts.
- Each notification has its own identifier.
- Workers can record attempts and outcomes.
- Failed messages can be investigated by notification ID.
- No need to hold a database transaction open while SMTP is executing.

### Outbox Does Not Automatically Eliminate All Duplicates

If a worker finishes sending and crashes before recording `SUBMITTED`, the notification may be picked up again. Therefore:

- Use atomic claims and leases to limit two workers sending concurrently.
- Persist correlation and status.
- Classify `UNKNOWN` when the outcome is unclear.
- Use provider-level idempotency if the provider API supports it.
- Do not claim exactly-once delivery solely from having an outbox.

## 26. Do Not Confuse a Failed Message with a Retry Candidate

A message appearing in `getFailedMessages()` is **a message for which the sender recorded an error**. It is not necessarily a message **safe to resend immediately**.

Consider three cases:

**Case A — Connection refused before SMTP session starts.** The message was never transmitted over the failed connection. This is usually a retry candidate after waiting/backoff.

**Case B — Recipient explicitly rejected with 550.** Resending to the same address immediately will likely fail again; fix the recipient or resolve provider policy.

**Case C — Connection dropped after DATA.** The message may have been accepted. Immediate retry risks duplicates; use `UNKNOWN` or provider reconciliation.

Therefore, the workflow should not be:

```text
failedMessages => retry all
```

but rather:

```text
failedMessages
  -> match notification
  -> inspect root cause / SMTP stage
  -> classify outcome
  -> choose policy
  -> update durable state
```

## 27. Reading Recipient Data from Failed Messages: Security Notes

When the key is `MimeMessage`, you can inspect recipients:

```java
if (message instanceof MimeMessage mime) {
    Address[] recipients = mime.getAllRecipients();
    // Process internally only; do not log raw if containing personal data.
}
```

However, reading recipients from a failed object has several limitations:

- `getAllRecipients()` can throw `MessagingException`.
- Recipients may include To, Cc, and Bcc.
- Not every recipient failed if a message has multiple recipients.
- Logging recipients can leak email addresses and Bcc lists.

Instead of relying on the raw message to find the notification, store correlation beforehand. If recipient-level reporting is needed, extract details from `SendFailedException` and store results with appropriate access controls.

## 28. Testing `MailSendException` with an SMTP Test Server

Do not test transport errors by sending real emails to users.

Useful tools include:

- **GreenMail:** SMTP server for integration tests to verify messages and simulate sending scenarios.
- **Mailpit/MailHog:** capture emails locally/in staging, inspect content and raw MIME.
- **Mock `JavaMailSender`:** inject deliberate errors when unit testing exception-handling branches.
- **SMTP test server with rejection rules:** test response codes and cases where one recipient/message is rejected.

### Test 1 — Single Message Sent Successfully

Configure the SMTP test server to accept messages. Verify:

- `send(...)` does not throw `MailSendException`.
- The message arrives at the test server.
- The notification is recorded as `SUBMITTED`, not `DELIVERED`.

### Test 2 — Unable to Connect

Point the sender to an unavailable SMTP endpoint in the test environment. Verify:

- The error is classified appropriately as connection/transport.
- The notification is not deleted.
- Retry policy uses backoff.
- Logs do not contain credentials.

### Test 3 — Invalid Recipient

SMTP test server rejects one recipient. Verify:

- `MailSendException` or appropriate exception is recorded.
- `SendFailedException` is accessible when provided by the implementation.
- Lists of invalid/valid sent/valid unsent are not misinterpreted.
- The entire message is not resent to already-accepted recipients.

### Test 4 — Batch with Only One Message Rejected

Send a batch of two or three messages, configuring the server to reject one specific message.

Expectations:

- Failed entry is correlated to the notification ID.
- The entire batch is not marked failed by default.
- The entire batch is not automatically retried.
- Each notification's state reflects actual evidence.

### Test 5 — Exception Without a Failed-Message Map

Simulate a `MailSendException` without a detailed map. Verify:

- Code does not throw `NullPointerException` when iterating.
- An empty map is not treated as success.
- The entire operation moves to appropriate investigation/reconciliation.

### Test 6 — Ambiguous Outcome After DATA

The SMTP test harness intentionally closes the connection at the boundary after receiving DATA but before sending the final reply.

Expectations:

- The application does not immediately auto-retry assuming it was not sent.
- State can transition to `UNKNOWN`.
- Clear reconciliation or operational policy exists.

## 29. Example of a Safe Error-Summary Utility

Instead of logging entire messages, a utility can output error-type statistics:

```java
public record SendFailureSummary(
        int failedMessageCount,
        List<String> exceptionTypes,
        boolean hasPerMessageDetails
) {}

public SendFailureSummary summarize(MailSendException ex) {
    Map<Object, Exception> failed = ex.getFailedMessages();

    List<String> types = failed.values().stream()
            .map(value -> value.getClass().getSimpleName())
            .distinct()
            .sorted()
            .toList();

    return new SendFailureSummary(
            failed.size(),
            types,
            !failed.isEmpty()
    );
}
```

This is a **technical** summary, not a verdict on "how many emails did not reach the Inbox". It helps logs and dashboards report failed message counts without containing recipients/bodies.

If the map is empty while the exception still has a cause, you can log `exceptionType` and a separate `diagnosticCode`; no need to store raw unsanitized exception messages.

## 30. Metrics and Observability for Failed Messages

| Metric | Meaning |
| --- | --- |
| `mail_submission_attempt_total` | Number of send attempts |
| `mail_submission_success_total` | Number of sender calls observed to succeed |
| `mail_send_exception_total` | Number of `MailSendException` occurrences |
| `mail_failed_message_total` | Number of recorded failed-message entries |
| `mail_authentication_error_total` | Number of authentication errors |
| `mail_retry_scheduled_total` | Number of notifications scheduled for retry |
| `mail_unknown_outcome_total` | Number of notifications with indeterminate outcomes |
| `mail_permanent_failure_total` | Number of notifications with terminal failure |
| `mail_outbox_lag_seconds` | Delay from recording notification to processing |

When designing metrics, avoid high cardinality. Do not use email addresses, notification IDs, subjects, or exception messages as time-series metric labels. That information belongs in controlled logs/tracing, not metric labels.

### Distinguishing Three Counts

- **Exception count:** one `send(...)` call can throw one exception.
- **Failed-message count:** one exception can contain many failed-message entries.
- **Recipient failure count:** one message can have many recipients and different per-recipient outcomes.

These three numbers should not be added or compared as if they share the same unit.

## 31. Practical Diagnostic Workflow

When the system reports `MailSendException`, proceed in order:

1. **Identify notification/batch:** retrieve notification ID, attempt, timestamp, and SMTP host alias.
2. **Check exception type:** `MailSendException`, `MailAuthenticationException`, or `MailPreparationException`.
3. **Read failed messages:** entry count, mapping back to notification ID; handle separately if the map is empty.
4. **Trace cause:** exception class, cause chain, `MessagingException.getNextException()`, and SMTP reply code if present.
5. **Pinpoint SMTP stage:** connect, AUTH, `MAIL FROM`, `RCPT TO`, DATA, or close.
6. **Assess partial outcome:** single message or multiple messages; single recipient or multiple recipients.
7. **Classify:** known retryable failure, permanent failure, ambiguous outcome, observed submission.
8. **Persist durable state:** `RETRY_WAIT`, `FAILED`, `UNKNOWN`, or `SUBMITTED` based on evidence.
9. **Reconcile with provider:** if the outcome is ambiguous, check event/logs or ask operations to verify.
10. **Review impact:** avoid resending notifications that were already accepted.

This workflow should be automated for parts that can be determined with certainty, while leaving a dedicated path for situations where SMTP does not supply sufficient proof.

## 32. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging only `ex.getMessage()` | Do not know which message failed | Read `getFailedMessages()` and correlate |
| Treating an empty map as success | Misses transport/close errors | Analyze outer exception and operation state |
| Assuming every key is `MimeMessage` | `ClassCastException` when sending simple mail | Check key type, use correlation ID |
| Using recipient string as map key | Cannot find message error | Key is the message object, not recipient by default |
| Logging entire failed messages | Leaks To/Cc/Bcc, body, and headers | Log notification ID and sanitized metadata |
| Using failed entry count as failed recipient count | Inaccurate statistics | Separate message-level and recipient-level |
| Retrying the entire batch | Duplicates already-accepted messages | Retry per notification based on evidence |
| Retrying every `MailSendException` | Duplicates or retries permanent errors | Classify root cause, SMTP stage, `UNKNOWN` |
| Treating `send(...)` success as delivered | Misreports delivery status | Use `SUBMITTED`, track delivery separately |
| Ignoring `MailAuthenticationException` | Authentication errors go unhandled | Catch full `MailException` taxonomy |
| Not bounding SMTP timeouts | Workers hang, queue backs up | Configure connect/read/write timeouts |
| Using `Message-ID` to prevent duplicates | May still receive two emails | Use application/provider-level idempotency |
| Not persisting notification state | Cannot retry/reconcile after restart | Durable outbox and state |
| Relying solely on exception text | Brittle classification across provider messages | Prefer type, stage, and reply code |
| Ignoring multiple recipients | May resend to people who already received it | Analyze `SendFailedException`/partial send |

## 33. Practice Scenarios

### Scenario A: Three Messages, One Fails

The application calls `mailSender.send(m1, m2, m3)`. The exception contains `failedMessages` with key `m2`.

**How to handle:** correlate `m2` to its notification ID; inspect `m2`'s cause and classify it. Do not automatically retry `m1` and `m3`. For the remaining messages, rely on send evidence and system-recorded state to determine submitted/unknown.

### Scenario B: `failedMessages` Is Empty

`MailSendException` occurs, but the map has no entries.

**How to handle:** do not declare all messages successful. Check `getCause()`, general message, failure stage, and provider logs. Reconciliation for the entire operation may be needed.

### Scenario C: SMTP Rejects One Recipient in a Multi-Recipient Message

A `MimeMessage` has three recipients; `SendFailedException` reports one invalid address and two others in valid groups.

**How to handle:** read address groups and partial send policies. Do not equate one failed message with three failed recipients; do not resend to everyone if some were already accepted by the server.

### Scenario D: SMTP Connection Timeout Before Connect

The application has not yet established an SMTP connection.

**How to handle:** check DNS, host, port, firewall, TLS mode, and timeouts. If certain the message was not sent over this connection, queue the notification for retry with backoff.

### Scenario E: Server Received DATA but Reply Was Lost

The worker receives a timeout exception after transmitting the message.

**How to handle:** record `UNKNOWN`, check provider logs/events, and avoid auto-retrying without assessing duplicate risk.

### Scenario F: Async Send Followed by Process Restart

A worker catches `MailSendException` and only logs it without saving state. After restarting, there is no record of which notification failed.

**How to handle:** use an outbox/notification table, attempt count, claim, outcome, and durable retry policy.

### Scenario G: SMTP Credentials Revoked

The application keeps retrying mail sends, but every attempt fails authentication.

**How to handle:** classify as `MailAuthenticationException`, pause retries, and fix credentials/permissions per provider policy. Do not increase concurrency to "try faster".

### Scenario H: Dashboard Reports 100 Failed Messages

A shared connection error occurs on a batch of 100 messages; the map has 100 entries with the same cause.

**How to handle:** distinguish 100 affected notifications from one connection incident. Count exception classes/root causes separately to avoid mistakenly thinking 100 independent failures happened.

## 34. Rules to Remember

1. **`MailSendException` is a Spring Mail send/transport error; it does not mean every message was not received.**
2. **`getFailedMessages()` returns `Map<Object, Exception>` keyed by message object**, not recipient or notification ID.
3. **`getMessageExceptions()` provides per-message causes**, though the map is better when correlation is needed.
4. **A failed message differs from a failed recipient.** With multiple recipients, inspect `SendFailedException` and SMTP details.
5. **An empty map does not mean the batch succeeded.**
6. **A batch can have different per-message outcomes.** Do not retry the entire batch just because of one exception.
7. **SMTP acceptance is not delivery.** A successful sender call only reports observed transport results.
8. **A timeout after DATA can be an ambiguous outcome.** Use `UNKNOWN` and reconciliation when needed.
9. **Classify by exception type, SMTP stage, and reply code**, not based on a single message string.
10. **Persist notification IDs and durable state**, using retry/backoff and an outbox for business emails.
11. **Protect data in logs.** Do not print full `MimeMessage`, Bcc, tokens, or SMTP credentials.
12. **Use an SMTP test server and fault injection** to test error branches, including empty maps and partial batches.

## 35. Conclusion

`MailSendException` is a critical signal when Spring Framework Mail cannot complete a send operation per observed transport results. For batches, `getFailedMessages()` helps identify **reported failed message objects** and their causes; `getMessageExceptions()` helps inspect component errors. However, a single exception alone cannot speak for the entire SMTP history, per-recipient status, or final delivery outcome.

The safe approach is to **correlate each message with a notification ID before sending**, read exceptions across Spring/Jakarta Mail/SMTP layers, pinpoint the failure stage, distinguish definite errors from ambiguous outcomes, and then persist `SUBMITTED`, `RETRY_WAIT`, `FAILED`, or `UNKNOWN` based on evidence. For async or multi-worker applications, combine a transactional outbox, atomic claims, and bounded retries so work is not lost across restarts without accidentally resending the entire batch. As a result, the system both diagnoses `MailSendException` more accurately and reduces duplicate sends and misreported email statuses.
