# Encoded MIME size differs from original file size

## 1. Why can sending an email still fail even when the file is smaller than the limit?

When a **Spring Framework Mail** application sends attachments, the original file size on disk is usually **different from** the **MIME** message size sent over SMTP. Binary data is typically represented in **Base64** to traverse email systems compatibly. Base64 increases the byte count; then MIME also adds line breaks, per-part headers, multipart boundaries, message body content, and message headers.

For example, a **10 MiB** (10,485,760-byte) PDF file packaged as MIME Base64, wrapped at 76 characters with CRLF between lines, has an encoded data section of **14,348,936 bytes** (roughly **13.68 MiB**). That size **does not yet include** MIME headers, boundaries, and email body content. Therefore, checking only the original file size is insufficient to know whether the SMTP server will accept the message.

Common scenarios:

- A user attaches a file smaller than 20 MiB, yet the SMTP server caps **total message size** at 20 MiB.
- An email has multiple small files whose raw total looks valid, yet after Base64 exceeds the limit.
- An HTML email has embedded images plus a `text/plain` version, so the sum of MIME parts exceeds the displayed content.
- The application accepts the file upload successfully, yet the subsequent mail-sending step gets a “message too large” response.

The key takeaway is to distinguish **original file bytes**, **part data bytes after Content-Transfer-Encoding**, and **bytes of the entire serialized email**.

## 2. MIME contains many parts beyond the file's content

MIME (Multipurpose Internet Mail Extensions) defines how emails carry content with different charsets, multiple body parts, and binary files. An attachment becomes a **MIME body part**, carrying headers declaring content type, file name, and transport encoding.

Abbreviated message example, purely illustrative of structure:

~~~mime
From: reports@example.com
To: recipient@example.net
Subject: Monthly report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="example-boundary"

--example-boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Your report is attached.
--example-boundary
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKJUVPRgo=
--example-boundary--
~~~

The Base64 string represents only a few bytes, not a complete PDF document. In standard email, lines end with **CRLF**, i.e., the two bytes 0x0D and 0x0A. The example above also omits headers servers may add and nested multipart layers.

| Component | Present in original file? | Present in MIME message? |
|---|---|---|
| Initial binary data | Yes | Represented via transfer encoding |
| Base64 characters | No | Yes if the part uses Base64 |
| Base64 line-break CRLFs | No | Yes |
| Content-Type, Content-Disposition, Content-Transfer-Encoding | No | Yes |
| File name encoded in MIME header | Metadata about the file | Yes |
| Headers From, To, Subject, Date, Message-ID... | No | Yes |
| text/plain, text/html content, embedded images | Not part of the attachment under consideration | Yes if added to the message |
| Multipart boundaries and blank lines | No | Yes |

Consequently, **attachment size is not message size**. Beyond total message size, a service may also limit file count, per-file size, recipient count, and total received storage per account.

## 3. The Base64 formula: from 3 bytes to 4 characters

Base64 converts every **3 bytes** of data (24 bits) into **4 ASCII characters**, each representing 6 bits. If the trailing data has fewer than 3 bytes, padding characters **=** are used to complete the 4-character group.

~~~text
3 original bytes (24 bits)
        |
        v
4 groups, 6 bits each
        |
        v
4 Base64 characters (4 ASCII bytes)
~~~

Examples:

~~~text
Man -> TWFu   (3 bytes into 4 characters)
Ma  -> TWE=   (2 bytes into 4 characters)
M   -> TQ==   (1 byte into 4 characters)
~~~

With **n** as the original file byte count, the pure Base64 character count is:

\[
B(n) = 4\left\lceil \frac{n}{3} \right\rceil
\]

**B(n)** is also the byte count if Base64 characters are represented in ASCII, before line wrapping. When n is divisible by 3, the ratio is **4/3**, meaning roughly **33.33% larger than the original data**. For tiny files, because a 4-character group must be padded, the percentage increase can be higher: 1 byte becoming 4 bytes is a 300% increase.

**Base64 is neither compression nor security encryption.** Anyone holding Base64 data can recover the original bytes. It is used for its ability to represent binary data using an ASCII character set safe for traditional email protocols.

## 4. MIME Base64 also adds CRLF for line wrapping

When used as **Content-Transfer-Encoding: base64** in MIME, encoded data lines must be **no longer than 76 characters**, excluding the line-terminating CRLF. CRLF is **2 bytes**, so the actual Base64 section on the wire is normally larger than B(n).

Under common packaging with at most 76 characters per line and **no trailing CRLF at the end of the data section**, we calculate:

\[
L = \left\lceil \frac{B}{76} \right\rceil
\]

Where **L** is the number of lines when B > 0. There are **L − 1** gaps between lines, so the wrapped Base64 data size is:

\[
E = B + 2(L-1)
\]

If the file is empty (n = 0), then B = 0 and E = 0. Specific serializers may append one trailing CRLF after the data before the multipart boundary, adding another 2 bytes; that part and the boundaries belong to the enclosing MIME layer. Hence formula **E** measures **Base64 data and inter-line CRLFs**, not total email size.

Two small examples:

~~~text
n = 57 bytes
B = 4 * ceil(57 / 3) = 76 characters
L = 1 line
E = 76 bytes

n = 58 bytes
B = 4 * ceil(58 / 3) = 80 characters
L = 2 lines
E = 80 + 2 = 82 bytes
~~~

Adding one original byte can sometimes trigger an entire new Base64 group and a new CRLF, so size grows in **discrete steps**.

## 5. Sample calculation with 1 MiB and 10 MiB files

**MB** and **MiB** are two different units:

- **1 MB** in decimal is **1,000,000 bytes**.
- **1 MiB** in binary is **1,048,576 bytes**.

Java file APIs such as `Files.size(path)` return **byte counts**, so compute limits in bytes first before converting to display units.

### 1 MiB file

~~~text
n = 1,048,576 bytes
B = 4 * ceil(1,048,576 / 3) = 1,398,104 bytes
L = ceil(1,398,104 / 76) = 18,397 lines
CRLF between lines = (18,397 - 1) * 2 = 36,792 bytes
E = 1,398,104 + 36,792 = 1,434,896 bytes
~~~

### 10 MiB file

~~~text
n = 10,485,760 bytes
B = 4 * ceil(10,485,760 / 3) = 13,981,016 bytes
L = ceil(13,981,016 / 76) = 183,961 lines
CRLF between lines = (183,961 - 1) * 2 = 367,920 bytes
E = 13,981,016 + 367,920 = 14,348,936 bytes
~~~

| Original file | Unwrapped Base64 | Wrapped MIME Base64, excluding trailing CRLF | Notes |
|---|---:|---:|---|
| 3 bytes | 4 bytes | 4 bytes | Fits one group |
| 57 bytes | 76 bytes | 76 bytes | Fits one line |
| 58 bytes | 80 bytes | 82 bytes | Needs an extra CRLF |
| 1 MiB | 1,398,104 bytes | 1,434,896 bytes | Excludes headers/boundaries |
| 10 MiB | 13,981,016 bytes | 14,348,936 bytes | Excludes headers/boundaries |

For sufficiently large files, a quick approximation is:

\[
\frac{4}{3} \times \frac{78}{76}
= \frac{26}{19}
\approx 1.36842
\]

This means **MIME Base64 data** can be roughly **36.84%** larger than the original file when using 76-character lines separated by CRLF. This factor is an **estimate**: short files are affected by padding and line-break positions; the whole email also includes other parts.

## 6. When an email has multiple parts, sizes add up

An email can have **multipart/mixed** containing text content and multiple attachments, while another body section uses **multipart/alternative** to hold both text/plain and text/html.

~~~text
multipart/mixed
|
+-- multipart/alternative
|   +-- text/plain
|   +-- text/html
|
+-- application/pdf  (attachment, base64)
|
+-- image/jpeg       (attachment, base64)
|
+-- image/png        (inline image, base64 if used)
~~~

Both `text/plain` and `text/html` parts reside in the message even though the client displays only one version. An image embedded in HTML still consumes size if its image data is packaged as a MIME part.

If three binary files are **4 MiB**, **3 MiB**, and **2 MiB**, the raw total is **9 MiB**. Using the approximate MIME Base64 factor, the total data of those attached parts already reaches roughly **12.32 MiB**, before counting headers, boundaries, and text body. Hence you must **sum the sizes of all parts** rather than checking only the largest file.

File names containing Unicode, such as **Báo cáo quý.pdf**, may require encoded MIME parameters and header line folding. That makes the wire header longer than the displayed character count. That cost is usually smaller than Base64 on large files, yet still matters when an email sits near the allowed threshold.
## 7. Not all MIME content uses Base64

MIME allows each part to declare a different **Content-Transfer-Encoding**. The actual mechanism depends on content type, inner bytes, and supporting libraries/SMTP infrastructure.

| Encoding | Representation | Size impact |
|---|---|---|
| **7bit** | Content obeys 7-bit byte and message line-length requirements | No Base64 expansion, though CRLF/headers remain |
| **8bit** | Body can contain 8-bit bytes when transport supports it properly | No Base64 multiplier; related rules still apply |
| **quoted-printable** | Keeps most ASCII readable; bytes needing encoding become =HH | Varies with data; can grow sharply with many non-ASCII bytes |
| **base64** | Encodes data into ASCII characters | ~33.33% before wrapping, ~36.84% for large files with 76-char lines |
| **binary** | Preserves binary data over supporting transport | Cannot be assumed over traditional 7-bit SMTP paths |

Do not multiply the **1.36842** factor across **the entire email**. A short ASCII `text/plain` segment may use 7bit with minimal growth; Vietnamese `text/html` may be encoded via quoted-printable or Base64; attached PDFs or images are typically packaged in Base64.

Quoted-printable example:

~~~text
One data byte needing escaping: E1
Quoted-printable representation: =E1

1 byte is represented by 3 ASCII characters.
~~~

Quoted-printable also uses **soft line breaks** to wrap lines within formatting limits; this cost depends on content. For text containing many UTF-8 bytes needing escaping, quoted-printable can become larger than Base64. Yet when text is mostly ASCII, it can be more compact than Base64 and remain human-readable.

### MIME is not compression

Base64 makes data larger for transport compatibility, not to shrink files. ZIP compression can reduce size **before attaching**, if the data is compressible; afterward the ZIP file can still be represented as MIME Base64.

~~~text
Source file
    |
    +-- Attach directly -----> MIME encoding --> transmitted data
    |
    +-- Compress to ZIP -----> MIME encoding --> transmitted data
~~~

CSV files or repetitive multi-line logs compress well. JPEG, PNG, MP4, ZIP, or already compressed files rarely benefit from re-compressing; sometimes a new ZIP file is even larger. Whether to compress should depend on file type, business requirements, and the recipient's ability to open the content.

## 8. Where do SMTP servers measure size limits?

There are multiple independent limits across the mail-sending pipeline:

| Layer | Data typically limited | Example consequence |
|---|---|---|
| **HTTP upload** | Bytes of the HTTP request/multipart upload sent to the app | File fails to upload before any email is created |
| **Spring application** | Raw file, attachment count, estimated total email size | Application returns an error before calling JavaMailSender |
| **SMTP submission server** | Entire SMTP message size, plus quotas and sending policies | SMTP rejects the message when threshold is exceeded |
| **Receiving SMTP relay/MX** | Message size the destination accepts, per-domain/recipient policies | Message accepted at submission yet fails to deliver downstream |
| **Mailbox/message store** | Storage quota or retention rules | Delivery fails when storing into the mailbox |

SMTP has the **SIZE** extension, allowing a server to advertise the maximum message size it is willing to accept and allowing clients to declare estimated size.

Abbreviated SMTP session example:

~~~smtp
C: EHLO app.example.com
S: 250-mail.example.net
S: 250-SIZE 20971520
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
~~~

The value **20,971,520 bytes = 20 MiB** is an example of capability/policy at **the connected SMTP server**. A server may enforce a lower threshold per account, sender address, or recipient; acceptance at one hop does not guarantee downstream hops share the same threshold. For outgoing SMTP, the relevant size is the encoded/header-wrapped message the SMTP server must accept, not simply `Files.size` of the attachment.

A size error response may look like:

~~~text
552 5.3.4 Message size exceeds fixed maximum message size
~~~

Exact codes and wording vary by system. When using an **email API over HTTP**, the error may be **413 Payload Too Large** if the HTTP request is too big. Providers may measure limits on HTTP JSON, on total decoded file bytes, or on the built MIME email; never assume those three quantities are equal.

### A 20 MiB limit does not allow attaching a 20 MiB file

If a provider caps **total email at 20 MiB**, a 20 MiB raw attachment sent via MIME Base64 will have a data section of about **27.37 MiB** before headers/body even count. It exceeds the limit.

Reverse budget estimate for **one large attachment**:

\[
\text{Raw budget} \approx
\frac{\text{Message budget}}{1.36842}
\]

With a 20 MiB cap, the theoretical raw byte budget for a single Base64 part alone is roughly **14.6 MiB**, before subtracting space for all headers, message text, and other parts. This is a **planning estimate**, not a guarantee a provider accepts a file right at that threshold.

When setting application limits, leave **headroom** because real multiparts, charsets, filenames, signatures, and headers expand message size. For services using multiple providers, limits should be based on each provider's policy or the lowest threshold among destinations served.

## 9. How does Spring Framework Mail create MIME attachments?

In Spring, **JavaMailSender** uses **Jakarta Mail** to build and send **MimeMessage**. **MimeMessageHelper** helps construct multipart emails, HTML, and attachments without writing boundary lines or MIME headers manually.

Example sending a PDF over SMTP:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {
    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient, Path file)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Monthly report");
        helper.setText("Your report is attached.", false);
        helper.addAttachment(
                file.getFileName().toString(),
                new FileSystemResource(file.toFile()));

        mailSender.send(message);
    }
}
~~~

**FileSystemResource** lets Jakarta Mail read the file when packaging and sending data. It **does not mean** SMTP transmits the attachment as raw bytes. The library chooses a suitable Content-Transfer-Encoding for the body part, typically Base64 for binary data.

Implementation points to remember:

1. **MimeMessageHelper(message, true, ...)** enables multipart support.
2. **addAttachment(...)** adds file content along with filename and MIME metadata.
3. **MimeMessage** is serialized into headers, boundaries, body parts, and encoded data.
4. **JavaMailSender.send()** succeeding means submission-level sending completed accordingly; it does not assert the recipient opened the email.
5. When sending asynchronously, the file must remain present and unchanged while the worker reads it; retries may require reopening the stream.

For large files, avoid constructing a **`byte[]`** holding the whole file just to measure size before attaching when a suitable resource can be used. Loading large files into RAM alongside building the full MIME in memory increases out-of-heap risk. Measuring/estimating size by bytes and streams fits constrained resources better.

## 10. Writing a Java function to estimate MIME Base64 using integers

When you know an attachment will use Base64 with lines up to 76 characters, you can compute exact **B** and **E** from the formulas above without creating an encoded file.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class MimeBase64Size {
    private MimeBase64Size() {
    }

    public static long estimateBodyBytes(long rawBytes) {
        if (rawBytes < 0) {
            throw new IllegalArgumentException("Negative file size");
        }
        if (rawBytes == 0) {
            return 0;
        }

        // ceil(rawBytes / 3), avoiding rawBytes + 2 overflow.
        long groups = rawBytes / 3;
        if (rawBytes % 3 != 0) {
            groups = Math.addExact(groups, 1);
        }

        long base64Chars = Math.multiplyExact(groups, 4);

        // CRLF only between Base64 lines, not a trailing CRLF.
        long lineSeparators = (base64Chars - 1) / 76;
        long crlfBytes = Math.multiplyExact(lineSeparators, 2);

        return Math.addExact(base64Chars, crlfBytes);
    }

    public static void main(String[] args) throws Exception {
        Path path = Path.of("report.pdf");
        long rawBytes = Files.size(path);
        long encodedBodyBytes = estimateBodyBytes(rawBytes);

        System.out.println("File bytes: " + rawBytes);
        System.out.println("Estimated Base64 MIME bytes: "
                + encodedBodyBytes);
    }
}
~~~

**Math.multiplyExact** and **Math.addExact** catch `long` overflow instead of silently producing wrong results. The method above counts **only Base64 data and inter-line CRLFs**. It excludes headers, trailing body CRLFs, boundaries, HTML, text/plain, or other attachments; it also assumes the library uses Base64 and corresponding line wrapping.

For multiple files, you can sum the estimated bytes:

~~~java
long totalBase64BodyBytes = 0;
for (Path attachment : attachments) {
    long size = Files.size(attachment);
    totalBase64BodyBytes = Math.addExact(
            totalBase64BodyBytes,
            MimeBase64Size.estimateBodyBytes(size));
}
~~~

**totalBase64BodyBytes** is the total cost of the Base64 attachment parts, **not the size of the complete MimeMessage**. Comparing this total against the SMTP limit still requires adding headroom for the remaining components.

## 11. Measuring the byte count of an actually serialized MimeMessage

When an email sits close to the threshold, estimating by multiplier is not enough. You can build the **MimeMessage**, call **saveChanges()** to finalize certain headers, and write it to a **byte-counting OutputStream**. This avoids holding the entire message inside a `ByteArrayOutputStream`.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.OutputStream;

public final class MimeMessageBytes {
    private MimeMessageBytes() {
    }

    public static long count(MimeMessage message)
            throws MessagingException, IOException {
        message.saveChanges();
        CountingOutputStream counter = new CountingOutputStream();
        message.writeTo(counter);
        return counter.getCount();
    }

    private static class CountingOutputStream extends OutputStream {
        private long count;

        @Override
        public void write(int value) {
            count = Math.addExact(count, 1);
        }

        @Override
        public void write(byte[] bytes, int offset, int length) {
            if (bytes == null) {
                throw new NullPointerException("bytes");
            }
            if (offset < 0 || length < 0
                    || offset > bytes.length - length) {
                throw new IndexOutOfBoundsException();
            }
            count = Math.addExact(count, length);
        }

        long getCount() {
            return count;
        }
    }
}
~~~

After adding all bodies and attachments to the `MimeMessage`, you can call:

~~~java
long serializedBytes = MimeMessageBytes.count(message);
long providerLimit = 20L * 1024 * 1024;

if (serializedBytes > providerLimit) {
    throw new IllegalArgumentException(
            "Email MIME exceeds configured size limit");
}

mailSender.send(message);
~~~

This is a **measurement of serialized MIME bytes at the current moment**. It is far more accurate than relying solely on raw files, yet still has limits:

- Sending or an MTA may add/alter headers; providers may also apply different counting rules.
- Wire-level SMTP protocol bytes (such as transparency/dot-stuffing) should not be equated with MIME content size.
- Counting must **re-read files** to serialize, costing I/O and time; attachments must stay unchanged across counting and sending.
- If the `MimeMessage` is modified after counting, the measured byte count no longer represents the new message.

Therefore, **estimate quickly from raw file sizes** to pre-filter clearly oversized cases, only **serialize to count** when near the limit, and still reserve headroom for real-world SMTP infrastructure.
## 12. Controlling email limits step-by-step in the application

A workflow involving file uploads and email sending should be split into clear decision points:

~~~mermaid
flowchart TD
    A[User selects attachment] --> B[Read original file bytes]
    B --> C{Meets upload criteria?}
    C -- No --> X[Return upload limit error]
    C -- Yes --> D[Estimate Base64 and expected parts]
    D --> E{Within message limit with headroom?}
    E -- No --> Y[Suggest reducing size or using download link]
    E -- Yes --> F[Build MimeMessage and MIME parts]
    F --> G{Need exact serialized byte count?}
    G -- Yes --> H[Count complete MIME bytes]
    G -- No --> I[Send with JavaMailSender]
    H --> J{Within allowed threshold?}
    J -- No --> Y
    J -- Yes --> I
    I --> K[SMTP server accepts or returns error]
~~~

### Limit at upload time

An HTTP endpoint can reject files based on request size or the application's multipart configuration. This is a limit for **data ingestion**, not an email limit. A successfully uploaded file can still exceed SMTP limits once encoded. Conversely, an SMTP provider allowing 25 MiB messages does not mean the HTTP server should accept unbounded uploads.

### Limit when building MIME

For an email with multiple attachments, sum each encoded body plus text/plain, text/html, inline images, boundaries, and headers. You can set an internal raw threshold lower than the provider limit to keep headroom. If a provider changes its size policy or the app adds an HTML signature, logo image, and new attachment, the MIME budget must also be updated.

### Limit when sending to the SMTP server

When the SMTP server reports a size limit error, the application should record a clear error and **never retry indefinitely** with the same unchanged message. A permanent oversized-message error will not vanish by itself after a few seconds. However, if an error is transient and the server uses a matching reply code, retry policies must rely on **reply codes and actual semantics**, not just error message text.

### Limit at the recipient's server

Even after **JavaMailSender.send()** succeeds at SMTP submission, the receiving server can reject the message at a subsequent hop for being too large or violating policy. Hence, application-side byte measurement is part of **pre-send** error control, not a replacement for delivery status, bounces, DSNs, or webhooks from the email service.

## 13. Example presenting size to the user

Suppose the SMTP service allows at most **20 MiB for the total email**. A user selects a 10 MiB PDF:

~~~text
File name:                       report.pdf
Original file size:              10.00 MiB
Estimated Base64 MIME part:      13.68 MiB
Message body + headers:          Not yet added
Total email limit:               20.00 MiB

Result: Can proceed to build MIME to verify limit.
~~~

Then the user selects an additional 7 MiB original image:

~~~text
Original PDF file:               10 MiB
Original image file:              7 MiB
Total source files:              17 MiB

Approx. MIME Base64 PDF:         13.68 MiB
Approx. MIME Base64 image:        9.58 MiB
                                 ---------
Total of two attachment parts:   23.26 MiB

Headers/body not yet added.
Total email limit:               20.00 MiB

Result: Cannot send as a single attached email as-is.
~~~

The application can suggest shrinking file size, compressing suitable file types, or sending a **file download link** instead of an attachment. When using links, ensure only authorized recipients can view the file, links have appropriate expiration and revocation, and data-security policies are met. Splitting one email into multiple emails can also inconvenience recipients and must be decided per business requirements.

A good message should not merely say “file too large” if the raw file is actually below the upload limit. It can say:

> Total email size after packaging attachments is expected to exceed the mail service's 20 MiB limit. Please reduce the file size or use a shared link.

## 14. Common misconceptions

**“Base64 always increases size by exactly 33%.”** Not quite. The 4/3 ratio is Base64's baseline when byte count is divisible by 3. MIME also wraps lines with CRLF and the tail may need padding, so large file data bodies typically grow by nearly 36.84% with 76-character wrapping.

**“A longer file name makes the Base64 file data larger.”** File name does not affect Base64 bytes computed from file content; it affects the length of the **MIME header** holding filename. Headers with Unicode or requiring folding can be longer.

**“Choosing UTF-8 reduces attachment size.”** The UTF-8 charset is for representing text. It does not make PDFs, images, ZIP files, or other binary data smaller. MIME Content-Transfer-Encoding addresses a different problem from charset.

**“Just use Java String.length() to know the size.”** Java `String.length()` counts UTF-16 code units, not email bytes. When text content must convert to UTF-8, quoted-printable, or Base64, byte length changes further. For whole messages, rely on data serialized into bytes.

**“HTTP multipart/form-data size equals MIME email size.”** No. They are two separate packaging layers. HTTP uploads have request boundaries/headers; email uses MIME and may Base64-encode content. For JSON email APIs embedding Base64, JSON request size also differs from final MIME email size.

**“A Base64-encoded ZIP file will be smaller.”** ZIP may have compressed the source data beforehand, yet **Base64 of the ZIP file** is still longer than the original ZIP bytes. Base64 is not compression.

**“Summing file sizes multiplied by 1.37 is always enough.”** Multiplying is only an approximate estimate for the Base64 section of large files. Emails also have text, HTML, inline images, MIME headers, filenames, boundaries, and other encodings. Near the threshold, keep headroom or measure serialized MIME.

**“Once SMTP accepts it, the destination server is guaranteed to receive it.”** Acceptance at SMTP submission only marks the point where the sending server takes responsibility for processing the message. Forwarding through downstream servers can encounter different size limits or quotas.

## 15. From file upload to MIME: a metrics model to keep distinct

When reading logs or monitoring mail-sending jobs, use unambiguous metric names:

| Metric | Meaning | What is it used for? |
|---|---|---|
| **rawAttachmentBytes** | Original file size on disk | Upload limits, storage, source file checks |
| **estimatedEncodedBodyBytes** | Estimated Base64 or transfer encoding of a part | Pre-warning before creating MIME |
| **estimatedMessageBytes** | Estimated total of parts and overhead | Sending budget and headroom planning |
| **serializedMimeBytes** | Bytes of `MimeMessage` at a specific serialization | Near-limit check for a concrete message |
| **providerReportedSize** | Size as defined by the provider | Reconciling provider responses/quotas |

Do not lump all metrics under a single generic name like **fileSize**. When a 10 MiB file is uploaded and the email is rejected at a 12 MiB limit, a log saying only “fileSize=10” fails to explain why it was rejected.

Example business log with sensitive content stripped:

~~~text
mailRequestId=mail-2048
attachmentCount=2
rawAttachmentBytes=17825792
estimatedEncodedBodyBytes=24400000
serializedMimeBytes=24402620
configuredMessageLimitBytes=20971520
result=REJECTED_BY_APPLICATION_SIZE_POLICY
~~~

Encoded and serialized values in the example are illustrative. In practice, compute and log accurate measurements, keep identifiers to correlate with SMTP outcomes, and avoid logging filenames, addresses, or sensitive content unnecessarily.

## 16. Formulas and how to apply them in Spring Mail

If an **n-byte** attachment is definitely encoded in **MIME Base64** with at most **76 characters per line** and no extra trailing CRLF at the end of the data section:

~~~text
B = 4 * ceil(n / 3)         // Base64 bytes before line wrapping
L = ceil(B / 76)            // Number of Base64 lines when B > 0
E = B + 2 * (L - 1)         // Base64 + CRLFs between lines

For n = 0: E = 0
For large files: E ≈ n * 1.36842
~~~

For the complete message:

~~~text
MIME message bytes =
    Message headers
  + MIME part headers
  + Encoded body of each MIME part
  + Multipart boundaries and CRLFs
  + Other included body parts
~~~

**In Spring Framework Mail, check original file size in bytes, budget for encoding expansion and MIME overhead, and compare against the SMTP provider's total email limit.** When data sits close to the threshold, you can measure serialized **`MimeMessage`** bytes. Errors occurring at SMTP still require dedicated handling by reply code and delivery status, because “acceptable pre-send size” is no guarantee that the email reached the destination mailbox.
