# Adding attachments from File, InputStream, and Resource

In **Spring Framework Mail**, `MimeMessageHelper` helps an application send emails with file attachments (*attachments*) without having to construct MIME boundaries, Base64-encode manually, or assemble email headers by string concatenation. However, attachments can come from many different sources: a file sitting on disk, data generated right in memory, a resource on the classpath, or a byte stream from a storage system.

The important point is not just passing data into `addAttachment(...)`. **Jakarta Mail may need to read the data multiple times during the preparation and sending of the MIME message.** Therefore, distinguishing `File`, `InputStream`, `InputStreamSource`, and `Resource` has direct significance for sending success, memory usage, and error handling.

This lesson presents how to add attachments from these sources, choose the appropriate `MimeMessageHelper` overload, determine `Content-Type`, handle streams safely, and organize mail-sending code in Spring Boot.

## 1. What is an attachment in MIME structure?

An email does not consist only of `Subject` and `Text` strings. When there are attached files, the email is usually represented as a **MIME multipart message**, in which the message body and each attachment are a separate **MIME part**.

Conceptual structure example:

```text
MimeMessage
└── multipart/mixed
    ├── text/plain; charset=UTF-8
    │   └── "This month's invoice is attached."
    ├── application/pdf
    │   ├── Content-Disposition: attachment
    │   ├── filename="invoice.pdf"
    │   └── PDF data encoded appropriately for email
    └── text/csv
        ├── Content-Disposition: attachment
        ├── filename="orders.csv"
        └── CSV data
```

An attachment part usually has headers such as:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64
```

Three pieces of information to distinguish:

| Component | Meaning |
| --- | --- |
| `Content-Type` | Content type, for example `application/pdf`, `image/png`, or `text/csv` |
| `Content-Disposition` | How the mail client handles the part; `attachment` usually makes the file appear in the attachments area |
| `Content-Transfer-Encoding` | How bytes are represented for transport, usually `base64` for binary data |

When using `MimeMessageHelper.addAttachment(...)`, **the application provides the filename, data source, and optional media type**; the helper works with Jakarta Mail to create the corresponding MIME part.

**Do not convert PDF bytes into a text string yourself and call `setText(...)`.** The contents of a PDF, ZIP, or PNG must be passed to the attachment as **raw bytes**.

## 2. Common `addAttachment(...)` overloads

`MimeMessageHelper` provides several ways to add attachments:

```java
// Source is a physical file.
helper.addAttachment(String attachmentFilename, File file);

// Byte source that can provide a fresh InputStream.
helper.addAttachment(
        String attachmentFilename,
        InputStreamSource inputStreamSource
);

// Byte source and explicitly specified media type.
helper.addAttachment(
        String attachmentFilename,
        InputStreamSource inputStreamSource,
        String contentType
);

// Data source per Jakarta Activation.
helper.addAttachment(
        String attachmentFilename,
        DataSource dataSource
);
```

The lines above are **method signature illustrations**, not complete standalone Java statements.

| Data source | Object to use | When is it suitable? |
| --- | --- | --- |
| File on disk | `java.io.File` | The file already exists at a specific path |
| File on disk via Spring abstraction | `FileSystemResource` | Want to use the `Resource` API to read the file |
| Resource packaged in the application | `ClassPathResource` | Attaching sample documents or files available on the classpath |
| Bytes already in RAM | `ByteArrayResource` | PDF/CSV generated in memory |
| Stream source needing a fresh open each time | Custom `InputStreamSource` implementation | File/object storage or custom retrieval source |
| An already-open `InputStream` | **Should not be passed directly as a read-once source** | Need to convert to a **re-openable** source or save temporarily |

Common point: `MimeMessageHelper` needs **a sufficiently stable byte source** throughout the entire email creation and sending process.

## 3. Preparing Spring Boot and `JavaMailSender`

To send mail in Spring Boot, the application usually uses the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Example `application.yml` with SMTP submission supporting STARTTLS on port 587:

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

Values in `${...}` are environment placeholders in Spring syntax once written to the file. Port 587/STARTTLS is only suitable when the server supports that mode; endpoints using implicit TLS on 465 need different settings. SMTP credentials should come from the environment or a secret manager, not be hardcoded.

`spring.mail.default-encoding=UTF-8` supports Vietnamese characters in **the text parts**. It does not alter PDF bytes or automatically determine `Content-Type` for attachments.

### 3.1. Creating a MIME message with multipart mode

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Attached document");
helper.setText("Please see the document in the email.", false);
```

The `true` parameter in the constructor enables **multipart** mode. This is a prerequisite when adding attachments with the helper. If you create a helper not in multipart mode and call `addAttachment(...)`, the operation does not fit the message structure and may raise `IllegalStateException`.

The `"UTF-8"` parameter is the **charset** for text content, not a media type, and does not mean binary files will be converted into UTF-8 strings.

### 3.2. `MULTIPART_MODE_MIXED_RELATED` when the message has both HTML and files

For emails with HTML, inline images, and attachments, you can choose the mode:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
```

The helper can organize the MIME parts in `multipart/mixed` and `multipart/related` form to separate attachments from inline resources related to the HTML content. The exact structure depends on the added parts; the application does not need to set `boundary` itself.

In an example with only text and attachments, `new MimeMessageHelper(message, true, "UTF-8")` is sufficient for illustration purposes.

## 4. Method 1 — Adding an attachment from `java.io.File`

When the file is already on disk, the direct way is:

```java
import java.io.File;

File file = new File("/srv/app/reports/invoice.pdf");
helper.addAttachment("invoice.pdf", file);
```

`File` is an object describing **a path to a file**, not all the bytes of the file already loaded into RAM. Jakarta Mail can read the file's data when preparing/serializing the message.

### 4.1. Example of a service sending a file from disk

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@Service
public class FileAttachmentMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public FileAttachmentMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendReport(String recipient, Path reportPath)
            throws MessagingException {
        if (!Files.isRegularFile(reportPath) ||
                !Files.isReadable(reportPath)) {
            throw new IllegalArgumentException("Report file is unavailable");
        }

        File reportFile = reportPath.toFile();
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name()
        );

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Periodic report");
        helper.setText("The report is sent in the attached file.", false);

        helper.addAttachment("report.pdf", reportFile);

        mailSender.send(message);
    }
}
```

The example **assumes the file is genuinely a PDF** and resides on a filesystem where the `Path` can be converted to a `File`. If the file is CSV or XLSX, the filename and media type need to change according to the actual format.

At the business level, you must ensure the file is not deleted, renamed, or overwritten while Jakarta Mail is reading it. A prior `Files.isReadable(...)` check **does not guarantee** the file will still exist at every later moment; when multiple processes operate concurrently, use a separate temporary file or a suitable snapshot mechanism.

### 4.2. Advantages and limitations of `File`

Advantages:

- Short code when the file has already been created on disk.
- No need to pre-allocate a `byte[]` of the entire file in application memory.
- The file can be reopened via its path when the library needs to read multiple times.

Limitations:

- The file must exist and have read permission on the machine running the application.
- Resources inside a JAR or object storage do not necessarily have a valid `File` path.
- The file could be deleted/modified between message creation and the time Jakarta Mail reads it.
- Working with user-supplied paths can lead to **path traversal** or unauthorized file access if uncontrolled.
- Even without loading all bytes into `byte[]` yourself, the send path still consumes RAM, CPU, and transmission bandwidth; there is no “zero-copy” guarantee.

**Do not pass an arbitrary client-supplied path directly into `new File(...)` and send it**. The file must be selected from a set that the application is authorized by business rules to access.

## 5. Method 2 — `InputStream` and `InputStreamSource`

This is the part most easily misunderstood.

### 5.1. An open `InputStream` is a stateful read stream

Java's `InputStream` represents a byte stream currently being read:

```java
InputStream stream = Files.newInputStream(path);
```

Once bytes have been consumed, a stream usually **does not automatically rewind to the beginning**. Some implementations support marking and rewinding via `mark/reset`, but you should not assume you can re-read the entire content or open the stream again from the same instance.

Meanwhile, building a MIME message may require reading an attachment **more than once**; for example, to determine transfer encoding or write the data portion to the sending stream. Therefore, the `MimeMessageHelper` API accepts **`InputStreamSource`**, not a single `InputStream`.

### 5.2. `InputStreamSource` is a factory for streams

`InputStreamSource` belongs to the package:

```java
import org.springframework.core.io.InputStreamSource;
```

Conceptually, it has the contract:

```java
InputStream getInputStream() throws IOException;
```

Each time it is called, a proper implementation must be able to provide **a fresh stream that reads the same content**. For MIME attachments, this is an important condition so that data does not run out mid-way or cause errors when the library needs to access it again.

```text
An open InputStream:
  stream -> read to end -> no guarantee it can be read again

Suitable InputStreamSource:
  getInputStream() -> stream A -> read/close
  getInputStream() -> stream B -> read/close
                         same content bytes
```

Not every class implementing `InputStreamSource` has the same re-read capability. **`InputStreamResource` is a case requiring special caution**, because it usually wraps an already-open stream.

### 5.3. Example using `InputStreamSource` opening a fresh file each time

If you need to write a re-openable source yourself:

```java
import org.springframework.core.io.InputStreamSource;

import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("/srv/app/reports/monthly.csv");
InputStreamSource source = () -> Files.newInputStream(path);

helper.addAttachment(
        "monthly.csv",
        source,
        "text/csv; charset=UTF-8"
);
```

Each time Jakarta Mail calls `source.getInputStream()`, `Files.newInputStream(path)` will return a new stream. **Do not use a lambda that closes over an already-opened `InputStream` and repeatedly returns that exact same instance**:

```java
InputStream openedOnce = Files.newInputStream(path);

// Unsuitable: the same stream is returned on every call.
InputStreamSource oneShot = () -> openedOnce;
```

`InputStreamSource` is suitable when the resource is not a `File` or needs custom stream-opening logic. If merely reading a simple local file, `FileSystemResource` is usually shorter and clearer.

### 5.4. If you already received a single `InputStream` from an external source

Suppose an API or SDK returns an `InputStream` **that can only be used once**. Two common strategies:

**Strategy A — small or medium documents: load bytes into memory.**

```java
import org.springframework.core.io.ByteArrayResource;

byte[] bytes;
try (InputStream input = upstreamStream) {
    bytes = input.readAllBytes();
}

helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(bytes),
        "application/pdf"
);
```

`ByteArrayResource` can create a new `ByteArrayInputStream` over the same byte array on each access. In return, the application holds the entire content in RAM. With large files or many concurrent emails, this approach can consume significant memory.

**Strategy B — large documents: write to a managed temporary file.**

```java
Path temp = Files.createTempFile("mail-attachment-", ".pdf");

try (InputStream input = upstreamStream) {
    Files.copy(input, temp, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
}

// Execute while temp still exists:
helper.addAttachment(
        "document.pdf",
        new org.springframework.core.io.FileSystemResource(temp),
        "application/pdf"
);

mailSender.send(message);

// Clean up the temporary file only after sending has completed
// or after error handling, preferably with a finally block.
```

The second snippet illustrates **part of a workflow**, assuming `helper`, `message`, and `mailSender` have been prepared. In production code, put the copy, send, and temp-file deletion into a `try/finally` structure to avoid leaking files on error; do not delete the file before JavaMail has finished reading it.

If the system can call the object-download API again and receive a fresh stream for the same data, you can also build an `InputStreamSource` that reopens the object. Ensure the data does not change between reads or use an immutable object version/ETag/identifier.

## 6. Method 3 — Spring `Resource` types

`org.springframework.core.io.Resource` is an abstraction for a resource source. Common implementations can read from the filesystem, classpath, or memory. `Resource` also provides the ability to obtain an `InputStream`; thus an appropriate resource can be passed to the `addAttachment(..., InputStreamSource)` overload.

### 6.1. `FileSystemResource` — file on disk

```java
import org.springframework.core.io.FileSystemResource;

FileSystemResource resource =
        new FileSystemResource("/srv/app/reports/invoice.pdf");

helper.addAttachment("invoice.pdf", resource, "application/pdf");
```

`FileSystemResource` preserves the `Resource` abstraction and can reopen the file via its path. It is convenient when other services in the application already use the Spring Resource API.

Like `File`, the file must still exist and be accessible during sending. Having a `FileSystemResource` does not mean the file's bytes were captured into an immutable copy.

### 6.2. `ClassPathResource` — resource packaged with the application

For example, the application has the file:

```text
src/main/resources/mail/guide.pdf
```

It can be attached:

```java
import org.springframework.core.io.ClassPathResource;

ClassPathResource resource =
        new ClassPathResource("mail/guide.pdf");

helper.addAttachment(
        "guide.pdf",
        resource,
        "application/pdf"
);
```

`ClassPathResource` is useful for guide documents, content templates, or static files packaged when building the application.

**Do not force `ClassPathResource` into a `File` via `getFile()` when the application runs in an executable JAR**. A resource packaged inside a JAR is not necessarily an independent file on the filesystem. Reading via the resource's `getInputStream()` is usually more appropriate.

### 6.3. `ByteArrayResource` — bytes in memory

When the application generates PDF or CSV itself, the data may already be in a `byte[]`:

```java
import org.springframework.core.io.ByteArrayResource;

byte[] pdfBytes = invoicePdfGenerator.generate(order);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Here `invoicePdfGenerator.generate(order)` is an **illustrative business function**, not an API provided by Spring Mail.

`ByteArrayResource`:

- Does not require creating a file on disk.
- Is able to provide a fresh stream for subsequent reads.
- Is suitable when bytes are already available in memory.
- Is not suitable if too many very large files must be held simultaneously.

When attaching file bytes, **do not call `new String(pdfBytes, UTF_8)`** and send it as text, because binary bytes may not be representable in UTF-8 and will be corrupted.

### 6.4. `InputStreamResource` — the case easily misused

`InputStreamResource` usually describes an already-opened `InputStream`, so it has **one-shot** characteristics—that is, it is not designed as a factory able to provide a fresh stream for multiple reads.

Example to avoid:

```java
import org.springframework.core.io.InputStreamResource;

InputStream input = Files.newInputStream(path);

// Unsuitable as a MIME attachment if the library needs to re-read.
InputStreamResource resource = new InputStreamResource(input);
helper.addAttachment("report.pdf", resource, "application/pdf");
```

`MimeMessageHelper` may reject a `Resource` holding an open stream, or sending may fail if the source can only be read once. For a file with a `Path`, replace it with `FileSystemResource`. For bytes already read into RAM, use `ByteArrayResource`. For a source that must be reloaded, use an `InputStreamSource` that provides a **fresh** stream each time.

### 6.5. Comparison table of `Resource` types

| Resource | Where data is held | Can data be reopened? | Notes |
| --- | --- | --- | --- |
| `FileSystemResource` | File on filesystem | Usually yes, if the file still exists | Fits local files; mind read permissions and file lifecycle |
| `ClassPathResource` | Classpath/JAR or classpath directory | Usually yes | Do not assume a `File` always exists |
| `ByteArrayResource` | `byte[]` array in RAM | Yes | Memory cost grows with file count and size |
| `InputStreamResource` | Existing stream | **Not guaranteed** | Avoid as attachment when JavaMail needs to re-read |
| Custom `Resource` | Depends on implementation | Must verify specific contract | Key is providing a fresh stream and stable bytes |

## 7. What is the difference between File and Resource?

Both `File` and `Resource` can represent content residing on the filesystem, but their abstraction and usage differ.

| Criterion | `File` | `Resource` |
| --- | --- | --- |
| Type in API | `java.io.File` | `org.springframework.core.io.Resource` |
| Represents physical file | Direct | Can via `FileSystemResource` |
| Supports classpath in JAR | Not a suitable abstraction | `ClassPathResource` |
| Supports bytes in RAM | Not direct | `ByteArrayResource` |
| Has `getInputStream()` method | Read via other Java APIs like `Files.newInputStream(...)` | Present in Resource |
| Use with `MimeMessageHelper` | `addAttachment(filename, File)` overload | Overload accepting `InputStreamSource` |
| Guarantees immutable data | No | Not every Resource is immutable |

Choose according to **data location** and **lifecycle**, not just code length. If a service already manages files on disk using `Path`, using `File` or `FileSystemResource` is reasonable. If the document sits on the classpath or is already a `byte[]`, `Resource` is usually more flexible.

## 8. Determining `Content-Type` for an attachment

For a MIME part, the filename and `Content-Type` are not the same thing. For example:

```text
Filename: invoice.pdf
Media type: application/pdf

Filename: report.csv
Media type: text/csv

Filename: logo.png
Media type: image/png
```

When using an overload without passing `contentType`, `MimeMessageHelper` can rely on **`FileTypeMap`** to guess the MIME type from the filename. In many cases, this works well for common extensions. However, the mapping depends on configuration/libraries and **does not inspect the actual bytes of the file**.

If the application already knows for certain that the data it generated is PDF:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

This is clearer than guessing the type from `invoice.pdf`. Common values:

| Format | Commonly used `Content-Type` |
| --- | --- |
| PDF | `application/pdf` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| CSV | `text/csv` |
| JSON | `application/json` |
| ZIP | `application/zip` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Undetermined | `application/octet-stream` |

**Setting the right `Content-Type` does not alter the data bytes**. If a PDF file is corrupted, declaring `application/pdf` will not fix it.

### CSV and charset

If the system exports CSV in UTF-8, the media type can be expressed as:

```java
helper.addAttachment(
        "report.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
```

This is only meaningful if `csvBytes` was genuinely generated in UTF-8. It also **does not replace** CSV conventions such as delimiters, quoting, or how spreadsheet tools interpret data.

### `Content-Transfer-Encoding` is not `Content-Type`

For binary bytes, the library usually uses base64. But `base64` is not a media type:

```text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
```

An ordinary application does not need to convert PDF bytes to base64 itself and pass the result to `addAttachment(...)`. Doing so may create a file containing the literal base64 string instead of the original PDF data.

## 9. A Spring Boot example using all three source types

Suppose a system has three sending methods:

1. Send a PDF file already on disk.
2. Send a CSV generated in memory.
3. Send a guide document packaged on the classpath.

We can use one service to unify MIME message creation. This section only illustrates the email-sending path; validating recipients, generating files, storing send results, and handling retries must be designed according to business requirements.

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

@Service
public class AttachmentMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public AttachmentMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendPdfFile(String recipient, Path file)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = newHelper(message, recipient);

        helper.setSubject("PDF Report");
        helper.setText("Please see the attached report.", false);
        helper.addAttachment(
                "report.pdf",
                new FileSystemResource(file),
                "application/pdf"
        );

        mailSender.send(message);
    }

    public void sendCsvBytes(String recipient, byte[] csv)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = newHelper(message, recipient);

        helper.setSubject("CSV Data");
        helper.setText("Please see the attached data.", false);
        helper.addAttachment(
                "data.csv",
                new ByteArrayResource(csv),
                "text/csv; charset=UTF-8"
        );

        mailSender.send(message);
    }

    public void sendGuide(String recipient)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = newHelper(message, recipient);

        helper.setSubject("Guide document");
        helper.setText("The guide document is in the attachment.", false);
        helper.addAttachment(
                "guide.pdf",
                new ClassPathResource("mail/guide.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }

    private MimeMessageHelper newHelper(
            MimeMessage message,
            String recipient
    ) throws MessagingException {
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name()
        );
        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        return helper;
    }
}
```

In the example, `FileSystemResource(file)` is a source reading from the filesystem; `ByteArrayResource(csv)` holds existing CSV bytes; `ClassPathResource("mail/guide.pdf")` reads a resource on the classpath. All three are passed as byte sources to `addAttachment(...)`.

**The code assumes valid data sources:** `file` is a real, readable PDF; `csv` is UTF-8 CSV bytes; `guide.pdf` is packaged in `src/main/resources/mail/`. If an assumption is false, errors must be handled at the data creation/validation layer.

## 10. Adding multiple attachments in one email

An email can contain multiple files. Simply call `addAttachment` multiple times **on the same multipart helper**:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("customer@example.net");
helper.setSubject("This month's document set");
helper.setText("Includes PDF and CSV.", false);

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource("/srv/reports/invoice.pdf"),
        "application/pdf"
);
helper.addAttachment(
        "orders.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);

mailSender.send(message);
```

Jakarta Mail will organize the attachments into separate MIME parts. **Do not** call `setText(...)` with all the binary data concatenated together, and there is no need to create `multipart/mixed` headers by hand.

### Duplicate filenames

If you add two attachments both having `attachmentFilename = "report.pdf"`, the email may contain two parts with the same display name. Mail clients may present or save the two files differently. Use distinct names, for example `report-sales.pdf` and `report-stock.pdf`, especially when the system exports multiple reports.

## 11. Distinguishing attachments from inline images

Attachments are usually handled as files the user downloads. **Inline resources** serve HTML content, such as a logo referenced via `cid:logo`.

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Invoice and logo");

helper.setText(
        "<p>The invoice is in the attached file.</p>"
            + "<img src=\"cid:logo\" alt=\"Logo\"/>",
        true
);

helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

mailSender.send(message);
```

`addInline(...)` uses **Content-ID** to link the image to HTML; `addAttachment(...)` creates the attachment part. With `MimeMessageHelper`, set `setText(...)` **before** adding inline resources to have a structure compatible with many mail clients.

The `image/png` media type only helps describe the data; it does not guarantee every mail client will display inline images the same way.

## 12. Stream lifecycle: who opens, who closes, and when is it re-read?

A common error lies not in `Content-Type` but in when the resource is closed or modified.

```text
Application creates message
        |
        | addAttachment(filename, source)
        v
MimeMessage holds reference to source
        |
        | library may read source to determine data characteristics
        v
JavaMail/Jakarta Mail serializes MIME
        |
        | may read source another time to write actual bytes
        v
SMTP transport
        |
        v
Mail server accepts or rejects
```

Therefore:

- There is no guarantee that all bytes are copied immediately at the `addAttachment(...)` call.
- Do not close a shared stream and expect the helper to be able to re-read it.
- Do not delete a temporary file right after attaching it to the helper but before `send(...)` finishes.
- For mutable sources, ensure repeated reads yield the same content.
- If the data source is a remote object, retry/reopen rules must fit that system's API.

### Cleaning up temporary files with `try/finally`

A temporary-file lifecycle management pattern:

```java
Path temporary = Files.createTempFile("mail-report-", ".pdf");
try {
    Files.write(temporary, pdfBytes);

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, true, "UTF-8"
    );

    helper.setFrom("reports@example.org");
    helper.setTo("customer@example.net");
    helper.setSubject("Report");
    helper.setText("Please see the attached file.");
    helper.addAttachment(
            "report.pdf",
            new FileSystemResource(temporary),
            "application/pdf"
    );

    mailSender.send(message);
} finally {
    Files.deleteIfExists(temporary);
}
```

This is a **snippet inside a method**, assuming `mailSender`, `pdfBytes`, and required imports already exist. In Java, exceptions can occur during write, send, or delete operations; real applications need appropriate logging and error-handling policies. The file is deleted only when the synchronous send call has finished. If sending is handed off to an asynchronous worker, the file lifecycle must extend until the worker is no longer using it.

**Note:** confirming `send(...)` completed does not prove the email was delivered to the Inbox. It only reflects the result of the sending process at the corresponding application/SMTP submission layer.

## 13. Security when attaching files

Attachments can carry sensitive data or unsafe content. `MimeMessageHelper` is a MIME packaging tool, **not an anti-malware or access-control tool**.

Essential principles:

1. **Authenticate document read rights:** the caller requesting the send must have permission to access the sent content.
2. **Identify the right recipients:** check To/Cc/Bcc per business rules before sending files.
3. **Restrict paths:** do not take a raw user-entered path and read arbitrary system files.
4. **Do not trust uploaded filenames or media types:** validate the data type against allowed policies.
5. **Limit sizes:** account for both original file size and MIME encoding overhead.
6. **Do not put secrets into attachment names:** filenames can appear in mail clients and logs.
7. **Manage temporary file lifecycles:** place in a location with proper permissions, delete after send or failure.
8. **Do not log sensitive bytes or content:** log only necessary metadata and error codes.
9. **Consider secure download links for large/sensitive files:** emails can be forwarded and stored across many systems.

### What is path traversal in this context?

Suppose an API allows a caller to pass:

```text
GET /send-report?path=../../confidential/data.csv
```

If the backend directly concatenates the path string with a root directory and sends the file, the caller could attempt to select files outside the permitted scope. Fetch files by **business ID**, look up server-controlled metadata, and confine resources within authorized directories/storage spaces.

Do not treat the filename `invoice.pdf` or `Content-Type: application/pdf` as proof a file is safe. Names/metadata can be forged.

## 14. Size, Base64, and performance

Attachments are usually base64-encoded to travel through email. For a binary file of `N` bytes, the base64 data alone is roughly `4/3 × N` long, not counting line breaks and MIME headers.

Qualitative example:

```text
Original file:        9 MB
Base64 (approx):     12 MB
MIME headers/lines:  adds overhead
Entire email:        larger than original file
```

Therefore, if an SMTP provider caps the size of the **entire message** at some level, you cannot pick a file right near that limit and assume the email will be accepted.

Quick comparison:

| Source | Application memory cost | Characteristics to note |
| --- | --- | --- |
| `File` / `FileSystemResource` | No need to load the whole file into a service `byte[]` | Still has buffers/overhead when sending and depends on file still existing |
| `ByteArrayResource` | Holds all bytes in RAM | Easy for small/medium files, RAM-heavy for large files |
| `ClassPathResource` | Usually reads from classpath when needed | Fits static content, not ideal for user-modified files |
| Custom `InputStreamSource` | Depends on implementation | Must reopen stream; may incur repeated access cost |

**No option automatically bypasses SMTP limits or provider quotas.** At high email volumes, calculate connection counts, memory, transmission size, and retry policies concurrently.

## 15. Distinguishing attachment preparation errors from SMTP errors

Attachment errors can arise at multiple layers:

| Symptom | Possible cause | Direction to handle |
| --- | --- | --- |
| File not found | Wrong path, file deleted | Check file location and lifecycle |
| File unreadable | Read permission, lock, or I/O | Check access rights and filesystem status |
| Attachment has 0 bytes | Stream source already exhausted or returned empty content | Ensure source opens a fresh stream and source bytes are right |
| `InputStreamResource` rejected | Resource holds an open stream, unsuitable for re-reading | Use `FileSystemResource`/`ByteArrayResource` |
| Received PDF file is corrupted | Wrong source bytes, converted to String, or data changed between reads | Compare source bytes and resource creation |
| File has right name but wrong icon/preview | Missing or unsuitable `Content-Type` | Use overload with explicit `contentType` |
| Mail client does not recognize attachment | Wrong MIME structure/`Content-Disposition` | Use `MimeMessageHelper` multipart instead of hand-writing headers |
| Message rejected due to size | SMTP/provider limit, base64 overhead | Shrink file, compress appropriately, or use a download link |
| SMTP requires authentication | Wrong credentials/TLS config | Check submission endpoint and SMTP AUTH |
| Sent but recipient has not seen it | Message still in queue, filtered, or bounced downstream | Use provider logs/queues/delivery events |

### Exceptions to distinguish

- **`MessagingException`** (Jakarta Mail) may occur when preparing content, recipients, or MIME parts.
- **`MailException`** and Spring subclasses may appear when using `JavaMailSender.send(...)`.
- **`IOException`** may occur when reading streams/files in application-managed steps.
- **`IllegalArgumentException`** or state errors may occur if passing an invalid resource or the helper is not yet in multipart mode.

Do not catch every error and retry infinitely. If the source file is corrupted or unreadable, SMTP retries will not solve the problem. If encountering transient network errors, retry with limits and consider the scenario where **the SMTP server may have received the message even though the client did not receive the final response**, avoiding uncontrolled duplicate sends.

## 16. Common mistakes

### Mistake A: passing `InputStreamResource` for a one-time stream

```java
InputStream stream = Files.newInputStream(path);
helper.addAttachment(
        "invoice.pdf",
        new InputStreamResource(stream),
        "application/pdf"
);
```

Problem: the source does not promise to create a fresh stream on the next read. Better direction:

```java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(path),
        "application/pdf"
);
```

If the source only provides one stream from an external service, save the bytes in RAM or a temporary file and then use a re-readable source.

### Mistake B: creating a non-multipart helper

```java
MimeMessageHelper helper = new MimeMessageHelper(message);
helper.addAttachment("invoice.pdf", resource);
```

Attaching requires MIME multipart. When you know ahead of time there is an attachment:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8"
);
```

### Mistake C: passing binary bytes into `setText`

```java
helper.setText(new String(pdfBytes, StandardCharsets.UTF_8));
```

`setText` is for text. Converting a PDF byte array to text can cause data loss. Use `addAttachment(...)` with the raw bytes.

### Mistake D: deleting the file before `send`

```java
helper.addAttachment("report.pdf", new FileSystemResource(tempPath));
Files.delete(tempPath);
mailSender.send(message);
```

Here the path disappeared before the library might need to read the file. Keep the file until the synchronous send operation completes, then clean up in `finally`.

### Mistake E: choosing MIME type from an untrusted extension

An upload with filename `invoice.pdf` might contain different data. FileTypeMap does not check PDF signatures. Choose `application/pdf` only when the format has been verified or checked appropriately by the application.

### Mistake F: adding an attachment by setting raw headers manually

```java
message.setHeader("Content-Type", "application/pdf");
```

This statement does **not** create an attachment part by itself; it can also make top-level MIME headers conflict with the body. To create attachments, use `MimeMessageHelper.addAttachment(...)` in multipart mode.

## 17. Applied scenarios

### Scenario 1: PDF invoice generated directly in memory

The application has:

```java
byte[] invoice = invoiceService.renderPdf(orderId);
```

`invoiceService.renderPdf(orderId)` is an illustrative business API. Suitable choice:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoice),
        "application/pdf"
);
```

No need to create a temporary file if the data is small/medium and already in RAM.

### Scenario 2: attaching a large file already on the server

The application knows the path to an authorized file.

Suitable choice:

```java
helper.addAttachment(
        "archive.zip",
        new FileSystemResource(archivePath),
        "application/zip"
);
```

No need to read the entire file into `byte[]` just to send. However, message size after Base64 and SMTP limits still need to be considered.

### Scenario 3: guide file residing in a JAR

Choice:

```java
helper.addAttachment(
        "guide.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);
```

Does not depend on whether a resource inside the JAR can be converted to `java.io.File`.

### Scenario 4: SDK returns only a read-once stream

Choose between:

- Loading bytes via `readAllBytes()` and using `ByteArrayResource` when the file is small enough and has reasonable size limits.
- Copying the stream to a temporary file and using `FileSystemResource` when the file is large, while ensuring file cleanup.
- If the API supports reopening the same immutable object, creating an `InputStreamSource` whose `getInputStream()` calls that API each time.

Do not return the same consumed `InputStream` via `InputStreamSource`.

### Scenario 5: email with both an inline logo and a PDF report

Create an appropriate multipart helper, use `setText(html, true)`, add the logo via `addInline("logo", resource, "image/png")` and the PDF via `addAttachment("report.pdf", resource, "application/pdf")`. These two operations create **two kinds of MIME parts with different roles**.

### Scenario 6: mail client opens CSV file with wrong Vietnamese characters

Check whether the real CSV bytes were generated in UTF-8, choose `Content-Type: text/csv; charset=UTF-8` when appropriate, and consider how spreadsheet software opens CSV. `spring.mail.default-encoding=UTF-8` for the text body does not automatically convert all content of a CSV file that the application generated with another charset.

## 18. Quick decision table

| Question | Choice to consider |
| --- | --- |
| Does the file currently exist on the filesystem? | `File` or `FileSystemResource` |
| Are bytes already available in RAM? | `ByteArrayResource` |
| Does the resource sit on the classpath/JAR? | `ClassPathResource` |
| Does the source provide a fresh stream for every call? | Appropriate `InputStreamSource` |
| Only have one already-open stream? | Convert to `byte[]` or temp file; avoid one-shot `InputStreamResource` |
| Format of data already known? | Use `addAttachment(filename, source, contentType)` overload |
| Multiple attached files? | Call `addAttachment` multiple times on the same multipart helper |
| Image referenced in HTML? | Use `addInline` with matching Content-ID |
| Email size limit exists? | Account for MIME/Base64 overhead; consider secure download link |
| File might change/be deleted during send? | Keep stable snapshot, manage lifecycle before and during `send` |

## 19. Conclusion

`MimeMessageHelper.addAttachment(...)` lets Spring Framework Mail attach data from many sources without the application having to hand-write the MIME protocol. **`File`** fits files on disk; **`FileSystemResource`** and **`ClassPathResource`** leverage Spring's abstraction; **`ByteArrayResource`** is useful when data is already in RAM; and **`InputStreamSource`** is the contract for a source providing re-readable streams.

The key takeaway when sending attachments from byte streams is: **Jakarta Mail may open the source multiple times, so each time must read the same content**. Alongside that, create the helper in multipart mode, use a `Content-Type` matching the data, preserve raw binary bytes, and manage the file/stream lifecycle until sending finishes. These principles make emails with attachments more reliable, easier to extend, and less prone to data loss or corruption.
