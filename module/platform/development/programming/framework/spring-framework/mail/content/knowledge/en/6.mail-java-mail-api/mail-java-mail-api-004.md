# MimeMessagePreparator for Preparing Messages

## 1. What Is MimeMessagePreparator?

In **Spring Framework Mail**, **MimeMessagePreparator** is a **functional interface** in the **org.springframework.mail.javamail** package. It describes the work of **preparing the contents of a MimeMessage** supplied by the mail-sending layer. The application implements this interface to populate the sender, recipients, subject, plain-text body, HTML, attachments, or other MIME components, and then passes the callback to **JavaMailSender.send(...)**.

Core concept:

> **MimeMessagePreparator decides how to build the message; JavaMailSender decides when to create the message and executes the send operation.**

Instead of writing the entire **createMimeMessage() → edit MimeMessage → send(mimeMessage)** sequence directly, the application can supply a **prepare(MimeMessage)** callback to JavaMailSender:

~~~java
MimeMessagePreparator preparator = mimeMessage -> {
    // Prepare fields and MIME structure here.
};

mailSender.send(preparator);
~~~

This is one of the helpful APIs when email content is complex, message-building logic can be reused, or you want to separate **the preparation step** from **the sending step** in your application design.

### Interface Signature

In meaning, the interface contract corresponds to:

~~~java
package org.springframework.mail.javamail;

@FunctionalInterface
public interface MimeMessagePreparator {
    void prepare(jakarta.mail.internet.MimeMessage mimeMessage) throws Exception;
}
~~~

The snippet above presents **the signature for learning**, not code to declare again in your application. In Spring Framework 6 and Spring Boot 3+ applications, the MIME message type belongs to **jakarta.mail.internet**. When using Spring Framework 5 or Spring Boot 2, the underlying mail APIs typically use the **javax.mail** namespace; align dependencies and imports with the framework version in your project.

Because the interface has only a single abstract method, it can be implemented with a **lambda**, an **anonymous class**, or a dedicated class.

## 2. Where Does MimeMessagePreparator Fit in Spring Mail?

Related components to distinguish:

| Component | Responsibility | Does it send email itself? |
|---|---|---|
| **MimeMessagePreparator** | Callback that customizes the provided **MimeMessage** object | **No** |
| **MimeMessage** | Actual Jakarta Mail MIME message containing headers and body | **No** |
| **MimeMessageHelper** | Utility for building headers, HTML/plain-text bodies, attachments, and inline resources | **No** |
| **JavaMailSender** | Spring contract for creating and sending MIME messages | **Yes**, via **send(...)** overloads |
| **JavaMailSenderImpl** | Common implementation using Jakarta Mail and SMTP | **Yes**, when appropriately configured |
| **SimpleMailMessage** | Data object for plain-text emails | **No** |

Do not confuse **MimeMessagePreparator** with **MimeMessageHelper**. Preparator is **the callback contract**, whereas Helper is **the tool for manipulating the message** inside the callback.

Typical call flow diagram:

~~~text
          Application / NotificationService
                        |
                        | Create MimeMessagePreparator
                        v
               JavaMailSender.send(...)
                        |
                        | Create MimeMessage
                        v
           MimeMessagePreparator.prepare(...)
                        |
                        | Use MimeMessageHelper to configure content
                        v
                  Prepared MimeMessage
                        |
                        | JavaMailSenderImpl + Jakarta Mail
                        v
                     SMTP server
                        |
                        v
              Email delivery infrastructure
~~~

A call to **prepare(...)** does not confirm the message was sent. Even when **send(...)** completes successfully, that does not guarantee the message landed in the recipient's Inbox; SMTP hops and the destination mail system continue processing afterward.

## 3. Why Use a Callback Instead of Creating MimeMessage Directly?

To see the benefit, compare two ways of organizing the same operation.

**Approach A — create directly and send:**

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setTo("user@example.net");
helper.setFrom("no-reply@example.com");
helper.setSubject("Notification");
helper.setText("Message content");
mailSender.send(message);
~~~

**Approach B — hand a callback to JavaMailSender:**

~~~java
MimeMessagePreparator preparator = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setTo("user@example.net");
    helper.setFrom("no-reply@example.com");
    helper.setSubject("Notification");
    helper.setText("Message content");
};

mailSender.send(preparator);
~~~

Both approaches are valid, depending on requirements. **Approach A** is easy to follow when the application needs to hold onto a MimeMessage object for manual configuration. **Approach B** centralizes message-building logic into one callback and lets JavaMailSender orchestrate the message lifecycle. For use cases with HTML templates, attachments, or multiple notification types, the callback can become an independent unit of logic easy to pass to the sending layer.

Notable benefits:

- **Centralized preparation**: recipient info, headers, and body are described in one place.
- **Separation of concerns**: the content-building class does not need to manage SMTP connections.
- **Clean fit with Spring DI**: services depend on the JavaMailSender interface and template-rendering services.
- **Reusability**: a function or class can build a preparator from business data and return the callback to the sending layer.
- **Each send gets a MIME object supplied by the sender**: avoids accidentally reusing an old MimeMessage mutated in a previous send.

Preparator does **not** automatically add queuing, retries, transactions, or asynchronous sending. It is strictly a content-preparation API during the email-sending process.

## 4. Basic Example: Sending a Plain-Text Email with MimeMessagePreparator

For very simple emails, **SimpleMailMessage** is a lighter choice. Still, the following example shows how the callback works before moving on to HTML or attachments.

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class WelcomeEmailService {

    private final JavaMailSender mailSender;

    public WelcomeEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("no-reply@example.com");
            helper.setTo(recipient);
            helper.setSubject("Welcome");
            helper.setText("Your account has been created successfully.");
        };

        mailSender.send(preparator);
    }
}
~~~

Here:

1. **WelcomeEmailService** receives **JavaMailSender** via constructor injection.
2. The lambda receives the **MimeMessage** provided by JavaMailSender and uses **MimeMessageHelper** to set fields.
3. **helper.setText(String)** creates the plain-text body.
4. **mailSender.send(preparator)** triggers the preparation and sending workflow.

Addresses and content in the example are for illustration; the application needs an SMTP server, sending permissions, and an appropriately configured sender address.

### Why Doesn't the Lambda Declare throws MessagingException?

The **prepare(...)** method of MimeMessagePreparator is declared with **throws Exception**. Therefore, the callback can invoke Jakarta Mail or MimeMessageHelper APIs that throw checked exceptions without wrapping every single call in a RuntimeException. When JavaMailSender executes the callback, errors from preparation or sending are surfaced to the application through Spring Mail's exception mechanism.

However, **message structure errors** still differ from **SMTP transport errors**. Always inspect the exception type and underlying cause before deciding whether to fix data or retry sending.

## 5. Key Example: Building HTML and Plain-Text Alternative Emails

A business notification often aims to give recipients both an HTML email and an equivalent plain-text version. **MimeMessagePreparator** pairs cleanly with **MimeMessageHelper** to create these MIME parts.

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class AccountEmailService {

    private final JavaMailSender mailSender;

    public AccountEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAccountReady(String recipient, String displayName) {
        String safeName = escapeHtml(displayName);

        String plainText = """
                Hello %s,

                Your account is ready.
                Visit https://example.com/account to view your details.
                """.formatted(displayName);

        String htmlText = """
                <html lang="en">
                  <body>
                    <h2>Hello %s!</h2>
                    <p>Your account is ready.</p>
                    <p><a href="https://example.com/account">
                      Go to account page
                    </a></p>
                  </body>
                </html>
                """.formatted(safeName);

        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage,
                    true,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("no-reply@example.com");
            helper.setTo(recipient);
            helper.setSubject("Your account is ready");
            helper.setText(plainText, htmlText);
        };

        mailSender.send(preparator);
    }

    private static String escapeHtml(String value) {
        return value
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
~~~

The example uses **Java text blocks** and **String.formatted(...)**, compatible with Java 21. The `escapeHtml` helper here only illustrates escaping a plain string when inserting into an HTML *text node*; in real applications, use a template engine with context-aware escaping. Do not rely on this simple escaper to sanitize arbitrary values embedded into URLs, JavaScript, or CSS.

Key points:

- **MimeMessageHelper(mimeMessage, true, "UTF-8")** enables multipart mode and configures encoding.
- **setText(plainText, htmlText)** creates two alternative representations of the same content, typically inside **multipart/alternative**.
- Both versions should remain consistent in content and required actions; the text version should include a readable URL if the HTML uses a button.
- **MimeMessagePreparator** only configures content, while **JavaMailSender** manages the send call.

If you only pass **setText(htmlText, true)**, the helper marks a single content part as HTML; that method does not automatically generate an equivalent plain-text part.

## 6. Preparing Emails with Attachments

MIME allows an email to contain one or more attached files. The helper supports methods such as **addAttachment(...)** inside the callback, provided multipart mode is enabled.

~~~java
import java.io.File;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, File invoicePdf) {
        MimeMessagePreparator preparator = mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("billing@example.com");
            helper.setTo(recipient);
            helper.setSubject("Your invoice");
            helper.setText(
                    "Your PDF invoice is attached.",
                    "<p>Your PDF invoice is attached.</p>"
            );
            helper.addAttachment("invoice.pdf", invoicePdf);
        };

        mailSender.send(preparator);
    }
}
~~~

The meaning of **MULTIPART_MODE_MIXED_RELATED** is that Spring constructs a multipart tree suited for combining content parts with attachments and inline resources. The actual MIME structure may contain nested **multipart/mixed**, **multipart/related**, and **multipart/alternative** layers, as these types express distinct relationships:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   └── multipart/alternative
    │       ├── text/plain
    │       └── text/html
    └── application/pdf (attachment)
~~~

The diagram is an example of **logical relationships** between parts, not a guarantee that every mail client or Jakarta Mail version produces the exact same node hierarchy.

Several rules when adding attachments:

1. Allow only files within business scope with verified access permissions.
2. Enforce size limits; many SMTP providers impose message size caps.
3. Never use a user-supplied filename directly as an arbitrary file path.
4. Ensure attachment data remains readable **when the callback executes and the message is sent**.
5. Avoid logging confidential files or sensitive data when catching errors.

If attached content is generated temporarily and closed/deleted too early, MIME construction or sending can fail even though the application constructed the preparator.

## 7. Inline Images and HTML Content

Unlike downloadable attachments, inline images are typically referenced by HTML via **Content-ID** using the **cid:** syntax.

Conceptual example:

~~~java
MimeMessagePreparator preparator = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
    );

    helper.setFrom("brand@example.com");
    helper.setTo("recipient@example.net");
    helper.setSubject("Notification");
    helper.setText(
            "New notification from the brand.",
            "<p>New notification</p><img src=\"cid:brandLogo\" alt=\"Logo\">"
    );

    helper.addInline("brandLogo", logoResource);
};

mailSender.send(preparator);
~~~

The snippet assumes **logoResource** is a prepared **org.springframework.core.io.Resource**. When using **MimeMessageHelper**, **set the body with setText(...) first before calling addInline(...)** to improve compatibility across email clients.

An inline image is a **related component of the HTML** (a *related* relationship), not a third alternative version of the body. Even with images, the email should still convey key information if the client blocks image rendering.

## 8. Preparing Messages via Lambda, Anonymous Class, or Dedicated Class

Because MimeMessagePreparator has only one abstract method, lambda syntax is usually the most concise:

~~~java
MimeMessagePreparator preparator = mimeMessage -> {
    MimeMessageHelper helper = new MimeMessageHelper(mimeMessage, "UTF-8");
    helper.setTo("user@example.net");
    helper.setFrom("sender@example.com");
    helper.setSubject("Schedule reminder");
    helper.setText("Your appointment starts tomorrow.");
};
~~~

If you need a configurable component or many complex steps, you can define a dedicated class:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public final class ReminderPreparator implements MimeMessagePreparator {

    private final String recipient;
    private final String content;

    public ReminderPreparator(String recipient, String content) {
        this.recipient = recipient;
        this.content = content;
    }

    @Override
    public void prepare(MimeMessage mimeMessage) throws Exception {
        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage, "UTF-8"
        );
        helper.setFrom("reminders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Schedule reminder");
        helper.setText(content);
    }
}
~~~

When sending:

~~~java
mailSender.send(
        new ReminderPreparator(
                "recipient@example.net",
                "Your appointment will begin tomorrow."
        )
);
~~~

This is useful when the application has many notification types and wants to keep message construction in specialized classes. However, for a few-line callback, introducing an extra class can make control flow harder to read; choose the style that matches the complexity.

## 9. Separating Preparator Creation from Calling send()

A common organization separates **notification data**, **a preparator-building factory/builder**, and **the mail-sending adapter**:

~~~text
Controller / Domain Service
        |
        v
Notification command (recipient, template data)
        |
        v
EmailPreparatorFactory
        |   Build callback from input data
        v
MimeMessagePreparator
        |
        v
JavaMailSender.send(preparator)
        |
        v
SMTP / Email provider
~~~

Example of a factory returning a callback:

~~~java
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public final class AlertMailFactory {

    private AlertMailFactory() {
    }

    public static MimeMessagePreparator create(
            String recipient,
            String subject,
            String body
    ) {
        return mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage, "UTF-8"
            );
            helper.setFrom("alerts@example.com");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(body);
        };
    }
}
~~~

In the service:

~~~java
MimeMessagePreparator preparator = AlertMailFactory.create(
        "operator@example.net",
        "System alert",
        "A task requires inspection."
);

mailSender.send(preparator);
~~~

Note that the callback may **be created before execution time**. Therefore, pass immutable data or a snapshot of the data to be sent; avoid referencing mutable variables/objects that another thread might alter between callback creation and when the sender invokes **prepare()**. The callback should also avoid side effects like mutating order state or writing business data, since its primary responsibility is email preparation.

## 10. Combining with a Template Engine to Compose Content

Real-world email content is rarely a static HTML string. Applications can use **Thymeleaf**, **FreeMarker**, or another template engine to render HTML and plain text before submitting the message.

Example processing flow:

~~~text
Transaction details
      |
      v
Service loads authorized data
      |
      +--> Plain text template --> plainText
      |
      +--> HTML template --------> htmlText
      |
      v
MimeMessagePreparator
      | helper.setText(plainText, htmlText)
      v
JavaMailSender.send(...)
~~~

Build both versions from **a single consistent business data source** so HTML and plain text never show conflicting amounts, order IDs, or expiration dates. If the message has a confirmation link, the text version should include a copyable URL; HTML can use a button or labeled link.

When inserting user data into HTML, rely on the template engine's **context-aware escaping**. Avoid concatenating untrusted display names, notes, or URLs directly into HTML; email clients interpret HTML differently and may process unwanted tags.

You do not have to render HTML **inside the callback**. You can render beforehand and have the callback merely attach the resulting strings to the MimeMessage. That keeps the callback simple and separates template rendering errors from send errors. Conversely, if you render inside the callback, template exceptions surface as message preparation errors; identify and handle them accordingly.

## 11. Sending Multiple Preparators at Once

**JavaMailSender** supports **send(...)** methods accepting a single preparator or an array of preparators.

Example:

~~~java
MimeMessagePreparator first = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setFrom("alerts@example.com");
    helper.setTo("first@example.net");
    helper.setSubject("Personal notice");
    helper.setText("Content for the first recipient.");
};

MimeMessagePreparator second = message -> {
    MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
    helper.setFrom("alerts@example.com");
    helper.setTo("second@example.net");
    helper.setSubject("Personal notice");
    helper.setText("Content for the second recipient.");
};

mailSender.send(first, second);
~~~

Each preparator represents **a separate email message to be prepared**. Do not confuse sending multiple preparators with one email containing multiple To/Cc/Bcc addresses: those are two different models.

Important: **send(first, second)** is not an atomic transaction across messages. One message may be accepted by the mail system while another fails. When per-recipient status reporting or retry handling is needed, track each message individually and reconcile with feedback from the sending infrastructure.

## 12. Exception Handling: Preparation Errors vs. Transport Errors

When using callbacks, errors can arise in two places:

**Group 1 — Preparation errors**

- Invalid email addresses or input data.
- Errors loading templates or data.
- Unable to read attachment files when building content.
- Invalid MIME structure, encoding, or operations on MimeMessage.
- Callback throws an exception during execution.

**Group 2 — Send/transport errors**

- Incorrect SMTP host, port, or DNS.
- Connection timeout, TLS handshake failure.
- SMTP AUTH failure.
- SMTP relay rejects sender, recipient, or data.
- Server overload, rate limiting, or network issues after submission.

In Spring Mail, errors may surface as exceptions in the **MailException** family, such as:

| Exception | Common meaning |
|---|---|
| **MailPreparationException** | Exception while executing the message preparation callback. |
| **MailParseException** | Unable to parse or construct a valid message. |
| **MailAuthenticationException** | Failed to authenticate with the mail server. |
| **MailSendException** | Failure while sending the message, possibly containing per-message details. |

Do not assume every **MessagingException** is wrapped by Spring in the same exception type in every scenario. Inspect the **cause** and actual error message to tell whether the exception came from message preparation or SMTP communication.

Example service recording errors at the orchestration layer:

~~~java
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

public class MailDispatchService {

    private final JavaMailSender sender;

    public MailDispatchService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void dispatch(MimeMessagePreparator preparator) {
        try {
            sender.send(preparator);
        } catch (MailPreparationException ex) {
            // Check data and content construction logic.
            throw ex;
        } catch (MailAuthenticationException ex) {
            // Check credentials and SMTP usage permissions.
            throw ex;
        } catch (MailException ex) {
            // Record safe diagnostic information and classify further.
            throw ex;
        }
    }
}
~~~

The snippet distinguishes error types and does not yet implement a retry policy. Avoid writing SMTP passwords, tokens, email bodies, or secret paths to logs.

### Case Where It Is Uncertain Whether Sending Succeeded

If the connection drops right after the client finishes sending data without receiving confirmation from the SMTP server, it is possible **the server accepted the message while the client still observes a timeout**. Automatic retries without message tracking risk producing duplicate emails.

When email is critical, track **notification ID**, **attempt ID**, transient/permanent states, and **UNKNOWN** outcomes; and reconcile against provider logs where available. **MimeMessagePreparator does not provide exactly-once delivery by itself.**

## 13. Synchronous, Asynchronous, and Transactions

Calling **mailSender.send(preparator)** in the standard way is a **synchronous** operation: the caller waits until preparation and email submission finish or throw an exception. Using a callback does not make this operation asynchronous.

If the user interface needs fast responses or you need retries independent of HTTP requests, the application can persist a send request and let a background worker execute it:

~~~text
HTTP request
     |
     v
Save business data + send request in outbox
     |
   COMMIT
     |
     v
Background worker
     |
     +--> Build MimeMessagePreparator from stored data
     |
     +--> JavaMailSender.send(preparator)
     |
     +--> Record accepted / failed / unknown
~~~

If business data and email-sending intent must commit consistently, the **transactional outbox** pattern helps: store the business record and outbox entry in the same database transaction, then let a worker read the outbox and send. However, SMTP does not participate in the database transaction: if the worker sends successfully and crashes before updating outbox status, rerunning may send duplicates. Design retries and deduplication to match system requirements.

Do not place MimeMessage objects, MimeMessageHelper instances, or lambdas capturing live resources (connections, temporary streams) directly into a long-lived queue. Instead, **persist serializable business data** and construct the callback when the worker processes it.

## 14. Testing Components That Use MimeMessagePreparator

Because the callback is a pure message-preparation component, you can test MIME construction logic without sending real emails. For instance, use a fake or mock JavaMailSender to capture the preparator and call **prepare(...)** on a test MimeMessage created by Jakarta Mail.

Illustrative idea with Mockito:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

import java.util.Properties;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class WelcomeEmailServiceTest {

    @Test
    void preparesAddressAndSubject() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        WelcomeEmailService service = new WelcomeEmailService(sender);

        service.sendWelcome("recipient@example.net");

        org.mockito.ArgumentCaptor<MimeMessagePreparator> captured =
                org.mockito.ArgumentCaptor.forClass(
                        MimeMessagePreparator.class
                );
        verify(sender).send(captured.capture());

        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties())
        );
        captured.getValue().prepare(message);

        org.junit.jupiter.api.Assertions.assertEquals(
                "Welcome", message.getSubject()
        );
        org.junit.jupiter.api.Assertions.assertEquals(
                "recipient@example.net",
                message.getRecipients(jakarta.mail.Message.RecipientType.TO)[0].toString()
        );
    }
}
~~~

The example assumes a test environment with JUnit 5, Mockito, and Jakarta Mail available. It illustrates how to **inspect the callback and the resulting MIME object after prepare**, without calling SMTP. For HTML, attachments, or complex headers, you can inspect the **BodyPart** contents and corresponding MIME types. Testing SMTP connectivity remains a separate scope, typically requiring a mock mail server or test infrastructure.

The goal is to verify **message structure and data**, not to equate valid MIME with a guarantee that the email will be delivered successfully across the Internet.

## 15. Common Design Pitfalls

| Practice | Why it causes issues | How to handle |
|---|---|---|
| Calling **prepare(...)** without calling **send(...)** | The callback only builds the message, it does not send it | Pass the preparator to JavaMailSender.send(...). |
| Creating a lambda that depends on an external mutable object | Data may change before the callback runs | Capture immutable data or a validated snapshot. |
| Creating a MimeMessage once and reusing it across sends | Risk of carrying over old headers/body and unintended mutations | Use a fresh object per message or let the sender create one via preparator. |
| Creating only HTML without plain text | Recipients using text mode may struggle to read or miss info | Use setText(plainText, htmlText) when an alternative is needed. |
| Adding attachments when the helper is not in multipart mode | No appropriate multipart tree exists | Initialize MimeMessageHelper with multipart=true or an appropriate mode. |
| Calling addInline before setText | May affect rendering in some email clients | Set the body first, then add inline resources. |
| Rendering content from unescaped data | Can break HTML and introduce content injection risks | Use a template engine with context-aware escaping. |
| Treating MailPreparationException like a network error | Repeatedly retries an invalid message | Fix the data source or structure before resending. |
| Treating send() success as delivered to Inbox | SMTP only confirms one hop of delivery | Track events, bounces, and status from the ESP if needed. |
| Pushing a lambda capturing a temporary file into a queue for much later execution | File may already be deleted or stream closed | Persist durable data and build the preparator when the worker sends. |
| Sending email directly inside a critical business transaction | Database may roll back after the email is already sent | Consider an outbox and worker for high-reliability requirements. |

## 16. When Should You Choose MimeMessagePreparator?

**Choose MimeMessagePreparator when:**

- You want to build MIME via a clear callback, keeping the mail-sending service focused on accepting preparation requests.
- Emails have HTML, attachments, inline images, custom headers, or customized MIME configurations.
- You want to reuse email-construction logic across multiple send calls.
- You want to separate message construction from SMTP configuration and the send invocation mechanism.
- You want to test MimeMessage content independently by running the callback on a test message.

**Cases where simpler options exist:**

- Emails with only subject and plain text: **SimpleMailMessage** + **MailSender** is sufficient.
- The application needs to manipulate an existing MimeMessage directly: use **JavaMailSender.createMimeMessage()**, **MimeMessageHelper**, and then **send(message)**.
- The project already has a dedicated notification gateway: the gateway can create/accept preparators inside the adapter, while business logic only requests sending a notification.

Choosing a callback does not change the core sending capabilities of Spring Mail; the difference lies mainly in **how the message-preparation step is structured**.

## 17. Summary

**MimeMessagePreparator** is a functional interface in **Spring Framework Mail** with the method **prepare(MimeMessage)**. It allows the application to describe how to build an email, commonly using **MimeMessageHelper** to set From, To, Cc, Bcc, Subject, plain text, HTML, attachments, or inline resources. When passing a preparator to **JavaMailSender.send(...)**, the sender creates a message, executes the preparation callback, and hands the message off to the mail-sending system.

Remember three boundaries: **the preparator only prepares content**; **the sender executes the send call**; and **SMTP and receiving systems are responsible for delivery across downstream hops**. Keeping these three roles distinct makes application code easier to read, organize, control for errors, and adapt to complex email workflows.
