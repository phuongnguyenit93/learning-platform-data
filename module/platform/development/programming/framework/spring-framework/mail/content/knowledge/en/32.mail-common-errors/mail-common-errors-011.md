# Retrying Every Exception with the Same Backoff

In **Spring Framework Mail**, retries are often added after an application starts encountering email sending failures: the SMTP server is busy, connections time out, an account loses sending permissions, or a recipient is invalid. A common quick fix is to **catch every exception and retry sending after the same wait interval**.

For example:

~~~java
try {
    javaMailSender.send(message);
} catch (Exception ex) {
    Thread.sleep(5_000);
    javaMailSender.send(message);
}
~~~

This approach appears to improve reliability, but in practice it can cause many problems:

- **An invalid recipient address** is not fixed just by waiting another 5 seconds.
- **A wrong SMTP password** will keep generating failed AUTH attempts, potentially causing an account lockout.
- **An invalid TLS certificate or hostname** requires fixing configuration, not retrying.
- **Provider rate limits** require a backoff schedule and throttling aligned with quota; retrying simultaneously after a fixed interval can create another traffic spike.
- **Transient SMTP 4xx errors** may be retryable, but not every 4xx code has the same root cause.
- **SMTP 5xx errors** may be recipient rejections, sender policy blocks, message size limits, or other distinct failures; switching providers or retrying blindly both carry risks.
- **A timeout after the SMTP relay receives DATA** may have an undetermined outcome. Resending can create **two emails**.
- **Failures while building a MimeMessage, reading an attachment, or rendering a template** usually need to be handled before transport, not by opening more SMTP connections.
- A sleep/retry loop on a request thread can hold an HTTP request or database transaction open for a very long time.
- Unbounded retries cause worker backlogs, SMTP costs, logs, and alerts to surge dramatically.

This lesson analyzes the design mistake **“Retrying Every Exception with the Same Backoff”** in the **Common Errors** chapter of Spring Framework Mail. The focus is not just how many seconds of backoff to use, but **deciding which error types may be retried, what conditions make retrying safe enough, when to stop, and when to reconcile the SMTP outcome before doing anything next**.

> Core principle: **retrying is a decision based on error semantics and send state, not an automatic reflex inside catch(Exception)**. The exact same exception thrown from a send call might call for retrying, fixing configuration, fixing data, deferring due to rate limits, or holding for reconciliation to avoid duplicates.

## 1. Why is retrying every exception an anti-pattern?

In Spring Framework Mail, errors can originate at different layers:

~~~text
Business event / outbox
       |
       v
Validate recipient and sender
       |
       v
Render template
       |
       v
Build MIME / load attachment
       |
       v
DNS / TCP connection
       |
       v
SMTP STARTTLS / AUTH
       |
       v
MAIL FROM / RCPT TO
       |
       v
DATA / final SMTP reply
       |
       v
Relay queues message
       |
       v
Downstream delivery / bounce
~~~

An exception during rendering differs from an exception during SMTP AUTH. An RCPT TO error differs from a timeout while waiting for the final reply after DATA. Retrying everything with the same mechanism obscures context.

### 1.1. Retrying does not fix a permanent root cause

A syntactically invalid recipient error or a revoked password can fail 10,000 times identically. If the worker keeps trying, the system consumes resources without meaningfully increasing the probability of a successful send.

### 1.2. Retrying can amplify an incident

When an SMTP provider is overloaded, all workers retrying together after 5 seconds create **synchronized traffic peaks**. The provider rejects or throttles again, and the workers retry in unison once more. That is the retry storm phenomenon.

### 1.3. Retrying can break business correctness

If the provider already accepted the message but the client missed the final response, a retry can cause the recipient to receive the email twice. This case is not merely a performance problem.

### 1.4. Three questions are needed before every retry

1. **What is the cause?** Data error, configuration error, transient provider error, rate limit, or unknown outcome?
2. **Is it safe to resend?** Have we confirmed the relay has not accepted the message yet?
3. **Is it still worth sending?** Has the deadline passed, has the token expired, has maxAttempts been exceeded, or has the business event been canceled?

## 2. Distinguishing retry, reschedule, failover, and resend

Actions that are often lumped into the single word “resend”:

| Action | Meaning | Example |
| --- | --- | --- |
| **Retry** | Retrying the same mail intent after an error | Resending when the server temporarily reports 421 |
| **Reschedule** | Deferring processing time to the future | RETRY_WAIT until nextAttemptAt |
| **Failover** | Switching to another SMTP provider/account | Provider A outage, using B if authorized |
| **Reconcile** | Investigating status when the outcome is unclear | Querying the provider about a suspicious submission |
| **Manual resend** | Intentionally sending a new additional email | A support agent resending an invoice |
| **Re-render** | Regenerating HTML/MIME | Template version or token needs updating |

### 2.1. Retry does not mean re-render

If the outbox already stored a valid content snapshot, a transport retry can reuse that content. Unnecessary re-rendering can alter data within the same mail event.

### 2.2. Failover is not always safer than retrying the same provider

If provider A already received the message before the connection dropped after DATA, switching to provider B can also produce duplicates. Switching providers does not eliminate the possibility that relay A already accepted it.

### 2.3. Manual resend must have an audit trail

If a user explicitly requests resending an invoice or confirmation email, that operation should be recorded as a new controlled business action, rather than arbitrarily flipping status SENT back to PENDING.

## 3. Exception types in Spring Mail

**JavaMailSender** can throw exceptions in the **org.springframework.mail.MailException** hierarchy (unchecked). Common types include:

| Spring exception | Common context | Meaning for retry |
| --- | --- | --- |
| **MailAuthenticationException** | SMTP authentication error | Investigate credentials/account; do not retry blindly |
| **MailSendException** | Error sending one or more messages | Must inspect root cause and per-message result |
| **MailPreparationException** | Cannot prepare message | Fix data/template/resource or evaluate root cause |
| **MailParseException** | Error interpreting/parsing mail message | Do not auto-retry if input is fixed |
| **Other MailException** | Wrapper/implementation depends on call path | Classify by actual cause and phase |

You cannot rely on the class name **MailSendException** alone to conclude “this error is retryable”. Inside it may be a transient network failure or a permanently rejected recipient.

### 3.1. Jakarta Mail is a different layer

In Spring Framework 6 / Boot 3 ecosystems, this namespace is commonly used:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.SendFailedException;
import jakarta.mail.AuthenticationFailedException;
import jakarta.mail.internet.AddressException;
~~~

Spring Mail may wrap **MessagingException** or provider-specific exceptions inside MailException. The exact structure depends on the send call, provider, and Jakarta Mail implementation.

### 3.2. Do not inspect only the outermost exception class

~~~text
MailSendException
  |
  +-- MessagingException
        |
        +-- SMTP server reply / linked exception
              |
              +-- IOException / address-specific information
~~~

Looking only at **ex.getClass().getSimpleName()** can lose SMTP reply, recipient, and phase information.

### 3.3. A Spring Mail exception is usually not the final delivery error

When send() returns normally, the relay may have accepted the message, yet a downstream MX may still bounce it later. A delivery webhook/bounce event, if present, is a different signal stream from a synchronous Spring Mail exception.

## 4. Traversing the cause chain and MessagingException linked exceptions

**MessagingException** provides the **getNextException()** API in addition to **getCause()**. If you only walk Throwable.getCause(), the system may miss information located in the linked exception chain.

Example of a safe utility to collect the exception graph:

~~~java
import jakarta.mail.MessagingException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

public final class MailThrowableGraph {

    private MailThrowableGraph() {}

    public static List<Throwable> flatten(
            Throwable root
    ) {
        List<Throwable> result = new ArrayList<>();
        if (root == null) {
            return result;
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Map<Throwable, Boolean> seen =
                new IdentityHashMap<>();

        pending.add(root);

        while (!pending.isEmpty() && result.size() < 64) {
            Throwable current = pending.removeFirst();

            if (seen.put(current, Boolean.TRUE) != null) {
                continue;
            }

            result.add(current);

            Throwable cause = current.getCause();
            if (cause != null) {
                pending.addLast(cause);
            }

            if (current instanceof MessagingException mail) {
                Exception next = mail.getNextException();

                if (next != null) {
                    pending.addLast(next);
                }
            }
        }

        return result;
    }
}
~~~

### 4.1. Why use IdentityHashMap?

The exception graph may reference the same object through multiple links or unusual cycles. Identity-based tracking and a 64-node limit help prevent infinite traversal.

### 4.2. Flattening alone does not decide retries

The utility only gathers exception nodes. A classifier also needs the **SMTP phase**, reply code, provider context, and whether the relay may already have accepted the message.

### 4.3. Do not log the entire exception graph at every level

Stack traces and provider reply text can contain email addresses, hosts, or internal metadata. Log errorCategory, SMTP code, and correlation ID as needed; keep full diagnostics only in environments with appropriate authorization and sanitization.

## 5. Retry decision matrix by error type

A starter matrix:

| Error type | Example | Default action |
| --- | --- | --- |
| **Invalid recipient syntax** | AddressException | STOP and fix data |
| **Recipient permanently rejected** | 5.1.1 with matching context | STOP/suppress address per policy |
| **SMTP AUTH invalid** | 535, wrong credentials | STOP; fix account/secret |
| **TLS/certificate misconfiguration** | SSLHandshakeException | STOP; fix trust/hostname |
| **Missing attachment/template** | Deterministic resource error | STOP or fix data |
| **Provider throttling** | Classified throttle response | RETRY with provider-aware delay |
| **Temporary SMTP rejection** | 421/450/451 depending on context | RETRY with backoff |
| **Connection failed before submission** | ConnectException before DATA | RETRY if evidence shows not accepted |
| **Timeout after DATA** | Lost final reply | HOLD/RECONCILE, avoid blind retry |
| **Partial recipient result** | Some RCPT TO rejected | RETRY selectively, do not resend entire batch |
| **Unknown/unclassified** | Insufficient phase/reply | INVESTIGATE/HOLD or cautious policy |
| **Deadline expired** | Reset link/OTP expired | STOP even if error is transient |
| **Max attempts exhausted** | Exceeded retry budget | STOP/DEAD_LETTER |

This is a **suggested policy**, not an automatic rule to apply blindly to every system. A single SMTP code or exception class is not sufficient on its own to prove retry safety.

### 5.1. Category and action are two separate fields

Record **errorCategory=rate_limit** and **retryAction=reschedule**. Do not turn every category into a fixed retryable boolean when context differs.

### 5.2. Backoff does not replace classification

Even with a one-hour wait interval, retrying a definitely wrong password remains futile. Classification and safety checks must come before delay calculation.

### 5.3. Retries must consider email content

A marketing email can be delayed for a long time; an about-to-expire OTP should not wait 30 minutes. Policy should consider **mailKind**, deadline, and importance.

## 6. Invalid recipient addresses do not resolve after backoff

Example:

~~~text
Input recipient: "alice@@example.org"
Stage: address validation / MIME prepare
Category: invalid_address_syntax
Recommended: stop and correct data
~~~

In Jakarta Mail, an **AddressException** can occur when parsing/validating an address.

### 6.1. Valid syntax does not prove the mailbox exists

InternetAddress can validate syntax at an appropriate level, but it does not verify that the destination server actually has that mailbox.

### 6.2. SMTP 550 needs context

Not every 550 means “mailbox does not exist”. It can reflect sender policy or content restrictions. If the enhanced code is 5.1.1 and the server reply genuinely indicates user unknown, retrying is usually unhelpful, though classification must come from reliable signals.

### 6.3. Do not retry an invalid recipient across multiple providers

Sending the same invalid address through providers A, B, and C only increases errors and cost. Maintain recipient-level status to avoid blind resends.

## 7. SMTP authentication errors require fixing configuration

Example:

~~~text
SMTP AUTH -> 535
Spring: MailAuthenticationException
Category: auth_invalid
Action: stop, investigate secret/account
~~~

Possible causes:

- Username/password changed.
- SMTP account locked/disabled.
- Provider requires an App Password, OAuth, or another AUTH mode.
- Secret was not deployed properly.
- Account lacks sending permission under policy.

### 7.1. Why is retrying every 5 seconds dangerous?

It generates repeated failed logins, which can trigger lockouts, abuse alerts, or rate limits. A secret issue can escalate into a longer outage.

### 7.2. Temporary AUTH differs from invalid credentials

Some AUTH-related SMTP codes can reflect a temporary service issue (such as 454 in the appropriate context), unlike deterministically wrong credentials. Classify by reply and provider semantics rather than treating every AuthenticationFailedException identically.

### 7.3. Do not enable debug logging in a way that exposes credentials

Never log passwords, bearer tokens, or AUTH payloads. Only log allowlisted accountAlias, providerAlias, and errorCategory.

### 7.4. Retry after fixing the secret

Once configuration is resolved, unexpired mail events can be returned to the queue through a controlled procedure; there is no need to keep workers continuously retrying throughout an outage.

## 8. TLS errors cannot be solved by waiting in unison

Example errors:

~~~text
SSLHandshakeException
PKIX path building failed
No subject alternative name matching hostname
Unsupported protocol / cipher mismatch
~~~

An invalid certificate will not become valid simply by waiting another 10 seconds, unless infrastructure or the provider actually changes.

### 8.1. Fix the root cause

Inspect the endpoint, STARTTLS vs implicit TLS, truststore, certificate chain, hostname verification, and supported protocols.

### 8.2. Do not disable certificate validation to make retries succeed

Disabling hostname checking or bypassing trust validation can lead to insecure connections. That is not a retry strategy.

### 8.3. Temporary TLS outages can happen, but do not guess blindly

A transiently failing edge endpoint may recover, but policy still needs classification and retry limits. If the error is a certificate/hostname mismatch, the default action should be fixing configuration.

## 9. Mail preparation errors differ from transport errors

Examples:

- Template rendering fails.
- Important placeholder is missing.
- Subject contains disallowed data.
- Attachment path does not exist.
- File exceeds size limit.
- MIME content is invalid.
- InputStreamResource cannot be reopened.
- Blocked because the tenant lacks permission to use the From identity.

These errors occur **before or during message creation/serialization**, not necessarily due to an SMTP server issue.

### 9.1. Errors can surface late

An attached resource may only be read when Jakarta Mail serializes the message during send(). In that case, an I/O error can appear inside MailSendException even though the root cause is the attachment source.

### 9.2. Do not label every IOException as provider down

If a file resides on object storage or local disk, an IOException may come from the resource. Instrumenting the phase and resource loading helps classify accurately.

### 9.3. Data errors must be fixed or marked terminal

Retries should not loop endlessly over the same template with bad input data. Check retry conditions, data sources, deadlines, and access permissions.

## 10. SMTP reply codes: 4xx and 5xx

In SMTP, reply codes typically use the first digit to indicate the status class.

| Group | General meaning | Retry? |
| --- | --- | --- |
| **2xx** | Positive completion | Not an error to retry |
| **3xx** | Positive intermediate | Protocol needs to continue |
| **4xx** | Transient negative completion | May retry after an appropriate delay |
| **5xx** | Permanent negative completion | Usually stop or fix condition |
| **No reply** | Connection/timeout | Must inspect phase and certainty |

### 10.1. 421

Usually relates to service not available or closing the connection. Can signal a transient outage; inspect provider context, volume, and stage.

### 10.2. 450, 451, 452

Can reflect a mailbox temporarily unavailable, a local processing error, or insufficient system storage depending on SMTP context. Do not assume all three share the same delay.

### 10.3. 535

Typically relates to invalid or rejected AUTH credentials. This is not a recipient error and should not be hammered with retries.

### 10.4. 550, 552, 553, 554

Can indicate recipient, policy, size, or transaction failure, depending on command position and enhanced code. Do not classify by the 3-digit code alone while ignoring context.

### 10.5. 4xx does not always mean “safe to resend”

If the response is lost after DATA, the client does not know whether the relay accepted the message. A network failure at that point must be managed as an **ambiguous outcome**, even though other attempts may retry after a clear SMTP 4xx.

## 11. Enhanced status codes help classify more deeply

Some SMTP responses provide structured enhanced status codes:

~~~text
5.1.1  Mailbox/user not found (common usage)
5.7.8  Authentication credentials invalid (common usage)
4.7.0  Temporary policy/security-related condition
4.2.2  Mailbox full (may be temporary)
~~~

### 11.1. Do not treat enhanced codes as absolute truth

Providers may have different mappings and messages. Preserve **SMTP stage**, the 3-digit code, the enhanced code if available, and provider-specific documented semantics.

### 11.2. Do not use raw reply text as a retry key

A reply may contain a specific recipient or host. Using the full string as a key/tag makes policy unstable and increases metrics cardinality.

### 11.3. Classify where the best data exists

JavaMailSender has no standard API that always returns complete SMTP replies and phases across every provider. The Jakarta Mail/provider exception layer or a specialized integration may hold richer details; if unavailable, record **unknown** instead of fabricating.

## 12. Rate limits require a different wait strategy than ordinary transient errors

If a provider reduces quota or is throttling, retrying after 2 seconds may still be earlier than when the provider is ready.

Example:

~~~text
Provider: smtp-provider-a
Account: transactional
Error: throttled
Recommended by local policy: backoff at least 60s
Current concurrency: 50 connections
~~~

### 12.1. Do not use one delay for every account/provider

Provider A has a different quota than provider B; a security account may have a different priority than marketing. Backoff can vary by **providerAlias/accountAlias/mailKind** and capacity policy.

### 12.2. Do not assume SMTP has a standard Retry-After header like HTTP

HTTP 429 may include **Retry-After**. SMTP does not have a standard Retry-After header used uniformly across every reply like HTTP. If a provider gives specific delay guidance, it must be **provider-specific and verified** data.

### 12.3. Rate limiting and backoff are two different layers

- Backoff: decides **when** an event is retried.
- Rate limiting: decides the **rate** and **concurrency** of attempts per provider/account.

Retrying with the right delay while still letting 1,000 workers send together can still get throttled.

### 12.4. Retry-After when using a provider HTTP API

If the system uses an email HTTP API instead of SMTP, HTTP Retry-After may be applied when the provider supports it and the response is trustworthy. Do not blindly copy HTTP handling into SMTP.

## 13. Network errors: distinguishing before and after submission

Some exceptions:

~~~text
UnknownHostException
ConnectException
SocketTimeoutException
SocketException: Connection reset
SSLException
IOException during MIME transfer
~~~

These classes **do not by themselves tell you** whether the relay already received the message.

### 13.1. DNS/connection failure before the SMTP transaction

If it is certain no connection was established, no message could have been accepted by the relay on that attempt. Retrying with backoff can be appropriate after checking provider health.

### 13.2. Timeout during STARTTLS/AUTH

Usually happens before DATA, but you need to know whether the same SMTP session was still active. Do not infer phase solely from an IOException class name.

### 13.3. Timeout while transferring DATA

The client may have transmitted part of the message. The provider may reject it or drop the connection; handle according to certainty of acceptance.

### 13.4. Losing the final reply after DATA

This is the most critical case: the provider may have accepted the message, yet the final reply never reached the client. A fixed backoff cannot resolve this uncertainty.

## 14. UNKNOWN_OUTCOME and duplicate send risk

A timeline:

~~~text
Client                            SMTP relay
  |-- MAIL FROM ---------------------->|
  |<-- 250 ---------------------------|
  |-- RCPT TO ------------------------>|
  |<-- 250 ---------------------------|
  |-- DATA -------------------------->|
  |<-- 354 ---------------------------|
  |-- message bytes + final dot ----->|
  |                                   |
  |        relay may commit mail      |
  |<--- final 250 reply lost ---------X
  |
  +-- SocketTimeoutException
~~~

The application observes an exception, yet **does not know for sure** whether the relay accepted the message.

### 14.1. Why is retrying unsafe?

If the relay accepted it, retrying on the same provider or a backup provider can create a second email. Having the same MIME Message-ID does not guarantee that the SMTP relay will deduplicate it.

### 14.2. Appropriate actions

Several options depending on business requirements:

- Transition to **UNKNOWN_OUTCOME**.
- Store enough mailEventId/attemptId/provider/phase details to reconcile.
- Check the provider dashboard/API/logs if reliable data exists.
- Wait for an observation window.
- Manual review or an explicit policy accepting duplicate risk.
- If retrying, document clearly that this is a risk-bearing decision, not “definitely unsent”.

### 14.3. Do not equate unknown with permanent failure

There is no proof the email was permanently rejected. Yet there is also no proof it is safe to resend immediately. It requires a dedicated state.

## 15. Partial recipient acceptance

For a MimeMessage with multiple recipients:

~~~text
RCPT TO alice@example.net  -> accepted
RCPT TO bob@example.net    -> rejected
RCPT TO carol@example.net  -> accepted
~~~

Jakarta Mail has **SendFailedException**, which can provide:

~~~java
SendFailedException ex = /* received exception */;
jakarta.mail.Address[] invalid =
        ex.getInvalidAddresses();

jakarta.mail.Address[] validSent =
        ex.getValidSentAddresses();

jakarta.mail.Address[] validUnsent =
        ex.getValidUnsentAddresses();
~~~

### 15.1. Do not retry the entire recipient list

If some recipients were already accepted by the relay, resending the whole list can produce duplicates for that group.

### 15.2. Per-recipient outcome

The application may need to persist recipient-level state in access-restricted storage, or design **one mail event per recipient** when sending transactional/personalized emails.

### 15.3. ValidSent does not prove inbox delivery

This is a status reported by the client/provider for the send operation, not confirmation that the recipient opened the email.

### 15.4. Do not log the entire address list

Exception details may contain recipients. When recording metrics, use appropriate categories/counts rather than using addresses as labels.

## 16. Batch send and MailSendException.getMessageExceptions()

Spring JavaMailSender can process multiple mail messages in a single call. When per-message errors occur, **MailSendException** can provide details:

~~~java
import org.springframework.mail.MailSendException;
import java.util.Map;

void inspect(MailSendException ex) {
    Map<Object, Exception> failures =
            ex.getFailedMessages();

    Exception[] messages =
            ex.getMessageExceptions();

    int failedCount = failures.size();
    int exceptionCount = messages.length;

    // Use to record controlled classification;
    // do not retry the whole batch by default.
}
~~~

### 16.1. One outer exception can represent multiple failures

Some messages may have succeeded while others failed. Retrying the whole batch can duplicate the messages that already succeeded.

### 16.2. Do not treat failedMessages as a complete result table

If the API returns information about failed messages, that does not automatically produce an exact result table for every recipient or downstream delivery. Know the exact contract of the sender implementation.

### 16.3. Use batching with clear intent

One message per recipient, or one outbox event per recipient, is usually easier to retry and reconcile in transactional systems. When batching for throughput, partial outcomes must be managed.

## 17. Retry budget: attempt count, deadline, total time

A policy cannot simply be “sleep 5 seconds”. It should include:

- **maxAttempts:** maximum submission attempts for the event.
- **firstAttemptAt:** start timestamp of the retry lifecycle.
- **deadlineAt:** after this time the email no longer has value.
- **baseDelay:** backoff base per category.
- **maxDelay:** application-defined delay ceiling.
- **jitter:** prevents synchronized retries.
- **provider cooldown:** avoids an unhealthy provider/account during outage.
- **rate limit budget:** overall concurrency/throughput.
- **unknown outcome policy:** reconciliation rules.
- **terminal handling:** FAILED, SUPPRESSED, or dead-letter.

### 17.1. Attempt cap is a hard limit

If maxAttempts=5, after 5 failed send attempts a 6th scheduled attempt must not be created simply because cron wakes the worker up.

### 17.2. Deadline is an independent condition

A password reset email whose token expires after 10 minutes should not be sent 30 minutes later, even if SMTP has recovered.

### 17.3. Retry budgets can be per-provider and system-wide

If thousands of messages fail due to a provider outage, each event has its own retry budget, while total attempts must be controlled via a circuit breaker/rate limiter.

## 18. Fixed backoff vs exponential backoff

Suppose an event fails multiple times.

**Fixed backoff:**

~~~text
Attempt 1 -> wait 5s
Attempt 2 -> wait 5s
Attempt 3 -> wait 5s
Attempt 4 -> wait 5s
~~~

**Exponential backoff (e.g., base=2s):**

~~~text
Attempt 1 -> wait 2s
Attempt 2 -> wait 4s
Attempt 3 -> wait 8s
Attempt 4 -> wait 16s
Attempt 5 -> wait 32s
~~~

A commonly used formula:

\[
d_n = \min(d_{\max}, d_{\text{base}}\times 2^{n-1})
\]

where n is the number of the attempt that just failed, starting from 1.

### 18.1. Exponential does not automatically solve every error

Exponential backoff is still inappropriate for fixing an invalid address or wrong AUTH password. **Classify first, compute delay second.**

### 18.2. Max delay and max attempts are different

A 15-minute delay cap does not by itself stop an event from retrying for days. You still need an attempt cap and a deadline.

### 18.3. Backoff does not mean sleeping the thread

It is better to persist **nextAttemptAt** and let a scheduler/outbox worker handle it later, rather than calling Thread.sleep while holding a transaction, HTTP thread, or worker slot.

## 19. Jitter prevents retry storms

If 10,000 events all fail at 12:00:00 and all use a 30-second delay, they may retry almost simultaneously at 12:00:30.

**Full jitter** picks a random value between 0 and the capped exponential delay:

\[
d_n^{\text{jitter}} \sim U(0,d_n)
\]

For example, with a 10-second base and a 40-second exponential delay on an attempt, events can be scheduled across 0–40 seconds instead of firing at once.

### 19.1. Do not use jitter to bypass a provider minimum delay

If the provider has reliable guidance to wait at least 60 seconds, do not pick full jitter and retry after 2 seconds. Combine it with a provider-specific **not-before** bound.

### 19.2. Jitter needs an appropriate randomness source

In production code, ThreadLocalRandom can be used for routine scheduling jitter; unit tests should inject a random source or fake jitter for deterministic assertions.

### 19.3. Jitter does not replace a rate limiter

Spreading retries over time only reduces synchronization. If total load still exceeds quota, separate admission/rate control is needed.

## 20. Provider cooldown, circuit breaker, and backpressure

When an SMTP provider has a systemic outage, per-email retries are not enough.

~~~text
Provider A outage
     |
     +-- Circuit breaker OPEN
     |
     +-- New attempts paused/routed if allowed
     |
     +-- Outbox events remain durable
     |
     +-- Controlled probe/half-open
     |
     +-- Resume at bounded rate
~~~

### 20.1. Circuit breaker handles provider health

A breaker can be driven by systemic error rates, timeouts, or health probes; it **should not** count a recipient 550 as a provider outage and trip the system-wide breaker.

### 20.2. Rate limiting per account/provider

Provider A’s quota of 20 requests/second must not be exceeded just because there are 10 worker pods each allowing themselves 20 requests/second. Split the budget or use a shared limiter scoped to the quota.

### 20.3. When the breaker is OPEN

Do not delete mail outbox events. They can stay in RETRY_WAIT or another waiting state until the provider can be tried again; avoid a hot retry loop.

### 20.4. Half-open should not dump the entire backlog

When the provider has just recovered, limit probe count and traffic ramp-up rate so you do not cause a second outage.

## 21. Difference between category-based and business-priority-based backoff

A reference table **for illustration only**, not a recommended number of seconds for every provider:

| Group | Suggested base delay for modeling | Max delay | Condition |
| --- | --- | --- | --- |
| Connection failure before DATA | A few seconds | A few minutes | Evidence of non-acceptance |
| SMTP temporary 4xx | Tens of seconds | Many minutes | Clear transient reply |
| Provider throttling | Tens of seconds to minutes | Per quota/cooldown | Respect provider guidance |
| Temporary auth infrastructure | Per runbook | Bounded | Not invalid credentials |
| Invalid address | No retry | — | Fix data |
| AUTH invalid | No retry | — | Fix secret/account |
| TLS misconfiguration | No retry | — | Fix transport security |
| Ambiguous after DATA | No auto-retry | — | Reconcile |
| Deadline expired | No retry | — | Suppress/terminal |

### 21.1. Business priority must not override safety

OTP emails are time-sensitive, yet a timeout after DATA still carries duplicate risk. Priority only changes deadline/capacity policy; it does not turn an ambiguous outcome into “definitely unsent”.

### 21.2. Do not prioritize critical emails infinitely

A downed provider needs fail-fast/backpressure, not security messages retrying infinitely every 100 ms simply because they are important.

## 22. Designing FailureFacts to decouple exceptions from decisions

A cleaner design than catch(Exception) is normalizing data from the adapter:

~~~text
FailureFacts:
  errorKind
  smtpPhase
  smtpReplyCode
  enhancedStatusCode
  providerAlias
  accountAlias
  definitelyNotAccepted
  providerMinimumDelay
  attemptNumber
  eventDeadline
~~~

Where:

- **errorKind:** a finite taxonomy such as AUTH_INVALID, THROTTLED, TEMPORARY_SMTP.
- **smtpPhase:** connect, starttls, auth, mail_from, rcpt_to, data, after_data, unknown.
- **definitelyNotAccepted:** true only when there is reliable grounds that the relay did not accept the message on that attempt.
- **providerMinimumDelay:** minimum wait time from the provider/API if reliable guidance exists.
- **eventDeadline:** business cutoff after which we no longer want to send.

### 22.1. Do not infer definitelyNotAccepted from a single exception class

A SocketTimeoutException cannot prove the SMTP outcome without knowing the phase. If data is missing, use false or UNKNOWN; do not set true on your own.

### 22.2. Error classification is a dedicated component

The adapter layer observes/collects exceptions and the SMTP phase. The retry planner layer decides the action from normalized data. The outbox layer persists durable state.

### 22.3. Do not rely solely on regex over getMessage()

Provider wording changes or localization can break policy. Prefer structured replies/enhanced codes, exception types, and phase from trusted sources.

## 23. Java example: error-type-aware RetryPlanner

The example below illustrates a **pure Java decision engine** that does not directly open SMTP connections, making unit testing straightforward. It assumes the transport classifier layer has already determined **FailureKind** and the **definitelyNotAccepted** flag from reliable information.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

public final class MailRetryPlanner {

    public enum FailureKind {
        INVALID_ADDRESS,
        AUTH_INVALID,
        TLS_CONFIGURATION,
        MISSING_RESOURCE,
        PERMANENT_SMTP,
        TEMPORARY_SMTP,
        THROTTLED,
        CONNECT_BEFORE_DATA,
        AMBIGUOUS_AFTER_DATA,
        UNKNOWN
    }

    public enum Action {
        RETRY_LATER,
        STOP,
        RECONCILE
    }

    public record FailureFacts(
            FailureKind kind,
            boolean definitelyNotAccepted,
            Duration providerMinimumDelay
    ) {}

    public record Decision(
            Action action,
            Instant nextAttemptAt,
            String reasonCode
    ) {}

    @FunctionalInterface
    public interface Jitter {
        long pickMillis(long maxInclusive);
    }

    public static Jitter randomJitter() {
        return max -> ThreadLocalRandom.current()
                .nextLong(max + 1);
    }

    private final Clock clock;
    private final Jitter jitter;
    private final int maxAttempts;

    public MailRetryPlanner(
            Clock clock,
            Jitter jitter,
            int maxAttempts
    ) {
        this.clock = Objects.requireNonNull(clock);
        this.jitter = Objects.requireNonNull(jitter);

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive"
            );
        }

        this.maxAttempts = maxAttempts;
    }

    public Decision decide(
            FailureFacts failure,
            int attemptsCompleted,
            Instant deadline
    ) {
        Objects.requireNonNull(failure);
        Objects.requireNonNull(deadline);

        Instant now = clock.instant();

        if (now.isAfter(deadline) || now.equals(deadline)) {
            return new Decision(
                    Action.STOP, null, "deadline_expired"
            );
        }

        if (attemptsCompleted >= maxAttempts) {
            return new Decision(
                    Action.STOP, null, "max_attempts"
            );
        }

        switch (failure.kind()) {
            case INVALID_ADDRESS:
            case AUTH_INVALID:
            case TLS_CONFIGURATION:
            case MISSING_RESOURCE:
            case PERMANENT_SMTP:
                return new Decision(
                        Action.STOP, null, "non_retryable"
                );

            case AMBIGUOUS_AFTER_DATA:
            case UNKNOWN:
                return new Decision(
                        Action.RECONCILE, null,
                        "submission_not_confirmed"
                );

            default:
                break;
        }

        if (!failure.definitelyNotAccepted()) {
            return new Decision(
                    Action.RECONCILE, null,
                    "acceptance_uncertain"
            );
        }

        long baseMillis = switch (failure.kind()) {
            case THROTTLED -> 30_000L;
            case TEMPORARY_SMTP -> 10_000L;
            case CONNECT_BEFORE_DATA -> 2_000L;
            default -> throw new IllegalStateException(
                    "Unrecognized retry category"
            );
        };

        long capMillis = Duration.ofMinutes(15).toMillis();
        long window = baseMillis;

        for (int i = 1;
             i < Math.min(attemptsCompleted, 10);
             i++) {
            window = Math.min(capMillis, window * 2);
        }

        long jitterDelay = jitter.pickMillis(window);

        Duration minimum = failure.providerMinimumDelay() == null
                ? Duration.ZERO
                : failure.providerMinimumDelay();

        if (minimum.isNegative()) {
            minimum = Duration.ZERO;
        }

        long delayMillis = Math.max(
                jitterDelay,
                minimum.toMillis()
        );

        Instant next = now.plusMillis(delayMillis);

        if (!next.isBefore(deadline)) {
            return new Decision(
                    Action.STOP, null,
                    "retry_would_miss_deadline"
            );
        }

        return new Decision(
                Action.RETRY_LATER,
                next,
                "retryable_transient"
        );
    }
}
~~~

### 23.1. Action has three branches

- **RETRY_LATER:** store nextAttemptAt, do not sleep the thread.
- **STOP:** terminal failure/suppression per business rules.
- **RECONCILE:** outcome is not certain enough to auto-resubmit.

### 23.2. definitelyNotAccepted is a safety condition

Even when kind=TEMPORARY_SMTP, if we do not yet know whether the relay accepted the message, the planner routes to RECONCILE. This flag **must not be set based solely on a SocketTimeoutException name**.

### 23.3. Provider floor is respected

If full jitter picks 3 seconds while the provider requires at least 60 seconds, nextAttemptAt is at least 60 seconds from now. This is a delay verified by the classifier/integration, not extracted from a non-existent standard SMTP header.

### 23.4. Deadline is checked both before and after delay calculation

An expiring event will STOP if the next retry time would pass the deadline.

### 23.5. The code sample intentionally omits full production rules

It does not cover per-recipient partial outcomes, circuit breaker state, provider failover, database transactions, per-category attempt budgets, policy configuration, clock/overflow at extreme values, or manual operator overrides. Those belong to the orchestration/persistence layer.

## 24. JUnit 5 test example for RetryPlanner

One benefit of decoupling the planner from transport is deterministic testing without needing an SMTP server.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class MailRetryPlannerTest {

    private final Clock clock =
            Clock.fixed(
                    Instant.parse("2026-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );

    private final MailRetryPlanner planner =
            new MailRetryPlanner(
                    clock,
                    max -> max / 2,
                    5
            );

    @Test
    void invalidAuthStopsImmediately() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.AUTH_INVALID,
                true,
                Duration.ZERO
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(600)
        );

        assertEquals(
                MailRetryPlanner.Action.STOP,
                result.action()
        );

        assertNull(result.nextAttemptAt());
    }

    @Test
    void timeoutAfterDataRequiresReconciliation() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.AMBIGUOUS_AFTER_DATA,
                false,
                Duration.ZERO
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(600)
        );

        assertEquals(
                MailRetryPlanner.Action.RECONCILE,
                result.action()
        );
    }

    @Test
    void throttleRespectsProviderMinimumDelay() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.THROTTLED,
                true,
                Duration.ofSeconds(90)
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(600)
        );

        assertEquals(
                MailRetryPlanner.Action.RETRY_LATER,
                result.action()
        );

        assertEquals(
                clock.instant().plusSeconds(90),
                result.nextAttemptAt()
        );
    }

    @Test
    void deadlineStopsRetry() {
        var facts = new MailRetryPlanner.FailureFacts(
                MailRetryPlanner.FailureKind.THROTTLED,
                true,
                Duration.ofMinutes(5)
        );

        var result = planner.decide(
                facts,
                1,
                clock.instant().plusSeconds(30)
        );

        assertEquals(
                MailRetryPlanner.Action.STOP,
                result.action()
        );
    }
}
~~~

### 24.1. No Thread.sleep needed

Clock.fixed and a deterministic jitter function make it possible to test nextAttemptAt results without waiting in real time.

### 24.2. Safety tests matter more than delay math tests

Make sure invalid AUTH stops, timeout after DATA does not auto-retry, provider minimum delay is preserved, and the deadline is not exceeded.

### 24.3. The test only verifies the planner

It does not validate the exception classification layer, database claim, or SMTP transport. Separate tests are needed for those layers.

## 25. Classifying from MailException requires caution

A classifier can start with:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.MailException;

String classifyHighLevel(MailException ex) {
    if (ex instanceof MailAuthenticationException) {
        return "auth_or_account";
    }

    if (ex instanceof MailParseException) {
        return "parse";
    }

    if (ex instanceof MailPreparationException) {
        return "prepare";
    }

    return "needs_transport_inspection";
}
~~~

The code above **intentionally does not return a retryable boolean yet**. Reason: the same class can mask multiple causes and does not provide the SMTP phase.

### 25.1. Inspect nested exceptions

You can use MailThrowableGraph.flatten(ex) to locate AddressException, SendFailedException, IOException, or provider-specific SMTP exceptions. Yet you still need to know the server outcome and phase.

### 25.2. Unclassified errors must have a safe fallback

If retry safety cannot be proven, do not automatically label it transient. Route it to an investigation queue or a cautious policy.

### 25.3. Do not classify solely by contains("timeout")

Exception messages can change language, wording, provider, or contain user data. Use structured details and controlled instrumentation.

## 26. Transactional outbox instead of sleep loops

Anti-pattern:

~~~java
@Transactional
public void sendNow() {
    mailSender.send(message);

    Thread.sleep(10_000);

    mailSender.send(message);
}
~~~

This snippet can both send duplicates and hold the transaction/thread open for a long time.

A sturdier model:

~~~text
Business transaction
     |
     +-- update business record
     +-- insert mail_outbox event
     |
     v
COMMIT
     |
     v
Scheduled worker
     |
     v
Claim due event
     |
     v
Prepare + submit via JavaMailSender
     |
     v
Classify result
     |
     +-- SENT
     +-- RETRY_WAIT with nextAttemptAt
     +-- FAILED
     +-- UNKNOWN_OUTCOME
~~~

### 26.1. Outbox stores the send intent durably

When the application restarts, non-terminal events remain in the database instead of being lost with an in-memory thread.sleep.

### 26.2. Do not hold a DB transaction across an SMTP call

SMTP does not participate in the same database transaction. Sending inside a transaction and then rolling back can cause the recipient to receive an email even though business data rolled back.

### 26.3. Outbox does not create exactly-once SMTP

If the relay accepts the message but the worker crashes before recording SENT, a re-claim can send a duplicate. Recovery/unknown handling is needed.

## 27. Database schema for retries and auditing

PostgreSQL example:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL,
    mail_kind VARCHAR(64) NOT NULL,
    payload_reference TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts_completed INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at TIMESTAMPTZ,
    claim_owner VARCHAR(128),
    claim_token UUID,
    claim_version BIGINT NOT NULL DEFAULT 0,
    claim_until TIMESTAMPTZ,
    last_error_category VARCHAR(64),
    last_provider_alias VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(business_key, mail_kind)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox(status, next_attempt_at);

CREATE TABLE mail_attempt (
    attempt_id UUID PRIMARY KEY,
    mail_event_id UUID NOT NULL
        REFERENCES mail_outbox(id),
    attempt_number INTEGER NOT NULL,
    provider_alias VARCHAR(64),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(32) NOT NULL,
    error_category VARCHAR(64),
    smtp_reply_code VARCHAR(16),
    smtp_phase VARCHAR(32),
    duration_ms BIGINT,
    UNIQUE(mail_event_id, attempt_number)
);
~~~

### 27.1. nextAttemptAt is only for retry-eligible events

Do not blindly set next_attempt_at to now()+5s on every exception. STOP/UNKNOWN_OUTCOME require different states so the scheduler does not keep picking them up.

### 27.2. Deadline and maxAttempts belong to policy

Store deadline on the event; maxAttempts can come from policy by mailKind. Avoid letting one worker use a different value without versioning/consistency.

### 27.3. Attempt history aids reconciliation

Record per-attempt provider, phase if known, category, and elapsed duration. If a process crashes, a STARTED attempt with no final result is a signal requiring investigation.

### 27.4. Do not store credentials/raw MIME in telemetry tables

Payloads may contain sensitive information, so store a reference to protected storage with an appropriate retention policy.

## 28. Atomic claim to prevent two workers from retrying simultaneously

A scheduler with multiple replicas must never do:

~~~text
Worker A: SELECT retry due
Worker B: SELECT retry due
Both call JavaMailSender.send
~~~

With PostgreSQL, a claim pattern:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= now()
      AND (
          deadline_at IS NULL
          OR deadline_at > now()
      )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox m
SET status = 'PROCESSING',
    claim_owner = :worker_id,
    claim_token = :new_token,
    claim_version = m.claim_version + 1,
    claim_until = now() + INTERVAL '90 seconds',
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING m.id, m.claim_version, m.claim_token;
~~~

### 28.1. Commit before SMTP

The transaction only claims rows and commits; JavaMailSender.send runs afterward. Keeping the database transaction open during send does not achieve atomicity with SMTP.

### 28.2. Updates must verify ownership

When transitioning to RETRY_WAIT, SENT, or FAILED:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY_WAIT',
    next_attempt_at = :next_attempt_at,
    last_error_category = :category,
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

If affected rows = 0, the owner’s lease may have expired or been reclaimed. Never overwrite unconditionally.

### 28.3. Lease expiry does not prove unsent

The worker might already be past DATA. A stale worker is rejected from updating the database, yet the SMTP side effect may already have occurred.

## 29. A safe retry orchestrator at a conceptual level

~~~java
public void processClaimed(ClaimedMail job) {
    try {
        MimeMessage mime = composer.compose(job);

        attemptStore.recordStarted(job);
        transport.send(mime, job.providerAlias());

        outbox.markSentIfOwned(job);
        attemptStore.recordReturnedOk(job);

    } catch (RuntimeException ex) {
        FailureFacts facts =
                classifier.classify(ex, job.transportContext());

        RetryDecision decision =
                retryPlanner.decide(
                        facts,
                        job.attemptsCompleted(),
                        job.deadline()
                );

        switch (decision.action()) {
            case RETRY_LATER ->
                    outbox.rescheduleIfOwned(
                            job,
                            decision.nextAttemptAt(),
                            facts.kind()
                    );

            case STOP ->
                    outbox.failIfOwned(job, facts.kind());

            case RECONCILE ->
                    outbox.markUnknownIfOwned(
                            job,
                            facts.kind()
                    );
        }
    }
}
~~~

**ClaimedMail, composer, transport, classifier, attemptStore, outbox, and RetryDecision** here are illustrative application abstractions. They are not built-in Spring Framework Mail classes.

### 29.1. Production needs refined state-recording order

In the example, if SMTP send succeeds but markSentIfOwned fails, the catch block could receive a database exception. **Never classify a database failure as an SMTP failure and retry the message.** A production implementation must separate the **send try/catch** from the **state persistence try/catch**, explicitly recording the transport outcome before handling state-write errors.

### 29.2. Separate rendering errors from SMTP errors

If composer.compose throws an exception, do not create an SMTP attempt. Policy must classify it as a preparation failure rather than incrementing the transport retry count.

### 29.3. Do not treat the example as complete copy-paste code

It illustrates the decision branches. You still need durable transaction boundaries, metadata, callbacks, and error handling tailored to your project.

## 30. Spring Retry: when to use it?

**Spring Retry** helps build retry policies and backoff for synchronous operations. Yet using a single generic annotation for every exception remains an anti-pattern.

A simple configuration such as:

~~~java
@Retryable(
    retryFor = Exception.class,
    maxAttempts = 5,
    backoff = @Backoff(delay = 5000)
)
public void send(MimeMessage message) {
    javaMailSender.send(message);
}
~~~

clearly shows the problem: it retries **every Exception**, with the same delay, without considering SMTP phase, without checking whether the relay already accepted it, without considering mail kind/deadline, and it can sleep on a request thread.

### 30.1. The annotation above is only an anti-pattern example

Using these annotations requires Spring Retry dependencies and supporting configuration. It should not be copied into production.

### 30.2. Retry policy can be used per exception category

Spring Retry provides RetryTemplate, retry policies, backoff policies, and hooks/listeners suitable for many use cases. However, the **classifier must be reliable** and must distinguish retryable errors from ambiguous outcomes.

### 30.3. Synchronous retry fits short, bounded operations

For example, a connect failure definitely occurring before DATA with at most one retry and a short total deadline can be handled synchronously inside a worker. Retries spanning multiple minutes should use outbox nextAttemptAt.

### 30.4. @Retryable does not solve self-invocation

In standard Spring AOP proxy setups, calling an annotated method from another method on the same instance may bypass the proxy. Do not assume the annotation takes effect merely because it appears in source code.

## 31. Distinguishing retries in workers from retries in providers

An application can have multiple retry layers:

~~~text
HTTP request / event listener
        |
        v
Outbox worker retry
        |
        v
Spring Retry around JavaMailSender
        |
        v
SMTP provider queue/retry to next MX
~~~

Without control, a single event can be attempted far more times than intended.

### 31.1. Retry amplification

For example, worker maxAttempts=5 while the JavaMailSender wrapper retries 3 times per attempt. Total SMTP invocations can reach 15, even if the outbox dashboard only shows 5 worker attempts when tracking sits at the wrong layer.

### 31.2. One layer owns the retry decision

For critical email sending, designate a single **primary retry orchestrator** owning maxAttempts, deadline, and nextAttemptAt. Lower-level retries, if any, must be explicitly measured and must not obscure side effects.

### 31.3. Provider downstream retries are independent

Once the SMTP relay receives the message, the provider can independently retry delivery to the receiving MX. The application should not send extra copies simply because a downstream delivered webhook has not arrived immediately.

## 32. Multi-provider failover requires its own policy

An architecture:

~~~text
Mail event
    |
    v
Routing policy
    |
    +-- provider A / account A
    |       |
    |       +-- attempt 1 -> connect failure
    |
    +-- provider B / account B
            |
            +-- attempt 2 -> success
~~~

### 32.1. Failover only when appropriate

Provider B must be authorized to use the From domain, have proper SPF/DKIM/DMARC configuration, and meet quota/policy requirements.

### 32.2. Do not fail over to evade recipient/content policy

If A rejected due to an invalid recipient, sender authorization, or valid policy enforcement, switching to B to try bypassing rejection may be non-compliant and will not improve deliverability.

### 32.3. UNKNOWN_OUTCOME persists across failover

If A may have accepted after DATA, resending via B carries the same duplicate risk as retrying on A.

### 32.4. Per-attempt attribution

Record the providerAlias and accountAlias **actually used on that attempt**. Do not attribute B’s success to A merely because A is the mail event’s default provider.

## 33. SLAs, deadlines, and distinguishing transactional vs marketing emails

Different email types have different time sensitivity:

| Mail kind | Characteristics | Retry considerations |
| --- | --- | --- |
| **Password reset** | Token expires | Stop after deadline, do not send useless links |
| **OTP/security alert** | Time-sensitive and confusing if duplicated | Unknown timeouts require duplicate protection |
| **Order confirmation** | Transactional accuracy needed | Outbox and idempotency by business key |
| **Invoice** | Fixed content/snapshot | Preserve exact version; attachment access |
| **Marketing newsletter** | High volume, tolerates delay | Rate limiting and quota |
| **Daily digest** | Periodic content | Idempotency by business date |

### 33.1. Do not unintentionally change content on each retry

If templates are rendered from live data on the third retry, the same mailEventId can contain different information than on the first attempt. A snapshot/version policy is needed.

### 33.2. Retry deadline and token TTL

If the token is no longer valid at retry time, STOP or create a new business intent per policy instead of sending an expired token.

### 33.3. Observe business time-to-submit

A mail event might sit 10 minutes in RETRY_WAIT even though the final send call took only 500 ms. Track event-to-relay latency alongside SMTP attempt latency.

## 34. Metrics: do not only count retry count

A suggested set of metrics:

| Metric | Low-cardinality tags | Meaning |
| --- | --- | --- |
| **mail.smtp.submit.attempts** | provider, outcome | Actual SMTP invocations |
| **mail.smtp.submit.duration** | provider, outcome | How long send calls take |
| **mail.retry.decisions** | kind, action | Retry/stop/reconcile decisions |
| **mail.retry.scheduled** | category, provider | Events moved to RETRY_WAIT |
| **mail.retry.delay** | category | Chosen delay |
| **mail.retry.exhausted** | kind, category | MaxAttempts/deadline |
| **mail.outbox.pending** | mailKind/priority | Backlog |
| **mail.outbox.retry_wait** | kind | Waiting events |
| **mail.outbox.oldest_pending_age** | priority | Starvation |
| **mail.smtp.unknown_outcomes** | provider | Ambiguous outcomes |
| **mail.provider.throttled** | provider/accountTier | Throttle |
| **mail.circuit_breaker.state** | provider | Whether provider is paused or open |
| **mail.event.terminal_failed** | kind, category | Undeliverable business intents |

### 34.1. Count retry decisions separately from SMTP attempts

An event can be rescheduled in the database without having executed a send. Do not treat mail.retry.scheduled as attempt count.

### 34.2. Do not use recipient or mailEventId as tags

These values have high cardinality and may be PII. Use them in access-controlled structured logs when detailed tracing is required.

### 34.3. Observing success after retry does not erase the prior failure

If attempt 1 fails and attempt 2 succeeds, both one failure and one success must be recorded. The business event may complete successfully, yet provider health still had a real error.

## 35. Structured logging for retry decisions

Example:

~~~json
{
  "event": "mail.retry.decision",
  "mailEventId": "event-42",
  "attemptId": "attempt-2",
  "mailKind": "order_confirmation",
  "providerAlias": "smtp-provider-a",
  "errorCategory": "temporary_smtp",
  "smtpPhase": "rcpt_to",
  "smtpReplyCode": "450",
  "action": "RETRY_LATER",
  "reasonCode": "retryable_transient",
  "attemptsCompleted": 2,
  "nextAttemptAt": "2026-11-12T10:05:00Z"
}
~~~

An unknown event:

~~~json
{
  "event": "mail.retry.decision",
  "mailEventId": "event-43",
  "attemptId": "attempt-1",
  "providerAlias": "smtp-provider-a",
  "smtpPhase": "after_data",
  "errorCategory": "timeout_unknown",
  "action": "RECONCILE",
  "reasonCode": "submission_not_confirmed"
}
~~~

### 35.1. Log reason code, not body

You do not need the email body, Subject, OTP, password, or full attachments to understand why a retry was scheduled.

### 35.2. Audit manual overrides

If an operator forces a retry on an UNKNOWN_OUTCOME, record actor, approval, business justification, and accepted duplicate risk in a suitably authorized audit system.

### 35.3. Do not use raw exception.getMessage as a metric tag

Reply text can contain addresses, hosts, customized content, and many distinct values. Map to a finite taxonomy.

## 36. Tracing to see where time is spent

A flow:

~~~text
mail.worker.process
       |
       +-- mail.validate
       +-- mail.render
       +-- mail.mime.build
       +-- mail.route.select
       +-- mail.smtp.submit
       |       provider=A
       |       outcome=failure
       |
       +-- mail.retry.plan
       |       action=RETRY_LATER
       |
       +-- mail.outbox.reschedule
~~~

### 36.1. Retrying after several minutes is an async flow

You do not need to keep a single trace/span open across the entire wait interval. Attempts can be linked via mailEventId and appropriate span links/correlation fields.

### 36.2. Timeout and queue delay must be separated

A slow 30-second SMTP send differs from an event waiting 30 minutes in backoff. Measure both attempt duration and event-to-submit latency.

### 36.3. Do not put PII into tracing attributes

The tracing backend also stores data. Never automatically place recipients, HTML content, or SMTP credentials into spans.

## 37. Alerting on retry storms and non-recoverable errors

Actionable alerts:

- Invalid AUTH rising on the same accountAlias → stop retries, check secret.
- TLS handshake/certificate failures rising → investigate config, do not disable TLS.
- Retry attempts/second spiking → check outage and backoff policy.
- Provider continuously throttled → reduce concurrency, check quota.
- Oldest RETRY_WAIT/pending exceeding SLA → check capacity/routing.
- UNKNOWN_OUTCOME rising → inspect network after DATA and duplicate risk.
- Terminal failures rising → classify invalid address/content/config.
- Circuit breaker OPEN for long duration → identify provider and recovery runbook.
- Retry budget exhausted rising → review deadline/maxAttempts.
- Mail events with many attempts but few completions → check for retry amplification.

### 37.1. Alerts need appropriate sample sizes

A 50% failure rate across 2 attempts differs from 50% across 10,000 attempts. Look at failure count, rate, sample window, and mailKind/provider mix.

### 37.2. Do not respond to rate limit alerts by speeding up

A throttling provider usually needs load reduction, not spinning up more workers.

## 38. Fake sender tests: must not send more than allowed

A test can use **Mockito JavaMailSender**, a fake clock, and a durable repository test double:

~~~text
Given:
  One event E
  maxAttempts = 3
  Provider raises temporary failure before DATA
When:
  Worker processes attempts at eligible times
Then:
  E may be attempted at most 3 times
  nextAttemptAt always respects backoff
  No attempt is launched before nextAttemptAt
  After exhaustion E is terminal
~~~

### 38.1. Production SMTP is not needed

Unit tests should mock JavaMailSender. Integration tests use an SMTP capture server in a controlled environment to avoid accidentally sending to real recipients.

### 38.2. Simulate exception causes

Test MailAuthenticationException, MailSendException with nested causes, AddressException, SendFailedException, and errors with/without SMTP replies.

### 38.3. Test missing phase

If the classifier does not know whether the timeout occurred before or after DATA, the planner must not assert definitelyNotAccepted=true.

### 38.4. Test partial recipients

If a batch has recipients already accepted, retrying must not blindly resend to the entire group.

## 39. Test matrix by error and action

| Scenario | Expected policy |
| --- | --- |
| Address syntax invalid | STOP |
| Mailbox unknown 5.1.1 with clear source | STOP/suppress |
| SMTP AUTH 535 invalid | STOP + alert |
| TLS hostname mismatch | STOP + alert |
| Template missing variable | STOP/fix input |
| Attachment missing | STOP/fix resource |
| Temporary SMTP 421 confirmed not accepted | RETRY_LATER |
| Throttling with minimum delay | RETRY after appropriate floor |
| Connection refused before DATA | RETRY_LATER with budget |
| Timeout after DATA | RECONCILE |
| Unknown exception/phase | RECONCILE or cautious policy |
| Partial recipient acceptance | Retry unaccepted group appropriately |
| Deadline expired | STOP |
| MaxAttempts reached | STOP |
| Provider breaker OPEN | Reschedule/suspend according to policy |
| Worker crash after SMTP success | Do not replay without reconciliation |
| Retry planner returns RETRY_LATER | nextAttemptAt persisted, no sleep |
| Two workers claim same event | Only one valid owner |
| Fencing token stale | State update rejected |

### 39.1. Test on a database with matching semantics

If using PostgreSQL FOR UPDATE SKIP LOCKED, concurrency tests should run against real PostgreSQL/Testcontainers. Mocks/H2 do not emulate row locking by default.

### 39.2. Crash-window tests must not claim exactly-once

You can simulate fake SMTP accept followed by a worker crash before the DB update. The test will show that reconciliation and a duplicate policy are needed, and cannot prove the SMTP provider will deduplicate on its own.

### 39.3. Deterministic deadline and jitter tests

Use Clock.fixed, fake jitter, and assertions on nextAttemptAt instead of flaky Thread.sleep calls.

## 40. Comparing three retry implementation approaches

| Approach | Benefits | Limitations |
| --- | --- | --- |
| **Catch + Thread.sleep** | Very simple | Blocks threads, not durable, usually unclassified, storm-prone |
| **Spring Retry in worker** | Policies/backoff for synchronous calls | Needs classifier/safety, not durable across crashes |
| **Transactional outbox + nextAttemptAt** | Durable, long-term rescheduling, multi-attempt observability | Needs schema, workers, claim/lease/recovery |
| **Broker delayed retry/DLQ** | Infrastructure queueing support | Still needs idempotency and SMTP unknown handling |

### 40.1. Do not use Spring Retry to bypass true SMTP semantics

No matter how powerful the retry library is, it cannot prove the relay did not accept after DATA.

### 40.2. Outbox alone does not stop retry storms

If the classification policy is wrong or rate limiting is missing, an outbox can still generate millions of retry attempts. Durable storage and sound policy must go together.

### 40.3. Choose one primary orchestration layer

If Spring Retry, worker retries, and broker delivery redelivery are all enabled, calculate total transport invocations and ensure accurate accounting.

## 41. Runbook when emails keep failing

When on-call sees the same mail event retried repeatedly:

1. Find mailEventId, attempt history, providerAlias, and mailKind.
2. Check whether the error is preparation, SMTP AUTH/TLS, recipient, throttling, or network.
3. Determine the SMTP phase and whether there is evidence it **was not accepted by the relay**.
4. If AUTH/config/TLS is deterministic, stop retries and fix configuration.
5. If recipient error, fix data or suppress per policy.
6. If rate-limited, inspect quota/circuit breaker/concurrency.
7. If clearly temporary SMTP, ensure exponential backoff+jitter and nextAttemptAt.
8. If unknown after DATA, avoid blind retries; reconcile with the provider or handle per approved policy.
9. Check maxAttempts, deadline/token TTL, and priority.
10. Check whether the event has multiple active owners or worker retry amplification.
11. Only manually retry after confirming the true status and having authorization to act.
12. After resolving the incident, drain the backlog **at a controlled rate**, not all at once.
13. Reconcile dashboard attempts, unique mail events, and terminal states.
14. Document the incident cause to improve the classifier and policy.

### 41.1. Do not arbitrarily change database status SENT to PENDING

An event already accepted by the relay can send duplicates if flipped back to PENDING. Resends must be a separate audited business workflow.

### 41.2. Do not disable TLS as a “quick fix”

If there is a certificate error, fix trust/endpoint and deploy the right configuration; disabling TLS verification weakens security.

## 42. Common anti-patterns

| Anti-pattern | Consequence | Replace with |
| --- | --- | --- |
| catch(Exception) then retry | Retries unrecoverable errors | Failure classification |
| One fixed delay for all errors | Storms, wrong retry schedule | Category-aware backoff |
| Retrying invalid addresses | Wastes resources | STOP/fix data |
| Retrying AUTH 535 continuously | Lockout/account abuse | STOP/fix credentials |
| Skipping TLS validation | Insecure connections | Fix TLS |
| Treating all 4xx identically | Throttling goes unmitigated | SMTP/enhanced code context |
| Treating all 5xx as provider outage | Wrong failover | Error taxonomy |
| Timeout means unsent | Duplicates after DATA | UNKNOWN_OUTCOME |
| Retrying entire batch | Duplicates partial recipients | Per-message/recipient status |
| No maxAttempts | Infinite retries | Budget/deadline |
| Only maxDelay | Events retry for days | Deadline + attempt cap |
| No jitter | Herd effect | Full/decorrelated jitter |
| Using Thread.sleep in transaction | Holds DB locks/connections | Durable nextAttemptAt |
| Multiple uncontrolled retry layers | Retry amplification | One owner orchestrator |
| Outbox without atomic claim | Two workers send one event | Lease/claim/fencing |
| Not tracking SMTP phase | Unclear if safe-to-retry | Transport instrumentation |
| Treating send success as inbox delivered | Wrong dashboard/SLA | Separate downstream signals |
| Logging raw provider replies/credentials | Data leakage | Structured safe logs |
| recipient/eventId as metric label | High cardinality/PII | Allowlist tags |
| Arbitrarily rerendering templates on retry | Content differs within same intent | Snapshot/version |
| Switching providers to evade content policy | Compliance violation | Authorized routing |
| Retrying after token expiration | Useless/dangerous mail | Deadline check |
| Flushing backlog all at once after outage | Provider throttles again | Gradual ramp-up |

## 43. Frequently Asked Questions

**1. Why not retry every MailException?**

Because MailException covers errors with vastly different causes and recoverability. Invalid AUTH, bad input, TLS config, temporary SMTP, and timeouts after DATA cannot share the same decision.

**2. Does Spring Retry automatically understand SMTP 421 and 550?**

Do not assume so. You need a classifier from exception/reply/phase and an application policy. A generic annotation cannot tell whether the relay already accepted the email.

**3. Are SMTP 4xx errors always retryable?**

They usually indicate a transient negative reply, but you need to know the exact phase of the reply, provider semantics, budget, and whether non-acceptance is certain.

**4. Are SMTP 5xx errors always permanent recipient failures?**

No. They can be sender policy, content, or size failures. Inspect enhanced status, phase, and provider documentation.

**5. How should 535 AUTH be handled?**

Stop aggressive retries and check credentials/account/policy. A temporary AUTH infrastructure error may require a different policy than an invalid password.

**6. How do timeouts before connect and after DATA differ?**

Before connect, if no SMTP submission occurred for certain, retrying can be safe. After DATA, the relay may have accepted; UNKNOWN_OUTCOME/reconciliation is required.

**7. Is jitter mandatory?**

Not always mandatory, but very useful to keep thousands of events from retrying simultaneously after an outage. Rate limiting and provider-specific minimum delays are still needed.

**8. Is exponential backoff better than fixed delay in every case?**

Not automatically. It suits many transient errors, but does not fix input/config errors or ambiguous outcomes. Classification and safety matter more than the delay formula.

**9. Can maxDelay replace maxAttempts?**

No. Max delay only caps the time between two attempts; maxAttempts/deadline are what prevent infinite retries.

**10. Why avoid Thread.sleep in a worker?**

It holds threads/connections, is hard to recover after crashes, and is unsuitable for long delays. Storing nextAttemptAt in an outbox is usually much easier to operate.

**11. Does SMTP have Retry-After like HTTP 429?**

There is no standard Retry-After header used uniformly across all SMTP replies. Wait guidance from a provider is provider-specific; verify before applying.

**12. Does switching providers avoid duplicates after a timeout?**

No. Provider A may already have accepted before the response was lost. Sending through B adds another submission with duplicate risk.

**13. Does Message-ID prevent duplicate sends?**

There is no guarantee that an SMTP relay will drop messages with a duplicate Message-ID. It is useful for correlation/threading, not a replacement for an idempotency policy.

**14. If one message has 10 recipients and 2 fail, can we retry all 10?**

Do not retry blindly if 8 were already accepted. Per-recipient/partial outcome handling or a one-event-per-recipient design is needed.

**15. Is MailSendException.getMessageExceptions enough to decide retries?**

No. It helps inspect specific exceptions, yet you still need phase, reply context, outcome safety, and per-message status.

**16. Can internal Spring Retry and outbox retries be used together?**

Technically yes, but you must count total actual SMTP attempts, prevent retry amplification, and have one layer own the budget/deadline.

**17. Is an attachment error an SMTP provider error?**

Not necessarily. A resource can be read late during MIME serialization inside send, so an IOException inside send can originate from files/storage.

**18. Should full exception stack traces be saved in logs?**

Only when needed and properly authorized; diagnostic text can contain recipients and metadata. For metrics, use finite categories/codes.

**19. Can retries be tested without sending real emails?**

Yes. Test the planner with Clock.fixed/fake jitter; mock JavaMailSender; use an SMTP capture server for integration tests. Never send production emails from CI.

**20. Does an outbox guarantee exactly-once emails?**

No. It provides durable intent/claim/retry, but SMTP and the database do not commit atomically. A crash after SMTP accept before SENT still leaves a duplicate window.

**21. When should you RECONCILE?**

When relay acceptance certainty is insufficient, such as a timeout after DATA or a worker crash during an unclear stage.

**22. Could 4.7.0 be a rate limit?**

It may relate to policy/throttling depending on the provider, though it must not be inferred rigidly without context. Use provider-specific mappings and reply semantics.

**23. What if the provider is in an outage while many emails are pending?**

Keep the outbox durable, open the circuit breaker/backoff, monitor quota, and ramp speed back up in a controlled way upon recovery.

**24. Why might an OTP email stop retrying earlier than an invoice?**

An OTP/token has a short deadline, and sending after expiration can be useless or confusing. An invoice can tolerate a longer delay while still requiring a snapshot and business policy.

**25. Should every IOException be retried automatically?**

No. An IOException can come from sockets, attachment streams, or storage, and does not clarify phase/acceptance.

## 44. Key takeaways on retrying every exception with the same backoff

**“Catch every exception, wait the same amount of time, and resend” is an anti-pattern in Spring Framework Mail.** It mixes unrecoverable errors (invalid recipient, AUTH invalid, TLS config, template/resource errors), transient errors (SMTP 4xx, provider throttling, connection failure before submission), and **undetermined outcomes** (lost reply after DATA). Those three groups require different actions: **STOP**, **RETRY_LATER**, or **RECONCILE**.

Classify based on the Spring Mail/Jakarta Mail exception chain, SMTP reply/enhanced code, transport phase, per-recipient outcome, and certainty that the relay has not accepted the message. **Backoff may only be computed after deciding that retrying is truly appropriate and safe enough.** For transient errors, use exponential/capped backoff, jitter, provider minimum delay, maxAttempts, deadline, and appropriate rate limiting/circuit breakers.

For extended retries, use a **transactional outbox** with nextAttemptAt, atomic worker claims, durable attempt history, and RETRY_WAIT/FAILED/UNKNOWN_OUTCOME states instead of keeping threads asleep. Do not hold a database transaction across SMTP send, do not replay whole batches, do not auto-resend when the outcome is ambiguous, and do not equate JavaMailSender.send success with inbox delivery.

Monitor **attempts, error categories, backoff decisions, retry backlog, oldest pending age, provider throttling, and unknown outcomes** with Micrometer, logs, and tracing; test policies with fake Clock/jitter, Mockito, and database concurrency tests. When retries are designed around **cause, safety, and business value**, the system recovers better from transient errors while avoiding turning configuration mistakes or network incidents into retry storms and duplicate emails.
