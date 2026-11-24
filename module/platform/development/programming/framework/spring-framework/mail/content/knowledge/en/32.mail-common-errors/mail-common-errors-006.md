# Not Reading Failed Messages in `MailSendException`

When a **Spring Framework Mail** application sends multiple emails in a batch, an error from `JavaMailSender.send(...)` does not necessarily mean **every message failed the same way**. One email may have been accepted by the SMTP relay, another rejected due to an invalid recipient, and the remaining one never sent because the connection dropped.

A common anti-pattern:

~~~java
try {
    mailSender.send(messages);
} catch (MailException ex) {
    log.error("Failed to send email", ex);
    markEveryJobAsFailed(batch);
}
~~~

This code looks only at the **overall exception** and ignores message-level information that Spring can provide. When the concrete exception is `MailSendException`, `getFailedMessages()` returns a map associating each **failed message** with its **corresponding exception**; `getMessageExceptions()` can also be used to inspect aggregated message exceptions.

**Failing to read failed messages in `MailSendException`** makes per-job diagnosis difficult, leads to wrong-scope retries, leaves audit logs incomplete, and obscures the difference between message-level failures and batch-level transport errors.

However, `getFailedMessages()` **is not a delivery ledger**. It does not prove emails absent from the map reached an inbox; nor does it automatically resolve partial recipients or SMTP timeouts after `DATA`. Reliable handling requires understanding **exception types, object identity, failure scope, idempotency, outboxes, and retry conditions**.

This lesson examines the Spring Mail APIs, building per-message diagnostics, Java examples, single/multi-recipient scenarios, Jakarta Mail cause chains, safe structured logging, testing, and operations.

## 1. How Does One Email Differ from a Batch of Emails?

With a single message:

~~~java
MimeMessage mime =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                mime, false, "UTF-8"
        );

helper.setTo("buyer@example.org");
helper.setSubject("Order confirmed");
helper.setText("Order ORD-981 has been confirmed.");

mailSender.send(mime);
~~~

If an error occurs, the caller knows which job failed because there is only one message. Still, you must classify the error and account for whether SMTP may have accepted before the connection dropped.

With a batch:

~~~java
MimeMessage a = createMessageA();
MimeMessage b = createMessageB();
MimeMessage c = createMessageC();

mailSender.send(a, b, c);
~~~

One possible outcome is:

~~~text
Message A: relay accepted
Message B: recipient invalid
Message C: hit transport error or not yet attempted
~~~

Catching the outer exception and marking everything `FAILED` or retrying the entire batch risks resending Message A and giving the recipient a duplicate email.

Conversely, simply logging the exception and marking the batch complete means B or C may never be retried or handled.

**To make per-mail-job decisions, you must correlate error details with each individual message.**

## 2. Relevant Spring Mail Exceptions

| Exception | General Scope | Handling Direction |
| --- | --- | --- |
| `MailException` | Base abstraction for Spring Mail errors | Catch-all, log/propagate per policy |
| `MailSendException` | Send failure; may hold failed-message map | Read `getFailedMessages()` and cause |
| `MailAuthenticationException` | SMTP authentication failed | Check credentials, do not hot-retry |
| `MailPreparationException` | Mail preparation failed | Check composer/template |
| `MailParseException` | Parsing/preparing content issue | Check MIME/addresses/data |
| Jakarta Mail `MessagingException` | Mail transport/format-level error | Usually appears in cause/nested chain |

Not every error carries `getFailedMessages()` data. Catching too broadly can lose specialized handling branches:

~~~java
try {
    mailSender.send(messages);
} catch (MailSendException ex) {
    // Message-level + transport diagnostics.
} catch (MailAuthenticationException ex) {
    // Credential/account-level error.
} catch (MailException ex) {
    // Other Spring Mail error types.
}
~~~

These separate catch blocks illustrate ordering from specific to general. `MailAuthenticationException` and `MailSendException` are distinct branches of `MailException`; placing `MailException` first would make later branches unreachable.

## 3. What Data Does `getFailedMessages()` Return?

API:

~~~java
Map<Object, Exception> failures =
        mailSendException.getFailedMessages();
~~~

Each entry contains:

- **Key:** the message object recorded as failed.
- **Value:** the `Exception` describing the corresponding cause.

The key type is **`Object`**, not always `MimeMessage`. Along standard Spring Mail paths, it can correspond to the original `MimeMessage` or `SimpleMailMessage` depending on the overload and internal conversion.

Conceptual model:

~~~text
MailSendException
  failedMessages:
    MimeMessage B -> SendFailedException
    MimeMessage C -> MessagingException
~~~

A common mistake is unconditional casting:

~~~java
for (Object key : ex.getFailedMessages().keySet()) {
    MimeMessage failed = (MimeMessage) key;
}
~~~

This code fails if the application sent `SimpleMailMessage[]` and the map contains the original simple messages.

**Rule:** Handle key object types matching the sender API/overload used; if unrecognized, record an unknown mapping rather than casting or attributing to another job.

## 4. `getMessageExceptions()` vs. `getFailedMessages()`

You can also read:

~~~java
Exception[] messageCauses =
        ex.getMessageExceptions();
~~~

This retrieves exceptions tied to message-level failures. Yet when you need to know **which mail job hit which exception**, the key → value map is usually far more useful.

| API | Provides | Does Not Guarantee |
| --- | --- | --- |
| `getFailedMessages()` | Message object → exception | Complete delivery/attempt state |
| `getMessageExceptions()` | Array of message-related exceptions | Correlation to each job without keys |
| `getCause()` | Overall/high-level cause | Every per-recipient failure |
| `getMessage()` | Descriptive text | Stable machine-parseable format |
| Stack trace | Code call site | SMTP acceptance/delivery outcome |

Never infer message index from array position, and never regex-parse `getMessage()` as the source of truth for permanent/transient policies.

## 5. Example: Reading the Failed-Message Map on Catch

~~~java
try {
    mailSender.send(messages);

} catch (MailSendException ex) {

    Map<Object, Exception> failures =
            ex.getFailedMessages();

    log.warn(
            "Mail batch failure, failedEntries={}",
            failures.size()
    );

    for (Map.Entry<Object, Exception> entry
            : failures.entrySet()) {

        Object failedMessage = entry.getKey();
        Exception cause = entry.getValue();

        log.warn(
                "Mail item failure: messageType={}, causeType={}",
                failedMessage == null
                        ? "unknown"
                        : failedMessage.getClass()
                                .getSimpleName(),
                cause == null
                        ? "unknown"
                        : cause.getClass()
                                .getSimpleName()
        );
    }

    throw ex;
}
~~~

Here only **types** are logged to avoid accidentally printing raw recipients/subjects/bodies. In production, also log `mailJobId`, `attemptId`, `providerId`, or a normalized error category.

Calling `throw ex` ensures upstream callers still know the batch failed. If a gateway persists per-job state and swallows the exception, define an explicit contract so callers never assume the whole batch succeeded.

## 6. Why Not Log Only the Outer Exception?

Two logging approaches:

~~~java
log.error("Could not send mail", ex);
~~~

versus:

~~~text
batchId: batch-981
providerId: relay-a
failedEntries: 2

jobId: job-B
  failureCategory: INVALID_RECIPIENT

jobId: job-C
  failureCategory: TEMPORARY_TRANSPORT
~~~

differ dramatically in usefulness.

A generic log has a stack trace yet cannot necessarily answer:

- How many messages failed?
- Which specific job errored?
- Was a recipient malformed or non-existent?
- Is the failure account-level or message-level?
- Can individual jobs be retried independently?
- Did any attempt have an uncertain outcome?
- Does the incident affect one tenant or the whole provider?

When batches contain dozens of emails, ignoring the failed map cripples incident investigation and accurate retry decisions.

## 7. An Empty Map Does Not Mean No Error

`getFailedMessages()` can be **empty** when the exception represents a global transport/connection failure or when an implementation does not populate per-message entries.

Never write:

~~~java
if (ex.getFailedMessages().isEmpty()) {
    markBatchSubmitted(batchId);
}
~~~

That is a misinterpretation. The exception already signaled a failure; there are simply **no failed-message entries to correlate**.

A safer pattern:

~~~java
Map<Object, Exception> failed =
        ex.getFailedMessages();

if (failed.isEmpty()) {
    recordGlobalFailure(
            batchId,
            ex.getCause()
    );
} else {
    recordItemFailures(
            batchId,
            failed
    );
}
~~~

`recordGlobalFailure` and `recordItemFailures` are application abstractions. Without per-message evidence, status should reflect an **unresolved/unknown outcome** rather than turning the whole batch into success.

## 8. Is a Message Absent from the Map Guaranteed Sent?

**There is no universal rule that “not in failed map = delivered”.**

Consider:

1. The Spring sender may have sent some messages before failing.
2. Some messages may not have been attempted due to connection failure.
3. The relay may have accepted a message while the client lost the reply.
4. A single MIME message may list multiple recipients and the server accepted only a subset.
5. Sender libraries/overloads can differ in how failed entries are populated.
6. Inbox delivery happens downstream after submission.

For a specific implementation/version, reading the contract and testing can clarify when keys are recorded. Still, never turn an unverified assumption into a system-wide business guarantee.

**`getFailedMessages()` records observed failures; it is not a receipt confirming every external side effect.**

## 9. Correlating Failed Messages Back to Mail Jobs

A batch should pair each job ID with its constructed object:

~~~java
public record MailItem(
        UUID jobId,
        MimeMessage message) {
}
~~~

~~~java
List<MailItem> items =
        prepareMessages(outboxJobs);

MimeMessage[] batch =
        items.stream()
                .map(MailItem::message)
                .toArray(MimeMessage[]::new);
~~~

For MIME objects in a batch, map by **object identity**:

~~~java
Map<MimeMessage, UUID> jobByObject =
        new IdentityHashMap<>();

for (MailItem item : items) {
    jobByObject.put(
            item.message(),
            item.jobId()
    );
}
~~~

On catch:

~~~java
for (Map.Entry<Object, Exception> entry
        : ex.getFailedMessages().entrySet()) {

    UUID jobId = null;
    Object key = entry.getKey();

    if (key instanceof MimeMessage mime) {
        jobId = jobByObject.get(mime);
    }

    if (jobId == null) {
        recordUnmappedFailure(
                batchId, entry.getValue()
        );
    } else {
        recordFailureForJob(
                jobId, entry.getValue()
        );
    }
}
~~~

`prepareMessages` and the record methods are illustrative APIs. `IdentityHashMap` is useful when matching the **exact instance** passed to the sender.

Important precondition: the key in the failed map must be an object the integration boundary can map. Do not assume every implementation/overload always preserves identical object references.

## 10. Why Not Correlate Jobs by Subject or Recipient?

An anti-pattern:

~~~java
UUID jobId =
        findJobBySubject(message.getSubject());
~~~

Multiple emails can share the subject `Order confirmation`. One recipient can receive multiple notifications with the same `To`; a single email can also address multiple recipients.

Headers like `Message-ID` or `X-Correlation-ID` help tracing, yet:

- They may be regenerated during compose/retry.
- They may be missing or modified.
- They do not guarantee external provider deduplication.
- They should not replace internal job/attempt IDs.

**Binding the job ID to the object at batch creation** is far clearer than guessing correlation from email content.

## 11. `SimpleMailMessage` Requires Dedicated Key Handling

Example:

~~~java
SimpleMailMessage first =
        new SimpleMailMessage();

first.setTo("first@example.org");
first.setSubject("Notice A");
first.setText("Content A");

SimpleMailMessage second =
        new SimpleMailMessage();

second.setTo("second@example.org");
second.setSubject("Notice B");
second.setText("Content B");

mailSender.send(first, second);
~~~

The simple-mail send path may store the **original `SimpleMailMessage`** as the key, whereas the MIME path may use `MimeMessage`.

A diagnostic adapter can distinguish both:

~~~java
Object key = entry.getKey();

if (key instanceof SimpleMailMessage simple) {
    // Lookup original simple message -> jobId.
} else if (key instanceof MimeMessage mime) {
    // Lookup MIME instance -> jobId.
} else {
    // Do not misattribute: record unknown message type.
}
~~~

Never cast every key to MIME. When handling sensitive payloads, never call `simple.toString()` or serialize the full message into logs to correlate.

## 12. Do Not Infer Batch Index from the Failed Map

Avoid:

~~~java
int failedIndex =
        ex.getFailedMessages().size() - 1;
~~~

Entry count does not indicate the position of the first failed message. A `Map` makes no contract about input array indices. Nor can you rely on `getMessageExceptions()` ordering to recover indices reliably.

Instead:

- Keep `MailItem(jobId, message)` per batch.
- Attach an attempt ID per job.
- Map by object identity when the API preserves it.
- Flag an unknown mapping whenever correlation fails.
- Never assume lower-indexed messages were definitely delivered.

For use cases needing clear per-job outcomes without needing batch throughput, **one send call per message** usually lowers complexity dramatically.


## 13. A Single Failed `MimeMessage` May Contain Multiple Recipients

One message:

~~~java
MimeMessage message =
        mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message, false, "UTF-8"
        );

helper.setTo(new String[] {
        "a@example.org",
        "b@example.org",
        "c@example.org"
});

helper.setSubject("Maintenance notice");
helper.setText("Scheduled service maintenance.");

mailSender.send(message);
~~~

An SMTP relay may accept `a@example.org`, reject `b@example.org`, and leave `c@example.org` unsent. `MailSendException#getFailedMessages()` keys failures by **message object**, not as a separate map per recipient.

A message-level exception can carry recipient-level details in Jakarta Mail:

~~~text
MimeMessage:
  recipient A: validSent
  recipient B: invalid
  recipient C: validUnsent

MailSendException:
  key = MimeMessage
  value = SendFailedException / transport detail
~~~

Not every provider populates all three arrays reliably. That depends on connection state, SMTP replies, and transport behavior.

Retrying the entire MIME risks duplicating to A. Dropping the MIME entirely leaves C unnotified. Thus the system needs a policy that genuinely understands **partial sends**.

## 14. `SendFailedException` and Address Groups

Jakarta Mail provides `SendFailedException` with these APIs:

~~~java
import jakarta.mail.Address;
import jakarta.mail.SendFailedException;

void reportRecipientGroups(
        SendFailedException ex) {

    Address[] invalid =
            ex.getInvalidAddresses();

    Address[] validSent =
            ex.getValidSentAddresses();

    Address[] validUnsent =
            ex.getValidUnsentAddresses();

    log.warn(
            "Recipient outcomes: invalid={}, " +
            "validSent={}, validUnsent={}",
            invalid == null ? 0 : invalid.length,
            validSent == null ? 0 : validSent.length,
            validUnsent == null ? 0 : validUnsent.length
    );
}
~~~

General meaning:

| Group | Reported Meaning |
| --- | --- |
| `invalidAddresses` | Addresses determined invalid by the transport |
| `validSentAddresses` | Addresses reported sent/accepted at the transport level |
| `validUnsentAddresses` | Valid addresses not yet sent |
| null/empty | No info for this group; do not infer other groups' outcomes |

**`validSent` does not prove inbox delivery.** It describes only the transport-level exception state, not final delivery events.

In production, track recipient IDs in the job store and reconcile transport details through a reliable mapping without logging full addresses unless authorized and necessary.

### Why Is One Job per Recipient Often Simpler?

With one job per recipient:

- Idempotency key is clear per recipient.
- Retries are independent.
- Suppression and unsubscribe are clean.
- Other recipients' `To`/`Cc` addresses are never leaked.
- Attempt/delivery status is easy to record.
- B's failure does not force A to fail.

If business logic uses one message for multiple recipients, you must handle recipient-level outcomes or accept a specialized retry policy.

## 15. Jakarta Mail's Cause Chain

An underlying SMTP error can be wrapped by Spring into `MailSendException`, containing a `MessagingException` or subclass.

Investigation should inspect:

~~~java
Throwable topCause =
        ex.getCause();

Map<Object, Exception> failed =
        ex.getFailedMessages();

Exception[] messageFailures =
        ex.getMessageExceptions();
~~~

Never read a single `ex.getMessage()` line and declare the root cause.

Jakarta Mail's `MessagingException` also exposes:

~~~java
MessagingException#getNextException()
~~~

It can contain additional transport errors that do not follow Java's `getCause()` chain the way applications expect.

Bounded diagnostic traversal example:

~~~java
import jakarta.mail.MessagingException;

void visitMailExceptions(
        MessagingException initial) {

    MessagingException current = initial;

    int depth = 0;

    while (current != null && depth++ < 16) {

        log.debug(
                "Mail nested exception type={}",
                current.getClass().getSimpleName()
        );

        Exception next =
                current.getNextException();

        current = next instanceof
                MessagingException nested
                        ? nested
                        : null;
    }
}
~~~

This example walks `MessagingException` nodes only. A full collector can also capture a final non-`MessagingException` node while tracking visited object identities to prevent reference cycles.

### Do Not Parse Exception Text into Business Rules

Avoid:

~~~java
if (ex.getMessage().contains("Mailbox unavailable")) {
    markPermanent(jobId);
}
~~~

Message strings are not a stable machine-readable protocol. SMTP providers use varying wording, languages/locales, and nested exception formats.

When reply codes/enhanced status codes are available from the transport and provider contract, use those structured fields in your classifier. When details are lacking, keep category `UNKNOWN` to handle safely.

## 16. SMTP 4xx, 5xx, and Classification Limits

SMTP reply codes help distinguish:

- 4xx: protocol-level temporary failure, generally retryable.
- 5xx: reply-code permanent failure, generally should not immediately retry with identical payload/route.

Yet caution is essential:

1. Providers may assign custom meanings for quotas, sender verification, or policies.
2. One failed SMTP command does not automatically mean every recipient failed.
3. Exceptions may bundle multiple codes from `RCPT`/`DATA`.
4. A timeout with no reply code means an uncertain outcome.
5. A 5xx credential/sender-account error can affect every job on that account.
6. A permanent configuration error may need fixing before retrying rather than deleting the job.

Therefore:

~~~text
Spring Mail exception
  -> Jakarta Mail cause / nextException
  -> SMTP reply / enhanced status if present
  -> provider policy
  -> classify attempt
  -> decide retry / hold / permanent / unknown
~~~

Never apply a blanket rule like “retry every `MailSendException` after 30 seconds”.

## 17. `MailSendException` and Connection-Level Failures

A batch can fail before sending the first message:

~~~text
Connect to SMTP host
  -> TLS handshake failure
  -> exception
  -> no message submitted
~~~

Or:

~~~text
Connect OK
  -> AUTH rejected
  -> cannot send
~~~

Yet if failure hits after a few messages, the state differs:

~~~text
Connect OK
  -> A accepted
  -> B accepted
  -> socket closed before C
~~~

All of these can surface as mail-related exceptions at the application boundary.

Therefore, diagnostics must capture:

- Transport error type.
- Any TLS/AUTH/connection cause.
- Contents of failed-message entries.
- Corresponding attempt/batch/job IDs.
- Selected sender account/provider.
- Whether reliable SMTP acceptance exists for any item.
- Whether an unknown outcome occurred after `DATA`.

For account-level errors like AUTH, never hot-retry the entire outbox using the old password; fix credentials/refresh caches and relieve account pressure.

## 18. Preparation Errors Differ from Send Errors

With `MimeMessagePreparator`:

~~~java
mailSender.send(mime -> {

    MimeMessageHelper helper =
            new MimeMessageHelper(
                    mime, true, "UTF-8"
            );

    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(html, true);

    // Add attachments, inline assets, headers...
});
~~~

If template/rendering/attachment setup fails, the system may throw `MailPreparationException` or another exception before SMTP submission is even attempted.

Separate:

| Stage | Example Failure | Handling Direction |
| --- | --- | --- |
| Business validation | Disallowed recipient | Reject job creation |
| Template rendering | Missing variable, broken template | Fix template/payload |
| MIME preparation | Missing attachment, invalid header | Fix content/storage |
| SMTP connect/auth | TLS/credential failure | Alert provider/account |
| SMTP RCPT | One recipient rejected | Classify per recipient |
| SMTP DATA | Message too large, policy reject | Do not retry identical payload endlessly |
| SMTP response lost | Unknown outcome | Reconcile/retry with duplicate awareness |
| Provider delivery | Bounce/complaint | Separate feedback workflow |

`getFailedMessages()` applies only when a corresponding `MailSendException` exists. Never use it to obscure pipeline failures that never even built MIME.

## 19. A Strongly Typed Diagnostic Helper

You can build a model returning diagnostic results without logging raw emails:

~~~java
public enum MailFailureScope {
    MESSAGE,
    BATCH,
    CONNECTION,
    UNKNOWN
}
~~~

~~~java
public record MessageFailureDiagnostic(
        UUID jobId,
        String exceptionType,
        MailFailureScope scope) {
}
~~~

A boundary receiving `MailSendException` and mapping it:

~~~java
public List<MessageFailureDiagnostic> diagnostics(
        MailSendException exception,
        Map<MimeMessage, UUID> jobsByMime) {

    List<MessageFailureDiagnostic> result =
            new ArrayList<>();

    for (Map.Entry<Object, Exception> entry
            : exception.getFailedMessages().entrySet()) {

        UUID jobId = null;

        if (entry.getKey()
                instanceof MimeMessage mime) {
            jobId = jobsByMime.get(mime);
        }

        Exception failure = entry.getValue();

        result.add(
                new MessageFailureDiagnostic(
                        jobId,
                        failure == null
                                ? "unknown"
                                : failure.getClass()
                                        .getSimpleName(),
                        jobId == null
                                ? MailFailureScope.UNKNOWN
                                : MailFailureScope.MESSAGE
                )
        );
    }

    return result;
}
~~~

This is an example of **diagnostic translation**, not a full send-outcome classifier. When the failed map is empty, the returned list is empty while the outer exception still stands; callers must record the batch-level error separately. When `jobId == null`, never attribute the error to the first job by default.

### Do Not Turn a `null jobId` into Success

If mapping cannot locate the job, causes may include:

- Mismatched send overload.
- Key object differs from the object built earlier.
- Key is a `SimpleMailMessage`.
- Sender/custom adapter changed object identity.
- Context mapping was lost across an async boundary.

That is a correlation error to log by batch ID and investigate, not a reason to ignore the failure.

## 20. A Mail Gateway Should Return a Structured Outcome

An application-level API can define:

~~~java
public enum SubmissionOutcome {
    SUBMITTED,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE,
    UNKNOWN_OUTCOME
}
~~~

~~~java
public record MailSubmissionResult(
        UUID mailJobId,
        UUID attemptId,
        SubmissionOutcome outcome,
        String failureCategory) {
}
~~~

The gateway layer will:

1. Select an approved sender account.
2. Compose the message.
3. Attach job/attempt correlation.
4. Send.
5. On `MailSendException`, read the map and cause.
6. Classify the outcome within what is certain.
7. Return the result / persist the attempt under an authorized ID.

When sending one job per call, mapping is simpler:

~~~java
public void submitOne(
        UUID jobId,
        MimeMessage mime) {

    try {
        mailSender.send(mime);
        resultStore.recordSubmitted(jobId);

    } catch (MailSendException ex) {
        Exception itemFailure =
                ex.getFailedMessages().get(mime);

        resultStore.recordSendFailure(
                jobId, ex, itemFailure
        );
    }
}
~~~

This is a skeleton: `resultStore` must classify and persist in short transactions; `recordSendFailure` must not mark permanent failure if details are insufficient. If a DB write failure occurs after SMTP acceptance, the job may be retried. This example intentionally makes no exactly-once promise.

With multiple tenants/providers, choose the sender instance by route before creating `MimeMessage`. Never mutate username/password on a shared sender across threads.

## 21. Large Batches Make Partial Failures Harder to Reason About

A call like:

~~~java
mailSender.send(
        mimeA, mimeB, mimeC, mimeD, mimeE
);
~~~

may reduce overhead in some cases, yet raises complexity:

- Which jobs were accepted by the relay?
- Which jobs were never attempted?
- Which jobs were temporarily rejected?
- Will retries duplicate?
- Does a single message have multiple recipients?
- Can map keys be correlated back to jobs?
- Can each attempt be audited?

For transactional emails with low per-call volume and strict tracking needs, sending one job at a time in a worker is usually far more maintainable.

If high volume makes batching yield measurable gains, build a result adapter tailored to the exact sender version in use, tested against partial failures and unknown outcomes.

**Never choose batching solely because the method accepts varargs.** Choose based on throughput, latency, rate limiting, and retry complexity.

## 22. Outbox Pattern Handling Failures Per Job

Systems needing durability typically store mail intent in `mail_outbox` inside the business transaction:

~~~text
Business transaction:
  UPDATE order
  INSERT mail_outbox
  COMMIT

Worker:
  claim one mail job
  compose MimeMessage
  JavaMailSender.send
  record outcome
  retry if policy allows
~~~

A basic schema:

~~~text
mail_outbox:
  id
  tenant_id
  purpose
  recipient_contact_id
  sender_profile_id
  status
  attempt_count
  next_attempt_at
  lease_token
  last_failure_category
  last_failure_scope
  last_failed_message_type
  created_at
  updated_at
~~~

With one job per recipient, failure correlation ties directly to `jobId`. With batches, `failedMessages` mapping records results against the right jobs.

Crucially: **outbox transactions and SMTP do not commit atomically**. If `send` succeeds and the worker crashes before updating the DB, the job may be submitted again once the lease expires.

## 23. Crash Windows and Unknown SMTP Outcomes

A scenario:

~~~text
Worker sends MIME over SMTP.
Server accepts DATA.
Network drops before client reads reply.
JavaMailSender throws error.
Worker may retry.
Recipient may receive two emails.
~~~

This cannot be fixed by a check like:

~~~java
if (failed.containsKey(mime)) {
    retry(mime);
}
~~~

Because the failed map tells you the transport **reported an error**, not that the external relay **never received the content**.

For financial emails, OTPs, or sensitive notifications, plan for:

- Idempotent content or token versions.
- Outbox attempt IDs.
- Duplicate-tolerant business semantics where possible.
- Reconciliation via provider APIs when correlation exists.
- Policy-appropriate retries.
- Never promising exact-once SMTP without a supporting contract.

A fixed `Message-ID` helps tracing, yet no universal rule requires every SMTP/receiving server to deduplicate by that header.

## 24. Evidence-Based Retry Classification

A classifier might define:

~~~java
public enum MailFailureCategory {
    TEMPORARY_TRANSPORT,
    PROVIDER_THROTTLED,
    AUTHENTICATION_FAILED,
    TLS_FAILURE,
    INVALID_RECIPIENT,
    INVALID_SENDER,
    MESSAGE_TOO_LARGE,
    CONTENT_REJECTED,
    ATTACHMENT_UNAVAILABLE,
    UNKNOWN_OUTCOME,
    UNKNOWN
}
~~~

Illustrative policy table:

| Category | Action |
| --- | --- |
| Temporary transport before submission | Retry with backoff |
| Explicit SMTP throttling | Retry after delay |
| Auth failure | Hold account/alert, refresh credentials |
| TLS verification failure | Fix trust/endpoint, never disable TLS |
| Permanent invalid recipient | Do not retry as-is; apply suppression |
| Invalid sender/domain | Fix sender verification |
| Message too large | Shrink attachments or use links |
| Attachment storage temporarily down | Retry while resource stays valid |
| Timeout after DATA | Unknown outcome/reconcile |
| Insufficient details | Unknown; do not auto-mark submitted |

Never equate exception class with policy: `MailSendException` is only the starting point. Inspect causes/codes/provider responses and business rules.

## 25. Retry Backoff and Quotas

Temporary SMTP failures must not create a tight retry loop:

~~~text
Attempt 1 -> immediate
Attempt 2 -> 30 seconds later
Attempt 3 -> 1 minute later
Attempt 4 -> 2 minutes later
Attempt 5 -> 4 minutes later
... bounded by max delay and age
~~~

Apply jitter so workers do not retry in lockstep.

In addition to backoff:

- Enforce maximum attempts/age per mail purpose.
- Never send expired OTP/password-reset tokens.
- Recheck unsubscribe/consent for marketing mail.
- Cap concurrency per SMTP account.
- Enforce provider and tenant quotas.
- Never retry a multi-recipient MIME blindly after partial acceptance without resolving per-recipient outcomes.
- Do not retain attachments past their valid lifetime.
- On account AUTH errors, hold jobs rather than hammering the provider.

An accurate failed-messages map identifies which jobs need attention, yet **does not replace retry policies and business authorization**.

## 26. Logging Failures per Job Without Leaking Email Contents

A good log entry:

~~~text
mailJobId: mail-981
attemptId: attempt-2
batchId: batch-47
providerId: relay-a
senderProfileId: tx-tenant-42
failureScope: MESSAGE
exceptionType: SendFailedException
failureCategory: INVALID_RECIPIENT
outcome: PERMANENT_FAILURE
~~~

Never log:

~~~java
log.error(
        "Failed message={}",
        failedMimeMessage
);
~~~

or serialize full message objects, which can expose:

- Recipients and contact info.
- Subjects containing private details.
- HTML/plain-text bodies.
- Password reset/OTP tokens.
- Attachment filenames or contents.
- Confidential customer data.

Log masked recipient/contact IDs per policy. When exception stack debugging is necessary, store it in access-controlled systems with proper retention, avoiding raw credentials or MIME.

### Never Use Message Content as Metric Labels

A metric with a `subject` or `recipient` label creates unbounded cardinality and leaks PII. Use `failureCategory`, `providerId`, `purpose`, and controlled account groups.


## 27. Monitoring Failed Messages and Error Categories

Useful metrics:

| Metric | Meaning |
| --- | --- |
| `mail_submit_attempt_total` | Count of send attempts |
| `mail_send_exception_total` | Spring Mail exceptions encountered |
| `mail_failed_message_total` | Reported failed-message entries |
| `mail_send_batch_failure_total` | Batches throwing outer exceptions |
| `mail_failure_category_total` | Errors by classifier category |
| `mail_unknown_outcome_total` | Attempts with uncertain outcomes |
| `mail_partial_recipient_failure_total` | Observed partial-recipient failures |
| `mail_job_retry_total` | Jobs scheduled for retry |
| `mail_job_permanent_failure_total` | Jobs halted from retrying |
| `mail_outbox_oldest_pending_age_seconds` | Age of oldest pending job |
| `mail_provider_auth_failure_total` | AUTH failures |
| `mail_provider_throttle_total` | Throttling events |
| `mail_message_correlation_miss_total` | Keys in failed map unmatched to jobs |
| `mail_submit_duration_seconds` | SMTP submission duration |

Some metrics measure **exception observations**, not delivery rates. Never add up failed-message entries and call that “total emails not delivered to users”.

### Recommended Alerts

- Spike in `MailSendException` after deployment.
- Repeated SMTP AUTH/TLS failures per provider account.
- Failed-messages map populated with high correlation misses.
- Growing outbox retry backlog and oldest age breaching SLA.
- Sudden jump in permanent recipient failures.
- Spike in `UNKNOWN_OUTCOME` after network drops/timeouts.
- Sustained throttling on a provider.
- One tenant experiencing far more failures than usual.

Never attach recipient emails, subjects, or raw exception messages as metric labels. For detailed investigation, look up job/attempt IDs in access-controlled structured logs.

## 28. Scoping Errors Correctly in Multi-Tenant Systems

A SaaS app may send mail for multiple tenants through different sender accounts:

~~~text
tenant-a -> smtp-account-a
tenant-b -> smtp-account-b
tenant-c -> shared-platform-account
~~~

An AUTH failure on account A does not necessarily impact account B; a quota error on the shared account can impact all tenants sharing it.

When reading `MailSendException`, record:

- Trusted mail job and tenant ID.
- Selected provider/account route.
- Approved sender domain/From identity.
- Failure category.
- Attempt number.
- Unknown/partial outcome if present.
- Retry policy tailored to provider/tenant/purpose.

**Never choose a retry route based on an unverified `From` inside a MIME object.** Tenant routing must come from the job and policy, not from a subject or recipient scraped out of an exception.

If using a backup provider, verify domains, SPF/DKIM/DMARC, bounce routing, quotas, and compatible policies. Never route marketing mail onto a security account just because a batch had a few failed entries.

## 29. Async Email Sending: Do Not Let Exceptions Disappear

A method:

~~~java
@Async("mailExecutor")
public void sendInBackground(
        MimeMessage message) {

    mailSender.send(message);
}
~~~

runs on a worker thread. If `MailSendException` occurs, the original HTTP thread cannot catch it directly as in a synchronous call.

You must:

- Catch failures in the worker and read `getFailedMessages()`.
- Persist attempts/outcomes to a durable store.
- When using `CompletableFuture`, propagate or observe failed futures.
- When using `void @Async`, configure proper exception handling.
- Never just log and forget the job.
- Never rely on thread-local tenant context from a finished request.
- Never treat an in-memory executor as a durable queue.

A `CompletableFuture`-returning submit service might look like:

~~~java
@Async("mailExecutor")
public CompletableFuture<Void> submit(
        MimeMessage message) {

    mailSender.send(message);

    return CompletableFuture.completedFuture(null);
}
~~~

Callers must observe the future's exception. Firing and ignoring the future means failures may never trigger business retries. For durable sending requirements, a transactional outbox fits far better than simply wrapping `mailSender.send` with `@Async`.

## 30. What Status Should an HTTP API Promise?

If an API simply enqueues an outbox job:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"mailJobId":"mail-981","status":"PENDING"}
~~~

This means the send request was accepted per API contract, **not that the email was delivered**.

Even if an endpoint sends synchronously and `JavaMailSender.send` returns without error, never claim the recipient opened the message. The provider can still report a bounce later.

For batch partial failures, an API can choose to:

- Hide SMTP details from public clients; return only authorized job IDs and statuses.
- Track each job as a separate resource.
- Return a batch ID for status polling.
- Never expose internal raw exceptions, provider credentials, or other tenants' recipients.

`getFailedMessages()` is an internal diagnostic map and must never be serialized straight into a JSON HTTP response.

## 31. Do Not Classify Errors via `message.toString()`

Some debug snippets write:

~~~java
Object failed = entry.getKey();

log.warn(
        "Failed message: {}",
        failed.toString()
);
~~~

This can accidentally print recipients, subjects, bodies, or sensitive metadata. Nor should you hash the entire body just to match jobs when you already have job IDs.

A better strategy:

~~~text
Compose:
  jobId -> MimeMessage instance

Send:
  same MimeMessage instance(s)

Catch:
  getFailedMessages -> object identity lookup

Log:
  jobId, attemptId, provider, category
~~~

When using mutable message objects, never mutate content while another thread is sending. Never share one `MimeMessage` across multiple jobs.

## 32. Limits of Logging Raw Exceptions

Even without printing the message object, a stack trace or provider exception text can contain:

- SMTP command details.
- Recipient addresses.
- Provider hosts.
- Fragments of raw responses.
- `From` addresses or subjects.
- Server/account information.

Therefore:

1. Log `exceptionType` and category to metrics.
2. Log stack traces only in systems with proper access control when needed for diagnostics.
3. Avoid logging credentials, OAuth tokens, or full MIME.
4. Mask email addresses when policy requires it.
5. Enforce retention/rotation.
6. Retain correlation IDs/job IDs so you can reconcile without raw bodies.

**Ignoring the failed map** hurts diagnostics; **reading and dumping whole objects** creates security risks. Extract structured, minimal data.

## 33. Unit Testing `getFailedMessages()`

You can construct a synthetic `MailSendException` containing an error map:

~~~java
@Test
void extractsFailedMimeMessage() throws Exception {

    MimeMessage failed =
            new MimeMessage(
                    Session.getInstance(
                            new Properties()
                    )
            );

    MessagingException cause =
            new MessagingException(
                    "Simulated SMTP failure"
            );

    Map<Object, Exception> failures =
            new LinkedHashMap<>();

    failures.put(failed, cause);

    MailSendException exception =
            new MailSendException(
                    "Batch failed",
                    null,
                    failures
            );

    assertEquals(
            1,
            exception.getFailedMessages().size()
    );

    assertSame(
            cause,
            exception.getFailedMessages().get(failed)
    );
}
~~~

Basic imports:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailSendException;
~~~

This unit test demonstrates reading the map; no SMTP connection is required. Build a fixture with two failed messages and one absent message to test diagnostic output and the unknown branch.

### Testing Map Extraction Is Not Testing Delivery

A synthetic `MailSendException` tests your application's adapter logic; it does not prove a real SMTP provider returns the exact same map in every scenario.

## 34. Testing Failure Correlation to Individual Mail Jobs

A test should set up:

~~~text
job-A -> mime-A
job-B -> mime-B
job-C -> mime-C

Exception failed map:
  mime-B -> invalid recipient
  mime-C -> temporary transport
~~~

Assertions:

- Diagnostics record job-B with the right failure type.
- Diagnostics record job-C with the right failure type.
- B's error is never attributed to A.
- A is never **asserted delivered** solely due to its absence from the map.
- If the failed map holds an unknown key, record a correlation miss.
- If the map is empty, record a global/batch-level failure.
- If a key is a `SimpleMailMessage`, do not cast to `MimeMessage`.

A test can use `IdentityHashMap` and `assertSame` to verify the boundary preserves exact object identity.

### Testing an Empty Map Is Crucial

~~~java
@Test
void emptyFailedMapIsNotSuccess() {

    MailSendException exception =
            new MailSendException(
                    "Transport failed"
            );

    FailureAnalysis analysis =
            analyzer.analyze(
                    batchContext,
                    exception
            );

    assertNotEquals(
            SubmissionOutcome.SUBMITTED,
            analysis.batchOutcome()
    );
}
~~~

`FailureAnalysis`, `analyzer`, and `batchContext` are project-defined test seams; the goal is preventing an empty map from being interpreted as submission success.

## 35. Testing `SimpleMailMessage` and `MimeMessage`

If the app uses both send overloads, build separate fixtures:

| Send Path | Test |
| --- | --- |
| `send(SimpleMailMessage)` | Key is simple message per implementation/contract |
| `send(SimpleMailMessage[])` | Mapping multiple simple objects |
| `send(MimeMessage)` | MIME object key and job ID |
| `send(MimeMessage[])` | Partial batch diagnostics |
| `send(MimeMessagePreparator)` | Preparation errors vs. send failures |
| `send(MimeMessagePreparator[])` | Per-MIME preparation stage and SMTP errors |
| Custom mail sender | Key semantics verified against adapter |

Tests missing key correlation can pass for MIME yet throw `ClassCastException` when switching to simple messages in production.

Test the sender integration boundary directly rather than making business services handle unfamiliar key types.

## 36. Integration Testing with an SMTP Test Server

Use GreenMail, Mailpit, or an isolated SMTP server capable of simulating relevant failures:

~~~text
Spring Mail Gateway
    |
    v
JavaMailSender
    |
    v
Isolated SMTP Test Server
    |
    v
Capture / reject / disconnect scenarios
~~~

Scenarios:

1. Send a single valid MIME message.
2. Send a multi-message batch.
3. Server rejects a specific recipient when supported by the test server.
4. Server closes connection before send.
5. Server disconnects mid-transaction.
6. Simulated provider response timeout.
7. Simulated account-level AUTH/TLS errors in a compatible fixture.
8. Classify the failed map and causes.
9. Record corresponding job/attempt IDs.
10. Retry and verify messages are never auto-marked delivered.

Not every SMTP test server can simulate partial recipients, post-DATA response loss, or specific 4xx/5xx codes. Where capabilities fall short, use a fake sender in unit/component tests to produce controlled `MailSendException`s, combined with SMTP server integration tests for real transport checks.

**Never use production SMTP in automated tests**, and never assert on “latest email” in a shared mailbox.

## 37. Testing Unknown Outcomes and Duplicate Windows

A scenario:

~~~text
Attempt 1:
  fake sender records SMTP acceptance
  but simulates lost reply / error before DB status update

Outbox:
  job still not SUBMITTED

Attempt 2:
  worker retries
  fake sender records second submission
~~~

This test demonstrates that an outbox cannot create exactly-once SMTP by itself. Ensure:

- Jobs are never marked `DELIVERED` without basis.
- Attempt logs exist.
- Retry policies account for duplicate possibility.
- Jobs are not lost on worker crashes.
- When using provider idempotency tokens, rely only on documented provider contracts.
- Time-limited token emails are revalidated before retrying.

Separate **recorded failure** from **known no-submission**; they are not synonymous.

## 38. Scenario Test Matrix

| Scenario | Expected Behavior |
| --- | --- |
| Single email sends successfully | Record `SUBMITTED` per contract |
| Single `MailSendException` with failed map | Record job + message cause |
| Empty failed map | Record batch/global failure; never treat as success |
| Failed map contains unrecognized key | Record correlation miss |
| `SimpleMailMessage` key | No bad cast |
| `MimeMessage` key | Correlate to right MIME job |
| Two messages with identical subjects | Never cross-assign jobs |
| One message with multiple recipients | Apply partial-outcome policy |
| Exception cause has nested chain | No lost diagnostics |
| AUTH failure | Alert on account; no hot retries |
| TLS failure | Fix config/trust; never disable verify |
| Hard invalid recipient | Permanent/suppression policy |
| Temporary SMTP 4xx | Backoff/retry if safe |
| SMTP timeout after DATA | `UNKNOWN_OUTCOME` |
| Send succeeded then DB update failed | Accept retry/duplicate risk |
| Bulk batch partial failure | Do not unconditionally mark all failed |
| Template preparation error | Do not treat as SMTP rejection |
| Unreadable attachment | Distinct storage/compose error |
| Async task failure | Durable job updated |
| Provider outage | Backlog alert and rate limit |
| Multiple tenants sharing provider | Never leak another tenant's message/recipient |
| Exception logging | Zero PII/credential leaks |

Not every case needs a real network round-trip. Use unit/fake tests for structured edge cases and SMTP integration tests to verify key transport behaviors.

## 39. Common Implementation Mistakes

### 39.1. Catching `MailException` and Ignoring the Failed Map

Loses message-level details, making it hard to tell which jobs need handling.

### 39.2. Retrying the Entire Batch When One Item Fails

Can duplicate messages that were already accepted.

### 39.3. Treating Every Item Absent from the Map as Delivered

The map is not a delivery ledger; connection/global failures can leave outcomes undetermined.

### 39.4. Treating an Empty Map as No Error

False: the exception still happened, just without per-message entries.

### 39.5. Using Only `getMessageExceptions()` and Guessing Indices

The exception array is not a reliable positional map to batch indices.

### 39.6. Casting Every Key to `MimeMessage`

`SimpleMailMessage` paths can use different key types.

### 39.7. Mapping Failed Messages by Subject

Multiple messages share subjects, causing misattributed jobs.

### 39.8. Mapping Solely by Recipient

One recipient can have multiple jobs; one MIME can address multiple recipients.

### 39.9. Reading Only `getCause()` and Ignoring `nextException`

Jakarta Mail exposes additional nested errors via `getNextException()`.

### 39.10. Parsing Exception Text to Decide Permanence

Message strings are not a stable machine-readable API.

### 39.11. Lumping Connection Failures with Invalid Recipients

One affects the whole account; the other affects one email/recipient.

### 39.12. Retrying Hard 5xx or Message-Too-Large Forever

Creates an unrecoverable queue without fixing data or config.

### 39.13. Treating Every 4xx as Safe for Immediate Retry

Requires backoff, quotas, and inspecting the outcome/SMTP phase.

### 39.14. Ignoring Partial Recipient Acceptance

Risks resending to recipients the provider already accepted.

### 39.15. Treating SMTP Accepted as Delivered

Bounces or deferrals can still occur afterward.

### 39.16. Assuming a Static `Message-ID` Prevents All Duplicates

SMTP has no universal deduplication by `Message-ID`.

### 39.17. Logging the Entire `MimeMessage` on Failure

Exposes recipients, bodies, tokens, and attachment metadata.

### 39.18. Swallowing Exceptions Without Updating Outbox State

Jobs can appear complete or lose retry capability.

### 39.19. Using `@Async` Without Observing Failed Futures

Background thread errors do not automatically return to the request thread.

### 39.20. Keeping One Shared Mutable `JavaMailSender` Across Tenants

Mutating username/password across threads can send via the wrong account.

### 39.21. Missing Job/Attempt Correlation

The failed map has keys, yet the app cannot tell which jobs they belong to.

### 39.22. Failing to Test Empty Maps and Unknown Keys

Code works only on happy failures and breaks on edge failure paths.

## 40. Practice Questions

**Q1.** Why is `catch (MailException)` with a generic log insufficient when sending batches?

Because it skips per-message failures inside `MailSendException#getFailedMessages()`.

**Q2.** What type does `getFailedMessages()` return?

`Map<Object, Exception>`, where keys are message objects and values are the associated exceptions.

**Q3.** Can every key be cast to `MimeMessage`?

No. For simple messages or custom sender adapters, keys can have other types.

**Q4.** Does `getMessageExceptions()` retain job ID mappings?

Not directly. It returns an array of exceptions without object-key context for direct correlation.

**Q5.** If `getFailedMessages()` is empty when `MailSendException` is thrown, did all emails succeed?

No. It only means no per-message entries were populated in the map.

**Q6.** Is a message absent from the failed map guaranteed delivered?

No. The map is not a delivery ledger, and SMTP acceptance is not inbox delivery.

**Q7.** Why is using subject as a correlation key wrong?

Subjects can collide and are not a stable job identity.

**Q8.** How can batch MIME messages be correlated?

Pair each job ID with its MIME object before sending, using object identity when the API preserves the original objects.

**Q9.** What does `SendFailedException` tell you about recipients?

It may expose invalid, valid-sent, and valid-unsent address arrays depending on the transport.

**Q10.** One recipient was accepted while another was rejected. What is the risk of retrying the entire MIME?

The already-accepted recipient may receive a duplicate email.

**Q11.** Besides Java's cause chain, which nested API does Jakarta Mail provide?

`MessagingException#getNextException()`.

**Q12.** If SMTP times out after `DATA`, did the relay definitely not receive the message?

No. It may be an unknown outcome.

**Q13.** Is a template error while preparing MIME guaranteed to be a `MailSendException`?

No. It may be `MailPreparationException` or another error before SMTP.

**Q14.** Should AUTH failures immediately retry all jobs?

No. Hold/back off per account, inspect credentials, and alert.

**Q15.** Does an outbox unique idempotency key guarantee each email is sent only once?

No. It prevents duplicate enqueueing; crashes after SMTP acceptance can still cause resends.

**Q16.** Does `@Async void` let the request thread catch `MailSendException`?

Not by default. Errors must be handled in the worker or via futures/uncaught handlers.

**Q17.** Should `MimeMessage.toString()` be logged on error?

No. It can leak PII/content; log job ID, type, and failure category.

**Q18.** How can batch partial failures be simplified?

Send one message per job/call for clean correlation and independent retries, when throughput allows.

## 41. Mental Model

~~~mermaid
flowchart TD
    A["Mail jobs + job IDs"] --> B["Compose Simple/MIME messages"]
    B --> C["Keep object -> job mapping"]
    C --> D["JavaMailSender.send"]
    D --> E{"Exception?"}
    E -->|"No"| F["SUBMITTED per transport contract"]
    E -->|"Yes"| G{"MailSendException?"}
    G -->|"No"| H["Classify preparation/auth/other"]
    G -->|"Yes"| I["getFailedMessages()"]
    I --> J{"Map has entries?"}
    J -->|"Yes"| K["Map message key to job"]
    J -->|"Empty"| L["Global/unknown failure"]
    K --> M["Inspect per-message exception"]
    M --> N["Jakarta cause/nextException"]
    N --> O["Classify transient/permanent/unknown"]
    O --> P["Retry/hold/fail + attempt log"]
    H --> P
    L --> P
    P --> Q["Observability + provider feedback"]
~~~

Key principles:

1. **`MailSendException` can hold per-message errors**; never log only the outer exception.
2. **`getFailedMessages()` returns `Map<Object, Exception>`**, requiring appropriate key-type handling.
3. **`getMessageExceptions()` holds causes but lacks object-key correlation** compared to the map.
4. **Never cast keys blindly**; `SimpleMailMessage` and `MimeMessage` follow different paths.
5. **Bind job IDs to original message objects before sending**, not by guessing from subject or `To`.
6. **An empty map does not mean no error**, and an item absent from the map is not automatically confirmed delivered.
7. **A multi-recipient MIME can experience partial acceptance**; inspect recipient-level transport details.
8. **Jakarta Mail has both cause and `nextException` chains**, helpful for classification without arbitrary text parsing.
9. **Separate preparation, authentication, SMTP send, and delivery feedback** rather than lumping all errors together.
10. **Timeouts after SMTP `DATA` can leave unknown outcomes**, where retries risk duplicates.
11. **Outboxes support durable intent and retries**, yet do not guarantee exactly-once SMTP.
12. **Retry based on failure category, purpose, backoff, and deadline**, never retrying every `MailSendException` endlessly.
13. **Log job/attempt/provider/category**, never dumping messages or credentials.
14. **Metrics/alerts should track failures, correlation misses, backlogs, and unknown outcomes**, not just a single “send failed” count.
15. **Test populated maps, empty maps, unknown keys, Simple/MIME, partial recipients, and crash windows**.
16. **One job/recipient per send call** is usually easier to manage than complex batches when high accuracy is required.

In Spring Framework Mail, handling `MailSendException` properly does not stop at a `catch` statement. You must **read failed messages**, understand each error's scope, correlate back to real mail jobs, and preserve clear boundaries between **observed failures**, **confirmed submission**, and **uncertain delivery**. Combining diagnostic maps with idempotency, retries/outboxes, structured logging, and failure-path testing lets your system recover from SMTP errors while minimizing both lost emails and duplicates.


