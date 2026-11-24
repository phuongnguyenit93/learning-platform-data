# `spring.mail.default-encoding`

When a Spring Boot application sends Vietnamese email, a very common error is that the SMTP server accepts the mail but the recipient sees `ChÃ o`, `Th?ng b?o`, or characters that do not match the content the application created. For a mail client to recover the text, the MIME content part must be converted into bytes using an appropriate **character set (charset)** and described by accurate headers.

Spring Boot provides the property **`spring.mail.default-encoding`** to configure the **default charset when creating a MIME message through the mail sender automatically configured by Spring Boot**. The commonly used value is **`UTF-8`**. This is a small setting, but you need to understand the scope of its effect: it does not choose HTML or text by itself, does not replace `Content-Type`, does not control the SMTP relay, and cannot fix data that was already read with the wrong charset in an earlier step.

This lesson explains the role, how to apply it, the precedence when overriding, the relationship with `JavaMailSender` and `MimeMessageHelper`, and how to analyze character problems in email.

## 1. Where does email encoding sit?

Email does not transport a Java `String` object directly. When creating content, the application needs to turn the Unicode string into bytes. MIME allows declaring the data type, the charset, and how the bytes are represented on the mail path.

```text
Data source / template
       |
        | Reads using the source's correct charset
       v
Java String: "Chào bạn"
       |
       | Charset: UTF-8
       v
Byte: 43 68 C3 A0 6F 20 62 E1 BA A1 6E
       |
        | Content-Transfer-Encoding (if needed)
       v
MIME body, for example: Ch=C3=A0o b=E1=BA=A1n
       |
       | SMTP / mail server / mailbox
       v
Mail client decodes the transfer encoding
       |
        | Uses the declared charset
       v
Text: "Chào bạn"
```

For a MIME part containing text, the headers may look like this:

```eml
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n
```

Here:

- `Content-Type: text/plain` indicates the data is **plain text**.
- `charset=UTF-8` indicates that the bytes of **this text part** are interpreted into characters using UTF-8.
- `Content-Transfer-Encoding: quoted-printable` indicates how the bytes are represented in the body; the `=C3=A0` sequences are a transport encoding form, not the original text.
- The mail client must first recover the bytes from quoted-printable, **then** use UTF-8 to display `Chào bạn`.

The `spring.mail.default-encoding` property mainly relates to choosing the **default charset at the step of creating the MIME text**.

## 2. What does `spring.mail.default-encoding` mean?

This is a property of **Spring Boot Mail**:

```properties
spring.mail.default-encoding=UTF-8
```

Or written in `application.yml`:

```yaml
spring:
  mail:
    default-encoding: UTF-8
```

Spring Boot uses this value to configure the default encoding for `JavaMailSenderImpl` when auto-configuration creates the sender. The value is a **charset name recognized by Java**, such as `UTF-8`. Spring Boot 3.x defaults to **UTF-8** for mail encoding in its standard configuration; declaring it explicitly is still useful when you want to make the application's convention clear.

### The meaning of the word "default"

`Default` means **the value used when the place that creates the MIME part does not request a different charset**. It is not a hard rule forcing all content, all attachments, and all mail clients to use the same charset.

Example:

```text
Spring Boot configuration
  spring.mail.default-encoding = UTF-8
                |
                v
JavaMailSenderImpl (defaultEncoding = "UTF-8")
                |
                | mailSender.createMimeMessage()
                v
Spring-managed MimeMessage
                |
                | new MimeMessageHelper(message, ...)
                | if encoding is not overridden
                v
Text part / HTML part created with UTF-8
                |
                v
Jakarta Mail packages the MIME and sends over SMTP
```

The point to distinguish: **Spring Boot** binds the property and configures the sender; **Spring Framework Mail** provides `JavaMailSenderImpl` and `MimeMessageHelper`; **Jakarta Mail** performs the details of building and sending the MIME message.

### Default encoding is not SMTP configuration

| Property | Purpose | Example |
| --- | --- | --- |
| `spring.mail.host` | The SMTP server's host | `smtp.example.org` |
| `spring.mail.port` | The SMTP connection port | `587` |
| `spring.mail.username` | The authentication identity if needed | The application account |
| `spring.mail.password` | The secret used for authentication if needed | Taken from the environment |
| `spring.mail.properties.*` | Additional Jakarta Mail/SMTP properties | `mail.smtp.starttls.enable` |
| **`spring.mail.default-encoding`** | **The default charset for MIME messages** | **`UTF-8`** |

Replacing `UTF-8` with another value does **not** change the host, port, TLS, SMTP AUTH, sending limits, sender address, or relay permission.

## 3. Why should you use UTF-8 for Vietnamese email?

UTF-8 is a way of encoding Unicode into bytes, capable of representing Vietnamese, many other languages, and commonly used characters. It preserves the byte representation of ASCII in the basic character range, so it is very suitable for modern applications.

Consider the string:

```text
Chào bạn
```

The corresponding UTF-8 bytes:

```text
43 68 C3 A0 6F 20 62 E1 BA A1 6E
```

For example, the character `à` is represented by two bytes `C3 A0`; the character `ạ` is represented by three bytes `E1 BA A1`. **The number of Java characters, the number of UTF-8 bytes, and the number of characters in quoted-printable/base64 are different quantities**.

Suppose the application uses a charset that only supports ASCII characters or cannot represent the Vietnamese characters that need to be sent. When converting the `String` to bytes, some characters may be replaced with `?` or another result according to the encoder's policy. If the bytes have already lost information, changing the header to `charset=UTF-8` at a later stage cannot restore the lost diacritics.

### The correct charset must match the actual bytes

MIME header:

```text
Content-Type: text/plain; charset=UTF-8
```

is a **declaration about the body's bytes after the transfer encoding is decoded**. If the application creates bytes using a different charset but declares UTF-8, the mail client may display it incorrectly. Conversely, if the mail contains correct UTF-8 bytes but the header declares a mismatched charset, the reader also encounters errors.

Using UTF-8 consistently is a good principle, but **consistency from the data source all the way to the MIME part** is what is decisive.

## 4. Actual configuration in Spring Boot

### 4.1. Dependency

With Maven, you usually declare:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Spring Boot provides auto-configuration for `JavaMailSender` when the library and configuration conditions are satisfied. The mail starter brings the components needed to integrate Spring Mail/Jakarta Mail in a Boot application.

### 4.2. `application.yml`

Example of SMTP submission using STARTTLS on port 587:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Explanation:

- `default-encoding: UTF-8` specifies the default charset for MIME messages.
- `host` and `port` are the address of the server receiving the submission.
- `username`/`password` serve authentication if the SMTP server requires it.
- `mail.smtp.starttls.enable` and `required` illustrate requiring the connection protection to be upgraded via STARTTLS.
- The timeouts, in milliseconds, aim to prevent connections or send calls from waiting indefinitely when the server does not respond.
- `app.mail.from` is the application's own property, **not** a default property of Spring Mail.

The example configuration suits an endpoint that supports STARTTLS on 587. If the provider uses implicit TLS on 465 or OAuth, you must use a configuration suited to that service. You also need to choose a `From` address within the scope the provider has authorized for sending.

**Do not put the real SMTP password into the repository.** You can supply credentials via environment variables or the deployment platform's secret manager.

### 4.3. Using `application.properties`

The YAML and properties styles express the same configuration:

```properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
```

The placeholders `${SMTP_HOST}`, `${SMTP_USERNAME}`, and `${SMTP_PASSWORD}` receive values from the environment or the corresponding configuration source when the application runs; the `:587` in `${SMTP_PORT:587}` indicates the default value if there is no other configuration.

## 5. How does `JavaMailSenderImpl` receive the default encoding?

`JavaMailSenderImpl` belongs to the package:

```java
import org.springframework.mail.javamail.JavaMailSenderImpl;
```

This class has the API:

```java
sender.setDefaultEncoding("UTF-8");
```

When the sender creates a message via `createMimeMessage()`, the sender's default settings are stored on the MIME message type that Spring uses so that `MimeMessageHelper` can recognize them. In the typical path:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true);
```

If the message is created from a `JavaMailSenderImpl` that has a default encoding, the helper can retrieve that configuration without needing the charset name passed again.

Example when the application **manages the sender itself**:

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.org");
sender.setPort(587);
sender.setDefaultEncoding("UTF-8");
```

This is an API illustration; a real SMTP sender also has to configure credentials, TLS, and appropriate transport properties.

### Distinguishing Spring Boot auto-configuration from a self-declared bean

When Spring Boot creates the sender itself, `spring.mail.default-encoding` is applied in that configuration. But if the application defines its own `JavaMailSender`/`JavaMailSenderImpl` bean, Boot may **no longer create the default sender**. The self-managed bean will need the corresponding encoding configured.

Example:

```java
@Bean
JavaMailSender customSender() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.org");
    sender.setPort(587);
    sender.setDefaultEncoding("UTF-8");
    // Configure auth/TLS and other settings depending on the SMTP server.
    return sender;
}
```

You should not assume that every `spring.mail.*` property is still automatically copied into a bean the application creates itself. With a self-configured sender, determine clearly who owns every SMTP parameter, encoding, timeout, and credentials.

### The property's data type

At the Boot configuration level, encoding is a **charset** value, converted into an appropriate name when attached to the JavaMail sender. `UTF-8` is a standard charset supported by Java. Avoid entering an unsupported charset name or a value that looks like a media type name:

```properties
# Correct: a charset name
spring.mail.default-encoding=UTF-8

# Wrong meaning: this is a media type, not a charset name
# spring.mail.default-encoding=text/html

# Wrong meaning: this is a transfer encoding
# spring.mail.default-encoding=base64
```

## 6. Using the default encoding with `MimeMessageHelper`

`MimeMessageHelper` is a utility API for creating text, HTML, and multipart mail in Spring Framework Mail. Below are examples using the default encoding supplied by the sender.

### 6.1. Sending plain text

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public AccountMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(message);

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Chào mừng đến với hệ thống");
        helper.setText(
                "Xin chào! Tài khoản của bạn đã được tạo thành công.",
                false
        );

        mailSender.send(message);
    }
}
```

This snippet uses `new MimeMessageHelper(message)` **without passing the encoding explicitly**. With a message created through a sender that already has the default encoding `UTF-8`, the helper uses the appropriate default to create the text part. `setText(..., false)` states clearly that the body is plain text.

The `fromAddress` and `recipient` addresses must be valid according to the application's requirements and the SMTP server's policy. Jakarta Mail/Spring exceptions reflect preparation or sending errors; they do not implicitly prove the user received the mail.

### 6.2. Sending HTML containing Vietnamese

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo xác nhận");
helper.setText(
        "<h1>Xin chào!</h1>"
            + "<p>Đơn hàng của bạn đã được xác nhận.</p>",
        true
);

mailSender.send(message);
```

`setText(html, true)` indicates HTML content and makes the MIME part carry `Content-Type: text/html`. A default charset such as `UTF-8` helps encode the Vietnamese characters in the HTML.

**Using UTF-8 does not turn text into HTML by itself.** If you call `setText(html, false)`, the helper will create plain text and the recipient may see the `<h1>` and `<p>` tags verbatim. Two different concepts:

- `isHtml`/`Content-Type`: determines whether the data is HTML or text.
- `charset`: determines how the text characters are encoded.

### 6.3. Sending both text and HTML

A transactional mail can provide two versions of the same content:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");

helper.setText(
        "Chào bạn. Đơn hàng đã được xác nhận.",
        "<p>Chào bạn. <strong>Đơn hàng</strong> đã được xác nhận.</p>"
);

mailSender.send(message);
```

The `setText(plainText, htmlText)` method creates alternative text parts in the MIME structure. Each text part needs an appropriate charset; the helper can use the sender's default encoding when preparing the parts. The mail client chooses the text or HTML version according to its capability and settings.

Because the two parts represent the same message, important business content needs to appear in **both versions**.

## 7. Precedence: the default property versus an explicit encoding

When creating the helper, the application can specify its own charset:

```java
import java.nio.charset.StandardCharsets;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        StandardCharsets.UTF_8.name()
);
```

The constructor that takes an explicit encoding will use that encoding for the content the helper creates, instead of relying only on the default from the message. This is useful when a sending flow has its own requirement or the application wants to see the charset clearly at the place where the MIME is built.

| Deciding place | Example | Result in principle |
| --- | --- | --- |
| Spring Boot property | `spring.mail.default-encoding=UTF-8` | The default encoding of the sender configured by Boot |
| Self-configured sender | `sender.setDefaultEncoding("UTF-8")` | The default applies to messages created by the sender |
| Helper without specifying encoding | `new MimeMessageHelper(message, true)` | Inherits the message's default when present |
| Helper specifying encoding | `new MimeMessageHelper(message, true, "UTF-8")` | Uses the encoding passed to the helper |
| MIME part manipulated directly at the Jakarta Mail level | `mimePart.setText(text, "UTF-8")` | The charset may be decided at that part itself |

These are **layers of charset selection**, not a table guaranteeing that every part of a message always has exactly one charset. When intervening directly with Jakarta Mail, the application can create parts with different charsets.

### Example: overriding for just one message

Suppose the sender is configured with a default that is an encoding compatible with a legacy system, but one specific email needs UTF-8:

```java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime,
        false,
        "UTF-8"
);

helper.setSubject("Thông báo bằng tiếng Việt");
helper.setText("Dữ liệu dùng UTF-8.", false);
```

`false` here is the **multipart** parameter, not a switch to turn UTF-8 on/off. The helper has already received UTF-8 in the third parameter. Choose multipart based on the desired email structure; choose the encoding based on the text to be represented.

If the real code has multiple places that create `MimeMessageHelper`, you need to know which pass the encoding explicitly and which inherit the default to avoid misunderstanding the effect of the Boot property.

## 8. `Content-Type`, `charset`, and `Content-Transfer-Encoding` are different

Three concepts appear together in the MIME headers but solve three separate problems:

| Concept | Question answered | Example |
| --- | --- | --- |
| **Content-Type** | What kind of content is this? | `text/plain`, `text/html`, `application/pdf` |
| **charset** | Under which character set do the bytes of the **text part** correspond to characters? | `UTF-8` |
| **Content-Transfer-Encoding** | How are the bytes represented in the email's transmitted content? | `quoted-printable`, `base64`, `7bit` |

Example 1, Vietnamese plain text:

```eml
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n.
```

Example 2, Vietnamese HTML:

```eml
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>
```

Example 3, a PDF attachment:

```eml
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKLi4u
```

The base64 PDF string is an illustrative snippet, **not a complete PDF file**. A PDF's data bytes do not need `charset=UTF-8`: PDF is a binary data type, not a text part of the email.

### Why not set `spring.mail.default-encoding=base64`?

Base64 is a byte-representation mechanism, **not a charset**. It is the responsibility of `Content-Transfer-Encoding`, and Jakarta Mail usually chooses an appropriate transport method when serializing the MIME part.

Similarly, `text/html` is a media type, **not an encoding**. If you want to send Vietnamese HTML, you need to choose `text/html` **and** an appropriate charset, for example UTF-8.

### Are `8BITMIME` and `SMTPUTF8` related?

SMTP extensions such as `8BITMIME` and `SMTPUTF8` have their own purposes. `8BITMIME` allows cases where the body contains 8-bit bytes when both sides support it; `SMTPUTF8` relates to internationalized email in components that traditional SMTP does not support.

Configuring `default-encoding=UTF-8` **does not automatically enable** these SMTP extensions. For a Vietnamese body packaged with quoted-printable/base64, the application does not need to enable SMTPUTF8 itself just because the content has diacritics.

## 9. How are accented Subjects and sender names handled?

The body is not the only part that contains Unicode. The subject, the sender's display name, and the recipient's display name can also have diacritics:

```text
Subject: Xác nhận đơn hàng
From: "Bộ phận chăm sóc khách hàng" <support@example.org>
```

In traditional email, some header values must be encoded with their own rules, for example the **MIME encoded-word** form:

```text
Subject: =?UTF-8?B?Q2jDoG8=?=
```

The string `=?UTF-8?B?Q2jDoG8=?=` represents the word `Chào` in a header example. This is the **header encoding syntax**, different from the body's `Content-Transfer-Encoding` even though both can use base64.

When building email with Spring:

```java
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.org", "Bộ phận thông báo");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");
helper.setText("Xin chào bạn.", false);
```

These APIs help the library create correctly formatted header values. An accented display name should be passed to an API that supports charsets, instead of concatenating a raw header string with arbitrary bytes yourself.

**The body part's charset does not mean the whole header is interpreted under the same rules.** Therefore, if only the `Subject` is wrong but the body displays fine, you must look at how the header is encoded, not just check the body's `Content-Type`.

## 10. MIME multipart: each part has its own charset

An HTML email with an attachment is a **MIME tree**, not a single block of text:

```text
Top-level message:
  Content-Type: multipart/mixed
      |
      +-- Part 1: multipart/alternative
      |      |
      |      +-- text/plain; charset=UTF-8
      |      |
      |      +-- text/html; charset=UTF-8
      |
      +-- Part 2: application/pdf
               Content-Disposition: attachment
               Content-Transfer-Encoding: base64
```

Only parts representing text need a charset in this sense. **The `spring.mail.default-encoding` property does not turn image/PDF/ZIP bytes into UTF-8.**

Example of Spring creating HTML and a PDF file:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true);

helper.setFrom("billing@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn tháng này");
helper.setText(
        "Xin chào. Hóa đơn của bạn ở tệp đính kèm.",
        "<p>Xin chào. <strong>Hóa đơn</strong> ở tệp đính kèm.</p>"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf"
);

mailSender.send(message);
```

Here, the UTF-8 default supports the text and HTML parts. The PDF's media type is passed explicitly; the PDF bytes are put into a `ByteArrayResource` and are not passed through a Java `String`.

### An accented file name is a separate matter

For example `helper.addAttachment("hóa-đơn.pdf", resource, "application/pdf")`. The file name lives in a MIME header parameter such as `Content-Disposition`, which has its own encoding rules and is also affected by the receiving mail client. The MIME library helps handle internationalized file names, but you should not infer that just setting `spring.mail.default-encoding=UTF-8` will fix every case of a broken filename on every client.

If the file name contains untrusted information from users, the application must also sanitize the path, control characters, and limit the length. This is an input-handling responsibility, not the responsibility of the encoding property.

## 11. Does `SimpleMailMessage` need this property?

`SimpleMailMessage` is Spring's abstraction for plain-text email:

```java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.org");
mail.setTo("customer@example.net");
mail.setSubject("Chào mừng");
mail.setText("Xin chào! Tài khoản của bạn đã được kích hoạt.");
mailSender.send(mail);
```

For `JavaMailSenderImpl`, sending a `SimpleMailMessage` ultimately still needs to turn the content into an email message suitable for transport. The sender's default charset relates to the MIME creation and sending path underneath. However, `SimpleMailMessage` **does not let the application clearly describe a multipart structure or HTML** the way `MimeMessageHelper` does.

Therefore:

- For simple plain-text email, `SimpleMailMessage` can meet the need.
- When you need to control the encoding per message, HTML, attachments, display names, or complex MIME parts, use `JavaMailSender` and `MimeMessageHelper`.
- Do not confuse `default-encoding` with the ability to add HTML: `SimpleMailMessage` is still a simple text API.

## 12. Why is the mail still garbled even with UTF-8 configured correctly?

One important cause is that **the characters were already corrupted before being passed to the mail sender**.

Suppose the system reads a template with UTF-8 bytes but uses the wrong charset:

```text
File template (correct UTF-8 bytes)
     |
     | Read with a different charset
     v
Java String has become "ChÃ o"
     |
     | MIME encode as UTF-8 (correct process)
     v
Recipient sees "ChÃ o"
```

Here Spring Mail **encoded exactly the string the application supplied**, but that string is not the desired content. Changing the mail property to another charset usually only masks the symptom or corrupts the data further.

An example of reading a template with the correct charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String template = Files.readString(
        Path.of("templates/welcome.txt"),
        StandardCharsets.UTF_8
);
```

If the template is in the classpath of an application packaged as a JAR, you should use Spring's `Resource`/`InputStream` reading mechanism and decode UTF-8 appropriately, instead of assuming an operating-system file path always exists.

### Errors in the database, API, or template

The data source may already be wrong in:

- The database stores or returns strings under an unsuitable character set.
- An external HTTP API declares the wrong charset or sends mismatched bytes.
- A template file is saved in one charset but read as another.
- A component generating HTML converts text to bytes and then creates a `String` with a different charset.
- The message is pre-encoded into a base64/quoted-printable string and then encoded once more by the MIME helper.

To find the cause, identify **the first time the content was changed**: the data source, the Java `String`, the MIME part, the SMTP transport, or the receiving client.

## 13. Common errors and how to read the signs

| Symptom | What may have happened | What to check |
| --- | --- | --- |
| `ChÃ o` instead of `Chào` | UTF-8 bytes were decoded under another character set at some stage | The source string, the read/write charset, and the MIME headers |
| `Th?ng b?o` or the `�` character | Data was replaced because the codec does not support it or the bytes are wrong | Look at the `String` content before sending and the encoding at the source |
| `Ch=C3=A0o` appears directly | Quoted-printable was not decoded as expected | `Content-Transfer-Encoding` on the exact MIME text part |
| `SGVsbG8=` appears as text | Base64 is treated as text or there is a wrong manual encode step | Avoid double encoding; look at the raw MIME |
| Body text is correct, `Subject` is broken | Header encoding differs from body encoding | How `setSubject` is called, the raw header, and the encoded-word |
| HTML mail shows the raw tags | The part is `text/plain` or `setText(html, false)` was called | Media type/`isHtml` rather than just charset |
| The attached PDF file will not open | Binary bytes were altered or the attachment was created incorrectly | Use `addAttachment` with intact bytes |
| The property is declared but has no effect | The application uses a self-created sender or a helper overrides the encoding | Look at where the `JavaMailSender` is created and the helper constructor |
| Different mail clients display differently | MIME is missing headers, charset mismatch, or the client handles it differently | The raw MIME of the exact part and the client's behavior |
| Vietnamese body is OK, accented file name is wrong | Filename parameter encoding rules or client compatibility | `Content-Disposition` and the library creating the attachment |

### 13.1. Reading the raw MIME in the right place

An email with an attachment usually has the outermost header `Content-Type: multipart/mixed`. The charset **does not necessarily appear in the outermost header**; it may be on the inner `text/plain`/`text/html` part.

```text
MIME message: multipart/mixed
  |
  +-- text/html; charset=UTF-8
  |     Content-Transfer-Encoding: quoted-printable
  |
  +-- application/pdf
        Content-Transfer-Encoding: base64
```

When you encounter an accent error:

1. Identify the exact part that contains the broken text.
2. Check `Content-Type` and `charset` on that part.
3. Check `Content-Transfer-Encoding` on the **same part**.
4. Decode the transfer encoding to determine the text bytes.
5. Compare the bytes/string with the content right before the application passes it into the helper.

This is **a way of understanding the email structure for diagnosis**; there is no need to edit the raw MIME in the application yourself.

### 13.2. Do not fix MIME by string replacement

Avoid operations like:

```java
// Not the right solution:
// rawMail = rawMail.replace(
//     "charset=ISO-8859-1", "charset=UTF-8");
```

Replacing the header without converting the actual bytes can leave the declaration and the content no longer matching. It is better to fix **the source that generates the bytes/string** or **the API used to create the part**.

### 13.3. Encoding is not a security mechanism

UTF-8 is just a character set. Quoted-printable and base64 are transfer encodings, **not data encryption to keep it secret**. Using `spring.mail.default-encoding=UTF-8` does not protect the content from being read in transit; SMTP connection security depends on TLS and infrastructure settings, while end-to-end security is a different problem.

## 14. Important boundaries in Spring Boot configuration

### 14.1. The default encoding does not apply to non-text data

Data such as PDF, PNG images, ZIP, or other binary bytes need to be preserved intact and described with an appropriate media type:

```java
helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

`spring.mail.default-encoding` is not used to determine `application/pdf` and does not replace `FileTypeMap`, the mechanism that maps a filename to a MIME media type when it has not been declared explicitly.

### 14.2. The default encoding does not set the recipient address

`To`, `Cc`, and `Bcc` relate to email addresses and the SMTP envelope. The body's charset does not decide who receives the mail. Display names containing Unicode require their own header encoding, but routing still depends on valid addresses and the server's policy.

### 14.3. The default encoding does not guarantee successful sending

An SMTP server may reject the login, not grant relay permission, limit the number of recipients, restrict message size, or block content. A message created with correct UTF-8 can still be rejected or not yet delivered to the mailbox.

The `mailSender.send(...)` result completing without an exception only describes the state of the application's interaction with the sending mechanism at that hop; it does not prove the recipient has read the mail.

### 14.4. The default encoding does not determine the charset of all input data

A database connection, an HTTP client, or a template engine may have its own charset configuration. The `spring.mail.default-encoding` property does not by itself change `Files.readString(...)`, a JSON parser, or how another system sends bytes.

## 15. Practical example: multilingual email

An application needs to send email to Vietnamese users and some international markets. The goal is to preserve Unicode end-to-end without having to choose a separate charset for each language.

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
```

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message);

helper.setFrom("notifications@example.org", "Bộ phận thông báo");
helper.setTo("customer@example.net");
helper.setSubject("Đơn hàng đã xác nhận");
helper.setText(
        "Xin chào! Đơn hàng của bạn đã được xác nhận.",
        false
);

mailSender.send(message);
```

Here, **UTF-8 as the sender's default** avoids each service having to rewrite the charset name. The application must ensure that the strings passed to the helper are already correct Unicode, while Jakarta Mail performs the appropriate header/body encoding.

When sending the English version:

```java
helper.setSubject("Order confirmed");
helper.setText("Hello! Your order has been confirmed.", false);
```

UTF-8 is still suitable because ASCII characters also have a valid representation in UTF-8. There is no need to change `default-encoding` just because the content has no diacritics.

### If integrating a legacy system that uses a different character set

Suppose an old data source stores content in a charset other than UTF-8. The recommended handling is:

1. Read the source bytes using **the source's real charset**.
2. Convert them into a Java `String` carrying the correct Unicode characters.
3. Create the MIME text part with UTF-8 per the sender's default.
4. Ensure the MIME header describes the charset of the actual bytes.

Do not change the default encoding of the entire mail system just to compensate for a decoding error in one data source. A consistent default value makes the code easier to maintain when the application serves multiple languages.

## 16. Comprehension check questions

**Question 1.** Does `spring.mail.default-encoding=UTF-8` make the content `<b>Xin chào</b>` display in bold when calling `helper.setText(html, false)`?

> No. The UTF-8 charset only describes how characters are encoded. `false` requests plain text. To send HTML, you need to use `helper.setText(html, true)` or an appropriate text/HTML version.

**Question 2.** A PDF file is corrupted after sending. Would changing `default-encoding` from UTF-8 to another charset solve it?

> Usually not. PDF is binary data. You need to check the source bytes, the MIME part, how the attachment is added, and the transfer encoding process; do not turn PDF bytes into a `String`.

**Question 3.** The application declares default UTF-8 in YAML, but the code creates its own `JavaMailSenderImpl` and does not call `setDefaultEncoding`. Can you conclude the sender will use the Boot property?

> No. When the application declares the sender itself, you need to know exactly the bean's configuration path. The Boot property is only applied when a corresponding component reads it and attaches it to the sender.

**Question 4.** Why can an accented Subject look like base64 in the raw email even though the body uses quoted-printable?

> Because a header containing non-ASCII characters uses its own header encoding syntax, such as encoded-word, while the body uses the MIME part's `Content-Transfer-Encoding`. The two mechanisms may choose different representations.

**Question 5.** If the Java `String` already contains `ChÃ o` before calling `send()`, would adjusting `spring.mail.default-encoding` restore `Chào`?

> No. You need to fix the step of reading or decoding the data source. The mail sender can accurately encode a Unicode string that was already wrong beforehand, but it cannot infer what the user originally wanted to send.

## 17. Rules to remember

| Goal | Appropriate setting or API | What to remember |
| --- | --- | --- |
| Use UTF-8 by default in Spring Boot Mail | `spring.mail.default-encoding=UTF-8` | The default for the sender Boot configures |
| Self-configure `JavaMailSenderImpl` | `sender.setDefaultEncoding("UTF-8")` | You must manage the sender configuration yourself |
| Create text/HTML inheriting the default | `new MimeMessageHelper(message)` or a multipart constructor that does not specify a charset | The message should be created via `mailSender.createMimeMessage()` |
| Need an explicit charset for one helper | `new MimeMessageHelper(message, true, "UTF-8")` | Override at the place where the content is created |
| Choose text or HTML | `helper.setText(text, false/true)` | `Content-Type` is different from charset |
| Send both text and HTML | `helper.setText(plain, html)` on a multipart helper | Two versions expressing the same message |
| Send a PDF or image | `helper.addAttachment(...)` / `addInline(...)` | The content type and file bytes differ from the text charset |
| Accent error only in Subject | Look at header encoding, `setSubject(...)` | The body charset does not describe the whole header |
| Data was already wrong before the message was created | Fix the step reading from the template/database/API | Email encoding does not restore lost data |

**`spring.mail.default-encoding` specifies a default charset for the MIME message creation path in Spring Boot Mail.** For Vietnamese and multilingual applications, `UTF-8` is the appropriate choice. For email to display correctly, the application must at the same time keep the input data as correct Unicode, set the correct `Content-Type` for each part, not corrupt the attachment bytes itself, and let the library create MIME headers/transfer encoding in the correct structure.
