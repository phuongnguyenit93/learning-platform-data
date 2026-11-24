# Authentication or Address Errors Should Not Be Retried Blindly

In Spring Framework Mail, a retry mechanism helps the system recover when the SMTP server is temporarily unavailable, the network connection drops, or rate limiting occurs for a short period. However, **not every email sending error should be retried**.

If the SMTP account has the wrong password, an OAuth token has been revoked, or SMTP AUTH is disabled, resending the same request every few seconds usually accomplishes nothing. It can also trigger account lockouts, generate security alerts, or clog the entire email queue. Similarly, if the recipient address does not exist, resending dozens of times only wastes traffic and can harm sending reputation.

A safe policy must distinguish:

- **Recoverable transient errors:** busy server, rate limiting, temporary network failures.
- **Configuration or credential errors requiring fixes:** wrong credentials, disabled SMTP permissions, incompatible authentication mechanism.
- **Address or recipient errors:** bad syntax, non-existent mailbox, rejected recipient.
- **Policy errors:** domain, content, sender, or organization rejected by the server.
- **Uncertain outcomes:** connection dropped after SMTP may have already accepted the message; retrying risks sending a duplicate.

Core principle: **retries must be based on error type, stage of occurrence, SMTP response, and actual task state; never solely on the presence of an exception**.

## 1. Why Is Blind Retrying Harmful?

Suppose a worker pulls pending emails from an outbox and calls `JavaMailSender`:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (Exception ex) {
        Thread.sleep(1000);
    }
}
~~~

This is a pattern to avoid because:

1. It does not know whether the exception is transient.
2. There is no maximum attempt limit or proper backoff.
3. Authentication errors can make the worker retry repeatedly with invalid credentials.
4. Non-existent addresses keep getting retried indefinitely.
5. If the message was already accepted by SMTP but the response was lost, the next attempt may send a duplicate.
6. The worker is tied up by a failing task instead of processing other valid tasks.
7. The system does not persist state so operators know configuration or data needs fixing.

Example failure chain:

~~~text
SMTP password changed
        |
        v
JavaMailSender.send()
        |
        v
Authentication failed
        |
        v
Retry every second
        |
        +-- Increases failed login count
        +-- Risk of account lockout
        +-- Increases logs and alerts
        +-- No emails are sent
~~~

Credential errors require a different action: **pause the group of tasks using the broken configuration, alert, and require fixing the configuration** before resuming delivery.

## 2. How to Read SMTP Responses

SMTP uses three-digit reply codes, usually accompanied by descriptive text. Some systems also return an **enhanced status code** in a three-part format such as 5.1.1 or 4.7.0.

Basic classification:

| Category | General meaning | Initial handling |
| --- | --- | --- |
| **2xx** | Command accepted | Continue per protocol; no error to retry at this step |
| **3xx** | Server requests data or next step | Not a final error for the message |
| **4xx** | Transient negative completion | May retry with limits after analyzing the cause |
| **5xx** | Negative completion unacceptable under current conditions | Usually requires fixing data/config/policy before retrying |

**4xx does not mean definitely retry immediately**, and **5xx does not mean every address must be permanently deleted**. You must check which stage the response belongs to and what the server is actually reporting.

### 2.1. Enhanced Status Codes Add Context

Example:

~~~text
550 5.1.1 User unknown
~~~

Where:

- **550** is the SMTP reply code.
- **5.1.1** is the enhanced status code, usually indicating the destination address does not exist.
- **User unknown** is the server's diagnostic text.

Another response:

~~~text
535 5.7.8 Authentication credentials invalid
~~~

This is an authentication signal, not proof that the recipient's email address is wrong.

Actual codes and messages depend on the provider. Consult your SMTP provider's documentation to understand provider-specific cases; do not simply match a keyword in diagnostic text and decide to delete an address.

### 2.2. Common Codes and Cautious Interpretation

| Example response | Common stage | Possible meaning | Typical appropriate handling |
| --- | --- | --- | --- |
| **535 5.7.8** | AUTH | Invalid authentication credentials | Stop automatic retries, fix credentials |
| **534 5.7.x** | AUTH | Authentication mechanism/condition not accepted | Check authentication policy, MFA/OAuth |
| **530 5.7.x** | MAIL FROM or other command | Authentication or TLS required before continuing | Check configuration/session |
| **454 4.7.0** | AUTH | Authentication temporarily unavailable | Bounded retry with backoff, alert if prolonged |
| **421 4.x.x** | Connection or SMTP command | Service temporarily unavailable | Retry with backoff if message not yet accepted |
| **450 4.2.x** | RCPT TO | Mailbox temporarily unavailable | Retry per policy |
| **451 4.3.x** | RCPT TO/DATA | Temporary processing error | Bounded retry |
| **452 4.2.2** | RCPT TO | Mailbox full or temporary resource shortage | Wait, limit retries |
| **501 5.1.3** | MAIL FROM/RCPT TO | Invalid address or parameter syntax | Fix data, do not retry as-is |
| **550 5.1.1** | RCPT TO | Mailbox does not exist | Mark recipient invalid when signal is reliable |
| **553 5.1.3** | RCPT TO | Malformed mailbox address syntax | Fix address |
| **550 5.7.1** | RCPT TO or DATA | Not permitted, policy rejection | Investigate sender, permissions, and policy |
| **552 5.2.2** | RCPT TO/DATA | Mailbox full per server response | Classify per provider; do not assume user unknown |
| **554 5.7.x** | DATA or end of transaction | Rejected due to policy/content | Stop retrying as-is, investigate policy |

This table lists common examples, **not an absolute mapping**. The same three-digit SMTP code can carry different meanings depending on the enhanced code, phase, and diagnostic text. In particular, **550 alone does not prove the recipient address does not exist**.

## 3. Distinguishing SMTP Stages

An exception from `JavaMailSender` can arise at multiple stages:

~~~text
CONNECT
   |
   v
TLS / STARTTLS
   |
   v
AUTH
   |
   v
MAIL FROM
   |
   v
RCPT TO
   |
   v
DATA
   |
   v
Server accepts or rejects message
~~~

Information about **the failure stage** guides the retry decision.

### 3.1. CONNECT and TLS

Timeouts when opening a connection may be temporary network errors. However, a wrong host, wrong port, invalid certificate, or incompatible STARTTLS configuration usually requires a configuration fix.

If the TLS certificate is untrusted, repeated retries will not change the outcome. Do not disable certificate verification as a "quick fix" for an authentication or TLS error.

### 3.2. AUTH

Errors at AUTH relate to the account, authentication method, token, permissions, or authentication service. You must separate temporary outages from configuration errors.

### 3.3. MAIL FROM

The server may reject the envelope sender because the account lacks permission to send as that address, the domain is not yet allowed, or sending policy checks fail.

This is not a recipient email error. Do not put all recipients on an invalid-address list when the failure occurred at `MAIL FROM`.

### 3.4. RCPT TO

This stage typically provides specific signals about the recipient address: mailbox does not exist, invalid address, recipient rejected, or temporarily unavailable.

However, a rejection at `RCPT TO` can also be caused by policy, rate limits, or sender reputation. Inspect both the code and diagnostics.

### 3.5. DATA and Final Response

If the server rejects content at `DATA`, the error may relate to policy, size, or attachment type. If the connection drops after sending data but before the application receives the final response, the send outcome **may be unknown**.

This is one of the most critical scenarios for idempotency: retrying can create a duplicate email if the server already accepted the message.

## 4. Authentication Errors: Do Not Retry With the Same Credentials Forever

Some common causes:

- SMTP password was changed.
- App password was revoked.
- SMTP AUTH was disabled on the account or tenant.
- Account requires OAuth2 while the application still uses a password.
- Access token expired and the refresh mechanism failed.
- Server requires TLS before AUTH.
- Account is locked or blocked by security policy.
- Wrong SMTP host, port, or TLS mode.
- Account is not allowed to send using the chosen envelope sender or `From` address.

These causes may require an administrator or credential-provisioning mechanism to fix. They should not be treated as temporary network errors.

### 4.1. The 535 Response

Example:

~~~text
535 5.7.8 Authentication credentials invalid
~~~

If configured credentials have not changed, resending the same AUTH command one second later will usually fail again.

Handling steps:

1. Identify the affected sending account/configuration using a non-sensitive identifier.
2. Transition related mail jobs to a configuration-paused state.
3. Stop retrying with the same credentials in a loop.
4. Alert operators or the secrets-management mechanism.
5. After verifying the new configuration, perform one controlled probe.
6. Resume processing the queue at a rate-limited pace.

Never log passwords, OAuth tokens, or Authorization header contents.

### 4.2. SMTP AUTH Disabled

A provider may reject even a valid username and password because the account, tenant, or organization disallows SMTP AUTH.

In that case, permissions must be changed or another sending mechanism chosen per provider policy. Retrying cannot fix a disabled capability.

### 4.3. Expired OAuth Token

When using OAuth2, an expired token is a condition recoverable via a valid refresh flow.

A safe policy might be:

- Detect token expiration from a reliable provider response.
- Refresh the token using the implemented refresh flow.
- Retry **with limits**, typically once with the new token for that attempt.
- If refresh fails, the token is revoked, or the account loses access, transition to a state requiring intervention.
- Use synchronization or single-flight refresh to prevent hundreds of workers from refreshing the token simultaneously.

**Do not assume every 535 response means an expired token.** Check the authentication mechanism and provider signals.

### 4.4. Temporary AUTH Errors Can Still Be Retried

For example, some providers return:

~~~text
454 4.7.0 Temporary authentication failure
~~~

If this is genuinely a temporary error in the authentication service, you may retry after a wait period with an attempt limit.

Do not retry aggressively: even repeated 4xx errors can add load or trigger anti-abuse policies.

### 4.5. Avoiding Account Lockouts

A system with 20 workers where each worker retries 5 times can generate 100 failed AUTH attempts in a short period.

For errors sharing the same credentials, implement a **pause/circuit breaker per SMTP account or tenant** instead of letting each message retry unboundedly. A failure on one account should not halt other independent tenants or sending accounts.

## 5. Invalid Recipient Address: Fix Data Instead of Retrying

Not every string that looks like an email address actually exists.

Some cases:

- Missing `@` or domain part.
- Address contains characters disallowed by system policy.
- Domain does not exist or does not accept mail.
- Mailbox has been deleted.
- Recipient mistyped the mailbox name.
- Recipient rejected by server policy.
- Mailbox is temporarily not accepting messages.

These cases require different handling.

### 5.1. Address Syntax Errors

Example:

~~~text
501 5.1.3 Bad recipient address syntax
~~~

If the address was mistyped, retrying as-is will not help. The application should flag the data as needing correction and not retry until the address is updated.

Validate syntax before building the email:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public void validateRecipient(String email) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException(
                "Email address must not be blank"
        );
    }

    try {
        InternetAddress address = new InternetAddress(email, true);
        address.validate();

        if (address.isGroup()) {
            throw new IllegalArgumentException(
                    "A single mailbox is required, not an address group"
            );
        }
    } catch (AddressException ex) {
        throw new IllegalArgumentException(
                "Invalid email address",
                ex
        );
    }
}
~~~

This is only a syntax-checking layer using the Jakarta Mail API. It **does not guarantee the mailbox exists**, does not verify address ownership, and does not replace permission checks or product rules.

Consider internationalized addresses, SMTPUTF8 support policies, and special domain cases if your system requires them.

### 5.2. Mailbox Does Not Exist

Example:

~~~text
550 5.1.1 User unknown
~~~

If the provider confirms the mailbox does not exist at `RCPT TO`, the application can mark the recipient as needing correction or add it to a suppression list per policy.

Do not keep retrying the same address just because the outbox job has not reached its attempt limit.

However, do not automatically infer "unknown user" from every `550` code. Inspect the enhanced status code, detailed response, phase, and provider behavior.

### 5.3. Mailbox Full Is Not the Same as Non-Existent Mailbox

Example:

~~~text
452 4.2.2 Mailbox full
~~~

A full mailbox can accept mail again once the user frees space. Depending on the provider, slow, bounded retries may be considered.

A `5.2.2` class response may mean rejection due to inability to process at that time. Never label an address as "non-existent" simply because the mailbox is full.

### 5.4. Domain Does Not Accept Mail

If the error is domain not found or no suitable mail route, it could be bad data or a temporary DNS failure. Distinguish a persistent DNS NXDOMAIN from a DNS timeout.

Do not delete a recipient due to a brief DNS timeout. Conversely, do not retry indefinitely for a clearly non-existent domain.

### 5.5. Do Not Use SMTP VRFY as Definitive Proof

Many systems disable or restrict the `VRFY` command to prevent address harvesting. Some servers intentionally do not confirm users during an SMTP transaction.

Do not build an "address existence checker" by sending bulk probe commands. This is unreliable and may be treated as abusive activity.

A better way to verify address ownership in many products is to send a time-limited verification email and require the user to complete the confirmation flow.

## 6. Policy Errors Are Not Address Errors

Some SMTP responses reject delivery because:

- The sender is not authorized.
- The sending domain is not yet authenticated per provider policy.
- SPF, DKIM, or DMARC are not properly configured.
- IP/domain reputation is low.
- Content or attachments violate rules.
- Account or tenant sending limits were reached.
- The recipient domain enforces a specific policy.

Example:

~~~text
550 5.7.1 Message rejected by policy
~~~

If you see `550` and immediately suppress the recipient as "mailbox does not exist," the system can lose valid addresses.

The right approach is to classify by **error origin**:

- Sender/domain error: check configuration and sending reputation.
- Content error: investigate templates, links, and attachments.
- Sending permission error: check account and provider policy.
- Clear recipient error: handle recipient data.
- Quota/rate limit error: wait per policy instead of editing the address.

No single SMTP code table is sufficient to decide every case without provider context.

## 7. Transient Errors: Conditional and Bounded Retries

Some errors suitable for retry:

- SMTP server temporarily unavailable.
- Connection timeout before message acceptance.
- Rate limiting or throttling explicitly reported by the provider.
- 4xx error at `RCPT TO` or `DATA` indicating a temporary state.
- Temporary interruption of the authentication service, when backed by reliable signals.

Still, retries require:

1. Limiting the number of attempts.
2. Spacing attempts with exponential backoff.
3. Adding jitter to avoid synchronized resends.
4. Respecting provider-recommended wait times if present.
5. Limiting concurrency per account/provider.
6. Separating shared configuration failures from individual message failures.
7. Recording the reason and next retry timestamp.

Example illustrative backoff sequence:

~~~text
Attempt 1 -> temporary error
  Wait ~30 seconds + jitter
Attempt 2 -> temporary error
  Wait ~2 minutes + jitter
Attempt 3 -> temporary error
  Wait ~10 minutes + jitter
Attempt 4 -> temporary error
  Wait ~30 minutes + jitter
Threshold exceeded -> MANUAL_REVIEW or FAILED
~~~

The intervals above are architectural examples, not defaults of Spring Mail. Actual policy depends on SLAs, the SMTP provider, notification type, and recoverability.

### 7.1. Do Not Retry Immediately on Provider Rate Limits

If the server responds with something like:

~~~text
421 4.7.0 Too many requests
~~~

retrying immediately across many workers can worsen the situation. Slow down, apply backoff, and cap total connections/send commands.

### 7.2. Circuit Breaker for Global Errors

If every email sent through an SMTP account receives the same persistent AUTH error, instead of retrying each message individually, open a circuit breaker for that account.

~~~text
SMTP account A
      |
      v
Repeated permanent AUTH errors
      |
      v
PAUSED_CONFIG
      |
      +-- Alert owner
      +-- Update/validate credentials
      +-- Controlled recovery
      |
      v
Resume queued sends
~~~

Other independent accounts can continue operating normally.

## 8. How Spring Mail Represents Errors

Spring provides **JavaMailSender** to build and send `MimeMessage` objects. Runtime sending errors are typically translated into exceptions under the **MailException** hierarchy.

Common types:

| Exception | Typical meaning | Note |
| --- | --- | --- |
| **MailAuthenticationException** | Authentication failed | Check whether the error is permanent or temporary |
| **MailSendException** | Error sending one or more messages | May contain per-message failure details |
| **MailParseException** | Unable to parse mail message | Usually requires fixing data or message construction |
| **MailPreparationException** | Error preparing message | Do not retry SMTP if input/template is invalid |
| **MailException** | Base class for mail errors in Spring | Insufficient to decide retries |

Example:

~~~java
try {
    mailSender.send(mimeMessage);
} catch (MailAuthenticationException ex) {
    // Usually requires checking AUTH configuration before retrying.
} catch (MailSendException ex) {
    // Inspect cause, message failures, and SMTP response.
} catch (MailException ex) {
    // Classify by specific cause; do not retry unconditionally.
}
~~~

**The Spring-level exception name alone is not enough to draw an accurate conclusion.** A `MailSendException` can contain SMTP errors with varying codes, or even outcome details for multiple recipients.

### 8.1. Jakarta Mail and Nested Exceptions

When working with Jakarta Mail, useful exception types include:

- **jakarta.mail.MessagingException**
- **jakarta.mail.AuthenticationFailedException**
- **jakarta.mail.SendFailedException**
- **jakarta.mail.internet.AddressException**

A `MessagingException` can hold chained exceptions via **getNextException()**, not just through the standard Java cause chain. Spring's `MailSendException` can also expose detailed exceptions via **getMessageExceptions()** or a failed-messages map.

An error classifier should inspect **the actual exception chain and SMTP response**, rather than checking only the outermost exception class name.

### 8.2. Provider-Specific SMTP Exceptions

Some Jakarta Mail providers include specialized exceptions for SMTP addresses or commands containing the SMTP reply code and recipient information. Specific package/class names may depend on the mail provider implementation and version in use.

Do not hard-code an SMTP provider package name across your entire domain logic. Write an adapter in the infrastructure layer to translate provider exceptions into neutral signals such as:

~~~text
phase
smtpReplyCode
enhancedStatusCode
recipient
providerDiagnostic
outcomeKnown
~~~

Then the retry policy depends only on normalized signals.

### 8.3. Partial Success Is Possible

A send to multiple recipients can have different outcomes for each address. Jakarta Mail's `SendFailedException` can report address groups such as:

- Invalid addresses.
- Valid addresses to which the message was sent per transport results.
- Valid addresses to which the message was not sent.

Inspect those groups alongside provider policy. Never retry the entire list just because one address was rejected; doing so can send duplicate copies to recipients who already received the email.

## 9. Designing a Clear Retry Classifier

An infrastructure layer can convert errors into structured data, and then a policy determines the action.

Java model example:

~~~java
public enum SmtpStage {
    CONNECT,
    TLS,
    AUTH,
    MAIL_FROM,
    RCPT_TO,
    DATA,
    AFTER_DATA,
    UNKNOWN
}

public record FailureSignals(
        SmtpStage stage,
        Integer replyCode,
        String enhancedCode,
        boolean responseLostAfterData,
        boolean malformedRecipient
) {}

public enum RetryDecision {
    RETRY_WITH_BACKOFF,
    STOP_INVALID_RECIPIENT,
    STOP_FIX_AUTH,
    STOP_FIX_POLICY,
    REVIEW_UNKNOWN_OUTCOME
}
~~~

Fields are populated from actual exception/SMTP diagnostics. **Do not guess `replyCode` or `stage` if the provider does not supply them.** Leave them `null`/`UNKNOWN` and classify conservatively.

### 9.1. Illustrative Policy Example

~~~java
public final class MailRetryPolicy {

    public RetryDecision decide(FailureSignals f) {
        if (f.responseLostAfterData()) {
            return RetryDecision.REVIEW_UNKNOWN_OUTCOME;
        }

        if (f.malformedRecipient()) {
            return RetryDecision.STOP_INVALID_RECIPIENT;
        }

        Integer code = f.replyCode();
        String enhanced = f.enhancedCode();

        if (f.stage() == SmtpStage.AUTH) {
            if (code != null && code >= 500 && code <= 599) {
                return RetryDecision.STOP_FIX_AUTH;
            }
            if (code != null && code >= 400 && code <= 499) {
                return RetryDecision.RETRY_WITH_BACKOFF;
            }
            return RetryDecision.REVIEW_UNKNOWN_OUTCOME;
        }

        if (f.stage() == SmtpStage.RCPT_TO &&
                ("5.1.1".equals(enhanced) ||
                 "5.1.3".equals(enhanced))) {
            return RetryDecision.STOP_INVALID_RECIPIENT;
        }

        if (code != null && code >= 400 && code <= 499) {
            return RetryDecision.RETRY_WITH_BACKOFF;
        }

        if (code != null && code >= 500 && code <= 599) {
            return RetryDecision.STOP_FIX_POLICY;
        }

        return RetryDecision.REVIEW_UNKNOWN_OUTCOME;
    }
}
~~~

This is a **minimal policy to illustrate structure**, not a complete classifier for every SMTP provider. In production, you also need to consider TLS, policies, quotas, sender addresses, specific enhanced status codes, the DATA stage, and network failure signals. **RETRY_WITH_BACKOFF** must also be subject to attempt/TTL limits and duplicate-prevention conditions.

### 9.2. Separating Classification From Action

The classifier should not call SMTP again itself. It should only return a decision. Another worker will:

- Record the state.
- Choose the retry time.
- Update attempt counts.
- Emit alerts if needed.
- Wait for configuration to be fixed.
- Execute the send when the task becomes eligible.

Separating responsibilities allows the retry policy to be unit-tested independently without a live SMTP connection.

## 10. Classifying Authentication Errors in Java

At the Spring Mail level, you can specifically intercept AUTH errors:

~~~java
public void deliver(MimeMessage message) {
    try {
        mailSender.send(message);
    } catch (MailAuthenticationException ex) {
        throw new SmtpAccountNeedsAttentionException(
                "SMTP authentication failed",
                ex
        );
    }
}
~~~

**SmtpAccountNeedsAttentionException** is an application-defined exception used to signal to the orchestration layer that the sending account needs review. It is not a built-in Spring class.

Example:

~~~java
public class SmtpAccountNeedsAttentionException
        extends RuntimeException {

    public SmtpAccountNeedsAttentionException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
~~~

This approach is useful for flagging a severe category of failure, but **you should not equate every `MailAuthenticationException` with permanently wrong credentials**. If the provider indicates AUTH is temporarily unavailable, the policy can allow bounded retries.

The key rule is **do not catch `MailAuthenticationException` and retry unconditionally forever**:

~~~java
catch (MailAuthenticationException ex) {
    // Wrong: immediately resending repeatedly with the same credentials.
}
~~~

The mail-sending layer should report the failure accurately; the orchestration layer decides whether to stop, fix configuration, or retry.

## 11. Distinguishing Recipient Errors From Exceptions

If the provider returns an error at `RCPT TO`, the details to determine include:

- Which recipient was rejected?
- What is the SMTP reply code?
- Is the enhanced status code reliable?
- Is the error due to a non-existent recipient or policy?
- Were other recipients accepted?
- Was the message already accepted after `DATA`?

Some implementations provide exceptions specific to SMTP addresses. Jakarta Mail's `SendFailedException` can also provide lists of valid sent, invalid, and valid unsent addresses.

Example of inspecting this exception type:

~~~java
catch (MailSendException ex) {
    for (Exception cause : ex.getMessageExceptions()) {
        if (cause instanceof jakarta.mail.SendFailedException sfe) {
            Address[] invalid = sfe.getInvalidAddresses();
            Address[] validSent = sfe.getValidSentAddresses();
            Address[] validUnsent = sfe.getValidUnsentAddresses();

            // Map into structured per-recipient results.
            // Do not blindly resend to the entire list.
        }
    }
}
~~~

This snippet illustrates extracting details at the infrastructure layer. The arrays may be `null`, exceptions may be nested deeper, and exact behavior depends on the provider. Handle those cases in the adapter.

Do not write raw diagnostics, full addresses, or message contents to unprotected logs. Redact unnecessary data when reporting errors.

## 12. One Failing Address Does Not Mean the Whole Batch Failed

Suppose you send one message to three recipients:

~~~text
alice@example.net  -> accepted
bob@example.net    -> unknown user
carol@example.net  -> accepted
~~~

If the mail sender throws an exception because of Bob, retrying the whole message for Alice, Bob, and Carol can:

- Send duplicates to Alice and Carol.
- Keep trying Bob's non-existent address.
- Make it harder to determine who actually received the email.

A simple strategy for transactional email is **one send intent per recipient**, especially when retries and suppression must be tracked independently. If business rules require sending to multiple recipients in the same message, use per-recipient outcome details from the transport and provider policy to decide retries.

Do not infer partial delivery solely from an API throwing an exception. Inspect the actual transport signals available.

## 13. Outbox States Suitable for AUTH and Recipient Errors

If using a transactional outbox, you should not only have `PENDING` and `SENT`. Error states requiring different actions need to be represented.

An illustrative model:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted ------> ACCEPTED_BY_RELAY
   |
   +-- Temporary error ----> RETRY_WAIT
   |
   +-- AUTH fixed error ---> PAUSED_CONFIG
   |
   +-- Invalid recipient --> INVALID_RECIPIENT
   |
   +-- Policy rejection --> NEEDS_REVIEW
   |
   +-- Ambiguous result ---> UNKNOWN_OUTCOME
   |
   +-- Retry exhausted ---> FAILED
~~~

These state names are application examples, not a built-in Spring enum.

| State | Meaning | Action |
| --- | --- | --- |
| **PENDING** | Send intent has been committed | Wait for worker |
| **PROCESSING** | Worker has claimed the row | Process within lease duration |
| **RETRY_WAIT** | Failure assessed as temporary | Wait until `nextAttemptAt` |
| **PAUSED_CONFIG** | SMTP account needs AUTH/TLS/policy fix | Do not auto-retry per message |
| **INVALID_RECIPIENT** | Recipient confirmed invalid | Wait for address fix or suppression |
| **NEEDS_REVIEW** | Policy rejection or unclear cause | Investigate before retrying |
| **UNKNOWN_OUTCOME** | Message may have been accepted by server | Reconcile and retry cautiously |
| **ACCEPTED_BY_RELAY** | SMTP provider accepted message | Monitor bounces/delivery if available |
| **FAILED** | Limit reached or cannot proceed | Operational handling |

Do not use `ACCEPTED_BY_RELAY` to claim the recipient opened the email.

### 13.1. AUTH Errors Are an Account-Level Issue

If SMTP account A has an authentication error, thousands of messages may be affected. There is no need to increment each message's attempt counter dozens of times just to prove the same credentials are still wrong.

You can mark account A as `PAUSED_CONFIG`, keep affected messages in `PENDING`/`PAUSED`, raise an alert, and resume after the configuration is verified valid.

### 13.2. Recipient Errors Are an Address-Level Issue

If a specific recipient is invalid, only tasks for that recipient need to be paused or handled. Messages to other valid addresses continue normally.

Isolating errors by **account**, **sender domain**, **recipient**, and **message** prevents expanding the blast radius of an incident.

## 14. Write Outbox in Data Transaction, Send SMTP After Commit

A common architecture:

~~~text
Order service @Transactional
     |
     +-- Commit order state
     +-- Insert mail_outbox(status=PENDING)
     |
     v
   COMMIT
     |
     v
Outbox worker
     |
     +-- Claim event
     +-- Build MIME
     +-- Call JavaMailSender
     +-- Classify AUTH/recipient/policy/network
     +-- Update status or retry schedule
~~~

If the business transaction rolls back, the outbox row also rolls back. If it commits successfully, a worker can process the task even after a restart.

Important: **do not hold a database transaction locking rows while waiting on SMTP**. A worker can claim in a short transaction, send outside the transaction, and update the result in another short transaction.

### 14.1. Worker Pseudocode Example

~~~java
public void process(MailOutboxEvent event) {
    if (smtpAccountRegistry.isPaused(event.accountId())) {
        // Avoid wasting another invalid AUTH attempt.
        outboxService.deferUntilConfigRestored(event.id());
        return;
    }

    try {
        mailDeliveryService.send(event);
        outboxService.markAcceptedByRelay(event.id());
    } catch (Exception ex) {
        FailureSignals signals = failureExtractor.extract(ex);
        RetryDecision decision = retryPolicy.decide(signals);

        outboxService.applyDecision(
                event.id(),
                decision,
                signals
        );
    }
}
~~~

The services **smtpAccountRegistry**, **outboxService**, and **failureExtractor** are illustrative application components, not built-in Spring Mail APIs. Applying the decision must update attempts, `nextAttemptAt`, lease, account pause, and retry limits per policy.

### 14.2. Retries Must Not Re-Run the Entire Business Operation

If only SMTP fails, the worker should retry **the email send intent**, not re-run the transaction that created the order, issued the invoice, or generated a verification code.

You can reuse a DTO snapshot saved in the outbox to rebuild the same message. This avoids turning a resend into a new business transaction.

## 15. Idempotency and Unknown SMTP Outcomes

An important limitation:

~~~text
1. Worker sends DATA.
2. SMTP server accepts message.
3. Connection drops before response reaches application.
4. Worker records timeout.
5. Worker retries.
6. Recipient may receive two emails.
~~~

You cannot infer "the message was definitely not sent" from a timeout alone.

### 15.1. Distinguishing Safer Retries From Duplicate-Risk Retries

- Errors before any recipient is accepted or before `DATA` typically carry lower risk of creating duplicate messages, when confirmed by transport signals.
- Errors after `DATA` has been transmitted and the final response is not received must be marked **UNKNOWN_OUTCOME** if unverifiable.
- A high-level Java error can mask the actual phase; when information is missing, do not assume the message was not sent.

Exactly-once email delivery cannot be guaranteed by application-level retries alone.

### 15.2. Using a Stable Event ID

Each send intent has an event ID that stays unchanged across retries:

~~~text
mailEventId = ORDER_CONFIRMED:1001:version-3
~~~

The event ID is used for logging, reconciliation, and outbox state. It is not a fresh ID generated on every attempt.

### 15.3. Message-ID Does Not Guarantee Deduplication

A MIME message has a `Message-ID` header. Keeping a consistent `Message-ID` can assist some reconciliation tools, but it does not force every SMTP server or email client to deduplicate duplicate sends.

If a provider supports an idempotency key via its own API, use it according to the provider's contract. Standard SMTP has no universal exactly-once idempotency key.

### 15.4. Content Must Tolerate Duplicate Delivery

For transactional emails, retries must not:

- Generate another order.
- Issue a new verification code for the same event.
- Charge a payment again.
- Mutate unrelated business state.
- Cause a duplicate email to be interpreted as a new transaction.

Use business IDs and immutable snapshots so content does not change unexpectedly between attempts.

## 16. Handling Bounces After SMTP Acceptance

Not every address error is detected at `RCPT TO`. An SMTP relay may accept a message, and later the receiving system returns a **delivery status notification (DSN)** or bounce notice.

Thus, the following can happen:

~~~text
SMTP send returns success
        |
        v
Provider accepts message
        |
        v
Later delivery attempt fails
        |
        v
Hard bounce or soft bounce
~~~

A mail job marked `ACCEPTED_BY_RELAY` can still fail final delivery later.

### 16.1. Hard Bounces and Soft Bounces

Common terms:

- **Hard bounce:** a persistent delivery failure, such as a non-existent address.
- **Soft bounce:** a temporary failure, such as a full mailbox or temporarily unavailable receiving server.

However, hard/soft labels depend on the provider and do not replace analyzing actual SMTP/DSN codes.

### 16.2. Do Not Auto-Suppress From an Ambiguous SMTP 550 Alone

Suppression lists must be based on reliable signals. For instance, a provider confirming `5.1.1 user unknown` for an address is a stronger signal than a generic `550` policy rejection.

When deciding on suppression:

1. Record the reason and data source.
2. Scope to the recipient or tenant.
3. Do not permanently delete the address from the user's profile if you only need to block sending.
4. Allow updating the address or requiring re-verification per product workflow.
5. Ensure the suppression list complies with privacy/retention policies.

## 17. Security When Handling AUTH Errors

Authentication errors often contain information valuable to attackers. Exercise care when logging and surfacing exceptions.

### 17.1. Never Log Secrets

Never record:

- SMTP passwords.
- OAuth access tokens or refresh tokens.
- `Authorization` headers.
- SMTP AUTH payloads.
- Raw connection transcripts containing sensitive data.

If protocol debugging is enabled, strictly control log storage, environments where it is used, and access permissions.

### 17.2. Access Control When Updating Credentials

Only authorized people or services should be able to change SMTP account credentials. After an update, perform a controlled connection test before reopening the queue.

Do not allow an end-user request to trigger unlimited AUTH attempts to "probe" a shared SMTP account.

### 17.3. Alert per Account, Not per Message

If 500 messages fail together because a password changed, do not send 500 identical alerts. Group alerts by account ID and error type while still maintaining individual state for affected mail jobs.

## 18. Observability and Logging for Accurate Error Classification

A mail failure event can record the following fields:

~~~text
eventId
accountId
tenantId
recipientReference
smtpStage
smtpReplyCode
enhancedStatusCode
errorCategory
retryDecision
attemptNumber
nextAttemptAt
provider
timestamp
~~~

Enforce access control and data redaction per policy. There is no need to store the full MIME message, attachments, or credentials in every log entry.

### 18.1. Useful Metrics

Metrics to track:

- Pending email count.
- Emails currently in retry.
- Tasks in `PAUSED_CONFIG`.
- AUTH error rate by SMTP account.
- Invalid recipient rate by data entry source.
- 4xx/5xx rates by provider.
- Count of `UNKNOWN_OUTCOME` cases.
- Age of oldest `PENDING` task.
- Time from business commit to provider acceptance.
- Active worker count and queue depth.

These metrics help distinguish a configuration incident from a provider outage or a batch of recipients with bad data.

### 18.2. Actionable Alerts

Examples:

| Alert | Action |
| --- | --- |
| Repeated SMTP AUTH 535 for account A | Check secrets, account policy, and OAuth |
| Spike in 421/4.7.0 in a short period | Reduce concurrency, check rate limits |
| Spike in 5.1.1 from a signup source | Check input validation and verification flow |
| Spike in 5.7.1 at MAIL FROM/DATA | Check sender, domain authentication, and policy |
| Rising `UNKNOWN_OUTCOME` | Inspect network/SMTP responses and duplicate risk |
| Continuously growing outbox backlog | Inspect workers, provider, and retry scheduling |

## 19. Testing Retry Policies

You can test the classifier without a real SMTP server by constructing `FailureSignals`:

~~~java
MailRetryPolicy policy = new MailRetryPolicy();

RetryDecision auth = policy.decide(
        new FailureSignals(
                SmtpStage.AUTH,
                535,
                "5.7.8",
                false,
                false
        )
);

assertEquals(RetryDecision.STOP_FIX_AUTH, auth);

RetryDecision unknownUser = policy.decide(
        new FailureSignals(
                SmtpStage.RCPT_TO,
                550,
                "5.1.1",
                false,
                false
        )
);

assertEquals(
        RetryDecision.STOP_INVALID_RECIPIENT,
        unknownUser
);

RetryDecision temporary = policy.decide(
        new FailureSignals(
                SmtpStage.RCPT_TO,
                450,
                "4.2.0",
                false,
                false
        )
);

assertEquals(
        RetryDecision.RETRY_WITH_BACKOFF,
        temporary
);
~~~

This example uses the model defined earlier. Signals are passed directly to test the policy; tests for provider exception extraction should be written separately.

### 19.1. Test Scenario Matrix

| Scenario | Expected result |
| --- | --- |
| AUTH 535 with unchanged credentials | Stop automatic retries and alert |
| AUTH 454 with temporary signal | Retry with backoff, limited attempts |
| RCPT TO 550 5.1.1 | Mark recipient invalid per policy |
| RCPT TO 450 4.2.x | Schedule retry |
| 550 5.7.1 policy rejection | Do not label recipient unknown; inspect policy |
| Invalid TLS certificate | Stop and fix configuration |
| Account-level rate limit | Slow down, do not retry immediately |
| Connection lost after DATA | `UNKNOWN_OUTCOME`; assess duplicate risk |
| Multi-recipient send with partial acceptance | Do not blindly resend to accepted recipients |
| Worker restart after `PAUSED_CONFIG` | Do not auto-reopen queue before fixing and verifying config |
| Worker restart after `RETRY_WAIT` | Resume according to `nextAttemptAt` |
| Event reprocessed | Do not create a new business task |

### 19.2. SMTP Capture Servers and Fault Injection

An SMTP test server or fake transport can produce AUTH/RCPT TO/DATA responses to test the worker. For production providers, separately test their authentication flows, rate limits, and how they format enhanced status codes.

Do not repeatedly test wrong credentials against a live account just to verify retry policy. Use fakes/stubs or an authorized test environment.

## 20. Operational Decision Matrix

| Error type | Auto-retry? | Suggested state | Required action |
| --- | --- | --- | --- |
| Wrong password or SMTP AUTH disabled | **No**, while config is unchanged | `PAUSED_CONFIG` | Fix credentials/permissions |
| OAuth access token expired with valid refresh | Bounded after refresh | `RETRY_WAIT` or `PROCESSING` | Refresh safely, no storm |
| Temporary 4xx AUTH error | Bounded | `RETRY_WAIT` | Backoff and monitor |
| Recipient syntax error | **No** | `INVALID_RECIPIENT` | Fix address |
| Clear `5.1.1` user unknown | **No** | `INVALID_RECIPIENT` | Suppress or verify |
| Recipient temporarily unavailable 4xx | Bounded | `RETRY_WAIT` | Backoff per provider |
| Mailbox full | Depends on code/provider | `RETRY_WAIT` or `NEEDS_REVIEW` | Avoid labeling unknown user |
| Sender/policy rejected 5.7.x | Do not retry as-is | `NEEDS_REVIEW` | Check permissions, domain, content |
| Server rate limit 4xx | Yes, after waiting | `RETRY_WAIT` | Reduce speed and concurrency |
| Invalid TLS config/certificate | **No** | `PAUSED_CONFIG` | Fix configuration safely |
| Timeout before DATA at known phase | Bounded | `RETRY_WAIT` | Backoff and check network |
| Timeout after DATA with unknown outcome | Do not retry blindly | `UNKNOWN_OUTCOME` | Reconcile, accept duplicate risk if retrying |
| Broken MIME/template | **No** until fixed | `NEEDS_REVIEW` | Fix template/data |

Do not use this table as a complete substitute for provider documentation. It is a framework for building an explainable policy with clear next actions.

## 21. Frequently Asked Questions

**1. Why shouldn't AUTH errors be retried continuously?**

If the password is wrong, the account is locked, or SMTP AUTH is disabled, unchanged credentials will continue to be rejected. Rapid retries increase load and can trigger security lockouts.

**2. Is a 535 error a recipient address error?**

No. 535 usually relates to the AUTH stage. Check the sending account, login mechanism, and permissions; do not put the recipient on an invalid-address list.

**3. Can a 454 error be retried?**

Yes, if the provider confirms it is a temporary AUTH error. Use backoff, cap attempts, and avoid burst retries.

**4. Should I delete the recipient's email when encountering SMTP 550?**

Not automatically. 550 can mean the mailbox does not exist, but it can also be a policy rejection. Only act on the recipient based on sufficiently clear signals such as enhanced status `5.1.1` in the proper context.

**5. Should 501 or 553 syntax errors be retried?**

Do not retry the same unfixed address. Update the data and validate syntax before creating a new send task.

**6. Is a full mailbox the same as an invalid recipient?**

No. A full mailbox can receive mail again once space is freed. Handle according to the code and provider policy.

**7. Is Spring's `MailAuthenticationException` enough to know credentials are wrong?**

It signals an authentication failure, but you need to inspect the root cause to distinguish misconfiguration, an expired token, and a temporary outage of the authentication service.

**8. What is the risk of retrying an error after DATA?**

The server may have accepted the message while the application missed the response. Retrying can produce a duplicate email.

**9. Does `Message-ID` prevent SMTP duplicates?**

Not guaranteed. It helps identify and correlate messages, but SMTP does not require servers or clients to deduplicate by `Message-ID`.

**10. Should the entire email be retried when only one recipient fails?**

Not if other recipients were already accepted. Track per-recipient results or split into one send intent per recipient.

**11. What should be done when all tasks fail with AUTH errors?**

Pause the corresponding SMTP account, alert, fix credentials/configuration, run a controlled check, and then resume the queue. Do not pointlessly increment each message's attempts.

**12. Can `InternetAddress.validate()` prove an address exists?**

No. That API mainly checks syntax. It does not confirm the mailbox actually exists or that the user owns the address.

**13. Can a bounce occur after `JavaMailSender` returns success?**

Yes. The SMTP relay can accept the message and the downstream delivery system can report a bounce later. Track DSN/provider events if required by the business.

**14. Does an outbox guarantee exactly-once email delivery?**

No. An outbox durably stores the send intent, but a worker can crash after SMTP acceptance and before recording the status, causing a retry to send a second message.

**15. Should 4xx errors always be retried?**

No. Retries must consider stage, response details, provider, attempt limits, and duplicate risk. A misconfiguration returning a temporary code should not be retried forever without human intervention.

## 22. Takeaways for Handling Authentication or Address Errors

**Do not blindly retry every `MailException`.** Distinguish authentication errors, recipient errors, policy errors, transient errors, and unknown send outcomes. SMTP responses consist of a three-digit code, an enhanced status code, and diagnostic text; interpret them together with the `CONNECT`, `AUTH`, `MAIL FROM`, `RCPT TO`, or `DATA` stage. **A generic 550 code is not enough to conclude a mailbox does not exist**, while AUTH 535 is typically a sending-account issue rather than a recipient address problem.

For persistent authentication failures, **pause the affected SMTP account, alert, and fix configuration** before performing a controlled retry. For malformed recipients or confirmed `user unknown`, **fix the data or suppress per policy** instead of resending as-is. For genuinely temporary errors, use **backoff, jitter, attempt limits, and concurrency limits**. If the server may have received `DATA`, mark **UNKNOWN_OUTCOME** and handle duplicate risk rather than assuming the send completely failed.

In Spring Framework Mail, keep classification logic outside `JavaMailSender`, extract the cause chain and SMTP diagnostics in the infrastructure layer, persist decisions in an outbox/queue, and retry only the **send task**, never re-running the business transaction. Protect credentials and recipient data in logs. The goal of retrying is not "keep trying until the error disappears," but **recover properly from recoverable errors, stop properly on errors that require fixes, and avoid creating new side effects**.
