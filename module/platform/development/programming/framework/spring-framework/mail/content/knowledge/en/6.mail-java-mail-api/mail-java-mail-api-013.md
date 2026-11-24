# Reading the Root Cause from the Exception Chain in Spring Framework Mail

## 1. Why Does One Email-Sending Failure Have Multiple Exception Layers?

When calling `JavaMailSender.send(...)`, a Spring application may receive an exception with a fairly generic message such as "Failed messages" or "Mail server connection failed". Looking only at the outermost message makes it easy to conclude that **the SMTP server is down**, whereas the direct cause could be:

- Failure to resolve DNS for the SMTP host.
- TCP connection to the SMTP port refused or timed out.
- TLS handshake failure due to certificates or security configuration.
- Server rejecting SMTP authentication.
- Sender address not permitted by the current account.
- One or more recipients rejected at `RCPT TO`.
- MIME data, attachments, or content sources unreadable.
- Server returning an error after receiving `DATA`.

With **Spring Framework Mail**, a failure can traverse multiple layers:

~~~mermaid
flowchart TD
    A["Business service"] --> B["JavaMailSender"]
    B --> C["Spring MailException"]
    C --> D["Jakarta Mail MessagingException"]
    D --> E["SMTP / TLS / I-O exception"]
    E --> F["Specific cause: SMTP code, DNS, socket, certificate..."]
~~~

This diagram illustrates layers **that may appear**, not a guarantee that every failure contains all of them. For instance, MIME construction errors can happen before touching SMTP, while auth failures may be surfaced by Spring directly as `MailAuthenticationException`.

**An exception chain** is a sequence of exceptions representing the same incident at different abstraction levels. To diagnose accurately, preserve two kinds of information:

1. **Outer-layer context**: which send action failed, what `JavaMailSender` reported, and whether preparation or sending failed.
2. **Inner-layer technical cause**: network error, TLS, authentication, SMTP reply code, recipient, or MIME content.

> **Principle:** Find the meaningful deep cause while preserving outer exception context. The "last exception" does not necessarily explain the state of every recipient or every message.

## 2. Java Cause Chain and Jakarta Mail Next Exception

Java supports standard exception chaining via `Throwable.getCause()`: one exception can wrap another cause, which in turn wraps a deeper exception.

Illustrative example:

~~~text
org.springframework.mail.MailSendException
  └── jakarta.mail.MessagingException
        └── java.net.SocketTimeoutException
              "Read timed out"
~~~

However, **Jakarta Mail also provides `MessagingException.getNextException()`**. This is Jakarta Mail's own exception link, which may hold details missed by tools that only traverse `getCause()` along a single chain.

~~~text
MessagingException
  ├── getCause()          -> Throwable cause (if present)
  └── getNextException()  -> Next exception in Jakarta Mail's mechanism
~~~

In some implementations, `getCause()` and `getNextException()` point to the same object, or to related objects. An inspector should therefore **traverse both edges, deduplicate by exception identity, and prevent cycles**.

Moreover, `MailSendException` can carry **multiple errors tied to multiple messages**, rather than a single linear cause. During batch sends, the failure state is better modeled as an **exception graph**:

~~~text
MailSendException
  ├── getCause() -> overall error (if present)
  ├── getMessageExceptions() -> per-message errors
  └── getFailedMessages() -> map Message => Exception
                               ├── message A => SendFailedException
                               └── message B => MessagingException
~~~

Calling only `getRootCause()` or `getMostSpecificCause()` on a Spring exception can help along the **`getCause()` chain**, yet does not replace checking `getNextException()` and message-level branches.

## 3. Exception Types to Recognize

### 3.1. Spring Mail-Layer Exceptions

`org.springframework.mail.MailException` is Spring Mail's runtime base exception. Common subclasses:

| Exception type | Typical meaning | What to inspect next |
|---|---|---|
| `MailAuthenticationException` | Authentication with the mail system failed | Credentials, SMTP AUTH method, provider policy, TLS |
| `MailSendException` | Failed to send one or more messages | Cause, per-message errors, SMTP protocol, I/O, recipients |
| `MailParseException` | Unable to parse/construct mail content on a processing path | MIME, addresses, charset, inner error details |
| `MailPreparationException` | Message preparation callback failed | Code inside `MimeMessagePreparator`, body/attachment data |
| `MailException` | General Spring mail-sending error group | Concrete subclass and cause |

Do not assume **every** socket error is wrapped by Spring in the exact same class: the call path and implementation determine the final exception type.

### 3.2. Jakarta Mail-Layer Exceptions

| Type | Meaning |
|---|---|
| `jakarta.mail.MessagingException` | General Jakarta Mail error; supports `getNextException()` |
| `jakarta.mail.AuthenticationFailedException` | Mail authentication failure |
| `jakarta.mail.SendFailedException` | May carry valid/invalid address groups during sending |
| `jakarta.mail.internet.AddressException` | Address parsing or syntax validation failure |
| `jakarta.mail.internet.ParseException` and MIME errors | Structural, header, or message data errors |

`SendFailedException` offers particularly useful methods:

- `getInvalidAddresses()`: addresses considered invalid/unaccepted during the send attempt.
- `getValidSentAddresses()`: addresses recorded by the transport as successfully sent per its tracked state.
- `getValidUnsentAddresses()`: valid addresses not yet successfully sent in this attempt.

Any of these arrays may be `null`. "Valid sent" is a **transport-layer** result, not proof that the recipient opened the email or that it landed in the Inbox.

### 3.3. Provider and Network-Layer Exceptions

| Class / error group | Indicator |
|---|---|
| `UnknownHostException` | Failed to resolve SMTP hostname |
| `ConnectException` | Failed to establish TCP connection, e.g., refused |
| `SocketTimeoutException` | Connection or network read timed out |
| `SSLHandshakeException` | TLS handshake failed |
| `CertificateException` or certificate errors | Typically appears inside a TLS error's cause |
| SMTP exception with reply code | Server rejected a specific SMTP command |
| I/O / file / stream errors | Unable to access or read attachment data |

Package names of concrete SMTP exceptions depend on the Jakarta Mail implementation: you may see `SMTPAddressFailedException` or `SMTPSendFailedException` from **Eclipse Angus Mail** (`org.eclipse.angus.mail.smtp`), or from implementations using older package names. Never hardcode package/provider assumptions if your application must work across implementations.

Reply codes like `550 5.1.1`, `535 5.7.8`, or `554 5.7.1` are **signals returned by the SMTP server**. Combine them with the active command and provider policy; one error code does not always map to a single cause.

## 4. Steps for Tracing an Exception

Suppose a service builds a message with `MimeMessageHelper` and calls `mailSender.send(message)`. Instead of stopping at the message:

~~~text
MailSendException: Failed messages
~~~

trace step by step:

1. **Concrete Spring error type**: `MailAuthenticationException` or `MailSendException`?
2. **Cause chain**: does `getCause()` lead to `MessagingException`, a network error, or a TLS error?
3. **Jakarta Mail chain**: for every `MessagingException`, what else does `getNextException()` contain?
4. **Message-level failures**: if `MailSendException`, how many errors do `getFailedMessages()` and `getMessageExceptions()` hold?
5. **Recipient-level failures**: what does `SendFailedException` report for `invalid`, `validSent`, and `validUnsent`?
6. **SMTP stage/reply**: which command did the server reject, and with what code?
7. **State prior to failure**: connection never opened, authenticated, recipients accepted, or DATA already received?

Example of two identical outermost exceptions with completely different remedies:

~~~text
Case A:
MailSendException
  -> MessagingException "Could not connect to SMTP host"
     -> ConnectException "Connection refused"

Case B:
MailSendException
  -> SendFailedException
     -> RCPT TO rejected, SMTP reply 550 5.1.1
~~~

Case A points to checking endpoint, port, firewall, and listening services. Case B requires checking the recipient address and acceptance policies. Tweaking HTML or charsets solves neither.

## 5. Java Utility to Traverse the Exception Graph

The code below collects **exception types, message counts, and recipient counts** without printing raw exception messages that might contain email addresses, SMTP banners, or message content. It traverses causes, Jakarta Mail next exceptions, suppressed exceptions, and Spring's per-message errors.

~~~java
package com.example.mail.diagnostics;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;
import org.springframework.mail.MailSendException;

public final class MailFailureInspector {

    private static final int MAX_NODES = 64;

    private MailFailureInspector() {
    }

    public static List<String> summarize(Throwable failure) {
        if (failure == null) {
            return List.of();
        }

        List<String> details = new ArrayList<>();
        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>());
        pending.addLast(failure);

        while (!pending.isEmpty() && seen.size() < MAX_NODES) {
            Throwable current = pending.removeFirst();
            if (!seen.add(current)) {
                continue;
            }

            details.add("exception=" + current.getClass().getName());

            if (current instanceof MailSendException sendFailure) {
                details.add("failedMessages="
                        + sendFailure.getFailedMessages().size());
                for (Exception nested : sendFailure.getMessageExceptions()) {
                    enqueue(pending, nested);
                }
                for (Exception nested :
                        sendFailure.getFailedMessages().values()) {
                    enqueue(pending, nested);
                }
            }

            if (current instanceof SendFailedException addressFailure) {
                details.add("invalidRecipients="
                        + count(addressFailure.getInvalidAddresses()));
                details.add("validSentRecipients="
                        + count(addressFailure.getValidSentAddresses()));
                details.add("validUnsentRecipients="
                        + count(addressFailure.getValidUnsentAddresses()));
            }

            if (current instanceof MessagingException messagingFailure) {
                enqueue(pending, messagingFailure.getNextException());
            }

            enqueue(pending, current.getCause());
            for (Throwable suppressed : current.getSuppressed()) {
                enqueue(pending, suppressed);
            }
        }

        if (!pending.isEmpty()) {
            details.add("exceptionGraphTruncated=true");
        }
        return details;
    }

    private static void enqueue(Deque<Throwable> pending,
                                Throwable failure) {
        if (failure != null) {
            pending.addLast(failure);
        }
    }

    private static int count(Address[] addresses) {
        return addresses == null ? 0 : addresses.length;
    }
}
~~~

Usage example:

~~~java
try {
    mailSender.send(message);
} catch (org.springframework.mail.MailException ex) {
    List<String> summary = MailFailureInspector.summarize(ex);
    summary.forEach(System.out::println); // Illustrative; replace with an appropriate logger.
    throw ex;
}
~~~

**Why are multiple traversal edges needed?**

- `getCause()` is Java's standard mechanism.
- `getNextException()` is Jakarta Mail's mechanism.
- `getMessageExceptions()` and `getFailedMessages()` reflect **multi-message** errors, not just one cause.
- `getSuppressed()` holds exceptions attached while closing resources or running secondary steps.
- `IdentityHashMap` ensures **identical exception instances** are detected to avoid duplicates or reference cycles.
- `MAX_NODES` caps diagnostic output if an exception source has an unusual structure.

The snippet omits `Throwable.getMessage()` directly because library error messages may expose sensitive data. In authorized environments, you can add fields like **SMTP reply code, command, request ID, and failure stage** after filtering/masking sensitive values. The generated list is **a graph traversal result**, not a guarantee that the final element is always the sole root cause.

## 6. MailSendException: Reading Per-Message Failures

When sending:

~~~java
mailSender.send(firstMessage, secondMessage, thirdMessage);
~~~

the server or client may fail on one message in the batch. `MailSendException` gives access to per-message failure details:

~~~java
catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        Object messageObject = entry.getKey();
        Exception reason = entry.getValue();

        // Illustrative; do not log messageObject/toString() in production.
        System.out.println("Message type: "
                + messageObject.getClass().getName());
        System.out.println("Failure type: "
                + reason.getClass().getName());
    }
}
~~~

`getFailedMessages()` returns a map from **the message object** to **the corresponding exception**. Keys can contain full headers, bodies, and attachments, so never serialize or `toString()` those keys into logs. `getMessageExceptions()` retrieves related exceptions; both APIs can reference the same exception instance, so deduplicate when aggregating.

Do not assume every email in the batch failed whenever a `MailSendException` occurs: some messages may already have been accepted by the server. Conversely, a message missing from the failure list is still no proof that the final recipient read it.

### 6.1. SendFailedException and the Three Address Groups

Suppose you send to:

~~~text
To:  lan@example.net
Cc:  team@example.net
Bcc: quan@example.org
~~~

The transport may accept some recipients and reject others. `SendFailedException` provides these groups:

~~~java
failed.getInvalidAddresses();
failed.getValidSentAddresses();
failed.getValidUnsentAddresses();
~~~

A single message can have accepted recipients and server-rejected recipients. Depending on transport policy and configuration, the message may have been sent to valid addresses, sent to nobody, or have some addresses needing retries.

**Base retries on actual outcomes**, avoiding resending to people already accepted by the system. "Valid sent" reflects transport-reported results, not proof that the email landed in the Inbox.

## 7. Tracing Failures by SMTP Stage

To send an email over SMTP, the client typically opens TCP, greets with `EHLO`, optionally runs `STARTTLS` and `AUTH`, and then sends `MAIL FROM`, `RCPT TO`, and `DATA`. **The command or stage immediately preceding the error** determines how to interpret the exception chain.

| Stage | Exception indicators | Verification direction |
|---|---|---|
| Opening TCP connection | `UnknownHostException`, `ConnectException`, `SocketTimeoutException` | Hostname, DNS, port, firewall, routing, server |
| STARTTLS / TLS | `SSLHandshakeException`, certificate-related causes | TLS port/mode, trust chain, hostname, certificates |
| SMTP AUTH | `AuthenticationFailedException`, `MailAuthenticationException`, `535` or other replies | Account, AUTH method, account permissions, provider policy |
| `MAIL FROM` | Reply code rejecting sender address | Reverse-path, account/domain send permissions |
| `RCPT TO` | `SendFailedException`, per-recipient SMTP reply | Rejected recipient, relay policy, valid/invalid recipients |
| `DATA` and end-of-DATA | Transport error, MIME/stream failure, message-rejection reply code | Size, content, attachment data, post-DATA outcome |
| After server acceptance | Bounce/DSN or later provider status | Delivery status, not just `send(...)` exceptions |

Example:

~~~text
MailSendException
  └── MessagingException
        └── SSLHandshakeException
              └── CertificateException
~~~

points to checking **TLS/trust store/certificates**, not editing HTML or removing attachments. Yet some errors happen when calling `send(...)` because `MimeMessage` data has not been fully serialized yet; always inspect the specific stack trace/cause rather than guessing from the outermost class name.

### 7.1. SMTP 4xx and 5xx Codes

In SMTP, reply codes:

- **`4xx`** denote temporary errors; retrying later per policy may be considered.
- **`5xx`** denote permanent rejection in the context of the current command; typically require fixing addresses, permissions, or configuration.

| Illustrative reply code | Common meaning | Handling notes |
|---|---|---|
| `421` | Service unavailable / closing channel | May be transient |
| `450` | Mailbox/recipient temporarily unavailable | Check retry policy |
| `451` | Temporary local server error | Retry with backoff |
| `535` | SMTP authentication failed on many servers | Inspect AUTH and specific reply text |
| `550` | Address or action rejected | Does not always mean nonexistent mailbox |
| `552` | May relate to storage/size limits | Check reply text and server limits |
| `554` | Content or transaction rejected for various reasons | Inspect enhanced status code and policy |

Enhanced codes such as `5.1.1` or `5.7.1` help narrow down the issue, yet **do not replace reading the command, reply text, and provider configuration**. The same `550` can represent either a bad mailbox or a relay/policy rejection.

### 7.2. When a Timeout Does Not Prove the Email Failed

Suppose the session reaches:

~~~text
C: DATA
S: 354 Continue
C: [Headers, blank line, body/MIME]
C: .
   [Connection drops before client receives final reply]
~~~

The client does not know whether the server accepted and queued the message. If the system retries unconditionally, **it risks creating duplicate emails**.

Hence, distinguish timeouts when:

1. **Opening TCP connection**: no basis to believe the server received an SMTP transaction.
2. **Waiting on EHLO/AUTH**: normally no mail transaction completed.
3. **Sending RCPT TO**: determine which recipients the server accepted.
4. **Waiting on final DATA reply**: content acceptance may be **indeterminate**.

`SocketTimeoutException` is a concrete technical cause, yet the retry decision must depend on **the stage**. For important business emails, use request IDs, application-level deduplication, bounded retries, and provider reconciliation where supported.

## 8. Analyzing Common Scenarios

### 8.1. SMTP Authentication Failure

An exception pattern might look like:

~~~text
MailAuthenticationException: Authentication failed
  └── AuthenticationFailedException: 535 ...
~~~

Reading the chain:

- Failure occurred at **the authentication step**; normally never reached `MAIL FROM`.
- Check how the provider expects login: username/password, application password, OAuth2, or a custom mechanism.
- Check whether SMTP access was disabled on the account, blocked by policy, or missing TLS.
- Never put passwords/tokens into logs to "prove" configuration is right.

**`535` does not automatically prove a wrong password.** The provider can reject due to permissions, AUTH method, or account policy.

### 8.2. One Recipient Address Rejected

A failure branch may look like:

~~~text
MailSendException
  └── SendFailedException
        ├── validSentAddresses: lan@example.net
        └── invalidAddresses: old-account@example.net
             └── SMTP RCPT TO reply 550 5.1.1
~~~

In this scenario:

- The error concerns **a specific recipient**, not an HTML parsing error.
- Inspect the server reply and rejected address.
- Do not treat all recipients as unsent.
- Before retrying, distinguish which addresses the transport marked sent vs. unsent.

Addresses here are dummy data. In production, log request IDs and recipient counts; avoid exposing personal emails to unnecessary log systems.

### 8.3. Unable to Connect to the SMTP Server

Example:

~~~text
MailSendException
  └── MessagingException: Could not connect to SMTP host
        └── ConnectException: Connection refused
~~~

Investigation path:

1. Check the configured host, port, DNS, and actual endpoint.
2. Verify the SMTP service is listening on that port.
3. Check network policies, firewalls, routing, or proxies in the application environment.
4. If timed out, inspect timeout type and stage before deciding on retries.

Changing `MimeMessageHelper.setText(...)` will never fix a refused TCP connection.

### 8.4. TLS Handshake Failure

Example:

~~~text
MailSendException
  └── MessagingException
        └── SSLHandshakeException
              └── trust chain validation error
~~~

Investigation path:

- Distinguish **STARTTLS on port 587** from **implicit TLS on port 465** per provider.
- Check certificate chain, trust store, hostname verification, and certificate expiration.
- Never disable certificate or hostname verification just to make sending pass.

Occasionally providers rotate TLS policies; when the exception points to certificates/trust, prioritize that diagnostic path.

### 8.5. Attachments Causing Sending Failure

Code may build a `MimeMessage` with `MimeMessageHelper.addAttachment(...)`, yet the file data source is unreadable, deleted, oversized, or readable only once. Failures can occur during:

- **MIME part preparation**: e.g., invalid data or filename.
- **Message serialization**: body part requires reopening the stream.
- **Transport reading and transmitting content**: file source errors or exceeds server policy.

Do not assume broken attachments **always** throw before `send(...)`. Trace stack frames, causes, data sources, and the actual stage. When fixing, use a `Resource` with a suitable readable source, bound sizes, and verify access permissions. Never log internal file paths or sensitive attachment contents.

### 8.6. Message Sends Successfully Yet HTML Renders Wrong

If `send(...)` returns normally yet the recipient sees raw HTML tags, broken CID images, or duplicated bodies, **there may be no exception chain at all**. This usually requires checking the MIME tree and email client capabilities:

- HTML body tagged as `text/plain` instead of `text/html`.
- Two body versions not placed inside a proper `multipart/alternative`.
- `cid:...` in HTML not matching the inline image's `Content-ID`.
- Charset or `Content-Transfer-Encoding` mismatched against actual bytes.

In that case, inspect the serialized `MimeMessage` and the recipient's raw `.eml`. Not every email issue is a transport error.

## 9. Preserving Causes When Wrapping Errors at the Business Layer

A Spring service can classify errors at message-creation and message-sending boundaries:

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportNotificationService {

    private final JavaMailSender mailSender;

    public ReportNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String reportText) {
        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, false, "UTF-8");
            helper.setFrom("reports@example.com");
            helper.setTo(recipient);
            helper.setSubject("Weekly report");
            helper.setText(reportText, false);
        } catch (MessagingException ex) {
            throw new MailRequestException(
                    "Unable to prepare MIME message", ex);
        }

        try {
            mailSender.send(message);
        } catch (MailAuthenticationException ex) {
            throw new MailRequestException(
                    "SMTP authentication failed", ex);
        } catch (MailSendException ex) {
            throw new MailRequestException(
                    "SMTP submission failed", ex);
        } catch (MailException ex) {
            throw new MailRequestException(
                    "Mail service failed", ex);
        }
    }

    private static final class MailRequestException
            extends RuntimeException {
        private MailRequestException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

The example highlights two moments:

1. **Creating `MimeMessage`**: `MimeMessageHelper` APIs can throw `MessagingException` (checked). Errors are wrapped while preserving cause.
2. **Sending `MimeMessage`**: `JavaMailSender.send(...)` uses Spring's `MailException` hierarchy. Rewrapping still preserves the full exception for downstream diagnosis.

Splitting error branches like this shows readers where the error originated, though **it is not a retry algorithm yet**. Specifically, after `MailSendException`, inspect which messages/recipients were already accepted by transport before resending.

### 9.1. Do Not Lose the Root Cause

Pattern to avoid:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    throw new IllegalStateException("Unable to send email");
}
~~~

Because the new exception drops the cause, callers lose the diagnostic chain. How to preserve cause:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    throw new IllegalStateException("Unable to send email", ex);
}
~~~

Logging only `ex.getMessage()` can also miss causes, `getNextException()`, and per-message errors. Conversely, dumping full stack traces indiscriminately can expose sensitive data. Pick observability granularity aligned with your environment and access controls.

### 9.2. When Should Stack Traces and SMTP Replies Be Logged?

In authorized development/investigation environments, stack traces pinpoint where control crossed from Spring to Jakarta Mail and the network layer. In production, exception messages or traces may contain SMTP hosts, email addresses, filenames, internal paths, provider messages, or auth-related data.

Information typically sufficient for monitoring:

- Send-request ID and attempt count, never using real subjects or recipients as IDs.
- Spring exception type and deeper exception type.
- Stage such as `CONNECT`, `AUTH`, `MAIL_FROM`, `RCPT_TO`, `DATA` where evidenced.
- Filtered SMTP reply code and enhanced status code.
- Counts of succeeded, failed, or unknown messages/recipients.
- Retry status, next retry timestamp, and provider verification source if available.

## 10. Structured Email-Error Observability

A diagnostic record might be represented as:

~~~text
mail_request_id = req-2026-00123
attempt = 2
phase = SMTP_RCPT
status = FAILED
spring_exception = MailSendException
mail_exception = SendFailedException
smtp_reply_code = 550
smtp_enhanced_code = 5.1.1
recipient_count = 3
failed_recipient_count = 1
~~~

This is **a log-design example**, not fields automatically emitted by `JavaMailSender`. Never infer exact `phase` from a vague message line; phase must come from exception evidence, protocol traces, or proper telemetry.

| Error group | How apps/operations usually handle |
|---|---|
| Auth / config rejected | Notify SMTP integration owners |
| DNS / connect / pre-transaction timeout | Inspect infrastructure and optionally apply bounded retries |
| TLS / certificate | Fix secure connectivity and trust; never skip verification |
| Recipient permanently rejected | Check address, send permissions, or policies |
| SMTP 4xx | Retry per provider backoff/limits |
| Unknown result after DATA | Reconcile with provider or use duplicate-prevention mechanics |
| MIME / attachment error | Check data sources, encoding, and message structure |

When using metrics, classify with low-cardinality labels like `auth`, `dns`, `network_timeout`, `tls`, `recipient_rejected`, `content`, `unknown`. Never place raw exception messages, email addresses, or subjects into metric labels: that leaks data and causes cardinality explosions.

## 11. Technical Cause and Business Decision Are Two Separate Layers

A `SocketTimeoutException` tells us a network operation waited too long. Yet the retry decision requires extra context:

- A timeout **before connecting** differs from a timeout **after transmitting DATA**.
- One `SendFailedException` can include both sent recipients and unsent recipients.
- `250` after DATA only confirms the server accepted it for processing; bounce notices can arrive later.
- An email rendering incorrectly may produce zero exceptions in `send(...)`.

Therefore, "found the root cause" means identifying **the concrete technical failure and its place in the flow**, rather than automatically deciding whom to retry, when to retry, or asserting that nobody received it.

## 12. Common Confusions

**"Is calling getRootCause() alone enough?"**  
Not necessarily. It helps with `getCause()`, yet Jakarta Mail also has `getNextException()`, and `MailSendException` can hold multiple per-message errors. Inspect all relevant branches.

**"Can getCause() and getNextException() return the same exception?"**  
Yes, depending on implementation. When traversing, maintain a visited set to avoid double counting or cycles.

**"Does MailAuthenticationException definitely mean a wrong password?"**  
No. It indicates authentication failed. Causes can include credentials, account policies, AUTH methods, or provider security requirements.

**"Does MailSendException mean no recipient was sent to?"**  
No. Sending multiple messages or one message to multiple recipients can fail partially. Inspect exception data tied to each message/recipient.

**"Is SocketTimeoutException a temporary error that can always be retried immediately?"**  
Do not decide from the exception name alone. If the timeout happened after DATA, message status may be indeterminate and retrying risks duplicate delivery.

**"Does send() throwing no exception mean the email landed in the Inbox?"**  
No. The SMTP server may only have accepted the email for forwarding; delivery and reading are separate downstream steps.

**"Is just logging the raw stack trace enough?"**  
Stack traces aid investigation, yet do not replace inspecting `getNextException()`/message-level failures and must be access-controlled with sensitive data masked.

## 13. Example Conclusions Drawn from Exception Chains

Suppose collected data shows:

~~~text
Spring exception: MailSendException
Jakarta exception: SendFailedException
SMTP detail: RCPT TO rejected
SMTP reply: 550 5.1.1
Valid-sent recipients: 2
Invalid recipients: 1
~~~

Appropriate technical conclusion:

> The transport reported one recipient rejected at the `RCPT TO` step while two other recipients were in the valid-sent group. The issue relates to recipient address or policy, not HTML formatting. Reconcile server replies and per-recipient state; when retrying, avoid sending duplicates to recipients already recorded as sent.

For the scenario:

~~~text
Spring exception: MailSendException
Jakarta exception: MessagingException
Java cause: SSLHandshakeException
Detail: certificate path validation failed
~~~

the conclusion differs:

> The TLS handshake failed before the mail transaction completed. Check TLS port/mode settings, trust store, certificate chain, and SMTP server hostname. There is no evidence the error stems from `MimeMessage` content.

Thoroughly reading **`MailException` → `MessagingException` → `getCause()`/`getNextException()` → SMTP or I/O errors**, while inspecting per-message and per-recipient failure branches, enables pinpointing true root causes in Spring Framework Mail. Preserving causes when wrapping errors, recording the stage, and interpreting success strictly up to what SMTP replies actually prove form the foundation for effective email troubleshooting.
