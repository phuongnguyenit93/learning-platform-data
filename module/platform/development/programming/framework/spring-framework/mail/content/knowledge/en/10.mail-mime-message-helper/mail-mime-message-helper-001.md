# Initializing MimeMessageHelper with a message and an encoding

## 1. The role of MimeMessageHelper in Spring Framework Mail

When a Spring application sends an email, the `jakarta.mail.internet.MimeMessage` object represents the email message at the Jakarta Mail layer: it holds the headers, addresses, subject, content, and MIME structure. A developer can manipulate the `MimeMessage` directly, but creating an email with HTML, Unicode characters, multiple recipients, inline images, or attachments requires many detailed operations.

**`org.springframework.mail.javamail.MimeMessageHelper`** is a Spring Framework helper class intended to simplify **composing an existing `MimeMessage`**, especially managing characters, setting common fields, and building multipart structures. The helper **does not create an SMTP server and does not send mail by itself**. The common path is:

~~~mermaid
flowchart LR
    A["JavaMailSender"] -->|"createMimeMessage()"| B["MimeMessage"]
    B --> C["new MimeMessageHelper(message, encoding)"]
    C --> D["setFrom / setTo / setSubject / setText"]
    D --> E["JavaMailSender.send(message)"]
    E --> F["Jakarta Mail / SMTP transport"]
~~~

Two parameters need to be understood right from the start:

1. **`message`**: the very `MimeMessage` object that the helper will modify. The helper works on the object passed in; it does not create a separate email and then automatically synchronize it back to another message.
2. **`encoding`**: the name of the character encoding used when the helper creates the relevant content or header text, usually **`UTF-8`** to represent Vietnamese and many other languages.

A minimal example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Thông báo: Báo cáo tuần");
helper.setText("Chào Lan, báo cáo tuần đã sẵn sàng.", false);

mailSender.send(message);
~~~

The code assumes it sits in a method that handles or declares `MessagingException`, and that the `mailSender` variable has type `JavaMailSender`. Note that the **`mailSender.send(message)` call sends exactly the object that was passed to the helper**.

> **Remember:** `new MimeMessageHelper(message, "UTF-8")` only creates a mail-composing tool attached to `message` and chooses the character encoding; you must assign the mail information and then call the sending API before any email is actually sent.

## 2. Create the MimeMessage first, then create the helper

A typical Spring service depends on the `JavaMailSender` interface:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
~~~

`JavaMailSender.createMimeMessage()` provides a `MimeMessage` that fits the sender being configured. With the common `JavaMailSenderImpl` implementation, the message is created based on the sender's Jakarta Mail `Session` and may carry relevant default information such as the encoding.

You should use the message created by the sender because:

- **Correct context**: the email is built in the context of the mail sender configured for the application.
- **Convenient defaults**: the sender can supply a default encoding and some information for the helper.
- **Clear lifecycle**: each compose/send round has its own message; the service does not need to manage a Jakarta Mail `Session` itself just to send.
- **Easy to replace in tests**: the service depends on `JavaMailSender`, so it can be tested with a fake sender that creates valid messages.

You can create a `MimeMessage` directly from a Jakarta Mail `Session` in specific situations, but for a Spring application that uses `JavaMailSender`, the approach above avoids having two parallel sources of configuration.

### 2.1. Do not confuse the message with the helper

Consider this example:

~~~java
MimeMessage first = mailSender.createMimeMessage();
MimeMessage second = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(first, "UTF-8");
helper.setTo("lan@example.net");
helper.setText("Content of first", false);

mailSender.send(second); // Does not send the content just assigned to first.
~~~

The helper only modifies `first`; `second` is still a different message. Sending `second` cannot automatically pick up the fields assigned to `first`. Therefore, name variables clearly and send exactly the message that is being built.

### 2.2. One helper can be used across multiple composing operations

After initialization, the same helper can set, one after another:

~~~java
helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setCc("team@example.net");
helper.setReplyTo("support@example.com");
helper.setSubject("Monthly report");
helper.setText("Report content...", false);
~~~

These calls modify the **same `MimeMessage` object** in memory. They do not correspond to individual SMTP commands being sent as soon as a setter is called. The SMTP protocol is carried out at the sending stage.

You should not share a `MimeMessage` or a `MimeMessageHelper` that is being modified between multiple concurrent requests/threads. Each time you compose a new email, create a **separate message and helper** to avoid situations where headers/recipients/content get mixed up.

## 3. The constructors of MimeMessageHelper

Spring provides several constructors for choosing the **encoding** and the **multipart mode**. The commonly used forms:

~~~java
new MimeMessageHelper(message);
new MimeMessageHelper(message, "UTF-8");

new MimeMessageHelper(message, false);
new MimeMessageHelper(message, false, "UTF-8");

new MimeMessageHelper(message, true);
new MimeMessageHelper(message, true, "UTF-8");

new MimeMessageHelper(message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED);
new MimeMessageHelper(message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

Note: the constructors that enable multipart may declare `MessagingException` because setting up the MIME structure requires operating on the message.

| Constructor | Explicit encoding? | Choose multipart? | Suitable for |
| --- | --- | --- | --- |
| `MimeMessageHelper(message)` | No | No | Composing simple content when the defaults are already suitable |
| `MimeMessageHelper(message, encoding)` | Yes | No | Simple text/HTML that needs a controllable charset |
| `MimeMessageHelper(message, multipart)` | No | Boolean flag | Composing mail with or without multiple MIME parts |
| `MimeMessageHelper(message, multipart, encoding)` | Yes | Boolean flag | Unicode mail that may need HTML/attachments/inline resources |
| `MimeMessageHelper(message, multipartMode)` | No | Specific mode | Controlling the shape of the MIME tree |
| `MimeMessageHelper(message, multipartMode, encoding)` | Yes | Specific mode | Controlling both the MIME tree and the charset |

In the table, `encoding` is a `String` such as `"UTF-8"`. `multipart` is a `boolean`; `multipartMode` is an `int` constant of `MimeMessageHelper`. Do not confuse:

~~~java
new MimeMessageHelper(message, true, "UTF-8");   // boolean
new MimeMessageHelper(message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");                                 // int mode
~~~

Both constructors allow building multiple parts, but the form with a mode makes the **desired structure** explicit when the mail contains both inline resources and attachments.

### 3.1. Constructor with an encoding but without enabling multipart

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
~~~

Here the helper uses the specified encoding and **does not initialize a multipart tree by itself**. It suits the case where you need only a single text or HTML body:

~~~java
helper.setSubject("Registration confirmed");
helper.setText("<p>Hello, registration <strong>succeeded</strong>.</p>", true);
~~~

The `true` in `setText(..., true)` means **HTML content**, not enabling multipart. The two concepts are different:

- **HTML** determines the body type `text/html`.
- **Multipart** allows the message to organize multiple parts, for example text and HTML coexisting, or a body accompanied by attachments.

If you want to call `addAttachment(...)` or `addInline(...)`, choose a constructor that enables multipart from the start.

### 3.2. Boolean constructor and encoding

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

`multipart=true` activates the multipart structure in the default mode that the Spring helper uses when this flag is enabled. `encoding="UTF-8"` instructs the helper when writing text content and the subject. This form is convenient when you do not need to specify the mode in detail.

For complex mail, you can write it explicitly:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

The `MIXED_RELATED` mode is usually suitable when the body has images referenced by Content-ID while the mail also has separate attachments. This relates to **how the MIME tree is organized**, while `"UTF-8"` is still the choice of character encoding for the text content.

## 4. What is encoding and which components does it affect?

Computers store and transmit data as bytes; a character such as “á”, “Đ”, or “✓” must be encoded into bytes according to a **character encoding**. In email, text content may additionally have a **Content-Transfer-Encoding** layer so that those bytes are carried in a form suitable for MIME.

An example body:

~~~text
Chào bạn, tài khoản đã được kích hoạt.
~~~

When it is set with:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setText("Chào bạn, tài khoản đã được kích hoạt.", false);
~~~

the helper uses UTF-8 to create the text content. A MIME part may carry headers such as:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Or it may use `base64` or another transfer encoding, depending on the library and the content. **UTF-8 is not a Content-Transfer-Encoding**. When reading the mail, the client decodes the transfer-encoding layer, then interprets the bytes according to the charset to recover the characters.

### 4.1. Three easily confused concepts

| Concept | Example | Responsibility |
| --- | --- | --- |
| **Charset** | `UTF-8` | Converts text characters to bytes and back |
| **MIME Content-Type** | `text/plain`, `text/html` | Indicates what kind of content the part contains |
| **Content-Transfer-Encoding** | `quoted-printable`, `base64` | Represents the bytes on the MIME transport |

A mail that has:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: base64
~~~

is not so because the email is “written in base64”, but because the bytes of the UTF-8 HTML are converted to base64 for transport. The email client will decode the base64 and then use UTF-8 to display the HTML.

### 4.2. UTF-8 does not make everything Unicode automatically

`"UTF-8"` in the constructor helps with **text content and the headers that the helper encodes appropriately**, but it does not solve every problem:

- **Email addresses with international characters** may need the `SMTPUTF8` SMTP extension. The body's charset does not by itself grant support for such addresses.
- **Binary attachments** such as PDF/PNG are not “converted to UTF-8”; they use their own MIME content type and transfer encoding.
- **Attachment filenames** have their own header-encoding rules; you need to observe the real message and check mail client compatibility.
- **HTML rendering** also depends on the HTML/CSS supported by the client, not just the charset.
- **Input data that was already corrupted before the mail was built** cannot be fixed by changing the encoding in the helper.

### 4.3. Charset of the subject and body

`MimeMessageHelper.setSubject(...)` can use the helper's encoding to create a subject containing Unicode:

~~~java
helper.setSubject("Xác nhận đơn hàng: Đã hoàn tất");
~~~

When the message is serialized, the subject may appear as a MIME **encoded-word** following the corresponding rules. The recipient sees the Vietnamese string, while the raw header may contain encoding notation. You should not create an encoded-word yourself and then pass it into `setSubject(...)`, because there is a risk of double encoding.

Similarly:

~~~java
helper.setText("Đơn hàng của bạn đã được xác nhận.", false);
~~~

is a call for a text body. The encoding is applied when the library builds the part's content. If you set both plain and HTML, each text part must also have a reasonable charset:

~~~java
helper.setText(
        "Đơn hàng đã được xác nhận.",
        "<p>Đơn hàng đã <strong>được xác nhận</strong>.</p>");
~~~

The `setText(plain, html)` example is used with a helper in multipart mode; it creates two versions of the content following `multipart/alternative` semantics.

## 5. Should you always pass "UTF-8" in the constructor?

**Specifying UTF-8 explicitly** is usually a reasonable choice for content in Vietnamese and for systems that need predictable results. For example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

Developers can also rely on the **mail sender's default encoding** configured centrally. For Spring's `JavaMailSenderImpl`, `setDefaultEncoding("UTF-8")` specifies the default encoding for the messages it creates. `MimeMessageHelper` can detect this default when using a message created by the sender.

For example in a **Spring Boot** application:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    default-encoding: UTF-8
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

This is a structural configuration; the credentials, sender address, TLS policy, and provider must be supplied from the actual deployment environment. `spring.mail.default-encoding` is a Spring Boot property that supports the auto-configured sender, which is different from configuring `MimeMessageHelper` directly in code.

When using Spring Framework without relying on Boot, you can configure the bean:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.net");
sender.setPort(587);
sender.setDefaultEncoding("UTF-8");
// Add authentication, TLS, and timeouts according to system requirements.
~~~

Do not interpret `setDefaultEncoding("UTF-8")` as configuring the SMTP server's encoding; it is the default used during message construction.

### 5.1. When no encoding is passed

~~~java
MimeMessageHelper helper = new MimeMessageHelper(message);
~~~

If the message was created by `JavaMailSenderImpl` with a recognizable default encoding, the helper can use that default. For a message created by hand from a Jakarta Mail `Session` or in a default environment that has not been configured, the effective encoding may depend on the rules of the library/runtime.

The point to remember is that **you should not rely on a vague “default UTF-8”** when the system needs to send multilingual content reliably across environments. You can pass the encoding to the constructor or establish an explicit sender default, and then inspect the serialized mail.

### 5.2. When to configure globally and when to specify locally?

| Situation | How to choose the encoding |
| --- | --- |
| All of the application's emails use Unicode/UTF-8 | Configure `JavaMailSenderImpl.setDefaultEncoding("UTF-8")` or `spring.mail.default-encoding` |
| A mailer wants to declare the charset explicitly in place | `new MimeMessageHelper(message, "UTF-8")` |
| Mail has multipart and needs a clear charset | `new MimeMessageHelper(message, true, "UTF-8")` or a constructor with a mode |
| The system receives source messages that already use a different charset | Distinguish parsing an existing message from creating a new one; avoid changing the charset arbitrarily |
| Email contains only binary resources | The helper's charset does not turn a binary attachment into text; use the appropriate MIME type and attachment API |

When choosing an encoding, keep a consistent convention across the system to make inspection easier. If one method uses UTF-8 and another omits the encoding, this can create differences that are hard to detect if the sender default is not clearly managed.

## 6. Complete example: initializing the helper for a Vietnamese text email

A Spring Framework service can be written as:

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailer {

    private final JavaMailSender mailSender;

    public RegistrationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name());

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn đến với hệ thống");
        helper.setText(
                "Xin chào!\nTài khoản của bạn đã được kích hoạt.",
                false);

        mailSender.send(message);
    }
}
~~~

The main components:

1. **`JavaMailSender`** is injected through the constructor. The SMTP configuration belongs to the Spring configuration, not to the code that sends the content.
2. **`createMimeMessage()`** provides a new message for the current send.
3. **`new MimeMessageHelper(message, false, UTF_8)`** initializes a **non-multipart** helper with an explicitly stated encoding. `StandardCharsets.UTF_8.name()` returns the charset name `"UTF-8"`.
4. **`setFrom`, `setTo`, `setSubject`, `setText`** set the headers and body on the message.
5. **`mailSender.send(message)`** triggers the transport to send that very object.

In the example, `recipient` is data that has already been validated and authorized by the calling layer. Production code needs to use a `From` address that the SMTP provider allows; do not let unauthenticated users freely choose the sending identity.

### 6.1. Why does the constructor use false?

This email has only a single `text/plain` body. There is no need to build a `multipart/mixed` or `multipart/related` structure to hold additional parts. Choosing `false` makes the intent clear: a single text message is being sent.

If you later want plain text **and** HTML, or to add a PDF, you can change the choice when initializing the helper to enable multipart, and then add the appropriate parts. You should not sneak in an attachment after you have already decided on non-multipart mode.

### 6.2. Why use StandardCharsets.UTF_8.name()?

Both ways express the same charset:

~~~java
new MimeMessageHelper(message, false, "UTF-8");
new MimeMessageHelper(message, false,
        StandardCharsets.UTF_8.name());
~~~

Using `StandardCharsets.UTF_8.name()` avoids mistyping the charset name and takes advantage of the standard Java constant. This constructor takes an encoding **`String`**; do not pass `StandardCharsets.UTF_8` directly, because that is a `Charset` object, not a `String`.

## 7. Example: a helper with an encoding and two text/HTML versions

Transactional email often has attractive HTML but still provides a plain-text version for recipients who do not use HTML:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("lan@example.net");
helper.setSubject("November invoice");

String plain = "The November invoice is ready.";
String html = "<p>The November invoice is "
        + "<strong>ready</strong>.</p>";

helper.setText(plain, html);
mailSender.send(message);
~~~

When `setText(plain, html)` is called on a multipart helper, Spring creates parts that carry the meaning of **alternative versions of the same content**. The general form:

~~~text
MimeMessage
└── multipart/...
    └── multipart/alternative
        ├── text/plain; charset=UTF-8
        └── text/html; charset=UTF-8
~~~

The outer containers may differ depending on the multipart mode in use. The important points are:

- `text/plain` and `text/html` are two ways of presenting the same information.
- The charset must be appropriate for **each text part**.
- The email client decides which version is displayed according to its capabilities and policy.
- The HTML must contain content that has been properly escaped/sanitized if untrusted data is inserted.

Compare with:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
helper.setText("<p>Hello!</p>", true);
~~~

This call creates **a single HTML version**, and the `true` parameter in `setText` does not enable multipart. When you need only one HTML body and no text version or attachments, this can be entirely appropriate.

## 8. Example: a helper with a mode, UTF-8, an inline image, and a PDF

When an email has an embedded image referenced from the HTML and an attachment, you should choose a MIME structure that has a clear relationship among the body, the inline resource, and the standalone file.

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailer {

    private final JavaMailSender mailSender;

    public InvoiceMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            Resource logoPng,
            Resource invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your electronic invoice");

        String plain = "The invoice is ready; please see the PDF.";
        String html = "<p>The invoice is <strong>ready</strong>.</p>"
                + "<img src=\"cid:company-logo\" alt=\"Logo\">"
                + "<p>Please see the attached PDF file.</p>";

        // Create the body before adding inline resources.
        helper.setText(plain, html);
        helper.addInline("company-logo", logoPng, "image/png");
        helper.addAttachment("invoice.pdf", invoicePdf);

        mailSender.send(message);
    }
}
~~~

This example shows **two independent choices** in the constructor:

- `MULTIPART_MODE_MIXED_RELATED` chooses how the MIME is organized: the body and the inline image are related to each other; the PDF is a standalone attachment.
- `UTF-8` chooses the encoding used for the text/subject created by the helper.

A typical tree might be:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   │       <img src="cid:company-logo">
    │   └── image/png
    │       Content-ID: <company-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

This is an illustrative tree for the common mode; you need to inspect the real message to know the specific structure produced by the library in your application.

**Points to note:**

1. **`setText(plain, html)` before `addInline(...)`**: Spring recommends setting the body part before adding inline images so that the resources are placed in the appropriate MIME relationship.
2. **Matching CIDs**: `cid:company-logo` in the HTML must correspond to the ID `company-logo` passed to `addInline(...)`.
3. **Readable resources**: the logo and the PDF must come from authorized sources; avoid putting internal paths specified by users into the email.
4. **Stream sources that can be reopened when needed**: Jakarta Mail may need to read the content during serialization; an `InputStreamSource` that cannot be reopened can easily cause errors.
5. **Do not turn binary into text**: the `"UTF-8"` parameter does not change the nature of the PDF/PNG bytes; each attachment has its own MIME content type and transfer encoding.
6. **Size limits**: the SMTP provider may set a limit on the total size of the email after MIME encoding, which is larger than the size of the original files.

### 8.1. When is the true constructor enough?

If you are adding only one PDF:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText("The report is ready.", false);
helper.addAttachment("report.pdf", reportResource);
~~~

The boolean form may be enough for many applications. But when you need clear control over the relationship between inline resources and attachments across mail clients, choosing a specific mode is usually easier to explain and verify.

### 8.2. Common multipart modes

| Mode | Main organization | Case to consider |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Does not use multipart to add resources | Simple email body |
| `MULTIPART_MODE_MIXED` | Groups multiple parts under `multipart/mixed` | Combining body/attachments; inline support may differ by client |
| `MULTIPART_MODE_RELATED` | Groups related parts under `multipart/related` | HTML with related resources |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` on the outside, `related` for the body and inline resources on the inside | Email with both inline images and attachments |

Choosing the right mode is a decision about **message structure**, not a decision about charset. An email can use UTF-8 without multipart, or have a complex multipart structure in which each text part must still specify an appropriate charset.

## 9. Mistakes that are easy to make right when initializing the helper

### 9.1. Passing the wrong message

~~~java
MimeMessage messageA = mailSender.createMimeMessage();
MimeMessage messageB = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(messageA, "UTF-8");

helper.setTo("lan@example.net");
helper.setText("Content A", false);
mailSender.send(messageB);
~~~

The mistake is **sending messageB** while the helper is composing on messageA. Keep one message variable per send and use that variable consistently.

### 9.2. Forgetting to enable multipart before adding an attachment

~~~java
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");
helper.setText("The report is attached.", false);
helper.addAttachment("report.pdf", reportResource);
~~~

The helper was initialized as non-multipart, so the operation of adding an attachment requires a structure that it does not have. You need to choose a multipart constructor from the start:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

Do not interpret `helper.setText(html, true)` as having enabled multipart. The `true` in that method only marks the content as HTML.

### 9.3. Omitting the encoding and relying on the environment

A system that works correctly on a developer's machine but shows broken Vietnamese text in another runtime may have a problem with the input charset, the default encoding, or the serialized data. Specifying UTF-8 explicitly or configuring the sender default helps reduce variables, but you still need to check whether the source data was **already correct before the message was created**.

If the input body is already the string `"ChÃ o"` instead of `"Chào"`, switching to `new MimeMessageHelper(message, "UTF-8")` does not automatically fix a Java string that is already corrupted.

### 9.4. Creating the helper before there is a valid message

The helper needs a real `MimeMessage`. In a test, if you mock `JavaMailSender.createMimeMessage()` to return `null`, initializing or calling the helper cannot work normally.

When testing code that builds mail, you should provide a valid message through a fake sender or a configured mock:

~~~java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
// When mocking createMimeMessage(), return this valid message.
~~~

The example snippet needs to import `jakarta.mail.Session`, `jakarta.mail.internet.MimeMessage`, and `java.util.Properties`. It is only an example of creating a standalone message for **testing**, and does not require an SMTP connection.

### 9.5. Creating a new message to fix the encoding of an existing mail

Suppose the application reads a received email whose text part declares a different charset. Initializing `MimeMessageHelper(existingMessage, "UTF-8")` only configures the **helper's subsequent content-assigning operations**; it does not automatically convert all the bytes already present in the old parts to UTF-8. To normalize an existing mail, you must understand the source content and how it is parsed/serialized, and avoid overwriting the charset in a way that loses data.

### 9.6. Using an encoding with a wrong name

~~~java
new MimeMessageHelper(message, "UTF_8"); // Not the standard name you should use.
~~~

You should use `"UTF-8"` or `StandardCharsets.UTF_8.name()`. If the charset is not supported, an error may appear when the helper or Jakarta Mail applies the encoding to the header/body, depending on the operation being performed.

## 10. Where can encoding errors appear?

| Symptom | Where to check | Possible explanation |
| --- | --- | --- |
| The subject shows `=?UTF-8?...?=` characters in the client | The raw `Subject` header and the client parser | The encoded-word header is displayed as raw text or is double-encoded |
| A Vietnamese body turns into garbage characters | Input bytes, `Content-Type; charset`, Content-Transfer-Encoding | The content is decoded with a different encoding from the one that was used |
| HTML appears as text tags | `setText(text, isHtml)` and `Content-Type` | `isHtml=false` was set for HTML content |
| Only plain is shown despite having HTML | The `multipart/alternative` tree, part order, and client policy | The alternative is incorrect or the client chooses the plain version |
| Inline image is broken | `cid:...`, `Content-ID`, `multipart/related` | The resource does not match the reference or the client does not support it |
| The PDF name has character errors | The attachment's filename header, filename encoding | Filenames have their own header-encoding rules |
| UTF-8 is correct locally but wrong in production | Sender default, config, and template data | The environment uses a different data source or encoding |

An important difference: an **SMTP transport error** such as `MailAuthenticationException` or `SocketTimeoutException` cannot be fixed just by changing the constructor's encoding. Conversely, if SMTP returns success but the mail displays incorrectly, you need to inspect the MIME tree and the real data, which is not necessarily related to the network connection.

## 11. Observing the MimeMessage after using the helper

Because the constructor takes `message`, the application still holds the very object being composed and can serialize it to observe the MIME before sending. In a controlled test environment:

~~~java
package com.example.mail;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class MimePreview {

    private final JavaMailSender mailSender;

    public MimePreview(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void exportSample(Path destination)
            throws IOException, MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo("test-recipient@example.net");
        helper.setSubject("Báo cáo: Đã sẵn sàng");
        helper.setText("Xin chào, báo cáo đã được tạo.", false);

        message.saveChanges();
        try (OutputStream output = Files.newOutputStream(destination)) {
            message.writeTo(output);
        }
    }
}
~~~

This method **has not sent an email** because it does not call `mailSender.send(message)`. It only writes the message to an `.eml` file so that you can view the structure.

A header form you may encounter:

~~~text
From: reports@example.com
To: test-recipient@example.net
Subject: =?UTF-8?...?=
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

[Body encoded according to Content-Transfer-Encoding if needed]
~~~

This is an **abbreviated example**, not a complete raw email to be sent out. The real headers, the form of the encoded-word subject, and the specific transfer encoding are decided by Jakarta Mail.

For multipart mail, the root may carry `Content-Type: multipart/mixed` and **have no `charset=UTF-8` at the root**. The charset sits on the inner `text/plain`/`text/html` parts. When diagnosing, you must walk the parts rather than only look at the `Content-Type` of the root message.

### 11.1. If the received email still displays incorrectly

Distinguish four layers of data:

1. **Java String before it is put into the helper**: are the Vietnamese characters already correct?
2. **MimeMessage after serialization**: are the Content-Type, charset, and body data appropriate?
3. **The real email in the receiving mailbox**: did a gateway or intermediary service change the body/headers?
4. **The mail reader**: does the client filter HTML or remote images, or have a different way of decoding?

If the plain/HTML versions are in the wrong order within `multipart/alternative`, changing the encoding cannot fix the MIME tree. If the tree is correct but the body bytes do not match the charset, you need to go back to the source data and how the helper is used.

Exporting `.eml` should only be done with simulated data or in an authorized environment; real email may contain personal information, sensitive URLs, and attachments that have not been published.

## 12. Combining with environment-specific Spring Boot configuration

An application running locally, in staging, and in production can use the same mail-composing code:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

Meanwhile, the SMTP configuration lives in property sources and Spring profiles. An example of the shared configuration:

~~~yaml
# application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

An example of a local environment using an isolated SMTP sink:

~~~yaml
# application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
~~~

An example of production using SMTP submission with STARTTLS:

~~~yaml
# application-prod.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
~~~

The placeholders are taken from the environment or an appropriate secret source; do not commit real passwords to the repository. A local SMTP sink without auth/TLS is only suitable for an isolated test network. Sending through a real provider requires TLS, authentication, and sending permissions appropriate to the service.

In this example:

- `spring.mail.default-encoding=UTF-8` sets the **default for the sender**.
- `new MimeMessageHelper(message, false, "UTF-8")` declares the charset **at the place where the mail is composed**.
- `spring.mail.host`, `port`, and the SMTP properties decide **where and how the mail is sent**, not the body's charset.

When the helper has received an explicit encoding, the sending code does not need to read the active profile to decide the encoding itself. If all environments need consistent Vietnamese content, this approach avoids depending on unclear defaults.

## 13. Misconceptions to avoid

**“Does MimeMessageHelper create a new email?”**  
The helper is a support object that **modifies the `MimeMessage` passed to it**. The message is usually created beforehand through `JavaMailSender.createMimeMessage()`.

**“I called new MimeMessageHelper, so has the mail been sent?”**  
No. The constructors and setters only prepare the email. You need to call `JavaMailSender.send(message)` to send.

**“Does the true parameter in the constructor mean HTML?”**  
No. In `new MimeMessageHelper(message, true, "UTF-8")`, `true` means **multipart**. In `helper.setText(body, true)`, `true` means **HTML**.

**“Is multipart required if I want HTML?”**  
No. A single HTML email can use `new MimeMessageHelper(message, "UTF-8")` and `setText(html, true)`. Multipart is needed when combining parts such as text/HTML alternatives, inline images, or attachments.

**“Will setting UTF-8 encode images and PDFs as text as well?”**  
No. Binary content has its own MIME/transfer-encoding mechanism. `UTF-8` in the helper mainly serves the text fields that the helper creates.

**“Does UTF-8 allow every Unicode email address?”**  
No. International email addresses may need the `SMTPUTF8` SMTP extension and a supporting provider; the charset of the subject/body is a different matter.

**“Does changing the encoding automatically fix a message that was created with the wrong charset?”**  
No. Creating a new helper with a different encoding does not safely convert all the old parts automatically. You need to handle the source data correctly and rebuild the content if necessary.

**“Does MimeMessageHelper(message) always use UTF-8?”**  
You should not assume so without knowing the sender default and the Jakarta Mail runtime. You can pass `UTF-8` explicitly or configure a controlled default encoding.

**“Why does the MIME root not state UTF-8?”**  
In multipart email, the charset is usually declared on the child text parts. The root holds the container type such as `multipart/mixed` or `multipart/related`.

## 14. Which constructor for which need?

| Need | Constructor that usually fits | Content-creating API |
| --- | --- | --- |
| Vietnamese plain-text email | `new MimeMessageHelper(message, false, "UTF-8")` | `setText(text, false)` |
| Simple HTML email | `new MimeMessageHelper(message, "UTF-8")` | `setText(html, true)` |
| Email with plain and HTML | `new MimeMessageHelper(message, true, "UTF-8")` | `setText(plain, html)` |
| Email with a PDF | `new MimeMessageHelper(message, true, "UTF-8")` | `setText(...)` and `addAttachment(...)` |
| HTML with a CID image and a PDF | `new MimeMessageHelper(message, MULTIPART_MODE_MIXED_RELATED, "UTF-8")` | `setText(plain, html)`, `addInline(...)`, `addAttachment(...)` |
| Sender with a centrally managed default encoding | `new MimeMessageHelper(message)` or a constructor with a mode | The appropriate setters; determine the sender default first |

For most services that send plain-text email, the initialization pattern can be written as:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Thông báo mới");
helper.setText("Nội dung tiếng Việt được tạo bằng UTF-8.", false);

mailSender.send(message);
~~~

When multiple MIME parts are needed, choose a constructor that enables multipart and use an appropriate mode. In every case, **`message` must be the object that will be sent**, while `encoding` should be an explicit charset for the text content. Understanding these two parameters correctly, together with the multipart mode, helps avoid character errors, avoid sending the wrong object, and safely extend from a single text email to HTML, inline images, or attachments.
