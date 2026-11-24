# Character encoding in subject and body

## 1. The problem: the email sends, yet Vietnamese text is garbled

In **Spring Framework Mail**, applications usually use **JavaMailSender** and **MimeMessageHelper** to send emails with Vietnamese text, HTML, special characters, and emoji. An email may be accepted by the SMTP server, yet when opened in an email client, errors such as these appear:

- The intended subject **“Xác nhận đơn hàng”** becomes unreadable characters or question marks.
- The subject displays correctly, yet the body becomes **“ChÃ o”** or replacement characters.
- The HTML body displays Vietnamese properly, yet the text/plain part has corrupted diacritics.
- The email looks right in the application's preview UI, yet the copy received in Outlook or Gmail differs.
- The sender name or attachment filename is garbled even though the subject and message content are fine.

This is not necessarily an SMTP bug. Email has **different encoding rules for headers and body**; with HTML, you must also distinguish **HTML escaping** from **character encoding**. To send accurately, you need to understand each layer.

The goal of this lesson is to build emails with Subject, text, and HTML containing valid Unicode in Spring Mail; understand the MIME structure on the wire; and systematically inspect and fix charset mismatches.

## 2. Three character-transformation layers to distinguish

A string in Java:

~~~java
String subject = "Xác nhận đơn hàng số 123";
String html = "<p>Xin chào, cảm ơn bạn! ✅</p>";
~~~

is represented as a **Java String**, made of UTF-16 code units in memory. When building an email, Jakarta Mail needs to convert characters into bytes and MIME structure. The email client decodes this structure to display the characters again.

~~~text
Java String Unicode
  |
  +-- Subject / display name (header)
  |      |
  |      +--> MIME header encoding
  |             (usually using RFC 2047 encoded-word)
  |
  +-- text/plain / text/html (body)
         |
         +--> Character encoding: UTF-8
         |
         +--> Content-Transfer-Encoding:
                quoted-printable or Base64 or another mechanism
~~~

If the content is HTML, user data also passes through an **HTML escaping** step before being inserted into the template:

~~~text
User input -> escape HTML -> Java String containing HTML
    -> encode UTF-8 -> MIME transfer encoding
    -> email client decode -> render HTML
~~~

| Concept | What does it solve? | Example |
|---|---|---|
| **Character encoding / charset** | Maps Unicode characters to bytes and back | UTF-8 |
| **MIME header encoding** | Represents Unicode in email headers in a compatible way | Encoded-word like =?UTF-8?B?...?= |
| **Content-Transfer-Encoding** | Represents body bytes for safe transport over email | quoted-printable, base64 |
| **HTML escaping** | Prevents user text from being interpreted as HTML syntax | `<` to `&lt;`, `&` to `&amp;` |

**UTF-8 is not Base64. Base64 is not security encryption. HTML escaping does not replace UTF-8.** The mechanisms solve different layers of the message.

## 3. Subject is a header, not an HTML body

**Subject** belongs to the email **header**. In traditional MIME, when the subject contains Unicode, the library usually represents it using an **encoded-word** per RFC 2047. General syntax:

~~~text
=?charset?encoding?encoded-text?=
~~~

Where:

- **charset**: how characters are turned into bytes, usually UTF-8.
- **encoding**: usually B (Base64) or Q (an encoding mechanism similar to quoted-printable for headers).
- **encoded-text**: content transformed according to the encoding.

For example, the word **Café** may appear on the wire as:

~~~text
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

or:

~~~text
Subject: =?UTF-8?Q?Caf=C3=A9?=
~~~

Both forms represent the word **Café**; the client decodes the header and then displays it to the user. A long Subject may be split into multiple encoded-words and header-folded according to MIME rules. Seeing multiple `=?UTF-8?...?=` segments in raw headers **does not mean there is an error**.

### How do B and Q differ?

| Mechanism | Representation | Characteristics |
|---|---|---|
| **B** | Charset bytes encoded as Base64 | Suitable for subjects with many non-ASCII characters |
| **Q** | Some bytes represented as =HH, space may be _ | Can be easier to read in mostly ASCII raw headers |

**Q-encoding in RFC 2047 is not completely identical to body quoted-printable**. In Q-style encoded-words, an underscore can carry the meaning of a space; the rules applying to headers differ from the body. Do not take HTML escaping or body quoted-printable yourself to encode the Subject.

### How to do it with Spring Mail

**Pass a normal Unicode Java String to MimeMessageHelper.setSubject(...)** and supply the UTF-8 charset. Jakarta Mail is responsible for serializing the header appropriately.

~~~java
helper.setSubject("Xác nhận đơn hàng – cảm ơn bạn ✅");
~~~

There is no need to convert the Subject to Base64 yourself, no need to assemble `=?UTF-8?B?...?=` yourself, and **do not encode the Subject with one helper and then pass it through an API that may encode it again**. Encoding twice can make the recipient see the literal encoded-word string instead of the subject.

## 4. Body uses charset and Content-Transfer-Encoding

The body does not use header encoded-words for the entire content. Each MIME body part can declare:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

**Content-Type** supplies the media type and charset. **Content-Transfer-Encoding** describes how the body's bytes are represented for transport. The email client decodes transfer encoding **first**, then uses the charset to produce Unicode.

~~~mermaid
flowchart LR
    A[Java String] --> B[UTF-8 bytes]
    B --> C[Quoted-printable or Base64]
    C --> D[MIME text/html part]
    D --> E[Decode transfer encoding]
    E --> F[Decode UTF-8]
    F --> G[Render HTML]
~~~

Example of a body part using quoted-printable:

~~~mime
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html><body><p>Xin ch=C3=A0o, Caf=C3=A9!</p></body></html>
~~~

The two UTF-8 bytes C3 A0 are represented by =C3=A0, corresponding to the character **à**. C3 A9 represents **é**. The email client needs to decode both transfer encoding and charset to display **“Xin chào, Café!”**.

The library may choose **Base64** instead of quoted-printable. Do not assume every UTF-8 body must use quoted-printable; what matters is that **MIME declares it accurately and the data decodes back accurately**.

### What if the charset does not match the bytes?

If the actual bytes are UTF-8 yet MIME declares charset ISO-8859-1, the recipient may see **“ChÃ o”**. If the data was already replaced with `?` characters before reaching the mail layer, fixing only the MIME header at the end of the pipeline cannot recover the original text.

**The charset must describe how the bytes were actually created**, not merely be a wished-for label.

## 5. HTML meta charset does not replace MIME charset

An HTML template may contain:

~~~html
<!doctype html>
<html lang="vi">
  <head><meta charset="UTF-8"></head>
  <body><p>Chào bạn, cảm ơn đã đăng ký!</p></body>
</html>
~~~

On a web page, meta charset helps the browser understand the source encoding. However, **in MIME email, the body part already has Content-Type and charset**. Email clients may handle meta tags differently; merely adding a meta tag to the HTML body while passing bytes in the wrong charset **is not a reliable fix**.

You should ensure consistency:

1. The Java String holds valid Unicode.
2. MimeMessageHelper uses UTF-8 to build the part.
3. MIME declares text/html; charset=UTF-8 or an equivalent value.
4. Transfer encoding is generated by the library to match the body.
5. If there is a meta charset in HTML, it does not conflict with the MIME charset.

## 6. Configuring UTF-8 in Spring Boot

Spring Boot has the **spring.mail.default-encoding** property to configure the default charset for the JavaMailSender auto-configured by Boot:

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
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Host and port here are illustrative only; credentials must come from the deployment environment or a secret manager. Timeouts are in milliseconds. Having TLS/AUTH on SMTP submission protects the sending path and proves client identity, yet **does not automatically change the charset** of the content.

If creating the sender manually:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.net");
sender.setPort(587);
sender.setDefaultEncoding(StandardCharsets.UTF_8.name());
~~~

In critical code paths, you can pass **UTF-8 explicitly into MimeMessageHelper** to avoid depending on another sender's default encoding. A UTF-8 email configuration does not automatically fix data that was already corrupted earlier in an HTTP request, database, or template engine.

## 7. Sending a Vietnamese Subject and HTML body with MimeMessageHelper

Spring service example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class VietnameseHtmlMailService {
    private final JavaMailSender mailSender;

    public VietnameseHtmlMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmation(
            String recipient,
            String customerName,
            String orderCode) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.net");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode + " ✅");

        String safeName = escapeHtml(customerName);
        String safeCode = escapeHtml(orderCode);

        String html = """
                <!doctype html>
                <html lang="vi">
                  <head><meta charset="UTF-8"></head>
                  <body>
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p>Xin chào, %s!</p>
                    <p>Mã đơn hàng: <strong>%s</strong></p>
                  </body>
                </html>
                """.formatted(safeName, safeCode);

        helper.setText(html, true);
        mailSender.send(message);
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

The example uses Java text blocks and String.formatted (requires a supporting Java version, such as Java 17). Key points:

- **createMimeMessage()** creates an object compatible with the sender.
- **MimeMessageHelper(message, false, "UTF-8")** specifies the encoding; false is suitable for a simple HTML part without attachments.
- **setSubject** accepts Unicode; the library performs header encoding when serializing.
- **setText(html, true)** marks the content as HTML.
- **escapeHtml** processes user data before inserting it into the template; it does not replace UTF-8 or transfer encoding.
- **send()** performs SMTP submission; when the server accepts the message there is still no proof the recipient read it.

When using a template engine such as Thymeleaf, use the template's context-aware escaping instead of concatenating HTML strings. The template must be rendered into a valid Unicode string, then passed to setText(..., true).
## 8. Emails with both text/plain and text/html

An HTML email should usually have a **text/plain** version to support email clients that do not render HTML, screen readers, or content filtering systems. MIME uses **multipart/alternative** to package multiple representations of the same content.

~~~text
multipart/alternative
  |
  +-- text/plain; charset=UTF-8
  |     Content-Transfer-Encoding: ...
  |
  +-- text/html; charset=UTF-8
        Content-Transfer-Encoding: ...
~~~

The two parts may use different transfer encodings, yet should align on **meaningful content** and declare the right charset. For example, the same notification must display Vietnamese text accurately both when the reader selects HTML and when the system shows only plain text.

With **MimeMessageHelper**, you can provide two versions:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class AlternativeBodyMail {
    private final JavaMailSender mailSender;

    public AlternativeBodyMail(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        // Use multipart when creating alternative parts.
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("notifications@example.net");
        helper.setTo(recipient);
        helper.setSubject("Thông báo mới – đơn hàng #123");

        String plain = """
                Xin chào!
                Đơn hàng #123 của bạn đã được xác nhận.
                Cảm ơn bạn đã sử dụng dịch vụ.
                """;

        String html = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <h1>Xin chào!</h1>
                    <p>Đơn hàng <strong>#123</strong>
                       của bạn đã được xác nhận.</p>
                    <p>Cảm ơn bạn đã sử dụng dịch vụ.</p>
                  </body>
                </html>
                """;

        helper.setText(plain, html);
        mailSender.send(message);
    }
}
~~~

In the example, **setText(plain, html)** represents two versions of the same notification. When built with multipart mode, the helper can organize parts into a **nested multipart structure** suited to the implementation. Do not assume the plain part is at index 0 of the outermost multipart in every case; inspect the actual Content-Type/parts if parsing is needed.

When the email also has **attachments or inline images**, the MIME structure can nest **multipart/mixed**, **multipart/related**, and **multipart/alternative**. Body parts must still have appropriate charset and transfer encoding regardless of how deep they sit in the MIME tree.

### Do not use an HTML string as plain text

This snippet:

~~~java
helper.setText("<p>Xin chào!</p>", false);
~~~

is interpreted as text/plain and the recipient may see the literal HTML tag characters. Conversely:

~~~java
helper.setText("<p>Xin chào!</p>", true);
~~~

marks the body as text/html. The boolean parameter here is the **HTML flag**, not an on/off flag for UTF-8. The charset is supplied separately when constructing the helper.

## 9. SimpleMailMessage and Vietnamese plain text

Not every email needs MimeMessageHelper. When there is only a subject and a text body, **SimpleMailMessage** is usually enough:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class PlainTextMailService {
    private final JavaMailSender sender;

    public PlainTextMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("noreply@example.net");
        mail.setTo(recipient);
        mail.setSubject("Lịch hẹn ngày mai");
        mail.setText("Xin chào! Lịch hẹn của bạn đã được xác nhận.");
        sender.send(mail);
    }
}
~~~

With JavaMailSenderImpl, sending a SimpleMailMessage converts it to an appropriate MIME form before sending over SMTP. When Unicode is needed, there should be a **UTF-8 default encoding** on the sender. If the project uses multiple JavaMailSender beans, ensure the sender actually injected is the properly configured one.

Comparison:

| Scenario | Appropriate approach |
|---|---|
| Short notification text with Vietnamese | SimpleMailMessage and sender default UTF-8 |
| HTML with tags, inline CSS | MimeMessageHelper.setText(html, true) |
| Both text/plain and text/html | MimeMessageHelper.setText(plain, html) in multipart |
| Attachments, inline images, complex MIME structure | MimeMessage with multipart and helper |
| Need fine-grained control over specific headers/parts | Jakarta Mail API with the corresponding MIME rules |

**Having Vietnamese content does not force you to use HTML**. Text/plain with UTF-8 also expresses Vietnamese completely and is often a good choice for short notifications.

## 10. Sender name, addresses, and attachment filenames also have their own encoding

Fixing only Subject/body does not guarantee every part of the email displays properly. Other areas need separate handling:

- **Display name**: the name part shown in From, for example “Bộ phận Chăm sóc khách hàng”; this is a header component.
- **Email address**: a mailbox has its own syntax rules; you cannot treat the entire address as a UTF-8 subject snippet.
- **Attachment filename**: filenames in MIME headers have their own parameter encoding rules, which may involve RFC 2231 and client compatibility behavior.
- **Reply-To, To, Cc**: the display name part can be Unicode, while the address must comply with server and protocol capabilities.

Example of setting a Unicode display name:

~~~java
import jakarta.mail.internet.InternetAddress;

helper.setFrom(new InternetAddress(
        "support@example.net",
        "Bộ phận Hỗ trợ Khách hàng",
        "UTF-8"));
~~~

This InternetAddress constructor accepts address, personal name, and charset for the personal name. Jakarta Mail represents the display name appropriately when serializing the header. Do not add Base64 to the address yourself or directly concatenate Unicode names into header strings bypassing the API.

Example of an attachment with a Vietnamese filename:

~~~java
import org.springframework.core.io.FileSystemResource;

helper.addAttachment(
        "Báo cáo tháng 11.pdf",
        new FileSystemResource("/var/reports/report.pdf"));
~~~

The filename is **metadata in the MIME header**, while the file content bytes are usually represented with a separate Content-Transfer-Encoding, such as Base64. Email clients do not always handle Unicode filename parameters identically, especially older systems. If an error appears only in the attachment filename, inspect the actual Content-Disposition/Content-Type headers and choose a compatible configuration; do not change the charset of the entire HTML body to fix a filename header.

### Subject charset differs from internationalized email addresses

A subject with Vietnamese diacritics can be encoded as an RFC 2047 encoded-word even when the SMTP server only supports ASCII addresses. However, **email addresses with Unicode characters in the local-part** are a different problem; transmitting such addresses may require **SMTPUTF8** support under extensions related to internationalized email. Internationalized domain names also have their own IDNA rules.

Therefore, **setting subject=UTF-8 does not automatically allow all Unicode email addresses**. You need to validate address syntax and the SMTP provider's support before using internationalized addresses.

## 11. Do not confuse charset errors with HTML injection

Suppose a user sets their name to:

~~~text
An <script>alert("x")</script>
~~~

If this name is concatenated directly into the HTML body, the email client may process it as markup, depending on its filtering and rendering mechanisms. This is an **input escaping/validation** problem, not a UTF-8 problem. When you want to display it verbatim, the data must be escaped for the HTML text node context:

~~~html
<p>Xin chào, An &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</p>
~~~

If inserting into an **HTML attribute** such as href, src, title, or style, you must also handle it according to the **attribute/URL/CSS context**. Do not take a text-node escape function and treat it as a safe solution everywhere. It is best to use a template engine with automatic escaping for the appropriate context.

### Subject and header injection

Subject is a header, not HTML. User-supplied CR/LF characters can cause **header injection** if the application or library handles them improperly. For dynamic Subject parts:

~~~java
public static String requireSingleLineSubject(String subject) {
    if (subject == null || subject.isBlank()) {
        throw new IllegalArgumentException("Subject is required");
    }
    if (subject.indexOf('\r') >= 0 || subject.indexOf('\n') >= 0) {
        throw new IllegalArgumentException(
                "Subject must not contain CR or LF");
    }
    return subject;
}
~~~

Combine with length limits and content policies if needed. Using MimeMessageHelper helps the library handle standard header encoding, yet **does not replace validating untrusted data** or preventing users from unauthorized control over recipient headers.

### Unicode normalization and emoji

A visually identical character can have multiple Unicode representations, for example an accented character stored as a precomposed code point or a base character + combining mark. UTF-8 can encode both forms, yet the resulting bytes differ. If the application compares, searches, or signs content by bytes, you can consider **Unicode normalization** according to system policy.

Do not apply normalization arbitrarily to all data: tokens, digital signatures, or strings whose exact byte sequence matters could be altered. Emoji can also contain multiple code points and variation selectors; Java String length, number of code points, and number of user-perceived characters **are not the same**. Simply setting UTF-8 preserves the bytes, yet **the email client's font and rendering capability** still decide how the symbol displays.

## 12. Corrupted data may come from elsewhere before sending mail

A realistic pipeline:

~~~text
HTTP request / database / template resource
        |
        v
Application/domain Java String
        |
        v
Template rendering HTML
        |
        v
MimeMessageHelper + Jakarta Mail
        |
        v
SMTP transport
        |
        v
Email client
~~~

If the source is a template file, read it using the exact charset:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String html = Files.readString(
        Path.of("templates/email/welcome.html"),
        StandardCharsets.UTF_8);
~~~

This is an example of reading from a filesystem path; in a Spring Boot application packaged as a JAR, templates usually live on the **classpath** and should be read via an appropriate resource/template engine, rather than assuming a physical path exists.

A common mistake is converting a Unicode string to bytes with the default charset, then reconstructing a String with a different charset:

~~~java
// Do not do this: risks corrupting Unicode data.
byte[] bytes = original.getBytes();  // Depends on default charset.
String wrong = new String(bytes, StandardCharsets.ISO_8859_1);
~~~

When handling bytes to integrate with external systems, explicitly specify the charset of both the **byte producer** and the **byte reader**. If data already turned into question marks at the database or API layer, configuring MimeMessageHelper=UTF-8 only preserves those question marks and cannot recover the original text.

In systems using JDBC/JPA, check connection/column/database encoding according to the actual DBMS and how the driver maps Unicode. With a message broker, template renderer, or an upstream HTTP service, you need to know whether they send Unicode strings or bytes and which charset is declared at that boundary.
## 13. Viewing raw MIME to distinguish encoding errors from display errors

When users report garbled email diacritics, looking only at the email client UI is not enough to identify the cause. You can inspect the **original MIME source** of the message in a local/staging SMTP sink or through the email client's view-source feature, if permitted.

Example of a message:

~~~mime
From: notifications@example.net
To: recipient@example.org
Subject: =?UTF-8?B?Q2Fmw6k=?=
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html><body><p>Xin ch=C3=A0o, Caf=C3=A9!</p></body></html>
~~~

A compliant email client will decode this to:

~~~text
Subject: Café
Body: Xin chào, Café!
~~~

If the raw source declares **Content-Type: text/html; charset=US-ASCII** yet the body carries UTF-8 bytes not properly represented, inspect the MIME creation step. If the raw source already contains question marks instead of Vietnamese letters right before encoding, the data may have been corrupted at the source. If the raw MIME has valid data yet one specific client renders it wrongly, check that client's MIME decoding and rendering capability or transformations by intermediate infrastructure.

### Do not read the entire raw MIME as a UTF-8 text file

A MIME message can contain multiple parts with **different** charsets and transfer encodings. Reading the entire raw message into a UTF-8 String and searching for Vietnamese text may not be accurate, because the body might be in Base64 or quoted-printable. **Reading each MIME part with Jakarta Mail** lets the library decode the corresponding Content-Transfer-Encoding and charset.

In a controlled diagnostic context, you can view the decoded subject and raw header:

~~~java
String decodedSubject = message.getSubject();
String rawSubject = message.getHeader("Subject", null);

System.out.println("Decoded Subject: " + decodedSubject);
System.out.println("Raw Subject: " + rawSubject);
~~~

**Do not automatically log Subject, recipients, or mail content in production** if they contain personal data. This is only a diagnostic example in a test environment.

### SMTP sink helps observe MIME

An SMTP sink such as a local/test environment can capture messages without sending to external addresses. You can view:

~~~text
Spring Mail service
    |
    v
SMTP sink / test server
    |
    +-- Raw MIME source
    +-- Decoded subject
    +-- text/plain preview
    +-- text/html preview
    +-- Attachment metadata
~~~

Use fake or sanitized data. The sink may store the entire content and attachments, so access to the admin UI must be restricted.

## 14. Testing Subject and body UTF-8 round-trip

You can test **MIME building** without needing an SMTP server: create a MimeMessage, serialize it to bytes, parse it back, and assert the **decoded Unicode value**. This approach shows the string survives the library's encode/decode step.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

class VietnameseMimeEncodingTest {
    @Test
    void preservesVietnameseSubjectAndHtmlBody() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, StandardCharsets.UTF_8.name());
        helper.setFrom("notifications@example.net");
        helper.setTo("alice@example.org");
        helper.setSubject("Thông báo mới – cảm ơn bạn ✅");
        helper.setText(
                "<html><body><p>Xin chào, bạn nhé! ✅</p></body></html>",
                true);

        message.saveChanges();
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        message.writeTo(bytes);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(bytes.toByteArray()));

        assertEquals(
                "Thông báo mới – cảm ơn bạn ✅",
                parsed.getSubject());
        assertTrue(parsed.isMimeType("text/html"));
        assertTrue(
                ((String) parsed.getContent())
                    .contains("Xin chào, bạn nhé! ✅"));
    }
}
~~~

Important points in the example:

1. **saveChanges()** finalizes required MIME metadata before serialization.
2. **writeTo(...)** produces the message bytes, including header and body transfer encoding.
3. A second MimeMessage is created from bytes; this tests **round-trip** instead of just reading the same initial Java object.
4. **getSubject()** returns the header already decoded by Jakarta Mail.
5. **getContent()** of a simple text/html part can return a String decoded according to Content-Type and Content-Transfer-Encoding.

This test **does not check SMTP connection or inbox delivery**. It focuses on MIME construction. With multipart/alternative or attachment structures, getContent may return **Multipart**; in that case you need to traverse the body parts and find text/plain or text/html via **isMimeType(...)**, rather than casting the whole message to String.

### Do not lock tests to a fixed raw Base64 string

Do not assume every library version will always pick the same line folding, the same header conversion, or the same Content-Transfer-Encoding when multiple ways are valid. More important assertions:

- Decoded Subject preserves exact Unicode.
- Parts have expected Content-Type and charset.
- Decoded body has exact characters and content.
- Dynamic HTML data is escaped properly according to context.
- Plain/HTML alternatives have the same essential information.

When the goal is to test **SMTP transport, STARTTLS, SMTP AUTH, or specific clients**, an integration test in an authorized environment is needed, such as an SMTP sink or test account. Mocking JavaMailSender only verifies mock calls, not actual MIME data.
## 15. Common symptoms and how to diagnose them

| Symptom | Possible cause | What to check |
|---|---|---|
| Subject has corrupted diacritics, body is fine | Wrong header encoding or already encoded beforehand | Pass Unicode to setSubject, inspect raw Subject |
| Subject is fine, HTML body is corrupted | text/html charset mismatches bytes or template source error | Check MIME Content-Type, transfer encoding, and source data |
| Plain text is fine, HTML is corrupted | Two parts built from different sources/charsets | Inspect each part and the helper's encoding |
| HTML is fine, plain text is corrupted | Plain part built with wrong content or charset | Check the two arguments of setText(plain, html) |
| Recipient sees `=?UTF-8?B?...?=` | Possible double-encoding of Subject or email client decoding bug | Do not pre-encode before setSubject |
| Recipient sees `=C3=A0` in the body | Possible missing or wrong Content-Transfer-Encoding header | Compare raw body against the part's declaration |
| Replacement character  or `?` appears | Bytes already decoded wrongly or data lost earlier | Check HTTP, database, template, then MIME |
| Email shows literal HTML tags | Body was sent as text/plain | Call setText(html, true) |
| Content displays `&amp;lt;` instead of `<` | HTML may have been escaped twice | Check rendering and escaping pipeline |
| From name is garbled yet subject is fine | Display name encoding in the header | Use InternetAddress with an appropriate charset |
| Vietnamese attachment filename is garbled | MIME filename encoding method or client support | Inspect actual Content-Disposition/Content-Type headers |
| Emoji turns into boxes | Font/client lacks glyph or original data was replaced | Check Unicode round-trip and client rendering |
| One client is wrong, others are right | Different rendering/MIME decoder capability or intermediate transformation | Compare original MIME and MIME on the receiving side |

An effective troubleshooting process:

~~~mermaid
flowchart TD
    A[Email displays corrupted diacritics] --> B{Is the Java String right before creating the email?}
    B -- No --> C[Check HTTP / DB / template / source charset]
    B -- Yes --> D[Capture serialized MIME]
    D --> E{Do header/part have suitable charset?}
    E -- No --> F[Check helper and sender configuration]
    E -- Yes --> G{Re-parse MIME with Jakarta Mail correctly?}
    G -- No --> H[Check part encoding and data]
    G -- Yes --> I[Compare MIME at client or relay]
    I --> J[Check intermediate transformation or client rendering]
~~~

**Pinpointing which stage introduces the error** is more effective than randomly switching the charset from UTF-8 to ISO-8859-1 and retrying. If changing the charset fixes one paragraph yet breaks another, the source data may already have mixed multiple encodings.

## 16. Advanced situations to keep in mind

### Long Subject headers can be folded

Email headers have line-length limit rules, so the library may split a subject into multiple encoded-words or insert CRLF with whitespace. This is normal **header folding** behavior. When inspecting raw source, do not join lines by arbitrarily stripping characters or processing Base64 piece by piece on a guess; Jakarta Mail already has header parse/decode logic.

### MIME bodies can be wrapped even when original text had no line breaks

Quoted-printable can use an **`=`** sign at the end of a line to indicate a **soft line break**. Base64 is also wrapped into character groups per MIME rules. These line breaks serving encoding **are not necessarily line breaks that the reader will see** after decoding.

~~~mime
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

This is a long line that may be split using a soft line break =
without inserting a visible newline in the decoded content.
~~~

When the content is decoded, soft line breaks do not become newline characters in the text. Therefore, when comparing the raw email and the Java String, do not take the raw line count as proof that the body has extra newlines.

### HTML and CSS content do not depend on charset alone

An HTML body can contain valid UTF-8 Vietnamese yet still render differently between Gmail and Outlook due to CSS support, fonts, dark mode, or remote images. These issues belong to **email client rendering capability**, not character encoding errors. Separate **decoding Unicode accurately** from **displaying identical UI**.

### Size after encoding can change

UTF-8 uses a different number of bytes per character; Vietnamese usually needs more bytes than ASCII, and emoji can require four bytes for a single code point. Base64 and quoted-printable can make the MIME body longer than the initial content string. When sending mail with long HTML or attachments, compare the **encoded MIME size** against the SMTP provider's limit, not just `Java String.length()`.

### UTF-8 charset does not solve integrity or transport security

UTF-8 specifies how characters are represented, not secret encryption. Emails can be read if the channel/infrastructure is unprotected. Using STARTTLS/TLS, authentication policies, and appropriate sending permissions is a separate topic that complements encoding. Meanwhile, **HTML escaping** helps avoid introducing untrusted markup into content, yet does not protect secrets stored in email.

### Multilingual emails

UTF-8 supports Vietnamese, English, Japanese, Korean, and many other scripts in the same message without needing a separate charset per language. You can set appropriate `lang` attributes in HTML to support assistive technology and pronunciation hints:

~~~html
<html lang="vi">
  <body>
    <p>Chào bạn!</p>
    <p lang="en">Thank you for your order.</p>
  </body>
</html>
~~~

However, some scripts or emoji still need corresponding fonts on the email client side. Having correct bytes is only a necessary condition; it does not guarantee glyphs display like the mockup.

## 17. Coordinating APIs in Spring Mail

To avoid confusion between Subject, body, and HTML, choose APIs according to need:

| Need | Commonly used API | Points to watch |
|---|---|---|
| Simple text email | SimpleMailMessage + JavaMailSender | Sender has UTF-8 default encoding |
| Vietnamese Subject | MimeMessageHelper.setSubject(String) | Pass Unicode directly, do not Base64 yourself |
| Plain-text body | MimeMessageHelper.setText(text, false) | UTF-8 charset for text/plain |
| HTML body | MimeMessageHelper.setText(html, true) | UTF-8 charset, escape dynamic data |
| Plain text + HTML | MimeMessageHelper.setText(plain, html) | Choose appropriate multipart, check both parts |
| Sender name with diacritics | InternetAddress(address, personal, charset) | Header encoding separate from mailbox address |
| Attachment with Unicode filename | MimeMessageHelper.addAttachment(...) | Check filename encoding when compatibility issues arise |
| Test encoding without SMTP connection | MimeMessage.writeTo + re-parse | Assert decoded content, not just raw source |

A proper email-building flow:

~~~text
1. Receive valid Unicode data from the application layer.
2. Render the HTML template with context-aware escaping.
3. Create MimeMessage using JavaMailSender.
4. Create MimeMessageHelper with explicit UTF-8 charset.
5. Set From/To, Subject using the corresponding header APIs.
6. Set text/plain and/or text/html matching MIME.
7. Let Jakarta Mail generate Content-Type and transfer encoding.
8. Send over SMTP; handle submission errors separately from delivery.
~~~

Skeleton example:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notifications@example.net");
helper.setTo("alice@example.org");
helper.setSubject("Xin chào – thông báo của bạn");
helper.setText(
        "Xin chào! Đây là thông báo dạng văn bản.",
        "<html lang=\"vi\"><body><p>Xin chào!</p>"
                + "<p>Đây là <strong>thông báo</strong> HTML.</p>"
                + "</body></html>");

mailSender.send(message);
~~~

**Core principle:** Subject belongs to the **MIME header** layer; text/plain and text/html belong to the **MIME body** layer; UTF-8 describes text bytes, Content-Transfer-Encoding describes how bytes are transmitted, and HTML escaping handles content syntax. In Spring Framework Mail, use **MimeMessageHelper with UTF-8**, pass unencoded Unicode strings to setSubject/setText, and verify results with a **MIME round-trip** when character issues arise. That is how Vietnamese and multilingual content are preserved consistently across email.
