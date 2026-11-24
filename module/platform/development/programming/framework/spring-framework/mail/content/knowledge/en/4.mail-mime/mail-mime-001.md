# MIME structure of an email

When building a mail-sending module with **Spring Framework Mail**, an email may contain only a few lines of text, or it may include plain text, HTML, images displayed inside the content, and multiple attachments. So that email-reading applications can understand each type of data and how they relate to one another, email uses **MIME (Multipurpose Internet Mail Extensions)**.

MIME is neither a mail server nor a replacement protocol for SMTP. **SMTP** handles exchanging and delivering messages between systems; **MIME** specifies how message content is described and packaged. In Spring, `JavaMailSender` sends the message, while `MimeMessage` and `MimeMessageHelper` are the components commonly used to build MIME content.

After this lesson, you should be able to read the structure of a MIME email, distinguish the `multipart` types, understand how charset and transfer encoding affect content, and visualize the structure Spring produces when sending HTML, inline images, and attachments.

## 1. An email has two structural layers: the message and MIME content

An email message in Internet Message Format has a **header** section, a blank line, and a **body** section:

~~~text
From: sender@example.com
To: recipient@example.net
Subject: Hello
Date: Thu, 12 Nov 2026 09:00:00 +0700
Message-ID: <message-123@example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Hello, this is the message body.
~~~

Key components:

- **Message headers** (`From`, `To`, `Date`, `Subject`, `Message-ID`): describe the sender, displayed recipients, subject, timestamp, and message identity.
- **MIME headers** (`MIME-Version`, `Content-Type`, `Content-Transfer-Encoding`, etc.): describe how to read and interpret the content of the message or each child part.
- **Blank line**: separates the headers from the body. This line must not be removed when parsing a raw message.
- **Body**: can be simple text or a `multipart` structure consisting of multiple nested parts.

According to mail standards, lines on the wire are separated by **CRLF** (`\r\n` characters); examples in this document are displayed as ordinary lines of text for readability.

Common misconception: `From` and `To` in the displayed headers are **not identical** to `MAIL FROM` and `RCPT TO` of the *SMTP envelope*. The envelope serves transport; the headers are part of the email data. They can differ—for example, a BCC message still has the recipient in the SMTP envelope without needing to show that person in the `To` header.

## 2. Important MIME headers

| Header | Example | Role |
| --- | --- | --- |
| `MIME-Version` | `MIME-Version: 1.0` | Indicates that the message follows MIME version 1.0 mechanisms. |
| `Content-Type` | `text/html; charset=UTF-8` | Indicates the data type and parameters needed to interpret the data. |
| `Content-Transfer-Encoding` | `base64` | Indicates how the part's payload is encoded for transmission through the mail system. |
| `Content-Disposition` | `attachment; filename="invoice.pdf"` | Suggests whether the mail client should treat the content as an attachment or display it inline. |
| `Content-ID` | `<logo-1@example.com>` | Assigns an identifier to a content part, commonly used when HTML references an inline image via `cid:`. |
| `Content-Description` | `Company logo` | Provides additional description of a MIME part when needed. |

Not every email needs all of the headers above. A simple text message without attachments has a completely different structure from an HTML email with images and a PDF. Some headers appear at the message level; some headers live **inside each MIME part**, because child parts can have different data types and encodings.

### 2.1. `Content-Type`: what is this data?

A `Content-Type` value consists of a **media type**, a **subtype**, and optional **parameters**:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Type: text/html; charset=UTF-8
Content-Type: application/pdf; name="invoice.pdf"
Content-Type: image/png; name="logo.png"
Content-Type: multipart/alternative; boundary="alt-abc"
~~~

- `text/plain`: the body is plain text without interpreting HTML tags.
- `text/html`: HTML content for the client to render according to its capabilities and security policy.
- `image/png`, `image/jpeg`, `application/pdf`: image or document data.
- `application/octet-stream`: generic binary type when the exact file type is unknown.
- `multipart/...`: this is a **container** holding different MIME parts inside.

The `charset` parameter describes the character encoding of a text part; `boundary` is the delimiter between parts of a `multipart`. You should not treat `charset` or `boundary` as standalone headers outside `Content-Type`.

### 2.2. `Content-Transfer-Encoding`: how is the data transmitted?

Common mechanisms:

| Value | When to use | Things to remember |
| --- | --- | --- |
| `7bit` | Content uses only ASCII characters and lines meet transport constraints | Not suitable for writing non-ASCII Unicode characters verbatim. |
| `8bit` | Content has non-ASCII octets when the transport path has appropriate support | Requires checking `8BITMIME` support and related SMTP conditions. |
| `quoted-printable` | Text is mostly ASCII with additional characters | Encodes necessary bytes as `=XX`; usually still fairly readable. |
| `base64` | Binary data such as images/PDFs; can also be used for text | Converts data into transport-safe characters; increases size. |
| `binary` | Raw binary data in environments with matching transport support | Should not assume typical SMTP supports this form. |

**Transfer encoding is not security encryption.** Anyone with Base64 data can still decode the content. If end-to-end security is needed, a separate mechanism such as S/MIME or appropriate encryption solutions must be used rather than relying on Base64.

A part may have:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, b=E1=BA=A1n!
~~~

After decoding `quoted-printable` as UTF-8, the displayed content is **“Xin chào, bạn!”**. Proper reading consists of two steps: **decoding the transfer encoding back to the original bytes**, then **decoding the text bytes using the charset**. Performing only one step or choosing the wrong charset can cause the recipient to see garbled characters.

### 2.3. `Content-Disposition`: inline or attachment?

Two common values:

~~~text
Content-Disposition: inline
Content-Disposition: attachment; filename="report.pdf"
~~~

- `inline`: suggests displaying the content alongside the email body, such as a logo image.
- `attachment`: suggests displaying it as a downloadable attached file.

`filename` is a suggested file name for the recipient. It **does not validate the actual content of the file** and does not allow the application to implicitly trust that the file is safe. Final rendering depends on the email client, security policies, and content type.

Unicode characters in file names may require appropriate MIME parameter encoding; let the mail library handle this rather than concatenating header strings manually.

## 3. MIME part: the basic unit for building structure

Each **MIME part** can contain one of two forms:

1. **Leaf part:** contains actual data such as text, HTML, an image, or a PDF.
2. **Multipart part (container part):** contains multiple other parts and defines the relationship between them.

You can think of the entire email as a **tree**:

~~~mermaid
flowchart TD
    M["Email message"]
    M --> H["Message headers"]
    M --> B["MIME body"]
    B --> P["multipart/mixed"]
    P --> A["multipart/alternative"]
    A --> T["text/plain"]
    A --> R["multipart/related"]
    R --> W["text/html"]
    R --> I["image/png - inline"]
    P --> F["application/pdf - attachment"]
~~~

A part holding different data will have its own `Content-Type` and `Content-Transfer-Encoding`. `multipart` containers have a `boundary` and are not ordinary attached files. **The relationship between parts is determined by the `multipart` type and nesting position**, not just by file name.

## 4. Common `multipart` types

### 4.1. `multipart/mixed`: multiple independent components

This type is commonly used when an email has a **message body accompanied by one or more attachments**.

~~~text
multipart/mixed
├── text/plain              (message body)
├── application/pdf         (invoice.pdf)
└── application/zip         (documents.zip)
~~~

The parts can be displayed/saved independently. `multipart/mixed` does not mean the parts are alternative ways to render the same content.

### 4.2. `multipart/alternative`: multiple representations of the same content

This type is commonly used when both **plain text** and **HTML** versions of a message are needed:

~~~text
multipart/alternative
├── text/plain
└── text/html
~~~

The two parts are **alternative versions**, not two different emails. The client usually picks the version matching its capabilities, configuration, and policy. The convention is to place the simpler representation first and the richer one later—for example, text before HTML.

The content of both versions should convey **the same core information**. If HTML contains a confirmation link that plain text omits, users on a text-only client may be unable to complete the action.

### 4.3. `multipart/related`: directly related parts

This type is used when a primary document depends on other resources, such as HTML with a logo image linked via `Content-ID`:

~~~text
multipart/related
├── text/html                (HTML containing <img src="cid:company-logo">)
└── image/png                (Content-ID: <company-logo>)
~~~

This is a compound set of interrelated content. The HTML part is typically the primary content, while the image is a supporting resource needed to display that content. When a more complex structure has `start` or `type` parameters, they can help identify the root part and the type of the primary document.

**An inline image is not the same as an attachment file.** An image can be a MIME part while simultaneously referenced from HTML, whereas a PDF attachment is usually an independent part. Even so, some email clients may still display inline images in the attachment list.

### 4.4. Which type to choose for your needs?

| Requirement | Typically suitable MIME structure |
| --- | --- |
| Plain-text-only email | `text/plain`, no `multipart` needed |
| HTML-only email | `text/html`; a text version can be added to improve compatibility |
| Both plain text and HTML | `multipart/alternative` |
| HTML with images displayed via CID | `multipart/related` |
| Message body with PDF | `multipart/mixed` |
| Text + HTML + inline image + PDF | Combine `mixed`, `alternative`, and `related` in a tree structure |

The names `mixed`, `alternative`, and `related` indicate a **relationship**, not a fixed level. The actual tree built by a library can vary depending on the multipart mode, the APIs called, and email client compatibility requirements. What matters is that parts are grouped by the right relationships and have valid headers.

## 5. How `boundary` separates parts

With `multipart`, the `Content-Type` header declares a `boundary` value. The body uses that value to open and close the parts.

Example email with two content versions:

~~~text
From: notification@example.com
To: reader@example.net
Subject: Welcome
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="alt-123"

--alt-123
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Hello, your account is ready.

--alt-123
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html><body><p>Hello, <b>your account is ready.</b></p></body></html>

--alt-123--
~~~

Analysis:

- The header sets `boundary="alt-123"`, while the delimiter in the body starts with **two hyphens**, i.e., `--alt-123`.
- After each delimiter, a new MIME part begins; that part has its own headers, blank line, and content.
- The line `--alt-123--` has **two trailing hyphens** to close the multipart.
- The blank line between headers and body of each part must still be preserved.
- The boundary must be chosen so it is not confused with any real content line; nested multipart levels should use distinct boundaries.

Outside the parts, the standard allows a *preamble* region before the first delimiter and an *epilogue* after the closing delimiter, though most mail-display applications do not use them as primary content. If constructing raw MIME manually, using a wrong boundary or missing the closing delimiter will cause clients to parse it incorrectly. **With Spring, let Jakarta Mail generate boundaries automatically.**

## 6. Complete email example: text, HTML, inline logo, and PDF

Suppose an invoice email needs four elements:

- A **plain text** version for clients that do not render HTML.
- An **HTML** version with a reference to an inline logo.
- A **PNG logo** referenced via `cid:`.
- A **PDF file** as an attachment for the recipient to download.

A sensible structure is represented as follows:

~~~text
Email
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── multipart/related
    │       ├── text/html
    │       └── image/png (inline, Content-ID: company-logo)
    └── application/pdf (attachment: invoice.pdf)
~~~

Here:

1. The root `mixed` groups the main content and the attached file.
2. `alternative` gives the recipient two ways to read the message.
3. The HTML version sits inside `related` alongside the logo used by the HTML.
4. The PDF is placed outside the `alternative` group so clients do not treat the PDF as a substitute for the text content.

### 6.1. Abbreviated raw MIME representation

This is a structural illustration, **not a complete valid email file ready to send directly**: Base64 lines use placeholders, content/IDs are simplified, and some headers are omitted for easier reading.

~~~text
From: billing@example.com
To: customer@example.net
Subject: Invoice 123
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-1"

--mixed-1
Content-Type: multipart/alternative; boundary="alt-1"

--alt-1
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, h=C3=B3a =C4=91=C6=A1n c=E1=BB=A7a b=E1=BA=A1n =C4=91=C3=A3 s=E1=BA=B5n s=C3=A0ng.

--alt-1
Content-Type: multipart/related; boundary="related-1"

--related-1
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html><body>
  <h1>Your invoice is ready</h1>
  <img src="cid:company-logo" alt="Company logo">
</body></html>

--related-1
Content-Type: image/png; name="logo.png"
Content-Transfer-Encoding: base64
Content-ID: <company-logo>
Content-Disposition: inline; filename="logo.png"

[BASE64_IMAGE_BYTES]

--related-1--
--alt-1--
--mixed-1
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

[BASE64_PDF_BYTES]

--mixed-1--
~~~

Notice the difference between `Content-ID: <company-logo>` (declared on the image MIME part) and `src="cid:company-logo"` (referenced in HTML). The identifiers must match so the client can link the image into the right position. In a real system, Content-ID should be sufficiently unique and follow appropriate syntax.

Some email clients may ignore HTML content or block images due to security policies. Therefore, alternative text and the `alt` attribute remain meaningful; never place essential information inside images alone.

## 7. How Spring Framework Mail builds MIME

In Spring, the primary components are:

| Component | Belongs to library | Responsibility |
| --- | --- | --- |
| `JavaMailSender` | Spring Mail | Creates and sends `MimeMessage`; abstracts the sending operation. |
| `MimeMessage` | Jakarta Mail (`jakarta.mail.internet.MimeMessage`) | Object representing the MIME message and its headers/body. |
| `MimeMessageHelper` | Spring Mail (`org.springframework.mail.javamail.MimeMessageHelper`) | Helps build text/HTML, multipart, inline resources, attachments, and encoding. |
| `MimeMultipart`, `MimeBodyPart` | Jakarta Mail | Low-level building blocks for multipart structures when direct manipulation is needed. |
| `DataSource`, `Resource` | Jakarta Activation/Spring Core | Provides data sources for attachments and inline resources. |

In a Spring Boot project, you can include Spring Mail in the application with the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

The application must configure the SMTP sender according to the actual environment. MIME and SMTP are two separate layers of responsibility: a properly structured MIME file still cannot be sent if the SMTP host or credentials are wrong; conversely, a working SMTP connection cannot fix malformed MIME content.

### 7.1. Example 1: text only

For a simple message, `SimpleMailMessage` is often sufficient:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("customer@example.net");
message.setSubject("Registration successful");
message.setText("Your account has been created.");

mailSender.send(message);
~~~

Spring converts the message into a form suitable for the sender. If the application needs HTML or attachments, it must switch to `MimeMessage`. `SimpleMailMessage` does not represent a multi-part MIME tree.

### 7.2. Example 2: text and HTML with `MimeMessageHelper`

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcome(JavaMailSender sender, String recipient)
        throws MessagingException {
    MimeMessage message = sender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
    );

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Welcome");
    helper.setText(
        "Hello! Your account is ready.",
        "<html><body><h1>Welcome!</h1>" +
        "<p>Your account is ready.</p></body></html>"
    );

    sender.send(message);
}
~~~

`setText(plainText, htmlText)` creates two content representations for the client to choose from. In the example, a multipart mode that supports extending with inline images and attachments is used; if only a simple text part is needed, such a complex structure is unnecessary.

Note: the example illustrates the **API** and how content is built, without asserting the exact shape of every MIME level across all Spring/Jakarta Mail versions. The library determines the concrete structure based on the multipart mode and the operations performed on the helper.

### 7.3. Example 3: text + HTML + inline image + PDF attachment

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {
        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            mime,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");

        String plain = "Hello, your invoice is ready.";
        String html = """
            <html><body>
              <h1>Your invoice is ready</h1>
              <p>Thank you.</p>
              <img src="cid:company-logo" alt="Company logo">
            </body></html>
            """;

        // Set the content before declaring inline resources.
        helper.setText(plain, html);
        helper.addInline(
            "company-logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
        );

        sender.send(mime);
    }
}
~~~

Explanation:

- `createMimeMessage()` creates a MIME email object.
- `MULTIPART_MODE_MIXED_RELATED` supports combining related parts (content/inline) with independent attachments. This is one of the modes Spring provides to handle multi-part needs.
- `setText(plain, html)` creates two versions of the same email content.
- `addInline("company-logo", ...)` adds an image with an ID used in HTML as `cid:company-logo`.
- `addAttachment("invoice.pdf", ...)` adds a file with the corresponding name and content type.
- `sender.send(mime)` hands the MIME message over for sending via the configured transport.

The snippet assumes the application has the resource `src/main/resources/mail/logo.png` and `pdfBytes` contains previously generated PDF data. The email addresses are examples only. For HTML content taken from users or business data, proper escaping and safe link construction are required instead of arbitrary string concatenation.

**Order of operations matters:** `setText(...)` should be called before `addInline(...)` per `MimeMessageHelper` usage guidance, because some email clients are sensitive to the ordering of MIME parts.

## 8. Multipart modes of `MimeMessageHelper`

`MimeMessageHelper` provides several modes to control structure when creating multipart messages:

| Mode | Idea | When it can be used |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Do not enable multipart | Only a single simple body is needed, no inline/attachments. |
| `MULTIPART_MODE_MIXED` | Create a `multipart/mixed` structure | Need to group independent parts, especially attachments. |
| `MULTIPART_MODE_RELATED` | Create a `multipart/related` structure | Email has related resources such as inline images. |
| `MULTIPART_MODE_MIXED_RELATED` | Combine mixed with nested related | Email contains HTML content, inline resources, and attachments. |

No mode guarantees every email client will render identically. Choose the mode according to the relationships among parts and test actual emails on your product's important clients.

The constructor `new MimeMessageHelper(message, true, "UTF-8")` is commonly used to enable multipart; when you want to make the intended structure explicit, passing an explicit mode makes the code's intent clearer to readers.

### 8.1. How to tell what MIME a snippet is building?

Read in sequence:

1. Does `MimeMessageHelper` enable multipart, and which mode does it use?
2. Is `setText(...)` called with one string or two strings? Is the boolean `html` parameter enabled when using the corresponding overload?
3. Is `addInline(...)` used, and does the HTML have a matching `cid:...` reference?
4. Does `addAttachment(...)` appear, and with which file/resource is it called?
5. What `charset` is passed into the helper?

From this, you can deduce whether the email should contain text, HTML, images, or documents without immediately opening the raw MIME.

## 9. Encoding, Unicode, and headers with Vietnamese diacritics

An email can have **two independent encoding issues**:

1. **Body content:** each `text/*` part has a `charset` and `Content-Transfer-Encoding`.
2. **Message headers:** fields like `Subject` or sender display name have their own character representation rules; they are not treated like body text.

Example:

~~~text
Subject: =?UTF-8?B?<base64-encoded-utf8-bytes>?=
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

The `Subject` line illustrates the *encoded-word* form used for headers under MIME mechanisms. The portion inside `<...>` is only a placeholder; the library generates the real value. The encoded-word format can use Base64 (`B`) or the `Q` form, while the body has its own transfer-encoding rules.

In Java/Spring, the recommended approach is:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(mime, false, "UTF-8");
helper.setSubject("Xác nhận đơn hàng của bạn");
helper.setText("Xin chào, đơn hàng đã được ghi nhận.", false);
~~~

When choosing UTF-8, the library takes responsibility for building appropriate headers and body parts; you should not manually Base64-encode a string and pass the encoded string into `setSubject` unless there is a very specific requirement.

Beyond traditional MIME header encoding, there are extensions for internationalized domains/addresses and headers. **Email addresses with non-ASCII characters** depend on SMTPUTF8 support and related compatibility rules; merely setting a UTF-8 charset for the body **does not automatically** make every SMTP server accept internationalized addresses.

### 9.1. Why does the recipient see characters like `Ã¡` or `=C3=A1`?

Two common causes:

- **Wrong charset:** UTF-8 bytes are decoded as a different character set, distorting accented characters.
- **Transfer encoding not decoded:** the reader or debugging tool displays the raw `=C3=A1` string that needed to be quoted-printable decoded.

Therefore, when inspecting a part with garbled Vietnamese text, check **both `Content-Type; charset=...` and `Content-Transfer-Encoding`**, then inspect the actual byte sequence.

## 10. Differences between MIME, attachments, and transport data

### 10.1. MIME does not decide whether an email is delivered successfully

A nicely formatted HTML email with valid MIME content can still be rejected by a server due to an invalid address, missing sending permissions, a file exceeding size limits, or filtering policies. Conversely, `JavaMailSender.send(...)` returning normally does not prove the email reached the Inbox; it is the result of sending through the transport.

### 10.2. Base64 makes emails larger

For example, a 1 MB PDF when Base64-encoded increases in size by roughly one-third, not counting line breaks and headers. In addition, emails with many inline images also increase the actual size. Limits imposed by providers are usually calculated on **the packaged message**, not just the original file size.

For large files, you can send a controlled download link instead of an attachment, if business and security requirements allow.

### 10.3. `Content-Type` is only a declaration

If a malicious file is labeled `Content-Type: application/pdf`, it does not automatically become a safe PDF. File data still needs to be validated according to application needs and file-handling policies. Similarly, `filename` should not be used directly as a file path when saving on the server.

### 10.4. Inline images, URL images, and tracking pixels

HTML can reference:

~~~html
<img src="cid:company-logo" alt="Logo inline">
<img src="https://assets.example.com/logo.png" alt="Logo remote">
~~~

- `cid:...` points to a MIME part attached within the same email.
- `https://...` asks the email client to fetch the resource over the network when permitted.

Remote images may be blocked to protect privacy; inline images increase email size but reduce reliance on loading external resources. Some clients block or alter both approaches, so appropriate alternative text is needed.

## 11. Reading and inspecting MIME structure during development

When an email has formatting issues, the most useful step is to view the **raw message / original message / source** in a mail testing tool or a client that supports viewing source.

Reading workflow:

1. Find `MIME-Version` and `Content-Type` of the overall message.
2. If it is `multipart`, read the `boundary` parameter and identify the opening/closing delimiters.
3. Follow the part tree; on each part, read `Content-Type`, `Content-Transfer-Encoding`, `Content-Disposition`, and `Content-ID` if present.
4. Identify which part is text, HTML, inline image, and attachment.
5. Compare how the client renders it against the discovered MIME structure.

In development environments, you can use a test SMTP server (such as Mailpit or GreenMail) to inspect emails without sending them externally. With Jakarta Mail, you can export a `MimeMessage` to an `.eml` file to examine its structure:

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import jakarta.mail.internet.MimeMessage;

MimeMessage message = sender.createMimeMessage();
// ... use MimeMessageHelper to populate headers and content ...

message.saveChanges();
try (OutputStream output = Files.newOutputStream(Path.of("sample-mail.eml"))) {
    message.writeTo(output);
}
~~~

The example is a development-time action on a prepared message, not a step to run on every send. An `.eml` file can contain full addresses, content, and attachments, so do not store it in public places or commit it to a repository if it contains real data.

### 11.1. Common errors and how to view them from MIME structure

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| HTML shows as raw text `<h1>...` | Body is declared as text/plain or API was called as plain text | `Content-Type` and how `setText` was called |
| Vietnamese characters are garbled | Wrong charset or wrong transfer encoding decoding | Part's `charset` and `Content-Transfer-Encoding` |
| Logo image does not appear | `cid:` does not match `Content-ID`, image is not in a related structure, or client blocks images | `multipart/related`, `Content-ID`, HTML reference |
| PDF renders as text or is corrupted | Wrong part or transfer encoding, source data is not valid PDF bytes | `Content-Type`, `Content-Transfer-Encoding`, `addAttachment` source |
| Recipient sees only text or only HTML | Client picks one alternative branch; not every client displays both | `multipart/alternative` and contents of each branch |
| File appears as an attachment even though intended inline | Client has its own rendering rules or MIME part is not declared appropriately | `Content-Disposition`, `Content-ID`, and `related` relationship |
| Entire content merges into a single part | Mismatched boundary or missing closing delimiter | `boundary` and `--boundary` lines |
| Email is too large, rejected by SMTP | Base64 increases size, many images/attachments | Size of the complete MIME message |

### 11.2. Questions to ask yourself when looking at a raw email

Consider a content part:

~~~text
Content-Type: application/pdf; name="receipt.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="receipt.pdf"

JVBERi0xLjQK...
~~~

We know this part is declared as a **PDF**, uses **Base64** to represent bytes over the wire, and is suggested to display as an **attachment** named `receipt.pdf`. We **cannot yet** assert that the decoded bytes form a valid PDF file, that the file is safe, or that the recipient downloaded it.

Consider another part:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>
~~~

We know this part is **HTML**, characters are **UTF-8**, and the data must be **quoted-printable decoded** before the renderer interprets the HTML.

## 12. Remembering the structure through three levels

When looking at a MIME email, go from outside to inside:

1. **Message level:** identify displayed sender/recipients, subject, timestamp, and body `Content-Type`.
2. **Multipart level:** identify `mixed`, `alternative`, `related` groups and boundaries to understand the relationships between parts.
3. **Part level:** identify data type (`text/plain`, `text/html`, `image/png`, `application/pdf`), charset, transfer encoding, disposition, and Content-ID.

In a Spring Mail module, from a requirement like **“invoice email with text version, HTML, logo, and PDF”**, you can deduce which MIME parts must exist and how to group them; then use `MimeMessageHelper` to build a semantically correct message. When diagnosing a misrendered email, reading the **MIME tree along with each part's headers** is usually far more useful than looking only at the original HTML string.

### Standards documents for further reference

- **RFC 5322 — Internet Message Format:** email message structure, headers, and body.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** MIME headers, content types, multipart, and encoding mechanisms.
- **RFC 2387 — The MIME Multipart/Related Content-type:** model of primary content and related resources.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** extensions for representing parameters and file names with special characters.
- **RFC 6532 — Internationalized Email Headers:** extensions related to internationalized email headers.

The RFCs describe structure and protocol; the `JavaMailSender`, `MimeMessage`, and `MimeMessageHelper` APIs help turn those principles into real emails in a Java/Spring application.
