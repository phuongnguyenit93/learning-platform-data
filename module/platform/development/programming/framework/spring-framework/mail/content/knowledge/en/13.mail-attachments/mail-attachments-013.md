# Checking Viruses and File Types Before Sending in Spring Framework Mail

When sending emails with attachments, an application should never pass every received file straight into `MimeMessageHelper.addAttachment(...)`. A file can carry a spoofed extension, declare an inaccurate MIME type, contain malware, exploit bugs in document viewers, or have a size that exhausts system memory. For transactional emails, invoices, records, or user-uploaded documents, **verifying file types and scanning for malware before sending** is an essential part of attachment handling.

A safe workflow typically includes:

1. Receiving the file and enforcing size limits.
2. Sanitizing the display name; never using the filename as a storage path.
3. Checking the extension against a business allowlist.
4. Detecting the actual format from file contents (signature/content detection).
5. Validating structure, decompressed size, and risk characteristics if required by the format.
6. Placing the data into quarantine or a scan-pending area.
7. Sending the content through an antivirus/malware scanning service.
8. Only when the result is **CLEAN** and policy permits, building an email containing that file.
9. Recording status, hash, and required operational metadata; deleting temporary data per retention policy.

**Spring Mail does not automatically scan for viruses or validate attachment contents.** `MimeMessageHelper` only packages files into MIME messages. The application must enforce controls before calling `addAttachment(...)` and `JavaMailSender.send(...)`.

## 1. Why must files be inspected before sending emails?

Attachments are data that can be opened by recipients or automated systems behind a mailbox. If an application forwards a malicious file, it can become a distribution channel for malware, phishing, or vulnerability exploits.

Common risks:

- **Format spoofing:** a file that is actually a program or script renamed to `.pdf` or `.jpg`.
- **Malware inside documents:** Office macros, embedded scripts, PDFs with active content, or malicious payloads.
- **Archive bombs:** a small ZIP file that decompresses into massive data, deep nesting, or huge file counts.
- **Resource-exhaustion files:** images with enormous pixel dimensions, complex documents, or compressed files that spike CPU/RAM during parsing.
- **Path traversal:** filenames containing paths like `../../...` causing the application to write files to unintended locations if used directly.
- **Disallowed content:** files outside permitted business types, such as sending an HTML or executable file through a PDF-only form.
- **Information leakage:** attachments containing personal data, internal records, or another person's documents.
- **Reader software exploits:** files crafted specifically to exploit vulnerabilities in PDF viewers, Office suites, or preview tools.

Sending emails also amplifies reach: files can be forwarded, archived on mail servers, synced to devices, or processed by DLP/antispam systems. Therefore, checks at both upload time and pre-send time matter.

### Complementary defense layers

| Control | Question answered | Limitation |
| --- | --- | --- |
| Extension allowlist | Does business policy allow this filename type? | Filenames can be spoofed |
| MIME type detection | Does content resemble the declared format? | MIME/signatures do not prove a file is clean |
| File signature / magic bytes | Does the binary header match the format? | Complex formats or polyglots are hard to classify |
| Parser/structural validation | Is the file structurally valid for its format? | A valid file can still contain malware |
| Antivirus/malware scan | Does the engine detect known malware or suspicious patterns? | Does not guarantee catching every novel threat |
| Quarantine and access control | Are unapproved files blocked from use? | Must protect both storage and read paths |
| Size/resource limits | Are oversized files or archive bombs prevented? | Must be enforced across multiple layers |

No single check suffices to declare a file safe. **Allowlist + content detection + malware scan + resource limits + quarantine** form defense in depth.

## 2. Identifying file types with an allowlist

For a specific business workflow, define **only the file types genuinely needed**. For example, an invoice-sending feature may accept only PDFs; a product-photo feature may accept only PNG and JPEG.

Example allowlist:

| Extension | Expected MIME type | Use case |
| --- | --- | --- |
| `.pdf` | `application/pdf` | Invoices, contracts, or reports |
| `.png` | `image/png` | Raster images |
| `.jpg`, `.jpeg` | `image/jpeg` | Raster images |

This is only an example. Pick file types based on real needs rather than enabling dozens of formats simply because a library can read them. If there is no need to send `.exe`, `.js`, `.html`, `.svg`, macro-enabled Office files, or archives, exclude them from the allowlist.

### Allowlists are better than blocklists

A blocklist tries to enumerate forbidden extensions:

~~~text
.exe, .bat, .cmd, .js, .vbs, ...
~~~

Such lists are hard to keep exhaustive given the variety of scripts, nested formats, double extensions, and evasion tricks. An allowlist asks the opposite question: **which formats does the business logic exclusively accept?**

Example:

~~~java
private static final Map<String, String> ALLOWED_TYPES = Map.of(
        ".pdf", "application/pdf",
        ".png", "image/png",
        ".jpg", "image/jpeg",
        ".jpeg", "image/jpeg");
~~~

If a feature only sends PDFs, the allowlist should contain only `.pdf`. Fewer allowed formats mean fewer parsers, fewer special behaviors, and a smaller attack surface.

### Do not trust user-supplied extensions

All of the following names can be misleading:

~~~text
invoice.pdf.exe
invoice.exe.pdf
photo.jpg.html
report.PDF
archive.zip.pdf
document.pdf.
~~~

The application should:

- Normalize extensions with `Locale.ROOT` for consistent case handling.
- Inspect only the final extension per policy; multi-extension names require explicit control.
- Strip or reject control characters, separators, and empty names.
- Never treat a `.pdf` name as proof that the content is PDF.
- Never rename extensions to turn a disallowed format into an allowed one.

Some systems reject names with multiple dots or suspicious patterns outright rather than guessing intent. Rules must fit business needs and be applied consistently.

## 3. Client-declared MIME types are untrustworthy

When uploading via HTTP, browsers or clients typically send:

~~~http
Content-Disposition: form-data; name="file"; filename="invoice.pdf"
Content-Type: application/pdf
~~~

The `Content-Type` in the request is **sender-supplied metadata**. Clients can set it to any string, even when the actual content is not a PDF. Never use `MultipartFile.getContentType()` alone to decide whether a file may be sent.

For example, the actual file is HTML/script while the client declares:

~~~text
filename: invoice.pdf
Content-Type: application/pdf
body: non-PDF content
~~~

If the application checks only those first two fields, the spoofed file slips through.

### Distinguishing three concepts

| Value | Source | Trustworthiness |
| --- | --- | --- |
| Original filename | Request header / multipart | Untrusted; use only as a hint after sanitization |
| Declared Content-Type | Request header | Untrusted; may be logged for diagnostics |
| Detected media type | Content analysis by a detector | Better for classification, though does not prove safety |

**MIME detection is not antivirus.** A file can be a valid PDF and still carry a malicious payload. A PNG with a valid signature can still exploit a parser bug or contain anomalous data.

## 4. Checking file signatures (magic bytes)

Many file formats have characteristic bytes at the beginning or specific offsets. These are commonly called **file signatures** or **magic bytes**. Illustrative examples:

| Format | Common leading signature (hex) |
| --- | --- |
| PDF | `25 50 44 46` (`%PDF`) |
| PNG | `89 50 4E 47 0D 0A 1A 0A` |
| JPEG | `FF D8 FF` |
| ZIP | `50 4B 03 04` (a common ZIP signature) |

These bytes provide preliminary format identification. Do not implement a naive magic-byte list and treat it as a complete parser. Some formats have multiple variants, headers at different offsets, or shared containers.

### Why does ZIP require special handling?

DOCX, XLSX, and PPTX are Office Open XML packages stored inside ZIP containers. Seeing only a ZIP signature may cause a detector to identify `application/zip` instead of the specific Office document type. A parser capable of recognizing container structure is needed if business rules allow Office files.

ZIP files can also contain:

- Multiple child files with their own names and paths.
- Nested files or multi-layer nested archives.
- Entry names containing path traversal.
- Password-encrypted files preventing scanners from reading contents.
- Excessive entry counts or decompressed sizes.

If archives are unnecessary, rejecting ZIP/RAR/7z is simpler. If required, enforce dedicated archive inspection policies capping total decompressed size, entry count, nesting depth, and processing time.

### Using Apache Tika to detect media types

Apache Tika can analyze content to detect formats. Illustrative example with size-bounded data:

~~~java
import org.apache.tika.Tika;

Tika tika = new Tika();
String detectedType = tika.detect(fileBytes);
~~~

Results may be `application/pdf`, `image/png`, `image/jpeg`, or a generic type depending on the data and detector. Choose a Tika version approved for your project and understand the outputs the detector returns. For complex container formats, additional parsers and metadata analysis may be required.

An acceptance policy may simultaneously require:

1. Extension is in the allowlist.
2. Detected media type is in the allowlist.
3. Extension and detected type match each other.
4. File structure passes the appropriate parser/validator.
5. Malware scanner returns a clean result.

If the declared MIME type differs from the detected type, never trust the declared type automatically. Per policy, reject the file, request re-upload, or log the mismatch for investigation. Do not silently rewrite the MIME type and send an unrecognized file.

## 5. Checking filenames and metadata

Filenames typically appear in email MIME headers and recipient interfaces. Never use the raw `MultipartFile.getOriginalFilename()` as a storage path or inject it directly into headers.

### Path traversal risks

Example filenames:

~~~text
../../../../etc/passwd
......Windowswin.ini
/var/app/secrets.txt
~~~

If the application concatenates these names onto a storage directory, files could be written outside the intended area. Even when the goal is only emailing attachments, temporary storage for scanning is still at risk if user-supplied names become paths.

Principles:

- Generate random storage keys or derive them from internal IDs.
- Never use the original filename as the physical filename.
- Keep only a sanitized, length-limited display name.
- Strip slashes, backslashes, control characters, CR/LF, and header-unsafe characters.
- Do not write untrusted filenames into logs if they might contain sensitive data or control characters.

Example extracting a path-stripped display name:

~~~java
static String safeDisplayFilename(String originalName) {
    if (originalName == null || originalName.isBlank()) {
        throw new IllegalArgumentException("Filename is required");
    }

    String normalized = originalName.replace('\\', '/');
    int lastSeparator = normalized.lastIndexOf('/');
    String basename = normalized.substring(lastSeparator + 1).trim();

    if (basename.isBlank()
            || basename.equals(".")
            || basename.equals("..")
            || basename.codePoints().anyMatch(Character::isISOControl)) {
        throw new IllegalArgumentException("Invalid filename");
    }

    if (basename.length() > 120) {
        throw new IllegalArgumentException("Filename is too long");
    }

    return basename;
}
~~~

This is a basic display-name sanitization step, not a full Unicode validator. For cross-platform systems, standardize Unicode normalization, lookalike characters, trailing dots/spaces, and filesystem naming rules. Storage names should still be application-generated IDs.

### Keep CR/LF out of headers

Filenames can end up in MIME `Content-Disposition`. Uncontrolled line breaks can produce invalid headers or cause header injection if libraries mishandle them. Use Spring/Jakarta Mail APIs with sanitized display names; never concatenate raw header strings.

### Hashing to identify exact content

You can compute SHA-256 of the byte stream to identify the file:

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

static String sha256(byte[] bytes) throws Exception {
    byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
    return HexFormat.of().formatHex(digest);
}
~~~

A hash does not tell you whether a file is clean or malicious. It binds scan results to **the exact content version**, detects modified data, and supports auditing without logging entire files. If content changes by a single byte after scanning, the hash changes and the old scan result no longer applies.

## 6. Enforcing size limits before reading the whole file

Do not call `MultipartFile.getBytes()` on every upload without bounds. Large files can consume massive heap, trigger GC pressure, or cause out-of-memory crashes. Enforce limits at multiple layers:

- Reverse proxy / API gateway.
- Spring Boot multipart settings and servlet container.
- Controller/service validation.
- Storage/quarantine quotas.
- Antivirus scanner and parser limits.
- Total size of all attachments in one email.
- SMTP provider and receiving mailbox limits.

Spring Boot configuration example:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 15MB
~~~

This is an illustrative upload limit; actual values must fit business needs, infrastructure, and email limits. `max-request-size` must be large enough for multipart overhead and other fields, yet not overly permissive.

### Emails can be larger than original files

Attachments are usually Base64-encoded in MIME. Base64 expands data by roughly one-third, excluding headers, boundaries, and other content parts. Thus, a 10 MB PDF does not produce an exact 10 MB final email.

If the SMTP provider limits message size, leave adequate headroom. Multiple small attachments can also add up to an oversized email.

### Archive bombs and decompression limits

A ZIP may be tiny in transit yet extract into gigabytes or millions of files. If a scanner or parser extracts archives without limits, it can suffer DoS.

When allowing archives, cap:

| Limit | Purpose |
| --- | --- |
| Compressed archive size | Bounds uploaded data |
| Total decompressed size | Prevents decompression bombs |
| Entry count | Prevents archives with excessive tiny files |
| Archive nesting depth | Caps recursion |
| Maximum compression ratio | Detects anomalous compressed payloads |
| CPU/scan duration | Prevents unbounded processing |
| Entry names and paths | Prevents path traversal inside archives |

If the scanner cannot inspect encrypted archives or nested files, reject them or route them to dedicated handling; **never treat a scanner skipping unreadable content as CLEAN**.

## 7. Scanning for viruses/malware with a dedicated service

Spring applications rarely implement their own antivirus engine. Instead, they integrate with a separately operated scanner service, such as:

- ClamAV daemon or a scanner-protocol-compatible service.
- ICAP antivirus gateway.
- Platform/cloud malware scanning services.
- Organization-managed endpoint/content security products.

Overall architecture:

~~~mermaid
flowchart LR
    A["Upload attachment"] --> B["Validate size + type"]
    B --> C["Quarantine storage"]
    C --> D["Malware scanner"]
    D --> E{"Scan result"}
    E -- "CLEAN" --> F["Approved attachment"]
    E -- "INFECTED" --> G["Reject / quarantine"]
    E -- "ERROR / UNKNOWN" --> H["Hold / retry / alert"]
    F --> I["MimeMessageHelper.addAttachment"]
    I --> J["JavaMailSender.send"]
~~~

The scanner may inspect a byte stream or file via a dedicated protocol. The application needs an adapter to stream data to the scanner and normalize results into an internal model.

### Scanner interface in the application

~~~java
import java.io.IOException;
import java.io.InputStream;

public interface MalwareScanner {

    ScanResult scan(InputStream content) throws IOException;
}

public record ScanResult(
        ScanStatus status,
        String engine,
        String signatureVersion,
        String detectionName
) {
}

public enum ScanStatus {
    CLEAN,
    INFECTED,
    ERROR,
    UNKNOWN
}
~~~

This interface creates a boundary between business code and the scanner vendor. Real adapters call ClamAV, ICAP, or a security service API; authentication, timeouts, protocols, size limits, and error codes depend on the chosen product.

**Never fabricate a CLEAN result when the scanner cannot be reached.** If the scanner times out, is unavailable, returns an unparseable response, or cannot scan an encrypted file, the outcome must be ERROR/UNKNOWN or a pending state per policy.

### Decision rules

| Scanner result | Typical decision |
| --- | --- |
| CLEAN | Can proceed to subsequent approval steps |
| INFECTED | Quarantine/reject; do not attach |
| ERROR | Hold in pending state or reject; never send as clean |
| UNKNOWN | Isolate or require manual handling |

For user-uploaded documents that the system emails externally, the standard safe approach is **fail closed**: if the file cannot be confirmed clean, do not send it. Some workflows may omit the attachment and send an alternative notice, though that decision must be defined upfront.

## 8. Quarantine and scan states

Never place newly uploaded files in a location the sender can immediately read. Separate data zones:

~~~text
upload/
  -> QUARANTINED
       |
       +--> SCANNING
              |
              +--> CLEAN ------> APPROVED
              |
              +--> INFECTED ---> REJECTED / ISOLATED
              |
              +--> ERROR ------> SCAN_PENDING / MANUAL_REVIEW
~~~

State meanings:

| State | Meaning | Allowed to send? |
| --- | --- | --- |
| QUARANTINED | Newly received file, not yet scanned | No |
| SCANNING | Currently being processed by scanner | No |
| CLEAN / APPROVED | Scanner returned clean and other checks passed | Yes, if business policy permits |
| INFECTED / REJECTED | Threat detected or rejected by policy | No |
| ERROR / UNKNOWN | No reliable result obtained | No |
| EXPIRED | Retention elapsed or job expired | No |

### Why is quarantine necessary?

Quarantine prevents an unverified file from being used due to ordering bugs. For instance, an upload endpoint saves the file and immediately fires an email event while antivirus scanning runs asynchronously. If the sender does not check state, the email can leave the system before the scanner finishes.

Only a specific service or role should be allowed to read approved files. The sender account should not have direct read access to the quarantine zone. Once confirmed clean, the system can update the state and grant read access through a separate API or storage location.

### Scan results must bind to the exact content

Do not store just:

~~~text
fileId = 123
scanStatus = CLEAN
~~~

if the file content could be replaced after scanning. Link the result to:

- File ID or object key.
- SHA-256 of the scanned content.
- Size and detected media type.
- Scanner engine and signature/database version.
- Scan timestamp.
- Outcome and detection name (if any).
- Object version or storage generation if using object storage.

Before sending, verify the byte stream being sent has the **exact same hash/version** as the scanned content. This mitigates TOCTOU (time-of-check to time-of-use): a file being replaced after scanning but before attaching.

## 9. Example inspection and scanning pipeline in Java

The following example uses byte arrays for clarity and fits **small, size-bounded files**. For large files, avoid loading everything onto the heap; a later section covers quarantine storage and re-openable streams.

### Approved attachment model

~~~java
public record ApprovedAttachment(
        String filename,
        String contentType,
        byte[] content,
        String sha256
) {
}
~~~

Never construct this object directly from a request. Only the validation/scanning service should be allowed to instantiate it after checks pass.

### Validation and scanning service

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.Locale;
import java.util.Map;

import org.apache.tika.Tika;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class AttachmentInspectionService {

    private static final long MAX_BYTES = 10L * 1024 * 1024;

    private static final Map<String, String> ALLOWED_TYPES = Map.of(
            ".pdf", "application/pdf",
            ".png", "image/png",
            ".jpg", "image/jpeg",
            ".jpeg", "image/jpeg");

    private final Tika tika = new Tika();
    private final MalwareScanner malwareScanner;

    public AttachmentInspectionService(MalwareScanner malwareScanner) {
        this.malwareScanner = malwareScanner;
    }

    public ApprovedAttachment inspect(MultipartFile upload)
            throws IOException {
        if (upload == null || upload.isEmpty()) {
            throw new IllegalArgumentException("Attachment is empty");
        }

        if (upload.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("Attachment is too large");
        }

        String filename = safeDisplayFilename(
                upload.getOriginalFilename());
        String extension = extensionOf(filename);
        String expectedType = ALLOWED_TYPES.get(extension);

        if (expectedType == null) {
            throw new IllegalArgumentException(
                    "File extension is not allowed");
        }

        // Only use getBytes() because this example caps size at 10 MiB.
        byte[] bytes = upload.getBytes();
        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid file size");
        }

        String detectedType = tika.detect(bytes);
        if (!expectedType.equals(detectedType)) {
            throw new IllegalArgumentException(
                    "File content does not match the allowed type");
        }

        ScanResult scan;
        try (ByteArrayInputStream input = new ByteArrayInputStream(bytes)) {
            scan = malwareScanner.scan(input);
        }

        if (scan == null || scan.status() != ScanStatus.CLEAN) {
            throw new IllegalStateException(
                    "Attachment has not passed malware scanning");
        }

        return new ApprovedAttachment(
                filename,
                detectedType,
                bytes,
                sha256(bytes));
    }

    private static String extensionOf(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot <= 0) {
            return "";
        }
        return filename.substring(dot).toLowerCase(Locale.ROOT);
    }
}
~~~

The `safeDisplayFilename(...)` and `sha256(...)` helpers were described earlier; place them in an appropriate utility class or service. This code is an integration example, not a complete antivirus adapter.

Key points to understand:

1. Size is bounded before reading the byte array.
2. Extension is checked against the allowlist.
3. Tika detects media type from content.
4. Extension and detected type must match per business mapping.
5. The scanner receives the exact retained byte array.
6. Only a CLEAN result creates `ApprovedAttachment`.
7. When sending, use the exact scanned byte array; do not re-read a file that could have changed.

In a real system, handle scanner exceptions into a classified ERROR state rather than turning them into CLEAN. Also validate file types using an appropriate parser when required by the format, since media detection only performs preliminary format identification.

### How to handle declared Content-Type?

The sample code does not use `upload.getContentType()` as grounds for approval. You can store that value for auditing or logging mismatches:

~~~java
String clientDeclaredType = upload.getContentType();
String detectedType = tika.detect(bytes);
~~~

If the client declares `application/pdf` yet the detector finds `image/png`, policy may reject the upload. If the client sends `application/octet-stream` yet the actual content is a valid PDF, policy may accept based on the detected type. The key is basing decisions on allowlists and trusted detection rather than client headers alone.

## 10. Attaching approved files to emails with MimeMessageHelper

Once `ApprovedAttachment` is obtained, the sender can attach it:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class ReportMailSender {

    private final JavaMailSender mailSender;

    public ReportMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            ApprovedAttachment attachment)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your report");
        helper.setText(
                "Hello, your report has been inspected and is attached.");

        helper.addAttachment(
                attachment.filename(),
                new ByteArrayResource(attachment.content()),
                attachment.contentType());

        mailSender.send(message);
    }
}
~~~

Here `true` enables multipart; `addAttachment(...)` packages the inspected byte array into the MIME message. **The `addAttachment` method performs no antivirus scanning**. Safety guarantees must be established before the sender receives `ApprovedAttachment`.

A better design keeps the `ApprovedAttachment` constructor package-private or uses a dedicated factory/service so other classes cannot arbitrarily instantiate an object treated as clean. The public Java record in the example is solely to illustrate data; it does not create a security boundary on its own.

## 11. Handling large files with streams and quarantine storage

For large files, `MultipartFile.getBytes()` can spike heap usage. Stream to temporary/quarantine storage, scan the content there, and issue a re-openable resource only after approval.

Overall flow:

~~~text
MultipartFile input stream
        |
        v
Quarantine object / temp file (random key)
        |
        +--> compute SHA-256
        |
        +--> detect media type
        |
        +--> antivirus scan
        |
        v
CLEAN result + hash + object version
        |
        v
Approved storage object
        |
        v
InputStreamSource opens fresh stream
        |
        v
MimeMessageHelper.addAttachment(...)
~~~

### InputStreamSource must be able to open fresh streams

Spring's `MimeMessageHelper.addAttachment(String, InputStreamSource, String)` takes an `InputStreamSource`. The provided resource must be able to open a fresh stream whenever the library needs to read data. Conceptual example:

~~~java
InputStreamSource attachmentSource = () ->
        approvedStorage.openStream(
                attachment.objectKey(),
                attachment.objectVersion());

helper.addAttachment(
        attachment.filename(),
        attachmentSource,
        attachment.contentType());
~~~

This is illustrative code; `approvedStorage.openStream(...)` is an application-defined storage API. Ensure it reads the exact **scanned object version**, not a mutable current object that could be overwritten.

### Do not reuse an already-consumed stream

Scanners typically read a stream to completion. If you pass the exact same `InputStream` that was scanned into `addAttachment`, the stream may be at EOF or closed, causing the email to attach an empty or broken file.

Solution:

- Scan from a dedicated stream opened from the quarantine object.
- Send using a fresh stream from the exact verified object/version.
- Or keep small byte arrays in memory and create a fresh stream from the byte array.
- Never reuse an InputStream already consumed by the scanner.

### Safe temporary files

If temporary files are needed:

- Store in a dedicated directory not served by the web server.
- Generate random application-owned names.
- Grant read/write permissions only to the required process/role.
- Never use the original filename as a path.
- Cap disk space and file counts.
- Delete files upon completion or expiration.
- Never allow senders to access quarantine files prior to the CLEAN state.
- Consider encrypting storage per data policy.

## 12. Asynchronous scanning when handling many files

For systems with heavy uploads or slow scanners, split scanning into an asynchronous job:

~~~mermaid
sequenceDiagram
    participant U as User/API
    participant A as Attachment Service
    participant Q as Quarantine Storage
    participant W as Scan Worker
    participant AV as Antivirus
    participant M as Mail Worker

    U->>A: Upload file
    A->>A: Validate size/name/type
    A->>Q: Store as QUARANTINED
    A-->>U: attachmentId + PENDING_SCAN
    W->>Q: Read exact object version
    W->>AV: Scan content
    AV-->>W: CLEAN / INFECTED / ERROR
    W->>Q: Record scan result and hash
    alt CLEAN
        W->>M: Notify approved attachment
        M->>Q: Open same approved version
        M->>M: Attach and send email
    else INFECTED or ERROR
        W->>Q: Keep isolated / reject
    end
~~~

Advantages:

- Upload requests do not block waiting on slow scanners.
- Scan workers can scale independently.
- Retries can run when the scanner is temporarily unavailable.
- Clear states exist for UI or business tracking.

However, never send the email right after upload simply because an attachment ID exists. The mail worker must check CLEAN status and the matching version/hash before opening the file.

### Scan job states

| State | Typical valid transitions |
| --- | --- |
| PENDING_SCAN | SCANNING or EXPIRED |
| SCANNING | CLEAN, INFECTED, ERROR |
| CLEAN | APPROVED or REVOKED per policy |
| INFECTED | REJECTED / ISOLATED |
| ERROR | RETRY_PENDING or MANUAL_REVIEW |
| APPROVED | ATTACHED / SENT when business workflow finishes |

Never let an ERROR job automatically transition to CLEAN after a timeout. Only a trustworthy scanner result combined with other checks permits approval.

## 13. File types with special risks

### PDF

PDF is a common format for invoices and documents, yet can contain JavaScript, embedded files, launch actions, forms, embedded payloads, or complex structures. Antivirus scanning is one layer; if business rules only require simple PDF documents, use a parser to validate structure and apply extra policies for active content. Never strip PDF content by editing raw byte streams without a proper library.

### Office documents

DOCX/XLSX/PPTX can be ZIP containers. Macro-enabled variants like DOCM/XLSM behave differently and must be clearly distinguished. If macros are unnecessary, reject macro-enabled types. If Office documents are permitted, scanners must understand containers and enforce extraction limits; never check only the `.docx` extension.

### SVG and HTML

SVG is XML that can contain scripts, external resource references, or complex payloads. HTML can contain scripts, forms, phishing links, and active content. If only images are needed, prefer PNG/JPEG over allowing arbitrary SVGs. Never send HTML files as harmless attachments merely because they end in `.html`.

### Images

Images can have huge pixel dimensions despite small compressed files, sensitive metadata (e.g. EXIF/GPS), or structures that cause parsers to consume excessive resources. If processing or thumbnailing, cap width, height, total pixels, and decode time. If stripping metadata, use an appropriate imaging library and **re-scan the content after transformation**.

### Archives

Archives can hold executables, scripts, nested files, traversal paths, or oversized compressed payloads. Accept archives only if business rules require them; scanners must inspect inner entries and clearly report encrypted/unscannable files.

### Password-protected documents

Scanners may be unable to read contents inside encrypted PDFs, Office files, or ZIPs. If the engine returns "encrypted" or "cannot inspect", never treat it as clean by default. Reject it, request an unencrypted version through a controlled channel, or route to manual review per policy.

## 14. Combining file-type checks, antivirus, and business policies

An attachment approval decision should combine multiple conditions:

~~~text
ACCEPT =
    size within limit
    AND extension is allowed
    AND detected media type is allowed
    AND extension matches detected type
    AND structural validation passes (when required)
    AND archive/resource limits pass (when applicable)
    AND malware scan result == CLEAN
    AND attachment belongs to this user/transaction
~~~

This is conceptual logic. Each workflow may add rules: whether the sender is authorized to attach that document, whether it belongs to the right order/record, whether the recipient is allowed to receive it, and whether this email type permits sending sensitive documents.

### Final MIME type used in the email

Once the actual type is verified:

~~~java
helper.addAttachment(
        approved.filename(),
        new ByteArrayResource(approved.content()),
        approved.contentType());
~~~

Set content type to **the detected and approved format**, never taking the client-declared header directly. The display filename must also be sanitized.

If the detector only returns `application/octet-stream` or fails to identify the type, never assign `application/pdf` just because the filename ends in `.pdf`. Handle per policy: reject or use a more capable parser/detector.

## 15. Spring Boot integration: layers of responsibility

A design can separate into:

| Component | Responsibility |
| --- | --- |
| Upload controller | Receives multipart requests, enforces authorization, returns status |
| Attachment policy | Extension/type allowlists, size caps, business rules |
| Content detector | Detects media type from byte stream |
| Structural validator | Checks format-specific structure and limits |
| MalwareScanner adapter | Calls antivirus/ICAP/cloud scanner |
| Quarantine storage | Stores unapproved content |
| Attachment approval service | Records CLEAN status, hash, and object version |
| Mail service | Accepts only approved attachments and sends |

For instance, a controller should not scan and send in the same method if scanning can take a long time. The controller can create an attachment job and return status:

~~~java
@PostMapping("/attachments")
public ResponseEntity<AttachmentSubmission> upload(
        @RequestParam("file") MultipartFile file) {

    AttachmentSubmission submission = attachmentService.submit(file);

    return ResponseEntity.accepted().body(submission);
}
~~~

This snippet assumes `attachmentService.submit(...)` performs basic checks, saves to quarantine, and starts a scan job; `AttachmentSubmission` is an application-defined DTO. The endpoint needs authorization, CSRF protection where appropriate, rate limiting, and infrastructure multipart limits.

### Mail service accepts approved data types

Instead of accepting `MultipartFile` directly:

~~~java
public void sendReport(
        String recipient,
        ApprovedAttachment attachment) {
    // Build MimeMessage and attach the approved attachment.
}
~~~

This clarifies the contract: the sender receives only data that passed inspection/scanning. In large systems, pass the approved object ID and have the mail worker re-check status and hash before opening the stream.

## 16. Scanner failures and fail-closed policy

Antivirus services are also dependencies that can fail:

- Network timeouts.
- Scanner daemon not running.
- Outdated signature database.
- File exceeds scanner size limits.
- Encrypted format or unsupported parser.
- Scanner returns an invalid response.
- Scan queue backed up or out of capacity.

Never map any of these cases to CLEAN. Distinguish them:

| Outcome | Handling |
| --- | --- |
| CLEAN | Proceed if other policies pass |
| INFECTED | Reject, quarantine, and raise appropriate alerts |
| TIMEOUT | Keep pending, retry with backoff, or require intervention |
| UNAVAILABLE | Do not send file; report scanner status |
| UNSUPPORTED | Reject or route to manual review |
| ENCRYPTED / CANNOT_INSPECT | Never treat as clean; handle per policy |
| MALFORMED_RESPONSE | UNKNOWN; log adapter error and investigate |

### Fail-closed and user experience

Fail-closed does not mean the entire application must crash. You can:

- Save the upload in scan-pending state.
- Display "The file is being inspected".
- Let the user continue tasks unrelated to the attachment.
- Send the email only after scanning finishes.
- If scanning stays failed, inform the user the file could not be sent yet and guide them to re-upload or contact support.

For emails without attachments, workflows can proceed if independent of the file. However, **never send an unverified file** just to stay on schedule.

### Scanner timeouts and retries

Scanner retries should include:

- Separate connect timeouts and processing timeouts.
- Maximum attempt counts.
- Exponential backoff and jitter.
- Dead-letter queues for jobs exceeding attempt limits.
- Alerts when the scanner stays unavailable for extended periods.
- Avoiding duplicate sends or infinite re-scanning of the same file.

Scan results can be cached by hash and engine/signature-database version, provided there is an expiration and a re-scan policy when signatures update or risk levels change. Never cache CLEAN indefinitely for files that might later be flagged.

## 17. TOCTOU risk: sending the exact scanned file

A subtle bug:

1. The application scans file A and gets CLEAN.
2. The file on storage is replaced with file B.
3. The sender reads file B and attaches it.

The CLEAN scan result belonged to A, yet the email sends B. This is a **time-of-check to time-of-use (TOCTOU)** bug.

Reduce risk by:

- Creating immutable objects or version IDs after upload.
- Computing SHA-256 while reading the content for scanning.
- Storing the hash alongside the scan result.
- Having the sender read only that exact object version.
- Verifying the hash while streaming the send if architecture permits.
- Disallowing in-place updates to approved objects; edits create a new object/version requiring re-scanning.

If the application transforms a file after scanning (e.g. image resizing, PDF conversion, metadata stripping), the transformed output is a new file and should be **re-checked and re-scanned** before sending.

## 18. Privacy and file retention

Quarantines and scanners may handle documents containing personal or confidential data. You should:

- Encrypt data at rest and in transit per infrastructure policy.
- Restrict read permissions on quarantine and approved storage.
- Never serve quarantine files over public URLs.
- Use time-limited signed URLs with authorization if downloads are needed.
- Never log file contents, document passwords, or full personal data.
- Set retention periods for clean files, rejected files, and scan-failed files.
- Delete temporary copies after sending or job expiration per policy.
- Record audit events for upload, scan, approval, rejection, and send.

Third-party scanners may receive copies of files. Before integrating, verify storage regions, data processing locations, retention windows, access controls, and organizational security requirements. Never send sensitive data to an unauthorized service merely because its scanner API is convenient.

## 19. Testing the attachment pipeline

Tests should cover both success and failure cases:

| Case | Expected outcome |
| --- | --- |
| Valid PDF, detected type PDF, scanner CLEAN | Eligible for approval |
| Executable renamed to `.pdf` | Rejected because detected type mismatches |
| Client declares wrong MIME | Never trust declaration; detect/compare and enforce policy |
| Extension not in allowlist | Rejected before scan or per policy |
| Empty file | Rejected |
| Oversized file | Rejected before reading all bytes into heap |
| Scanner returns INFECTED | Quarantined/rejected, not sent |
| Scanner timeout/unavailable | ERROR/PENDING state, not sent |
| Encrypted/uninspectable ZIP | Never treated as CLEAN |
| File modified after scan | Hash/version mismatch, requires re-scan |
| Filename has path traversal or CR/LF | Rejected or safely sanitized |
| Approved attachment | Email uses exact content bytes, filename, and detected MIME type |

### Unit testing with a mock scanner

In tests, replace the real antivirus with a mock to test service decisions:

~~~java
when(malwareScanner.scan(any(InputStream.class)))
        .thenReturn(new ScanResult(
                ScanStatus.CLEAN,
                "test-engine",
                "test-signatures",
                null));
~~~

This test only verifies application flow when the scanner returns CLEAN; it does not prove a real antivirus works. Integration tests against a test scanner instance or controlled environment are needed to verify protocols, timeouts, size caps, and real result handling.

### Verifying attachments in test emails

After creating `MimeMessage`, inspect the MIME tree or send to an SMTP capture server to confirm:

- The attachment has the expected sanitized display name.
- Content-Type matches the detected type.
- Byte content/hash matches the scanned file.
- No file in PENDING/ERROR/INFECTED state is attached.
- Final email size stays within limits.

Never send real malicious test files to user mailboxes. When testing scanner detection, use dedicated test files recommended by your scanner vendor, such as EICAR in an isolated test environment, per organizational security policy.

## 20. Common mistakes

### Checking only the file extension

```java
if (filename.endsWith(".pdf")) {
    helper.addAttachment(filename, file);
}
```

This does not verify actual content, scan for malware, enforce resource limits, or check user permissions. Extensions are merely an input check within an allowlist.

### Trusting `MultipartFile.getContentType()` alone

Client-declared Content-Type can be spoofed. Use content detection from the byte stream and corresponding policies; antivirus scanning is still required.

### Scanning one file yet sending another

If scanning reads a temporary copy while the sender reads a mutable path, the scan result no longer binds to the sent bytes. Use immutable objects/versions and hashes.

### Sending anyway when the scanner is unreachable

Never treat timeout/unavailable as CLEAN. Hold the file pending or reject attaching until a reliable result arrives.

### Calling `getBytes()` on unbounded files

This can exhaust the heap. Enforce limits before reading; for large files, stream to quarantine storage and open fresh streams for scanning and sending.

### Sending ZIPs without inspecting contents

ZIPs can hide executables, nested archives, encrypted files, or archive bombs. Permit them only when business rules require and scanners/policies inspect inner contents.

### Using the original filename as a path

This risks path traversal and file overwrites. Storage names must be application-generated; display names must be sanitized separately.

### Treating a valid format as a clean file

Magic bytes or parsers verifying format do not replace antivirus. A valid PDF can still contain malicious payloads.

### Scanning before transformation then sending the transformed file

If you resize, convert, or edit a file after scanning, the hash and content changed. Re-scan the final version that will actually be sent.

### Skipping files the scanner cannot read

Encrypted or unsupported does not mean clean. Route to UNKNOWN/ERROR or reject per policy.

## 21. Pre-send attachment processing workflow

An applicable workflow:

1. Authenticate user and verify permission to attach the document to the transaction.
2. Check whether the request/file is empty or exceeds limits.
3. Sanitize the display name and generate a random storage ID.
4. Check extension against the allowlist.
5. Read/stream into quarantine, compute hash, and detect media type.
6. Compare extension, detected type, and format policy.
7. Validate structure, archive limits, and parser-specific rules if needed.
8. Send the file to the antivirus scanner; receive CLEAN/INFECTED/ERROR/UNKNOWN.
9. Approve only when all conditions pass and the result binds to the exact hash/version.
10. Mail worker verifies approved status, reads the exact object version, and attaches via `MimeMessageHelper`.
11. Send via `JavaMailSender` and record submission status.
12. Delete temporary/quarantine files per retention and audit policies.

### Final decision table

| Condition | Decision |
| --- | --- |
| Disallowed format | Reject |
| Extension and detected type mismatch | Reject or manual review |
| Invalid structure | Reject |
| Size/decompression exceeds limit | Reject |
| Scanner detects malware | Isolate / reject |
| Scanner unavailable | Pending / reject; do not send |
| Scanner returns CLEAN and hash/version match | Eligible to approve |
| File modified after scan | Re-scan |
| Attachment approved and recipient authorized | Eligible for MIME message |

## 22. Self-check questions

**1. Why is checking only the file extension insufficient?**

Because filenames can be renamed. A `.pdf` file can hold non-PDF content; content-based media type detection and malware scanning are required.

**2. Can `MultipartFile.getContentType()` be trusted?**

No. It is a client-declared value that can be wrong or forged. Use a content detector and allowlist.

**3. Do magic bytes prove a file is clean?**

No. They only assist with preliminary format identification. A format-valid file can still contain malware or parser exploits.

**4. Why use an allowlist?**

Because business workflows only need a specific set of file types; an allowlist shrinks the attack surface far better than trying to enumerate every dangerous format.

**5. If the scanner times out, can the file be treated as CLEAN?**

No. A timeout is ERROR/UNKNOWN. Under safe policies, the file must remain pending or be rejected, never sent.

**6. Why must files be quarantined?**

To prevent unscanned files from being read and sent by a sender or another user before results arrive.

**7. Why is a post-scan hash needed?**

To bind the CLEAN result to the exact byte content. If the file changes after scanning, it must be scanned again.

**8. Can `getBytes()` be used for all uploaded files?**

No. It loads the entire file onto the heap. Use it only with small size caps; large files should stream to storage and open fresh streams for scanning and sending.

**9. Can a ZIP be considered safe when its signature is valid?**

No. You must check entries, nested archives, encrypted files, path traversal, and decompression limits—or reject archives if business rules do not need them.

**10. If an image is resized after scanning, does it need to be re-scanned?**

Yes. The final content differs from the scanned byte stream, so the previous CLEAN result no longer applies.

**11. Does `MimeMessageHelper.addAttachment(...)` scan for viruses automatically?**

No. It only adds content to the MIME message. Scanning and approval must happen beforehand.

**12. Why check the total email size?**

Base64 makes attachments larger than raw files and MIME adds overhead. Multiple files together can exceed SMTP provider limits.

## Conclusion

**Virus and file-type checks must occur before an attachment is placed into an email.** Spring Framework Mail provides `MimeMessageHelper.addAttachment(...)` to package files, not to validate formats or scan for malware. Use business allowlists, byte-based media-type detection, structural checks and resource limits, antivirus scanning, quarantine for pending files, and approve only when the scanner returns CLEAN for the exact hash/version. When sending, use the exact approved content, sanitized display name, and verified MIME type. If the scanner fails, the file is encrypted, or it cannot be inspected, never assume it is clean. **A multi-layered inspection pipeline prevents unsafe files from spreading via email and keeps clear boundaries between upload, scanning, approval, and SMTP delivery.**
