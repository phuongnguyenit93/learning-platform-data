# Unicode Filenames and Encoding Handling

In an email-sending module built with **Spring Framework Mail**, an attachment may carry a filename containing Vietnamese or Unicode characters, for example:

~~~text
Báo cáo tháng 11.pdf
Hóa đơn Nguyễn An – 2026.xlsx
契約書_注文123.pdf
Résumé – édition finale.docx
~~~

This filename is displayed in the email client's attachment list. Even when the file's bytes are completely valid, the recipient may still see a garbled name such as `BÃ¡o cÃ¡o.pdf`, question marks, or a cryptic encoded string if MIME metadata is represented or decoded improperly.

An important distinction is that **filename encoding** and **file content encoding** are two separate concerns. For a PDF, the content is typically binary bytes packaged with an appropriate transfer encoding; the Unicode filename sits in a MIME header parameter such as `Content-Disposition: attachment; filename=...`. For CSV or TXT files, in addition to the filename, you must also specify the charset of the text bytes themselves.

Spring Mail and Jakarta Mail help construct the required MIME headers. When using `MimeMessageHelper`, the application should pass **the original filename as a Java String** and let the library handle header encoding according to the compatibility capabilities of the version in use; do not manually Base64- or URL-encode the filename before calling the mail API.

## 1. Where does the filename live in a MIME email?

An attachment is a MIME part inside the message body. The part's headers typically describe:

- **`Content-Type`:** the data type, e.g. `application/pdf`, `image/png`, or `text/csv`.
- **`Content-Transfer-Encoding`:** how bytes are represented for transport, typically `base64` for binary data.
- **`Content-Disposition`:** hints whether the content is an attachment or inline, and can include the filename via the `filename` parameter.
- **`Content-ID`:** identifies the MIME part when referenced in HTML, commonly used for inline images.

Abbreviated example:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQK...
~~~

The name `invoice.pdf` resides in the **MIME part header**, while the PDF content resides in the transfer-encoded body. These are two distinct regions of data.

Some legacy messages or compatibility systems may also include a `name` parameter in `Content-Type`:

~~~text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
~~~

`name` is a common historical representation; `filename` in `Content-Disposition` is what is typically used to indicate the downloaded filename. Do not rely on a single header alone to guess how every email client renders attachments.

### 1.1. Why are Unicode filenames harder than ASCII names?

With an ASCII-only name:

~~~text
filename="invoice-2026.pdf"
~~~

Characters such as unaccented Latin letters, digits, hyphens, and dots can be represented directly in standard MIME header syntax. However, a name like:

~~~text
filename="Báo cáo tháng 11.pdf"
~~~

contains non-ASCII characters. Older generations of email clients and mail libraries did not agree on how to represent these characters in header parameters. Consequently, MIME standards provide extension mechanisms to carry the charset and bytes of Unicode values.

## 2. Distinguishing charset, transfer encoding, and filename encoding

These three concepts are often lumped together as "encoding", yet they solve different problems:

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Charset** | Which character encoding converts a text string into bytes? | UTF-8 |
| **Content-Transfer-Encoding** | How are the MIME part bytes represented for transmission? | base64, quoted-printable, 7bit |
| **Filename parameter encoding** | How is a Unicode filename represented in a MIME header? | RFC 2231 extended parameter |

Example with a CSV file:

- **Filename:** `Báo cáo tháng 11.csv`, which must be properly represented in the filename parameter.
- **Content bytes:** the CSV string converted to bytes using UTF-8.
- **Transfer encoding:** the CSV bytes may be sent as base64 in the MIME part.
- **Content-Type:** `text/csv; charset=UTF-8` describes the content as CSV along with the charset of the text.

If you only fix filename encoding while the CSV bytes were generated with a different charset, the recipient will still open the file and see garbled Vietnamese text. Conversely, completely valid UTF-8 CSV content with a broken filename header can still leave the filename corrupted.

## 3. RFC 2231: the standard way to represent Unicode parameters

**RFC 2231** extends MIME parameter syntax to represent values with a charset and language. For Unicode filenames, the common form is an asterisk **extended parameter**:

~~~text
filename*=UTF-8''B%C3%A1o%20c%C3%A1o%20th%C3%A1ng%2011.pdf
~~~

Structure:

~~~text
filename*=charset'language'percent-encoded-octets
~~~

- `filename*`: the `*` indicates this is an extended parameter.
- `UTF-8`: the charset used to decode the bytes.
- The segment between the two single quotes is the language tag; it can be left empty.
- The trailing part consists of the filename's percent-encoded octets.

When decoded as UTF-8, the example above resolves back to:

~~~text
Báo cáo tháng 11.pdf
~~~

In this example, the character `á` is represented as UTF-8 bytes and then `%C3%A1`; a space becomes `%20`. This is a **MIME parameter** encoding mechanism, not a requirement for the application to turn the filename into a URL itself.

### 3.1. Fallback for older email clients

A message may contain both an ASCII fallback name and an extended value:

~~~text
Content-Disposition: attachment;
 filename="report-2026.pdf";
 filename*=UTF-8''B%C3%A1o%20c%C3%A1o%202026.pdf
~~~

Email clients supporting RFC 2231 can use `filename*` to obtain the Unicode name. Older clients may ignore the extended parameter and use the ASCII fallback `filename`. Combining both improves compatibility, though **it does not guarantee every client displays the same name**.

If the ASCII fallback differs from the Unicode name, users on older clients will see the fallback name. Therefore, pick a short, recognizable fallback with the right extension, such as `bao-cao-2026.pdf`.

### 3.2. Long names and parameter continuations

Email headers have line-length limits. RFC 2231 allows splitting a long value into parameter continuation segments:

~~~text
filename*0*=UTF-8''Bao%20cao%20thang%2011%20-
filename*1*=%20khach%20hang%20Nguyen%20An.pdf
~~~

This example only illustrates the continuation concept; when generating real MIME, the library may choose different line folding and parameter splitting. Do not manually slice Unicode strings into character chunks and concatenate headers yourself, as you may split mid-UTF-8 byte sequence or break continuation syntax.

**Let Jakarta Mail handle header encoding and folding** rather than manually building `filename*0*` and `filename*1*` strings.

## 4. RFC 2047 encoded-word vs. RFC 2231

Another format you might see in headers is:

~~~text
=?UTF-8?B?QsOhbyBjw6FvLnBkZg==?=
~~~

This is **encoded-word** syntax per RFC 2047. It is designed for header fields containing non-ASCII text words/phrases, such as `Subject` or the sender display name.

For MIME parameters like `filename`, the standard mechanism for extended parameters is **RFC 2231**. Some legacy software uses RFC 2047 encoded-word inside the filename value as a proprietary compatibility workaround. Therefore:

- Do not assume encoded-word inside `filename` is standard across all clients.
- Do not call `MimeUtility.encodeText(...)` to encode a filename and assume it is equivalent to RFC 2231.
- Do not manually inject `=?UTF-8?B?...?=` strings into the filename unless you have verified the exact compatibility requirements of target clients.
- Let Jakarta Mail/Spring Mail generate parameters according to the supported implementation and configuration.

### 4.1. When is `MimeUtility.encodeText` used?

Example:

~~~java
import jakarta.mail.internet.MimeUtility;

String encodedSubject =
        MimeUtility.encodeText("Báo cáo tháng 11", "UTF-8", null);
~~~

`MimeUtility.encodeText` is useful when encoding **header text** under MIME encoded-word rules, such as Subject or display names. When using `MimeMessageHelper.setSubject(...)` or display-name overloads, the library can encode headers appropriately on its own; manually calling `encodeText` beforehand is normally unnecessary.

A filename is a MIME parameter with its own rules. Never pass the output of `encodeText` into `addAttachment(...)`; the attachment API expects the **original display name**, not an already-encoded string.

## 5. Setting Unicode filenames with MimeMessageHelper

With Spring Mail, the standard approach is `MimeMessageHelper.addAttachment(...)`:

~~~java
import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendReport(
        JavaMailSender sender,
        byte[] pdfBytes,
        String recipient) throws MessagingException {

    MimeMessage mime = sender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());

    helper.setFrom("reports@example.com");
    helper.setTo(recipient);
    helper.setSubject("Monthly report");
    helper.setText("The report is attached to this email.");

    String fileName = "Báo cáo tháng 11 – Nguyễn An.pdf";
    helper.addAttachment(
            fileName,
            new ByteArrayResource(pdfBytes),
            "application/pdf"
    );

    sender.send(mime);
}
~~~

Points to note:

1. `fileName` is the original Unicode name as a `String`.
2. `ByteArrayResource` supplies the PDF file bytes; it is not responsible for encoding the filename.
3. `application/pdf` is the attachment's content type.
4. `MimeMessageHelper` builds the MIME part and sets the attachment filename.
5. `JavaMailSender` sends the entire `MimeMessage` via the configured transport.

**Do not** do the following:

~~~java
// Do not manually Base64/URL-encode the filename before passing to the helper.
String fileName = Base64.getEncoder()
        .encodeToString("Báo cáo tháng 11.pdf".getBytes(StandardCharsets.UTF_8));

helper.addAttachment(fileName, new ByteArrayResource(pdfBytes));
~~~

If you encode the filename yourself, recipients may see a Base64 string instead of the intended name; if the library encodes it again, the result may be double-encoded.

### 5.1. Spring's filename encoding setting

Some versions of Spring Framework provide `MimeMessageHelper.setEncodeFilenames(boolean)` to support filename encoding for email clients with compatibility requirements. When this API is available in your project's version:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());

helper.setEncodeFilenames(true);
helper.addAttachment(
        "Báo cáo tháng 11.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

Consult the API documentation for your exact Spring version before applying it. Depending on the version and Jakarta Mail provider, this option may use MIME encoded-word to improve compatibility with certain legacy clients; **do not assume it is identical to RFC 2231 extended parameters**. Inspect the raw MIME and test with real clients if you need to decide whether to enable or disable it.

If your Spring version does not offer this method, do not immediately patch raw headers in the service. First check your Jakarta Mail provider's RFC 2231 support and supported mail MIME properties.

### 5.2. Using FileSystemResource or ClassPathResource

When the attachment already exists as a file:

~~~java
import org.springframework.core.io.FileSystemResource;

FileSystemResource resource =
        new FileSystemResource("/srv/reports/report.pdf");

helper.addAttachment(
        "Báo cáo tháng 11.pdf",
        resource,
        "application/pdf"
);
~~~

The display name can differ from the physical filename on the server. For instance, the internal path may be `/srv/reports/report-2026-11.pdf`, while the name the recipient sees is `Báo cáo tháng 11.pdf`. Separating the two avoids exposing directory structures or internal storage names.

For resources on the classpath:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.addAttachment(
        "Hướng dẫn sử dụng.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);
~~~

The resource must exist in the running artifact. Do not rely on the process's relative working directory, as the current directory can vary between local, container, and production environments.

### 5.3. InputStreamSource must be able to open an appropriate stream

`MimeMessageHelper` has overloads accepting `InputStreamSource`. When sending, the library may need to read the resource while constructing MIME content; therefore, the source should be capable of supplying a fresh stream when requested.

Often convenient options:

- `ByteArrayResource` for bytes already in memory of suitable size.
- `FileSystemResource` for existing files on the filesystem.
- `ClassPathResource` for files packaged on the classpath.

Be cautious with `InputStreamResource` or any **read-once** source. If the stream is consumed before the mail transport reads it, the attachment may be empty or fail. For large files, avoid loading the entire file into a byte array if size could cause memory pressure; pick a resource/stream with a clear lifecycle.

## 6. Controlling MIME properties at the Jakarta Mail level

When lower-level control is needed, the application can create a `MimeBodyPart` and set the filename via the Jakarta Mail API. Conceptual example:

~~~java
import jakarta.mail.Part;
import jakarta.mail.internet.MimeBodyPart;

MimeBodyPart attachment = new MimeBodyPart();
attachment.setDataHandler(dataHandlerForPdf);
attachment.setDisposition(Part.ATTACHMENT);
attachment.setFileName("Báo cáo tháng 11.pdf");
multipart.addBodyPart(attachment);
~~~

`setFileName(...)` accepts the filename as a string; the specific MIME header generation is handled by Jakarta Mail/the provider and its configuration. Do not concatenate headers yourself:

~~~java
attachment.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + userProvidedName + "\""
);
~~~

String concatenation like this risks syntax errors, encoding bugs, invalid line folding, and header injection if the name comes from untrusted input. High-level APIs already provide parameter/header handling; only manipulate headers manually when a specific protocol requirement exists and you fully understand the compatibility impact.

### 6.1. MIME properties related to filenames

A Jakarta Mail implementation may support configuration properties for parameters and filenames. Some commonly cited properties:

| Property | General purpose | Notes |
| --- | --- | --- |
| `mail.mime.encodeparameters` | Controls RFC 2231 extended MIME parameter encoding in supporting implementations | Check defaults and provider documentation |
| `mail.mime.decodeparameters` | Controls decoding of extended MIME parameters | Useful when reading messages; not every send-only app needs to configure it |
| `mail.mime.encodefilename` | Compatibility mechanism using encoded-word for filenames in some implementations | Not synonymous with RFC 2231 |
| `mail.mime.decodefilename` | Decodes filenames using the encoded-word compatibility mechanism | Enable only when needed and impact is understood |

Property names, defaults, and configuration scope may depend on the Jakarta Mail/provider version. Before changing anything, check the documentation for the actual implementation in your dependency graph. Do not copy a batch of properties just because you saw an example online; a legacy compatibility flag can alter how every attachment is sent or read across the application.

If you need to configure properties via Spring Boot, they are typically passed to the mail session/provider under `spring.mail.properties`, for example:

~~~yaml
spring:
  mail:
    properties:
      "[mail.mime.encodeparameters]": true
~~~

This is merely an example for implementations supporting that property. **Do not toggle it globally without testing against your provider and target email clients**. Global MIME settings can affect all messages sent within the same session.

## 7. Encoding of attachment content

A Unicode filename can be completely correct while the content is still garbled if the bytes were created with the wrong charset.

### 7.1. PDF, image, or ZIP attachments

PDF, PNG, JPEG, ZIP, and other binary files should be passed as **raw bytes**. Do not convert binary bytes into a `String` using UTF-8 and do not call `getBytes()` on binary data:

~~~java
byte[] pdfBytes = Files.readAllBytes(pdfPath);
helper.addAttachment(
        "Hóa đơn tháng 11.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

During MIME construction, the library selects the appropriate transfer encoding (usually base64 for binary attachments). There is no need to manually Base64-encode PDF bytes before wrapping in `ByteArrayResource`.

### 7.2. TXT/CSV attachments with Vietnamese text

For text data, convert the string to bytes using the chosen charset:

~~~java
String csvText = """
    Mã đơn,Tên khách hàng,Tổng tiền
    A123,Nguyễn An,220000
    """;

byte[] csvBytes = csvText.getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
        "Báo cáo khách hàng.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

Two things happen here:

- The name `Báo cáo khách hàng.csv` must be represented properly in the MIME filename parameter.
- The CSV content is encoded as **UTF-8 bytes**, and `Content-Type` declares the matching charset.

Do not use `fileName.getBytes(UTF_8)` as a substitute for the filename; the filename is a header parameter, not body text. Also do not assume `Content-Transfer-Encoding: base64` automatically makes CSV content UTF-8: Base64 only encodes raw bytes and does not determine their character encoding.

### 7.3. Excel, Word, and Office formats

For `.xlsx`, `.docx`, and modern Office formats, the data is usually a binary ZIP/XML package. Use the bytes produced by the file-generation library while declaring the appropriate MIME type:

| File type | Commonly used Content-Type |
| --- | --- |
| PDF | `application/pdf` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| ZIP | `application/zip` |
| CSV | `text/csv; charset=UTF-8` when content is UTF-8 |
| TXT UTF-8 | `text/plain; charset=UTF-8` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |

Content-Type should be determined from the actual data type or an application-allowlisted set of formats, not blindly trusting user-entered extensions. Declaring the right MIME type helps email clients suggest how to open the file, though **it does not validate that the file content is safe or well-formed**.

## 8. Normalizing and sanitizing Unicode filenames

A filename passed from a user or external system may contain:

- slashes and path-like sequences;
- control characters or line breaks;
- leading or trailing whitespace;
- consecutive dots or an empty name;
- Unicode characters in different composition forms;
- an extension that does not match the actual content;
- an overly long string that renders poorly or exceeds provider limits.

Before using a name as the **display name in an email**, the application should apply a policy:

1. Extract the **basename** if the input could be a path; never let server directory paths appear in the email.
2. Strip control characters, CR/LF, NUL, and characters disallowed by product rules.
3. Limit length by code points or display rules without splitting inside a surrogate pair.
4. Preserve required language characters; you can normalize Unicode to NFC for a consistent representation.
5. Choose the extension from the verified file type rather than trusting the client-sent name.
6. If the sanitized name is empty or invalid, generate a safe fallback name with an ID.

### 8.1. Unicode normalization example

Unicode can represent an accented letter as a single precomposed code point or as a base letter plus a combining mark. Two strings may look identical yet have different underlying bytes.

Java supports normalization via `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(
        originalFileName,
        Normalizer.Form.NFC
);
~~~

NFC helps produce a composed canonical form where possible. It does **not** automatically remove path traversal, control characters, empty names, or overly long strings; you still need validation/sanitization according to application rules.

### 8.2. Never use the filename as a storage path

Suppose a user uploads:

~~~text
../../private/customer-data.pdf
~~~

This name must not be concatenated directly into a filesystem path. When storing the file, the server should generate a safe internal name/key (such as a UUID or dedicated object key), while keeping the original name only as sanitized metadata to display to recipients.

When sending the email:

~~~java
String displayName = "Hồ sơ khách hàng.pdf";
helper.addAttachment(
        displayName,
        new FileSystemResource(trustedStoredFile),
        "application/pdf"
);
~~~

`trustedStoredFile` must be a system-identified and controlled resource. The display name must never be used to select an arbitrary file on the server.

### 8.3. Preventing header injection

Never allow filenames containing CR/LF or control characters to inject additional headers:

~~~text
report.pdf"\r\nBcc: victim@example.net
~~~

The mail library may check some cases, but the application must still validate inputs. Use the setters on `MimeMessageHelper`/Jakarta Mail instead of manually building `Content-Disposition`. Never allow users to pass raw MIME headers or raw filename parameters.

## 9. Complete example: sending a PDF with a Vietnamese filename

A service may receive generated PDF bytes and send them to a recipient:

~~~java
package com.example.mail.application;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceAttachmentMailService {
    private final JavaMailSender sender;

    public InvoiceAttachmentMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(
            String recipient,
            byte[] pdfBytes,
            String invoiceNumber) throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, StandardCharsets.UTF_8.name());

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Invoice " + invoiceNumber);
        helper.setText(
                "Hello,\n\nYour invoice is attached to this email.\n"
        );

        String attachmentName =
                "Hóa đơn " + invoiceNumber + " – Nguyễn An.pdf";
        helper.addAttachment(
                attachmentName,
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        sender.send(mime);
    }
}
~~~

This example assumes `pdfBytes` was generated from valid data, `recipient` has been validated per business rules, and `invoiceNumber` contains no control characters. If the filename is derived from user input, run it through normalization/validation before passing it to the helper.

### 9.1. UTF-8 CSV example

~~~java
String csv = """
        Mã đơn,Tên khách hàng,Tổng tiền
        A123,Nguyễn An,220000
        A124,Trần Bình,1250000
        """;

byte[] csvBytes = csv.getBytes(StandardCharsets.UTF_8);
String csvName = "Báo cáo khách hàng tháng 11.csv";

helper.addAttachment(
        csvName,
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

If users open the CSV in an older spreadsheet program, how that software guesses the charset may vary. UTF-8 is the standard choice; if you need to support a specific application, check its BOM or import requirements, rather than blindly adding a BOM to all file types.

## 10. Multiple attachments with multiple Unicode names

`MimeMessageHelper` allows calling `addAttachment` multiple times:

~~~java
helper.addAttachment(
        "Hóa đơn A123.pdf",
        new ByteArrayResource(invoicePdf),
        "application/pdf"
);

helper.addAttachment(
        "Chi tiết đơn hàng – Nguyễn An.xlsx",
        new ByteArrayResource(orderWorkbook),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
);

helper.addAttachment(
        "Điều khoản dịch vụ.pdf",
        new ClassPathResource("mail/terms.pdf"),
        "application/pdf"
);
~~~

Each part has its own filename, Content-Type, and data. One attachment's Unicode filename does not change the charset of another attachment. When an email has multiple files:

- limit the count and total size;
- clearly define the order/meaning of each file;
- avoid duplicate names that confuse recipients;
- avoid accidentally adding an internal or unexpected temporary file;
- verify each data source remains available during sending/retries.

## 11. Inspecting raw MIME to diagnose encoding issues

When an email client displays a filename incorrectly, do not immediately assume the file bytes are corrupted. Inspect the **raw source/original message** or save the message as `.eml` in a test environment.

An example part might look like:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment;
 filename="report-2026.pdf";
 filename*=UTF-8''B%C3%A1o%20c%C3%A1o%202026.pdf

JVBERi0xLjQK...
~~~

Inspection steps:

1. **Locate the right MIME part** for the attachment, not just the outermost message headers.
2. **Read `Content-Disposition`:** does it have `filename`, `filename*`, or continuations?
3. **Decode the parameter per the standard:** if `filename*` is present, read the charset and percent-encoded bytes per RFC 2231.
4. **Check Content-Type and transfer encoding:** verify how the file content is described.
5. **Decode the attachment bytes and compare with the original file:** for PDFs check signatures and checksums; for CSVs verify UTF-8.
6. **Test in target email clients:** different clients may pick fallbacks or parse parameters differently.

### 11.1. Classifying symptoms

| Symptom | What to investigate |
| --- | --- |
| PDF content opens fine, but filename is wrong | Filename parameter encoding or how the client decodes it |
| Filename is fine, but CSV has garbled accents | Charset of the CSV bytes and declared `charset` |
| Name renders literally as `=?UTF-8?B?...?=` | Client does not decode encoded-word in filenames, or inappropriate encoding mode |
| Name renders as `BÃ¡o cÃ¡o.pdf` | UTF-8 bytes interpreted with a different charset, or filename encoded wrongly |
| Name is truncated at spaces/special chars | Quoting, parameter folding, or invalid MIME header |
| One client displays it right, another wrong | Differences in RFC 2231/2047 support and fallbacks |
| Attachment has size 0 | One-shot `InputStreamSource`, consumed stream, missing file, or source error |
| PDF/Office file fails to open | Bytes altered, manually Base64-encoded twice, or wrong Content-Type |

### 11.2. Do not look only at Java logs

Logs show what name the service passed to `addAttachment(...)`, but do not prove how the final header was encoded. To diagnose, inspect the **serialized MIME** after the library constructs the message. You can save a test copy to `.eml` in a local environment, while protecting it because the file may contain real addresses, content, and attachments.

## 12. Testing Unicode filenames

A useful test checks both **the input value** and **the generated header**.

### 12.1. Verifying the helper is called with the original name

Unit tests can mock or capture the attachment-building logic to confirm the service passes the original Unicode name rather than a Base64 or URL-encoded string. This tests at the application layer.

### 12.2. Integration testing with a mock SMTP server

You can use Mailpit or GreenMail to:

1. Run an SMTP test server that does not send externally.
2. Send an email with the filename `Báo cáo tháng 11 – Nguyễn An.pdf`.
3. Fetch the raw MIME or download the `.eml` from the test server.
4. Inspect `Content-Disposition` for the filename parameter per the chosen standard/provider.
5. Decode the filename using the corresponding mechanism and compare against the expected name.
6. Extract the attachment bytes and compare checksums against the original file.
7. View it in the email clients your product needs to support.

Do not write brittle tests asserting every implementation must emit the exact same byte-for-byte header string. Headers may be folded, parameters reordered, or encoded in other valid ways. Test **the decoded semantics**, alongside targeted raw-header checks where compatibility requires.

### 12.3. Sample test name suite

| Category | Example | What to observe |
| --- | --- | --- |
| ASCII | `invoice-2026.pdf` | Baseline case |
| Vietnamese with diacritics | `Báo cáo tháng 11.pdf` | UTF-8 and RFC 2231 |
| Spaces and en-dash | `Hóa đơn – Nguyễn An.pdf` | Parameter quoting/encoding |
| CJK characters | `契約書_注文123.pdf` | Non-Latin Unicode |
| Combining characters | Name with accents in decomposed form | NFC normalization and rendering |
| Long name | Multi-word report name | Folding/continuation |
| Special characters | Quotes, semicolons | Quoting and sanitization |
| Empty/malicious names | `../../secret.pdf`, CR/LF | Validation and basename extraction |

## 13. Size, limits, and compatibility

Filename encoding does not noticeably change the file's content bytes, though longer headers may require folding or continuations. Meanwhile, **Base64 enlarges the attachment** by roughly one-third over the original bytes, before accounting for headers and multipart boundaries.

For example, a 9 MB PDF file can exceed 12 MB after Base64 encoding. Providers may enforce size limits on the whole email, not just individual files. Therefore:

- check total size before sending;
- avoid reading many large files onto the heap at the same time;
- pick a resource capable of opening streams appropriately;
- if the file is too large, consider sending an authenticated, time-limited download link instead of an attachment;
- never place secrets in download URLs or filenames.

Compatibility must also be considered:

- **Modern clients** usually support RFC 2231 extended parameters.
- **Older clients** may understand encoded-word or only ASCII fallback names.
- **Providers/gateways** may rewrite, filter, or normalize headers.
- **Recipients' file management systems** may apply their own naming rules, such as replacing invalid characters.

No single encoding option guarantees every system renders Unicode names identically. Choose standards-compliant representation, provide ASCII fallbacks when needed, and test with real clients.

## 14. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Manually Base64-encoding filename before `addAttachment` | Recipients see an encoded string instead of the name | Pass the original Unicode name |
| Using `URLEncoder` on filenames | Spaces become `+`, wrong syntax for MIME | Let Jakarta Mail handle RFC 2231 |
| Calling `MimeUtility.encodeText` on filename then passing to helper | May produce improper encoded-word or double-encode | Distinguish RFC 2047 from RFC 2231 |
| Thinking UTF-8 helper charset fixes PDF bytes | Mixes encoding metadata with binary data | Keep file bytes intact; charset applies only to text content |
| Fixing filename without setting charset for CSV | Filename is right, but CSV content has garbled accents | Produce UTF-8 bytes and declare `text/csv; charset |
| Manually concatenating `Content-Disposition` from input | Syntax errors or header injection | Use `addAttachment` / `setFileName` |
| Testing on only one email client | Compatibility bugs may be missed | Test key clients and inspect raw MIME |
| Holding a read-once `InputStream` | Attachment may be empty or fail | Use a resource capable of opening streams properly |
| Using upload name as server path | Path traversal or internal layout leak | Store with a safe key, keep display name separate |
| Trusting user-supplied file extension | MIME type and actual file mismatch | Validate file type, restrict formats and content |
| Treating Base64 as security encryption | Bytes can be publicly decoded | Use proper data protection; Base64 is only transfer encoding |

## 15. Design checklist in a Spring Mail module

When adding an attachment with a Unicode filename, determine:

1. **Display name:** original name or application-generated? Is it normalized and length-limited?
2. **File source:** bytes, filesystem, classpath, or object storage? Will the resource still exist when a worker sends it?
3. **Content type:** is the MIME type determined from trusted content or only from the extension?
4. **Text content:** if CSV/TXT, what is the byte charset and does `Content-Type` declare it accurately?
5. **Filename encoding:** how does your Spring/Jakarta Mail version support RFC 2231? Is a fallback needed for older clients?
6. **Security:** does the name contain CR/LF, path separators, or sensitive data? Has the file been checked/scanned per policy?
7. **Size:** does the total email exceed provider limits or cause memory pressure?
8. **Testing:** have raw MIME, decoded filename, attachment bytes, and target clients been verified?

## 16. End-to-end scenario: sending a Vietnamese report via Spring Mail

An application generates a monthly report for customer Nguyễn An. The PDF file is stored internally under the name:

~~~text
report-2026-11-8842.pdf
~~~

The name intended for the recipient to see:

~~~text
Báo cáo tháng 11 – Nguyễn An.pdf
~~~

Appropriate flow:

1. **Report service** generates the PDF and stores the bytes or resource in a controlled location.
2. **Application service** determines the display name, normalizes Unicode, and checks control characters and extensions.
3. **Mail service** creates `MimeMessage` and `MimeMessageHelper` with UTF-8.
4. Calls `addAttachment(displayName, resource, "application/pdf")`, without manually encoding the filename.
5. **Jakarta Mail/provider** constructs MIME headers and transfer encoding for the data.
6. **SMTP provider** accepts the message; the recipient's email client parses the filename parameter.
7. If the display name renders wrongly, inspect raw `Content-Disposition` and the RFC 2231/compatibility mechanism before changing configuration.

This model clearly separates:

~~~text
Storage key:     report-2026-11-8842.pdf
Display name:    Báo cáo tháng 11 – Nguyễn An.pdf
Content-Type:    application/pdf
Content bytes:   original PDF bytes
Transfer coding: chosen by MIME implementation
Filename coding: MIME parameter encoding handled by mail library
~~~

The display name does not dictate which file is read; the stored file does not need a Unicode name; the content bytes are not mutated to "fix the name"; and the mail-sending code does not manually write raw headers. When these responsibilities are separated, emails with Unicode attachment filenames become much easier to control and keep compatible.

### References

- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** MIME structure, content types, and transfer encoding.
- **RFC 2231 — MIME Parameter Value and Encoded Word Extensions:** extended parameters, charsets, languages, and continuations.
- **RFC 2047 — MIME Message Header Extensions:** encoded-word in text header fields.
- **Spring Framework API — `MimeMessageHelper`:** `addAttachment`, `setEncodeFilenames` (when available in your version), and MIME message construction.
- **Jakarta Mail API — `MimeBodyPart` / `MimeUtility`:** setting filenames, header handling, and encoding mechanisms.
- **Spring Boot Reference — Sending Email:** configuring `JavaMailSender` and `spring.mail.*`.
