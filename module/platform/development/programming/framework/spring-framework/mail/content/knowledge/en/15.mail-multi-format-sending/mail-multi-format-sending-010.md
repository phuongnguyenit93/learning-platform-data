# Consistent Encoding Across Parts

A Spring Framework Mail email can contain multiple MIME parts: a plain text version, an HTML version, inline images, attached PDFs, or CSV files. These parts may be generated from different data sources, yet when assembled into one message, the application must ensure every part is decoded with the right characters and content.

For Vietnamese emails, encoding errors often manifest as characters like **"Hóa đơn"** turning into **"HÃ³a Ä‘Æ¡n"**, missing Vietnamese diacritics, garbled sender names, or CSV files opening with broken characters. The root cause may lie in the body charset, how a String is converted to bytes, MIME headers, how templates are read, or how encoding is declared for attachments.

Two concepts must be distinguished:

- **Charset** specifies how bytes map to characters, such as UTF-8.
- **Content-Transfer-Encoding** specifies how the bytes of a MIME part are represented for email transport, such as quoted-printable or Base64.

These two concepts solve two different problems. Base64 does not replace UTF-8; UTF-8 also does not decide whether a MIME part is transported using Base64 or quoted-printable.

In Spring Mail, an easy-to-control implementation approach is using **UTF-8 consistently for all text parts**, letting Spring/Jakarta Mail handle transfer encoding, while declaring the right MIME type for binary attachments. For emails with plain text and HTML, use **MimeMessageHelper.setText(plainText, htmlText)** to create two representations of the same content.

## 1. Charset and Content-Transfer-Encoding Differ

A MIME email may have a text part like:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, =C4=91=C6=A1n h=C3=A0ng =C4=91=C3=A3 s=E1=BA=B5n s=C3=A0ng.
~~~

In this example:

- **charset=UTF-8** states that after decoding transfer encoding, the bytes are decoded into text using UTF-8.
- **Content-Transfer-Encoding: quoted-printable** states that the body's bytes are represented using quoted-printable syntax.
- Sequences such as **=C3=A0** are quoted-printable byte representations; they are not the original UTF-8 text representation.

A client conceptually performs two steps:

~~~text
Content in MIME
       |
       v
Decode Content-Transfer-Encoding
       |
       v
Byte sequence
       |
       v
Decode using UTF-8 charset
       |
       v
Displayed characters and text
~~~

If the charset is declared wrongly, valid transfer encoding can still yield garbled characters. If transfer encoding is misinterpreted, the client may show encoded sequences instead of the original content.

### 1.1. What Is Charset?

Charset defines how characters are encoded into bytes and how bytes are restored back into characters.

For example, the Vietnamese character **ơ** is represented by multiple bytes in UTF-8. If an application takes UTF-8 bytes and decodes them with a different charset, the result will be wrong.

Java example:

~~~java
String text = "Đơn hàng đã được xác nhận";

byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);

String restored = new String(
        utf8Bytes,
        StandardCharsets.UTF_8
);
~~~

Both sides use UTF-8, so the restored string preserves the original content.

### 1.2. What Is Content-Transfer-Encoding?

MIME transfer encoding determines how bytes are represented in the message. Common values:

| Value | General meaning | Common use case |
| --- | --- | --- |
| **7bit** | Data contains only 7-bit bytes, respecting MIME line limits | Suitable ASCII content |
| **8bit** | Allows 8-bit bytes in body per MIME/transport rules | Transports supporting 8BITMIME |
| **quoted-printable** | Represents special bytes using equals signs and hex codes | Mostly ASCII text with some non-ASCII characters |
| **base64** | Converts byte data into the Base64 character alphabet | Images, PDFs, and binary data; can also be used for text |

Transfer encoding is not charset. A UTF-8 text part can be transported via quoted-printable or Base64. A PNG image can also be transported via Base64, yet an image does not have a UTF-8 charset like a text part.

### 1.3. Do Not Manually Base64-Encode Strings Before Passing to Helper

Do not do this:

~~~java
String text = "Hóa đơn đã sẵn sàng";

String base64 = Base64.getEncoder().encodeToString(
        text.getBytes(StandardCharsets.UTF_8)
);

helper.setText(base64, false);
~~~

In this case, the email body contains the literal Base64 characters themselves. When the helper builds MIME, it treats that Base64 string as text content and does not know it needs to decode it back into a Vietnamese sentence.

Standard approach:

~~~java
helper.setText("Hóa đơn đã sẵn sàng", false);
~~~

Provide the original String and appropriate charset to the helper. Jakarta Mail handles transfer encoding when serializing the MIME message.

## 2. Why Is Consistent Encoding Needed Across Parts?

An email can contain multiple different text parts:

~~~text
multipart/alternative
├── text/plain
└── text/html
~~~

If plain text uses UTF-8 while HTML is built from bytes read as Windows-1252, the two content versions may display differently. Users choosing plain text mode see proper Vietnamese, while HTML mode has garbled diacritics.

A more complex message:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   └── image/png
└── application/pdf
~~~

Here:

- **text/plain** is the text version.
- **text/html** is the HTML version.
- **image/png** is binary data referenced by HTML.
- **application/pdf** is an attached binary document.

Consistent encoding does not mean every MIME part must use the same Content-Transfer-Encoding. What needs consistency is **the character encoding rule for text parts** and **properly describing each type of data**.

| Part | Charset | Common transfer encoding |
| --- | --- | --- |
| text/plain | UTF-8 | quoted-printable, Base64, or 7bit if content allows |
| text/html | UTF-8 | quoted-printable, Base64, or transport-suitable form |
| text/csv attachment | UTF-8 if file was generated as UTF-8 | quoted-printable or Base64 depending on library |
| application/pdf | No text charset normally declared | Base64 commonly used |
| image/png | No charset declared | Base64 commonly used |
| image/jpeg | No charset declared | Base64 commonly used |

Images and PDFs are binary bytes. Never decode them into a UTF-8 String just to "unify encoding". Keep the raw bytes intact and declare the right MIME type.

## 3. Using UTF-8 for Plain Text and HTML in Spring Mail

Spring Framework provides **MimeMessageHelper** to configure MIME content. The constructor accepting an encoding lets the application specify the charset used when creating text parts.

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        "UTF-8"
);
~~~

The second parameter enables multipart; the third parameter is the default encoding the helper uses for content and headers per its API.

Example:

~~~java
String plainText = """
        Hello An,

        Order ORD-2026-001 has been confirmed.
        Total: 500,000 VND.

        Thank you.
        """;

String htmlText = """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <title>Order Confirmation</title>
          </head>
          <body>
            <h1>Hello An,</h1>
            <p>Order <strong>ORD-2026-001</strong> has been confirmed.</p>
            <p>Total: <strong>500,000 VND</strong>.</p>
            <p>Thank you.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
~~~

**setText(plainText, htmlText)** lets you send two alternative versions of the same content. When the helper is initialized with UTF-8, it uses that encoding to construct the text parts.

### 3.1. Complete Service Example

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("orders@example.org");
        helper.setTo(recipient);
        helper.setSubject("Order Confirmation");

        String plainText = """
                Hello,

                Your order has been confirmed.
                Thank you for shopping with us.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="UTF-8">
                  </head>
                  <body>
                    <h1>Order Confirmed</h1>
                    <p>Thank you for shopping with us.</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);

        mailSender.send(message);
    }
}
~~~

The text parts are created through the helper with the same UTF-8 encoding. The message has both plain text and HTML so the client can select the appropriate display mode.

If a message has only plain text, you can call **helper.setText(plainText, false)**. If only HTML, call **helper.setText(htmlText, true)**. When both representations are needed, use the overload taking both Strings.

### 3.2. The Meta Charset Tag Does Not Replace MIME Charset

In HTML you can include:

~~~html
<meta charset="UTF-8">
~~~

This tag is a supplemental hint for HTML. However, email clients first process the MIME part and its **Content-Type** header, for example:

~~~text
Content-Type: text/html; charset=UTF-8
~~~

If the MIME header declares the wrong charset, adding a meta tag is not a reliable fix. Ensure the helper creates the HTML part with UTF-8; the meta tag merely clarifies the HTML content.

## 4. The multipart/alternative Structure and Two Content Versions

When an email needs both plain text and HTML, the appropriate MIME subtype is **multipart/alternative**.

Example structure:

~~~text
Content-Type: multipart/alternative
├── text/plain; charset=UTF-8
└── text/html; charset=UTF-8
~~~

The two parts represent the same message in two formats. By MIME convention, alternatives are ordered from the simpler form to the richer form; clients pick the last part they support.

Therefore, when using Spring:

~~~java
helper.setText(plainText, htmlText);
~~~

the parameter order is **plain text first, HTML second**.

### 4.1. Both Versions Must Be Semantically Consistent

Plain text must not say "Order paid" while HTML says "Awaiting payment". The two parts are alternatives of the same message, not two independent business contents.

Keep order code, customer name, amount and currency unit, status, timestamps, action URLs or critical instructions, language, and locale aligned.

Layout may differ, yet data and meaning must remain consistent.

### 4.2. Do Not Put Essential Content Only in HTML

Some clients or users may choose plain text. If a verification code, deadline, or key condition appears only in HTML, plain-text readers will miss that information.

Ensure plain text conveys complete business content. HTML can add colors, tables, and images, but must never be the sole place holding essential facts.

### 4.3. Build Both Versions from the Same Model

A good approach is building the model once and rendering both templates:

~~~text
OrderMailData
      |
      +----> plain-text template
      |
      +----> HTML template
~~~

Example:

~~~java
public record OrderMailData(
        String customerName,
        String orderNumber,
        String totalAmount,
        String statusText
) {}
~~~

Both renderers receive the same DTO. This reduces the risk of updating one version while forgetting to update the other.

## 5. Configuring Spring Boot Default Encoding

With Spring Boot Mail, you can set the default encoding in application properties:

~~~properties
spring.mail.default-encoding=UTF-8
~~~

Or YAML:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

This property configures the default encoding for the Boot-managed mail sender. However, if code creates **MimeMessageHelper** manually, pass the encoding explicitly on initialization:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);
~~~

This makes the code's intent explicit rather than forcing readers to trace default encoding from deployment configuration.

### 5.1. application.properties and application.yml Are Equivalent

Properties:

~~~properties
spring.mail.default-encoding=UTF-8
~~~

YAML:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
~~~

Both declare the exact same Boot property. There is no need to declare one separate key for plain text and another for HTML if the application intentionally shares UTF-8 encoding.

### 5.2. Avoid Mixing Charsets Across Layers

An error-prone setup:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "ISO-8859-1"
);

String html = loadTemplateAsUtf8();
helper.setText(plainText, html);
~~~

The template was read into a String as UTF-8, yet the helper declares a different charset. When bytes are generated using the helper's charset, characters unrepresentable in ISO-8859-1 may be replaced or corrupted.

For Vietnamese content, use UTF-8 end-to-end from template files, models, and helper all the way to MIME parts.

## 6. Reading Templates from Files as UTF-8

A common source of bugs is reading templates using the host machine's default charset. Specify the charset explicitly:

~~~java
String template = Files.readString(
        path,
        StandardCharsets.UTF_8
);
~~~

If the template is on the classpath:

~~~java
ClassPathResource resource =
        new ClassPathResource("templates/mail/order.html");

String html;

try (InputStream input = resource.getInputStream()) {
    html = StreamUtils.copyToString(
            input,
            StandardCharsets.UTF_8
    );
}
~~~

This reads bytes from the resource and decodes them explicitly as UTF-8, then passes the String to a helper initialized with UTF-8.

### 6.1. Ensure Template Files Are Actually Saved as UTF-8

Declaring charset in code cannot fix a file saved in the wrong encoding. If an editor saved the template in Windows-1258 while the application reads it as UTF-8, the content will still break.

Align across the board:

- HTML/TXT files are saved as UTF-8.
- Editors/IDEs use UTF-8.
- Build/packaging does not unexpectedly alter encoding.
- File-reading code specifies UTF-8.
- The helper creates MIME parts with UTF-8.

### 6.2. Java Source File Encoding

If Java source code contains Vietnamese literals:

~~~java
String subject = "Thông báo thanh toán";
~~~

then the `.java` file must also be read by the compiler with the right encoding. Source encoding can be configured in Gradle:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

This configures Java source compilation, which is distinct from email MIME charset. An application can compile source properly and still generate broken emails if the helper or template reader uses a different charset.

## 7. Encoding for Subject and Sender Display Name

The body is not the only place that can contain Unicode characters. Email headers can also have a Vietnamese Subject, sender display name, and recipient display name.

Example:

~~~java
helper.setSubject("Hóa đơn điện tử tháng 11");
~~~

When the helper is initialized with UTF-8, it can use that encoding when setting the subject via Spring's API.

Display name:

~~~java
helper.setFrom(
        "billing@example.org",
        "Phòng Kế toán"
);
~~~

For personal names or Unicode display names, the helper has an overload accepting the display name and using the configured encoding. You can also construct an **InternetAddress** with an explicit charset:

~~~java
InternetAddress from = new InternetAddress(
        "billing@example.org",
        "Phòng Kế toán",
        StandardCharsets.UTF_8.name()
);

helper.setFrom(from);
~~~

### 7.1. Headers Are Not Body Text

The Subject header does not reside inside `text/plain` or `text/html` MIME body parts. Therefore, header charsets follow separate MIME header encoding rules, typically RFC 2047 encoded-words for Unicode content in headers.

You cannot fix a garbled Subject by adding a meta charset tag to HTML. Use Spring/Jakarta Mail header APIs with the appropriate encoding.

### 7.2. Internationalized Email Addresses Are a Separate Issue

UTF-8 for body and display names does not automatically guarantee that every email address with Unicode characters in the local-part is supported by the SMTP server. Internationalized email addresses and SMTPUTF8 are a separate protocol concern.

For systems needing internationalized email address support, verify the capabilities of your SMTP provider and transport library. Do not infer SMTPUTF8 support solely because the body uses UTF-8.

## 8. Encoding of Filenames and Attachments

Attachment filenames can also contain Unicode:

~~~java
helper.addAttachment(
        "Hóa đơn-2026.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

The filename is passed via the API, and then the mail library handles parameter representation in the header via the right MIME mechanism. Do not manually concatenate raw `Content-Disposition` headers to force encoding.

### 8.1. Filename and File Content Have Two Separate Encodings

PDF attachment example:

- The filename may be Unicode and need encoding in the MIME header.
- The PDF content is binary data with no UTF-8 charset.
- The part's Content-Transfer-Encoding may be Base64.

With CSV:

- The filename is header metadata.
- CSV content can be generated as UTF-8 bytes.
- The MIME type can declare charset UTF-8.
- Transfer encoding is handled separately.

Example:

~~~java
byte[] csvBytes = csvText.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "Báo cáo đơn hàng.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

### 8.2. Do Not Convert PDFs or Images into UTF-8 Strings

Wrong:

~~~java
String pdfText = new String(pdfBytes, StandardCharsets.UTF_8);
byte[] changedBytes = pdfText.getBytes(StandardCharsets.UTF_8);
~~~

PDF is binary data. Decoding it as UTF-8 can corrupt invalid byte sequences or alter the data.

Right:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Preserve raw bytes and declare the matching MIME type.

### 8.3. CSV Needs an Explicit Charset

If generating CSV from a Java String:

~~~java
String csv = """
        order_id,customer,total
        ORD-001,Nguyễn An,500000
        """;

byte[] csvBytes = csv.getBytes(StandardCharsets.UTF_8);
~~~

Then the byte content is already UTF-8 encoded. When adding the attachment, declare:

~~~java
helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Different spreadsheet applications detect UTF-8 differently. If specific software must be supported, test opening the file; do not add a BOM blindly unless confirmed necessary for the data contract.

## 9. Encoding of Inline Resources

Inline resources are also MIME parts, though not all inline resources are text.

PNG logo example:

~~~java
helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

PNG is binary data. Do not declare charset UTF-8 on `image/png` the way you do for `text/html`. MIME transfer encoding may be Base64; after decoding, bytes must preserve the exact PNG content.

If an inline resource is text content—such as a text or CSS part in a specialized MIME structure—then a charset may be meaningful. For ordinary PNG/JPEG images, however, there is no text charset.

### 9.1. Content-ID Is Unrelated to Charset

Content-ID only identifies a part:

~~~text
Content-ID: <companyLogo>
~~~

HTML reference:

~~~html
<img src="cid:companyLogo">
~~~

HTML charset and image bytes are independent concerns. Changing Content-ID will not fix garbled Vietnamese accents; changing charset will not fix a mismatched Content-ID.

## 10. Complete Example with Plain Text, HTML, Inline Image, and PDF

A transactional email may consist of:

- Plain text for clients that do not display HTML.
- HTML for rich layout.
- Inline logo referenced by CID.
- PDF attachment for the recipient to download.

Conceptual MIME structure:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   │       └── <img src="cid:companyLogo">
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Code example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationMailer {

    private final JavaMailSender mailSender;

    public OrderConfirmationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            byte[] invoicePdf
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("billing@example.org");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận hóa đơn điện tử");

        String plainText = """
                Hello,

                Your electronic invoice is ready.
                Please see the attached PDF file.

                Best regards,
                Accounting Department
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <head>
                    <meta charset="UTF-8">
                    <title>Invoice Confirmation</title>
                  </head>
                  <body>
                    <img
                      src="cid:companyLogo"
                      alt="Company logo"
                      width="160">
                    <h1>Electronic invoice is ready</h1>
                    <p>Hello,</p>
                    <p>Please see the attached PDF file.</p>
                    <p>Best regards,<br>Accounting Department</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);

        helper.addInline(
                "companyLogo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        helper.addAttachment(
                "Hoa-don-dien-tu.pdf",
                new ByteArrayResource(invoicePdf),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

The example uses an ASCII PDF filename to reduce filename rendering differences across clients. Unicode names can be used when product requirements call for preserving Vietnamese and compatibility has been tested.

### 10.1. Encoding of Each Part in the Example

| Component | Content | Encoding handling |
| --- | --- | --- |
| Subject | Xác nhận hóa đơn điện tử | Helper uses UTF-8 for proper header encoding |
| Display name From | Accounting Department | Helper/InternetAddress encodes display name |
| text/plain | Text content | Charset UTF-8 |
| text/html | Text and markup | Charset UTF-8 |
| PNG logo | Image bytes | Binary, no UTF-8 charset |
| PDF | Document bytes | Binary, no UTF-8 charset |
| PDF filename | Hoa-don-dien-tu.pdf | Filename header parameter formatted by library |

Each part is handled appropriately while the overall message stays consistent in meaning and encoding.

## 11. Setting Encoding in Spring Boot and JavaMail Properties

With Spring Boot, configure:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8
    host: \${SMTP_HOST}
    port: \${SMTP_PORT:587}
    username: \${SMTP_USERNAME}
    password: \${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
~~~

Where:

- **spring.mail.default-encoding** is the default encoding for the Boot-configured mail sender.
- **spring.mail.host/port/username/password** define the SMTP connection.
- **spring.mail.properties[...]** pass JavaMail properties to the SMTP transport.
- The `MimeMessageHelper` constructor can receive UTF-8 explicitly when creating a message.

Do not confuse **mail.smtp.auth** or **mail.smtp.starttls.enable** with charset. Those are SMTP transport options, not controls for how body bytes are decoded into characters.

### 11.1. Is Setting mail.mime.charset Necessary?

Jakarta Mail has default MIME charset settings in some contexts, yet for Spring Mail applications the clearest practice is:

1. Use Unicode Strings inside the application.
2. Read templates as UTF-8.
3. Initialize `MimeMessageHelper` with UTF-8.
4. Use helper APIs for body, subject, and display names.
5. Declare charset for text attachments when generating bytes.
6. Let the library manage Content-Transfer-Encoding.

Do not add a global JavaMail property without understanding its scope of impact. A global setting can affect multiple messages or content parts the application did not intend to alter.

### 11.2. Do Not Confuse JVM Encoding with Email Encoding

Running a JVM in an environment with a different default charset does not necessarily break emails if code specifies UTF-8 properly. Conversely, a JVM defaulting to UTF-8 does not guarantee every data source is decoded properly.

Control encoding at boundaries: reading files, converting Strings to `byte[]`, creating MIME parts, setting headers, and reading CSV or text data from external sources.

## 12. Common Encoding Failure Modes

### 12.1. Mojibake: UTF-8 Read with Another Charset

Original content example:

~~~text
Hóa đơn đã sẵn sàng
~~~

If UTF-8 bytes are mistakenly interpreted as Windows-1252 or an incompatible charset, the result can become:

~~~text
HÃ³a Ä‘Æ¡n Ä‘Ã£ sẵn sÃ ng
~~~

This is a sign of byte-to-charset mismatch. Trace where bytes were produced and where they were decoded, rather than just tweaking CSS or HTML.

### 12.2. Double Encoding

A string that was already encoded and then gets encoded a second time can produce garbled content.

For instance, do not manually Base64-encode a body and pass it into `setText` as text. Nor should you convert a UTF-8 String into bytes and decode those bytes with another charset before sending.

Keep Unicode Strings at the application layer and let the helper convert according to the configured encoding.

### 12.3. Plain Text Is Right, HTML Is Broken

Possible causes:

- Plain text and HTML were read from files using different charsets.
- One template has a BOM or invalid bytes.
- HTML was rendered from data already corrupted by mojibake earlier.
- The two templates use different model sources.
- The HTML MIME part declares the wrong charset.

Check the String content separately before calling the helper and check the charset in each part's MIME header.

### 12.4. HTML Is Right, Subject Is Broken

Subject is a header, not the HTML body. Check helper encoding, `setSubject` API usage, and how display names are built. A meta charset in HTML cannot fix headers.

### 12.5. CSV Opens with Garbled Characters in Excel

This can happen because CSV bytes are not UTF-8, charset was not declared, or the software detects files with its own rules. Generate bytes explicitly:

~~~java
byte[] csvBytes = csvText.getBytes(StandardCharsets.UTF_8);
~~~

And declare:

~~~java
helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Then test with the software recipients use. If a BOM or a specific CSV convention is needed, decide based on real compatibility rather than adding one arbitrarily.

### 12.6. Emojis or Characters Outside the Basic Multilingual Plane Break

UTF-8 can represent emojis and Unicode characters outside the BMP. However, the entire string must stay intact at every step. A library, database, or template may truncate strings by UTF-16 code units instead of code points and break surrogate pairs.

Do not split a String in the middle of a surrogate pair. If length limits are needed, use code-point- or grapheme-aware APIs suited to the business domain.

## 13. Let the Library Choose Content-Transfer-Encoding

A common question: should you manually set `Content-Transfer-Encoding` to Base64 for every part of an email?

Usually **no**. Jakarta Mail can choose an appropriate transfer encoding when constructing the MIME message. If you manually set a header that does not match the actual bytes, clients may decode it wrongly.

### 13.1. Text Parts

Text can use quoted-printable, Base64, or another suitable encoding. The choice depends on content, MIME provider, and transport.

Quoted-printable is often convenient when text is mostly ASCII with some non-ASCII characters. Base64 can also be used for text, though it is harder to read when inspecting raw messages.

### 13.2. Binary Parts

Images and PDFs typically use Base64 because binary data can contain bytes unsuitable for direct transport as 7-bit text.

Never decode images/PDFs into Strings to apply UTF-8. Keep raw bytes untouched and let the MIME library handle transfer encoding.

### 13.3. 8bit and SMTP Transport

A MIME part can use 8bit under suitable conditions, yet 8bit transmission also depends on SMTP server capabilities and extensions such as **8BITMIME**. Do not force 8bit without considering the transport.

To send Vietnamese emails, you do not need to force SMTP to 8bit just because Unicode characters are present. Use UTF-8 charset and let Jakarta Mail/transport choose the right representation.

## 14. Ensuring Identical Data for Plain Text and HTML

A good practice is building the model once:

~~~java
public record OrderMailData(
        String customerName,
        String orderNumber,
        String total,
        String status
) {}
~~~

Then render both templates:

~~~java
String plainText = plainRenderer.render(data);
String htmlText = htmlRenderer.render(data);

helper.setText(plainText, htmlText);
~~~

Both renderers should use the same locale and same input data. If currency or date/time formatting happens separately inside each template, use a shared formatter/service or pass pre-formatted values in the model.

### 14.1. Locale and Charset Are Two Different Concerns

**UTF-8** represents characters. **Locale** determines language, number, date/time, and currency formatting rules.

For example, the same numeric value can be formatted differently across locales. Having both parts use UTF-8 does not automatically give amounts or dates the same format.

Choose the locale explicitly for the message and apply the same rules in both plain text and HTML.

### 14.2. Avoid Rendering Twice Against Changing Data

If plain text and HTML are generated via two independent database queries, data could change between the two reads. It is better to capture a single snapshot/model and render both from the same data.

This keeps both alternative contents consistent even when the system experiences concurrent updates.

## 15. Inspecting Raw MIME to Verify Encoding

When an email displays incorrectly, inspect the raw MIME of the message in an SMTP capture server or test tool.

Example of a proper `text/plain` part:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

And HTML:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

What to confirm:

- Text parts have UTF-8 charset.
- Transfer encoding suits the data and decodes properly.
- HTML and plain text carry the same business information.
- Binary attachments have the right MIME types.
- Subject/display names use proper header encoding.
- Unicode filenames are validly encoded by the library if used.

You do not need to require every part to use the same Content-Transfer-Encoding. That is not the goal of consistent encoding.

### 15.1. Observing Content-Type

If the raw message shows:

~~~text
Content-Type: text/html; charset=ISO-8859-1
~~~

while the actual body was built as UTF-8, that is a mismatch indicator.

If the header says UTF-8 while the underlying bytes were already corrupted before the helper received the String, changing the header will not restore the original content.

### 15.2. Do Not Judge Solely by Undecoded Raw Message

If transfer encoding is quoted-printable or Base64, the raw body will not look like human-readable text. That is normal. You must decode transfer encoding first and then decode bytes by charset before judging the output.

A sequence like **=E1=BB...** can be valid quoted-printable for UTF-8 bytes, not an error. Likewise, a Base64 block in a PDF part does not mean the file is security-encrypted.

## 16. Testing Encoding in a Spring Application

### 16.1. Test String Content Before Building MIME

Use a string containing full Vietnamese characters and special characters:

~~~java
String expected =
        "Đơn hàng của Nguyễn An đã thanh toán: 500.000 đồng.";

assertEquals(expected, renderedPlainText);
~~~

This separates template/model bugs from MIME serialization bugs.

### 16.2. Test MIME Headers and Body Parts

After creating the message, inspect Content-Type and part contents with the Jakarta Mail API. For `multipart/alternative`, retrieve each BodyPart and verify both the declared charset and the content after library decoding.

Do not test by comparing a full raw MIME string verbatim, since boundaries, transfer encodings, and header order may vary by provider.

### 16.3. Test Text and Binary Attachments Separately

For CSV, confirm decoded bytes match valid UTF-8. For PDF or PNG, compare original bytes after MIME transfer encoding is decoded; do not convert bytes into a String.

### 16.4. Test on Target Email Clients

An SMTP capture server confirms the message is built properly. However, email clients handle HTML, fonts, and images differently. Verify the plain text version, HTML version, Subject and display names, Unicode filenames if used, CSV opened in target software, inline images, and attachments.

## 17. Common Mistakes and How to Fix Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Vietnamese turns into mojibake | UTF-8 bytes decoded with a different charset | Use UTF-8 from source reading through MIME |
| Plain text right, HTML wrong | Two templates have different encodings or data | Read both templates as UTF-8 and render from same model |
| HTML right, Subject wrong | Header encoding differs from body encoding | Use helper/InternetAddress with UTF-8 |
| Subject right, filename broken | MIME parameter encoding or client differences | Use attachment API, valid filename, and test clients |
| CSV opens with broken accents | CSV bytes or declared charset wrong | Generate bytes as UTF-8 and declare charset |
| PDF/PNG corrupted | Binary bytes converted through String or wrongly encoded | Keep raw bytes untouched, right MIME type |
| Raw MIME has =C3... sequences | Quoted-printable | Normal if decoding yields valid UTF-8 |
| Body displays Base64 | App manually Base64-encoded before calling setText | Pass raw String, let MIME library handle |
| HTML meta UTF-8 yet still broken | Wrong MIME part charset or bytes corrupted earlier | Check Content-Type and template reading step |
| Emojis replaced | Source, database, or string slicing broke Unicode | Check every data boundary and surrogate pairs |
| SMTP rejects 8bit | Transport/server lacks support for forced mode | Let library choose suitable transfer encoding |
| Each part uses different charset | Helper or templates configured inconsistently | Use one UTF-8 convention across all text parts |

## 18. Practical Workflow to Keep Encoding Consistent

A simple workflow:

1. **Data source:** keep Unicode Strings in the application; avoid arbitrary charset conversions.
2. **Templates:** save HTML and plain text as UTF-8.
3. **Reading templates:** specify `StandardCharsets.UTF_8`.
4. **Model:** create one shared DTO for both templates.
5. **MimeMessageHelper:** initialize with UTF-8.
6. **Body:** use `setText(plainText, htmlText)` when alternatives are needed.
7. **Headers:** set Subject/display names via encoding-aware APIs.
8. **Text attachments:** generate `byte[]` in UTF-8 and declare charset in MIME type.
9. **Binary attachments:** keep raw `byte[]`; do not decode to String.
10. **Transport:** let the mail library handle Content-Transfer-Encoding.
11. **Inspection:** inspect decoded raw MIME and rendering on target clients.

~~~text
UTF-8 Templates ----------+
                          |
Shared Model -------------+--> Plain text (UTF-8) --+
                          |                          |
                          +--> HTML (UTF-8) ----------+--> MimeMessage
                                                     |
Binary PDF/PNG --------------------------------------+
                                                     |
Subject/display name --------------------------------+
                                                     |
                                                     v
                                             Jakarta Mail MIME
                                                     |
                                                     v
                                                 SMTP send
~~~

This workflow does not require every part to share the same transfer encoding. It ensures text sources follow clear charset rules and binary data is never mishandled as text.

## 19. Frequently Asked Questions

**1. Are UTF-8 and Base64 the same?**

No. UTF-8 is a charset mapping characters to bytes. Base64 is a transfer encoding representing bytes as ASCII characters in MIME. A UTF-8 text part can be transported via Base64.

**2. Must plain text and HTML use the same Content-Transfer-Encoding?**

No. The two parts can use different transfer encodings. What matters is that each part is properly declared and decoded; text part charsets should follow a unified application convention.

**3. Why use setText(plainText, htmlText)?**

To send two alternative representations of the same content. Plain text serves clients not using HTML; HTML provides rich layout. Both should hold the same business data.

**4. Should meta charset UTF-8 be added in HTML?**

It can be added as an HTML hint, but it does not replace the MIME header **Content-Type: text/html; charset=UTF-8**. Configure the right charset when building the MIME part.

**5. Is spring.mail.default-encoding enough?**

It sets the default encoding for the Spring Boot-configured mail sender. If code instantiates `MimeMessageHelper` directly, passing UTF-8 explicitly to the constructor keeps intent clear.

**6. Should I manually set Content-Transfer-Encoding to Base64?**

Usually no. Provide raw Strings or bytes and let Jakarta Mail choose the appropriate representation. Intervene only when specific MIME/transport requirements demand it and verify the outcome.

**7. Does a PDF need charset UTF-8?**

No. PDF is binary data. Keep original bytes and use MIME type `application/pdf`. Charset applies only to appropriate text content.

**8. Does CSV need a charset?**

If CSV content is UTF-8 encoded, declaring **text/csv; charset=UTF-8** helps describe the data. You must also test the software recipients use to open the file.

**9. Why is Subject still broken when the body is fine?**

Subject is a separate header, not a body part. Use Spring/Jakarta Mail APIs with UTF-8 encoding for subject and display names; HTML meta tags do not affect headers.

**10. Are Vietnamese filenames supported?**

MIME APIs have mechanisms for encoding Unicode filenames, though different clients may handle them differently. Pass filenames via `addAttachment` and test on target clients; do not concatenate raw headers manually.

**11. Why does raw MIME have =E1 characters or Base64 blocks?**

That can be valid Content-Transfer-Encoding. Decode transfer encoding first, then decode bytes by charset to see the actual displayed text.

**12. Does SMTP need 8BITMIME enabled to send Vietnamese?**

Not necessarily. UTF-8 charset and transfer encoding are two separate layers. Jakarta Mail/transport can pick quoted-printable or Base64 appropriately without the application forcing 8bit.

**13. Can emojis be sent in UTF-8 emails?**

Yes, provided every string, template, MIME part, and client preserves Unicode. Avoid slicing strings across surrogate pairs and test on target clients.

## 20. Takeaways on Consistent Encoding Across Parts

**Charset** defines how bytes map to characters; **Content-Transfer-Encoding** defines how bytes are represented for transport in MIME. These two layers do not replace each other. For Vietnamese emails, use UTF-8 consistently across plain text, HTML, templates, subject, and display names; let Spring/Jakarta Mail handle transfer encoding for each part.

When sending multiple formats, **multipart/alternative** containing plain text and HTML provides two representations of the same content. Use **MimeMessageHelper.setText(plainText, htmlText)** with a helper initialized in UTF-8. Images and PDFs are binary data and need no UTF-8 charset; preserve raw bytes and declare the right MIME type. CSV or text attachments must have bytes generated in the chosen charset and declare that charset accordingly.

Control encoding at every boundary: reading templates, converting Strings to bytes, creating MIME parts, setting headers, and attaching files. Do not manually Base64-encode the body before calling the helper, do not convert binary files into Strings, and do not rely on HTML meta charset to fix broken MIME headers. Inspect decoded raw MIME and view emails on target clients to confirm consistent display.
