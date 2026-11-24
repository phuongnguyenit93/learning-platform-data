# MailException and Common Spring Errors

In **Spring Framework Mail**, calling **JavaMailSender.send(...)** looks like an ordinary Java method call, yet behind it lie many steps that can fail: building addresses, assembling the MIME message, reading attachments, opening connections, SMTP authentication, exchanging commands with the mail server, and handing the message off to receiving systems. Spring groups many failures from this process under the **MailException** hierarchy so applications can handle them at a consistent boundary.

The hard part is **interpreting** the exception. An SMTP login failure calls for a different fix than a malformed recipient address; a network timeout differs from a provider rejecting a message for policy reasons. Crucially, **an exception during email sending does not always prove the remote server never received the message**. Therefore, merely writing a **catch (Exception)** block and retrying everything is insufficient for reliable applications.

This lesson belongs to the **Java Mail API** section of Spring Framework Mail, clarifying the **MailException** hierarchy, underlying Jakarta Mail/SMTP causes, how to inspect error details, and how to decide whether to report an error, fix configuration, or retry.

## 1. Which Layer Does MailException Sit At in the Sending Process?

When using Spring Mail, applications usually interact with one of two APIs:

- **MailSender** sends simple plain-text messages, typically via **SimpleMailMessage**.
- **JavaMailSender** extends sending capabilities with **MimeMessage**, supporting HTML, charsets, multipart, attachments, and **MimeMessagePreparator**.

A sending flow can be pictured as:

~~~text
Application calls JavaMailSender.send(...)
             |
             v
Prepare data: recipient, subject, body
             |
             v
Create SimpleMailMessage or MimeMessage
             |
             v
Spring Mail + Jakarta Mail transport
             |
             +-- Read SMTP config and attachments
             +-- TCP / TLS connection
             +-- Authentication (if required)
             +-- MAIL FROM / RCPT TO / DATA
             |
             v
SMTP server accepts or reports error
             |
             v
Mail infrastructure continues delivery (if accepted)
~~~

Errors across multiple steps are represented by Spring using an exception in the **org.springframework.mail.MailException** family. Depending on where the failure occurred and library version, however, Spring may wrap a lower-level exception such as **jakarta.mail.MessagingException**, **jakarta.mail.AuthenticationFailedException**, socket errors, or SMTP provider errors. Thus, **the MailException subtype** and **its cause chain** should be inspected together.

### MailException Is an Unchecked Exception

**MailException** is the abstract base class for Spring Mail errors and is a **runtime exception**; code calling **send(...)** does not have to declare **throws MailException** or write **try/catch** to compile.

Example:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class PlainMailSender {
    private final JavaMailSender mailSender;

    public PlainMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.test");
        message.setTo(recipient);
        message.setSubject("Notification");
        message.setText("Notification content.");

        // May throw MailException at runtime.
        mailSender.send(message);
    }
}
~~~

Declaring **throws MailException** is unnecessary, yet at the business or mail-worker boundary you still need deliberate error handling. If an exception escapes an HTTP controller without being mapped to a proper response, users may just see a 500 error; if it escapes a background job without being recorded, the job may be lost or reprocessed uncontrollably.

**Distinction:** methods on **MimeMessageHelper** can throw **MessagingException** or other checked exceptions while constructing MIME content; **JavaMailSender.send(...)** follows Spring Mail's error contract. The same message can fail during preparation and be wrapped by Spring into **MailPreparationException**, depending on how the API is used.

## 2. Spring Mail Exception Hierarchy

Common types in Spring Framework Mail:

~~~text
RuntimeException
    |
    +-- NestedRuntimeException (Spring)
           |
           +-- MailException  (abstract)
                  |
                  +-- MailAuthenticationException
                  +-- MailParseException
                  +-- MailPreparationException
                  +-- MailSendException
~~~

These subclasses describe **the stage or nature of the error at the Spring level**, rather than forming a one-to-one mapping to every SMTP reply code.

| Exception | Typical meaning | First line of action |
| --- | --- | --- |
| **MailAuthenticationException** | Failed to authenticate with the mail server/provider | Check credentials, auth mechanism, account, TLS/provider policy |
| **MailParseException** | Unable to parse/convert the message into a valid send structure | Check address data, syntax, or message content |
| **MailPreparationException** | Failed to prepare MimeMessage via preparator | Check content-building logic, attachments, MIME headers, and cause |
| **MailSendException** | Error during transport send operation; may involve multiple messages | Inspect SMTP/network response, failed messages, cause, and partial-send results |
| **MailException** | Common base class; can be caught to cover Spring Mail failure modes | Record error and apply appropriate fallback policy |

Important note: **exception class name alone is not enough to decide on retries**. For instance, **MailSendException** can stem from a temporary network drop, a permanently rejected mailbox, or an indeterminate send state. Different root causes can sit beneath the exact same exception type.

### Relationship with Jakarta Mail Exceptions

Spring Mail relies on Jakarta Mail to prepare and transport MIME messages. In modern sending flows, you may encounter:

- **jakarta.mail.MessagingException**: base error class at the Jakarta Mail layer.
- **jakarta.mail.AuthenticationFailedException**: related to authentication.
- **jakarta.mail.SendFailedException**: related to sending; may carry valid/invalid address lists.
- **jakarta.mail.internet.AddressException**: address syntax/parsing error.
- Network and TLS exceptions such as **ConnectException**, **SocketTimeoutException**, **UnknownHostException**, and **SSLException** deeper in the cause chain, depending on the failure.

In older Spring projects, JavaMail imports often start with **javax.mail** instead of **jakarta.mail**. The core flow is similar, though **never mix both namespaces** in the same dependency setup.

## 3. MailAuthenticationException: SMTP Login Failure

An application may send mail through an SMTP server requiring authentication. If credentials or the selected mechanism are rejected, Spring can throw **MailAuthenticationException**.

Common causes:

1. Wrong username/password or expired credentials.
2. Provider requires an **app password**, OAuth2, or another auth mechanism while the app uses a regular login password.
3. SMTP account is disabled, locked, or lacks sending permissions.
4. SMTP server rejects the **AUTH** mechanism proposed by the client.
5. TLS/STARTTLS settings do not satisfy provider policy; depending on where it fails, Spring may report a different exception type rather than MailAuthenticationException.

Illustrative configuration example:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: smtp-user
    password: your-secret-from-environment
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
~~~

This is an example configuration structure; in real applications, load secrets from environment variables or a secrets manager. Host, port, SSL/STARTTLS, and AUTH settings must follow the specific provider's documentation.

An SMTP reply such as:

~~~text
535 5.7.8 Authentication credentials invalid
~~~

may indicate an auth error, though **provider wording and detail codes are not always identical**. The Java-layer exception is a signal, while server/provider logs help pinpoint the exact cause.

**How to handle:** do not continuously retry with the same invalid password. First verify configuration and account permissions, and raise an operational alert if the error hits multiple send jobs. Never log passwords or access tokens. If a token expires and the app supports token refresh, perform refresh at the authentication layer rather than retrying indefinitely.

## 4. MailParseException: Unable to Build a Valid Message Structure

**MailParseException** is typically associated with Spring converting a simple message or content data into a structure usable by the mail layer.

Example input data:

~~~text
To: lan@@example.test
Subject: Document
Body: Hello
~~~

Syntactically invalid addresses can cause the parser to fail before touching SMTP. Depending on whether **SimpleMailMessage**, **MimeMessageHelper**, or **MimeMessagePreparator** is used and where addresses are processed, the resulting exception may be **MailParseException**, **MailPreparationException**, or a checked **AddressException/MessagingException** during message construction.

Therefore, never write logic assuming:

~~~java
// Incorrect:
// "Whenever a recipient address is invalid, MailParseException is guaranteed."
~~~

Instead, **validate recipient data before calling send(...)**, and treat MailParseException as an integration-boundary safeguard for surfacing unexpected errors.

**How to handle:** review addresses, From/To/Cc/Bcc, custom headers, and message construction. For user-supplied data, return an API contract error such as **INVALID_RECIPIENT** prior to sending. For errors from system data, hold the job for repair or mark it non-retryable without resending the same bad data.

## 5. MailPreparationException: MIME Message Preparation Failed

When using **JavaMailSender.send(MimeMessagePreparator)**, the application hands Spring a callback to prepare the MIME message. If the callback fails, Spring can wrap the error as **MailPreparationException**.

Possible causes include:

- Invalid MIME headers or addresses.
- Failure reading attachment files.
- Invalid multipart or content-structure assembly.
- Application code errors inside the preparation callback.
- Required data missing or data sources deleted before preparation runs.

Example:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public class DocumentMailService {
    private final JavaMailSender sender;

    public DocumentMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendDocumentNotice(String recipient) {
        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mimeMessage, true, "UTF-8");
            helper.setFrom("documents@example.test");
            helper.setTo(recipient);
            helper.setSubject("New document");
            helper.setText("The document has been updated.", false);
        };

        sender.send(preparator);
    }
}
~~~

This is a valid content-preparation flow when input data and configuration are sound. If an operation inside **preparator** throws a checked exception or runtime error, Spring can wrap it so callers observe **MailPreparationException**. This wrapping avoids propagating a slew of Jakarta Mail checked exceptions across services.

**Do not equate MailPreparationException with "SMTP tried to send and failed".** In many cases, SMTP has not even been contacted. Retrying the exact same broken content will not help; inspect data errors, template logic, or attachment resources.

### MailPreparationException vs. MessagingException

When creating **MimeMessage** manually and calling **MimeMessageHelper** outside a preparator:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, true, "UTF-8");
helper.setTo(recipient); // May throw MessagingException.
sender.send(mime);      // May throw MailException.
~~~

A content-building error can surface directly as **MessagingException** on the helper line before reaching **send(...)**. When using a preparator callback, Spring has the opportunity to wrap preparation errors. Thus, the final exception class depends on **which API boundary threw the error**, not solely on "whether the email is valid".

## 6. MailSendException: Send-Stage Failures and Partial Delivery

**MailSendException** typically indicates Spring could not complete sending one or more messages as intended. Common causes:

- DNS, TCP, or SMTP server connectivity issues.
- Unexpected server disconnect, timeout, or TLS failure.
- SMTP rejects certain commands, sender, recipients, or message content.
- Mail server/provider enforces rate limits or anti-spam rules.
- Sending multiple messages where **some succeed and some fail**.

Example sending multiple messages:

~~~java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("notifications@example.test");
first.setTo("lan@example.test");
first.setSubject("Notice A");
first.setText("Content A");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("notifications@example.test");
second.setTo("minh@example.test");
second.setSubject("Notice B");
second.setText("Content B");

mailSender.send(first, second);
~~~

Suppose the first message is submitted successfully while the second is rejected. A **MailSendException** does not prove **neither** was sent. When sending **multiple messages**, Spring exposes details on failed messages via **MailSendException.getFailedMessages()** when the implementation captures that data.

Conditional logging example:

~~~java
import org.springframework.mail.MailSendException;

try {
    mailSender.send(first, second);
} catch (MailSendException ex) {
    int failedCount = ex.getFailedMessages().size();
    logger.warn(
            "Mail sending failed; recorded failed message count: {}",
            failedCount,
            ex
    );
    throw ex;
}
~~~

In the example, **logger** is assumed to be configured on the class. **failedCount** is the number of message objects recorded in the failure map, not the total number of rejected recipients, nor proof that all other messages reached an Inbox. Alongside the failed-messages map, you can inspect **getMessageExceptions()** for exceptions tied to the send operation.

### One Message with Multiple Recipients

If a single MimeMessage has multiple **To/Cc/Bcc** addresses, SMTP may accept one recipient and reject another. Jakarta Mail exceptions such as **SendFailedException** can carry address arrays like:

- **valid sent**: addresses determined by the transport to have been sent successfully at that step.
- **valid unsent**: valid addresses not yet sent.
- **invalid**: addresses deemed invalid in that send context.

These groups depend on transport responses and capabilities; not every network failure supplies complete information. **"Valid sent" does not mean "delivered to Inbox"**. Spring may wrap lower-level exceptions inside **MailSendException**, so inspect the cause and provider details for per-recipient specifics.

A connection failure after the server already accepted the message leaves an **indeterminate state**. You cannot blindly resend to every recipient without risking duplicate emails.

## 7. Common Real-World Spring Mail Errors

Operators often see a Java error message while the root cause lies in network setup, the SMTP server, or recipient data. The table below is an **investigation guide**, not a strict mapping: the same symptom can raise different exceptions depending on failure location and mail transport.

| Symptom | Common causes | Possible exceptions/causes | Where to check |
| --- | --- | --- | --- |
| **Authentication failed** | Invalid credentials, account disallowed for SMTP AUTH | **MailAuthenticationException**, **AuthenticationFailedException** | Check username, secret, AUTH method, and provider policy |
| **Connection refused** | Wrong host/port, SMTP service not listening, firewall block | **MailSendException** wrapping connection error | DNS, host, port, firewall, outbound rules |
| **Connection timed out** | Network drop or server unresponsive in time | **MailSendException**, socket connect timeout | Check network and **mail.smtp.connectiontimeout** |
| **Read timed out** | Connected but waiting too long for SMTP reply | **MailSendException**, **SocketTimeoutException** | Check SMTP load, proxies, and **mail.smtp.timeout** |
| **Write timed out** | Writing data to socket blocked too long | **MailSendException** or transport error | Check network, message size, and **mail.smtp.writetimeout** |
| **SSL handshake failed** | Wrong TLS mode, certificate, or trust chain | Usually mail send/transport error with SSL cause | Check STARTTLS/SMTPS, hostname, certificates |
| **Invalid address** | Malformed address syntax or violates parser rules | **AddressException**, **MailParseException**, or **MailPreparationException** | Validate input pre-send, distinguish one mailbox vs. list |
| **Recipient rejected** | Address cannot receive mail, provider policy, or cap | **MailSendException** with underlying SMTP reply | Check SMTP code, specific recipient, provider events |
| **Sender rejected** | Not permitted to send from From/envelope sender | **MailSendException** or transport error | Check send permissions, domain, sender policy |
| **Message too large** | Email after MIME encoding exceeds provider limit | **MailSendException** with SMTP reply | Count Base64 overhead, headers, and attachments |
| **MIME preparation failed** | File source, template, encoding, or MIME build error | **MailPreparationException** or checked **MessagingException** | Check resources and MimeMessage construction |
| **Temporary SMTP error** | Busy server, temporary quota, transient error | **MailSendException** with SMTP **4xx** if present | Retry with backoff after scoping the error |
| **No mail sender bean** | Missing dependency/config or bean not created | Spring DI/config error, not necessarily **MailException** | Check mail starter and auto-configuration settings |

The last row shows that not every email-related error is a **MailException**. For example, Spring failing to create a **JavaMailSender** bean at startup can raise **NoSuchBeanDefinitionException**, **UnsatisfiedDependencyException**, or configuration errors. These happen **before any mail-sending call is ever made**.

### DNS, TCP, TLS, and SMTP Are Distinct Stages

~~~text
Hostname resolution (DNS)
        |
        +-- UnknownHostException
        v
TCP connection to host:port
        |
        +-- Connection refused / connect timeout
        v
TLS setup if required
        |
        +-- SSL handshake/trust error
        v
SMTP greeting / EHLO / AUTH
        |
        +-- Authentication failed / server unavailable
        v
MAIL FROM / RCPT TO / DATA
        |
        +-- Sender/recipient/message rejected
        v
SMTP server accepts message
        |
        v
Downstream delivery steps outside the Spring call
~~~

From the application perspective, many underlying failures surface as **MailSendException**. When analyzing, asking **which stage failed** is usually more helpful than counting how often a given exception class appears.

## 8. SMTP Reply Codes and Careful Interpretation

SMTP uses three-digit reply codes; the leading digit distinguishes success, temporary failure, and failure reported as permanent in that command's context.

| Illustrative group/code | General meaning | Action to consider |
| --- | --- | --- |
| **2xx** | Corresponding command accepted/succeeded | Does not mean the email reached an Inbox |
| **4xx** | SMTP reports a temporary error | Can retry with backoff and bounds |
| **5xx** | SMTP reports a permanent error at that step | Usually requires fixing data/config or checking policy |
| **421** | Service unavailable/closing channel, per server | Check server health, retry in a controlled manner |
| **450/451/452** | Temporary errors involving mailbox, processing, or resources | Inspect extended codes and provider details |
| **535** | Commonly used for SMTP AUTH errors | Check credentials/auth mechanism |
| **550/553** | Rejections of mailbox, sender, recipient, or policy | Do not conclude root cause from three digits alone |
| **552** | May relate to storage/size limits in context | Inspect detailed reply and provider limits |
| **554** | May indicate transaction/message rejection by policy | Check reputation, send permissions, content, provider policy |

SMTP messages may include **enhanced status codes** like **5.1.1** or **4.7.0**, adding detail on the failure class. However, exact code assignment, descriptions, and policies vary among providers.

Abbreviated transcript example:

~~~text
C: EHLO mail-app.example.test
S: 250-smtp.example.test
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN

C: MAIL FROM:<no-reply@example.test>
S: 250 Sender accepted

C: RCPT TO:<unknown@recipient.test>
S: 550 5.1.1 User unknown
~~~

This only illustrates command ordering, not a full production session to copy verbatim; in configurations requiring TLS, the client must complete STARTTLS and proper authentication before sending. Never transmit credentials over an unencrypted channel.

### Does "550" Always Mean the Email Does Not Exist?

**No.** A server can return **550** when a mailbox does not exist, when an account is blocked by policy, when a domain is disallowed, or for other reasons. To distinguish a "bad address" from "blocked by policy", examine the full reply text, enhanced status code if present, and provider data. Never automatically purge all subscribers with a **550** code without understanding its meaning in that environment.

### Does SMTP Returning Success Guarantee Delivery?

**No.** When the application receives success from the SMTP server, the server may only have **accepted responsibility for processing** the message. Along subsequent delivery hops, mail can bounce, be delayed, forwarded, or filtered as spam. Thus, **SUBMITTED** and **DELIVERED** must be distinct state concepts if your system tracks email lifecycles.

## 9. Catching Exceptions by Group to Avoid Masking Root Causes

In a mail-sending service, you can classify at the Spring layer as follows:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) {
        MimeMessagePreparator preparator = mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, false, "UTF-8");
            helper.setFrom("welcome@example.test");
            helper.setTo(recipient);
            helper.setSubject("Welcome");
            helper.setText("Your account has been created.", false);
        };

        try {
            mailSender.send(preparator);
        } catch (MailAuthenticationException ex) {
            // SMTP account/config issue; alert operations.
            throw new MailDispatchFailure(
                    "SMTP_AUTH_FAILED", ex
            );
        } catch (MailParseException | MailPreparationException ex) {
            // Check data, template, or MIME structure.
            throw new MailDispatchFailure(
                    "MESSAGE_PREPARATION_FAILED", ex
            );
        } catch (MailSendException ex) {
            // Inspect SMTP/network cause before deciding on retry.
            throw new MailDispatchFailure(
                    "SUBMISSION_FAILED_OR_UNKNOWN", ex
            );
        } catch (MailException ex) {
            // Fallback for other Spring Mail errors.
            throw new MailDispatchFailure(
                    "MAIL_FAILED_UNCLASSIFIED", ex
            );
        }
    }

    public static class MailDispatchFailure extends RuntimeException {
        private final String code;

        public MailDispatchFailure(String code, Throwable cause) {
            super(code, cause);
            this.code = code;
        }

        public String getCode() {
            return code;
        }
    }
}
~~~

The sample code intentionally **does not retry itself**. It maps exception groups to business codes so an external component can decide: return an API response, keep the mail job for retry, or raise an alert. A **MailSendException** is labeled **SUBMISSION_FAILED_OR_UNKNOWN** because server-side state may remain uncertain after a network failure.

Key points to keep in mind:

- Catch subclasses **before** the base **MailException**.
- Never use **catch (Exception)** to treat every error as "transient SMTP failure".
- Never convert **MailAuthenticationException** into a recipient-input validation error.
- Preserve **cause** so operations can trace underlying details.
- If the wrapper exception is logged at a controller or worker boundary, avoid logging the entire stack trace redundantly at every layer.
- Never return raw stack traces or provider replies containing infrastructure details to end users.

If the application must handle **MessagingException** while building a message outside a preparator, catch or propagate it at the appropriate place; it is not automatically wrapped as MailException there. Keep **prepare** and **send** boundaries clear to choose the right handling strategy.

### When Should You Catch the Base MailException?

When a layer's sole responsibility is **marking a send job incomplete and forwarding the error to monitoring**, catching the base **MailException** may suffice:

~~~java
try {
    mailSender.send(message);
    markSubmitted(jobId);
} catch (MailException ex) {
    markSubmissionError(jobId, ex);
    throw ex;
}
~~~

`markSubmitted` and `markSubmissionError` here are pseudocode representing application status updates. If retries are needed, classify the cause in the worker/job handler and handle **indeterminate submission state**. Never assume `markSubmissionError` automatically means "the server definitely did not receive the email".

### Where Business Logic Must Decide Instead of the Exception Alone

A registration welcome email might be a secondary task, whereas a verification-code email directly blocks completing the user flow. The exact same **MailSendException** can lead to two different product decisions:

- Welcome email fails: keep the created account and schedule a retry for the send job.
- Verification-code email fails: the account may stay **unverified**, allowing the user to request a resend after a cooldown period.

Which decision is right depends on business rules, not solely on the exception class name.

## 10. Choosing Retries by Error Type and Concrete Evidence

Retrying is an essential mechanism, yet retrying the wrong way can cause **duplicate sends**, SMTP overload, or provider account suspension.

| Issue type | Should you retry? | Reason |
| --- | --- | --- |
| Wrong credentials, locked account | **Do not auto-retry with same config** | Cannot recover merely by calling again |
| Syntactically invalid recipient data | **No**, wait for data fix | Same input reliably triggers the same error |
| Broken template/multipart/attachment | **Usually no** until cause is fixed | Retrying does not change broken data |
| Transient DNS/network error | **Possible**, with backoff and limits | Infrastructure glitches can self-recover |
| Transient SMTP **4xx** | **Possible**, per provider policy | Server explicitly requests trying later |
| SMTP **5xx** due to data/policy | **Usually no** until cause is resolved | Rejection is reported permanent at that step |
| Timeout after sending DATA | **Requires inspection due to uncertain state** | SMTP may have accepted the mail despite lost reply |
| Provider confirms some recipients succeeded | **Do not blindly retry whole batch** | Risks duplicating for already-submitted users |
| Message passed its useful expiration | **Do not continue sending** | Content may now be stale or invalid |

### Exponential Backoff and Jitter

A common algorithm picks the delay for attempt **k**:

~~~text
delay = min(maxDelay, initialDelay * 2^(k - 1))
actualDelay = delay + randomizedJitter
~~~

For example (illustrative only), start at a few seconds and grow gradually up to a max attempt count or expiration deadline. **Jitter** prevents workers from waking up in lockstep and hammering an already overloaded SMTP server.

When a provider supplies **Retry-After** or valid retry-timing hints, prioritize that guidance per the specific contract. Guard against infinite retries, and record attempt counts, causes, next-attempt timestamps, and per-recipient or per-job status.

### Indeterminate State Errors Are a Special Case

Suppose:

1. The client finishes transmitting the message body over SMTP.
2. The server accepts the message and prepares a success reply.
3. The connection drops before the client receives the reply.
4. Spring reports **MailSendException** due to the network failure.

On the application side, we know the submission attempt errored, **without knowing for sure whether the server accepted the email**. Retrying can produce two identical emails. If the system needs to minimize duplicates, use:

- **Business key / idempotency key** so two send jobs are never created for the same event.
- **Message-ID** and provider IDs where supported to correlate logs and events, noting Message-ID alone does not force mail infrastructure to deduplicate.
- **One job per recipient** if independent status and retries are needed.
- **Provider data, webhooks/DSN** to reconcile outcomes when available.

Even with persisted jobs and one worker processing at a time, there is no atomic transaction across database and SMTP. Systems typically have to accept **at-least-once submission** or design to mitigate duplicate email effects.

## 11. Timeout Configuration: Avoiding Overly Long Calls

Jakarta Mail timeout settings are commonly passed through **spring.mail.properties** in Spring Boot:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: smtp-user
    password: placeholder-use-secret-manager
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

Timeout values are in **milliseconds** in standard SMTP transport configuration:

- **mail.smtp.connectiontimeout**: wait limit for establishing a connection.
- **mail.smtp.timeout**: wait limit for reading data/responses from the socket.
- **mail.smtp.writetimeout**: wait limit for writing data to the socket.

These numbers are illustrative only and must be chosen for your network latency and operational needs. In many setups without timeouts, default behavior can hang for a very long time. Setting timeouts controls resource usage, yet **does not guarantee a call aborts at the exact desired instant in every phase** and does not eliminate indeterminate states after the server already received the message.

If a Spring MVC app sends mail directly inside an HTTP request, SMTP time adds directly to API response latency. Consider a background worker or queue to decouple sending from requests when latency or reliability matters. Merely moving **send(...)** to **@Async** reduces request wait time, **but does not provide durable persistence or retries after a process restart**.

## 12. Logging and Monitoring MailException Properly

To resolve a mail-sending incident, seeing only the line:

~~~text
Failed to send mail
~~~

is usually insufficient. The system needs to know which job failed, at which stage, and an actionable cause. Yet logging raw recipient addresses, message bodies, usernames, and passwords in every log risks exposing private data.

### Useful Fields to Capture

| Field | Purpose |
| --- | --- |
| **mailJobId** | Correlate a send request across logs, retries, and provider events |
| **notificationType** | Identify whether the email is registration, invoice, or alert |
| **attemptNumber** | Number of submission attempts made |
| **failureCategory** | Application-level category: AUTH, PREPARATION, NETWORK, SMTP_REJECTED, UNKNOWN |
| **exceptionClass** | Identify which exception Spring threw |
| **smtpStatus** (if available) | 4xx/5xx reply or enhanced status from provider |
| **retryScheduledAt** | Scheduled time for the next attempt |
| **recipientCount** | Count recipients without logging every address |
| **providerMessageId** (if available) | Used to reconcile against provider status |

Not every exception contains **smtpStatus** or **providerMessageId**. Keep those fields **optional** rather than parsing fragile message strings unreliably.

Operational metrics can be defined as:

~~~text
mail_submissions_total{result="submitted"}
mail_submissions_total{result="failed",category="auth"}
mail_submissions_total{result="failed",category="transport"}
mail_retry_pending
mail_outbox_oldest_pending_age_seconds
mail_provider_bounces_total
~~~

These are illustrative metric names. Avoid putting **recipient email** or **arbitrary message IDs** into metric labels, as they cause high cardinality and expose personal data. Use access-controlled logs or storage for detailed lookups when necessary.

### Should You Log Full Stack Traces?

For an unknown root-cause incident, a stack trace helps by showing exception classes and cause chains. However:

- A normalized input validation error usually only needs appropriate log severity, not a full stack trace on every request.
- An SMTP config outage across thousands of jobs can flood logs; aggregate and alert by category.
- Avoid capturing **passwords**, sensitive bodies, or full raw emails in exception reporting.
- Log at **one accountable boundary**; do not let every service catch, log, and rethrow the exact same error.

A logger cannot replace durable mail job state. If the process stops, logs alone make it hard to guarantee the system knows which jobs need retrying. Persist **send-job business state** in suitable storage.

## 13. MailException in Transactions and Background Processing

Consider the flow "save order then send confirmation email":

~~~java
@Transactional
public void placeOrder(OrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailService.sendOrderConfirmation(order);
}
~~~

This is **pseudocode** illustrating transaction relationships, not a complete Java class. Database **@Transactional** does not create an atomic transaction with SMTP. If the mail server accepts the email and a later database statement fails causing rollback, the customer can still receive the email. If data commits and SMTP fails, rolling back the mail send does not automatically undo the order.

To separate responsibilities, the system can:

1. Save the order and an **outbox event** requesting notification in **the same database transaction**.
2. Commit the transaction and return the order-creation result.
3. Have a worker read **PENDING** jobs, build MIME messages, and call **JavaMailSender.send(...)**.
4. Record **SUBMITTED**, **RETRY_PENDING**, **FAILED**, or **UNKNOWN** with cause and retry schedule per policy.
5. When provider events or DSNs arrive, update delivery status accordingly.

~~~text
HTTP Request
     |
     v
Service -> Database transaction
            |-- save business record
            |-- save mail outbox event
            '-- COMMIT
     |
     v
HTTP response

Background worker
     |
     |-- load pending outbox
     |-- build MIME message
     |-- JavaMailSender.send(...)
     |      |
     |      +-- MailPreparationException -> handle content error
     |      +-- MailAuthenticationException -> alert operations
     |      +-- MailSendException -> classify cause/SMTP
     |
     '-- persist result / retry schedule
~~~

A transactional outbox **persists send intent** alongside business data so jobs are not lost if the process dies after commit. Still, it **does not turn database + SMTP into a distributed transaction with exactly-once delivery**. A worker can crash after the provider accepted the email but before saving status, so ambiguous retry risks must still be managed.

### When Should You Return an HTTP Error?

If a user submits a request with invalid recipient data, such as **lan@@example.test**, the API should catch it during validation and return an appropriate input error, typically **400 Bad Request**. Never let bad data travel down to SMTP only to turn into an opaque failure.

If the SMTP server is temporarily unavailable:

- For synchronous direct-send APIs, return a service error with a stable error code.
- For APIs that **accept a send request** and persist it to an outbox, you can return **202 Accepted** or a contract status without waiting on SMTP.
- For APIs creating a primary business entity, reflect the business outcome accurately and track notification state separately.

Never return a promise to the user stating **"the email has been delivered to your Inbox"** merely because **JavaMailSender.send(...)** threw no exception.

## 14. Scenario-Based Error Analysis Examples

### Scenario A — Wrong SMTP Password

The application receives **MailAuthenticationException** with authentication failure details in the cause.

**Analysis:** this is usually a configuration or system-account permission issue. Immediately retrying hundreds of times with the same credentials risks locking the account and will not self-heal.

**Action:** verify secrets, SMTP AUTH permissions, TLS setup, and provider policy; alert operations; resume sending only once fixed.

### Scenario B — Malformed Recipient Syntax

A user enters **lan@@example.test**; the application receives **AddressException** while constructing the MIME message or Spring wraps it in the corresponding MailException subtype.

**Analysis:** the error lies in input data; SMTP may not have been contacted at all.

**Action:** validate/normalize per input policy prior to sending, return **INVALID_RECIPIENT**, and do not retry with the same bad address.

### Scenario C — Attachment File Was Deleted

A worker claims a job at 10:00 and builds the email at 10:05; the attachment path no longer exists. MIME preparation or reading fails.

**Analysis:** this may be an application resource error, surfacing as MailPreparationException, MessagingException, or a serialization/send failure depending on attachment setup and read timing.

**Action:** ensure attachment sources are stored durably until sending completes, or move content to lifecycle-managed storage. Retrying when the file is permanently gone is futile.

### Scenario D — SMTP Returns 451

The provider replies with code **451** to a send command, described as a temporary error.

**Analysis:** likely eligible for retry, though check provider details and possible rate limits.

**Action:** transition the job to **RETRY_PENDING** with backoff and max attempts, monitor failure rates, and avoid firing thousands of immediate retries.

### Scenario E — SMTP Returns 550 for One Recipient

A message has three recipients; the server rejects one address with **550**, while two others are accepted.

**Analysis:** outcomes can vary per recipient. Do not conclude all three failed or mechanically retry everyone.

**Action:** inspect address groups in **SendFailedException** or provider data if present, record per-recipient results, and distinguish policy blocks from nonexistent mailboxes using concrete details.

### Scenario F — Timeout After Sending DATA

The Spring call reports **MailSendException** with a timeout cause. Provider logs show the message was received before the connection dropped.

**Analysis:** the application received no success reply, yet the email may still be delivered. Direct retry risks sending a second email.

**Action:** correlate job ID/message ID with provider logs or events, weigh duplicate-send risk, and mark the attempt **UNKNOWN** until sufficient evidence exists.

### Scenario G — Missing JavaMailSender Bean

The application fails to start because a constructor requires **JavaMailSender** and no matching bean exists.

**Analysis:** this is usually a Spring Boot dependency-injection or configuration error, not a MailException during a send call.

**Action:** verify the mail starter dependency, **spring.mail.host**, or session/bean configuration. Do not troubleshoot the SMTP server when sending code has not even run.

### Scenario H — Submitted Successfully Yet User Cannot Find It

**JavaMailSender.send(...)** returns normally, yet the customer reports never seeing the email.

**Analysis:** this may be a post-submission delivery issue, spam filtering, alias, forwarding, mailbox, or provider policy issue. No MailException does not mean the email reached the Inbox.

**Action:** inspect provider events, bounces, destination address, SPF/DKIM/DMARC, and infrastructure delivery info. Never fabricate a MailSendException to represent an "undelivered" state that the application did not actually observe.

## 15. Questions to Answer Before Handling a MailException

When seeing a mail-sending failure in Spring, ask these questions in order:

~~~text
At which step did the exception occur?
  |
  +-- Spring context failed to create bean?
  |      -> Config/DI error, SMTP not contacted
  |
  +-- Building SimpleMailMessage / MimeMessage?
  |      -> Check inputs, charset, headers, MIME, attachments
  |
  +-- Authenticating with SMTP?
  |      -> Check credentials, AUTH, TLS, account permissions
  |
  +-- Connecting or transmitting data?
  |      -> Check DNS/TCP/TLS/timeouts/cause
  |      -> Determine whether submit state is certain or unknown
  |
  +-- Server rejected sender/recipient/message?
  |      -> Read SMTP code and provider details
  |      -> Determine transient failure vs. data fix needed
  |
  +-- Server accepted, yet email hasn't reached recipient?
         -> Track delivery/bounces via provider
         -> Do not infer MailException from missing Inbox mail
~~~

Key follow-up decisions: **does input/config need fixing, is retry safe, who should be retried, is there duplicate risk, and how should business state be recorded**.

**MailException is Spring Framework Mail's convenient error boundary, not the final verdict on an email's delivery journey.** Distinguishing **MailAuthenticationException**, **MailParseException**, **MailPreparationException**, and **MailSendException**, and combining exception type with cause, SMTP replies, and job state, enables accurate error handling that is easy to investigate and minimizes duplicate emails.
