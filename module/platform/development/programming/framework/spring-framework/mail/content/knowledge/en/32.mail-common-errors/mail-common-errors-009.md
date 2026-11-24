# Using `ByteArrayResource` While Setting the Attachment Filename Incorrectly

## 1. A Common Problem in Spring Framework Mail

In **Spring Framework Mail**, a very common scenario is generating file contents in memory—such as a PDF invoice, Excel report, CSV export, or a template-generated document—and attaching those bytes to an email using `ByteArrayResource`.

The code often starts like this:

~~~java
byte[] pdfBytes = invoicePdfGenerator.generate(invoice);
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setTo(customerEmail);
helper.setSubject("Invoice");
helper.setText("Invoice is attached.", false);

helper.addAttachment(resource.getFilename(), resource);
mailSender.send(message);
~~~

At a glance, `resource.getFilename()` looks reasonable. However, **`ByteArrayResource` carries no default filename**, so `getFilename()` normally returns `null`. Passing that value into the `attachmentFilename` argument of `MimeMessageHelper.addAttachment(...)` can fail parameter validation right at the email-building stage.

Even when replaced with an extensionless name like `"report"`, the email may send while the mail client displays a confusing attachment name, misidentifies the content type, or fails to show the name users expect.

**Root of the mistake:** raw file bytes, the `Resource` object, and **the filename on the MIME attachment** are three distinct things. When using `ByteArrayResource`, pass an **explicit, valid attachment filename** to `MimeMessageHelper.addAttachment(...)` instead of assuming `ByteArrayResource` knows that name.

## 2. Quick and Proper Fix

For in-memory generated PDF content:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.com");
helper.setSubject("November invoice");
helper.setText("Please see the invoice in the attached file.", false);

byte[] pdfBytes = invoicePdfGenerator.generate(invoice);
ByteArrayResource resource = new ByteArrayResource(pdfBytes);

// Attachment name comes from business context, not getFilename().
helper.addAttachment(
        "november-invoice.pdf",
        resource,
        "application/pdf");

mailSender.send(message);
~~~

`invoicePdfGenerator` and `invoice` are illustrative business components. Email addresses and filenames here are dummy data.

Key points:

- The **first** argument is the filename the recipient will see, e.g. `november-invoice.pdf`.
- The **second** argument is the content source; `ByteArrayResource` supplies a stream reading from the byte array.
- The **third** argument is the MIME content type; `application/pdf` for PDF, `text/csv` for CSV.
- `MimeMessageHelper(message, true, "UTF-8")` enables multipart so attachments can be added and sets the charset for text parts.
- `setText(...)` configures the email body; `addAttachment(...)` configures the separate MIME attachment part.
- The PDF payload must **actually contain valid PDF bytes**; renaming or setting a content type does not turn arbitrary bytes into a PDF.

In most cases, **simply fixing how the filename is passed** solves the core issue:

~~~java
// Wrong: ByteArrayResource#getFilename() returns null.
helper.addAttachment(resource.getFilename(), resource);

// Right: provide an explicit filename.
helper.addAttachment("invoice-2026-11.pdf", resource);

// Even clearer when you want explicit MIME content type control.
helper.addAttachment(
        "invoice-2026-11.pdf",
        resource,
        "application/pdf");
~~~

There is no need to subclass `ByteArrayResource` or write temp files to disk just to give an attachment a name.

## 3. What Is `ByteArrayResource` Really?

`ByteArrayResource` lives in `org.springframework.core.io`. It wraps a `byte[]` inside a `Resource` abstraction, typically used when bytes are already in RAM.

Example:

~~~java
byte[] bytes = new byte[] {1, 2, 3, 4};

ByteArrayResource resource =
        new ByteArrayResource(bytes);

long size = resource.contentLength();     // 4
String description = resource.getDescription();
String filename = resource.getFilename(); // null by default
~~~

Useful capabilities:

- `getInputStream()` returns a fresh `ByteArrayInputStream` to read the data.
- The byte source can be read repeatedly (unlike single-use stream wrappers).
- `contentLength()` is derived from the byte array length.
- `getDescription()` is descriptive Resource metadata, **not an email attachment filename**.
- `getFilename()` is not derived by `ByteArrayResource` from its description or bytes.

This explains why:

~~~java
new ByteArrayResource(pdfBytes)
~~~

is not equivalent to:

~~~text
A PDF file on disk with a filesystem filename.
~~~

An in-memory buffer has no filesystem path or physical filename for Spring to infer.

### Difference Between `Resource` and a MIME Attachment

`Resource` is an abstraction for **reading data**. Meanwhile, a MIME attachment needs at least a **payload** plus metadata such as `Content-Disposition`, `filename`, and `Content-Type`. `MimeMessageHelper` combines these when building the MIME part.

~~~text
byte[] PDF data
    |
    v
ByteArrayResource
    |
    | supplies bytes
    v
MimeMessageHelper.addAttachment(
    attachmentFilename,
    inputStreamSource,
    contentType
)
    |
    v
MIME body part with headers + bytes
    |
    v
Mail client renders attachment
~~~

## 4. Two `ByteArrayResource` Constructors That Cause Confusion

Spring provides `ByteArrayResource(byte[])` and `ByteArrayResource(byte[], String description)`.

Many developers write:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(
                pdfBytes,
                "invoice-november.pdf");

helper.addAttachment(resource.getFilename(), resource);
~~~

expecting the two-argument constructor to set the filename. **Incorrect.** The second parameter is `description`; it describes the `Resource` in diagnostic messages and does not populate `getFilename()`.

Illustrative example:

~~~java
ByteArrayResource resource = new ByteArrayResource(
        "hello".getBytes(java.nio.charset.StandardCharsets.UTF_8),
        "my-report.txt");

System.out.println(resource.getDescription());
System.out.println(resource.getFilename());
~~~

`getDescription()` contains a descriptive string mentioning `my-report.txt`, while `getFilename()` remains `null`. So you still must write:

~~~java
helper.addAttachment("my-report.txt", resource);
~~~

**Rule:** `description` is `Resource` metadata; `attachmentFilename` is MIME part metadata. Never swap the two concepts.

## 5. What Parameters Does `MimeMessageHelper.addAttachment` Accept?

Commonly used overloads on `MimeMessageHelper` include:

~~~java
addAttachment(String attachmentFilename,
              InputStreamSource inputStreamSource)

addAttachment(String attachmentFilename,
              InputStreamSource inputStreamSource,
              String contentType)
~~~

In this context:

| Parameter | Role | Illustrative Value |
|---|---|---|
| `attachmentFilename` | Attachment name in the email | `receipt-583.pdf` |
| `inputStreamSource` | Supplies streams to read bytes | `new ByteArrayResource(pdfBytes)` |
| `contentType` | MIME media type of the attachment | `application/pdf` |

When using the overload without `contentType`, the helper may infer the media type from the attachment filename via its `FileTypeMap`. Hence an **accurate file extension** helps both recipients identify the file and the system detect the content type.

If the application must support custom formats or avoid relying on filename-based detection, pass content type explicitly:

~~~java
helper.addAttachment("export.csv", resource, "text/csv");
helper.addAttachment("report.pdf", resource, "application/pdf");
helper.addAttachment(
        "archive.zip", resource, "application/zip");
~~~

Content type is only a MIME declaration. **It does not repair corrupt data, prove a file is safe, or append an extension to the filename.**

### Passing `null` or Blank Names

Never pass:

~~~java
helper.addAttachment(null, resource);
helper.addAttachment("", resource);
~~~

Null/blank names have no valid attachment semantics. The helper checks for non-null names; for empty or whitespace-only names, the application must proactively validate. Do not wait for mail clients to display a weird name before handling it.

## 6. Filename Is Not MIME Content Type

When receiving an email, mail clients inspect several headers:

~~~text
Content-Type: application/pdf; name="receipt-583.pdf"
Content-Disposition: attachment; filename="receipt-583.pdf"
Content-Transfer-Encoding: base64
~~~

This is an **illustrative MIME snippet**; exact header formatting and encoding vary by Jakarta Mail, charset, and mail client.

Three aspects:

1. **Filename:** suggested name when the recipient downloads the file.
2. **Content-Type:** declared media type from the application.
3. **Payload:** actual bytes transmitted in the MIME body part.

Examples:

| Filename | Content-Type | Payload | Outcome |
|---|---|---|---|
| `report.pdf` | `application/pdf` | Valid PDF bytes | Proper |
| `report` | `application/pdf` | Valid PDF bytes | May lack extension when saved |
| `report.pdf` | `application/octet-stream` | Valid PDF bytes | Some clients still open it, weaker metadata |
| `report.pdf` | `application/pdf` | CSV bytes | **Wrong content** even though metadata looks right |
| `report.csv` | `text/csv` | UTF-8 CSV bytes | Proper; consider charset/BOM per client |
| `report.xlsx` | Standard XLSX MIME | Valid XLSX bytes | Proper |

Thus fixing filename **differs from fixing content type**; one mistake can accompany the other.

## 7. Why Errors Can Occur Before Calling `send`

This snippet:

~~~java
helper.addAttachment(resource.getFilename(), resource);
mailSender.send(message);
~~~

can fail right at `addAttachment(...)` when filename is null. That is not an SMTP error and **does not mean the provider received a submission**.

Error stages:

| Stage | Symptom | What to Check |
|---|---|---|
| Resource creation | `pdfBytes` null/empty | PDF generator and input |
| Filename selection | `resource.getFilename() == null` | Build an explicit filename |
| `addAttachment(...)` | Argument validation / MIME construction | Filename, content type, multipart mode |
| MIME rendering | Unexpected filename header, encoding, or MIME type | Inspect MIME part before sending |
| `mailSender.send(...)` | Auth/TLS/SMTP rejection/timeout | Transport and provider, separate from filename |
| Client opening email | Different name displayed or attachment blocked | MIME headers, client policy, malware/security |

Never treat an `IllegalArgumentException` during MIME assembly as a transient SMTP error and retry with exponential backoff. A filename bug repeats until code or data is fixed.

## 8. Wrong Code Variants and Fixes

### 8.1. Getting the Name from `ByteArrayResource.getFilename()`

~~~java
ByteArrayResource bytes = new ByteArrayResource(pdfBytes);
helper.addAttachment(bytes.getFilename(), bytes); // Wrong.
~~~

Fix:

~~~java
helper.addAttachment("invoice.pdf", bytes, "application/pdf");
~~~

### 8.2. Mistaking `description` for `filename`

~~~java
ByteArrayResource bytes =
        new ByteArrayResource(pdfBytes, "invoice.pdf");
helper.addAttachment(bytes.getFilename(), bytes); // Still wrong.
~~~

Fix:

~~~java
helper.addAttachment("invoice.pdf", bytes, "application/pdf");
~~~

### 8.3. Using an Extensionless Filename

~~~java
helper.addAttachment("invoice-583", bytes);
~~~

This creates an attachment whose file type is hard to recognize; type detection may also fail expectations. Fix:

~~~java
helper.addAttachment(
        "invoice-583.pdf", bytes, "application/pdf");
~~~

### 8.4. Using the Wrong Extension

~~~java
helper.addAttachment(
        "invoice-583.txt", pdfBytesResource, "application/pdf");
~~~

The MIME type says PDF while the filename says TXT. The name must match **the actual byte format**; never tack on a different extension just to bypass a validation check.

### 8.5. Passing an Absolute Path as the Name

~~~java
helper.addAttachment(
        "C:\\company\\internal\\customer-583.pdf",
        resource);
~~~

Recipients may see an internal path or a confusing name depending on the client. Pass only a safe basename:

~~~java
helper.addAttachment(
        "customer-583.pdf", resource, "application/pdf");
~~~

### 8.6. Using `addInline` for a Downloadable File

~~~java
helper.addInline("report.pdf", resource, "application/pdf");
~~~

`addInline(...)` has **Content-ID inline embedding** semantics, not normal downloadable attachment semantics. For documents recipients should download, use `addAttachment(...)`.

## 9. Complete Example: Sending a PDF Invoice from `byte[]`

Suppose a use case generates PDF bytes through a business component:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;
    private final InvoicePdfGenerator pdfGenerator;

    public InvoiceMailService(
            JavaMailSender mailSender,
            InvoicePdfGenerator pdfGenerator) {
        this.mailSender = mailSender;
        this.pdfGenerator = pdfGenerator;
    }

    public void sendInvoice(Invoice invoice)
            throws MessagingException {

        byte[] pdfBytes = pdfGenerator.generate(invoice);
        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalStateException(
                    "Generated invoice PDF is empty");
        }

        String filename =
                "invoice-" + invoice.safeReference() + ".pdf";

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(invoice.recipientEmail());
        helper.setSubject(
                "Invoice " + invoice.safeReference());
        helper.setText(
                "Hello, please see the attached invoice.",
                false);

        helper.addAttachment(
                filename,
                new ByteArrayResource(pdfBytes),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

`Invoice` and `InvoicePdfGenerator` are illustrative application components. `invoice.safeReference()` is assumed to return a **validated business reference** (e.g., alphanumeric and hyphens), never raw user input.

### Why Declare Multipart Mode Explicitly?

`MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED` supports body content plus attachment and inline parts. Using `new MimeMessageHelper(message, true, "UTF-8")` is also common for enabling multipart, yet the explicit mode constant tells readers the code constructs a multi-part MIME tree.

The order `setText(...)` then `addAttachment(...)` keeps the example clear. For inline content (CID images), ordering also affects compatibility with certain mail clients, explained later.

### Transaction and Exception Notes

`sendInvoice(...)` should not be called inside the invoice-writing transaction if consistency between business state and email is required. SMTP submission does not roll back with the database. When reliability is required, write mail intent to a **transactional outbox**, then let a worker build MIME and submit.

`MessagingException` can occur during MIME preparation; SMTP errors are usually wrapped by Spring Mail in corresponding `MailException` subclasses. Classify errors by stage so misnamed files are not retried as transport outages.

## 10. In-Memory CSV Example

Dynamic CSV exports commonly run into filename mistakes:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;

String csv = "id,amount\r\n"
        + "INV-1001,250000\r\n"
        + "INV-1002,180000\r\n";

byte[] csvBytes = csv.getBytes(StandardCharsets.UTF_8);
ByteArrayResource csvResource =
        new ByteArrayResource(csvBytes);

helper.addAttachment(
        "invoice-export-2026-11.csv",
        csvResource,
        "text/csv; charset=UTF-8");
~~~

Here the filename comes from the report context rather than `csvResource.getDescription()` or `getFilename()`.

### CSV Opened in Excel Garbles Vietnamese Diacritics?

That is usually a **CSV content encoding / spreadsheet app** issue, not an attachment filename error. Factors to check:

- Were content bytes encoded in UTF-8 or the expected charset?
- Does the file use `,`, `;`, or tabs as expected by the user's locale?
- Does Excel in the target environment expect a UTF-8 BOM?
- Are fields with commas, quotes, or newlines properly CSV-quoted?
- Did the download tool preserve attachment bytes intact?

Changing filename from `report` to `report.csv` improves file recognition yet **never fixes encoding bugs inside the bytes**.

### CSV Formula Injection

When CSV contains user-supplied data, cells starting with `=`, `+`, `-`, or `@` can be interpreted as formulas by spreadsheet software. Design proper escaping/encoding when exporting CSVs for spreadsheets. That is content protection, separate from attachment naming.

## 11. Excel XLSX Example and Proper MIME Type

A modern Excel attachment:

~~~java
byte[] xlsxBytes = exportService.generateXlsx(report);

helper.addAttachment(
        "sales-2026-11.xlsx",
        new ByteArrayResource(xlsxBytes),
        "application/vnd.openxmlformats-officedocument."
                + "spreadsheetml.sheet");
~~~

In Java code, the content type string is split across two literals for readability; the actual MIME value is one continuous string.

Avoid naming `.xlsx` bytes as `report.xls`: XLS and XLSX are different formats. Changing an extension does not convert formats.

### If the File Already Exists on Disk

If a producer already wrote the file to the filesystem, there is no need to load everything into `byte[]`:

~~~java
import org.springframework.core.io.FileSystemResource;
import java.io.File;

FileSystemResource file =
        new FileSystemResource(new File(
                "/srv/reports/monthly-sales.xlsx"));

helper.addAttachment(
        "monthly-sales.xlsx",
        file,
        "application/vnd.openxmlformats-officedocument."
                + "spreadsheetml.sheet");
~~~

`FileSystemResource` can extract a filename from the path, yet you should still pass an **application-chosen display name**. The internal name `/srv/reports/monthly-sales.xlsx` need not be exposed to recipients.

The path above is illustrative; in production ensure files are system-generated and never build paths from unvalidated user input.

## 12. Comparing `Resource` Types for Email Attachments

| Type | Data Source | `getFilename()` | Repeatable Stream? | When Appropriate |
|---|---|---|---|---|
| `ByteArrayResource` | `byte[]` in RAM | Usually `null` | Yes, new stream over `byte[]` | Moderate-sized PDF/CSV/XLSX generated in memory |
| `FileSystemResource` | File on filesystem | Usually basename | Can open fresh streams | Large files or files already on disk |
| `ClassPathResource` | Resource on classpath | Usually resource name | Generally repeatable depending on source | Static files like guides or sample docs |
| `InputStreamResource` | An already-open `InputStream` | No reliable filename | Usually single-use | Usually **unsuitable** for MIME attachments needing re-reads |
| Custom `InputStreamSource` | Stream provider | No `getFilename()` on interface | Depends on implementation | Large storage objects needing fresh streams each call |

### Why Does `InputStreamResource` Cause Other Failures?

`MimeMessageHelper.addAttachment(...)` requires a stream source that can be opened when MIME is serialized. `InputStreamResource` typically wraps an **already-opened stream**, reports `isOpen() == true`, and does not guarantee opening a fresh stream. The helper may reject it or fail on re-read.

Pattern to avoid:

~~~java
InputStream input = storage.openStream(key);
InputStreamResource resource =
        new InputStreamResource(input);

helper.addAttachment("export.pdf", resource);
~~~

For small payloads, use `ByteArrayResource`. For large files, use `FileSystemResource` or an `InputStreamSource` designed so **every `getInputStream()` opens a fresh stream**, with data retention lasting until sending finishes.

### Does `InputStreamSource` Have a Filename?

`InputStreamSource` describes only how to supply an `InputStream`. It promises no path or filename. The MIME name remains the `attachmentFilename` parameter on the helper, regardless of whether bytes come from memory, filesystem, or object storage.

## 13. Why Passing the Filename in `addAttachment` Beats Subclassing `Resource`

You could write a subclass of `ByteArrayResource` overriding `getFilename()`:

~~~java
public final class NamedByteArrayResource
        extends ByteArrayResource {
    private final String filename;

    public NamedByteArrayResource(
            byte[] bytes, String filename) {
        super(bytes);
        this.filename = filename;
    }

    @Override
    public String getFilename() {
        return filename;
    }
}
~~~

This illustrative class is conceptually valid if another application API genuinely requires a named `Resource`. However, for `MimeMessageHelper.addAttachment(...)`:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes));
~~~

is sufficient and usually clearer. Adding a subclass can mislead readers into thinking the helper uses `getFilename()` automatically from the resource, whereas the helper API **requires an explicit filename**.

A subclass helps only when you truly need the filename property to travel alongside the `Resource` across multiple layers. Even then, validate the filename and never assume every consumer reads `getFilename()`.

## 14. Where Should the Attachment Filename Come From?

A good name usually follows a pattern:

~~~text
<document-type>-<safe-reference>-<date>.<extension>
~~~

Examples:

- `invoice-INV-583-2026-11.pdf`
- `sales-report-2026-11.xlsx`
- `support-attachments-2026-11.zip`
- `statement-2026-Q4.csv`

Preferred data sources:

1. Server-determined **document type**.
2. Validated **business reference** that avoids leaking unnecessary info.
3. Locale-independent **date/reporting period**.
4. **Extension** matching the actual generated byte format.

Avoid using directly:

- Recipient's email address in the filename.
- Full names or sensitive ID numbers.
- Server temporary paths.
- Raw email subject strings.
- Unvalidated user-uploaded filenames.
- Names containing `../` or control characters.

### Filenames Are Externally Visible Data

Even when attachments are encrypted in transit over TLS, recipients still see the filename and can forward or save it. Never stuff sensitive details into the filename just because it is outside the body.

## 15. Using the Right Extension to Support Content-Type Detection

The `addAttachment` overload without content type infers it from the filename:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes));
~~~

In standard setups, `.pdf` maps to `application/pdf`. Yet exact MIME mappings depend on framework versions and `FileTypeMap` configuration.

When deterministic behavior is needed, pass the type explicitly:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Never set `filename="invoice.pdf"` with `contentType="text/plain"` when the bytes are a PDF. Such inconsistency causes receiving software to behave unpredictably.

### Extensions Do Not Determine Security Either

A file named `invoice.pdf` can hold invalid or malicious bytes. Receiving mail systems scan/quarantine attachments based on actual bytes, file type, domain reputation, and security policies. Never rely on a filename to claim a file is safe.

## 16. Unicode Filenames, Vietnamese Diacritics, and Compatibility

Examples of Vietnamese filenames:

~~~text
Hóa đơn tháng 11.pdf
Báo cáo doanh thu quý IV.xlsx
Tổng hợp yêu cầu.csv
~~~

MIME headers define encoding rules for non-ASCII filenames, and mail clients vary in how well they support them. Jakarta Mail/Spring Mail handle encoding filename headers; applications should never manually concatenate Vietnamese diacritics straight into raw MIME headers without understanding encoding rules.

For broad compatibility across email clients, consider using **safe ASCII** names:

~~~text
hoa-don-thang-11.pdf
bao-cao-doanh-thu-q4.xlsx
~~~

This is a compatibility option, not a mandatory ban on Unicode.

### What to Check When Unicode Filenames Garble

- Is the message/body charset configured, e.g. `UTF-8`?
- How is the Jakarta Mail implementation encoding filename parameters?
- Does any code overwrite `Content-Disposition` or `Content-Type` headers after the helper builds the part?
- Does a proxy/gateway rewrite MIME headers?
- Which parameter does the mail client read to display the filename?
- Did the attachment name come from a data source using a different encoding?

Spring's `MimeMessageHelper` offers settings related to filename encoding, such as `setEncodeFilenames(boolean)`, depending on Spring version. Still, toggling one option cannot replace testing MIME compatibility between Jakarta Mail and target clients. Mechanisms like MIME encoded-words and RFC 2231 parameters have uneven support histories; test against your actual framework, version, and provider.

## 17. Sanitizing Dynamic Filenames Before Putting Them in MIME

When an attachment name is built from business data, strip or reject OS-incompatible characters and header control characters.

A **simple policy** for filenames can require:

- Basename only—no absolute paths or directories.
- No `CR`/`LF` newlines, NUL bytes, or control characters.
- No `/`, `\`, colons, or special characters problematic on Windows.
- A known extension matching **the actual file format**, never taken blindly from clients.
- Length caps to avoid overly long attachment names.
- No sensitive names, `.`, `..`, or OS-reserved filenames.

### Best: Construct Names from a Controlled Pattern

Example with a constrained business ID:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public final class InvoiceAttachmentNames {
    private InvoiceAttachmentNames() {
    }

    public static String fromInvoice(
            String invoiceCode, LocalDate issueDate) {
        if (invoiceCode == null
                || !invoiceCode.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException(
                    "Invalid invoice code");
        }
        if (issueDate == null) {
            throw new IllegalArgumentException(
                    "Issue date is required");
        }

        return "invoice-" + invoiceCode + "-"
                + issueDate.format(
                        DateTimeFormatter.ISO_LOCAL_DATE)
                + ".pdf";
    }
}
~~~

Usage:

~~~java
String filename = InvoiceAttachmentNames.fromInvoice(
        "INV-583", LocalDate.of(2026, 11, 12));

helper.addAttachment(
        filename,
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Result:

~~~text
invoice-INV-583-2026-11-12.pdf
~~~

This approach is strong because the server selects the extension from the document type while strictly bounding the variable portion.

### If You Must Accept User-Uploaded Filenames

Strings like:

~~~text
../../internal/secrets.pdf
invoice.pdf\r\nX-Custom-Header: suspicious
report.pdf.exe
~~~

must never pass verbatim into attachment filenames or filesystem filenames. Enforce a dedicated upload-name validator and file-type policy; separate:

- **Safe display name** in the email.
- **Server-generated storage name** (usually an opaque ID).
- **Valid extension** derived from the verified file format.

Simple path-stripping/truncating steps alone do not make uploaded content safe or block all path traversal variants; untrusted files also require authorization, content scanning, size limits, and storage policies.

## 18. `Content-Disposition`: `attachment` or `inline`?

Email MIME parts can be displayed for two purposes:

| Mechanism | Typical Header | Meaning |
|---|---|---|
| Attachment | `Content-Disposition: attachment` | Recipient sees a downloadable file |
| Inline | `Content-Disposition: inline` and/or `Content-ID` | Image/content embedded inside HTML |

Attaching a PDF report:

~~~java
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Embedding a logo in HTML:

~~~java
helper.setText(
        "<html><body>"
                + "<p>Hello!</p>"
                + "<img src='cid:companyLogo' alt='Logo'/>"
                + "</body></html>",
        true);

helper.addInline(
        "companyLogo",
        new ByteArrayResource(logoPngBytes),
        "image/png");
~~~

In the HTML example, `companyLogo` is a **Content-ID reference**, not an attachment filename. Some mail clients still show inline resources in the attachment tray, yet sending semantics differ.

### Order of `setText` and `addInline`

For CID-embedded HTML, call `setText(...)` before `addInline(...)` to avoid compatibility bugs in some email clients. For downloadable files, call `addAttachment(...)` explicitly.

## 19. Never Craft `Content-Disposition` with Raw Header Strings

Sometimes developers see a wrong filename and try patching it via:

~~~java
// Not recommended as a default fix:
bodyPart.setHeader(
        "Content-Disposition",
        "attachment; filename=" + userProvidedName);
~~~

Risks:

- Names with quotes, semicolons, or Unicode require proper encoding.
- Injecting untrusted data into raw headers creates security vulnerabilities.
- Headers can get overwritten or fall out of sync with `Content-Type`.
- Manual MIME header logic is hard to test across clients.

`MimeMessageHelper.addAttachment(filename, source, contentType)` provides the right abstraction for passing name, content type, and data. Touch raw MIME headers only for specific compatibility needs when you understand MIME specs and test across target mail clients.

### If Clients Display “noname”

Do not blindly tack on headers. Inspect the actual MIME:

1. Does the attachment part exist?
2. Does `Content-Disposition` include `attachment` and `filename`?
3. Does `Content-Type` have the right type and `name` parameter if needed?
4. Was the filename encoded/decoded accurately?
5. Does the part contain real bytes and valid content?
6. Did a gateway or client rewrite headers or split the file?

A filename failing in Outlook yet working in Thunderbird may be a MIME/filename-parameter encoding issue, not `ByteArrayResource`. Distinguish both by inspecting pre-send MIME and received mail.

## 20. Byte Sources Must Remain Valid When the Email Is Serialized

`MimeMessageHelper.addAttachment(...)` does not immediately copy everything into a finished email byte array at call time. Actual MIME serialization may happen later, inside `mailSender.send(...)` or `message.writeTo(...)`.

With `ByteArrayResource`, data stays in the byte array and each `getInputStream()` returns a fresh stream. That is one reason it fits in-memory attachments well.

### Never Mutate the Byte Array While Another Worker Sends

Broken data ownership:

~~~java
byte[] sharedBuffer = pdfGenerator.generate(invoice);
ByteArrayResource resource =
        new ByteArrayResource(sharedBuffer);

helper.addAttachment("invoice.pdf", resource, "application/pdf");

// Another thread might zero/overwrite sharedBuffer before MIME reads it.
java.util.Arrays.fill(sharedBuffer, (byte) 0);

mailSender.send(message);
~~~

`ByteArrayResource` does not perform an immutable deep copy of bytes. It holds a reference to the passed array. If bytes could be mutated elsewhere, enforce clear ownership or copy defensively:

~~~java
byte[] stableBytes = java.util.Arrays.copyOf(
        generatedBytes, generatedBytes.length);

ByteArrayResource resource =
        new ByteArrayResource(stableBytes);
~~~

Copying isolates content at the cost of **higher memory usage**. For large payloads or high throughput, prefer storage/streaming designs instead of repeated copies.

### Attachments Have a Lifecycle

If a job sits in an outbox for hours, never hold a `ByteArrayResource` in a RAM variable expecting it to survive a process restart. Store files/payloads in protected durable storage; when it is time to send, the worker fetches the payload and builds a fresh `Resource`. Store only payload references/versions in the outbox, never Java objects.

## 21. Repeated Reads: `ByteArrayResource` vs. `InputStreamResource`

A suitable mail attachment source should return a **fresh stream positioned at byte zero** whenever the sender requests one:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(pdfBytes);

try (var first = resource.getInputStream();
     var second = resource.getInputStream()) {
    // Two independent streams both read from the start of the byte array.
}
~~~

If you use a single-use stream:

~~~java
InputStreamResource oneShot =
        new InputStreamResource(
                new java.io.ByteArrayInputStream(pdfBytes));
~~~

MIME assembly may request the stream multiple times to measure or serialize content. `InputStreamResource` generally forbids such re-reads, and the helper may reject an already-open resource.

Solutions:

- Small payloads: `ByteArrayResource`.
- Disk files: `FileSystemResource`.
- Object storage: `InputStreamSource` whose `getInputStream()` opens a **fresh stream every time** for an immutable payload version.

Custom stream sources must guarantee **content does not mutate between opens**. If an object in storage can be overwritten, a second read could see a different file than the first.

## 22. Attachment Size: `ByteArrayResource` Does Not Fit Every File

Consider a 20 MiB PDF:

~~~text
PDF bytes in byte[]             ~20 MiB
Potential render/copy buffers   additional memory
MIME Base64 representation      roughly 4/3 payload + line overhead
Concurrent sends               multiplied by active jobs
~~~

These figures are rough estimates; actual heap usage depends on implementation, copying, streaming/serialization, and GC. Do not treat 4/3 as the exact total RAM footprint of an email.

When 100 workers hold 20 MiB files simultaneously:

\[
100 \times 20\text{ MiB} = 2000\text{ MiB}
\]

the raw byte arrays alone occupy ~2 GiB, before MIME objects, copies, and buffers.

Options:

1. Cap concurrency for large attachments.
2. Never load jobs/attachments into RAM before acquiring an SMTP slot.
3. Enforce file size limits and provider message-size limits.
4. Use file-backed `Resource`s or reopenable storage streams where appropriate.
5. Send a download link to protected storage when product policy allows, rather than attaching huge files.

**Provider size limits apply to MIME-encoded bytes**, not just `byte[].length`. A 20 MiB file produces a MIME message noticeably larger than 20 MiB.

## 23. Do Not Let Attachment Filename Bugs Trigger an SMTP Retry Storm

In production, a clean sequence is:

~~~text
Mail job due
    |
    v
Load payload and choose filename
    |
    v
Validate filename / MIME type / content
    |
    +-- Invalid -> PREPARATION_FAILED
    |             audit + remediation
    |
    v
Acquire provider quota/concurrency permit
    |
    v
Submit via JavaMailSender
    |
    v
Classify SMTP outcome
~~~

A bad filename is a **message preparation error**, usually deterministic:

~~~text
INVALID_ATTACHMENT_FILENAME
EMPTY_ATTACHMENT_PAYLOAD
ATTACHMENT_CONTENT_TYPE_MISMATCH
ATTACHMENT_TOO_LARGE
~~~

Never loop retries with identical inputs because it will fail identically every time. Once data/templates/filenames are fixed, replay in a controlled manner.

### Validate Before Requesting Quotas

If you already know the attachment filename is blank or the payload is missing, do not consume a rate-limiter token only for the helper to throw. Preflight:

- Valid filename with right extension.
- Retrievable payload.
- Attachment size within product/provider limits.
- MIME type matches actual format.
- Authorized recipient and sender.

Because full MIME assembly before a quota gate can consume CPU/memory, run lightweight preflight checks before admission and serialize fully **closer to send time** with policy-based permit handling.

## 24. Unit Test: Proving `getFilename()` Has No Name

Before fixing, reproduce the false assumption with JUnit 5 and AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;

class ByteArrayResourceFilenameTest {

    @Test
    void plainByteArrayResourceDoesNotHaveFilename() {
        ByteArrayResource resource =
                new ByteArrayResource(
                        "test-data".getBytes(StandardCharsets.UTF_8));

        assertThat(resource.getFilename()).isNull();
        assertThat(resource.contentLength()).isEqualTo(9);
    }

    @Test
    void descriptionDoesNotBecomeFilename() {
        ByteArrayResource resource =
                new ByteArrayResource(
                        new byte[] {1, 2, 3},
                        "report.pdf");

        assertThat(resource.getDescription())
                .contains("report.pdf");
        assertThat(resource.getFilename()).isNull();
    }
}
~~~

The second test clearly shows the two-argument constructor only sets `description`.

### Testing `addAttachment` Error with a `null` Filename

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

class InvalidAttachmentNameTest {

    @Test
    void cannotUseByteArrayResourceFilenameAsAttachmentName()
            throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        MimeMessageHelper helper = new MimeMessageHelper(
                sender.createMimeMessage(), true, "UTF-8");

        ByteArrayResource resource =
                new ByteArrayResource(new byte[] {1, 2, 3});

        assertThatThrownBy(
                () -> helper.addAttachment(
                        resource.getFilename(), resource))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Specific exception details and message wording can vary across Spring versions, so assert the invalid-filename contract rather than exact English message text. No SMTP commands are issued in this test.

## 25. Unit Test: Verifying the Actual Attachment Name and Bytes

You do not need to send real emails to test MIME attachments. `JavaMailSenderImpl.createMimeMessage()` builds a `MimeMessage` in memory. After `MimeMessageHelper` configures it, use Jakarta Mail to read back the MIME parts.

Example verifying ASCII filename, Content-Type, and payload bytes:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

class MailAttachmentMimeTest {

    @Test
    void attachmentHasExpectedFilenameAndContent()
            throws Exception {
        byte[] data = "a,b\r\n1,2\r\n"
                .getBytes(StandardCharsets.UTF_8);

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("sender@example.test");
        helper.setTo("recipient@example.test");
        helper.setSubject("Report");
        helper.setText("Attached CSV report.", false);

        helper.addAttachment(
                "report-2026-11.csv",
                new ByteArrayResource(data),
                "text/csv; charset=UTF-8");

        mime.saveChanges();
        Multipart content = (Multipart) mime.getContent();
        BodyPart attachment = findAttachment(content);

        assertThat(attachment).isNotNull();
        assertThat(attachment.getFileName())
                .isEqualTo("report-2026-11.csv");
        assertThat(attachment.isMimeType("text/csv")).isTrue();

        try (InputStream input = attachment.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(data);
        }
    }

    private static BodyPart findAttachment(Multipart multipart)
            throws Exception {
        for (int index = 0;
                index < multipart.getCount();
                index++) {

            BodyPart part = multipart.getBodyPart(index);
            if (Part.ATTACHMENT.equalsIgnoreCase(
                    part.getDisposition())) {
                return part;
            }

            Object child = part.getContent();
            if (child instanceof Multipart nested) {
                BodyPart found = findAttachment(nested);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
~~~

Because `MimeMessageHelper` supports multiple multipart modes, traverse **recursively through nested multiparts** instead of assuming the attachment always sits at `getBodyPart(1)`. Body alternatives and inline images alter the MIME tree.

### What Does This Test Verify?

- The attachment part exists.
- The filename set by the helper is right.
- The content type semantically matches `text/csv`.
- The returned payload bytes match what was supplied.
- Everything runs purely in memory without SMTP credentials or sending real mail.

This test does not prove a specific email client displays the name identically or that no gateway rewrites headers. For Unicode or very long filenames, add appropriate integration tests.

## 26. Inspecting Raw MIME to Debug Header Errors

When determining whether an issue is in Spring's helper or a mail client, serialize a **test email with dummy content**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

mimeMessage.saveChanges();
ByteArrayOutputStream raw = new ByteArrayOutputStream();
mimeMessage.writeTo(raw);

String mimeText = raw.toString(
        StandardCharsets.ISO_8859_1);
System.out.println(mimeText);
~~~

Then inspect:

~~~text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="..."

--...
Content-Type: text/plain; charset=UTF-8

...
--...
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

...
~~~

This is an **illustrative mockup**; exact header order, boundaries, encoding, and MIME nesting may vary across Jakarta Mail versions.

### Never Print Raw MIME of Customer Emails

`System.out.println(mimeText)` belongs strictly in **dummy test fixtures**. Raw MIME exposes bodies, recipients, attachments, and sensitive data; never log raw MIME in production just to “check filenames”.

Production observability should record:

~~~text
event=mail_attachment_prepared
mailJobId=opaque-job-583
attachmentType=INVOICE_PDF
fileExtension=pdf
sizeBytes=16384
filenameValidation=PASSED
~~~

When investigating a real message, use an access-controlled diagnostic workflow with masking and short retention.

## 27. Integration Testing with an SMTP Sink

After MIME unit tests, run integration tests against an SMTP sink/test server such as Mailpit or GreenMail, avoiding real recipients.

Flow:

~~~text
Spring Mail service
    |
    v
JavaMailSender configured for SMTP sink
    |
    v
SMTP sink receives message
    |
    v
Read saved message's MIME parts
    |
    +-- Content-Disposition: attachment
    +-- Filename: report-2026-11.pdf
    +-- Content-Type: application/pdf
    +-- Bytes: expected fixture
~~~

Scenarios:

| Scenario | Expected Outcome |
|---|---|
| `ByteArrayResource` + valid filename | Attachment shows expected name |
| `ByteArrayResource` + `getFilename()` | Blocked at MIME build step |
| Extensionless filename | Caught as violating business metadata contract |
| PDF bytes with PDF MIME | MIME part has right type and bytes |
| Valid Unicode name | Read back per Jakarta Mail / target client behavior |
| Multiple attachments | Each part has the right name without mixed bytes |
| HTML + inline logo + PDF attachment | Inline and attachment keep distinct semantics |
| Large file | Verify max size/memory/transport |
| Server returns SMTP error | Not misclassified as filename bug |
| Job retry | Each attempt builds MIME with expected filename/content version |

An SMTP sink verifies emails submit cleanly as MIME without spamming external mailboxes. Still, it does not simulate all Gmail, Outlook, or enterprise gateway behaviors; for strict compatibility needs, test on target clients with test accounts.

## 28. Duplicate Filenames Across Multiple Attachments in One Email

If a message attaches two reports:

~~~java
helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(firstPdf),
        "application/pdf");

helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(secondPdf),
        "application/pdf");
~~~

both MIME parts carry **the same display filename**. Nothing guarantees mail clients will disambiguate them cleanly; on download, users may get `report (1).pdf`, overwrite prompts, or inconsistent behavior.

Instead of relying on client disambiguation:

~~~java
helper.addAttachment(
        "invoice-INV-583.pdf",
        new ByteArrayResource(firstPdf),
        "application/pdf");

helper.addAttachment(
        "payment-receipt-INV-583.pdf",
        new ByteArrayResource(secondPdf),
        "application/pdf");
~~~

Give each attachment a semantically distinct name. When attaching multiple versions of the same document, include a version, date, or controlled reference.

### Never Use Raw File Paths to Avoid Collisions

Do not generate names like `/tmp/report-1234.pdf` or include full object storage keys. Uniqueness in email filenames should come from safe business IDs without exposing server paths.

## 29. Using Custom `Multipart` or `DataSource` Instead of `ByteArrayResource`

`MimeMessageHelper` also provides overloads taking `DataSource` or `File`. These still carry the MIME filename concept.

Example with `ByteArrayDataSource` from Jakarta Mail:

~~~java
import jakarta.mail.util.ByteArrayDataSource;

ByteArrayDataSource dataSource =
        new ByteArrayDataSource(
                pdfBytes, "application/pdf");

helper.addAttachment(
        "invoice-583.pdf",
        dataSource);
~~~

The `DataSource` supplies bytes and content type; **the MIME attachment display name is still passed explicitly to `addAttachment`**. If you build body parts manually without the helper, you must handle `Content-Disposition`, filename encoding, and data lifecycle far more carefully.

### Do Not Confuse `DataSource.getName()` with the Desired Display Name

A `DataSource`'s self-reported name may not match what recipients should see. When calling `MimeMessageHelper.addAttachment(attachmentFilename, dataSource)`, still pick an explicit filename matching the content.

## 30. Separating Content, Filename, and SMTP Send Errors

A well-structured mail pipeline separates phases:

~~~text
1. Resolve business record
2. Generate attachment bytes
3. Determine filename + content type
4. Validate attachment size and policy
5. Compose MimeMessage
6. Submit SMTP
7. Persist submission outcome
~~~

Suggested internal error codes:

| Phase | Suggested Internal Code | Retry SMTP Immediately? |
|---|---|---|
| Resolve | `BUSINESS_DATA_MISSING` | No; needs valid data |
| Generate | `PDF_GENERATION_FAILED` | Depends on generator cause |
| Filename | `INVALID_ATTACHMENT_FILENAME` | No; fix name |
| Payload | `EMPTY_ATTACHMENT` | No; check source |
| Size | `ATTACHMENT_EXCEEDS_LIMIT` | No; shrink or switch delivery method |
| MIME composition | `MIME_PREPARATION_FAILED` | Classify exact cause first |
| SMTP auth | `SMTP_AUTH_FAILED` | Do not hot-retry with same credentials |
| SMTP temp reject | `SMTP_TEMPORARY_REJECTION` | May retry with backoff |
| Network ambiguous | `SMTP_OUTCOME_UNKNOWN` | Never blind-retry |
| Accepted | `SMTP_SUBMITTED` | Do not resend merely awaiting delivery event |

Filename failures happen **before submission**; never count them as SMTP provider throttling or burn transport retry budgets on them.

## 31. Quick Diagnostic Table When Attachments Show Wrong Names

| Symptom | Possible Cause | How to Check | Fix |
|---|---|---|---|
| `attachmentFilename must not be null` or similar argument error | Used `ByteArrayResource.getFilename()` | Inspect/assert filename **in tests** | Pass explicit name to `addAttachment` |
| `ByteArrayResource(bytes, name)` still lacks filename | `name` is `description` | Test `getFilename()` | Do not use `description` as filename |
| File shows `noname` | MIME part missing/unreadable filename | Inspect `Content-Disposition` | Pass valid name; check encoding/headers |
| File named only `report` | Missing extension | Check `addAttachment` argument | Use `report.pdf`/`report.csv` |
| File named `report.pdf.txt` | Extension appended twice | Inspect filename builder | Derive extension once from format |
| Duplicate names across attachments | Parts share identical filename | Inspect all MIME parts | Add business reference/version |
| PDF reported as “corrupted/invalid file” | Bytes not PDF or truncated | Test content bytes/size | Fix generator/stream, not just filename |
| App opens attachment in wrong program | Extension/content type mismatch | Check name, type, and content | Align all three |
| Vietnamese diacritics garbled in name | Header encoding or client compatibility | Test raw MIME and multiple clients | Charset/encoding policy; consider ASCII |
| Attachment missing in client | Added as inline instead of attachment | Check disposition | Use `addAttachment` for downloads |
| `Resource is already open` or second-read error | Used `InputStreamResource` | Check `isOpen`/repeatability | Use `ByteArrayResource` or fresh-stream source |
| Email sends yet attachment is empty | Empty `byte[]` or failed source | Unit test payload length/readback | Validate bytes before composing |
| Name right in sink yet changed in client | Gateway/client rewrite | Compare MIME before/after provider | Investigate policy/client compatibility |
| Some emails fail while others succeed | Dynamic filename contains invalid chars | Log reason code; check builder | Sanitize/validate input |
| Server runs out of heap sending many PDFs | `ByteArrayResource` holds many `byte[]`s | Heap/GC metrics | Bound concurrency, use file-backed resources |

### Never Fix the Wrong Layer

If the stack trace shows `IllegalArgumentException` inside `MimeMessageHelper.addAttachment(...)`, raising SMTP timeouts or changing passwords solves nothing. Conversely, if MIME tests pass and SMTP returns `AuthenticationFailedException`, changing filenames will not fix login failures.

Always find **the first stage that failed** before tweaking configuration.

## 32. Dynamic Filenames in Systems with Retries/Outboxes

A production system may persist an email job in the database and send minutes later:

~~~text
Order created
     |
     v
Outbox mail job
  invoiceId = INV-583
  payloadVersion = 2
  attachmentKind = INVOICE_PDF
     |
     v
Worker loads payload
     |
     v
Filename builder
  invoice-INV-583.pdf
     |
     v
ByteArrayResource + addAttachment
     |
     v
SMTP submission
~~~

Better to persist:

~~~json
{
  "mailJobId": "opaque-id-583",
  "attachmentKind": "INVOICE_PDF",
  "businessRef": "INV-583",
  "payloadVersion": 2
}
~~~

instead of holding raw `byte[]` or a Java `Resource` instance in RAM. The worker derives the filename per policy at send time and can record a **filename version** so retries keep stable metadata if required.

### Should Filenames Change Between Retries?

For the same intent to send an issued invoice, keep **name and content consistent** across attempts:

~~~text
Attempt 1: invoice-INV-583.pdf
Attempt 2: invoice-INV-583.pdf
~~~

Renaming to `invoice-final-v7.pdf` on the second retry just because a template changed can deliver two differently named versions when the first attempt's outcome was uncertain. Enforce snapshot/versioning policies on both payloads and filenames.

### Never Create Duplicate Intents Just to Fix a Filename

If a job failed on filename prior to SMTP submission, fix the generator and replay through a controlled workflow. Never spawn brand-new email jobs for the same business event without an idempotency key. Use `PREPARATION_FAILED` or an equivalent reason code to separate it from SMTP rejections.

## 33. Filenames and Privacy

Attachment names can expose:

- Customer full names.
- Identifying invoice or contract numbers.
- Email addresses or phone numbers.
- Patient IDs, bank accounts, or similar sensitive numbers.
- Internal project codenames or server file paths.

Even when emailed to the right recipient, files get downloaded, forwarded, or stored on shared machines. A name like:

~~~text
medical-records-john-doe-2026.pdf
~~~

may violate data minimization policies, whereas:

~~~text
document-INV-583.pdf
~~~

may satisfy UX needs if `INV-583` is non-sensitive. This depends on domain rules; avoid embedding unnecessary identifiers in filenames.

### Storage Paths Differ from Download Names

~~~text
Internal object key:
  tenants/42/private/invoices/INV-583/pdf/v2/7c31a...

Public attachment filename:
  invoice-INV-583.pdf
~~~

Never expose the object key as the filename, as it leaks storage layout and tenant IDs. Separate display names from storage references.

### Controlling User-Supplied Names

If customers are allowed to pick names:

1. Verify authorization to access the document.
2. Verify format/MIME type.
3. Cap length and strip problematic characters.
4. Strip or reject control characters and path separators.
5. Enforce PII and sensitive-content policies.
6. Never put raw names into metric labels.
7. Use an independent storage name; never build filesystem paths from this name.

## 34. Should MIME Type Be Set to `application/octet-stream`?

`application/octet-stream` denotes generic binary data. For an unknown binary format, it can be a reasonable fallback. Yet when you know it is a PDF:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

is far clearer than:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfBytes),
        "application/octet-stream");
~~~

in terms of content semantics.

However, **never use MIME types to deceive mail clients**. If the bytes are an executable or malicious file, naming it `invoice.pdf` and declaring `application/pdf` does not make it a safe PDF. Gateways inspect payloads and quarantine accordingly.

### `Content-Type` Is Not File Validation

For files generated internally by a trusted library, the generator knows the type. For uploads from untrusted sources, enforce dedicated format and security checks: magic numbers/signatures, safe parsers, antivirus policies, size caps, and authorization. Never trust extensions or HTTP upload `Content-Type` headers alone.

## 35. How Do Attachments Differ Between HTTP Responses and Emails?

A download API typically sets:

~~~http
Content-Disposition: attachment; filename="invoice.pdf"
Content-Type: application/pdf
~~~

in **HTTP response headers**. When emailing, `MimeMessageHelper.addAttachment(...)` creates **MIME body part headers** with related semantics, yet via a completely different API.

Do not copy:

~~~java
response.setHeader(
        "Content-Disposition",
        "attachment; filename=invoice.pdf");
~~~

into a controller expecting the email to automatically gain an attachment. HTTP response headers do not modify a `MimeMessage` sent over SMTP.

Likewise, a `ByteArrayResource` inside an HTTP `ResponseEntity<Resource>` needs HTTP headers to supply a download filename; `ByteArrayResource.getFilename()` does not change just because it was used at the web layer. Always set filenames explicitly at **the layer producing output metadata**.

## 36. A Practical Helper for `byte[]` Attachments

In applications exporting multiple file formats, centralize validation and `addAttachment`:

~~~java
import jakarta.mail.MessagingException;
import java.util.Objects;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class MailAttachmentSupport {
    private MailAttachmentSupport() {
    }

    public static void addBytes(
            MimeMessageHelper helper,
            String filename,
            String contentType,
            byte[] bytes) throws MessagingException {

        Objects.requireNonNull(helper, "helper");
        Objects.requireNonNull(bytes, "bytes");

        if (bytes.length == 0) {
            throw new IllegalArgumentException(
                    "Attachment must not be empty");
        }
        if (filename == null
                || filename.isBlank()
                || filename.contains("/")
                || filename.contains("\\")
                || filename.indexOf((char) 13) >= 0
                || filename.indexOf((char) 10) >= 0) {
            throw new IllegalArgumentException(
                    "Invalid attachment filename");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException(
                    "Attachment content type is required");
        }

        helper.addAttachment(
                filename,
                new ByteArrayResource(bytes),
                contentType);
    }
}
~~~

Usage example:

~~~java
MailAttachmentSupport.addBytes(
        helper,
        "invoice-INV-583.pdf",
        "application/pdf",
        pdfBytes);
~~~

**Limitations of this helper:** it illustrates only the basic contract. Production code should add max byte limits, extension/content-type allowlists, filename length limits, Unicode control-character filtering, OS-reserved name checks, and real content-type verification. A valid-looking filename does not mean the bytes are a valid PDF or passed security scanning.

### Why Use a Shared Helper?

When multiple services send attachments, centralizing the logic prevents future developers from slipping back into:

~~~java
helper.addAttachment(
        byteArrayResource.getFilename(),
        byteArrayResource);
~~~

A helper also provides one consistent spot to adjust MIME policies, charsets, or size limits without editing dozens of email templates.

## 37. Incident Workflow When Users Report Wrong Filenames

Suppose customers receive an invoice email whose attachment is named `noname`, `attachment`, or `invoice.pdf.txt`.

**Never start by bulk-resending emails.** First determine whether the bug occurred before SMTP, in MIME output, or at the mail client.

~~~mermaid
flowchart TD
    A[Attachment filename is wrong] --> B{Was email submitted successfully?}
    B -- No --> C[Inspect errors during MimeMessage creation]
    C --> D{ByteArrayResource.getFilename null?}
    D -- Yes --> E[Pass explicit filename to addAttachment]
    D -- No --> F[Check validation/content type/multipart]
    B -- Yes --> G[Inspect test/sink MIME]
    G --> H{MIME part has right filename?}
    H -- No --> I[Fix filename builder/header encoding]
    H -- Yes --> J[Compare mail clients/gateways]
    J --> K[Check Unicode, MIME rewrites, security policies]
~~~

### Step 1. Inspect the Attachment-Building Code

Search for patterns:

~~~java
new ByteArrayResource(...)
resource.getFilename()
helper.addAttachment(...)
~~~

Pay special attention to:

~~~java
ByteArrayResource resource =
        new ByteArrayResource(bytes, "report.pdf");
helper.addAttachment(resource.getFilename(), resource);
~~~

The name in the two-argument constructor is a description and never becomes the filename.

### Step 2. Define the Expected Application Metadata

Example:

~~~text
documentKind = INVOICE_PDF
safeReference = INV-583
desiredFilename = invoice-INV-583.pdf
desiredMimeType = application/pdf
payloadSize = 32768 bytes
~~~

All values are dummy guidance data. Never take filenames directly from user requests or long storage keys.

### Step 3. Reproduce in a Unit Test

No real credentials or Internet connection needed. Use `JavaMailSenderImpl.createMimeMessage()` and `MimeMessageHelper` to construct a fixture, then assert `BodyPart.getFileName()`, `isMimeType(...)`, and stream bytes.

If the MIME test fails, fix application code before investigating providers.

### Step 4. Check the SMTP Sink

If unit tests pass while messages captured by the sink are wrong, compare built MIME against sink-received MIME. Intermediate code on the send path may be modifying headers or attachments.

### Step 5. Compare Target Clients

If MIME in the sink is valid, send dummy test emails to target mail clients to check Unicode/filename encoding or gateway policies. Test only within authorized scope and never with real customer data.

### Step 6. Handle Failed Mail Jobs

If emails **were not sent** due to filename errors, fix config/code and replay via an approved workflow. If the provider **already accepted**, do not bulk-resend solely because a customer reported an odd display name; weigh duplicate risks, sensitive content, and support strategy.

## 38. Anti-Patterns to Avoid

### 38.1. Calling `Resource.getFilename()` on Every `Resource` Type

~~~java
helper.addAttachment(resource.getFilename(), resource);
~~~

`ByteArrayResource`, custom `InputStreamSource`s, and non-path resources lack filenames. Choose an explicit name at the application layer when adding attachments.

### 38.2. Mistaking `ByteArrayResource` `description` for `filename`

~~~java
new ByteArrayResource(bytes, "invoice.pdf");
~~~

This constructor alone never sets a filename. `addAttachment("invoice.pdf", resource)` is still required.

### 38.3. Putting `.pdf` on Every Attachment

CSV or XLSX bytes do not become a PDF by renaming. Extension, MIME type, and byte format must match.

### 38.4. Leaving Filename Blank Assuming Clients Name It

Blank/null names are rejected by the helper or display poorly. Require valid filenames with proper extensions.

### 38.5. Using Filesystem Paths as Download Names

~~~text
C:\\internal\\temp\\invoice.pdf
/srv/app/private/tenant-42/invoice.pdf
~~~

Internal paths leak system internals; pass only a controlled basename.

### 38.6. Passing Unvalidated Filenames Straight from Requests

Names with control characters, `../`, or sensitive strings must be sanitized or replaced by server-generated names.

### 38.7. Using `addInline` Instead of `addAttachment`

`addInline(...)` is for `Content-ID` embedded content, not standard downloadable attachments.

### 38.8. Crafting Raw MIME Headers from Untrusted Strings

Filenames require proper quoting and encoding rules. `MimeMessageHelper` is the safer API unless specialized MIME behavior is needed.

### 38.9. Using `InputStreamResource` for Single-Read Streams

Serialization may need to reopen the stream. Use `ByteArrayResource` for `byte[]`, or fresh-stream sources for large files.

### 38.10. Clearing or Mutating `byte[]` Before `send`

`ByteArrayResource` retains the `byte[]` to read later; mutating the buffer mid-flight corrupts the attachment.

### 38.11. Creating Thousands of Large `ByteArrayResource`s at Once

Spikes heap and GC, especially alongside MIME/Base64 buffering. Bound size/concurrency and use file-backed storage where appropriate.

### 38.12. Retrying SMTP When `addAttachment` Throws Argument Errors

That is an input/preparation error, not a provider outage. Retries will never fix a null filename.

### 38.13. Using `application/octet-stream` Blindly for All Formats

Generic fallbacks prevent clients from recognizing documents cleanly. When the document type is known, declare the exact MIME type.

### 38.14. Testing Only That `mailSender.send` Was Called

Mockito `verify(send(...))` does not prove MIME parts carry the right filenames. Inspect the generated `MimeMessage` and `BodyPart.getFileName()` in tests.

### 38.15. Assuming the Attachment Is Always the Second MIME Part

Emails with HTML alternatives, inline logos, and nested multiparts shift part order. Locate parts by disposition/filename rather than hardcoding indices.

### 38.16. Blaming Spring Just Because Gmail/Outlook Render Differently

Compare raw MIME before and after gateways. The issue may be encoding, client policy, or gateway rewriting rather than `ByteArrayResource`.

### 38.17. Logging Raw MIME to Debug Filename Bugs

Raw MIME exposes PII, attachments, and secrets; use dummy test fixtures and log safe metadata.

### 38.18. Making Filenames Unique Using Recipients' Personal Emails

Filenames are visible metadata and can be forwarded. Use non-sensitive business codes or opaque references.

### 38.19. Subclassing Just So the Helper Needs No Filename

`MimeMessageHelper.addAttachment(...)` still requires the filename parameter. Subclassing is unnecessary when the application passes an explicit name.

### 38.20. Treating a Valid Filename as Proof of a Valid Attachment

Name, content type, and payload must each be validated independently. An `invoice.pdf` with zero bytes or wrong format is still a broken attachment.

## 39. Practice Exercises

### Exercise 1: Fixing a `null` Filename Error

Initial code:

~~~java
byte[] data = reportService.exportPdf(reportId);
ByteArrayResource source =
        new ByteArrayResource(data, "report.pdf");

helper.addAttachment(source.getFilename(), source);
~~~

Tasks:

1. Explain why `getFilename()` does not return `report.pdf`.
2. Fix the code to attach as `report-2026-11.pdf`.
3. Declare the PDF MIME type.
4. Write a JUnit test verifying the filename.

Solution:

~~~java
byte[] data = reportService.exportPdf(reportId);
ByteArrayResource source = new ByteArrayResource(data);

helper.addAttachment(
        "report-2026-11.pdf",
        source,
        "application/pdf");
~~~

Reason: the two-argument constructor sets description, not filename; MIME names must be supplied by the application at `addAttachment(...)`.

### Exercise 2: Distinguishing Three Formats

Given three byte arrays produced by dedicated generators:

~~~java
byte[] pdf = pdfService.generate();
byte[] csv = csvService.generate();
byte[] xlsx = xlsxService.generate();
~~~

Attach all three with names:

~~~text
monthly-report.pdf
monthly-data.csv
monthly-table.xlsx
~~~

and accurate MIME types:

~~~java
helper.addAttachment(
        "monthly-report.pdf",
        new ByteArrayResource(pdf),
        "application/pdf");

helper.addAttachment(
        "monthly-data.csv",
        new ByteArrayResource(csv),
        "text/csv; charset=UTF-8");

helper.addAttachment(
        "monthly-table.xlsx",
        new ByteArrayResource(xlsx),
        "application/vnd.openxmlformats-officedocument."
                + "spreadsheetml.sheet");
~~~

Extension hint: test all three attachments by traversing every MIME part and asserting name, type, and byte payload without relying on part order.

### Exercise 3: Filename from Untrusted Input

Suppose a request contains:

~~~text
filename = "../../private/report.pdf"
~~~

Never use that string directly in email or as a filesystem path. Do the following:

1. Determine the allowed report type from the server-side business event.
2. Generate a server-controlled name, e.g. `report-REQ-583.pdf`.
3. Enforce format, length, MIME type, and size limits.
4. Use a storage key independent of the display name.
5. Never log the raw untrusted name or sensitive paths to metrics.

The solution should reflect **choosing a valid name**, not just stripping `..` and trusting everything else.

## 40. Frequently Asked Questions

**Why does `ByteArrayResource.getFilename()` return `null`?** Because `ByteArrayResource` only wraps in-memory byte data rather than representing a file path. It has no way to know the name recipients should see. Supply the filename via `MimeMessageHelper.addAttachment(...)`.

**Does `ByteArrayResource(bytes, "report.pdf")` set the filename?** No. The second argument is a description for the `Resource`. `getFilename()` is not populated from the description.

**I passed `new ByteArrayResource(bytes)`, why does `addAttachment(...)` still ask for a name?** That is the API design: the byte source and MIME attachment name are separate inputs. The name goes into the `attachmentFilename` argument.

**What is the quickest fix?** Use `helper.addAttachment("report.pdf", new ByteArrayResource(bytes), "application/pdf")`, provided the bytes are truly PDF and the filename fits business rules.

**Should I subclass `ByteArrayResource` to override `getFilename()`?** Only when another code path genuinely requires a named `Resource`. For Spring Mail, passing the filename directly to `addAttachment(...)` is usually simpler and clearer.

**Can I pass a `null` filename and let the mail client name it?** Do not. Null names are rejected by API validation and cause MIME preparation errors; display names must be explicitly set by the application.

**If there is no extension, does the email still send?** Possibly, depending on inputs and helper. Yet recipients struggle to open the file and content-type detection becomes unreliable. Always include the right extension.

**Must content type be passed explicitly?** The two-argument overload infers type from the filename. For formats where certainty matters, pass content type explicitly to avoid relying on MIME maps.

**Is `application/octet-stream` wrong?** Not always; it is the generic binary type. Yet when you know a file is PDF/CSV/XLSX, a specific media type gives more accurate metadata.

**I set `filename="report.pdf"`, why does the recipient see `report.txt`?** Check `Content-Type`, `Content-Disposition`, the actual MIME part, client/gateway rewriting, and byte format. Other code may be mutating headers after `addAttachment(...)`.

**Are Vietnamese filenames with diacritics allowed?** Yes, though you must consider MIME filename encoding and varying client support. Safe ASCII names are a reliable compatibility choice when Unicode is not strictly required.

**Does `MimeMessageHelper.setEncodeFilenames(true)` fix all garbled Unicode names?** No. It affects how filenames are encoded in some helper/Spring versions. You still need to consider Jakarta Mail, MIME standards, and target mail clients; no single toggle guarantees every client.

**Should I manually construct the `Content-Disposition` header?** Usually no. `MimeMessageHelper.addAttachment(...)` provides the proper API. Hand-crafting headers invites quoting, Unicode, and injection bugs.

**How does `addInline(...)` differ from `addAttachment(...)`?** `addInline` is for Content-ID embedded content, usually HTML images. `addAttachment` creates downloadable attachments.

**Why is `InputStreamResource` discouraged?** It wraps an already-open stream and does not guarantee repeatable reads. MIME serialization may open streams more than once; `ByteArrayResource` or a reopenable source fits better.

**Can `FileSystemResource` replace `ByteArrayResource`?** Yes, when the file already lives on disk and outlives the send operation. Still pass an explicit download filename rather than exposing internal paths.

**Does `ByteArrayResource` copy the `byte[]`?** Do not assume it deep-copies the passed array. When bytes might be modified concurrently, enforce clear ownership or copy intentionally.

**Is `ByteArrayResource` good for a 100 MB PDF?** Think carefully. Huge byte arrays across concurrent sends spike heap and GC, while MIME Base64 inflates message size further. Evaluate file-backed resources, quotas, size caps, or download links.

**Why is the attachment empty even when the name is right?** The generator may have returned empty bytes, the stream was already drained, or it was truncated. Assert payload size and bytes in unit tests; fixing the filename cannot create missing bytes.

**Can `.csv` be renamed to `.xlsx` so Excel opens it better?** No. XLSX is a completely different file format; changing the extension does not convert CSV bytes into XLSX.

**Why are there two files with the same name in the email?** The app likely called `addAttachment(...)` twice with identical filenames. Generate distinct names by document kind/reference instead of relying on clients to rename them.

**Do we need to test with real production emails?** No. Most filename and MIME bugs are caught locally using `MimeMessage`, JUnit, and an SMTP sink. Use real clients only for targeted compatibility checks with dummy data.

**Does `mailSender.send(...)` succeeding mean the recipient can open the attachment?** No. It confirms only that SMTP submission completed from the client's perspective. Gateways may strip files or clients may fail to open contents; verify delivery/attachments separately.

**If `addAttachment(...)` throws `IllegalArgumentException`, should we retry?** Never keep retrying SMTP with the same null filename. That is an email preparation bug requiring an input or code fix.

**What if the filename comes from the customer's name?** Consider privacy and unsafe characters. It is usually better to use an authorized non-sensitive business reference or generic document name.

**Can we use the filename from an object storage URL?** Never copy raw URLs or keys as MIME names, as they can leak paths/tokens and produce ugly names. Choose a dedicated display name.

**Should filenames be stored in the outbox?** Depends on policy. Store a validated filename or store document kind/reference/version so workers generate stable names. Never store Java `Resource` objects in the DB.

**What if a job retries after filename policy changes?** Keep version/snapshot policies for issued documents so retries of the same job do not unexpectedly produce different names or contents.

**Can we use one fixed name `attachment.pdf` for all emails?** Technically yes, yet users struggle to tell documents apart after saving them. Safe business-context names are much friendlier.

**When inspecting MIME, why isn't the attachment in the second body part?** Multipart MIME can nest several levels deep, especially when emails combine plain text, HTML, inline images, and attachments. Locate parts by disposition/filename.

**How do we avoid leaking content when debugging?** Use dummy fixtures in unit tests. In production log only safe metadata like file extension, size, document kind, internal job ID, and error reason codes.

## 41. Standard Workflow to Prevent Recurring Errors

Whenever a new feature attaches in-memory bytes to email, follow these steps:

1. **Identify content format:** PDF, CSV, XLSX, ZIP, or other.
2. **Generate valid bytes:** call the generator, verify non-null/non-empty and within size limits.
3. **Derive name from business context:** use document kind, safe business reference, and period/date; never `ByteArrayResource.getFilename()`.
4. **Validate filename:** basename, length, extension, control characters, privacy.
5. **Select MIME content type:** match the actual byte format.
6. **Create `ByteArrayResource`** for moderate payloads; choose file-backed or reopenable sources for large files.
7. **Build multipart message:** `MimeMessageHelper(message, true, "UTF-8")` or explicit mode.
8. **Set From/To/Subject/Body:** valid inputs and authorized sender identity.
9. **Call `addAttachment(filename, resource, contentType)`:** explicit filename.
10. **Unit-test MIME before SMTP:** verify filename, content type, and bytes.
11. **Test with sink/clients when needed:** especially for Unicode or mixed inline/attachments.
12. **Classify exceptions properly:** filename/file errors are preparation failures, not transient SMTP throttles.
13. **Dispatch via outbox when reliability matters:** keep payload references and metadata stable across retries.
14. **Observe safely:** log error codes, extensions, sizes, and opaque IDs—never raw MIME or PII.

### Final Reference Example

~~~java
byte[] attachmentBytes = documentGenerator.generate(document);
String attachmentName = "document-"
        + document.safeReference() + ".pdf";

if (attachmentBytes == null
        || attachmentBytes.length == 0) {
    throw new IllegalStateException(
            "Document generator returned empty data");
}

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("documents@example.com");
helper.setTo(recipientEmail);
helper.setSubject("Your document");
helper.setText("Please see the attached file.", false);

helper.addAttachment(
        attachmentName,
        new ByteArrayResource(attachmentBytes),
        "application/pdf");

mailSender.send(message);
~~~

In production code, `document.safeReference()` and sender/recipient must pass appropriate business rules, authorization, and validation. `documentGenerator` and `document` are placeholders.

## 42. Summary

The error **“Using `ByteArrayResource` while setting the attachment filename incorrectly”** usually stems from one false assumption:

> Because `ByteArrayResource` is a `Resource`, `getFilename()` must return the generated file's name.

**That assumption is false.** `ByteArrayResource` wraps a `byte[]` and carries no filename; even the two-argument constructor `ByteArrayResource(bytes, description)` only sets a description.

Core usage:

~~~java
byte[] pdfBytes = pdfGenerator.generate();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addAttachment(
        "invoice-583.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
~~~

Keep three values distinct:

~~~text
ByteArrayResource  -> byte source
attachmentFilename -> download display name
contentType        -> declared MIME type
~~~

Key takeaways:

1. **Never rely on `ByteArrayResource.getFilename()` to name attachments.** Build a valid name from business context.
2. **Never confuse `description` with `filename`.** The two-argument constructor does not fix filename errors.
3. **Filename, extension, `Content-Type`, and byte format must align.** A nice filename cannot fix empty or corrupt bytes.
4. **Use the right abstraction:** `addAttachment` for downloadable files, `addInline` for CID-embedded HTML content.
5. **Choose repeatable content sources:** `ByteArrayResource` for reasonably sized memory payloads, file-backed/reopenable streams for large files.
6. **Test MIME parts directly** with `getFileName()`, `getContentType()`, and byte streams; no real email send is needed to catch filename bugs.
7. **Protect data:** never put internal paths, sensitive recipient names, or control characters in attachment names.
8. **Classify errors accurately:** filename errors are email-preparation failures, not SMTP outages to retry endlessly.

When your application explicitly specifies **the attachment name during MIME construction**, attaching in-memory PDFs, CSVs, XLSX reports, or generated documents becomes clear and testable—eliminating a class of errors that confuses recipients and operators alike.
