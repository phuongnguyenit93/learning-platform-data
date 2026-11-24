# File Content Types and FileTypeMap

When sending an email with attachments using **Spring Framework Mail**, the application does not just need to provide file bytes and a filename. Each MIME part must also describe its **content type (Content-Type)** so the email client knows whether the data is a PDF, PNG image, CSV, Word document, or a generic byte stream. If declared incorrectly, recipients may see the wrong file icon, be unable to open the file in the expected application, or encounter unexpected handling behavior.

Spring provides **MimeMessageHelper** to add attachments and inline resources. When only a filename and an **InputStreamSource** are passed, the helper needs to determine the MIME type for the part. Jakarta Activation's **FileTypeMap** mechanism performs the mapping from filename or extension to content type. Developers can also specify an explicit MIME type when the exact data type is already known.

This lesson explains the role of **Content-Type**, how **FileTypeMap** works, how to configure mappings for custom formats, and how to inspect the result in a **MimeMessage**. The final sections cover important limitations: a file extension does not prove actual content, **application/octet-stream** is the generic fallback, and MIME type does not replace file safety checks.

## 1. Content-Type in a MIME attachment

Email supports multiple content types via MIME (*Multipurpose Internet Mail Extensions*). An attachment is typically represented as a **body part** inside the email's multipart structure.

For example, an attached PDF might have headers like:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQK...
~~~

The three headers above serve three distinct purposes:

| Header | Role | Example |
| --- | --- | --- |
| **Content-Type** | Describes the part's data type | `application/pdf` |
| **Content-Transfer-Encoding** | Describes how bytes are represented in the MIME body | `base64`, `quoted-printable`, `7bit` |
| **Content-Disposition** | Hints how the part is presented and its filename | `attachment; filename="invoice.pdf"` |

**Content-Type is not the filename.** `application/pdf` indicates the part contains PDF data; `invoice.pdf` is the filename supplied to the recipient. The two values usually correspond, but they do not automatically validate one another.

**Content-Transfer-Encoding also does not determine the file format.** Base64 can be used to transport PDF bytes, PNG images, or ZIP archives. After decoding the transfer encoding, the original bytes still belong to the data type described by Content-Type.

### Media type structure

A media type has the general form:

~~~text
type/subtype; parameter=value
~~~

Examples:

| Media type | Meaning |
| --- | --- |
| `application/pdf` | PDF document |
| `image/png` | PNG image |
| `image/jpeg` | JPEG image |
| `text/plain; charset=UTF-8` | UTF-8 plain text |
| `text/csv; charset=UTF-8` | UTF-8 text-based CSV data |
| `application/zip` | ZIP archive |
| `application/json` | JSON data |
| `application/octet-stream` | Generic byte data, not specifically described |

The **type** part is usually a broad category such as `text`, `image`, `audio`, `video`, `application`, or `multipart`. The **subtype** identifies the more specific format. Parameters may supply a charset or other information depending on the content type.

### What does Content-Type affect?

Email clients use MIME metadata to decide how to interpret a part:

- An `application/pdf` part may be recognized as a PDF document.
- An `image/png` part may be previewed as an image.
- A `text/csv` part may be opened with a spreadsheet app or text viewer.
- An `application/octet-stream` part is usually treated as generic binary data and may prompt the user to choose an application to open it.

This is a **format hint for the receiving software**, not an enforceable command. Email clients, operating systems, and security policies can still choose different behavior.

## 2. What is FileTypeMap?

**FileTypeMap** is an abstract class in Jakarta Activation that provides a mechanism to map filenames or file objects to **MIME content types**. Spring Mail uses this mechanism when preparing a MIME body part for an attachment or inline resource for which the application has not supplied an explicit Content-Type.

The main APIs live in the package:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
~~~

`FileTypeMap` defines MIME type lookup methods. `MimetypesFileTypeMap` is a common implementation that reads mappings of MIME types and extensions.

Conceptual example:

~~~java
FileTypeMap map = FileTypeMap.getDefaultFileTypeMap();

String pdfType = map.getContentType("invoice.pdf");
String pngType = map.getContentType("logo.png");
String unknownType = map.getContentType("archive.unknownext");
~~~

Common results might be:

~~~text
invoice.pdf              -> application/pdf
logo.png                 -> image/png
archive.unknownext       -> application/octet-stream
~~~

Exact results depend on the implementation, loaded mappings, runtime environment, and application configuration. Do not assume a default mapping set is identical across all machines.

### FileTypeMap looks up by name, not content verification

A crucial point: **FileTypeMap primarily infers from the filename/extension**. If a text file is named `report.pdf`, the mapping may return `application/pdf` even though the bytes are not a PDF.

Example:

~~~text
Filename: invoice.pdf
Actual content: plain text "hello"

FileTypeMap may return: application/pdf
~~~

This is not a bug in FileTypeMap. It answered the question **"What MIME type does this extension usually correspond to?"**, not **"What format are the bytes inside the file actually in?"**.

To verify content, the application must add byte-inspection steps or use a parser appropriate for the file type, alongside security policies and an allowlist of permitted formats.

## 3. How does MimeMessageHelper use FileTypeMap?

Spring Mail provides **MimeMessageHelper** to add attachments and inline resources without manually creating `MimeBodyPart` instances or setting MIME boundaries.

A common call:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath)
);
~~~

In this overload, the application passes:

- The attachment name that will appear to the recipient: `invoice.pdf`.
- An **InputStreamSource** supplying the file content.

The helper needs to determine Content-Type for the part. It uses the **FileTypeMap** configured on the helper to infer from the filename. Then, the helper creates the body part and attaches the data source.

Conceptual flow:

~~~text
MimeMessageHelper.addAttachment(filename, resource)
                 |
                 v
          FileTypeMap
                 |
                 | filename -> MIME type
                 v
          application/pdf
                 |
                 v
          MIME body part
          Content-Type: application/pdf
          Content-Disposition: attachment
                 |
                 v
          MimeMessage
                 |
                 v
          JavaMailSender.send(...)
~~~

### Attachment name can differ from the source filename

Example:

~~~java
helper.addAttachment(
        "monthly-report.pdf",
        new FileSystemResource(sourcePath)
);
~~~

The MIME type is inferred from the **attachment filename** used by the helper. If the source file has a different extension or no extension, while the passed attachment name ends in `.pdf`, the lookup can follow `.pdf`.

This is helpful when the application renames the file for the recipient, but it is also why you must verify that **the filename and MIME type match the actual content**. Naming something `.pdf` does not turn arbitrary data into a PDF.

### Both attachments and inline resources need a MIME type

When adding an inline image:

~~~java
helper.addInline(
        "company-logo",
        new FileSystemResource(logoPath)
);
~~~

The image part also needs a Content-Type so email clients know how to interpret the bytes. If inferred from a filename, `logo.png` may map to `image/png`; a name without an extension or a missing mapping may fall back to a generic type.

If the exact image type is known, you can pass the explicit MIME type to the corresponding overload. Determining Content-Type does not replace **Content-ID** and the `multipart/related` structure; those are separate pieces for HTML to reference the image.

## 4. Default MIME type and application/octet-stream

When no mapping is found for a filename, common implementations of `MimetypesFileTypeMap` typically return:

~~~text
application/octet-stream
~~~

This is the generic media type for a byte stream. It means the application could not provide a more specific type from the available mappings.

Examples:

| Filename | Possible result |
| --- | --- |
| `photo.png` | `image/png` |
| `invoice.pdf` | `application/pdf` |
| `notes.txt` | `text/plain` |
| `data.unknownext` | `application/octet-stream` |
| `payload` | `application/octet-stream` |

Do not treat `application/octet-stream` as an email-sending failure. The file can still be attached and downloaded; the client merely lacks specific format metadata. However, if business rules require recipients to receive a PDF, CSV, or image with an explicit Content-Type, provide a mapping or specify the MIME type explicitly.

### Do not replace octet-stream with an arbitrary type

When seeing `application/octet-stream`, do not set every file to `application/pdf` or `application/zip` just to make the attachment icon look nicer. A wrong MIME type can cause receiving software to attempt opening the bytes with an incompatible parser.

Determine the actual format from an authoritative source, then select the matching MIME type. If it cannot be determined, keep the generic type or reject the file per product policy.

## 5. Ways to provide Content-Type in Spring Mail

There are three common approaches:

1. Let **FileTypeMap** infer from the filename.
2. Configure **custom mappings** so extensions are recognized.
3. Pass an **explicit Content-Type** when calling the attachment/inline method.

The right choice depends on the data source and your level of certainty about the format.

### Approach 1: Using the default mapping

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setTo(recipient);
helper.setSubject("Document");
helper.setText("The file is attached.");

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath)
);

mailSender.send(message);
~~~

With suitable default mappings, `.pdf` is typically recognized as `application/pdf`. This approach is simple when using common formats and the runtime already includes the corresponding mappings.

### Approach 2: Specifying Content-Type when adding the attachment

When the application already knows the data type from a trusted source:

~~~java
helper.addAttachment(
        "export.csv",
        new FileSystemResource(csvPath),
        "text/csv; charset=UTF-8"
);
~~~

Or:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf"
);
~~~

The overload accepting **contentType** avoids relying on filename-based mapping for that part. It is especially useful for application-generated filenames, extensionless names, or content types not recognized by default mappings.

**An explicit MIME type must still match the actual bytes.** This is a metadata declaration, not a format conversion operation. If you pass `application/pdf` for a CSV, the part still contains CSV bytes.

## 6. Creating a custom FileTypeMap

When an application frequently attaches formats not yet recognized by default mappings, you can add custom mappings. With **MimetypesFileTypeMap**, the **addMimeTypes(...)** method accepts lines formatted as:

~~~text
mime/type extension1 extension2 ...
~~~

Example:

~~~java
import jakarta.activation.MimetypesFileTypeMap;

MimetypesFileTypeMap fileTypeMap = new MimetypesFileTypeMap();
fileTypeMap.addMimeTypes("text/csv csv");
fileTypeMap.addMimeTypes(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document docx"
);
fileTypeMap.addMimeTypes(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet xlsx"
);
fileTypeMap.addMimeTypes("application/x-example-report rptx");
~~~

This mapping indicates:

| Extension | MIME type |
| --- | --- |
| `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| `xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `csv` | `text/csv` |
| `rptx` | `application/x-example-report` |

The first two MIME types are standard types for Office Open XML formats. **application/x-example-report** is merely an example of an application-specific media type; when designing a real format, choose a registered type or an appropriate vendor type per organizational conventions.

After building the mapping, you can query it:

~~~java
System.out.println(fileTypeMap.getContentType("quarterly.docx"));
System.out.println(fileTypeMap.getContentType("sales.xlsx"));
System.out.println(fileTypeMap.getContentType("export.csv"));
~~~

The mapping affects only lookups performed against that specific **fileTypeMap** instance. Creating a separate mapping object does not automatically alter every `FileTypeMap` in the JVM.

### Configuring the mapping on MimeMessageHelper

One way is to pass the `FileTypeMap` to a **MimeMessageHelper** constructor:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimetypesFileTypeMap fileTypeMap = new MimetypesFileTypeMap();
fileTypeMap.addMimeTypes("text/csv csv");

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8",
        (FileTypeMap) fileTypeMap
);

helper.setTo(recipient);
helper.setSubject("Report");
helper.setText("The report is attached.");
helper.addAttachment(
        "sales.csv",
        new FileSystemResource(csvPath)
);
~~~

With the constructor accepting **FileTypeMap**, the helper uses the provided mapping when inferring MIME types for parts. Check the API of your project's Spring Framework version if using an older release; constructor signatures can differ across library generations.

### Managing FileTypeMap as a Spring bean

If multiple services send the same file types, you can define a shared bean:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MailAttachmentConfiguration {

    @Bean
    public FileTypeMap mailFileTypeMap() {
        MimetypesFileTypeMap map = new MimetypesFileTypeMap();
        map.addMimeTypes("text/csv csv");
        map.addMimeTypes("application/x-example-report rptx");
        return map;
    }
}
~~~

The service injects the bean and passes it to the helper:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AttachmentMailService {

    private final JavaMailSender mailSender;
    private final FileTypeMap fileTypeMap;

    public AttachmentMailService(
            JavaMailSender mailSender,
            FileTypeMap fileTypeMap
    ) {
        this.mailSender = mailSender;
        this.fileTypeMap = fileTypeMap;
    }

    public void sendReport(String recipient, Resource report)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8",
                fileTypeMap
        );

        helper.setTo(recipient);
        helper.setSubject("Report");
        helper.setText("The report is attached.");
        helper.addAttachment("monthly-report.rptx", report);

        mailSender.send(message);
    }
}
~~~

Registering a bean lets services share the same mapping set. Treat the map after initialization as **shared configuration, never mutating it arbitrarily per request**. If a service needs a one-off exception for a file type, pass an explicit Content-Type on that call or create a clearly scoped separate map.

### Why not replace the JVM-wide default FileTypeMap?

Jakarta Activation has an API to set the shared **default FileTypeMap**. Changing the global default can affect other components in the same process, not just Spring Mail:

- Another library may also rely on the default FileTypeMap.
- Tests running in parallel can interfere with each other if global state is mutated.
- One module's custom setting can inadvertently alter MIME types in another module.
- It becomes hard to trace where the default was changed during incident investigation.

In a Spring application, passing a specific instance into **MimeMessageHelper** usually keeps configuration scope clear and easier to test.

## 7. Mapping files and multiple extensions

Besides calling **addMimeTypes(...)** in Java, **MimetypesFileTypeMap** can load mappings from MIME types configuration sources supported by the implementation. A simple mapping file looks like:

~~~text
text/csv csv
application/x-example-report rptx
application/vnd.openxmlformats-officedocument.presentationml.presentation pptx
image/webp webp
~~~

Each line contains a media type followed by one or more extensions. Do not include a leading dot before extensions in standard mappings.

One MIME type can correspond to multiple extensions:

~~~text
image/jpeg jpeg jpg jpe
~~~

And an extension can have different mappings across different configuration systems. If duplicate mappings exist, the outcome depends on the implementation's loading/precedence rules and mapping sources; do not depend on accidental ordering. Keep mappings consistent and avoid declaring the same extension under conflicting MIME types.

### Compound extension formats

A name such as:

~~~text
backup.tar.gz
~~~

is typically looked up by its final extension under FileTypeMap rules, namely **gz**, rather than recognizing the full **tar.gz** sequence as a distinct file type. Some mapping systems may support custom rules, but do not assume FileTypeMap recognizes compound extension structures.

If business logic needs to distinguish **.tar.gz** from other **.gz** files, use explicit file-classification logic before calling the helper and pass the appropriate Content-Type.

### Extensions and case sensitivity

Names like **REPORT.PDF** and **report.pdf** are usually recognized as the same type by common mappings. However, if building a custom FileTypeMap, enforce consistent extension normalization; do not assume every custom implementation handles casing identically.

## 8. Distinguishing FileTypeMap from other MIME detection methods

In Java, several APIs can return a MIME type based on a name or path. They are not the same mechanism.

| API/mechanism | Primary inference source | Key notes |
| --- | --- | --- |
| **Jakarta Activation FileTypeMap** | Mapping by filename or File | Used by Jakarta Mail/Activation in the MIME flow |
| **MimetypesFileTypeMap** | Loaded MIME type mappings | Supports adding custom mappings |
| **Files.probeContentType(Path)** | OS or runtime file type detector/provider | Result is environment-dependent, may return null |
| **URLConnection.guessContentTypeFromName(...)** | Filename and URLConnection mappings | Name-based heuristic, does not verify bytes |
| **Magic-byte detector/parser** | Byte signatures or content structure | Can recognize content better but never guarantees absolute safety |

NIO example:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("report.pdf");
String detected = Files.probeContentType(file);
~~~

**Files.probeContentType(...)** may return null if no detector recognizes the file. Results can vary across Windows, Linux, macOS, containers, and runtime providers. It does not necessarily use the same mappings as **MimetypesFileTypeMap**.

### Do not mix results without a policy

Suppose:

~~~text
FileTypeMap.getContentType("report.pdf")
    -> application/pdf

Files.probeContentType(path)
    -> application/octet-stream
~~~

Two APIs can use different mapping sources. The application must decide **which source is authoritative** for the email-sending flow. If the system already knows the format from its PDF generation pipeline, using the business-determined MIME type is usually clearer than querying multiple detectors and picking the first result at random.

### Magic bytes are also only a signal

Some formats have characteristic byte signatures; for example, PDFs typically start with the byte sequence corresponding to `%PDF-`. Checking magic bytes helps catch some spoofed extensions, yet:

- A file may contain a valid header while trailing content is corrupted.
- Many formats share a common container or ZIP structure.
- A file can contain actively malicious content despite a valid signature.
- A format-valid file can still contain macros, scripts, or dangerous payloads.

Therefore, combining extension checks, MIME mappings, signature detection, and parsers/antivirus per policy is the safer approach when the application accepts files from untrusted sources.

## 9. Checking Content-Type after MimeMessageHelper builds the attachment

After the helper creates the MIME part, you can inspect **Content-Type**, **Content-Disposition**, and **filename** directly from the message. This confirms metadata was attached properly before sending.

Example building a message for inspection:

~~~java
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setTo("learner@example.test");
helper.setSubject("Document");
helper.setText("The PDF file is attached.");
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(Path.of("data/invoice.pdf"))
);

message.saveChanges();
~~~

Then, read the root multipart and child parts:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

Object content = message.getContent();
if (content instanceof Multipart multipart) {
    for (int i = 0; i < multipart.getCount(); i++) {
        BodyPart part = multipart.getBodyPart(i);
        System.out.println("type=" + part.getContentType());
        System.out.println("disposition=" + part.getDisposition());
        System.out.println("filename=" + part.getFileName());
    }
}
~~~

For a PDF attachment, expected output looks like:

~~~text
type=application/pdf
disposition=attachment
filename=invoice.pdf
~~~

Actual output may include additional charset, boundary, or header parameters. **Content-Type** can typically be `application/pdf` without a charset because PDF is binary data.

### Recursive multipart traversal

A complex email may have **multipart/mixed** at the root, containing **multipart/related** and **multipart/alternative** inside. Inspecting only direct children of the root can miss deeply nested attachments or inline resources.

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;

public final class AttachmentInspector {

    private AttachmentInspector() {
    }

    public static void inspect(Part part)
            throws MessagingException, IOException {

        String type = part.getContentType();
        String disposition = part.getDisposition();
        String filename = part.getFileName();

        System.out.printf(
                "type=%s disposition=%s filename=%s%n",
                type,
                disposition,
                filename
        );

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    inspect(child);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nested) {
                inspect(nested);
            }
        }
    }
}
~~~

This function only prints metadata and descends into multipart/nested message containers. It does not read file payloads. This is a safer option when you only need to inspect structure; avoid calling **getContent()** on every binary part unnecessarily.

### Do not assert only on filename

If a test only asserts:

~~~java
assertEquals("invoice.pdf", part.getFileName());
~~~

that does not prove Content-Type is right. Check at least:

~~~java
assertTrue(part.isMimeType("application/pdf"));
assertEquals(Part.ATTACHMENT, part.getDisposition());
assertEquals("invoice.pdf", part.getFileName());
~~~

Depending on the Jakarta Mail version and serialization, disposition may vary in case or include parameters; in tests, use case-insensitive checks or compare normalized values.

## 10. Testing mappings and attachments

`FileTypeMap` can be tested independently of SMTP:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.activation.MimetypesFileTypeMap;
import org.junit.jupiter.api.Test;

class MailFileTypeMapTest {

    @Test
    void mapsCustomReportExtension() {
        MimetypesFileTypeMap map = new MimetypesFileTypeMap();
        map.addMimeTypes("application/x-example-report rptx");

        assertEquals(
                "application/x-example-report",
                map.getContentType("monthly.rptx")
        );
    }
}
~~~

This test only verifies **filename-based mapping**. It does not inspect file contents or a sent MIME message.

### Testing the MIME part created by the helper

A test can build a message in memory, add an attachment, and inspect the part:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

class AttachmentContentTypeTest {

    private final JavaMailSender mailSender = createTestMailSender();

    @Test
    void createsPdfAttachmentWithExpectedContentType() throws Exception {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setTo("learner@example.test");
        helper.setSubject("Invoice");
        helper.setText("Attached.");
        helper.addAttachment(
                "invoice.pdf",
                new FileSystemResource(Path.of("src/test/resources/invoice.pdf"))
        );

        message.saveChanges();
        Multipart multipart = (Multipart) message.getContent();

        Part attachment = multipart.getBodyPart(1);
        assertTrue(attachment.isMimeType("application/pdf"));
        assertEquals(Part.ATTACHMENT, attachment.getDisposition());
        assertEquals("invoice.pdf", attachment.getFileName());
    }
}
~~~

**createTestMailSender()** is a test helper setting up a `JavaMailSender`, not a built-in Spring API. This example assumes the text body is the first part and the attachment is the second part in this simple layout. If you change the multipart mode or add inline/alternative parts, locate the attachment by **disposition + filename + MIME type** rather than a fixed index.

### Testing after serialization

To observe headers in actual MIME form, call **saveChanges()** and write the message to an output stream in tests. Then re-parse the raw message via **MimeMessage(Session, InputStream)** and inspect parts. This confirms metadata is represented in MIME after serialization rather than only checking the in-flight builder object.

Do not compare the entire raw message against a fixed string because boundaries and some headers are generated dynamically. Parse the MIME and assert **Content-Type**, **Content-Disposition**, filename, and required content.

## 11. Content-Type for common file types

Some commonly used media types when attaching files:

| Format | Common extensions | MIME type |
| --- | --- | --- |
| PDF | `pdf` | `application/pdf` |
| PNG | `png` | `image/png` |
| JPEG | `jpg`, `jpeg` | `image/jpeg` |
| GIF | `gif` | `image/gif` |
| WebP | `webp` | `image/webp` |
| CSV | `csv` | `text/csv` |
| Plain text | `txt` | `text/plain` |
| JSON | `json` | `application/json` |
| XML | `xml` | `application/xml` |
| ZIP | `zip` | `application/zip` |
| GZIP | `gz` | `application/gzip` |
| Microsoft Word Open XML | `docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Microsoft Excel Open XML | `xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| Microsoft PowerPoint Open XML | `pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |

The list above shows common examples, not an exhaustive catalog. Some older formats have legacy or vendor-specific MIME types; when integrating with external systems, use the type agreed upon by both sides.

### Text files and charset

For text files, Content-Type may need a charset parameter:

~~~text
Content-Type: text/csv; charset=UTF-8
~~~

This helps describe how text bytes should be decoded. However, **FileTypeMap usually maps extensions to a base media type**, such as `text/csv`; it does not automatically append a charset matching the content.

If generating a UTF-8 CSV, make sure the bytes are actually UTF-8 and declare the matching Content-Type. If the bytes use another encoding while the header states UTF-8, recipients may see garbled characters. Adding a charset to the header does not transcode bytes.

### Binary files do not need a charset

PDF, PNG, JPEG, and ZIP are binary data. Do not attach `charset=UTF-8` to those types merely because the email overall uses UTF-8. Charset applies to text content, whereas bytes of binary attachments are preserved via transfer encoding.

## 12. When to use mapping vs. explicit MIME type?

| Scenario | Suggested choice | Reason |
| --- | --- | --- |
| Common format, standard extension | Default `FileTypeMap` | Simple, minimal configuration |
| App has custom format, stable extension | Custom mapping | Reusable across multiple attachments |
| App-renamed or extensionless file | Explicit Content-Type | Independent of filename |
| Text content needing specific charset | Explicit Content-Type with charset | Base MIME type does not describe encoding |
| File type known from trusted system metadata | Pass verified MIME type | Avoids re-guessing from name |
| User-uploaded file, unverified | Validate first, do not send yet | Extensions and MIME headers do not confirm safety |

A system can combine all three: use default mappings for ordinary files, add custom mappings for internal formats, and pass explicit Content-Type for special parts.

### Example CSV with UTF-8 charset

~~~java
helper.addAttachment(
        "customers.csv",
        new FileSystemResource(csvPath),
        "text/csv; charset=UTF-8"
);
~~~

This snippet assumes the source file was written in UTF-8. If the file is actually UTF-16 or another encoding, convert the bytes to UTF-8 before declaring it. Content-Type only describes existing data; it does not transform it.

### Example inline image with explicit MIME type

~~~java
helper.addInline(
        "brand-logo",
        new FileSystemResource(logoPath),
        "image/png"
);
~~~

HTML can reference:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

The MIME type describes the image bytes; Content-ID links the image part to HTML; `multipart/related` groups the related parts. All three factors have distinct roles and all must be correct.

## 13. Content-Type is not a file security mechanism

A serious design flaw is believing a file is safe simply because:

- Its extension is on an allowlist.
- `FileTypeMap` returns a valid MIME type.
- The client renders a PDF or image icon.
- The Content-Type header looks right.

Those signals **do not prove the bytes are safe content**. An attacker can rename a file, spoof the MIME type in a request, or craft malicious data intentionally.

Example:

~~~text
Client-sent filename: invoice.pdf
Client-declared Content-Type: application/pdf
Actual bytes: other content or malicious payload
~~~

If the server simply trusts the client-supplied filename and header and forwards them straight into an email, the application may distribute malformed or dangerous content.

### Verification layers to have

For files coming from users or external systems, you can apply:

1. **File type allowlist**: accept only formats genuinely needed by business rules.
2. **Size limits**: check both per-file size and total attachment size.
3. **Filename sanitization**: prevent path traversal, control characters, header injection, and misleading names.
4. **Extension checks**: use as an input signal, never final proof.
5. **Signature/magic-byte inspection**: catch certain spoofed extensions.
6. **Dedicated library parsing**: verify content structure per file type if required by business rules.
7. **Malware scanning**: apply security tools appropriate for the environment.
8. **Server-side MIME type determination**: select based on validation results or trusted metadata rather than accepting arbitrary client values verbatim.
9. **Permission and lifecycle controls**: allow reading only the validated file source, avoiding file replacement between validation and sending.

Not every system needs every layer at the same strictness. Control depth depends on data type, upload source, and the impact of distributing a bad file.

### Do not manually concatenate raw MIME headers

Do not build headers by string-concatenating user data:

~~~java
part.setHeader(
        "Content-Type",
        uploadedMimeType + "; name=" + uploadedFilename
);
~~~

Uncontrolled filenames or MIME types can produce malformed headers or cause injection if concatenated directly. Use Jakarta Mail/Spring MIME APIs, validate names and data types, and let the library handle proper encoding/quoting.

**MimeMessageHelper** helps build well-formed MIME parts; it does not replace application validation for uploaded data.

### Filenames and privacy

Attachment names can contain customer names, record IDs, account numbers, or internal information. Before sending an email, create a concise display name and avoid exposing unnecessary sensitive data in filenames.

For example, instead of using an internal path:

~~~text
/srv/app/private/customer-12345/medical-record-2026.pdf
~~~

provide a business-neutral display name:

~~~text
document.pdf
~~~

Internal storage paths must never become display filenames shown to recipients.

## 14. Common errors and troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Attachment shows as `application/octet-stream` | No mapping for extension or filename has no extension | Check the `FileTypeMap` used by the helper and the attachment name |
| PDF declared as `text/plain` | Wrong mapping or extension mapped to wrong MIME type | Check conflicting mappings, explicit Content-Type, and source bytes |
| Inline image not displayed | Wrong image MIME type, mismatched Content-ID, or improper `multipart/related` | Check Content-Type, Content-ID, HTML `cid` reference, and MIME tree |
| CSV opens with garbled Vietnamese accents | Charset header does not match byte encoding | Inspect file bytes and declared charset |
| File has right name but fails to open | Actual content is wrong format, corrupted, or truncated | Check signature/parser and decoded payload |
| Attachment name has garbled characters | Filename encoding/quoting or unnormalized name data | Check `getFileName()` and raw MIME header |
| Cannot read attachment on send | Resource no longer available or read-once `InputStream` | Check Resource lifecycle and serialization timing |
| Custom mapping has no effect | Helper is using a different `FileTypeMap` | Check constructor/bean passed to helper |

### Mapping is not being used as expected

If you added a mapping yet the part still gets `application/octet-stream`, check:

1. What attachment filename is actually passed to the helper?
2. Which `FileTypeMap` instance is attached to the `MimeMessageHelper`?
3. Does the mapping have the right extension and valid syntax?
4. Is another mapping conflicting with that extension?
5. Is an explicit Content-Type overload overriding inference?

Do not inspect only the JVM default `FileTypeMap` if the helper was created with a dedicated instance.

### Wrong Content-Type despite right extension

`FileTypeMap` does not read file contents. If a malformed file has a valid extension, the mapping will still return the MIME type for that extension. In this case, adding another mapping will not fix the problem; inspect the bytes or the file-producing source.

### Wrong charset on CSV

A UTF-8 CSV file may be attached with `Content-Type: text/csv` without a charset. Many clients guess right, but do not rely on that behavior when business rules require multilingual data. Declare the right charset and ensure the bytes actually use that encoding.

If the file is generated by an external system, check encoding at the read/write step. Do not arbitrarily pretend bytes are another encoding by changing headers.

## 15. Resource must remain readable when the message is serialized

**MimeMessageHelper** accepts an **InputStreamSource** or **DataSource** to read attachment content. Depending on the source type, bytes may be read when creating the part or later when Jakarta Mail serializes/sends the message.

Therefore, ensure the resource remains available until the email finishes sending:

- **FileSystemResource** requires the file to exist and the process to have read permission.
- **ByteArrayResource** fits small content already in memory.
- **InputStreamResource** typically represents a stream that can only be opened/read once; be careful if the library needs to re-open the stream.
- Resources fetched from object storage must maintain valid access permissions and not expire before serialization.

Example using `ByteArrayResource` for a small file:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] reportBytes = createSmallReport();
ByteArrayResource resource = new ByteArrayResource(reportBytes);

helper.addAttachment(
        "report.pdf",
        resource,
        "application/pdf"
);
~~~

This example assumes **reportBytes** actually holds a valid PDF. `ByteArrayResource` keeps data in RAM; avoid this approach for large attachments if it significantly increases application heap usage.

### Do not close the stream too early

A common mistake is creating an `InputStream`, closing it right after calling **addAttachment(...)**, and only then calling **send(...)**. If the resource depends on the closed stream, serialization can fail.

With APIs accepting **InputStreamSource**, supply a source capable of opening a fresh stream per its contract. If you only have a single-use stream, read it into an appropriate resource within size limits or design the sending flow to manage the stream lifecycle at the right time.

## 16. Using Spring's ConfigurableMimeFileTypeMap

Besides Jakarta Activation's general implementation, Spring Mail provides **ConfigurableMimeFileTypeMap** for configuring mappings in a Spring application.

Example:

~~~java
import jakarta.activation.FileTypeMap;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.ConfigurableMimeFileTypeMap;

@Configuration
public class MailMimeTypeConfiguration {

    @Bean
    public FileTypeMap mailFileTypeMap() {
        ConfigurableMimeFileTypeMap map =
                new ConfigurableMimeFileTypeMap();

        map.setMappings(
                "text/csv csv",
                "application/x-example-report rptx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document docx"
        );

        return map;
    }
}
~~~

Spring bean management handles the initialization lifecycle of the configuration object. You can pass this bean into the **MimeMessageHelper** constructor accepting **FileTypeMap** as shown earlier.

**ConfigurableMimeFileTypeMap** fits when you want to keep mappings in Spring configuration and add custom entries. Specific mapping/resource options depend on the Spring Framework version; use the API present in your project's actual dependency.

### Should you use MimetypesFileTypeMap or ConfigurableMimeFileTypeMap?

| Option | When suitable |
| --- | --- |
| **MimetypesFileTypeMap** | Want to use Jakarta Activation directly and add mappings via `addMimeTypes(...)` |
| **ConfigurableMimeFileTypeMap** | Want to configure mappings as a Spring bean and integrate with Spring configuration lifecycle |
| **Explicit Content-Type** | Only one part has a well-known type, no need to change shared mappings |

There is no need to create a separate `FileTypeMap` class per attachment if default mappings or explicit content types already meet requirements. Keeping configuration simple avoids the same extension being recognized differently across services.

## 17. Building an attachment-sending flow from validated data

For uploaded files, never let a controller take the filename and Content-Type from the request and pass them directly to **MimeMessageHelper**. A flow with clear responsibilities can look like:

~~~text
File upload / generated file
        |
        v
Validate size and name
        |
        v
Check allowed file types
        |
        v
Inspect bytes / signature / parser
        |
        v
Scan content per policy
        |
        v
ValidatedAttachment
  - resource
  - safe filename
  - trusted content type
        |
        v
MimeMessageHelper.addAttachment(...)
        |
        v
JavaMailSender.send(...)
~~~

**ValidatedAttachment** is an application model concept, not a built-in Spring class. It represents validated data with more trustworthy metadata than raw client input.

Record example:

~~~java
import org.springframework.core.io.Resource;

public record ValidatedAttachment(
        String filename,
        String contentType,
        Resource resource
) {
    public ValidatedAttachment {
        if (filename == null || filename.isBlank()) {
            throw new IllegalArgumentException("Missing filename");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException("Missing contentType");
        }
        if (resource == null) {
            throw new IllegalArgumentException("Missing resource");
        }
    }
}
~~~

The mail-sending service only accepts a validated object:

~~~java
public void sendDocument(
        String recipient,
        ValidatedAttachment attachment
) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED,
            "UTF-8"
    );

    helper.setTo(recipient);
    helper.setSubject("Your document");
    helper.setText("The document is attached.");
    helper.addAttachment(
            attachment.filename(),
            attachment.resource(),
            attachment.contentType()
    );

    mailSender.send(message);
}
~~~

This snippet illustrates the sending layer's responsibility: using the already-determined filename and content type, then building the MIME part. It does not perform upload validation, malware scanning, or byte verification itself; those belong to the attachment-preparation service.

### Why not trust the Content-Type sent by the browser?

A multipart HTTP upload typically includes a client-declared filename and Content-Type. Those values are useful for reference, but the client can send any string. If the server uses the upload header verbatim as the email's Content-Type, a sender could intentionally label an unsafe file as `image/png` or `application/pdf`.

Treat client-sent MIME types as **untrusted metadata**. The server must apply an allowlist, inspect contents, and determine the data type per system policy before sending.

### Limiting total size

When an email has multiple attachments, check:

- Individual file size.
- Total size of all files.
- Overhead from MIME boundaries, headers, and `Content-Transfer-Encoding`.
- SMTP provider message limits.
- Limits accepted by the recipient's mailbox.

Base64 makes the encoded representation of binary data larger than the raw bytes, in addition to headers and multipart boundaries. Therefore, never simply sum file sizes and conclude the email is safely under provider limits.

## 18. Jakarta namespace vs. legacy JavaMail

In modern Spring Framework versions using the Jakarta ecosystem, imports typically look like:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
import jakarta.mail.internet.MimeMessage;
~~~

In older applications based on Java EE/JavaMail prior to the Jakarta transition, packages may start with:

~~~java
import javax.activation.FileTypeMap;
import javax.activation.MimetypesFileTypeMap;
import javax.mail.internet.MimeMessage;
~~~

**javax.activation** and **jakarta.activation** are two distinct namespaces. You cannot pass a `javax` `FileTypeMap` into a constructor expecting `jakarta` just because the class names match. Align your Spring Mail, Jakarta Mail/Activation versions, and imports with your application's dependencies.

If the IDE reports **MimetypesFileTypeMap** or **FileTypeMap** cannot be found, check Activation dependencies and mail library versions before creating a class with a conflicting name.

## 19. Common misconceptions

### Misconception 1: A .pdf extension proves the file is a PDF

No. `FileTypeMap` maps extensions to MIME types. It does not read all bytes to validate PDF structure.

**Solution:** verify the file at ingestion or document creation time, then use the MIME type determined from a trusted source.

### Misconception 2: Content-Type causes bytes to be converted

No. Setting `application/pdf` on a part does not turn CSV data into a PDF.

**Solution:** generate the right file content first; Content-Type only describes the data type.

### Misconception 3: Base64 is a MIME type

No. Base64 is a **Content-Transfer-Encoding**; `application/pdf` or `image/png` is a **Content-Type**.

**Solution:** inspect the right header for each purpose.

### Misconception 4: FileTypeMap not recognizing an extension means the file cannot be sent

No. You can use a generic MIME type or pass an explicit content type if the format is known.

**Solution:** add a mapping or use the explicit content-type overload; never assign a fake MIME type.

### Misconception 5: Files.probeContentType and FileTypeMap always return the same result

No. They use different detectors and mapping sources depending on the runtime.

**Solution:** pick one authoritative source for the sending flow and test it in your deployment environment.

### Misconception 6: Calling addAttachment means the file has already been fully read

Not necessarily. The resource may be read at serialization or sending time.

**Solution:** keep the resource available until `send` completes; be careful with single-read streams.

### Misconception 7: A right filename means the attachment is right

No. Check Content-Type, disposition, and payload as well.

**Solution:** traverse MIME parts and verify decoded bytes if data integrity is required.

### Misconception 8: You can change the JVM-wide default MIME type for one service

Changing the global default can affect other components.

**Solution:** pass a dedicated `FileTypeMap` into `MimeMessageHelper` or configure a clearly scoped bean.

### Misconception 9: A valid MIME type means the file is safe

No. A file can contain malicious content despite a valid extension and header.

**Solution:** apply allowlists, byte checks, parsers, and malware scanning according to risk level.

## 20. Scenario exercises

### Scenario A — Extensionless file

The data source is a valid PDF, but the display filename is **invoice**.

**Question:** Is `FileTypeMap` guaranteed to return `application/pdf`?

**Answer:** no. Without an extension or matching name-based mapping, the map may return `application/octet-stream`. If the application already confirmed this is a PDF, pass explicit content type `application/pdf`.

### Scenario B — File named report.pdf containing CSV bytes

**Question:** Which MIME type does `FileTypeMap` return?

**Answer:** a name-based mapping may return `application/pdf`. That does not confirm the bytes are a PDF. The system must detect the mismatch and reject or handle it per policy.

### Scenario C — Custom extension rptx

The application generates an internal report format with extension `rptx`.

**Question:** How do you make the helper infer the MIME type?

**Answer:** add a mapping for `rptx` in `MimetypesFileTypeMap` or `ConfigurableMimeFileTypeMap` and pass that map to the helper. For a single send call, you can pass an explicit content type.

### Scenario D — CSV with Vietnamese text has garbled accents

The file bytes are UTF-8, yet the part only declares `text/csv` without a charset.

**Question:** Will switching `FileTypeMap` to another instance solve it?

**Answer:** not necessarily. Ensure UTF-8 bytes and declare `charset=UTF-8` in the part's `Content-Type`.

### Scenario E — Attachment has the right MIME type but fails to open

The header is `application/pdf` and the filename is `invoice.pdf`, yet the PDF parser reports a corrupted file.

**Question:** Can you conclude the email client is buggy?

**Answer:** not yet. Check the source file, resource, serialization, and bytes after decoding `Content-Transfer-Encoding`. Valid MIME metadata does not guarantee an intact payload.

### Scenario F — Mapping works in tests but fails on the server

Local returns `image/webp`, while the container returns `application/octet-stream`.

**Question:** Why?

**Answer:** the runtime environments may load different mappings, or the service may be using a different `FileTypeMap`. Configure the map explicitly and inspect the actual instance passed to the helper.

### Scenario G — Inline image renders as an attachment

**Question:** Is fixing `FileTypeMap` to `image/png` enough?

**Answer:** not necessarily. Check `Content-ID`, `Content-Disposition`, the HTML `cid` reference, and the `multipart/related` structure. The MIME type only describes the image byte type.

### Scenario H — An upload claims application/pdf but is actually an executable

**Question:** Should you keep the client-sent header?

**Answer:** no. Client-sent MIME types are untrusted data. The server must check the actual format, allowlist, and security policies before attaching or rejecting the file.

## 21. Workflow for choosing Content-Type for attachments

~~~text
Does the app know the exact data type from a trusted source?
        |
        +-- Yes
        |    |
        |    v
        |  Use the verified MIME type
        |  (can pass explicitly to helper)
        |
        '-- No
             |
             v
       Look up FileTypeMap by filename
             |
             +-- Matching mapping found
             |      |
             |      v
             |   Check extension and content
             |
             '-- No mapping found
                    |
                    v
              application/octet-stream
              or re-determine file type

After choosing MIME type
        |
        v
Verify Content-Type / filename / disposition
        |
        v
Ensure Resource remains readable
        |
        v
Build MimeMessage and send
~~~

A practical checklist for each attachment:

- Identify the **actual format** of the file from a trusted source.
- Choose the right **MIME type**, including charset if it is text data requiring declaration.
- Use default **FileTypeMap**, custom mappings, or explicit Content-Type as appropriate.
- Set a safe, meaningful **filename** for the recipient.
- Confirm **Content-Disposition** is `attachment` or `inline` as intended.
- Keep **Resource/InputStreamSource** available until the message is serialized and sent.
- Verify MIME parts in tests, including Content-Type, filename, and payload when needed.
- For files from untrusted sources, perform validation and scanning per policy before sending.

**Attachment Content-Type** helps receiving software understand the data type; **FileTypeMap** helps Jakarta Activation and Spring Mail infer that type from the filename; **MimeMessageHelper** uses the metadata to build the MIME part. When consistent results are needed, configure a clearly scoped mapping or pass an explicit Content-Type from validated data. Always remember that extension, MIME header, and transfer encoding are three separate concepts, and none of them proves on its own that a file is safe or well-formed.
