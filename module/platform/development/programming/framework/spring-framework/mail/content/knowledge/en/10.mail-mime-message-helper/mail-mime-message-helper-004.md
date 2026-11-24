# Setting the subject and text

An email notification from a Spring application usually has two parts that the recipient cares about first: the **subject** to know what the message is about, and the **content** (*text/body*) to read the details. When using **Spring Framework Mail**, the `MimeMessageHelper` class provides concise methods for filling in these two parts of a `MimeMessage`:

~~~java
helper.setSubject("Your order has been confirmed");
helper.setText("Thank you for your order.", false);
~~~

The two statements look simple, but what needs to be understood lies behind them: **the Subject is an email header**, while **the text is MIME content**. The content can be plain text or HTML; an email can also contain both forms so that the mail reader chooses. For Vietnamese text, you need to use an appropriate charset to avoid broken diacritics.

This lesson focuses on how to set `subject` and `text` for the right purpose, explains the overloaded versions of `setText(...)`, how to choose plain text or HTML, the MIME structures that are created, and common errors in Spring Boot applications.

## 1. Where does MimeMessageHelper stand in the mail-sending flow?

`MimeMessageHelper` is a helper class in the package `org.springframework.mail.javamail`. It helps developers build email content through a convenient API, instead of manually manipulating each header and each Jakarta Mail `MimeBodyPart`.

The common flow:

~~~mermaid
flowchart LR
    A["Business data"] --> B["Create MimeMessage"]
    B --> C["MimeMessageHelper"]
    C --> D["Set Subject and Text"]
    D --> E["JavaMailSender.send"]
    E --> F["SMTP relay"]
    F --> G["Email receiving infrastructure"]
~~~

The components have different responsibilities:

| Component | Role |
| --- | --- |
| `JavaMailSender` | Creates the `MimeMessage` and sends it through the configured SMTP infrastructure. |
| `MimeMessage` | Represents the email message in the Jakarta Mail model: headers, content, and MIME parts. |
| `MimeMessageHelper` | Helps set the sender, recipients, Subject, text, HTML, file attachments, and inline resources. |
| `setSubject(...)` | Fills in the **message subject**, which belongs to the headers. |
| `setText(...)` | Fills in the **message content**, deciding the plain text/HTML form or the alternative versions. |

`MimeMessageHelper` **does not send mail by itself**. Calling `setSubject` or `setText` only changes the message object being prepared; the send operation starts only when the application calls `mailSender.send(message)`.

## 2. Create the helper before setting the subject and text

The example below uses a Spring Boot application with the mail starter and a configured `JavaMailSender`.

### 2.1. Gradle dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

With Spring Boot using Jakarta Mail, import the message classes from the package `jakarta.mail.*`, while `MimeMessageHelper` still belongs to `org.springframework.mail.javamail`.

### 2.2. Illustrative SMTP configuration

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

`smtp.provider.example` is only an illustrative hostname. When deploying, you need to use the host, port, TLS mechanism, and credentials of the actual SMTP provider. Secrets should be taken from the environment or a secret-management system; do not write real passwords in the repository.

These connection configuration properties are **different from the Subject and Text**. They determine which SMTP relay the application sends the message to; they do not fill in content for an email by themselves.

### 2.3. A message with a Subject and plain text

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);

        helper.setSubject("Welcome to the system");
        helper.setText(
                "Your account has been created successfully.",
                false
        );

        mailSender.send(message);
    }
}
~~~

In the constructor:

~~~java
new MimeMessageHelper(message, false, "UTF-8")
~~~

- `message` is the MIME object that needs to be filled with data.
- `false` means, in this example, **not creating a multipart structure from the start**. This suits simple text content.
- `"UTF-8"` specifies the charset that the helper uses for operations that need character encoding.

The `From` address must be allowed by the SMTP provider. To keep the example compact, the code does not add recipient syntax checking, retry handling, or sending-status storage; those are independent responsibilities of the application.

## 3. setSubject(String): setting the email subject

The method:

~~~java
helper.setSubject("Registration confirmation");
~~~

sets the value of the message's **`Subject` header**. This is what usually appears in the message list, in phone notifications, and on the detail screen of email-reading applications.

For example:

~~~java
helper.setSubject("Order #A102 has been confirmed");
~~~

The reader usually sees:

~~~text
Order #A102 has been confirmed
~~~

In the raw email source, the data may appear in an equivalent header form:

~~~text
Subject: =?UTF-8?B?...encoded-data...?=
~~~

The `...encoded-data...` segment in the example above is only a **placeholder**, not valid Base64 to be decoded. The library is responsible for creating the real MIME string according to the appropriate encoding rules.

### 3.1. The Subject is a header, not part of the body

Consider the message:

~~~text
From: notice@example.org
To: buyer@example.net
Subject: Your order has been confirmed
Content-Type: text/plain; charset=UTF-8

This is the detailed content of the email.
~~~

The `Subject` line belongs to the **headers**; the part after the blank line is the **body**. When using `MimeMessageHelper`, you do not need to add the word `Subject:` before the string yourself:

~~~java
// Correct: pass the subject value.
helper.setSubject("Your order has been confirmed");

// Not needed and should not be done: attaching the header name yourself:
helper.setSubject("Subject: Your order has been confirmed");
~~~

The second way would make the word `Subject:` become part of the **subject content**, rather than an operation that creates a new header.

### 3.2. Vietnamese and Unicode subjects

A Java string can contain accented letters, letters from many languages, and emoji:

~~~java
helper.setSubject("Lịch hẹn của bạn đã được xác nhận 📅");
~~~

With a helper created with the `UTF-8` charset, the Jakarta Mail library can convert the Subject's Unicode characters into a suitable header form, for example a **MIME encoded-word per RFC 2047**. The raw header may contain the structure:

~~~text
=?UTF-8?B?...?=
=?UTF-8?Q?...?=
~~~

B and Q are two ways of representing Unicode data with characters that are safe for traditional email headers. They are **not security encryption methods**. The mail-reading program decodes the header to present the Subject string normally.

An internationalized email system can also support UTF-8 directly in headers according to the appropriate standards. For a typical Spring application, putting a Unicode string into `setSubject(...)` with an explicit charset is the easy-to-maintain way, rather than computing the encoded-word yourself.

**You should not call Base64 yourself before passing the Subject to the helper.** If you send an already-encoded string into an API that is itself responsible for encoding headers, the result may be encoded once more, or the user may see a technical string instead of the subject.

### 3.3. Subject length and content

The subject should be specific enough for the recipient to understand the email, but not too long. When the Subject contains data from users or external systems, you need to control:

- Do not leave it `null`, an empty string, or only whitespace if the business requires a subject.
- Do not put passwords, tokens, authentication codes, or detailed private information into the Subject.
- Restrict control characters and the `CR`/`LF` line-break characters that are unsuitable for headers.
- Have a length limit per interface and business requirements; do not cut arbitrarily in the middle of Unicode characters.
- Do not use raw HTML content as the Subject; it is a text subject, not an HTML display area.

An example input-checking method:

~~~java
private static String requireSubject(String subject) {
    if (subject == null || subject.isBlank()) {
        throw new IllegalArgumentException(
                "The email subject must not be empty"
        );
    }

    if (subject.indexOf('\r') >= 0
            || subject.indexOf('\n') >= 0) {
        throw new IllegalArgumentException(
                "The email subject must not contain line-break characters"
        );
    }

    return subject;
}
~~~

Then call:

~~~java
helper.setSubject(requireSubject(subject));
~~~

The check above illustrates two basic conditions. The rules for length, data types, other control characters, and permitted content must be determined by the system's requirements.

## 4. setText(String): plain-text content

The method:

~~~java
helper.setText("Hello!");
~~~

sets the **plain text** content for the message. This is the suitable way when the email has only text and does not need HTML formatting.

For example:

~~~java
helper.setText("""
        Hello,

        Your support request has been received.

        Best regards,
        Support team
        """);
~~~

Plain text keeps lines and whitespace according to how the mail reader handles them. HTML tags such as `<p>`, `<strong>`, or `<a>` are not interpreted into interface elements.

### 4.1. When to use plain text?

Plain text is especially suitable for:

- Short system notifications whose content is mainly text.
- Content that needs to be easy to view across many different mail-reading applications.
- Emails that need no layout, color scheme, images, or complex presentation.
- An alternative to HTML content to improve readability when HTML is blocked or not supported.

For example:

~~~text
Hello,

Support request code: TKT-1024
Status: Received

You can track the request in the application.
~~~

If the content needs only that, `setText(plainText)` is usually enough. There is no need to build HTML just to display a few lines.

### 4.2. The effect of line-break characters

In plain text, you can create a new line with the newline character in a Java string:

~~~java
String text = "Hello,\n"
        + "\n"
        + "Your request has been received.\n"
        + "\n"
        + "Best regards.";
helper.setText(text);
~~~

The display of whitespace and line breaks can differ between mail-reading applications. Avoid using many spaces to align columns or assuming the recipient always uses a monospace font.

In the raw MIME data, the library is responsible for normalizing the content representation and the line-break style suited to the email protocol; the application does not need to build each MIME line byte by byte.

## 5. setText(String, boolean): choosing plain text or HTML

This overloaded version is one of the most important APIs:

~~~java
helper.setText(content, isHtml);
~~~

Meaning:

- `isHtml = false`: the content is treated as **plain text**.
- `isHtml = true`: the content is treated as **HTML**.

A comparison example:

~~~java
// The body is plain text.
helper.setText(
        "The order has been confirmed.",
        false
);
~~~

and:

~~~java
// The body is HTML.
helper.setText(
        "<p>The order has been <strong>confirmed</strong>.</p>",
        true
);
~~~

This is a choice of **content type**, not a “send successfully”, “enable Unicode”, or “enable security” option.

### 5.1. What happens if you pass HTML with false?

~~~java
helper.setText(
        "<h1>Notice</h1><p>Hello.</p>",
        false
);
~~~

In that case, the application is declaring the body as plain text. The recipient may see the literal characters `<h1>`, `</h1>`, `<p>`, because the reader was not asked to interpret them as HTML.

### 5.2. What happens if you pass plain text with true?

~~~java
helper.setText(
        "Hello,\nYour request has been completed.",
        true
);
~~~

This text will be marked as HTML. The reader may collapse whitespace or display line breaks differently from plain text, because in HTML a bare newline character is **not equivalent** to the `<br>` or `<p>` tag.

Create genuine HTML content when setting `true`:

~~~java
helper.setText(
        "<p>Hello,</p>"
        + "<p>Your request has been completed.</p>",
        true
);
~~~

You should not use `isHtml = true` just because you want to keep Vietnamese diacritics: the **charset** and the **HTML mode** solve two different problems.

## 6. setText(String plainText, String htmlText): two representations of the same content

A transactional email can provide **two versions of the content**:

- `text/plain` for readers that do not support HTML or users who prefer text form.
- `text/html` for readers capable of presenting rich content.

`MimeMessageHelper` has the version:

~~~java
helper.setText(plainText, htmlText);
~~~

This is not “sending two emails”. The helper organizes the two content forms within a MIME structure of the **`multipart/alternative`** kind, so that the email-reading application chooses the form it supports.

### 6.1. An example of two content forms

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("buyer@example.net");
helper.setSubject("Your order has been confirmed");

String plainText = """
        Hello,

        Order #A102 has been confirmed.
        See the information in your account.
        """;

String htmlText = """
        <html>
          <body>
            <h2>The order has been confirmed</h2>
            <p>Your order <strong>#A102</strong>
               has been confirmed.</p>
            <p>See the information in your account.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);

mailSender.send(message);
~~~

Here the constructor receives `true` to create a **multipart message**. This is important: the `setText(plainText, htmlText)` version needs a helper that supports a multipart structure to place the alternative parts.

Do not use a non-multipart constructor and expect the library to create every needed container for the two-content API. For a simple email with exactly one text body, the constructor with `false` is suitable; for plain/HTML alternatives, you should use multipart mode.

### 6.2. Why should there be a plain-text version?

Some email environments restrict HTML; some users choose a text-only mode. A plain-text version also helps the message retain its meaning when HTML is not interpreted.

The two versions should be **equivalent in important information**. For example, if the HTML has an appointment date and an essential action link, the plain version should also have the appointment date and a readable URL. Do not create an empty plain version just to have one.

A conceptual MIME structure:

~~~text
MIME message
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    └── text/html; charset=UTF-8
~~~

In practice, depending on the `MimeMessageHelper` mode, the `multipart/alternative` structure can be nested inside `multipart/mixed` or `multipart/related`. Do not infer the position of the parts just from the method name without looking at the real MIME structure.

### 6.3. When are two versions not needed?

If the email is a short plain-text passage with no need for HTML, you can just call `setText(plainText)`. If the product chooses HTML-only, you can call `setText(htmlText, true)`, but you need to understand that there is no replacement text/plain version created by that very call.

The decision to create both is a **decision about compatibility and the mail-receiving experience**, not a syntactic requirement for every email.

## 7. Summary table of the setText versions

| Call | Meaning | Content structure |
| --- | --- | --- |
| `setText(String text)` | Sets plain text | `text/plain` |
| `setText(String text, false)` | Sets plain text explicitly | `text/plain` |
| `setText(String text, true)` | Sets HTML | `text/html` |
| `setText(String plainText, String htmlText)` | Sets both plain text and HTML | `multipart/alternative` (can sit inside another multipart container) |

Note when reading code: the two versions have **two parameters** but completely different meanings:

~~~java
helper.setText(html, true);
helper.setText(plain, html);
~~~

In the first call, the second parameter is a **boolean**. In the second call, the second parameter is a **String**. The IDE and the compiler distinguish them by parameter type.

If a variable `html` has type `String` and is mistakenly passed to the boolean version, the program does not compile; but if you already have two strings and choose the wrong overload, the program can still create a message with a structure different from your intent. You should name them clearly `plainText`, `htmlText` and use the appropriate overload.

## 8. The Subject and the body are Unicode-encoded differently

Both parts can contain Vietnamese, but their positions in the email differ:

~~~text
Subject: [the message's MIME header]
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

[the message's body]
~~~

**The Subject is a header:** Jakarta Mail can use an `encoded-word` to represent Unicode in traditional headers. The raw header may differ from the original Java string.

**The text is the body:** Jakarta Mail marks the content type such as `text/plain` or `text/html` and the charset, and can also choose an appropriate `Content-Transfer-Encoding` to carry the data through email.

For example:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Xin chào – Đơn hàng đã xác nhận ✅");
helper.setText(
        "Cảm ơn bạn. Đơn hàng đã được xử lý.",
        false
);
~~~

With this message, both the Subject and the text have Unicode letters. Specifying `UTF-8` gives the library charset information when building the MIME data, but it **does not make the two fields encoded with the same syntax**.

### Do not pre-encode with Base64

This is an error-prone approach:

~~~java
// There is no need to convert the subject to Base64 and then pass it to the helper.
// String encodedSubject = Base64.getEncoder()
//         .encodeToString(subject.getBytes(StandardCharsets.UTF_8));
// helper.setSubject(encodedSubject);
~~~

`setSubject(...)` takes the **text you want the recipient to see**, not a manually built MIME header field.

Similarly, there is no need to convert the body to Base64 yourself in order to use `setText(...)`. Unless you are implementing another custom protocol, give the helper the **original content** and let Jakarta Mail handle the encoding when serializing.

## 9. MIME structures of single text, single HTML, and multipart

For the same logical content, the way of building can produce different structures.

### 9.1. Plain text only

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Notification");
helper.setText("The request has been completed.");
~~~

When represented as raw MIME, the body part may look similar to:

~~~text
Subject: Notification
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

The request has been completed.
~~~

The raw example above only illustrates the structure; a real Subject/body in accented Vietnamese may use a different encoding representation.

### 9.2. HTML only

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setSubject("Notification");
helper.setText("<p>The request has been completed.</p>", true);
~~~

The body part is of type `text/html`. There is no need to create multipart just because the body is HTML.

### 9.3. Plain text + HTML

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setSubject("Notification");
helper.setText(
        "The request has been completed.",
        "<p>The request has been <strong>completed</strong>.</p>"
);
~~~

This case needs to contain two MIME parts. Jakarta Mail manages the boundaries so that the `text/plain` and `text/html` parts do not get mixed with each other.

### 9.4. HTML + file attachment

If you add a PDF or an inline image:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

helper.setSubject("Weekly report");
helper.setText(
        "The weekly report is ready.",
        "<p>The weekly report is <strong>ready</strong>.</p>"
);

helper.addAttachment(
        "report.pdf",
        new ClassPathResource("mail/report.pdf"),
        "application/pdf"
);
~~~

The example assumes that `org.springframework.core.io.ClassPathResource` has been imported and the file `mail/report.pdf` is on the classpath. Multipart mode helps the body and attachment parts be represented in an appropriate structure.

Point to remember: **the Subject is still a header of the message**, while `setText` only determines the corresponding content parts. Having an attachment does not change the purpose of `setSubject(...)`.

## 10. Composing content from a template without breaking the Subject/text

In a real application, the Subject and body are usually built from dynamic data such as the customer name, order code, or appointment time.

~~~java
String subject = "Order " + orderCode + " has been confirmed";

String plainText = """
        Hello,

        Your order %s has been confirmed.
        """.formatted(orderCode);

helper.setSubject(subject);
helper.setText(plainText, false);
~~~

String concatenation illustrates this quite clearly, but when there are many templates, multiple languages, or many variables, you should have a template-rendering layer that prepares the **logical content** before calling `MimeMessageHelper`.

~~~mermaid
flowchart LR
    A["Validated data"] --> B["Template and locale"]
    B --> C["subject / plainText / htmlText"]
    C --> D["MimeMessageHelper"]
    D --> E["MimeMessage"]
~~~

### 10.1. The Subject is rendered as plain text

Suppose there is a template:

~~~text
Order {orderCode} has been confirmed
~~~

The template layer replaces `{orderCode}` with valid data. Do not embed HTML tags to bold the Subject; email clients do not interpret the Subject as an HTML document.

When there are multiple languages, create a translated Subject per locale, then put the final Unicode string into `setSubject(...)`. There is no need to convert to ASCII by dropping Vietnamese diacritics.

### 10.2. HTML needs dynamic data to be handled by context

Suppose the customer name is content entered by the user. The following snippet is risky if the value is concatenated straight into HTML:

~~~java
String html = "<p>Hello " + customerName + "</p>";
~~~

If the name contains special characters such as `<`, `>`, or `&`, the HTML can be altered. For untrusted data, you need to use a template engine with a mechanism for **escaping by HTML context**, or an appropriate escape function. Do not regard `MimeMessageHelper.setText(html, true)` as a malicious-HTML filter: the helper only sets the **HTML content form**, and does not itself validate or sanitize all the data inside.

For URLs provided externally, you must also validate the scheme, host, and access rights; HTML escaping does not replace URL validation. In transactional email, avoid creating links that carry sensitive tokens in the Subject.

### 10.3. Plain text should not be HTML with tags arbitrarily stripped

Some applications want to create the plain version by removing all HTML tags. This approach can lose the link URLs, the table contents, or important action information.

It is better to build a **plain version with equivalent content**, for example:

~~~text
Hello An,

Order A102 has been confirmed.
View details at: https://app.example.org/orders/A102
~~~

and the HTML:

~~~html
<p>Hello An,</p>
<p>Order <strong>A102</strong> has been confirmed.</p>
<p><a href="https://app.example.org/orders/A102">View details</a></p>
~~~

The illustrative URL does not represent a real service. Both versions convey the same main information, differing only in the level of presentation.

## 11. A complete example: an email-sending service with subject, plain, and HTML

Suppose the application sends order-update notifications and wants the recipient to have both plain-text and HTML content. Below is a simple service using `JavaMailSender` and `MimeMessageHelper`.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public OrderStatusMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {

        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendStatus(
            String recipient,
            String orderCode,
            String status) throws MessagingException {

        String to = requireText(recipient, "Recipient");
        String code = requireText(orderCode, "Order code");
        String state = requireText(status, "Status");

        // Business content. With real HTML, dynamic data must be escaped.
        String subject = "Order update " + code;

        String plainText = """
                Hello,

                Order %s has the status: %s.

                Please log in to the application to see the details.
                """.formatted(code, state);

        // This simple example only uses a status that the system controls.
        // If code/state can contain HTML characters, they must be escaped first.
        String htmlText = """
                <html>
                  <body>
                    <h2>Order update</h2>
                    <p>Order <strong>%s</strong>
                       has the status: <strong>%s</strong>.</p>
                    <p>Please log in to the application to see the details.</p>
                  </body>
                </html>
                """.formatted(code, state);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(to);
        helper.setSubject(requireSubject(subject));
        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }

    private static String requireText(
            String value, String fieldName) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " must not be empty"
            );
        }
        return value;
    }

    private static String requireSubject(String value) {
        String subject = requireText(value, "Subject");

        if (subject.indexOf('\r') >= 0
                || subject.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    "Subject must not contain line-break characters"
            );
        }

        return subject;
    }
}
~~~

The application's own configuration:

~~~properties
app.mail.from=${APP_MAIL_FROM}
~~~

The example above assumes `orderCode` and `status` are data already controlled by the business layer and have a suitable character set to be used directly in HTML. If they come from free-form data or an untrusted source, you need to **escape HTML by context** before rendering the HTML, not just check for non-empty like the `requireText(...)` method.

### Analysis of the important steps

1. `subject` is created from the business meaning; `plainText` and `htmlText` are built as two representations of the same content.
2. `createMimeMessage()` returns a new message object for each send request.
3. `new MimeMessageHelper(message, true, "UTF-8")` creates a helper with multipart and charset support.
4. `setSubject(...)` puts the subject into the Subject header.
5. `setText(plainText, htmlText)` sets the alternative body parts of the MIME message.
6. `mailSender.send(message)` is what actually performs the SMTP interaction.

**Do not create a singleton `MimeMessage` and replace the Subject/text for multiple concurrent requests.** `MimeMessage` is a mutable object; each send request should have its own message to avoid mixing up recipients and content.

## 12. The order of calling setSubject and setText

For a simple message, you can set the Subject before the Text or vice versa; the two methods affect different areas of the message's data.

For example:

~~~java
helper.setSubject("Notification");
helper.setText("Content.", false);
~~~

or:

~~~java
helper.setText("Content.", false);
helper.setSubject("Notification");
~~~

Both ways mean setting one Subject and one body.

But note that **subsequent `setText` calls usually replace the body content that the helper is managing**, rather than “appending a paragraph”:

~~~java
helper.setText("First content.", false);
helper.setText("Second content.", false);
~~~

You should not expect to get:

~~~text
First content.
Second content.
~~~

If you want to join two paragraphs, build a complete string first before calling once:

~~~java
String body = """
        First content.

        Second content.
        """;

helper.setText(body, false);
~~~

With multipart, do not arbitrarily mix multiple `setText(...)` versions expecting the helper to add more body parts. Determine the content structure you need to create, choose the appropriate overload, and set the main content according to your intent.

### When there are inline images, set the Text first

For HTML email with images referenced by `cid:`, the usually recommended usage is to **call `setText(...)` first and then `addInline(...)`**:

~~~java
helper.setText(
        "<p>Hello!</p><img src=\"cid:logo\" alt=\"Logo\">",
        true
);
helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

This snippet assumes the helper was built in an appropriate multipart mode and `ClassPathResource` has been imported. The order above helps avoid compatibility problems with some email readers when recognizing inline resources.

Adding inline images or attachments requires understanding the MIME structure; it does not change the role of the Subject.

## 13. Does setText send mail by itself or mark it as read?

No. A few method names in the mail ecosystem can be confusing:

- `setSubject(...)` only sets the subject.
- `setText(...)` only sets the body.
- `saveChanges()` can finalize some MIME headers/metadata when needed; it **does not send SMTP**.
- `JavaMailSender.send(...)` is what submits the message through the SMTP transport.
- A message accepted by the relay **does not mean** the message reached the Inbox or was opened by the recipient.

A conceptual state diagram:

~~~mermaid
flowchart TD
    A["New MimeMessage"] --> B["Set Subject, Text, From, To"]
    B --> C["Prepared message"]
    C --> D["JavaMailSender.send"]
    D --> E["SMTP relay accepts or returns an error"]
    E --> F["Later delivery process"]
~~~

A successful call to `setText` only indicates that the object was updated according to the API; it does not prove the body was displayed correctly by the email client, does not check that the recipient exists, and does not confirm that the infrastructure has delivered it.

## 14. Reading the subject and text back when you need to observe the message

During development, you can check the fields of a `MimeMessage` that was just built:

~~~java
String subject = message.getSubject();
String contentType = message.getContentType();
boolean isPlainText = message.isMimeType("text/plain");
boolean isHtml = message.isMimeType("text/html");
~~~

`getSubject()` provides a way to read the subject through the Jakarta Mail API. `getContentType()` tells the MIME type of the current object. However, for a multipart message, the outer level may be `multipart/mixed` or `multipart/related` even when a child part is `text/html`.

If you want to view the body directly:

~~~java
Object content = message.getContent();
~~~

The type of `content` may be `String`, `Multipart`, or another data form depending on the `Content-Type` and how the message was built. **Do not always cast it to `String`** for every message.

For a simple test email, you can observe the serialized MIME:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

static String rawMimeForLocalTest(MimeMessage message)
        throws MessagingException, IOException {

    message.saveChanges();

    ByteArrayOutputStream out = new ByteArrayOutputStream();
    message.writeTo(out);

    return new String(
            out.toByteArray(),
            StandardCharsets.US_ASCII
    );
}
~~~

**Note:** This is only an example of observing headers and MIME boundaries in a development environment with fake data; the raw MIME representation may contain non-ASCII bytes in some configurations, so you should not regard `new String(..., US_ASCII)` as a way to fully read every Unicode message. If you need to analyze real MIME, use the Jakarta Mail API or keep the binary bytes intact in an appropriate testing tool.

`writeTo(...)` may access attachment data and consume memory proportional to the message size. Do not use this as a mandatory step for every production email, and **do not write raw MIME containing customer data to logs**.

### Checking the Subject property directly

When you want to see the raw value of the header:

~~~java
message.saveChanges();

String rawSubject = message.getHeader("Subject", null);
String decodedSubject = message.getSubject();
~~~

`rawSubject` may contain an encoded-word or header folding; `decodedSubject` is more convenient for the application. Do not write tests that depend on **a specific Base64 string** generated by the library, because the way of encoding and splitting the header can change within the scope of the standard.

## 15. Handling errors when setting the Subject and Text

The MIME-building APIs can throw `MessagingException`; within the sending process, Spring also uses exceptions belonging to the `MailException` group. You should distinguish input-data errors from SMTP infrastructure errors.

| Symptom | Possible cause | Approach |
| --- | --- | --- |
| Empty Subject | The business has not rendered the subject | Check the value before calling `setSubject` |
| The recipient sees the text `<p>` or `<strong>` | HTML data declared as plain text | Use `setText(html, true)` when you want HTML displayed |
| Line breaks in the content are not as expected | Plain text put into HTML mode | Write proper HTML or use plain text |
| Body is correct but the Subject has broken diacritics | The source charset or header encoding is not appropriate | Check the Java string before sending and how the helper is used with UTF-8 |
| No plain-text version | Only `setText(html, true)` is used | Consider `setText(plainText, htmlText)` with multipart |
| Error when setting both plain/HTML | The helper was not created in an appropriate multipart mode | Create the helper with a multipart mode before calling the two-String overload |
| HTML displays unwanted content | Dynamic data has not been escaped | Escape by context in the template layer |
| SMTP reports an auth/TLS/connection error | The sending configuration is unsuitable or the infrastructure has a fault | Check host, port, credentials, TLS, and messages from SMTP |
| Email was sent but is not seen in the Inbox | Bounce, spam, receiving-system policy | Track the provider's status, do not only look at the `setText` call |

### Separate data errors from sending errors

For example, an API may receive the Subject and body from the business layer:

~~~java
if (subject == null || subject.isBlank()) {
    throw new IllegalArgumentException(
            "Invalid Subject"
    );
}

if (body == null || body.isBlank()) {
    throw new IllegalArgumentException(
            "Invalid email content"
    );
}
~~~

These are data errors that need to be handled before contacting SMTP.

Conversely, if `mailSender.send(message)` fails because of connection, authentication, or server rejection, that is an error of the **sending process**. Checking the Subject/body before sending cannot replace the retry mechanism, bounce handling, or SMTP administration.

## 16. Misconceptions to avoid

### “setSubject only supports English without diacritics”

No. You can pass a Java string containing accented Vietnamese and Unicode. When using `MimeMessageHelper` and an appropriate charset, Jakarta Mail will handle the header representation.

### “If setText receives HTML, it automatically understands it must display HTML”

Not always. `setText(String)` sets plain text. To get HTML, you need to use `setText(String, true)` or the two-string plain/HTML version.

### “The true parameter of the constructor is the HTML mode”

No. In `new MimeMessageHelper(message, true, "UTF-8")`, `true` indicates **multipart mode**. In `setText(html, true)`, `true` indicates **isHtml**. The two boolean positions have independent meanings.

### “Just setting Content-Type makes all email readers display the same”

No. Mail-reading applications have different levels of support and HTML safety policies. The library helps create correctly structured MIME, but CSS, images, and layout may be restricted.

### “setText(plain, html) creates two different emails”

No. It creates **two content forms within the same message** through the MIME alternative structure. Choosing which form to display is decided by the mail-reading program.

### “You can set the Subject and then add CRLF yourself to insert a header”

You should not. The Subject needs to be handled as text data, not a raw header block. Dynamic data with line-break characters must be checked to avoid syntax errors and the risk of header injection.

### “Base64-encoding the Subject will help security”

No. MIME encoded-word is used to **represent characters**, not to keep secrets. The email Subject can still be decoded by the transport systems, storage, and readers.

### “After setText the mail has reached the recipient”

No. `setText` only changes the message. `send` submits the mail to SMTP; final delivery and read status need other tracking mechanisms.

### “You need to call setText many times to add paragraphs”

Usually, create **one complete body** and call `setText` once in the desired form. Subsequent content settings may replace the earlier structure, and do not mean appending a paragraph.

## 17. Practice questions

**Question 1.** Which is the appropriate call for an email containing only plain text?

~~~java
helper.setText("Hello there.", false);
~~~

`setText("Hello there.")` is also suitable. There is no need to use `true` if you do not want HTML.

**Question 2.** To display “Completed” in bold in HTML, what do you write?

~~~java
helper.setText(
        "<p>It is <strong>completed</strong>.</p>",
        true
);
~~~

The HTML snippet is passed as the body, while the Subject is still set with `setSubject(...)`.

**Question 3.** You have equivalent plain text and HTML. Should you call `setText(plain)` and then `setText(html, true)` to create an alternative?

**No.** Create a multipart helper and call `setText(plainText, htmlText)` to represent the two content forms in the same message.

**Question 4.** Is `new MimeMessageHelper(message, true, "UTF-8")` setting an HTML body?

**No.** The `true` here requests multipart mode; you must call `setText(html, true)` to declare an HTML body.

**Question 5.** The Subject string is `"Đặt lịch thành công ✅"`. Do you need to Base64-encode it yourself before calling `setSubject`?

**No.** Put the original Unicode string into the helper with an appropriate charset; the library handles header encoding.

**Question 6.** Someone sends an email with an HTML body containing a customer name taken from a form. Does `setText(html, true)` automatically escape the user's name?

**No.** You need to escape dynamic data by HTML context in the template-creation layer; the helper only sets the content and the MIME type.

**Question 7.** `message.getContentType()` returns `multipart/mixed`. Does that mean the content contains no HTML?

**No.** HTML can sit inside a child MIME part. You need to understand the multipart structure instead of only checking the outer-level Content-Type.

**Question 8.** `mailSender.send(message)` returns without reporting an error. Does that prove the recipient opened the mail?

**No.** This is the result of the sending step to the SMTP relay, not evidence that the recipient opened the email.

## 18. A mnemonic model

When using `MimeMessageHelper` to set the Subject and Text, you can remember the process:

~~~mermaid
flowchart TD
    A["Create MimeMessage"] --> B["Create MimeMessageHelper with UTF-8"]
    B --> C["Set From, To, Subject"]
    C --> D{"Which format does the content need?"}
    D -->|"Plain text only"| E["setText(text)"]
    D -->|"HTML only"| F["setText(html, true)"]
    D -->|"Plain + HTML"| G["Multipart + setText(plain, html)"]
    E --> H["JavaMailSender.send(message)"]
    F --> H
    G --> H
~~~

The four most important ideas:

1. **`setSubject(String)` sets the subject header**, does not set the body, and should not receive a raw `Subject: ...` string.
2. **`setText(String)` or `setText(text, false)` sets plain text**; **`setText(html, true)` sets HTML**.
3. **`setText(plainText, htmlText)` creates two ways of presenting the same content** and needs a helper with an appropriate multipart structure.
4. **UTF-8, dynamic-data checking, and security are necessary responsibilities**, but they do not change the meaning of the APIs that set the Subject/Text.

With a Spring Boot application, the business code should prepare the subject and the content to display as Java strings, validate the source data, choose the `setText(...)` overload by content type, and then let `MimeMessageHelper` and Jakarta Mail create the MIME message. After that, `JavaMailSender` takes charge of sending through the configured SMTP.
