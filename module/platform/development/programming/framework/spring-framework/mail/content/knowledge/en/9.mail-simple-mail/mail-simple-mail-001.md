# When SimpleMailMessage Is the Right Fit in Spring Framework Mail

In Spring Framework Mail, not every email needs HTML, images, attachments, or a multipart MIME structure. A short notification email that has only a subject, a sender, a recipient, and a few lines of text can be built with the `SimpleMailMessage` class. This class is the right choice when the content is truly simple, while the SMTP connection and the actual sending of the email are delegated to `MailSender` or `JavaMailSender`.

For example, an application may need to send:

- An account verification code together with brief instructions.
- A notification that a support request has been received.
- An alert to the operations team that a background task has failed.
- A reminder or an order status notification with a few lines of text.
- A confirmation link with a clear explanation in plain text.

However, if the email needs HTML formatting, a logo embedded in the body, an attached PDF file, or both a plain text and an HTML version, use `MimeMessage` with `MimeMessageHelper`. Understanding this boundary correctly helps you pick an API with just the right level of complexity and avoid mistakes such as sending raw HTML tags to the reader.

## 1. What does SimpleMailMessage represent?

`SimpleMailMessage` is a class in the `org.springframework.mail` package. It describes the basic properties of a **plain text** email:

| Component | Typical API | Meaning |
| --- | --- | --- |
| Sender | `setFrom(String)` | Address in the `From` field of the message |
| Primary recipients | `setTo(String...)` | List of `To` recipients |
| Carbon copy recipients | `setCc(String...)` | List of `Cc` recipients |
| Blind carbon copy recipients | `setBcc(String...)` | List of `Bcc` recipients |
| Reply address | `setReplyTo(String)` | The `Reply-To` field |
| Subject | `setSubject(String)` | Subject of the message |
| Content | `setText(String)` | Plain text body |
| Sent date | `setSentDate(Date)` | The time declared on the message when needed |

This is a mutable data object. It **does not connect itself** to the SMTP server, does not send by itself, and does not open the recipient's mailbox. To send, the application passes the object to a sender component.

```text
Business service
       |
       | create a new SimpleMailMessage
       | setFrom, setTo, setSubject, setText
       v
SimpleMailMessage
       |
       | JavaMailSender.send(message)
       v
JavaMailSender / JavaMailSenderImpl
       |
       | Convert the message into a form that can be transmitted over SMTP
       | Use Jakarta Mail to work with the SMTP transport
       v
SMTP relay / Email Service Provider
       |
       v
Receiving mail system
```

`SimpleMailMessage` is not a "lightweight HTML email" class. It is designed for the case where the content is only text. The fact that an implementation at a lower layer may create a `MimeMessage` to pass through Jakarta Mail **does not make `SimpleMailMessage` a full MIME message composition API**.

### Relationship with MailSender and JavaMailSender

- `MailSender` is the Spring interface that supports sending a `SimpleMailMessage`.
- `JavaMailSender` is the interface that extends the ability to send MIME emails, while still supporting sending a `SimpleMailMessage`.
- `JavaMailSenderImpl` is a common SMTP implementation of `JavaMailSender`.
- `MimeMessageHelper` helps build a `MimeMessage` with HTML, multipart, attachments, and more headers/content types.

In a Spring Boot application, you usually only need to inject `JavaMailSender` into a service to have both the simple option and the MIME option. A project that uses only plain text can, in terms of API, depend on `MailSender` if it does not need the extended capabilities of `JavaMailSender`.

## 2. When to choose SimpleMailMessage

An easy-to-apply criterion is: **the recipient can understand and take every necessary action from just a few paragraphs of text, without needing a rich layout or accompanying files**.

| Situation | Is SimpleMailMessage suitable? | Reason |
| --- | --- | --- |
| OTP or short verification code | Yes | The content is a few lines with little presentation required |
| Order received confirmation | Yes, if it contains only brief information | Order ID, status, and a link to view details are sufficient as text |
| Job failure alert to the engineering team | Yes | Summary log, error code, and dashboard link are clear |
| Simple reminder | Yes | Time, location, and instructions can be read as text |
| Marketing email with multiple columns and banner | Not suitable | Needs HTML/CSS and may include inline images |
| Invoice as a PDF | Not suitable | Needs an attachment via MIME |
| Email with an HTML version and a plain text fallback | Not suitable for SimpleMailMessage alone | Needs `multipart/alternative` |
| Message with a logo displayed in the body | Not suitable | Needs an inline resource with a Content-ID |
| Calendar invite as an `.ics` file | Not suitable if sent as an attachment/calendar MIME | Needs appropriate MIME content |
| Email with custom MIME headers, priority, or specialized DSN | Usually not suitable | Needs control over `MimeMessage` or a provider mechanism |
| Email that requires open/click tracking via an ESP | Can be used if only a text body is needed; tracking depends on the ESP | SimpleMailMessage itself does not track those events |

**Length is not the only criterion.** A very short email that must include an image or a file still needs MIME. Conversely, a relatively long text email that consists only of paragraphs and links can still use `SimpleMailMessage` if the reading experience is appropriate.

### Example 1: Background task notification

```text
Subject: [Scheduler] Backup completed

Task: backup-daily
Environment: production
Result: success
Time: 2026-11-12 02:00 UTC

Details: https://ops.example.com/jobs/backup-daily
```

This message does not need HTML. The important information is presented as easy-to-read lines with a complete link.

### Example 2: Support request confirmation

```text
Subject: Request #SUP-1042 received

Hello,

We have received your support request.

Request ID: SUP-1042
Track it at: https://example.com/support/requests

Best regards,
Support Team
```

This content can be read in many email clients and accessibility tools without any CSS or images.

## 3. Spring Boot configuration before sending

In a Spring Boot application that uses Maven and Boot's dependency management, add the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

If you use Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Declare the SMTP settings in `src/main/resources/application.properties`:

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

The host and port values are illustrative only; they must be replaced with the SMTP endpoint provided by your organization or provider. Port 587 usually uses STARTTLS, but some systems use port 465 with implicit TLS, or internal relays with different policies.

In the example:

- `spring.mail.username` and `spring.mail.password` are taken from the environment; do not write real passwords into the repository.
- `spring.mail.default-encoding=UTF-8` helps represent content with Vietnamese diacritics correctly.
- `auth` and `starttls.*` must be compatible with the authentication/encryption policy of the SMTP server.
- The three timeouts are in milliseconds and set separate limits for connect/read/write to reduce the risk of a task hanging for a long time.
- `JavaMailSenderImpl` will be auto-configured by Spring Boot when the dependency and the configuration conditions are met; normally there is no need to create a new sender in each service.

Setting timeouts helps deal with slow networks, but the total duration of `send()` can still be longer than each individual timeout value because SMTP consists of many sequential operations. Sending mail also depends on the network path, DNS, TLS, authentication, the provider's quota, and the server state.

### Configuration to avoid sending a test message at application startup

With Spring Boot, `spring.mail.test-connection` is an independent property:

```properties
spring.mail.test-connection=false
```

The value `false` means that testing the SMTP connection during startup is not required by this feature. If set to `true`, when the auto-configuration applies, Boot may check the transport at startup and fail if the SMTP server cannot be reached. **It does not send a test `SimpleMailMessage`** and does not prove that an email has reached the inbox.

## 4. Example of sending a simple email with JavaMailSender

The service below sends a request-received notification:

```java
package example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class SupportNotificationService {

    private final JavaMailSender mailSender;

    public SupportNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendRequestReceived(
            String recipient,
            String requestCode) {

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("support@example.com");
        message.setTo(recipient);
        message.setReplyTo("helpdesk@example.com");
        message.setSubject("Request received " + requestCode);

        String body = """
                Hello,

                We have received your support request.

                Request ID: %s
                Track it at: https://example.com/support/requests

                Best regards,
                Support Team
                """.formatted(requestCode);

        message.setText(body);
        mailSender.send(message);
    }
}
```

Here:

1. Spring injects a shared sender into the service through the constructor.
2. Each call to `sendRequestReceived(...)` creates **a new `SimpleMailMessage`**.
3. `setFrom(...)` determines the displayed sender address; `setReplyTo(...)` determines where replies are received.
4. `setTo(...)` determines the recipient.
5. `setSubject(...)` and `setText(...)` build the subject and the body.
6. `mailSender.send(message)` hands the sending process to the configured SMTP transport.

A successful return from `send` does not mean the message has been delivered to the inbox or that the user has read it. It only reflects the result of the submission to the SMTP relay, within the scope the application interacts with.

### Use MailSender when only simple mail is needed

If every method of the service only sends a `SimpleMailMessage`, you can depend on the slimmer interface:

```java
package example.mail;

import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class AlertMailService {

    private final MailSender mailSender;

    public AlertMailService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAlert(String recipient, String description) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("alerts@example.com");
        mail.setTo(recipient);
        mail.setSubject("System alert");
        mail.setText(description);

        mailSender.send(mail);
    }
}
```

`JavaMailSender` extends `MailSender`, so a regular `JavaMailSenderImpl` bean can also satisfy a dependency of type `MailSender`. However, if the application has multiple beans that satisfy that type, you need to identify the bean explicitly with `@Qualifier` or an appropriate configuration.

## 5. How to compose plain text that is easy for recipients to read

Because `SimpleMailMessage` does not provide an HTML layout, the quality of the content depends on how it is presented in text. A good text email should have:

- **A clear purpose right from the subject**: "Request #SUP-1042 received" is easier to understand than "Notification".
- **A short opening**: the recipient knows which action the email relates to.
- **Key information in a few lines**: order ID, time, status, priority level.
- **Sensible whitespace and line breaks**: separate paragraphs with blank lines and avoid one long block.
- **Complete links**: include both `https://` and the hostname; do not use relative paths.
- **A clear action**: "Open the page to confirm", "Contact support if you did not make this request".
- **Signature/source**: so the recipient knows which system the notification comes from.

A contrasting example:

**Hard to read:**

```text
New order. Code: ORD-1023 status: confirmed.
Check it now and review again if needed.
```

**Easier to read:**

```text
Subject: Order confirmation ORD-1023

Hello,

Your order has been received.

Order ID: ORD-1023
Status: Confirmed

View details:
https://example.com/orders

If you did not make this transaction, please contact support.

Thank you.
```

Note: `setSubject(...)` is a separate subject, so there is no need to put a "Subject:" line into `setText(...)`. The example only illustrates the structure as it is read.

### Newlines and line break characters

In Java, you can use `\n` or a text block to create paragraphs:

```java
String text =
        "Hello,\n\n"
        + "Your request has been received.\n"
        + "Code: SUP-1042\n\n"
        + "Best regards,\n"
        + "Support Team";

message.setText(text);
```

The `MimeMessage` built by the sender at the lower layer will handle how the content is transmitted over SMTP. When building the body, there is no need to manually add MIME separators or a `Content-Type` header to the text string.

Email clients may automatically detect URLs and turn them into clickable links, but **there is no guarantee that every client behaves the same way**. For essential tasks, include the full URL and an easy-to-understand instruction; users can still copy the link if the client does not automatically turn it into a link.

### Vietnamese text and encoding

`SimpleMailMessage` can contain Java Unicode strings:

```java
message.setSubject("Mã xác nhận tài khoản");
message.setText("Xin chào,\n\nMã của bạn là: 284193.");
```

Encoding for transmission over SMTP is handled by the Jakarta Mail implementation. In a Spring Boot project, configuring `spring.mail.default-encoding=UTF-8` helps use one consistent encoding for the content and headers that the sender creates. You should not manually replace Vietnamese diacritics with HTML escapes such as `&aacute;` in a plain text body: HTML entities may be displayed literally.

## 6. Sending to multiple recipients, Cc, and Bcc

`SimpleMailMessage` supports multiple recipient addresses:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("alerts@example.com");
mail.setTo("oncall@example.com", "operations@example.com");
mail.setCc("teamlead@example.com");
mail.setBcc("audit@example.com");
mail.setSubject("Incident alert");
mail.setText("The data synchronization task has failed.");

mailSender.send(mail);
```

Functionally:

| Field | What do recipients usually see? |
| --- | --- |
| `To` | List of primary recipients |
| `Cc` | List of carbon copy recipients |
| `Bcc` | Hidden recipients are usually not disclosed in the copy delivered to other recipients |
| `Reply-To` | The address the email client uses when the user chooses Reply |

You should not put hundreds of unrelated user addresses in a single `To` or `Cc`: the addresses may be exposed to each other. For emails that need personalization, privacy protection, per-recipient tracking, or separate bounce handling, you should create **one delivery record and one message for each recipient**, or use the provider's safe bulk sending feature.

`SimpleMailMessage` supports multiple recipients but **does not itself provide a bulk mailing system, quota management, a suppression list, or per-recipient status tracking**. These requirements belong to the application layer and/or the Email Service Provider.

## 7. Why not send HTML with SimpleMailMessage?

Suppose the service does the following:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("user@example.net");
mail.setSubject("Welcome");
mail.setText("<h1>Welcome!</h1><p>Your account is ready.</p>");
mailSender.send(mail);
```

The recipient may see the literal characters:

```text
<h1>Welcome!</h1><p>Your account is ready.</p>
```

The cause is that `setText(...)` in `SimpleMailMessage` defines **text content**. It has no `html=true` parameter and does not let the developer directly configure `text/html` or a multipart structure.

When you really need HTML, use:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mimeMessage = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("user@example.net");
helper.setSubject("Welcome");
helper.setText("<h1>Welcome!</h1><p>Your account is ready.</p>", true);

mailSender.send(mimeMessage);
```

In the `helper.setText(String, boolean)` overload, `true` means the input content is HTML. If you want both plain text and HTML in the same email, you need to enable multipart:

```java
MimeMessage mimeMessage = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("user@example.net");
helper.setSubject("Welcome");
helper.setText(
    "Hello! Your account is ready.",
    "<h1>Hello!</h1><p>Your account is ready.</p>"
);

mailSender.send(mimeMessage);
```

The `setText(plain, html)` overload adds two versions of the same content using the appropriate MIME mechanism. `SimpleMailMessage` provides no equivalent operation.

## 8. Do not use SimpleMailMessage for attachments or inline images

An email with a PDF guide is not just "text plus a file name". An attachment needs a MIME structure with `Content-Disposition`, `Content-Type`, and properly encoded binary data. `SimpleMailMessage` has no `addAttachment(...)` method.

Example using `MimeMessageHelper` to attach a PDF:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mimeMessage = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setFrom("support@example.com");
helper.setTo("user@example.net");
helper.setSubject("User guide");
helper.setText("Please see the attached PDF file.", false);

helper.addAttachment(
    "user-guide.pdf",
    new ClassPathResource("mail/user-guide.pdf")
);

mailSender.send(mimeMessage);
```

The file `mail/user-guide.pdf` in the example must actually be on the classpath, for instance `src/main/resources/mail/user-guide.pdf`. To display an image in HTML with `cid:logo`, you must also use `MimeMessageHelper#addInline(...)` with the appropriate multipart mode.

Therefore, when the requirement changes from "send a short reminder" to "send a reminder with a PDF", you can keep the `JavaMailSender` bean as is and upgrade the part that creates the **message** from `SimpleMailMessage` to `MimeMessage`. There is no need to rewrite the entire SMTP connection configuration.

## 9. SimpleMailMessage is mutable: create a new one for each email

An important mistake in applications with many requests is to store a `SimpleMailMessage` in a field of a singleton service and then change its properties per recipient.

**Do not:**

```java
@Service
public class UnsafeMailer {
    private final JavaMailSender mailSender;

    // One object shared across many requests:
    private final SimpleMailMessage shared = new SimpleMailMessage();

    public UnsafeMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String text) {
        shared.setTo(recipient);
        shared.setText(text);
        mailSender.send(shared);
    }
}
```

If two threads call `send(...)` concurrently, the `To` or `Text` value of one thread may be changed by the other thread before the content is sent. As a result, the email risks being sent to the wrong person or carrying the wrong content. A similar problem occurs when you keep a shared `MimeMessage` and change it across requests.

**Create a new object for each send:**

```java
public void send(String recipient, String text) {
    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("no-reply@example.com");
    mail.setTo(recipient);
    mail.setSubject("Notification");
    mail.setText(text);
    mailSender.send(mail);
}
```

A `JavaMailSender` bean can be injected and shared across services as long as the sender configuration is set up and is not changed while sending. That **does not mean a message should be reused across multiple requests**.

### Use a message template via the copy constructor

If many emails share the same From/Reply-To or a default subject, `SimpleMailMessage` has a copy constructor to create a copy:

```java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("no-reply@example.com");
template.setReplyTo("support@example.com");
template.setSubject("Notification");

// Each send creates an independent copy:
SimpleMailMessage message = new SimpleMailMessage(template);
message.setTo(recipient);
message.setText(body);

mailSender.send(message);
```

An important condition: the original template must be created and configured before multiple threads use it, and then treated as **unchanging**. Only modify the copy for each send. Do not put the recipient or the body of a request into a shared template.

For most small services, creating a new `SimpleMailMessage` and setting the necessary fields is usually concise enough; copying a template is only useful when there are really many shared properties.

## 10. The From address, Reply-To, and SMTP account are not the same thing

`SimpleMailMessage` has `setFrom(...)` and `setReplyTo(...)`, but these two fields do not directly select the username/password used to log in to SMTP.

Example:

```java
message.setFrom("orders@shop.example.com");
message.setReplyTo("help@shop.example.com");
```

Meanwhile, the sending configuration may be:

```properties
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
```

- `From` is the sender identity displayed on the message.
- `Reply-To` is where the email client sends replies.
- Username/password authenticate with the SMTP provider.
- The SMTP envelope sender (`MAIL FROM`) may be controlled separately by the provider, for bounce handling and mail delivery policy.

An ESP may require a verified `From` address or domain even if the application creates the message successfully. If the sender is not allowed, the provider may reject or rewrite the sender information. `SimpleMailMessage` does not bypass these rules by itself.

In addition, an email may be accepted by the SMTP relay but later be spam-filtered or bounced. Choosing `SimpleMailMessage` instead of `MimeMessage` does not guarantee deliverability.

## 11. Encoding, user input, and content safety

Using plain text reduces the complexity of HTML, but you still need to handle input carefully.

### Do not build raw headers yourself

Subject and address fields should be set through setters:

```java
mail.setTo(recipient);
mail.setSubject("Request confirmation");
mail.setText(body);
```

Do not assemble a raw email yourself with a string like `"To: " + recipient + "\r\nSubject: ..."` and then try to send it directly. Input containing CR/LF or control characters can lead to header injection if the application builds unsafe header syntax itself.

For user-supplied data:

- Validate recipient addresses according to business rules, and limit the number of recipients and the length.
- Limit the length of `Subject` and avoid allowing unnecessary control characters.
- Avoid putting all personal information, sensitive support content, or secrets into the subject/headers because they easily appear in logs and transport tools.
- Do not treat sending plain text as a form of end-to-end encryption; SMTP/TLS protects some transport hops, which does not mean the content is always encrypted all the way to the recipient's device.
- Do not put passwords or long-lived tokens into emails. For verification codes, there must be an expiration, a limit on the number of attempts, and secure confirmation logic on the backend.

### With verification codes, the security logic lives outside SimpleMailMessage

Example:

```java
public void sendOtp(String recipient, String otp) {
    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("security@example.com");
    mail.setTo(recipient);
    mail.setSubject("Verification code");
    mail.setText(
        "Your code is: " + otp
        + "\nThe code is valid only for the specified time."
    );
    mailSender.send(mail);
}
```

`SimpleMailMessage` only puts the code into the message. It does not itself:

- Generate a sufficiently secure random OTP.
- Store the hash/state of the code.
- Check the expiration.
- Limit the number of verification attempts.
- Lock the code after use.
- Guarantee that the recipient has received or read the email.

Those functions must live in a separate security and business layer. Do not log the raw OTP just because you need to diagnose the email sending process.

## 12. Separating text from business logic and supporting multiple languages

A simple mail service can start by concatenating Java strings. When emails have many variants or languages, you should separate the content out into a template/resource.

Example of a plain text template:

```text
Hello {name},

We have received your request {requestCode}.

Track progress:
{requestUrl}

Best regards,
Support Team
```

A renderer class can receive business data, ensure the content is formatted, and return a `String`. `SimpleMailMessage` only receives the resulting string via `setText(...)`. There is no need to switch to HTML just because the application uses templates.

With Spring, `MessageSource` can provide strings per locale, for example:

```properties
# messages_en.properties
mail.support.subject=Request {0} received
mail.support.body=Hello {0},\n\nRequest {1} has been received.\n\nBest regards.
```

Example code to get the message by language:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;

String subject = messageSource.getMessage(
    "mail.support.subject",
    new Object[] {requestCode},
    Locale.forLanguageTag("en-US")
);

String body = messageSource.getMessage(
    "mail.support.body",
    new Object[] {displayName, requestCode},
    Locale.forLanguageTag("en-US")
);

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("support@example.com");
mail.setTo(recipient);
mail.setSubject(subject);
mail.setText(body);
mailSender.send(mail);
```

This is an example for when the application already has `MessageSource` and the corresponding resource bundles. The `.properties` content needs to follow the correct escaping rules of resource bundles/message formats; for more complex templates, you can build a dedicated renderer to avoid problems with placeholders or languages.

### When should you switch to HTML because of experience requirements?

Plain text can support multiple languages and templates. But if the email needs:

- A multi-column invoice table with a clear layout.
- A CTA button with prominent formatting.
- A logo, inline images, or a brand identity system.
- Two versions, `text/plain` and `text/html`, for the same content.
- Attachments or standard MIME calendar content.

Then the choice of `MimeMessage` is driven by **the structural requirements of the message**, not because the number of variables in the template has grown.

## 13. Sending multiple SimpleMailMessage objects and notes on the result

`MailSender` and `JavaMailSender` support sending one or more `SimpleMailMessage` objects:

```java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("alerts@example.com");
first.setTo("alice@example.net");
first.setSubject("Notification A");
first.setText("Content A");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("alerts@example.com");
second.setTo("bob@example.net");
second.setSubject("Notification B");
second.setText("Content B");

mailSender.send(first, second);
```

A varargs call like the one above passes multiple messages to the sender in a single API call; it **does not mean they all become a single email** or guarantee that all recipients will succeed at the same time. If an error occurs, some messages may already have been accepted by the SMTP server before the error appears.

For systems that need to know the result **per delivery**, you should create a delivery ID and record a separate attempt for each recipient or each message. If you use an ESP with webhooks, reconcile the separate message ID/event to know whether it was deferred, bounced, or delivered.

A successful `send` usually only proves that the relay has accepted the corresponding submission. `SimpleMailMessage` has no built-in mechanism to know whether an email has been **opened** or **clicked**. These metrics, if available, require tracking infrastructure/an ESP, and the open/click signals themselves have limited reliability.

## 14. Error handling and retry

SMTP sending is an I/O operation that can run into network failures or provider policies. Spring Mail provides the `MailException` family to reflect email sending errors. Common kinds include:

| Type of problem | Example | Suggested action |
| --- | --- | --- |
| Connection error | Connection refused, connect timeout | Check host/port/firewall, retry with a limit if it is a temporary error |
| Read or write error | Read timeout while waiting for SMTP, write timeout while transmitting | Determine the sending stage and whether the provider may have received the message |
| Authentication error | Account or application is not allowed to log in | Fix the credentials/authentication mechanism; do not retry indefinitely |
| Invalid header/address | `To` or `From` value is rejected | Check the input data and the sender domain |
| Provider policy | Rate limit, unverified sender, message size | Follow the SMTP/ESP message to choose how to handle it |
| Bounce after submission | The destination server could not deliver the mail | Track ESP events; this is not necessarily an error in `send` |

Example of error handling at the service boundary:

```java
import org.springframework.mail.MailException;

public void sendStatusUpdate(String recipient, String statusText) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("no-reply@example.com");
    message.setTo(recipient);
    message.setSubject("Status update");
    message.setText(statusText);

    try {
        mailSender.send(message);
        // Record the submission result at the application layer.
    } catch (MailException exception) {
        // Record the error type and correlation ID in the logging infrastructure.
        // Pass the error to the appropriate handling/retry process.
        throw exception;
    }
}
```

This code does not implement retry yet. Retry needs a separate policy to avoid infinite loops in an HTTP thread. In particular, if a timeout occurs **after the client has finished sending `DATA` but has not yet received the `250` response**, the application cannot be sure whether the relay has received the email. Resending unconditionally may create a duplicate email.

A reasonable retry process may:

1. Store a stable `notification_id` or `delivery_id` for the send request.
2. Store each `attempt_id`, send time, provider, and result.
3. Classify temporary errors, configuration errors, permanent errors, and uncertain results.
4. Retry with **exponential backoff with jitter**, a limit on the number of attempts, and an appropriate deadline.
5. Track webhooks or the provider's reconciliation capabilities when available.
6. Do not mark `delivered` just because `send` returned successfully.

For OTP emails, the sending deadline policy needs to be tied to the validity period of the code. For operational alerts, you need to limit storms when the same error is detected continuously.

## 15. Do not let sending simple mail block the HTTP thread

`SimpleMailMessage` makes the **content creation** step simpler; it does not make SMTP operations non-blocking. `JavaMailSender.send(...)` in common usage still waits for the operations that communicate with the SMTP transport.

If you send directly within the request:

```text
POST /orders
   |
   v
Save order
   |
   v
Create SimpleMailMessage
   |
   v
JavaMailSender.send()
   |
   +--> TCP, TLS, AUTH, DATA, wait for acknowledgement
   |
   v
Return HTTP response
```

When SMTP is slow or down, the request will wait. For critical systems, a better organization may be an outbox/queue and a separate worker:

```text
HTTP request
     |
     v
Business service
     | Write business data and an outbox record
     v
HTTP response
     |
     v
Outbox / queue
     |
     v
Email worker
     | Create SimpleMailMessage
     | Call JavaMailSender
     | Retry/backoff and track attempts
     v
SMTP / ESP
```

An outbox helps tie the send request to the business transaction when implemented correctly. The worker handles SMTP errors independently, reducing the risk of one mail provider clogging the entire API.

However, the choice between synchronous and asynchronous sending also depends on the need: if an internal tool only sends a few non-urgent notifications upon an administrator's action, a synchronous call with a reasonable timeout may be enough. There is no need to build a complex queue just because you are using `SimpleMailMessage`.

## 16. Testing SimpleMailMessage

One advantage of the simple message type is that you can check its fields without a real mail server. Since the service depends on `JavaMailSender` through its constructor, a unit test can use Mockito.

Suppose we test `SupportNotificationService` from section 4:

```java
package example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class SupportNotificationServiceTest {

    @Test
    void sendsReadableRequestAcknowledgement() {
        JavaMailSender sender = mock(JavaMailSender.class);
        SupportNotificationService service =
                new SupportNotificationService(sender);

        service.sendRequestReceived("customer@example.net", "SUP-1042");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("support@example.com", sent.getFrom());
        assertEquals("customer@example.net", sent.getTo()[0]);
        assertEquals("helpdesk@example.com", sent.getReplyTo());
        assertEquals("Request received SUP-1042", sent.getSubject());
        assertEquals(true, sent.getText().contains("SUP-1042"));
    }
}
```

This test confirms that the service creates the correct message and calls the sender with that message. It **does not check** SMTP AUTH, TLS, whether the mail was accepted by the relay, or delivered to the inbox.

If you want to test integration, you can configure Spring Boot to use an internal SMTP test server on a port reserved for tests, then retrieve the received message from the server to inspect the headers and body. Do not use production SMTP to run automated unit tests.

A simple test example can also check Unicode, newlines, the recipient list, and that addresses are not exposed in Cc/To. When using dynamic templates, the test needs to verify that the important content is present and the variables are set correctly.

## 17. Common mistakes when using SimpleMailMessage

| Symptom | Common cause | Fix |
| --- | --- | --- |
| The recipient sees raw `<p>` or `<strong>` tags | HTML was put into `setText(...)` | Switch to `MimeMessageHelper#setText(html, true)` |
| Want to attach a PDF but cannot find `addAttachment` | `SimpleMailMessage` only supports simple text | Use `MimeMessage` + multipart `MimeMessageHelper` |
| Vietnamese email has broken diacritics | The sender's encoding or the environment is inconsistent | Configure UTF-8 and check the sending/receiving systems |
| Email content gets mixed up between two requests | A single mutable `SimpleMailMessage` is shared | Create a new message for each send |
| Messages from another address are rejected by SMTP | `From` does not belong to the verified sender domain | Review the SMTP/ESP policy and the sender configuration |
| Bounces are not received at `Reply-To` | Reply-To is confused with the SMTP envelope sender | Configure the bounce address through the appropriate provider |
| Used `Bcc` but accidentally exposed recipients | Built a `To` list yourself or sent together against the rules | Use recipient isolation and the correct API |
| Do not know whether the recipient has read it | `send` only performs a submission | Integrate telemetry from the ESP if needed |
| HTTP request is slow when sending mail | Blocking SMTP, network, or high timeout | Use timeouts, a queue/outbox, or a worker |
| Retry causes two identical emails | The server may have received the message before the timeout | Store attempts and reconcile the result |
| Tests connect to real SMTP | No fake/mock sender is used in unit tests | Inject a mock, use an SMTP test server for integration |
| Modifying the original template leaks content | Editing an object shared between threads | Copy the template before changing To/Text |

## 18. Decision rules in a project

When developing a new email feature, you can choose by following this flow:

```text
Do you need to send email from the Spring application?
             |
             v
Can the body be fully expressed in plain text?
             |
       +-----+-----+
       |           |
      Yes          No
       |           |
       v           v
Need attachment,  Use MimeMessage
inline image,     + MimeMessageHelper
HTML alternative
or custom MIME?
       |
   +---+---+
   |       |
   No     Yes
   |       |
   v       v
SimpleMailMessage   MimeMessage
+ JavaMailSender    + MimeMessageHelper
```

Four practical questions:

1. **Does the recipient only need to read information or copy a URL?** `SimpleMailMessage` is usually enough.
2. **Do you need formatting, buttons, banners, images, or files?** Use `MimeMessage`.
3. **Do you need both a plain text and an HTML version in one email?** Use multipart `MimeMessageHelper`; do not send two independent `SimpleMailMessage` objects as a substitute.
4. **Do you need bulk sending, retry, tracking, or delivery events?** This is a mail-sending architecture/ESP requirement; you may still use `SimpleMailMessage` for the body, but you must add a worker, event storage, and provider policy.

### Examples from simple to complex

**Level 1 — Status email**

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("customer@example.net");
mail.setSubject("Request received");
mail.setText("We have received your request.");
mailSender.send(mail);
```

**Level 2 — Status email with a link**

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("customer@example.net");
mail.setSubject("Track your request");
mail.setText(
    "Your request has been received.\n\n"
    + "View progress: https://example.com/support/requests"
);
mailSender.send(mail);
```

Adding a URL does not require switching to HTML.

**Level 3 — Status email with a PDF**

```text
Requirement: send status + confirmation.pdf file
→ Switch to MimeMessage and addAttachment(...).
```

**Level 4 — Email with a CTA button, logo, and a plain text fallback**

```text
Requirement: HTML + inline image + plain text alternative
→ Use multipart MimeMessageHelper, setText(plain, html), addInline(...).
```

Each upgrade only changes how the message is built according to the need; the `JavaMailSender` configuration and the SMTP infrastructure can still be reused.

## 19. Takeaways for Spring Mail developers

`SimpleMailMessage` is suitable when an email **needs only plain text, basic header fields, and content that is easy to read as text**. A small API makes the service easy to understand, easy to unit test, and less prone to HTML/MIME structure errors.

The usage principles to keep consistent:

- Use a Spring-managed `JavaMailSender` or `MailSender`; do not create a new SMTP sender for each email.
- Create a **new `SimpleMailMessage` for each send**, or copy an immutable template before modifying it.
- Set `From`, `To`, `Reply-To`, `Subject`, and `Text` through the appropriate setters.
- Write plain text with paragraphs, line breaks, and full URLs; keep Unicode/UTF-8.
- When you need HTML, an alternative part, attachments, inline images, or advanced headers, switch to `MimeMessage` and `MimeMessageHelper`.
- Treat a successful `send()` as the result of an SMTP submission, not proof of delivered/opened/clicked.
- Protect input, secrets, and recipient data; apply timeouts, retry, and queues if operational requirements call for them.

The right choice is not about which API is "more powerful" but about **the form of email you need to create**. For a plain text email, `SimpleMailMessage` is usually a clear and sufficient tool; for a complex message, `MimeMessage` is the choice designed for that structure.
