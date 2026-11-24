# Partial Recipient Rejection Errors

When a **Spring Framework Mail** application sends an email to multiple recipients, not every address is necessarily accepted the same way by the SMTP server. In a single send attempt, it is possible that:

- `alice@example.net` is accepted by the server;
- `bob@example.net` is rejected because the address does not exist;
- `carol@example.net` is temporarily rejected because the mailbox is full or due to rate limits;
- the overall sending outcome for the group depends on how the mail provider handles **partial recipient failure**.

This is a **partial recipient rejection** scenario: some addresses may be valid and accepted at one SMTP stage while others are not. This differs from the SMTP server refusing the connection entirely, wrong passwords, or rejecting the entire email content.

The crucial rule is **never automatically resend to the entire recipient list when only some recipients fail**. If certain addresses were already accepted and the email content was sent to them, retrying everything can produce duplicate emails.

This lesson focuses on the SMTP flow, differences between all-or-nothing and partial sending configs, reading exceptions from Jakarta Mail/Spring Mail, classifying recipients for retry, and designing safe delivery states.

## 1. What Is Partial Recipient Rejection?

A message can contain multiple addresses across groups:

~~~text
To:  alice@example.net, bob@example.net
Cc:  carol@example.net
Bcc: audit@example.net
~~~

The SMTP server does not decide acceptance solely by reading `To`, `Cc`, or `Bcc` headers. During sending, the SMTP client builds **envelope recipients** and issues an `RCPT TO` command for each address in turn.

An illustrative SMTP session:

~~~text
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250 SIZE 25000000

C: MAIL FROM:<notifications@example.com>
S: 250 2.1.0 Sender OK

C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<bob@example.net>
S: 550 5.1.1 User unknown

C: RCPT TO:<carol@example.net>
S: 450 4.2.2 Mailbox temporarily unavailable

C: RCPT TO:<audit@example.net>
S: 250 2.1.5 Recipient OK
~~~

At the `RCPT TO` stage:

- Alice and the audit address were accepted as recipients for the current SMTP transaction.
- Bob was rejected with a 5xx reply.
- Carol was temporarily rejected with a 4xx reply.

**Accepting `RCPT TO` does not mean the email was successfully submitted.** The SMTP client still has to transfer content via `DATA` (or an equivalent mechanism if supported by the provider) and receive the final completion reply. Without a successful content submission step, recipients previously accepted at `RCPT TO` may still **not have been sent**.

### 1.1. Three Questions That Must Be Separated

When diagnosing, answer separately:

1. **Which addresses were accepted at `RCPT TO`?**
2. **Was the message content accepted by the SMTP server after `DATA`?**
3. **Was the email actually delivered to the final mailbox?**

These three questions are not equivalent. Normally Spring Mail/Jakarta Mail directly reports the **SMTP submission** result; downstream delivery/bounce events occurring later may require provider events, DSNs, or separate webhooks.

### 1.2. Partial Rejection Is Not Just "Invalid Email Syntax"

An address can have valid syntax like `alice@example.net` and still be rejected by SMTP due to:

- mailbox does not exist;
- domain or relay policy disallows it;
- quota/mailbox temporarily full;
- recipient blocked by policy lists;
- server requires authentication or disallows relay;
- sending rate or reputation throttled;
- server rejects for a temporary reason without disclosing details.

Conversely, syntactically invalid addresses can be caught directly in Java before the application ever reaches SMTP commands.

## 2. SMTP Progression When Recipients Are Rejected

To understand error handling, trace the SMTP sequence:

~~~mermaid
sequenceDiagram
    participant A as Spring Mail
    participant S as SMTP server
    A->>S: MAIL FROM
    S-->>A: 250 Sender accepted
    A->>S: RCPT TO Alice
    S-->>A: 250 Accepted
    A->>S: RCPT TO Bob
    S-->>A: 550 Rejected
    A->>S: RCPT TO Carol
    S-->>A: 450 Temporary rejection
    Note over A,S: Continuing or stopping depends on sendpartial/provider configuration
    alt Partial delivery enabled
        A->>S: DATA for accepted recipients
        S-->>A: 250 Message queued
        Note over A: Report error/partial result for rejected recipients
    else Partial delivery disabled
        A->>S: RSET or terminate transaction
        Note over A: Do not submit DATA on default non-partial path
    end
~~~

Exact transport behavior also depends on the Jakarta Mail SMTP provider and configuration. Key rules:

- Each address's `RCPT TO` command can get an independent reply.
- Sending to the remainder or aborting the entire message is decided by the SMTP client/provider.
- In non-partial mode, a single failed recipient can abort the whole message before `DATA` submission.
- With partial send, the provider can submit content for accepted recipients while simultaneously reporting errors for rejected ones.

### 2.1. `2xx`, `4xx`, and `5xx` Reply Codes

| Reply | General meaning | Example | Handling direction |
| --- | --- | --- | --- |
| `250` | Recipient accepted in the current SMTP transaction | `250 2.1.5 Recipient OK` | Continue processing message; do not assume delivery |
| `251` | Server accepts and has a forwarding mechanism | `251 User not local; will forward` | Treat as acceptance per server reply |
| `450` | Temporary rejection | Mailbox unavailable | May retry per policy |
| `451` | Temporary processing error | Local error | May retry with backoff |
| `452` | Temporary resource shortage | Insufficient storage | May retry with limits |
| `550` | Rejection usually considered permanent | User unknown/policy | Check cause; do not blindly retry |
| `551` | User not local; forwarding hint provided | User not local | Follow address policy; do not blindly forward |
| `553` | Mailbox name not accepted | Invalid mailbox name | Fix/check address |
| `554` | Transaction or policy rejected | Transaction failed | Analyze reply by stage |

In the SMTP model:

- **4xx** is a transient negative completion: the issue may be temporary.
- **5xx** is a permanent negative completion: the exact same request should not be retried indefinitely as-is.

However, the reply code within the **context of a specific command** determines its meaning. For instance, `550` at `RCPT TO` differs from `550` or `554` at the message-submission stage. Server descriptive text is also not a fully standardized API.

### 2.2. Enhanced Status Codes

Servers may return detailed codes:

~~~text
550 5.1.1 Recipient address rejected: User unknown
450 4.2.2 Mailbox full
550 5.7.1 Relay access denied
451 4.7.1 Temporary rate limit
~~~

Examples:

- `5.1.1` usually relates to a nonexistent recipient address.
- `4.2.2` usually relates to quota/mailbox full in a temporary sense.
- `5.7.1` can be policy, authentication, or relay restriction.
- `4.7.1` can be a temporary throttling policy.

**Do not infer the entire root cause from the text description alone.** Inspect the SMTP command, 3-digit code, enhanced status, and provider policy.

## 3. Two Processing Modes: All-or-Nothing vs. Partial Send

With the standard SMTP transport in Jakarta Mail, the `mail.smtp.sendpartial` property controls how partial recipient rejections are handled.

### 3.1. Default Is Usually `sendpartial=false`

Example:

~~~properties
mail.smtp.sendpartial=false
~~~

In this mode, when the provider encounters an unaccepted recipient, it typically **does not submit the message content to the remaining group** and reports a send error. Addresses that previously received `250` at `RCPT TO` may still belong to **valid but unsent**: addresses valid at RCPT, yet no message was sent on this attempt.

Example:

~~~text
To: Alice, Bob, Carol
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 250

sendpartial=false
-> SMTP transport does not send DATA for this message
-> This send attempt fails for the entire message
~~~

Cautious conclusion: if the cause really was rejecting one recipient at the RCPT stage in a provider behaving this way, do not label "Alice received the email" just because `RCPT TO` was accepted. Verify exception data and actual transport behavior.

### 3.2. Enabling `sendpartial=true`

Example:

~~~properties
mail.smtp.sendpartial=true
~~~

In this mode, a supporting SMTP transport can send the message to **accepted recipients**, even when other recipients are rejected.

~~~text
To: Alice, Bob, Carol
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 250

sendpartial=true
-> DATA is sent for the accepted group
-> Transport reports partial failure
-> Alice/Carol: reported valid-sent if DATA was accepted
-> Bob: not sent via this submission
~~~

Common source of confusion: **partial send can both succeed for one group and throw an exception for the overall send call**. Do not infer "method threw exception => nobody was sent to".

### 3.3. Comparison Table

| Aspect | `sendpartial=false` | `sendpartial=true` |
| --- | --- | --- |
| One recipient rejected at RCPT | Usually halts content submission for the whole message | Can send to remaining accepted recipients |
| Recipients that got `250` at RCPT | Likely valid but unsent | Likely among the group submitted |
| Java call | Throws error | May still throw error even though part was sent |
| Risk when retrying whole list | Can resend after fixing recipients, but must verify prior outcome | **Very high** if one group already succeeded |
| Operational state | Message-level failure is usually clearer | Requires recipient-level outcomes |
| Suitable use case | Want to avoid sending if the list has pre-DATA errors | Want maximum delivery to valid group and per-address tracking |

Do not enable `sendpartial=true` as a "bug fix". This is an **application semantics decision**: whether a message is permitted to reach only a subset of the list.

## 4. Spring Boot Configuration for Partial Send

When using Spring Boot and a Jakarta Mail SMTP provider supporting the property, configure via `spring.mail.properties`:

~~~yaml
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
      "[mail.smtp.sendpartial]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

`mail.smtp.sendpartial` is an SMTP provider property, not a method on `MimeMessageHelper`. Defaults and execution details depend on the Jakarta Mail/provider library, so verify the exact implementation and version deployed.

If you do not want partial delivery, keep the default or set it explicitly:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.sendpartial]": false
~~~

### 4.1. Do Not Confuse `sendpartial` with `reportsuccess`

Some SMTP providers support `mail.smtp.reportsuccess` to report detailed status even for accepted addresses. When enabled, the library may create success-reporting exceptions per address and cause the call to throw `SendFailedException` even when every recipient was submitted cleanly per provider mechanics.

Therefore:

- Do not enable `mail.smtp.reportsuccess` just to "log more" unless you have built handling for its exceptions.
- Do not assume every exception in the cause chain represents a failed recipient.
- Distinguish provider-specific success reports from `SMTPAddressFailedException`.
- Record the effective configuration when diagnosing seemingly contradictory send outcomes.

### 4.2. Affects Only the Active SMTP Transaction

The `sendpartial` property does not:

- pre-verify whether mailboxes exist before sending;
- automatically create retry jobs;
- automatically remove bad recipients from the database;
- guarantee delivery to the inbox;
- make messages idempotent;
- persist per-recipient state for the next attempt.

The application still needs classification logic and state persistence at the business layer.

## 5. Relevant Exceptions in Spring Mail and Jakarta Mail

When calling:

~~~java
mailSender.send(mimeMessage);
~~~

Spring may throw `MailException` (a runtime exception). Send failures may appear as `MailSendException`. Underlying exceptions from Jakarta Mail/provider can carry detailed data on which addresses were sent or rejected.

Key types:

| API / exception | Role |
| --- | --- |
| `org.springframework.mail.MailException` | Base exception in Spring Mail |
| `org.springframework.mail.MailSendException` | Send error; may hold per-message failures |
| `MailSendException.getFailedMessages()` | Map from failed message object to its exception |
| `jakarta.mail.SendFailedException` | Send error that can provide valid-sent, valid-unsent, and invalid address arrays |
| `jakarta.mail.MessagingException` | Base Jakarta Mail exception supporting `getNextException()` chaining |
| Provider's `SMTPAddressFailedException` | May carry rejected recipient, command, and SMTP code |
| Provider's `SMTPSendFailedException` | May carry SMTP-level send transaction error |

Package names for SMTP provider-specific classes vary between JavaMail generations and Jakarta Mail/Angus Mail. For instance, classes may live under `com.sun.mail.smtp` or `org.eclipse.angus.mail.smtp` depending on version. Therefore, handle at the standard `SendFailedException` API level first and use provider-specific classes only when detailed SMTP codes are needed.

### 5.1. `MailSendException` Can Wrap Multiple Errors

`JavaMailSender` has overloads sending multiple messages:

~~~java
mailSender.send(message1, message2, message3);
~~~

If some messages fail, `MailSendException.getFailedMessages()` holds errors keyed by **message object**. This is a different layer from multiple **recipients** inside a single message.

Two kinds of "partial":

1. **A batch of multiple messages:** message A succeeded while message B failed.
2. **One message with multiple recipients:** within message B, Alice was accepted while Bob was rejected.

Do not conflate these two outcome layers. First locate the specific message in `getFailedMessages()`, then analyze recipients inside that message's exception.

### 5.2. Three Address Sets from `SendFailedException`

`jakarta.mail.SendFailedException` provides:

~~~java
Address[] getValidSentAddresses();
Address[] getValidUnsentAddresses();
Address[] getInvalidAddresses();
~~~

General meaning:

| Address set | Cautious interpretation |
| --- | --- |
| `validSentAddresses` | Provider reports addresses were valid and sent during this submission |
| `validUnsentAddresses` | Provider reports addresses were valid but **not sent** this time |
| `invalidAddresses` | Provider reports addresses were unaccepted/invalid in this send context |

Note:

- An array may be `null`; that does not mean "sent".
- Provider/version/error type may return only partial information.
- `invalidAddresses` does not by itself prove the error is **permanent**; deciding retries requires SMTP codes and error types.
- `validSentAddresses` reflects reported submission outcomes, **not Inbox delivery**.
- Arrays may need reconciliation against the original recipient list; do not guess statuses for unreported addresses.

### 5.3. Multi-Layer Exception Chains

Spring exceptions can wrap Jakarta Mail exceptions via `getCause()`; additionally, `MessagingException` has `getNextException()`. Sometimes address details sit inside an inner exception rather than the outermost one.

An example tree:

~~~text
MailSendException
  |
  +-- failedMessages[MimeMessage]
        |
        +-- SendFailedException
              |
              +-- SMTPAddressFailedException (Bob, 550, RCPT TO)
              +-- SMTPAddressFailedException (Carol, 450, RCPT TO)
~~~

Do not assume every exception chain always has this exact shape. Actual data depends on the provider, error kind, and timing of failure.

## 6. Example Sending One Email to Multiple Recipients

For illustration, using `MimeMessageHelper`:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendAnnouncement(JavaMailSender sender)
        throws MessagingException {

    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            false,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("notifications@example.com");
    helper.setTo(new String[] {
            "alice@example.net",
            "bob@example.net"
    });
    helper.setCc("carol@example.net");
    helper.setSubject("System maintenance notification");
    helper.setText(
            "The system will undergo scheduled maintenance as announced."
    );

    sender.send(message);
}
~~~

`setTo` and `setCc` create recipient metadata on the message. When sending, transport constructs the appropriate envelope recipient list. If Bob is rejected at `RCPT TO` while Alice and Carol are accepted, the actual outcome depends on `mail.smtp.sendpartial` and subsequent server replies.

**Do not blindly modify the recipient list upon catching a generic exception.** Read recipient details from SMTP causes and persist state at the exact delivery unit defined by your application.

### 6.1. `To`/`Cc`/`Bcc` Are Not Three Independent SMTP Transactions

Within one `MimeMessage`, `To`/`Cc`/`Bcc` addresses normally participate in the same SMTP submission with corresponding `RCPT TO` commands. A Bcc error can also affect delivery for `To` if transport is in all-or-nothing mode.

Conversely, enabling partial send does not turn sending for each `To`/`Cc`/`Bcc` into independent jobs with individual retries. To have distinct per-recipient states and policies, the application must manage recipient lists at the job layer.

## 7. Reading Recipient Errors in a Structured Way

A diagnostic approach in Java:

1. Catch `MailSendException` when the send call fails.
2. Extract the specific `MimeMessage`'s failure from `getFailedMessages()`.
3. Walk `cause` and `MessagingException.getNextException()`.
4. Locate `SendFailedException` to extract address arrays.
5. If supported by the provider, inspect exceptions carrying specific SMTP codes.
6. Record recipient-level outcomes; indeterminate recipients must be marked **`UNKNOWN`**, never assumed sent or unsent.

### 7.1. Function to Traverse the Exception Chain

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;

public final class MailExceptionInspector {
    private MailExceptionInspector() {
    }

    public static List<SendFailedException> findRecipientReports(
            Throwable error) {
        if (error == null) {
            return List.of();
        }

        Deque<Throwable> queue = new ArrayDeque<>();
        Set<Throwable> visited = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>());
        List<SendFailedException> reports = new ArrayList<>();
        queue.add(error);

        while (!queue.isEmpty()) {
            Throwable current = queue.removeFirst();
            if (!visited.add(current)) {
                continue;
            }
            if (current instanceof SendFailedException report) {
                reports.add(report);
            }

            if (current.getCause() != null) {
                queue.addLast(current.getCause());
            }

            if (current instanceof MessagingException messaging) {
                Exception next = messaging.getNextException();
                if (next != null) {
                    queue.addLast(next);
                }
            }
        }
        return List.copyOf(reports);
    }
}
~~~

This function only **extracts reports** without interpreting or resending. It traverses both the cause chain and Jakarta Mail's next-exception chain, using an identity-based `visited` set to guard against duplicates or reference cycles.

### 7.2. Extracting Address Lists

~~~java
import java.util.Arrays;
import java.util.List;
import jakarta.mail.Address;
import jakarta.mail.SendFailedException;

static List<String> addresses(Address[] values) {
    if (values == null) {
        return List.of();
    }
    return Arrays.stream(values)
            .map(Address::toString)
            .toList();
}

static void inspectReport(SendFailedException report) {
    List<String> sent = addresses(
            report.getValidSentAddresses());
    List<String> unsent = addresses(
            report.getValidUnsentAddresses());
    List<String> invalid = addresses(
            report.getInvalidAddresses());

    // Illustrative diagnostic data only.
    // Production should log IDs/counts instead of raw personal addresses.
    System.out.println("valid-sent count: " + sent.size());
    System.out.println("valid-unsent count: " + unsent.size());
    System.out.println("invalid count: " + invalid.size());
}
~~~

If multiple nested reports exist, do not mechanically sum counts because the same address may be reported at different exception layers. Merge by recipient identity and understand provider semantics. When reports appear contradictory or omit addresses, flag for investigation instead of auto-retrying.

### 7.3. Extracting Causes from `MailSendException`

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailSendException;

try {
    sender.send(message);
} catch (MailSendException ex) {
    Exception messageFailure =
            ex.getFailedMessages().get(message);

    if (messageFailure != null) {
        var reports = MailExceptionInspector
                .findRecipientReports(messageFailure);

        for (var report : reports) {
            inspectReport(report);
        }
    } else {
        // No reliable recipient-level report
        // for this message: record UNKNOWN and investigate.
    }

    throw ex; // Do not turn a partial failure into a false success.
}
~~~

The example assumes `message` is the exact `MimeMessage` object passed to the sender. For multi-message batches, iterate each entry in `getFailedMessages()` and correlate with the corresponding job/recipients.

### 7.4. Why Not Catch Only `MessagingException`?

`JavaMailSender.send(...)` declares Spring-layer errors using `MailException`; unlike direct Jakarta Mail API calls that use `MessagingException`.

Avoid writing:

~~~java
try {
    sender.send(message);
} catch (MessagingException ex) { // Not the primary error of JavaMailSender.send
    // ...
}
~~~

This catch block may not match the method signature or Spring's exception translation. In code calling `MimeMessageHelper`, `MessagingException` can occur during **MIME preparation**; in code calling `JavaMailSender.send`, handle `MailException`/`MailSendException` at the Spring layer.

## 8. Reading Provider-Specific SMTP Codes

Standard `SendFailedException` exposes address groups, yet lacks full details for every `RCPT TO` reply. SMTP providers may offer dedicated classes, such as `SMTPAddressFailedException`, with methods like:

~~~java
getAddress();      // Affected address.
getCommand();      // SMTP command, usually RCPT TO.
getReturnCode();   // 3-digit code, e.g., 450 or 550.
~~~

Package names depend on the provider. With a compatible version of Angus Mail, you might have:

~~~java
import org.eclipse.angus.mail.smtp.SMTPAddressFailedException;

void inspectProviderError(Throwable cause) {
    if (cause instanceof SMTPAddressFailedException smtpError) {
        int code = smtpError.getReturnCode();
        String command = smtpError.getCommand();
        String address = smtpError.getAddress().toString();

        // Map code + command into diagnostics;
        // do not log raw addresses directly in production.
    }
}
~~~

This is an **Angus Mail-dependent illustration**: use this import only if your project's dependencies actually include that class. With older JavaMail generations, the package differs. Avoid coupling to provider-specific APIs for errors already sufficiently represented by standard `SendFailedException`.

### 8.1. Know Which Stage Produced the Reply

Example:

~~~text
RCPT TO Bob -> 550 5.1.1 User unknown
~~~

this is a per-recipient error.

Whereas:

~~~text
DATA -> 552 5.3.4 Message size exceeds fixed maximum message size
~~~

may be a whole-message error after earlier `RCPT TO` commands were already accepted. Do not take a `552` at the DATA stage and conclude a specific recipient was rejected for a full mailbox.

Similarly, `MAIL FROM`, authentication, or TLS errors usually affect the entire submission, not just one recipient.

## 9. Designing Per-Recipient State

If the product allows partial sends, persist state **per recipient**, not just one boolean `emailSent` for the whole list.

Example:

~~~text
Mail job: job-752
Message key: maintenance-2026-11-12:group-7

Recipient                 Status
------------------------------------------------
alice@example.net         SUBMITTED
bob@example.net           REJECTED_PERMANENT
carol@example.net         RETRY_WAIT
audit@example.net         SUBMITTED
~~~

For operations, statuses can include:

| Status | Meaning |
| --- | --- |
| `PENDING` | Not yet attempted |
| `PROCESSING` | Worker currently executing attempt |
| `SUBMITTED` | Provider/transport reported message submitted for recipient |
| `RETRY_WAIT` | Not sent; transient error awaiting retry |
| `REJECTED_PERMANENT` | Definitively rejected based on reliable outcome |
| `INVALID_INPUT` | Invalid/malformed address at application layer |
| `UNKNOWN` | Uncertain whether accepted or not |
| `FAILED_FINAL` | Retries exhausted per policy |
| `BOUNCED` | Provider reported delivery failure after submission |

`BOUNCED` is an event that can appear **after** `SUBMITTED`, not necessarily an immediate outcome of `send(...)`.

### 9.1. A Reference Schema

~~~sql
CREATE TABLE mail_delivery_job (
    id              VARCHAR(64) PRIMARY KEY,
    message_key     VARCHAR(160) NOT NULL UNIQUE,
    subject_key     VARCHAR(120) NOT NULL,
    created_at      TIMESTAMP NOT NULL
);

CREATE TABLE mail_recipient_delivery (
    id                  VARCHAR(64) PRIMARY KEY,
    mail_job_id         VARCHAR(64) NOT NULL,
    recipient_address   VARCHAR(320) NOT NULL,
    recipient_role      VARCHAR(10) NOT NULL,
    status              VARCHAR(40) NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    last_smtp_code      INTEGER,
    last_enhanced_code  VARCHAR(20),
    next_attempt_at     TIMESTAMP,
    submitted_at        TIMESTAMP,
    last_error_at       TIMESTAMP,
    FOREIGN KEY (mail_job_id) REFERENCES mail_delivery_job(id),
    UNIQUE (mail_job_id, recipient_address, recipient_role)
);
~~~

This is an illustrative schema. If the product allows the same address to appear in multiple roles (`To`/`Cc`/`Bcc`) within the same job, define deduplication rules and an appropriate uniqueness scope. The `recipient_address` column holds personal data; enforce access controls, encryption, and retention policies.

### 9.2. Separating Logical Request from Attempts

A message key usually identifies a logical send request. Yet each retry may carry a **different subset of recipients**. Do not use an attempt ID as the message key.

~~~text
Logical mail job:
  messageKey = announcement:group-7:version-1

Attempt 1 recipients:
  Alice, Bob, Carol

Attempt 2 recipients:
  Carol

Attempt 3 recipients:
  Carol (if attempt 2 outcome remained unclear)
~~~

In this model, recipient-level status and attempt history provide the data needed to decide which group gets retried.

## 10. Retrying Exactly the Unsent Subset

Suppose the provider reports:

~~~text
Alice: valid-sent
Bob:   invalid (550 5.1.1)
Carol: invalid/unsent (450 4.2.2)
~~~

If partial send already submitted the email to Alice, calling again:

~~~java
helper.setTo(new String[] {
        "alice@example.net",
        "bob@example.net",
        "carol@example.net"
});
sender.send(message);
~~~

can cause Alice to receive the email a second time. That is an **unsafe** retry.

Instead, the ideal policy:

1. Mark Alice = `SUBMITTED` per reliable reported result.
2. Mark Bob = `REJECTED_PERMANENT` if the SMTP code genuinely indicates a permanent recipient error.
3. Mark Carol = `RETRY_WAIT` if the code indicates a temporary error and the provider confirms unsent.
4. Create a new attempt for Carol only.
5. Do not auto-retry `UNKNOWN` addresses without an explicit duplicate-risk policy.

### 10.1. `4xx` Codes Do Not Always Mean Retry Immediately

A temporary reply may be:

~~~text
450 4.2.2 Mailbox full
451 4.7.1 Temporarily deferred
~~~

Use backoff and cap retry counts:

~~~text
Attempt 1: immediately when job is created
Attempt 2: after a wait interval
Attempt 3: longer wait interval
Attempt 4: final retry or transition to FAILED_FINAL
~~~

Use exponential backoff with jitter, capping total attempts and message lifetime. For emails containing OTPs or expiring links, do not retry after the content loses business validity.

### 10.2. `5xx` Codes Require Root-Cause Verification

If the server returns:

~~~text
550 5.1.1 User unknown
~~~

you usually should not retry that address endlessly with the same content. Yet another `5xx` code, such as `5.7.1`, may relate to domain policy, permissions, or relay configuration rather than a user typo.

Therefore:

- Do not automatically delete customer accounts just because one `RCPT TO` was rejected.
- Do not automatically rewrite recipient addresses from server reply text.
- Classify the reason before marking permanent failure.
- If the failure involves sender/provider configuration, resolve it at the operational layer.

### 10.3. `UNKNOWN` Status Is a Valid Outcome

If the connection drops after content was transmitted but before the application received a confirmation reply, it may be unknown whether the SMTP server accepted the message.

~~~text
Client sends DATA bytes
SMTP server may accept
Network connection lost
JavaMailSender throws exception
~~~

In this situation, retrying can create duplicates. Never infer `NOT_SENT` merely because an exception was thrown. For critical emails, check provider events or apply a retry policy accepting potential duplicates.

## 11. Best Approach When Per-Recipient Control Is Needed

If each recipient needs personalized content or independent retries, consider **one separate message/job per recipient** instead of sending a single MIME message to a large list.

### 11.1. One Email to Multiple Recipients

Pros:

- fewer SMTP submissions;
- simple when sending identical content to a small group;
- fits conversational threads with visible `To`/`Cc`.

Cons:

- one recipient error can affect other recipients;
- complex partial outcomes;
- harder to retry per recipient;
- `To`/`Cc` addresses may be exposed to one another;
- harder to personalize content and tracking.

### 11.2. One Email per Recipient

Pros:

- outcomes are usually easy to classify per job;
- retries do not require rebuilding recipient lists;
- avoids accidentally exposing recipient lists;
- easy to personalize language, names, tokens, and templates.

Cons:

- higher submission count and operational overhead;
- requires queues, rate limits, and compatible provider policies;
- unsuitable if the goal is a shared conversation where everyone must see the same `To`/`Cc`.

### 11.3. Decision Matrix

| Requirement | Usually suitable design |
| --- | --- |
| Transactional emails per customer | One job/message per recipient |
| OTP or password reset emails | One message per recipient |
| Bulk personalized notifications | Fan-out into independent jobs |
| Internal correspondence with multiple `To`/`Cc` | Can use one multi-recipient message |
| Need exact visibility into which recipient retries | Detailed job/recipient state or one message/recipient |
| Do not want one bad recipient blocking everyone | Consider partial send or splitting messages |
| Provider has per-recipient HTTP API status | Can integrate dedicated API per provider contract |

There is no universally right option. Delivery structure must align with product semantics and privacy policies.

## 12. Recipient Headers and SMTP Envelope Are Not Identical

When building:

~~~text
To: alice@example.net, bob@example.net
Cc: carol@example.net
~~~

these are headers helping email clients display recipients. The SMTP envelope determines which addresses routers deliver to.

If `sendpartial=true` and Bob is rejected, the email delivered to Alice can still keep the header:

~~~text
To: alice@example.net, bob@example.net
~~~

even though Bob did **not** receive the message on that send. The library does not necessarily strip rejected addresses from headers of the transmitted body.

Consequences:

- Recipients may see names/addresses of recipients who were not sent to.
- Downstream systems should not infer from headers that everyone received the mail.
- If retrying only for Bob, decide the retry message's visible headers per business policy.

### 12.1. `Bcc` Must Be Protected

`Bcc` is normally omitted from visible headers of messages sent to recipients, yet still participates in envelope delivery. When manually building MIME or retrying, never accidentally place `Bcc` addresses into `To`/`Cc` or public logs.

When emailing unrelated customers in bulk, **one message per recipient** is usually much safer for privacy than trying to bundle everyone into `To`/`Cc`.

## 13. Designing Idempotency for Partial Retries

A failed recipient may be retried multiple times due to queue redeliveries or worker crashes. Distinguish:

- **Message key:** identifies the logical send request.
- **Recipient key:** identifies a single recipient within the request.
- **Attempt ID:** identifies a single SMTP attempt.

Example:

~~~text
messageKey = maintenance-2026-11-12:group-7

recipientKey[alice] = <messageKey>:user-101
recipientKey[bob]   = <messageKey>:user-102
recipientKey[carol] = <messageKey>:user-103

attempt 1: Alice/Bob/Carol
attempt 2: Carol
~~~

Preserve the same message key and recipient key across all attempts. A database unique constraint on `(message_key, recipient_key)` prevents creating duplicate logical recipient jobs when events are replayed.

### 13.1. Outbox and Durable State

For critical emails:

1. Persist one outbox job and its recipients inside the same business transaction.
2. Workers claim the job or eligible recipient subset.
3. Send via SMTP outside database lock-holding transactions.
4. Analyze partial outcomes for recipients in that attempt.
5. Update per-recipient statuses in a separate transaction.
6. Retry eligible recipients while preserving identities.

Persisting recipient states should use transactions to prevent lost/overwritten updates across workers. With multiple workers, use leases/locking/versioning to prevent concurrent processing of the same recipient.

### 13.2. A Duplicate Window Still Exists

Scenario:

~~~text
T1 Worker sends to Alice
T2 SMTP accepts
T3 Worker crashes before DB updates Alice = SUBMITTED
T4 Job is re-claimed after lease timeout
T5 Alice may be sent to again
~~~

Unique keys cannot turn SMTP and a database into an atomic transaction. To reduce duplicates:

- use provider APIs with idempotency keys if supported;
- record provider message IDs when available;
- manage leases and `UNKNOWN` outcomes;
- choose retry policies based on business risk;
- design content to tolerate duplicates if they cannot be fully prevented.

## 14. Distinguishing Synchronous Rejection from Post-Send Bounces

A recipient may be accepted by the SMTP server during submission yet still bounce later.

~~~text
Application -> SMTP relay: 250 Message accepted
SMTP relay -> Destination server: Mailbox not found
SMTP relay -> Return-path: Delivery failure / bounce
~~~

In this case:

- `JavaMailSender.send(...)` initially returns normally.
- No `SendFailedException` occurs at send time.
- Delivery failure surfaces later via bounces, DSNs, provider APIs, or webhooks.

This is **not** the same phenomenon as the server synchronously rejecting `RCPT TO`.

| Failure type | When known | Data source | Status |
| --- | --- | --- | --- |
| `RCPT TO` rejected | During SMTP submission | SMTP exception / reply | Rejected/Retry wait |
| `DATA` rejected | During SMTP submission | Transport exception | Message-level failed/unknown |
| Bounce after acceptance | After transport submitted | DSN/provider event | Bounced |
| User does not open email | Not an SMTP error | Engagement event if available | Do not infer from send |

Do not automatically promote `SUBMITTED` to `DELIVERED` just because `send(...)` threw no error.

## 15. Diagnostic Workflow When Production Reports Partial Recipient Rejection

When receiving a report like "sent to three people, only one received it", follow a systematic workflow.

### Step 1 — Identify the Exact Logical Job and Attempt

Record:

~~~text
mailJobId
messageKey
attemptId
provider
smtpHost
configurationProfile
timestamp
~~~

Do not start by immediately resending. Avoid duplicating to already-accepted recipients.

### Step 2 — Inspect the Intended Recipient List

Take the address list **from the persisted job snapshot**, not just from the `To` header:

~~~text
To: Alice, Bob
Cc: Carol
Bcc: Audit
~~~

Check for duplicate recipients, malformed syntax, or list changes between attempts.

### Step 3 — Check Transport Configuration

Verify:

~~~text
mail.smtp.sendpartial
mail.smtp.reportsuccess
SMTP host/port
TLS/authentication
Provider implementation/version
~~~

A single change to `sendpartial` can dramatically alter how Spring Mail reports results.

### Step 4 — Inspect the Exception Chain

Read:

- Which Spring exception type?
- Which message is inside `MailSendException.getFailedMessages()`?
- Is `SendFailedException` present?
- What do `validSent`, `validUnsent`, and `invalid` arrays report?
- Is `SMTPAddressFailedException` present with address/code/command?
- Did the failure occur at `RCPT TO` or `DATA`?

Do not rely solely on message text like "Send failed", because it does not convey full partial outcomes.

### Step 5 — Cross-Check Provider Logs

If SMTP relay/provider logs exist, search by timestamp, message/job ID, or provider ID. Note:

- providers may log recipient rejections separately;
- logs do not necessarily include full `Bcc` or body content;
- never share verbatim logs containing personal addresses, tokens, or credentials.

If no evidence is found for a recipient, keep `UNKNOWN` rather than assuming `NOT_SENT`.

### Step 6 — Decide on Retries

| Verified outcome | Action |
| --- | --- |
| Already submitted | Do not retry just because another recipient failed |
| Temporarily rejected, definitely unsent | Retry that recipient with backoff |
| Permanently rejected | Report failure / fix data or policy |
| Unsent due to all-or-nothing | After fixing root cause, can retry whole message |
| Uncertain whether sent | Apply `UNKNOWN` policy, weighing duplicate risk |

### Step 7 — Record Outcomes

Store per-recipient status, SMTP code, attempt ID, and timestamp. Never store only one `sent = true/false` flag for an entire multi-recipient job.

## 16. Security and Privacy When Handling Recipient Errors

SMTP provider exceptions can contain recipient addresses and server replies. Logging full exceptions can leak personal data.

Principles:

- Do not log SMTP username/password, tokens, or raw authentication commands.
- Do not log full email bodies/attachments to diagnose recipients.
- Log only internal recipient IDs or masked/redacted addresses where possible.
- Restrict access to logs and recipient status data.
- Do not put email addresses into high-cardinality metric labels.
- Do not expose "user does not exist" details to unauthenticated callers.
- If using `mail.debug` or SMTP protocol traces in test environments, protect logs and disable when no longer needed.

Operational log example:

~~~text
event=mail_partial_failure
mailJobId=job-752
attemptId=try-3
validSentCount=2
validUnsentCount=0
rejectedCount=2
temporaryRejectCount=1
permanentRejectCount=1
result=PARTIAL_SUBMISSION
~~~

When looking up a specific recipient, use an internal `recipientId` rather than raw emails in public dashboards.

## 17. Testing Partial Recipient Failures

When building a mail module, test both the transport layer and business retry policy layer separately.

### 17.1. Testing One Rejected Recipient with `sendpartial=false`

Simulate an SMTP server:

~~~text
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 250
~~~

Verify:

- adapter reports the right error category;
- message is not recorded as `SUBMITTED` for all recipients;
- recipients that got `250` without `DATA` submission are recognized as unsent;
- retry policy does not mark Alice delivered.

### 17.2. Testing `sendpartial=true`

With the same `RCPT TO` replies:

- verify provider sends `DATA` for permitted recipients;
- call may throw an exception containing partial results;
- `validSent` recipients get submitted status;
- rejected recipients get appropriate statuses;
- subsequent retries exclude the `validSent` group.

### 17.3. Testing Multiple Response Types

| Case | Simulation | Expectation |
| --- | --- | --- |
| 1 | All `250`, DATA `250` | Submission completes with no synchronous error |
| 2 | One `550 5.1.1` | Diagnoses permanent recipient rejection |
| 3 | One `450 4.2.2` | Can retry rejected recipient |
| 4 | All RCPT `250`, DATA `554` | Message-level failure, not blamed on one recipient |
| 5 | Connection drops after DATA | Outcome `unknown`, not assumed unsent |
| 6 | `reportsuccess=true` | Parser distinguishes success reports from failures |
| 7 | `Bcc` rejected | Does not leak `Bcc` addresses into `To`/`Cc` or public logs |
| 8 | Batch of multiple `MimeMessage` | Does not confuse failed messages with failed recipients |
| 9 | Worker retry after partial | Preserves states and does not resend `validSent` |
| 10 | Provider bounce after submit | Status updated via separate event |

### 17.4. Mocking `JavaMailSender` Is Not Enough for SMTP Replies

Unit tests can mock `JavaMailSender` to verify exception-to-state policy logic. Yet a mock cannot verify `RCPT TO`, `DATA`, or provider `mail.smtp.sendpartial` behavior.

To test real SMTP behavior, use an integration SMTP test server capable of per-recipient configurable replies or a custom test server. Some mail catchers accept every recipient and are unsuitable for simulating `RCPT TO` rejections without custom rules.

Never use production SMTP to test failure cases with real customer addresses.

### 17.5. Testing Races and Crash Windows

With durable job/recipient state, also test:

- two workers claiming the same recipient;
- lease expiring while a worker is still sending;
- SMTP accepted yet worker crashes before DB update;
- retry picking up the same key, same recipient;
- provider rejecting a recipient after the job partially progressed;
- recipient status updates not suffering lost updates across concurrent workers.

These tests verify idempotency and retry logic, not just MIME sending mechanics.

## 18. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Catching `MailException` and treating all recipients as failed | May retry already-sent group | Read partial reports and store per-recipient state |
| Treating `250 RCPT TO` as delivered | Misreports status and loses retry capability | Separate RCPT, DATA, and delivery |
| Enabling `sendpartial=true` while storing one `sent` boolean | Cannot represent partial success | Per-recipient outcomes |
| Default `sendpartial=false` yet marking `250` recipients as sent | Fails to resend what was never sent | Inspect `validUnsent` and DATA outcome |
| Treating every `invalid` address as permanent | Ignores temporary 4xx errors | Combine with SMTP code/command |
| Retrying whole list after partial send | Already-sent recipients get duplicate mail | Retry only unsent subset with clear evidence |
| Relying only on `getCause()` | Misses `MessagingException.getNextException()` | Traverse both chains |
| Confusing `MailSendException.getFailedMessages()` with recipient list | Misclassifies message-level vs. recipient-level | Separate both outcome layers |
| Always treating exceptions as nobody sent to | Wrong when partial enabled or outcome uncertain | Have an `UNKNOWN` status |
| Relying on `To` header to know who received mail | Headers do not reflect envelope/acceptance | Store recipients and transport outcomes |
| Putting `Bcc` into retry `To`/`Cc` | Leaks secret recipient list | Preserve roles; split messages when needed |
| Enabling `reportsuccess` while parser treats all exceptions as errors | Misreports submissions | Distinguish provider success reports |
| Deleting rejected recipients from customer accounts | May delete due to transient policy/reputation | Classify and follow operational workflows |
| Marking `DELIVERED` right after `send` | Misses subsequent bounces | Use `SUBMITTED` and separate delivery events |

## 19. End-to-End Scenario: Sending a Notification to Three People

An application sends a maintenance notice to Alice, Bob, and Carol. Configuration:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.sendpartial]": true
~~~

SMTP outcome:

~~~text
RCPT Alice -> 250 Accepted
RCPT Bob   -> 550 5.1.1 User unknown
RCPT Carol -> 450 4.2.2 Temporarily unavailable
DATA       -> 250 Message accepted for Alice
~~~

Per verified provider report:

~~~text
Alice = SUBMITTED
Bob   = REJECTED_PERMANENT
Carol = RETRY_WAIT
~~~

Application records:

~~~text
mailJobId = job-752
messageKey = maintenance:2026-11-12:group-7
attemptCount = 1
status = PARTIAL_SUBMISSION
~~~

After backoff, the worker creates a second attempt:

~~~text
Recipient list: Carol
Message key: still maintenance:2026-11-12:group-7
Attempt ID: new
~~~

Alice is excluded from the second attempt because she was reported submitted. Bob is not retried automatically due to permanent rejection. Carol is the only eligible recipient. If the second attempt succeeds, the job finishes with an aggregate summary such as "2/3 submitted, 1/3 permanent reject".

If the SMTP server reply left it unclear whether Alice received DATA, the application **cannot conclude with certainty that Alice was sent to**. State must then reflect that uncertainty rather than using the simple logic above.

### 19.1. Comparing When `sendpartial=false`

With the same `RCPT TO` codes yet `sendpartial=false`:

~~~text
RCPT Alice -> 250
RCPT Bob   -> 550
RCPT Carol -> 450
Transport does not submit DATA for the message under all-or-nothing config
~~~

Recipients that returned `250` should not be marked delivered/submitted for this send. After fixing the list or applying updated policies, the application can schedule an appropriate attempt. The key difference is **the confirmed outcome at the DATA stage** and how transport reports valid-sent/valid-unsent, not merely `250` counts on `RCPT TO`.

## 20. Checklist for Handling Partial Recipient Rejection

When designing or investigating:

1. **Identify send style:** one multi-recipient message or multiple independent messages?
2. **Check configuration:** what are active `sendpartial` and `reportsuccess` settings?
3. **Separate SMTP stages:** rejection at `RCPT TO`, `DATA`, or post-submission bounce?
4. **Read exceptions at the right layer:** Spring `MailSendException`, Jakarta `SendFailedException`, and provider-specific SMTP exceptions.
5. **Reconcile all three address sets:** valid-sent, valid-unsent, invalid, against the original recipient list.
6. **Do not equate invalid with permanent:** require SMTP 4xx/5xx codes and context.
7. **Persist per-recipient state:** submitted, retry wait, permanent reject, or unknown.
8. **Retry selectively:** never resend to recipients reliably confirmed submitted.
9. **Protect `Bcc` and personal data:** avoid leaking recipient lists in headers or logs.
10. **Coordinate idempotency:** keep message key and recipient identity stable across retries.
11. **Do not claim exactly-once:** a crash window between SMTP and DB updates still exists.
12. **Test with an SMTP server simulating rejections:** mocking the sender alone cannot verify protocol behavior.

## 21. Key Takeaways

- SMTP replies individually to each `RCPT TO`, so a single message can encounter **partial recipient rejection**.
- `250` at `RCPT TO` only accepts the recipient for that step; submission still depends on `DATA`.
- With `mail.smtp.sendpartial=false`, providers usually halt content sending if any recipient is rejected.
- With `mail.smtp.sendpartial=true`, providers may send to the valid group and **still throw an exception** to report the failed group.
- `SendFailedException` carries three important sets: valid-sent, valid-unsent, and invalid.
- `MailSendException.getFailedMessages()` is keyed **by message**, not directly a failed-recipient list.
- For specific error codes, inspect `SMTPAddressFailedException` and SMTP commands per provider.
- **Never retry the entire group** when part of it was already submitted.
- Indeterminate outcomes must be recorded as `UNKNOWN` when clear evidence is lacking.
- Emails marked `SUBMITTED` can still bounce later; delivery is a separate state.

Handling partial recipient rejection is not merely catching an exception and calling `send(...)` again. A reliable Spring Mail system must know **which recipients were submitted, which were unsent, which were rejected, and which outcomes remain uncertain**. Only by cleanly separating those states can an application retry safely, curb duplicate emails, and report truthful per-recipient sending outcomes.

### References

- **RFC 5321 — Simple Mail Transfer Protocol:** `MAIL FROM`, `RCPT TO`, `DATA`, and SMTP reply codes.
- **RFC 3463 — Enhanced Mail System Status Codes:** detailed codes for addresses, mailboxes, and policies.
- **Spring Framework Reference — Email:** `JavaMailSender` and `MimeMessageHelper`.
- **Spring Framework API — `MailSendException`:** handling send failures and `getFailedMessages()`.
- **Jakarta Mail API — `SendFailedException` / `MessagingException`:** valid-sent, valid-unsent, invalid addresses, and next-exception chains.
- **Jakarta Mail/Angus Mail SMTP provider documentation:** `mail.smtp.sendpartial`, `mail.smtp.reportsuccess`, and specific SMTP failure classes.
