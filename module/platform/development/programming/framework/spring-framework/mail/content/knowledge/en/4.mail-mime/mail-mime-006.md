# Boundary and how parts are separated

A plain-text-only email can usually be represented by a single body part. However, a notification email in a Spring application can simultaneously contain a **plain text version**, an **HTML version**, **images displayed inside HTML**, and an **attached PDF file**. The receiver needs to know which part is the message body, which part is a file, and where each part begins and ends.

**MIME (Multipurpose Internet Mail Extensions)** extends the email format to represent multiple content types. When an email has multiple components, MIME uses a `multipart/*` content type and a delimiter string called a **boundary**. Boundaries act as structured dividing lines between message parts so the receiving program can separate and read each part accurately.

In **Spring Framework Mail**, when using `JavaMailSender`, `MimeMessage`, and `MimeMessageHelper`, we normally **do not create boundaries manually**. The Jakarta Mail library takes care of generating and inserting the appropriate delimiters into the message. Nevertheless, understanding boundaries is very useful when reading raw emails, diagnosing broken attachments, distinguishing HTML from inline images, and finding why an email renders incorrectly.

## 1. From a single-part email to a multi-part email

An email has two major regions:

- **Message headers**: contain fields such as `From`, `To`, `Subject`, `MIME-Version`, and `Content-Type`.
- **Message body**: contains the content. The body can be a single text part or a multi-part structure separated by boundaries.

With simple content:

~~~text
From: notice@example.org
To: reader@example.net
Subject: Hello
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hello, your account is ready.
~~~

The blank line between headers and body separates **the top of the email** from **the email body**. In this example, `Content-Type: text/plain` states that the body is plain text, so **no boundary is needed**.

By contrast, when an email has both HTML and an attachment, the body is no longer one uniform block of text. The mail reader must recognize a list of smaller parts. In that case, the header may contain:

~~~text
Content-Type: multipart/mixed; boundary="mail_outer_8d42"
~~~

The pieces of information on this line have distinct meanings:

| Component | Meaning |
| --- | --- |
| `Content-Type` | MIME field indicating the structure or content type of the body. |
| `multipart/mixed` | Body consists of multiple independent parts, commonly used when attachments are present. |
| `boundary=...` | Parameter declaring the string used to identify part-delimiter lines. |
| `"mail_outer_8d42"` | Illustrative boundary value; the quotation marks enclosing the value in the header are not part of the boundary string itself. |

A boundary is **a parameter of `Content-Type` on the enclosing container**. It is not an email address, a file name, an SMTP port, or an encryption mechanism.

## 2. Exact syntax of delimiter lines

Suppose the outer container declares:

~~~text
Content-Type: multipart/mixed; boundary="mail_outer_8d42"
~~~

The boundary value is `mail_outer_8d42`. Delimiters in the body are formed by the rule:

~~~text
--mail_outer_8d42       ← opens the first part
...first part content...

--mail_outer_8d42       ← opens the next part
...next part content...

--mail_outer_8d42--     ← closes the entire list of parts
~~~

Distinguish between **the boundary value** and **a delimiter line**:

| Component | Syntax | Role |
| --- | --- | --- |
| Header value | `boundary="mail_outer_8d42"` | Declares the identifying string. |
| Normal delimiter | `--mail_outer_8d42` | Ends the previous part and begins the next part. |
| Closing delimiter | `--mail_outer_8d42--` | Ends the current multipart region; two extra hyphens go **at the end**. |

The two `--` hyphens at the **start** of a delimiter line are mandatory markers defined by MIME; they are **not inside the value** of the `boundary` parameter in this example. The two `--` hyphens at the **end** appear only on the closing delimiter. Therefore:

- `--mail_outer_8d42` is a part-opening boundary marker;
- `--mail_outer_8d42--` is the closing marker of the multipart region;
- `mail_outer_8d42` appearing alone in text is **not** a MIME delimiter line.

Boundary characters are case-sensitive. A delimiter is recognized by the exact string declared by the header.

### Position and newline characters

In standard MIME data, lines use **CRLF** (`\r\n`) line endings. A delimiter line must sit at the start of a line and follow valid syntax. Under MIME rules, the CRLF immediately preceding a delimiter is treated as attached to the delimiter, not necessarily as a blank line belonging to the preceding content. This matters when extracting binary data or checking encoded content lengths.

The example blocks in this document display line breaks in ordinary Markdown style for readability. When sending real mail, **the MIME library normalizes line endings and constructs the structure**. Do not concatenate arbitrary text strings and guess how email readers detect parts.

## 3. Complete example: HTML + text + one attachment

Consider a message with two display forms for the body and an attached `note.txt` file. This is **illustrative MIME data**, not content sent from a live system.

~~~text
From: notice@example.org
To: reader@example.net
Subject: Your report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer_8d42"

This is a multipart message.
--outer_8d42
Content-Type: multipart/alternative; boundary="inner_53b7"

--inner_53b7
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Your report is ready.
--inner_53b7
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<p>Your <strong>report</strong> is ready.</p>
--inner_53b7--
--outer_8d42
Content-Type: text/plain; name="note.txt"
Content-Disposition: attachment; filename="note.txt"
Content-Transfer-Encoding: base64

SGVsbG8K
--outer_8d42--
~~~

The message contains **two nested multipart layers**:

~~~mermaid
flowchart TD
    A["multipart/mixed — outer_8d42"] --> B["multipart/alternative — inner_53b7"]
    A --> E["attachment — note.txt"]
    B --> C["text/plain"]
    B --> D["text/html"]
~~~

### Reading the example layer by layer

**Outer layer: `multipart/mixed`.** The message header declares `outer_8d42`. Hence, `--outer_8d42` identifies each part directly belonging to the outer layer. Here, the first part is an alternative content group, and the second part is the attached file. `--outer_8d42--` closes the outer layer.

**Inner layer: `multipart/alternative`.** The first part of the outer layer has its own header:

~~~text
Content-Type: multipart/alternative; boundary="inner_53b7"
~~~

This part contains two representations of the same information: `text/plain` and `text/html`. The mail reader can pick the suitable display format; the two parts are not automatically two separate messages. The `--inner_53b7--` line only closes the **alternative group**; afterward, the parser continues processing the next part belonging to `outer_8d42`.

**Attachment part.** The `note.txt` file is declared as `text/plain`, has `Content-Disposition: attachment`, and is encoded with `base64` for message-format-safe transport. The string `SGVsbG8K` is merely illustrative Base64 data for a tiny text file; it is not a boundary.

### Why are two different boundaries needed?

If both the outer and inner layers used the same boundary, the parser would encounter boundary lines whose scope is ambiguous. Every `multipart` region must have its **own boundary**, avoiding confusion with delimiters of parent layers, child layers, or actual payload data. Upon encountering `--inner_53b7--`, the reader finishes the inner group and resumes the outer layer.

Tree-structured boundaries let MIME represent multiple content layers without “flattening” everything into a single list.

## 4. What does a MIME part contain?

Inside a `multipart` region, each part typically has the structure:

~~~text
--some_boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
Content-Disposition: inline

...content of this part...
~~~

Right after the delimiter, header lines dedicated to the **child part** appear; a blank line marks where the child part's body starts. A part's headers do not necessarily match the whole email's headers.

| MIME field inside a part | What is it used for? |
| --- | --- |
| `Content-Type` | Specifies the part's content type, e.g., `text/plain`, `text/html`, `image/png`, `application/pdf`, or `multipart/related`. |
| `Content-Transfer-Encoding` | Specifies how the part's data is represented in the message, e.g., `base64` or `quoted-printable`. |
| `Content-Disposition` | Suggests how to handle the part: `inline` to display within content or `attachment` to treat as attached. |
| `Content-ID` | Assigns an identifier to a part, commonly used when HTML references inline images or resources via `cid:`. |
| `Content-Type: ...; name=...` | Can carry a suggested name for the resource; for attachments, also check `filename` on `Content-Disposition`. |

Not every part needs all of these headers. A `multipart` part is a **container of child parts**, so it itself has `Content-Type: multipart/...; boundary=...` and contains delimiters inside its body. An ordinary `text/plain` part has a text body and needs no boundary declaration of its own.

**Splitting by boundary** and **decoding content** are two separate jobs. A MIME reader first identifies which parts belong to the enclosing container, then uses `Content-Transfer-Encoding` and `Content-Type` to interpret each part's data.

## 5. Common multipart types and the role of boundaries

Boundaries use one shared syntactic mechanism, while the **multipart type** defines the relationship among child parts.

| Type | Common meaning | Typical reading behavior |
| --- | --- | --- |
| `multipart/mixed` | Multiple independent parts in sequence; usually combines primary content and attachments | Display the body while offering attachments for download |
| `multipart/alternative` | Multiple ways of expressing **the same content** | Pick the version matching reader capabilities; typically plain text and HTML |
| `multipart/related` | Parts related to form one composite piece of content | HTML referencing attached images or resources via `cid:` |
| `multipart/signed` | Container holding content and signature in an appropriate security format | Requires a signature processor to verify; boundaries still merely separate parts |
| `multipart/encrypted` | Container holding control info and encrypted data per an appropriate protocol | Boundaries do not encrypt anything themselves; corresponding cryptographic mechanisms are needed |

### `multipart/alternative`

Example of an email with both plain text and HTML versions:

~~~text
Content-Type: multipart/alternative; boundary="alt_q91"

--alt_q91
Content-Type: text/plain; charset=UTF-8

Your booking is confirmed.
--alt_q91
Content-Type: text/html; charset=UTF-8

<p>Your <strong>booking</strong> is confirmed.</p>
--alt_q91--
~~~

The parts express the same information at different formatting levels. Under common organization, the simpler form such as `text/plain` appears first, followed by the richer form such as `text/html`. The reader can pick whichever version it supports best instead of displaying both sequentially.

### `multipart/mixed`

When an email has attached documents, `multipart/mixed` is usually the top-level container:

~~~text
multipart/mixed
├── message body part
├── attachment: invoice.pdf
└── attachment: terms.txt
~~~

Each part can have its own `Content-Type` and `Content-Disposition`. Readers do not infer attachments merely from boundary names.

### `multipart/related` and inline images

An HTML email with an inline logo image can be organized as follows:

~~~text
Content-Type: multipart/related; boundary="rel_x4"

--rel_x4
Content-Type: text/html; charset=UTF-8

<html><body><img src="cid:brand-logo"></body></html>
--rel_x4
Content-Type: image/png
Content-ID: <brand-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

...Base64-encoded image data...
--rel_x4--
~~~

`cid:brand-logo` in HTML references the part with `Content-ID: <brand-logo>`. The image is **a separate MIME part**, linked by Content-ID. The boundary helps locate the boundaries of the image part, whereas HTML placing the image at the display position relies on `cid:` and `Content-ID`.

Email readers and security policies can affect image rendering. Adding an image to MIME does not guarantee every mail application renders it identically.

## 6. How is a boundary chosen?

Typically, a library generates a value distinct enough not to appear accidentally as a delimiter line inside wrapped data.

A valid boundary must follow MIME syntax rules; per RFC 2046, the value is **no longer than 70 characters** (excluding the two `--` hyphens of delimiters), uses permitted characters, and does not end with a space. The value may be enclosed in quotes when declared as a header parameter. In practice, use simple ASCII strings and let the library choose them rather than designing them yourself.

For example, two independent messages can have different boundaries:

~~~text
boundary="----=_Part_842_1234567890"
boundary="----=_Part_843_1234567891"
~~~

Even with a boundary string starting with hyphens like above, **the delimiter still gets two `--` hyphens prepended**:

~~~text
------=_Part_842_1234567890
~~~

Do not strip the leading two hyphens from the boundary value when reading a header. Only the rule of prepending `--` applies when forming a delimiter line.

### Boundaries must avoid colliding with data

Suppose a text part unexpectedly contains the exact line:

~~~text
--outer_8d42
~~~

while the container uses `outer_8d42` as its boundary. A MIME parser may treat that as a part split point, causing data to be misread. Therefore, the boundary must be chosen so it does not match any delimiter line inside contained parts; boundaries of nested multiparts must also be distinct and unambiguous.

This is one reason to let Jakarta Mail generate MIME: boundary selection and encoding must happen consistently with the message's data.

## 7. What are preamble and epilogue?

MIME allows content before the first delimiter and after the closing delimiter:

~~~text
Content-Type: multipart/mixed; boundary="demo_123"

This message uses MIME multipart.
--demo_123
Content-Type: text/plain

Hello.
--demo_123--
Optional text after the final delimiter.
~~~

- **Preamble**: the text region after the multipart's headers but **before** the first `--demo_123` line.
- **Epilogue**: the text region **after** the `--demo_123--` line closing the multipart.

MIME readers typically ignore both when assembling part contents. Historically, the preamble provided a hint for software lacking MIME support; it is **not the first part**. Nor is the epilogue an extra attachment.

When inspecting raw messages yourself, do not mistake the preamble for the email's `text/plain` or assume text after the closing boundary is a new part.

## 8. How do boundaries and Content-Transfer-Encoding relate?

SMTP and traditional email formats were originally built around line-oriented text data. MIME may need to carry PDFs, images, or text with many non-ASCII characters. Hence, each part can declare how its data is transformed into a transport-friendly form.

Example:

~~~text
--file_20
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="guide.pdf"

JVBERi0xLjQKJ...
--file_20--
~~~

`base64` states that the file data is represented using text characters; upon receipt, the processor decodes that string to recover the file's bytes. Meanwhile, `--file_20--` is the delimiter closing the **container**, not Base64 data.

Points to remember:

1. **Boundaries operate on MIME structure**, marking where a part begins and ends.
2. **Content-Transfer-Encoding operates on a single part's data**, specifying how to read and decode the extracted body.
3. **Content-Type and charset** instruct how to interpret data after decoding, such as UTF-8 text or a PNG image.
4. **Content-Disposition/Content-ID** help the reader decide whether the part is a file, an inline resource, or another display option.

With `quoted-printable`, specific characters can be represented using an equals sign and byte codes, suitable for text with mostly ordinary characters. With `base64`, binary data is represented as a character sequence safer for mail transport environments. Never infer displayed content directly from encoded strings without decoding and knowing the charset.

**Never place a delimiter inside a Base64 string expecting the reader to guess**. Boundaries must appear at the exact positions in the MIME structure dictated by the container.

## 9. Multipart detection and parsing mechanism

You can visualize how a MIME parser processes a message:

~~~mermaid
flowchart TD
    A["Read MIME entity headers"] --> B{"Is Content-Type multipart?"}
    B -->|"No"| C["Decode/interpret body per Content-Type and encoding"]
    B -->|"Yes"| D["Extract boundary parameter"]
    D --> E["Find first delimiter line"]
    E --> F["Read headers of next part"]
    F --> G{"Is part multipart?"}
    G -->|"Yes"| H["Recursively parse with its own boundary"]
    G -->|"No"| I["Read body up to container delimiter"]
    H --> J{"Next delimiter?"}
    I --> J
    J -->|"Normal delimiter"| F
    J -->|"Closing delimiter"| K["End container; return to parent"]
~~~

This is a conceptual model. Real parsers must conform to syntax rules for headers, lines, encoding, nested parts, and resource limits. A naive search with `split("--boundary")` is insufficient to implement a compliant MIME parser because it can slice content erroneously, mishandle CRLF, confuse closing delimiters, or misparse nested parts.

Within an email, **each multipart level uses the exact boundary declared in that level's header**. A parent level's delimiter does not replace a child level's delimiter. When a child level closes, the parser resumes processing the parent structure.

## 10. How does Spring Framework Mail create multiparts and boundaries?

Spring Framework Mail provides `MimeMessageHelper` to build MIME messages conveniently. Developers usually specify the **logical content** — text, HTML, images, files — and let Jakarta Mail handle serialization, including headers, boundaries, and delimiters.

### 10.1. Example: an email with plain text, HTML, inline image, and PDF

Suppose the application has two resources on the classpath:

~~~text
src/main/resources/mail/logo.png
src/main/resources/mail/guide.pdf
~~~

We can write a service:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class GuideMailService {
    private final JavaMailSender mailSender;

    public GuideMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendGuide(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject("User guide");

        String plainText = "The user guide is attached.";
        String htmlText = """
                <html>
                  <body>
                    <p>The user guide is attached.</p>
                    <img src="cid:brandLogo" alt="Logo">
                  </body>
                </html>
                """;

        // Two representations of the same content.
        helper.setText(plainText, htmlText);

        // Add inline resource after setting HTML.
        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        // Independent file attached to the email.
        helper.addAttachment(
                "guide.pdf",
                new ClassPathResource("mail/guide.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Deployment notes for the example: the sender address must be permitted by the SMTP provider; the resource files must actually exist on the classpath at runtime; the SMTP server and credentials must be configured separately. The example demonstrates MIME composition rather than describing a production-ready email service.

Notable points in the code:

- `mailSender.createMimeMessage()` creates a Jakarta Mail MIME object.
- The `MULTIPART_MODE_MIXED_RELATED` mode organizes a composite container with related content parts and attachment parts.
- `helper.setText(plainText, htmlText)` supplies two text representations to construct an appropriate `multipart/alternative` structure.
- `helper.addInline("brandLogo", ...)` registers an inline image with a Content-ID referenced by HTML as `cid:brandLogo`.
- `helper.addAttachment(...)` adds a file as an attached MIME part.
- When `mailSender.send(message)` runs, Jakarta Mail finalizes the MIME representation for transport, including boundaries for the required multiparts.

Do not assume exact boundary strings or the ordering of every header Jakarta Mail will generate. They can vary by version, multipart mode, payload characteristics, and save/send behavior. What matters is that the parts and MIME relationships are constructed accurately.

### 10.2. Why not set boundaries manually in Java code?

Normally, the application simply calls:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brandLogo", logoResource, "image/png");
helper.addAttachment("guide.pdf", pdfResource, "application/pdf");
~~~

Manually setting `Content-Type: multipart/mixed; boundary=...` while still letting the helper generate the body can cause **the value in the header not to match the delimiter generated in the body**. The reader then cannot locate parts properly, even though Java code prepared all files and HTML.

Likewise, writing `--boundary` lines into HTML or plain text strings does not create additional MIME parts: they are just text characters in the current part unless the MIME builder established the corresponding container structure. Let `MimeMessageHelper` or dedicated Jakarta Mail APIs manage the structure instead of raw string concatenation.

### 10.3. Choosing MimeMessageHelper's multipart mode

`MimeMessageHelper` provides multiple multipart modes depending on requirements and mail-reader compatibility:

| Mode | General meaning |
| --- | --- |
| `MULTIPART_MODE_NO` | Does not construct a multipart structure; suitable when no inline resources or attachments are needed. |
| `MULTIPART_MODE_MIXED` | Uses `multipart/mixed` structure, typically serving attachment parts. |
| `MULTIPART_MODE_RELATED` | Uses `multipart/related` structure to attach resources related to the primary content. |
| `MULTIPART_MODE_MIXED_RELATED` | Organizes a combination of `mixed` and `related` regions for HTML/inline content along with attachments. |

When creating the helper with the boolean constructor, e.g., `new MimeMessageHelper(message, true, "UTF-8")`, Spring picks the helper's default multipart mode. Using an explicit mode constant expresses intent clearly when structural control matters.

### 10.4. Call order of setText and addInline

When HTML references images using `cid:`, **call `setText(...)` first, then call `addInline(...)`**. This ordering avoids issues where some mail readers fail to resolve inline references.

If there are attachments, `addAttachment(...)` creates the corresponding part and sets the required MIME headers. File names with non-ASCII characters may need proper header encoding; library APIs handle these requirements better than concatenating headers manually.

## 11. Distinguishing MIME boundaries from SMTP DATA termination

A boundary is **not** the end-of-message marker of an SMTP session. These are two separate protocol layers:

- **MIME:** `--some_boundary` and `--some_boundary--` separate parts inside **one email**.
- **SMTP DATA:** when sending mail over standard SMTP, a line containing only a single dot (`.`) — i.e., `<CRLF>.<CRLF>` — terminates the message data transmission of the `DATA` command.

Illustrative example:

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: Content-Type: multipart/mixed; boundary="abc123"
C:
C: --abc123
C: Content-Type: text/plain
C:
C: Hello
C: --abc123--
C: .
S: 250 Message accepted
~~~

`--abc123--` closes the multipart structure **inside the email payload**. The `.` line ends **SMTP DATA** so the SMTP server knows the client has finished transmitting the message. If the content itself has a line starting with a dot, SMTP also has **dot-stuffing** rules to prevent misinterpreting it as end of DATA; that too belongs to the SMTP transport layer, separate from MIME.

Similarly, STARTTLS only protects the SMTP channel; it does not govern how multiparts are divided in the body. An email can have the exact same MIME structure regardless of whether the SMTP connection uses TLS.

## 12. Common mistakes with boundaries

### 12.1. Declared boundary and delimiter do not match

For example, the header says:

~~~text
Content-Type: multipart/mixed; boundary="part_A"
~~~

yet the body uses:

~~~text
--part_B
Content-Type: text/plain

Hello
--part_B--
~~~

The reader looks for `part_A` delimiters and may fail to split the parts. Ensure exact value, exact case, and the proper `--` prefix.

### 12.2. Missing closing delimiter

If there are multiple parts without a terminating `--boundary--`, the parser may treat the message as truncated or apply custom recovery heuristics. Some software shows partial content, while others report errors or drop attachments. You cannot rely on email readers' error recovery.

### 12.3. Using the same boundary for nested layers

If `multipart/mixed` and an inner `multipart/alternative` declare the same value, determining where the child structure ends and the parent's next part starts becomes ambiguous. Each container must use a proper boundary that does not collide with delimiters in inner parts.

### 12.4. Having boundary markers without a multipart Content-Type

`--xyz` markers in the body do not automatically turn a `text/plain` message into multipart. The parser relies on the **container's** `Content-Type` and `boundary` parameter to interpret delimiter lines. If the whole email is declared `text/plain`, those markers may simply render as text.

### 12.5. Binary body altered or wrongly encoded

If a file is placed into MIME without an appropriate `Content-Transfer-Encoding`, data may not traverse traditional hops safely or may confuse reading software. Let the library encode each part; never inject raw arbitrary binary bytes into raw MIME strings.

### 12.6. Mistaking Content-Disposition for a delimiter

`Content-Disposition: attachment` tells the mail-reading app that this is an attachment; it does not mark the start/end of a part. Splitting parts still relies on the container's boundary. Conversely, having valid boundaries does not make a part appear as an attachment if related metadata is not set properly.

### 12.7. Editing MIME headers after the helper built the structure

Modifying `Content-Type` or inserting boundaries manually after `MimeMessageHelper` has prepared the parts risks creating inconsistent headers and body. Use library APIs to alter the structure and let the library re-serialize properly.

## 13. Inspecting MIME while troubleshooting

When an email sends successfully yet HTML displays as an attachment, `cid:` images fail to appear, or a PDF is corrupted, you can inspect the **raw MIME source** of the email in a test environment.

A useful reading workflow:

1. Find `MIME-Version` and `Content-Type` at the message level.
2. If you see `multipart/*`, note the `boundary` value of that exact level.
3. Locate delimiters starting with `--<boundary>` and the closing delimiter `--<boundary>--`.
4. Within each part, read `Content-Type`, `Content-Transfer-Encoding`, `Content-Disposition`, and `Content-ID` if present.
5. If a part is itself `multipart/*`, repeat the process using the **child part's new boundary**.
6. Once the right part is identified, interpret the data after decoding; e.g., `text/html`, an image with `cid:`, or an `application/pdf` file.

For quick reasoning, you can represent it as a tree:

~~~text
message/rfc822
└── multipart/mixed [boundary = outer]
    ├── multipart/related [boundary = related]
    │   ├── multipart/alternative [boundary = alt]
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png [Content-ID: <brandLogo>]
    └── application/pdf [attachment]
~~~

The tree above is only **one possible structure**, not mandatory for every message containing HTML and images. The actual structure is determined by the MIME builder and how the application declares content.

When saving or sharing raw emails for debugging, strip user addresses, tokens, sensitive content, and real file data. A MIME message can contain the complete email content in plain text or easily Base64-decodable form.

## 14. Practice questions

**Question 1.** A header declares `boundary="abc"`. Which line marks the end of all parts in the container?

~~~text
--abc
--abc--
abc--
~~~

**Answer:** `--abc--`. The line `--abc` only starts a next part; `abc--` is not valid delimiter syntax for this boundary.

**Question 2.** A part inside `multipart/mixed` has `Content-Type: multipart/alternative; boundary="alt"`. When `--alt--` is reached, has the whole email ended?

**No.** Only the `multipart/alternative` region ends; the parser returns to the parent `multipart/mixed` region to look for subsequent parts.

**Question 3.** An image has `Content-ID: <banner>`. How can HTML reference and use that image?

~~~html
<img src="cid:banner" alt="Banner">
~~~

**Explanation:** The boundary separates the image part from other parts; `Content-ID` and `cid:` let HTML link the exact image.

**Question 4.** When using `MimeMessageHelper` to send HTML and a PDF, do you need to assemble `--boundary` lines manually?

**No.** Call `setText(...)` and `addAttachment(...)` with the appropriate multipart mode, and let Jakarta Mail generate and output the MIME structure.

**Question 5.** Why does `Content-Transfer-Encoding: base64` not replace a boundary?

Because Base64 describes **how a single part's data is represented**, whereas a boundary describes **the borders between parts** inside a container.

## 15. Mental model to remember

A multi-part MIME email resembles a **tree of containers**. Each `multipart` region declares the relationship type of its child parts (`mixed`, `alternative`, `related`, ...) and **its own boundary** to divide the parts directly belonging to that region. Each part has its own headers describing data type, encoding, display role, or relationships with other parts.

In Spring Framework Mail, **`MimeMessageHelper` is where the developer describes logical content**, while **Jakarta Mail turns that structure into a properly formatted MIME message**. When encountering broken HTML, missing inline images, or unreadable attachments, identify the multipart layer, that layer's boundary, the part headers, and the encoded data before looking for causes in SMTP or the mail client UI.

