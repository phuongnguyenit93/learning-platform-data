# multipart/mixed for content and attachments

An email can contain a message, HTML, images, and files such as PDF, CSV, or ZIP. However, email content is transmitted as a **MIME-structured message**, not a plain text string with binary data appended directly to the end of the message.

In **Spring Framework Mail**, the **multipart/mixed** content type is an essential foundation when you want to send an **email body along with one or more attachments**. The keyword *mixed* expresses that a message contains multiple independent parts: for example, one part for the recipient to read and the remaining parts as documents sent along with the message.

A simple mental model:

~~~text
Email
├── Headers: From, To, Subject, MIME-Version, Content-Type
└── multipart/mixed
    ├── Part 1: text/plain       -> Message inside the email
    ├── Part 2: application/pdf -> Attached PDF invoice
    └── Part 3: text/csv        -> Attached CSV data table
~~~

Users typically see an email with a message body and two downloadable files; a MIME reader sees **three body parts** separated by boundaries. These are two views of the same message.

## 1. Why are MIME and multipart/mixed needed?

### 1.1. A simple text email

A simple text email may look like this:

~~~text
From: reports@example.org
To: thao@example.net
Subject: Monthly report
Content-Type: text/plain; charset=UTF-8

Please review the monthly report.
~~~

Everything after the blank line separating headers from the body is a single text payload. Such a structure does not clearly describe which part is a PDF file, which is an embedded image, and which is the content for the recipient to read.

If you merely append PDF data after the text, an email client will not automatically know which section is a named file, what data type should be downloaded, or which bytes belong to the file.

### 1.2. MIME solves representing multiple content types

**MIME (Multipurpose Internet Mail Extensions)** extends how Internet messages are represented using headers such as:

- **MIME-Version:** indicates the message uses MIME structure, usually version 1.0.
- **Content-Type:** describes the content type, such as **text/plain**, **text/html**, **application/pdf**, or **multipart/mixed**.
- **Content-Transfer-Encoding:** indicates how a part's content is encoded for transport, such as **base64** or **quoted-printable**.
- **Content-Disposition:** suggests how the client should present a part: **inline** or **attachment**.
- **Content-ID:** identifies a MIME part, commonly used when HTML references embedded resources.

**multipart/mixed** is a **Content-Type** at the message level or wrapping-part level, announcing that the inner content consists of multiple independent parts combined into one MIME unit.

### 1.3. Where does MIME fit in the mail-sending process?

Transport and representation layers should be separated:

~~~text
Spring application
    |
    | Build MimeMessage with headers, body, and attachments
    v
JavaMailSender / Jakarta Mail
    |
    | SMTP: MAIL FROM, RCPT TO, DATA
    v
SMTP server
    |
    | Inside DATA is the entire Internet message with MIME
    v
Receiving server / mail-reading application
    |
    | Parse Content-Type and boundaries
    v
Display content + attachment list
~~~

SMTP is responsible for **delivering the message to the recipient**; MIME defines **what structure and meaning the bytes in the message carry**. Having multiple MIME parts does not mean calling SMTP DATA multiple times: typically the entire multipart structure is transmitted inside a single DATA phase of the sending transaction.

## 2. Standard structure of a multipart/mixed message

A **multipart/mixed** message includes:

1. Message headers, including **Content-Type: multipart/mixed** with the **boundary** parameter.
2. A blank line separating the top-level headers from the content section.
3. Sequential parts; each part begins with a boundary delimiter.
4. Each part can have its own headers, a blank line, and its own content.
5. The final closing delimiter has two additional hyphens **--**.

The example below is a *structurally complete illustrative* email: the body is text, and the attachment is a file **note.txt** containing “Hello from attachment.” encoded in base64.

~~~text
From: reports@example.org
To: thao@example.net
Subject: Monthly report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mix-example-001"

--mix-example-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Please read the attached note.

--mix-example-001
Content-Type: text/plain; name="note.txt"
Content-Disposition: attachment; filename="note.txt"
Content-Transfer-Encoding: base64

SGVsbG8gZnJvbSBhdHRhY2htZW50Lg==

--mix-example-001--
~~~

In real email data, protocol lines use **CRLF** line endings. The illustration above shows the structure using text lines for readability.

### 2.1. Content-Type at the message level

~~~text
Content-Type: multipart/mixed; boundary="mix-example-001"
~~~

This line states that the message body is not a single text/plain block. It is a container holding multiple parts, and the string **mix-example-001** is used as the delimiter token.

**multipart/mixed** has two key aspects:

- **multipart**: a structured content type consisting of multiple parts.
- **mixed**: the parts are independent components to be presented in an appropriate order, typically a message and attachments.

### 2.2. Boundary: how parts are separated

Each part begins with a line having **two hyphens before the boundary token**:

~~~text
--mix-example-001
~~~

After the last part, the closing delimiter has **two extra hyphens at the end**:

~~~text
--mix-example-001--
~~~

A common point of confusion is that **boundary is declared as a token without the two-hyphen prefix** in the header. Only when it appears as a delimiter line does the token get the **--** prefix.

| Location | Example | Meaning |
| --- | --- | --- |
| Header | boundary="mix-example-001" | Declares the delimiter token |
| Before each part | --mix-example-001 | Opens the next part |
| After the last part | --mix-example-001-- | Ends the entire multipart |
| Part header | Content-Type: application/pdf | Indicates the data type of that specific part |

The boundary must be chosen so it does not collide with a line of data that looks like a delimiter inside the parts' content. MIME libraries normally auto-generate collision-resistant tokens, insert delimiters, and manage CRLF themselves. **You do not need to write boundaries manually in Spring Mail code** when using MimeMessageHelper.

### 2.3. Each part has its own headers

The message part in the example:

~~~text
--mix-example-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Please read the attached note.
~~~

Here:

- **Content-Type: text/plain** indicates the content is plain text.
- **charset=UTF-8** specifies how bytes decode to characters.
- **Content-Transfer-Encoding: 7bit** fits the ASCII data in the example.
- The blank line after the headers marks the start of **the part's body**, distinct from the email's top-level headers.

A part containing a file can have other headers:

~~~text
--mix-example-001
Content-Type: text/plain; name="note.txt"
Content-Disposition: attachment; filename="note.txt"
Content-Transfer-Encoding: base64

SGVsbG8gZnJvbSBhdHRhY2htZW50Lg==
~~~

**Content-Disposition: attachment** is the common signal for email clients to display the part as an attached file. The **filename** parameter suggests a file name when saving. **base64** indicates that the content carried in the part's body is encoded data, not a line of text to display verbatim.

You should not rely solely on **filename** to infer safety or the actual data type. File names and Content-Type can be misdeclared or intentionally spoofed by the sender.

## 3. Why are attachments usually base64-encoded?

Email and MIME evolved from text-transmission environments. Binary content such as PDF, ZIP, or PNG images can contain arbitrary byte values; transmitting them raw without an appropriate transport mechanism can corrupt or alter the data.

**Base64** represents binary bytes using an ASCII character set. Example:

~~~text
File content: Hello from attachment.
Base64:       SGVsbG8gZnJvbSBhdHRhY2htZW50Lg==
~~~

The receiving side relies on the **Content-Transfer-Encoding: base64** header to decode the part's data back into original bytes.

Common transfer encoding types:

| Encoding | Meaning | Common scenario |
| --- | --- | --- |
| **7bit** | Content already fits 7-bit transport | ASCII text |
| **quoted-printable** | Keeps most ASCII characters readable, encodes necessary bytes | Text emails with accents or certain special bytes |
| **base64** | Encodes data into ASCII characters | PDFs, images, binary files; sometimes text too |
| **8bit** | Allows text data containing 8-bit bytes when infrastructure supports it properly | Depends on server capabilities and transport path |

Base64 increases data size, theoretically about **4 characters for every 3 bytes**, excluding line breaks and headers. Thus, a 15 MB file can make the transmitted email substantially larger than 15 MB. SMTP server email size limits are usually calculated on the encoded message, not only the initial file size.

**Base64 does not provide security encryption**: anyone with the email content can decode the attachment. When sending sensitive documents, appropriate recipient controls and protection mechanisms are required rather than treating base64 as a confidentiality measure.

### Distinguishing Content-Transfer-Encoding and charset

These two pieces of information serve two purposes:

- **charset=UTF-8**: once text bytes are obtained, which encoding table converts them into characters?
- **Content-Transfer-Encoding: base64**: how were those bytes represented as data transmitted on the wire?

A part can declare both simultaneously:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64
~~~

When reading, the client decodes base64 to bytes and then decodes the bytes as UTF-8. Do not confuse the two steps as one.

## 4. multipart/mixed and other multipart types

Not every multi-part email uses **multipart/mixed** for everything. Other subtypes express different relationships among parts.

| Content-Type | Meaning | Use case |
| --- | --- | --- |
| **multipart/mixed** | Parts are separate components accompanying one another | Message body + PDF + CSV |
| **multipart/alternative** | Parts are alternative representations of the same content | Plain text version and HTML version of the same message |
| **multipart/related** | Parts are related to form a single presentation object together | HTML referencing embedded images via Content-ID |
| **multipart/digest** | Collection of messages or digest-style content | Aggregating multiple messages in one email |

Note that **multipart/form-data** is commonly seen when submitting HTTP forms with file uploads; it is not the same as **multipart/mixed** in email even though both use multipart/boundary concepts.

### 4.1. mixed: one message and two separate files

~~~text
multipart/mixed
├── text/plain          -> "Please see the document"
├── application/pdf     -> report.pdf (attachment)
└── text/csv            -> data.csv (attachment)
~~~

This is the simple model at the core of this lesson: attachments are independent parts alongside the readable body content.

### 4.2. alternative: two renderings of the same content

~~~text
multipart/alternative
├── text/plain -> "The report is ready"
└── text/html  -> "<p><b>The report</b> is ready</p>"
~~~

The client typically selects one suitable representation to display rather than showing both as two attachments. Versions in **alternative** should convey the same core message; the HTML version usually follows the plain text version because it is the richer representation.

### 4.3. related: HTML and embedded resources

~~~text
multipart/related
├── text/html -> <img src="cid:companyLogo">
└── image/png -> Content-ID: <companyLogo>; disposition: inline
~~~

In this case, the image is meant to display **inside the HTML content**, not merely as an independent file for the user to download. The client uses **Content-ID** to associate the **cid:** reference with the part containing the image.

This is why an email containing embedded images and an attached PDF usually needs a **nested multipart structure**.

## 5. HTML content and attachments: nested MIME structure

Suppose the application wants to send:

- A message in plain text for clients that do not render HTML.
- The same message in HTML.
- A PDF file for downloading.

A reasonable structural representation is:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf
    └── Content-Disposition: attachment; filename="report.pdf"
~~~

**Why nest?**

- The **multipart/alternative** branch describes two equivalent versions of the main content.
- The **application/pdf** branch is an independent attachment separate from the main content.
- The **multipart/mixed** root combines those components into one message.

An abbreviated raw MIME example:

~~~text
MIME-Version: 1.0
From: reports@example.org
To: thao@example.net
Subject: Report
Content-Type: multipart/mixed; boundary="outer-001"

--outer-001
Content-Type: multipart/alternative; boundary="inner-001"

--inner-001
Content-Type: text/plain; charset=UTF-8

Please view the report.

--inner-001
Content-Type: text/html; charset=UTF-8

<p>Please <strong>view the report</strong>.</p>

--inner-001--

--outer-001
Content-Type: application/pdf; name="report.pdf"
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64

[base64-data-of-PDF]

--outer-001--
~~~

The line **[base64-data-of-PDF]** in the example is an illustrative placeholder, not valid PDF data. When the application actually sends mail, Jakarta Mail generates and encodes the file's bytes. Each multipart level has its **own boundary**, and the client must close each level's boundary properly.

### 5.1. When there is also an inline image

If the HTML contains an embedded logo image and the email also has an attached PDF, the structure may be:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html (references cid:logo)
│   └── image/png
│       ├── Content-ID: <logo>
│       └── Content-Disposition: inline
└── application/pdf
    └── Content-Disposition: attachment
~~~

At the application level, the difference between an **inline image** and a **PDF attachment** lies in the presentation relationship:

- An inline image is a resource related to HTML; HTML references it via **cid:**.
- A PDF attachment is an independent file that the recipient can view/download separately.
- A part is not by default an “attachment” merely because its content is binary. How the client renders it also depends on Content-Type, Content-Disposition, MIME part position, and client compatibility.

There is no need to concatenate the MIME tree as strings manually when using Spring Mail's appropriate APIs.

## 6. Spring Framework Mail: from MimeMessage to MimeMessageHelper

In Spring Framework, **JavaMailSender** provides the ability to create and send MIME messages using Jakarta Mail; **MimeMessageHelper** makes setting headers, multipart content, attachments, and inline resources easier.

Key components to know:

| Component | Role |
| --- | --- |
| **JavaMailSender** | Creates MimeMessage and sends the message |
| **MimeMessage** | Represents an email supporting MIME, headers, and content parts |
| **MimeMessageHelper** | Assists with setTo, setSubject, setText, addAttachment, addInline, etc. |
| **Multipart** / **MimeMultipart** | Represents a multi-MIME-part structure at the Jakarta Mail layer |
| **Resource** / **InputStreamSource** | Byte source for attachments or inline resources |
| **FileSystemResource** | Resource that reads a file from the filesystem |

When working in a Spring Boot application, you can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example SMTP configuration in **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Sender account and password settings should be provided via **SPRING_MAIL_USERNAME**, **SPRING_MAIL_PASSWORD** environment variables, or an appropriate secret store. The addresses and domains in this article are examples only. SMTP port, TLS mode, and authentication must match the real mail server.

## 7. Example sending plain text with an attached PDF

Below is a Spring service that takes the path of a generated report and sends it with a message.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportEmailService {

    private final JavaMailSender mailSender;

    public ReportEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient, Path reportFile)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setFrom("reports@example.org");
        helper.setTo(recipient);
        helper.setSubject("November report");
        helper.setText(
                "Hello,\n"
                + "Please see the attached PDF report.",
                false
        );

        helper.addAttachment(
                "report.pdf",
                new FileSystemResource(reportFile)
        );

        mailSender.send(message);
    }
}
~~~

Step-by-step explanation:

1. **createMimeMessage()** creates a MIME message via Jakarta Mail.
2. **MULTIPART_MODE_MIXED** tells the helper to build a structure supporting **multipart/mixed** at the root level.
3. **setFrom**, **setTo**, **setSubject** set headers and recipients used by the library when sending.
4. **setText(..., false)** creates a plain text body part; the **false** argument indicates this is not HTML.
5. **addAttachment("report.pdf", resource)** adds a MIME part for the file with the display name **report.pdf**.
6. **mailSender.send(message)** hands the constructed message to the mail transport.

The **reportFile** path must point to an existing file that the application has permission to read. If the file does not exist, loses permissions, or changes during sending, constructing/reading the attachment data can fail. A real-world system should validate the source, access permissions, and lifecycle of the file before invoking the sending service.

Conceptual MIME outcome:

~~~text
multipart/mixed
├── text/plain
│   └── Hello, please see the attached PDF report.
└── application/pdf
    ├── Content-Disposition: attachment
    ├── filename="report.pdf"
    └── PDF bytes encoded for transport
~~~

The actual Content-Type name of the attachment depends on the data source, file name, and media type detection. If exact control is needed, you can use the **addAttachment** overload that accepts a media type.

### 7.1. Why not use SimpleMailMessage?

**SimpleMailMessage** is intended for simple text emails with fields like sender, recipient, subject, and text. It is not an API for adding MIME parts/attachments.

For attached documents, use **MimeMessage** and **MimeMessageHelper**. Putting file content into SimpleMailMessage's text string does not generate **multipart/mixed**, lacks Content-Disposition, and will not cause clients to recognize an attachment.

### 7.2. Adding multiple files to the same email

You can call **addAttachment** multiple times before sending:

~~~java
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath)
);

helper.addAttachment(
        "transactions.csv",
        new FileSystemResource(csvPath)
);
~~~

The result is a message carrying multiple attachment parts. The display order of files in the client may differ from the order added in code; business requirements should not depend strictly on attachment display order.

### 7.3. Sending a MIME attachment with a specific data type

Example using an in-memory byte source generated by the application:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] csvBytes = "id,amount\n1,100\n".getBytes(
        java.nio.charset.StandardCharsets.UTF_8
);

helper.addAttachment(
        "transactions.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

In the example, the data is small enough to illustrate **ByteArrayResource**. For large files, consider **FileSystemResource** or a suitable streaming source to reduce holding multiple data copies in RAM.

When using overloads accepting **InputStreamSource**, the data source must be able to provide an input stream compatible with how Jakarta Mail accesses attachments. An **InputStreamResource** wrapping a single-use stream is not always suitable, because building/sending MIME may require acquiring the stream multiple times. **ByteArrayResource** and **FileSystemResource** are familiar choices for repeatable readable data.

## 8. Plain text + HTML + attachment in one message

Applications often want to send a rich HTML version while still having a plain text fallback. In that case, MimeMessageHelper's **setText(String plainText, String htmlText)** helps create the appropriate representations.

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("thao@example.net");
helper.setSubject("November report");

helper.setText(
        "The November report is ready. See the attached PDF.",
        "<html><body>"
        + "<p>The <strong>November report</strong> is ready.</p>"
        + "<p>See the attached PDF.</p>"
        + "</body></html>"
);

helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath)
);

mailSender.send(message);
~~~

Logically, the message section has two representations, **text/plain** and **text/html**; the attachment remains a separate part. The MIME structure may be nested to preserve those relationships. The receiving client picks the suitable content version and offers the attachment for the user to open or download.

Do not treat **setText(plain, html)** as two different messages; they are **two representations of the same content** within one email.

### 8.1. Which multipart mode to choose in MimeMessageHelper?

Spring Mail provides several multipart modes, notably:

| Mode | Meaning and scenario |
| --- | --- |
| **MULTIPART_MODE_NO** | Does not build a multipart structure; unsuitable when addAttachment is needed |
| **MULTIPART_MODE_MIXED** | Creates a **multipart/mixed** root; suitable for independent content and attachments |
| **MULTIPART_MODE_RELATED** | Uses **multipart/related** at the root; emphasizes content and related resources |
| **MULTIPART_MODE_MIXED_RELATED** | **multipart/mixed** root containing a **multipart/related** branch for content/inline, with attachments placed appropriately at the mixed level |

An API detail worth noting: if you use the common constructor:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8"
);
~~~

then in Spring Framework, **true** enables multipart using the default mode **MULTIPART_MODE_MIXED_RELATED**. Therefore, **true** does not guarantee that every part is placed directly beneath a simple multipart/mixed root.

When the goal is to clearly illustrate a pure **mixed** structure for message and attachments, you can explicitly choose **MULTIPART_MODE_MIXED**. When HTML has inline images or a structure with broader client compatibility is needed, **MULTIPART_MODE_MIXED_RELATED** is usually the appropriate choice.

Do not infer the entire MIME tree solely from the number of **addAttachment** calls. The actual structure also depends on the multipart mode, how **setText** is called, adding inline resources, and the specific library implementation.

## 9. Distinguishing attachments from inline images

Two common calls on **MimeMessageHelper**:

~~~java
helper.addAttachment(
        "company-profile.pdf",
        new FileSystemResource(profilePath)
);

helper.addInline(
        "companyLogo",
        new FileSystemResource(logoPath),
        "image/png"
);
~~~

Effect:

- **addAttachment** adds content as an independent attached document, typically with **Content-Disposition: attachment**.
- **addInline** adds a resource serving HTML content, referenced by its corresponding **Content-ID**.

HTML may contain:

~~~html
<p>Welcome!</p>
<img src="cid:companyLogo" alt="Company logo">
~~~

The string **companyLogo** in **cid:** must match the identifier used in **addInline**. Many email clients block or restrict image rendering, so alternative text should be provided whenever possible.

In messages that have HTML, inline images, and a PDF, you can use:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setText(htmlBody, true);
helper.addInline("companyLogo", logoResource, "image/png");
helper.addAttachment("report.pdf", reportResource);
~~~

Per Spring Mail guidance, when using inline resources, **setText** should be called before **addInline** so email clients handle inline references more reliably.

Do not add an image with **addAttachment** and expect a **cid:** tag in HTML to link to that part automatically. A normal attachment does not necessarily carry a Content-ID and the required **multipart/related** relationship.

## 10. File names, Content-Type, and Content-Disposition

A MIME part used for an attachment may have:

~~~text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64
~~~

The headers play different roles:

**Content-Type** helps the receiving side understand the data format, such as PDF, CSV, ZIP, or generic binary **application/octet-stream**.

**Content-Disposition: attachment** suggests presenting that part as a separate document for download.

**filename** is a suggested file name, not an absolute path on the recipient's machine, and should not be trusted as a safe path.

### 10.1. File extension and media type are not the same thing

If you call:

~~~java
helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath)
);
~~~

the library may infer the media type from the file name or configured content detection mechanism. However, **the .pdf extension does not guarantee the actual bytes are a PDF**. In systems processing user-supplied files, content verification and file policies must be enforced at the business layer.

Similarly, setting Content-Type **application/pdf** does not turn a text string into a PDF; it is only metadata describing the data type declared by the sender.

### 10.2. File names with Vietnamese characters

A filename may contain non-ASCII characters, such as **báo-cáo-tháng-11.pdf**. MIME has specific rules for representing headers containing international characters, depending on standards and client support levels. When using Jakarta Mail/Spring Mail, prefer file-naming APIs and proper charset configuration; avoid concatenating unencoded headers directly.

For compatibility across many mail-receiving systems, short meaningful ASCII file names such as **bao-cao-thang-11.pdf** are often simpler. If preserving Unicode is required, test against target email clients.

### 10.3. Filename is untrusted data

When an application **receives** an email with attachments, never concatenate filename directly into a file write path. A sender-declared name can contain special characters, relative paths, or misleading characters. Normalize the name, choose an application-managed directory, and apply file-type allowlist policies.

When an application **sends** attachments, also choose clear names to avoid leaking internal paths such as temporary directory paths, non-public customer names, or file names from unverified sources.

## 11. Common mistakes when building multipart/mixed

### 11.1. Using setText instead of addAttachment for files

Wrong idea:

~~~java
message.setText("Here is the PDF file: " + pdfAsBase64);
~~~

This snippet merely inserts a base64 string into the text body; it does not create a MIME part with proper **Content-Type** and **Content-Disposition**. Clients will not know to display it as a named file.

The right approach is to create **MimeMessageHelper** in multipart mode and call **addAttachment** with the file's byte source.

### 11.2. Concatenating boundaries manually and sending as text/plain

If an application builds a string containing **--boundary** lines and calls **SimpleMailMessage.setText**, the content is just ordinary text. The client will not receive a **multipart/mixed** header and valid MIME structure.

A MIME message is not just delimiters; it requires matching top-level headers, part headers, encoding, CRLF, and boundaries. To avoid formatting errors, use dedicated MIME APIs.

### 11.3. Forgetting multipart mode

If the helper is created in non-multipart mode and **addAttachment** is called, the necessary structure to hold attachments will be missing. Choose a constructor supporting multipart, such as passing **MULTIPART_MODE_MIXED** or **true** when appropriate.

### 11.4. Reading an InputStream and reusing the exhausted stream

An attachment may need to be accessed by Jakarta Mail while serializing the message. If the data source allows reading only once, a subsequent read may fail or yield empty data.

The solution is to use a re-openable source such as **FileSystemResource**, or store bytes in **ByteArrayResource** when size is small enough. Do not hold onto an already consumed InputStream across multiple steps without a management strategy.

### 11.5. Sending oversized files

An email does not count only the original file size: base64, headers, and MIME structure increase the transmitted size. SMTP servers can reject oversized messages, mail providers have their own quotas, and the receiving side may impose different limits.

If a file is very large, an alternative is to store it on an access-controlled file service and send an appropriate download link; this changes the security model and file lifecycle, so it must be designed proactively.

### 11.6. Attaching an attachment yet describing it as inline

Some email clients may automatically render images or preview PDFs even when the header uses **attachment**. Do not rely on how one client renders it to deduce the MIME structure. Inspect **Content-Disposition**, multipart relationships, and **Content-ID**, and test on target clients.

### 11.7. Successful send does not mean the recipient sees the attachment

Even when the SMTP server accepts the message, the receiving side can still:

- Block risky file types or files exceeding limits.
- Quarantine the message under anti-malware policies.
- Strip or alter attachment handling.
- Route the message to spam, delay it, or bounce a delivery error.

Therefore, “was the message accepted by SMTP?” and “could the recipient open the attachment?” must be tracked via different signals.

## 12. How to read the structure of a real email

When encountering an email with a message and three attachments, read from outside to inside:

~~~text
Message headers
    |
    +-- MIME-Version: 1.0
    +-- Content-Type: multipart/mixed; boundary="outer"
            |
            +-- Part #1: text/plain
            |       message body
            |
            +-- Part #2: application/pdf
            |       Content-Disposition: attachment
            |       filename="invoice.pdf"
            |       Content-Transfer-Encoding: base64
            |
            +-- Part #3: text/csv
            |       Content-Disposition: attachment
            |       filename="items.csv"
            |
            +-- Part #4: application/zip
                    Content-Disposition: attachment
                    filename="backup.zip"
~~~

If the first part is **multipart/alternative** instead of text/plain, continue parsing its child parts. If there is **multipart/related**, locate Content-IDs and relationships with HTML. MIME structures can have multiple layers; an email-processing algorithm should not assume “body is always part 0 and all remaining parts are attachments” for every email in the world.

In a Spring mail-sending application itself, a technical check when troubleshooting is to inspect the constructed message in a development environment:

- Does the message root have the expected **Content-Type: multipart/mixed** or desired multipart type?
- Does the body part have the right **text/plain** or **text/html**?
- Does the attachment have **Content-Disposition: attachment**, matching filename, and appropriate media type?
- Does the body preserve UTF-8 and Vietnamese characters?
- Can the source data be opened and read completely when the mail transport uses it?
- Is the payload within the SMTP service's size limits?

These questions guide diagnosis. Real content verification, test sends, and code quality evaluation are carried out in dedicated system testing stages rather than relying solely on structural descriptions.

## 13. Business scenario illustration: sending a report with PDF and CSV

Suppose an application has a “send sales report” feature after aggregating data. The recipient needs to:

1. Read a short message in the email.
2. Open the PDF version to view the formatted report.
3. Download the CSV to import data into another system.

The desired message structure is:

~~~text
From: reports@example.org
To: manager@example.net
Subject: November sales report

multipart/mixed
├── text/plain:
│     "The report has been generated; please see the attached files."
├── application/pdf:
│     report-november.pdf
└── text/csv:
      report-november.csv
~~~

Illustrative Java snippet focusing on declaring MIME parts:

~~~java
public void sendMonthlyReport(
        String recipient,
        Path pdfPath,
        Path csvPath
) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED,
            "UTF-8"
    );

    helper.setFrom("reports@example.org");
    helper.setTo(recipient);
    helper.setSubject("November sales report");

    helper.setText(
            "The report has been generated.\n"
            + "Please see the attached PDF and CSV files.",
            false
    );

    helper.addAttachment(
            "report-november.pdf",
            new FileSystemResource(pdfPath)
    );
    helper.addAttachment(
            "report-november.csv",
            new FileSystemResource(csvPath),
            "text/csv; charset=UTF-8"
    );

    mailSender.send(message);
}
~~~

The example assumes **mailSender** is injected into the service; **pdfPath** and **csvPath** are verified, generated, and ready to read. Writing report files, checking recipient authorization, and managing transport errors are responsibilities of the application surrounding this method.

Key takeaway: **three content components are packaged into one MimeMessage**. The message does not need to be sent separately; the two files do not need separate **mailSender.send** calls; the library automatically creates the multipart structure and transmits the message over SMTP according to the mail configuration.

## 14. Questions to reinforce understanding

**“Why does multipart/mixed need a boundary?”**

Because an entire MIME message is a single data stream that can hold multiple parts with separate headers/bodies. The boundary lets the receiving side determine where one part ends and the next begins. MIME libraries typically generate and handle boundaries automatically.

**“Is every part in multipart/mixed an attachment?”**

No. The first part is usually the primary content to display; other parts may be attachments. A part can also be a nested multipart. Identification should rely on structure, headers, and context.

**“I want both HTML and a PDF—is mixed enough on its own?”**

You can use a **multipart/mixed** root to hold HTML content and a PDF, but if you want both plain text and HTML representing the same message, use **multipart/alternative** nested inside mixed. If there are also inline images, **multipart/related** can be added.

**“Are the message and the PDF two separate emails?”**

No. They are two MIME parts inside the same email. They can be transported inside the same SMTP DATA payload.

**“Does calling addAttachment make SMTP send another message?”**

No. **addAttachment** modifies the structure of the MimeMessage, while **send** performs the sending step. The number of SMTP transactions and recipients depends on the sending operation, not the number of MIME parts.

**“Can the recipient download the PDF file when the part uses base64?”**

Yes. The MIME client decodes Content-Transfer-Encoding to recover the file bytes, then uses Content-Type/Content-Disposition/filename to decide how to present it. However, opening or downloading still depends on client and receiving email system policies.

**“Can I manually base64-encode an attachment and put it into setText?”**

You should not. It remains text content unless a proper MIME part and headers are created. Use **addAttachment** so the library handles file bytes and transfer encoding.

**“Do I always have to set the PDF's Content-Type manually?”**

Not always, because the library can detect it from the file name or media type configuration. When certainty is needed or the data has an uncommon extension, use the **addAttachment** overload with an explicit content type.

## 15. Remembering the essence of multipart/mixed

**multipart/mixed** is how MIME packages **email content and attachments into structured parts within a single message**. The root Content-Type header declares the multipart type and boundary; each part has its own headers and body; attachments typically use **Content-Disposition: attachment** and **Content-Transfer-Encoding: base64**.

In Spring Framework Mail, the pair **JavaMailSender** and **MimeMessageHelper** helps build this structure through operations such as **setText** and **addAttachment**. When there is only a message and files, **MULTIPART_MODE_MIXED** expresses the desired structure clearly. When there are multiple content versions or embedded resources, **multipart/alternative** and **multipart/related** structures can be nested inside mixed.

Having a firm grasp on this boundary helps you understand why an email can hold multiple files while remaining **one message**, know how to read raw MIME when attachment errors occur, and choose the right APIs when building document-sending features with Spring Mail.
