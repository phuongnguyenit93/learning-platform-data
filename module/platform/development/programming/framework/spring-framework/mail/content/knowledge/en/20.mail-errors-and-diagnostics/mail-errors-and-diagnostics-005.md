# MessagingException and Root Causes from Jakarta Mail

When sending emails using Spring Framework Mail, an error appearing in **MimeMessageHelper**, **Jakarta Mail**, SMTP transport, or network connectivity can be represented under several exception classes. Looking only at the outermost message makes it easy to jump to wrong conclusions: seeing **MailSendException** and assuming "SMTP rejected it", seeing **MessagingException** and assuming "wrong address", or immediately retrying on any timeout.

In reality, **`jakarta.mail.MessagingException`** is Jakarta Mail's foundational exception type for many mail-system failures. It is not the name of a single root cause. To diagnose accurately, inspect the **exception subtype**, **cause chain**, **Jakarta Mail linked exceptions**, **sending stage**, and, if available, the **SMTP reply code**.

For example, the same send operation can fail because:

- Unable to create a MIME part due to an invalid attachment name or data.
- Unable to connect to the SMTP server.
- STARTTLS or TLS handshake error.
- SMTP login failed.
- One or more recipient addresses were rejected.
- The message was rejected by the server at the DATA stage.
- Connection dropped after the server may have accepted the email.

Those situations cannot share a single retry policy. The goal of this lesson is to understand **`MessagingException` and how to find actual root causes from Jakarta Mail**, then turn those findings into structured diagnostic signals and appropriate actions in a Spring application.

## 1. Where Do Spring Mail and Jakarta Mail Sit in the Sending Flow?

A Spring application typically works with **`JavaMailSender`**, **`MimeMessage`**, and **`MimeMessageHelper`**. Underneath, Spring uses Jakarta Mail to construct the message and execute transport.

~~~text
Application service
       |
       v
JavaMailSender / MimeMessageHelper
       |
       +-- Build MIME headers, body, attachments, inline resources
       |
       v
Jakarta Mail
       |
       +-- Session
       +-- Message / MimeMessage
       +-- Transport
       |
       v
SMTP provider / server
       |
       v
Remote mail infrastructure
~~~

Errors can appear at two major points:

1. **Message preparation:** Jakarta Mail APIs are called to set headers, body, multipart, or attachments. Some methods declare **`throws MessagingException`**.
2. **Executing send:** Spring `JavaMailSender` invokes transport. Errors are translated by Spring into **`MailException`** or an appropriate runtime subtype for the application to handle.

Key point: **`MessagingException` is not synonymous with `MailException`**. They belong to two different exception hierarchies.

### 1.1. Example of Preparation with Checked Exception

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("user@example.net");
helper.setSubject("Notification");
helper.setText("Hello!", false);
~~~

`MimeMessageHelper` operations may declare **`MessagingException`**. Therefore, code inside the method must catch the exception or declare `throws` per Java rules.

### 1.2. Example of Sending with Spring Runtime Exception

~~~java
mailSender.send(message);
~~~

**`JavaMailSender.send(...)`** is declared per the Spring Mail API and typically throws **`MailException`** or a subtype if sending fails. Underlying exceptions from Jakarta Mail can be preserved in the cause or accompanying detail structures.

Hence, distinguish **MIME construction errors** from **mail sending errors** before classifying.

## 2. What Is MessagingException?

**`jakarta.mail.MessagingException`** is Jakarta Mail's checked exception representing issues in mail send/receive APIs, MIME, or transport. It extends **`Exception`**, so a method declaring `throws MessagingException` must follow Java's checked exception rules.

Example:

~~~java
import jakarta.mail.MessagingException;

public MimeMessage createMessage(
        JavaMailSender sender,
        String recipient
) throws MessagingException {

    MimeMessage message = sender.createMimeMessage();

    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

    helper.setTo(recipient);
    helper.setSubject("Confirmation");
    helper.setText("Email content", false);

    return message;
}
~~~

This method lets the caller know that preparing `MimeMessage` can fail.

### 2.1. Not Every `MessagingException` Means the Same Thing

Important subtypes:

| Exception type | Common context | Questions to check |
| --- | --- | --- |
| **MessagingException** | General mail error | Which step failed? Is there a nested exception? |
| **AuthenticationFailedException** | Mail server authentication | Credentials, token, AUTH mechanism, or policy? |
| **SendFailedException** | Send failure, possibly address-related | Which recipients are valid, invalid, or unsent? |
| **AddressException** | Email address syntax | Is the address input valid? |
| **ParseException** | Parsing mail content or syntax | Were headers/addresses/content constructed properly? |

**`AddressException`** belongs to package **`jakarta.mail.internet`** and is a specific subtype related to address syntax. Its class name does not mean SMTP confirmed the mailbox does not exist: syntax checking and real mailbox verification are two different things.

### 2.2. Namespace Migration Across Versions

In Spring Framework 6 and Spring Boot 3+, Jakarta Mail uses namespace **`jakarta.mail`**.

Example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
~~~

Many older Spring 5/JavaMail docs or codebases use:

~~~java
import javax.mail.MessagingException;
import javax.mail.internet.MimeMessage;
~~~

**`javax.mail`** and **`jakarta.mail`** are two distinct API namespaces. Do not mix them in modern Spring Mail code if dependencies target Jakarta. When upgrading, align dependencies, imports, and Jakarta Mail provider implementations together.

## 3. Difference Between `MessagingException` and `MailException`

Spring places an abstraction over `JavaMailSender` so application code handles mail-sending failures via Spring runtime exceptions.

~~~text
Spring Mail
  MailException
      |
      +-- MailAuthenticationException
      +-- MailSendException
      +-- MailParseException
      +-- MailPreparationException
      |
      +-- Other subtypes

Jakarta Mail
  MessagingException
      |
      +-- AuthenticationFailedException
      +-- SendFailedException
      +-- ParseException
            |
            +-- AddressException
~~~

The diagram shows common types and primary relationships, not the complete class hierarchy across every library version.

| Aspect | Jakarta `MessagingException` | Spring `MailException` |
| --- | --- | --- |
| Package | **`jakarta.mail`** | **`org.springframework.mail`** |
| Exception kind | Checked | Runtime |
| Commonly encountered | MIME API, Jakarta Mail transport | `JavaMailSender` API and Spring abstraction |
| Cause details | Subtype, `getNextException`, cause | Spring subtype, cause, failed messages depending on class |
| Used to handle | Inspect low-level error details from Jakarta Mail | Decide error handling at the Spring application layer |

### 3.1. Why Does Spring Wrap Exceptions?

Applications usually do not want every mail-sending service forced to declare checked transport exceptions. `JavaMailSender` lets Spring translate provider errors into subtypes of `MailException`.

For instance, an AUTH error from Jakarta Mail may surface in Spring as **`MailAuthenticationException`**, while **`AuthenticationFailedException`** remains inside the cause.

However, there is no guarantee every SMTP error maps neatly to a single Spring subtype. Inspect both the wrapper and nested underlying causes.

### 3.2. General Catching Pattern

~~~java
try {
    mailSender.send(message);
} catch (MailAuthenticationException ex) {
    // Authentication is a group requiring separate handling.
} catch (MailSendException ex) {
    // Inspect failed messages and root causes.
} catch (MailException ex) {
    // Other Spring Mail-layer error.
}
~~~

Place subtypes before superclasses in catch order. Do not catch **`Exception`** and auto-retry every failure, because preparation, syntax, and configuration errors cannot necessarily be recovered by retrying.

## 4. Jakarta Mail's Special Linked-Exception Mechanism

A crucial point is that **`MessagingException` has an exception-chaining mechanism via `getNextException()`**. That is why diagnostics inspecting only Java **`Throwable.getCause()`** may miss information.

Conceptual view:

~~~text
MessagingException
    |
    +-- getCause() --> cause exposed by standard Java
    |
    +-- getNextException() --> Jakarta Mail's linked exception
                                 |
                                 +-- May be another MessagingException
                                 +-- May be a SocketException
                                 +-- May be an SSLException
                                 +-- May be a provider exception
~~~

Depending on library version and how an exception is constructed, **`getCause()` may point to the nested exception**, yet you should not assume the cause chain always reflects every Jakarta Mail link.

### 4.1. `getNextException()`

API:

~~~java
Exception next = messagingException.getNextException();
~~~

It returns the next exception in the linked chain if present, or `null`.

Diagnostic example:

~~~java
if (error instanceof MessagingException messaging) {
    Exception next = messaging.getNextException();

    if (next != null) {
        log.warn(
                "Jakarta Mail nested exception type: {}",
                next.getClass().getName()
        );
    }
}
~~~

This example only logs the exception type. If traversing further links, bound the traversal and guard against cycles.

### 4.2. `setNextException()`

Jakarta Mail also provides:

~~~java
boolean added = messagingException.setNextException(otherException);
~~~

This API allows appending an exception to the linked chain in appropriate cases. Normally, **application code does not need to mutate the exception chain manually**. Manually appending errors can hinder diagnostics if conventions are unclear.

In normal application flows, **observe `getNextException()`** instead of attaching unrelated exceptions just for logging.

### 4.3. `getCause()` Still Matters

A Spring `MailException` may wrap a Jakarta `MessagingException` via standard Java `cause`. From `MessagingException`, you then need to check `getNextException`.

~~~text
MailSendException (Spring)
       |
       +-- getCause()
              |
              v
         MessagingException (Jakarta)
              |
              +-- getNextException()
                     |
                     v
                SocketTimeoutException
~~~

If you log only the outermost class, you lose the timeout information. If you read only `getCause` from `MessagingException`, you may miss exceptions linked via Jakarta Mail's own API in some cases.

### 4.4. Do Not Confuse Exception Messages with Root Causes

A string like **"Could not send message"** only indicates a high-level operation failed. It cannot distinguish:

- Wrong account credentials.
- Server rejected `RCPT TO`.
- Attachment file unreadable.
- TLS handshake failure.
- Connection timeout.
- Server received DATA but the response was lost.

Sub-messages may add context, but you must check classes, SMTP codes, and actual phase.

## 5. Utility to Traverse `cause` and Jakarta `nextException`

A small utility can collect **exception types** across both **`getCause()`** and **`getNextException()`**. The code below avoids cycles and does not log secrets.

~~~java
import jakarta.mail.MessagingException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class MailExceptionInspector {

    private MailExceptionInspector() {
    }

    public static List<String> collectExceptionTypes(
            Throwable root
    ) {
        if (root == null) {
            return List.of();
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());
        List<String> result = new ArrayList<>();

        pending.addLast(root);

        while (!pending.isEmpty() && result.size() < 32) {
            Throwable current = pending.removeFirst();

            if (!visited.add(current)) {
                continue;
            }

            result.add(current.getClass().getName());

            Throwable cause = current.getCause();
            if (cause != null && cause != current) {
                pending.addLast(cause);
            }

            if (current instanceof MessagingException mailError) {
                Exception next = mailError.getNextException();

                if (next != null && next != current) {
                    pending.addLast(next);
                }
            }
        }

        return result;
    }
}
~~~

Usage example:

~~~java
try {
    mailSender.send(message);
} catch (MailException ex) {
    List<String> types =
            MailExceptionInspector.collectExceptionTypes(ex);

    log.error(
            "Mail operation failed. Exception types: {}",
            types
    );

    throw ex;
}
~~~

### 5.1. Why Use `IdentityHashMap`?

Because exceptions can link through multiple paths (`cause` and `next`), ensure you never revisit the same object. **`IdentityHashMap`** uses object identity instead of `equals` to track visited exception instances accurately.

### 5.2. Why Cap at 32 Nodes?

A malformed or unusual exception chain should not cause the logger to run endlessly. Bounding node count keeps diagnostic overhead predictable.

The number 32 is illustrative. Adjust as needed while also bounding message lengths and logged data volume.

### 5.3. This Utility Does Not Cover Every Spring Error Structure

For example, **`MailSendException`** can hold per-message exception details in its own structures. A function walking only `cause` and Jakarta `next` will **not automatically** inspect all of those entries.

Therefore, to diagnose batch send errors, also inspect accessors like **`getMessageExceptions()`** or **`getFailedMessages()`** when available.

## 6. `SendFailedException` and Differently Processed Addresses

**`jakarta.mail.SendFailedException`** is an important subtype when a send call does not complete as expected. It can provide three address groups:

- **`getInvalidAddresses()`**: addresses determined invalid per transport outcome.
- **`getValidSentAddresses()`**: valid addresses marked as sent by transport.
- **`getValidUnsentAddresses()`**: valid addresses that were not sent.

Example:

~~~java
import jakarta.mail.Address;
import jakarta.mail.SendFailedException;

public void inspectRecipients(SendFailedException failure) {
    Address[] invalid = failure.getInvalidAddresses();
    Address[] validSent = failure.getValidSentAddresses();
    Address[] validUnsent = failure.getValidUnsentAddresses();

    int invalidCount = invalid == null ? 0 : invalid.length;
    int sentCount = validSent == null ? 0 : validSent.length;
    int unsentCount = validUnsent == null ? 0 : validUnsent.length;

    log.warn(
            "SMTP recipient result: invalid={}, validSent={}, validUnsent={}",
            invalidCount,
            sentCount,
            unsentCount
    );
}
~~~

### 6.1. Do Not Reflexively Retry the Whole Batch

Suppose a message has three recipients:

~~~text
alice@example.net   -> accepted and sent
bob@example.net     -> invalid
carol@example.net   -> valid but unsent
~~~

If retrying the entire message to all three recipients:

- Alice may receive a duplicate copy.
- Bob continues to be rejected.
- Carol may need a retry, but based on specific outcomes.

Cross-check address groups against how the provider handles **partial sends**. Do not infer per-recipient truth solely from a whole-message boolean success/failure.

### 6.2. Accepted Does Not Mean Delivered

Even when transport marks an address as sent, that usually reflects only the SMTP/provider handoff step. The server can accept the message and later emit a bounce.

Use accurate status names like **`ACCEPTED_BY_RELAY`** or **`SMTP_SENT`**, never assuming the recipient opened the email.

### 6.3. A Recipient May Be Rejected by Policy

An address in the invalid group or a `550` SMTP reply does not necessarily prove the mailbox does not exist. The error may relate to sender, policy, or quota.

To decide on suppression, inspect enhanced status codes and reliable signals from the provider.

## 7. `AddressException`: Syntax Error Is Not Nonexistent Mailbox

**`jakarta.mail.internet.AddressException`** typically appears when parsing or validating address syntax. It differs from an SMTP server returning **`550 5.1.1 User unknown`** for a syntactically valid address.

Syntax check example:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public void validateAddress(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(
                "Email address must not be blank"
        );
    }

    try {
        InternetAddress address = new InternetAddress(value, true);
        address.validate();
    } catch (AddressException ex) {
        throw new IllegalArgumentException(
                "Invalid email address syntax",
                ex
        );
    }
}
~~~

Keep in mind:

- Syntax validation does not guarantee the mailbox exists.
- A domain may not accept mail or may have special policies.
- Internationalized addresses have specific `SMTPUTF8` requirements.
- Parsing a string does not verify the recipient owns the mailbox.

An `AddressException` during message preparation usually requires **fixing input data**, not retrying SMTP.

## 8. `AuthenticationFailedException` and SMTP Login Errors

**`jakarta.mail.AuthenticationFailedException`** describes authentication failure at the Jakarta Mail layer. In Spring, it may be wrapped into **`MailAuthenticationException`**.

Common causes:

- Wrong username or password.
- Revoked app password.
- SMTP AUTH disabled.
- Expired, wrong-scope, or revoked OAuth token.
- Unsupported AUTH mechanism.
- Locked account.
- Provider authentication service temporarily unavailable.

### 8.1. Do Not Blindly Retry AUTH Errors

If configuration is wrong, retrying the same credentials every few seconds usually does nothing helpful and may trigger account lockout protections.

Handling approach:

1. Identify the affected sending account.
2. Pause jobs using the misconfigured account.
3. Alert operations.
4. Fix credentials, permissions, or authentication mechanism.
5. Run a controlled test before resuming the queue.

If the provider returns a temporary AUTH error, such as `454 4.7.0`, bounded retries with backoff can be used; do not assume every `AuthenticationFailedException` is permanent.

### 8.2. Example Catching Spring Errors at the Service Boundary

~~~java
public void deliver(MimeMessage message) {
    try {
        mailSender.send(message);
    } catch (MailAuthenticationException ex) {
        log.error(
                "SMTP authentication failed for sender account {}",
                senderAccountId
        );

        throw ex;
    }
}
~~~

Never log passwords, OAuth tokens, raw AUTH payloads, or secrets. **`senderAccountId`** is a non-sensitive internal identifier in the example.

### 8.3. AUTH Errors Differ from `MAIL FROM` Errors

An account may sign in successfully yet lack permission to send using a specific envelope sender address. That error occurs at `MAIL FROM`, not AUTH.

Do not change passwords when the server is actually rejecting permission to send on behalf of a domain or `From` address.

## 9. Network and TLS Errors in the Cause Chain

Mail-sending failures can also originate from Java networking or TLS exceptions appearing beneath `MessagingException`:

| Error type | Example cause | Investigation direction |
| --- | --- | --- |
| **UnknownHostException** | SMTP host cannot be resolved | Check hostname, DNS, configuration |
| **ConnectException** | Connection refused | Check host, port, firewall, service |
| **SocketTimeoutException** | Connect/read timeout | Check network, timeouts, sending stage |
| **SocketException** | Connection reset/broken pipe | Check connection, proxy, provider |
| **SSLHandshakeException** | TLS handshake error | Check certificate, trust, protocol, SNI |
| **CertificateException** | Invalid certificate/trust | Check certificate chain and truststore |

Example error chain:

~~~text
MailSendException
    |
    v
MessagingException: Could not connect to SMTP host
    |
    v
ConnectException: Connection refused
~~~

In that case, changing the recipient solves nothing.

### 9.1. Distinguishing Configuration Errors from Transient Errors

- Wrong host or wrong port is a configuration error that needs fixing.
- Long-term firewall blocks require policy or route changes.
- A brief timeout may merit bounded retries.
- Expired certificates or missing CAs in truststore usually require config/TLS fixes.
- Do not disable certificate validation just to make emails go through.

### 9.2. Timeout Stage Determines Duplicate Risk

If timeout occurs at CONNECT, the SMTP server never had a chance to receive that session's message.

If timeout occurs after the application sent all DATA but before receiving the final response, the server **may have already accepted the message**. Retrying then risks duplicates.

A bare `SocketTimeoutException` does not always carry enough stage information. If the phase is unclear, record **`UNKNOWN_OUTCOME`** instead of assuming "not sent".

## 10. SMTP Reply Codes and Enhanced Status Codes

SMTP errors typically carry a three-digit reply code:

| Group | General meaning |
| --- | --- |
| **2xx** | Command accepted |
| **3xx** | Waiting for further information from client |
| **4xx** | Transient negative completion |
| **5xx** | Negative completion under current conditions |

Additionally, some servers supply enhanced status codes like **`5.1.1`**, **`4.7.0`**, or **`5.7.8`**.

Examples:

~~~text
550 5.1.1 User unknown
~~~

~~~text
535 5.7.8 Authentication credentials invalid
~~~

~~~text
421 4.7.0 Temporarily rate limited
~~~

These signals are far more useful than a generic Spring Mail message. However, specific codes and diagnostic text depend on the provider.

### 10.1. A Single `550` Code Is Insufficient to Conclude Invalid Recipient

For example:

~~~text
550 5.1.1 User unknown
~~~

may indicate a nonexistent mailbox.

Whereas:

~~~text
550 5.7.1 Message rejected by policy
~~~

may indicate send permissions, policy, or sender reputation.

If you see `550` and automatically add the recipient to a suppression list, you risk suppressing valid addresses.

### 10.2. `4xx` Does Not Mean Retry Immediately

A `4xx` response generally means temporary, yet still requires backoff and limits. If the provider is rate-limiting, retrying immediately makes things worse.

### 10.3. `5xx` Does Not Always Mean Fix the Recipient

`5xx` can relate to AUTH, `MAIL FROM`, `RCPT TO`, or DATA. Identify the phase and enhanced status code.

## 11. SMTP Provider Exceptions: A Specialized Diagnostic Layer

Beyond generic Jakarta Mail classes, SMTP providers often have exceptions carrying reply codes or affected addresses. For instance, some providers use names like:

- **SMTPAddressFailedException**
- **SMTPAddressSucceededException**
- **SMTPSendFailedException**

These classes may reside in implementation-dependent packages, such as Angus Mail packages or legacy JavaMail providers. **Do not assume a specific provider package is always present in every application.**

### 11.1. Why Are Provider Exceptions Useful?

When an exception provides SMTP reply codes, commands, or recipients, the application can distinguish:

~~~text
SMTP command = RCPT TO
Reply code   = 550
Enhanced     = 5.1.1
Recipient    = recipient-ref-42
~~~

from:

~~~text
SMTP command = DATA
Reply code   = 554
Enhanced     = 5.7.1
Recipient    = not necessarily one mailbox
~~~

The first case may involve a specific mailbox; the latter may be a whole-message policy rejection.

### 11.2. Do Not Classify Fragilely by Message Text

Code such as:

~~~java
if (exception.getMessage().contains("User unknown")) {
    // Treat recipient as permanently invalid
}
~~~

easily breaks when a provider changes wording, formatting, or diagnostic text. Prefer structured provider info, enhanced status codes, and stages. If only text is available, classify conservatively and mark for investigation.

### 11.3. Building a Provider-Independent Adapter

A general diagnostic model:

~~~java
public enum SmtpPhase {
    CONNECT,
    TLS,
    AUTH,
    MAIL_FROM,
    RCPT_TO,
    DATA,
    AFTER_DATA,
    UNKNOWN
}

public record SmtpFailureSignals(
        SmtpPhase phase,
        Integer replyCode,
        String enhancedStatus,
        String recipientReference,
        boolean responseMayHaveBeenLostAfterData
) {}
~~~

The infrastructure layer extracts data from provider exceptions, while the business layer uses only `SmtpFailureSignals`. When switching Jakarta Mail implementations or SMTP providers, policy logic stays decoupled from old provider packages.

## 12. `MailSendException` Can Hold Failures for Multiple Messages

Spring **`MailSendException`** can be thrown when sending one or more `MimeMessage` instances fails. It exposes additional information beyond normal causes, such as:

~~~java
ex.getMessageExceptions();
ex.getFailedMessages();
~~~

### 12.1. `getMessageExceptions()`

~~~java
catch (MailSendException ex) {
    Exception[] failures = ex.getMessageExceptions();

    for (Exception failure : failures) {
        log.warn(
                "Failed mail message exception type: {}",
                failure.getClass().getName()
        );
    }
}
~~~

Each exception can contain its own Jakarta next exception or cause. Do not read only the first error and apply that conclusion to the entire batch.

### 12.2. `getFailedMessages()`

~~~java
catch (MailSendException ex) {
    Map<Object, Exception> failures = ex.getFailedMessages();

    log.warn(
            "Failed mail messages: {}",
            failures.size()
    );
}
~~~

This mapping links failed messages to their corresponding exceptions. Exact map key types can involve `MimeMessage` or objects passed through the API. Consult your Spring version's contract when building detailed adapters.

**Do not log full keys or call `toString` on messages if doing so risks exposing email content.** Reduce keys to internal correlation IDs or appropriate counts.

### 12.3. Separating Preparation Errors from Send Errors

An error rendering a template or calling `addAttachment` does not have the same semantics as a post-DATA error. An error thrown before calling `send` generally carries no risk that the server already accepted the message on that attempt.

However, if a batch already sent several messages before an error occurred on a later message, you still need per-message tracking rather than treating the whole batch as "unsent".

## 13. Example Spring Service Separating Preparation and Send Errors

A service can separate the two stages to record causes clearly:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceDeliveryService {

    private final JavaMailSender mailSender;

    public InvoiceDeliveryService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdf
    ) {
        if (pdf == null || pdf.length == 0) {
            throw new IllegalArgumentException(
                    "Invoice PDF must not be empty"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    MimeMessageHelper.MULTIPART_MODE_MIXED,
                    "UTF-8"
            );

            helper.setFrom("billing@example.org");
            helper.setTo(recipient);
            helper.setSubject("Invoice " + invoiceNumber);
            helper.setText("Please see the attached invoice.", false);

            helper.addAttachment(
                    "invoice.pdf",
                    new ByteArrayResource(pdf),
                    "application/pdf"
            );
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot prepare invoice email",
                    ex
            );
        }

        try {
            mailSender.send(message);
        } catch (MailException ex) {
            // Forward error to the delivery/outbox layer for classification.
            throw ex;
        }
    }
}
~~~

The snippet illustrates two areas of responsibility:

- **Prepare:** construct MIME parts, headers, body, and attachments.
- **Send:** hand the message to Jakarta Mail transport via `JavaMailSender`.

In a real application, `recipient` and `invoiceNumber` must be validated/normalized per business rules. Never put untrusted user input into headers or filenames.

### 13.1. Why Not Retry Preparation Errors?

If the recipient has invalid syntax or the PDF is empty, resending immediately with the same data will keep failing. Fix the source data before creating a new send attempt.

### 13.2. Why Do Send Errors Require Deep Diagnostics?

If `send` throws `MailSendException`, the root cause could be connectivity, authentication, `RCPT TO`, DATA, or an indeterminate outcome. The exception name alone is insufficient to choose an action.

## 14. Example Using `MimeMessagePreparator`

Spring supports building messages via **`MimeMessagePreparator`**:

~~~java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(mimeMessage, true, "UTF-8");

    helper.setFrom("support@example.org");
    helper.setTo("user@example.net");
    helper.setSubject("Notification");
    helper.setText("Email content", false);
});
~~~

This wraps preparation and sending into a single API call. If message preparation fails, Spring may wrap the error into an appropriate `MailException` for preparation/parsing, depending on the error type and adapter handling.

Pros: concise and convenient when constructing a single message. Diagnostic limitation: the caller sees an outer Spring exception rather than `MessagingException` directly, so inspecting the cause remains essential.

### 14.1. Comparing the Two Styles

| Style | Advantage | Note |
| --- | --- | --- |
| Build `MimeMessage` manually then send | Clear code boundary between prepare and send | Must catch `MessagingException` during preparation |
| Use `MimeMessagePreparator` | Concise syntax focused on MIME construction | Spring may wrap preparation errors; inspect cause |

Both approaches use Jakarta Mail under Spring and both can throw errors requiring diagnostics.

## 15. Do Not Use a Single Catch-All to Retry

Pattern to avoid:

~~~java
try {
    mailSender.send(message);
} catch (Exception ex) {
    retryLater(message);
}
~~~

It conflates:

- Invalid input/headers.
- Unreadable templates.
- Permanently rejected AUTH.
- Nonexistent mailboxes.
- Temporarily overloaded SMTP.
- Timeouts after DATA that may have succeeded.

An appropriate policy considers both root cause and outcome certainty.

### 15.1. Classification Result Model

~~~java
public enum DeliveryFailureCategory {
    INVALID_INPUT,
    AUTH_CONFIGURATION,
    RECIPIENT_REJECTED,
    POLICY_REJECTED,
    TEMPORARY_SERVER_FAILURE,
    NETWORK_FAILURE,
    MESSAGE_PREPARATION,
    UNKNOWN_OUTCOME
}

public enum DeliveryAction {
    STOP_AND_FIX_DATA,
    PAUSE_SENDER_CONFIG,
    RETRY_WITH_BACKOFF,
    REVIEW_BEFORE_RETRY
}
~~~

These are application-designed business enums, not built-in Spring or Jakarta Mail enums.

### 15.2. Diagnostic Matrix

| Signal | Likely failure category | Recommended action |
| --- | --- | --- |
| `AddressException` during preparation | Input/address syntax | Fix address, do not retry as-is |
| `MailAuthenticationException` + AUTH 535 | Credentials/send permissions | Pause sender, inspect configuration |
| AUTH `454 4.7.x` | Authentication temporarily unavailable | Retry with backoff and limits |
| Reliable `RCPT TO 550 5.1.1` | Recipient does not exist | Verify/suppress per policy |
| `RCPT TO 450 4.2.x` | Recipient temporarily unavailable | Bounded retry |
| `MAIL FROM`/`DATA 550 5.7.1` | Policy or send permissions | Investigate; do not label user unknown |
| Connection refused | Host/port/firewall/provider | Check config and service health |
| `SSLHandshakeException` | TLS/certificate | Check trust/cert/protocol |
| Timeout before DATA, clear phase | Transient network error | Retry with backoff |
| Lost response after DATA | Indeterminate outcome | Reconcile, weigh duplicate risk |
| Unreadable attachment | Resource/file | Fix file or data source |

Do not treat this table as an absolute classifier. In practice, phase, enhanced status, or root causes may be missing, requiring an `UNKNOWN`/`REVIEW` state instead of forcing a definitive decision.

## 16. Recording Failure States in an Outbox

For critical emails, using an outbox decouples committing business data from SMTP. Workers send emails, diagnose errors, and update outcomes separately.

Illustrative state model:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP accepted ------> ACCEPTED_BY_RELAY
   |
   +-- 4xx temporary ------> RETRY_WAIT
   |
   +-- AUTH configuration -> PAUSED_CONFIG
   |
   +-- Invalid recipient -> INVALID_RECIPIENT
   |
   +-- Policy rejection --> NEEDS_REVIEW
   |
   +-- Unknown after DATA > UNKNOWN_OUTCOME
   |
   +-- Retry exhausted ---> FAILED
~~~

Records can store:

~~~text
eventId
attemptCount
smtpAccountReference
recipientReference
errorCategory
smtpReplyCode
enhancedStatusCode
smtpPhase
outcomeKnown
nextAttemptAt
lastAttemptAt
~~~

No need to store raw MIME bodies, attachments, or passwords to diagnose retries.

### 16.1. Account Errors and Recipient Errors Have Different Scopes

If an SMTP account has a wrong password, all jobs using that account can fail. Pause the account rather than letting individual jobs retry relentlessly.

If only one recipient has invalid syntax or does not exist, keep other jobs running normally.

### 16.2. Retries Should Not Re-Run Business Logic

If an invoice confirmation email fails to send, the worker should retry only **the send task**. Never re-run invoice generation, order creation, or payment capture just because SMTP failed.

## 17. Indeterminate Outcomes and Duplicate Risk

A critical failure window:

~~~text
1. Worker sends SMTP DATA.
2. Server receives full content.
3. Server accepts the message.
4. Connection drops before response reaches worker.
5. JavaMailSender reports error/timeout.
6. Worker does not know whether the message was accepted.
~~~

If retried, the message may be sent a second time.

### 17.1. `MailSendException` Does Not Prove Nothing Was Sent

Even when `JavaMailSender` throws `MailSendException`, the application should not automatically assume no recipients received the message. Inspect partial-send results and error timing.

### 17.2. `Message-ID` Is Not an Exactly-Once Guarantee

The `Message-ID` header aids identification and reconciliation, yet SMTP servers/clients are not required to deduplicate messages sharing the same `Message-ID`.

If the provider offers an idempotency key via a dedicated API, follow the provider's contract. Plain SMTP has no universal exactly-once email delivery mechanism.

### 17.3. Designing Retry-Safe Content

A business event should have a stable ID. Retries should not create duplicate orders, alter state, or issue new verification codes if processing the same send intent.

Example:

~~~text
Mail event:
  eventId = ORDER_CONFIRMED:1001:version-3
  recipientRef = customer-42
  template = order-confirmation-v2
~~~

This is illustrative business metadata, not a mandatory Jakarta Mail format.

## 18. Enabling Jakarta Mail Debug Under Control

When diagnosing connections, authentication, or SMTP replies in development environments, Jakarta Mail debugging can be enabled via its property.

Spring Boot YAML example:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      "[mail.debug]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

This is an example configuration; timeout values are in milliseconds and must be tuned to provider, system load, and SLAs.

### 18.1. Debug Output Can Expose Sensitive Data

Protocol logs can contain servers, senders, recipients, commands, responses, or metadata. Depending on configuration and provider, credentials and message data may also be logged.

Enable debug only in controlled environments, time-bounded, with protected log access and data redaction. Never leave verbose protocol logging enabled by default in production.

### 18.2. Timeouts Do Not Fix Root Causes

Finite timeouts prevent workers from hanging forever. However, if DNS is wrong, credentials are rejected, or certificates are invalid, merely increasing timeouts will not fix the error.

### 18.3. Distinguish the Three Timeouts

- **`connectiontimeout`:** time waiting to establish a connection.
- **`timeout`:** time waiting to read responses.
- **`writetimeout`:** time waiting to write data to the socket.

Timeouts during writing or reading after DATA can produce indeterminate outcomes. Therefore, timeout settings are part of reliability, not merely a tool to "avoid errors".

## 19. Safe Logging When Handling `MessagingException`

A useful log typically includes **task context** and **cause category**, not the entire email.

Example:

~~~text
eventId=mail-event-123
accountRef=smtp-account-01
recipientRef=customer-42
phase=RCPT_TO
smtpReply=550
enhancedStatus=5.1.1
category=RECIPIENT_REJECTED
attempt=1
decision=STOP_AND_FIX_DATA
~~~

Information to avoid logging directly:

- SMTP passwords and OAuth tokens.
- MIME bodies containing personal data.
- Attachments or PDF files.
- Raw AUTH commands.
- Full unsanitized exception messages.
- Full recipients in broadly accessible log systems when unnecessary.

### 19.1. Log the Root Cause Without Losing Context

Logging only:

~~~text
SocketTimeoutException
~~~

may be insufficient because it omits whether the timeout occurred before or after DATA and which task it belonged to.

Conversely, logging only:

~~~text
MailSendException: Mail server connection failed
~~~

is also insufficient.

A good log includes event ID, phase when known, exception class, SMTP code, policy decision, and attempt count.

### 19.2. Do Not Log the Same Error at Every Layer

If the infrastructure layer already logs an error in full and the worker logs the same stack trace again, logs duplicate heavily. Let lower layers return structured errors while the orchestration layer logs a single decision record with correlation ID.

## 20. Step-by-Step Investigation of a `MessagingException`

When a real incident occurs:

1. **Identify the operation:** did the error happen during MIME preparation or during `send`?
2. **Inspect the outermost exception:** `MailException` subtype or direct `MessagingException`?
3. **Read the cause chain:** what is the underlying exception class?
4. **Read `getNextException`:** is there a linked provider or network exception?
5. **Inspect `MailSendException` details:** which messages and recipients were affected?
6. **Pinpoint SMTP phase:** CONNECT, TLS, AUTH, `MAIL FROM`, `RCPT TO`, or DATA?
7. **Read reply and enhanced status:** are structured codes available from the provider?
8. **Determine outcome:** accepted by server, not accepted, or `UNKNOWN`?
9. **Classify error:** config, data, policy, transient, or unclear?
10. **Choose action:** fix config, fix address, bounded retry, reconcile, or halt.
11. **Record state:** update outbox/job and monitor.
12. **Verify recovery:** after fixing, test in a controlled way before resuming the queue.

### 20.1. Illustration: Wrong SMTP Password

~~~text
MailAuthenticationException
    |
    v
AuthenticationFailedException
    |
    v
SMTP AUTH rejected
~~~

Conclusion: authentication issue. Do not mark the recipient invalid. Pause the sender account and check credentials or policy.

### 20.2. Illustration: Nonexistent Mailbox

~~~text
MailSendException
    |
    v
SendFailedException
    |
    v
Provider recipient failure
    |
    v
RCPT TO -> 550 5.1.1
~~~

Conclusion: with reliable feedback, the recipient does not exist. Handle the address per policy; do not blindly retry the same data.

### 20.3. Illustration: TLS Error

~~~text
MailSendException
    |
    v
MessagingException
    |
    v
SSLHandshakeException
~~~

Conclusion: check certificates, truststore, TLS protocol, and host. Do not disable TLS validation to bypass errors.

### 20.4. Illustration: Timeout After DATA

~~~text
MailSendException
    |
    v
MessagingException
    |
    v
SocketTimeoutException
    |
    v
Phase: AFTER_DATA, result unknown
~~~

Conclusion: do not assert the email was not sent. Record `UNKNOWN_OUTCOME` and reconcile if provider signals exist; any retry must account for duplicate risk.

## 21. Testing Exception Diagnostics

Diagnostic logic can be tested independently without sending emails over the Internet.

### 21.1. Testing the `getNextException` Utility

Example:

~~~java
@Test
void inspectorSeesJakartaNestedException() {
    MessagingException outer =
            new MessagingException("Sending failed");

    outer.setNextException(
            new java.net.SocketTimeoutException("Read timed out")
    );

    List<String> types =
            MailExceptionInspector.collectExceptionTypes(outer);

    assertTrue(types.contains(
            "java.net.SocketTimeoutException"
    ));
}
~~~

This test verifies the utility detects `nextException`. It requires no real SMTP server.

### 21.2. Testing MIME Creation Errors

Cases to test:

- Malformed recipient address syntax.
- Invalid attachment parameters.
- Unreadable resources.
- Inappropriate content or headers.
- Errors thrown by the template renderer.

The goal is separating preparation failures from transport send failures.

### 21.3. Testing AUTH, `RCPT TO`, and DATA Errors

An SMTP test server or fake transport can produce deterministic replies:

| Scenario | Expected policy |
| --- | --- |
| AUTH `535 5.7.8` | Pause sender config |
| AUTH `454 4.7.0` | Retry with backoff and limits |
| `RCPT TO 550 5.1.1` | Do not retry same address |
| `RCPT TO 450 4.2.x` | Scheduled retry |
| DATA `554 5.7.x` | Investigate policy/content |
| Timeout before DATA | Conditional retry |
| Lost response after DATA | `UNKNOWN_OUTCOME` |
| Partial recipients | Do not blindly resend whole list |

Never use production accounts to intentionally submit wrong passwords repeatedly for test cases.

### 21.4. Testing Batch Failures

If `JavaMailSender` accepts multiple `MimeMessage` objects, simulate one failing message and one succeeding message to verify failed-message mapping and per-message retry handling.

Crucially, never mark an entire batch as sent or unsent just because the API threw a single general exception.

## 22. Common Mistakes

| Mistake | Why it is dangerous | How to handle |
| --- | --- | --- |
| Logging only `MessagingException.getMessage()` | Misses nested causes/provider errors | Traverse `cause` and `getNextException` |
| Walking only Java `getCause()` | Can miss Jakarta Mail linked exceptions | Check `getNextException` |
| Treating every `MessagingException` as an SMTP error | Exception may occur while building MIME | Separate prepare and send |
| Retrying every `MailException` | Input/AUTH/policy errors usually need fixes | Use classifier and durable states |
| Equating `550` with user unknown | `550` can also be policy | Inspect enhanced code and phase |
| Equating SMTP accept with delivered | Can bounce after server acceptance | Record accurate statuses |
| Retrying whole batch on partial send | May duplicate to already-accepted recipients | Track per-message/per-recipient |
| Assuming timeouts mean definitely unsent | May occur after DATA | Record `UNKNOWN_OUTCOME` |
| Logging raw MIME and AUTH payloads | Leaks personal data/secrets | Redaction and structured logging |
| Disabling TLS certificate validation to avoid errors | Loses connection protection | Fix trust/certificate/config |
| Using regex on message text as sole classifier | Diagnostics vary by provider | Prefer structured codes/phases/types |
| Mixing `javax.mail` with `jakarta.mail` | Incompatible namespaces/dependencies | Align API with active Spring version |

## 23. Frequently Asked Questions

**1. Is `MessagingException` an SMTP sending error?**

Not necessarily. It is Jakarta Mail's general checked exception and can arise during MIME preparation or transport.

**2. Why does `JavaMailSender.send()` throw `MailSendException` instead of `MessagingException`?**

Spring uses a runtime `MailException` abstraction. Underlying Jakarta Mail errors may be preserved in `cause` or message-failure structures for diagnostics.

**3. How does `getNextException()` differ from `getCause()`?**

`getNextException()` is Jakarta `MessagingException`'s linked-exception API. `getCause()` is standard Java `Throwable` chaining. For thorough diagnostics, inspect both with cycle protection.

**4. Should I call `setNextException()` myself?**

Normally no. It is a Jakarta Mail API for chaining exceptions. Application code should primarily read the cause chain provided by the library.

**5. Does `AuthenticationFailedException` always mean the password is wrong?**

No. It could be tokens, AUTH mechanisms, account policies, or transient errors. Inspect server replies and provider configuration.

**6. Does `AddressException` prove the mailbox does not exist?**

No. It usually relates to address parsing/syntax. Whether a mailbox exists is separate information typically provided by the receiving system or bounce processing.

**7. Can `SendFailedException` contain multiple recipient groups?**

Yes. The API exposes `invalid`, `validSent`, and `validUnsent` addresses. Handle according to actual outcomes rather than retrying everything.

**8. Why do TLS errors appear inside `MessagingException`?**

Jakarta Mail transport may wrap network/TLS exceptions raised during connection or sending, so inspect nested exceptions.

**9. Can SMTP reply codes be retrieved directly from `MessagingException`?**

Generic `MessagingException` does not expose a universal SMTP reply code property across all cases. Some specialized provider exceptions carry it; adapters must read per implementation or provider-published data.

**10. Should `4xx` errors always be retried?**

No. Use backoff, attempt limits, and context. A prolonged `4xx` error may require alerting or investigation.

**11. Do `5xx` errors always mean a bad address?**

No. They can relate to AUTH, sender/policy, or message content. Inspect SMTP phase and enhanced status.

**12. If `getNextException()` returns `null`, is the final cause known?**

Not necessarily. Check `cause`, `MailSendException` message failures, permitted logs, and provider outcomes.

**13. Should full stack traces be logged in production?**

Only when aligned with security policies and log budgets. Never log credentials, raw MIME, or sensitive data; prefer structured events and correlation IDs.

**14. Why does `JavaMailSender` return cleanly yet bounces still happen?**

The SMTP relay can accept a message and fail at a later delivery hop. SMTP acceptance and delivery are distinct milestones.

**15. How do we avoid duplicates on timeout?**

There is no universal exactly-once guarantee with SMTP. Use stable event IDs, an outbox, `UNKNOWN_OUTCOME` state, reconciliation when available, and retry-safe content design.

## 24. Key Takeaways on `MessagingException` and Jakarta Mail Root Causes

**`MessagingException` is the starting point for diagnostics, not the root-cause conclusion.** In a Spring Mail application, distinguish exceptions raised while building `MimeMessage` from `MailException` thrown by `JavaMailSender` during sending. Inspect subtypes, Java `cause`, and **`MessagingException.getNextException()`**; if it is **`MailSendException`**, check per-message exceptions and recipient outcomes when present.

**`AuthenticationFailedException`**, **`SendFailedException`**, and **`AddressException`** carry distinct meanings. An authentication error is not an address error; an address syntax error does not prove a nonexistent mailbox; a general send error does not prove the server never accepted the email. SMTP reply codes, enhanced status codes, and phases help classify root causes, though they may be missing or differ across providers.

Translate underlying errors into structured diagnostic results so the orchestration layer can decide whether to fix data, pause a sending account, retry with backoff, or reconcile. Do not blindly retry, do not over-infer beyond actual error evidence, do not log secrets, and do not equate **SMTP accepted**, **delivered**, and **read**. This is the foundation for running Spring Framework Mail reliably with verifiable incident handling.
