# Risks of Building MIME Manually in Spring Framework Mail

When sending emails with multiple formats, inline images, or attachments, the application must produce a message conforming to the MIME (Multipurpose Internet Mail Extensions) standard. MIME describes content types, data encoding, boundaries between parts, and relationships among parts in the same email.

An email can contain a `text/plain` version, a `text/html` version, inline images referenced by HTML via `cid:...`, PDF/CSV/XLSX attachments, and Unicode content in subjects or filenames.

Concatenating a raw MIME string manually to build these parts may seem simple at first, yet it very easily creates malformed messages or bugs that surface only on certain mail clients. Mistakes commonly occur in boundaries, CRLF, encoding, headers, MIME nesting, binary data, and handling of untrusted input.

**In Spring Framework Mail, use `MimeMessageHelper` and Jakarta Mail APIs to build the message via an object model.** Only construct low-level MIME manually when a specific requirement cannot be satisfied by the helper; even then, use `MimeBodyPart`, `MimeMultipart`, and `DataHandler` instead of concatenating headers, boundaries, and bytes into one string.

## 1. What Problem Does MIME Solve?

Early email primarily transported plain text. MIME extends the format so a message can describe content of many types, such as HTML, images, PDFs, or encoded data.

A MIME part typically has:

- Headers describing the part, such as `Content-Type`.
- Optionally `Content-Transfer-Encoding` describing how bytes are represented for transport.
- Optionally `Content-Disposition`, `Content-ID`, or related headers.
- A blank line separating headers and body.
- The part's payload data.

Illustrative example of an HTML part:

```text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Hello there!</p>
```

A multi-part message uses a multipart structure:

```text
Content-Type: multipart/alternative; boundary="example-boundary"

--example-boundary
Content-Type: text/plain; charset=UTF-8

Hello there!

--example-boundary
Content-Type: text/html; charset=UTF-8

<p>Hello <strong>there</strong>!</p>

--example-boundary--
```

In the example, `boundary` divides the message into parts. Leading `--` before a boundary opens a part; trailing `--` at the end of a boundary closes the entire multipart. This is only an example for understanding the structure, not a pattern for building emails via string concatenation in an application.

### MIME Is Not Just Adding One Header

Putting `Content-Type: multipart/alternative` at the top of an email is not enough to make a message valid. The content must declare and consistently use boundaries, every part must place headers and body properly, and the multipart must close cleanly. Binary files require suitable transfer encoding; HTML referencing CIDs requires MIME parts with matching Content-IDs.

Thus, when building MIME manually, the application becomes responsible for the entire message structure. That is the exact responsibility Jakarta Mail and Spring Mail provide APIs to manage.

## 2. Risk 1: Invalid or Inconsistent Boundaries

A boundary is the string separating parts in `multipart/*`. The header declares the boundary, while the body uses that exact string in delimiters.

Common mistakes:

- Header declares `boundary="abc"` while body uses `--xyz`.
- Forgetting the leading `--` on delimiters.
- Forgetting the closing delimiter `--boundary--`.
- Reusing the same boundary across nested multiparts.
- The boundary appearing verbatim inside part content, tricking parsers into ending early.
- Concatenating or quoting boundaries wrongly when values contain special characters.

Incorrect example:

```text
Content-Type: multipart/alternative; boundary="outer"

--inner
Content-Type: text/plain

Hello

--outer--
```

The header declares the boundary as `outer`, yet the opening delimiter uses `inner`. Parsers cannot determine the structure properly.

### Boundaries in Nested Multiparts

An email with an alternative body, inline images, and attachments can have multiple multipart layers:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   └── image/png (CID)
└── application/pdf (attachment)
```

Each multipart needs its own boundary. When concatenating strings manually, generating unique boundaries, declaring them accurately at each level, and closing them in the right order is very error-prone. When using the object model, Jakarta Mail manages boundaries and serialization.

**How to avoid:** never generate boundaries by concatenating strings. Use `MimeMultipart` or `MimeMessageHelper` so the library creates boundaries and manages parts.

## 3. Risk 2: Wrong CRLF and Header/Body Separators

Internet Message Format uses the CRLF (`\r\n`) line convention. In raw MIME, headers and body are separated by a blank line—that is, a double CRLF.

Structure example:

```text
Subject: Monthly report\r\n
MIME-Version: 1.0\r\n
Content-Type: text/plain; charset=UTF-8\r\n
\r\n
Report is ready.\r\n
```

If an application uses LF (`\n`) newlines inconsistently, or omits the blank line between headers and body, some parsers may fail to read the message as expected.

Common mistakes:

- Using only LF in raw MIME.
- Using CRLF inconsistently between headers and delimiters.
- Adding spaces or characters before the first header.
- Forgetting the blank line after a part's headers.
- Placing newlines in the wrong position, adding extra blank lines to content or merging a boundary into the body.
- Rewriting newlines in text content without understanding the impact on the data.

### Do Not Hand-Write SMTP DATA

Beyond MIME, SMTP also has data transmission rules, such as dot-stuffing when a data line starts with a dot. Jakarta Mail's SMTP transport handles those transmission rules. If an application concatenates MIME manually and sends SMTP over a raw socket, it must also handle SMTP commands, response codes, dot transparency, timeouts, TLS, and AUTH.

Let `JavaMailSender`/Jakarta Mail handle transport. Applications should work with `MimeMessage`, not hand-write SMTP sessions from command strings.

## 4. Risk 3: Confusing Charset with Content-Transfer-Encoding

These two headers solve two different problems:

| Attribute | Question answered | Example |
|---|---|---|
| `charset` in Content-Type | Which character encoding decodes text bytes into characters? | `charset=UTF-8` |
| `Content-Transfer-Encoding` | How are a part's bytes represented inside MIME? | `quoted-printable`, `base64`, `7bit` |

Example:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
```

`UTF-8` defines how Vietnamese characters are interpreted. `quoted-printable` defines how bytes are represented in the MIME body. They do not substitute for each other.

### Errors When Encoding Content Manually

If a Java String was encoded as UTF-8 bytes yet the header declares another charset, recipients may see garbled characters. If content was converted into a base64 string yet still declares `Content-Transfer-Encoding: 8bit`, clients will display the literal base64 string instead of the original content.

Another mistake is manually base64-encoding content and passing it to an API that encodes the part again. The result is **double encoding**: clients decode one layer and end up with a base64 string instead of the original data.

### Why Not Set Content-Transfer-Encoding Manually?

Jakarta Mail can choose an appropriate transfer encoding based on content type and transport capabilities. If you set the header manually without converting the payload to match, the header and body will contradict each other.

For text, use APIs like `setText(text, "UTF-8")` or `MimeMessageHelper`. For HTML, set content type and charset through the helper. For files, supply a resource/`DataHandler` so the library reads bytes and builds the right MIME part.

Spring example:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(
        "Order has been confirmed.",
        "<p>Order <strong>has been confirmed</strong>.</p>");
```

There is no need to manually convert both strings to bytes, base64-encode them, and write MIME headers by hand.

## 5. Risk 4: Mis-Encoding Binary Files

PDF, PNG, JPEG, XLSX, and other binary files contain arbitrary bytes. Putting bytes directly into a text MIME string without proper transfer encoding can corrupt data through charset conversion, newline normalization, control-character stripping, or misinterpretation.

Unsafe example:

```java
// Do not convert PDF bytes into a String to concatenate into raw email.
String pdfText = new String(pdfBytes, StandardCharsets.UTF_8);
String rawMessage = "Content-Type: application/pdf\r\n\r\n"
        + pdfText;
```

A PDF is not UTF-8 text. Converting PDF bytes into a String can corrupt content and fails to produce a valid MIME attachment.

### Use Resource/ByteArrayResource

With Spring Mail:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
```

Jakarta Mail handles reading bytes and representing the attachment in MIME. For inline images:

```java
helper.setText(
        "The report is ready.",
        "<p>The report is ready.</p><img src=\"cid:chart\">");
helper.addInline(
        "chart",
        new ByteArrayResource(chartPng),
        "image/png");
```

There is no need to convert images into base64 strings manually and paste them into the raw body.

## 6. Risk 5: Wrong Multipart Structure

Multipart subtypes have distinct meanings. Choosing the wrong subtype can cause clients to render content incorrectly or treat parts as attachments.

| Subtype | Meaning | Usage example |
|---|---|---|
| `multipart/alternative` | Alternative representations of the same content | Plain text and HTML |
| `multipart/related` | Main content and resources it references | HTML and CID images |
| `multipart/mixed` | Independent parts grouped in the same message | Email body and PDF attachment |

### Alternative Is Not Mixed

`multipart/alternative` is for multiple versions of the same content. For example, text/plain and text/html convey the same information. Versions are normally ordered from less rich to richer, so text/plain precedes text/html.

If a PDF attachment is placed as an alternative part, mail clients may misinterpret the PDF as an alternative version of the body. The PDF must be organized as an independent part inside a mixed structure.

### Related Is Not a Regular Attachment

An image referenced by HTML via `cid:logo` has a relationship with the HTML part. `multipart/related` describes that relationship. If an image is only placed in `multipart/mixed` while HTML references a CID without the proper structure, some clients may fail to link the image to the body or display it as an attachment.

### Reference Structure

A message with text, HTML, a CID logo, and a PDF can be logically represented as:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png
    │       Content-ID: <logo>
    └── application/pdf
        Content-Disposition: attachment
```

This is an illustrative structure; exact nesting depends on the API, multipart mode, and library. When using `MimeMessageHelper`, pick the right multipart mode instead of building layers manually with raw strings.

## 7. Risk 6: Invalid Headers and Header Injection

Emails have many headers:

- `From`, `To`, `Cc`, `Bcc`.
- `Subject`.
- `Reply-To`.
- `Date`, `Message-ID`.
- `MIME-Version` and content-related headers.

Headers have specific syntax, supporting folding and encoding. Never concatenate user input directly into raw headers.

Dangerous example:

```java
// Do not concatenate user input into raw headers.
String rawHeader = "Subject: " + userSuppliedSubject + "\r\n";
```

If the input contains CRLF, it can inject new headers or alter message structure. Some Jakarta Mail APIs reject newline characters in header values, yet applications must still validate input and never concatenate raw headers manually.

### Use Typed APIs

```java
helper.setSubject(subject);
helper.setFrom(fromAddress);
helper.setTo(recipientAddress);
helper.setReplyTo(replyToAddress);
```

These APIs know how to set headers properly, far better than writing `Subject: ...` or `To: ...` into a string.

### Validate Email Addresses

If a recipient address comes from input, parse and validate it using the address API while enforcing application policies:

```java
import jakarta.mail.internet.InternetAddress;

InternetAddress address = new InternetAddress(recipient, true);
address.validate();
helper.setTo(address);
```

This validates address syntax at the library level; it does not prove the mailbox exists or that the requester is authorized to send to that address. Sending permissions and business rules must still be checked separately.

### Do Not Put Bcc Into Content Manually

`Bcc` is a recipient header that must be handled by the mail API/transport. Do not put Bcc addresses into the body or manually write a Bcc header in a raw string expecting every transport layer to handle it properly. Use `helper.setBcc(...)` or the equivalent API. Transport layers can strip the Bcc header from outbound copies per standard email behavior.

## 8. Risk 7: Subject, Display Name, and Filename Encoding

Email headers have specific encoding rules for non-ASCII characters. A subject like `"Báo cáo tháng 11 – Nguyễn An"` and a filename `"Hóa đơn tháng 11.pdf"` may require encoded-words or encoded parameters to be compatible across mail clients.

Do not manually base64-encode the entire subject and drop it into a header arbitrarily. Header encoding is not the same as body encoding.

### Subject and Display Name

Use the API:

```java
helper.setSubject("Báo cáo tháng 11 – Nguyễn An", "UTF-8");
helper.setFrom(
        new InternetAddress("notifications@example.org", "Đội ngũ Example", "UTF-8"));
```

Jakarta Mail handles proper encoding when serializing the message.

### Attachment Filenames

Filenames can contain Vietnamese diacritics, spaces, or Unicode characters. Representing the filename parameter has specific rules, typically involving RFC 2231 and client compatibility differences. Use:

```java
helper.addAttachment(
        "Hoa-don-thang-11.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
```

If a Unicode filename is needed, pass the filename to the attachment API and test across target clients. Do not manually concatenate `Content-Disposition: attachment; filename="..."` with unescaped strings.

Beyond encoding, sanitize filenames: strip path separators, control characters, and internal path names. Send only the basename the recipient needs to see, never server paths inside filenames.

## 9. Risk 8: Line Length and Transfer Encoding

Email standards impose limits on line lengths in headers and bodies. For example:

- Headers follow folding and line-length rules per Internet Message Format.
- Base64 in MIME is normally line-wrapped at a maximum of 76 characters per line per MIME rules.
- Quoted-printable also has line-length limits.

Concatenating a very long base64 string onto a single line can cause some parsers or gateways to mishandle it. Wrapping lines improperly can alter data upon decoding.

Do not write your own base64 and line-wrapping functions when Jakarta Mail can do it. Supply a byte array or resource to the part so the library serializes it properly.

### Do Not Confuse 7bit, 8bit, and binary

`7bit`, `8bit`, and `binary` are not synonyms:

- `7bit` restricts data to 7-bit ASCII and obeys line rules.
- `8bit` permits 8-bit bytes, though transmission depends on SMTP capabilities like 8BITMIME.
- `binary` is for binary data and requires corresponding transport support.
- `base64` and `quoted-printable` represent data in ways more compatible across email systems.

Declaring `8bit` manually when an SMTP server or gateway lacks support can cause content to be rejected or corrupted. Jakarta Mail can choose the appropriate encoding based on configuration and transport.

## 10. Risk 9: Mismatched HTML, CID, and Content-ID

An email with inline images must keep these synchronized:

1. `src="cid:logo"` in HTML.
2. `Content-ID: <logo>` on the image part.
3. Exact `Content-Type` such as `image/png`.
4. Appropriate `multipart/related` structure.

Common mistakes:

- HTML uses `cid:logo` while the part has ID `brand-logo`.
- Two images share the same Content-ID.
- The image part declares the wrong MIME type.
- HTML is rendered/set after inline resources were added and alters the multipart structure.
- The image is added as a regular attachment instead of an inline resource.

With Spring:

```java
helper.setText(
        plainText,
        "<p>Logo:</p><img src=\"cid:brand-logo\" alt=\"Logo\">");

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

Call `setText` before `addInline`. Do not put a local filesystem path in HTML expecting the helper to locate the file automatically. `addInline` takes the actual resource and builds the MIME part for HTML to reference.

## 11. Risk 10: Untrusted Data in MIME and HTML

When building emails from user data, distinguish header values like subject, display name, and recipient; `text/plain` content; HTML content; filenames; and URLs in `href` and `src`. Each context has its own handling rules. A string that has been HTML-escaped is not automatically safe in headers, URLs, or filenames.

### HTML Injection

Do not insert user names directly into HTML:

```java
// Do not concatenate unescaped data into markup.
String html = "<p>Hello " + customerName + "</p>";
```

Use a template engine with auto-escaping or escape according to exact HTML context. For URLs in `href`/`src`, besides escaping, validate scheme and host. Never let user input arbitrarily create `javascript:` URLs or links to spoofed domains.

### Header Injection

Never concatenate CRLF or header fragments from input into raw MIME. Use typed APIs and validate values.

### Filename Injection

Never accept a path like `../../private/secret.pdf` as an attachment name. Generate filenames from safe internal IDs or keep only a sanitized basename.

### Spoofed MIME Types

Do not trust file extensions. If a file is named `report.pdf` while its actual bytes are a different format, declaring `application/pdf` does not turn it into a PDF. Verify actual format and file-type policies before sending.

## 12. Risk 11: Manual Bcc, Recipient, and Inconsistent Header Handling

A message can have multiple recipients via To, Cc, and Bcc. Manually concatenating raw headers can expose Bcc recipients to other recipients, duplicate addresses, produce invalid headers, or leak private data by mixing up recipient lists.

Use `MimeMessageHelper`/Jakarta Mail APIs to set recipients:

```java
helper.setTo(toAddress);
helper.setCc(ccAddress);
helper.setBcc(bccAddress);
```

SMTP envelope recipients and header recipients serve different roles. If an application needs to send to multiple addresses without revealing the list, use Bcc or send separate messages per policy; never edit raw headers manually to hide addresses.

## 13. Risk 12: Raw MIME Incompatible with Mail Clients

A MIME message may be accepted by a parser yet render differently across Gmail, Outlook, Apple Mail, webmail, and mobile apps. Causes include non-standard nested multipart structures, unsuitable `Content-Disposition`, differing header or filename encodings, unsupported HTML/CSS, CID parts not placed properly inside related multiparts, or non-standard boundaries/transfer encodings.

You cannot rely on a single browser preview to conclude raw MIME works on every mail client. Use standard MIME structures and test on the clients that matter to your product.

## 14. The Safer Approach: Use MimeMessageHelper

For most Spring emails, `MimeMessageHelper` is the recommended choice. Example of an email with plain text, HTML, a CID logo, and a PDF attachment:

```java
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

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            byte[] invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("notifications@example.org");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");

        String plainText = """
                Your invoice is ready.
                Please open the attached PDF file to view details.
                If you need support, contact support@example.org.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <p>
                      <img src="cid:invoice-logo"
                           alt="Example Logo"
                           width="130">
                    </p>
                    <h2>Your invoice is ready</h2>
                    <p>Please open the attached PDF file to view details.</p>
                    <p>Need support? support@example.org</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        helper.addInline(
                "invoice-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");
        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(invoicePdf),
                "application/pdf");

        mailSender.send(message);
    }
}
```

In this example:

- `MIXED_RELATED` multipart mode supports the body, related resources, and attachments.
- `setText(plainText, htmlText)` creates alternative content versions.
- `addInline` adds the image referenced by HTML via CID.
- `addAttachment` adds the PDF as an independent file.
- UTF-8 charset is configured when creating the helper.
- Jakarta Mail handles serializing the MIME message.

In real applications, sender and recipient addresses must come from configuration and validated data; the example uses illustrative addresses only. Limit the size of `invoicePdf` and validate artifacts before attaching.

### Choosing the Right Multipart Mode

`MimeMessageHelper` provides multipart modes, typically including:

| Mode | General meaning | Use case |
|---|---|---|
| `MULTIPART_MODE_NO` | Multipart disabled | A single simple body |
| `MULTIPART_MODE_MIXED` | Uses multipart/mixed | Body and attachments |
| `MULTIPART_MODE_RELATED` | Uses multipart/related | HTML and inline resources |
| `MULTIPART_MODE_MIXED_RELATED` | Combines mixed and related | HTML/CID with attachments |

Exact mode names and structures should be checked against the API of your Spring Framework version. Do not assume every helper constructor builds the exact same MIME tree.

## 15. When the Helper Is Not Enough: Use the Jakarta Mail Object Model

There are cases needing lower-level control over MIME structure, such as a system requiring specific part nesting or manipulating specialized headers/parts. Even then, use the Jakarta Mail object model rather than concatenating raw MIME strings.

### 15.1. Creating the Alternative Part

```java
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;

MimeMultipart alternative = new MimeMultipart("alternative");

MimeBodyPart plainPart = new MimeBodyPart();
plainPart.setText(plainText, "UTF-8");
alternative.addBodyPart(plainPart);

MimeBodyPart htmlPart = new MimeBodyPart();
htmlPart.setContent(htmlText, "text/html; charset=UTF-8");
alternative.addBodyPart(htmlPart);
```

Parts are added in plain text then HTML order. Each body part has its own API to configure content and charset.

### 15.2. Wrapping Alternative in Related for CID Images

```java
import jakarta.activation.DataHandler;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;
import jakarta.mail.util.ByteArrayDataSource;

MimeBodyPart alternativesContainer = new MimeBodyPart();
alternativesContainer.setContent(alternative);

MimeMultipart related = new MimeMultipart("related");
related.addBodyPart(alternativesContainer);

MimeBodyPart logoPart = new MimeBodyPart();
logoPart.setDataHandler(new DataHandler(
        new ByteArrayDataSource(logoBytes, "image/png")));
logoPart.setHeader("Content-ID", "<brand-logo>");
logoPart.setDisposition(MimeBodyPart.INLINE);
related.addBodyPart(logoPart);
```

HTML in `htmlText` must use `<img src="cid:brand-logo">`. The example uses `ByteArrayDataSource` to supply image data to `DataHandler`.

### 15.3. Wrapping Related in Mixed for Attachments

```java
import jakarta.activation.DataHandler;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMultipart;
import jakarta.mail.util.ByteArrayDataSource;

MimeBodyPart relatedContainer = new MimeBodyPart();
relatedContainer.setContent(related);

MimeMultipart mixed = new MimeMultipart("mixed");
mixed.addBodyPart(relatedContainer);

MimeBodyPart pdfPart = new MimeBodyPart();
pdfPart.setDataHandler(new DataHandler(
        new ByteArrayDataSource(invoicePdf, "application/pdf")));
pdfPart.setFileName("invoice.pdf");
pdfPart.setDisposition(MimeBodyPart.ATTACHMENT);
mixed.addBodyPart(pdfPart);

message.setContent(mixed);
message.saveChanges();
```

This is low-level MIME construction using the object model. The application remains responsible for choosing subtypes, part order, Content-ID, filename, disposition, and payload. Jakarta Mail manages boundary serialization and encoding when saving/sending.

For a typical Spring application, `MimeMessageHelper` is shorter and less error-prone. Drop down to lower-level APIs only when genuine control is needed; avoid reimplementing features the helper already provides.

## 16. Why Not Concatenate Raw MIME Using Strings?

Example of an error-prone approach:

```java
// Anti-pattern example: do not use in applications.
String boundary = "----my-boundary";

String rawMime =
        "MIME-Version: 1.0\r\n"
        + "Content-Type: multipart/mixed; boundary=" + boundary + "\r\n"
        + "\r\n"
        + "--" + boundary + "\r\n"
        + "Content-Type: text/plain; charset=UTF-8\r\n"
        + "\r\n"
        + plainText + "\r\n"
        + "--" + boundary + "\r\n"
        + "Content-Type: application/pdf\r\n"
        + "\r\n"
        + new String(pdfBytes, StandardCharsets.UTF_8)
        + "\r\n"
        + "--" + boundary + "--\r\n";
```

This example illustrates several problems:

- The PDF is converted to a UTF-8 String, potentially corrupting bytes.
- There is no suitable `Content-Transfer-Encoding` for the PDF.
- Filename and disposition headers are missing.
- If text content contains the boundary delimiter, parsers can misread the structure.
- Nested multiparts, CIDs, and HTML are not handled properly.
- No header/encoding normalization mechanism exists.
- Recipients, Bcc, and other message headers are unhandled.

Even if the PDF is replaced with base64, the author still has to manage line wrapping, header encoding, boundaries, CRLF, and every content type. Maintenance cost and bug risk are far higher than using the APIs.

## 17. Inspecting the Generated MIME Message

When display bugs occur or clients fail to recognize attachments, inspect the raw source of the message in a test environment. An SMTP sink such as Mailpit or a local mail testing tool lets you inspect messages without sending to real recipients.

Points to observe:

- Does the root `Content-Type` have the right subtype?
- Do declared boundaries match delimiters in the body?
- Do nested multiparts serve the right roles?
- Do `text/plain` and `text/html` have appropriate charsets?
- Do HTML CIDs have matching Content-ID parts?
- Does the PDF have the right `Content-Type` and `Content-Disposition`?
- Are attachment filenames encoded appropriately?
- Does the message have proper closing boundaries and no abnormal empty parts?

### Using Jakarta Mail to Re-Read the Structure

In tests, you can inspect the constructed message:

```java
MimeMessage message = mailSender.createMimeMessage();
// Set up the message via helper or Jakarta Mail API.
message.saveChanges();

Object content = message.getContent();
if (content instanceof MimeMultipart multipart) {
    int count = multipart.getCount();
    // Verify part count and content per the designed structure.
}
```

This is a sketch: depending on multipart mode, root content can be nested multiparts. Tests should traverse the part tree recursively and confirm exact subtypes, Content-IDs, filenames, and MIME types rather than assuming the root has a fixed part count.

### Testing on Mail Clients

Valid raw MIME source does not guarantee every client renders identically. For critical emails, check these scenarios:

| Scenario | What to observe |
|---|---|
| Client displaying only plain text | Business content remains complete |
| Client displaying HTML | Layout and links are readable |
| Client blocking remote images | Alt text and content are not lost |
| Client displaying CIDs | Inline images sit in the right spots |
| Client with attachment viewer | PDF opens cleanly and filename is right |
| Client using different locale | Subject, Vietnamese, and Unicode have no errors |

Do not use a single successful SMTP send as proof that all MIME content renders properly on receiving devices.

## 18. Logging and Diagnosing MIME Errors

When sending emails, log per stage:

1. Whether content rendering succeeded or failed.
2. Whether creating the MIME message and adding parts succeeded or failed.
3. Whether SMTP submission succeeded or failed.
4. Delivery/bounces if the provider supplies events.

Safe fields to log: mail job ID, email type/template version, attachment count and total bytes, high-level MIME subtype, provider message ID if available, error category, and exception class.

Avoid logging SMTP passwords, access tokens, PDF/image contents, password-reset tokens or OTPs, full raw MIME messages containing personal data, and sensitive local paths.

### Classifying Errors

| Error | Typically related layer |
|---|---|
| Invalid boundary / malformed multipart | MIME construction |
| Unsupported encoding / malformed header | MIME construction or receiving parser |
| CID lacks matching part | Content and MIME structure |
| Empty attachment | Resource lifecycle / MIME part |
| Address rejected | Header/recipient or SMTP policy |
| Authentication failed | SMTP transport |
| Message too large | MIME size / SMTP provider |
| SMTP accepted yet email bounced | Post-submission delivery |

If the SMTP server accepted the message, that does not prove the recipient opened the email or could view the content. For delivery errors, inspect events from the provider or mail gateway.

## 19. Practical Rules

1. **Do not concatenate raw MIME with Strings.** Use Spring `MimeMessageHelper` or the Jakarta Mail object model.
2. **Let the library manage boundaries.** Never generate or concatenate multipart boundaries manually.
3. **Use library-managed CRLF and serialization.** Do not hand-write SMTP DATA or dot-stuffing.
4. **Distinguish charset from transfer encoding.** UTF-8 describes characters; base64/quoted-printable describes how bytes are transported.
5. **Never convert binary bytes into Strings.** Use `Resource`, `DataHandler`, or byte arrays.
6. **Choose the right multipart subtype.** Alternative for content versions, related for CID, mixed for independent attachments.
7. **Use typed APIs for headers and recipients.** Never concatenate subject, addresses, or Bcc into raw headers.
8. **Let the library encode subjects and filenames.** Do not craft encoded-words or filename parameters via string concatenation.
9. **Escape HTML and validate URLs by context.** Never use one escaping mechanism for every field.
10. **Inspect MIME source and mail clients.** Submission success does not prove display behavior.

## 20. Frequently Asked Questions

**Is MIME just the Content-Type header?** No. MIME includes part descriptions, transfer encoding, multipart boundaries, headers, and bodies. With multipart, boundaries and nested structures must remain consistent.

**Why shouldn't I generate boundaries manually?** Boundaries must be declared and used consistently in every delimiter, closed properly, and never collide with content. Jakarta Mail generates and serializes them automatically.

**Can I build MIME with Strings if there are only text and HTML?** Risks around CRLF, boundaries, charset, transfer encoding, and multipart semantics still apply. Using `MimeMessageHelper.setText(plain, html)` is simpler and safer.

**Should I base64-encode a file manually and paste it into the email?** No. Use `addAttachment` or `DataHandler` so the library creates the MIME part and transfer encoding.

**Does charset UTF-8 replace base64?** No. Charset specifies how characters decode; base64 is a byte representation in MIME.

**Why does a PDF get corrupted when sent?** A common cause is converting PDF bytes into a String or manually encoding/decoding incorrectly. Use `ByteArrayResource` or `FileSystemResource` with MIME type `application/pdf`.

**Can `multipart/alternative` contain a PDF attachment?** It should not. Alternative is for alternative versions of the same content. Independent attachments belong in a mixed structure.

**Do CID images need `multipart/related`?** That is the MIME structure used to describe HTML and its related resources. Let `MimeMessageHelper` select the appropriate multipart mode or build a related multipart with the Jakarta Mail object model when needed.

**Can Content-ID be set by adding a raw header?** At a low level via the part header API, yes, though you must control the value and keep it synchronized with `cid:` in HTML. Whenever possible, use `MimeMessageHelper.addInline(...)`.

**How does header injection happen?** When untrusted data containing CRLF is concatenated into a raw header, it can add or alter other headers. Use typed header APIs and validate input.

**Does Jakarta Mail automatically encode Vietnamese subjects?** Jakarta Mail APIs support proper header encoding when serializing messages. Use `setSubject(subject, "UTF-8")` or the helper instead of crafting encoded-words manually.

**Do Vietnamese attachment filenames work on all clients?** Unicode filename support varies across clients and implemented standards. Use the attachment API, test target clients, and consider safe ASCII names if broad compatibility is required.

**Does `send()` succeeding mean MIME rendered properly?** No. It usually only indicates the SMTP submission server accepted the message. Mail clients may still choose another alternative, block images, or display attachments according to their own policies.

**When should I use Jakarta Mail directly instead of MimeMessageHelper?** When specialized MIME structures or part manipulations are needed that the helper does not provide. Still use the object model rather than raw MIME strings.

## 21. Related Technical References

- **Spring Framework Mail — `MimeMessageHelper`:** building multipart messages, `setText(...)`, `addInline(...)`, `addAttachment(...)`.
- **Spring Framework Mail — `JavaMailSender`:** creating and sending `MimeMessage`.
- **Jakarta Mail:** `MimeMessage`, `MimeBodyPart`, `MimeMultipart`, `DataHandler`, and MIME serialization.
- **RFC 2045–2049 — MIME:** media types, transfer encoding, and multipart.
- **RFC 2046 — MIME Media Types:** multipart subtypes such as `mixed`, `alternative`, and `related`.
- **RFC 2183 — Content-Disposition:** `inline` and `attachment` metadata.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** non-ASCII parameters and filenames.
- **RFC 2392 — Content-ID and Message-ID URLs:** referencing resources via `cid:`.
- **RFC 5322 — Internet Message Format:** headers, folding, and message structure.

---

**Takeaway:** concatenating raw MIME manually easily causes bugs in boundaries, CRLF, charset, transfer encoding, binary attachments, multipart nesting, header injection, and filename encoding. In Spring Framework Mail, prefer `MimeMessageHelper` to build plain text/HTML bodies, inline resources, and attachments; when lower-level control is needed, use Jakarta Mail's `MimeBodyPart` and `MimeMultipart`. Let the library handle MIME serialization and SMTP transport, and inspect raw source alongside target mail clients before release.
