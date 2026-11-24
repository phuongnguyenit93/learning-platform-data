# Base64, quoted-printable, and binary data

In **Spring Framework Mail**, an email can contain Vietnamese text, HTML, inline images, PDFs, and other binary files. To a developer, adding content seems straightforward: create a **MimeMessage**, call **MimeMessageHelper.setText(...)** or **addAttachment(...)**, and then use **JavaMailSender.send(...)**. However, SMTP and the email format were built back when transport systems mainly worked with ASCII characters. Therefore, data must be described and sometimes **encoded for transport** before traveling over the email path.

Two common methods are **Base64** and **quoted-printable**. Both belong to MIME's **Content-Transfer-Encoding** concept, yet solve different data scenarios. Understanding how they work helps you read raw emails, recognize Vietnamese diacritic bugs, predict attachment sizes, and avoid confusing binary content with text seen by the user.

## 1. Why are MIME and transfer encoding needed?

**MIME (Multipurpose Internet Mail Extensions)** extends the email format to describe many content types: **text/plain**, **text/html**, **image/png**, **application/pdf**, **multipart/mixed**, and others. MIME uses headers to state what type of data a message part carries, which character set it uses, and how it is represented during transport.

Before suitable extensions existed, traditional mail transport paths were mainly designed for **7-bit** data. A UTF-8 byte representing a Vietnamese diacritic can fall outside the 7-bit ASCII range; a PDF or PNG file contains arbitrary bytes, including non-text bytes. Sending those bytes directly over a 7-bit-only route can alter or reject the content.

MIME separates two critical questions:

- **What is the content?** For example, UTF-8 text, HTML, a PNG image, or a PDF file. This is the responsibility of **Content-Type** and related parameters.
- **As what bytes/characters is the content represented for transport?** This is the responsibility of **Content-Transfer-Encoding**, such as **base64**, **quoted-printable**, **7bit**, **8bit**, or **binary**.

Example:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

In the part above, the string the user should see is **Xin chào!**, while the raw line contains **=C3=A0** instead of the letter **à**. The **UTF-8** character set dictates that bytes **C3 A0** correspond to the character à; **quoted-printable** dictates representing those bytes with transport-safe ASCII characters.

### Three transformation layers to distinguish

~~~text
Characters seen by the user
       |
       | Charset (e.g., UTF-8)
       v
Byte sequence representing the text
       |
       | Content-Transfer-Encoding (QP or Base64)
       v
Transport representation in the MIME body
       |
       | SMTP / email infrastructure
       v
Receiver decodes transfer -> decodes charset -> displays
~~~

**Charset** and **transfer encoding** are not the same concept. UTF-8 is not Base64; Base64 also does not tell whether the decoded byte sequence is Vietnamese text, a PDF, or an image. You must rely on the corresponding MIME headers to interpret the data accurately.

## 2. Structure of a MIME content part

A MIME part typically has headers and a content body, separated by a blank line:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64

SGVsbG8=
~~~

The raw body here is **SGVsbG8=**. After decoding Base64, we get the ASCII bytes of **Hello**. Because the header states **charset=UTF-8**, the mail reader proceeds to decode the bytes into the corresponding characters. For simple English strings, ASCII and UTF-8 produce the same result.

Key headers:

| Header | Answers the question | Example |
| --- | --- | --- |
| **Content-Type** | What kind of data is this? | **text/plain**, **text/html**, **application/pdf** |
| **charset** (Content-Type parameter) | Under which encoding are text bytes decoded to characters? | **UTF-8** |
| **Content-Transfer-Encoding** | How is the MIME part's body encoded for transport? | **base64**, **quoted-printable** |
| **Content-Disposition** | Should this part be presented as body content or an attachment? | **inline**, **attachment** |
| **filename** / **name** | File name or suggested name when displaying | **invoice.pdf** |
| **Content-ID** | Identifies a MIME part, commonly so HTML can reference inline resources | **<logo-1@example.test>** |

**Content-Disposition: attachment** does not replace **Content-Type** or **Content-Transfer-Encoding**. The same PDF part can still use **Content-Type: application/pdf**, **Content-Disposition: attachment**, and **Content-Transfer-Encoding: base64**.

MIME can be a single part or a **multipart** structure containing multiple parts, each with its own Content-Type and Content-Transfer-Encoding. There is no rule that an email must use the same transfer encoding for all content.

## 3. Base64: turning arbitrary bytes into transportable characters

**Base64** is a reversible transformation: it encodes byte data into characters from the Base64 alphabet, mainly consisting of **A–Z**, **a–z**, **0–9**, **+**, **/**, and padding character **=** when needed. Because this character set lies within ASCII, it passes smoothly through infrastructure originally handling 7-bit text.

### The 3-bytes-into-4-characters principle

Base64 groups up to **3 bytes = 24 bits**, splitting them into **4 groups of 6 bits**. Each group maps to one Base64 character. When the data lacks a full 3 bytes at the end, the encoding usually pads with **=** to complete a 4-character group.

~~~text
Initial bytes:
  00        FF        10
00000000  11111111  00010000

Split 24 bits into 4 groups:
000000  001111  111100  010000
   0      15      60      16
   A       P       8       Q

Base64 result: AP8Q
~~~

For the string **Hello**:

~~~text
ASCII bytes: 48 65 6C 6C 6F
Base64:      SGVsbG8=
~~~

The binary file example with three bytes **00 FF 10** shows that Base64 does not care whether the data is text or not. It only processes **bytes**.

### How much does size increase?

For **n** input bytes, the number of Base64 characters before line wrapping is usually:

~~~text
4 * ceil(n / 3)
~~~

The asymptotic ratio is **4/3**, meaning large payloads typically grow by about **33%** due to Base64 alone. MIME Base64 also usually wraps lines after at most **76 encoded characters**, so calculating wire payload size must also count **CRLF** line breaks, MIME headers, and multipart boundaries.

For example, if a file has a nominal size of **3 MiB**, its Base64 section requires roughly **4 MiB** of characters before counting CRLF and other overhead. Consequently, an “attachment size limit” shown in a UI does not necessarily equal the size limit of **the entire email transmitted over SMTP**.

### MIME Base64 and API Base64 do not look identical in formatting

Base64 used in MIME belongs to the email transport variant with line-wrapping rules. When working with Base64 in URLs or some JSON APIs, you may encounter unwrapped Base64 or **base64url** using **-**, **_** instead of **+**, **/**. Do not assume all Base64 strings share the same line wrapping, alphabet, and padding rules.

When reading raw emails, **Content-Transfer-Encoding: base64** lets the MIME parser apply the exact email decoding rules; applications normally do not need to strip CRLF manually and write a custom decoder.

### Base64 is not security encryption

Anyone with Base64 data can decode it back to the original bytes. Base64:

- **Does not encrypt confidentially**; anyone with the raw message can read the decoded data.
- **Does not compress content**; size generally increases.
- **Does not protect integrity** against deliberate modification.
- **Does not authenticate the sender**.

To protect email in transit, appropriate mechanisms like **TLS** during transport are needed; to protect content end-to-end, content encryption/signing technologies such as **S/MIME** or equivalent solutions are needed, depending on business requirements. Base64 is strictly a **data representation layer for transport**.

## 4. Quoted-printable: keeping text readable in raw form

**Quoted-printable** is especially suitable when most content is ASCII and only some bytes cannot be represented safely directly. Instead of converting all bytes into Base64 characters, it leaves most printable ASCII characters untouched and uses the **=HH** form to represent bytes needing encoding, where **HH** is two hexadecimal digits.

For example, the word **Café** UTF-8-encoded into bytes:

~~~text
C    a    f     é
43   61   66   C3 A9
~~~

Using quoted-printable, a valid representation is:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

For Vietnamese:

~~~text
Text: Xin chào!
UTF-8 of "à": C3 A0
Quoted-printable: Xin ch=C3=A0o!
~~~

For English text or HTML content containing mostly ASCII, quoted-printable is usually easier to read than Base64 in raw messages. If text has too many non-ASCII bytes, each byte must be represented by three characters **=HH**, so size can increase significantly; Base64 is sometimes more space-efficient.

### Equals signs and whitespace have special meaning

The **=** sign is the control character of quoted-printable. When the data itself contains an equals sign, it must be encoded as **=3D** where required. Example:

~~~text
Original text: A=B
Quoted-printable: A=3DB
~~~

Spaces or tabs at the **end of an encoded line** must also be protected; for instance, a space can be represented as **=20**. Leaving a literal space at the end of a line risks having some transport systems or processors strip it, losing data. Quoted-printable has exact rules to prevent that case.

### Soft line breaks differ from text newlines

Quoted-printable caps each encoded line at **at most 76 characters** per MIME rules. If a content line is long, the encoder can insert a **soft line break**: an **=** sign right before **CRLF**. When decoding, this sequence is **removed**, because it only wraps lines for transport.

~~~text
Raw data:
This is a very long line so it is split here=
 and the continuation stays on the same line.
~~~

After decoding, the **=** sign and the line break immediately following it disappear; the continuation belongs to the **same logical line**. By contrast, an ordinary line break without a trailing **=** is a real newline in the decoded content.

This matters when comparing user-visible text against the raw email: raw lines are not always content lines.

### When is quoted-printable poorly suited?

If data contains many binary bytes such as **00**, **FF**, or long runs of non-printable bytes, quoted-printable must encode each byte as **=HH**, making the payload very long and hard to read. In such cases Base64 is usually better suited.

## 5. Comparing Base64, quoted-printable, and other transfer encoding values

MIME defines multiple **Content-Transfer-Encoding** options. It is important not to conflate these values with **Content-Type**.

| Value | Meaning | When commonly used | Notes |
| --- | --- | --- | --- |
| **7bit** | Body uses only data within traditional 7-bit mail limits | Simple ASCII text | Not for directly carrying non-ASCII UTF-8 bytes or arbitrary binary |
| **quoted-printable** | Protected bytes are represented as **=HH**, most ASCII stays intact | Near-ASCII text, HTML, or plain text | Raw-readable but grows when many non-ASCII bytes exist |
| **base64** | Every 3 bytes are encoded into up to 4 ASCII characters | Images, PDFs, binary files, and some text parts | Increases size ~33% plus line-wrapping overhead |
| **8bit** | Allows bytes with the eighth bit set in the body | Text transported over an 8-bit-capable path | Depends on SMTP support and line limits |
| **binary** | Allows binary data without 7bit/8bit line constraints | Paths and protocols supporting binary MIME | Requires matching protocol conditions; not a default feature of every SMTP server |

### How do 8BITMIME and BINARYMIME relate to SMTP?

**8BITMIME** is an SMTP extension permitting transmission of 8-bit content under matching constraints, instead of forcing everything through a 7-bit ASCII representation. However, **8-bit** does not mean arbitrary binary bytes are all accepted: line lengths, line endings, and other limits still matter.

**BINARYMIME** together with appropriate transmission mechanisms such as **CHUNKING/BDAT** allows handling binary content directly on supporting hops. This capability should not be assumed across a general SMTP ecosystem; relay paths can differ in extension support and handling.

Because of broad compatibility, **base64** remains the standard choice for binary attachments, even when some systems support 8-bit or binary transport.

**You cannot simply set Content-Transfer-Encoding: 8bit or binary and assume every SMTP server along the path will handle it properly.** Metadata and actual transport capabilities must align.

## 6. Multipart: multiple encodings can coexist in one email

A real email may contain plain text, HTML text, and an attached PDF. The MIME structure is usually a tree: **multipart/mixed** wraps the primary content along with attachments; inside the primary content there may be **multipart/alternative** for different display versions.

~~~text
multipart/mixed
|
+-- multipart/alternative
|   |
|   +-- text/plain; charset=UTF-8
|   |       Content-Transfer-Encoding: quoted-printable
|   |
|   +-- text/html; charset=UTF-8
|           Content-Transfer-Encoding: quoted-printable
|
+-- application/pdf
        Content-Transfer-Encoding: base64
        Content-Disposition: attachment
~~~

In this example, **multipart** only describes parts combined into the same message; each child part specifies its own content type and transfer encoding. The plain and HTML parts are **two alternative display options**, not two paragraphs meant to appear simultaneously. The PDF part is an attachment.

### An abbreviated raw MIME message

~~~text
MIME-Version: 1.0
From: sender@example.test
To: reader@example.test
Subject: Document
Content-Type: multipart/mixed; boundary="mix-01"

--mix-01
Content-Type: multipart/alternative; boundary="alt-01"

--alt-01
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!

--alt-01
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>

--alt-01--
--mix-01
Content-Type: application/pdf; name="guide.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="guide.pdf"

JVBERi0xLjQK

--mix-01--
~~~

**The example is abbreviated to illustrate structure**, not a complete PDF file. **JVBERi0xLjQK** is the leading Base64 representation of the byte sequence starting with **%PDF-1.4** and a newline; a real PDF requires the entire file content encoded. The **--mix-01** and **--alt-01** markers are boundaries separating parts; they are not part of the attachment's data.

When decoding, the mail reader must:

1. Parse boundaries and MIME headers to identify each part.
2. Apply the **Content-Transfer-Encoding** of each part (e.g., quoted-printable or base64).
3. For **text/** parts, use **charset** to turn bytes into characters.
4. For binary parts, pass the decoded bytes to the appropriate handler (PDF viewer, file downloader, image renderer).

Taking a Base64 block from a raw email and displaying it directly as UTF-8 text produces meaningless characters, because it may represent a PDF or image rather than text.

## 7. Vietnamese text: wrong charset differs from wrong transfer encoding

Vietnamese diacritic issues are a classic case for telling encoding layers apart.

Suppose the intended content is:

~~~text
Xin chào!
~~~

In UTF-8, the bytes for the letter **à** are **C3 A0**. When using quoted-printable, the raw message may record:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

On the receiving side, if QP decodes properly yet **bytes are decoded under the wrong charset**, the user may see garbled accents (mojibake). Conversely, if UTF-8 charset is declared properly yet QP is not decoded, the user may see the literal string **=C3=A0**.

To pinpoint where the error occurs, classify the symptom:

| Symptom | Likely area to investigate |
| --- | --- |
| Reader sees **Xin ch=C3=A0o** | MIME QP was not decoded, or QP data was passed in as plain text |
| Reader sees strange characters after decoding | Wrong charset; content was generated using a different charset than declared |
| Attachment reports corrupt on open | Data was altered, truncated, or metadata/transfer encoding is mismatched |
| Raw email contains long Base64 | May be completely normal; must decode according to Content-Transfer-Encoding |
| Attachment is larger than original file | Base64 overhead, line wrapping, and MIME headers are normal |

Merely changing **Content-Type: text/plain** to **text/html** does not cure byte or charset bugs. Input data, the charset when creating the MIME message, and transfer encoding must all align.

## 8. Building emails with Vietnamese and attachments using Spring Mail

**Spring Framework Mail** provides **JavaMailSender** and **MimeMessageHelper** to construct messages without assembling MIME lines manually. With Jakarta Mail-based Spring, the following example sends plain text, HTML, and a PDF:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class GuideMailService {

    private final JavaMailSender mailSender;

    public GuideMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendGuide(String recipient, Path pdfFile)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("no-reply@example.test");
        helper.setTo(recipient);
        helper.setSubject("User guide");

        helper.setText(
                "Hello! Your guide is attached.",
                "<p>Hello! Your <strong>guide</strong> is attached.</p>"
        );

        helper.addAttachment(
                "guide.pdf",
                new FileSystemResource(pdfFile.toFile())
        );

        mailSender.send(message);
    }
}
~~~

The example uses two content variants:

- The first argument of **setText(plainText, htmlText)** is plain text.
- The second argument is HTML.
- **addAttachment(...)** adds the PDF file as a separate MIME part.
- The **"UTF-8"** argument instructs creating text headers/content using the appropriate charset.

**MimeMessageHelper** works with the Jakarta Mail library to build the MIME parts. The mail layer decides the appropriate transfer encoding for each part; typical application code **does not need to Base64-encode PDFs itself** or manually turn Vietnamese into **=HH** before calling **addAttachment** or **setText**.

In particular, avoid calling Base64 encoding on PDF bytes and passing the **Base64 string** to **addAttachment** as though it were an original PDF file. When Jakarta Mail encodes for MIME a second time, recipients may download an attachment containing **Base64 text** instead of real PDF content. That is a **double encoding** bug.

### Why use FileSystemResource?

**FileSystemResource** allows Jakarta Mail to read file content from the filesystem via the Resource abstraction when creating/sending MIME parts. For in-memory content, **ByteArrayResource** can be used, though heap memory should be considered when generating large batches of large emails. For stream sources, pay attention to stream re-openability because the sending layer may need to read data multiple times during MIME preparation.

If attaching user-uploaded files, check size limits, file names, content types, and access permissions before placing files into the message. Do not treat client-supplied **Content-Type** as definitive proof that a file is safe or matches the declared format.

## 9. How do inline images differ from attachments?

Images displayed inside HTML email are typically placed in a separate MIME part with **Content-ID**, then referenced from HTML via a **cid:** path. Example:

~~~html
<html>
  <body>
    <p>Hello!</p>
    <img src="cid:course-logo" alt="Course logo">
  </body>
</html>
~~~

The related image part may carry headers:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <course-logo>
Content-Disposition: inline

[Base64-encoded PNG image data]
~~~

The line in square brackets is only a description, not a valid Base64 payload. **Content-ID** links the binary part to the **cid:** reference inside HTML; **Content-Disposition: inline** suggests the mail reader display that part inline within content rather than treating it as an ordinary attachment.

An example adding an inline image via Spring:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setFrom("no-reply@example.test");
helper.setTo("student@example.test");
helper.setSubject("Course notification");
helper.setText(
        "<p>Hello!</p><img src=\"cid:course-logo\" alt=\"Logo\">",
        true
);

helper.addInline(
        "course-logo",
        new FileSystemResource("assets/course-logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

In the code above, create the HTML content with **setText(...)** before calling **addInline(...)** per standard **MimeMessageHelper** usage. The string **course-logo** in **cid:** and **addInline(...)** must match. The resource path is illustrative only; real applications must know where the image file resides.

**Inline** is about how content is arranged, referenced, and displayed, whereas **Base64** is how bytes are represented for transport. An inline image can still have **Content-Transfer-Encoding: base64**, just like an attached image. Do not treat the two concepts as mutually exclusive choices.

Additionally, some email clients block images or do not render inline images as expected. The **alt** attribute and meaningful HTML/text content remain essential; proper encoding only solves byte transport, not rendering uniformity across all clients.

## 10. Body encoding differs from email header encoding

Fields such as **Subject**, sender display name, or attachment file name can also contain Vietnamese:

~~~text
Subject: Tài liệu buổi học
From: "Bộ phận đào tạo" <training@example.test>
Content-Disposition: attachment; filename="báo cáo.pdf"
~~~

However, the mechanism for handling non-ASCII characters in **headers** is not the same as using **Content-Transfer-Encoding** on the **body**.

For traditional text headers, MIME defines the **encoded-word** mechanism (RFC 2047), taking the forms:

~~~text
=?charset?B?encoded-text?=
=?charset?Q?encoded-text?=
~~~

Here **B** is Base64-based encoding for *a header text segment*, while **Q** is a header-specific form resembling quoted-printable with its own rules. For example, for the word **Café**, a valid header representation is:

~~~text
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

Compliant mail readers decode the header content and display **Café**. Conversely, the message body can have:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

Both appear to involve Base64 or quoted-printable, yet **their syntactic contexts differ**. Never take raw QP body text, paste it straight into Subject, and expect email clients to understand it properly.

Attachment file names containing non-ASCII characters may use extended parameter mechanisms such as **RFC 2231**, depending on libraries and sending/receiving systems. When using **MimeMessageHelper.setSubject(...)** and **addAttachment(...)**, let the mail library build the appropriate headers. When supporting legacy clients is required, inspect the actually received file names rather than writing arbitrary encoded strings into headers yourself.

### Does SMTPUTF8 replace Base64 and quoted-printable?

**SMTPUTF8** expands the ability to use international characters in email identities/headers when supported by all parties. That is a **different** topic from representing bodies and attachments via MIME transfer encoding. A mail path supporting internationalized addresses does not mean every binary part will be transmitted raw or that Base64 and QP become obsolete.

When debugging character bugs, identify whether the bug occurs in the **header**, **body**, **email address**, or **filename**, because each area has different rules and protocol support.

## 11. Common mistakes with MIME encoding

### Mistake 1: Passing Base64 data into setText and expecting the recipient to get a file

Example:

~~~java
String encodedPdf = /* Base64 of PDF content */;
helper.setText(encodedPdf, false);
~~~

The **setText(...)** method creates **text content**, so recipients may see a long Base64 string instead of an attached PDF file. To send a PDF, supply the **real bytes** of the PDF in a MIME part with proper Content-Type and Content-Disposition, usually via **addAttachment(...)**.

Conversely, if an email provider's HTTP API *requires JSON containing a Base64 string of the attachment*, follow that API's contract. Calling a provider HTTP API and calling **JavaMailSender** are two different layers; do not mechanically apply the same data preparation to both.

### Mistake 2: Double-encoding Base64

Suppose a file contains binary bytes **00 FF 10**. Its proper Base64 is **AP8Q**. If the application takes the bytes of the character string **AP8Q** and Base64-encodes them a second time, decoding once yields only the text **AP8Q**, not the original three bytes.

A MIME mail client normally decodes **one layer of Content-Transfer-Encoding** per the header. It does not automatically know to Base64-decode a second time. Therefore, you must know clearly whether data in your application is **raw bytes** or **encoded text** before passing it to mail APIs.

### Mistake 3: Picking a charset that does not match input bytes

For example, the body holds UTF-8 bytes while metadata states **charset=ISO-8859-1**. Quoted-printable or Base64 may decode flawlessly at the transport layer, yet the resulting bytes get mapped to the wrong characters. The bug does not lie in Base64/QP itself.

For application-generated text data, standardize on UTF-8 whenever possible and avoid byte/String conversions with unspecified charsets.

### Mistake 4: Editing raw MIME directly and breaking boundaries

A multipart email depends on **--boundary** lines and per-part headers. Concatenating files manually, inserting line breaks in wrong places, or truncating payloads during transmission can prevent receiving parsers from recognizing attachments or cause invalid-MIME errors.

Working with **MimeMessage**, **MimeBodyPart**, or **MimeMessageHelper** is usually much safer than concatenating raw MIME text manually, especially with multiple parts and attachments.

### Mistake 5: Seeing =HH sequences and thinking the content is corrupted

In a raw email, **=C3=A0** is the normal quoted-printable representation of UTF-8 bytes; **SGVsbG8=** is the normal Base64 representation of Hello. Read **Content-Transfer-Encoding** before concluding the data is corrupt.

Only if the email client UI displays those literal strings instead of decoded text should you investigate MIME generation or receiving-side processing.

### Mistake 6: Treating Content-Type as proof a file is safe

An attachment declaring **Content-Type: application/pdf** can still contain non-PDF data. Base64 only transforms bytes; it does not validate content. For systems accepting user-supplied files, verify the actual format, enforce size limits, and scan content per security requirements; do not trust file extensions or MIME headers.

## 12. Size limits and performance when sending binary files

For emails with attachments, total message size is usually larger than the sum of the original files' bytes:

~~~text
Size sent over SMTP
  ≈ encoded text content
    + Base64 section of attachments
    + line-wrapping CRLFs
    + MIME headers and boundaries
    + email headers
~~~

For instance, a **9 MiB** file already occupies about **12 MiB** just in Base64 characters, not counting line breaks and other parts. If a provider enforces a total message limit at a given threshold, applications should not allow attachments right up to that limit assuming sending will succeed.

Costs to consider:

- **SMTP bandwidth and time:** Base64 increases the number of bytes to transmit.
- **Memory:** holding multiple attachments simultaneously as byte arrays can grow heap usage rapidly.
- **File/stream reading:** attachment data may need to be read when the message is serialized or sent.
- **Queues and retries:** resending a large message consumes substantial bandwidth and time.
- **Provider limits:** providers may cap total message size, recipient count, throughput, or attachment formats.

If files are very large or many people need to download them, a sound solution can be **storing the file on an access-controlled storage service and sending an expiring download link**. That avoids duplicating binary payloads in every message, though it requires designing access permissions, link expiration, and revocation independently.

### Notes on binary data and CRLF

Do not read a binary file using a **Reader** and rewrite it using a **Writer** to prepare an attachment. Converting bytes to characters can alter data, especially bytes invalid in the chosen charset. PDF, ZIP, or image files must go through a **byte stream/Resource**, whereas only plain text goes through a charset layer.

In quoted-printable, CRLF can be part of text line-representation rules; in Base64, line breaks of the encoded representation are typically ignored when recovering **payload bytes**. The two mechanisms handle lines differently; do not apply arbitrary newline replacement operations across both.

## 13. How to read and process a MIME email upon receipt

Suppose an application needs to read incoming reply emails with attachments. Conceptual workflow:

~~~text
Receive raw email
    |
    v
Read MIME headers of the message
    |
    v
If multipart, split MIME parts by boundary
    |
    +--> For text/plain or text/html:
    |      Decode transfer encoding
    |      Convert bytes to text using charset
    |
    +--> For application/pdf or image/png:
    |      Decode transfer encoding
    |      Obtain file or image bytes
    |
    v
Validate, store, or display according to content type
~~~

A solid MIME parser must inspect **Content-Type** of each part as well as nested multipart structures. You cannot naively split a raw email at the keyword **Content-Transfer-Encoding** expecting the next section to always be an attachment.

When receiving external data, also enforce limits on message size, MIME part count, multipart nesting depth, and decoding resources. An email can contain many parts or abnormal structures; file parsing must never be allowed to consume unbounded resources.

### Checking attachment integrity

In principle, Base64 and quoted-printable are lossless transformations when encoded and decoded properly. Therefore:

~~~text
raw bytes
  -> MIME transfer encode
  -> MIME transfer decode
  -> original raw bytes
~~~

If you need to verify data was not altered, you can compare the **hash** of bytes before sending and bytes after receiving in a controlled test. However, MIME transport does not provide a security signature by itself; verifying integrity/authenticity requires an appropriate signing or authentication mechanism.

## 14. Analysis exercises

### Scenario A: Two emails with identical displayed content

First email:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

Second email:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64

Q2Fmw6k=
~~~

**Question:** could the recipient see different content?

**Answer:** when decoded properly per the headers, both display **Café**. The two parts have **different transport representations** yet the exact same UTF-8 byte sequence after decoding.

### Scenario B: Seeing a PDF file as a Base64 string

A raw email snippet has:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="manual.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK
~~~

**Question:** why can that Base64 snippet not be opened as a complete PDF?

**Answer:** because it is only a few encoded leading bytes, lacking the full PDF file structure. To download a valid PDF, the receiver must decode **the entire body part** and have the complete input data. Seeing a common PDF Base64 prefix does not guarantee the payload is complete or valid.

### Scenario C: Email with Vietnamese diacritics displays garbled text

An email declares:

~~~text
Content-Type: text/plain; charset=ISO-8859-1
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

**Question:** where is the bug if the sender actually used UTF-8 bytes for the body?

**Answer:** QP decodes accurately to bytes **43 61 66 C3 A9**, yet the declared charset **ISO-8859-1** does not match the original UTF-8 bytes. Fix how the charset is generated and declared rather than blindly switching quoted-printable to Base64.

### Scenario D: Email with plain text, HTML, and an attached file

**Question:** must all three parts use Base64?

**Answer:** no. Each MIME part can use its own transfer encoding. Plain text and HTML can use quoted-printable, while the binary file uses Base64. The multipart structure describes relationships among parts and does not mandate a single encoding.

### Scenario E: Switching from Base64 to 8bit to reduce size

**Question:** is changing only the header to **Content-Transfer-Encoding: 8bit** enough?

**Answer:** no. You must ensure the body conforms to 8-bit representation and the SMTP transport path actually supports it; **8bit cannot carry arbitrary binary bytes** like a PDF/ZIP attachment. When uncertain about those conditions, Base64 remains the broadly compatible solution.

## 15. Principles worth remembering

When creating emails in Spring Framework Mail, you can reason in sequence:

~~~text
Is the content text?
    |
    +-- Yes:
    |     Choose charset, usually UTF-8
    |     -> create text/plain or text/html
    |     -> library selects appropriate transfer encoding
    |
    +-- No:
          Keep binary bytes intact
          -> place into a MIME part with the right Content-Type
          -> library applies Base64 when appropriate

Multiple contents?
    -> use multipart and determine alternative/related/mixed relationships

Need to inspect a raw email?
    -> read Content-Type, charset, Content-Transfer-Encoding
    -> decode per MIME part

Encountered Vietnamese errors or corrupt files?
    -> isolate whether the fault is charset, transfer encoding,
       multipart structure, or input bytes
~~~

**Base64** suits arbitrary bytes, especially binary attachments; **quoted-printable** suits text with many ASCII characters where keeping the raw section relatively readable is desirable. Both are solely **MIME transport encoding mechanisms**—they do not define what the content is, do not guarantee delivery, and are not security encryption solutions.

In Spring, the durable approach is to **pass the original data into JavaMailSender/MimeMessageHelper, select the right charset and MIME structure, and let the mail layer handle transfer encoding**. When reading a received email, perform the reverse: parse MIME, decode transfer encoding, and only then interpret bytes according to Content-Type and charset.
