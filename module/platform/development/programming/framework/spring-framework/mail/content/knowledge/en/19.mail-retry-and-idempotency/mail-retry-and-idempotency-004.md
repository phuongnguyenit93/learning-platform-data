# Classifying Exceptions for Retry Policies

## 1. Why Must Errors Be Classified Before Retrying an Email?

In an application using **Spring Framework Mail**, calling **JavaMailSender.send(...)** can fail for many very different reasons: missing required fields when building the email, wrong SMTP account, invalid recipient, temporarily overloaded server, dropped connection, or the application failing to receive the final response from the SMTP server.

If every exception is handled by immediately retrying, the application can:

- Repeatedly send an email that will never be valid.
- Increase load on an already overloaded SMTP server.
- Stall the queue due to a configuration error that cannot self-heal.
- Send duplicate emails after a timeout even though the server already received the message.
- Resend to recipients who already succeeded in a batch with partial outcomes.
- Report "send failed" or "delivered successfully" when there is actually insufficient information to conclude either.

Therefore, before retrying, you must **classify the error based on exception type, root cause, SMTP response, the stage at which the failure occurred, and the known state of the send attempt**.

The goal of this lesson is to design an evidence-based retry policy rather than a simplistic "catch all exceptions and resend" rule.

The processing flow should look like this:

~~~text
Build content + MimeMessage
            |
            v
     JavaMailSender.send(...)
            |
      +-----+------+
      |            |
      v            v
   Success     Exception
      |            |
      v            v
  SUBMITTED    Gather context
                   |
                   v
             Classify error
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
   Retryable   Non-retryable  Unknown outcome
       |           |           |
       v           v           v
  RETRY_WAIT   FAILED/ALERT   UNKNOWN/RECONCILE
~~~

**Retrying is only one of the possible actions.** A sound system also knows when to stop, when data or configuration must be fixed, and when reconciliation is required before deciding to resend.

## 2. Distinguishing Send Errors From Recipient Delivery Status

Before classifying exceptions, understand which step in an email's journey the send call represents:

~~~text
Application
  |
  v
Build MIME
  |
  v
SMTP submission
  |
  v
SMTP server / Email provider accepts
  |
  v
Relay / Queue / Recipient MX
  |
  v
Mailbox / Spam / Quarantine / Bounce
~~~

A successful **JavaMailSender.send(...)** call generally means the email was successfully submitted to the mail transport or first-hop SMTP server. It **does not guarantee the email reached the Inbox, arrived for all recipients, or was opened**.

Conversely, an exception from `send` does not always prove the SMTP server never received the message. For example, the connection may have dropped after the server accepted `DATA` but before the application received the final reply.

Therefore, separate these two status groups:

| Group | Examples | Meaning |
|---|---|---|
| **Submission status** | `PENDING`, `SUBMITTED`, `RETRY_WAIT`, `UNKNOWN`, `FAILED` | What the application knows about submitting the email |
| **Delivery status** | `DELIVERED`, `BOUNCED`, `DEFERRED`, `COMPLAINED` | Delivery outcome reported back by the provider or receiving system |

Never set **DELIVERED** merely because no exception was thrown. If provider bounce webhooks or delivery events exist, process them as a separate result stream.

## 3. Three Core Error Categories

A practical classification divides errors into three groups:

| Group | Nature | Default action |
|---|---|---|
| **Transient / Retryable** | Error likely to self-recover over time | Retry with backoff, jitter, and limits |
| **Permanent / Non-retryable** | Same input/config will keep failing | Stop, fix root cause, alert when needed |
| **Ambiguous / Unknown outcome** | Unknown whether the server received the email | Reconcile or handle per duplicate-prevention policy |

Examples:

**Transient:**

- SMTP returns **421**, **450**, **451**, or **452** in an appropriate context.
- Server is temporarily overloaded or enforcing rate limits.
- Unable to connect to the SMTP server briefly and confirmed submission has not started.
- Temporary DNS error, when confirmed to be transient.

**Permanent or requiring intervention:**

- Email address has invalid syntax.
- SMTP authentication fails due to wrong credentials or permissions.
- MIME/template cannot be rendered due to bad data or configuration.
- SMTP permanently rejects the recipient with a `5xx` code.
- Message exceeds a fixed size limit that waiting will not resolve.

**Ambiguous:**

- Timeout while waiting for the final reply after the SMTP `DATA` command.
- Connection severed after the application transmitted the message without knowing the result.
- Provider accepted the request, but the application lost the confirmation response.

Classification also depends on **the phase in which the error occurred**. The exact same `SocketTimeoutException` may be retryable if it happened before submission, yet ambiguous if it occurred after transmitting the message body.

## 4. Stages of an SMTP Send Attempt

To classify accurately, visualize the send progression phase by phase:

~~~text
1. PREPARE
   Build subject, recipient, HTML/MIME, attachment
             |
             v
2. CONNECT
   TCP connection, DNS, timeout, proxy
             |
             v
3. SECURE / AUTHENTICATE
   TLS, STARTTLS, credentials
             |
             v
4. ENVELOPE
   MAIL FROM, RCPT TO
             |
             v
5. DATA
   Send MIME content
             |
             v
6. WAIT FINAL REPLY
   Wait for SMTP server to confirm acceptance or reject DATA
             |
             v
7. SUBMITTED
   Server replied accepting at this stage
~~~

| Phase | Typical errors | Initial assessment |
|---|---|---|
| `PREPARE` | Missing template data, invalid address syntax, unreadable attachment | Usually do not retry blindly |
| `CONNECT` | Connection refused, connect timeout | Usually retryable if `DATA` not yet sent |
| `TLS/AUTH` | Authentication failed, certificate error | Usually needs config fix; brief connection errors assessed separately |
| `MAIL FROM` / `RCPT TO` | SMTP `4xx` or `5xx` | Inspect server reply, per recipient |
| `DATA` before clear reply | Mid-stream connection failure | May be uncertain, depending on transmission/receipt evidence |
| `WAIT FINAL REPLY` | Read timeout, connection reset | Outcome may be unknown |
| After receiving success reply | Error saving application state | Never resend solely because DB write failed |

Not every SMTP implementation exposes detailed per-phase information through Spring `MailException`. When evidence is insufficient, keep the state as **UNKNOWN** instead of guessing that the error definitely happened before the server received the message.

## 5. Spring Framework Mail Exception Hierarchy

Spring Mail provides the **MailException** abstraction and the following common exceptions:

| Exception | General meaning | Recommended policy |
|---|---|---|
| **MailAuthenticationException** | SMTP authentication failed | Do not continuously retry with the same credentials; alert and investigate |
| **MailParseException** | Error parsing or preparing mail content | Stop, fix input/template/MIME |
| **MailPreparationException** | Error preparing the message, e.g., preparator callback | Stop or classify the underlying cause |
| **MailSendException** | Error while sending one or more messages | Must inspect cause, SMTP reply, and per-message outcomes |
| **MailException** (base) | Base exception of the Spring Mail layer | Insufficient information to retry by default |

The exception class name tells you **which layer detected the error**, but it is not enough to determine transience in every case.

### MailAuthenticationException

Example where the server rejects credentials:

~~~text
SMTP authentication failed
  -> MailAuthenticationException
  -> wrong credentials / account locked / unsupported auth mechanism
~~~

With the same username/password and configuration, retrying a few seconds later usually will not solve it. Instead:

- Check credentials and the authentication mechanism required by the provider.
- Check sending permissions, account status, and application policies.
- Alert operations or move notifications to a state waiting for configuration repair.
- Only replay after the root cause is fixed or there is evidence of a temporary provider outage.

### MailParseException and MailPreparationException

These errors typically involve data or message construction:

- Invalid address.
- Malformed headers or MIME data.
- Template rendering failure.
- A **MimeMessagePreparator** throwing `MessagingException`.

If the data does not change, retrying will usually reproduce the same error. Still, inspect the cause: if preparation failed because a remote attachment source was temporarily unreachable, the policy may differ from a template missing a required variable.

### MailSendException

This is the case that **cannot be classified by class alone**. It can wrap connection errors, SMTP replies, per-message send failures, or uncertain-outcome scenarios.

One `MailSendException` can carry details for multiple messages in a batch. Never automatically retry the whole batch without identifying which parts failed.

## 6. Underlying Jakarta Mail and Network Exceptions

Spring Mail uses Jakarta Mail to interact with SMTP. Root causes can originate from multiple layers:

| Layer | Example | Relevance to retry evaluation |
|---|---|---|
| Jakarta Mail | **AuthenticationFailedException** | Usually do not retry with the same configuration |
| Jakarta Mail | **SendFailedException** | May involve rejected recipients or partial delivery |
| Jakarta Mail | **MessagingException** | General error; inspect detailed cause |
| Java networking | **ConnectException** | May retry if there is no sign the message was sent |
| Java networking | **SocketTimeoutException** | Must know which phase it occurred in |
| Java networking | **UnknownHostException** | Check DNS/hostname; do not assume transient from class alone |
| TLS/security | **SSLHandshakeException** | Could be bad cert/config or temporary outage; usually needs investigation |
| Data source | **IOException** | Could be missing file, bad read permissions, or remote timeout |

**MessagingException** can hold a chain of related exceptions via **getNextException()** in addition to the standard Java cause chain. For complete diagnostics, your cause collector should handle both mechanisms and guard against cycles.

When using a specific SMTP provider, additional exceptions may expose the SMTP reply code and recipient addresses, such as SMTP classes in a Jakarta Mail implementation. Those are provider-specific details; do not assume every implementation shares the same classes or getters.

### Do Not Classify by Matching Strings in Exception Messages

Example of what not to do:

~~~java
if (ex.getMessage().contains("timeout")) {
    retry();
}
~~~

Problems:

- Messages can vary across library versions.
- Messages can be localized or contain server-supplied details.
- The string `"timeout"` does not indicate whether it occurred before or after `DATA`.
- Messages may contain sensitive data; do not use them for business decisions or log them verbatim.

Prefer **exception types, verified SMTP reply codes, and send context**.

## 7. SMTP 4xx and 5xx Codes

SMTP servers use reply codes to describe the outcome of a command. General rules:

- **4xx:** temporary error; client may retry after waiting, per policy.
- **5xx:** error usually permanent for the current command/request; fix the root cause instead of blind retries.
- **2xx:** corresponding command accepted; specifically, the reply accepting `DATA` indicates submission succeeded at that hop.

Examples:

| SMTP code | Common meaning | Handling approach |
|---|---|---|
| **421** | Service temporarily unavailable, closing connection | Retry with backoff if not yet accepted |
| **450** | Mailbox or action temporarily unavailable | Bounded retry |
| **451** | Temporary processing error | Retry and monitor |
| **452** | Insufficient resources or temporary limit | Retry with appropriate delay |
| **550** | Mailbox unavailable or rejected | Usually stop; inspect recipient/policy |
| **551** | User not local to this server, forwarding may be offered | Do not retry as-is without route adjustment |
| **552** | Exceeded storage or size allocation depending on server | Inspect details; usually requires intervention |
| **553** | Invalid mailbox name | Fix address |
| **554** | Transaction rejected | Analyze policy, content, or server response |

**Do not decide solely from a numeric code while ignoring the command being executed.** For instance, a `5xx` during `RCPT TO` differs from a `5xx` during `AUTH`. With mail gateways, the reply text and SMTP enhanced status code help clarify the reason.

### Enhanced Status Codes

Some SMTP servers return extended codes like:

~~~text
550 5.1.1 User unknown
451 4.7.1 Try again later
552 5.3.4 Message size exceeds fixed maximum message size
~~~

The first three digits indicate the `4xx`/`5xx` group. The **x.y.z** code adds detail. For instance, a fixed size limit error requires reducing attachment size; waiting a few seconds will not help. Enhanced status parsing should follow the provider's contract.

## 8. Connection and DNS: Not All Network Errors Are Equal

Some errors may be retried after confirming email submission had not begun:

- TCP connection refused while the SMTP server is restarting.
- Connect timeout due to transient network congestion.
- Temporary DNS error from the resolver.
- Connection dropped before the SMTP session sent `MAIL FROM`.

However, continuous retries can backfire when:

- The hostname is misconfigured and permanently non-existent.
- The port is wrong or permanently blocked by a firewall.
- DNS records are misconfigured.
- The SMTP server only allowlists a different IP.
- The TLS certificate is untrusted due to a wrong truststore.

Example:

~~~text
ConnectException at CONNECT:
    -> Can retry with backoff

UnknownHostException for smtp.invalid:
    -> Check hostname/DNS before long-term retries

SocketTimeoutException while waiting for final DATA reply:
    -> Unknown whether the server accepted it
~~~

Thus, the system should record **the phase where the error occurred** or the confidence level of that information. If the mail client layer does not provide an exact phase, do not guess from an `IOException` class.

## 9. Authentication and TLS: When Not to Retry

Authentication error example:

~~~java
try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Do not keep resending with the same credentials.
    // Transition to a state requiring config/permission inspection.
    throw ex;
}
~~~

If the SMTP server returns a clear authentication error, check credentials, account permissions, AUTH mechanism, and provider policies. Rapid retries with the same secret can trigger account lockouts or inflate error counts.

With TLS, do not disable certificate validation or weaken security just to make the next send succeed. Instead:

- Verify hostname and certificate.
- Verify truststore and CA chain.
- Verify STARTTLS/SMTPS requirements per provider.
- Check system clock accuracy.
- Separate persistent configuration errors from temporary infrastructure incidents.

There is no single absolute answer for every `SSLHandshakeException`. By default, **not retrying blindly and never bypassing TLS verification** is the safe operational path.

## 10. MIME, Template, and Attachment Preparation Errors

Errors occurring before submission typically require fixing input or content:

| Error | Example | Handling approach |
|---|---|---|
| Template | Missing template key or required variable | Stop, fix renderer/data |
| Address | `AddressException`, invalid recipient syntax | Fix address, do not retry as-is |
| Header | Invalid subject or address | Validate and normalize data |
| Charset | Incorrect content encoding | Fix MIME construction |
| Attachment | Local file does not exist | Check file lifecycle, do not retry blindly |
| Remote attachment | Object storage temporarily timed out | Bounded retry downloading file if source still exists |
| Size | File exceeds provider limit | Reduce file size or send a secure link |

**Preparation errors can have temporary external causes**, but that does not make every `MailPreparationException` retryable.

Same `IOException`, different meanings:

~~~text
NoSuchFileException:
    temporary file was deleted
    -> need to fix resource lifecycle

SocketTimeoutException from object storage:
    source still exists, temporary network error
    -> can retry the file download step
~~~

Do not retry the entire SMTP send if the attachment source could not be read. Re-verify and re-prepare the content before placing the email back into the sending queue.

## 11. Timeouts: Know Whether the Error Happened Before or After DATA

A timeout is a clear example of why **exception class alone is insufficient to decide retries**.

### Timeout at CONNECT

~~~text
Application --X--> SMTP server
             connect timeout

No SMTP session yet or message not yet sent.
~~~

If there is evidence the connection was never established and no email data was submitted, retrying with backoff may be appropriate.

### Timeout While Sending Data

~~~text
Application ---- DATA bytes ----> SMTP server
                     |
                     X connection reset
~~~

Depending on when the connection was severed, the server may have received part or all of the data. Without the final reply to `DATA`, the application may not know whether the message was accepted.

### Timeout While Waiting for the Final DATA Reply

~~~text
Application                      SMTP server
    |                                |
    | ------ DATA / body ---------> |
    | ------ end of DATA ---------> |
    |                                | processes, may enqueue
    | <------- 250 reply ----------- X
    |         connection lost        |
    v
SocketTimeoutException / I/O error
~~~

If the server accepted and queued the message, resending can create a duplicate copy. Therefore, **an error while waiting for the final reply after `DATA` must be treated as an unknown outcome unless there is proof the server rejected it**.

### What If a Clear Rejection Reply Is Received?

If the SMTP server returned a `4xx` or `5xx` reply confirming it rejected the transaction, the situation differs from a lost response. With a clear `4xx` reply, you can retry per policy; with a clear `5xx`, you usually must fix the cause.

Key summary:

| Evidence | Assessment |
|---|---|
| Connection not opened / message not submitted | May retry after temporary error |
| Received `4xx` reply for the deciding step | Conditionally retryable |
| Received `5xx` reply for the deciding step | Usually non-retryable |
| Received confirmation accepting `DATA` | Already `SUBMITTED`; do not resend |
| Transmitted data, lost final reply | `UNKNOWN`; requires reconciliation |

If you do not know the phase or reply, never fabricate a false label like "definitely not sent."

## 12. One MailSendException Can Contain Multiple Errors

**JavaMailSender** supports sending multiple messages. If a batch send encounters errors, Spring may create a **MailSendException** and expose per-message failure details through APIs such as:

~~~java
MailSendException exception = ...;

Map<Object, Exception> failedMessages = exception.getFailedMessages();
Exception[] messageExceptions = exception.getMessageExceptions();
~~~

These are methods for inspecting error information, not send calls. In practice, the application catches the exception:

~~~java
try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    Map<Object, Exception> failed = ex.getFailedMessages();

    for (Map.Entry<Object, Exception> entry : failed.entrySet()) {
        Object message = entry.getKey();
        Exception error = entry.getValue();

        // Use application's message identifier to correlate the record.
        // Classify the error separately for each failed message.
    }
}
~~~

The example assumes `messages` is a prepared `MimeMessage` array. Map keys should be correlated with application-managed notification IDs; do not use `Object.toString()` as a stable identifier or log MIME content.

### Why Not Retry the Entire Batch?

Suppose three emails are sent:

~~~text
Email A: accepted by server
Email B: recipient error
Email C: network error
~~~

If you catch `MailSendException` and resend the entire `A+B+C` batch, Email A may be sent twice. Email B will keep failing due to invalid data. Email C must be classified based on the phase where the failure occurred.

Instead of resending the entire batch:

1. Attach a stable notification ID to each message.
2. Record outcomes per message where sufficient evidence exists.
3. Classify the cause of each failed message.
4. Retry only messages definitely not accepted that have retryable errors.
5. Mark `UNKNOWN` if a message's outcome cannot be determined.

**The failure map does not always prove every message absent from the map achieved final delivery.** It must be interpreted according to the API contract and exact failure point.

## 13. One Message With Multiple Recipients: Partial Success

Even when sending a single **MimeMessage**, that email may have multiple recipients across `To`, `Cc`, and `Bcc`. Some mail transports can succeed for one subset of recipients and fail for another, depending on configuration and SMTP behavior.

Jakarta Mail provides **SendFailedException** with methods to inspect the address sets:

~~~java
SendFailedException ex = ...;

Address[] invalid = ex.getInvalidAddresses();
Address[] validSent = ex.getValidSentAddresses();
Address[] validUnsent = ex.getValidUnsentAddresses();
~~~

General meaning:

- **invalidAddresses:** addresses invalid per the reported error.
- **validSentAddresses:** valid addresses considered sent within what the transport determined.
- **validUnsentAddresses:** valid addresses not yet sent.

These arrays may be empty or incomplete on some failure paths; they are not absolute proof of final delivery. Check how your Jakarta Mail provider and SMTP server implement partial-send behavior.

### Risk of Retrying the Entire MimeMessage

~~~text
Recipient A  -> accepted
Recipient B  -> rejected
Recipient C  -> accepted
~~~

If the whole message is resent to A, B, and C, A and C may receive duplicates. Practical options are:

- Track notification state per recipient when the system genuinely must send one multi-recipient message.
- Rebuild the resend for only the appropriate recipient subset, when clear state evidence exists.
- For transactional notifications with personalized data, it is usually simpler and safer to create **one notification per recipient**.

Do not assume every `SendFailedException` means all recipients failed. Conversely, do not assume recipients listed in `validSent` definitely saw the email in their Inbox.

## 14. Classifying by Final Error and Operational Action

A policy can use the following actions:

| Action | When chosen | Outcome |
|---|---|---|
| **RETRY** | Evidence of transient error and no acceptance received | Set `next_attempt_at` with backoff |
| **STOP** | Data error, config error, or permanent rejection | Mark `FAILED` or require intervention |
| **RECONCILE** | Outcome unclear, possibly already accepted | Mark `UNKNOWN`; reconcile before retrying |
| **SUBMITTED** | Evidence the server accepted the message at submission | Record as submitted, track delivery separately |

**SUBMITTED is not an exception type**, but a send outcome that must be preserved separately to avoid retrying due to errors occurring after SMTP accepted the message.

### Illustrative Decision Matrix

| Exception / evidence | Phase | Action |
|---|---|---|
| `MailParseException` due to invalid address syntax | `PREPARE` | `STOP` |
| `MailPreparationException` due to missing template variable | `PREPARE` | `STOP` |
| `MailAuthenticationException` with wrong credentials | `AUTH` | `STOP` + `ALERT` |
| `ConnectException` before SMTP session | `CONNECT` | Bounded `RETRY` |
| SMTP `421` | `CONNECT` or explicitly rejected command | `RETRY` |
| SMTP `451` at `RCPT TO` | `ENVELOPE` | `RETRY` corresponding recipient |
| SMTP `550` with user unknown | `ENVELOPE` | `STOP` corresponding recipient |
| SMTP `552` due to oversized message | `DATA` or policy stage | `STOP`, reduce size |
| `SocketTimeoutException` waiting for final DATA reply | `WAIT_FINAL_REPLY` | `RECONCILE` |
| SMTP acceptance confirmed, DB update failed | `AFTER_ACK` | `SUBMITTED` for sending; recover record state |
| `UnknownHostException` due to misconfigured host | `CONNECT` | `STOP`/`ALERT` |
| `SSLHandshakeException` due to wrong truststore | `TLS` | `STOP`/`ALERT` |

This matrix is only a guide. If additional data reliably shows whether the provider had a transient or permanent issue, the policy should incorporate that trusted evidence.

## 15. Normalizing Failure Evidence Before Deciding

Rather than catching exceptions and making ad-hoc decisions everywhere, normalize failures into a shared structure.

Example:

~~~java
public enum SendPhase {
    PREPARE,
    CONNECT,
    TLS,
    AUTH,
    ENVELOPE,
    DATA,
    WAIT_FINAL_REPLY,
    AFTER_ACCEPTANCE,
    UNKNOWN
}

public enum RetryAction {
    RETRY,
    STOP,
    RECONCILE,
    SUBMITTED
}

public record FailureEvidence(
        SendPhase phase,
        Integer definitiveSmtpReplyCode,
        boolean acceptanceConfirmed,
        boolean acceptanceMayHaveHappened
) {
}

public record RetryDecision(
        RetryAction action,
        String reason
) {
}
~~~

Where:

- **phase:** the processing phase observed or reliably inferred from evidence.
- **definitiveSmtpReplyCode:** the explicit SMTP reply of the relevant operation, not a code guessed from exception text.
- **acceptanceConfirmed:** an acceptance response for submission was received.
- **acceptanceMayHaveHappened:** the message may have been accepted without definite confirmation.
- **action:** the action the system will take.
- **reason:** a short code/reason for logs and metrics, containing no sensitive data.

These are not built-in Spring Mail fields. **FailureEvidence** is an application-designed model that must be populated from data actually supplied by the mail transport/provider. When information is unavailable, keep **UNKNOWN**; never invent a fake SMTP code to make the policy look more certain.

## 16. Java Example: Context-Aware Error Classifier

A basic implementation:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;

public final class MailRetryClassifier {

    public RetryDecision classify(
            Throwable failure,
            FailureEvidence evidence
    ) {
        if (evidence.acceptanceConfirmed()) {
            return new RetryDecision(
                    RetryAction.SUBMITTED,
                    "SMTP_ACCEPTANCE_CONFIRMED"
            );
        }

        Integer reply = evidence.definitiveSmtpReplyCode();
        if (reply != null) {
            if (reply >= 400 && reply <= 499) {
                return new RetryDecision(
                        RetryAction.RETRY,
                        "SMTP_TRANSIENT_REJECTION"
                );
            }
            if (reply >= 500 && reply <= 599) {
                return new RetryDecision(
                        RetryAction.STOP,
                        "SMTP_PERMANENT_REJECTION"
                );
            }
        }

        if (evidence.acceptanceMayHaveHappened()
                || evidence.phase() == SendPhase.WAIT_FINAL_REPLY
                || evidence.phase() == SendPhase.AFTER_ACCEPTANCE) {
            return new RetryDecision(
                    RetryAction.RECONCILE,
                    "SUBMISSION_OUTCOME_UNKNOWN"
            );
        }

        if (hasCause(failure, MailAuthenticationException.class)) {
            return new RetryDecision(
                    RetryAction.STOP,
                    "MAIL_AUTHENTICATION_FAILED"
            );
        }

        if (hasCause(failure, MailParseException.class)
                || hasCause(failure, MailPreparationException.class)) {
            return new RetryDecision(
                    RetryAction.STOP,
                    "MAIL_PREPARATION_FAILED"
            );
        }

        if (evidence.phase() == SendPhase.CONNECT
                && (hasCause(failure, ConnectException.class)
                    || hasCause(failure, SocketTimeoutException.class))) {
            return new RetryDecision(
                    RetryAction.RETRY,
                    "SMTP_CONNECT_TRANSIENT"
            );
        }

        return new RetryDecision(
                RetryAction.RECONCILE,
                "INSUFFICIENT_FAILURE_EVIDENCE"
        );
    }

    private boolean hasCause(
            Throwable failure,
            Class<? extends Throwable> expectedType
    ) {
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<>()
        );

        Throwable current = failure;
        while (current != null && seen.add(current)) {
            if (expectedType.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
~~~

### How to Read This Example

The implementation checks **acceptance evidence** first, then reads the SMTP reply, identifies uncertain outcomes, and finally inspects exception types. Consequently, even if a data update fails after SMTP acceptance is confirmed, the policy will not automatically resend the email.

**This illustrates a decision core, not a complete production classifier.** You still need to add:

- Verification of which step an SMTP reply belongs to, especially with multiple `RCPT TO` commands.
- Traversal of **MessagingException.getNextException()** in addition to `getCause()`.
- Per-message failure inspection from `MailSendException` and per-recipient details from `SendFailedException` when needed.
- Distinctions for TLS config errors, wrong hostname, missing files, missing templates, and provider API errors.
- Handling `2xx`, `3xx`, and invalid codes per actual phase, rather than assuming them as submission proof.
- Treating connection errors with unknown phase as uncertain instead of blindly retrying.

In Spring, mail exceptions are usually thrown after the send API succeeds or fails. Populating **FailureEvidence** accurately may require a transport-layer adapter, provider events, SMTP diagnostics, or step-tracking state. Never assign a phase by guessing from an exception name.

## 17. Be Careful With Rule Priority Order

A rule engine can easily misfire when conditions are evaluated in the wrong order.

Example of a wrong order:

~~~java
if (hasCause(ex, SocketTimeoutException.class)) {
    return RetryAction.RETRY;
}

if (acceptanceMayHaveHappened) {
    return RetryAction.RECONCILE;
}
~~~

If a timeout happens while waiting for the reply after `DATA`, the first branch will immediately retry and risk sending a duplicate.

Order checks by strongest evidence:

1. Was SMTP acceptance already confirmed?
2. Is there an explicit `4xx`/`5xx` rejection reply for the corresponding send step?
3. Could the message have been accepted while the reply was lost?
4. If definitely not sent, do the exception and phase indicate a transient or permanent failure?
5. If evidence is still lacking, move to a reconciliation/investigation state.

Not every system must use the same enums or code order, but the policy must ensure **no overly broad retry rule overrides evidence that the email may already have been accepted**.

## 18. When Should Only One Recipient Be Retried?

If one notification contains multiple addresses, an exception or SMTP server may report differing outcomes.

Example:

~~~text
Recipient A: 250 accepted
Recipient B: 450 temporary failure
Recipient C: 550 permanent rejection
~~~

At the `RCPT TO` phase, which recipients were accepted or rejected also depends on how the client and server continue the transaction. You cannot look at three codes alone and infer that `DATA` was transmitted for A and finally accepted.

A safer model for transactional emails:

~~~text
Business event
    |
    +--> Notification A -> recipient A -> separate state
    +--> Notification B -> recipient B -> separate state
    +--> Notification C -> recipient C -> separate state
~~~

Each notification has:

- Its own recipient.
- Its own event ID or notification key.
- Its own attempt counter.
- Its own retry status.
- Its own send result and reconciliation.

For multi-recipient messages, you need a partial-success handling policy and per-recipient outcome separation if supported by the transport. Never overwrite all recipients' states with one recipient's outcome.

## 19. Retry Policy Cannot Be Separated From Idempotency

Even when the classifier correctly decides an error is retryable, the system must still prevent duplicate processing of business events.

For example, a payment webhook delivered twice:

~~~text
PaymentSucceeded event E1
         |
         +--> HTTP delivery #1
         |
         +--> HTTP delivery #2
~~~

If every HTTP delivery creates a new email notification, the buyer can receive two receipts even with zero SMTP errors.

Therefore, maintain a stable notification identity:

~~~text
notification key =
  businessEventId + notificationType + recipientId
~~~

Or if the system tracks event versions:

~~~text
aggregateId + transitionVersion + notificationType + recipientId
~~~

Enforcing a unique constraint in the database prevents concurrent requests from creating duplicate notification records. Checking existence with a `SELECT` followed by `INSERT` without a constraint introduces a race condition.

Still, a database idempotency key **does not guarantee SMTP sends exactly once**:

1. Worker sends the message and SMTP accepts it.
2. Worker stops before marking `SUBMITTED`.
3. Lease expires; another worker reprocesses the record.
4. The email may be sent a second time.

Thus, **idempotent event handling** and **idempotent email delivery** are two distinct problems. Many SMTP servers do not offer an end-to-end deduplication API.

## 20. Message-ID Does Not Replace an Idempotency Key

The **Message-ID** header helps identify an email across mail systems. However, there is no universal guarantee that resending a message with the same `Message-ID` causes every SMTP server or mailbox to drop duplicates.

Therefore:

- You can attach a correlation ID or stable `Message-ID` to aid tracing per policy.
- Do not treat `Message-ID` as proof that retries will not produce duplicates.
- When a provider supports an idempotency key via API, carefully read its scope and retention window.
- With plain SMTP, treat duplicates as a risk to minimize and monitor, not something eliminable solely by a database transaction.

In an **UNKNOWN** scenario where reconciliation via the provider is impossible, deciding whether to resend or wait for manual review is a trade-off between **missing a notification** and **sending a duplicate**. Establish this decision per email type.

## 21. Retrying With Exponential Backoff and Jitter

Once an error is determined to be **retryable**, do not resend immediately back-to-back. A policy typically includes:

- **Initial delay:** wait time before the first retry.
- **Backoff multiplier:** factor by which wait time grows between attempts.
- **Maximum delay:** cap on any single wait interval.
- **Jitter:** random offset so multiple workers do not retry at the exact same instant.
- **Maximum attempts:** upper bound on attempts.
- **Maximum age:** maximum time a notification may wait if the business imposes an expiry.

An illustrative formula:

~~~text
baseDelay(attempt) =
    min(maxDelay, initialDelay * 2^(attempt - 1))

actualDelay = baseDelay + jitter
~~~

Suppose `initialDelay = 30 seconds` and `maxDelay = 30 minutes`:

| Retry # | Base delay before jitter |
|---:|---:|
| 1 | 30 seconds |
| 2 | 60 seconds |
| 3 | 120 seconds |
| 4 | 240 seconds |
| 5 | 480 seconds |
| 6 | 960 seconds |
| 7 | 1,800 seconds, capped |

This is an example policy, not Spring Mail defaults. Tune according to SMTP quotas, email type, and SLAs.

### Delay Calculation Function in Java

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelayPolicy {

    private static final long INITIAL_SECONDS = 30L;
    private static final long MAX_SECONDS = 1_800L;

    public Duration delayForRetry(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException(
                    "retryNumber must be greater than or equal to 1"
            );
        }

        long seconds = INITIAL_SECONDS;
        for (int i = 1; i < retryNumber; i++) {
            seconds = Math.min(MAX_SECONDS, seconds * 2);
        }

        long jitter = ThreadLocalRandom.current()
                .nextLong(0, Math.max(1, seconds / 4) + 1);

        return Duration.ofSeconds(seconds + jitter);
    }
}
~~~

This illustrates bounded delay computation. In real systems, avoid overflow risks if extending the formula, use a consistent `Clock`, and persist **nextAttemptAt** so retries survive restarts.

If an SMTP server returns a standardized, reliable retry delay, use that information to adjust the schedule. Never assume every SMTP response includes an HTTP-style **Retry-After** field.

## 22. Do Not Re-Run the Whole Business Method to Retry an Email

Suppose a payment endpoint both updates data and sends an email:

~~~java
public void completePayment(PaymentRequest request) {
    paymentService.capture(request);
    mailService.sendReceipt(request);
}
~~~

If sending the email fails, **do not retry all of `completePayment`** just to resend the receipt. That could cause duplicate payment processing if the business layer lacks proper idempotency.

Instead:

1. Handle the payment event idempotently.
2. Create a notification/outbox record within the relevant transaction.
3. Have a worker pick up that record.
4. Have the worker retry only **the notification send step** after the classifier re-evaluates the error.

~~~text
Payment transaction
    |
    +--> Write payment state
    |
    +--> Write notification outbox
    |
   COMMIT
    |
    v
Outbox worker
    |
    v
Render email + JavaMailSender
    |
    +--> SUBMITTED
    +--> RETRY_WAIT
    +--> FAILED
    +--> UNKNOWN
~~~

That way, SMTP failures never cause an endpoint to repeat business actions with financial or state consequences.

### Does Spring Retry Solve This Automatically?

A method-level retry tool can help re-execute a temporarily failing operation. However, merely wrapping **mailSender.send(...)** in a retry loop:

- Does not automatically persist durable state across process restarts.
- Does not automatically know whether SMTP `DATA` was accepted.
- Does not automatically resolve partial recipients.
- Does not automatically prevent mailbox-side duplicates.
- Can hold request threads too long if sleeping/backing off synchronously.

For critical notifications, usually let a worker/outbox manage durable retry schedules and let the classifier make decisions. A retry library is merely a policy-execution tool, not a replacement for idempotency design.

## 23. Persisting Classification Results in the Notification Record

A notification record can include:

| Field | Purpose |
|---|---|
| **notification_id** | Notification identifier |
| **event_id** | Source business event |
| **recipient_ref** | Recipient reference |
| **attempt_count** | Number of send attempts made |
| **status** | `PENDING`, `RETRY_WAIT`, `SUBMITTED`, `FAILED`, `UNKNOWN` |
| **last_failure_code** | Normalized error code, e.g., `SMTP_TRANSIENT_REJECTION` |
| **last_smtp_reply** | SMTP code if determined and permitted to store |
| **last_send_phase** | Send phase if known |
| **next_attempt_at** | Next retry timestamp |
| **provider_message_id** | Provider ID if available |
| **updated_at** | Last modified timestamp |

### State Machine

~~~text
       PENDING
          |
          v
       SENDING
          |
          +------ accepted ----------> SUBMITTED
          |
          +------ transient ---------> RETRY_WAIT
          |                               |
          |                               v
          |                            SENDING
          |
          +------ permanent ---------> FAILED
          |
          +------ ambiguous ---------> UNKNOWN
                                          |
                             +------------+------------+
                             |                         |
                             v                         v
                        SUBMITTED                 MANUAL_REVIEW
                       (reconciled)               or controlled
                                                    retry
~~~

Do not automatically turn `UNKNOWN` into `RETRY_WAIT` merely because the next polling cycle arrived. If you choose reconciliation, provide a dedicated worker or workflow to resolve uncertain states.

### Updating State With Ownership Fencing

In a multi-worker system, update conditionally by claim token:

~~~sql
UPDATE notification_outbox
SET status = 'RETRY_WAIT',
    next_attempt_at = :nextAttemptAt,
    last_failure_code = :reasonCode,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :notificationId
  AND status = 'SENDING'
  AND claim_token = :claimToken;
~~~

If the update affects 0 rows, the worker may have lost ownership. Never overwrite state with an unconditional update.

## 24. Using the Classifier in a Worker

Orchestration skeleton example:

~~~java
public void process(ClaimedNotification notification) {
    try {
        RenderedEmail rendered = renderer.render(notification);
        MimeMessage message = buildMimeMessage(
                notification.recipient(),
                rendered
        );

        mailSender.send(message);

        resultService.markSubmitted(
                notification.id(),
                notification.claimToken()
        );
    } catch (MailException exception) {
        FailureEvidence evidence =
                failureEvidenceExtractor.from(
                        notification,
                        exception
                );

        RetryDecision decision = classifier.classify(
                exception,
                evidence
        );

        resultService.apply(
                notification.id(),
                notification.claimToken(),
                decision
        );
    }
}
~~~

**failureEvidenceExtractor**, **buildMimeMessage**, **resultService.apply**, and the domain types are illustrative components to implement. For completeness, also handle `MessagingException` during MIME construction and data/rendering errors arising outside `MailException`.

The snippet shows where the classifier fits, not a copy-paste production implementation:

- With **MailSendException**, the extractor must handle per-message errors.
- When no reliable SMTP code/phase exists, the extractor must record insufficient evidence.
- For errors known to occur after acceptance, never apply generic retries.
- When persisting failure state, use a short database transaction separate from SMTP sending.
- If `resultService` fails to persist state after sending, use a recovery mechanism that does not blindly resend.

In practice, split the pipeline into **prepare -> submit -> finalize** steps to separate preparation exceptions from transport exceptions, avoiding catching one exception type for every phase.

## 25. Separate Prepare Errors From Transport Errors in Code

One way to give the classifier stronger evidence is a clear boundary:

~~~java
RenderedEmail content;
MimeMessage message;

try {
    content = renderer.render(notification);
    message = mimeFactory.create(notification, content);
} catch (TemplateException | InvalidNotificationException ex) {
    resultService.markFailed(notification.id(), "INVALID_CONTENT");
    return;
} catch (MessagingException ex) {
    resultService.markFailed(notification.id(), "MIME_PREPARATION_ERROR");
    return;
}

try {
    mailSender.send(message);
    resultService.markSubmitted(notification.id());
} catch (MailException ex) {
    // Collect known reply and phase, then classify.
    classifyAndRecord(notification, ex);
}
~~~

`TemplateException`, `InvalidNotificationException`, `mimeFactory`, and `resultService` methods are application-defined examples. Production code must use claim tokens, transactional result updates, and proper handling for temporarily unavailable attachment sources.

Splitting `try/catch` blocks by phase avoids a blanket `catch` lumping template errors, database errors, and SMTP errors together as "mail send error."

However, `send(message)` may still perform some MIME serialization/reading while transmitting data. Thus, attachment read or content encoding errors can still surface during the transport phase. Code boundaries aid diagnostics, though you still must inspect the actual cause.

## 26. Real-World Classification Scenarios

### Scenario A: Invalid Recipient Syntax

~~~text
Input: user@@example..com
Exception: address parse error
SMTP DATA: not sent
~~~

Action: **STOP**, require fixing the address. Retrying the same string will fail repeatedly.

### Scenario B: SMTP Server Temporarily Overloaded

~~~text
SMTP: 421 Service not available
Server explicitly rejected at the corresponding stage
~~~

Action: **RETRY** with backoff and jitter. Track retry counts to avoid adding further pressure on the server.

### Scenario C: Wrong SMTP Password

~~~text
Exception: MailAuthenticationException
Credentials/config unchanged
~~~

Action: **STOP or pause queue and ALERT**. After fixing credentials, perform a controlled replay per policy.

### Scenario D: Mailbox Does Not Exist

~~~text
SMTP: 550 5.1.1 User unknown
Recipient: customer@example.invalid
~~~

Action: **STOP** for that recipient. Do not retry continuously. Verify and fix the recipient.

### Scenario E: Timeout After DATA

~~~text
Application sent MIME content
Final response not yet received
SocketTimeoutException
~~~

Action: **RECONCILE**. If the provider has a tracking API, look up the outcome by correlation ID. If reconciliation is unavailable, choose manual handling or retry accepting duplicate risk, depending on notification criticality.

### Scenario F: Three Messages Where Two Were Accepted

~~~text
Batch: A, B, C
A: success
B: failed due to invalid recipient
C: connection error
~~~

Action: **do not retry the entire batch**. Record outcomes per message; stop B, classify C by phase and reply, and do not resend A.

### Scenario G: SMTP Accepted, but Database Result Write Failed

~~~text
JavaMailSender.send(...) returned normally
resultRepository.markSubmitted(...) failed
~~~

Action: **do not treat as an SMTP send failure**. Recover state via DB update retry/reconciliation; never resend simply because recording the result in the database failed.

## 27. Testing the Exception Classifier

A classifier should be tested with intentional inputs without needing a live SMTP server for every branch.

### Minimum Test Cases

| Case | Evidence | Expected decision |
|---|---|---|
| Auth failed | `MailAuthenticationException` | `STOP` |
| Parse failed | `MailParseException` | `STOP` |
| Connect refused | `CONNECT` phase, `ConnectException` | `RETRY` |
| SMTP 451 | Explicit rejection reply | `RETRY` |
| SMTP 550 | Explicit rejection reply | `STOP` |
| Lost final reply | `WAIT_FINAL_REPLY` phase | `RECONCILE` |
| Confirmed accepted | `acceptanceConfirmed = true` | `SUBMITTED` |
| Unknown cause and phase | Insufficient evidence | `RECONCILE` |
| Timeout after DATA | `MayHaveAccepted = true` | `RECONCILE` |
| Batch partial success | Different per-message outcomes | Handle per message |

JUnit 5 example using the classifier above:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.ConnectException;
import java.net.SocketTimeoutException;
import org.junit.jupiter.api.Test;

class MailRetryClassifierTest {

    private final MailRetryClassifier classifier =
            new MailRetryClassifier();

    @Test
    void retriesConnectionFailureBeforeSubmission() {
        FailureEvidence evidence = new FailureEvidence(
                SendPhase.CONNECT,
                null,
                false,
                false
        );

        RetryDecision result = classifier.classify(
                new ConnectException("Connection refused"),
                evidence
        );

        assertEquals(RetryAction.RETRY, result.action());
    }

    @Test
    void doesNotBlindlyRetryLostFinalReply() {
        FailureEvidence evidence = new FailureEvidence(
                SendPhase.WAIT_FINAL_REPLY,
                null,
                false,
                true
        );

        RetryDecision result = classifier.classify(
                new SocketTimeoutException("Read timed out"),
                evidence
        );

        assertEquals(RetryAction.RECONCILE, result.action());
    }

    @Test
    void stopsOnPermanentSmtpRejection() {
        FailureEvidence evidence = new FailureEvidence(
                SendPhase.ENVELOPE,
                550,
                false,
                false
        );

        RetryDecision result = classifier.classify(
                new RuntimeException("recipient rejected"),
                evidence
        );

        assertEquals(RetryAction.STOP, result.action());
    }
}
~~~

These tests verify the classifier's rules rather than proving the real SMTP library always emits these exact pieces of evidence. Write integration tests against a test SMTP server to verify how the adapter extracts reply codes, cause chains, and per-message behavior.

### Testing Network Errors With Unknown Outcomes

A test SMTP server can be configured to accept `DATA` and deliberately drop the connection before returning the final reply. This verifies the pipeline neither marks `FAILED` definitively nor auto-retries immediately.

Never simulate errors by sending real emails to production customers.

## 28. Operational Observability and Alerting

When classifying errors, emit metrics by **error category** and **action**, not just total exception counts.

Examples:

| Metric | Purpose |
|---|---|
| `mail_attempt_total` | Total send attempts |
| `mail_submission_success_total` | Confirmed submissions |
| `mail_retry_scheduled_total` | Failures classified as retryable |
| `mail_permanent_failure_total` | Failures stopped permanently |
| `mail_unknown_outcome_total` | Uncertain-outcome cases |
| `mail_auth_failure_total` | Authentication/configuration failures |
| `mail_smtp_reply_total` | SMTP reply code distribution |
| `mail_retry_queue_age` | Backlog age of retrying notifications |
| `mail_attempt_duration` | Transport-layer send latency |

A structured event log might contain:

~~~text
notificationId=... eventId=...
phase=CONNECT
errorCategory=TRANSIENT
decision=RETRY
attempt=3
smtpCode=421
nextAttemptAt=...
~~~

These fields are illustrative only. Never write credentials, MIME bodies, attachments, OTPs, tokens, or full email addresses to unprotected logs.

### Suggested Alerts

- Spike in `MailAuthenticationException`: suspect credential or provider policy changes.
- Rising SMTP `4xx`: possible provider overload or rate limiting.
- Rising SMTP `5xx`: possible recipient data or content policy issues.
- Rising `UNKNOWN`: possible late-phase network timeouts or adapter bug.
- `RETRY_WAIT` backlogged too long: worker or SMTP disruption.
- Rising `FAILED`: data/template/config needs fixing, not simply more retries.

## 29. Data Security When Analyzing Exceptions

A mail exception may contain:

- Sender or recipient email addresses.
- SMTP responses with externally supplied server content.
- Hostnames, TLS details, or authentication info.
- Attachment file paths.
- MIME data in certain stack traces or debug logs.

Therefore:

1. Log **normalized error codes** such as `SMTP_TRANSIENT_REJECTION` rather than copying raw responses into general logs.
2. Protect logs and restrict access permissions.
3. Do not log full `MimeMessage` contents merely to diagnose retries.
4. Do not use exception messages to construct notifications sent directly to customers.
5. Do not include tokens or verification links in operational error messages.
6. Limit retention duration for failure details and attempt histories.
7. If raw SMTP replies must be stored for investigation, apply appropriate data controls.

Accurate error classification does not require capturing every byte of the email. Usually only the phase, normalized reason, SMTP code, and correlation ID are needed.

## 30. Summary Decision Table

| Reliable evidence | Category | Action | Additional conditions |
|---|---|---|---|
| Invalid template/address syntax | Permanent | `STOP` | Update input/template then replay if needed |
| Credentials rejected | Permanent/configuration | `STOP` + `ALERT` | Replay only after credentials/permissions fixed |
| Invalid TLS certificate | Configuration/security | `STOP` + `ALERT` | Never bypass TLS verification |
| TCP connect timeout before submission | Transient | `RETRY` | Backoff, max attempts |
| Explicit SMTP `4xx` rejection | Transient | `RETRY` | Honor delay/quota |
| Explicit SMTP `5xx` rejection | Permanent | `STOP` | Inspect recipient, size, content, and policy |
| Local attachment missing | Preparation | `STOP` | Fix file lifecycle |
| Remote attachment timeout | Transient preparation | `RETRY` source | Ensure data still matches snapshot |
| Transmitted `DATA`, lost final reply | Ambiguous | `RECONCILE` | No blind retries |
| Acceptance confirmed, DB write failed | Post-submission | `SUBMITTED` | Recover DB state |
| Batch partial success | Mixed outcomes | Per-message action | Never resend whole batch |
| Unknown phase/SMTP code | Unknown | `RECONCILE` | Gather evidence, do not guess |

The final policy should reflect actual requirements. Short-lived OTP emails may lose value after delayed retries; critical invoice emails may warrant thorough investigation before dropping; marketing emails may have distinct quotas and suppression policies. A shared classification table should allow **configuration per notification type** without breaking safety rules for duplicates and unknown outcomes.

## 31. Key Takeaways

**Classifying exceptions for retries in Spring Framework Mail is not a mapping from one exception class to a retry count.** `MailAuthenticationException`, `MailParseException`, and `MailPreparationException` generally point to data/configuration checks; `MailSendException` requires inspecting nested causes and can contain multi-message outcomes. Jakarta Mail, network errors, and SMTP reply codes supply further causal evidence.

Always ask: **Which phase did the error happen in? Did the server give an explicit 4xx/5xx rejection reply? Might the message already have been accepted? Did any recipients or messages succeed?** If the error is transient and definitely not accepted, retry with backoff, jitter, attempt limits, and durable state. If permanent, stop and fix the root cause. If the outcome is uncertain, reconcile before resending.

The classifier must be paired with **event identity, notification-level idempotency, partial-success handling, an outbox/queue, observability, and an UNKNOWN policy**. These mechanisms reduce the risk of lost notifications or duplicates, though they do not turn SMTP into exactly-once delivery.

**The most important rule: only retry when there is strong enough evidence that retrying is justified; never turn an unknown exception into an unconditional resend.**


