# Attaching In-Memory Generated Data

In **Spring Framework Mail**, an email can attach content generated directly during business processing: PDF reports, CSV tables, invoices, JSON files, chart images, or ZIP archives. That data does not always need to be written to disk as a file. The application can generate the content into a **byte array (`byte[]`) or an in-memory buffer**, and then pass the data directly into the email via `MimeMessageHelper`.

This approach is useful when reports are generated individually per recipient, when data only needs to exist while sending, or when the application runs in a container without a suitable temporary directory. However, in-memory attachments require attention to **stream re-readability, MIME type, filename, data size, and RAM consumption**. A successfully sent email can still carry an empty or malformed file if the data-generation and packaging steps are not designed properly.

This lesson covers how to create attachments from byte arrays, `ByteArrayOutputStream`, `ByteArrayResource`, and `InputStreamSource`, how to use them in Spring Mail, how to control size and security, along with CSV/PDF examples and MIME content inspection.

## 1. What is in-memory generated data?

Typically, a file attachment workflow may consist of:

```text
Business data
       |
       v
Report generator / exporter
       |
       v
ByteArrayOutputStream or byte[]
       |
       v
ByteArrayResource / InputStreamSource
       |
       v
MimeMessageHelper.addAttachment(...)
       |
       v
JavaMailSender.send(...)
       |
       v
SMTP server
```

**In-memory generated data** means the application builds the file content in RAM and supplies those bytes directly to the email library. There is no need to create a path like `/tmp/report.pdf` before attaching.

Examples:
- Generating a CSV from a transaction list and sending it to a manager.
- Creating a PDF invoice from order data and sending it after payment.
- Exporting JSON or XML as interchange data for another system.
- Rendering a chart as PNG and attaching it to a periodic report.
- Compressing several documents into a ZIP to send at once.

The file data is still represented as bytes in memory. When sending the email, Jakarta Mail reads the data, creates the MIME part, and encodes it appropriately for SMTP transport.

## 2. Essential Spring Mail APIs

### 2.1. JavaMailSender and MimeMessage

`JavaMailSender` creates and sends a `MimeMessage`. To send attachments, you must use a MIME message rather than `SimpleMailMessage`:

```java
MimeMessage message = mailSender.createMimeMessage();
```

`SimpleMailMessage` is for simple plain-text emails. It does not provide the MIME multipart structure required to carry attached files.

### 2.2. MimeMessageHelper

`MimeMessageHelper` is a Spring utility for setting headers and building MIME parts. Common constructor:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");
```

Parameters:
- `message`: the email created from `JavaMailSender`.
- `true`: enables multipart mode, allowing both a body and attachments.
- `"UTF-8"`: encoding for applicable text content.

After creating the helper, you can call `setFrom`, `setTo`, `setSubject`, `setText`, and `addAttachment`.

### 2.3. ByteArrayResource

`ByteArrayResource` is a Spring Resource wrapping a byte array:

```java
byte[] fileBytes = ...;
ByteArrayResource resource = new ByteArrayResource(fileBytes);
```

A useful property is that each call to `getInputStream()` can create a new `ByteArrayInputStream` from the same byte array. This is the **repeatable** read property, fitting MIME preparation and transmission which may need to read data from the source.

When using `MimeMessageHelper.addAttachment(...)`, pass an explicit filename and MIME type:

```java
helper.addAttachment(
    "report.csv",
    new ByteArrayResource(fileBytes),
    "text/csv; charset=UTF-8"
);
```

The filename is passed separately because `ByteArrayResource` does not necessarily provide a meaningful filename.

### 2.4. InputStreamSource

`InputStreamSource` is Spring's abstraction for supplying an `InputStream`:

```java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

InputStreamSource source =
    () -> new ByteArrayInputStream(fileBytes);
```

Important rule: **each time `getInputStream()` is called, the source should return a fresh stream readable from the start**. Do not hold an exhausted stream and return the same object every time. If the library needs to read the data again, the old stream will be at EOF or closed.

`ByteArrayResource` already implements `InputStreamSource`, so for existing byte arrays there is usually no need to write a custom source class.

## 3. Workflow for generating and attaching in-memory data

Recommended steps:

1. Retrieve business data and verify recipient authorization.
2. Generate the file into a byte array or a data source capable of opening fresh streams.
3. Confirm the data is non-empty and its size is within limits.
4. Create `MimeMessage` and `MimeMessageHelper` in multipart mode.
5. Set sender, recipient, subject, and message body.
6. Call `addAttachment(filename, resource, contentType)`.
7. Send via `JavaMailSender`.
8. Record the send result and business key without logging sensitive file contents.

```text
generate bytes
     |
     v
validate size / non-empty / format
     |
     v
create MimeMessage + multipart helper
     |
     v
set headers and body
     |
     v
addAttachment(...)
     |
     v
send(...)
```

Separating data generation from sending makes it easier to validate the file before packaging and handle errors per stage.

## 4. Basic example: attaching an existing byte[]

Example when another component has already generated the file data:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class AttachmentMailService {

    private final JavaMailSender mailSender;

    public AttachmentMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendFile(
            String recipient,
            byte[] fileBytes) throws MessagingException {

        if (fileBytes == null || fileBytes.length == 0) {
            throw new IllegalArgumentException(
                "File data must not be empty"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Report file");
        helper.setText(
            "Hello,\nThe report file is attached to this email."
        );

        helper.addAttachment(
            "report.pdf",
            new ByteArrayResource(fileBytes),
            "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Explanation:
- `fileBytes` contains the generated file's bytes.
- Checking `null` and length prevents sending an unintentionally empty attachment.
- `new MimeMessageHelper(message, true, "UTF-8")` enables multipart.
- `addAttachment` accepts the display name, byte source, and content type.
- `application/pdf` describes PDF content; the filename extension should match the actual format.
- `mailSender.send(message)` sends the MIME message via configured SMTP.

This example assumes `fileBytes` is actually a valid PDF. Setting the content type to `application/pdf` does not turn arbitrary data into a PDF; **the format must be generated properly before attaching**.

## 5. Generating CSV in memory and sending

CSV is often well suited for transaction reports or data meant to be opened in spreadsheets. You can build the content with `StringBuilder`, convert it to a UTF-8 byte array, and use `ByteArrayResource`.

### 5.1. Creating the CSV

Example of a data row:

```java
public record OrderRow(
    String orderCode,
    String customerName,
    long quantity,
    String amount
) {}
```

A basic CSV escaping helper wraps each field in quotes and doubles any internal quotes:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

public class CsvExporter {

    public byte[] export(List<OrderRow> rows) {
        StringBuilder csv = new StringBuilder();
        csv.append("Order,Customer,Quantity,Amount\n");

        for (OrderRow row : rows) {
            csv.append(csvCell(row.orderCode())).append(',');
            csv.append(csvCell(row.customerName())).append(',');
            csv.append(csvCell(Long.toString(row.quantity()))).append(',');
            csv.append(csvCell(row.amount())).append('\n');
        }

        return csv.toString().getBytes(StandardCharsets.UTF_8);
    }

    private static String csvCell(String value) {
        String safe = value == null ? "" : value;
        return "\"" + safe.replace("\"", "\"\"") + "\"";
    }
}
```

This handles structural CSV escaping for ordinary text data. For data that may be opened in Excel or similar spreadsheets, also consider **CSV formula injection**: user-controlled values starting with `=`, `+`, `-`, or `@` may be interpreted as formulas by spreadsheets. If exporting untrusted data, apply a dedicated sanitization policy for text cells without corrupting valid numeric columns. Standard comma/quote CSV escaping does not by itself prevent spreadsheets from executing formulas.

For CSVs aimed at Vietnamese users, check encoding and how target spreadsheet applications detect UTF-8. A UTF-8 BOM may be needed depending on the target software, though do not add a BOM mechanically if downstream systems expect the first byte to be the first character of the header.

### 5.2. Sending the CSV

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.List;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderReportMailService {

    private final JavaMailSender mailSender;
    private final CsvExporter csvExporter;

    public OrderReportMailService(
            JavaMailSender mailSender,
            CsvExporter csvExporter) {
        this.mailSender = mailSender;
        this.csvExporter = csvExporter;
    }

    public void sendReport(
            String recipient,
            List<OrderRow> rows) throws MessagingException {

        byte[] csvBytes = csvExporter.export(rows);

        if (csvBytes.length == 0) {
            throw new IllegalStateException("Generated CSV is empty");
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order report");
        helper.setText(
            "The order report is attached as a CSV."
        );

        helper.addAttachment(
            "order-report.csv",
            new ByteArrayResource(csvBytes),
            "text/csv; charset=UTF-8"
        );

        mailSender.send(message);
    }
}
```

The CSV is created entirely in RAM. There is no need to write `order-report.csv` to a temp directory only to read it back afterward. However, if a report has millions of rows, building both the CSV string and byte array can consume significant memory; see the size limits section.

## 6. Generating a PDF with ByteArrayOutputStream

Many PDF generation libraries expose an API that writes to an `OutputStream`. In that case, you can pass a `ByteArrayOutputStream` to keep the result in memory.

```text
PDF generator
     |
     | write(OutputStream)
     v
ByteArrayOutputStream
     |
     | toByteArray()
     v
byte[]
     |
     v
ByteArrayResource
     |
     v
MimeMessageHelper.addAttachment(...)
```

Suppose the application has a `PdfReportGenerator` component that accepts data and writes a valid PDF to an output stream:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;

public class PdfReportService {

    private final PdfReportGenerator generator;

    public PdfReportService(PdfReportGenerator generator) {
        this.generator = generator;
    }

    public byte[] createReport(List<OrderRow> rows) throws IOException {
        try (ByteArrayOutputStream output =
                 new ByteArrayOutputStream()) {

            generator.write(rows, output);
            return output.toByteArray();
        }
    }
}
```

`PdfReportGenerator` is an illustrative application-defined abstraction; real PDF libraries have their own APIs. `ByteArrayOutputStream` does not require closing to release OS resources, though try-with-resources still clarifies lifecycle. `toByteArray()` returns a byte copy of the written data.

Then attach it:

```java
byte[] pdfBytes = pdfReportService.createReport(rows);

helper.addAttachment(
    "order-report.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

If the PDF library can output directly to a byte array, use that result directly. If it only writes to a stream, `ByteArrayOutputStream` is a simple bridge when the size fits in RAM.

## 7. Complete example: generating a PDF and sending with an HTML email

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.util.List;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class PdfAttachmentMailService {

    private final JavaMailSender mailSender;
    private final PdfReportService pdfReportService;

    public PdfAttachmentMailService(
            JavaMailSender mailSender,
            PdfReportService pdfReportService) {
        this.mailSender = mailSender;
        this.pdfReportService = pdfReportService;
    }

    public void sendMonthlyReport(
            String recipient,
            List<OrderRow> rows)
            throws IOException, MessagingException {

        // 1. Generate the file content in memory.
        byte[] pdfBytes = pdfReportService.createReport(rows);

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalStateException(
                "Failed to generate PDF content"
            );
        }

        // 2. Create a multipart MIME message.
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED,
            "UTF-8"
        );

        // 3. Set email metadata and body.
        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Monthly report");
        helper.setText(
            "Hello,\nThe monthly report is attached as a PDF.",
            """
            <html>
              <body>
                <h2>Monthly report</h2>
                <p>The detailed report is attached to this email.</p>
              </body>
            </html>
            """
        );

        // 4. Add the file generated in RAM.
        helper.addAttachment(
            "monthly-report.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
        );

        // 5. Send after completing the MIME message.
        mailSender.send(message);
    }
}
```

This example assumes `PdfReportService` can build the report from `rows` and `recipient` has been validated/authorized per business rules. In production sending, handle exceptions in the caller layer to record attempts and manage controlled retries.

Use `MULTIPART_MODE_MIXED` when the email has a body and independent attachments. If the email also has inline images referenced by HTML, consider `MULTIPART_MODE_MIXED_RELATED` and call `setText(...)` before `addInline(...)`; independent attachments are added via `addAttachment(...)`.

## 8. Using InputStreamSource when a re-readable source is needed

`MimeMessageHelper` has overloads accepting `InputStreamSource`. If the data is already in a byte array, you can write:

```java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

byte[] bytes = createFileBytes();

InputStreamSource source =
    () -> new ByteArrayInputStream(bytes);

helper.addAttachment(
    "data.json",
    source,
    "application/json; charset=UTF-8"
);
```

The lambda creates a new stream each time the helper or provider requests to read the data. For an existing byte array, `ByteArrayResource` is more concise and makes the intent clear.

### 8.1. Why not reuse an already-opened InputStream?

Bug-prone pattern:

```java
InputStream input = createInputStream();

InputStreamSource oneShot = () -> input;

helper.addAttachment(
    "report.pdf",
    oneShot,
    "application/pdf"
);
```

This source always returns the exact same stream. After the stream is read to EOF or closed, a subsequent read may return empty data or throw an error. The mail library may need to re-read the content when preparing and sending MIME.

Instead, provide a factory that opens a fresh stream:

```java
InputStreamSource repeatable = () ->
    storage.openNewStream(reportId);
```

`storage.openNewStream(...)` is a hypothetical application API; each call must create an independent stream starting from the beginning. If storage only provides a single-use stream, you can spool the data into memory when small or to a controlled temporary file when large.

### 8.2. ByteArrayResource vs. InputStreamResource

| Resource | Typical behavior | When appropriate |
|---|---|---|
| `ByteArrayResource` | Holds the byte array and creates a fresh stream from the start on each read. | File already in RAM, suitable size. |
| `InputStreamResource` | Typically wraps an existing stream; should not be assumed re-readable. | Single-use sources in APIs not requiring replay; use caution as a mail attachment. |
| `FileSystemResource` | Opens the file from a path when reading is needed. | File exists on disk and can be re-opened. |
| `ClassPathResource` | Opens a resource packaged on the classpath. | Static files inside the application. |
| Custom `InputStreamSource` | Depending on implementation, may return a new stream or a one-shot stream. | Storage/object store or dynamic sources with a re-open API. |

For email attachments, prefer **re-openable sources**. Do not rely on "it worked once in a quick test" to conclude a stream source works in all cases.

## 9. Choosing Content-Type and filename

A MIME part needs an appropriate content type:

| Format | Suggested filename | Content-Type |
|---|---|---|
| PDF | `report.pdf` | `application/pdf` |
| CSV | `report.csv` | `text/csv; charset=UTF-8` |
| JSON | `data.json` | `application/json; charset=UTF-8` |
| XML | `data.xml` | `application/xml; charset=UTF-8` |
| ZIP | `documents.zip` | `application/zip` |
| PNG | `chart.png` | `image/png` |
| JPEG | `photo.jpg` | `image/jpeg` |
| Excel Open XML | `report.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

**Filename, extension, and Content-Type must be consistent with the actual bytes.** You cannot set `application/pdf` on CSV data and expect the recipient to open a PDF.

### 9.1. Choosing clear and safe filenames

Example:

```java
helper.addAttachment(
    "invoice-2026-11.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Avoid directly using arbitrary filenames from users or untrusted data. A filename should:
- contain no path segments such as `../../secret.txt`;
- contain no CR/LF or control characters;
- have an extension matching the format;
- have a reasonable length;
- avoid exposing unnecessary personal data or sensitive internal info.

If Unicode filenames are needed, test how target email clients display the filename. Libraries handle header encoding, though compatibility can vary between older and newer clients.

### 9.2. Content-Type does not verify content

Content-Type is declared metadata. If the input bytes are corrupted or swapped, the header may still say `application/pdf`. When data comes from a file generator, handle exporter exceptions, verify valid output within the generator library's capabilities, and avoid treating a check of the first few bytes as complete validation.

## 10. Memory limits and email size

Attaching from RAM is simple, but it has memory costs.

### 10.1. Base64 makes emails larger

Binary data is usually Base64-encoded in MIME. The encoded payload size increases by about **one-third** over the original bytes, excluding headers, boundaries, newlines, and body content.

| Original data | Approximate Base64 size |
|---:|---:|
| 300 KB | 400 KB |
| 1 MB | 1.33 MB |
| 5 MB | 6.67 MB |
| 10 MB | 13.33 MB |

These are estimates for the Base64 payload only, not the final email size or provider limits. SMTP servers may enforce limits based on message size, account, recipient, or other policies.

### 10.2. RAM usage can exceed the file size

For a single attachment, the data may exist in several forms simultaneously:
- the generator's internal buffer;
- the byte array returned by `toByteArray()`;
- the byte array retained in `ByteArrayResource`;
- internal buffers when Jakarta Mail encodes MIME;
- transport, framework, and JVM buffers.

`ByteArrayOutputStream.toByteArray()` creates a byte copy of the written content, so peak memory can be higher than the file size. Many large attachments generated concurrently by multiple workers can cause heap spikes or `OutOfMemoryError`.

### 10.3. Enforce limits before generating or sending

You should define:
- per-file size limits;
- total attachment size limits;
- attachment count limits;
- limits on concurrent emails generating files;
- recipient/worker limits aligned with provider quotas;
- policy when a file exceeds limits (reject, split, or store in a document repository and send a secure link).

You can check after generating the byte array:

```java
private static final int MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;

if (pdfBytes.length > MAX_ATTACHMENT_BYTES) {
    throw new IllegalArgumentException(
        "File exceeds allowed limit"
    );
}
```

The 5 MB threshold is only an application example, **not a universal Spring or SMTP limit**. In practice, set limits appropriate to your provider after accounting for MIME overhead and body content.

If the file is very large, consider storing it in object storage/a document service with proper access controls and sending a **time-limited link** instead of an attachment. Links also require controlling recipients, expiration, download permissions, and keeping tokens out of logs.

## 11. Security of attached data

In-memory generated data may contain invoices, personal information, internal metrics, or financial records. Protect it from creation until the email is sent:

- Verify the recipient is authorized to receive that exact report/document.
- Include only the data fields necessary for the email's purpose.
- Never log byte arrays, Base64, PDF/CSV contents, or download URLs with tokens.
- Never place secrets, passwords, or access tokens in filenames, headers, or content.
- Validate filenames to prevent header injection and path disclosure.
- Avoid persisting files in caches, dumps, or temp files unnecessarily.
- If the email must encrypt documents at the application level, design encryption and key distribution separately; SMTP TLS only protects hop-by-hop transport, not end-to-end file encryption.
- Maintain a retention policy for copies held by providers and recipient mailboxes.

For CSVs that might be opened in spreadsheets, watch out for **formula injection** when cells contain user data starting with characters that can trigger formulas. Standard CSV quoting does not prevent spreadsheets from executing formulas. Protective policies must match the data type and recipient software.

## 12. Attaching multiple in-memory generated files

You can call `addAttachment(...)` multiple times on the same helper:

```java
helper.addAttachment(
    "summary.csv",
    new ByteArrayResource(csvBytes),
    "text/csv; charset=UTF-8"
);

helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);

helper.addAttachment(
    "chart.png",
    new ByteArrayResource(chartBytes),
    "image/png"
);
```

Each part has its own filename, Content-Type, and byte source. Verify:
- filenames do not collide and confuse the recipient;
- bytes match the declared file type;
- total size is within limits;
- each resource can open a fresh stream;
- one recipient's document is never placed into another recipient's email during batch processing.

If an email is personalized for multiple recipients, you should normally build a separate message for each recipient, with attachments matching their access permissions. Do not group all recipients in `To` and send everyone's individual documents.

## 13. Attachment vs. inline resource

The two methods serve different purposes:

| Method | Purpose | How referenced |
|---|---|---|
| `helper.addAttachment(...)` | Independent attachment for the recipient to open/download | Filename and `Content-Disposition: attachment`. |
| `helper.addInline(...)` | Resource used for rendering HTML content | HTML references via `cid:...`, MIME part has `Content-ID`. |

Attachment example:

```java
helper.setText("The report is attached.");
helper.addAttachment(
    "report.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Inline image example:

```java
helper.setText(
    "Report",
    "<html><body><img src=\"cid:chart\"></body></html>"
);
helper.addInline(
    "chart",
    new ByteArrayResource(chartBytes),
    "image/png"
);
```

For inline resources, follow the order **`setText(...)` before `addInline(...)`** to construct the body and related resources in the proper MIME structure. For independent attachments, adding them after setting the body also keeps the flow easy to read and control.

## 14. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Attachment is 0 bytes | Empty byte array, exporter did not write to output stream | Check exporter output before calling `addAttachment`. |
| Received file cannot be opened | Wrong Content-Type/filename or corrupted generated bytes | Check actual format, exporter, and output bytes. |
| Truncated data at end of file | Stream was partially read, exporter did not finish | Use a source that opens fresh streams; finish exporter before reading bytes. |
| First send works, later sends have empty file | `InputStreamSource` returns the same single-use stream | Use `ByteArrayResource` or a factory creating fresh streams. |
| Attachment missing | Helper is not in multipart mode or code never called `addAttachment` | Enable multipart and inspect MIME source. |
| File has strange name | No separate filename passed or client filename encoding differs | Pass an explicit filename and test clients supporting Unicode. |
| SMTP rejects oversized message | File plus Base64 exceeds quota | Limit size, reduce files, or send a secure link. |
| App heap grows / `OutOfMemory` | Many large reports generated concurrently | Limit concurrency, spool, or use object storage. |
| Filename contains path/odd chars | Using raw filename from user | Normalize and whitelist filenames. |
| CSV shows garbled accents | Wrong encoding or client misdetection | Use UTF-8 and determine whether target software needs a BOM. |
| CSV executes unexpected formulas | Text data starts with special spreadsheet characters | Apply formula-injection policy to text cells. |
| PDF/CSV leaked to wrong recipient | Reusing message or byte data out of scope | Bind data to recipient/job; build separate messages and check permissions. |

### 14.1. Distinguishing file generation errors from email sending errors

```text
Generate report
    | IOException / exporter error
    v
Validate byte[] and size
    | empty / oversized data
    v
Build MimeMessage
    | MessagingException
    v
JavaMailSender.send
    | MailException
    v
SMTP acceptance
    | bounce/delivery event (if supported by provider)
```

Do not retry SMTP to fix a PDF exporter failure. Conversely, if the file was generated properly but SMTP timed out, you may need to retry sending according to an outbox and dedicated idempotency policy.

A successful `send(...)` call generally only tells you the SMTP server accepted the message; it does not prove the file was downloaded or the email was opened by the recipient.

## 15. Inspecting MIME attachments

When diagnosing issues, you can view the raw source of a received email or inspect `MimeMessage` before sending. An illustrative MIME part:

```text
Content-Type: application/pdf; name="monthly-report.pdf"
Content-Disposition: attachment; filename="monthly-report.pdf"
Content-Transfer-Encoding: base64

[BASE64_ENCODED_PDF_BYTES]
```

Headers to compare:
- `Content-Type`: data format.
- `Content-Disposition: attachment`: marks the file as an attachment.
- `filename`: name visible to the recipient.
- `Content-Transfer-Encoding`: how data is represented in MIME.

You can check the number of MIME parts before sending:

```java
message.saveChanges();

Object content = message.getContent();
if (content instanceof jakarta.mail.Multipart multipart) {
    System.out.println("MIME parts: " + multipart.getCount());
}
```

Never print file bytes or Base64 to logs. If you need to verify content, compare hashes in a test environment against known test data, or extract into controlled test memory. Raw MIME can contain sensitive data and should not be retained long-term in production logs.

## 16. Practice exercises

### Exercise 1 — Attaching a byte array
Create a byte array representing small file content, create a `MimeMessage` and multipart `MimeMessageHelper`, and attach it with `ByteArrayResource`. Specify an appropriate filename and Content-Type.

### Exercise 2 — Generating CSV from a list
Write an exporter taking a list of orders, building headers and CSV rows, escaping commas/quotes, converting to a UTF-8 byte array, and sending it. Test customer names containing commas, double quotes, and Vietnamese characters.

### Exercise 3 — Generating PDF via OutputStream
Simulate an exporter with a `write(data, outputStream)` method. Use `ByteArrayOutputStream`, call `toByteArray()` after the exporter finishes, and attach the result. Explain why `toByteArray()` creates a copy of the data.

### Exercise 4 — Testing a single-use stream source
Create an `InputStreamSource` returning the same exhausted `ByteArrayInputStream` instance. Observe the second read. Fix it to a lambda creating `new ByteArrayInputStream(bytes)` on each call or switch to `ByteArrayResource`.

### Exercise 5 — Checking Content-Type
Attach a PDF file while declaring `text/csv`. Explain why a mismatched filename/Content-Type does not convert the file content and can cause email clients to handle it incorrectly.

### Exercise 6 — Size limits
Create 1 MB, 5 MB, and 10 MB payloads; calculate the estimated Base64 payload increase of roughly one-third, then choose an allowed threshold based on provider limits and concurrency. Do not treat these thresholds as default SMTP quotas.

### Exercise 7 — Protecting CSVs
Insert `=HYPERLINK(...)`, `+SUM(...)`, and `@...` values into a text column. Distinguish CSV quoting from formula-injection policy when the file is opened in a spreadsheet.

### Exercise 8 — Multiple recipients
A report contains personal data for each customer. Design a job that creates separate attachments and MIME messages for each authorized recipient; never reuse messages/byte data across scopes.

## 17. Summary

To **attach in-memory generated data** with Spring Framework Mail, produce the file content as a `byte[]` or an `InputStreamSource` capable of opening fresh streams, then pass it to `MimeMessageHelper.addAttachment(...)` with the proper filename and Content-Type. `ByteArrayResource` is a simple choice when the data is already in RAM; `ByteArrayOutputStream` is useful when a file-generation library writes to an `OutputStream`.

This approach eliminates temp-file write/read steps, but requires controlling **size, peak memory, re-readability, recipient authorization, filenames, MIME types, and sensitive content**. For large files or many concurrent jobs, consider controlled spooling or storing documents in object storage and sending a secure link. Only after finalizing the data bytes and MIME structure does `JavaMailSender` send the email via SMTP.

