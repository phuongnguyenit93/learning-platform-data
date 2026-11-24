# Content-Type, charset, and Content-Transfer-Encoding

An email can contain Vietnamese text, HTML, images, PDF invoices, and multiple attachments. However, SMTP was originally designed around transporting text-based data with restrictions on characters and lines. **MIME (Multipurpose Internet Mail Extensions)** adds ways to describe content types, character encodings, and data representations so that diverse email systems can transmit and read messages accurately.

Three concepts need to be kept distinct:

- **`Content-Type`**: *what type of content* is this piece of data? Plain text, HTML, PDF, an image, or a multi-part container?
- **`charset`**: if this is text, *under which character encoding are the bytes interpreted as characters*? For example, `UTF-8`.
- **`Content-Transfer-Encoding`**: *in what form are the content's bytes represented for transport through the email environment*? For example, `quoted-printable` or `base64`.

The three pieces of information answer three different questions. Setting the right `charset` while declaring the wrong `Content-Transfer-Encoding` will still make a mail client display garbage; declaring `text/html` while passing malformed HTML content can also make the recipient see HTML code as plain text.

In **Spring Framework Mail**, `JavaMailSender` and `MimeMessageHelper` help construct properly formatted MIME messages. Understanding these headers helps you choose the right API and diagnose bugs such as lost diacritics, garbled characters, corrupted attachments, or broken HTML rendering.

## 1. From a Java String to the email the recipient sees

A `String` in Java holds Unicode characters at the string-model level. To send it over the protocol, the system must convert the string into bytes, optionally transform those bytes into a transport-safe representation, and then the receiving side performs the reverse process.

```text
Spring / Java application
   |
   | String: "Chào bạn"
   v
[MIME text part]
   |
   | charset=UTF-8: characters -> UTF-8 bytes
   v
  43 68 C3 A0 6F 20 62 E1 BA A1 6E
   |
   | Content-Transfer-Encoding: quoted-printable
   v
  Ch=C3=A0o b=E1=BA=A1n
   |
   | SMTP transports MIME-packaged content
   v
[Receiving system / Mail client]
   |
   | Decode quoted-printable -> recover bytes
   | Decode UTF-8 -> recover Unicode
   v
Reader sees: "Chào bạn"
```

This is the flow for **a text part**; if `base64` is used, the transport conversion differs, but the recovery process still has two steps. For PDF files or images, the system may use base64 to carry bytes over the wire, without interpreting those bytes as UTF-8 characters.

### Role of each header in an example

```eml
MIME-Version: 1.0
From: notifications@example.org
To: customer@example.net
Subject: Hello
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n
```

- `MIME-Version: 1.0` indicates the message uses MIME.
- `Content-Type: text/plain` states that this body is plain text.
- `charset=UTF-8` specifies how to map bytes to text characters.
- `Content-Transfer-Encoding: quoted-printable` states that the body on the wire must be quoted-printable decoded to recover the original bytes.

The snippet above is an example of a *raw MIME message*. The blank line between the headers and the body is part of the message structure. In an actual message, lines are separated according to email protocol conventions; line breaks in a Markdown editor are purely illustrative.

## 2. `Content-Type`: what kind of data is it?

`Content-Type` is a MIME header describing the **media type** of a content part. A value typically has the form:

```text
Content-Type: type/subtype; parameter=value
```

Where:

- `type` is the content category, such as `text`, `image`, `application`, or `multipart`.
- `subtype` specifies the exact type within that category, such as `plain`, `html`, `pdf`, or `mixed`.
- `parameter` provides additional information depending on the content type; most commonly `charset` for text and `boundary` for `multipart`.

Some common values:

| `Content-Type` | Meaning | Email scenario |
| --- | --- | --- |
| `text/plain; charset=UTF-8` | Plain text using UTF-8 | Order confirmation email in text format |
| `text/html; charset=UTF-8` | HTML content using UTF-8 | Transactional email styled with HTML |
| `multipart/alternative; boundary="..."` | Multiple alternative versions of the same content | Including both plain text and HTML |
| `multipart/mixed; boundary="..."` | Multiple independent components in the same message | Main message body with a PDF |
| `multipart/related; boundary="..."` | Parts with internal relationships | HTML referencing inline images via CID |
| `application/pdf` | PDF data | Attached invoice |
| `image/png` | PNG image data | Inline image or attachment |
| `application/octet-stream` | Binary bytes with no more specific type | Attachment whose exact media type is unspecified |

**`Content-Type` is not `Content-Disposition`.** `Content-Disposition: attachment` suggests the client should offer the file as an attachment, whereas `Content-Disposition: inline` suggests displaying it within the content when possible. `Content-Type` states *what the content is*; `Content-Disposition` relates to *how it is presented or handled*.

Example:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"
```

Here, PDF is the data type; `attachment` is how the file is attached to the email; `base64` is how the bytes are represented for transport.

### 2.1. How do `text/plain` and `text/html` differ?

The two contents below look similar when reading the source, yet ask for different rendering:

```text
Content-Type: text/plain; charset=UTF-8

<strong>Order confirmed</strong>
```

The mail client may display the literal characters `<strong>` and `</strong>` because the content is declared as **plain text**.

```text
Content-Type: text/html; charset=UTF-8

<strong>Order confirmed</strong>
```

The mail client may render the text in bold when it supports HTML and permits that rendering. Not all CSS properties, images, or scripts in HTML email are supported by clients; many clients actively restrict content for security and privacy reasons.

### 2.2. `multipart` is a container

`multipart/*` does not interpret the entire body as a single block of text or PDF. It indicates that the body contains **multiple MIME parts**, each with its **own headers**, its **own body**, separated by a `boundary` marker.

The types carry different meanings:

- **`multipart/alternative`:** alternative versions of the same message, typically text and HTML. The client picks the version it can and wants to display.
- **`multipart/mixed`:** a collection of separate parts, usually the main message body plus attachments.
- **`multipart/related`:** content with mutual relationships, such as HTML and inline images referenced via `cid:...`.

A message with HTML and an attached file can nest `multipart/alternative` inside `multipart/mixed`. When `MimeMessageHelper` is used properly, the library generates the structure and boundaries for the application.

### 2.3. `boundary` separates MIME parts

Simple example with two text/HTML versions:

```eml
MIME-Version: 1.0
From: store@example.org
To: customer@example.net
Subject: Order confirmed
Content-Type: multipart/alternative; boundary="alternative-123"

--alternative-123
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n, =C4=91=C6=A1n h=C3=A0ng =C4=91=C3=A3 x=C3=A1c nh=E1=BA=ADn.

--alternative-123
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Ch=C3=A0o b=E1=BA=A1n, <strong>=C4=91=C6=A1n h=C3=A0ng</strong> =C4=91=C3=A3 x=C3=A1c nh=E1=BA=ADn.</p>

--alternative-123--
```

The string `boundary="alternative-123"` is declared in the container's header. Each part starts with `--alternative-123`, and the marker `--alternative-123--` closes the multipart. In real messages, boundaries should be generated by the MIME library so they do not accidentally collide with inner data.

**Note:** each child part can declare a different `Content-Type`, `charset`, and `Content-Transfer-Encoding`. You must not assume all parts inherit the charset/encoding of the parent `multipart`.

## 3. `charset`: how characters and bytes are converted

**Character set / character encoding** defines the mapping between character sequences and stored or transported bytes. For text content, MIME usually declares it via the `charset` parameter in `Content-Type`:

```text
Content-Type: text/plain; charset=UTF-8
```

If the same sequence of bytes is read under different charsets, the recipient may see completely different characters from what the sender intended.

### 3.1. Why choose UTF-8?

**UTF-8** can represent Unicode, including accented Vietnamese, characters from many languages, and symbols. It is compatible with ASCII in the basic range, widely supported by modern systems, and is the standard choice for application emails.

Example string:

```text
Chào bạn
```

When UTF-8 encoded, the bytes in hexadecimal are:

```text
43 68 C3 A0 6F 20 62 E1 BA A1 6E
```

The letter `à` takes two bytes `C3 A0`; the letter `ạ` takes three bytes `E1 BA A1`. This shows that **character count, UTF-8 byte count, and character count after transfer encoding are not the same quantity**.

If the application produced UTF-8 bytes but a mail client mistakenly decoded them with a different encoding, the reader might see text like `ChÃ o` or replacement characters `�`. This case differs from seeing literal `=C3=A0`: the latter symptom suggests that quoted-printable has not been decoded.

### 3.2. Declared charset must match actual bytes

A MIME part with the header:

```text
Content-Type: text/plain; charset=UTF-8
```

must contain **UTF-8 encoded text bytes** after decoding transfer encoding. If the actual bytes were created using another charset while the header still says UTF-8, the mail client cannot reliably self-correct the mismatch.

Legacy charsets such as `ISO-8859-1`, `windows-1252`, or regional encodings can still appear in older emails. Only use them when compatibility with a data source using that encoding is genuinely required; do not rely on a mail client's charset-guessing heuristics.

In classic MIME, if `text/plain` omits `charset`, the standard default is `US-ASCII`. Some clients attempt to guess the encoding to render legacy messages, but results are inconsistent. Therefore, for Vietnamese text, always **declare `charset=UTF-8` explicitly**.

### 3.3. Charset only applies to data interpreted as text

An email attaching a PNG image:

```text
Content-Type: image/png
Content-Transfer-Encoding: base64
```

PNG bytes do not need a `charset=UTF-8` parameter. Likewise, PDF data or a ZIP archive does not somehow become “UTF-8 text” just because the Java application handles a file path or file name as a `String`.

Accented file names in MIME are instead a matter of **header parameter value encoding**, typically handled by the library using appropriate rules; do not concatenate raw UTF-8 bytes into headers assuming every client will understand them.

## 4. `Content-Transfer-Encoding`: how bytes are represented on the wire

Once text content has been turned into bytes according to a charset, MIME can use **Content-Transfer-Encoding (CTE)** to represent bytes in a form suitable for email transport.

Example header:

```text
Content-Transfer-Encoding: quoted-printable
```

This is **not** an algorithm for turning language into bytes, nor is it a compression or security encryption mechanism. Base64 or quoted-printable keeps nothing secret: any client can decode them.

| CTE | How it works | Suitable for | Notes |
| --- | --- | --- | --- |
| **`7bit`** | Body uses only data conforming to 7-bit email constraints | Simple ASCII text | Cannot represent non-ASCII UTF-8 bytes directly |
| **`8bit`** | Allows high-bit bytes in the body where the environment supports it | Text containing non-ASCII bytes when transport supports it | Usually requires infrastructure supporting `8BITMIME` |
| **`binary`** | Represents bytes without 7bit/8bit line constraints | Special environments supporting binary transport | Not a default choice for inter-domain email |
| **`quoted-printable`** | Keeps ASCII characters readable; other or special bytes encoded as `=HH` | Text content, especially when mostly ASCII | Must be decoded before applying charset |
| **`base64`** | Encodes all bytes using an ASCII alphabet | PDFs, images, ZIPs, and text with many non-ASCII bytes | Increases data size by roughly one-third, excluding line breaks |

### 4.1. `7bit`

`7bit` fits the traditional mail transport model when the body contains ASCII characters within protocol-permitted line limits. Example:

```eml
Content-Type: text/plain; charset=US-ASCII
Content-Transfer-Encoding: 7bit

Your order is confirmed.
```

If the body contains letters like `ă`, `ộ`, `ữ` in UTF-8, those bytes are no longer strictly within ASCII. You must not leave non-ASCII bytes as-is while claiming `7bit`.

### 4.2. `8bit` and `binary`

`8bit` permits high-bit bytes in the body when the transport path and SMTP servers support it. The SMTP `8BITMIME` extension lets clients and servers negotiate capability to handle 8-bit content. However, 8BITMIME support does not guarantee every hop, proxy, and client always handles every form of data accurately.

`binary` is less common, because transmitting unconstrained binary bytes also involves SMTP extensions such as `BINARYMIME` and `CHUNKING`. For ordinary application emails, let Jakarta Mail choose the appropriate MIME encoding rather than trying to push raw binary data directly.

**`8BITMIME` and `SMTPUTF8` are two distinct capabilities.** `8BITMIME` relates to 8-bit bytes of the message body on the SMTP wire; `SMTPUTF8` supports cases requiring UTF-8 in email components and internationalized addresses where traditional SMTP forbids them. An email with a UTF-8 Vietnamese body does not necessarily require SMTPUTF8 if the body is properly transfer-encoded and other components do not require that extension.

### 4.3. `quoted-printable`

Quoted-printable keeps most ASCII in a readable form. A byte needing encoding becomes `=` followed by two hexadecimal digits:

```text
UTF-8 bytes: C3 A0
QP:          =C3=A0
Character:   à
```

Full example:

```eml
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n
```

After decoding quoted-printable, the reader gets the UTF-8 bytes for `Chào bạn`; decoding UTF-8 reconstructs the character string.

In quoted-printable:

- `=HH` represents one byte with hexadecimal value `HH`.
- `=3D` represents the byte of the `=` sign when escaping is needed.
- An `=` at the **end of an encoded line** marks a *soft line break*: the next line continues the same content without adding a logical newline.
- Encoding trailing spaces or tabs at the end of a line must follow specific rules so they are not stripped by mail systems processing whitespace.
- Each encoded line is capped per quoted-printable rules, typically at most 76 characters including the encoded content, excluding CRLF.

Illustrative soft line break example:

```text
Don hang cua ban =
da duoc xac nhan.
```

After decoding, the snippet above represents a single line `Don hang cua ban da duoc xac nhan.`.

Quoted-printable is well suited when content is mostly ASCII and readability in raw message form is helpful. If most bytes are multibyte characters requiring escaping, size can also grow significantly.

### 4.4. `base64`

Base64 represents bytes using the ASCII character set `A-Z`, `a-z`, `0-9`, `+`, `/`, and padding `=`. It is suited for binary data and can also be used for text.

Simple example, the byte content of `Hello`:

```text
Original bytes (ASCII/UTF-8): 48 65 6C 6C 6F
Base64 representation:        SGVsbG8=
```

Corresponding MIME part:

```eml
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64

SGVsbG8=
```

The receiving side decodes base64 to recover bytes `48 65 6C 6C 6F`, then interprets them as UTF-8 to get `Hello`.

Base64 **is not security encryption**. The recipient or anyone inspecting the raw message can recover the original bytes. Base64 output length is approximately `4/3` of the input byte length, plus line-break characters when wrapped per MIME. In MIME, base64 data is wrapped into lines of no more than 76 characters.

Illustrative PDF example:

```eml
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKLi4u
```

The base64 string above represents only a few simulated leading bytes of PDF content, **not a complete PDF file**. The MIME library must encode all actual bytes of the attachment.

## 5. How the three factors work together and processing order

For a **text part**, the order on the sending side is:

```text
Unicode String in application
        |
        | 1. Choose Content-Type: text/plain or text/html
        v
Text characters
        |
        | 2. Charset: UTF-8
        v
UTF-8 bytes
        |
        | 3. Content-Transfer-Encoding:
        |    quoted-printable / base64 / ...
        v
SMTP-safe representation
        |
        v
Wire transport and email storage infrastructure
        |
        | 4. Decode transfer encoding
        v
UTF-8 bytes
        |
        | 5. Decode charset
        v
Text displayed by mail client
```

For binary files, there is no step turning PDF/PNG bytes into UTF-8 characters. The receiving system simply decodes transfer encoding to recover the **original file bytes**, then uses `Content-Type` along with the file extension or client capabilities to open the file.

**A common mistake:** applying base64 to a Java String, passing that base64 string into `MimeMessageHelper.setText(...)`, and also forcing the MIME part to `base64`. This can cause **double encoding**, making the recipient see a base64 string or corrupted data. Pass the **original content** to the library and let it handle charset/transfer encoding.

### An easy-to-remember mapping table

| Question | Answering component | Example |
| --- | --- | --- |
| Is the data text, HTML, an image, or a file? | `Content-Type` | `text/html` |
| Under which encoding do text bytes decode to characters? | `charset` of the text part | `UTF-8` |
| How are bytes safely represented over the email wire? | `Content-Transfer-Encoding` | `quoted-printable` |
| Should the file be presented as an attachment or inline? | `Content-Disposition` | `attachment; filename="a.pdf"` |
| How are multiple MIME parts separated? | `boundary` of `multipart` | `boundary="mix-123"` |

## 6. An email with text, HTML, and an attached PDF

Real-world emails often have **multiple nested MIME layers**. The following example shows a message with two ways of rendering the same content and a PDF:

```eml
MIME-Version: 1.0
From: billing@example.org
To: customer@example.net
Subject: Invoice
Content-Type: multipart/mixed; boundary="mixed-001"

--mixed-001
Content-Type: multipart/alternative; boundary="alt-001"

--alt-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n, vui l=C3=B2ng xem h=C3=B3a =C4=91=C6=A1n.

--alt-001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Ch=C3=A0o b=E1=BA=A1n, vui l=C3=B2ng xem <b>h=C3=B3a =C4=91=C6=A1n</b>.</p>

--alt-001--
--mixed-001
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQKLi4u

--mixed-001--
```

Explanation:

1. The outermost header is `multipart/mixed` because the message has a main content section and an attachment.
2. The first part is `multipart/alternative`: two versions `text/plain` and `text/html` carrying the same meaning.
3. Each text version declares its own `charset=UTF-8` and `quoted-printable`.
4. The PDF part declares `application/pdf`, `base64`, and `Content-Disposition: attachment`.
5. The two boundaries `mixed-001` and `alt-001` are independent; each structure has a closing marker ending with `--`.

The boundaries and PDF content in the example are illustrative only. When creating real emails, let **Jakarta Mail/Spring MimeMessageHelper** generate the structure, boundaries, and encodings for each part.

### Why not declare a single charset for the whole message?

A `multipart` message can contain UTF-8 text, a PNG image, and a PDF file. Charset only makes sense for **text parts**. A `multipart` container cannot use `charset=UTF-8` to turn all child parts into text. Each part carries formatting metadata matching its own data.

## 7. Spring Framework Mail: `JavaMailSender` and `MimeMessageHelper`

With Spring, the typical flow is:

```text
Business Service
       |
       v
JavaMailSender.createMimeMessage()
       |
       v
MimeMessageHelper
  - setText(...)
  - setSubject(...)
  - addAttachment(...)
       |
       v
Jakarta Mail builds MIME entities + headers + transfer encoding
       |
       v
JavaMailSender.send(mimeMessage)
       |
       v
SMTP server -> receiving system -> mail client
```

`JavaMailSender` is Spring Framework's mail-sending abstraction. `MimeMessage` and `MimeMessageHelper` are part of working with MIME for richer emails. `MimeMessageHelper` takes a charset on initialization and helps structure multipart messages and attachments.

### 7.1. Dependency in Spring Boot

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

An example `application.yml` using SMTP submission and default encoding configuration:

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
```

`spring.mail.default-encoding` is the default setting provided by Spring Boot for outgoing mail. Choose the SMTP connection settings and secret values according to the actual server. **This configuration does not replace declaring the proper `Content-Type` when constructing MIME parts.**

If using plain Spring Framework, you need to configure the `JavaMailSender` implementation, Jakarta Mail, and corresponding default encoding yourself.

### 7.2. Sending HTML with proper Content-Type and UTF-8

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String to) throws MessagingException {
        MimeMessage mime = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mime, StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.org");
        helper.setTo(to);
        helper.setSubject("Welcome to the system");
        helper.setText(
                "<h1>Hello!</h1><p>Thank you for registering.</p>",
                true
        );

        mailSender.send(mime);
    }
}
```

Here:

- The `UTF-8` parameter in `MimeMessageHelper`'s constructor instructs the helper to use UTF-8 charset when creating relevant text parts.
- `setText(html, true)` marks the body as **HTML**, resulting in `Content-Type: text/html` for the content part.
- `setSubject(...)` accepts a Unicode String; Jakarta Mail handles encoding the header appropriately when needed.
- Choosing `quoted-printable` or `base64` for transfer encoding may be decided by Jakarta Mail based on the payload and related properties. **Do not assume a fixed CTE simply because UTF-8 was chosen.**

The address `notifications@example.org` is only an example; in deployment you must use a sender address permitted by the SMTP server.

### 7.3. Sending both text and HTML with `multipart/alternative`

A mail client may not support or want to render HTML. A transactional email usually includes a text version as well:

```java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, StandardCharsets.UTF_8.name()
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Order confirmation");

String plain = "Hello. Your order has been confirmed.";
String html = "<p>Hello. Your <strong>order</strong> has been confirmed.</p>";

helper.setText(plain, html);
mailSender.send(mime);
```

The `setText(plainText, htmlText)` method requests a MIME multipart containing two alternatives for the same message. The actual structure is built by the helper and Jakarta Mail, so there is no need to concatenate `boundary` strings manually.

**Both versions must convey the same business information.** If the HTML version contains an important action link that the text version omits completely, users choosing text-only may be unable to perform the required action.

### 7.4. HTML, text, and an attached PDF

Example building a message with two text versions and a PDF:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;

public void sendInvoice(
        JavaMailSender mailSender,
        String recipient,
        byte[] invoicePdf
) throws MessagingException {
    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("billing@example.org");
    helper.setTo(recipient);
    helper.setSubject("Your invoice");
    helper.setText(
            "Hello. Your invoice is in the attached file.",
            "<p>Hello. Your <strong>invoice</strong> is in the attached file.</p>"
    );
    helper.addAttachment(
            "invoice.pdf",
            new ByteArrayResource(invoicePdf),
            "application/pdf"
    );

    mailSender.send(message);
}
```

In this example:

- The text parts are processed using UTF-8.
- Text/HTML are grouped as alternative versions.
- The PDF part carries the raw bytes from `invoicePdf`; the MIME layer encodes the binary part for transport, typically base64.
- File name and `Content-Type`/`Content-Disposition` information are generated by the helper based on the `addAttachment` call.

`ByteArrayResource` fits examples where PDF bytes are already in memory. For large files, consider using `FileSystemResource` or an appropriate data source to avoid holding unnecessary byte copies.

**Do not turn `invoicePdf` into a Java String and call `setText(...)`.** Binary bytes of a PDF must be preserved as file data.

## 8. Subject headers and attachment names also have their own encoding rules

`charset=UTF-8` on `Content-Type` only declares the charset of **the corresponding body part**; it does not automatically describe header fields such as `Subject` or `filename`.

In traditional MIME, header values containing non-ASCII characters may require **encoded-word** syntax, for example:

```text
Subject: =?UTF-8?B?Q2jDoG8=?=
```

The example string is the subject `Chào` encoded in encoded-word form. The `B` marker here indicates base64 **used inside header-encoding syntax**, not a body `Content-Transfer-Encoding: base64` header. Encoded-word also has a `Q` variant, related to quoted-printable though its rules are not identical to body transfer encoding (for example, underscores have special meaning in `Q` encoded-words).

Attachment file names with diacritics such as `hóa-đơn.pdf` are another case: the `filename` parameter value can be encoded using mechanisms for MIME header parameters, such as the extensions in RFC 2231. How the file name is displayed also depends on the mail client.

In Spring code, pass ordinary Unicode Strings to `setSubject(...)` and `addAttachment(filename, ...)` so the library performs the appropriate encoding. **Do not manually base64-encode the entire subject and pass it directly as the subject**, as this easily causes the mail client to display a meaningless string or double-encode it.

## 9. Common display bugs and how to trace them

| Symptom seen by recipient | Likely cause | What to inspect |
| --- | --- | --- |
| Sees `ChÃ o` instead of `Chào` | UTF-8 bytes interpreted under a different charset | `Content-Type` of the exact text part, bytes after decoding CTE, and byte source |
| Sees literal `Ch=C3=A0o` | Quoted-printable not recognized/decoded as expected | `Content-Transfer-Encoding` and the MIME part containing the body |
| Sees `SGVsbG8=` instead of `Hello` | Base64 treated as raw text or double-encoded | CTE header, how the application prepares the payload |
| HTML shows literal tags `<p>`, `<strong>` | Declared `text/plain` or called `setText(html, false)` | Media type and `isHtml` parameter |
| Accented characters appear as `?` | Characters lost during encoding with an unsupported charset | Source charset, byte conversion, and MIME charset |
| Attachment reports corrupted file on open | Original bytes altered, wrong transfer encoding, or source file already corrupt | Original size/file, MIME part, and decoding process |
| Attachment renders as long text | File part has wrong `Content-Type`/`Content-Disposition` or was placed into text body by mistake | Use `addAttachment` and inspect part headers |
| Attachment file name loses diacritics | `filename` parameter encoded incompatibly or decoded wrongly | Attachment-building library, mail client, and raw MIME headers |
| Sees only part of HTML or broken layout | Incorrect MIME multipart/alternative/related or HTML unsupported by client | MIME structure and HTML email compatibility |
| Mail client fails to split parts | Wrong boundary, missing closing marker, or manual editing | `Content-Type: multipart` and delimiters |

### 9.1. Inspecting the right MIME part

For a simple email, there may be only one outermost `Content-Type`. But for a message with attachments, the outermost header is usually `multipart/*`, while `charset=UTF-8` lives on the **inner text parts**. Looking only at the outermost header and concluding “the email does not have UTF-8” easily leads to misdiagnosis.

A systematic way to read a raw message:

1. Inspect the outermost headers: `MIME-Version` and `Content-Type`.
2. If multipart, read `boundary` and locate each MIME part.
3. For each part, identify `Content-Type` and the `charset` parameter if it is text.
4. Check `Content-Transfer-Encoding` of **that specific part**.
5. Decode CTE into bytes, then apply the charset to interpret text bytes.
6. If it is an attachment, compare decoded bytes against the original file source.

You do not need to know the SMTP password to inspect these three MIME headers: they are properties of the **message**, not mail-sending credentials.

### 9.2. Why can setting the right charset still fail?

For example, the application reads a template file containing UTF-8 bytes yet uses an API that defaults to decoding the file as `ISO-8859-1`. At that point, the Java `String` already holds wrong characters *before* being passed into `MimeMessageHelper`. Configuring `UTF-8` for the email only encodes **that corrupted string** consistently; it cannot recover the original text.

Therefore, examine the entire pipeline:

```text
Template file / Database / API
         |
         | Read source with the right charset
         v
Java String with correct content
         |
         | MimeMessageHelper UTF-8
         v
MIME bytes + CTE
         |
         v
Mail client
```

A character error can originate at the **data source**, the **charset conversion step**, the **MIME declaration**, or **client-side decoding**.

### 9.3. Do not edit MIME by string-replacing the raw message

Operations like replacing all `Content-Type: text/plain` with `text/html`, changing `boundary` via find-and-replace, or editing `quoted-printable` after the library has packaged it can make the entire message inconsistent. Instead of patching raw MIME with text replacement, set the right content via `MimeMessageHelper` methods.

## 10. Frequently confused protocol details

### 10.1. MIME encoding is not SMTP dot-stuffing

In traditional SMTP, when a client sends content after the `DATA` command, a line containing only a single dot `.` marks the end of data; lines starting with a dot are handled via **dot-stuffing** so they are not mistaken for the end of the message.

This is an **SMTP framing** rule, distinct from a MIME part's `Content-Transfer-Encoding`. SMTP libraries typically handle dot-stuffing automatically; applications should not manually insert dots when generating message text.

### 10.2. `Content-Transfer-Encoding` is not HTTP's `Content-Encoding`

HTTP has concepts like `Content-Encoding: gzip` to indicate a data representation transformation. In MIME email, `Content-Transfer-Encoding` addresses transporting bytes across the mail wire, usually via base64 or quoted-printable.

Similar names do not make them equivalent. `base64` is also not gzip and provides no security.

### 10.3. Email HTML does not always behave like web HTML

`Content-Type: text/html` only tells the mail client that the part is HTML. The mail client may strip scripts, alter CSS, block remote images, or fall back to the text version. No MIME header forces all clients to render an email identically to a browser.

### 10.4. MIME encoding may be chosen automatically by the library

Two emails both having `Content-Type: text/plain; charset=UTF-8` may respectively use `quoted-printable` and `base64`. Both are valid if the content is encoded and decoded according to the headers. Rely on **the semantics of the recovered data**, rather than treating one specific raw representation as mandatory.

## 11. Applied scenarios

### Scenario A: Vietnamese email renders “ChÃ o”

The application sends the string `Chào bạn` yet the recipient sees `ChÃ o báº¡n`.

**Analysis:** inspect the source creating the string, bytes generated at the charset step, the `Content-Type` header of the text part, and how the client decodes it. `Content-Transfer-Encoding` may be completely valid; the bug occurs because UTF-8 bytes are interpreted under another encoding.

### Scenario B: Declared `UTF-8` yet the body has `=E1=BA=AD`

Inspecting the raw message shows `Content-Type: text/plain; charset=UTF-8`, `Content-Transfer-Encoding: quoted-printable`, and many `=HH` sequences.

**Analysis:** this can be completely standard-compliant data. Quoted-printable is designed to represent bytes that way. The mail client decodes CTE first and only then decodes UTF-8.

### Scenario C: HTML email displays tags as text

The service calls `helper.setText("<h1>Hello</h1>", false)`.

**Analysis:** the `false` parameter declares the content as plain text. To make the content HTML, use `helper.setText(html, true)`. To support both rendering modes, use `helper.setText(plain, html)`.

### Scenario D: PDF file cannot be opened

A service converts the PDF's `byte[]` into `new String(pdfBytes, UTF_8)` and passes it as the message body.

**Analysis:** PDF bytes are not UTF-8 text. Forcing a decode into a Java String can corrupt invalid byte sequences. Keep the original bytes and call `helper.addAttachment("invoice.pdf", new ByteArrayResource(pdfBytes), "application/pdf")`.

### Scenario E: Changing only the outermost `Content-Type` fails to fix accented characters

The message has `Content-Type: multipart/mixed`, while inside it the text part wrongly declares `charset=US-ASCII`.

**Analysis:** charset must be checked and declared on the **actual text part**, rather than applying a single charset to handle both the container and attachments.

### Scenario F: Subject has garbled accents while the body is fine

The body part is declared `text/plain; charset=UTF-8` and renders properly; only `Subject` is broken.

**Analysis:** subject belongs to the **message header**, which uses separate header-encoding rules; body `Content-Type` and CTE do not directly encode the subject. Let Jakarta Mail handle Unicode subjects via `MimeMessageHelper.setSubject(...)`.

## 12. Key principles to remember when writing Spring Mail

1. **Specify the right media type:** plain text uses `text/plain`; HTML uses `text/html`; PDF uses `application/pdf`.
2. **Use UTF-8 for Vietnamese text:** configure default encoding when needed and pass UTF-8 into `MimeMessageHelper`.
3. **Separate charset from transfer encoding:** charset governs **characters ↔ bytes**; CTE governs **bytes ↔ wire representation**.
4. **Do not pre-encode data passed to Jakarta Mail:** normally pass the original content and attachments to the helper.
5. **Read per MIME part:** metadata on a multipart container does not replace headers of inner text/attachment parts.
6. **Choose the right API:** `setText(text, false)` for text, `setText(html, true)` for HTML, `setText(plain, html)` for two versions, `addAttachment(...)` for files.
7. **Use raw MIME for diagnosis:** check `Content-Type`, `charset`, `Content-Transfer-Encoding`, `boundary`, and part structure; do not jump to conclusions solely from strings printed in logs.

In a properly formatted email, **`Content-Type` describes the meaning of the content part, `charset` interprets text bytes, and `Content-Transfer-Encoding` helps bytes traverse mail infrastructure safely**. These three layers work together, and `MimeMessageHelper` helps a Spring application build them without assembling raw MIME by hand.
