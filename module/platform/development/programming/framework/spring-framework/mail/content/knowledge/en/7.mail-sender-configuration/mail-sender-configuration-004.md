# Default FileTypeMap and Content Type Handling

In Spring Framework Mail, sending plain-text-only emails is usually straightforward. However, when a message includes **attachments**, **inline images displayed in HTML**, or data such as PDF, CSV, JSON, or ZIP, the application must tell the mail client what kind of data it is receiving. A key component in that process is **`FileTypeMap`**: a mechanism that maps a filename to a **MIME media type**.

`JavaMailSenderImpl` can carry a **default FileTypeMap** for the `MimeMessage` instances it creates. `MimeMessageHelper` uses this map to infer the `Content-Type` of an attachment or inline resource when the application **has not explicitly specified the content type**. That makes attaching common file types convenient, though filename-based inference has limitations and must not be treated as actual content inspection.

This lesson explains what `FileTypeMap` is, how the default is passed from sender to message, when to rely on the map versus declaring `Content-Type` explicitly, and how to configure and troubleshoot common issues in Spring Mail.

## 1. What does content type mean in email?

MIME (Multipurpose Internet Mail Extensions) allows emails to contain many kinds of data. Each **MIME part** can declare its own headers:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"
```

These three headers serve different purposes:

| Header | Problem solved | Example |
| --- | --- | --- |
| **`Content-Type`** | What kind of data is the content? | `application/pdf`, `image/png`, `text/plain; charset=UTF-8` |
| **`Content-Transfer-Encoding`** | How are the bytes represented for email transport? | `base64`, `quoted-printable` |
| **`Content-Disposition`** | Suggests whether the mail client treats this part as inline or attachment; may include filename | `attachment; filename="invoice.pdf"` |

For example, a PDF file can be sent with `Content-Type: application/pdf`, `Content-Disposition: attachment`, and `Content-Transfer-Encoding: base64`. **`FileTypeMap` only helps resolve the content-type value**; it is not responsible for encoding PDF bytes into base64, nor does it decide whether a file should be an attachment or inline.

### Media type vs. file extension

The filename `invoice.pdf` has the `.pdf` extension, while the corresponding MIME media type is typically `application/pdf`. The two are related, yet they are different concepts:

```text
Filename:            invoice.pdf
Extension:           .pdf
MIME media type:     application/pdf

Filename:            logo.png
Extension:           .png
MIME media type:     image/png
```

**A file extension is a hint, not proof of the bytes inside.** A file that actually contains PNG data but was renamed to `logo.pdf` may be guessed as PDF by `FileTypeMap`. Therefore, any system handling uploaded files must validate content and enforce allowlists at a business-appropriate step independent of `FileTypeMap`.

## 2. What is `FileTypeMap`?

In the modern Spring Framework ecosystem using Jakarta Mail, `FileTypeMap` belongs to the package:

```java
import jakarta.activation.FileTypeMap;
```

It is a Jakarta Activation abstraction for looking up a media type from a **filename** or a `File` object. Representative methods include:

```java
String getContentType(String filename);
String getContentType(File file);
```

An illustrative lookup example:

```text
FileTypeMap
  |
  +-- "report.pdf"   --> "application/pdf"
  +-- "logo.png"     --> "image/png"
  +-- "data.csv"     --> "text/csv"      (if mapped)
  +-- "archive.xyzx" --> "application/octet-stream"
                           (when unrecognized)
```

Exact results depend on the configured mapping table. `application/octet-stream` is the generic binary type commonly used when the format is unknown. **Do not assume a given file extension is always recognized across every library version or runtime environment.**

### Common media types

| Data type | Common media type | Notes |
| --- | --- | --- |
| Plain text | `text/plain` | For text bodies, may include `charset=UTF-8` |
| HTML | `text/html` | HTML body and charset must match |
| PDF | `application/pdf` | Widely used for invoices and reports |
| PNG | `image/png` | Can be an inline image or attachment |
| JPEG | `image/jpeg` | Can be an inline image or attachment |
| GIF | `image/gif` | Depends on mail client rendering support |
| CSV | `text/csv` | Consider charset, delimiter, and spreadsheet tools |
| JSON | `application/json` | Can be sent as a data attachment |
| XML | `application/xml` | XML data |
| ZIP | `application/zip` | Binary compressed archive |
| Word DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Long media type; must map accurately |
| Excel XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Do not use `application/vnd.ms-excel` for XLSX |
| Unknown | `application/octet-stream` | Generic choice when file type is unknown |

This table only lists **the appropriate media type names for file types**; it does not guarantee all mappings exist in every application's default `FileTypeMap`.

### `MimetypesFileTypeMap` and `ConfigurableMimeFileTypeMap`

A common Jakarta Activation implementation is `MimetypesFileTypeMap`:

```java
import jakarta.activation.MimetypesFileTypeMap;

MimetypesFileTypeMap fileTypeMap = new MimetypesFileTypeMap();
String type = fileTypeMap.getContentType("report.pdf");
```

Spring Framework Mail provides `org.springframework.mail.javamail.ConfigurableMimeFileTypeMap`, an implementation whose mapping source can be configured. It is used in Spring Mail's default `FileTypeMap` mechanism. This helps Spring support common content types without forcing every application to declare each extension manually.

Crucially, **mapping is extension-based**: `FileTypeMap` does not open files to inspect magic bytes, PDF structure, ZIP contents, or embedded payloads.

## 3. How does the default FileTypeMap flow from sender to message?

`JavaMailSenderImpl` is the standard `JavaMailSender` implementation in Spring. It can configure both **default encoding** and **default FileTypeMap** used when creating a `MimeMessage`.

Conceptual flow:

```text
JavaMailSenderImpl
  |
  | defaultEncoding
  | defaultFileTypeMap
  v
createMimeMessage()
  |
  | MimeMessage carrying default hints
  v
MimeMessageHelper
  |
  | On addAttachment/addInline:
  |   Explicit contentType provided?
  |      | Yes -> use the specified contentType
  |      | No
  |      v
  |   use FileTypeMap to look up filename/resource
  v
MIME part with Content-Type
  |
  v
Jakarta Mail serializes message to send via SMTP
```

Spring uses a `MimeMessage` variant capable of carrying the sender's default settings so `MimeMessageHelper` can pick up defaults from `JavaMailSenderImpl`. When using standard APIs:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
```

the helper can use the default `FileTypeMap` configured on the sender.

This differs from creating a `MimeMessage` manually via `new MimeMessage(session)` from an arbitrary session: the default hints attached by `JavaMailSenderImpl` may no longer be present. When using Spring Mail, obtain messages through `mailSender.createMimeMessage()`.

### Two completely different default settings

| Setting | Effect | No effect on |
| --- | --- | --- |
| **Default encoding** | Character encoding of relevant text content, e.g., `UTF-8` | Does not identify whether data is PDF or PNG |
| **Default FileTypeMap** | Infers media type from filename for MIME parts needing lookup | Does not convert bytes to UTF-8 or base64-encode them |

For example, with a PDF named `invoice.pdf`:

- Default `FileTypeMap` may resolve `application/pdf`.
- MIME helper/Jakarta Mail handles transfer encoding for the data bytes.
- Charset `UTF-8` on the helper mainly serves text parts and needed header values; **it does not turn PDF bytes into character strings**.

## 4. When does `MimeMessageHelper` use `FileTypeMap`?

`MimeMessageHelper` has convenience methods to attach files or resources to an email. In overloads that **do not accept a media type**, the helper must pick a `Content-Type`, and it can rely on `FileTypeMap`.

Example:

```java
helper.addAttachment("invoice.pdf", new ByteArrayResource(pdfBytes));
```

The helper receives the name `invoice.pdf` and can look up the media type in `FileTypeMap`. If the map has no specific mapping, the result may be a generic type such as `application/octet-stream`.

If the application already knows the data type, it can **specify the content type explicitly**:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

Here the application passes `application/pdf` directly for the attachment's MIME part. This is the right choice when the file is generated by the system and its format is known for certain—for instance, a service that just produced a valid PDF.

### Ways to add attachments

| Attachment method | Explicit media type? | Source of `Content-Type` |
| --- | --- | --- |
| `addAttachment(filename, File)` | No | Usually from filename via `FileTypeMap` |
| `addAttachment(filename, InputStreamSource)` | No | Usually from attachment filename via `FileTypeMap` |
| `addAttachment(filename, InputStreamSource, contentType)` | Yes | `contentType` value passed by application |
| `addAttachment(filename, DataSource)` | Via DataSource | `DataSource.getContentType()` and library mechanism |

Method signatures are abbreviated for readability; exact details depend on the overload used. For resources whose media type is known to the application, the overload taking `contentType` is generally clearer than relying on file extensions.

### Is there a difference between an attachment and an inline resource?

Yes. An **attachment** is typically shown as a downloadable attached file; an **inline resource** is typically referenced from HTML, such as:

```html
<img src="cid:logo" alt="Company logo"/>
```

An inline image is still a MIME part and also needs an appropriate `Content-Type`, such as `image/png`. You can use:

```java
helper.addInline(
        "logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

When using an overload without an explicit content type, inference may rely on the resource name or `contentId` depending on the overload. A `contentId` like `logo` usually **has no extension**, so declaring `image/png` explicitly avoids relying on guesswork.

**A principle worth remembering:** a MIME media type describes the content of a *MIME part*, not "the whole email." An HTML email with an inline image and a PDF contains multiple parts with different media types.

## 5. Determining Content-Type: explicit choice or inference?

If the system generates the content or holds trustworthy metadata, select the content type from that information. `FileTypeMap` is useful as a **fallback** or part of the configuration for application-controlled file types.

A decision guide:

```text
Application needs to add a file to an email
                |
                v
     Media type known for sure?
           /            \
         Yes             No
          |               |
          v               v
  Pass explicit       Identify file source
  contentType         and trust level
          |               |
          |      +--------+--------+
          |      |                 |
          |  System-controlled  User-uploaded
          |  filename           file
          |      |                 |
          |  FileTypeMap       Validate file type
          |  can be useful     against policy
          |      |                 |
          +------+-----------------+
                 |
                 v
     Create MIME part with appropriate type
                 |
                 v
      If format is truly unknown:
      application/octet-stream
```

Never assign `application/pdf` merely because a user renamed a file to `contract.pdf`. Content type does not validate file safety.

### Why is `application/octet-stream` not always an error?

`application/octet-stream` indicates generic binary data. Many mail clients still allow downloading the file with its normal filename. When software does not know the exact data type, this value is **better than falsely claiming a format**.

However, some clients may limit previews, apply stricter filters, or ask the recipient to pick an application to open it. When the system truly generates PDF/PNG/CSV, declaring the exact type usually provides a better experience.

### What role does the filename play?

The filename helps the OS/mail client suggest how to open the file and helps recipients recognize the document. You should:

- Choose a filename whose extension matches the actual format.
- Never blindly trust filenames from uploads or requests.
- Keep the displayed name **free of directory paths** and characters unsuitable for headers.
- Limit length; handle Unicode characters through the MIME library.
- Avoid putting secrets, tokens, or sensitive data into filenames unnecessarily.

The filename and media type should be consistent, while **file safety must still be enforced outside the email-composition step**.

## 6. Spring Boot example: attachment with explicit Content-Type

With Spring Boot, add the mail starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Illustrative `application.yml` configuring SMTP submission with STARTTLS:

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
    sender: ${MAIL_SENDER_ADDRESS}
```

This config only illustrates an SMTP endpoint supporting authentication and STARTTLS on port 587. Credentials must be supplied via environment or secret manager; never put real credentials in source code. `spring.mail.default-encoding` handles **text characters**, which is completely separate from `FileTypeMap` configuration.

Service sending a system-generated PDF:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;
    private final String senderAddress;

    public InvoiceMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.sender}") String senderAddress
    ) {
        this.mailSender = mailSender;
        this.senderAddress = senderAddress;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom(senderAddress);
        helper.setTo(recipient);
        helper.setSubject("Your Invoice");
        helper.setText("Your invoice is attached to this email.", false);

        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
```

In this example:

1. `true` in the helper constructor enables multipart mode required for attachments.
2. `UTF-8` handles text content and related header values.
3. `pdfBytes` is **already-generated** PDF data; the example excludes the PDF generation step.
4. `ByteArrayResource` provides bytes from memory whenever requested by the library.
5. `"application/pdf"` is an explicit media type; no inference from `invoice.pdf` is needed.
6. The helper/Jakarta Mail packages the attachment as MIME, typically using transfer encoding like base64 for binary data.

Do not convert `pdfBytes` into a `String` and pass it to `setText(...)`; PDF is not a UTF-8 text string. When sending large files, consider `FileSystemResource` or a source that can reopen streams multiple times, avoiding holding multiple copies of the data in RAM.

### When you want to use the default FileTypeMap

If the filename is controlled by the application and the map has a matching entry, you can use the overload:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes)
);
```

The helper then relies on `FileTypeMap` to infer `Content-Type`. This is convenient when sending many common files with accurate names. It also makes behavior depend on runtime mappings, so understand the defaults and fallback behavior.

## 7. Configuring FileTypeMap per message

`MimeMessageHelper` exposes `setFileTypeMap(FileTypeMap)`. It lets you swap the file-type mapping **for the current helper**, useful when one sending flow needs mappings different from the default.

Example using `MimetypesFileTypeMap`:

```java
import jakarta.activation.MimetypesFileTypeMap;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");

MimetypesFileTypeMap map = new MimetypesFileTypeMap();
map.addMimeTypes("application/vnd.example.export exportx");
helper.setFileTypeMap(map);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Exported Data");
helper.setText("The data file is attached.");
helper.addAttachment(
        "data.exportx",
        new ByteArrayResource(exportBytes)
);

mailSender.send(message);
```

In this example:

- `exportx` is a **hypothetical** extension for an internal format.
- `application/vnd.example.export` is an **illustrative** media type, not a registered public media type.
- `addMimeTypes(...)` adds a recognition rule to `MimetypesFileTypeMap`.
- `helper.setFileTypeMap(map)` tells the helper to use this map when inferring media types.
- If there is only one specific file type, calling `addAttachment(..., "application/vnd.example.export")` can be simpler than configuring a map.

### Scope of `setFileTypeMap`

A `MimeMessageHelper` is bound to a single `MimeMessage`; a map set on the helper primarily affects parts added through that helper. **Do not treat this as changing a global default** across all `JavaMailSender` instances or future messages.

When many emails share a common mapping rule, configuring it on the sender makes more sense. When sending a single special file, passing the media type directly is usually more readable and has narrower impact.

## 8. Configuring a default FileTypeMap on `JavaMailSenderImpl`

`JavaMailSenderImpl` allows setting `defaultFileTypeMap`. This is the option when an application needs **a shared mapping table** for `MimeMessage` objects created by the same sender.

Relevant method:

```java
import jakarta.activation.FileTypeMap;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
FileTypeMap customMap = /* configured instance */;
sender.setDefaultFileTypeMap(customMap);
```

The snippet above only illustrates the API, not a complete SMTP bean.

### 8.1. Using Spring's `ConfigurableMimeFileTypeMap`

Spring provides `ConfigurableMimeFileTypeMap`, which loads a mapping file in `mime.types` format.

Example application resource at `src/main/resources/mail/mime.types`:

```text
# Custom MIME mappings for application attachments
application/pdf pdf
text/csv csv
application/json json
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet xlsx
application/vnd.example.export exportx
```

This is a MIME-type-and-extension mapping format, **not YAML or Spring properties**. Specific media types/extensions should match the data your application actually produces.

Bean configuring the map:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.ConfigurableMimeFileTypeMap;

@Configuration
public class MailTypeMapConfiguration {

    @Bean
    public ConfigurableMimeFileTypeMap mailFileTypeMap() {
        ConfigurableMimeFileTypeMap map = new ConfigurableMimeFileTypeMap();
        map.setMappingLocation(
                new ClassPathResource("mail/mime.types")
        );
        return map;
    }
}
```

`ConfigurableMimeFileTypeMap` supports Spring's lifecycle initialization. When declared as a bean this way, Spring runs the initialization step needed to load the mappings. If instantiated with `new` outside the container and used directly, ensure it is initialized per the class contract.

**Note:** overriding the mapping location can replace built-in rules. Treat `mail/mime.types` as an application-managed configuration source and include all custom/needed mappings explicitly rather than assuming every default mapping is merged automatically.

### 8.2. Attaching the map to the sender when configuring the bean manually

In **plain Spring Framework**, or when an application **deliberately creates** the `JavaMailSenderImpl` bean itself, you can write:

```java
import jakarta.activation.FileTypeMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

@Configuration
public class ManualMailSenderConfiguration {

    @Bean
    public JavaMailSenderImpl javaMailSender(
            FileTypeMap mailFileTypeMap,
            @Value("${SMTP_HOST}") String host,
            @Value("${SMTP_PORT:587}") int port,
            @Value("${SMTP_USERNAME}") String username,
            @Value("${SMTP_PASSWORD}") String password
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(username);
        sender.setPassword(password);
        sender.setDefaultEncoding(StandardCharsets.UTF_8.name());
        sender.setDefaultFileTypeMap(mailFileTypeMap);

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");
        return sender;
    }
}
```

This snippet demonstrates **one way to configure a sender manually**, assuming a `FileTypeMap` bean and matching SMTP environment variables exist. Port 587/STARTTLS is only one common submission mode; use your actual provider's settings.

In **Spring Boot**, auto-configuration normally creates `JavaMailSender` from `spring.mail.*` when conditions match. Declaring your own `JavaMailSenderImpl` bean may prevent Boot's auto-configuration from **creating the default sender**; settings like `spring.mail.host` and `spring.mail.properties.*` are not automatically copied onto a manually declared bean. Therefore:

- If you only send a few files with specific formats, prefer **the overload accepting an explicit media type**.
- If you want a custom map for certain messages, configure it on **`MimeMessageHelper`**.
- If every email needs a shared mapping and the application already owns sender configuration, you can use **`setDefaultFileTypeMap(...)`**.
- When using Boot auto-config, choose an extension approach that fits your application's structure rather than creating an unintended second sender bean.

### 8.3. Can you just configure a `spring.mail.default-file-type-map` property?

Spring Boot has familiar properties like `spring.mail.host`, `spring.mail.port`, and `spring.mail.default-encoding`. However, **default FileTypeMap** is a Jakarta Activation Java object, not a simple scalar value typically bound via a one-line property like `spring.mail.default-encoding`.

Therefore, for custom mapping requirements, configure a **bean/map or inline content type** using the Spring/Jakarta Mail APIs instead of assuming a standard `spring.mail.default-file-type-map` property exists.

## 9. MIME parts and content types in different positions

A multipart message may have a structure like:

```text
MIME message
Content-Type: multipart/mixed; boundary="outer"
  |
  +-- Part 1:
  |     Content-Type: multipart/alternative; boundary="alt"
  |        |
  |        +-- text/plain; charset=UTF-8
  |        |
  |        +-- text/html; charset=UTF-8
  |
  +-- Part 2:
  |     Content-Type: application/pdf
  |     Content-Disposition: attachment; filename="invoice.pdf"
  |
  +-- Part 3:
        Content-Type: text/csv; charset=UTF-8
        Content-Disposition: attachment; filename="data.csv"
```

Here:

- The outermost `multipart/mixed` header describes **a container** holding multiple parts.
- `multipart/alternative` holds different presentation variants of the same content.
- `text/plain` and `text/html` are text parts requiring an appropriate charset.
- `application/pdf` describes the PDF attachment.
- `text/csv` describes the CSV attachment; the application may need to handle charset and specific CSV conventions.

**Do not change the entire message's `Content-Type` to `application/pdf` just because the email attaches a PDF.** `FileTypeMap` is used when creating **the attachment part**, not to set the media type of the top-level multipart container.

### When adding CSV

If the system generates UTF-8 CSV, the media type can include a charset parameter:

```java
helper.addAttachment(
        "report.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
```

This is helpful when the application knows for certain that `csvBytes` was encoded as UTF-8. However, **`text/csv` and `charset=UTF-8` do not solve CSV dialect issues** (delimiters, quoting, BOM, or how spreadsheet apps import files). Those must be handled when generating the CSV.

## 10. HTML email and inline images: choosing the right Content-Type

Example welcome email with HTML and a logo:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;

public void sendWelcomeWithLogo(
        JavaMailSender mailSender,
        String recipient
) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            StandardCharsets.UTF_8.name()
    );

    helper.setFrom("notifications@example.org");
    helper.setTo(recipient);
    helper.setSubject("Welcome!");
    helper.setText(
            "<p>Welcome to the platform.</p>"
                    + "<img src=\"cid:logo\" alt=\"Logo\"/>",
            true
    );

    helper.addInline(
            "logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
    );

    mailSender.send(message);
}
```

Explanation:

- `helper.setText(..., true)` creates **`text/html`** content rather than `text/plain`.
- `cid:logo` references an inline MIME part whose Content-ID is `logo`.
- `addInline("logo", ..., "image/png")` declares the media type for the image. Because `logo` has no extension, **explicit declaration** avoids relying on filename guesswork.
- `MULTIPART_MODE_RELATED` fits the relationship between HTML and inline resources here; if you also need attachments or text/HTML alternatives, the MIME structure can be more complex.
- HTML is set **before** adding inline resources, matching how many mail clients process CID references.

**Not all mail clients display inline images the same way.** `image/png` describes the content properly, but does not force a client to load images or render them identically.

## 11. Controlling filenames and data sources yourself

When an application handles user-uploaded files, three pieces of metadata must be managed **separately**:

| Information | Possible source | Completely trustworthy? |
| --- | --- | --- |
| **Original filename** | Name sent by browser/client | No |
| **Client-reported content type** | HTTP `Content-Type` of upload request | No |
| **File bytes** | Actual uploaded file contents | Must be validated against policy and supported formats |

Never pick an email `Content-Type` by blindly trusting a user-controlled extension or upload header.

A common business workflow:

1. Verify user upload permissions and file size limits.
2. Allow only formats the application genuinely supports.
3. Determine the format using proper inspection (e.g., magic bytes/format parser where needed) instead of reading only the extension.
4. Assign a **safe filename** for the email, free of paths and unsafe control characters.
5. Choose the media type based on the verified format.
6. Attach the raw bytes via `ByteArrayResource`, `FileSystemResource`, or an appropriate `InputStreamSource`.

`FileTypeMap` can participate in **the step mapping an already-trusted filename** to a media type; it does not replace security and content validation steps.

### Why must `InputStreamSource` provide re-readable data?

`MimeMessageHelper.addAttachment(...)` may need to reopen the input stream while JavaMail prepares/serializes the message. Therefore, the input resource should be able to provide a **fresh stream on each read**. `ByteArrayResource` and `FileSystemResource` are usually suitable; an `InputStreamResource` wrapping a single-use stream can fail in some flows.

When sending large files, consider memory limits, post-base64 email size, and SMTP server quotas. Picking the right `FileTypeMap` **does not shrink file size or bypass SMTP limits**.

## 12. When Content-Type is wrong, what happens in mail clients?

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| PDF arrives with right name but appears as generic binary data | Mapping did not recognize `.pdf` or filename lacked extension | `FileTypeMap`/`addAttachment` overload and part headers |
| Mail client does not preview inline image | Inline part tagged `application/octet-stream` or wrong CID/MIME structure | `Content-Type`, `Content-ID`, and `multipart/related` structure |
| HTML shows raw tags | Body declared as `text/plain` instead of `text/html` | `helper.setText(..., true)` |
| PDF reported corrupted when opened | Source bytes were wrong, converted to String, or transfer encoding broke | Input bytes, MIME part, and receiving flow |
| `.csv` file treated as a binary attachment | `FileTypeMap` lacks a CSV mapping | Explicit `text/csv` media type or custom map |
| Filenames with diacritics display inconsistently | Filename parameter encoding rules or client support | `Content-Disposition`, MIME library, and mail client |
| Email exceeds size limit even though original file seemed small | Base64 and MIME overhead increase size | SMTP/provider limits; consider download links |
| Email with attachment has empty/missing body | MIME multipart constructed incorrectly | How `MimeMessageHelper` was created and part ordering |
| One environment recognizes `.exportx` while another returns octet-stream | Different maps loaded across environments | Default map configuration / custom `mime.types` |
| Attachment rejected by receiving system | Provider/recipient blocks file type or anti-abuse policy | SMTP/provider rules; file type; response logs |

**Important distinction:** the wrong file type does not necessarily corrupt the file's bytes. A mail client may still let the user download and open it with the right program. Conversely, declaring `application/pdf` correctly cannot fix a PDF whose bytes are already corrupted.

### How to read raw MIME when suspecting a wrong content type

Example message with attachment:

```eml
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-123"

--mixed-123
Content-Type: text/plain; charset=UTF-8

Invoice attached.

--mixed-123
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKLi4u

--mixed-123--
```

This is a structural illustration; the base64 string is a short placeholder and does not contain a full PDF.

Reading the outermost `multipart/mixed` header and thinking "the email isn't PDF so the type is missing" is a misunderstanding: **the PDF lives inside a child part**. Check `Content-Type` on the specific part that carries `Content-Disposition: attachment`.

Inspection order:

1. Identify the top-level `Content-Type` and `boundary` if multipart.
2. Locate the exact MIME part containing the problematic file or image.
3. Check the part's `Content-Type`, `Content-Disposition`, and `Content-ID` (if inline).
4. Separate content-type errors from transfer-encoding or source-byte errors.
5. Compare the file's true format with the media type declared by the application.

Inspecting raw MIME distinguishes `FileTypeMap` configuration issues from source-file corruption and client-specific rendering quirks.

## 13. Common mistakes

### Mistake 1: "Just changing the outermost email's `Content-Type` is enough"

An application builds a multipart message for text and PDF, then calls:

```java
message.setHeader("Content-Type", "application/pdf");
```

This call can make **the outermost container** header conflict with the multipart structure. Never manually overwrite MIME headers to "fix" attachment types. Use the `addAttachment(..., "application/pdf")` overload or `FileTypeMap` on the right helper.

### Mistake 2: "`FileTypeMap` reads bytes and knows the actual content"

A file named `photo.jpg` can contain something else entirely. `FileTypeMap` only guesses from the name; it is not a file-signature scanner, malware detector, or upload content validator.

### Mistake 3: "Setting `defaultEncoding=UTF-8` makes PDFs get detected as the right type"

Encoding applies to **text**. A PDF still needs `Content-Type: application/pdf`, either inferred via `FileTypeMap` or passed explicitly.

### Mistake 4: "Base64 is a MIME type"

`base64` is a **`Content-Transfer-Encoding`** value. It is not a `Content-Type`. A PDF can have `Content-Type: application/pdf` and `Content-Transfer-Encoding: base64` at the same time.

### Mistake 5: "Renaming the extension converts the format"

Renaming `report.txt` to `report.pdf` does not turn text into a PDF. The inferred media type may change, while the underlying bytes remain text. Converting formats requires software that generates a new file in the target format.

### Mistake 6: "Having a default FileTypeMap on the sender means every helper uses that exact map"

The default map is passed along when creating messages via the right code paths. If the application creates messages manually, overrides `helper.setFileTypeMap(...)`, or passes an explicit `contentType`, the effective source can differ. Know **how the message is created and which overload is used**.

### Mistake 7: "Adding a mapping to a Spring Boot property is all it takes"

`FileTypeMap` is a Jakarta Activation object. For custom mappings, use `ConfigurableMimeFileTypeMap`, `MimeMessageHelper.setFileTypeMap(...)`, or `JavaMailSenderImpl.setDefaultFileTypeMap(...)` according to the required scope. Do not guess non-existent application properties.

## 14. Practical scenarios

### Scenario A: system sends XLSX, but mail clients do not recognize it properly

The application generates valid XLSX bytes and calls:

```java
helper.addAttachment("report.xlsx", new ByteArrayResource(xlsxBytes));
```

One environment assigns the right media type while another assigns octet-stream.

**Explanation:** the two environments may have different mappings. Since the application knows for sure it is XLSX, it can use:

```java
helper.addAttachment(
        "report.xlsx",
        new ByteArrayResource(xlsxBytes),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
);
```

If many XLSX files share the same convention, adding the mapping to a shared `FileTypeMap` is also an option.

### Scenario B: inline image gets sent as `application/octet-stream`

The application uses content ID `logo` and an overload that does not specify a content type.

**Explanation:** `logo` has no extension for the map to guess from. Use `addInline("logo", resource, "image/png")` when you know the file is PNG. Also ensure the HTML contains `cid:logo` and the MIME part is created in the proper structure.

### Scenario C: attached PDF has the "right type" yet the file is broken

The application calls `addAttachment("invoice.pdf", resource, "application/pdf")`, but recipients cannot open it.

**Explanation:** the media type header is declared, yet `resource` bytes may be invalid or the stream was not re-read completely. Check the byte source and stream re-readability; changing `FileTypeMap` cannot fix PDF bytes.

### Scenario D: sending an internal `.exportx` format

Multiple sending flows produce this file type and need a consistent media type across the application.

**Explanation:** you can define the mapping in `mime.types`, use `ConfigurableMimeFileTypeMap`, and set the map on the sender if you manage the sender configuration directly. If only one special email sends it, passing the media type explicitly to `addAttachment` is simpler.

### Scenario E: Spring Boot app loses SMTP settings after adding a custom sender bean

A team creates a `@Bean JavaMailSenderImpl` just to call `setDefaultFileTypeMap(...)`, forgetting to set host, credentials, and TLS.

**Explanation:** a manually declared bean can suppress auto-configuration. When owning the sender bean, you must configure all SMTP settings; if you only need to adjust one attachment, avoid replacing the sender and pass the content type directly via the overload.

## 15. Best practices for Spring Mail

| Need | Suitable approach | Reason |
| --- | --- | --- |
| Send a system-generated PDF | `addAttachment(..., "application/pdf")` | Data type is known, minimal environment dependency |
| Send an inline PNG | `addInline(..., "image/png")` | Content ID may lack an extension |
| Send many common files with accurate names | Use default `FileTypeMap` | Convenient, avoids repeating media types |
| Add a custom extension for one sending flow | `helper.setFileTypeMap(...)` or explicit content type | Narrow change scope |
| Standardize mappings across a self-configured sender | `JavaMailSenderImpl.setDefaultFileTypeMap(...)` | Shared default across related messages |
| Load mappings from application resources | `ConfigurableMimeFileTypeMap` + `mime.types` | Separates mapping table from business code |
| Attach user-uploaded files | Inspect actual format and pick type after validation | Extensions and upload MIME types can be spoofed |
| Format unknown | `application/octet-stream` | Avoids claiming an inaccurate content type |
| Support Vietnamese text in body | Appropriate `charset=UTF-8` / default encoding | Handles text characters, separate from `FileTypeMap` |

**Default `FileTypeMap` is a filename-based media-type inference mechanism** used by the sender and MIME helper when needed. It makes attaching files more convenient, but does not verify data bytes, guarantee safety, perform transfer encoding, or replace application content policies. When the exact format is known, **specify `Content-Type` explicitly**; when shared rules for multiple extensions are needed, configure the map at the appropriate scope on `MimeMessageHelper` or `JavaMailSenderImpl`.
